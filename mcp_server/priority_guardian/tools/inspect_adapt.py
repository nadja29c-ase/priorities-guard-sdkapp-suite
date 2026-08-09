"""
inspect_adapt tool for Priority Guardian MCP.

Records confirmed action steps from an inspect & adapt reflection.
Single-call tool — LLM facilitates the full reflection conversation,
then calls this tool once to commit the action steps.

No backend endpoint needed. No data to fetch, no persistence.
Shapes the LLM's conversational behavior through schema constraints,
provenance validation, and assistant_guidance.

Implements increment_30 specification.
"""

import structlog
from mcp import types as mcp_types

from .base import ToolDefinition, ToolUsageError

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "inspect_adapt"

DESCRIPTION = """Guide the user through an inspect & adapt reflection and confirm their action steps.
Call this tool ONCE after facilitating the full reflection conversation.

CALL PRECONDITIONS — DO NOT CALL unless ALL are true:
- user_reflection_verbatim: non-empty, user's exact words for each reflection item
- user_action_verbatim: non-empty, user's exact words for each action step
- derived_from_id: each action step links to a reflection item

Call this tool:
- When user wants to reflect on their week, says "reflect", "reflection", "what worked", "what didn't work", "inspect and adapt"
- When user says "yes" to the reflection nudge from the weekly report
- When user asks "what should I do differently next week?"

INSPECT & ADAPT PROTOCOL: This reflection follows a structured facilitation protocol rather than an open-ended coaching conversation. It intentionally does not diagnose root causes, teach coaching frameworks, probe strategic alignment, or propose actions the user did not imply. The protocol asks ONE question at a time. After the user answers, continue to the next step of the protocol rather than extending the discussion with additional probing. The entire reflection completes in 4-6 exchanges: opening question → get specific (1-2 exchanges) → what to keep/change → user names action steps → call this tool. NEVER exceed 6 exchanges before calling this tool.

After this tool returns successfully, mention the user can schedule these as calendar events."""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "reflection_items": {
            "type": "array",
            "description": "1-3 specific behaviors, rituals, or decisions the user named during reflection.",
            "items": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Stable identifier for this reflection item. Use 'r1', 'r2', 'r3'. Referenced by action_steps.derived_from_id.",
                    },
                    "user_reflection_verbatim": {
                        "type": "string",
                        "description": (
                            "User's exact words. Must be non-empty. "
                            "To gather: pick ONE opening question based on context — "
                            "progress visible: 'What specifically helped — a routine, a decision, a boundary you held?' "
                            "priorities behind: 'What got in the way — what actually happened?' "
                            "Mixed: default to obstacle lens. "
                            "This reflection is procedural rather than conversational — it captures "
                            "what the user said rather than advising on it. "
                            "If vague, ONE follow-up to get specific. If specific, move forward immediately."
                        ),
                        "minLength": 1,
                    },
                },
                "required": ["id", "user_reflection_verbatim"],
                "additionalProperties": False,
            },
            "minItems": 1,
            "maxItems": 3,
        },
        "action_steps": {
            "type": "array",
            "description": "1-3 action steps for next week. Each must link to a reflection item by id.",
            "items": {
                "type": "object",
                "properties": {
                    "user_action_verbatim": {
                        "type": "string",
                        "description": (
                            "User's exact words for what they will do next week. Must be non-empty. "
                            "To gather: ask what to keep as habit or do differently. "
                            "The protocol accepts the user's answer as given rather than refining, "
                            "expanding, or probing further. "
                            "Only rephrase into commitment if needed for clarity."
                        ),
                        "minLength": 1,
                    },
                    "derived_from_id": {
                        "type": "string",
                        "description": "The 'id' of the reflection item this action connects to (e.g., 'r1').",
                    },
                },
                "required": ["user_action_verbatim", "derived_from_id"],
                "additionalProperties": False,
            },
            "minItems": 1,
            "maxItems": 3,
        },
    },
    "required": ["reflection_items", "action_steps"],
    "additionalProperties": False,
}

REQUIRED_SCOPES = ["pg.access"]

# No widget for inspect_adapt - LLM narrates conversationally
WIDGET_URI = None


# ============================================================================
# Provenance Guidance Messages
# ============================================================================

GUIDANCE_EMPTY_REFLECTION_VERBATIM = (
    "user_reflection_verbatim is empty for one or more reflection items. "
    "Do not call this tool until the user has stated what helped or hindered their progress. "
    "Ask ONE question and wait for their answer. Store their exact words in user_reflection_verbatim."
)

GUIDANCE_EMPTY_ACTION_VERBATIM = (
    "user_action_verbatim is empty for one or more action steps. "
    "Do not call this tool until the user has stated what they will do next week. "
    "Store their exact words in user_action_verbatim."
)

GUIDANCE_INVALID_DERIVED_FROM_ID = (
    "derived_from_id does not match any reflection item id. "
    "Each action step must reference a valid reflection item id (e.g., 'r1', 'r2', 'r3')."
)


# ============================================================================
# Guidance Constants
# ============================================================================

GUIDANCE_COMMIT_SUCCESS = (
    "The user's action steps have been confirmed. "
    "Present a brief summary of what they committed to. "
    "Mention they can add these to their calendar if they want to lock in the time. "
    "Do NOT add advice, expand on the steps, or probe further. 2-3 sentences max."
)


