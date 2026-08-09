#!/usr/bin/env python3
# (duplicate) — exists because it imports platform-specific config.
#
# !! ITS CONTENTS ARE NOT A COPY. Verified 2026-08-09 by symbol-level sweep: this
# file has diverged STRUCTURALLY from the source named below, and not every
# divergence is documented. Do not assume a symbol here behaves as its namesake
# does there — and note that a symbol may be ABSENT here entirely. That is exactly
# how A22 happened: BearerAuthMiddleware dropped JWT validation, scope enforcement
# and the 413 guard while this header claimed a config-only difference.
# See doc/DUPL_DIVERGENCE_SWEEP_2026-08-09.md.
# Logic lives in mcp_server/priority_guardian/server.py.
# Post-OpenAI-approval refactor: move shared logic to mcp_server/shared/
# with config injection and delete this file.

"""
Priority Guardian Claude MCP Server.

Infrastructure-only server: middleware, discovery routes, app factory, entrypoint.
Tool handlers are in tools/, dispatch logic is in handlers/tools_dupl.py.

Usage (factory mode - recommended for production):
    uvicorn mcp_server.priority_guardian_claude.server_dupl:create_app --factory --host 0.0.0.0 --port $PORT

Or (direct mode - for local development):
    python -m mcp_server.priority_guardian_claude.server_dupl
"""

import os
import time
import uuid
from pathlib import Path

# Minimal imports at module level for fast startup
# Heavy imports are deferred to create_app() for faster port binding
import structlog

logger = structlog.get_logger(__name__)


# ============================================================================
# Middleware Classes (no heavy imports needed)
# ============================================================================

class LifespanMiddleware:
    """
    ASGI middleware to handle cleanup on server shutdown.

    Intercepts ASGI lifespan events to run cleanup when the server shuts down.
    This ensures the HTTP client is closed properly to prevent connection leaks.
    """

    def __init__(self, app, cleanup_func):
        self.app = app
        self.cleanup_func = cleanup_func

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            async def receive_wrapper():
                message = await receive()
                return message

            async def send_wrapper(message):
                if message["type"] == "lifespan.shutdown.complete":
                    await self.cleanup_func()
                await send(message)

            await self.app(scope, receive_wrapper, send_wrapper)
        else:
            await self.app(scope, receive, send)


class RequestLoggingMiddleware:
    """
    ASGI middleware to log all HTTP requests with structured fields.

    Logs: method, path, status_code, client_ip, user_agent, origin,
    response_time_ms, service.

    Must be the outermost middleware to capture all requests including
    those short-circuited by HeadMcpMiddleware.
    """

    def __init__(self, app, service_name: str):
        self.app = app
        self.service_name = service_name

    async def __call__(self, scope, receive, send):
        # Only log HTTP requests, skip lifespan/websocket
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = time.monotonic()
        method = scope.get("method", "UNKNOWN")
        path = scope.get("path", "/")

        # Extract headers
        headers = {name.decode("utf-8").lower(): value.decode("utf-8")
                   for name, value in scope.get("headers", [])}

        # Get client IP (X-Forwarded-For first, then ASGI client)
        client_ip = headers.get("x-forwarded-for", "").split(",")[0].strip()
        if not client_ip:
            client = scope.get("client")
            client_ip = client[0] if client else "unknown"

        # Get User-Agent (truncated to 200 chars)
        user_agent = headers.get("user-agent", "")[:200]

        # Get Origin header
        origin = headers.get("origin", "")

        # Capture response status code
        status_code = 0

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            # Calculate response time
            response_time_ms = round((time.monotonic() - start_time) * 1000, 2)

            # Build log entry
            log_data = {
                "method": method,
                "path": path,
                "status_code": status_code,
                "client_ip": client_ip,
                "user_agent": user_agent,
                "response_time_ms": response_time_ms,
                "service": self.service_name,
            }
            if origin:
                log_data["origin"] = origin

            # Choose log level based on status code
            if status_code >= 500:
                logger.error("http.request", **log_data)
            elif status_code >= 400:
                logger.warning("http.request", **log_data)
            else:
                logger.info("http.request", **log_data)


