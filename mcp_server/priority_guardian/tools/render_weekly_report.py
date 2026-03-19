"""
render_weekly_report tool for Priority Guardian MCP.

Render tool (HAS widget) for displaying weekly report with pie chart.
Produces a widget when priorities exist and data is valid.

Two call types:
- Call 1: Basic weekly report (no semantic_groupings)
- Call 2: Confirmed groupings for other or priority → exploded chart

For priority breakdown, use get_priority_events first to fetch events,
then call this tool with semantic_groupings to render the exploded chart.
"""

import asyncio

import structlog
from mcp import types as mcp_types

from mcp_server.priority_guardian.http_client import backend_get
from .base import ToolDefinition, ToolUsageError
from .widget_tools.constants import WIDGET_URI
from .normalize import normalize_priority_report, normalize_time_allocation, normalize_event

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "render_weekly_report"

DESCRIPTION = (
    "Get your weekly report showing time invested in each priority, rendered as a pie chart.\n\n"
    "Call this tool:\n"
    "- When the user asks about their week, progress, or hours\n"
    "- When the user says \"how did I do?\", \"show my report\", \"weekly summary\"\n"
    "- At the start of a reflection or check-in conversation\n"
    "- After calling get_priority_events: immediately call this tool with semantic_groupings "
    "and semantic_target to render the P1/P2/P3 breakdown chart\n\n"
    "Do NOT call this tool:\n"
    "- During onboarding or priority setup\n"
    "- When the user is asking about patterns or trends over time (use get_patterns instead)\n"
    "- To fetch events for a breakdown — use get_priority_events first, then call this tool"
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
        "semantic_groupings": {
            "type": "array",
            "description": (
                "Semantic categories for the target slice. "
                "When provided together with semantic_target, replaces that category's slice "
                "in the pie chart with these subcategory slices. "
                "For 'other' breakdown: pass after user confirms your proposed groupings. "
                "For priority breakdown (P1/P2/P3): pass immediately after calling "
                "get_priority_events — no user confirmation needed."
            ),
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
                "additionalProperties": False,
            },
        },
        "semantic_target": {
            "type": "string",
            "enum": ["P1", "P2", "P3", "other"],
            "description": (
                "With semantic_groupings: replaces that category's slice in the chart with "
                "subcategory slices. For 'other', pass after user confirms your proposed groupings. "
                "For P1/P2/P3, pass immediately after calling get_priority_events — no user "
                "confirmation needed."
            ),
        },
    },
    "required": [],
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
            "tool.render_weekly_report.timeout",
            correlation_id=correlation_id,
            op_name=op_name,
            timeout=TIMEOUT_S,
        )
        raise ToolUsageError(f"{op_name} timed out. Please try again.")


# ============================================================================
# assistant_guidance Templates
# ============================================================================

GUIDANCE_NO_PRIORITIES = (
    "No priorities were being tracked during this week. "
    "Do not mention P1, P2, or P3 keywords or time allocation. "
    "Simply tell the user that priority tracking had not started yet for this time period. "
    "If they created priorities after this week, you can mention that tracking begins "
    "from the first full week after creation. "
    "Keep it to one or two sentences. "
)

GUIDANCE_CURRENT_WEEK = (
    "This is your CURRENT WEEK in progress. Numbers will change as you work through the week. "
    "Frame this as a progress check-in, not a final tally."
)

GUIDANCE_COMPLETED_WEEK = (
    "This is a COMPLETED WEEK reflection. Present it as a look back/ a snapshot at how the week was spent. "
    "Detailed event data is NOT available for past weeks. If the user asks for any time breakdown "
    "(within-priority or non-priority), say briefly it's not available for past weeks "
    "and suggest looking at the current week instead where event-level data is available. "
    "Do NOT suggest any other workarounds, sub-tags, naming patterns, or tracking changes."
)

GUIDANCE_PRIORITY_INSIGHTS = (
    "Do not repeat the priority names or hours — the report displays them."
)

