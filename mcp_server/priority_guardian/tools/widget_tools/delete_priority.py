"""
delete_priority tool for Priority Guardian MCP.

Private widget-only tool for deleting priorities.
Requires confirm=true to prevent accidental deletion.
"""

import asyncio

import structlog
from mcp import types as mcp_types

from mcp_server.priority_guardian.http_client import backend_delete
from ..base import ToolDefinition, ToolUsageError
from ..get_priorities import _normalize_priority

logger = structlog.get_logger(__name__)

# Timeout for backend calls (seconds) — must be under ChatGPT's ~10s window
TIMEOUT_S = 8.0


async def _call_with_timeout(coro, op_name: str, correlation_id: str):
    """Wrap a coroutine with timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=TIMEOUT_S)
    except asyncio.TimeoutError:
        logger.warning(
            "tool.delete_priority.timeout",
            correlation_id=correlation_id,
            op_name=op_name,
            timeout=TIMEOUT_S,
        )
        raise ToolUsageError(f"{op_name} timed out. Please try again.")

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "delete_priority"

DESCRIPTION = "Delete a priority and its deliverables (widget-only, requires confirmation)."

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "priority_id": {
            "type": "string",
            "description": "Priority ID (UUID)",
        },
        "confirm": {
            "type": "boolean",
            "description": "Must be true to confirm deletion",
        },
    },
    "required": ["priority_id", "confirm"],
    "additionalProperties": False,
}

REQUIRED_SCOPES = ["pg.access"]

WIDGET_URI = "ui://widget/pg-dashboard-v7.html"


# ============================================================================
# Handler
# ============================================================================

async def handle(user_id: str, correlation_id: str, arguments: dict) -> mcp_types.CallToolResult:
    """
    Delete a priority.

    Args:
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID
        arguments: Tool arguments (priority_id, confirm)

    Returns:
        CallToolResult with fresh priority list
    """
    logger.info(
        "tool.delete_priority.start",
        correlation_id=correlation_id,
        user_id=user_id,
    )

    # Validate required fields
    priority_id = arguments.get("priority_id")
    confirm = arguments.get("confirm")

    if not priority_id:
        raise ToolUsageError("priority_id is required")
    if confirm is not True:
        raise ToolUsageError("confirm must be true to delete a priority")

    # Call backend with timeout - mutation endpoints return full priority list
    import httpx
    try:
        response = await _call_with_timeout(
            backend_delete(
                f"/api/priority-guardian/priorities/{priority_id}",
                user_id,
                correlation_id
            ),
            "Delete priority",
            correlation_id,
        )
    except ToolUsageError:
        raise  # Re-raise timeout errors
    except Exception as e:
        logger.error(
            "tool.delete_priority.backend_error",
            correlation_id=correlation_id,
            error=str(e),
        )
        if isinstance(e, httpx.HTTPStatusError):
            if e.response.status_code == 404:
                raise ToolUsageError("Priority not found.")
        raise ToolUsageError("Failed to delete priority. Please try again.")

    # Use response directly - backend returns full priority list
    data = response.get("data", {})
    raw_priorities = data.get("priorities", [])
    google_connection = data.get("google_connection", {"connected": False})
    available_keywords = data.get("available_keywords", [])

    priorities = [_normalize_priority(p) for p in raw_priorities]

    logger.info(
        "tool.delete_priority.success",
        correlation_id=correlation_id,
        user_id=user_id,
        priority_id=priority_id,
    )

    structured_content = {
        "success": True,
        "data": {
            "google_connected": google_connection.get("connected", False),
            "priorities": priorities,
            "available_keywords": available_keywords,
        },
        "_meta": {
            "openai/outputTemplate": WIDGET_URI,
        },
        "assistant_guidance": "Priority deleted. The dashboard shows the updated list.",
    }

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text="Priority deleted."
        )],
        structuredContent=structured_content,
    )


# ============================================================================
# Tool Definition
# ============================================================================

DELETE_PRIORITY = ToolDefinition(
    name=NAME,
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=None,
    handle=handle,
    read_only_hint=False,
    destructive_hint=True,  # This is a destructive operation
    open_world_hint=False,
    widget_accessible=True,
    visibility="private",
)
