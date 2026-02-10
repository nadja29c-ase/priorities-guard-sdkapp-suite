"""
add_priority tool for Priority Guardian MCP.

Private widget-only tool for creating priorities post-onboarding.
Same backend endpoint as create_priority but with private visibility.
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

NAME = "add_priority"

DESCRIPTION = "Add a new priority (widget-only, post-onboarding)."

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Priority name (max 100 chars)",
            "maxLength": 100,
        },
        "type": {
            "type": "string",
            "enum": ["deadline", "flexible"],
            "description": "Priority type: deadline or flexible",
        },
        "deadline": {
            "type": "string",
            "format": "date",
            "description": "Hard end date (required for deadline type, ISO format)",
        },
        "weekly_hour_target": {
            "type": "number",
            "description": "Hours per week target (required for flexible type)",
            "exclusiveMinimum": 0,
        },
        "checkpoint_date": {
            "type": "string",
            "format": "date",
            "description": "Evaluation checkpoint (required for flexible type, ISO format)",
        },
        "desired_result": {
            "type": "string",
            "description": "Concrete outcome in ~1 month (required for flexible type)",
            "maxLength": 200,
        },
    },
    "required": ["name", "type"],
}

REQUIRED_SCOPES = ["pg.access"]

WIDGET_URI = "ui://widget/pg-dashboard.html"


# ============================================================================
# Handler
# ============================================================================

async def handle(user_id: str, correlation_id: str, arguments: dict) -> mcp_types.CallToolResult:
    """
    Create a new priority via widget.

    Args:
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID
        arguments: Tool arguments (name, type, deadline/flexible fields)

    Returns:
        CallToolResult with fresh priority list
    """
    logger.info(
        "tool.add_priority.start",
        correlation_id=correlation_id,
        user_id=user_id,
        priority_type=arguments.get("type"),
    )

    # Validate required fields
    name = arguments.get("name")
    priority_type = arguments.get("type")

    if not name:
        raise ToolUsageError("name is required")
    if not priority_type:
        raise ToolUsageError("type is required")
    if priority_type not in ("deadline", "flexible"):
        raise ToolUsageError("type must be 'deadline' or 'flexible'")

    # Build request payload
    payload = {
        "name": name,
        "type": priority_type,
    }

    if priority_type == "deadline":
        deadline = arguments.get("deadline")
        if not deadline:
            raise ToolUsageError("deadline is required for deadline type")
        payload["deadline"] = deadline
    else:  # flexible
        weekly_hour_target = arguments.get("weekly_hour_target")
        checkpoint_date = arguments.get("checkpoint_date")
        desired_result = arguments.get("desired_result")

        if weekly_hour_target is None:
            raise ToolUsageError("weekly_hour_target is required for flexible type")
        if not checkpoint_date:
            raise ToolUsageError("checkpoint_date is required for flexible type")
        if not desired_result:
            raise ToolUsageError("desired_result is required for flexible type")

        payload["weekly_hour_target"] = weekly_hour_target
        payload["checkpoint_date"] = checkpoint_date
        payload["desired_result"] = desired_result

    # Call backend
    try:
        response = await backend_post(
            "/api/priority-guardian/priorities",
            payload,
            user_id,
            correlation_id
        )
    except Exception as e:
        logger.error(
            "tool.add_priority.backend_error",
            correlation_id=correlation_id,
            error=str(e),
        )
        # Check for MAX_PRIORITIES_REACHED using proper httpx error handling
        import httpx
        if isinstance(e, httpx.HTTPStatusError):
            if e.response.status_code == 409:
                raise ToolUsageError("You already have 3 active priorities. Retire or delete one to add a new priority.")
            if e.response.status_code == 404:
                raise ToolUsageError("Priority not found.")
        raise ToolUsageError("Failed to create priority. Please try again.")

    # Extract priority data and fetch fresh list
    # Note: create_priority endpoint returns different shape, so we need to fetch fresh
    from mcp_server.priority_guardian.http_client import backend_get
    fresh_response = await backend_get(
        "/api/priority-guardian/priorities",
        user_id,
        correlation_id
    )

    data = fresh_response.get("data", {})
    raw_priorities = data.get("priorities", [])
    google_connection = data.get("google_connection", {"connected": False})
    available_keywords = data.get("available_keywords", [])

    priorities = [_normalize_priority(p) for p in raw_priorities]

    # Get assigned keyword from response
    created_priority = response.get("data", {}).get("priority", {})
    assigned_keyword = created_priority.get("calendar_keyword", "")

    logger.info(
        "tool.add_priority.success",
        correlation_id=correlation_id,
        user_id=user_id,
        assigned_keyword=assigned_keyword,
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
        "assistant_guidance": f"Priority created with keyword {assigned_keyword}. The dashboard shows the updated list.",
    }

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Priority created with keyword {assigned_keyword}."
        )],
        structuredContent=structured_content,
    )


# ============================================================================
# Tool Definition
# ============================================================================

ADD_PRIORITY = ToolDefinition(
    name=NAME,
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=None,  # Does not produce new widget, mutates existing
    handle=handle,
    read_only_hint=False,
    destructive_hint=False,
    open_world_hint=False,
    widget_accessible=True,
    visibility="private",  # Widget-only, LLM cannot see
)
