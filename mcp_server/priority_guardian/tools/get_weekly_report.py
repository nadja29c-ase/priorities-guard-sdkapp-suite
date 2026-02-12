"""
get_weekly_report tool for Priority Guardian MCP.

Returns weekly report data with per-priority hours, status indicators,
week-over-week comparison, and aggregate stats.

For completed weeks, persists snapshots and updates priority aggregates.
For current week, returns live data without persistence.
"""

import structlog
from mcp import types as mcp_types

from mcp_server.priority_guardian.http_client import backend_get
from .base import ToolDefinition, ToolUsageError

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "get_weekly_report"

DESCRIPTION = (
    "Get your weekly report showing time invested in each priority. "
    "Returns hours worked, status indicators (ahead/on_track/behind), "
    "and comparison to last week. For past weeks, saves a snapshot."
)

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "week_start": {
            "type": "string",
            "description": (
                "Monday of the target week (ISO date: YYYY-MM-DD). "
                "Must be a Monday. If omitted, returns current week."
            ),
            "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
        },
    },
    "required": [],
}

REQUIRED_SCOPES = ["pg.access"]

# Timeout for backend call (seconds)
BACKEND_TIMEOUT = 15.0  # Longer timeout for backfill scenarios


# ============================================================================
# Helpers
# ============================================================================

def _normalize_priority_report(p: dict) -> dict:
    """
    Normalize priority report fields from backend snake_case to spec camelCase.

    Args:
        p: Priority report dict from backend

    Returns:
        Normalized priority dict
    """
    result = {
        "id": p.get("id"),
        "name": p.get("name"),
        "type": p.get("type"),
        "calendarKeyword": p.get("calendar_keyword"),
        "actualHours": p.get("actual_hours"),
        "eventCount": p.get("event_count"),
    }

    # Deadline-specific fields
    if p.get("type") == "deadline":
        result["deadlineDate"] = p.get("deadline_date")
        result["daysRemaining"] = p.get("days_remaining")
        result["deliverablesCompleted"] = p.get("deliverables_completed")
        result["deliverablesTotal"] = p.get("deliverables_total")
        result["pacingStatus"] = p.get("pacing_status")

    # Flexible-specific fields
    elif p.get("type") == "flexible":
        result["targetHours"] = p.get("target_hours")
        result["flexStatus"] = p.get("flex_status")
        result["streakCount"] = p.get("streak_count")
        result["avgHoursWeek"] = p.get("avg_hours_week")
        result["totalHoursInvested"] = p.get("total_hours_invested")

    # Previous week comparison
    prev = p.get("previous_week")
    if prev:
        result["previousWeek"] = {
            "actualHours": prev.get("actual_hours"),
            "eventCount": prev.get("event_count"),
            "deltaHours": prev.get("delta_hours"),
        }
    else:
        result["previousWeek"] = None

    return result


def _normalize_time_allocation(ta: dict) -> dict:
    """Normalize time allocation fields."""
    keywords = ta.get("keywords", {})
    return {
        "totalTrackedHours": ta.get("total_tracked_hours"),
        "keywords": {
            "P1": {
                "hours": keywords.get("P1", {}).get("hours", 0.0),
                "eventCount": keywords.get("P1", {}).get("event_count", 0),
            },
            "P2": {
                "hours": keywords.get("P2", {}).get("hours", 0.0),
                "eventCount": keywords.get("P2", {}).get("event_count", 0),
            },
            "P3": {
                "hours": keywords.get("P3", {}).get("hours", 0.0),
                "eventCount": keywords.get("P3", {}).get("event_count", 0),
            },
        },
        "otherHours": ta.get("other_hours", 0.0),
    }


def _normalize_event(e: dict) -> dict:
    """Normalize event fields for LLM semantic grouping."""
    return {
        "title": e.get("title", ""),
        "description": e.get("description", ""),
        "start": e.get("start"),
        "end": e.get("end"),
        "matchedKeywords": e.get("matched_keywords", []),
    }


