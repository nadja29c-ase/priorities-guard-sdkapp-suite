"""
Frame Initiative Constraints Tool.

Captures the dominant constraint and definition of finished.
Requires confirmed intent from frame_initiative_intent.
Rejects empty constraints — forces user to identify MVP.
Self-registers at import time.

FACILITATOR ROLE: Ask questions to surface user's real limits.
Never suggest constraints. Never give advice.
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
# Tool Metadata
# ============================================================================

DESCRIPTION = """Capture the dominant constraint and definition of finished for an initiative. Requires confirmed intent. Rejects empty constraints. FACILITATOR ROLE: Ask questions to surface user's real limits. Never suggest constraints. Never give advice."""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "confirmed_intent": {
            "type": "object",
            "description": "Confirmed output from frame_initiative_intent (required)",
            "properties": {
                "who": {"type": "string"},
                "what": {"type": "string"},
                "why": {"type": "string"},
            },
            "required": ["who", "what"],
        },
        # NOTE: forced_mvp behaves like a normal constraint_type in validation,
        # but is only set after user_claims_no_constraints forcing loop completes.
        "constraint_type": {
            "type": "string",
            "enum": ["time", "capacity", "budget", "forced_mvp"],
            "description": "Which constraint dominates: time (deadline), capacity (hours or focused sessions per week available), budget, or forced_mvp (smallest result worth continuing, used after user claimed no constraints).",
        },
        "constraint_value": {
            "type": "string",
            "description": "The specific constraint in the user's own words.",
        },
        "definition_of_finished": {
            "type": "string",
            "description": "How will you know the WHAT is finished? Concrete, verifiable condition.",
        },
        "user_claims_no_constraints": {
            "type": "boolean",
            "description": "Set true if user explicitly claims no constraints exist. Triggers forcing logic.",
        },
    },
    "required": ["confirmed_intent"],
    "additionalProperties": False,
}


# ============================================================================
# Pydantic Models for Validation
# ============================================================================


class ConfirmedIntent(BaseModel):
    """Confirmed intent from Tool 1."""
    who: str
    what: str
    why: Optional[str] = None


class FrameConstraintsRequest(BaseModel):
    """Expected input structure from ChatGPT."""
    confirmed_intent: Optional[ConfirmedIntent] = None
    constraint_type: Optional[Literal["time", "capacity", "budget", "forced_mvp"]] = None
    constraint_value: Optional[str] = None
    definition_of_finished: Optional[str] = None
    user_claims_no_constraints: bool = False


# ============================================================================
# Assistant Guidance Instructions
# ============================================================================

GUIDANCE_INTENT_MISSING = """Intent framing must be confirmed before capturing constraints. Call frame_initiative_intent first and get user confirmation. Do not assume or infer the intent — the user must state it."""

GUIDANCE_FORCE_CONSTRAINT = """User claims no constraints. Ask: 'What is the smallest concrete result that would make this initiative worth continuing?' Wait for their answer — do not suggest what it might be. Use their answer as the constraint for the next call. Do not accept 'no constraints'. Call this tool again with constraint_type='forced_mvp' and constraint_value set to their answer."""

GUIDANCE_CLARIFY_CONSTRAINT = """Ask ONE question to clarify the constraint. For time: 'By when?' For capacity: 'How many hours or focused sessions per week can you realistically invest?' For budget: 'What's the maximum spend?' Do not suggest values. Do not estimate for them. Wait for their number. Call this tool again with updated value."""

GUIDANCE_CLARIFY_FINISHED = """Ask ONE question to clarify definition of finished. Push for concrete and verifiable: 'How will you know [WHAT] is actually done — what will you see or be able to do?' Do not suggest criteria. Do not give examples. Reflect their vague answer back and ask them to make it concrete. Call this tool again with updated value."""

GUIDANCE_CONFIRM_COMPLETE = """Present complete initiative framing using their exact words: '[WHO] needs [WHAT]. Constraint: [CONSTRAINT_TYPE] — [CONSTRAINT_VALUE]. Finished when: [DEFINITION_OF_FINISHED].' Ask user to confirm. Do not rephrase, improve, or add to their words. Only after confirmation, proceed to Step 2 (deliverable identification). Do not suggest what deliverables might be."""


