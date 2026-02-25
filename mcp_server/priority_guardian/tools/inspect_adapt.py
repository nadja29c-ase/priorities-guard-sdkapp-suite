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

DESCRIPTION = """Record confirmed action steps from an inspect & adapt reflection.
Call this tool ONCE after facilitating the full reflection conversation.

CALL PRECONDITIONS — DO NOT CALL unless ALL are true:
- User has identified 1-3 specific behaviors/rituals/decisions (helped or hindered)
- User has named 1-3 concrete action steps for next week
- All verbatim fields contain the user's exact words
- User has explicitly confirmed the action steps

INSPECT & ADAPT FACILITATION — BINDING RULES:
When the user wants to reflect on their week, your default behavior is SUSPENDED.
You are a facilitator, not an advisor.

FORBIDDEN:
- Proposing new actions the user didn't imply
- Batching multiple questions
- Inferring what the user 'probably means'

REQUIRED FLOW:
1. Ask ONE opening question based on conversation context:
   - If user made progress: 'What specifically helped — a routine, a decision, a boundary you held?'
   - If priorities got less time: 'What was the biggest thing that got in the way — what actually happened?'
   - If mixed context: default to the obstacle lens — it yields more concrete adjustments.
   Ask. Stop. Wait.

2. Help user get specific. If vague ('I just focused more'), follow up:
   'What did that look like — what did you do differently?'
   If already specific, reflect back and confirm.
   Gather up to 3 confirmed behaviors/rituals/decisions.

3. Ask: 'Anything you want to keep as a habit next week, or do differently?'
   Wait for user's answer.

4. User names action steps (up to 3). Quality-check each:
   - Small — doable in one week without heroic effort
   - Close to existing habits — adjustments, not overhauls
   - Concrete — 'block 90 min for P1 Tuesday and Thursday mornings' not 'focus more on P1'
   Only rephrase user's described behaviors into commitments.
   Do NOT propose new actions the user didn't imply.
   Push back if steps are too big, too vague, or more than 3.

5. Confirm action steps with user. Then call this tool with all data.

After this tool returns successfully, briefly mention the user can schedule
these as calendar events if they want to lock in the time."""

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
                        "description": "Copy-paste the user's exact words describing this behavior, ritual, or decision. Must be non-empty. Do NOT paraphrase or infer — use the user's actual statement.",
                        "minLength": 1,
                    },
                    "description": {
                        "type": "string",
                        "description": "Derived from user_reflection_verbatim — normalized for clarity. Do not invent specificity the user did not state.",
                    },
                    "lens": {
                        "type": "string",
                        "enum": ["helped", "hindered"],
                        "description": "Whether this item helped progress or hindered it. Derived from the user's framing.",
                    },
                },
                "required": ["id", "user_reflection_verbatim", "description", "lens"],
            },
            "minItems": 1,
            "maxItems": 3,
        },
        "action_steps": {
            "type": "array",
            "description": "1-3 small, concrete action steps for next week. Each must link to a reflection item by id.",
            "items": {
                "type": "object",
                "properties": {
                    "user_action_verbatim": {
                        "type": "string",
                        "description": "Copy-paste the user's exact words for what they will do next week. Must be non-empty. Do NOT propose new actions the user didn't imply — only rephrase the user's described behaviors into next-week commitments.",
                        "minLength": 1,
                    },
                    "action": {
                        "type": "string",
                        "description": "Derived from user_action_verbatim — normalized for clarity. Must be concrete enough to do in one week. Close to user's existing habits — adjustment, not overhaul.",
                    },
                    "derived_from_id": {
                        "type": "string",
                        "description": "The 'id' of the reflection item this action connects to. Must exactly match an id from reflection_items (e.g., 'r1').",
                    },
                },
                "required": ["user_action_verbatim", "action", "derived_from_id"],
            },
            "minItems": 1,
            "maxItems": 3,
        },
        "user_confirmed": {
            "type": "boolean",
            "description": "Must be true — indicates the user explicitly confirmed these action steps. Do NOT set to true unless the user has seen and agreed to the specific actions.",
        },
    },
    "required": ["reflection_items", "action_steps", "user_confirmed"],
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

GUIDANCE_EMPTY_REFLECTION_DESCRIPTION = (
    "description is empty for one or more reflection items. "
    "Derive from user_reflection_verbatim — normalize for clarity but do not invent specificity."
)

