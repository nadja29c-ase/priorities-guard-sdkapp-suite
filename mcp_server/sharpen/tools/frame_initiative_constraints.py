"""
Frame Initiative Constraints Tool.

Captures the dominant constraint and definition of finished.
Requires confirmed intent from frame_initiative_intent.
Self-registers at import time.
"""

from typing import Optional, Literal

import structlog
from mcp import types as mcp_types
from pydantic import BaseModel, ValidationError

from .base import ToolDefinition
from . import register_tool
from ..tool_logic import validate_initiative_constraints

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata (Goal-Oriented Description)
# ============================================================================

DESCRIPTION = """Records confirmed CONSTRAINT and DEFINITION OF FINISHED for an initiative. Without a clear constraint, scope expands endlessly. Without a definition of finished, work is never done. So this is an additional filter to maximize work not done later. Requires confidence="high".
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

CONFIDENCE EXAMPLES:
  HIGH: constraint_type="time" constraint_value="by March 15" definition_of_finished="Dashboard deployed and accessible to team". These are user confirmed.
  LOW:  constraint_type="time" constraint_value="soon" definition_of_finished="when it's done"
  HIGH: constraint_type="capacity" constraint_value="4 hours per week" definition_of_finished="API returns valid responses for all endpoints". These are user confirmed.
  LOW:  constraint_type="budget" constraint_value="flexible" definition_of_finished="ready to use"

If user claims "no constraints", set user_claims_no_constraints=true — backend will guide next steps.

EXAMPLE CONVERSATION:
  You: "What's the one constraint that limits this initiative most — a deadline, limited hours per week, or a budget cap?"
  User: "I only have about 3 hours a week to work on this"
  You: "3 hours per week — got it. How will you know the checklist is truly finished?"
  User: "When a new hire has used it and said it was helpful"
  You: "So it's finished when at least one new hire has used the checklist and confirmed it was helpful. Is that right?"
  User: "Yes"
  → Now call frame_initiative_constraints with constraint_type="capacity", constraint_value="3 hours per week", definition_of_finished="At least one new hire has used the checklist and confirmed it was helpful", confidence="high"."""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "constraint_type": {
            "type": "string",
            "enum": ["time", "capacity", "budget", "forced_mvp"],
            "description": "Which ONE constraint dominates: time (deadline), capacity (hours/sessions per week), budget, or forced_mvp (smallest result worth continuing). ACCORDING TO THE USER.",
        },
        "constraint_value": {
            "type": "string",
            "description": "The specific constraint in the user's own words (concrete, not vague like 'soon' or 'flexible').",
        },
        "definition_of_finished": {
            "type": "string",
            "description": "How will you know the WHAT is finished? Concrete, verifiable condition (not 'done' or 'ready'). ACCORDING TO THE USER.",
        },
        "user_claims_no_constraints": {
            "type": "boolean",
            "description": "Set true if user explicitly claims no constraints exist. Triggers forced_mvp flow to help the user define a minimal viable product.",
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "Your confidence that CONSTRAINT and DEFINITION OF FINISHED are concrete and user-confirmed. Must be 'high' to proceed.",
        },
    },
    "required": ["confidence"],
    "additionalProperties": False,
}


# ============================================================================
# Pydantic Models for Validation
# ============================================================================


class FrameConstraintsRequest(BaseModel):
    """Expected input structure from ChatGPT."""
    constraint_type: Optional[Literal["time", "capacity", "budget", "forced_mvp"]] = None
    constraint_value: Optional[str] = None
    definition_of_finished: Optional[str] = None
    user_claims_no_constraints: bool = False
    confidence: Optional[Literal["high", "medium", "low"]] = None


# ============================================================================
# Assistant Guidance Messages
# ============================================================================

GUIDANCE_CONFIDENCE_REJECTED = (
    "SHARPEN MODE STILL BINDING. "
    "Ask ONE question about CONSTRAINT or DEFINITION OF FINISHED (whichever is vaguer). "
    "Then stop and wait. Do not explain, suggest, or plan."
)