# Template with {other_hours} placeholder
GUIDANCE_SEMANTIC_PROPOSAL_TEMPLATE = (
    "The user has {other_hours:.1f} hours of non-priority time. "
    "Based on the event titles and descriptions in otherEvents, propose approximate "
    "semantic categories. Frame it as a NEUTRAL observation: 'Your non-priority time looks like "
    "it breaks down to roughly: Client calls ~Xh, Admin ~Yh, etc.' "
    "Ask if this grouping looks right or if they'd adjust it. "
    "CRITICAL: NEVER interpret/ judge non-priority time f.e. as wasted, unfocused, or dilutive. NEVER assume non-priority time should be strategic or priority-related. "
    "If they confirm OR express any intent to see the breakdown — including 'yes', 'sure', "
    "'show me', 'break it down', 'what's in Other', 'go ahead', or any similar phrasing — "
    "IMMEDIATELY call render_weekly_report again with the semantic_groupings parameter "
    "containing your proposed categories (category name, hours, event_count for each) "
    "and semantic_target='other'. "
    "Do NOT ask again. Do NOT re-propose. Just call the tool."
)

# Template with {other_hours} placeholder
GUIDANCE_SEMANTIC_NO_EVENTS_TEMPLATE = (
    "The user has {other_hours:.1f} hours of non-priority time. "
    "No event data available for past weeks — no breakdown possible. "
    "Breakdowns are only available during the current week while event data exists. "
    "Do NOT suggest sub-tags, naming patterns, or any other workarounds. "
    "Do NOT interpret or judge non-priority time."
)

GUIDANCE_WITHIN_PRIORITY_BREAKDOWN = (
    "You can also break down any single priority's time into subcategories. "
    "To do so, call get_priority_events with semantic_target set to the priority keyword "
    "(e.g. 'P1'). The tool will return that priority's events — immediately group them "
    "and call render_weekly_report with semantic_groupings to render the breakdown. "
    "No confirmation needed."
)

GUIDANCE_CLOSING = (
    "Keep the tone neutral and reflective. The goal is insight, not judgment. "
    "After presenting the report, ask briefly if the user wants to dig into "
    "what's helping them make progress or what's getting in the way — "
    "keep it short. "
)

GUIDANCE_SEMANTIC_PROVIDED = (
    "The pie chart now shows the refined breakdown for the selected category. "
    "Do NOT repeat or list the categories — the chart displays them. "
    "Make a brief neutral observation about the allocation pattern without evaluation or recommendation. "
    "Ask what stands out to them. "
    "Keep it short — the visual does the heavy lifting."
)


