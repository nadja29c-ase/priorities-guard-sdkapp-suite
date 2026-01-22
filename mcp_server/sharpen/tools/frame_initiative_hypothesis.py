"""
Frame Initiative Hypothesis Tool.

Captures WHAT (the hypothesized solution) after WHO + WHY are confirmed.
Requires prior step output as input to enforce sequence.
Self-registers at import time.
"""

from typing import Optional

import structlog
from mcp import types as mcp_types
from pydantic import BaseModel, ValidationError

from .base import ToolDefinition
from . import register_tool
from ..tool_logic import validate_initiative_hypothesis, validate_hypothesis_provenance

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata (Goal-Oriented Description)
# ============================================================================

DESCRIPTION = """Records WHAT (the hypothesized solution) after problem is understood. Requires confirmed WHO + WHY from frame_initiative_intent.

SHARPEN MODE — BINDING RULES (not guidelines)
When user selects Sharpen, your default assistant behavior is SUSPENDED.

SUSPENDED BEHAVIORS:
- Suggesting solutions
- Improving or "fixing" user's hypothesis
- Offering alternatives unprompted
- Jumping to planning or breakdown
- Claiming user said something they didn't say

ACTIVE BEHAVIORS:
- Ask ONE question: "What do you think needs to exist to help with that?"
- Wait for answer
- Quote user's exact words back to them
- Reflect back as hypothesis
- Confirm with user
- Call tool only after provenance evidence is available and user confirms

WHAT AS HYPOTHESIS:
The user's WHAT is a hypothesis, not a commitment. Frame it that way:
- "You think [WHAT] might help [WHO] so that [WHY]."
- "This is your current hypothesis — we'll pressure-test it against constraints."

Do NOT evaluate whether it's a good solution. That comes later via constraints.

PROVENANCE EVIDENCE REQUIRED:
This tool requires proof that WHAT came from the user:
- user_what_verbatim: Copy-paste the user's exact words. Must be non-empty — do not call until WHAT is stated.
- what_stated_by_user: Did user say WHAT? If false, tool rejects.
- user_confirmed_hypothesis: Did user confirm? If false, tool rejects.

If you cannot honestly set ALL booleans to true AND provide a non-empty verbatim quote, do NOT call the tool. Ask the user first.

EXAMPLE CONVERSATION:
  [After frame_initiative_intent confirmed: who="New engineering hires", why="So they can find answers without interrupting others"]
  You: "What do you think needs to exist to help with that?"
  User: "A checklist they can follow in their first week"
       ↑ THIS IS user_what_verbatim — store exactly
  You: "Your hypothesis: A first-week checklist for new engineering hires so they can find answers without interrupting others. Correct?"
  User: "Yes"
       ↑ NOW user_confirmed_hypothesis = true
  → Call tool with:
    who="New engineering hires"
    why="So they can find answers without interrupting others"
    user_what_verbatim="A checklist they can follow in their first week"
    what_derived_from_verbatim="A first-week checklist"
    what_stated_by_user=true
    user_confirmed_hypothesis=true
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
        "user_what_verbatim": {
            "type": "string",
            "description": "User's EXACT words describing their hypothesized solution. Copy-paste from their message. Must be non-empty — do not call this tool until user has stated a WHAT.",
        },
        "what_derived_from_verbatim": {
            "type": "string",
            "description": "The WHAT, optionally condensed for clarity but semantically equivalent to user_what_verbatim. Do not invent — derive from the verbatim.",
        },
        "what_stated_by_user": {
            "type": "boolean",
            "description": "True ONLY if user explicitly stated WHAT in their own words. False if you inferred, generalized, or suggested it.",
        },
        "user_confirmed_hypothesis": {
            "type": "boolean",
            "description": "True ONLY if you reflected the hypothesis back and user explicitly confirmed (e.g. 'yes', 'correct', 'that's right').",
        },
    },
    "required": [
        "who",
        "why",
        "user_what_verbatim",
        "what_derived_from_verbatim",
        "what_stated_by_user",
        "user_confirmed_hypothesis",
    ],
    "additionalProperties": False,
}


# ============================================================================
# Pydantic Models for Validation
# ============================================================================


class FrameHypothesisRequest(BaseModel):
    """Expected input structure from ChatGPT."""
    who: Optional[str] = None
    why: Optional[str] = None
    user_what_verbatim: Optional[str] = None
    what_derived_from_verbatim: Optional[str] = None
    what_stated_by_user: Optional[bool] = None
    user_confirmed_hypothesis: Optional[bool] = None


# ============================================================================
# Assistant Guidance Messages
# ============================================================================

GUIDANCE_PROVENANCE_FAILED = (
    "SHARPEN MODE STILL BINDING. "
    "Provenance check failed. You must have evidence from the user before calling this tool.\n"
    "- If WHAT not stated: Ask 'What do you think needs to exist to help with that?'\n"
    "- If not confirmed: Reflect the hypothesis back and ask 'Correct?'\n"
    "Ask ONE question. Then stop and wait. Do not suggest solutions."
)

GUIDANCE_EMPTY_VERBATIM = (
    "SHARPEN MODE STILL BINDING. "
    "user_what_verbatim is empty. Do not call this tool until user has stated a WHAT. "
    "Ask: 'What do you think needs to exist to help with that?' "
    "Then store their exact answer in user_what_verbatim."
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

    # Extract provenance flags (default to False if None)
    what_stated = validated_request.what_stated_by_user or False
    user_confirmed = validated_request.user_confirmed_hypothesis or False
    what_verbatim = (validated_request.user_what_verbatim or "").strip()

    # Provenance validation
    provenance_result = validate_hypothesis_provenance(
        what_stated_by_user=what_stated,
        user_confirmed_hypothesis=user_confirmed,
        user_what_verbatim=what_verbatim,
    )

    if not provenance_result["valid"]:
        error_type = provenance_result["error_type"]

        if error_type == "empty_verbatim":
            guidance = GUIDANCE_EMPTY_VERBATIM
        else:
            guidance = GUIDANCE_PROVENANCE_FAILED

        logger.info("frame_initiative_hypothesis.provenance_rejected",
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

    # Structural validation (maps input field to internal 'what')
    result = validate_initiative_hypothesis(
        who=validated_request.who,
        why=validated_request.why,
        what=validated_request.what_derived_from_verbatim,
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

    # Valid — return confirmed framing with provenance evidence
    framing = result["framing"]

    logger.info("frame_initiative_hypothesis.complete",
                who=framing["who"], what=framing["what"],
                has_verbatim=bool(what_verbatim))

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Hypothesis confirmed: {framing['who']} needs {framing['what']} so that {framing['why']}",
        )],
        structuredContent={
            "framing_intent": framing,
            "provenance": {
                "user_what_verbatim": what_verbatim,
                "what_stated_by_user": True,
                "user_confirmed_hypothesis": True,
            },
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