class OriginValidationMiddleware:
    """
    ASGI middleware to validate Origin header on /mcp requests.
    Anthropic submission requirement per review-criteria checklist.
    Only applied to /mcp path — discovery and OAuth proxy routes unaffected.
    No Origin header = allowed (server-to-server, Claude's MCP client uses python-httpx which doesn't send Origin).
    Unknown Origin = 403.
    """

    def __init__(self, app, allowed_origins: list[str]):
        self.app = app
        self._allowed_origins = set(allowed_origins)

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] == "http"
            and scope.get("method") in ("GET", "POST", "DELETE")
            and scope.get("path") == "/mcp"
        ):
            origin = None
            for name, value in scope.get("headers", []):
                if name == b"origin":
                    origin = value.decode("utf-8", errors="replace")
                    break

            if origin is not None and origin not in self._allowed_origins:
                logger.warning(
                    "origin.validation.rejected",
                    origin=origin,
                    path=scope.get("path"),
                )
                body = b'{"error": "forbidden", "error_description": "Origin not allowed"}'
                await send({
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"cache-control", b"no-store"),
                    ],
                })
                await send({
                    "type": "http.response.body",
                    "body": body,
                })
                return

        await self.app(scope, receive, send)


class HeadMcpMiddleware:
    """
    ASGI middleware to handle HEAD /mcp requests.

    OpenAI's reachability probe may send HEAD requests to /mcp.
    FastMCP returns 405 for HEAD (only allows GET, POST, DELETE).
    This middleware intercepts HEAD /mcp and returns 200 to pass connectivity checks.

    Middleware positioning: inside RequestLoggingMiddleware (so HEAD /mcp requests
    are logged), outside MCPContentTypeAndAcceptFixMiddleware (short-circuits before
    header processing for efficiency).
    """

    def __init__(self, app, allowed_origins: list[str] | None = None):
        self.app = app
        # Store allowed origins for CORS header
        # If None or empty, defaults to "*"
        self.allowed_origins = allowed_origins

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] == "http"
            and scope.get("method") == "HEAD"
            and scope.get("path") == "/mcp"
        ):
            # Build CORS origin header
            # Check if request has Origin header and if it's in allowed list
            origin_header = b"*"
            if self.allowed_origins:
                for name, value in scope.get("headers", []):
                    if name == b"origin":
                        request_origin = value.decode("utf-8")
                        if request_origin in self.allowed_origins:
                            origin_header = value
                        break

            # Return 200 with empty body
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"cache-control", b"no-store"),
                    (b"access-control-allow-origin", origin_header),
                    (b"vary", b"Origin"),
                ],
            })
            await send({
                "type": "http.response.body",
                "body": b"",
            })
            return

        await self.app(scope, receive, send)


