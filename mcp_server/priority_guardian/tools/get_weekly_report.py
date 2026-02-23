"""
get_weekly_report tool for Priority Guardian MCP.

Returns weekly report data with per-priority hours, status indicators,
and pie chart visualization of time allocation.

On first call: Shows P1/P2/P3 + "Other" slice. LLM proposes semantic groupings.
On second call (with semantic_groupings): Shows priority slices + user-confirmed
semantic category slices. No persistence - purely conversational refinement.
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
    "and a pie chart breakdown of how your week was spent."
)

WIDGET_URI = "ui://widget/pg-dashboard.html"

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
            },
        },
        "semantic_target": {
            "type": "string",
            "enum": ["P1", "P2", "P3", "other"],
            "description": (
                "Which category to explode into semantic subcategories. "
                "When set, the named category is replaced by its semantic_groupings "
                "while all other categories remain as single slices. "
                "Only one category can be expanded at a time. "
                "Requires semantic_groupings to also be provided."
            ),
        },
    },
    "required": [],
}

REQUIRED_SCOPES = ["pg.access"]

# Timeout for backend call (seconds)
BACKEND_TIMEOUT = 15.0


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
) -> tuple[list[dict], str | None]:
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
        Tuple of (slices list, validation error message or None)

    Raises:
        ToolUsageError: For input validation failures
    """
    keywords = time_allocation.get("keywords", {})
    other_hours = time_allocation.get("other_hours", 0.0)

    # Default semantic_target to "other" when groupings provided but target not specified
    # (backwards compatibility)
    if semantic_groupings and len(semantic_groupings) > 0 and not semantic_target:
        semantic_target = "other"

    # Validation: semantic_target requires semantic_groupings
    if semantic_target and (not semantic_groupings or len(semantic_groupings) == 0):
        raise ToolUsageError("semantic_target requires semantic_groupings to be provided.")

    # Build map of active priority keywords
    active_keywords = {p.get("calendar_keyword") for p in priorities if p.get("calendar_keyword")}

    # Validation: if targeting a priority, it must be active
    if semantic_target in ("P1", "P2", "P3") and semantic_target not in active_keywords:
        raise ToolUsageError(f"No active priority found for {semantic_target}.")

    # Determine target hours for validation
    if semantic_target == "other":
        target_hours = other_hours
    elif semantic_target in ("P1", "P2", "P3"):
        target_hours = keywords.get(semantic_target, {}).get("hours", 0.0)
    else:
        target_hours = None

    # Validation: grouped hours cannot exceed target's hours by more than 0.5h
    if semantic_groupings and target_hours is not None:
        grouped_total = sum(g.get("hours", 0) for g in semantic_groupings)
        if grouped_total > target_hours + 0.5:
            raise ToolUsageError(
                f"Grouped hours ({grouped_total:.1f}h) exceed {semantic_target} time "
                f"({target_hours:.1f}h) by more than rounding tolerance. Please adjust."
            )

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
            grouped_total = sum(g.get("hours", 0) for g in semantic_groupings)

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
        grouped_total = sum(g.get("hours", 0) for g in semantic_groupings)

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

    return slices, None


