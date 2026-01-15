"""
Frame Initiative Constraints Tool.

Captures the dominant constraint and definition of finished.
Requires confirmed intent from frame_initiative_intent.
Structural validation only — semantic quality is the LLM's job.
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

DESCRIPTION = """Records the confirmed CONSTRAINT and DEFINITION OF FINISHED for an initiative.

PURPOSE: This tool locks in the dominant constraint and success criteria before breakdown begins. Without a clear constraint, scope expands endlessly. Without a definition of finished, work is never done.

REQUIRES: Confirmed intent from frame_initiative_intent (pass as confirmed_intent).

CALL ONLY WHEN:
- User has stated ONE dominant constraint:
  - time: specific deadline ("by March 15", "within 2 weeks")
  - capacity: specific availability ("4 hours per week", "2 focused sessions")
  - budget: specific limit ("under $500", "no external spend")
  - forced_mvp: smallest result worth continuing (use when user initially claimed no constraints)
- User has stated a concrete definition of finished (verifiable condition, not "done" or "ready")
- User has confirmed both

SPECIAL CASE — NO CONSTRAINTS CLAIMED:
If user says "no constraints", set user_claims_no_constraints=true.
Then ask: "What is the smallest concrete result that would make this initiative worth continuing?"
Use their answer as constraint_type="forced_mvp" with their answer as constraint_value.

DO NOT CALL when constraint or definition of finished are vague or unconfirmed. Ask clarifying questions first.

FACILITATOR ROLE: Your job is to surface real limits through questions. Never suggest constraints. Never estimate for the user. Wait for their numbers."""

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

    # Convert to dict for pure function
    confirmed_intent = None
    if validated_request.confirmed_intent:
        confirmed_intent = validated_request.confirmed_intent.model_dump()

    # Structural validation
    result = validate_initiative_constraints(
        confirmed_intent=confirmed_intent,
        constraint_type=validated_request.constraint_type,
        constraint_value=validated_request.constraint_value,
        definition_of_finished=validated_request.definition_of_finished,
        user_claims_no_constraints=validated_request.user_claims_no_constraints,
    )

    # Handle missing intent
    if result["intent_missing"]:
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="Confirmed intent is required. Call frame_initiative_intent first.",
            )],
            structuredContent={
                "error": "intent_missing",
                "assistant_guidance": {
                    "instruction": "Call frame_initiative_intent first and get user confirmation before capturing constraints.",
                },
            },
            isError=True,
        )

    # Handle force constraint (user claimed no constraints)
    if result["force_constraint"]:
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="User claims no constraints. Ask for smallest concrete result worth continuing.",
            )],
            structuredContent={
                "force_constraint": True,
                "assistant_guidance": {
                    "instruction": "Ask: 'What is the smallest concrete result that would make this initiative worth continuing?' Wait for their answer — do not suggest. Use their answer as constraint_type='forced_mvp' and constraint_value=their answer. Then call this tool again.",
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
                "initiative_framing": result["initiative_framing"],
                "assistant_guidance": {
                    "instruction": "Ask the user to provide the missing information. Do not suggest what it should be. Do not estimate for them.",
                },
            },
            isError=True,
        )

    # Valid — return confirmed framing
    framing = result["initiative_framing"]

    logger.info("frame_initiative_constraints.complete",
                constraint_type=framing["constraint_type"],
                definition_of_finished=framing["definition_of_finished"][:50])

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Framing complete: {framing['who']} needs {framing['what']}. "
                 f"Constraint: {framing['constraint_type']} — {framing['constraint_value']}. "
                 f"Finished when: {framing['definition_of_finished']}",
        )],
        structuredContent={
            "initiative_framing": framing,
            "confirmed": True,
            "assistant_guidance": {
                "instruction": "Present the complete framing to the user using their exact words. Ask them to confirm. Only after confirmation, proceed to Step 2 (deliverable identification). Do not suggest what deliverables might be.",
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
