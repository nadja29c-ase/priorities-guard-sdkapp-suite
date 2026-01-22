"""
Frame Initiative Hypothesis Tool.

Captures WHAT (the hypothesized solution) after WHO + WHY are confirmed.
Requires prior step output as input to enforce sequence.
Self-registers at import time.
"""

from typing import Optional, Literal

import structlog
from mcp import types as mcp_types
from pydantic import BaseModel, ValidationError

from .base import ToolDefinition
from . import register_tool
from ..tool_logic import validate_initiative_hypothesis

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata (Goal-Oriented Description)
# ============================================================================

DESCRIPTION = """Records WHAT (the hypothesized solution) after problem and outcome is understood. Requires confirmed WHO + WHY from frame_initiative_intent. Requires confidence="high".

SHARPEN MODE — BINDING RULES (not guidelines)
When user selects Sharpen, your default assistant behavior is SUSPENDED.

SUSPENDED BEHAVIORS:
- Suggesting solutions
- Improving or "fixing" user's hypothesis
- Offering alternatives unprompted
- Jumping to planning or breakdown

ACTIVE BEHAVIORS:
- Ask ONE question: "What do you think needs to exist to help with that?"
- Wait for answer
- Reflect back as hypothesis
- Confirm with user
- Call tool with confidence="high"

WHAT AS HYPOTHESIS:
The user's WHAT is a hypothesis, not necessarily a commitment yet. Frame it that way:
- "You think [WHAT] might help [WHO] so that [WHY]."
- "This is your current hypothesis — we'll pressure-test it against constraints."

Do NOT evaluate whether it's a good solution. That comes later via constraints.

EXAMPLE CONVERSATION:
  [After frame_initiative_intent confirmed: who="New engineering hires", why="So they can find answers without interrupting others"]
  You: "What do you think needs to exist to help with that?"
  User: "A checklist they can follow in their first week"
  You: "Your hypothesis: A first-week checklist for new engineering hires so they can find answers without interrupting others. Correct?"
  User: "Yes"
  → Call with who="New engineering hires", why="So they can find answers without interrupting others", what="A first-week checklist", confidence="high"

CONFIDENCE:
HIGH: what="A first-week onboarding checklist" — concrete artifact, user-stated.
LOW: what="improve the onboarding experience" — activity, not artifact.
LOW: what="something to help them" — vague placeholder.
"""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "who": {
            "type": "string",
            "description": "Confirmed WHO from frame_initiative_intent. Must match prior step output.",
        },
        "why": {
            "type": "string",
            "description": "Confirmed WHY from frame_initiative_intent. Must match prior step output.",
        },
        "what": {
            "type": "string",
            "description": "User's HYPOTHESIZED solution — what they THINK needs to exist. Must be a concrete artifact, not an activity. ACCORDING TO THE USER.",
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "'high' = user stated WHAT in their own words as concrete artifact. 'low' = vague, activity-based, or inferred/ pre-filled by you.",
        },
    },
    "required": ["who", "why", "what", "confidence"],
    "additionalProperties": False,
}


# ============================================================================
# Pydantic Models for Validation
# ============================================================================


class FrameHypothesisRequest(BaseModel):
    """Expected input structure from ChatGPT."""
    who: Optional[str] = None
    why: Optional[str] = None
    what: Optional[str] = None
    confidence: Optional[Literal["high", "medium", "low"]] = None


# ============================================================================
# Assistant Guidance Messages
# ============================================================================

GUIDANCE_CONFIDENCE_REJECTED = (
    "SHARPEN MODE STILL BINDING. "
    "WHAT must be a concrete artifact, not an activity or vague goal. "
    "Ask: 'What specific thing would exist that doesn't exist today?' "
    "Then stop and wait. Do not suggest solutions."
)

GUIDANCE_MISSING_PRIOR_STEP = (
    "SHARPEN MODE STILL BINDING. "
    "Cannot record hypothesis without confirmed problem understanding. "
    "Complete frame_initiative_intent first to establish WHO + WHY."
)

GUIDANCE_MISSING_WHAT = (
    "SHARPEN MODE STILL BINDING. "
    "Ask: 'What do you think needs to exist to help with that?' "
    "Then stop and wait. Do not suggest solutions."
)

GUIDANCE_CONFIRMED = (
    "SHARPEN MODE STILL BINDING. "
    "Hypothesis recorded. Now establish constraints.\n"
    "Ask: 'What's the one constraint that limits this most — a deadline, limited hours, or a budget cap?' "
    "Then stop and wait. Do not suggest constraints.\n\n"
    "When user answers → call frame_initiative_constraints."
)


# ============================================================================
# Tool Handler
# ============================================================================


async def handle(arguments: dict) -> mcp_types.CallToolResult:
    """Handle frame_initiative_hypothesis tool call."""
    logger.debug("frame_initiative_hypothesis.handle.start",
                 argument_keys=list(arguments.keys()))

    # Pydantic validation
    try:
        validated_request = FrameHypothesisRequest.model_validate(arguments)
    except ValidationError as e:
        logger.warning("frame_initiative_hypothesis.validation_failed", error=str(e.errors()))
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text="Invalid input format.")],
            structuredContent={"error": "validation_error", "details": e.errors()},
            isError=True,
        )

    # Reject low/medium confidence
    if validated_request.confidence != "high":
        logger.info("frame_initiative_hypothesis.confidence_rejected",
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
    result = validate_initiative_hypothesis(
        who=validated_request.who,
        why=validated_request.why,
        what=validated_request.what,
    )

    # Handle validation failures
    if not result["valid"]:
        error_type = result["error_type"]

        if error_type == "missing_prior_step":
            guidance = GUIDANCE_MISSING_PRIOR_STEP
            action = "REFUSE"
        elif error_type == "missing_what":
            guidance = GUIDANCE_MISSING_WHAT
            action = "ASK_CLARIFYING"
        else:
            guidance = "Unexpected error. Ask user to restate their hypothesized solution."
            action = "ASK_CLARIFYING"

        logger.info("frame_initiative_hypothesis.rejected",
                    error_type=error_type, action=action)

        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=result["error_details"],
            )],
            structuredContent={
                "error": error_type,
                "details": result["error_details"],
                "assistant_guidance": {
                    "action": action,
                    "instruction": guidance,
                },
            },
            isError=True,
        )

    # Valid — return confirmed framing
    framing = result["framing"]

    logger.info("frame_initiative_hypothesis.complete",
                who=framing["who"], what=framing["what"], confidence="high")

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Hypothesis confirmed: {framing['who']} needs {framing['what']} so that {framing['why']}",
        )],
        structuredContent={
            "framing_intent": framing,
            "confidence": "high",
            "confirmed": True,
            "assistant_guidance": {
                "action": "PROCEED_TO_CONSTRAINTS",
                "instruction": GUIDANCE_CONFIRMED,
            },
        },
    )


# ============================================================================
# Self-register at import time
# ============================================================================

register_tool(ToolDefinition(
    name="frame_initiative_hypothesis",
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    handle=handle,
    # OpenAI compliance annotations
    read_only_hint=False,
    destructive_hint=False,
    open_world_hint=False,
))