class BearerAuthMiddleware:
    """
    ASGI middleware to enforce Bearer token VALIDITY on /mcp requests.

    When Claude initiates connector creation, it probes /mcp without a token.
    FastMCP cannot handle unauthenticated MCP protocol requests gracefully —
    it closes the internal memory stream, producing a ClosedResourceError
    instead of a clean HTTP 401. Claude interprets the broken connection
    as a DCR failure.

    FastMCP streamable HTTP uses:
    - GET /mcp for SSE stream initiation
    - POST /mcp for messages
    - DELETE /mcp for session close

    This middleware intercepts GET/POST/DELETE /mcp requests with no
    Authorization header and returns a standards-compliant HTTP 401 with
    WWW-Authenticate challenge BEFORE FastMCP sees the request. Claude
    reads the WWW-Authenticate header, follows the resource_metadata pointer
    to /.well-known/oauth-protected-resource, discovers the AS, and initiates DCR.

    A22: presence alone is not enough. An EXPIRED token carries a header, so a
    presence-only gate let it through to tool dispatch, which answers with an HTTP
    200 carrying isError=True. Claude does not honour a WWW-Authenticate header on
    a 200, so no refresh was triggered. Every request that reaches /mcp with a
    header now has its token validated here, and only here does a 401 remain
    possible — once FastMCP has the message, the response is already destined
    to be a 200.

    Three outcomes:
    - no header, bad format, or invalid/expired token -> 401 + WWW-Authenticate
    - JWKS unreachable with no usable cache             -> 503, no challenge
    - valid token                                        -> passes through unchanged

    Positioning: between HeadMcpMiddleware and MCPContentTypeAndAcceptFixMiddleware.
    """

    def __init__(self, app, www_authenticate_value: str):
        self.app = app
        self.www_authenticate_value = www_authenticate_value

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] == "http"
            and scope.get("method") in ("GET", "POST", "DELETE")
            and scope.get("path") == "/mcp"
        ):
            # Check for Authorization header
            has_auth = any(
                name == b"authorization"
                for name, _ in scope.get("headers", [])
            )

            if not has_auth:
                # Return 401 with WWW-Authenticate challenge
                # Claude reads this and initiates OAuth discovery + DCR
                # Must intercept GET/POST/DELETE - FastMCP streamable HTTP uses:
                # - GET for SSE stream initiation
                # - POST for messages
                # - DELETE for session close
                body = b'{"error": "unauthorized", "error_description": "Bearer token required"}'
                await self._send_challenge(send, 401, body)
                return

            # ---- A22: VALIDATE the token, do not merely detect the header ----
            #
            # Presence alone was the defect. An EXPIRED token carries a header, passed
            # this gate, reached tool dispatch, and came back as CallToolResult(
            # isError=True) — an HTTP 200. Claude does not honour a WWW-Authenticate
            # header on a 200, so no refresh was triggered and the user saw
            # "Authentication required. Please connect your account." where a re-auth
            # prompt belongs. Token expiry mid-session is routine, not an edge case.
            #
            # This check MUST live here rather than at dispatch. Per the lazy-auth
            # source: "the check has to happen before the JSON-RPC message reaches the
            # MCP SDK. Once a tool handler is running, its return value is already
            # destined to be wrapped in a 200 response."
            #
            # Imported lazily: this module is imported during app construction and
            # mcp_auth_dupl pulls in config; a module-level import here would couple
            # middleware definition to auth-module import order.
            import jwt

            from mcp_server.priority_guardian_claude.mcp_auth_dupl import (
                extract_bearer_token,
                validate_jwt,
            )

            auth_header = next(
                (value.decode("latin-1") for name, value in scope.get("headers", [])
                 if name == b"authorization"),
                None,
            )
            token = extract_bearer_token(auth_header)

            if not token:
                # Wrong scheme (Basic ...), or "Bearer" with nothing after it.
                # A22-3 classes 1 and 2: a 401, never a 500.
                body = b'{"error": "invalid_token", "error_description": "Invalid Authorization header format"}'
                await self._send_challenge(send, 401, body)
                return

            try:
                await validate_jwt(token, str(uuid.uuid4()))
            except jwt.PyJWTError:
                # EVERY PyJWT error is a TOKEN problem: expired, bad signature, wrong
                # issuer or audience, missing/unknown kid. jwt.PyJWTError is the base of
                # both ExpiredSignatureError and InvalidTokenError, which validate_jwt
                # re-raises. 401 tells Claude to re-authenticate, which is the correct
                # and achievable remedy.
                body = b'{"error": "invalid_token", "error_description": "Token validation failed"}'
                await self._send_challenge(send, 401, body)
                return
            except Exception:
                # NOT an auth failure — the SERVER could not validate. The realistic
                # cause is JWKS unavailable with no usable cache, which fetch_jwks
                # raises as a bare Exception after its stale-cache fallback is exhausted.
                #
                # Deliberately 503, NOT 401. A 401 here would tell Claude to
                # re-authenticate against a server that cannot validate anything —
                # producing a re-auth loop rather than a recovery. It is also not a 500:
                # this is a known, named, transient condition, and Starlette's default
                # 500 for an unhandled exception is exactly what A22-3 exists to prevent.
                #
                # No WWW-Authenticate: there is nothing for the client to re-auth against.
                body = b'{"error": "server_error", "error_description": "Unable to validate credentials"}'
                await send({
                    "type": "http.response.start",
                    "status": 503,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"cache-control", b"no-store"),
                    ],
                })
                await send({"type": "http.response.body", "body": body})
                return

        await self.app(scope, receive, send)

    async def _send_challenge(self, send, status: int, body: bytes) -> None:
        """Emit a 401 carrying the single, shared WWW-Authenticate challenge.

        One construction, injected at build time and already correct — it carries
        resource_metadata and scope="pg.access" from SCOPES_SUPPORTED. Two
        constructions of one challenge is the divergence problem.
        """
        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", self.www_authenticate_value.encode()),
                (b"cache-control", b"no-store"),
            ],
        })
        await send({"type": "http.response.body", "body": body})


