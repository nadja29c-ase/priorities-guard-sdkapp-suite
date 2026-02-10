"""
get_priorities tool for Priority Guardian MCP.

Returns user's priorities with Google Calendar connection status.
This is the primary data-fetching tool for the PG widget.
"""

import structlog
from mcp import types as mcp_types

from mcp_server.priority_guardian.http_client import backend_get
from .base import ToolDefinition

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "get_priorities"

DESCRIPTION = "Get your current priorities and Google Calendar connection status."

INPUT_SCHEMA = {
    "type": "object",
    "properties": {},
    "required": [],
}

REQUIRED_SCOPES = ["pg.access"]

WIDGET_URI = "ui://widget/pg-dashboard.html"


# ============================================================================
# Helpers
# ============================================================================

def _normalize_priority(p: dict) -> dict:
    """
    Normalize priority fields from backend snake_case to spec camelCase.

    Backend returns: calendar_keyword, created_at, weekly_hour_target, etc.
    Spec expects: calendarKeyword, createdAt, weeklyHourTarget, etc.
    """
    # Normalize deliverables (already camelCase from backend, but ensure consistency)
    deliverables = p.get("deliverables", [])
    normalized_deliverables = [
        {
            "id": d.get("id"),
            "name": d.get("name"),
            "done": d.get("done", False),
        }
        for d in deliverables
    ]

    return {
        "id": p.get("id"),
        "name": p.get("name"),
        "type": p.get("type"),
        "calendarKeyword": p.get("calendar_keyword"),
        "status": p.get("status"),
        "deadline": p.get("deadline"),
        "weeklyHourTarget": p.get("weekly_hour_target"),
        "weeklyHourActual": p.get("weekly_hour_actual"),  # Future field
        "checkpointDate": p.get("checkpoint_date"),
        "desiredResult": p.get("desired_result"),
        "deliverables": normalized_deliverables,
        "createdAt": p.get("created_at"),
        "updatedAt": p.get("updated_at"),
    }


# ============================================================================
# Handler
# ============================================================================

async def handle(user_id: str, correlation_id: str, arguments: dict) -> mcp_types.CallToolResult:
    """
    Get user's priorities with connection status.

    Args:
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID
        arguments: Tool arguments (none expected)

    Returns:
        CallToolResult with priorities, connection status, and widget metadata
    """
    logger.info(
        "tool.get_priorities.start",
        correlation_id=correlation_id,
        user_id=user_id
    )

    # Fetch priorities from backend
    response = await backend_get(
        "/api/priority-guardian/priorities",
        user_id,
        correlation_id
    )

    # Extract data from response
    data = response.get("data", {})
    raw_priorities = data.get("priorities", [])
    google_connection = data.get("google_connection", {"connected": False})

    # Normalize priority fields to camelCase (spec requirement)
    priorities = [_normalize_priority(p) for p in raw_priorities]

    logger.info(
        "tool.get_priorities.success",
        correlation_id=correlation_id,
        user_id=user_id,
        priority_count=len(priorities),
        google_connected=google_connection.get("connected", False),
    )

    # Build human-readable text summary
    if not priorities:
        text = "You don't have any priorities set up yet."
    else:
        active = [p for p in priorities if p.get("status") == "active"]
        text = f"You have {len(active)} active priorit{'y' if len(active) == 1 else 'ies'}."

    if not google_connection.get("connected"):
        text += " Google Calendar is not connected."

    # Build structuredContent matching spec format
    structured_content = {
        "success": True,
        "data": {
            "google_connected": google_connection.get("connected", False),
            "google_connected_at": google_connection.get("connected_at"),
            "priorities": priorities,
        },
        "_meta": {
            "openai/outputTemplate": WIDGET_URI,
        },
        "assistant_guidance": (
            "The dashboard is now showing the user's current priorities. "
            "Do not repeat or list the priorities in text — the widget displays them. "
            "If the user has no priorities, guide them through onboarding setup conversationally."
        ),
    }

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=text
        )],
        structuredContent=structured_content,
    )


# ============================================================================
# Tool Definition
# ============================================================================

GET_PRIORITIES = ToolDefinition(
    name=NAME,
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=WIDGET_URI,  # Points to the widget this tool produces
    handle=handle,
    read_only_hint=True,    # Pure data fetch, no side effects
    destructive_hint=False,
    open_world_hint=False,  # Backend-only, no external calls
    widget_accessible=True, # Widget can call this tool
)