GUIDANCE_FORCE_CONSTRAINT = (
    "SHARPEN MODE STILL BINDING. "
    "Ask exactly: 'What's the smallest result that would make this worth continuing?' "
    "Then stop and wait. Do not suggest examples. Use their answer as forced_mvp."
)

GUIDANCE_MISSING_FIELDS = (
    "SHARPEN MODE STILL BINDING. "
    "Ask ONE question about the missing field. "
    "Then stop and wait. Do not explain, suggest, or plan."
)

GUIDANCE_CONFIRMED = (
    "Present the complete framing using the user's exact words: "
    "WHO, WHAT, WHY (if any), CONSTRAINT, DEFINITION OF FINISHED. "
    "Then ask: 'Is this correct?' Stop and wait. Do not elaborate or add context.\n\n"
    "If user confirms → call identify_e2e_deliverables.\n"
    "If user corrects → update the framing and re-confirm."
)


# ============================================================================
# Tool Handler
# ============================================================================


async def handle(arguments: dict) -> mcp_types.CallToolResult:
    """Handle frame_initiative_constraints tool call."""
    logger.debug("frame_initiative_constraints.handle.start",
                argument_keys=list(arguments.keys()))

    # Pydantic validation
    try:
        validated_request = FrameConstraintsRequest.model_validate(arguments)
    except ValidationError as e:
        logger.warning("frame_initiative_constraints.validation_failed", error=str(e.errors()))
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text="Invalid input format.")],
            structuredContent={"error": "validation_error", "details": e.errors()},
            isError=True,
        )

    # Reject low/medium confidence (except for user_claims_no_constraints flow)
    if not validated_request.user_claims_no_constraints and validated_request.confidence != "high":
        logger.info("frame_initiative_constraints.confidence_rejected",
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
    result = validate_initiative_constraints(
        constraint_type=validated_request.constraint_type,
        constraint_value=validated_request.constraint_value,
        definition_of_finished=validated_request.definition_of_finished,
        user_claims_no_constraints=validated_request.user_claims_no_constraints,
    )

    # Handle force constraint (user claimed no constraints)
    if result["force_constraint"]:
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="User claims no constraints. Ask for first small win.",
            )],
            structuredContent={
                "force_constraint": True,
                "assistant_guidance": {
                    "action": "ASK_CLARIFYING",
                    "instruction": GUIDANCE_FORCE_CONSTRAINT,
                },
            },
        )

    # If structurally invalid (missing fields)
    if not result["valid"]:
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=f"Missing required fields: {', '.join(result['missing'])}",
            )],
            structuredContent={
                "error": "missing_fields",
                "missing": result["missing"],
                "constraint_framing": result["constraint_framing"],
                "assistant_guidance": {
                    "action": "ASK_CLARIFYING",
                    "instruction": GUIDANCE_MISSING_FIELDS,
                },
            },
            isError=True,
        )

    # Valid — return confirmed constraint framing
    framing = result["constraint_framing"]

    logger.info("frame_initiative_constraints.complete",
                constraint_type=framing["constraint_type"],
                definition_of_finished=framing["definition_of_finished"][:50],
                confidence="high")

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Constraints confirmed: {framing['constraint_type']} — {framing['constraint_value']}. "
                 f"Finished when: {framing['definition_of_finished']}",
        )],
        structuredContent={
            "constraint_framing": framing,
            "confidence": "high",
            "confirmed": True,
            "assistant_guidance": {
                "action": "CONFIRM_FRAMING",
                "instruction": GUIDANCE_CONFIRMED,
            },
        },
    )


# ============================================================================
# Self-register at import time
# ============================================================================

register_tool(ToolDefinition(
    name="frame_initiative_constraints",
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    handle=handle,
    # OpenAI compliance annotations
    read_only_hint=False,  # Produces structured output for user
    destructive_hint=False,  # No data modification
    open_world_hint=False,  # No external API calls
))
