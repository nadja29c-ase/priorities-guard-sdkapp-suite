#!/usr/bin/env python3
"""
Focused MCP Server - Thin wrapper around backend REST API (Increment 7D + 14).

This MCP server forwards tool calls to the backend HTTP API with:
- JWT authentication (OAuth 2.1 Bearer tokens)
- Per-tool scope enforcement with security metadata (Increment 14)
- OAuth Protected Resource discovery endpoint (Increment 14)
- Correlation ID propagation
- User identity extraction from tokens

No business logic, database access, or Google API calls happen here.

Usage:
    python -m mcp.focused.server

Or:
    python mcp/focused/server.py
"""

import json
import uvicorn
import httpx
import structlog
from typing import Optional, Dict, Any, Callable
from functools import wraps
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route, Mount

from mcp_server.focused.discovery import (
    openid_configuration,
    oauth_authorization_server,
    oauth_protected_resource,
)

from mcp_server.focused.config import (
    BACKEND_URL,
    MCP_SERVER_URL,
    OAUTH_ISSUER_URL,
)
from mcp_server.focused.mcp_auth import (
    authenticate_request,
    UnauthorizedError,
    InsufficientScopeError,
    build_unauthorized_error,
    build_forbidden_error,
    _jwks_cache,
)

logger = structlog.get_logger(__name__)

# Create FastMCP instance with stateless HTTP mode
# Stateless mode returns JSON directly instead of SSE streams,
# which is simpler for single-request patterns (ChatGPT, tests)
mcp = FastMCP("focused-mcp", stateless_http=True, streamable_http_path="/mcp")

# Shared HTTP client for calling backend API
http_client: httpx.AsyncClient | None = None


# ============================================================================
# Startup Configuration Validation
# ============================================================================

