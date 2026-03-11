"""
connect_google_calendar tool for Priority Guardian MCP.

Check Google Calendar connection status and provide connect URL if needed.
"""

import asyncio

import structlog
from mcp import types as mcp_types

from mcp_server.priority_guardian.http_client import backend_get, backend_post
from ..base import ToolDefinition, ToolUsageError

logger = structlog.get_logger(__name__)

# Timeout for backend calls (seconds) — must be under ChatGPT's ~10s window
TIMEOUT_S = 8.0


async def _call_with_timeout(coro, op_name: str, correlation_id: str):
    """Wrap a coroutine with timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=TIMEOUT_S)
    except asyncio.TimeoutError:
        logger.warning(
            "tool.connect_google_calendar.timeout",
            correlation_id=correlation_id,
            op_name=op_name,
            timeout=TIMEOUT_S,
        )
        raise ToolUsageError(f"{op_name} timed out. Please try again.")

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "connect_google_calendar"

DESCRIPTION = "Check Google Calendar connection status. If not connected, returns a secure link to connect your Google Calendar."

INPUT_SCHEMA = {
    "type": "object",
    "properties": {},
    "required": [],
    "additionalProperties": False,
}

REQUIRED_SCOPES = ["pg.access"]

WIDGET_URI = "ui://widget/pg-dashboard-v4.html"


# ============================================================================
# Handler
# ============================================================================

async def handle(user_id: str, correlation_id: str, arguments: dict) -> mcp_types.CallToolResult:
    """
    Check Google Calendar connection status and provide connect URL if needed.

    PG-specific implementation using PG backend paths.

    Args:
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID
        arguments: Tool arguments (none expected)

    Returns:
        CallToolResult with connection status or connect URL
    """
    logger.info(
        "tool.connect_google_calendar.start",
        correlation_id=correlation_id,
        user_id=user_id
    )

    # Check current connection status (PG backend path) with timeout
    status_response = await _call_with_timeout(
        backend_get(
            "/api/priority-guardian/google/connection-status",
            user_id,
            correlation_id
        ),
        "Check connection status",
        correlation_id,
    )

    if status_response.get("connected"):
        logger.info(
            "tool.connect_google_calendar.already_connected",
            correlation_id=correlation_id,
            user_id=user_id
        )
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="Google Calendar is already connected."
            )],
            structuredContent={
                "success": True,
                "data": {
                    "status": "connected",
                    "connected_at": status_response.get("connected_at"),
                    "message": "Google Calendar is already connected."
                },
                "_meta": {
                    "openai/outputTemplate": WIDGET_URI,
                },
            },
        )

    # Not connected - get connection URL (PG backend path) with timeout
    initiate_response = await _call_with_timeout(
        backend_post(
            "/api/priority-guardian/google/initiate-connection",
            {},
            user_id,
            correlation_id
        ),
        "Initiate connection",
        correlation_id,
    )

    # Extract connection URL with safe access
    connect_url = initiate_response.get("connect_url")
    expires_in = initiate_response.get("expires_in")

    if not connect_url:
        raise ToolUsageError("Failed to initiate Google Calendar connection. Please try again.")

    # Extract token prefix for logging (handle missing or non-string tokens safely)
    token = initiate_response.get("token")
    token_prefix = token[:8] if isinstance(token, str) and token else None

    logger.info(
        "tool.connect_google_calendar.url_generated",
        correlation_id=correlation_id,
        user_id=user_id,
        token_prefix=token_prefix,
    )

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Click the link to connect your Google Calendar. The link expires in 10 minutes."
        )],
        structuredContent={
            "success": True,
            "data": {
                "status": "not_connected",
                "connect_url": connect_url,
                "expires_in": expires_in,
                "message": "Click the link to connect your Google Calendar. The link expires in 10 minutes."
            },
            "_meta": {
                "openai/outputTemplate": WIDGET_URI,
            },
        },
    )


# ============================================================================
# Tool Definition
# ============================================================================

CONNECT_GOOGLE_CALENDAR = ToolDefinition(
    name=NAME,
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=WIDGET_URI,
    handle=handle,
    read_only_hint=False,   # Initiates OAuth flow, modifies connection state
    destructive_hint=False,
    open_world_hint=True,   # Initiates external Google OAuth flow
    widget_accessible=True, # Widget can call this tool
    visibility="private",   # Widget-only, LLM cannot see or call
)
