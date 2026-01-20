"""
Commit Week Deliverable Tool (Step 3).

Captures the user's stopping line for this week's work on the focus deliverable.
This is time-boxing, not scope-cutting.
Self-registers at import time.
"""

from typing import Optional, Literal

import structlog
from mcp import types as mcp_types
from pydantic import BaseModel, ValidationError

from .base import ToolDefinition
from . import register_tool
from ..tool_logic import validate_good_enough

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata
# ============================================================================

DESCRIPTION = """Records the user's "good enough" stopping line for this week. This defines when they can stop working on the focus deliverable and feel the week was successful. Requires confirmed focus deliverable from Step 2 and confidence="high".

SHARPEN MODE — BINDING RULES (not guidelines)
When user selects Sharpen, your default assistant behavior is SUSPENDED.

SUSPENDED BEHAVIORS:
- Suggesting what "good enough" should be
- Adding quality criteria
- Proposing milestones
- Expanding the definition
- "Being helpful" by setting higher bars

ACTIVE BEHAVIORS:
- Ask ONE question
- Wait for answer
- Reflect their words back
- Ask for user confirmation
- Then call tool with confidence="high"

THE ONLY QUESTION:
"What would be good enough that you could stop working on [focus_deliverable] this week and still feel it was worth the time?"

SCOPE REGRESSION GUARDRAIL:
If the user's answer expands scope beyond the focus deliverable (adds new outcomes, audiences, or deliverables), ask: 'That sounds like it goes beyond [focus_deliverable]. What would be good enough within just that scope?'
Do not accept expanded scope. Step 3 tightens, never expands.

GOOD ANSWERS (concrete, stoppable):
- "Checklist exists, even if rough"
- "Shared with team, not finalized"
- "Covers day one only"

BAD ANSWERS (vague, unstoppable):
- "Make progress"
- "Get it done"
- "Feel good about it"

If answer is vague, ask: "How would you know it's done?" Then stop and wait.

EXAMPLE CONVERSATION:
  You: "What would be good enough that you could stop working on 'First-week checklist' this week and still feel it was worth the time?"
  User: "Having a draft ready"
  You: "How would you know the draft is ready?"
  User: "When it has all 5 days listed with at least one task each"
  You: "So 'good enough' this week is: a draft checklist with all 5 days and at least one task per day. Correct?"
  User: "Yes"
  → Call commit_week_deliverable with good_enough_definition="Draft checklist with all 5 days and at least one task per day", confidence="high"
"""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "initiative_framing": {
            "type": "object",
            "description": "Confirmed Step 1 framing (required).",
            "properties": {
                "who": {"type": "string"},
                "what": {"type": "string"},
                "why": {"type": "string"},
                "constraint_type": {
                    "type": "string",
                    "enum": ["time", "capacity", "budget", "forced_mvp"],
                },
                "constraint_value": {"type": "string"},
            },
            "required": ["who", "what", "why", "constraint_type", "constraint_value"],
        },
        "focus_deliverable": {
            "type": "object",
            "description": "Confirmed focus deliverable from Step 2 (required).",
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["name"],
        },
        "good_enough_definition": {
            "type": "string",
            "description": "User's definition of 'good enough' to stop this week. Must be concrete and verifiable. ACCORDING TO THE USER.",
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "Your confidence that the stopping line is user-confirmed and concrete. Must be 'high' to proceed.",
        },
    },
    "required": ["initiative_framing", "focus_deliverable", "good_enough_definition", "confidence"],
    "additionalProperties": False,
}


# ============================================================================
# Pydantic Models
# ============================================================================


class FocusDeliverable(BaseModel):
    """Focus deliverable from Step 2."""
    name: str
    description: Optional[str] = None


class InitiativeFraming(BaseModel):
    """Step 1 framing object."""
    who: Optional[str] = None
    what: Optional[str] = None
    why: Optional[str] = None
    constraint_type: Optional[Literal["time", "capacity", "budget", "forced_mvp"]] = None
    constraint_value: Optional[str] = None


class CommitWeekDeliverableRequest(BaseModel):
    """Expected input structure from ChatGPT."""
    initiative_framing: Optional[InitiativeFraming] = None
    focus_deliverable: Optional[FocusDeliverable] = None
    good_enough_definition: Optional[str] = None
    confidence: Optional[Literal["high", "medium", "low"]] = None


# ============================================================================
# Assistant Guidance Messages
# ============================================================================

GUIDANCE_CONFIDENCE_REJECTED = (
    "SHARPEN MODE STILL BINDING. "
    "The stopping line is too vague. Ask: 'How would you know it's done?' "
    "Then stop and wait. Do not suggest criteria."
)

