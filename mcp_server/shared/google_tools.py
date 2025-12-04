"""
Shared Google Calendar connection tools (Increment 18).

These tools are shared across all SDK apps since they all use
the same Google OAuth flow via the shared backend.

Usage:
    Each SDK app's server.py imports these functions and registers
    them with their own @mcp.tool decorator:

    from mcp_server.shared.google_tools import (
        connect_google_calendar_logic,
        disconnect_google_calendar_logic,
        CONNECT_GOOGLE_CALENDAR_DESCRIPTION,
        DISCONNECT_GOOGLE_CALENDAR_DESCRIPTION,
    )

    @mcp.tool(name="connect_google_calendar", description=CONNECT_GOOGLE_CALENDAR_DESCRIPTION)
    @handle_mcp_errors("connect_google_calendar")
    async def connect_google_calendar(meta: Optional[Dict[str, Any]] = None) -> str:
        return await connect_google_calendar_logic(
            meta=meta,
            authenticate_fn=authenticate_request,
            backend_get_fn=backend_get,
            backend_post_fn=backend_post,
            logger=logger,
        )
"""

import json
from typing import Any, Awaitable, Callable, Dict, Optional

import structlog

# Tool descriptions (shared for consistent UX across apps)
CONNECT_GOOGLE_CALENDAR_DESCRIPTION = (
    "Check Google Calendar connection status. "
    "If not connected, returns a secure link to connect your Google Calendar."
)

DISCONNECT_GOOGLE_CALENDAR_DESCRIPTION = (
    "Disconnect Google Calendar and revoke access tokens. "
    "Requires confirmation to proceed."
)

# Type aliases for clarity
AuthenticateFn = Callable[[str, Optional[Dict[str, Any]]], Awaitable[Dict[str, Any]]]
BackendGetFn = Callable[[str, str, str], Awaitable[Dict[str, Any]]]
BackendPostFn = Callable[[str, Dict[str, Any], str, str], Awaitable[Dict[str, Any]]]


async def connect_google_calendar_logic(
    *,
    meta: Optional[Dict[str, Any]],
    authenticate_fn: AuthenticateFn,
    backend_get_fn: BackendGetFn,
    backend_post_fn: BackendPostFn,
    logger: structlog.stdlib.BoundLogger,
) -> str:
    """
    Check Google Calendar connection status and provide connect URL if needed.

    This is the shared logic for the connect_google_calendar tool.
    Each SDK app registers this with their own @mcp.tool decorator.

    Security (Increment 18):
        - Uses opaque tokens instead of exposing user_id in URLs
        - Tokens are single-use and expire after 10 minutes
        - user_id never appears in browser URLs

    Args:
        meta: Request metadata (headers, correlation_id)
        authenticate_fn: App-specific authentication function
        backend_get_fn: App-specific backend GET helper
        backend_post_fn: App-specific backend POST helper
        logger: App-specific logger instance

    Returns:
        JSON string with:
        - If connected: status="connected", connected_at, message
        - If not connected: status="not_connected", connect_url, expires_in, message
    """
    tool_name = "connect_google_calendar"

    # Authenticate request and extract user identity
    auth_context = await authenticate_fn(tool_name, meta)

    user_id = auth_context["user_id"]
    correlation_id = auth_context["correlation_id"]

    logger.info(
        "tool.connect_google_calendar.start",
        correlation_id=correlation_id,
        user_id=user_id
    )

    # Check current connection status
    status_response = await backend_get_fn(
        "/api/focused/google/connection-status",
        user_id,
        correlation_id
    )

    if status_response.get("connected"):
        logger.info(
            "tool.connect_google_calendar.already_connected",
            correlation_id=correlation_id,
            user_id=user_id
        )
        return json.dumps({
            "success": True,
            "data": {
                "status": "connected",
                "connected_at": status_response.get("connected_at"),
                "message": "Google Calendar is already connected."
            }
        })

    # Not connected - get connection URL
    initiate_response = await backend_post_fn(
        "/api/focused/google/initiate-connection",
        {},
        user_id,
        correlation_id
    )

    # Extract token prefix for logging (handle missing or non-string tokens safely)
    token = initiate_response.get("token")
    token_prefix = token[:8] if isinstance(token, str) and token else None

    logger.info(
        "tool.connect_google_calendar.url_generated",
        correlation_id=correlation_id,
        user_id=user_id,
        token_prefix=token_prefix,
    )

    return json.dumps({
        "success": True,
        "data": {
            "status": "not_connected",
            "connect_url": initiate_response["connect_url"],
            "expires_in": initiate_response["expires_in"],
            "message": "Click the link to connect your Google Calendar. The link expires in 10 minutes."
        }
    })


async def disconnect_google_calendar_logic(
    *,
    confirm: bool,
    meta: Optional[Dict[str, Any]],
    authenticate_fn: AuthenticateFn,
    backend_get_fn: BackendGetFn,
    backend_post_fn: BackendPostFn,
    logger: structlog.stdlib.BoundLogger,
) -> str:
    """
    Disconnect Google Calendar and revoke tokens.

    This is the shared logic for the disconnect_google_calendar tool.
    Each SDK app registers this with their own @mcp.tool decorator.

    Args:
        confirm: Must be True to proceed with disconnection
        meta: Request metadata (headers, correlation_id)
        authenticate_fn: App-specific authentication function
        backend_get_fn: App-specific backend GET helper
        backend_post_fn: App-specific backend POST helper
        logger: App-specific logger instance

    Returns:
        JSON string with:
        - If confirm=false: error with CONFIRMATION_REQUIRED code
        - If not connected: status="not_connected"
        - If disconnected: status="disconnected", message
    """
    tool_name = "disconnect_google_calendar"

    # Authenticate request and extract user identity
    auth_context = await authenticate_fn(tool_name, meta)

    user_id = auth_context["user_id"]
    correlation_id = auth_context["correlation_id"]

    logger.info(
        "tool.disconnect_google_calendar.start",
        correlation_id=correlation_id,
        user_id=user_id,
        confirm=confirm
    )

    # Require explicit confirmation
    if not confirm:
        logger.info(
            "tool.disconnect_google_calendar.confirmation_required",
            correlation_id=correlation_id,
            user_id=user_id
        )
        return json.dumps({
            "success": False,
            "error": {
                "code": "CONFIRMATION_REQUIRED",
                "message": "Please confirm disconnection by setting confirm=true. This will revoke access and delete cached calendar data."
            }
        })

    # Check if connected first
    status_response = await backend_get_fn(
        "/api/focused/google/connection-status",
        user_id,
        correlation_id
    )

    if not status_response.get("connected"):
        logger.info(
            "tool.disconnect_google_calendar.not_connected",
            correlation_id=correlation_id,
            user_id=user_id
        )
        return json.dumps({
            "success": True,
            "data": {
                "status": "not_connected",
                "message": "Google Calendar is not connected."
            }
        })

    # Call disconnect endpoint (Increment 10)
    await backend_post_fn(
        "/api/focused/disconnect",
        {},
        user_id,
        correlation_id
    )

    logger.info(
        "tool.disconnect_google_calendar.success",
        correlation_id=correlation_id,
        user_id=user_id
    )

    return json.dumps({
        "success": True,
        "data": {
            "status": "disconnected",
            "message": "Google Calendar has been disconnected. Your calendar data has been removed."
        }
    })
