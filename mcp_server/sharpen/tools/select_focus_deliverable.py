"""
Select Focus Deliverable Tool.

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

DESCRIPTION = """Records the user's focus deliverable after the realism/value evaluation loop has run.

CALL PRECONDITIONS — DO NOT CALL unless ALL are true:
- initiative_framing: confirmed from prior steps
- confirmed_deliverables: from identify_e2e_deliverables
- deferred_deliverables: list of deferred names (can be empty if user confirms none need deferring)
- EITHER selected_deliverable_name (exact match from remaining)
  OR sculpted_deliverable (with name + replaces list)
- confidence: high

NO CONFIRMATION — Do not ask "Correct?" after selection. Just proceed to commit_week_deliverable.

SHARPEN MODE — BINDING RULES (not guidelines)
When user selects Sharpen, your default assistant behavior is SUSPENDED.

SUSPENDED BEHAVIORS:
- Recommending which deliverable to select
- Suggesting how to sculpt
- Bundling without user direction
- Offering to "do all of them"
- Planning or sequencing
- Asking what to REMOVE/cut during focus selection (use KEEP/FOCUS language instead)

ACTIVE BEHAVIORS:
- Ask ONE question at a time
- Wait for answer
- Reflect their choice back
- Ask for user confirmation
- Then call tool with confidence="high"

REALISM/VALUE LOOP (runs BEFORE this tool):
After identify_e2e_deliverables confirms the deliverable list, evaluate each against constraints:
1. "Given [constraint_type]: [constraint_value], can [deliverable] realistically be completed?"
2. "Does [deliverable] directly deliver value to [who] for [why]?"

Deliverables that fail either check are DEFERRED by the user. This produces:
- deferred_deliverables: what didn't survive the loop
- remaining: what survived (confirmed minus deferred)

CRITICAL: The loop must run. If user claims "all are realistic", confirm explicitly:
"You're saying all [N] deliverables can be completed within [constraint]? None need to be deferred?"

FOCUS SELECTION (this tool):
After loop completes, select focus from REMAINING deliverables (not from full confirmed list).

TWO WAYS TO SET FOCUS:

1. SELECT EXISTING: User picks one remaining deliverable by exact name.
   → Use selected_deliverable_name

2. SCULPT NEW: User combines or tightens multiple remaining deliverables into one.
   → Use sculpted_deliverable with name + replaces list

AUTO-SELECT: If only ONE deliverable remains after deferrals, it automatically becomes focus.

OVER-CUTTING: If ZERO deliverables remain, error — user deferred too much. Re-evaluate.

SCULPTING INVARIANT: A sculpted deliverable may ONLY combine or reduce scope from the deliverables it replaces. It must not introduce new outcomes, audiences, or success criteria beyond what was already confirmed.

EXAMPLE CONVERSATION (with deferrals):
  [After identify_e2e_deliverables confirmed: "API", "Docs", "Tests"]
  You: "Given your constraint of 2 weeks, can all three realistically be completed?"
  User: "No, tests would take too long"
  You: "So 'Tests' is deferred. Between 'API' and 'Docs', which ONE must exist first to deliver value to [who]?"
  User: "API — docs can come later"
  → Call with deferred_deliverables=["Tests", "Docs"], selected_deliverable_name="API", confidence="high"

EXAMPLE CONVERSATION (auto-select after deferrals):
  [After identify_e2e_deliverables confirmed: "Checklist", "RASCI doc", "Buddy program"]
  You: "Given 3 hours/week, can all three realistically be completed?"
  User: "No way — just the checklist maybe"
  You: "So 'RASCI doc' and 'Buddy program' are deferred. 'Checklist' is the focus."
  → Call with deferred_deliverables=["RASCI doc", "Buddy program"], selected_deliverable_name="Checklist", confidence="high"

