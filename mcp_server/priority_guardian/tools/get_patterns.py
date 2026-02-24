"""
get_patterns tool for Priority Guardian MCP.

Returns behavioral patterns detected from user's priority tracking history.
Patterns include consistency streaks, low-investment priorities,
priority switching frequency, and priority protection under calendar pressure.

Called by LLM:
- During weekly reflection after presenting the weekly report
- When user asks "how am I doing?", "any trends?", "what patterns do you see?"
- When user asks about tracking behavior over time

Implements increment_21 specification.
"""

import structlog
from mcp import types as mcp_types

from mcp_server.priority_guardian.http_client import backend_get
from .base import ToolDefinition

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "get_patterns"

DESCRIPTION = (
    "Returns behavioral patterns detected from user's priority tracking history. "
    "Patterns include consistency streaks, low-investment detection (for flexible priorities, or deadline "
    "priorities when the deadline is approaching), priority switching frequency, and priority protection "
    "under calendar pressure. Requires at least 4 weeks of tracking data.\n\n"
    "Call this tool:\n"
    "- During weekly reflection after presenting the weekly report\n"
    "- When the user asks \"how am I doing?\", \"any trends?\", \"what patterns do you see?\"\n"
    "- When the user asks about their tracking behavior over time\n\n"
    "Do NOT call this tool:\n"
    "- During onboarding (not enough data)\n"
    "- When the user is doing CRUD operations on priorities\n"
    "- If you already called it in this conversation and data hasn't changed"
)

INPUT_SCHEMA = {
    "type": "object",
    "properties": {},
    "required": [],
}

REQUIRED_SCOPES = ["pg.access"]

# No widget for patterns - LLM narrates conversationally
WIDGET_URI = None


# ============================================================================
# assistant_guidance Templates
# ============================================================================

# Common guidance that applies to every patterns-found response
GUIDANCE_COMMON = (
    "Keep it conversational. No bullet points, no headers, no numbered lists. "
    "Weave patterns into a natural narrative. "
    "Observed numbers (\"0.5h/week\", \"6-week streak\", \"22% growth\") are good — state them. "
    "Internal thresholds and computation rules must never be mentioned. "
    "Do not use the word \"abandoned\" — paraphrase neutrally (e.g., \"getting very little time lately\"). "
    "Do not repeat any internal field names or identifiers from the data verbatim — "
    "use the narration_label or your own phrasing instead. "
    "If a pattern has calendar_keyword null, refer to the priority by name only — do not mention a keyword. "
    "For retired priorities, frame the pattern as historical "
    "(\"before you retired it\" or \"when it was active\") — do not imply the pattern is ongoing. "
    "Do not compute or invent patterns beyond what this response contains."
)

# Per-pattern guidance constants
GUIDANCE_CONSISTENCY_STREAK = (
    "Always bold the priority name (e.g., **Ship V1.0 PG**) when first mentioning it. "
    "The dashboard already shows the streak count — do not just restate it. "
    "weekly_detail contains the actual hours and target hours for each week in the streak. "
    "Use these specific numbers in your narration. "
    "If some weeks fell significantly below target but the user still logged time, "
    "acknowledge that showing up consistently matters more than hitting the target every week. "
    "Reference the specific week's hours. "
    "If hours are steady across weeks, note the reliability. "
    "If the streak is 4+ weeks, note that this has moved past initial motivation into habit territory — "
    "the weeks where hours were lowest are actually the most telling because the user kept going anyway. "
    "Keep it to 2-3 sentences max."
)

GUIDANCE_ABANDONED_PRIORITY = (
    "Always bold the priority name (e.g., **Plan my birthday party**) when first mentioning it. "
    "weekly_detail contains the actual hours for the last 4 weeks. "
    "Reference these specific numbers rather than just the average. "
    "State the observed pattern neutrally. "
    "If the pattern includes weeks_until_deadline, mention how close the deadline is as context "
    "(e.g., \"with about 3 weeks to go\" not \"you only have 3 weeks left!\"). "
    "If weeks_until_deadline is 0, the deadline has passed or is this week — "
    "frame accordingly without judgment. "
    "Ask what the user wants to do about it — do not prescribe action. "
    "Do not judge. Do not say \"you should retire this\" or \"you're neglecting this.\" "
    "Keep it to 1-2 sentences plus a question."
)

# Two variants for priority switching based on whether criteria were defined
GUIDANCE_PRIORITY_SWITCHING_NO_CRITERIA = (
    "This pattern detected multiple priorities that were retired without any goals or deliverables defined — "
    "meaning there was no clear success criteria to work toward. "
    "Name the specific retired priorities. "
    "Always bold the retired priority names when mentioning them. "
    "Present both interpretations: this could be healthy, intentional pivoting — "
    "or it could signal reactive switching. To help the user reflect, ask 1-2 of these "
    "questions based on what fits: Did you have hard evidence that each pivot was more "
    "promising, or did it feel more like a gut call? Were any of those switches driven "
    "by frustration, low energy, or feeling stuck rather than a clear reason to move on? "
    "Keep the overall narration to 2-4 sentences including the question(s)."
)