class MCPContentTypeAndAcceptFixMiddleware:
    """
    Fix Claude -> FastMCP header mismatch and capture Authorization header.

    Header fixes:
    - Claude sends Content-Type: application/octet-stream -> application/json
    - Claude sends Accept: */* -> text/event-stream, application/json

    Authorization capture:
    - Extracts Authorization header from HTTP request
    - Sets it in request_context.auth_header_var for tool handlers
    """

    def __init__(self, app, auth_header_var):
        self.app = app
        self.auth_header_var = auth_header_var

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("method") == "POST":
            if scope.get("path") == "/mcp":
                new_headers = []
                modified = False
                auth_header = None

                for name, value in scope["headers"]:
                    if name == b"content-type" and b"application/octet-stream" in value:
                        value = b"application/json"
                        modified = True

                    if name == b"accept":
                        value = b"text/event-stream, application/json"
                        modified = True

                    if name == b"authorization":
                        auth_header = value.decode("utf-8")

                    new_headers.append((name, value))

                if modified:
                    scope = dict(scope)
                    scope["headers"] = new_headers

                if auth_header:
                    token = self.auth_header_var.set(auth_header)
                    try:
                        await self.app(scope, receive, send)
                    finally:
                        self.auth_header_var.reset(token)
                    return

        await self.app(scope, receive, send)


# ============================================================================
# Application Factory
# ============================================================================

