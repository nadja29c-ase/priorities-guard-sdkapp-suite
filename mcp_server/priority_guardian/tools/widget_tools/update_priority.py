"""
update_priority tool for Priority Guardian MCP.

Private widget-only tool for editing priority fields.
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
            "tool.update_priority.timeout",
            correlation_id=correlation_id,
            op_name=op_name,
            timeout=TIMEOUT_S,
        )
        raise ToolUsageError(f"{op_name} timed out. Please try again.")

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "update_priority"

DESCRIPTION = "Update a priority's fields (widget-only). If the requested keyword is held by another active priority, they automatically swap keywords."

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "priority_id": {
            "type": "string",
            "description": "Priority ID (UUID)",
        },
        "name": {
            "type": "string",
            "description": "New priority name (max 100 chars)",
            "maxLength": 100,
        },
        "calendar_keyword": {
            "type": "string",
            "enum": ["P1", "P2", "P3"],
            "description": "Reassign keyword badge. If held by another priority, they swap.",
        },
        "deadline": {
            "type": "string",
            "format": "date",
            "description": "New deadline date (deadline type only, ISO format)",
        },
        "weekly_hour_target": {
            "type": "number",
            "description": "New hours per week target (flexible type only)",
            "exclusiveMinimum": 0,
        },
        "checkpoint_date": {
            "type": "string",
            "format": "date",
            "description": "New checkpoint date (flexible type only, ISO format)",
        },
    },
    "required": ["priority_id"],
    "additionalProperties": False,
}

REQUIRED_SCOPES = ["pg.access"]

WIDGET_URI = "ui://widget/pg-dashboard.html"


# ============================================================================
# Handler
# ============================================================================

async def handle(user_id: str, correlation_id: str, arguments: dict) -> mcp_types.CallToolResult:
    """
    Update a priority's fields.

    Args:
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID
        arguments: Tool arguments (priority_id + partial fields)

    Returns:
        CallToolResult with fresh priority list
    """
    logger.info(
        "tool.update_priority.start",
        correlation_id=correlation_id,
        user_id=user_id,
    )

    # Validate required fields
    priority_id = arguments.get("priority_id")
    if not priority_id:
        raise ToolUsageError("priority_id is required")

    # Validate name if provided (reject whitespace-only)
    name = arguments.get("name")
    if name is not None and (not name or not name.strip()):
        raise ToolUsageError("Name cannot be empty or whitespace-only.")

    # Build update payload (only include provided fields)
    payload = {}
    if name is not None:
        payload["name"] = name.strip()
    if "calendar_keyword" in arguments and arguments["calendar_keyword"] is not None:
        payload["calendar_keyword"] = arguments["calendar_keyword"]
    if "deadline" in arguments and arguments["deadline"] is not None:
        payload["deadline"] = arguments["deadline"]
    if "weekly_hour_target" in arguments and arguments["weekly_hour_target"] is not None:
        payload["weekly_hour_target"] = arguments["weekly_hour_target"]
    if "checkpoint_date" in arguments and arguments["checkpoint_date"] is not None:
        payload["checkpoint_date"] = arguments["checkpoint_date"]

    if not payload:
        raise ToolUsageError("No fields provided to update.")

    # Call backend with timeout - mutation endpoints return full priority list
    import httpx
    try:
        response = await _call_with_timeout(
            backend_put(
                f"/api/priority-guardian/priorities/{priority_id}",
                payload,
                user_id,
                correlation_id
            ),
            "Update priority",
            correlation_id,
        )
    except ToolUsageError:
        raise  # Re-raise timeout errors
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        logger.warning(
            "tool.update_priority.backend_error",
            correlation_id=correlation_id,
            status_code=status_code,
            error_type=type(e).__name__,
        )

        if status_code == 404:
            raise ToolUsageError("Priority not found.")
        if status_code == 422:
            raise ToolUsageError("Invalid field for this priority type.")
        if status_code == 409:
            # Parse error code to distinguish MAX_PRIORITIES_REACHED vs KEYWORD_CONFLICT
            try:
                error_data = e.response.json()
                error_code = error_data.get("error", {}).get("code", "UNKNOWN")
            except Exception:
                error_code = "UNKNOWN"

            if error_code == "MAX_PRIORITIES_REACHED":
                raise ToolUsageError("You already have 3 active priorities.")
            elif error_code == "KEYWORD_CONFLICT":
                raise ToolUsageError("Keyword conflict during reassignment. Please retry.")
            else:
                raise ToolUsageError("Conflict occurred. Please retry.")

        raise ToolUsageError("Failed to update priority. Please try again.")
    except Exception as e:
        logger.error(
            "tool.update_priority.unexpected_error",
            correlation_id=correlation_id,
            error_type=type(e).__name__,
        )
        raise ToolUsageError("Failed to update priority. Please try again.")

    # Use response directly - backend returns full priority list
    data = response.get("data", {})
    raw_priorities = data.get("priorities", [])
    google_connection = data.get("google_connection", {"connected": False})
    available_keywords = data.get("available_keywords", [])

    priorities = [_normalize_priority(p) for p in raw_priorities]

    logger.info(
        "tool.update_priority.success",
        correlation_id=correlation_id,
        user_id=user_id,
        priority_id=priority_id,
    )

    # Build assistant guidance - include keyword reminder if keyword was changed
    new_keyword = payload.get("calendar_keyword")
    if new_keyword:
        assistant_guidance = (
            f"Priority updated. The keyword is now {new_keyword}. "
            f"Remind the user to add {new_keyword} to future calendar event titles "
            f"to track time for this priority."
        )
    else:
        assistant_guidance = "Priority updated. The dashboard reflects the changes."

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
        "assistant_guidance": assistant_guidance,
    }

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text="Priority updated."
        )],
        structuredContent=structured_content,
    )


# ============================================================================
# Tool Definition
# ============================================================================

UPDATE_PRIORITY = ToolDefinition(
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