def _build_pie_slices(
    priorities: list[dict],
    time_allocation: dict,
    semantic_groupings: list[dict] | None,
    semantic_target: str | None,
) -> list[dict]:
    """
    Build pie chart slices from priorities and time allocation.

    Supports semantic zoom into any single category:
    - semantic_target="other" (or None with groupings): explode Other slice
    - semantic_target="P1"/"P2"/"P3": explode that priority's slice

    Only one category can be exploded at a time.

    Args:
        priorities: List of priority report dicts from backend
        time_allocation: Time allocation dict from backend
        semantic_groupings: Optional user-confirmed semantic categories
        semantic_target: Which category to explode ("P1", "P2", "P3", or "other")

    Returns:
        List of pie chart slices

    Raises:
        ToolUsageError: For input validation failures
    """
    keywords = time_allocation.get("keywords", {})
    other_hours = time_allocation.get("other_hours", 0.0)

    # Default semantic_target to "other" when groupings provided but target not specified
    # (backwards compatibility)
    if semantic_groupings and len(semantic_groupings) > 0 and not semantic_target:
        semantic_target = "other"

    # Build map of active priority keywords
    active_keywords = {p.get("calendar_keyword") for p in priorities if p.get("calendar_keyword")}

    # Validation: if targeting a priority, it must be active
    if semantic_target in ("P1", "P2", "P3") and semantic_target not in active_keywords:
        raise ToolUsageError(f"No active priority found for {semantic_target}.")

    slices = []

    # Build priority slices - explode if this priority is the semantic target
    for p in priorities:
        keyword = p.get("calendar_keyword")
        if not keyword:
            continue

        keyword_data = keywords.get(keyword, {})
        hours = keyword_data.get("hours", 0.0)

        # Skip zero-hour priorities (unless being exploded with subcategories)
        if hours <= 0 and keyword != semantic_target:
            continue

        if keyword == semantic_target and semantic_groupings:
            # Explode this priority into semantic subcategories
            grouped_total = sum(float(g.get("hours", 0)) for g in semantic_groupings)

            for g in semantic_groupings:
                slices.append({
                    "label": g.get("category", "Unnamed"),
                    "hours": g.get("hours", 0),
                    "type": "semantic",
                    "eventCount": g.get("event_count", 0),
                })

            # Add "Uncategorized" remainder if significant (>= 0.25h)
            remainder = max(0, hours - grouped_total)
            if remainder >= 0.25:
                slices.append({
                    "label": "Uncategorized",
                    "hours": round(remainder, 1),
                    "type": "semantic",
                })
        else:
            # Keep as single priority slice
            if hours > 0:
                slices.append({
                    "label": f"{keyword}: {p.get('name', 'Unnamed')}",
                    "hours": hours,
                    "type": "priority",
                    "keyword": keyword,
                })

    # Build "Other" slice - explode if semantic_target is "other"
    if semantic_target == "other" and semantic_groupings:
        # Explode Other into semantic subcategories
        grouped_total = sum(float(g.get("hours", 0)) for g in semantic_groupings)

        for g in semantic_groupings:
            slices.append({
                "label": g.get("category", "Unnamed"),
                "hours": g.get("hours", 0),
                "type": "semantic",
                "eventCount": g.get("event_count", 0),
            })

        # Add "Uncategorized" remainder if significant (>= 0.25h)
        remainder = max(0, other_hours - grouped_total)
        if remainder >= 0.25:
            slices.append({
                "label": "Uncategorized",
                "hours": round(remainder, 1),
                "type": "semantic",
            })
    else:
        # Keep as single "Other" slice
        if other_hours > 0:
            slices.append({
                "label": "Other",
                "hours": other_hours,
                "type": "semantic",
            })

    return slices


def _build_assistant_guidance(
    data: dict,
    priorities: list[dict],
    other_events: list[dict],
    has_semantic_groupings: bool,
) -> str:
    """
    Build assistant guidance for presenting the weekly report.

    Two modes (simplified from three after two-tool split):
    1. No priorities: Tracking hadn't started for this week
    2. Call 1 (no groupings): Propose other groupings, offer priority breakdown
    3. Call 2 (semantic_groupings provided): Brief neutral observation

    Args:
        data: Backend response data
        priorities: List of priority dicts
        other_events: Non-priority events (for call 1)
        has_semantic_groupings: Whether semantic_groupings parameter was provided
    """
    # Defense in depth: if handle() early return is bypassed, still return safe guidance
    if not priorities:
        return GUIDANCE_NO_PRIORITIES

    is_current = data.get("is_current_week", False)
    other_hours = data.get("time_allocation", {}).get("other_hours", 0)

    guidance_parts = []

    if has_semantic_groupings:
        # Call 2: Semantic groupings provided — brief observation only
        guidance_parts.append(GUIDANCE_SEMANTIC_PROVIDED)
    else:
        # Call 1: Basic weekly report — propose other groupings
        if is_current:
            guidance_parts.append(GUIDANCE_CURRENT_WEEK)
        else:
            guidance_parts.append(GUIDANCE_COMPLETED_WEEK)

        # Priority insights
        guidance_parts.append(GUIDANCE_PRIORITY_INSIGHTS)

        # Semantic grouping proposal for "Other" time
        if other_hours > 0 and other_events:
            guidance_parts.append(
                GUIDANCE_SEMANTIC_PROPOSAL_TEMPLATE.format(other_hours=other_hours)
            )
        elif other_hours > 0:
            guidance_parts.append(
                GUIDANCE_SEMANTIC_NO_EVENTS_TEMPLATE.format(other_hours=other_hours)
            )

        # Within-priority breakdown proposal (only when current week AND priorities have hours)
        has_priority_hours = any(
            kw_data.get("hours", 0) > 0
            for kw_data in data.get("time_allocation", {}).get("keywords", {}).values()
        )
        if is_current and has_priority_hours:
            guidance_parts.append(GUIDANCE_WITHIN_PRIORITY_BREAKDOWN)

        # Closing
        guidance_parts.append(GUIDANCE_CLOSING)

    return " ".join(guidance_parts)


