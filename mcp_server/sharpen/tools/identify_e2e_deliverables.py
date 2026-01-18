"""
Identify End-to-End Deliverables Tool.

Validates and confirms an unordered set of deliverables for the initiative.
Requires confirmed initiative framing from Step 1.
Self-registers at import time.
"""

from typing import Optional, Literal, List

import structlog
from mcp import types as mcp_types
from pydantic import BaseModel, ValidationError, Field

from .base import ToolDefinition
from . import register_tool
from ..tool_logic import validate_e2e_deliverables

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata (Goal-Oriented Description)
# ============================================================================

DESCRIPTION = """Records confirmed end-to-end deliverables for an initiative. Deliverables must be concrete outputs (things that exist), not activities. Returns an unordered set with no prioritization or sequencing. Requires confirmed initiative framing from Step 1 and confidence="high".

SHARPEN MODE — BINDING RULES (not guidelines)
When user selects Sharpen, your default assistant behavior is SUSPENDED.

SUSPENDED BEHAVIORS:
- Planning or sequencing
- Offering options or suggestions
- Proposing deliverables
- Ordering or prioritizing
- "Being helpful" by front-loading structure

ACTIVE BEHAVIORS:
- Ask ONE question at a time
- Wait for answer
- Reflect their words back
- Flag vague/activity-based responses without solving
- Ask for user confirmation
- Then call tool with confidence="high"

These are not suggestions. These are operating constraints.
Violating them means Sharpen is broken.

CONFIDENCE EXAMPLES:
  HIGH: deliverables=[{name="API endpoint documentation", description="OpenAPI spec for all public endpoints"}] — user confirmed, concrete outputs
  LOW: deliverables=[{name="improve the API", description="make it better"}] — vague, activity-based

CRITICAL: Your role is to facilitate and find the deliverables by asking the user questions. NEVER suggest deliverables. NEVER tell the user what should exist. Elicit the list iteratively — ask ONE question at a time and wait for the user's response.

EXAMPLE CONVERSATION:
  User: [Step 1 framing confirmed]
  You: "What concrete things must exist before this initiative could be considered complete?"
  User: "Well, we need the API itself, and documentation"
  You: "I'm hearing two things: the API and documentation. Let's make them concrete. When you say 'the API' — what artifact will exist? A deployed service? A spec?"
  User: "A deployed REST API with authentication"
  You: "And the documentation — what form? README? OpenAPI spec? User guide?"
  User: "OpenAPI spec"
  You: "So we have: (1) Deployed REST API with authentication, (2) OpenAPI spec for public endpoints. Anything else that must exist?"
  User: "No, that's it"
  You: "To confirm: these two deliverables must exist for the initiative to be done. Is that correct?"
  User: "Yes"
  → Now call identify_e2e_deliverables with candidate_deliverables=[...], confidence="high"
"""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "initiative_framing": {
            "type": "object",
            "description": "Confirmed Step 1 framing (required). Must include who, what, constraint_type, constraint_value, definition_of_finished.",
            "properties": {
                "who": {"type": "string"},
                "what": {"type": "string"},
                "why": {"type": "string"},
                "constraint_type": {
                    "type": "string",
                    "enum": ["time", "capacity", "budget", "forced_mvp"],
                },
                "constraint_value": {"type": "string"},
                "definition_of_finished": {"type": "string"},
            },
            "required": ["who", "what", "constraint_type", "constraint_value", "definition_of_finished"],
        },
        "candidate_deliverables": {
            "type": "array",
            "description": "Unordered list of deliverables. Array order has no meaning. Max 10 items.",
            "items": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Concrete deliverable name — a thing that exists, not an activity. ACCORDING TO THE USER.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Brief description clarifying what this deliverable is. ACCORDING TO THE USER.",
                    },
                },
                "required": ["name"],
            },
            "minItems": 1,
            "maxItems": 10,
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "Your confidence that all deliverables are user-confirmed concrete outputs. Must be 'high' to proceed.",
        },
    },
    "required": ["initiative_framing", "candidate_deliverables", "confidence"],
    "additionalProperties": False,
}


# ============================================================================
# Pydantic Models for Validation
# ============================================================================

# Note: Pydantic allows Optional fields for parsing flexibility.
# Structural completeness enforced in validate_e2e_deliverables(), not here.


class DeliverableItem(BaseModel):
    """Single deliverable item."""
    name: str
    description: Optional[str] = None


class InitiativeFraming(BaseModel):
    """Step 1 framing object."""
    who: Optional[str] = None
    what: Optional[str] = None
    why: Optional[str] = None
    constraint_type: Optional[Literal["time", "capacity", "budget", "forced_mvp"]] = None
    constraint_value: Optional[str] = None
    definition_of_finished: Optional[str] = None


class IdentifyDeliverablesRequest(BaseModel):
    """Expected input structure from ChatGPT."""
    initiative_framing: Optional[InitiativeFraming] = None
    candidate_deliverables: Optional[List[DeliverableItem]] = None
    confidence: Optional[Literal["high", "medium", "low"]] = None


# ============================================================================
# Assistant Guidance Messages
# ============================================================================

