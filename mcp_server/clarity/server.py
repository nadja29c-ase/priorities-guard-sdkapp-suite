#!/usr/bin/env python3
"""
Clarity MCP Server.

ChatGPT clusters and reasons BEFORE calling each tool.
Tools only format/validate - no AI logic here.
Widget renders clusters as visual cards.

Usage:
    python -m mcp_server.clarity.server

Or run directly:
    python mcp_server/clarity/server.py
"""

import os

import uvicorn
import structlog
from mcp.server.fastmcp import FastMCP
from mcp import types as mcp_types
from starlette.applications import Starlette
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

from mcp_server.clarity.http_client import cleanup_http_client
from mcp_server.clarity.mcp_auth import cleanup_jwks_cache
from mcp_server.clarity.request_context import auth_header_var
from mcp_server.clarity.discovery import (
    openid_configuration,
    oauth_authorization_server,
    oauth_protected_resource,
)
from mcp_server.clarity.handlers import (
    list_resources,
    list_resource_templates,
    handle_read_resource,
)
from mcp_server.clarity.handlers.tools import call_tool_request
from mcp_server.clarity.tools import list_tools
from mcp_server.clarity.config import CORS_ALLOWED_ORIGINS, IS_DEV

# ============================================================================
# Configuration
# ============================================================================

logger = structlog.get_logger(__name__)

# Create FastMCP instance
# stateless_http=True: Each request is self-contained, authenticated via JWT.
# This avoids session ID issues on deploy (server restart clears in-memory sessions).
mcp = FastMCP("clarity-mcp", streamable_http_path="/mcp", stateless_http=True)


# ============================================================================
# MCPContentTypeFixMiddleware - Fix ChatGPT octet-stream Content-Type
# ============================================================================

