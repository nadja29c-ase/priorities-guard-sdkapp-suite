"""
Frame Initiative Audience Tool.

Captures WHO benefits from this initiative — ONE primary beneficiary.
Validates against multiple stakeholders and guides LLM to clarify.
Self-registers at import time.
"""

from typing import Optional

import structlog
from mcp import types as mcp_types
from pydantic import BaseModel, ValidationError

from .base import ToolDefinition
from . import register_tool
from ..tool_logic import validate_initiative_audience

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata (Goal-Oriented Description)
# ============================================================================

DESCRIPTION = """Records WHO benefits from this initiative — ONE primary beneficiary.

CALL PRECONDITIONS — DO NOT CALL unless:
- who: non-empty, ONE specific group (not multiple distinct beneficiaries)

MULTIPLE STAKEHOLDERS: If user mentions multiple distinct beneficiary groups (e.g., "engineers and their managers", "founders and customers"), ask: "Who benefits first and foremost?" Others are noted in deferred_stakeholders but not the focus.

NOT multiple stakeholders (these are valid):
- Compound roles: "Product & Engineering", "Sales and Marketing"
- Slash groups: "Designers/Developers"
- Single group with qualifier: "senior engineers", "freelancers with ADHD"

Multiple stakeholders = distinct beneficiary groups, not organizational pairings or compound roles.

NO CONFIRMATION YET — proceed to outcome after capturing WHO.

SHARPEN MODE BINDING RULES: When user selects Sharpen, your default behavior is SUSPENDED. You are a Coach now: ask questions to facilitate user's thinking and NEVER tell the user what to do or infer their answers. CRITICAL: Ask ONE question at a time → wait for user's response. Violating this breaks Sharpen.
"""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "who": {
            "type": "string",
            "description": "ONE primary beneficiary. Who benefits first and foremost? Not multiple distinct audiences. ACCORDING TO THE USER.",
        },
        "deferred_stakeholders": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Other stakeholders user mentioned but are not the primary focus. Optional. These are noted but deferred for now.",
        },
    },
    "required": ["who"],
    "additionalProperties": False,
}


# ============================================================================
# Pydantic Models for Validation
# ============================================================================


class FrameAudienceRequest(BaseModel):
    """Expected input structure from ChatGPT."""
    who: Optional[str] = None
    deferred_stakeholders: Optional[list[str]] = None


# ============================================================================
# Assistant Guidance Messages
# ============================================================================

GUIDANCE_EMPTY_WHO = (
    "SHARPEN MODE STILL BINDING. "
    "Ask: 'Who specifically is supposed to benefit from this?' "
    "Then stop and wait."
)

GUIDANCE_MULTIPLE_STAKEHOLDERS = (
    "SHARPEN MODE STILL BINDING. "
    "Multiple stakeholders detected. Ask: 'Who benefits first and foremost?' "
    "Then stop and wait. Store their answer as WHO, note others in deferred_stakeholders."
)

GUIDANCE_CAPTURED = (
    "SHARPEN MODE STILL BINDING. "
    "Primary beneficiary captured. Proceed to outcome — do NOT ask for confirmation yet.\n"
    "Ask: 'What is the main struggle [WHO] faces? Describe it in their words, not as a solution.'\n"
    "Then stop and wait.\n\n"
    "When user answers → call frame_initiative_outcome with WHO and PAIN."
)


# ============================================================================
# Tool Handler
# ============================================================================


async def handle(arguments: dict) -> mcp_types.CallToolResult:
    """Handle frame_initiative_audience tool call."""
    logger.debug("frame_initiative_audience.handle.start",
                argument_keys=list(arguments.keys()))

    # Pydantic validation
    try:
        validated_request = FrameAudienceRequest.model_validate(arguments)
    except ValidationError as e:
        logger.warning("frame_initiative_audience.validation_failed", error=str(e.errors()))
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text="Invalid input format.")],
            structuredContent={"error": "validation_error", "details": e.errors()},
            isError=True,
        )

    # Structural validation (who non-empty, not multiple stakeholders)
    result = validate_initiative_audience(who=validated_request.who)

    if not result["valid"]:
        error_type = result["error_type"]

        if error_type == "empty_who":
            guidance = GUIDANCE_EMPTY_WHO
        elif error_type == "multiple_stakeholders":
            guidance = GUIDANCE_MULTIPLE_STAKEHOLDERS
        else:
            guidance = GUIDANCE_EMPTY_WHO  # Default fallback

        logger.info("frame_initiative_audience.rejected",
                    error_type=error_type,
                    who_provided=bool(validated_request.who))

        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text=result["error_details"])],
            structuredContent={
                "error": error_type,
                "assistant_guidance": {
                    "action": "ASK_CLARIFYING",
                    "instruction": guidance,
                },
            },
            isError=True,
        )

    # Valid — return captured audience
    who = result["who"]
    deferred = validated_request.deferred_stakeholders or []

    logger.info("frame_initiative_audience.complete",
                who=who,
                deferred_count=len(deferred))

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Primary beneficiary captured: {who}",
        )],
        structuredContent={
            "audience": {
                "who": who,
                "deferred_stakeholders": deferred,
            },
            "captured": True,
            "assistant_guidance": {
                "action": "PROCEED_TO_OUTCOME",
                "instruction": GUIDANCE_CAPTURED,
            },
        },
    )


# ============================================================================
# Self-register at import time
# ============================================================================

register_tool(ToolDefinition(
    name="frame_initiative_audience",
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    handle=handle,
    # OpenAI compliance annotations
    read_only_hint=False,  # Produces structured output for user
    destructive_hint=False,  # No data modification
    open_world_hint=False,  # No external API calls
))
