"""
add_deliverable tool for Priority Guardian MCP.

Private widget-only tool for adding deliverables to a priority.
"""

import structlog
from mcp import types as mcp_types

from mcp_server.priority_guardian.http_client import backend_post
from .base import ToolDefinition, ToolUsageError
from .get_priorities import _normalize_priority

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "add_deliverable"

DESCRIPTION = "Add a deliverable to a deadline-driven priority (widget-only). Flexible priorities do not have deliverables."

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "priority_id": {
            "type": "string",
            "description": "Parent priority ID (UUID)",
        },
        "name": {
            "type": "string",
            "description": "Deliverable name (max 200 chars)",
            "maxLength": 200,
        },
    },
    "required": ["priority_id", "name"],
}

REQUIRED_SCOPES = ["pg.access"]

WIDGET_URI = "ui://widget/pg-dashboard.html"


# ============================================================================
# Handler
# ============================================================================

async def handle(user_id: str, correlation_id: str, arguments: dict) -> mcp_types.CallToolResult:
    """
    Add a deliverable to a priority.

    Args:
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID
        arguments: Tool arguments (priority_id, name)

    Returns:
        CallToolResult with fresh priority list
    """
    logger.info(
        "tool.add_deliverable.start",
        correlation_id=correlation_id,
        user_id=user_id,
    )

    # Validate required fields
    priority_id = arguments.get("priority_id")
    name = arguments.get("name")

    if not priority_id:
        raise ToolUsageError("priority_id is required")
    if not name:
        raise ToolUsageError("name is required")

    # Call backend - mutation endpoints return full priority list
    try:
        import httpx
        response = await backend_post(
            f"/api/priority-guardian/priorities/{priority_id}/deliverables",
            {"name": name},
            user_id,
            correlation_id
        )
    except Exception as e:
        logger.error(
            "tool.add_deliverable.backend_error",
            correlation_id=correlation_id,
            error=str(e),
        )
        if isinstance(e, httpx.HTTPStatusError):
            if e.response.status_code == 404:
                raise ToolUsageError("Priority not found.")
        raise ToolUsageError("Failed to add deliverable. Please try again.")

    # Use response directly - backend returns full priority list
    data = response.get("data", {})
    raw_priorities = data.get("priorities", [])
    google_connection = data.get("google_connection", {"connected": False})
    available_keywords = data.get("available_keywords", [])

    priorities = [_normalize_priority(p) for p in raw_priorities]

    logger.info(
        "tool.add_deliverable.success",
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
        "assistant_guidance": "Deliverable added. The dashboard shows the updated list.",
    }

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text="Deliverable added."
        )],
        structuredContent=structured_content,
    )


# ============================================================================
# Tool Definition
# ============================================================================

ADD_DELIVERABLE = ToolDefinition(
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