GUIDANCE_EMPTY_ACTION_VERBATIM = (
    "user_action_verbatim is empty for one or more action steps. "
    "Do not call this tool until the user has stated what they will do next week. "
    "Only rephrase the user's described behaviors into next-week commitments. "
    "Do NOT propose new actions the user didn't imply. "
    "Store their exact words in user_action_verbatim."
)

GUIDANCE_EMPTY_ACTION = (
    "action is empty for one or more action steps. "
    "Derive from user_action_verbatim — normalize for clarity but do not invent specificity."
)

GUIDANCE_INVALID_DERIVED_FROM_ID = (
    "derived_from_id does not match any reflection item id. "
    "Each action step must reference a valid reflection item id (e.g., 'r1', 'r2', 'r3')."
)

GUIDANCE_USER_NOT_CONFIRMED = (
    "user_confirmed must be true. "
    "Present the action steps to the user and ask for explicit confirmation before calling again."
)


# ============================================================================
# Guidance Constants
# ============================================================================

GUIDANCE_COMMIT_SUCCESS = (
    "The user's action steps have been confirmed. "
    "Present a brief, clean summary of what they committed to. "
    "Mention they can add these to their calendar if they want to lock in the time. "
    "Do NOT add more advice. Do NOT expand on the steps. Keep it to 2-3 sentences max."
)

GUIDANCE_COMMIT_VALIDATION_ERROR = (
    "The commit could not be recorded. Tell the user what was missing and ask them to confirm again."
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


def _build_soft_block(instruction: str) -> mcp_types.CallToolResult:
    """Build a soft block response (conversational correction, not tool misuse)."""
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text="Action steps need user confirmation.",
        )],
        structuredContent={
            "success": False,
            "needs_confirmation": True,
            "assistant_guidance": instruction,
        },
        isError=False,
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

    Single-call tool: validate provenance → check confirmation → return success.

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
    user_confirmed = arguments.get("user_confirmed", False)

    # -------------------------------------------------------------------------
    # A. Provenance validation (behavioral gate) → isError: true
    # -------------------------------------------------------------------------

    # Check reflection_items present and non-empty
    if not reflection_items_raw or len(reflection_items_raw) == 0:
        logger.info(
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
            logger.info(
                "tool.inspect_adapt.provenance_failed",
                correlation_id=correlation_id,
                field="user_reflection_verbatim",
                index=i,
            )
            return _build_provenance_error("empty_reflection_verbatim", GUIDANCE_EMPTY_REFLECTION_VERBATIM)

        # Check description
        description = item.get("description", "")
        if not description or not description.strip():
            logger.info(
                "tool.inspect_adapt.provenance_failed",
                correlation_id=correlation_id,
                field="description",
                index=i,
            )
            return _build_provenance_error("empty_reflection_description", GUIDANCE_EMPTY_REFLECTION_DESCRIPTION)

        # Check lens
        lens = item.get("lens")
        if lens not in ("helped", "hindered"):
            raise ToolUsageError("lens must be 'helped' or 'hindered'.")

    # Check action_steps present and non-empty
    if not action_steps_raw or len(action_steps_raw) == 0:
        logger.info(
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
            logger.info(
                "tool.inspect_adapt.provenance_failed",
                correlation_id=correlation_id,
                field="user_action_verbatim",
                index=i,
            )
            return _build_provenance_error("empty_action_verbatim", GUIDANCE_EMPTY_ACTION_VERBATIM)

        # Check action
        action = step.get("action", "")
        if not action or not action.strip():
            logger.info(
                "tool.inspect_adapt.provenance_failed",
                correlation_id=correlation_id,
                field="action",
                index=i,
            )
            return _build_provenance_error("empty_action", GUIDANCE_EMPTY_ACTION)

        # Check derived_from_id references a valid reflection item
        derived_from_id = step.get("derived_from_id", "")
        if derived_from_id not in reflection_ids:
            logger.info(
                "tool.inspect_adapt.provenance_failed",
                correlation_id=correlation_id,
                field="derived_from_id",
                index=i,
                value=derived_from_id,
                valid_ids=list(reflection_ids),
            )
            return _build_provenance_error("invalid_derived_from_id", GUIDANCE_INVALID_DERIVED_FROM_ID)

    # -------------------------------------------------------------------------
    # B. Conversational guardrail (soft block) → isError: false
    # -------------------------------------------------------------------------

    if not user_confirmed:
        logger.info(
            "tool.inspect_adapt.soft_block",
            correlation_id=correlation_id,
            reason="user_not_confirmed",
        )
        return _build_soft_block(GUIDANCE_USER_NOT_CONFIRMED)

    # -------------------------------------------------------------------------
    # C. Success path
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