class MCPContentTypeAndAcceptFixMiddleware:
    """
    Fix ChatGPT → FastMCP header mismatch and capture Authorization header.

    Header fixes:
    - ChatGPT sends Content-Type: application/octet-stream → application/json
    - ChatGPT sends Accept: */* → text/event-stream, application/json

    Authorization capture:
    - Extracts Authorization header from HTTP request
    - Sets it in request_context.auth_header_var for tool handlers
    - This bridges the gap between HTTP headers and MCP tool handlers
      (FastMCP's @mcp.tool() decorator does this automatically, but
      Clarity uses a custom registry pattern that bypasses injection)
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
                    if name == b"content-type" and b"application/octet-stream" in value:
                        value = b"application/json"
                        modified = True

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
# Register MCP Handlers
# ============================================================================

# Resource handlers (widget discovery and serving)
@mcp._mcp_server.list_resources()
async def _list_resources():
    return await list_resources()


@mcp._mcp_server.list_resource_templates()
async def _list_resource_templates():
    return await list_resource_templates()


mcp._mcp_server.request_handlers[mcp_types.ReadResourceRequest] = handle_read_resource


# Tool handlers
@mcp._mcp_server.list_tools()
async def _list_tools():
    # Get tools from registry
    registry_tools = await list_tools()
    # Get any tools registered via @mcp.tool() decorator
    decorator_tools = await mcp.list_tools()
    return registry_tools + list(decorator_tools)


mcp._mcp_server.request_handlers[mcp_types.CallToolRequest] = call_tool_request


# ============================================================================
# OAuth Discovery Endpoints
# ============================================================================

async def wellknown_openid_configuration(_request):
    """Starlette wrapper for discovery.openid_configuration."""
    logger.debug("oauth.discovery.openid_configuration")
    return JSONResponse(await openid_configuration())


async def wellknown_oauth_authorization_server(_request):
    """Starlette wrapper for discovery.oauth_authorization_server."""
    logger.debug("oauth.discovery.authorization_server")
    return JSONResponse(await oauth_authorization_server())


async def wellknown_oauth_protected_resource(_request):
    """Starlette wrapper for discovery.oauth_protected_resource."""
    logger.debug("oauth.discovery.protected_resource")
    return JSONResponse(await oauth_protected_resource())


# ============================================================================
# App Startup
# ============================================================================

async def _cleanup_on_shutdown():
    """Clean up HTTP clients on shutdown."""
    logger.info("clarity.server.shutdown")
    await cleanup_jwks_cache()
    await cleanup_http_client()


def create_app():
    """
    Create the ASGI application.

    FastMCP is the root app with:
    - CORS middleware for widget compatibility
    - Discovery routes for OAuth
    - Header fix middleware for ChatGPT
    - Shutdown handler for cleanup
    """
    fastmcp_app = mcp.streamable_http_app()

    # Add CORS
    # ---------------------------------------------------------------
    # SECURITY: Restricted to known ChatGPT/OpenAI domains.
    # Production requires explicit CORS_ALLOWED_ORIGINS env var.
    # Dev mode adds localhost origins for MCP Inspector.
    # ---------------------------------------------------------------
    from starlette.middleware.cors import CORSMiddleware

    # Build allowed origins list
    allowed_origins = list(CORS_ALLOWED_ORIGINS)
    if IS_DEV:
        # Add localhost origins for MCP Inspector during development
        allowed_origins.extend([
            "http://localhost:5173",   # MCP Inspector default
            "http://127.0.0.1:5173",
            "http://localhost:3000",   # Common dev port
            "http://127.0.0.1:3000",
        ])

    fastmcp_app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST", "OPTIONS"],  # Restrict to needed methods
        allow_headers=["Authorization", "Content-Type", "Accept", "X-Correlation-ID"],
        allow_credentials=False,
    )

    # Register shutdown handler
    fastmcp_app.add_event_handler("shutdown", _cleanup_on_shutdown)

    # OpenAI Apps SDK domain verification endpoint
    async def openai_apps_challenge(request):
        """Return OpenAI domain verification token."""
        return PlainTextResponse(
            content="LNSVlw7Z-qPXhaP1hsVKpjnwHsApf--cHemEHHoJ3CA",
            media_type="text/plain"
        )

    # Discovery routes - all OAuth discovery endpoints
    discovery_routes = [
        Route("/openid-configuration", wellknown_openid_configuration, methods=["GET", "HEAD", "OPTIONS"]),
        Route("/oauth-authorization-server", wellknown_oauth_authorization_server, methods=["GET", "HEAD", "OPTIONS"]),
        Route("/oauth-protected-resource", wellknown_oauth_protected_resource, methods=["GET", "HEAD", "OPTIONS"]),
        # /mcp suffix variants for compatibility
        Route("/openid-configuration/mcp", wellknown_openid_configuration, methods=["GET", "HEAD", "OPTIONS"]),
        Route("/oauth-authorization-server/mcp", wellknown_oauth_authorization_server, methods=["GET", "HEAD", "OPTIONS"]),
        Route("/oauth-protected-resource/mcp", wellknown_oauth_protected_resource, methods=["GET", "HEAD", "OPTIONS"]),
        # OpenAI Apps SDK domain verification
        Route("/openai-apps-challenge", openai_apps_challenge, methods=["GET"]),
    ]
    discovery_app = Starlette(routes=discovery_routes)

    # Mount discovery routes
    fastmcp_app.mount("/.well-known", discovery_app)

    # Wrap with header-fix middleware
    return MCPContentTypeAndAcceptFixMiddleware(fastmcp_app)


# ASGI entrypoint
app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8002"))

    logger.info(
        "clarity.server.starting",
        host="127.0.0.1",
        port=port,
    )

    print("=" * 50)
    print("CLARITY MCP SERVER - V5 (Widget Integration)")
    print(f"Starting on http://127.0.0.1:{port}")
    print(f"MCP endpoint: http://127.0.0.1:{port}/mcp")
    print("=" * 50)

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
