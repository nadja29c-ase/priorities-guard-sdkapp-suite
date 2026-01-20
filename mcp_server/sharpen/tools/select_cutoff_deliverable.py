"""
Select Cutoff Deliverable Tool.

Forces selection of WHERE work intentionally stops.
Supports selection (pick existing) or sculpting (combine/reshape).
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

DESCRIPTION = """Records the user's focus deliverable — either by selecting an existing one OR sculpting a new one that combines/reshapes confirmed deliverables. This defines the current scope boundary. No ordering, scheduling, or planning allowed. Requires confirmed deliverables from Step 2.1 and confidence="high".

SHARPEN MODE — BINDING RULES (not guidelines)
When user selects Sharpen, your default assistant behavior is SUSPENDED.

SUSPENDED BEHAVIORS:
- Recommending which deliverable to select
- Suggesting how to sculpt
- Bundling without user direction
- Offering to "do all of them"
- Planning or sequencing

ACTIVE BEHAVIORS:
- Ask ONE question at a time
- Wait for answer
- Reflect their choice back
- Ask for user confirmation
- Then call tool with confidence="high"

TWO WAYS TO SET FOCUS:

1. SELECT EXISTING: User picks one deliverable by exact name.
   → Use selected_deliverable_name

2. SCULPT NEW: User combines or tightens multiple deliverables into one.
   → Use sculpted_deliverable with name + replaces list

SCULPTING INVARIANT: A sculpted deliverable may ONLY combine or reduce scope from the deliverables it replaces. It must not introduce new outcomes, audiences, or success criteria beyond what was already confirmed. If the user's sculpt adds scope, flag it: 'This seems to add scope beyond what [replaced deliverables] covered. Sculpting should tighten, not expand. What can we remove?'

CRITICAL: Use exactly ONE method. If user says "API and Docs together", that's sculpting — create a new name that captures the combined scope. If user picks one as-is, that's selection.

EXAMPLE CONVERSATION (Selection):
  You: "Your constraint is capacity: 3 hours per week. Which ONE of these can you realistically finish within that AND would still count as done?"
  User: "Just the checklist — the RASCI doc can wait"
  You: "So 'First-week checklist' is the focus, given your 3 hours/week. RASCI is deferred. Correct?"
  User: "Yes"
  → Call with selected_deliverable_name="First-week checklist", confidence="high"

EXAMPLE CONVERSATION (None fit — escape hatch):
  You: "Your constraint is time: 2 weeks. Which ONE of these can you realistically finish within that?"
  User: "Honestly, none of them fit in 2 weeks"
  You: "Is there a simpler approach to move toward [why] within 2 weeks?"
  User: "Maybe just a Slack message with key contacts instead of a full checklist"
  You: "That's a different solution. What deliverable would exist?"
  User: "A pinned Slack message with 'who to ask for what'"
  → Restart deliverables with this simpler approach
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
            },
            "required": ["who", "what", "why", "constraint_type", "constraint_value"],
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
            "description": "Select ONE existing deliverable by exact name. Use this OR sculpted_deliverable, not both. ACCORDING TO THE USER.",
        },
        "sculpted_deliverable": {
            "type": "object",
            "description": "Define a NEW focus deliverable that combines or reshapes existing ones. Use this OR selected_deliverable_name, not both. ACCORDING TO THE USER.",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name for the sculpted deliverable. Must be concrete, not activity-based.",
                },
                "description": {
                    "type": "string",
                    "description": "What this sculpted deliverable includes.",
                },
                "replaces": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Names of confirmed deliverables this replaces. All names must exist in confirmed_deliverables.",
                    "minItems": 1,
                },
            },
            "required": ["name", "replaces"],
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "Your confidence that the selection/sculpt is user-confirmed. Must be 'high' to proceed.",
        },
    },
    "required": ["initiative_framing", "confirmed_deliverables", "confidence"],
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


class SculptedDeliverable(BaseModel):
    """User-defined focus deliverable that replaces confirmed ones."""
    name: Optional[str] = None
    description: Optional[str] = None
    replaces: Optional[List[str]] = None


class SelectCutoffRequest(BaseModel):
    """Expected input structure from ChatGPT."""
    initiative_framing: Optional[InitiativeFraming] = None
    confirmed_deliverables: Optional[List[DeliverableItem]] = None
    selected_deliverable_name: Optional[str] = None
    sculpted_deliverable: Optional[SculptedDeliverable] = None
    confidence: Optional[Literal["high", "medium", "low"]] = None


# ============================================================================
# Assistant Guidance Messages
# ============================================================================

GUIDANCE_CONFIDENCE_REJECTED = (
    "SHARPEN MODE STILL BINDING. "
    "Ask ONE question: 'Which one deliverable must exist first?' "
    "Then stop and wait. Do not suggest which to select."
)

GUIDANCE_SELECTION_NOT_FOUND = (
    "SHARPEN MODE STILL BINDING. "
    "Present the confirmed deliverable names. Ask: 'Which of these is the focus?' "
    "Then stop and wait. Do not suggest."
)

GUIDANCE_MISSING_FRAMING = (
    "SHARPEN MODE STILL BINDING. "
    "initiative_framing parameter missing. If framing was already confirmed, include it in the tool call. "
    "If not yet confirmed, complete framing first via frame_initiative_intent + frame_initiative_constraints."
)