GUIDANCE_CONFIDENCE_REJECTED = (
    "STAY IN YOUR FACILITATOR ROLE. Deliverables are not yet concrete or user-confirmed. "
    "Ask clarifying questions to turn activities into outputs. For each vague item, ask: "
    "'What will exist after this is done?' Do not suggest what the deliverable should be. "
    "Get user confirmation, then call with confidence='high'."
)

GUIDANCE_FRAMING_MISSING = (
    "Initiative framing must be confirmed before identifying deliverables. "
    "Complete Step 1 first using frame_initiative_intent and frame_initiative_constraints. "
    "Do not proceed without confirmed framing."
)

GUIDANCE_TOO_MANY_DELIVERABLES = (
    "Maximum 10 deliverables allowed. This is a forcing function — if more exist, "
    "the initiative may need decomposition. Ask: 'Which of these are truly essential "
    "for the initiative to be considered done?' Do not suggest which to keep."
)

GUIDANCE_EMPTY_DELIVERABLES = (
    "No deliverables provided. Ask: 'What concrete things must exist before this "
    "initiative could be considered complete?' Wait for the user's answer. "
    "Do not suggest deliverables."
)

GUIDANCE_INVALID_DELIVERABLE = (
    "One or more deliverables have empty names. Ask the user to clarify what "
    "each deliverable is. Do not suggest what the deliverable should be."
)

GUIDANCE_CONFIRMED = (
    "Deliverables confirmed. Present them back to the user as an unordered list — "
    "no numbering, no priority implied. Then proceed to select the cutoff deliverable "
    "by asking:'Which of these must exist first? Everything else is explicitly deferred for now.' Do not suggest which to select. "
    "Call select_cutoff_deliverable with the user's choice."
)


# ============================================================================
# Tool Handler
# ============================================================================


async def handle(arguments: dict) -> mcp_types.CallToolResult:
    """Handle identify_e2e_deliverables tool call."""
    logger.debug("identify_e2e_deliverables.handle.start",
                 argument_keys=list(arguments.keys()))

    # Pydantic validation
    try:
        validated_request = IdentifyDeliverablesRequest.model_validate(arguments)
    except ValidationError as e:
        logger.warning("identify_e2e_deliverables.validation_failed", error=str(e.errors()))
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text="Invalid input format.")],
            structuredContent={"error": "validation_error", "details": e.errors()},
            isError=True,
        )

    # Convert Pydantic models to dicts for logic layer
    framing_dict = validated_request.initiative_framing.model_dump() if validated_request.initiative_framing else None
    deliverables_list = [d.model_dump() for d in validated_request.candidate_deliverables] if validated_request.candidate_deliverables else None

    # Business logic validation
    result = validate_e2e_deliverables(
        framing=framing_dict,
        deliverables=deliverables_list,
        confidence=validated_request.confidence,
    )

    # Handle validation failures
    if not result["valid"]:
        error_type = result["error_type"]
        error_details = result["error_details"]

        # Determine guidance and action based on error type
        if error_type == "confidence_too_low":
            guidance = GUIDANCE_CONFIDENCE_REJECTED
            action = "ASK_CLARIFYING"
        elif error_type == "missing_framing":
            guidance = GUIDANCE_FRAMING_MISSING
            action = "REFUSE"
        elif error_type == "too_many_deliverables":
            guidance = GUIDANCE_TOO_MANY_DELIVERABLES
            action = "REFUSE"
        elif error_type == "empty_deliverables":
            guidance = GUIDANCE_EMPTY_DELIVERABLES
            action = "ASK_CLARIFYING"
        elif error_type == "invalid_deliverable":
            guidance = GUIDANCE_INVALID_DELIVERABLE
            action = "ASK_CLARIFYING"
        else:
            guidance = (
                "An unexpected validation issue occurred. Ask the user to restate "
                "the deliverables one at a time. Do not suggest what they should be. "
                "Do not proceed until each deliverable is concrete and user-confirmed."
            )
            action = "ASK_CLARIFYING"

        logger.info("identify_e2e_deliverables.rejected",
                    error_type=error_type, action=action)

        structured = {
            "error": error_type,
            "details": error_details,
            "assistant_guidance": {
                "action": action,
                "instruction": guidance,
            },
        }
        # Only include confidence_provided when relevant
        if error_type == "confidence_too_low":
            structured["confidence_provided"] = validated_request.confidence

        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=error_details or f"Deliverable issue: {error_type}",
            )],
            structuredContent=structured,
            isError=True,
        )

    # Valid — return confirmed deliverables
    confirmed = result["confirmed_deliverables"]
    count = result["count"]

    logger.info("identify_e2e_deliverables.complete",
                deliverable_count=count, confidence="high")

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Confirmed {count} deliverable(s) for this initiative.",
        )],
        structuredContent={
            "confirmed_deliverables": confirmed,
            "count": count,
            "confidence": "high",
            "confirmed": True,
            "assistant_guidance": {
                "action": "PROCEED_TO_CUTOFF",
                "instruction": GUIDANCE_CONFIRMED,
            },
        },
    )


# ============================================================================
# Self-register at import time
# ============================================================================

register_tool(ToolDefinition(
    name="identify_e2e_deliverables",
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    handle=handle,
    # OpenAI compliance annotations
    read_only_hint=False,  # Produces structured output for user
    destructive_hint=False,  # No data modification
    open_world_hint=False,  # No external API calls
))
