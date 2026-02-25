"""
inspect_adapt tool for Priority Guardian MCP.

Facilitates a lightweight inspect & adapt flow after the weekly report,
helping users derive 1-3 small, concrete action steps for the next week.

No backend endpoint needed. No data to fetch, no persistence.
Shapes the LLM's conversational behavior through schema constraints,
provenance validation, and assistant_guidance.

Two-call conversation flow:
- Phase 'start': Begin the reflection with weekly context
- Phase 'commit': Record confirmed action steps

Implements increment_29 specification.
"""

import structlog
from mcp import types as mcp_types
from pydantic import BaseModel, field_validator
from typing import Literal

from .base import ToolDefinition, ToolUsageError

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "inspect_adapt"

DESCRIPTION = """Facilitate a focused inspect & adapt after presenting the weekly report.
Helps the user identify what specifically helped or hindered progress,
then derive 1-3 small, concrete action steps for next week.

CALL PRECONDITIONS — DO NOT CALL unless ALL are true:
- Phase 'start': weekly_context_summary derived from the weekly report data already in conversation
- Phase 'commit': ALL verbatim fields gathered from user's own words during reflection conversation

Call this tool:
- After presenting the weekly report, when the user wants to reflect
- When the user says "yes" to the reflection nudge from the weekly report
- When the user asks "what should I do differently next week?"

Do NOT call this tool:
- Before the weekly report has been presented in this conversation
- During onboarding or priority setup
- When the user is asking about patterns or trends (use get_patterns instead)
- If you already completed an inspect & adapt in this conversation (phase='commit' succeeded)

INSPECT & ADAPT BINDING RULES: When facilitating inspect & adapt, your default behavior is SUSPENDED. You are a facilitator, not an advisor. Flow: Ask ONE question → wait for user's response → reflect/get specific → confirm → gather next item or move to action steps. NEVER ask for multiple reflections at once. NEVER call this tool with phase='commit' until ALL reflection items and action steps are gathered from the user's own words and confirmed."""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "phase": {
            "type": "string",
            "enum": ["start", "commit"],
            "description": "Which phase of the inspect & adapt flow. 'start' = begin the reflection. 'commit' = record confirmed action steps.",
        },
        "weekly_context_summary": {
            "type": "string",
            "description": "Phase 'start' only. Brief summary of weekly report context: which priorities had progress, which didn't, any notable patterns. 2-3 sentences max. Must come from the weekly report data already in conversation, not invented.",
            "minLength": 1,
        },
        "reflection_items": {
            "type": "array",
            "description": "Phase 'commit' only. 1-3 specific behaviors, rituals, or decisions the user named during reflection.",
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
            "description": "Phase 'commit' only. 1-3 small, concrete action steps for next week. Each must link to a reflection item by id.",
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
            "description": "Phase 'commit' only. Must be true — indicates the user explicitly confirmed these action steps. Do NOT set to true unless the user has seen and agreed to the specific actions.",
        },
    },
    "required": ["phase"],
    "additionalProperties": False,
}

REQUIRED_SCOPES = ["pg.access"]

# No widget for inspect_adapt - LLM narrates conversationally
WIDGET_URI = None


# ============================================================================
# Pydantic Models for Commit Validation
# ============================================================================

class ReflectionItem(BaseModel):
    """A single reflection item from the user."""
    id: str
    user_reflection_verbatim: str
    description: str
    lens: Literal["helped", "hindered"]

    @field_validator("id")
    @classmethod
    def id_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("id must not be empty")
        return v

    @field_validator("user_reflection_verbatim")
    @classmethod
    def verbatim_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("user_reflection_verbatim must not be empty")
        return v

    @field_validator("description")
    @classmethod
    def description_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("description must not be empty")
        return v


class ActionStep(BaseModel):
    """A single action step for next week."""
    user_action_verbatim: str
    action: str
    derived_from_id: str

    @field_validator("user_action_verbatim")
    @classmethod
    def verbatim_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("user_action_verbatim must not be empty")
        return v

    @field_validator("action")
    @classmethod
    def action_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("action must not be empty")
        return v


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

