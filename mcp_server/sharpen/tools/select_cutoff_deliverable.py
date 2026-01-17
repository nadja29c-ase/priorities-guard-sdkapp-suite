"""
Select Cutoff Deliverable Tool.

Forces selection of WHERE work intentionally stops.
Requires confirmed deliverables from Step 2.1.
Self-registers at import time.
"""

from typing import Optional, Literal, List

import structlog
from mcp import types as mcp_types
from pydantic import BaseModel, ValidationError

from .base import ToolDefinition
from . import register_tool
from ..tool_logic import validate_cutoff_selection

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata (Goal-Oriented Description)
# ============================================================================

DESCRIPTION = """Records the user's selected cutoff deliverable — the point where work intentionally stops for now. This defines the current scope boundary. No ordering, scheduling, or planning allowed. Requires confirmed deliverables from Step 2.1 and confidence="high".

SHARPEN MODE — BINDING RULES (not guidelines)
When user selects Sharpen, your default assistant behavior is SUSPENDED.

SUSPENDED BEHAVIORS:
- Recommending which deliverable to select
- Suggesting "you could also..."
- Bundling multiple deliverables
- Offering to "do all of them"
- Planning or sequencing

ACTIVE BEHAVIORS:
- Ask ONE question at a time
- Wait for answer
- Reflect their choice back
- Ask for user confirmation
- Then call tool with confidence="high"

CRITICAL: Exactly ONE deliverable must be selected. No bundling. No "depends." No "not sure yet." If user resists choosing, ask: 'If you stopped after this deliverable, would the initiative still be worth doing?' Do not decide for them.

EXAMPLE CONVERSATION:
  You: "If you could only complete one of these deliverables right now, which would still make the initiative worth doing?"
  User: "I guess the API itself — without that, nothing else matters"
  You: "So if you stopped after 'Deployed REST API with authentication', the initiative would still be worth doing. The documentation would be explicitly deferred. Is that correct?"
  User: "Yes"
  → Now call select_cutoff_deliverable with selected_deliverable_name="Deployed REST API with authentication", confidence="high"
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
                "definition_of_finished": {"type": "string"},
            },
            "required": ["who", "what", "constraint_type", "constraint_value", "definition_of_finished"],
        },
        "confirmed_deliverables": {
            "type": "array",
            "description": "Confirmed deliverables from identify_e2e_deliverables.",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["name"],
            },
            "minItems": 1,
        },
        "selected_deliverable_name": {
            "type": "string",
            "description": "Name of the deliverable chosen as the cutoff point. Must match exactly one name in confirmed_deliverables. ACCORDING TO THE USER.",
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "Your confidence that the selection is user-confirmed. Must be 'high' to proceed.",
        },
    },
    "required": ["initiative_framing", "confirmed_deliverables", "selected_deliverable_name", "confidence"],
    "additionalProperties": False,
}


# ============================================================================
# Pydantic Models for Validation
# ============================================================================

# Note: Pydantic allows Optional fields for parsing flexibility.
# Structural completeness enforced in validate_cutoff_selection(), not here.


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


class SelectCutoffRequest(BaseModel):
    """Expected input structure from ChatGPT."""
    initiative_framing: Optional[InitiativeFraming] = None
    confirmed_deliverables: Optional[List[DeliverableItem]] = None
    selected_deliverable_name: Optional[str] = None
    confidence: Optional[Literal["high", "medium", "low"]] = None


# ============================================================================
# Assistant Guidance Messages
# ============================================================================

GUIDANCE_CONFIDENCE_REJECTED = (
    "STAY IN YOUR FACILITATOR ROLE. The selection is not yet user-confirmed. "
    "Ask: 'If you stopped after [their tentative choice], would the initiative "
    "still be worth doing?' Wait for their answer. Do not suggest which to select. "
    "Get explicit confirmation, then call with confidence='high'."
)

GUIDANCE_SELECTION_NOT_FOUND = (
    "The selected deliverable does not match any confirmed deliverable. "
    "Present the list of confirmed deliverables and ask the user to select "
    "one by name. Do not suggest which to select."
)

GUIDANCE_MISSING_FRAMING_OR_DELIVERABLES = (
    "Cannot select cutoff without confirmed framing and deliverables. "
    "Complete Step 1 and Step 2.1 first."
)

GUIDANCE_EMPTY_SELECTION = (
    "No deliverable was selected. Ask: 'If you could only complete one of these "
    "deliverables right now, which would still make the initiative worth doing?' "
    "Wait for the user's answer. Do not suggest which to select."
)


def build_confirmed_guidance(focus_name: str, deferred_names: list[str]) -> str:
    """Build guidance for confirmed selection."""
    if deferred_names:
        deferred_str = ", ".join(deferred_names)
        return (
            f"Scope boundary confirmed. Present: 'Focus deliverable: {focus_name}. "
            f"Deferred for now: {deferred_str}.' Then proceed to Step 3: work breakdown "
            f"for the focus deliverable only. Do not discuss deferred items. Do not suggest "
            f"tasks. Ask: 'What work items must be completed to produce {focus_name}?'"
        )
    else:
        return (
            f"Scope boundary confirmed. Present: 'Focus deliverable: {focus_name}.' "
            f"Then proceed to Step 3: work breakdown for the focus deliverable only. "
            f"Do not suggest tasks. Ask: 'What work items must be completed to produce "
            f"{focus_name}?'"
        )


# ============================================================================
# Tool Handler
# ============================================================================


async def handle(arguments: dict) -> mcp_types.CallToolResult:
    """Handle select_cutoff_deliverable tool call."""
    logger.debug("select_cutoff_deliverable.handle.start",
                 argument_keys=list(arguments.keys()))

    # Pydantic validation
    try:
        validated_request = SelectCutoffRequest.model_validate(arguments)
    except ValidationError as e:
        logger.warning("select_cutoff_deliverable.validation_failed", error=str(e.errors()))
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text="Invalid input format.")],
            structuredContent={"error": "validation_error", "details": e.errors()},
            isError=True,
        )

    # Convert Pydantic models to dicts for logic layer
    framing_dict = validated_request.initiative_framing.model_dump() if validated_request.initiative_framing else None
    deliverables_list = [d.model_dump() for d in validated_request.confirmed_deliverables] if validated_request.confirmed_deliverables else None

    # Business logic validation
    result = validate_cutoff_selection(
        framing=framing_dict,
        deliverables=deliverables_list,
        selected_name=validated_request.selected_deliverable_name,
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
            guidance = GUIDANCE_MISSING_FRAMING_OR_DELIVERABLES
            action = "REFUSE"
        elif error_type == "missing_deliverables":
            guidance = GUIDANCE_MISSING_FRAMING_OR_DELIVERABLES
            action = "REFUSE"
        elif error_type == "empty_selection":
            guidance = GUIDANCE_EMPTY_SELECTION
            action = "ASK_CLARIFYING"
        elif error_type == "selection_not_found":
            guidance = GUIDANCE_SELECTION_NOT_FOUND
            action = "ASK_CLARIFYING"
        else:
            guidance = (
                "An unexpected validation issue occurred. Ask the user to restate "
                "which deliverable they want to focus on. Do not suggest which to select. "
                "Do not proceed until the selection is explicit and user-confirmed."
            )
            action = "ASK_CLARIFYING"

        logger.info("select_cutoff_deliverable.rejected",
                    error_type=error_type, action=action)

        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=error_details or f"Validation failed: {error_type}",
            )],
            structuredContent={
                "error": error_type,
                "confidence_provided": validated_request.confidence if error_type == "confidence_too_low" else None,
                "details": error_details,
                "assistant_guidance": {
                    "action": action,
                    "instruction": guidance,
                },
            },
            isError=True,
        )

    # Valid — return focus and deferred deliverables
    focus = result["focus_deliverable"]
    deferred = result["deferred_deliverables"]

    logger.info("select_cutoff_deliverable.complete",
                focus_deliverable=focus["name"],
                deferred_count=len(deferred),
                confidence="high")

    # Build dynamic guidance with actual deliverable names
    deferred_names = [d["name"] for d in deferred]
    guidance = build_confirmed_guidance(focus["name"], deferred_names)

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Scope boundary confirmed. Focus: {focus['name']}. Deferred: {len(deferred)} deliverable(s).",
        )],
        structuredContent={
            "focus_deliverable": focus,
            "scope_boundary": "explicit",
            "deferred_deliverables": deferred,
            "confidence": "high",
            "confirmed": True,
            "assistant_guidance": {
                "action": "PROCEED_TO_STEP_3",
                "instruction": guidance,
            },
        },
    )


# ============================================================================
# Self-register at import time
# ============================================================================

register_tool(ToolDefinition(
    name="select_cutoff_deliverable",
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    handle=handle,
    # OpenAI compliance annotations
    read_only_hint=False,  # Produces structured output for user
    destructive_hint=False,  # No data modification
    open_world_hint=False,  # No external API calls
))