# Log resolved OAuth config (helps debug Railway env var issues)
logger.info(
    "oauth.config.resolved",
    BACKEND_URL=BACKEND_URL,
    OAUTH_ISSUER_URL=OAUTH_ISSUER_URL,
    MCP_SERVER_URL=MCP_SERVER_URL,
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
# OAuth Discovery Endpoints (Increment 15)
# Starlette wrappers for discovery.py functions
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


def handle_mcp_errors(tool_name: str) -> Callable:
    """
    Decorator to handle common MCP tool errors (DRY).

    Handles:
    - UnauthorizedError (401)
    - InsufficientScopeError (403)
    - HTTPStatusError (backend HTTP errors)
    - RequestError (connection failures, DNS, timeouts)
    - Generic exceptions

    Args:
        tool_name: Name of the tool for logging

    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> str:
            # Extract correlation_id from meta for error logging
            meta = kwargs.get("meta") or {}
            correlation_id = meta.get("correlation_id", "unknown")

            try:
                return await func(*args, **kwargs)

            except UnauthorizedError as e:
                # Token validation failed (401)
                error_response = build_unauthorized_error(e.error, e.description)
                return json.dumps(error_response)

            except InsufficientScopeError as e:
                # Missing required scopes (403)
                error_response = build_forbidden_error(e.required_scopes, e.actual_scopes)
                return json.dumps(error_response)

            except httpx.HTTPStatusError as e:
                # Backend returned an error status (4xx, 5xx)
                logger.error(
                    f"tool.{tool_name}.backend_error",
                    correlation_id=correlation_id,
                    status_code=e.response.status_code,
                    error=e.response.text
                )

                try:
                    error_data = e.response.json()
                    return json.dumps(error_data)
                except Exception:
                    return json.dumps({
                        "success": False,
                        "error": {
                            "code": "BACKEND_ERROR",
                            "message": f"Backend API returned {e.response.status_code}"
                        }
                    })

            except httpx.RequestError as e:
                # Connection failure (DNS, timeout, refused, etc.)
                logger.error(
                    f"tool.{tool_name}.connection_error",
                    correlation_id=correlation_id,
                    error_type=type(e).__name__,
                    url=str(e.request.url) if e.request else None,
                    error=str(e)
                )

                return json.dumps({
                    "success": False,
                    "error": {
                        "code": "BACKEND_UNAVAILABLE",
                        "message": "Backend API is unavailable"
                    }
                })

            except Exception as e:
                # Unexpected error
                logger.error(
                    f"tool.{tool_name}.unexpected_error",
                    correlation_id=correlation_id,
                    error_type=type(e).__name__,
                    error=str(e)
                )

                return json.dumps({
                    "success": False,
                    "error": {
                        "code": "MCP_ERROR",
                        "message": "An unexpected error occurred"
                    }
                })

        return wrapper
    return decorator


async def backend_post(
    path: str,
    json_data: dict,
    user_id: str,
    correlation_id: str
) -> dict:
    """
    Send a POST request to the backend API with user identity headers.

    Args:
        path: API path (e.g., "/api/focused/check_calendar")
        json_data: Request payload
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID for tracing

    Returns:
        Response JSON from backend

    Raises:
        httpx.HTTPStatusError: If backend returns error status
    """
    url = f"{BACKEND_URL}{path}"

    # Add user identity headers (Increment 7D)
    headers = {
        "X-User-ID": user_id,
        "X-Correlation-ID": correlation_id,
    }

    logger.info(
        "backend.api.call",
        correlation_id=correlation_id,
        url=path,
        user_id=user_id
    )

    resp = await http_client.post(url, json=json_data, headers=headers)
    resp.raise_for_status()
    return resp.json()


@mcp.tool(
    name="check_calendar",
    description="Identify focus blocks in Google Calendar. Scans events for focus-related keywords and returns matching events."
)
@handle_mcp_errors("check_calendar")
async def check_calendar(
    time_start: str | None = None,
    time_end: str | None = None,
    max_results: int = 20,
    meta: Optional[Dict[str, Any]] = None
) -> str:
    """
    Identify focus blocks in Google Calendar.

    Requires OAuth scope: focused.read

    Keywords are determined by the backend from:
    - System default keywords (e.g., "focus", "deep work")
    - User's custom keywords stored in the database

    This is a thin MCP wrapper that forwards the request to the backend API.

    Args:
        time_start: Start time (ISO8601), defaults to now
        time_end: End time (ISO8601), defaults to now + 7 days
        max_results: Max events to scan (1-50), defaults to 20
        meta: Request metadata (headers, correlation_id)

    Returns:
        JSON string with success status and data/error
    """
    tool_name = "check_calendar"

    # Authenticate request and extract user identity
    auth_context = await authenticate_request(tool_name, meta)

    user_id = auth_context["user_id"]
    correlation_id = auth_context["correlation_id"]

    logger.info(
        "tool.check_calendar.start",
        correlation_id=correlation_id,
        user_id=user_id,
        max_results=max_results
    )

    # Forward request to backend API with identity headers
    response = await backend_post(
        "/api/focused/check_calendar",
        {
            "time_start": time_start,
            "time_end": time_end,
            "max_results": max_results
        },
        user_id=user_id,
        correlation_id=correlation_id
    )

    # Backend already returns {success: bool, data/error: ...}
    return json.dumps(response)


@mcp.tool(
    name="watch_calendar",
    description="Register webhook for Google Calendar push notifications. Enables real-time calendar event updates."
)
@handle_mcp_errors("watch_calendar")
async def watch_calendar(
    meta: Optional[Dict[str, Any]] = None
) -> str:
    """
    Register webhook for Google Calendar push notifications.

    Requires OAuth scope: focused.write

    Registers a webhook channel with Google to receive real-time
    calendar event updates instead of polling.

    Args:
        meta: Request metadata (headers, correlation_id)

    Returns:
        JSON string with success status and data/error
    """
    tool_name = "watch_calendar"

    # Authenticate request and extract user identity
    auth_context = await authenticate_request(tool_name, meta)

    user_id = auth_context["user_id"]
    correlation_id = auth_context["correlation_id"]

    logger.info(
        "tool.watch_calendar.start",
        correlation_id=correlation_id,
        user_id=user_id
    )

    # Forward request to backend API with identity headers
    response = await backend_post(
        "/api/focused/watch_calendar",
        {"user_id": user_id},  # Keep in payload for backward compat
        user_id=user_id,
        correlation_id=correlation_id
    )

    return json.dumps(response)


@mcp.tool(
    name="run_focus_mode",
    description="Activate or deactivate Apple Focus Mode via iOS Shortcuts. Generates a shortcut:// URL for the ChatGPT client."
)
@handle_mcp_errors("run_focus_mode")
async def run_focus_mode(
    action: str,
    trigger_source: str,
    session_id: str | None = None,
    session_title: str | None = None,
    duration_minutes: int | None = None,
    user_confirmation: bool | None = None,
    meta: Optional[Dict[str, Any]] = None
) -> str:
    """
    Activate or deactivate Apple Focus Mode via iOS Shortcuts.

    Requires OAuth scope: focused.write

    This tool generates a shortcut:// URL that the ChatGPT client
    should open to trigger Apple Focus Mode on the user's device.

    One active session per user rule:
    - Must deactivate before re-activating
    - Returns "already_active" if trying to activate when already active

    Args:
        action: "on" to activate, "off" to deactivate
        trigger_source: "calendar" (from detected event) or "user" (manual)
        session_id: Focus session UUID (required for calendar-triggered)
        session_title: Session title (e.g., "Work", "Do Not Disturb")
        duration_minutes: Auto-deactivate after this many minutes (1-480)
        user_confirmation: User confirmed activation (required for action="on")
        meta: Request metadata (headers, correlation_id)

    Returns:
        JSON string with:
        - shortcut_status: "success" | "failed" | "already_active" | "already_inactive"
        - shortcut_url: URL for ChatGPT client to open
        - session_title: The session title used
        - start_time: ISO 8601 timestamp
        - end_time: ISO 8601 timestamp | None
        - message: Human-readable status message
    """
    tool_name = "run_focus_mode"

    # Authenticate request and extract user identity
    auth_context = await authenticate_request(tool_name, meta)

    user_id = auth_context["user_id"]
    correlation_id = auth_context["correlation_id"]

    logger.info(
        "tool.run_focus_mode.start",
        correlation_id=correlation_id,
        user_id=user_id,
        action=action,
        trigger_source=trigger_source,
    )

    # Forward request to backend API with identity headers
    response = await backend_post(
        "/api/focused/tools/run_focus_mode",
        {
            "action": action,
            "trigger_source": trigger_source,
            "session_id": session_id,
            "session_title": session_title,
            "duration_minutes": duration_minutes,
            "user_confirmation": user_confirmation,
        },
        user_id=user_id,
        correlation_id=correlation_id
    )

    # Backend already returns {success: bool, data/error: ...}
    return json.dumps(response)


@mcp.tool(
    name="notify_user",
    description="Send notification to user. Currently a stub for future implementation."
)
@handle_mcp_errors("notify_user")
async def notify_user(
    meta: Optional[Dict[str, Any]] = None
) -> str:
    """
    Send notification to user (stub for future implementation).

    Requires OAuth scope: focused.notify

    Args:
        meta: Request metadata (headers, correlation_id)

    Returns:
        JSON string with error indicating not implemented
    """
    tool_name = "notify_user"

    # Authenticate request (enforces focused.notify scope)
    auth_context = await authenticate_request(tool_name, meta)

    correlation_id = auth_context["correlation_id"]

    logger.info(
        "tool.notify_user.not_implemented",
        correlation_id=correlation_id
    )

    return json.dumps({
        "success": False,
        "error": {
            "code": "NOT_IMPLEMENTED",
            "message": "notify_user is not yet implemented"
        }
    })


# ============================================================================
# Application Factory (Increment 14)
# ============================================================================

def create_app() -> Starlette:
    """
    Clean ASGI app mounting for MCP compatibility with ChatGPT.
    No redirect, no slash normalization, no middleware that consumes the body.
    """
    fastmcp_asgi = mcp.streamable_http_app()

    @asynccontextmanager
    async def combined_lifespan(_app):  # noqa: ARG001
        global http_client

        if http_client is None:
            http_client = httpx.AsyncClient(timeout=30.0)
            logger.info("http_client.initialized")

        async with fastmcp_asgi.router.lifespan_context(fastmcp_asgi):
            yield

        if http_client is not None:
            await http_client.aclose()
            http_client = None
            logger.info("http_client.closed")

        await _jwks_cache.aclose()

    routes = [
        # ROOT DISCOVERY
        Route("/.well-known/openid-configuration", wellknown_openid_configuration),
        Route("/.well-known/oauth-authorization-server", wellknown_oauth_authorization_server),
        Route("/.well-known/oauth-protected-resource", wellknown_oauth_protected_resource),

        # PREFIXED DISCOVERY
        Route("/mcp/.well-known/openid-configuration", wellknown_openid_configuration),
        Route("/mcp/.well-known/oauth-authorization-server", wellknown_oauth_authorization_server),
        Route("/mcp/.well-known/oauth-protected-resource", wellknown_oauth_protected_resource),

        # *** MCP ENDPOINT - Route directly, no Mount ***
        Route("/mcp", fastmcp_asgi, methods=["POST"]),
    ]

    return Starlette(routes=routes, lifespan=combined_lifespan)


# --------------------------------------------------------------------
# ASGI entrypoint for uvicorn (Railway imports this)
# --------------------------------------------------------------------
app = create_app()


if __name__ == "__main__":
    import os

    # Initialize HTTP client
    http_client = httpx.AsyncClient(timeout=30.0)

    # Use PORT env var (Railway sets this) or default to 8001 for local dev
    port = int(os.getenv("PORT", "8001"))

    logger.info(
        "Starting Focused MCP server",
        host="0.0.0.0",
        port=port,
        mcp_server_url=MCP_SERVER_URL,
        oauth_issuer_url=OAUTH_ISSUER_URL
    )

    # Run with uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port)
