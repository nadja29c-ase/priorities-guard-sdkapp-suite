"""
get_priority_events tool for Priority Guardian MCP.

Data-only tool (no widget) for fetching calendar events for a specific priority.
Used as the first step in a two-call flow for priority breakdown:
1. get_priority_events → returns priorityEvents for the model to read
2. render_weekly_report with semantic_groupings → renders the exploded chart

This tool NEVER includes _meta in its response — no widget card ever.
"""

import asyncio

import structlog
from mcp import types as mcp_types

from mcp_server.priority_guardian.http_client import backend_get
from .base import ToolDefinition, ToolUsageError
from .normalize import normalize_priority_report, normalize_time_allocation, normalize_event

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "get_priority_events"

DESCRIPTION = (
    "Fetch calendar events for a specific priority to enable a breakdown chart.\n\n"
    "Call this tool ONLY when the user asks to break down or analyse their time within "
    "a single priority (e.g. \"break down my P1 time\", \"what's in my P2 this week?\").\n\n"
    "After calling this tool, read the priorityEvents and IMMEDIATELY call "
    "render_weekly_report with semantic_groupings and semantic_target to render the chart. "
    "Do NOT propose groupings to the user first. Do NOT ask for confirmation. Just call "
    "render_weekly_report.\n\n"
    "Do NOT call this tool for the initial weekly report — use render_weekly_report directly.\n"
    "Do NOT call this tool for past weeks (no event data available)."
)

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "semantic_target": {
            "type": "string",
            "enum": ["P1", "P2", "P3"],
            "description": (
                "Priority keyword to fetch events for. Returns that priority's "
                "calendar events so you can group them into subcategories. After reading the events, "
                "IMMEDIATELY call render_weekly_report with semantic_groupings and "
                "semantic_target to render the breakdown chart. No user confirmation needed."
            ),
        },
        "week_start": {
            "type": "string",
            "description": (
                "Monday of the target week (ISO date: YYYY-MM-DD). "
                "Must be a Monday. If omitted, returns current week."
            ),
            "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
        },
    },
    "required": ["semantic_target"],
    "additionalProperties": False,
}

REQUIRED_SCOPES = ["pg.access"]

# Timeout for backend calls (seconds) — must be under ChatGPT's ~10s window
TIMEOUT_S = 8.0


# ============================================================================
# Helpers
# ============================================================================

async def _call_with_timeout(coro, op_name: str, correlation_id: str):
    """
    Wrap a coroutine with timeout.

    Args:
        coro: Coroutine to execute
        op_name: Operation name for error message
        correlation_id: Correlation ID for logging

    Returns:
        Result of the coroutine

    Raises:
        ToolUsageError: On timeout
    """
    try:
        return await asyncio.wait_for(coro, timeout=TIMEOUT_S)
    except asyncio.TimeoutError:
        logger.warning(
            "tool.get_priority_events.timeout",
            correlation_id=correlation_id,
            op_name=op_name,
            timeout=TIMEOUT_S,
        )
        raise ToolUsageError(f"{op_name} timed out. Please try again.")


# ============================================================================
# assistant_guidance Template
# ============================================================================

# Template with {keyword} placeholder for priority breakdown
GUIDANCE_PRIORITY_BREAKDOWN_TEMPLATE = (
    "The user asked to break down their {keyword} time. "
    "Based on the event titles and descriptions in priorityEvents, group the events into "
    "semantic subcategories and assign approximate hours to each (category, hours, event_count). "
    "IMMEDIATELY call render_weekly_report again with semantic_groupings containing your "
    "categories and semantic_target='{keyword}'. "
    "Do NOT propose first. Do NOT ask for confirmation. Do NOT narrate the groupings. "
    "Just call the tool — the chart will show the breakdown."
)


# ============================================================================
# Handler
# ============================================================================

