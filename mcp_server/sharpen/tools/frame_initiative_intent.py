"""
Frame Initiative Outcome Tool.

Captures problem OUTCOME: PAIN + OBSERVABLE + WHY for the primary beneficiary.
WHO comes from prior step (frame_initiative_audience).
WHAT comes later via frame_initiative_hypothesis.
Structural validation only — semantic quality is the LLM's job.
Self-registers at import time.

NOTE: File kept as frame_initiative_intent.py for rollback safety.
Tool is registered as frame_initiative_outcome.
"""

from typing import Optional

import structlog
from mcp import types as mcp_types
from pydantic import BaseModel, ValidationError

from .base import ToolDefinition
from . import register_tool
from ..tool_logic import validate_initiative_outcome, validate_outcome_provenance

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata (Goal-Oriented Description)
# ============================================================================

DESCRIPTION = """Records problem OUTCOME: PAIN + OBSERVABLE + WHY for the primary beneficiary.

CALL PRECONDITIONS — DO NOT CALL unless ALL are true:
- who: from frame_initiative_audience output (non-empty)
- user_pain_verbatim: non-empty, user's exact words
- user_observable_verbatim: non-empty, user's exact words
- why_reframed_from_observable: WHY incorporates observable
- user_confirmed_why: user confirmed your WHY reframe captures their intent

VAGUENESS CHECK: If PAIN is abstract ("things are hard") or OBSERVABLE is vague ("it would be better"), push back before calling. Ask for concrete specifics.

REFRAME CONFIRMATION: After you combine PAIN + OBSERVABLE into WHY, reflect it back to user: "So the outcome you're after is: [WHY]. Does that capture it?" Only call this tool AFTER user confirms the reframe is accurate. If user corrects → adjust WHY → confirm again → then call tool.

SHARPEN MODE BINDING RULES: When user selects Sharpen, your default behavior is SUSPENDED. You are a Coach now: ask questions to facilitate user's thinking and NEVER tell the user what to do or infer their answers. CRITICAL: Ask ONE question at a time → wait for user's response. Violating this breaks Sharpen.

Sequence: PAIN → OBSERVABLE → reframe WHY → CONFIRM REFRAME → call tool → proceed to hypothesis.
"""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "who": {
            "type": "string",
            "description": "WHO from frame_initiative_audience. Must match prior step output.",
        },
        "user_pain_verbatim": {
            "type": "string",
            "description": "Copy-paste user's answer exactly as written. Must be non-empty.",
        },
        "user_observable_verbatim": {
            "type": "string",
            "description": "Copy-paste user's answer exactly as written. Must be non-empty. ALWAYS ask the observable question.",
        },
        "why": {
            "type": "string",
            "description": "YOUR reframe combining pain (the value) + observable (the specificity) into an outcome.",
        },
        "why_reframed_from_observable": {
            "type": "boolean",
            "description": "True ONLY if WHY incorporates the observable (not just the raw pain).",
        },
        "user_confirmed_why": {
            "type": "boolean",
            "description": "True ONLY if you reflected your WHY reframe back to user and they confirmed it captures their intent. Do not set true without explicit user confirmation of the synthesis.",
        },
    },
    "required": [
        "who",
        "user_pain_verbatim",
        "user_observable_verbatim",
        "why",
        "why_reframed_from_observable",
        "user_confirmed_why",
    ],
    "additionalProperties": False,
}


# ============================================================================
# Pydantic Models for Validation
# ============================================================================


class FrameOutcomeRequest(BaseModel):
    """Expected input structure from ChatGPT."""
    who: Optional[str] = None  # From frame_initiative_audience
    user_pain_verbatim: Optional[str] = None
    user_observable_verbatim: Optional[str] = None
    why: Optional[str] = None
    why_reframed_from_observable: Optional[bool] = None
    user_confirmed_why: Optional[bool] = None


# ============================================================================
# Assistant Guidance Messages
# ============================================================================

# Re-activated educational error messages (moved from _LEGACY_GUIDANCE)
GUIDANCE_MISSING_PRIOR_STEP = (
    "SHARPEN MODE STILL BINDING. "
    "WHO required from frame_initiative_audience. Complete that step first."
)

