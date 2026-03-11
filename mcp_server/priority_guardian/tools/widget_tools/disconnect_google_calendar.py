"""
disconnect_google_calendar tool for Priority Guardian MCP.

Disconnect Google Calendar and revoke tokens.
"""

import asyncio

import structlog
from mcp import types as mcp_types

from mcp_server.priority_guardian.http_client import backend_get, backend_post
from ..base import ToolDefinition, ToolUsageError
from .constants import WIDGET_URI

logger = structlog.get_logger(__name__)

# Timeout for backend calls (seconds) — must be under ChatGPT's ~10s window
TIMEOUT_S = 8.0


async def _call_with_timeout(coro, op_name: str, correlation_id: str):
    """Wrap a coroutine with timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=TIMEOUT_S)
    except asyncio.TimeoutError:
        logger.warning(
            "tool.disconnect_google_calendar.timeout",
            correlation_id=correlation_id,
            op_name=op_name,
            timeout=TIMEOUT_S,
        )
        raise ToolUsageError(f"{op_name} timed out. Please try again.")

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "disconnect_google_calendar"

DESCRIPTION = "Disconnect Google Calendar and revoke access tokens. No data is deleted — you can reconnect anytime. Requires confirmation to proceed."

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "confirm": {
            "type": "boolean",
            "description": "Must be true to confirm disconnection",
        },
    },
    "required": [],
    "additionalProperties": False,
}

REQUIRED_SCOPES = ["pg.access"]


# ============================================================================
# Handler
# ============================================================================

async def handle(user_id: str, correlation_id: str, arguments: dict) -> mcp_types.CallToolResult:
    """
    Disconnect Google Calendar and revoke tokens.

    PG-specific implementation using PG backend paths.

    Args:
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID
        arguments: Tool arguments (confirm: bool)

    Returns:
        CallToolResult with disconnection status
    """
    confirm = arguments.get("confirm", False)

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
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="Please confirm disconnection by setting confirm=true. This will revoke Google Calendar access. No user data is deleted."
            )],
            structuredContent={
                "success": False,
                "error": {
                    "code": "CONFIRMATION_REQUIRED",
                    "message": "Please confirm disconnection by setting confirm=true. This will revoke Google Calendar access. No user data is deleted."
                },
                "_meta": {
                    "openai/outputTemplate": WIDGET_URI,
                },
            },
            isError=True,
        )

    # Check if connected first (PG backend path) with timeout
    status_response = await _call_with_timeout(
        backend_get(
            "/api/priority-guardian/google/connection-status",
            user_id,
            correlation_id
        ),
        "Check connection status",
        correlation_id,
    )

    if not status_response.get("connected"):
        logger.info(
            "tool.disconnect_google_calendar.not_connected",
            correlation_id=correlation_id,
            user_id=user_id
        )
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="Google Calendar is not connected."
            )],
            structuredContent={
                "success": True,
                "data": {
                    "status": "not_connected",
                    "message": "Google Calendar is not connected."
                },
                "_meta": {
                    "openai/outputTemplate": WIDGET_URI,
                },
            },
        )

    # Call disconnect endpoint (PG backend path) with timeout
    await _call_with_timeout(
        backend_post(
            "/api/priority-guardian/disconnect",
            {},
            user_id,
            correlation_id
        ),
        "Disconnect calendar",
        correlation_id,
    )

    logger.info(
        "tool.disconnect_google_calendar.success",
        correlation_id=correlation_id,
        user_id=user_id
    )

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text="Google Calendar has been disconnected. You can reconnect anytime."
        )],
        structuredContent={
            "success": True,
            "data": {
                "status": "disconnected",
                "message": "Google Calendar has been disconnected. You can reconnect anytime."
            },
            "_meta": {
                "openai/outputTemplate": WIDGET_URI,
            },
        },
    )


# ============================================================================
# Tool Definition
# ============================================================================

DISCONNECT_GOOGLE_CALENDAR = ToolDefinition(
    name=NAME,
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=WIDGET_URI,
    handle=handle,
    read_only_hint=False,   # Revokes tokens, modifies state
    destructive_hint=True,   # Irreversible - revokes access
    open_world_hint=True,    # Revokes external Google OAuth tokens
    widget_accessible=True,  # Widget can call this tool
    visibility="private",    # Widget-only, LLM cannot see or call
)