def create_app():
    """
    Create the ASGI application.

    This is the main entry point for uvicorn --factory mode.
    All heavy imports are done here (not at module level) so that
    uvicorn can bind to the port quickly before loading dependencies.
    This is critical for Render's free tier port scan timeout.
    """
    # Import heavy dependencies here, not at module level
    from mcp.server.fastmcp import FastMCP
    from mcp import types as mcp_types
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse, PlainTextResponse, HTMLResponse
    from starlette.routing import Route

    from mcp_server.priority_guardian_claude.config import (
        MCP_SERVER_URL,
        MCP_RESOURCE_URL,
        OAUTH_ISSUER_URL,
        BACKEND_URL,
        CORS_ALLOWED_ORIGINS,
        SCOPES_SUPPORTED,
        IS_DEV,
    )
    from urllib.parse import urlparse as _urlparse
    _mcp_origin = f"{_urlparse(MCP_SERVER_URL).scheme}://{_urlparse(MCP_SERVER_URL).netloc}"
    # Per MCP spec: include scope in WWW-Authenticate to help Claude
    # understand required permissions during the discovery path
    _scopes = " ".join(SCOPES_SUPPORTED)
    WWW_AUTHENTICATE_VALUE = (
        f'Bearer resource_metadata="{_mcp_origin}/.well-known/oauth-protected-resource/mcp", '
        f'scope="{_scopes}"'
    )
    from mcp_server.priority_guardian_claude.discovery_dupl import (
        openid_configuration,
        oauth_authorization_server,
        oauth_protected_resource,
    )
    from mcp_server.priority_guardian_claude.http_client_dupl import cleanup_http_client
    from mcp_server.priority_guardian_claude.mcp_auth_dupl import cleanup_jwks_cache
    from mcp_server.priority_guardian.request_context import auth_header_var
    from mcp_server.priority_guardian_claude.handlers.tools_dupl import call_tool_request
    from mcp_server.priority_guardian_claude.handlers.resources_dupl import (
        list_resources,
        list_resource_templates,
        handle_read_resource,
    )

    # Log resolved config at startup
    logger.info(
        "mcp.server.startup",
        version="REFACTOR_V2",
        server_file=os.path.abspath(__file__),
        BACKEND_URL=BACKEND_URL,
        OAUTH_ISSUER_URL=OAUTH_ISSUER_URL,
        MCP_SERVER_URL=MCP_SERVER_URL,
        PORT=os.getenv("PORT"),
    )

    # Warn if localhost URLs are used
    if "localhost" in OAUTH_ISSUER_URL:
        logger.error(
            "oauth.config.localhost_detected",
            message="OAUTH_ISSUER_URL contains localhost - Claude OAuth will fail!",
            OAUTH_ISSUER_URL=OAUTH_ISSUER_URL,
        )

    if "localhost" in MCP_SERVER_URL:
        logger.error(
            "oauth.config.localhost_detected",
            message="MCP_SERVER_URL contains localhost - Claude OAuth will fail!",
            MCP_SERVER_URL=MCP_SERVER_URL,
        )

    # -------------------------------------------------------------------------
    # Create FastMCP instance and register handlers
    # -------------------------------------------------------------------------
    # stateless_http=True: Each request is self-contained, authenticated via JWT.
    # This avoids session ID issues on deploy (server restart clears in-memory sessions).
    mcp = FastMCP("priority-guardian-claude-mcp", streamable_http_path="/mcp", stateless_http=True)

    @mcp._mcp_server.list_resources()
    async def _list_resources():
        return await list_resources()

    @mcp._mcp_server.list_resource_templates()
    async def _list_resource_templates():
        return await list_resource_templates()

    # Register read_resource handler directly (same pattern as ChatGPT server)
    mcp._mcp_server.request_handlers[mcp_types.ReadResourceRequest] = handle_read_resource

    @mcp._mcp_server.list_tools()
    async def _list_tools():
        from mcp_server.priority_guardian_claude.tools_list_dupl import list_tools_for_claude
        return await list_tools_for_claude()

    mcp._mcp_server.request_handlers[mcp_types.CallToolRequest] = call_tool_request

    # -------------------------------------------------------------------------
    # OAuth Discovery Endpoints
    # -------------------------------------------------------------------------
    async def wellknown_openid_configuration(request):  # noqa: ARG001
        return JSONResponse(await openid_configuration())

    async def wellknown_oauth_authorization_server(request):  # noqa: ARG001
        return JSONResponse(await oauth_authorization_server())

    async def wellknown_oauth_protected_resource(request):  # noqa: ARG001
        logger.info("oauth.discovery.request")
        return JSONResponse(await oauth_protected_resource())

    # -------------------------------------------------------------------------
    # Build ASGI app
    # -------------------------------------------------------------------------
    fastmcp_app = mcp.streamable_http_app()

    # Discovery routes (Claude checks both root and /mcp suffixed versions)
    discovery_routes = [
        Route("/openid-configuration", wellknown_openid_configuration, methods=["GET", "HEAD", "OPTIONS"]),
        Route("/oauth-authorization-server", wellknown_oauth_authorization_server, methods=["GET", "HEAD", "OPTIONS"]),
        Route("/oauth-protected-resource", wellknown_oauth_protected_resource, methods=["GET", "HEAD", "OPTIONS"]),
        Route("/openid-configuration/mcp", wellknown_openid_configuration, methods=["GET", "HEAD", "OPTIONS"]),
        Route("/oauth-authorization-server/mcp", wellknown_oauth_authorization_server, methods=["GET", "HEAD", "OPTIONS"]),
        Route("/oauth-protected-resource/mcp", wellknown_oauth_protected_resource, methods=["GET", "HEAD", "OPTIONS"]),
        # NOTE: /openai-apps-challenge NOT included — that's a ChatGPT-specific
        # domain verification route with no relevance on the Claude server.
    ]
    discovery_app = Starlette(routes=discovery_routes)
    fastmcp_app.mount("/.well-known", discovery_app)

    # Health endpoints (for monitoring and reviewer reachability checks)
    async def health_root(request):  # noqa: ARG001
        """Root page with favicon links for Google crawler."""
        html = '''<!DOCTYPE html>
<html>
<head>
<link rel="icon" type="image/png" sizes="64x64" href="/favicon-64.png">
<link rel="shortcut icon" href="/favicon.ico">
<title>Priority Guardian MCP</title>
</head>
<body>
<p>Priority Guardian Claude MCP Server</p>
</body>
</html>'''
        return HTMLResponse(content=html)

    async def health_check(request):  # noqa: ARG001
        """Simple health check endpoint."""
        return PlainTextResponse("ok")

    async def robots_txt(request):  # noqa: ARG001
        """Allow all crawlers for favicon discovery."""
        return PlainTextResponse("User-agent: *\nAllow: /\n", media_type="text/plain")

    fastmcp_app.add_route("/", health_root, methods=["GET"])
    fastmcp_app.add_route("/health", health_check, methods=["GET"])
    fastmcp_app.add_route("/robots.txt", robots_txt, methods=["GET"])

    # Favicon for Claude MCP Directory listing (Google favicon service)
    from starlette.requests import Request
    from starlette.responses import Response as StarletteResponse

    async def favicon(request: Request) -> StarletteResponse:
        """Serve PG logo as favicon — Google favicon service requires same-origin PNG."""
        try:
            logo_path = Path(__file__).parent / "static" / "logo-pg-96.png"
            logger.info("favicon.request", path=str(logo_path), exists=logo_path.exists(), file=__file__)
            if logo_path.exists():
                content = logo_path.read_bytes()
                logger.info("favicon.serving", bytes=len(content))
                return StarletteResponse(
                    content=content,
                    media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"},
                )
            logger.warning("favicon.file_not_found", path=str(logo_path))
            return StarletteResponse(status_code=404)
        except Exception as e:
            logger.error("favicon.exception", error=str(e), type=type(e).__name__)
            return StarletteResponse(status_code=500)

    fastmcp_app.add_route("/favicon.ico", favicon, methods=["GET"])
    fastmcp_app.add_route("/favicon-64.png", favicon, methods=["GET"])

    # -------------------------------------------------------------------------
    # OAuth Proxy Routes
    # -------------------------------------------------------------------------
    # Claude requires issuer and all OAuth endpoints to share the same origin.
    # These routes transparently proxy OAuth requests to the backend.
    # No business logic added — just forward request/response unchanged.
    import httpx
    from starlette.requests import Request
    from starlette.responses import Response

    # Lazy-init proxy client (shares lifecycle with http_client)
    _proxy_client: httpx.AsyncClient | None = None

    async def _get_proxy_client() -> httpx.AsyncClient:
        nonlocal _proxy_client
        if _proxy_client is None:
            _proxy_client = httpx.AsyncClient(timeout=30.0)
        return _proxy_client

    async def _proxy_to_backend(request: Request, backend_path: str) -> Response:
        """
        Transparent proxy to backend OAuth endpoint.

        Forwards all headers (except host), query params, and body unchanged.
        Returns backend's status, headers, and body verbatim.
        """
        client = await _get_proxy_client()
        backend_url = f"{BACKEND_URL}{backend_path}"

        # Forward headers except host (which must be the backend's host)
        forward_headers = {}
        for key, value in request.headers.items():
            if key.lower() not in ("host", "content-length"):
                forward_headers[key] = value

        # Log proxy call (no body logging for security)
        logger.info(
            "oauth.proxy",
            method=request.method,
            path=str(request.url.path),
            backend_url=backend_path,
        )

        # Forward request based on method
        if request.method == "GET":
            resp = await client.get(
                backend_url,
                headers=forward_headers,
                params=dict(request.query_params),
            )
        elif request.method == "POST":
            body = await request.body()
            resp = await client.post(
                backend_url,
                headers=forward_headers,
                params=dict(request.query_params),
                content=body,
            )
        else:
            # Shouldn't happen, but handle gracefully
            return Response(content=b"Method not allowed", status_code=405)

        # Log response status
        logger.info(
            "oauth.proxy.response",
            method=request.method,
            backend_url=backend_path,
            status_code=resp.status_code,
        )

        # Forward response headers (except transfer-encoding which Starlette handles)
        response_headers = {}
        for key, value in resp.headers.items():
            if key.lower() not in ("transfer-encoding", "content-encoding", "content-length"):
                response_headers[key] = value

        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=response_headers,
        )

    # OAuth proxy route handlers
    async def oauth_jwks(request: Request) -> Response:
        """Proxy JWKS requests with forced identity encoding to prevent compression issues."""
        client = await _get_proxy_client()
        backend_url = f"{BACKEND_URL}/oauth/pg/jwks"
        forward_headers = {
            k: v for k, v in request.headers.items()
            if k.lower() not in ("host", "content-length", "accept-encoding")
        }
        forward_headers["accept-encoding"] = "identity"
        resp = await client.get(backend_url, headers=forward_headers)
        response_headers = {
            k: v for k, v in resp.headers.items()
            if k.lower() not in ("transfer-encoding", "content-encoding", "content-length")
        }
        return Response(content=resp.content, status_code=resp.status_code, headers=response_headers)

    async def oauth_authorize(request: Request) -> Response:
        return await _proxy_to_backend(request, "/oauth/pg/authorize")

    async def oauth_token(request: Request) -> Response:
        return await _proxy_to_backend(request, "/oauth/pg/token")

    async def oauth_register(request: Request) -> Response:
        """Proxy DCR requests. POST uses JSONResponse for proper JSON serialization."""
        from starlette.responses import JSONResponse

        if request.method == "GET":
            return await _proxy_to_backend(request, "/oauth/pg/register")

        # POST: Use JSONResponse to ensure proper JSON content-type
        client = await _get_proxy_client()
        backend_url = f"{BACKEND_URL}/oauth/pg/register"
        forward_headers = {
            k: v for k, v in request.headers.items()
            if k.lower() not in ("host", "content-length", "accept-encoding")
        }
        # Force identity encoding: prevent brotli/gzip compressed responses
        # httpx decompresses gzip automatically but brotli requires optional dep.
        # Safest: ask backend for uncompressed response.
        forward_headers["accept-encoding"] = "identity"
        body = await request.body()
        resp = await client.post(backend_url, headers=forward_headers, content=body)
        logger.info(
            "oauth.proxy.register_debug",
            status_code=resp.status_code,
            content_type=resp.headers.get("content-type", "MISSING"),
            content_encoding=resp.headers.get("content-encoding", "NONE"),
            body_hex=resp.content[:60].hex(),
        )
        try:
            return JSONResponse(content=resp.json(), status_code=resp.status_code)
        except Exception as e:
            logger.error("oauth.proxy.register_parse_failed", error=str(e), body_hex=resp.content[:120].hex())
            # Return raw content with explicit JSON content-type as last resort
            return Response(content=resp.content, status_code=resp.status_code, headers={"content-type": "application/json; charset=utf-8"})

    # Register OAuth proxy routes
    fastmcp_app.add_route("/oauth/jwks", oauth_jwks, methods=["GET"])
    fastmcp_app.add_route("/oauth/authorize", oauth_authorize, methods=["GET"])
    fastmcp_app.add_route("/oauth/token", oauth_token, methods=["POST"])
    fastmcp_app.add_route("/oauth/register", oauth_register, methods=["GET", "POST"])

    logger.info(
        "mcp.app.created",
        fastmcp_name=mcp.name,
        mcp_endpoint="/mcp",
        discovery_mount="/.well-known",
        oauth_proxy_routes=["/oauth/jwks", "/oauth/authorize", "/oauth/token", "/oauth/register"],
    )

    # -------------------------------------------------------------------------
    # Cleanup function
    # -------------------------------------------------------------------------
    async def _cleanup_on_shutdown():
        nonlocal _proxy_client
        logger.info("mcp.server.shutdown")
        await cleanup_jwks_cache()
        await cleanup_http_client()
        # Close proxy client
        if _proxy_client is not None:
            await _proxy_client.aclose()
            _proxy_client = None
            logger.info("oauth.proxy_client.closed")

    # -------------------------------------------------------------------------
    # Wrap with middlewares
    # -------------------------------------------------------------------------
    # Order matters: outermost runs first at request time
    # 1. RequestLoggingMiddleware (outermost) - logs all requests
    # 2. HeadMcpMiddleware - intercepts HEAD /mcp for reachability probes
    # 3. OriginValidationMiddleware - validates Origin header on /mcp (Anthropic requirement)
    # 4. LifespanMiddleware - handles shutdown cleanup
    # 5. BearerAuthMiddleware - enforces Bearer token on /mcp
    # 6. MCPContentTypeAndAcceptFixMiddleware - fixes headers, captures auth
    # 7. fastmcp_app (innermost) - handles MCP protocol

    # NOTE: Unlike Clarity, PG does not use Starlette's CORSMiddleware.
    # PG MCP server is not accessed directly by browsers - Claude proxies
    # all widget calls, and server-to-server MCP calls don't require CORS.
    # HeadMcpMiddleware handles CORS headers only for HEAD /mcp probes.
    allowed_origins = list(CORS_ALLOWED_ORIGINS)
    if IS_DEV:
        # Add localhost origins for MCP Inspector during development
        allowed_origins.extend([
            "http://localhost:5173",   # MCP Inspector default
            "http://127.0.0.1:5173",
            "http://localhost:3000",   # Common dev port
            "http://127.0.0.1:3000",
        ])

    content_type_app = MCPContentTypeAndAcceptFixMiddleware(fastmcp_app, auth_header_var)
    bearer_auth_app = BearerAuthMiddleware(content_type_app, WWW_AUTHENTICATE_VALUE)
    lifespan_app = LifespanMiddleware(bearer_auth_app, _cleanup_on_shutdown)
    origin_validation_app = OriginValidationMiddleware(lifespan_app, allowed_origins=allowed_origins)
    head_mcp_app = HeadMcpMiddleware(origin_validation_app, allowed_origins=allowed_origins)
    return RequestLoggingMiddleware(head_mcp_app, service_name="priority-guardian-claude-mcp")


