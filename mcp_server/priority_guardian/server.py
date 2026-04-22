#!/usr/bin/env python3
"""
Priority Guardian MCP Server.

Infrastructure-only server: middleware, discovery routes, app factory, entrypoint.
Tool handlers are in tools/, dispatch logic is in handlers/tools.py.

Usage (factory mode - recommended for production):
    uvicorn mcp_server.priority_guardian.server:create_app --factory --host 0.0.0.0 --port $PORT

Or (direct mode - for local development):
    python -m mcp_server.priority_guardian.server
"""

import json
import os
import time

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
    ASGI middleware for full HTTP-layer MCP auth compliance (401 + 403).

    Implements MCP spec 2025-06-18 §2 and OpenAI Apps SDK auth requirements:
    - HTTP 401 + WWW-Authenticate for missing, malformed, or invalid JWTs
    - HTTP 403 + WWW-Authenticate (error="insufficient_scope") for valid JWTs
      that lack required scopes for the requested tool
    - HTTP 413 for request bodies exceeding 1 MB

    FastMCP streamable HTTP uses:
    - GET /mcp for SSE stream initiation
    - POST /mcp for messages (JSON-RPC, including tools/call)
    - DELETE /mcp for session close

    Decision sequence for POST /mcp:
    1. Body size guard: reject > 1 MB with 413
    2. Check Authorization header presence → 401 if missing
    3. Extract Bearer token → 401 if invalid format
    4. Validate JWT (signature, iss, aud, exp) → 401 if invalid
    5. For tools/call: enforce scope requirements → 403 if insufficient

    GET/DELETE /mcp: steps 2-4 only (no body parsing).

    Positioning: between HeadMcpMiddleware and MCPContentTypeAndAcceptFixMiddleware.
    Does NOT set auth_header_var — that remains MCPContentTypeAndAcceptFixMiddleware's job.
    """

    # Maximum request body size (1 MB)
    MAX_BODY_SIZE = 1024 * 1024

    def __init__(self, app, mcp_origin: str):
        self.app = app
        self.mcp_origin = mcp_origin

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method")
        path = scope.get("path")

        # Only process /mcp requests
        if path != "/mcp" or method not in ("GET", "POST", "DELETE"):
            await self.app(scope, receive, send)
            return

        # Late imports to avoid circular dependencies
        import jwt
        from mcp_server.priority_guardian.mcp_auth import (
            extract_bearer_token,
            validate_jwt,
            check_scopes,
            extract_or_generate_correlation_id,
        )

        correlation_id = extract_or_generate_correlation_id(None)

        # Extract Authorization header and Content-Length from headers
        auth_header = None
        content_length = None
        for name, value in scope.get("headers", []):
            if name == b"authorization":
                auth_header = value.decode("utf-8")
            elif name == b"content-length":
                try:
                    content_length = int(value.decode())
                except (ValueError, UnicodeDecodeError):
                    pass

        # Step 2: Check for Authorization header (before Content-Length check
        # to avoid leaking body size limits to unauthenticated clients)
        if not auth_header:
            await self._send_401(send, "missing_header", "Authentication required", correlation_id, method)
            return

        # Step 3: Extract Bearer token
        token = extract_bearer_token(auth_header)
        if not token:
            await self._send_401(send, "invalid_format", "Invalid Authorization header format", correlation_id, method)
            return

        # Step 4: Validate JWT
        try:
            validated = await validate_jwt(token, correlation_id)
        except jwt.ExpiredSignatureError:
            await self._send_401(send, "token_expired", "Token expired", correlation_id, method)
            return
        except jwt.InvalidTokenError:
            await self._send_401(send, "invalid_token", "Token validation failed", correlation_id, method)
            return
        except Exception as e:
            logger.error("auth.middleware.validation_error", correlation_id=correlation_id, error=str(e))
            await self._send_401(send, "validation_error", "Token validation failed", correlation_id, method)
            return

        token_scopes = validated["scopes"]

        # For GET/DELETE: JWT validated, pass through
        if method in ("GET", "DELETE"):
            await self.app(scope, receive, send)
            return

        # For POST: Pre-flight Content-Length check (after auth, before buffering)
        # Avoids reading any body bytes for honest oversized requests
        if content_length is not None and content_length > self.MAX_BODY_SIZE:
            await self._send_413(send, content_length, correlation_id)
            return

        # For POST: need to buffer body for scope enforcement and replay
        # Step 0: Body size guard during streaming (for chunked/missing Content-Length)
        body_chunks = []
        total_size = 0

        async def buffering_receive():
            nonlocal total_size
            message = await receive()
            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                total_size += len(chunk)
                if total_size > self.MAX_BODY_SIZE:
                    # Will be caught below
                    raise _BodyTooLargeError(total_size)
                body_chunks.append(chunk)
            return message

        # Buffer the entire body
        try:
            while True:
                msg = await buffering_receive()
                if msg["type"] == "http.request":
                    if not msg.get("more_body", False):
                        break
                elif msg["type"] == "http.disconnect":
                    # Client disconnected mid-body; log and return cleanly
                    logger.info(
                        "auth.middleware.client_disconnected",
                        correlation_id=correlation_id,
                        bytes_received=total_size,
                    )
                    return
        except _BodyTooLargeError as e:
            await self._send_413(send, e.size, correlation_id)
            return

        full_body = b"".join(body_chunks)

        # Step 5: Parse JSON-RPC body for scope enforcement
        try:
            body_json = json.loads(full_body) if full_body else {}
        except json.JSONDecodeError:
            # Malformed JSON: let FastMCP handle the protocol error
            body_json = {}

        jsonrpc_method = body_json.get("method")

        # Only enforce scopes for tools/call
        if jsonrpc_method == "tools/call":
            params = body_json.get("params", {})
            tool_name = params.get("name")

            if tool_name:
                # Late import to avoid circular imports
                from mcp_server.priority_guardian.tools import get_tool

                tool_def = get_tool(tool_name)

                # Unknown tool: let FastMCP handle it (not a 403 concern)
                if tool_def is not None:
                    required_scopes = tool_def.required_scopes

                    # Only enforce if tool has required scopes
                    if required_scopes and not check_scopes(token_scopes, required_scopes):
                        await self._send_403(
                            send, tool_name, required_scopes, list(token_scopes), correlation_id
                        )
                        return

        # Create replay receive callable (pass original receive for post-body disconnect)
        replay_receive = self._create_replay_receive(full_body, receive)

        # Pass through to inner app with replayed body
        await self.app(scope, replay_receive, send)

    def _create_replay_receive(self, body: bytes, original_receive):
        """Create a receive callable that replays the buffered body.

        After the buffered body is consumed once, subsequent calls forward
        to the original receive to wait for real disconnect events (not
        synthesize fake ones that could prematurely tear down FastMCP streams).
        """
        sent = False

        async def replay_receive():
            nonlocal sent
            if not sent:
                sent = True
                return {
                    "type": "http.request",
                    "body": body,
                    "more_body": False,
                }
            # After body consumed, forward to original receive for real disconnect
            return await original_receive()

        return replay_receive

    async def _send_401(self, send, reason: str, description: str, correlation_id: str, method: str = "POST"):
        """Send HTTP 401 Unauthorized response."""
        logger.warning(
            "auth.middleware.rejected",
            method=method,
            path="/mcp",
            status=401,
            reason=reason,
            correlation_id=correlation_id,
        )

        www_auth = (
            f'Bearer resource_metadata="{self.mcp_origin}/.well-known/oauth-protected-resource", '
            f'error="invalid_token", error_description="{description}"'
        )
        body = json.dumps({
            "error": "unauthorized",
            "error_description": description,
        }).encode("utf-8")

        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", www_auth.encode("utf-8")),
                (b"cache-control", b"no-store"),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })

    async def _send_403(
        self, send, tool_name: str, required_scopes: list, actual_scopes: list, correlation_id: str
    ):
        """Send HTTP 403 Forbidden response."""
        logger.warning(
            "auth.middleware.rejected",
            method="POST",
            path="/mcp",
            status=403,
            reason="insufficient_scope",
            correlation_id=correlation_id,
            tool_name=tool_name,
            required_scopes=required_scopes,
            actual_scopes=actual_scopes,
        )

        scope_str = " ".join(required_scopes)
        www_auth = (
            f'Bearer resource_metadata="{self.mcp_origin}/.well-known/oauth-protected-resource", '
            f'error="insufficient_scope", error_description="Insufficient permissions", '
            f'scope="{scope_str}"'
        )
        body = json.dumps({
            "error": "insufficient_scope",
            "error_description": f"Insufficient permissions for tool '{tool_name}'",
            "required_scopes": required_scopes,
        }).encode("utf-8")

        await send({
            "type": "http.response.start",
            "status": 403,
            "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", www_auth.encode("utf-8")),
                (b"cache-control", b"no-store"),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })

    async def _send_413(self, send, size_bytes: int, correlation_id: str):
        """Send HTTP 413 Payload Too Large response."""
        logger.warning(
            "auth.middleware.rejected",
            method="POST",
            path="/mcp",
            status=413,
            reason="body_too_large",
            correlation_id=correlation_id,
            size_bytes=size_bytes,
        )

        body = json.dumps({
            "error": "payload_too_large",
            "error_description": "Request body exceeds maximum size",
        }).encode("utf-8")

        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"cache-control", b"no-store"),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })


class _BodyTooLargeError(Exception):
    """Internal exception for body size limit exceeded."""
    def __init__(self, size: int):
        self.size = size


class MCPContentTypeAndAcceptFixMiddleware:
    """
    Fix ChatGPT -> FastMCP header mismatch and capture Authorization header.

    Header fixes:
    - ChatGPT sends Content-Type: application/octet-stream -> application/json
    - ChatGPT sends Accept: */* -> text/event-stream, application/json

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
    from starlette.responses import JSONResponse, PlainTextResponse
    from starlette.routing import Route

    from mcp_server.priority_guardian.config import (
        MCP_SERVER_URL,
        MCP_RESOURCE_URL,
        OAUTH_ISSUER_URL,
        BACKEND_URL,
        CORS_ALLOWED_ORIGINS,
        IS_DEV,
    )
    from urllib.parse import urlparse as _urlparse
    _mcp_origin = f"{_urlparse(MCP_SERVER_URL).scheme}://{_urlparse(MCP_SERVER_URL).netloc}"
    from mcp_server.priority_guardian.discovery import (
        openid_configuration,
        oauth_authorization_server,
        oauth_protected_resource,
    )
    from mcp_server.priority_guardian.http_client import cleanup_http_client
    from mcp_server.priority_guardian.mcp_auth import cleanup_jwks_cache
    from mcp_server.priority_guardian.request_context import auth_header_var
    from mcp_server.priority_guardian.handlers.tools import call_tool_request
    from mcp_server.priority_guardian.handlers.resources import (
        list_resources,
        list_resource_templates,
        handle_read_resource,
    )
    from mcp_server.priority_guardian.tools import list_tools

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
            message="OAUTH_ISSUER_URL contains localhost - ChatGPT OAuth will fail!",
            OAUTH_ISSUER_URL=OAUTH_ISSUER_URL,
        )

    if "localhost" in MCP_SERVER_URL:
        logger.error(
            "oauth.config.localhost_detected",
            message="MCP_SERVER_URL contains localhost - ChatGPT OAuth will fail!",
            MCP_SERVER_URL=MCP_SERVER_URL,
        )

    # -------------------------------------------------------------------------
    # Create FastMCP instance and register handlers
    # -------------------------------------------------------------------------
    # stateless_http=True: Each request is self-contained, authenticated via JWT.
    # This avoids session ID issues on deploy (server restart clears in-memory sessions).
    mcp = FastMCP("priority-guardian-mcp", streamable_http_path="/mcp", stateless_http=True)

    @mcp._mcp_server.list_resources()
    async def _list_resources():
        return await list_resources()

    @mcp._mcp_server.list_resource_templates()
    async def _list_resource_templates():
        return await list_resource_templates()

    mcp._mcp_server.request_handlers[mcp_types.ReadResourceRequest] = handle_read_resource

    @mcp._mcp_server.list_tools()
    async def _list_tools():
        return await list_tools()

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

    # Discovery routes (ChatGPT checks both root and /mcp suffixed versions)
    discovery_routes = [
        Route("/openid-configuration", wellknown_openid_configuration, methods=["GET", "HEAD", "OPTIONS"]),
        Route("/oauth-authorization-server", wellknown_oauth_authorization_server, methods=["GET", "HEAD", "OPTIONS"]),
        Route("/oauth-protected-resource", wellknown_oauth_protected_resource, methods=["GET", "HEAD", "OPTIONS"]),
        Route("/openid-configuration/mcp", wellknown_openid_configuration, methods=["GET", "HEAD", "OPTIONS"]),
        Route("/oauth-authorization-server/mcp", wellknown_oauth_authorization_server, methods=["GET", "HEAD", "OPTIONS"]),
        Route("/oauth-protected-resource/mcp", wellknown_oauth_protected_resource, methods=["GET", "HEAD", "OPTIONS"]),
        Route(
            "/openai-apps-challenge",
            lambda request: PlainTextResponse("gmxOIeNMeuqOBZjXdRcGbfcqBHeZnhYV1GAFnn9KORk"),
            methods=["GET"]
        ),
    ]
    discovery_app = Starlette(routes=discovery_routes)
    fastmcp_app.mount("/.well-known", discovery_app)

    # Health endpoints (for monitoring and reviewer reachability checks)
    async def health_root(request):  # noqa: ARG001
        """Root health check - returns JSON for monitoring/reviewers."""
        return JSONResponse({"status": "ok", "service": "priority-guardian-mcp"})

    async def health_check(request):  # noqa: ARG001
        """Simple health check endpoint."""
        return PlainTextResponse("ok")

    fastmcp_app.add_route("/", health_root, methods=["GET"])
    fastmcp_app.add_route("/health", health_check, methods=["GET"])

    # -------------------------------------------------------------------------
    # OAuth Proxy Routes
    # -------------------------------------------------------------------------
    # ChatGPT requires issuer and all OAuth endpoints to share the same origin.
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
    # 3. LifespanMiddleware - handles shutdown cleanup
    # 4. MCPContentTypeAndAcceptFixMiddleware - fixes headers, captures auth
    # 5. fastmcp_app (innermost) - handles MCP protocol

    # NOTE: Unlike Clarity, PG does not use Starlette's CORSMiddleware.
    # PG MCP server is not accessed directly by browsers - ChatGPT proxies
    # all widget calls, and server-to-server MCP calls don't require CORS.
    # HeadMcpMiddleware handles CORS headers only for HEAD /mcp probes.
    allowed_origins = list(CORS_ALLOWED_ORIGINS)
    if IS_DEV:
        # Add localhost origins for MCP Inspector during development
        allowed_origins.extend([
            "http://localhost:6274",   # MCP Inspector
            "http://127.0.0.1:6274",
            "http://localhost:5173",   # Vite dev server
            "http://127.0.0.1:5173",
            "http://localhost:3000",   # Common dev port
            "http://127.0.0.1:3000",
        ])

    content_type_app = MCPContentTypeAndAcceptFixMiddleware(fastmcp_app, auth_header_var)
    bearer_auth_app = BearerAuthMiddleware(content_type_app, _mcp_origin)
    lifespan_app = LifespanMiddleware(bearer_auth_app, _cleanup_on_shutdown)
    head_mcp_app = HeadMcpMiddleware(lifespan_app, allowed_origins=allowed_origins)
    return RequestLoggingMiddleware(head_mcp_app, service_name="priority-guardian-mcp")


# --------------------------------------------------------------------
# ASGI entrypoint
# --------------------------------------------------------------------
# For production (Render): uvicorn server:create_app --factory
# For local dev: python -m mcp_server.priority_guardian.server
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


# For backward compatibility: `from server import app`
# This uses __getattr__ to lazily create the app only when accessed
def __getattr__(name):
    if name == "app":
        return create_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if __name__ == "__main__":
    import uvicorn

    app = create_app()
    port = int(os.getenv("PORT", "8003"))

    # Import config here to avoid loading at module level
    from mcp_server.priority_guardian.config import MCP_SERVER_URL, OAUTH_ISSUER_URL

    logger.info(
        "Starting Priority Guardian MCP server",
        host="0.0.0.0",
        port=port,
        mcp_server_url=MCP_SERVER_URL,
        oauth_issuer_url=OAUTH_ISSUER_URL
    )

    uvicorn.run(app, host="0.0.0.0", port=port)