# ============================================================================
# Tool Handler
# ============================================================================


async def handle(arguments: dict) -> mcp_types.CallToolResult:
    """
    Handle frame_initiative_constraints tool call.

    Args:
        arguments: Raw arguments from ChatGPT

    Returns:
        CallToolResult with framing constraints and guidance
    """
    logger.debug("frame_initiative_constraints.handle.start",
                argument_keys=list(arguments.keys()))

    # ============================================================
    # VALIDATION
    # ============================================================
    try:
        validated_request = FrameConstraintsRequest.model_validate(arguments)
        logger.debug("frame_initiative_constraints.validation_success")

    except ValidationError as e:
        logger.warning("frame_initiative_constraints.validation_failed",
                      error=str(type(e).__name__),
                      details=str(e.errors()))
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="Invalid input format.",
            )],
            structuredContent={
                "error": "validation_error",
                "details": e.errors(),
            },
            isError=True,
        )

    # Convert Pydantic model to dict for pure function
    confirmed_intent = None
    if validated_request.confirmed_intent:
        confirmed_intent = validated_request.confirmed_intent.model_dump()

    # ============================================================
    # VALIDATE CONSTRAINTS (call pure function)
    # ============================================================
    result = validate_initiative_constraints(
        confirmed_intent=confirmed_intent,
        constraint_type=validated_request.constraint_type,
        constraint_value=validated_request.constraint_value,
        definition_of_finished=validated_request.definition_of_finished,
        user_claims_no_constraints=validated_request.user_claims_no_constraints,
    )

    # ============================================================
    # HANDLE MISSING INTENT (return error)
    # ============================================================
    if result["intent_missing"]:
        logger.warning("frame_initiative_constraints.intent_missing")
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="Confirmed intent is required. Call frame_initiative_intent first.",
            )],
            structuredContent={
                "error": "intent_missing",
                "assistant_guidance": {
                    "action": "CALL_INTENT_TOOL_FIRST",
                    "instruction": GUIDANCE_INTENT_MISSING,
                },
            },
            isError=True,
        )

    # ============================================================
    # BUILD RESPONSE (handler shapes MCP transport layer)
    # ============================================================
    logger.info("frame_initiative_constraints.complete",
                confidence=result["confidence"],
                force_constraint=result["force_constraint"],
                needs_clarification=result["needs_clarification"])

    # Determine action and guidance based on result
    if result["force_constraint"]:
        action = "FORCE_CONSTRAINT"
        instruction = GUIDANCE_FORCE_CONSTRAINT
    elif result["needs_clarification"]:
        if result["clarify_type"] == "CONSTRAINT":
            action = "ASK_CLARIFYING"
            instruction = GUIDANCE_CLARIFY_CONSTRAINT
        else:  # FINISHED
            action = "ASK_CLARIFYING"
            instruction = GUIDANCE_CLARIFY_FINISHED
    else:
        action = "CONFIRM_FRAMING_COMPLETE"
        instruction = GUIDANCE_CONFIRM_COMPLETE

    # Build structuredContent
    structured_content = {
        "initiative_framing": result["initiative_framing"],
        "confidence": result["confidence"],
        "needs_clarification": result["needs_clarification"],
        "assistant_guidance": {
            "action": action,
            "instruction": instruction,
        },
    }

    # Add clarify object only when needed
    if result["needs_clarification"] and result["clarify_type"]:
        structured_content["clarify"] = {
            "type": result["clarify_type"],
        }

    # Add force_constraint flag only when true
    if result["force_constraint"]:
        structured_content["force_constraint"] = True

    # Build human-readable summary
    framing = result["initiative_framing"]
    if result["confidence"] == "high":
        summary = f"Framing complete: {framing['who']} needs {framing['what']}. "
        summary += f"Constraint: {framing['constraint_type']} — {framing['constraint_value']}. "
        summary += f"Finished when: {framing['definition_of_finished']}"
    elif result["force_constraint"]:
        summary = "User claims no constraints. Ask for smallest concrete result worth continuing."
    else:
        summary = f"Clarification needed for {result['clarify_type']}."

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=summary)],
        structuredContent=structured_content,
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