GUIDANCE_PRIORITY_SWITCHING_INCOMPLETE = (
    "This pattern detected multiple priorities that were retired with goals or deliverables "
    "still incomplete — meaning they were abandoned before completion, not finished and moved on from. "
    "Name the specific retired priorities and mention what was left incomplete "
    "(e.g., '1 out of 3 goals done') so the user knows exactly which ones you're referring to "
    "and what was unfinished. The user needs specifics to reflect meaningfully. "
    "Always bold the retired priority names when mentioning them. "
    "Present both interpretations: this could be healthy, intentional pivoting — "
    "or it could signal reactive switching. To help the user reflect, ask 1-2 of these "
    "questions based on what fits: Did you have hard evidence that each pivot was more "
    "promising, or did it feel more like a gut call? Were any of those switches driven "
    "by frustration, low energy, or feeling stuck rather than a clear reason to move on? "
    "Keep the overall narration to 2-4 sentences including the question(s)."
)

GUIDANCE_PRIORITY_PROTECTION = (
    "Always bold the priority name when first mentioning it. "
    "Acknowledge warmly that the user protected this priority's time despite growing calendar pressure. "
    "period_summary contains the exact numbers. Reference them: priority hours stayed at ~Xh/week "
    "while total calendar grew from ~Yh to ~Zh (N% increase). "
    "This is a positive signal — the user is defending what matters to them. "
    "Keep it to 1-2 sentences."
)

# Mapping from pattern_type to guidance constant
# Note: priority_switching is handled dynamically in _build_assistant_guidance
PATTERN_GUIDANCE = {
    "consistency_streak": GUIDANCE_CONSISTENCY_STREAK,
    "abandoned_priority": GUIDANCE_ABANDONED_PRIORITY,
    "priority_protection": GUIDANCE_PRIORITY_PROTECTION,
}

# Human-readable labels for pattern types (inline phrasing for guidance)
PATTERN_LABELS = {
    "consistency_streak": "consistency streak",
    "abandoned_priority": "low-investment priority",
    "priority_switching": "priority switching",
    "priority_protection": "priority protection",
}

# Canonical order for iterating patterns in guidance
CANONICAL_PATTERN_ORDER = [
    "consistency_streak",
    "abandoned_priority",
    "priority_switching",
    "priority_protection",
]

GUIDANCE_INSUFFICIENT_DATA_TEMPLATE = (
    "The user has {weeks} weeks of tracking data. We wait for at least 4 completed weeks of "
    "tracking snapshots before surfacing patterns. Mention this briefly and move on. "
    "Do not apologize or over-explain."
)

GUIDANCE_NO_PATTERNS = (
    "No notable patterns detected yet. Mention this briefly. Do not fill with generic advice."
)


# ============================================================================
# Helpers
# ============================================================================

def _get_switching_guidance(patterns: list) -> str:
    """
    Select the appropriate priority_switching guidance variant.

    If all retired priorities have goals_total == 0 and deliverables_total == 0,
    use NO_CRITERIA variant. Otherwise use INCOMPLETE variant (handles mixed cases).

    Args:
        patterns: List of pattern dicts from backend

    Returns:
        Selected switching guidance string
    """
    # Find the switching pattern
    switching_pattern = None
    for p in patterns:
        if p.get("pattern_type") == "priority_switching":
            switching_pattern = p
            break

    if not switching_pattern:
        return GUIDANCE_PRIORITY_SWITCHING_INCOMPLETE  # Fallback

    retired_priorities = switching_pattern.get("retired_priorities", [])

    if not retired_priorities:
        return GUIDANCE_PRIORITY_SWITCHING_NO_CRITERIA  # No data = no criteria

    # Check if ALL retired priorities have no criteria defined
    all_no_criteria = True
    for entry in retired_priorities:
        # Flexible priorities have goals_total, deadline priorities have deliverables_total
        goals_total = entry.get("goals_total", 0)
        deliverables_total = entry.get("deliverables_total", 0)
        if goals_total > 0 or deliverables_total > 0:
            all_no_criteria = False
            break

    if all_no_criteria:
        return GUIDANCE_PRIORITY_SWITCHING_NO_CRITERIA
    else:
        return GUIDANCE_PRIORITY_SWITCHING_INCOMPLETE


