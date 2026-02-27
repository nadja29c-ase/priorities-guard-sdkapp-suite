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

import os

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
        OAUTH_ISSUER_URL,
        BACKEND_URL,
    )
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
    mcp = FastMCP("priority-guardian-mcp", streamable_http_path="/mcp")

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

    logger.info(
        "mcp.app.created",
        fastmcp_name=mcp.name,
        mcp_endpoint="/mcp",
        discovery_mount="/.well-known",
    )

    # -------------------------------------------------------------------------
    # Cleanup function
    # -------------------------------------------------------------------------
    async def _cleanup_on_shutdown():
        logger.info("mcp.server.shutdown")
        await cleanup_jwks_cache()
        await cleanup_http_client()

    # -------------------------------------------------------------------------
    # Wrap with middlewares
    # -------------------------------------------------------------------------
    wrapped_app = MCPContentTypeAndAcceptFixMiddleware(fastmcp_app, auth_header_var)
    return LifespanMiddleware(wrapped_app, _cleanup_on_shutdown)


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
