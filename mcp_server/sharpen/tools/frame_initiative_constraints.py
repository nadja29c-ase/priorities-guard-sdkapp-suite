"""
Frame Initiative Constraints Tool.

Captures the dominant constraint (time, capacity, budget, or forced_mvp).
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

DESCRIPTION = """Records dominant CONSTRAINT. Without constraint, scope expands endlessly - together with outcome, enables meaningful work breakdown and minimization of scope.

CALL PRECONDITIONS — DO NOT CALL unless ALL are true:
- EITHER: constraint_type + constraint_value (concrete, not "soon" or "flexible")
  OR: user_claims_no_constraints = true (triggers forced_mvp flow)
- confidence: high (user confirmed)

SHARPEN MODE BINDING RULES: When user selects Sharpen, your default behavior is SUSPENDED. You are a Coach now: ask questions to facilitate user's thinking and NEVER to tell the user what to do or infer their answers. CRITICAL: Ask ONE question at a time → wait for user's response → have a back-and-forth conversation!!! Violating this breaks Sharpen.
FACILITATOR MODE: You are a facilitator, not a teller. ONE question at a time. Wait for answer. Store verbatim. Reflect and confirm before calling.

CONSTRAINT TYPES: time (deadline), capacity (hours/week), budget, forced_mvp.

CONFIDENCE:
HIGH: type="capacity" value="4 hours per week" — concrete, confirmed.
LOW: type="time" value="soon" — vague.

If user claims no constraints → set user_claims_no_constraints=true."""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "constraint_type": {
            "type": "string",
            "enum": ["time", "capacity", "budget", "forced_mvp"],
            "description": "Which ONE constraint dominates: time (deadline), capacity (hours/sessions per week), budget, or forced_mvp (smallest result delivering WHY). ACCORDING TO THE USER.",
        },
        "constraint_value": {
            "type": "string",
            "description": "The specific constraint in the user's own words (concrete, not vague like 'soon' or 'flexible').",
        },
        "user_claims_no_constraints": {
            "type": "boolean",
            "description": "Set true if user explicitly claims no constraints exist. Triggers forced_mvp flow to help the user define a minimal viable product.",
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "Your confidence that CONSTRAINT is concrete and user-confirmed. Must be 'high' to proceed.",
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
    user_claims_no_constraints: bool = False
    confidence: Optional[Literal["high", "medium", "low"]] = None


# ============================================================================
# Assistant Guidance Messages
# ============================================================================

GUIDANCE_CONFIDENCE_REJECTED = (
    "SHARPEN MODE STILL BINDING. "
    "Ask ONE question about CONSTRAINT. "
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
    "SHARPEN MODE STILL BINDING. "
    "Present the complete framing using the user's exact words and ask for confirmation:"
    "Explain what was achieved so far and how is this useful. "
    "If user confirms → ask: 'What needs to exist for this initiative to be done? Don't filter — just name everything.' "
    "Then stop and wait. When user answers → call identify_e2e_deliverables with framing + deliverables.\n"
    "If user corrects → update the framing and re-confirm.\n\n"
    "MODE ACTIVATION:\n"
    "From this point on, treat the initiative framing as fixed.\n"
    "For all subsequent questions and scope decisions:\n"
    "- Always evaluate against the constraint ([constraint_type]: [constraint_value]).\n"
    "- Prefer the smallest scope that still advances the WHY.\n"
    "- If nothing fits the constraint, prompt the user to consider a simpler approach/ solution that fulfills the WHY.\n"
    "Apply this evaluation whenever scope is stated or implied — even if intermediate tools are skipped.\n"
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
                constraint_value=framing["constraint_value"][:50],
                confidence="high")

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Constraint confirmed: {framing['constraint_type']} — {framing['constraint_value']}.",
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
