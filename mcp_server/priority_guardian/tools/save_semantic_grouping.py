"""
save_semantic_grouping tool for Priority Guardian MCP.

Saves user-confirmed semantic categories for non-priority time to the
weekly snapshot. Returns pie chart data with priority + semantic slices.

This tool is called after the LLM proposes groupings during the weekly
report conversation and the user reviews/confirms them.
"""

import structlog
from mcp import types as mcp_types

from mcp_server.priority_guardian.http_client import backend_post
from .base import ToolDefinition, ToolUsageError

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "save_semantic_grouping"

DESCRIPTION = (
    "Save your confirmed time allocation categories to your weekly snapshot, "
    "enabling a visual breakdown of where your entire week went. Call this "
    "after reviewing and optionally correcting the proposed groupings from "
    "your weekly report."
)

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "week_start": {
            "type": "string",
            "description": (
                "Monday of the week being saved (ISO date: YYYY-MM-DD). "
                "Must match an existing weekly report snapshot."
            ),
            "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
        },
        "groupings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Category name (e.g., 'Client calls', 'Admin')",
                    },
                    "hours": {
                        "type": "number",
                        "description": "Hours spent in this category",
                    },
                    "event_count": {
                        "type": "integer",
                        "description": "Number of events in this category",
                    },
                },
                "required": ["category", "hours", "event_count"],
            },
            "description": (
                "Finalized non-priority time categories confirmed by the user."
            ),
        },
    },
    "required": ["week_start", "groupings"],
}

REQUIRED_SCOPES = ["pg.access"]

WIDGET_URI = "ui://widget/pg-dashboard.html"

# Timeout for backend call (seconds)
BACKEND_TIMEOUT = 15.0


# ============================================================================
# Helpers
# ============================================================================

def _normalize_slice(s: dict) -> dict:
    """
    Normalize slice fields from backend snake_case to widget camelCase.

    Args:
        s: Slice dict from backend

    Returns:
        Normalized slice dict
    """
    result = {
        "label": s.get("label"),
        "hours": s.get("hours"),
        "type": s.get("type"),
    }

    # Priority-specific field
    if s.get("keyword"):
        result["keyword"] = s.get("keyword")

    # Semantic-specific field
    if s.get("eventCount") is not None:
        result["eventCount"] = s.get("eventCount")

    return result


# ============================================================================
# Handler
# ============================================================================

async def handle(user_id: str, correlation_id: str, arguments: dict) -> mcp_types.CallToolResult:
    """
    Save semantic grouping for a weekly report.

    Args:
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID
        arguments: Tool arguments (week_start, groupings)

    Returns:
        CallToolResult with pie chart data
    """
    week_start = arguments.get("week_start")
    groupings = arguments.get("groupings", [])

    logger.info(
        "tool.save_semantic_grouping.start",
        correlation_id=correlation_id,
        user_id=user_id,
        week_start=week_start,
        category_count=len(groupings),
    )

    # Validate required fields
    if not week_start:
        raise ToolUsageError("week_start is required")

    if not groupings:
        raise ToolUsageError("At least one category is required in groupings")

    # Call backend
    payload = {
        "week_start": week_start,
        "groupings": groupings,
    }

    try:
        result = await backend_post(
            "/api/priority-guardian/weekly-report/semantic-grouping",
            payload,
            user_id,
            correlation_id,
        )
    except Exception as e:
        logger.error(
            "tool.save_semantic_grouping.backend_error",
            correlation_id=correlation_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise

    # Check for error response
    if not result.get("success"):
        error = result.get("error", {})
        error_code = error.get("code", "UNKNOWN_ERROR")
        error_message = error.get("message", "Failed to save semantic grouping")

        logger.warning(
            "tool.save_semantic_grouping.error_response",
            correlation_id=correlation_id,
            error_code=error_code,
        )

        raise ToolUsageError(error_message)

    # Extract and normalize data
    data = result.get("data", {})
    slices = [_normalize_slice(s) for s in data.get("slices", [])]

    logger.info(
        "tool.save_semantic_grouping.success",
        correlation_id=correlation_id,
        user_id=user_id,
        week_start=data.get("week_start"),
        slice_count=len(slices),
        total_hours=data.get("total_hours"),
    )

    # Build human-readable summary
    priority_count = sum(1 for s in slices if s.get("type") == "priority")
    semantic_count = sum(1 for s in slices if s.get("type") == "semantic")
    total_hours = data.get("total_hours", 0)

    text = (
        f"Saved {semantic_count} category grouping{'' if semantic_count == 1 else 's'} "
        f"for week of {data.get('week_start')}. "
        f"Total: {total_hours}h across {priority_count} priorities and {semantic_count} categories."
    )

    # Build structured content for pie chart widget
    structured_content = {
        "success": True,
        "data": {
            "weekStart": data.get("week_start"),
            "weekEnd": data.get("week_end"),
            "slices": slices,
            "totalHours": total_hours,
        },
        "_meta": {
            "openai/outputTemplate": WIDGET_URI,
        },
        "assistant_guidance": (
            "Your time allocation categories have been saved for this week. "
            "The pie chart now shows how your week was distributed across priorities "
            "and other activities. Do not repeat or list the categories — the chart displays them. "
            "Ask what stands out to them or if they'd like to discuss any patterns."
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

SAVE_SEMANTIC_GROUPING = ToolDefinition(
    name=NAME,
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=WIDGET_URI,
    handle=handle,
    read_only_hint=False,  # Writes to pg_weekly_overview
    destructive_hint=False,  # Enriches, doesn't delete
    open_world_hint=True,  # Calls Google Calendar API for validation
    widget_accessible=True,  # Pie chart is a widget view
)