GUIDANCE_MISSING_DELIVERABLES = (
    "SHARPEN MODE STILL BINDING. "
    "confirmed_deliverables parameter missing. If deliverables were already confirmed, include them in the tool call. "
    "If not yet confirmed, complete deliverables first via identify_e2e_deliverables."
)

GUIDANCE_DUPLICATE_NAMES = (
    "SHARPEN MODE STILL BINDING. "
    "Ask: 'Two deliverables have the same name. Which ones are actually distinct?' "
    "Then stop and wait. Do not suggest names."
)

GUIDANCE_BOTH_METHODS = (
    "SHARPEN MODE STILL BINDING. "
    "Ask: 'Are you selecting one deliverable as-is, or combining multiple into a tighter scope?' "
    "Then stop and wait."
)

GUIDANCE_NO_METHOD = (
    "SHARPEN MODE STILL BINDING. "
    "Ask: 'Given [constraint_type]: [constraint_value], which ONE of these can you realistically finish "
    "AND would still move you toward [why]?' "
    "Then stop and wait. Do not suggest."
)

GUIDANCE_EMPTY_SCULPT_NAME = (
    "SHARPEN MODE STILL BINDING. "
    "Ask: 'What would you call this combined scope?' "
    "Then stop and wait. Do not suggest a name."
)

GUIDANCE_EMPTY_REPLACES = (
    "SHARPEN MODE STILL BINDING. "
    "Ask: 'Which confirmed deliverables does this replace?' "
    "Then stop and wait."
)

GUIDANCE_INVALID_REPLACES = (
    "SHARPEN MODE STILL BINDING. "
    "Present the confirmed deliverable names. Ask: 'Which of these does the sculpted deliverable replace?' "
    "Then stop and wait."
)


def build_confirmed_guidance(
    focus_name: str,
    deferred_names: list[str],
    replaces: list[str] | None = None,
) -> str:
    """Build guidance for confirmed selection/sculpt."""
    if replaces:
        replaces_str = ", ".join(replaces)
        scope_intro = f"Sculpted focus: '{focus_name}' (replaces: {replaces_str})."
    else:
        scope_intro = f"Focus: '{focus_name}'."

    # Step 3: Time-boxing question
    step_3_question = (
        f"Ask: 'What would be good enough that you could stop working on {focus_name} this week and still feel it was worth the time?' "
        f"Then stop and wait. Do not suggest. When user answers → call commit_week_deliverable with their answer."
    )

    if deferred_names:
        deferred_str = ", ".join(deferred_names)
        return (
            f"Scope confirmed. {scope_intro} Deferred: {deferred_str}.\n\n"
            f"{step_3_question}"
        )
    else:
        return f"Scope confirmed. {scope_intro} Nothing deferred.\n\n{step_3_question}"


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
    sculpted_dict = validated_request.sculpted_deliverable.model_dump() if validated_request.sculpted_deliverable else None

    # Business logic validation
    result = validate_cutoff_selection(
        framing=framing_dict,
        deliverables=deliverables_list,
        selected_name=validated_request.selected_deliverable_name,
        sculpted=sculpted_dict,
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
            guidance = GUIDANCE_MISSING_FRAMING
            action = "REFUSE"
        elif error_type == "missing_deliverables":
            guidance = GUIDANCE_MISSING_DELIVERABLES
            action = "REFUSE"
        elif error_type == "duplicate_deliverable_names":
            guidance = GUIDANCE_DUPLICATE_NAMES
            action = "REFUSE"
        elif error_type == "both_selection_methods":
            guidance = GUIDANCE_BOTH_METHODS
            action = "ASK_CLARIFYING"
        elif error_type == "no_selection_method":
            guidance = GUIDANCE_NO_METHOD
            action = "ASK_CLARIFYING"
        elif error_type == "selection_not_found":
            guidance = GUIDANCE_SELECTION_NOT_FOUND
            action = "ASK_CLARIFYING"
        elif error_type == "empty_sculpt_name":
            guidance = GUIDANCE_EMPTY_SCULPT_NAME
            action = "ASK_CLARIFYING"
        elif error_type == "empty_replaces":
            guidance = GUIDANCE_EMPTY_REPLACES
            action = "ASK_CLARIFYING"
        elif error_type == "invalid_replaces":
            guidance = GUIDANCE_INVALID_REPLACES
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
                text=error_details or f"Selection issue: {error_type}",
            )],
            structuredContent=structured,
            isError=True,
        )

    # Valid — return focus and deferred deliverables
    focus = result["focus_deliverable"]
    deferred = result["deferred_deliverables"]
    deferred_names = [d["name"] for d in deferred]

    # Get replaces from internal field (only present for sculpted path)
    replaces = result.get("_internal_replaces")

    logger.info("select_cutoff_deliverable.complete",
                focus_deliverable=focus["name"],
                deferred_count=len(deferred),
                sculpted=replaces is not None,
                confidence="high")

    # Build dynamic guidance with actual deliverable names
    guidance = build_confirmed_guidance(
        focus_name=focus["name"],
        deferred_names=deferred_names,
        replaces=replaces,
    )

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