def _build_assistant_guidance(data: dict) -> str:
    """
    Build assistant_guidance based on response state.

    Uses 'reason' enum from backend to select appropriate guidance.
    For PATTERNS_FOUND, composes guidance from GUIDANCE_COMMON plus
    per-pattern guidance for each pattern in the response.

    Iterates canonical order (not pattern array order) for stable guidance.
    priority_switching guidance is selected dynamically based on retired_priorities data.

    Args:
        data: Backend response data dict

    Returns:
        Guidance string for LLM
    """
    reason = data.get("reason", "")

    if reason == "INSUFFICIENT_WEEKS":
        weeks_available = data.get("weeks_available", 0)
        return GUIDANCE_INSUFFICIENT_DATA_TEMPLATE.format(weeks=weeks_available)

    if reason == "NO_PATTERNS":
        return GUIDANCE_NO_PATTERNS

    # PATTERNS_FOUND: compose guidance from common + per-pattern blocks
    guidance_parts = [GUIDANCE_COMMON]

    # Collect which pattern_types are present in the data
    patterns = data.get("patterns", [])
    present_types = {p.get("pattern_type") for p in patterns}

    # Iterate canonical order (not pattern array order) for stable guidance
    for pattern_type in CANONICAL_PATTERN_ORDER:
        if pattern_type not in present_types:
            continue

        label = PATTERN_LABELS.get(pattern_type, pattern_type)

        # priority_switching is handled dynamically based on retired_priorities data
        if pattern_type == "priority_switching":
            switching_guidance = _get_switching_guidance(patterns)
            guidance_parts.append(
                f"When narrating {label} patterns: {switching_guidance}"
            )
        elif pattern_type in PATTERN_GUIDANCE:
            guidance_parts.append(
                f"When narrating {label} patterns: {PATTERN_GUIDANCE[pattern_type]}"
            )
        # Unknown pattern_types are skipped gracefully (forward-compatible)

    return "\n\n".join(guidance_parts)


# ============================================================================
# Handler
# ============================================================================

async def handle(
    user_id: str,
    correlation_id: str,
    arguments: dict,
) -> mcp_types.CallToolResult:
    """
    Get behavioral patterns from user's tracking history.

    Args:
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID
        arguments: Tool arguments (none required)

    Returns:
        CallToolResult with pattern data and assistant_guidance
    """
    logger.info(
        "tool.get_patterns.start",
        correlation_id=correlation_id,
        user_id=user_id,
    )

    # Call backend
    endpoint = "/api/priority-guardian/patterns"

    try:
        result = await backend_get(endpoint, user_id, correlation_id)
    except Exception as e:
        logger.error(
            "tool.get_patterns.backend_error",
            correlation_id=correlation_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        # Return generic error - don't expose internal details
        return mcp_types.CallToolResult(
            isError=True,
            content=[mcp_types.TextContent(
                type="text",
                text="Unable to analyze patterns at this time. Please try again.",
            )],
        )

    # Check for error response (backend returns 200 with success: false)
    if not result.get("success"):
        logger.warning(
            "tool.get_patterns.error_response",
            correlation_id=correlation_id,
        )
        # Return generic error - don't expose backend error codes
        return mcp_types.CallToolResult(
            isError=True,
            content=[mcp_types.TextContent(
                type="text",
                text="Unable to analyze patterns at this time. Please try again.",
            )],
        )

    # Extract data
    data = result.get("data", {})
    pattern_count = data.get("pattern_count", 0)
    weeks_available = data.get("weeks_available", 0)
    reason = data.get("reason", "")

    logger.info(
        "tool.get_patterns.success",
        correlation_id=correlation_id,
        user_id=user_id,
        pattern_count=pattern_count,
        weeks_available=weeks_available,
        reason=reason,
    )

    # Build human-readable summary text
    if reason == "INSUFFICIENT_WEEKS":
        text = f"Need more tracking data ({weeks_available} weeks available, 4 required)."
    elif reason == "NO_PATTERNS":
        text = "No notable patterns detected in your tracking history."
    else:
        text = f"Found {pattern_count} pattern(s) in your tracking history."

    # Build assistant guidance
    assistant_guidance = _build_assistant_guidance(data)

    # Build structured content
    # No widget - assistant_guidance as top-level key, no _meta.openai/outputTemplate
    structured_content = {
        "success": True,
        "data": data,
        "assistant_guidance": assistant_guidance,
    }

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=text,
        )],
        structuredContent=structured_content,
    )


# ============================================================================
# Tool Definition
# ============================================================================

GET_PATTERNS = ToolDefinition(
    name=NAME,
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=WIDGET_URI,  # None - no widget, LLM narrates
    handle=handle,
    read_only_hint=True,  # Pure read, no side effects
    destructive_hint=False,
    open_world_hint=False,  # No external API calls
    widget_accessible=False,  # No widget to call this
)
