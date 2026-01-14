"""
Frame Initiative Intent Tool.

Captures WHO benefits and WHAT must exist. WHY is optional.
Call iteratively until confidence is high.
Self-registers at import time.

FACILITATOR ROLE: Ask questions to draw out user's thinking.
Never suggest what WHO or WHAT should be. Never give advice.
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
# Tool Metadata
# ============================================================================

DESCRIPTION = """Capture the beneficiary and intended outcome of an initiative. Call iteratively until confidence is high. FACILITATOR ROLE: Ask questions to draw out user's thinking. Never suggest what WHO or WHAT should be. Never give advice."""

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
# Assistant Guidance Instructions
# ============================================================================

GUIDANCE_CLARIFY_WHO = """Ask ONE question to clarify who benefits from this work. Do not suggest who it should be. Do not give examples. Do not ask about constraints or deliverables yet. Your role is to facilitate their thinking, not direct it. Call this tool again with updated components."""

GUIDANCE_CLARIFY_WHAT = """Ask ONE question to clarify what must exist. Focus on artifact/deliverable, not activity. Do not suggest what it should be. Do not offer examples. Do not ask about constraints yet. Reflect their words back and ask them to make it more concrete. Call this tool again with updated components."""

GUIDANCE_CONFIRM = """Present the intent: '[WHO] needs [WHAT]' (include 'so that [WHY]' only if WHY was provided). Ask user to confirm — do not rephrase or improve their words. If confirmed, call frame_initiative_constraints with confirmed_intent. Do not skip to deliverables. Do not offer suggestions for next steps beyond the constraint question."""


# ============================================================================
# Tool Handler
# ============================================================================


async def handle(arguments: dict) -> mcp_types.CallToolResult:
    """
    Handle frame_initiative_intent tool call.

    Args:
        arguments: Raw arguments from ChatGPT

    Returns:
        CallToolResult with framing intent and guidance
    """
    logger.debug("frame_initiative_intent.handle.start",
                argument_keys=list(arguments.keys()))

    # ============================================================
    # VALIDATION
    # ============================================================
    try:
        validated_request = FrameIntentRequest.model_validate(arguments)
        logger.debug("frame_initiative_intent.validation_success")

    except ValidationError as e:
        logger.warning("frame_initiative_intent.validation_failed",
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

    # ============================================================
    # VALIDATE INTENT (call pure function)
    # ============================================================
    result = validate_initiative_intent(
        who=validated_request.who,
        what=validated_request.what,
        why=validated_request.why,
    )

    # ============================================================
    # BUILD RESPONSE (handler shapes MCP transport layer)
    # ============================================================
    logger.info("frame_initiative_intent.complete",
                confidence=result["confidence"],
                needs_clarification=result["needs_clarification"])

    # Determine action and guidance based on result
    if result["needs_clarification"]:
        if result["clarify_type"] == "WHO":
            action = "ASK_CLARIFYING"
            instruction = GUIDANCE_CLARIFY_WHO
        else:  # WHAT
            action = "ASK_CLARIFYING"
            instruction = GUIDANCE_CLARIFY_WHAT
    else:
        action = "CONFIRM_AND_PROCEED"
        instruction = GUIDANCE_CONFIRM

    # Build structuredContent
    structured_content = {
        "framing_intent": result["framing_intent"],
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

    # Build human-readable summary
    intent = result["framing_intent"]
    if result["confidence"] == "high":
        summary = f"Intent captured: {intent['who']} needs {intent['what']}"
        if intent.get("why"):
            summary += f" so that {intent['why']}"
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
    name="frame_initiative_intent",
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    handle=handle,
    # OpenAI compliance annotations
    read_only_hint=False,  # Produces structured output for user
    destructive_hint=False,  # No data modification
    open_world_hint=False,  # No external API calls
))