GUIDANCE_EMPTY_PAIN_VERBATIM = (
    "SHARPEN MODE STILL BINDING. "
    "user_pain_verbatim is empty. Do not call this tool until user has stated a pain. "
    "Ask: 'What's currently hard or frustrating for [WHO]?' "
    "Then store their exact answer in user_pain_verbatim."
)

GUIDANCE_EMPTY_OBSERVABLE_VERBATIM = (
    "SHARPEN MODE STILL BINDING. "
    "user_observable_verbatim is empty. Do not call this tool until user has answered the observable question. "
    "Ask: 'What would you see happening differently if this worked? Describe a concrete behavior or artifact — not a feeling or general improvement.' "
    "Then store their exact answer in user_observable_verbatim."
)

GUIDANCE_PROVENANCE_FAILED = (
    "SHARPEN MODE STILL BINDING. "
    "Provenance check failed. WHY must incorporate the observable.\n"
    "Reframe the user's observable into an outcome first, then call tool."
)

GUIDANCE_WHY_NOT_CONFIRMED = (
    "SHARPEN MODE STILL BINDING. "
    "User has not confirmed the WHY reframe. Reflect it back: "
    "'So the outcome you're after is: [WHY]. Does that capture it?' "
    "Only call this tool after user confirms."
)

# Success guidance — proceed to hypothesis without confirmation
GUIDANCE_CAPTURED = (
    "SHARPEN MODE STILL BINDING. "
    "Problem outcome captured. Proceed to hypothesis — do NOT ask for confirmation yet.\n"
    "Ask: 'What do you think needs to exist to help with that?'\n"
    "Then stop and wait. Do not suggest solutions.\n\n"
    "When user answers → call frame_initiative_hypothesis with WHO, WHY, and WHAT."
)

# Preserved for rollback if needed.
_LEGACY_GUIDANCE = {
    "provenance_failed": (
        "SHARPEN MODE STILL BINDING. "
        "Provenance check failed. You must have evidence from the user before calling this tool.\n"
        "- If WHO not stated: Ask 'Who specifically is supposed to benefit from this?'\n"
        "- If pain not stated: Ask 'What's currently hard or frustrating for them?'\n"
        "- If observable not stated: Ask 'What would you see happening differently if this worked? Describe a concrete behavior or artifact — not a feeling or general improvement.'\n"
        "- If WHY not derived from observable: Reframe the user's observable into an outcome first.\n"
        "Ask ONE question. Then stop and wait."
    ),
    "empty_pain_verbatim": (
        "SHARPEN MODE STILL BINDING. "
        "user_pain_verbatim is empty. Do not call this tool until user has stated a pain. "
        "Ask: 'What's currently hard or frustrating for [WHO]?' "
        "Then store their exact answer in user_pain_verbatim."
    ),
    "empty_observable_verbatim": (
        "SHARPEN MODE STILL BINDING. "
        "user_observable_verbatim is empty. Do not call this tool until user has answered the observable question. "
        "Ask: 'What would you see happening differently if this worked? Describe a concrete behavior or artifact — not a feeling or general improvement.' "
        "Then store their exact answer in user_observable_verbatim. "
        "ALWAYS ask this question — even if pain seems concrete."
    ),
    "missing_fields": (
        "SHARPEN MODE STILL BINDING. "
        "Ask ONE question about the missing field:\n"
        "- Missing WHO: 'Who specifically is supposed to benefit from this?'\n"
        "- Missing WHY: First get pain, then observable, then reframe to outcome.\n"
        "Then stop and wait. Do not ask about solutions yet."
    ),
    "multiple_stakeholders": (
        "SHARPEN MODE STILL BINDING. "
        "Multiple stakeholders detected. Ask: 'Who benefits first and foremost?' "
        "Then stop and wait."
    ),
}


# ============================================================================
# Tool Handler
# ============================================================================