# --------------------------------------------------------------------
# ASGI entrypoint
# --------------------------------------------------------------------
# For production (Render): uvicorn server_dupl:create_app --factory
# For local dev: python -m mcp_server.priority_guardian_claude.server_dupl
#
# NOTE: We do NOT create `app` at module level to support factory mode.
# Factory mode allows uvicorn to bind the port before loading heavy deps.


def get_app():
    """
    Lazy app getter for backward compatibility.

    If something imports `app` directly, this creates it on first access.
    Prefer using create_app with --factory mode for production.
    """
    return create_app()


# For backward compatibility: `from server_dupl import app`
# This uses __getattr__ to lazily create the app only when accessed
def __getattr__(name):
    if name == "app":
        return create_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if __name__ == "__main__":
    import uvicorn

    app = create_app()
    port = int(os.getenv("PORT", "8004"))

    # Import config here to avoid loading at module level
    from mcp_server.priority_guardian_claude.config import MCP_SERVER_URL, OAUTH_ISSUER_URL

    logger.info(
        "Starting Priority Guardian Claude MCP server",
        host="0.0.0.0",
        port=port,
        mcp_server_url=MCP_SERVER_URL,
        oauth_issuer_url=OAUTH_ISSUER_URL
    )

    uvicorn.run(app, host="0.0.0.0", port=port)
