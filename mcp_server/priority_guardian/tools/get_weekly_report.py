"""
get_weekly_report tool for Priority Guardian MCP.

Returns weekly report data with per-priority hours, status indicators,
and pie chart visualization of time allocation.

On first call: Shows P1/P2/P3 + "Other" slice. LLM proposes semantic groupings.
On second call (with semantic_groupings): Shows priority slices + user-confirmed
semantic category slices. No persistence - purely conversational refinement.
"""

import asyncio

import structlog
from mcp import types as mcp_types

from mcp_server.priority_guardian.http_client import backend_get
from .base import ToolDefinition, ToolUsageError
from .widget_tools.constants import WIDGET_URI

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "get_weekly_report"

DESCRIPTION = (
    "Get your weekly report showing time invested in each priority. "
    "Returns hours worked and a pie chart breakdown of how your week was spent.\n\n"
    "Call this tool:\n"
    "- When the user asks about their week, progress, or hours\n"
    "- When the user says \"how did I do?\", \"show my report\", \"weekly summary\"\n"
    "- At the start of a reflection or check-in conversation\n\n"
    "Do NOT call this tool:\n"
    "- During onboarding or priority setup\n"
    "- When the user is asking about patterns or trends over time (use get_patterns instead)"
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
                "User-confirmed semantic categories for the target slice. "
                "When provided, replaces the target category's slice in the pie chart "
                "with these subcategory slices. Only pass this after user confirms groupings."
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
                "Dual role: (1) With semantic_groupings provided, specifies which "
                "category to explode into subcategories — the named category is "
                "replaced by its semantic_groupings while all other categories "
                "remain as single slices. (2) Without semantic_groupings, "
                "setting semantic_target to 'P1', 'P2', or 'P3' requests that "
                "priority's events be returned in priorityEvents for you to "
                "propose a breakdown. Do NOT combine a priority semantic_target "
                "with semantic_groupings — use one role at a time."
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
            "tool.get_weekly_report.timeout",
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
    "IMMEDIATELY call get_weekly_report again with the semantic_groupings parameter "
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
    "You can also propose a within-priority breakdown for any single priority. "
    "To do so, call get_weekly_report again with semantic_target set to the priority keyword "
    "(e.g. 'P1'). The tool will return that priority's events in priorityEvents for you to categorise."
)

