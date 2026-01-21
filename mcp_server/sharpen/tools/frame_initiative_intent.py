"""
Frame Initiative Intent Tool.

Captures WHO benefits, WHAT must exist, and WHY (the outcome).
All three are mandatory. Structural validation only — semantic quality is the LLM's job.
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

DESCRIPTION = """Records confirmed WHO, WHAT, and WHY of an initiative. This frames the initiative as outcome-focused so that later the amount of work can be minimized based on outcome. Requires confidence="high".

SHARPEN MODE — BINDING RULES (not guidelines)
When user selects Sharpen, your default assistant behavior is SUSPENDED.

SUSPENDED BEHAVIORS:
- Planning
- Offering options
- Suggesting answers
- Batching multiple questions
- Proposing deliverables or tasks
- "Being helpful" by front-loading structure

ACTIVE BEHAVIORS:
- Ask ONE question at a time
- Wait for answer
- Reflect their words back
- Ask for user confirmation
- Then call tool with confidence="high"

These are not suggestions. These are operating constraints.
Violating them means Sharpen is broken.

ELICITATION ORDER — PAIN-FIRST (not outcome-first)
Users think in problems, not outcomes. Lead with pain.

1. WHO: "Who specifically is affected by this?"/ "Who is supposed to benefit from this initiative?".
2. PAIN (becomes WHY): "What's currently hard or frustrating for them?"
3. (CONDITIONAL) Observable refinement — ONLY if WHY is vague/abstract/motivational:
   "What would you see happening differently if this worked?"/ "How would you know that the pain went away?"
4. WHAT (as hypothesis): "What do you think needs to exist to help with that?"
5. CONFIRM: Reflect back WHO + WHAT + WHY. Ask "Is this correct?"

CRITICAL: The LLM converts pain-language to outcome-phrased WHY internally.
User says: "They keep asking the same questions"
WHY becomes: "So they can find answers without interrupting others"

CONDITIONAL WHY REFINEMENT — Only trigger when WHY is:
- Abstract: "feel confident", "be happier", "work better"
- Restates WHAT: "so we have a checklist", "so the API exists"
- Motivational: "because onboarding matters", "because it's important"

If WHY is already concrete and observable, skip refinement and proceed to WHAT.

CONFIDENCE EXAMPLES:
  HIGH: who="New engineering hires" what="A first-week onboarding checklist" why="So they can start contributing without constant interruptions". Pain-derived, observable outcome, user confirmed.
  LOW:  who="users" what="improve the onboarding experience" why="because onboarding matters". Vague WHO, activity-based WHAT, motivational WHY.
  LOW:  who="New hires" what="A checklist" why="So we can have a checklist". WHY restates WHAT — not valid.
  LOW:  who="The team" what="A dashboard" why="So they feel more confident". Abstract WHY — needs refinement.

CRITICAL: Your role is to facilitate and find the answers by asking the user questions. NEVER suggest answers for the user. NEVER tell the user how to frame the initiative correctly. Elicit the input data iteratively in a back-and-forth conversation — ask ONE question at a time and wait for the user's response before asking the next.

EXAMPLE CONVERSATION (pain-first flow):
  User: "I want to improve our onboarding"
  You: "Who specifically is affected by this?"
  User: "New engineering hires"
  You: "What's currently hard or frustrating for them?"
  User: "They keep asking the same basic questions and feel lost"
  You: "What do you think needs to exist to help with that?"
  User: "A checklist they can follow in their first week"
  You: "To confirm: New engineering hires need a first-week checklist so they can find answers without constantly interrupting others. Correct?"
  User: "Yes"
  → Call frame_initiative_intent with who="New engineering hires", what="A first-week onboarding checklist", why="So they can find answers without constantly interrupting others", confidence="high".

