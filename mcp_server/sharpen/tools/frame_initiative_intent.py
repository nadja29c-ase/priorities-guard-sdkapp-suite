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

DESCRIPTION = """Clarifies the value the user wants to create with an initiative: WHO benefits and WHY (observable outcome derived from WHO's pain). Transforms vague intentions into concrete value statement before exploring solutions.

SHARPEN MODE BINDING: When the user selects Sharpen, your default behavior is SUSPENDED. Instead, you take on the role of a FACILITATOR. YOU ASK QUESTIONS TO FACILITATE USER'S THINKING, never tell. ONE question → wait → confirm → call.

STYLE: Acknowledge what user shared. Briefly explain why each question matters. Mark progress naturally. F.e. "Got it — new engineering hires. To understand the value you want to create, what's currently hard or frustrating for them during onboarding?"

Sequence YOU MUST FOLLOW: 
1. Elicit WHO (store verbatim)
2. Elicit PAIN (store verbatim)
3. Elicit OBSERVABLE (store verbatim)
4. Reframe WHY from observable + pain (this is the outcome)
5. Reflect: "To confirm: [WHO] needs something so that [WHY]. Correct?"
6. User confirms ← THE ONLY CONFIRMATION
7. Call tool
DO NOT SKIP STEPS.
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

GUIDANCE_PROVENANCE_FAILED = (
    "SHARPEN MODE STILL BINDING. "
    "Provenance check failed. You must have evidence from the user before calling this tool.\n"
    "- If WHO not stated: Ask 'Who specifically is supposed to benefit from this?'\n"
    "- If pain not stated: Ask 'What's currently hard or frustrating for them?'\n"
    "- If observable not stated: Ask 'What would you see happening differently if this worked? Describe a concrete behavior or artifact — not a feeling or general improvement.'\n"
    "- If WHY not derived from observable: Reframe the user's observable into an outcome first.\n"
    "- If not confirmed: Reflect WHO + WHY back and ask 'Correct?'\n"
    "Ask ONE question. Then stop and wait."
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
    "Then store their exact answer in user_observable_verbatim. "
    "ALWAYS ask this question — even if pain seems concrete."
)

GUIDANCE_MISSING_FIELDS = (
    "SHARPEN MODE STILL BINDING. "
    "Ask ONE question about the missing field:\n"
    "- Missing WHO: 'Who specifically is supposed to benefit from this?'\n"
    "- Missing WHY: First get pain, then observable, then reframe to outcome.\n"
    "Then stop and wait. Do not ask about solutions yet."
)

GUIDANCE_MULTIPLE_STAKEHOLDERS = (
    "SHARPEN MODE STILL BINDING. "
    "Multiple stakeholders detected. Ask: 'Who benefits first and foremost?' "
    "Then stop and wait. Frame confirmation as '[WHO] primarily benefits from this.'"
)

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
        logger.warning("frame_initiative_intent.validation_failed", error=str(e.errors()))
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text="Invalid input format.")],
            structuredContent={"error": "validation_error", "details": e.errors()},
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
        error_type = provenance_result["error_type"]

        if error_type == "empty_pain_verbatim":
            guidance = GUIDANCE_EMPTY_PAIN_VERBATIM
        elif error_type == "empty_observable_verbatim":
            guidance = GUIDANCE_EMPTY_OBSERVABLE_VERBATIM
        else:
            guidance = GUIDANCE_PROVENANCE_FAILED

        logger.info("frame_initiative_intent.provenance_rejected",
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

    # Structural validation (who, why content)
    result = validate_initiative_intent(
        who=validated_request.who,
        why=validated_request.why,
    )

    # If structurally invalid, return error
    if not result["valid"]:
        # Check for multiple stakeholders
        if result.get("multiple_stakeholders"):
            return mcp_types.CallToolResult(
                content=[mcp_types.TextContent(
                    type="text",
                    text="Multiple stakeholders detected. Need primary beneficiary.",
                )],
                structuredContent={
                    "error": "multiple_stakeholders",
                    "who_provided": result["framing_intent"]["who"],
                    "recovery_hint": "Ask user to name ONE primary beneficiary",
                    "assistant_guidance": {
                        "action": "ASK_CLARIFYING",
                        "instruction": GUIDANCE_MULTIPLE_STAKEHOLDERS,
                    },
                },
                isError=True,
            )

        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=f"Missing required fields: {', '.join(result['missing'])}",
            )],
            structuredContent={
                "error": "missing_fields",
                "missing": result["missing"],
                "assistant_guidance": {
                    "action": "ASK_CLARIFYING",
                    "instruction": GUIDANCE_MISSING_FIELDS,
                },
            },
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
