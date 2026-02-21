"""
onboarding_calendar_setup tool for Priority Guardian MCP.

Phase 2 onboarding — educates user on how PG tracks time via calendar keywords,
generates their first snapshot, introduces deliverables, and sets up weekly reflection.

Three phases called in sequence:
1. keyword_education — explains P1/P2/P3 mechanism, prompts user to add keywords to event titles
2. first_weekly_report — generates first weekly report with real data, introduces deliverables
3. reflection_setup — introduces dashboard + weekly report, suggests recurring reflection event
"""

from datetime import date, timedelta
import structlog
from mcp import types as mcp_types

from mcp_server.priority_guardian.http_client import backend_get
from .base import ToolDefinition, ToolUsageError

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "onboarding_calendar_setup"

DESCRIPTION = """Walk the user through how Priority Guardian tracks time using your Google Calendar. If permitted, this reads calendar events and priorities to show based on real calendar data how progress tracking workds.

This tool provides the educational content and user-specific data you need to teach the user how Priority Guardian tracks their time. You cannot explain the tracking mechanism correctly without calling this tool — it returns the user's real priorities, keywords, calendar data, and step-by-step guidance for each phase.

Call this tool ONLY after the user has set up their priorities AND connected Google Calendar via the dashboard. NEVER call this for returning users who have already completed onboarding.
If calendar is not connected, do NOT call this tool — instead guide user to connect via the full dashboard first. ALWAYS follow the flow of this tool.

FLOW: Call this tool THREE TIMES in sequence — once per phase (keyword_education → first_weekly_report → reflection_setup). Each call returns guidance for that step and tells you which phase to call next. Wait for user action between phases.

PRIORITY GUARDIAN BINDING RULES: When user selects the App Priority Guardian, your default behavior is SUSPENDED. Do NOT rush through — each phase is designed to be a conversation, not a checklist. Follow the FLOW described above, and use the assistant_guidance returned from each phase to drive the conversation empathically.
Example for empathic tone: 'So your first priority is Ship V1.0 PG with keyword P1 — that means if you have a calendar event like a backend implementation session, just pop P1 somewhere in the title. P1: Backend implementation, Backend implementation P1, doesn't matter. PG picks it up either way.'"""

WIDGET_URI = "ui://widget/pg-dashboard.html"

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "phase": {
            "type": "string",
            "enum": ["keyword_education", "first_weekly_report", "reflection_setup"],
            "description": (
                "Which phase of onboarding step 2 to execute. Must be called in sequence: "
                "keyword_education first, then first_weekly_report after user adds keywords to event titles, "
                "then reflection_setup after user sees snapshot."
            ),
        },
    },
    "required": ["phase"],
    "additionalProperties": False,
}

REQUIRED_SCOPES = ["pg.access"]



# ============================================================================
# Phase Handlers
# ============================================================================