def _build_assistant_guidance(
    data: dict,
    priorities: list[dict],
    all_events: list[dict],
    has_semantic_groupings: bool,
) -> str:
    """
    Build assistant guidance for presenting the weekly report.

    Three modes:
    1. No priorities: Tracking hadn't started for this week
    2. Without semantic_groupings: Propose groupings, ask user to confirm
    3. With semantic_groupings: Brief neutral observation, don't repeat categories

    Args:
        data: Backend response data
        priorities: List of priority dicts
        all_events: List of event dicts
        has_semantic_groupings: Whether semantic_groupings parameter was provided
    """
    # Defense in depth: if handle() early return is bypassed, still return safe guidance
    if not priorities:
        return (
            "No priorities were being tracked during this week. "
            "Do not mention P1, P2, or P3 keywords or time allocation. "
            "Simply tell the user that priority tracking had not started yet for this time period. "
            "If they created priorities after this week, you can mention that tracking begins "
            "from the first full week after creation. "
            "Keep it to one or two sentences. "
            "Do NOT mention snapshots, saving data, or persistence."
        )

    is_current = data.get("is_current_week", False)
    other_hours = data.get("time_allocation", {}).get("other_hours", 0)

    # Get non-priority events for semantic grouping proposal
    non_priority_events = [e for e in all_events if not e.get("matched_keywords")]

    guidance_parts = []

    if has_semantic_groupings:
        # MODE 2: Semantic groupings provided (second call)
        # Brief neutral observation, don't repeat categories
        guidance_parts.append(
            "The pie chart now shows the refined breakdown for the selected category. "
            "Do NOT repeat or list the categories — the chart displays them. "
            "Make a brief neutral observation about the allocation pattern without evaluation or recommendation. "
            "Ask what stands out to them. "
            "Keep it short — the visual does the heavy lifting."
        )
    else:
        # MODE 1: No semantic groupings (first call)
        # Opening context based on week status
        if is_current:
            guidance_parts.append(
                "This is your CURRENT WEEK in progress. Numbers will change as you work through the week. "
                "Frame this as a progress check-in, not a final tally."
            )
        else:
            guidance_parts.append(
                "This is a COMPLETED WEEK reflection. Present it as a look back at how the week was spent."
            )

        # Priority insights - narrate ALL active priorities including zero-hour ones
        guidance_parts.append(
            "Present each priority's hours naturally. For flexible priorities, note if they're "
            "ahead/on_track/behind their weekly target. For deadline priorities, mention pacing status "
            "and days remaining. IMPORTANT: Narrate ALL active priorities — if a priority has zero hours, "
            "say so explicitly (e.g., 'You didn't log any P3 time this week'). Keep insights brief and actionable."
        )

        # Semantic grouping proposal for "Other" time
        if other_hours > 0 and non_priority_events:
            guidance_parts.append(
                f"The user has {other_hours:.1f} hours of non-priority time. "
                "Based on the event titles and descriptions in allEvents, propose approximate "
                "semantic categories. Frame it as an observation: 'Your non-priority time looks like "
                "it breaks down to roughly: Client calls ~Xh, Admin ~Yh, etc.' "
                "Ask if this grouping looks right or if they'd adjust it. "
                "If they confirm, call get_weekly_report again with the semantic_groupings parameter "
                "containing the confirmed categories (category name, hours, event_count for each)."
            )
        elif other_hours > 0:
            guidance_parts.append(
                f"The user has {other_hours:.1f} hours of non-priority time but no matching events. "
                "Ask what this time was generally spent on if they'd like to reflect on it."
            )

        # Within-priority breakdown proposal
        guidance_parts.append(
            "You can also propose a within-priority breakdown for any single priority. "
            "If the user asks to see where their P1/P2/P3 time went, analyze the keyword-matched events "
            "for that priority from allEvents, propose approximate semantic categories based on event "
            "titles and descriptions, and if confirmed, call get_weekly_report again with semantic_target "
            "set to the keyword (e.g., 'P1') and semantic_groupings containing the confirmed within-priority "
            "categories. Only one category (a priority or 'other') can be expanded at a time."
        )

        # Closing
        guidance_parts.append(
            "Keep the tone reflective. The goal is insight, not judgment. "
            "Do NOT mention snapshots, saving data, or persistence."
        )

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

    has_semantic_groupings = semantic_groupings is not None

    logger.info(
        "tool.get_weekly_report.start",
        correlation_id=correlation_id,
        user_id=user_id,
        week_start=week_start,
        has_semantic_groupings=has_semantic_groupings,
        grouping_count=len(semantic_groupings) if semantic_groupings else 0,
        semantic_target=semantic_target,
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

    # Extract data
    data = result.get("data", {})
    priorities = data.get("priorities", [])
    time_allocation = data.get("time_allocation", {})
    all_events = data.get("all_events", [])

    # Early return when no priorities existed during this week
    # Prevents empty pie chart widget and incorrect LLM guidance
    if not priorities:
        week_label = (
            "This week" if data.get("is_current_week")
            else f"Week of {data.get('week_start')}"
        )
        no_priorities_guidance = (
            "No priorities were being tracked during this week. "
            "Do not mention P1, P2, or P3 keywords or time allocation. "
            "Simply tell the user that priority tracking had not started yet for this time period. "
            "If they created priorities after this week, you can mention that tracking begins "
            "from the first full week after creation. "
            "Keep it to one or two sentences. "
            "Do NOT mention snapshots, saving data, or persistence."
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
                "assistant_guidance": no_priorities_guidance,
            },
        )

    # Build pie chart slices (validates semantic_groupings/semantic_target if provided)
    try:
        slices, validation_error = _build_pie_slices(
            priorities, time_allocation, semantic_groupings, semantic_target
        )
    except ToolUsageError:
        # Re-raise ToolUsageError (input validation failures)
        raise

    if validation_error:
        logger.warning(
            "tool.get_weekly_report.validation_error",
            correlation_id=correlation_id,
            error=validation_error,
        )
        return mcp_types.CallToolResult(
            isError=True,
            content=[mcp_types.TextContent(
                type="text",
                text=validation_error
            )],
        )

    # Normalize data for response
    normalized_priorities = [_normalize_priority_report(p) for p in priorities]
    normalized_time_allocation = _normalize_time_allocation(time_allocation)
    normalized_events = [_normalize_event(e) for e in all_events]

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
    total_hours = normalized_time_allocation.get("totalTrackedHours", 0)

    logger.info(
        "tool.get_weekly_report.success",
        correlation_id=correlation_id,
        user_id=user_id,
        week_start=data.get("week_start"),
        is_current_week=data.get("is_current_week"),
        priority_count=len(priorities),
        slice_count=len(slices),
        has_semantic_groupings=has_semantic_groupings,
        semantic_target=semantic_target,
    )

    # Build human-readable summary
    # Note: empty priorities case handled by early return above
    week_label = "This week" if data.get("is_current_week") else f"Week of {data.get('week_start')}"

    if has_semantic_groupings:
        text = f"{week_label}: {total_hours:.1f}h tracked with refined time breakdown."
    else:
        text = f"{week_label}: {total_hours:.1f}h tracked across {len(priorities)} priorities."

    # Build assistant guidance based on whether groupings were provided
    assistant_guidance = _build_assistant_guidance(
        data, priorities, all_events, has_semantic_groupings
    )

    # Build structured content with pie chart data
    # Widget reads: slices, totalHours, weekStart, weekEnd
    # LLM reads: priorities, allEvents, isCurrentWeek via assistant_guidance context
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
            # Report fields (LLM uses these via guidance)
            "isCurrentWeek": data.get("is_current_week"),
            "priorities": normalized_priorities,
            "timeAllocation": normalized_time_allocation,
            "allEvents": normalized_events,
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
    read_only_hint=False,  # Token refresh can write to core_connections
    destructive_hint=False,
    open_world_hint=True,  # Calls Google Calendar API via backend
    widget_accessible=True,  # Widget can call this tool (for future 3-week nav)
)