def _build_assistant_guidance(
    data: dict,
    priorities: list[dict],
    all_events: list[dict],
) -> str:
    """
    Build conditional assistant guidance based on report state.

    The guidance shapes how the LLM presents the report and proposes
    semantic groupings for non-priority time.
    """
    is_current = data.get("is_current_week", False)
    snapshot_saved = data.get("snapshot_saved", False)
    weeks_backfilled = data.get("weeks_backfilled", 0)
    other_hours = data.get("time_allocation", {}).get("other_hours", 0)

    # Check if this is the user's first report (no previous week data)
    is_first_report = all(p.get("previous_week") is None for p in priorities)

    # Get non-priority events for semantic grouping
    non_priority_events = [e for e in all_events if not e.get("matched_keywords")]

    guidance_parts = []

    # Opening context
    if is_current:
        guidance_parts.append(
            "This is a MID-WEEK PREVIEW. The week is not complete, so these numbers will change. "
            "Frame this as a progress check, not a final report. No snapshot is saved for incomplete weeks."
        )
    elif is_first_report:
        guidance_parts.append(
            "This is the user's FIRST WEEKLY REPORT. Welcome them to the reflection process. "
            "Explain that weekly reports help track time investment patterns over time."
        )

    # Backfill mention
    if weeks_backfilled > 0:
        guidance_parts.append(
            f"NOTE: {weeks_backfilled} previous week(s) were backfilled with snapshots. "
            "Mention this briefly so the user knows their historical data is now tracked."
        )

    # Snapshot confirmation
    if snapshot_saved:
        guidance_parts.append(
            "A snapshot was saved for this completed week. The user's streaks and averages are updated."
        )

    # Priority insights
    guidance_parts.append(
        "Present each priority's hours naturally. For flexible priorities, note if they're "
        "ahead/on_track/behind their target. For deadline priorities, mention pacing status "
        "and days remaining. Use previousWeek.deltaHours for week-over-week comparison when available."
    )

    # Semantic grouping proposal (the bridge to Inc 07)
    if other_hours > 0 and non_priority_events:
        event_titles = [e.get("title", "Untitled") for e in non_priority_events[:15]]
        guidance_parts.append(
            f"IMPORTANT: The user has {other_hours} hours of non-priority time across "
            f"{len(non_priority_events)} events. Propose semantic categories based on these event titles: "
            f"{event_titles}. Group similar activities (e.g., 'Client calls', 'Admin tasks', "
            "'Learning/development'). Ask the user if these groupings look right, and if they'd "
            "like to adjust or save them. This opens the door to the save_semantic_grouping flow."
        )
    elif other_hours > 0:
        guidance_parts.append(
            f"The user has {other_hours} hours of non-priority time but event details aren't available. "
            "Ask them what this time was spent on if they'd like to categorize it."
        )

    # Closing
    guidance_parts.append(
        "Keep the tone reflective and coaching-oriented. The goal is insight, not judgment. "
        "Ask what stood out to them or what they'd like to adjust next week."
    )

    return " ".join(guidance_parts)


# ============================================================================
# Handler
# ============================================================================

async def handle(user_id: str, correlation_id: str, arguments: dict) -> mcp_types.CallToolResult:
    """
    Get weekly report for the user.

    Args:
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID
        arguments: Tool arguments (optional week_start)

    Returns:
        CallToolResult with weekly report data
    """
    week_start = arguments.get("week_start")

    logger.info(
        "tool.get_weekly_report.start",
        correlation_id=correlation_id,
        user_id=user_id,
        week_start=week_start,
    )

    # Build endpoint URL with optional query param
    endpoint = "/api/priority-guardian/weekly-report"
    if week_start:
        endpoint = f"{endpoint}?week_start={week_start}"

    # Call backend
    try:
        result = await backend_get(endpoint, user_id, correlation_id)
    except Exception as e:
        logger.error(
            "tool.get_weekly_report.backend_error",
            correlation_id=correlation_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise

    # Check for error response
    if not result.get("success"):
        error = result.get("error", {})
        error_code = error.get("code", "UNKNOWN_ERROR")
        error_message = error.get("message", "Failed to generate weekly report")

        logger.warning(
            "tool.get_weekly_report.error_response",
            correlation_id=correlation_id,
            error_code=error_code,
        )

        raise ToolUsageError(error_message)

    # Extract and normalize data
    data = result.get("data", {})
    priorities = data.get("priorities", [])
    time_allocation = data.get("time_allocation", {})
    all_events = data.get("all_events", [])

    normalized_priorities = [_normalize_priority_report(p) for p in priorities]
    normalized_time_allocation = _normalize_time_allocation(time_allocation)
    normalized_events = [_normalize_event(e) for e in all_events]

    logger.info(
        "tool.get_weekly_report.success",
        correlation_id=correlation_id,
        user_id=user_id,
        week_start=data.get("week_start"),
        is_current_week=data.get("is_current_week"),
        snapshot_saved=data.get("snapshot_saved"),
        weeks_backfilled=data.get("weeks_backfilled"),
        priority_count=len(priorities),
    )

    # Build human-readable summary
    week_label = "This week" if data.get("is_current_week") else f"Week of {data.get('week_start')}"
    total_hours = normalized_time_allocation.get("totalTrackedHours", 0)

    if not priorities:
        text = f"{week_label}: No active priorities."
    else:
        text = f"{week_label}: {total_hours} hours tracked across {len(priorities)} priorities."

    if data.get("snapshot_saved"):
        text += " Snapshot saved."
    if data.get("weeks_backfilled", 0) > 0:
        text += f" {data.get('weeks_backfilled')} weeks backfilled."

    # Build assistant guidance based on report state
    assistant_guidance = _build_assistant_guidance(data, priorities, all_events)

    # Build structured content
    structured_content = {
        "success": True,
        "data": {
            "weekStart": data.get("week_start"),
            "weekEnd": data.get("week_end"),
            "isCurrentWeek": data.get("is_current_week"),
            "snapshotSaved": data.get("snapshot_saved"),
            "weeksBackfilled": data.get("weeks_backfilled"),
            "backfillTruncated": data.get("backfill_truncated"),
            "priorities": normalized_priorities,
            "timeAllocation": normalized_time_allocation,
            "allEvents": normalized_events,
        },
        "assistant_guidance": assistant_guidance,
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

GET_WEEKLY_REPORT = ToolDefinition(
    name=NAME,
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=None,  # Conversational tool, no widget template
    handle=handle,
    read_only_hint=False,  # May persist snapshots for past weeks
    destructive_hint=False,
    open_world_hint=True,  # Calls Google Calendar API via backend
    widget_accessible=False,  # LLM-only conversational tool, not widget-callable
)