async def _handle_keyword_education(
    user_id: str,
    correlation_id: str,
) -> mcp_types.CallToolResult:
    """
    Phase 1: Keyword education.

    Fetches priorities with keywords, verifies calendar connection,
    returns guidance for teaching the keyword mechanism.
    """
    logger.info(
        "onboarding.phase_called",
        phase="keyword_education",
        user_id=user_id,
        correlation_id=correlation_id,
    )

    # Log if user might be returning (past snapshots exist), but don't block
    today = date.today()
    days_since_monday = today.weekday()
    last_monday = today - timedelta(days=days_since_monday + 7)
    week_start = last_monday.isoformat()

    try:
        past_report = await backend_get(
            f"/api/priority-guardian/weekly-report?week_start={week_start}",
            user_id,
            correlation_id,
        )
        if past_report.get("success") and past_report.get("data", {}).get("snapshot_saved"):
            logger.info(
                "onboarding.possible_returning_user",
                user_id=user_id,
                correlation_id=correlation_id,
                snapshot_saved=True,
            )
    except Exception as e:
        logger.warning(
            "onboarding.past_check_failed",
            user_id=user_id,
            correlation_id=correlation_id,
            error=str(e),
        )

    # Fetch priorities and connection status
    try:
        result = await backend_get(
            "/api/priority-guardian/priorities",
            user_id,
            correlation_id,
        )
    except Exception as e:
        logger.error(
            "onboarding.priorities_fetch_failed",
            user_id=user_id,
            correlation_id=correlation_id,
            error=str(e),
        )
        raise

    if not result.get("success"):
        raise ToolUsageError("Failed to fetch priorities")

    data = result.get("data", {})
    priorities = data.get("priorities", [])
    google_connection = data.get("google_connection", {"connected": False})

    # Guard: no calendar connection
    if not google_connection.get("connected"):
        logger.info(
            "onboarding.no_connection",
            user_id=user_id,
            correlation_id=correlation_id,
        )
        return mcp_types.CallToolResult(
            isError=True,
            content=[mcp_types.TextContent(
                type="text",
                text="Google Calendar isn't connected yet. Open the full dashboard to set that up first.",
            )],
        )

    # Guard: no active priorities
    active_priorities = [p for p in priorities if p.get("status") == "active"]
    if not active_priorities:
        logger.info(
            "onboarding.no_priorities",
            user_id=user_id,
            correlation_id=correlation_id,
        )
        return mcp_types.CallToolResult(
            isError=True,
            content=[mcp_types.TextContent(
                type="text",
                text="Set up at least one priority first.",
            )],
        )

    # Build priority list for guidance
    priority_list = [
        {"name": p.get("name"), "keyword": p.get("calendar_keyword")}
        for p in active_priorities
        if p.get("calendar_keyword")
    ]

    logger.info(
        "onboarding.phase_success",
        phase="keyword_education",
        user_id=user_id,
        correlation_id=correlation_id,
        priority_count=len(priority_list),
    )

    # Build structured response
    structured_content = {
        "success": True,
        "data": {
            "priorities": [
                {
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "type": p.get("type"),
                    "calendarKeyword": p.get("calendar_keyword"),
                }
                for p in active_priorities
            ],
        },
        "assistant_guidance": {
            "action": "KEYWORD_EDUCATION",
            "priorities": priority_list,
            "instruction": (
                "Explain how PG tracks time: PG scans calendar event titles for keywords (P1, P2, P3) to track time spent on each priority. "
                "When PG finds a keyword in an event title, it counts that event's hours toward that priority. It's flexible — 'P1: Sales calls', "
                "'Sales calls P1', or 'p1 client meeting' all work. Case and position don't matter. "
                "Use the user's real priority names and keywords as examples: 'If [priority_name] is "
                "[keyword], name your event something like [keyword]: [example activity]'. "
                "Then prompt: 'Create 2-3 test events in Google Calendar for this week with your keywords in the titles. "
                "Come back when you're done — check your dashboard progress bar at the top to see your hours update (refresh if necessary), "
                "and then tell me so I can pull up your weekly report.' "
            ),
            "next_phase": "first_weekly_report",
        },
    }

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text="Ready to explain how keyword tracking works.",
        )],
        structuredContent=structured_content,
    )


