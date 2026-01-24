"""
Frame Initiative Intent Tool.

Captures WHO benefits and WHY (the outcome). WHAT comes later via frame_initiative_hypothesis.
Structural validation only — semantic quality is the LLM's job.
Self-registers at import time.
"""

from typing import Optional

import structlog
from mcp import types as mcp_types
from pydantic import BaseModel, ValidationError

from .base import ToolDefinition
from . import register_tool
from ..tool_logic import validate_initiative_intent, validate_intent_provenance

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata (Goal-Oriented Description)
# ============================================================================

DESCRIPTION = """Records confirmed problem framing: WHO benefits and WHY (outcome derived from pain + observable).

CALL PRECONDITIONS — DO NOT CALL unless ALL are true:
- who_stated_by_user: user explicitly stated WHO
- user_pain_verbatim: non-empty, user's exact words
- user_observable_verbatim: non-empty, user's exact words
- why_reframed_from_observable: WHY incorporates observable
- user_confirmed_framing: user explicitly confirmed

SHARPEN MODE BINDING RULES: When user selects Sharpen, your default behavior is SUSPENDED. You are a Coach now: ask questions to facilitate user's thinking and NEVER to tell the user what to do or infer their answers. Ask ONE question at a time → wait for user's response -> have a back-and-forth conversation. Violating this breaks Sharpen.
FACILITATOR MODE: You are a facilitator, not a teller. ONE question at a time. Wait for answer. Store verbatim. Reflect and confirm before calling.

Sequence: WHO → PAIN → OBSERVABLE → reframe WHY → reflect and confirm → call tool.

STYLE: Briefly explain why each question matters. Acknowledge user's progress naturally.
"""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "who": {
            "type": "string",
            "description": "ONE primary beneficiary. Who benefits first and foremost? Not multiple audiences. ACCORDING TO THE USER.",
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
            "description": "YOUR reframe combining pain (the value) + observable (the specificity) into an outcome. Pain provides what matters; observable makes it measurable. Example: pain='they feel lost and blocked' + observable='ship first PR within 2 weeks' → WHY='So they can ship their first PR within 2 weeks without being blocked'.",
        },
        "who_stated_by_user": {
            "type": "boolean",
            "description": "True ONLY if user explicitly stated WHO in their own words. False if you inferred, generalized, or suggested it.",
        },
        "why_reframed_from_observable": {
            "type": "boolean",
            "description": "True ONLY if WHY incorporates the observable (not just the raw pain). False if observable was not asked or not used in WHY.",
        },
        "user_confirmed_framing": {
            "type": "boolean",
            "description": "True ONLY if you reflected WHO + WHY back and user explicitly confirmed (e.g. 'yes', 'correct', 'that's right').",
        },
    },
    "required": [
        "who",
        "user_pain_verbatim",
        "user_observable_verbatim",
        "why",
        "who_stated_by_user",
        "why_reframed_from_observable",
        "user_confirmed_framing",
    ],
    "additionalProperties": False,
}


# ============================================================================
# Pydantic Models for Validation
# ============================================================================


class FrameIntentRequest(BaseModel):
    """Expected input structure from ChatGPT."""
    who: Optional[str] = None
    user_pain_verbatim: Optional[str] = None
    user_observable_verbatim: Optional[str] = None
    why: Optional[str] = None
    who_stated_by_user: Optional[bool] = None
    why_reframed_from_observable: Optional[bool] = None
    user_confirmed_framing: Optional[bool] = None


# ============================================================================
# Assistant Guidance Messages
# ============================================================================

# Preserved for rollback if zero-info experiment fails.
_LEGACY_GUIDANCE = {
    "provenance_failed": (
        "SHARPEN MODE STILL BINDING. "
        "Provenance check failed. You must have evidence from the user before calling this tool.\n"
        "- If WHO not stated: Ask 'Who specifically is supposed to benefit from this?'\n"
        "- If pain not stated: Ask 'What's currently hard or frustrating for them?'\n"
        "- If observable not stated: Ask 'What would you see happening differently if this worked? Describe a concrete behavior or artifact — not a feeling or general improvement.'\n"
        "- If WHY not derived from observable: Reframe the user's observable into an outcome first.\n"
        "- If not confirmed: Reflect WHO + WHY back and ask 'Correct?'\n"
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
        "Then stop and wait. Frame confirmation as '[WHO] primarily benefits from this.'"
    ),
}

