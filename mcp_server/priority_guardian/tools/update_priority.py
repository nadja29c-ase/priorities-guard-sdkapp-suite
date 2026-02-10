"""
update_priority tool for Priority Guardian MCP.

Private widget-only tool for editing priority fields.
"""

import structlog
from mcp import types as mcp_types

from mcp_server.priority_guardian.http_client import backend_put
from .base import ToolDefinition, ToolUsageError
from .get_priorities import _normalize_priority

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "update_priority"

DESCRIPTION = "Update a priority's fields (widget-only)."

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
        "desired_result": {
            "type": "string",
            "description": "New desired result (flexible type only)",
            "maxLength": 200,
        },
    },
    "required": ["priority_id"],
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

    # Build update payload (only include provided fields)
    payload = {}
    if "name" in arguments and arguments["name"] is not None:
        payload["name"] = arguments["name"]
    if "deadline" in arguments and arguments["deadline"] is not None:
        payload["deadline"] = arguments["deadline"]
    if "weekly_hour_target" in arguments and arguments["weekly_hour_target"] is not None:
        payload["weekly_hour_target"] = arguments["weekly_hour_target"]
    if "checkpoint_date" in arguments and arguments["checkpoint_date"] is not None:
        payload["checkpoint_date"] = arguments["checkpoint_date"]
    if "desired_result" in arguments and arguments["desired_result"] is not None:
        payload["desired_result"] = arguments["desired_result"]

    # Call backend - mutation endpoints return full priority list
    try:
        import httpx
        response = await backend_put(
            f"/api/priority-guardian/priorities/{priority_id}",
            payload,
            user_id,
            correlation_id
        )
    except Exception as e:
        logger.error(
            "tool.update_priority.backend_error",
            correlation_id=correlation_id,
            error=str(e),
        )
        if isinstance(e, httpx.HTTPStatusError):
            if e.response.status_code == 404:
                raise ToolUsageError("Priority not found.")
            if e.response.status_code == 422:
                raise ToolUsageError("Invalid field for this priority type.")
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
        "assistant_guidance": "Priority updated. The dashboard reflects the changes.",
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