async def _handle_first_weekly_report(
    user_id: str,
    correlation_id: str,
) -> mcp_types.CallToolResult:
    """
    Phase 2: First snapshot.

    Generates current week report with live calendar data.
    Includes deliverable education in guidance.
    """
    logger.info(
        "onboarding.phase_called",
        phase="first_weekly_report",
        user_id=user_id,
        correlation_id=correlation_id,
    )

    # Log if user might be returning (past snapshots exist), but don't block
    today = date.today()
    days_since_monday = today.weekday()
    last_monday = today - timedelta(days=days_since_monday + 7)
    week_start = last_monday.isoformat()

    try:
        past_report = await backend_get(
            f"/api/priority-guardian/weekly-report?week_start={week_start}",
            user_id,
            correlation_id,
        )
        if past_report.get("success") and past_report.get("data", {}).get("snapshot_saved"):
            logger.info(
                "onboarding.possible_returning_user",
                user_id=user_id,
                correlation_id=correlation_id,
                snapshot_saved=True,
            )
    except Exception as e:
        logger.warning(
            "onboarding.past_check_failed",
            user_id=user_id,
            correlation_id=correlation_id,
            error=str(e),
        )

    # Fetch current week report (live computation, no persistence)
    try:
        result = await backend_get(
            "/api/priority-guardian/weekly-report",
            user_id,
            correlation_id,
        )
    except Exception as e:
        logger.error(
            "onboarding.weekly_report_failed",
            user_id=user_id,
            correlation_id=correlation_id,
            error=str(e),
        )
        raise

    if not result.get("success"):
        error = result.get("error", {})
        error_code = error.get("code", "UNKNOWN_ERROR")

        # Handle specific error codes
        if error_code == "GOOGLE_NOT_CONNECTED":
            logger.info(
                "onboarding.no_connection",
                user_id=user_id,
                correlation_id=correlation_id,
            )
            return mcp_types.CallToolResult(
                isError=True,
                content=[mcp_types.TextContent(
                    type="text",
                    text="Google Calendar isn't connected yet. Open the full dashboard to set that up first.",
                )],
            )

        raise ToolUsageError(error.get("message", "Failed to generate weekly report"))

    data = result.get("data", {})
    priorities = data.get("priorities", [])
    time_allocation = data.get("time_allocation", {})
    all_events = data.get("all_events", [])

    # Guard: no active priorities
    if not priorities:
        logger.info(
            "onboarding.no_priorities",
            user_id=user_id,
            correlation_id=correlation_id,
        )
        return mcp_types.CallToolResult(
            isError=True,
            content=[mcp_types.TextContent(
                type="text",
                text="Set up at least one priority first.",
            )],
        )

    # Check for zero keyword hours
    keywords = time_allocation.get("keywords", {})
    priority_hours = sum(
        keywords.get(kw, {}).get("hours", 0)
        for kw in ["P1", "P2", "P3"]
    )
    other_hours = time_allocation.get("other_hours", 0)
    total_hours = time_allocation.get("total_tracked_hours", 0)

    if total_hours == 0:
        # Empty week — no events at all
        logger.info(
            "onboarding.zero_keyword_hours",
            user_id=user_id,
            correlation_id=correlation_id,
            reason="no_events",
        )
        return mcp_types.CallToolResult(
            isError=True,
            content=[mcp_types.TextContent(
                type="text",
                text=(
                    "No calendar events found for this week. Make sure you have events "
                    "scheduled in Google Calendar with your priority keywords (P1, P2, P3) "
                    "in the titles. Try again after adding some events."
                ),
            )],
        )

    if priority_hours == 0 and other_hours > 0:
        # Events exist but no keywords in titles
        logger.info(
            "onboarding.zero_keyword_hours",
            user_id=user_id,
            correlation_id=correlation_id,
            reason="no_keywords",
            other_hours=other_hours,
        )
        return mcp_types.CallToolResult(
            isError=True,
            content=[mcp_types.TextContent(
                type="text",
                text=(
                    "Keywords aren't reflected yet — make sure they're in the event titles "
                    "(like 'P1: Client meeting') and give Google a moment to sync. "
                    "Try again in a minute."
                ),
            )],
        )

    logger.info(
        "onboarding.phase_success",
        phase="first_weekly_report",
        user_id=user_id,
        correlation_id=correlation_id,
        total_hours=total_hours,
        priority_hours=priority_hours,
        other_hours=other_hours,
    )

    # Build normalized response data
    normalized_priorities = [
        {
            "id": p.get("id"),
            "name": p.get("name"),
            "type": p.get("type"),
            "calendarKeyword": p.get("calendar_keyword"),
            "actualHours": p.get("actual_hours"),
            "eventCount": p.get("event_count"),
            "deadlineDate": p.get("deadline_date"),
            "daysRemaining": p.get("days_remaining"),
            "deliverablesCompleted": p.get("deliverables_completed"),
            "deliverablesTotal": p.get("deliverables_total"),
            "targetHours": p.get("target_hours"),
            "flexStatus": p.get("flex_status"),
            "pacingStatus": p.get("pacing_status"),
        }
        for p in priorities
    ]

    normalized_time_allocation = {
        "totalTrackedHours": total_hours,
        "keywords": {
            "P1": {
                "hours": keywords.get("P1", {}).get("hours", 0),
                "eventCount": keywords.get("P1", {}).get("event_count", 0),
            },
            "P2": {
                "hours": keywords.get("P2", {}).get("hours", 0),
                "eventCount": keywords.get("P2", {}).get("event_count", 0),
            },
            "P3": {
                "hours": keywords.get("P3", {}).get("hours", 0),
                "eventCount": keywords.get("P3", {}).get("event_count", 0),
            },
        },
        "otherHours": other_hours,
    }

    normalized_events = [
        {
            "title": e.get("title", ""),
            "description": e.get("description", ""),
            "start": e.get("start"),
            "end": e.get("end"),
            "matchedKeywords": e.get("matched_keywords", []),
        }
        for e in all_events
    ]

    # Build structured response
    structured_content = {
        "success": True,
        "data": {
            "weekStart": data.get("week_start"),
            "weekEnd": data.get("week_end"),
            "isCurrentWeek": data.get("is_current_week", True),
            "priorities": normalized_priorities,
            "timeAllocation": normalized_time_allocation,
            "allEvents": normalized_events,
        },
        "_meta": {
            "openai/outputTemplate": WIDGET_URI,
        },
        "assistant_guidance": {
            "action": "FIRST_WEEKLY_REPORT",
            "instruction": (
                "Present the weekly snapshot. Show how time splits across priorities. "
                "Explain other time: total calendar hours minus keyword hours. This is non-priority work. "
                "Present it as useful context, not a gap to fix: 'You have ~Xh in non-priority events — "
                "meetings, admin, coordination. That's the rest of your week.' "
                "Then explain semantic grouping: PG reads event titles and descriptions to group events into categories. "
                "Any events can be grouped and dissected further — but use other time as the example here: "
                "'Your 12h of non-priority time includes 4h of meetings, 3h of admin, 2h of client support...' "
                "More descriptive event titles and descriptions lead to more accurate grouping. "
                "Example: 'Team standup' tells PG less than 'Standup — discussing client migration timeline'."
            ),
            "deliverable_education": {
                "instruction": (
                    "After presenting the snapshot, explain E2E deliverables — these apply ONLY to deadline priorities. "
                    "Show the contrast: "
                    "Without deliverables: 'P1: 12h this week — client calls, proposal writing, "
                    "research.' Hours and activity, but no sense of whether you're on track. "
                    "With deliverables: 'P1: 4/10 E2E deliverables done, 20 days to deadline.' Now "
                    "you know exactly where you stand. Then: 'You can add E2E deliverables for your "
                    "deadline priorities in the dashboard — the big chunks of work from start to finish. "
                    "Not tasks, just the major pieces. "
                    "For example, if your deadline priority is Launch client website, your E2E deliverables "
                    "might be: Design mockup delivered, All pages built and functional, Content fully migrated, "
                    "Client review and approval. Each one is a complete piece of work you either shipped or didn't. "
                    "Add them anytime.' "
                    "For flexible priorities: deliverables don't apply — the monthly goal already anchors "
                    "what the hours should produce. No coaching. No prompting to add them now."
                ),
            },
            "transition_prompt": {
                "required": True,
                "message": "That's your first weekly report. Want me to show you how to set up a weekly reflection so you can track patterns over time?",
                "instruction": "You MUST end your response with this message (adapt naturally but keep the meaning). Wait for user response before calling next phase.",
            },
            "next_phase": "reflection_setup",
        },
    }

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Here's your first weekly report: {total_hours:.1f}h tracked this week.",
        )],
        structuredContent=structured_content,
    )