GUIDANCE_MISSING_FRAMING = (
    "SHARPEN MODE STILL BINDING. "
    "initiative_framing parameter missing. Complete Step 1 first via frame_initiative_intent + frame_initiative_constraints."
)

GUIDANCE_MISSING_FOCUS = (
    "SHARPEN MODE STILL BINDING. "
    "focus_deliverable parameter missing. Complete Step 2 first via identify_e2e_deliverables + select_cutoff_deliverable."
)

GUIDANCE_EMPTY_DEFINITION = (
    "SHARPEN MODE STILL BINDING. "
    "Ask: 'What would be good enough that you could stop working on [focus_deliverable] this week and still feel it was worth the time?' "
    "Then stop and wait. Do not suggest."
)

GUIDANCE_CONFIRMED = (
    "SHARPEN COMPLETE.\n\n"
    "Present the full sharpened scope:\n"
    "- WHO: [who]\n"
    "- WHAT: [what]\n"
    "- WHY: [why]\n"
    "- CONSTRAINT: [constraint_type]: [constraint_value]\n"
    "- FOCUS DELIVERABLE: [focus_deliverable]\n"
    "- THIS WEEK'S GOOD ENOUGH: [good_enough_definition]\n\n"
    "Then say: 'You're sharpened. When you hit [good_enough_definition], you can stop for the week.'\n"
    "Do not add tasks. Do not suggest next steps. Do not offer to help plan."
)


# ============================================================================
# Tool Handler
# ============================================================================


async def handle(arguments: dict) -> mcp_types.CallToolResult:
    """Handle commit_week_deliverable tool call."""
    logger.debug("commit_week_deliverable.handle.start",
                 argument_keys=list(arguments.keys()))

    # Pydantic validation
    try:
        validated_request = CommitWeekDeliverableRequest.model_validate(arguments)
    except ValidationError as e:
        logger.warning("commit_week_deliverable.validation_failed", error=str(e.errors()))
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text="Invalid input format.")],
            structuredContent={"error": "validation_error", "details": e.errors()},
            isError=True,
        )

    # Convert to dicts for logic layer
    framing_dict = validated_request.initiative_framing.model_dump() if validated_request.initiative_framing else None
    focus_dict = validated_request.focus_deliverable.model_dump() if validated_request.focus_deliverable else None

    # Business logic validation
    result = validate_good_enough(
        framing=framing_dict,
        focus=focus_dict,
        good_enough=validated_request.good_enough_definition,
        confidence=validated_request.confidence,
    )

    # Handle validation failures
    if not result["valid"]:
        error_type = result["error_type"]
        error_details = result["error_details"]

        if error_type == "confidence_too_low":
            guidance = GUIDANCE_CONFIDENCE_REJECTED
            action = "ASK_CLARIFYING"
        elif error_type == "missing_framing":
            guidance = GUIDANCE_MISSING_FRAMING
            action = "REFUSE"
        elif error_type == "missing_focus":
            guidance = GUIDANCE_MISSING_FOCUS
            action = "REFUSE"
        elif error_type == "empty_definition":
            guidance = GUIDANCE_EMPTY_DEFINITION
            action = "ASK_CLARIFYING"
        else:
            guidance = (
                "An unexpected validation issue occurred. Ask the user to restate "
                "what 'good enough' means for this week. Do not suggest."
            )
            action = "ASK_CLARIFYING"

        logger.info("commit_week_deliverable.rejected",
                    error_type=error_type, action=action)

        structured = {
            "error": error_type,
            "details": error_details,
            "assistant_guidance": {
                "action": action,
                "instruction": guidance,
            },
        }
        if error_type == "confidence_too_low":
            structured["confidence_provided"] = validated_request.confidence

        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=error_details or f"Good enough issue: {error_type}",
            )],
            structuredContent=structured,
            isError=True,
        )

    # Valid — return confirmed stopping line
    sharpened = result["sharpened_scope"]

    logger.info("commit_week_deliverable.complete",
                focus=sharpened["focus_deliverable"]["name"],
                good_enough=sharpened["good_enough_definition"][:50],
                confidence="high")

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Sharpened. Focus: {sharpened['focus_deliverable']['name']}. "
                 f"Good enough this week: {sharpened['good_enough_definition']}",
        )],
        structuredContent={
            "sharpened_scope": sharpened,
            "confidence": "high",
            "confirmed": True,
            "assistant_guidance": {
                "action": "SHARPEN_COMPLETE",
                "instruction": GUIDANCE_CONFIRMED,
            },
        },
    )


# ============================================================================
# Self-register at import time
# ============================================================================

register_tool(ToolDefinition(
    name="commit_week_deliverable",
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    handle=handle,
    read_only_hint=False,
    destructive_hint=False,
    open_world_hint=False,
))
