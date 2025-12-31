#!/usr/bin/env python3
"""
Unpack MCP Server.

A question-first sensemaking tool.
No authentication required (noauth).

Usage:
    python -m mcp_server.unpack.server

Or run directly:
    python mcp_server/unpack/server.py
"""

import os
from pathlib import Path

import uvicorn
import structlog
from mcp.server.fastmcp import FastMCP
from mcp import types as mcp_types
from starlette.responses import HTMLResponse, PlainTextResponse
from starlette.routing import Route

from mcp_server.unpack.config import CORS_ALLOWED_ORIGINS, IS_DEV, PORT
from mcp_server.unpack.tools import list_tools
from mcp_server.unpack.handlers.tools import call_tool_request
from mcp_server.unpack.handlers import (
    list_resources,
    list_resource_templates,
    handle_read_resource,
)

# ============================================================================
# Configuration
# ============================================================================

logger = structlog.get_logger(__name__)

# Create FastMCP instance
# stateless_http=True: Each request is self-contained
# Note: No transport_security - matches Clarity's working configuration
mcp = FastMCP("unpack-mcp", streamable_http_path="/mcp", stateless_http=True)


# ============================================================================
# MCPContentTypeFixMiddleware - Fix ChatGPT octet-stream Content-Type
# ============================================================================

class MCPContentTypeAndAcceptFixMiddleware:
    """
    Fix ChatGPT -> FastMCP header mismatch.

    Header fixes:
    - ChatGPT sends Content-Type: application/octet-stream -> application/json
    - ChatGPT sends Accept: */* -> text/event-stream, application/json
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("method") == "POST":
            if scope.get("path") == "/mcp":
                new_headers = []
                modified = False

                for name, value in scope["headers"]:
                    if name == b"content-type" and b"application/octet-stream" in value:
                        value = b"application/json"
                        modified = True

                    if name == b"accept" and value == b"*/*":
                        value = b"text/event-stream, application/json"
                        modified = True

                    new_headers.append((name, value))

                if modified:
                    scope = dict(scope)
                    scope["headers"] = new_headers
                    logger.debug("middleware.headers_fixed", path=scope.get("path"))

        await self.app(scope, receive, send)


# ============================================================================
# Static Routes
# ============================================================================

ASSETS_DIR = Path(__file__).parent / "assets"
INDEX_PATH = ASSETS_DIR / "index.html"
UNPACK_LANDING_PATH = ASSETS_DIR / "unpack-landing.html"
PRIVACY_POLICY_PATH = ASSETS_DIR / "privacy-policy.html"
TERMS_PATH = ASSETS_DIR / "terms.html"


async def index_handler(request):
    """Serve the landing page based on host."""
    host = request.headers.get("host", "")

    # Unpack subdomain gets app-specific landing page
    if host.startswith("unpack."):
        if UNPACK_LANDING_PATH.exists():
            return HTMLResponse(UNPACK_LANDING_PATH.read_text())
    else:
        # Main domain gets suite landing page
        if INDEX_PATH.exists():
            return HTMLResponse(INDEX_PATH.read_text())

    return PlainTextResponse("Page not found", status_code=404)


async def privacy_policy_handler(request):
    """Serve the privacy policy HTML page."""
    if PRIVACY_POLICY_PATH.exists():
        return HTMLResponse(PRIVACY_POLICY_PATH.read_text())
    return PlainTextResponse("Privacy policy not found", status_code=404)


async def terms_handler(request):
    """Serve the terms of service HTML page."""
    if TERMS_PATH.exists():
        return HTMLResponse(TERMS_PATH.read_text())
    return PlainTextResponse("Terms of service not found", status_code=404)


# ============================================================================
# Register MCP Handlers
# ============================================================================

# Resource handlers (widget discovery and serving) - must be registered first
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
# App Startup
# ============================================================================

def create_app():
    """
    Create the ASGI application.

    FastMCP is the root app with:
    - CORS middleware for widget compatibility
    - Header fix middleware for ChatGPT
    """
    fastmcp_app = mcp.streamable_http_app()

    # Add static routes
    fastmcp_app.add_route("/", index_handler, methods=["GET"])
    fastmcp_app.add_route("/privacy-policy", privacy_policy_handler, methods=["GET"])
    fastmcp_app.add_route("/terms", terms_handler, methods=["GET"])

    # Add CORS
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
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "X-Correlation-ID"],
        allow_credentials=False,
    )

    # Wrap with header-fix middleware
    return MCPContentTypeAndAcceptFixMiddleware(fastmcp_app)


# ASGI entrypoint
app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", str(PORT)))

    logger.info(
        "unpack.server.starting",
        host="127.0.0.1",
        port=port,
        mcp_endpoint=f"http://127.0.0.1:{port}/mcp",
    )

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
