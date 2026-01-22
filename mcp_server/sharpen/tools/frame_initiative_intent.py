"""
Frame Initiative Intent Tool.

Captures WHO benefits and WHY (the outcome). WHAT comes later via frame_initiative_hypothesis.
Structural validation only — semantic quality is the LLM's job.
Self-registers at import time.
"""

from typing import Optional, Literal

import structlog
from mcp import types as mcp_types
from pydantic import BaseModel, ValidationError

from .base import ToolDefinition
from . import register_tool
from ..tool_logic import validate_initiative_intent

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata (Goal-Oriented Description)
# ============================================================================

DESCRIPTION = """Records WHO benefits and WHY (outcome) for given initiative. Requires confidence="high".

SHARPEN MODE — BINDING RULES (not guidelines)
When user selects Sharpen, your default assistant behavior is SUSPENDED.

SUSPENDED BEHAVIORS:
- Asking about solutions/WHAT before understanding the problem
- Batching multiple questions
- Inferring what the user "probably means"
- Planning or structuring for the user

ACTIVE BEHAVIORS:
- Ask ONE question at a time
- Wait for answer
- Reflect back and confirm
- Call tool only after confidence="high"

ELICITATION ORDER:
1. WHO: "Who specifically is supposed to benefit from this?"
2. PAIN: "What's currently hard or frustrating for them?"
3. (If pain is abstract) OBSERVABLE: "What would you see happening differently if this worked?"
4. REFRAME: Convert pain → outcome-phrased WHY 
5. CONFIRM: "To confirm: [WHO] needs something so that [WHY]. Correct?"

CRITICAL: Do NOT ask about WHAT/solution yet. Problem and outcome understanding comes first.

PAIN → OUTCOME REFRAMING:
- User says: "They keep asking the same questions" (pain)
- You reframe: "So they can find answers without interrupting others" (outcome)
- User says: "They feel lost" (abstract pain)
- You probe: "What would you see them doing differently?"
- User says: "Taking on tasks independently"
- You reframe: "So they can work independently without hand-holding" (outcome)

EXAMPLE CONVERSATION:
  User: "I want to improve our onboarding"
  You: "Who specifically is supposed to benefit from this?"
  User: "New engineering hires"
  You: "What's currently hard or frustrating for new engineering hires?"
  User: "They keep asking the same basic questions and feel lost"
  You: "To confirm: New engineering hires need something so they can find answers without constantly interrupting others. Correct?"
  User: "Yes"
  → Call with who="New engineering hires", why="So they can find answers without constantly interrupting others", confidence="high"
  → Tool returns guidance to proceed to frame_initiative_hypothesis

CONFIDENCE:
HIGH: who="New engineering hires" why="So they can contribute without constant interruptions" — concrete, user-confirmed, outcome-phrased.
LOW: who="users" why="because onboarding matters" — vague, motivational, not outcome-phrased.
"""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "who": {
            "type": "string",
            "description": "ONE primary beneficiary. Who benefits first and foremost? Not multiple audiences. ACCORDING TO THE USER.",
        },
        "why": {
            "type": "string",
            "description": "So that WHO benefits HOW? Must be outcome-phrased (what changes), not pain-phrased. Elicit pain first, then reframe to outcome. ACCORDING TO THE USER.",
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "'high' = user stated WHO and WHY in their own words. 'low' = you inferred or filled gaps.",
        },
    },
    "required": ["who", "why", "confidence"],
    "additionalProperties": False,
}


# ============================================================================
# Pydantic Models for Validation
# ============================================================================


class FrameIntentRequest(BaseModel):
    """Expected input structure from ChatGPT."""
    who: Optional[str] = None
    why: Optional[str] = None
    confidence: Optional[Literal["high", "medium", "low"]] = None


# ============================================================================
# Assistant Guidance Messages
# ============================================================================

GUIDANCE_CONFIDENCE_REJECTED = (
    "SHARPEN MODE STILL BINDING. "
    "Check which field is vague:\n"
    "- Vague WHO: Ask 'Who specifically is affected?'\n"
    "- Vague/abstract WHY: Ask 'What would you see happening differently if this worked?'\n"
    "Ask ONE question. Then stop and wait. Do not ask about solutions yet."
)

GUIDANCE_MISSING_FIELDS = (
    "SHARPEN MODE STILL BINDING. "
    "Ask ONE question about the missing field:\n"
    "- Missing WHO: 'Who specifically is supposed to benefit from this?'\n"
    "- Missing WHY: 'What's currently hard or frustrating for them?'\n"
    "Then stop and wait. Do not ask about solutions yet."
)

GUIDANCE_MULTIPLE_STAKEHOLDERS = (
    "SHARPEN MODE STILL BINDING. "
    "Multiple stakeholders detected. Ask: 'Who benefits first and foremost?' "
    "Then stop and wait. Frame confirmation as '[WHO] primarily benefits from this.'"
)

GUIDANCE_CONFIRMED = (
    "SHARPEN MODE STILL BINDING. "
    "Problem and outcome understanding confirmed. Now ask about the hypothesized solution:\n"
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

    # Reject low/medium confidence
    if validated_request.confidence != "high":
        logger.info("frame_initiative_intent.confidence_rejected",
                   confidence=validated_request.confidence)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=f"Confidence '{validated_request.confidence}' rejected. Only 'high' accepted.",
            )],
            structuredContent={
                "error": "confidence_too_low",
                "confidence_provided": validated_request.confidence,
                "assistant_guidance": {
                    "action": "ASK_CLARIFYING",
                    "instruction": GUIDANCE_CONFIDENCE_REJECTED,
                },
            },
            isError=True,
        )

    # Structural validation
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

    # Valid — return confirmed framing
    intent = result["framing_intent"]

    logger.info("frame_initiative_intent.complete",
               who=intent["who"], why=intent["why"], confidence="high")

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Problem framing confirmed: {intent['who']} needs something so that {intent['why']}",
        )],
        structuredContent={
            "framing_intent": intent,  # Now only contains who + why
            "confidence": "high",
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
