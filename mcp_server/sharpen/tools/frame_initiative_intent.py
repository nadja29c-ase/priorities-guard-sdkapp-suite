"""
Frame Initiative Intent Tool.

Captures WHO benefits and WHAT must exist. WHY is optional.
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

DESCRIPTION = """Records confirmed WHO and WHAT of an initiative. This help frame the initiative as outcome-focused so that later the amount of work can be minimized based on outcome. Requires confidence="high".

CONFIDENCE EXAMPLES:
  HIGH: who="The sales team" what="A CRM integration that syncs contacts daily". These are user confirmed.
  LOW:  who="users" what="improve the onboarding experience". 
  HIGH: who="My team lead" what="A deployment runbook with rollback steps". These are user confirmed.
  LOW:  who="stakeholders" what="work on the infrastructure"

Backend rejects confidence="low" or "medium". Only call when WHO is specific (not "users"/"people") and WHAT is a concrete artifact (not an activity like "work on X").

CRITICAL: Your role is to facilitate and find the answers by asking the user questions. NEVER suggest answers for the user. NEVER tell the user how to frame the initiative correctly. Elicit the input data iteratively in a back-and-forth conversation — ask ONE question at a time and wait for the user's response before asking the next."""

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
            "description": "Optional: So that the beneficiary benefits in what specific way? ACCORDING TO THE USER. Used to find the value of the output (WHAT), this creates the outcome-focus.",
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "Your confidence that WHO and WHAT are concrete and user-confirmed. Must be 'high' to proceed.",
        },
    },
    "required": ["who", "what", "confidence"],
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
                    "instruction": "STAY IN YOUR FACILITATOR ROLE and ask the user clarifying questions until WHO is specific and WHAT is a concrete artifact. Get user confirmation, then call with confidence='high'.",
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
                    "instruction": "Ask the user to provide the missing information. Do not suggest what it should be.",
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
            text=f"Intent confirmed: {intent['who']} needs {intent['what']}" +
                 (f" so that {intent['why']}" if intent.get("why") else ""),
        )],
        structuredContent={
            "framing_intent": intent,
            "confidence": "high",
            "confirmed": True,
            "assistant_guidance": {
                "instruction": "Proceed with further framing the initiative and capture the one most dominant initiative constraint by calling frame_initiative_constraints. NEVER suggest what constraints might be — ask the user.",
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
