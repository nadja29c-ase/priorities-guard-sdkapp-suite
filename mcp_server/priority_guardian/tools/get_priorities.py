"""
get_priorities tool for Priority Guardian MCP.

Returns user's priorities with Google Calendar connection status and
time allocation data from calendar events.

This is the primary data-fetching tool for the PG widget.
"""

import asyncio
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

# Timeout for each backend call (seconds)
# Must be less than MCP's 10-second tool timeout
BACKEND_TIMEOUT = 8.0


# ============================================================================
# Helpers
# ============================================================================

def _normalize_priority(p: dict, calendar_hours: dict | None = None) -> dict:
    """
    Normalize priority fields from backend snake_case to spec camelCase.

    Backend returns: calendar_keyword, created_at, weekly_hour_target, etc.
    Spec expects: calendarKeyword, createdAt, weeklyHourTarget, etc.

    Args:
        p: Priority dict from backend
        calendar_hours: Optional dict mapping keyword (P1/P2/P3) to hours

    Returns:
        Normalized priority dict with weeklyHourActual populated if available
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

    # Compute weeklyHourActual from calendar data if available
    weekly_hour_actual = None
    if calendar_hours:
        keyword = p.get("calendar_keyword")
        if keyword and keyword in calendar_hours:
            weekly_hour_actual = calendar_hours[keyword]

    return {
        "id": p.get("id"),
        "name": p.get("name"),
        "type": p.get("type"),
        "calendarKeyword": p.get("calendar_keyword"),
        "status": p.get("status"),
        "deadline": p.get("deadline"),
        "weeklyHourTarget": p.get("weekly_hour_target"),
        "weeklyHourActual": weekly_hour_actual,
        "checkpointDate": p.get("checkpoint_date"),
        "desiredResult": p.get("desired_result"),
        "deliverables": normalized_deliverables,
        "createdAt": p.get("created_at"),
        "updatedAt": p.get("updated_at"),
    }


async def _fetch_with_timeout(coro, timeout: float, name: str, correlation_id: str):
    """
    Wrap a coroutine with a timeout.

    Args:
        coro: Coroutine to execute
        timeout: Timeout in seconds
        name: Name for logging
        correlation_id: Correlation ID for logging

    Returns:
        Result of coroutine, or Exception if failed/timed out
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(
            f"mcp.{name}.timeout",
            correlation_id=correlation_id,
            timeout=timeout,
        )
        return TimeoutError(f"{name} timed out after {timeout}s")
    except Exception as e:
        logger.warning(
            f"mcp.{name}.error",
            correlation_id=correlation_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        return e


# ============================================================================
# Handler
# ============================================================================

async def handle(user_id: str, correlation_id: str, arguments: dict) -> mcp_types.CallToolResult:
    """
    Get user's priorities with connection status and time allocation.

    Makes parallel calls to:
    - GET /api/priority-guardian/priorities
    - GET /api/priority-guardian/calendar/time-allocation

    Merges calendar data into priorities (weeklyHourActual) and adds
    timeAllocation block to response.

    If calendar endpoint fails, returns priorities without calendar data
    (graceful degradation).

    Args:
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID
        arguments: Tool arguments (none expected)

    Returns:
        CallToolResult with priorities, connection status, time allocation, and widget metadata
    """
    logger.info(
        "tool.get_priorities.start",
        correlation_id=correlation_id,
        user_id=user_id
    )

    # -------------------------------------------------------------------------
    # Parallel fetch: priorities + calendar
    # -------------------------------------------------------------------------
    priorities_coro = backend_get(
        "/api/priority-guardian/priorities",
        user_id,
        correlation_id
    )
    calendar_coro = backend_get(
        "/api/priority-guardian/calendar/time-allocation",
        user_id,
        correlation_id
    )

    # Use gather with return_exceptions=True so one failure doesn't crash both
    results = await asyncio.gather(
        _fetch_with_timeout(priorities_coro, BACKEND_TIMEOUT, "priorities", correlation_id),
        _fetch_with_timeout(calendar_coro, BACKEND_TIMEOUT, "calendar", correlation_id),
        return_exceptions=True,
    )

    priorities_result = results[0]
    calendar_result = results[1]

    # -------------------------------------------------------------------------
    # Handle priorities result (required)
    # -------------------------------------------------------------------------
    if isinstance(priorities_result, Exception):
        # Priorities failed - this is fatal
        logger.error(
            "tool.get_priorities.priorities_failed",
            correlation_id=correlation_id,
            error=str(priorities_result),
        )
        raise priorities_result

    # Extract priorities data
    data = priorities_result.get("data", {})
    raw_priorities = data.get("priorities", [])
    google_connection = data.get("google_connection", {"connected": False})
    available_keywords = data.get("available_keywords", [])

    # -------------------------------------------------------------------------
    # Handle calendar result (optional - graceful degradation)
    # -------------------------------------------------------------------------
    calendar_hours: dict | None = None
    time_allocation: dict | None = None

    if isinstance(calendar_result, Exception):
        # Calendar failed - continue without calendar data
        logger.warning(
            "tool.get_priorities.calendar_failed",
            correlation_id=correlation_id,
            error=str(calendar_result),
            error_type=type(calendar_result).__name__,
        )
    elif calendar_result and calendar_result.get("success"):
        # Calendar succeeded - extract data
        cal_data = calendar_result.get("data", {})
        keywords_data = cal_data.get("keywords", {})

        # Check for valid week dates (None means no Google connection)
        week_start = cal_data.get("week_start")
        week_end = cal_data.get("week_end")

        if week_start is not None and week_end is not None:
            # Valid calendar data - build calendar_hours mapping for priority enrichment
            calendar_hours = {
                "P1": keywords_data.get("P1", {}).get("hours"),
                "P2": keywords_data.get("P2", {}).get("hours"),
                "P3": keywords_data.get("P3", {}).get("hours"),
            }

            # Build timeAllocation block for widget
            time_allocation = {
                "weekStart": week_start,
                "weekEnd": week_end,
                "totalTrackedHours": cal_data.get("total_tracked_hours"),
                "keywords": {
                    "P1": {
                        "hours": keywords_data.get("P1", {}).get("hours", 0.0),
                        "eventCount": keywords_data.get("P1", {}).get("event_count", 0),
                    },
                    "P2": {
                        "hours": keywords_data.get("P2", {}).get("hours", 0.0),
                        "eventCount": keywords_data.get("P2", {}).get("event_count", 0),
                    },
                    "P3": {
                        "hours": keywords_data.get("P3", {}).get("hours", 0.0),
                        "eventCount": keywords_data.get("P3", {}).get("event_count", 0),
                    },
                },
                "otherHours": cal_data.get("other_hours", 0.0),
                "barSegments": cal_data.get("bar_segments", {}),
            }

            logger.info(
                "tool.get_priorities.calendar_merged",
                correlation_id=correlation_id,
                total_hours=cal_data.get("total_tracked_hours", 0),
            )
        else:
            # week_start/week_end are None - no Google connection, skip timeAllocation
            logger.info(
                "tool.get_priorities.calendar_no_connection",
                correlation_id=correlation_id,
            )
    else:
        logger.warning(
            "tool.get_priorities.calendar_unsuccessful",
            correlation_id=correlation_id,
            response=calendar_result,
        )

    # -------------------------------------------------------------------------
    # Normalize priorities with calendar data
    # -------------------------------------------------------------------------
    priorities = [_normalize_priority(p, calendar_hours) for p in raw_priorities]

    logger.info(
        "tool.get_priorities.success",
        correlation_id=correlation_id,
        user_id=user_id,
        priority_count=len(priorities),
        google_connected=google_connection.get("connected", False),
        calendar_available=time_allocation is not None,
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
            "available_keywords": available_keywords,
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

    # Add timeAllocation if available
    if time_allocation:
        structured_content["data"]["timeAllocation"] = time_allocation

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
    open_world_hint=True,   # Calls Google Calendar API via backend
    widget_accessible=True, # Widget can call this tool
)