# Template with {keyword} placeholder for priority breakdown (call 2b)
GUIDANCE_PRIORITY_BREAKDOWN_TEMPLATE = (
    "The user wants to see how their {keyword} time breaks down. "
    "Based on the event titles and descriptions in priorityEvents, propose approximate "
    "semantic subcategories. Frame it as a NEUTRAL observation: "
    "'Your {keyword} time looks like it breaks down to roughly: [category] ~Xh, etc.' "
    "Ask if this grouping looks right. "
    "CRITICAL: NEVER interpret or judge priority time. "
    "If they confirm OR express any intent to see the breakdown, "
    "IMMEDIATELY call get_weekly_report again with semantic_groupings containing your "
    "proposed categories and semantic_target='{keyword}'. "
    "Do NOT ask again. Just call the tool."
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


# ============================================================================
# Normalization Helpers
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
        # pacingStatus intentionally excluded - LLM should not use computed status

    # Flexible-specific fields
    elif p.get("type") == "flexible":
        result["targetHours"] = p.get("target_hours")
        # flexStatus intentionally excluded - LLM should not use computed status
        # Aggregates are placeholders (always 0/null until persistence ships)
        result["streakCount"] = p.get("streak_count", 0)
        result["totalHoursInvested"] = p.get("total_hours_invested", 0.0)

    # Previous week comparison (always null until persistence ships)
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

    # Note: semantic_target without semantic_groupings is valid — handler passes
    # slice_semantic_target=None for call 2b, so this function sees None and renders
    # normal chart. Validation of semantic_target + groupings combinations happens
    # at handler level (mutual exclusion check).

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
    priority_events: list[dict],
    has_semantic_groupings: bool,
    has_priority_breakdown: bool,
    semantic_target: str | None,
) -> str:
    """
    Build assistant guidance for presenting the weekly report.

    Four modes:
    1. No priorities: Tracking hadn't started for this week
    2. Call 1 (no groupings, no priority breakdown): Propose other groupings
    3. Call 2 (semantic_groupings provided): Brief neutral observation
    4. Call 2b (priority breakdown requested): Propose priority subcategories

    Args:
        data: Backend response data
        priorities: List of priority dicts
        other_events: Non-priority events (for call 1)
        priority_events: Events for specific priority (for call 2b)
        has_semantic_groupings: Whether semantic_groupings parameter was provided
        has_priority_breakdown: Whether this is a priority breakdown request (call 2b)
        semantic_target: Target keyword for breakdown ("P1", "P2", "P3", or "other")
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
    elif has_priority_breakdown:
        # Call 2b: Priority breakdown requested — propose subcategories
        if is_current:
            guidance_parts.append(GUIDANCE_CURRENT_WEEK)
        else:
            guidance_parts.append(GUIDANCE_COMPLETED_WEEK)

        if priority_events and semantic_target:
            guidance_parts.append(
                GUIDANCE_PRIORITY_BREAKDOWN_TEMPLATE.format(keyword=semantic_target)
            )
        else:
            # No events for this priority
            guidance_parts.append(
                f"No event data available for {semantic_target} breakdown. "
                "Breakdowns require event-level data from the current week."
            )
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
    Get weekly report for the user with pie chart visualization.

    Args:
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID
        arguments: Tool arguments (optional week_start, semantic_groupings, semantic_target)

    Returns:
        CallToolResult with weekly report data and pie chart slices
    """
    week_start = arguments.get("week_start")
    semantic_groupings = arguments.get("semantic_groupings")
    semantic_target = arguments.get("semantic_target")

    # Treat empty array same as not provided
    if semantic_groupings is not None and len(semantic_groupings) == 0:
        semantic_groupings = None

    # Call type detection (three-way, mutually exclusive)
    has_semantic_groupings = semantic_groupings is not None and len(semantic_groupings) > 0
    has_priority_breakdown = (
        semantic_target in ("P1", "P2", "P3")
        and not has_semantic_groupings
    )
    is_call1 = (
        not has_semantic_groupings
        and not has_priority_breakdown
    )
    # Note: semantic_target="other" with no semantic_groupings falls into is_call1 (correct —
    # "other" without groupings means no breakdown has been requested yet)

    # Mutual exclusion validation: semantic_groupings + priority semantic_target is invalid
    if has_semantic_groupings and semantic_target in ("P1", "P2", "P3"):
        logger.warning(
            "tool.get_weekly_report.invalid_parameters",
            correlation_id=correlation_id,
            user_id=user_id,
            semantic_target=semantic_target,
            has_semantic_groupings=has_semantic_groupings,
        )
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text="Invalid parameters.")],
            structuredContent={
                "success": False,
                "error": "invalid_parameters",
                "assistant_guidance": (
                    "semantic_groupings and a priority semantic_target cannot be used together. "
                    "Use semantic_target alone to request priority events for breakdown, "
                    "then semantic_groupings to confirm the categorisation."
                ),
            },
            isError=True,
        )

    logger.info(
        "tool.get_weekly_report.start",
        correlation_id=correlation_id,
        user_id=user_id,
        week_start=week_start,
        has_semantic_groupings=has_semantic_groupings,
        has_priority_breakdown=has_priority_breakdown,
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
            "tool.get_weekly_report.error_response",
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

    # Guard: reject semantic_groupings when no event data available
    # (past weeks have empty all_events, can't break down)
    if has_semantic_groupings and not all_events:
        logger.info(
            "tool.get_weekly_report.semantic_breakdown_unavailable",
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

    # Guard: reject call 2b (priority breakdown request) when no event data available
    # (past weeks have empty all_events, can't break down priorities either)
    if has_priority_breakdown and not all_events:
        logger.info(
            "tool.get_weekly_report.priority_breakdown_unavailable",
            correlation_id=correlation_id,
            user_id=user_id,
            week_start=data.get("week_start"),
            semantic_target=semantic_target,
        )
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

    # Early return when no priorities existed during this week
    # Prevents empty pie chart widget and incorrect LLM guidance
    if not priorities:
        week_label = (
            "This week" if data.get("is_current_week")
            else f"Week of {data.get('week_start')}"
        )

        logger.info(
            "tool.get_weekly_report.no_priorities",
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

    # Build pie chart slices (validates semantic_groupings/semantic_target if provided)
    # For Call 2b (priority breakdown), pass None to show normal chart (no slice explosion)
    slice_semantic_target = None if has_priority_breakdown else semantic_target
    try:
        slices = _build_pie_slices(
            priorities, time_allocation, semantic_groupings, slice_semantic_target
        )
    except ToolUsageError as e:
        logger.warning(
            "tool.get_weekly_report.slice_validation_error",
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
                    "The semantic groupings call was invalid — either semantic_target was "
                    "provided without semantic_groupings, or the targeted keyword has no "
                    "active priority. Check the parameters and retry."
                ),
            },
            isError=True,
        )

    # Normalize data for response
    normalized_priorities = [_normalize_priority_report(p) for p in priorities]
    normalized_time_allocation = _normalize_time_allocation(time_allocation)
    normalized_events = [_normalize_event(e) for e in all_events]

    # Filter events by call type (data minimization - Inc 75)
    if is_call1:
        # Call 1: Only non-priority events for semantic grouping proposal
        other_events = [e for e in normalized_events if not e.get("matchedKeywords")]
        priority_events = []
    elif has_priority_breakdown:
        # Call 2b: Only events matching the requested priority keyword
        other_events = []
        priority_events = [
            e for e in normalized_events
            if semantic_target in e.get("matchedKeywords", [])
        ]
    else:
        # Call 2: Groupings already provided, no events needed
        other_events = []
        priority_events = []

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
        "tool.get_weekly_report.success",
        correlation_id=correlation_id,
        user_id=user_id,
        week_start=data.get("week_start"),
        is_current_week=data.get("is_current_week"),
        priority_count=len(priorities),
        slice_count=len(slices),
        has_semantic_groupings=has_semantic_groupings,
        has_priority_breakdown=has_priority_breakdown,
        semantic_target=semantic_target,
        other_event_count=len(other_events),
        priority_event_count=len(priority_events),
    )

    # Build human-readable summary
    # Note: empty priorities case handled by early return above
    week_label = "This week" if data.get("is_current_week") else f"Week of {data.get('week_start')}"

    if has_semantic_groupings:
        text = f"{week_label}: {total_hours:.1f}h tracked with refined time breakdown."
    elif has_priority_breakdown:
        text = f"{week_label}: Breakdown for {semantic_target} ({len(priority_events)} events)."
    else:
        text = f"{week_label}: {total_hours:.1f}h tracked across {len(priorities)} priorities."

    # Build assistant guidance based on call type
    assistant_guidance = _build_assistant_guidance(
        data, priorities, other_events, priority_events,
        has_semantic_groupings, has_priority_breakdown, semantic_target
    )

    # Build structured content with pie chart data
    # Widget reads: slices, totalHours, weekStart, weekEnd
    # LLM reads: priorities, otherEvents/priorityEvents, isCurrentWeek via assistant_guidance context
    structured_content = {
        "success": True,
        "data": {
            # Pie chart fields (widget uses these)
            "weekStart": data.get("week_start"),
            "weekEnd": data.get("week_end"),
            "slices": slices,
            "totalHours": total_hours,
            "semanticTarget": semantic_target,  # "P1", "P2", "P3", "other", or None
            "semanticTargetLabel": semantic_target_label,  # "P1: Ship v1.0" or "Other" or None
            # Aggregate fields (always present — widget and model need these on every call)
            "isCurrentWeek": data.get("is_current_week"),
            "priorities": normalized_priorities,
            "timeAllocation": normalized_time_allocation,
            # Event fields — fixed keys, populated only for relevant call type
            "otherEvents": other_events,       # non-empty on call 1 only
            "priorityEvents": priority_events, # non-empty on call 2b only
        },
        "_meta": {
            "openai/outputTemplate": WIDGET_URI,
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
    widget_uri=WIDGET_URI,  # Pie chart renders in pg-dashboard widget
    handle=handle,
    read_only_hint=True,   # openWorldHint=True covers Google Calendar API call; token refresh is invisible backend detail
    destructive_hint=False,
    open_world_hint=True,  # Calls Google Calendar API via backend
    widget_accessible=True,  # Widget can call this tool (for future 3-week nav)
)