async def _handle_reflection_setup(
    user_id: str,
    correlation_id: str,
) -> mcp_types.CallToolResult:
    """
    Phase 3: Reflection setup.

    Guidance-driven — introduces dashboard + weekly report, suggests recurring reflection event.
    No backend call needed — purely guidance.
    """
    logger.info(
        "onboarding.phase_called",
        phase="reflection_setup",
        user_id=user_id,
        correlation_id=correlation_id,
    )

    # No past-snapshot check here — first_weekly_report already logs returning-user signal
    # and this phase is guidance-only (no backend data needed)

    logger.info(
        "onboarding.phase_success",
        phase="reflection_setup",
        user_id=user_id,
        correlation_id=correlation_id,
    )

    # Build structured response (no backend data needed)
    structured_content = {
        "success": True,
        "data": {},
        "assistant_guidance": {
            "action": "REFLECTION_SETUP",
            "instruction": (
                "Introduce two ways to track progress: "
                "1) Dashboard — the progress bar shows real-time hours, a quick glance anytime. "
                "2) Weekly report — PG saves your data each week, building history for week-over-week "
                "comparison. Over time this reveals patterns about how you allocate your time. The weekly report is where you can dive deeper "
                "and spot patterns. "
                "Explain how to get it: 'Just ask me for your weekly report anytime — something like "
                "Show me my weekly report.' "
                "Then suggest: 'What gets scheduled is not forgotten and gets done. Create a recurring Friday calendar event — something "
                "like Weekly review or Check priorities. That's 10 minutes to ask for your weekly report, "
                "see the patterns, and decide what to shift for next week.'"
            ),
            "onboarding_complete": True,
        },
    }

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text="Ready to set up your weekly reflection routine.",
        )],
        structuredContent=structured_content,
    )


# ============================================================================
# Handler
# ============================================================================

async def handle(user_id: str, correlation_id: str, arguments: dict) -> mcp_types.CallToolResult:
    """
    Handle onboarding_calendar_setup tool call.

    Routes to appropriate phase handler based on `phase` argument.

    Args:
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID
        arguments: Tool arguments (phase required)

    Returns:
        CallToolResult with phase-specific data and guidance
    """
    phase = arguments.get("phase")

    if not phase:
        raise ToolUsageError("phase is required")

    if phase not in ("keyword_education", "first_weekly_report", "reflection_setup"):
        raise ToolUsageError(
            f"Invalid phase: {phase}. Must be one of: keyword_education, first_weekly_report, reflection_setup"
        )

    if phase == "keyword_education":
        return await _handle_keyword_education(user_id, correlation_id)
    elif phase == "first_weekly_report":
        return await _handle_first_weekly_report(user_id, correlation_id)
    elif phase == "reflection_setup":
        return await _handle_reflection_setup(user_id, correlation_id)

    # Should never reach here due to validation above
    raise ToolUsageError(f"Unknown phase: {phase}")


# ============================================================================
# Tool Definition
# ============================================================================

ONBOARDING_CALENDAR_SETUP = ToolDefinition(
    name=NAME,
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=None,  # Only first_weekly_report phase renders widget via structuredContent._meta
    handle=handle,
    read_only_hint=True,  # Never mutates state
    destructive_hint=False,
    open_world_hint=True,  # Reads Google Calendar via backend
    widget_accessible=False,  # Widget cannot call this tool
)
