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

DESCRIPTION = """Records WHO benefits and WHY (outcome) for given initiative. WHAT comes later via frame_initiative_hypothesis.

SHARPEN MODE — BINDING RULES (not guidelines)
When user selects Sharpen, your default assistant behavior is SUSPENDED.

SUSPENDED BEHAVIORS:
- Asking about solutions/WHAT before understanding the problem
- Batching multiple questions
- Inferring or prefilling WHO/WHY on behalf of the user
- Planning or structuring for the user
- Claiming user said something they didn't say
- Skipping the observable question

ACTIVE BEHAVIORS:
- Ask ONE question at a time
- Wait for answer
- Quote user's exact words back to them
- ALWAYS ask the observable question (even if pain seems concrete)
- Reframe observable → outcome
- Confirm with user
- Call tool only after explicit user confirmation

ELICITATION ORDER (ALL STEPS MANDATORY):
1. WHO: "Who specifically is supposed to benefit from this?"
   → Wait for answer. Store exact words.
2. PAIN: "What's currently hard or frustrating for them?"
   → Wait for answer. Store EXACT quote in user_pain_verbatim.
3. OBSERVABLE: "What would you see happening differently if this worked?"
   → ALWAYS ASK THIS. Even if pain seems concrete.
   → Prompt for concrete behaviors or artifacts, not feelings.
   → Say: "Describe a concrete behavior or artifact you would see — not a feeling or general improvement."
   → Wait for answer. Store EXACT quote in user_observable_verbatim.

   GOOD observables (accept these):
   - "They'd submit their first PR within 2 weeks"
   - "They'd find documentation without asking"
   - "The onboarding checklist would exist and be current"

   BAD observables (push back on these):
   - "They'd feel more confident" ← feeling
   - "They'd understand the system better" ← meta state
   - "Onboarding would be smoother" ← vague improvement

   If user gives vague observable, push back:
   "That sounds like a feeling or general improvement. What concrete behavior or artifact would you actually see?"
4. REFRAME: Convert observable → outcome-phrased WHY
   → "So they can [outcome derived from observable]"
   → WHY must trace to observable, NOT raw pain.
5. CONFIRM: "To confirm: [WHO] needs something so that [WHY]. Correct?"
   → Wait for explicit "yes" / "correct" / confirmation.

CRITICAL: Do NOT ask about WHAT/solution yet. Problem understanding comes first.
CRITICAL: Do NOT skip the observable question. It sharpens vague pain into actionable outcomes.

PROVENANCE EVIDENCE REQUIRED:
This tool requires proof that data came from the user:
- user_pain_verbatim: Copy-paste the user's exact pain words. Must be non-empty.
- user_observable_verbatim: Copy-paste the user's exact observable words. Must be non-empty.
- who_stated_by_user: Did user say WHO? If false, tool rejects.
- why_reframed_from_observable: Is WHY derived from the observable (not raw pain)? If false, tool rejects.
- user_confirmed_framing: Did user confirm? If false, tool rejects.

If you cannot honestly set ALL booleans to true AND provide BOTH non-empty verbatim quotes, do NOT call the tool. Ask the missing question first.

EXAMPLE CONVERSATION:
  User: "I want to improve our onboarding"
  You: "Who specifically is supposed to benefit from this?"
  User: "New engineering hires"
  You: "What's currently hard or frustrating for new engineering hires?"
  User: "They feel disoriented and blocked in the first 4 weeks"
       ↑ THIS IS user_pain_verbatim — store exactly
  You: "What would you see happening differently if onboarding worked? Describe a concrete behavior or artifact — not a feeling or general improvement."
       ↑ ALWAYS ASK THIS — do not skip
  User: "They'd find documentation themselves and submit their first PR within 2 weeks"
       ↑ THIS IS user_observable_verbatim — store exactly
  You: "To confirm: New engineering hires need something so they can find documentation independently and ship their first PR within 2 weeks. Correct?"
       ↑ WHY reframed from observable, NOT from raw pain
  User: "Yes"
       ↑ NOW user_confirmed_framing = true
  → Call tool with:
    who="New engineering hires"
    user_pain_verbatim="They feel disoriented and blocked in the first 4 weeks"
    user_observable_verbatim="They'd find documentation themselves and submit their first PR within 2 weeks"
    why="So they can find documentation independently and ship their first PR within 2 weeks"
    who_stated_by_user=true
    why_reframed_from_observable=true
    user_confirmed_framing=true
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
            "description": "User's EXACT words describing their pain, frustration, or problem. Copy-paste from their message. Must be non-empty.",
        },
        "user_observable_verbatim": {
            "type": "string",
            "description": "User's EXACT words describing what would be different if this worked. Must be non-empty — ALWAYS ask 'What would you see happening differently?' even if pain seems concrete.",
        },
        "why": {
            "type": "string",
            "description": "YOUR reframe of user_observable_verbatim into an outcome. Must be traceable to the observable quote, not the raw pain. Do not invent — derive from the observable.",
        },
        "who_stated_by_user": {
            "type": "boolean",
            "description": "True ONLY if user explicitly stated WHO in their own words. False if you inferred, generalized, or suggested it.",
        },
        "why_reframed_from_observable": {
            "type": "boolean",
            "description": "True ONLY if WHY was derived by reframing user_observable_verbatim (not user_pain_verbatim). False if WHY was generated without the observable question.",
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