# ============================================================================
# Handler
# ============================================================================

async def handle(user_id: str, correlation_id: str, arguments: dict) -> mcp_types.CallToolResult:
    """
    Render weekly report with pie chart visualization.

    This is a render tool — produces a widget when priorities exist.

    Args:
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID
        arguments: Tool arguments (optional week_start, semantic_groupings, semantic_target)

    Returns:
        CallToolResult with weekly report data and pie chart slices (always includes _meta)
    """
    week_start = arguments.get("week_start")
    semantic_groupings = arguments.get("semantic_groupings")
    semantic_target = arguments.get("semantic_target")

    # Treat empty array same as not provided
    if semantic_groupings is not None and len(semantic_groupings) == 0:
        semantic_groupings = None

    # Call type detection (simplified to two states after two-tool split)
    has_semantic_groupings = semantic_groupings is not None and len(semantic_groupings) > 0
    is_call1 = not has_semantic_groupings

    logger.info(
        "tool.render_weekly_report.start",
        correlation_id=correlation_id,
        user_id=user_id,
        week_start=week_start,
        has_semantic_groupings=has_semantic_groupings,
        is_call1=is_call1,
        grouping_count=len(semantic_groupings) if semantic_groupings else 0,
        semantic_target=semantic_target,
    )

    # Build endpoint URL with optional query param
    endpoint = "/api/priority-guardian/weekly-report"
    if week_start:
        endpoint = f"{endpoint}?week_start={week_start}"

    # Call backend with timeout
    result = await _call_with_timeout(
        backend_get(endpoint, user_id, correlation_id),
        "Weekly report fetch",
        correlation_id,
    )

    # Check for error response
    if not result.get("success"):
        error = result.get("error", {})
        error_code = error.get("code", "UNKNOWN_ERROR")
        error_message = error.get("message", "Failed to generate weekly report")

        logger.warning(
            "tool.render_weekly_report.error_response",
            correlation_id=correlation_id,
            error_code=error_code,
            backend_message=error_message,
        )

        raise ToolUsageError("Unable to generate your weekly report. Please try again.")

    # Extract data
    data = result.get("data", {})
    priorities = data.get("priorities", [])
    time_allocation = data.get("time_allocation", {})
    all_events = data.get("all_events", [])

    # Guard: reject semantic_groupings for past weeks (no event data available)
    if has_semantic_groupings and not data.get("is_current_week"):
        logger.info(
            "tool.render_weekly_report.semantic_breakdown_unavailable",
            correlation_id=correlation_id,
            user_id=user_id,
            week_start=data.get("week_start"),
        )
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="Semantic breakdown not available for this week.",
            )],
            structuredContent={
                "success": False,
                "error": "semantic_breakdown_unavailable",
                "assistant_guidance": (
                    "Semantic breakdown is not available for past weeks — "
                    "detailed event data is only available for the current week. "
                    "Do NOT propose or offer any breakdown. "
                    "Suggest looking at the current week instead where event-level data is available. "
                    "Do NOT suggest any other workarounds, sub-tags, naming patterns, or tracking changes."
                ),
            },
            isError=True,
        )

    # Early return when no priorities existed during this week
    # Prevents empty pie chart widget and incorrect LLM guidance
    if not priorities:
        week_label = (
            "This week" if data.get("is_current_week")
            else f"Week of {data.get('week_start')}"
        )

        logger.info(
            "tool.render_weekly_report.no_priorities",
            correlation_id=correlation_id,
            user_id=user_id,
            week_start=data.get("week_start"),
            is_current_week=data.get("is_current_week"),
        )

        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=f"{week_label}: No priorities were being tracked during this period."
            )],
            structuredContent={
                "success": True,
                "data": {
                    "weekStart": data.get("week_start"),
                    "weekEnd": data.get("week_end"),
                    "isCurrentWeek": data.get("is_current_week"),
                    "priorities": [],
                    "slices": [],
                    "totalHours": 0,
                },
                "assistant_guidance": GUIDANCE_NO_PRIORITIES,
            },
        )

    # Normalize data for response
    normalized_priorities = [normalize_priority_report(p) for p in priorities]
    normalized_time_allocation = normalize_time_allocation(time_allocation)
    normalized_events = [normalize_event(e) for e in all_events]

    # -------------------------------------------------------------------------
    # Call 1 and Call 2: build pie chart slices and render widget
    # -------------------------------------------------------------------------

    # Filter events by call type (data minimization)
    if is_call1:
        # Call 1: Only non-priority events for semantic grouping proposal
        other_events = [e for e in normalized_events if not e.get("matchedKeywords")]
        priority_events = []
    else:
        # Call 2: Groupings already provided, no events needed
        other_events = []
        priority_events = []

    # Build pie chart slices
    try:
        slices = _build_pie_slices(
            priorities, time_allocation, semantic_groupings, semantic_target
        )
    except ToolUsageError as e:
        logger.warning(
            "tool.render_weekly_report.slice_validation_error",
            correlation_id=correlation_id,
            error=str(e),
        )
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=str(e),
            )],
            structuredContent={
                "success": False,
                "error": "slice_validation_error",
                "assistant_guidance": (
                    "The semantic groupings call was invalid — the targeted keyword has no "
                    "active priority. Check the parameters and retry."
                ),
            },
            isError=True,
        )

    # Compute semantic target label for widget subtitle
    semantic_target_label = None
    if semantic_target:
        if semantic_target in ("P1", "P2", "P3"):
            for p in priorities:
                if p.get("calendar_keyword") == semantic_target:
                    semantic_target_label = f"{semantic_target}: {p.get('name', '')}"
                    break
        elif semantic_target == "other":
            semantic_target_label = "Other"

    # Calculate total hours for pie chart
    total_hours = float(normalized_time_allocation.get("totalTrackedHours", 0))

    logger.info(
        "tool.render_weekly_report.success",
        correlation_id=correlation_id,
        user_id=user_id,
        week_start=data.get("week_start"),
        is_current_week=data.get("is_current_week"),
        priority_count=len(priorities),
        slice_count=len(slices),
        has_semantic_groupings=has_semantic_groupings,
        semantic_target=semantic_target,
        other_event_count=len(other_events),
    )

    # Build human-readable summary
    week_label = "This week" if data.get("is_current_week") else f"Week of {data.get('week_start')}"

    if has_semantic_groupings:
        text = f"{week_label}: {total_hours:.1f}h tracked with refined time breakdown."
    else:
        text = f"{week_label}: {total_hours:.1f}h tracked across {len(priorities)} priorities."

    # Build assistant guidance
    assistant_guidance = _build_assistant_guidance(
        data, priorities, other_events, has_semantic_groupings
    )

    # ALWAYS include _meta — render tool always produces widget
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=text
        )],
        structuredContent={
            "success": True,
            "data": {
                "weekStart": data.get("week_start"),
                "weekEnd": data.get("week_end"),
                "slices": slices,
                "totalHours": total_hours,
                "semanticTarget": semantic_target,
                "semanticTargetLabel": semantic_target_label,
                "isCurrentWeek": data.get("is_current_week"),
                "priorities": normalized_priorities,
                "timeAllocation": normalized_time_allocation,
                "otherEvents": other_events,
                "priorityEvents": priority_events,
            },
            "_meta": {
                "openai/outputTemplate": WIDGET_URI,
            },
            "assistant_guidance": assistant_guidance,
        },
    )


# ============================================================================
# Tool Definition
# ============================================================================

RENDER_WEEKLY_REPORT = ToolDefinition(
    name=NAME,
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=WIDGET_URI,  # Pie chart renders in pg-dashboard widget
    handle=handle,
    read_only_hint=True,
    destructive_hint=False,
    open_world_hint=True,  # Calls Google Calendar API via backend
    widget_accessible=True,  # Widget can call this tool (for future 3-week nav)
)