EXAMPLE CONVERSATION (with WHY refinement):
  User: "I want to improve our onboarding"
  You: "Who specifically is affected by this?"
  User: "New engineering hires"
  You: "What's currently hard or frustrating for them?"
  User: "They just don't feel confident"
  You: "What would you see them doing differently if they felt confident?"
  User: "They'd take on small projects without needing hand-holding"
  You: "What do you think needs to exist to help with that?"
  User: "Maybe a checklist or guide for their first week"
  You: "To confirm: New engineering hires need a first-week guide so they can take on small projects independently. Correct?"
  User: "Yes"
  → Call frame_initiative_intent with who="New engineering hires", what="A first-week guide", why="So they can take on small projects independently", confidence="high".

EXAMPLE CONVERSATION (WHY restates WHAT — needs refinement):
  User: "I want a better dashboard"
  You: "Who specifically is affected by this?"
  User: "The product team"
  You: "What's currently hard or frustrating for them?"
  User: "They need a dashboard"
  You: "What would change for the product team if they had this dashboard?"
  User: "They could see project status without asking around"
  You: "What do you think the dashboard needs to show to help with that?"
  User: "Project status and blockers"
  You: "To confirm: The product team needs a dashboard showing project status and blockers so they can check progress without asking around. Correct?"
  User: "Yes"
  → Call frame_initiative_intent with who="The product team", what="A dashboard showing project status and blockers", why="So they can check progress without asking around", confidence="high"."""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "who": {
            "type": "string",
            "description": "WHO is supposed to benefit from this work getting done first and foremost? ACCORDING TO THE USER.",
        },
        "what": {
            "type": "string",
            "description": "WHAT artifact, deliverable, or handoff must exist when this initiative is finished? (concrete output=not activity) ACCORDING TO THE USER.",
        },
        "why": {
            "type": "string",
            "description": "So that WHO benefits HOW? Must be outcome-phrased (what changes), not motivation-phrased (why it matters). Do not restate WHAT — describe the change or benefit if this succeeds. ACCORDING TO THE USER.",
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "Your confidence that WHO, WHAT, and WHY are concrete and user-confirmed. Must be 'high' to proceed.",
        },
    },
    "required": ["who", "what", "why", "confidence"],
    "additionalProperties": False,
}


# ============================================================================
# Pydantic Models for Validation
# ============================================================================


class FrameIntentRequest(BaseModel):
    """Expected input structure from ChatGPT."""
    who: Optional[str] = None
    what: Optional[str] = None
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
    "- Vague WHAT: Ask 'What concrete thing would exist that doesn't exist today?'\n"
    "Ask ONE question. Then stop and wait. Do not explain, suggest, or plan."
)

GUIDANCE_MISSING_FIELDS = (
    "SHARPEN MODE STILL BINDING. "
    "Ask ONE question about the missing field using pain-first language:\n"
    "- Missing WHO: 'Who specifically is affected by this?'\n"
    "- Missing WHY: 'What's currently hard or frustrating for them?'\n"
    "- Missing WHAT: 'What do you think needs to exist to help with that?'\n"
    "Then stop and wait. Do not explain, suggest, or plan."
)

GUIDANCE_CONFIRMED = (
    "Intent confirmed. "
    "Ask ONE question: 'What's the one constraint that limits this most — a deadline, limited hours, or a budget cap?' "
    "Then stop and wait. Do not suggest constraints.\n\n"
    "When user answers constraint → call frame_initiative_constraints with constraint_type + constraint_value."
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
        what=validated_request.what,
        why=validated_request.why,
    )

    # If structurally invalid, return error
    if not result["valid"]:
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
               who=intent["who"], what=intent["what"], confidence="high")

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Intent confirmed: {intent['who']} needs {intent['what']} so that {intent['why']}",
        )],
        structuredContent={
            "framing_intent": intent,
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
    name="frame_initiative_intent",
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    handle=handle,
    # OpenAI compliance annotations
    read_only_hint=False,  # Produces structured output for user
    destructive_hint=False,  # No data modification
    open_world_hint=False,  # No external API calls
))