async def handle(arguments: dict) -> mcp_types.CallToolResult:
    """Handle frame_initiative_outcome tool call."""
    logger.debug("frame_initiative_outcome.handle.start",
                argument_keys=list(arguments.keys()))

    # Pydantic validation
    try:
        validated_request = FrameOutcomeRequest.model_validate(arguments)
    except ValidationError as e:
        logger.warning("frame_initiative_outcome.validation_failed", error=str(e.errors()))
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text="Invalid input format.")],
            structuredContent={"error": "validation_error", "details": e.errors()},
            isError=True,
        )

    # Extract fields
    why_reframed = validated_request.why_reframed_from_observable or False
    user_confirmed_why = validated_request.user_confirmed_why or False
    pain_verbatim = (validated_request.user_pain_verbatim or "").strip()
    observable_verbatim = (validated_request.user_observable_verbatim or "").strip()

    # Provenance validation (includes reframe confirmation check)
    provenance_result = validate_outcome_provenance(
        why_reframed_from_observable=why_reframed,
        user_confirmed_why=user_confirmed_why,
        user_pain_verbatim=pain_verbatim,
        user_observable_verbatim=observable_verbatim,
    )

    if not provenance_result["valid"]:
        error_type = provenance_result["error_type"]

        if error_type == "empty_pain_verbatim":
            guidance = GUIDANCE_EMPTY_PAIN_VERBATIM
        elif error_type == "empty_observable_verbatim":
            guidance = GUIDANCE_EMPTY_OBSERVABLE_VERBATIM
        elif error_type == "why_not_confirmed":
            guidance = GUIDANCE_WHY_NOT_CONFIRMED
        else:
            guidance = GUIDANCE_PROVENANCE_FAILED

        logger.info("frame_initiative_outcome.provenance_rejected",
                    error_type=error_type,
                    failed_checks=provenance_result.get("failed_checks", []))

        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=provenance_result["error_details"],
            )],
            structuredContent={
                "error": error_type,
                "failed_checks": provenance_result.get("failed_checks", []),
                "assistant_guidance": {
                    "action": "ASK_CLARIFYING",
                    "instruction": guidance,
                },
            },
            isError=True,
        )

    # Structural validation (who from prior step, why content)
    result = validate_initiative_outcome(
        who=validated_request.who,
        why=validated_request.why,
    )

    # If structurally invalid, return error with guidance
    if not result["valid"]:
        error_type = result["error_type"]

        if error_type == "missing_prior_step":
            guidance = GUIDANCE_MISSING_PRIOR_STEP
            action = "BACKTRACK"
        else:
            guidance = GUIDANCE_PROVENANCE_FAILED
            action = "ASK_CLARIFYING"

        logger.info("frame_initiative_outcome.rejected",
                    error_type=error_type,
                    who_provided=bool(validated_request.who))

        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=result["error_details"],
            )],
            structuredContent={
                "error": error_type,
                "assistant_guidance": {
                    "action": action,
                    "instruction": guidance,
                },
            },
            isError=True,
        )

    # Valid — return captured outcome with provenance evidence
    outcome = result["framing_outcome"]

    logger.info("frame_initiative_outcome.complete",
               who=outcome["who"], why=outcome["why"],
               has_pain_verbatim=bool(pain_verbatim),
               has_observable_verbatim=bool(observable_verbatim))

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Problem outcome captured: {outcome['who']} needs something so that {outcome['why']}",
        )],
        structuredContent={
            "framing_outcome": outcome,
            "provenance": {
                "user_pain_verbatim": pain_verbatim,
                "user_observable_verbatim": observable_verbatim,
                "why_reframed_from_observable": True,
                "user_confirmed_why": True,
            },
            "captured": True,
            "assistant_guidance": {
                "action": "PROCEED_TO_HYPOTHESIS",
                "instruction": GUIDANCE_CAPTURED,
            },
        },
    )


# ============================================================================
# Self-register at import time
# ============================================================================

register_tool(ToolDefinition(
    name="frame_initiative_outcome",  # Changed from frame_initiative_intent
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    handle=handle,
    # OpenAI compliance annotations
    read_only_hint=False,  # Produces structured output for user
    destructive_hint=False,  # No data modification
    open_world_hint=False,  # No external API calls
))
