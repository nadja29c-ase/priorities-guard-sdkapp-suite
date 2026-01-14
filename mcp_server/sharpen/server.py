#!/usr/bin/env python3
"""
Sharpen MCP Server.

Stateless, single-session facilitated planning tool.
No OAuth, no persistence, no user accounts.

Usage:
    python -m mcp_server.sharpen.server

Or run directly:
    python mcp_server/sharpen/server.py
"""

import os
from pathlib import Path

import uvicorn
import structlog
from mcp.server.fastmcp import FastMCP
from mcp import types as mcp_types
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, PlainTextResponse
from starlette.routing import Route

from mcp_server.sharpen.handlers.tools import call_tool_request
from mcp_server.sharpen.tools import list_tools
from mcp_server.sharpen.config import CORS_ALLOWED_ORIGINS, IS_DEV

# ============================================================================
# Configuration
# ============================================================================

logger = structlog.get_logger(__name__)

# Path to assets directory
ASSETS_PATH = Path(__file__).parent / "assets"

# Create FastMCP instance
# stateless_http=True: Each request is self-contained, no session management needed.
mcp = FastMCP("sharpen-mcp", streamable_http_path="/mcp", stateless_http=True)


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

                    if name == b"accept":
                        value = b"text/event-stream, application/json"
                        modified = True

                    new_headers.append((name, value))

                if modified:
                    scope = dict(scope)
                    scope["headers"] = new_headers

        await self.app(scope, receive, send)


# ============================================================================
# Register MCP Handlers
# ============================================================================

# NOTE: Using _mcp_server internals to register handlers.
# This matches Clarity/Unpack and is required for streamable_http mode.
# FastMCP doesn't expose a public API for custom handler registration.
# TODO: Revisit when FastMCP exposes a public hook for this pattern.

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
# Static Page Handlers
# ============================================================================

def _load_html(filename: str) -> str:
    """Load HTML file from assets directory."""
    try:
        return (ASSETS_PATH / filename).read_text()
    except FileNotFoundError:
        logger.error("asset.load.file_not_found", filename=filename)
        return f"<html><body><h1>Page not found</h1><p>{filename}</p></body></html>"
    except Exception as e:
        logger.error("asset.load.error", filename=filename, error=str(e))
        return "<html><body><h1>Error loading page</h1></body></html>"


async def landing_page(_request):
    """Serve landing page."""
    return HTMLResponse(_load_html("index.html"))


async def privacy_policy(_request):
    """Serve privacy policy."""
    return HTMLResponse(_load_html("privacy-policy.html"))


async def terms_of_service(_request):
    """Serve terms of service."""
    return HTMLResponse(_load_html("terms.html"))


async def openai_apps_challenge(_request):
    """Return OpenAI domain verification token."""
    # TODO: Replace with actual token from OpenAI app registration
    return PlainTextResponse(
        content="PLACEHOLDER_SHARPEN_VERIFICATION_TOKEN",
        media_type="text/plain"
    )


# ============================================================================
# App Factory
# ============================================================================

def create_app():
    """
    Create the ASGI application.

    FastMCP is the root app with:
    - CORS middleware for ChatGPT compatibility
    - Static routes for landing/legal pages
    - Header fix middleware for ChatGPT
    """
    fastmcp_app = mcp.streamable_http_app()

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
        allow_headers=["Content-Type", "Accept"],
        allow_credentials=False,
    )

    # Static routes for landing and legal pages
    static_routes = [
        Route("/", landing_page, methods=["GET"]),
        Route("/privacy-policy", privacy_policy, methods=["GET"]),
        Route("/terms", terms_of_service, methods=["GET"]),
    ]

    # Mount static routes at root level
    # Note: FastMCP handles /mcp, we add other routes
    for route in static_routes:
        fastmcp_app.routes.insert(0, route)

    # Discovery routes - OpenAI verification
    discovery_routes = [
        Route("/openai-apps-challenge", openai_apps_challenge, methods=["GET"]),
    ]
    discovery_app = Starlette(routes=discovery_routes)

    # Mount discovery routes under /.well-known
    fastmcp_app.mount("/.well-known", discovery_app)

    # Wrap with header-fix middleware
    # NOTE: This wraps the entire app (including static routes), but only
    # mutates headers for POST /mcp requests (guarded by path check inside).
    # This placement is intentional - middleware must wrap the CORS-enabled app.
    return MCPContentTypeAndAcceptFixMiddleware(fastmcp_app)


# ASGI entrypoint
app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8004"))

    logger.info(
        "sharpen.server.starting",
        host="127.0.0.1",
        port=port,
    )

    print("=" * 50)
    print("SHARPEN MCP SERVER - V1 (Foundation)")
    print(f"Starting on http://127.0.0.1:{port}")
    print(f"MCP endpoint: http://127.0.0.1:{port}/mcp")
    print("=" * 50)

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
