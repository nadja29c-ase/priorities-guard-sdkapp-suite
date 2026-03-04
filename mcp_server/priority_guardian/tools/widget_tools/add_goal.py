"""
add_goal tool for Priority Guardian MCP.

Private widget-only tool for adding goals to flexible priorities.
"""

import asyncio

import structlog
from mcp import types as mcp_types

from mcp_server.priority_guardian.http_client import backend_post
from ..base import ToolDefinition, ToolUsageError
from ..get_priorities import _normalize_priority

logger = structlog.get_logger(__name__)

# Timeout for backend calls (seconds) — must be under ChatGPT's ~10s window
TIMEOUT_S = 8.0


async def _call_with_timeout(coro, op_name: str):
    """Wrap a coroutine with timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=TIMEOUT_S)
    except asyncio.TimeoutError:
        raise ToolUsageError(f"{op_name} timed out. Please try again.")

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "add_goal"

DESCRIPTION = "Add a goal to a flexible priority (widget-only). Max 3 goals per priority."

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "priority_id": {
            "type": "string",
            "description": "Parent priority ID (UUID)",
        },
        "text": {
            "type": "string",
            "description": "Goal text (max 200 chars)",
            "maxLength": 200,
        },
    },
    "required": ["priority_id", "text"],
    "additionalProperties": False,
}

REQUIRED_SCOPES = ["pg.access"]

WIDGET_URI = "ui://widget/pg-dashboard.html"


# ============================================================================
# Handler
# ============================================================================

async def handle(user_id: str, correlation_id: str, arguments: dict) -> mcp_types.CallToolResult:
    """
    Add a goal to a flexible priority.

    Args:
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID
        arguments: Tool arguments (priority_id, text)

    Returns:
        CallToolResult with fresh priority list
    """
    logger.info(
        "tool.add_goal.start",
        correlation_id=correlation_id,
        user_id=user_id,
    )

    # Validate required fields
    priority_id = arguments.get("priority_id")
    text = arguments.get("text")

    if not priority_id:
        raise ToolUsageError("priority_id is required")
    if not text:
        raise ToolUsageError("text is required")

    # Call backend with timeout
    import httpx
    try:
        response = await _call_with_timeout(
            backend_post(
                f"/api/priority-guardian/priorities/{priority_id}/goals",
                {"text": text},
                user_id,
                correlation_id
            ),
            "Add goal",
        )
    except ToolUsageError:
        raise  # Re-raise timeout errors
    except Exception as e:
        logger.error(
            "tool.add_goal.backend_error",
            correlation_id=correlation_id,
            error=str(e),
        )
        if isinstance(e, httpx.HTTPStatusError):
            if e.response.status_code == 404:
                raise ToolUsageError("Priority not found.")
            if e.response.status_code == 409:
                raise ToolUsageError("Maximum 3 goals per priority. Delete a goal to add a new one.")
            if e.response.status_code == 422:
                raise ToolUsageError("Goals are only valid for flexible priorities.")
        raise ToolUsageError("Failed to add goal. Please try again.")

    # Use response directly - backend returns full priority list
    data = response.get("data", {})
    raw_priorities = data.get("priorities", [])
    google_connection = data.get("google_connection", {"connected": False})
    available_keywords = data.get("available_keywords", [])

    priorities = [_normalize_priority(p) for p in raw_priorities]

    logger.info(
        "tool.add_goal.success",
        correlation_id=correlation_id,
        user_id=user_id,
        priority_id=priority_id,
    )

    structured_content = {
        "success": True,
        "data": {
            "google_connected": google_connection.get("connected", False),
            "google_connected_at": google_connection.get("connected_at"),
            "priorities": priorities,
            "available_keywords": available_keywords,
        },
        "_meta": {
            "openai/outputTemplate": WIDGET_URI,
        },
        "assistant_guidance": "Goal added. The dashboard reflects the changes.",
    }

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text="Goal added."
        )],
        structuredContent=structured_content,
    )


# ============================================================================
# Tool Definition
# ============================================================================

ADD_GOAL = ToolDefinition(
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