async def handle(user_id: str, correlation_id: str, arguments: dict) -> mcp_types.CallToolResult:
    """
    Fetch priority events for breakdown — data-only, no widget.

    Args:
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID
        arguments: Tool arguments (semantic_target required, optional week_start)

    Returns:
        CallToolResult with priority events data (no _meta, no widget)
    """
    semantic_target = arguments.get("semantic_target")
    week_start = arguments.get("week_start")

    # Validate semantic_target is provided (required parameter)
    if not semantic_target or semantic_target not in ("P1", "P2", "P3"):
        raise ToolUsageError("semantic_target must be one of: P1, P2, P3")

    logger.info(
        "tool.get_priority_events.start",
        correlation_id=correlation_id,
        user_id=user_id,
        semantic_target=semantic_target,
        week_start=week_start,
    )

    # Build endpoint URL with optional query param
    endpoint = "/api/priority-guardian/weekly-report"
    if week_start:
        endpoint = f"{endpoint}?week_start={week_start}"

    # Call backend with timeout
    result = await _call_with_timeout(
        backend_get(endpoint, user_id, correlation_id),
        "Priority events fetch",
        correlation_id,
    )

    # Check for error response
    if not result.get("success"):
        error = result.get("error", {})
        error_code = error.get("code", "UNKNOWN_ERROR")
        error_message = error.get("message", "Failed to fetch priority events")

        logger.warning(
            "tool.get_priority_events.error_response",
            correlation_id=correlation_id,
            error_code=error_code,
            backend_message=error_message,
        )

        raise ToolUsageError("Unable to fetch priority events. Please try again.")

    # Extract data
    data = result.get("data", {})
    priorities = data.get("priorities", [])
    time_allocation = data.get("time_allocation", {})
    all_events = data.get("all_events", [])

    # Guard: reject call when no event data available (past weeks)
    if not all_events:
        logger.info(
            "tool.get_priority_events.breakdown_unavailable",
            correlation_id=correlation_id,
            user_id=user_id,
            week_start=data.get("week_start"),
            semantic_target=semantic_target,
        )
        # CRITICAL: No _meta in error response either
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=f"Priority breakdown for {semantic_target} not available for this week.",
            )],
            structuredContent={
                "success": False,
                "error": "priority_breakdown_unavailable",
                "assistant_guidance": (
                    f"Priority breakdown for {semantic_target} is not available for past weeks — "
                    "detailed event data is only available for the current week. "
                    "Do NOT propose or offer any breakdown. "
                    "Suggest looking at the current week instead where event-level data is available. "
                    "Do NOT suggest any other workarounds, sub-tags, naming patterns, or tracking changes."
                ),
            },
            isError=True,
        )

    # Guard: no priorities at all
    if not priorities:
        logger.info(
            "tool.get_priority_events.no_priorities",
            correlation_id=correlation_id,
            user_id=user_id,
        )
        # CRITICAL: No _meta in this response
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="No priorities configured.",
            )],
            structuredContent={
                "success": False,
                "error": "no_priorities",
                "assistant_guidance": (
                    "No priorities were configured during this week. "
                    "Cannot break down priority time when no priorities exist."
                ),
            },
            isError=True,
        )

    # Normalize data
    normalized_priorities = [normalize_priority_report(p) for p in priorities]
    normalized_time_allocation = normalize_time_allocation(time_allocation)
    normalized_events = [normalize_event(e) for e in all_events]

    # Filter to only events matching the target priority
    priority_events = [
        e for e in normalized_events
        if semantic_target in e.get("matchedKeywords", [])
    ]

    # Build assistant guidance
    assistant_guidance = GUIDANCE_PRIORITY_BREAKDOWN_TEMPLATE.format(keyword=semantic_target)

    logger.info(
        "tool.get_priority_events.success",
        correlation_id=correlation_id,
        user_id=user_id,
        semantic_target=semantic_target,
        priority_event_count=len(priority_events),
    )

    # CRITICAL: No _meta in response — this is a data tool, no widget card
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Fetched {len(priority_events)} events for {semantic_target}.",
        )],
        structuredContent={
            "success": True,
            "data": {
                # Pie chart fields — empty, no widget rendered
                "weekStart": data.get("week_start"),
                "weekEnd": data.get("week_end"),
                "slices": [],
                "totalHours": float(normalized_time_allocation.get("totalTrackedHours", 0)),
                # Aggregates — model needs these to not lose context
                "isCurrentWeek": data.get("is_current_week"),
                "priorities": normalized_priorities,
                "timeAllocation": normalized_time_allocation,
                # Events for the model to categorise
                "priorityEvents": priority_events,
                "otherEvents": [],
            },
            # CRITICAL: No _meta — no widget render
            "assistant_guidance": assistant_guidance,
        },
    )


# ============================================================================
# Tool Definition
# ============================================================================

GET_PRIORITY_EVENTS = ToolDefinition(
    name=NAME,
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=None,  # CRITICAL: No widget — data tool only
    handle=handle,
    read_only_hint=True,
    destructive_hint=False,
    open_world_hint=True,  # Calls Google Calendar API via backend
    widget_accessible=False,  # Widget cannot call this tool
)