EXAMPLE CONVERSATION (all realistic — explicit confirmation):
  [After identify_e2e_deliverables confirmed: "Landing page", "Contact form"]
  You: "Given your constraint of 1 month, can both realistically be completed?"
  User: "Yes, both are doable"
  You: "Confirming: no deferrals needed — both 'Landing page' and 'Contact form' fit within 1 month. Which ONE is the focus?"
  User: "Landing page"
  → Call with deferred_deliverables=[], selected_deliverable_name="Landing page", confidence="high"
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
        "deferred_deliverables": {
            "type": "array",
            "description": "Deliverables explicitly deferred during realism/value evaluation. Names must match confirmed_deliverables. Can be empty ONLY after explicit confirmation that all deliverables are realistic within the constraint. ACCORDING TO THE USER — never infer deferrals.",
            "items": {"type": "string"},
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
    "required": ["initiative_framing", "confirmed_deliverables", "deferred_deliverables", "confidence"],
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


class SelectFocusRequest(BaseModel):
    """Expected input structure from ChatGPT."""
    initiative_framing: Optional[InitiativeFraming] = None
    confirmed_deliverables: Optional[List[DeliverableItem]] = None
    deferred_deliverables: List[str]
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

GUIDANCE_MISSING_DEFERRED = (
    "SHARPEN MODE STILL BINDING. "
    "deferred_deliverables parameter missing. Run the realism/value loop first: "
    "For each confirmed deliverable, ask 'Given [constraint], can this realistically be completed?' "
    "Collect deferrals, then call this tool with the list (can be empty if all survived)."
)

GUIDANCE_INVALID_DEFERRED = (
    "SHARPEN MODE STILL BINDING. "
    "Some deferred names don't match confirmed deliverables. "
    "Present the confirmed deliverable names. Ask: 'Which of these should be deferred?' "
    "Then stop and wait."
)

GUIDANCE_OVER_CUTTING = (
    "SHARPEN MODE STILL BINDING. "
    "All deliverables were deferred — nothing remains to focus on. "
    "Ask: 'You've deferred everything. Which ONE deliverable should we keep in scope?' "
    "Then stop and wait."
)

GUIDANCE_AUTO_SELECTED = (
    "SHARPEN MODE STILL BINDING. "
    "Only one deliverable remained after deferrals — auto-selected as focus. "
    "Scope confirmed. Focus: [focus_name]. Deferred: [deferred_list].\n\n"
    "Proceed to Step 3: commit_week_deliverable."
)

GUIDANCE_AMBIGUOUS_REMAINING = (
    "SHARPEN MODE STILL BINDING. "
    "Multiple deliverables remain after deferrals. "
    "Ask: 'Between [remaining], which ONE must exist first to deliver value to [who]?' "
    "Then stop and wait. Do not suggest."
)

GUIDANCE_SELECTION_WAS_DEFERRED = (
    "SHARPEN MODE STILL BINDING. "
    "The selected deliverable was already deferred. "
    "Present the remaining deliverable names. Ask: 'Which of these remaining deliverables is the focus?' "
    "Then stop and wait."
)

GUIDANCE_CONFIRMED = (
    "SHARPEN MODE STILL BINDING. "
    "Scope confirmed. Focus: [focus_name]. Deferred: [deferred_list].\n\n"
    "Move on with breaking the scope even futher into a meaningful deliverable that can be accomplished within the next seven days can call commit_week_deliverable.\n"
)


# ============================================================================
# Tool Handler
# ============================================================================


async def handle(arguments: dict) -> mcp_types.CallToolResult:
    """Handle select_focus_deliverable tool call."""
    logger.debug("select_focus_deliverable.handle.start",
                 argument_keys=list(arguments.keys()))

    # Pydantic validation
    try:
        validated_request = SelectFocusRequest.model_validate(arguments)
    except ValidationError as e:
        logger.warning("select_focus_deliverable.validation_failed", error=str(e.errors()))
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text="Invalid input format.")],
            structuredContent={"error": "validation_error", "details": e.errors()},
            isError=True,
        )

    # Convert Pydantic models to dicts for logic layer
    framing_dict = validated_request.initiative_framing.model_dump() if validated_request.initiative_framing else None
    deliverables_list = [d.model_dump() for d in validated_request.confirmed_deliverables] if validated_request.confirmed_deliverables else None
    deferred_list = validated_request.deferred_deliverables
    sculpted_dict = validated_request.sculpted_deliverable.model_dump() if validated_request.sculpted_deliverable else None

    # Business logic validation
    result = validate_cutoff_selection(
        framing=framing_dict,
        deliverables=deliverables_list,
        deferred=deferred_list,
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
        elif error_type == "missing_deferred":
            guidance = GUIDANCE_MISSING_DEFERRED
            action = "REFUSE"
        elif error_type == "invalid_deferred":
            guidance = GUIDANCE_INVALID_DEFERRED
            action = "ASK_CLARIFYING"
        elif error_type == "over_cutting":
            guidance = GUIDANCE_OVER_CUTTING
            action = "ASK_CLARIFYING"
        elif error_type == "ambiguous_remaining":
            guidance = GUIDANCE_AMBIGUOUS_REMAINING
            action = "ASK_CLARIFYING"
        elif error_type == "selection_was_deferred":
            guidance = GUIDANCE_SELECTION_WAS_DEFERRED
            action = "ASK_CLARIFYING"
        elif error_type == "replaces_includes_deferred":
            guidance = GUIDANCE_INVALID_REPLACES
            action = "ASK_CLARIFYING"
        else:
            guidance = (
                "An unexpected validation issue occurred. Ask the user to restate "
                "which deliverable they want to focus on. Do not suggest which to select. "
                "Do not proceed until the selection is explicit and user-confirmed."
            )
            action = "ASK_CLARIFYING"

        logger.info("select_focus_deliverable.rejected",
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

    # Get replaces from internal field (only present for sculpted path)
    replaces = result.get("_internal_replaces")
    auto_selected = result.get("auto_selected", False)

    logger.info("select_focus_deliverable.complete",
                focus_deliverable=focus["name"],
                deferred_count=len(deferred),
                sculpted=replaces is not None,
                auto_selected=auto_selected,
                confidence="high")

    # Determine guidance based on auto-select
    if auto_selected:
        guidance_instruction = GUIDANCE_AUTO_SELECTED
    else:
        guidance_instruction = GUIDANCE_CONFIRMED

    structured = {
        "focus_deliverable": focus,
        "scope_boundary": "explicit",
        "deferred_deliverables": deferred,
        "confidence": "high",
        "confirmed": True,
        "assistant_guidance": {
            "action": "PROCEED_TO_STEP_3",
            "instruction": guidance_instruction,
        },
    }

    # Include auto_selected flag if applicable
    if auto_selected:
        structured["auto_selected"] = True

    # Include replaces for sculpted path (LLM can mention in summary)
    if replaces:
        structured["replaces"] = replaces

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Scope boundary confirmed. Focus: {focus['name']}. Deferred: {len(deferred)} deliverable(s).",
        )],
        structuredContent=structured,
    )


# ============================================================================
# Self-register at import time
# ============================================================================

register_tool(ToolDefinition(
    name="select_focus_deliverable",
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    handle=handle,
    # OpenAI compliance annotations
    read_only_hint=False,  # Produces structured output for user
    destructive_hint=False,  # No data modification
    open_world_hint=False,  # No external API calls
))
