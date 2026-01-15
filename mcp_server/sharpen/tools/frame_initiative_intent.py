"""
Frame Initiative Intent Tool.

Captures WHO benefits and WHAT must exist. WHY is optional.
Structural validation only — semantic quality is the LLM's job.
Self-registers at import time.
"""

from typing import Optional

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

DESCRIPTION = """Records the confirmed WHO and WHAT of an initiative after the user has articulated them clearly.

PURPOSE: This tool creates a checkpoint — it locks in the beneficiary and concrete outcome before breakdown begins. Without clear WHO and WHAT, you cannot evaluate what work to eliminate.

CALL ONLY WHEN:
- User has stated WHO benefits (specific person or group, not "someone", "people", "users")
- User has stated WHAT must exist (a concrete artifact or deliverable, not an activity like "work on X" or vague like "improve Y")
- User has confirmed both

DO NOT CALL when WHO or WHAT are still vague, abstract, or unconfirmed. Ask clarifying questions first.

FACILITATOR ROLE: Your job is to draw out clarity through questions. Never suggest what WHO or WHAT should be. Never give examples. Use the user's exact words."""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "who": {
            "type": "string",
            "description": "Who is supposed to benefit from this work getting done first and foremost?",
        },
        "what": {
            "type": "string",
            "description": "What artifact, deliverable, or handoff must exist?",
        },
        "why": {
            "type": "string",
            "description": "Optional: So that the beneficiary benefits in what specific way? Used to test clarity of WHAT, not required.",
        },
    },
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

    # Structural validation only
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

    logger.info("frame_initiative_intent.complete", who=intent["who"], what=intent["what"])

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Intent confirmed: {intent['who']} needs {intent['what']}" +
                 (f" so that {intent['why']}" if intent.get("why") else ""),
        )],
        structuredContent={
            "framing_intent": intent,
            "confirmed": True,
            "assistant_guidance": {
                "instruction": "Present the confirmed intent to the user. Then proceed to capture constraints by calling frame_initiative_constraints. Do not suggest what constraints might be — ask the user.",
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