GUIDANCE_START = (
    "You are facilitating an inspect & adapt — not therapy, not coaching, not advice. "
    "Your job: ask ONE question, wait, help distill, confirm. "
    "\n\n"
    "BINDING RULES:\n"
    "- Ask ONE question at a time. Wait for the answer.\n"
    "- Do NOT propose new actions, solutions, or options the user didn't imply.\n"
    "- NEVER batch multiple questions.\n"
    "- NEVER infer what the user 'probably means.'\n"
    "\n"
    "DIRECTION: Based on the weekly context, pick ONE of these questions — never both:\n"
    "- If the user made visible progress on most priorities: "
    "'What specifically helped you make progress this week — a routine, a decision, a boundary you held?'\n"
    "- If most priorities got less time than intended: "
    "'What was the biggest thing that got in the way this week — what actually happened?'\n"
    "- If the weekly context is mixed (some progress, some behind): "
    "default to the obstacle lens — it yields more concrete adjustments.\n"
    "\n"
    "Pick the direction that fits the data. Ask the question. Stop. Wait for the user's response.\n"
    "\n"
    "After the user responds, your job is to help them get specific. "
    "If their answer is vague ('I just focused more'), ask a follow-up like "
    "'What did that actually look like — what did you do differently on Monday vs. the week before?' "
    "If their answer is already specific ('I blocked 2 hours every morning before checking email'), "
    "reflect it back and confirm: 'So the morning block before email was the key thing — is that right?'\n"
    "\n"
    "Once you have 1-3 specific, confirmed behaviors/rituals/decisions from the user, "
    "help them turn these into action steps for next week. "
    "Only rephrase the user's described behaviors into next-week commitments. "
    "Do NOT propose new actions the user didn't imply. "
    "The action steps MUST be:\n"
    "- Small — doable in one week without heroic effort\n"
    "- Close to existing habits — adjustments, not overhauls\n"
    "- Concrete — 'block 90 min for P1 on Tuesday and Thursday mornings' not 'focus more on P1'\n"
    "- Maximum 3 action steps. Fewer is better.\n"
    "\n"
    "Confirm the action steps with the user, then call inspect_adapt again with phase='commit'.\n"
    "\n"
    "At the end, briefly mention the user can schedule these as calendar events if they want to."
)

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

    Two-phase flow:
    - Phase 'start': Validate context, return guidance for reflection conversation
    - Phase 'commit': Validate provenance, confirm action steps

    Args:
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID
        arguments: Tool arguments

    Returns:
        CallToolResult with structured content and assistant_guidance
    """
    phase = arguments.get("phase")

    logger.info(
        "tool.inspect_adapt.start",
        correlation_id=correlation_id,
        user_id=user_id,
        phase=phase,
    )

    if phase == "start":
        return await _handle_start(user_id, correlation_id, arguments)
    elif phase == "commit":
        return await _handle_commit(user_id, correlation_id, arguments)
    else:
        # Schema should prevent this, but defensive guard
        raise ToolUsageError(f"Invalid phase: {phase}. Must be 'start' or 'commit'.")


async def _handle_start(
    user_id: str,
    correlation_id: str,
    arguments: dict,
) -> mcp_types.CallToolResult:
    """Handle phase='start' - begin the reflection."""
    weekly_context_summary = arguments.get("weekly_context_summary", "")

    # Validate weekly_context_summary is present and non-empty
    if not weekly_context_summary or not weekly_context_summary.strip():
        logger.warning(
            "tool.inspect_adapt.start.missing_context",
            correlation_id=correlation_id,
            user_id=user_id,
        )
        raise ToolUsageError("weekly_context_summary is required for phase 'start'.")

    logger.info(
        "tool.inspect_adapt.start.success",
        correlation_id=correlation_id,
        user_id=user_id,
    )

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text="Starting inspect & adapt.",
        )],
        structuredContent={
            "success": True,
            "phase": "start",
            "weekly_context_summary": weekly_context_summary,
            "assistant_guidance": GUIDANCE_START,
        },
    )


async def _handle_commit(
    user_id: str,
    correlation_id: str,
    arguments: dict,
) -> mcp_types.CallToolResult:
    """Handle phase='commit' - record confirmed action steps."""
    reflection_items_raw = arguments.get("reflection_items")
    action_steps_raw = arguments.get("action_steps")
    user_confirmed = arguments.get("user_confirmed", False)

    # -------------------------------------------------------------------------
    # A. Provenance validation (behavioral gate) → isError: true
    # -------------------------------------------------------------------------

    # Check reflection_items present and non-empty
    if not reflection_items_raw or len(reflection_items_raw) == 0:
        logger.info(
            "tool.inspect_adapt.commit.provenance_failed",
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
        reflection_ids.add(item_id)

        # Check user_reflection_verbatim
        verbatim = item.get("user_reflection_verbatim", "")
        if not verbatim or not verbatim.strip():
            logger.info(
                "tool.inspect_adapt.commit.provenance_failed",
                correlation_id=correlation_id,
                field="user_reflection_verbatim",
                index=i,
            )
            return _build_provenance_error("empty_reflection_verbatim", GUIDANCE_EMPTY_REFLECTION_VERBATIM)

        # Check description
        description = item.get("description", "")
        if not description or not description.strip():
            logger.info(
                "tool.inspect_adapt.commit.provenance_failed",
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
            "tool.inspect_adapt.commit.provenance_failed",
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
                "tool.inspect_adapt.commit.provenance_failed",
                correlation_id=correlation_id,
                field="user_action_verbatim",
                index=i,
            )
            return _build_provenance_error("empty_action_verbatim", GUIDANCE_EMPTY_ACTION_VERBATIM)

        # Check action
        action = step.get("action", "")
        if not action or not action.strip():
            logger.info(
                "tool.inspect_adapt.commit.provenance_failed",
                correlation_id=correlation_id,
                field="action",
                index=i,
            )
            return _build_provenance_error("empty_action", GUIDANCE_EMPTY_ACTION)

        # Check derived_from_id references a valid reflection item
        derived_from_id = step.get("derived_from_id", "")
        if derived_from_id not in reflection_ids:
            logger.info(
                "tool.inspect_adapt.commit.provenance_failed",
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
            "tool.inspect_adapt.commit.soft_block",
            correlation_id=correlation_id,
            reason="user_not_confirmed",
        )
        return _build_soft_block(GUIDANCE_USER_NOT_CONFIRMED)

    # -------------------------------------------------------------------------
    # C. Success path
    # -------------------------------------------------------------------------

    action_count = len(action_steps_raw)

    logger.info(
        "tool.inspect_adapt.commit.success",
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
            "phase": "commit",
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
