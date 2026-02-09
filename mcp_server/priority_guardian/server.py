#!/usr/bin/env python3
"""
Priority Guardian MCP Server.

Infrastructure-only server: middleware, discovery routes, app factory, entrypoint.
Tool handlers are in tools/, dispatch logic is in handlers/tools.py.

Usage:
    python -m mcp_server.priority_guardian.server

Or:
    python mcp_server/priority_guardian/server.py
"""

import os

import uvicorn
import structlog
from mcp.server.fastmcp import FastMCP
from mcp import types as mcp_types
from starlette.applications import Starlette
from starlette.responses import JSONResponse
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
from mcp_server.priority_guardian.tools import list_tools

logger = structlog.get_logger(__name__)


# ============================================================================
# Startup Configuration Validation
# ============================================================================

# Log resolved config at startup (helps debug Railway env var issues)
logger.info(
    "mcp.server.startup",
    version="REFACTOR_V1",
    server_file=os.path.abspath(__file__),
    BACKEND_URL=BACKEND_URL,
    OAUTH_ISSUER_URL=OAUTH_ISSUER_URL,
    MCP_SERVER_URL=MCP_SERVER_URL,
    PORT=os.getenv("PORT"),
)

# Warn if localhost URLs are used (will break ChatGPT OAuth in production)
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


# ============================================================================
# FastMCP Instance
# ============================================================================

# Create FastMCP instance with SSE streaming (required for ChatGPT)
# ChatGPT expects Server-Sent Events for MCP handshake
mcp = FastMCP("priority-guardian-mcp", streamable_http_path="/mcp")


# ============================================================================
# Register MCP Handlers
# ============================================================================

@mcp._mcp_server.list_tools()
async def _list_tools():
    """Return tools from registry."""
    return await list_tools()


# Register tool call handler
mcp._mcp_server.request_handlers[mcp_types.CallToolRequest] = call_tool_request


# ============================================================================
# Middleware
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
            # Intercept lifespan protocol to add cleanup
            async def receive_wrapper():
                message = await receive()
                return message

            async def send_wrapper(message):
                if message["type"] == "lifespan.shutdown.complete":
                    # Run cleanup before signaling shutdown complete
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
    - This bridges the gap between HTTP headers and MCP tool handlers
      (FastMCP's @mcp.tool() decorator does this automatically, but
      Priority Guardian uses a custom registry pattern that bypasses injection)
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("method") == "POST":
            if scope.get("path") == "/mcp":
                new_headers = []
                modified = False
                auth_header = None

                for name, value in scope["headers"]:
                    # Fix Content-Type (ChatGPT sends octet-stream)
                    if name == b"content-type" and b"application/octet-stream" in value:
                        value = b"application/json"
                        modified = True

                    # Fix Accept: allow SSE for handshake + JSON for tool results
                    if name == b"accept":
                        value = b"text/event-stream, application/json"
                        modified = True

                    # Capture Authorization header for tool handlers
                    if name == b"authorization":
                        auth_header = value.decode("utf-8")

                    new_headers.append((name, value))

                if modified:
                    scope = dict(scope)
                    scope["headers"] = new_headers

                # Set Authorization header in context for tool handlers
                # Use token pattern to ensure cleanup after request completes
                if auth_header:
                    token = auth_header_var.set(auth_header)
                    try:
                        await self.app(scope, receive, send)
                    finally:
                        auth_header_var.reset(token)
                    return

        await self.app(scope, receive, send)


# ============================================================================
# OAuth Discovery Endpoints
# ============================================================================

async def wellknown_openid_configuration(request):  # noqa: ARG001
    """Starlette wrapper for discovery.openid_configuration."""
    return JSONResponse(await openid_configuration())


async def wellknown_oauth_authorization_server(request):  # noqa: ARG001
    """Starlette wrapper for discovery.oauth_authorization_server."""
    return JSONResponse(await oauth_authorization_server())


async def wellknown_oauth_protected_resource(request):  # noqa: ARG001
    """Starlette wrapper for discovery.oauth_protected_resource."""
    logger.info("oauth.discovery.request")
    return JSONResponse(await oauth_protected_resource())


# ============================================================================
# Application Factory
# ============================================================================

async def _cleanup_on_shutdown():
    """Clean up HTTP clients and caches on shutdown."""
    logger.info("mcp.server.shutdown")
    await cleanup_jwks_cache()
    await cleanup_http_client()


def create_app():
    """
    Create the ASGI application.

    FastMCP is the root app with:
    - Discovery routes for OAuth
    - Header fix middleware for ChatGPT
    - Auth header capture for tool handlers
    - Shutdown handler for cleanup
    """
    # FastMCP is the root app - its lifespan will run properly
    fastmcp_app = mcp.streamable_http_app()

    # Discovery routes as a separate Starlette app
    # Include both root and /mcp suffixed versions (ChatGPT checks both)
    discovery_routes = [
        # Root discovery endpoints
        Route("/openid-configuration", wellknown_openid_configuration, methods=["GET", "HEAD", "OPTIONS"]),
        Route("/oauth-authorization-server", wellknown_oauth_authorization_server, methods=["GET", "HEAD", "OPTIONS"]),
        Route("/oauth-protected-resource", wellknown_oauth_protected_resource, methods=["GET", "HEAD", "OPTIONS"]),
        # ChatGPT also checks /mcp suffixed versions
        Route("/openid-configuration/mcp", wellknown_openid_configuration, methods=["GET", "HEAD", "OPTIONS"]),
        Route("/oauth-authorization-server/mcp", wellknown_oauth_authorization_server, methods=["GET", "HEAD", "OPTIONS"]),
        Route("/oauth-protected-resource/mcp", wellknown_oauth_protected_resource, methods=["GET", "HEAD", "OPTIONS"]),
    ]
    discovery_app = Starlette(routes=discovery_routes)

    # Mount discovery routes onto FastMCP app
    fastmcp_app.mount("/.well-known", discovery_app)

    # Log FastMCP configuration
    logger.info(
        "mcp.app.created",
        fastmcp_name=mcp.name,
        mcp_endpoint="/mcp",
        discovery_mount="/.well-known",
    )

    # Wrap with middlewares:
    # 1. LifespanMiddleware (outermost) - handles cleanup on shutdown
    # 2. MCPContentTypeAndAcceptFixMiddleware - fixes ChatGPT header issues + auth capture
    #
    # IMPORTANT: MCPContentTypeAndAcceptFixMiddleware must run before FastMCP
    # request handling so auth_header_var is set. Do not insert middleware between
    # MCPContentTypeAndAcceptFixMiddleware and fastmcp_app.
    wrapped_app = MCPContentTypeAndAcceptFixMiddleware(fastmcp_app)
    return LifespanMiddleware(wrapped_app, _cleanup_on_shutdown)


# --------------------------------------------------------------------
# ASGI entrypoint for uvicorn (Railway imports this)
# --------------------------------------------------------------------
app = create_app()


if __name__ == "__main__":
    # Use PORT env var (Railway sets this) or default to 8003 for local dev
    port = int(os.getenv("PORT", "8003"))

    logger.info(
        "Starting Priority Guardian MCP server",
        host="0.0.0.0",
        port=port,
        mcp_server_url=MCP_SERVER_URL,
        oauth_issuer_url=OAUTH_ISSUER_URL
    )

    # Run with uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port)