# Success guidance (still used — guidance on success is appropriate)
GUIDANCE_CONFIRMED = (
    "SHARPEN MODE STILL BINDING. "
    "Problem understanding confirmed with evidence. Now ask about the hypothesized solution:\n"
    "'What do you think needs to exist to help with that?'\n"
    "Then stop and wait. Do not suggest solutions.\n\n"
    "When user answers → call frame_initiative_hypothesis with the WHAT."
)


# ============================================================================
# Tool Handler
# ============================================================================


async def handle(arguments: dict) -> mcp_types.CallToolResult:
    """Handle frame_initiative_intent tool call."""
    logger.debug("frame_initiative_intent.handle.start",
                argument_keys=list(arguments.keys()))

    # Pydantic validation
    try:
        validated_request = FrameIntentRequest.model_validate(arguments)
    except ValidationError as e:
        logger.info(
            "frame_initiative_intent.rejected",
            error_type="validation_error",
            failed_checks=["pydantic_validation"],
            input_snapshot={"raw_keys": list(arguments.keys())},
        )
        return mcp_types.CallToolResult(
            content=[],
            structuredContent={"status": "incomplete"},
            isError=True,
        )

    # Extract provenance flags (default to False if None)
    who_stated = validated_request.who_stated_by_user or False
    why_reframed = validated_request.why_reframed_from_observable or False
    user_confirmed = validated_request.user_confirmed_framing or False
    pain_verbatim = (validated_request.user_pain_verbatim or "").strip()
    observable_verbatim = (validated_request.user_observable_verbatim or "").strip()

    # Provenance validation
    provenance_result = validate_intent_provenance(
        who_stated_by_user=who_stated,
        why_reframed_from_observable=why_reframed,
        user_confirmed_framing=user_confirmed,
        user_pain_verbatim=pain_verbatim,
        user_observable_verbatim=observable_verbatim,
    )

    if not provenance_result["valid"]:
        logger.info(
            "frame_initiative_intent.rejected",
            error_type=provenance_result["error_type"],
            failed_checks=provenance_result.get("failed_checks", []),
            input_snapshot={
                "who": validated_request.who,
                "user_pain_verbatim": bool(pain_verbatim),
                "user_observable_verbatim": bool(observable_verbatim),
                "why": validated_request.why,
                "who_stated_by_user": who_stated,
                "why_reframed_from_observable": why_reframed,
                "user_confirmed_framing": user_confirmed,
            },
        )
        return mcp_types.CallToolResult(
            content=[],
            structuredContent={"status": "incomplete"},
            isError=True,
        )

    # Structural validation (who, why content)
    result = validate_initiative_intent(
        who=validated_request.who,
        why=validated_request.why,
    )

    # If structurally invalid, return error
    if not result["valid"]:
        error_type = "multiple_stakeholders" if result.get("multiple_stakeholders") else "missing_fields"
        logger.info(
            "frame_initiative_intent.rejected",
            error_type=error_type,
            failed_checks=result.get("missing", []),
            input_snapshot={
                "who": validated_request.who,
                "user_pain_verbatim": bool(pain_verbatim),
                "user_observable_verbatim": bool(observable_verbatim),
                "why": validated_request.why,
                "who_stated_by_user": who_stated,
                "why_reframed_from_observable": why_reframed,
                "user_confirmed_framing": user_confirmed,
            },
        )
        return mcp_types.CallToolResult(
            content=[],
            structuredContent={"status": "incomplete"},
            isError=True,
        )

    # Valid — return confirmed framing with provenance evidence
    intent = result["framing_intent"]

    logger.info("frame_initiative_intent.complete",
               who=intent["who"], why=intent["why"],
               has_pain_verbatim=bool(pain_verbatim),
               has_observable_verbatim=bool(observable_verbatim))

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Problem framing confirmed: {intent['who']} needs something so that {intent['why']}",
        )],
        structuredContent={
            "framing_intent": intent,
            "provenance": {
                "user_pain_verbatim": pain_verbatim,
                "user_observable_verbatim": observable_verbatim,
                "who_stated_by_user": True,
                "why_reframed_from_observable": True,
                "user_confirmed_framing": True,
            },
            "confirmed": True,
            "assistant_guidance": {
                "action": "PROCEED_TO_HYPOTHESIS",
                "instruction": GUIDANCE_CONFIRMED,
            },
        },
    )


# ============================================================================
# Self-register at import time
# ============================================================================

register_tool(ToolDefinition(
    name="frame_initiative_intent",
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    handle=handle,
    # OpenAI compliance annotations
    read_only_hint=False,  # Produces structured output for user
    destructive_hint=False,  # No data modification
    open_world_hint=False,  # No external API calls
))