# ============================================================================
# Helper Functions
# ============================================================================

def _build_provenance_error(error_code: str, instruction: str) -> mcp_types.CallToolResult:
    """Build a structured error response for provenance validation failure."""
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Provenance validation failed: {error_code}",
        )],
        structuredContent={
            "success": False,
            "error": error_code,
            "assistant_guidance": {
                "action": "ASK_CLARIFYING",
                "instruction": instruction,
            },
        },
        isError=True,
    )


# ============================================================================
# Handler
# ============================================================================

async def handle(
    user_id: str,
    correlation_id: str,
    arguments: dict,
) -> mcp_types.CallToolResult:
    """
    Handle inspect_adapt tool calls.

    Single-call tool: validate provenance → return success.

    Args:
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID
        arguments: Tool arguments

    Returns:
        CallToolResult with structured content and assistant_guidance
    """
    logger.info(
        "tool.inspect_adapt.start",
        correlation_id=correlation_id,
        user_id=user_id,
    )

    reflection_items_raw = arguments.get("reflection_items")
    action_steps_raw = arguments.get("action_steps")

    # -------------------------------------------------------------------------
    # Provenance validation (behavioral gate) → isError: true
    # -------------------------------------------------------------------------

    # Check reflection_items present and non-empty
    if not reflection_items_raw or len(reflection_items_raw) == 0:
        logger.warning(
            "tool.inspect_adapt.provenance_failed",
            correlation_id=correlation_id,
            field="reflection_items",
            reason="missing_or_empty",
        )
        return _build_provenance_error("empty_reflection_verbatim", GUIDANCE_EMPTY_REFLECTION_VERBATIM)

    # Defensive guard: max 3 reflection items
    if len(reflection_items_raw) > 3:
        raise ToolUsageError("reflection_items must contain 1-3 items.")

    # Validate each reflection item
    reflection_ids = set()
    for i, item in enumerate(reflection_items_raw):
        # Check id
        item_id = item.get("id", "")
        if not item_id or not item_id.strip():
            raise ToolUsageError("Each reflection item must have an 'id'.")

        # Check for duplicate id
        if item_id in reflection_ids:
            raise ToolUsageError(f"Duplicate reflection item id: '{item_id}'.")
        reflection_ids.add(item_id)

        # Check user_reflection_verbatim
        verbatim = item.get("user_reflection_verbatim", "")
        if not verbatim or not verbatim.strip():
            logger.warning(
                "tool.inspect_adapt.provenance_failed",
                correlation_id=correlation_id,
                field="user_reflection_verbatim",
                index=i,
            )
            return _build_provenance_error("empty_reflection_verbatim", GUIDANCE_EMPTY_REFLECTION_VERBATIM)

    # Check action_steps present and non-empty
    if not action_steps_raw or len(action_steps_raw) == 0:
        logger.warning(
            "tool.inspect_adapt.provenance_failed",
            correlation_id=correlation_id,
            field="action_steps",
            reason="missing_or_empty",
        )
        return _build_provenance_error("empty_action_verbatim", GUIDANCE_EMPTY_ACTION_VERBATIM)

    # Defensive guard: max 3 action steps
    if len(action_steps_raw) > 3:
        raise ToolUsageError("action_steps must contain 1-3 items.")

    # Validate each action step
    for i, step in enumerate(action_steps_raw):
        # Check user_action_verbatim
        verbatim = step.get("user_action_verbatim", "")
        if not verbatim or not verbatim.strip():
            logger.warning(
                "tool.inspect_adapt.provenance_failed",
                correlation_id=correlation_id,
                field="user_action_verbatim",
                index=i,
            )
            return _build_provenance_error("empty_action_verbatim", GUIDANCE_EMPTY_ACTION_VERBATIM)

        # Check derived_from_id references a valid reflection item
        derived_from_id = step.get("derived_from_id", "")
        if derived_from_id not in reflection_ids:
            logger.warning(
                "tool.inspect_adapt.provenance_failed",
                correlation_id=correlation_id,
                field="derived_from_id",
                index=i,
                value=derived_from_id,
                valid_ids=list(reflection_ids),
            )
            return _build_provenance_error("invalid_derived_from_id", GUIDANCE_INVALID_DERIVED_FROM_ID)

    # -------------------------------------------------------------------------
    # Success path
    # -------------------------------------------------------------------------

    action_count = len(action_steps_raw)

    logger.info(
        "tool.inspect_adapt.success",
        correlation_id=correlation_id,
        user_id=user_id,
        reflection_count=len(reflection_items_raw),
        action_count=action_count,
    )

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Inspect & adapt complete. {action_count} action step(s) confirmed.",
        )],
        structuredContent={
            "success": True,
            "completed": True,
            "reflection_items": reflection_items_raw,
            "action_steps": action_steps_raw,
            "assistant_guidance": GUIDANCE_COMMIT_SUCCESS,
        },
    )


# ============================================================================
# Tool Definition
# ============================================================================

INSPECT_ADAPT = ToolDefinition(
    name=NAME,
    title="Inspect Adapt",
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=None,
    handle=handle,
    read_only_hint=True,   # No persistence, pure conversational shaping
    destructive_hint=False,
    open_world_hint=False,  # No external API calls
    widget_accessible=False,  # No widget to call this
)
