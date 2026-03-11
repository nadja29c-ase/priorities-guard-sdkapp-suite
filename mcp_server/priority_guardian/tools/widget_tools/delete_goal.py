"""
delete_goal tool for Priority Guardian MCP.

Private widget-only tool for deleting goals.
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
            "tool.delete_goal.timeout",
            correlation_id=correlation_id,
            op_name=op_name,
            timeout=TIMEOUT_S,
        )
        raise ToolUsageError(f"{op_name} timed out. Please try again.")

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "delete_goal"

DESCRIPTION = "Delete a goal from a priority (widget-only)."

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "goal_id": {
            "type": "string",
            "description": "Goal ID (UUID)",
        },
        "confirm": {
            "type": "boolean",
            "description": "Set to true to confirm deletion",
        },
    },
    "required": ["goal_id", "confirm"],
    "additionalProperties": False,
}

REQUIRED_SCOPES = ["pg.access"]

WIDGET_URI = "ui://widget/pg-dashboard-v3.html"


# ============================================================================
# Handler
# ============================================================================

async def handle(user_id: str, correlation_id: str, arguments: dict) -> mcp_types.CallToolResult:
    """
    Delete a goal.

    Args:
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID
        arguments: Tool arguments (goal_id, confirm)

    Returns:
        CallToolResult with fresh priority list
    """
    logger.info(
        "tool.delete_goal.start",
        correlation_id=correlation_id,
        user_id=user_id,
    )

    # Validate required fields
    goal_id = arguments.get("goal_id")
    confirm = arguments.get("confirm", False)

    if not goal_id:
        raise ToolUsageError("goal_id is required")
    if not confirm:
        raise ToolUsageError("confirm must be true to delete a goal")

    # Call backend with timeout
    import httpx
    try:
        response = await _call_with_timeout(
            backend_delete(
                f"/api/priority-guardian/goals/{goal_id}",
                user_id,
                correlation_id
            ),
            "Delete goal",
            correlation_id,
        )
    except ToolUsageError:
        raise  # Re-raise timeout errors
    except Exception as e:
        logger.error(
            "tool.delete_goal.backend_error",
            correlation_id=correlation_id,
            error=str(e),
        )
        if isinstance(e, httpx.HTTPStatusError):
            if e.response.status_code == 404:
                raise ToolUsageError("Goal not found.")
        raise ToolUsageError("Failed to delete goal. Please try again.")

    # Use response directly - backend returns full priority list
    data = response.get("data", {})
    raw_priorities = data.get("priorities", [])
    google_connection = data.get("google_connection", {"connected": False})
    available_keywords = data.get("available_keywords", [])

    priorities = [_normalize_priority(p) for p in raw_priorities]

    logger.info(
        "tool.delete_goal.success",
        correlation_id=correlation_id,
        user_id=user_id,
        goal_id=goal_id,
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
        "assistant_guidance": "Goal deleted. The dashboard reflects the changes.",
    }

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text="Goal deleted."
        )],
        structuredContent=structured_content,
    )


# ============================================================================
# Tool Definition
# ============================================================================

DELETE_GOAL = ToolDefinition(
    name=NAME,
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=None,
    handle=handle,
    read_only_hint=False,
    destructive_hint=True,
    open_world_hint=False,
    widget_accessible=True,
    visibility="private",
)
