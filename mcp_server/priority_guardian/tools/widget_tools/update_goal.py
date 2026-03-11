"""
update_goal tool for Priority Guardian MCP.

Private widget-only tool for updating goal text or achieved status.
"""

import asyncio

import structlog
from mcp import types as mcp_types

from mcp_server.priority_guardian.http_client import backend_put
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
            "tool.update_goal.timeout",
            correlation_id=correlation_id,
            op_name=op_name,
            timeout=TIMEOUT_S,
        )
        raise ToolUsageError(f"{op_name} timed out. Please try again.")

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "update_goal"

DESCRIPTION = "Update a goal's text or achieved status (widget-only)."

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "goal_id": {
            "type": "string",
            "description": "Goal ID (UUID)",
        },
        "text": {
            "type": "string",
            "description": "New goal text (max 200 chars)",
            "maxLength": 200,
        },
        "achieved": {
            "type": "boolean",
            "description": "Whether the goal is achieved",
        },
    },
    "required": ["goal_id"],
    "additionalProperties": False,
}

REQUIRED_SCOPES = ["pg.access"]

WIDGET_URI = "ui://widget/pg-dashboard-v5.html"


# ============================================================================
# Handler
# ============================================================================

async def handle(user_id: str, correlation_id: str, arguments: dict) -> mcp_types.CallToolResult:
    """
    Update a goal's text or achieved status.

    Args:
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID
        arguments: Tool arguments (goal_id + optional text/achieved)

    Returns:
        CallToolResult with fresh priority list
    """
    logger.info(
        "tool.update_goal.start",
        correlation_id=correlation_id,
        user_id=user_id,
    )

    # Validate required fields
    goal_id = arguments.get("goal_id")
    if not goal_id:
        raise ToolUsageError("goal_id is required")

    # Build update payload (only include provided fields)
    payload = {}
    if "text" in arguments and arguments["text"] is not None:
        payload["text"] = arguments["text"]
    if "achieved" in arguments and arguments["achieved"] is not None:
        payload["achieved"] = arguments["achieved"]

    # Call backend with timeout
    import httpx
    try:
        response = await _call_with_timeout(
            backend_put(
                f"/api/priority-guardian/goals/{goal_id}",
                payload,
                user_id,
                correlation_id
            ),
            "Update goal",
            correlation_id,
        )
    except ToolUsageError:
        raise  # Re-raise timeout errors
    except Exception as e:
        logger.error(
            "tool.update_goal.backend_error",
            correlation_id=correlation_id,
            error=str(e),
        )
        if isinstance(e, httpx.HTTPStatusError):
            if e.response.status_code == 404:
                raise ToolUsageError("Goal not found.")
        raise ToolUsageError("Failed to update goal. Please try again.")

    # Use response directly - backend returns full priority list
    data = response.get("data", {})
    raw_priorities = data.get("priorities", [])
    google_connection = data.get("google_connection", {"connected": False})
    available_keywords = data.get("available_keywords", [])

    priorities = [_normalize_priority(p) for p in raw_priorities]

    logger.info(
        "tool.update_goal.success",
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
        "assistant_guidance": "Goal updated. The dashboard reflects the changes.",
    }

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text="Goal updated."
        )],
        structuredContent=structured_content,
    )


# ============================================================================
# Tool Definition
# ============================================================================

UPDATE_GOAL = ToolDefinition(
    name=NAME,
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=None,
    handle=handle,
    read_only_hint=False,
    destructive_hint=False,
    open_world_hint=False,
    widget_accessible=True,
    visibility="private",
)
