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
from .base import ToolDefinition, ToolUsageError

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "get_patterns"

DESCRIPTION = (
    "Returns behavioral patterns detected from user's priority tracking history. "
    "Patterns include consistency streaks, low-investment priorities, priority switching frequency, "
    "and priority protection under calendar pressure. Requires at least 4 weeks of tracking data.\n\n"
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
    "The dashboard already shows the streak count — do not just restate it. "
    "Look at the actual_hours vs target_hours across the streak weeks in the data. "
    "If some weeks fell significantly below target but the user still logged time, "
    "acknowledge that showing up consistently matters more than hitting the target every week. "
    "If hours are steady, note the reliability. "
    "If the streak is 4+ weeks, note that this has moved past initial motivation into habit territory — "
    "the weeks where hours were lowest are actually the most telling because the user kept going anyway. "
    "Keep it to 2-3 sentences max."
)

GUIDANCE_ABANDONED_PRIORITY = (
    "State the observed average hours neutrally. "
    "Ask what the user wants to do about it — do not prescribe action. "
    "Do not judge. Do not say \"you should retire this\" or \"you're neglecting this.\" "
    "Keep it to 1-2 sentences plus a question."
)

GUIDANCE_PRIORITY_SWITCHING = (
    "Present both interpretations: this could be healthy pivoting and adapting, "
    "or it could signal difficulty committing. "
    "Ask what's been driving the changes. "
    "Do not lean toward either interpretation — present them equally. "
    "Keep it to 2-3 sentences."
)

GUIDANCE_PRIORITY_PROTECTION = (
    "Acknowledge warmly that the user protected this priority's time despite growing calendar pressure. "
    "Reference the observed numbers: priority hours stayed at ~Xh/week while total calendar grew Y%. "
    "This is a positive signal — the user is defending what matters to them. "
    "Keep it to 1-2 sentences."
)

# Mapping from pattern_type to guidance constant
PATTERN_GUIDANCE = {
    "consistency_streak": GUIDANCE_CONSISTENCY_STREAK,
    "abandoned_priority": GUIDANCE_ABANDONED_PRIORITY,
    "priority_switching": GUIDANCE_PRIORITY_SWITCHING,
    "priority_protection": GUIDANCE_PRIORITY_PROTECTION,
}

# Human-readable labels for pattern types
PATTERN_LABELS = {
    "consistency_streak": "Consistency Streak",
    "abandoned_priority": "Low-Investment Priority",
    "priority_switching": "Priority Switching",
    "priority_protection": "Priority Protection",
}

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

def _build_assistant_guidance(data: dict) -> str:
    """
    Build assistant_guidance based on response state.

    Uses 'reason' enum from backend to select appropriate guidance.
    For PATTERNS_FOUND, composes guidance from GUIDANCE_COMMON plus
    per-pattern guidance for each pattern in the response.

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

    patterns = data.get("patterns", [])
    for pattern in patterns:
        pattern_type = pattern.get("pattern_type", "")
        if pattern_type in PATTERN_GUIDANCE:
            label = PATTERN_LABELS.get(pattern_type, pattern_type)
            guidance_parts.append(f"[{label}]: {PATTERN_GUIDANCE[pattern_type]}")
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
