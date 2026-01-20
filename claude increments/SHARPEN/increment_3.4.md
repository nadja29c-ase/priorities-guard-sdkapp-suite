# SHARPEN V1 — INCREMENT 3.4: Constraint-Driven Cutoff + Step 3

## Claude Code Briefing

---

## Objective

Redesign the Step 2 → Step 3 flow to:
1. **Use Step 1 constraint as the cutoff filter** (not generic scarcity)
2. **Remove T-shirt sizing** (was a diagnostic, not a forcing function)
3. **Add escape hatch** for when no deliverable fits constraint (solution substitution)
4. **Add Step 3 tool** with single question: "What would be good enough to stop?"

---

## Design Rationale

### Current Problem

The cutoff question is generic:
> "If you could only complete ONE, which would it be?"

This doesn't use the constraint captured in Step 1. The constraint is decorative.

### The Fix

The cutoff question must USE the constraint:
> "Given [constraint_type]: [constraint_value] — which ONE of these can you realistically finish AND would still move you toward [definition_of_finished]?"

Now both Step 1 filters are active:
- **Constraint** → what's possible
- **Definition of finished** → what's valuable

### When "Simpler Solution?" Triggers

Only if user says: "None of them fit."

Then:
> "Is there a simpler approach to reach [definition_of_finished] within [constraint_value]?"

This is an escape hatch, not the main road.

### Step 3 Purpose

Step 3 is not another scope cut. It's **time-boxing**:
- Step 2 = What matters (scope)
- Step 3 = What's achievable this week (checkpoint)

One question only:
> "What would be good enough for you to stop working on [focus deliverable] this week?"

---

## Files to Modify

1. `mcp_server/sharpen/tools/identify_e2e_deliverables.py` — update GUIDANCE_CONFIRMED
2. `mcp_server/sharpen/tools/select_cutoff_deliverable.py` — update DESCRIPTION, guidance, and `build_confirmed_guidance()`
3. **NEW:** `mcp_server/sharpen/tools/commit_good_enough.py` — Step 3 tool
4. `mcp_server/sharpen/tool_logic.py` — add `validate_good_enough()` function

---

## Change 1: `identify_e2e_deliverables.py`

### Replace `GUIDANCE_CONFIRMED`

**Current:**
```python
GUIDANCE_CONFIRMED = (
    "SHARPEN MODE STILL BINDING.\n"
    "Deliverables confirmed. Present them as an unordered list (no numbering). "
    "Then ask: 'Quick check — how big does this feel? XS / S / M / L / XL (gut feel only).' "
    "Stop and wait.\n\n"
    "If XS/S/M → proceed to CUTOFF QUESTION below.\n"
    "If L/XL → ask: 'That size sometimes means there's room to subtract. Or that the initiative might be delivered in phases, not all at once. "
    "If this had to be M or smaller, what could be removed?' Then stop and wait.\n"
    "  - If user removes items → reflect the updated list, then proceed to CUTOFF QUESTION below.\n"
    "  - If user says 'fine as is' → proceed to CUTOFF QUESTION below.\n\n"
    "CUTOFF QUESTION:\n"
    "Ask: 'If you could only complete one of these right now, which would it be?' "
    "Stop and wait. Do not suggest. Call select_cutoff_deliverable with the user's choice."
)
```

**Replace with:**
```python
GUIDANCE_CONFIRMED = (
    "SHARPEN MODE STILL BINDING.\n"
    "Deliverables confirmed. Present them as an unordered list (no numbering).\n\n"
    "Then ask the CONSTRAINT-DRIVEN CUTOFF QUESTION:\n"
    "'Your constraint is [constraint_type]: [constraint_value]. "
    "Which ONE of these can you realistically finish within that AND would still count as [definition_of_finished]?'\n\n"
    "Stop and wait. Do not suggest.\n\n"
    "ESCAPE HATCH (only if user says 'none of them fit'):\n"
    "Ask: 'Is there a simpler approach to reach [definition_of_finished] within [constraint_value]?'\n"
    "If user proposes simpler solution → elicit new deliverables for that approach.\n"
    "If user picks one anyway → proceed with their choice.\n\n"
    "When user selects → call select_cutoff_deliverable with their choice."
)
```

**Key changes:**
- ❌ Removed T-shirt sizing
- ✅ Cutoff question now includes `[constraint_type]`, `[constraint_value]`, `[definition_of_finished]`
- ✅ Added escape hatch for "none fit"

---

## Change 2: `select_cutoff_deliverable.py`

### Update DESCRIPTION

In the DESCRIPTION, update the EXAMPLE CONVERSATIONS to use constraint-driven language.

**Find this section:**
```python
EXAMPLE CONVERSATION (Selection):
  You: "Looking at these deliverables, what's the minimum shippable scope?"
  User: "Just the API — docs can wait"
```

**Replace with:**
```python
EXAMPLE CONVERSATION (Selection):
  You: "Your constraint is capacity: 3 hours per week. Which ONE of these can you realistically finish within that AND would still count as done?"
  User: "Just the checklist — the RASCI doc can wait"
  You: "So 'First-week checklist' is the focus, given your 3 hours/week. RASCI is deferred. Correct?"
  User: "Yes"
  → Call with selected_deliverable_name="First-week checklist", confidence="high"

EXAMPLE CONVERSATION (None fit — escape hatch):
  You: "Your constraint is time: 2 weeks. Which ONE of these can you realistically finish within that?"
  User: "Honestly, none of them fit in 2 weeks"
  You: "Is there a simpler approach to reach 'new hire completes first week confidently' within 2 weeks?"
  User: "Maybe just a Slack message with key contacts instead of a full checklist"
  You: "That's a different solution. What deliverable would exist?"
  User: "A pinned Slack message with 'who to ask for what'"
  → Restart deliverables with this simpler approach
```

### Update `GUIDANCE_NO_METHOD`

**Current:**
```python
GUIDANCE_NO_METHOD = (
    "SHARPEN MODE STILL BINDING. "
    "Ask: 'If you could only complete one of these right now, which would it be?' "
    "Then stop and wait. Do not suggest."
)
```

**Replace with:**
```python
GUIDANCE_NO_METHOD = (
    "SHARPEN MODE STILL BINDING. "
    "Ask: 'Given [constraint_type]: [constraint_value], which ONE of these can you realistically finish "
    "AND would still count as [definition_of_finished]?' "
    "Then stop and wait. Do not suggest."
)
```

### Update `build_confirmed_guidance()` function

**Current:**
```python
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

    if deferred_names:
        deferred_str = ", ".join(deferred_names)
        return (
            f"Scope confirmed. {scope_intro} Deferred: {deferred_str}. "
            f"Ask: 'What work items must exist to produce {focus_name}?' "
            f"Then stop and wait. Do not suggest tasks. Do not discuss deferred items."
        )
    else:
        return (
            f"Scope confirmed. {scope_intro} Nothing deferred. "
            f"Ask: 'What work items must exist to produce {focus_name}?' "
            f"Then stop and wait. Do not suggest tasks."
        )
```

**Replace with:**
```python
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

    step_3_question = (
        f"Ask: 'What would be good enough that you could stop working on {focus_name} this week and still feel it was worth the time?' "
        f"Then stop and wait. Do not suggest. When user answers → call commit_good_enough with their answer."
    )

    if deferred_names:
        deferred_str = ", ".join(deferred_names)
        return (
            f"Scope confirmed. {scope_intro} Deferred: {deferred_str}.\n\n"
            f"{step_3_question}"
        )
    else:
        return f"Scope confirmed. {scope_intro} Nothing deferred.\n\n{step_3_question}"
```

**Key change:** Now points to Step 3 (`commit_good_enough`) instead of asking for work items.

---

## Change 3: NEW FILE `commit_good_enough.py`

Create new file: `mcp_server/sharpen/tools/commit_good_enough.py`

### File Content

```python
"""
Commit Good Enough Tool (Step 3).

Captures the user's stopping line for this week's work on the focus deliverable.
This is time-boxing, not scope-cutting.
Self-registers at import time.
"""

from typing import Optional, Literal

import structlog
from mcp import types as mcp_types
from pydantic import BaseModel, ValidationError

from .base import ToolDefinition
from . import register_tool
from ..tool_logic import validate_good_enough

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata
# ============================================================================

DESCRIPTION = """Records the user's "good enough" stopping line for this week. This defines when they can stop working on the focus deliverable and feel the week was successful. Requires confirmed focus deliverable from Step 2 and confidence="high".

SHARPEN MODE — BINDING RULES (not guidelines)
When user selects Sharpen, your default assistant behavior is SUSPENDED.

SUSPENDED BEHAVIORS:
- Suggesting what "good enough" should be
- Adding quality criteria
- Proposing milestones
- Expanding the definition
- "Being helpful" by setting higher bars

ACTIVE BEHAVIORS:
- Ask ONE question
- Wait for answer
- Reflect their words back
- Ask for user confirmation
- Then call tool with confidence="high"

THE ONLY QUESTION:
"What would be good enough that you could stop working on [focus_deliverable] this week and still feel it was worth the time?"

SCOPE REGRESSION GUARDRAIL:
If the user's answer expands scope beyond the focus deliverable (adds new outcomes, audiences, or deliverables), ask: 'That sounds like it goes beyond [focus_deliverable]. What would be good enough within just that scope?'
Do not accept expanded scope. Step 3 tightens, never expands.

GOOD ANSWERS (concrete, stoppable):
- "Checklist exists, even if rough"
- "Shared with team, not finalized"
- "Covers day one only"

BAD ANSWERS (vague, unstoppable):
- "Make progress"
- "Get it done"
- "Feel good about it"

If answer is vague, ask: "How would you know it's done?" Then stop and wait.

EXAMPLE CONVERSATION:
  You: "What would be good enough that you could stop working on 'First-week checklist' this week and still feel it was worth the time?"
  User: "Having a draft ready"
  You: "How would you know the draft is ready?"
  User: "When it has all 5 days listed with at least one task each"
  You: "So 'good enough' this week is: a draft checklist with all 5 days and at least one task per day. Correct?"
  User: "Yes"
  → Call commit_good_enough with good_enough_definition="Draft checklist with all 5 days and at least one task per day", confidence="high"
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
        "focus_deliverable": {
            "type": "object",
            "description": "Confirmed focus deliverable from Step 2 (required).",
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["name"],
        },
        "good_enough_definition": {
            "type": "string",
            "description": "User's definition of 'good enough' to stop this week. Must be concrete and verifiable. ACCORDING TO THE USER.",
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "Your confidence that the stopping line is user-confirmed and concrete. Must be 'high' to proceed.",
        },
    },
    "required": ["initiative_framing", "focus_deliverable", "good_enough_definition", "confidence"],
    "additionalProperties": False,
}


# ============================================================================
# Pydantic Models
# ============================================================================


class FocusDeliverable(BaseModel):
    """Focus deliverable from Step 2."""
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


class CommitGoodEnoughRequest(BaseModel):
    """Expected input structure from ChatGPT."""
    initiative_framing: Optional[InitiativeFraming] = None
    focus_deliverable: Optional[FocusDeliverable] = None
    good_enough_definition: Optional[str] = None
    confidence: Optional[Literal["high", "medium", "low"]] = None


# ============================================================================
# Assistant Guidance Messages
# ============================================================================

GUIDANCE_CONFIDENCE_REJECTED = (
    "SHARPEN MODE STILL BINDING. "
    "The stopping line is too vague. Ask: 'How would you know it's done?' "
    "Then stop and wait. Do not suggest criteria."
)

GUIDANCE_MISSING_FRAMING = (
    "SHARPEN MODE STILL BINDING. "
    "initiative_framing parameter missing. Complete Step 1 first via frame_initiative_intent + frame_initiative_constraints."
)

GUIDANCE_MISSING_FOCUS = (
    "SHARPEN MODE STILL BINDING. "
    "focus_deliverable parameter missing. Complete Step 2 first via identify_e2e_deliverables + select_cutoff_deliverable."
)

GUIDANCE_EMPTY_DEFINITION = (
    "SHARPEN MODE STILL BINDING. "
    "Ask: 'What would be good enough that you could stop working on [focus_deliverable] this week and still feel it was worth the time?' "
    "Then stop and wait. Do not suggest."
)

GUIDANCE_CONFIRMED = (
    "SHARPEN COMPLETE.\n\n"
    "Present the full sharpened scope:\n"
    "- WHO: [who]\n"
    "- WHAT: [what]\n"
    "- CONSTRAINT: [constraint_type]: [constraint_value]\n"
    "- FOCUS DELIVERABLE: [focus_deliverable]\n"
    "- THIS WEEK'S GOOD ENOUGH: [good_enough_definition]\n\n"
    "Then say: 'You're sharpened. When you hit [good_enough_definition], you can stop for the week.'\n"
    "Do not add tasks. Do not suggest next steps. Do not offer to help plan."
)


# ============================================================================
# Tool Handler
# ============================================================================


async def handle(arguments: dict) -> mcp_types.CallToolResult:
    """Handle commit_good_enough tool call."""
    logger.debug("commit_good_enough.handle.start",
                 argument_keys=list(arguments.keys()))

    # Pydantic validation
    try:
        validated_request = CommitGoodEnoughRequest.model_validate(arguments)
    except ValidationError as e:
        logger.warning("commit_good_enough.validation_failed", error=str(e.errors()))
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text="Invalid input format.")],
            structuredContent={"error": "validation_error", "details": e.errors()},
            isError=True,
        )

    # Convert to dicts for logic layer
    framing_dict = validated_request.initiative_framing.model_dump() if validated_request.initiative_framing else None
    focus_dict = validated_request.focus_deliverable.model_dump() if validated_request.focus_deliverable else None

    # Business logic validation
    result = validate_good_enough(
        framing=framing_dict,
        focus=focus_dict,
        good_enough=validated_request.good_enough_definition,
        confidence=validated_request.confidence,
    )

    # Handle validation failures
    if not result["valid"]:
        error_type = result["error_type"]
        error_details = result["error_details"]

        if error_type == "confidence_too_low":
            guidance = GUIDANCE_CONFIDENCE_REJECTED
            action = "ASK_CLARIFYING"
        elif error_type == "missing_framing":
            guidance = GUIDANCE_MISSING_FRAMING
            action = "REFUSE"
        elif error_type == "missing_focus":
            guidance = GUIDANCE_MISSING_FOCUS
            action = "REFUSE"
        elif error_type == "empty_definition":
            guidance = GUIDANCE_EMPTY_DEFINITION
            action = "ASK_CLARIFYING"
        else:
            guidance = (
                "An unexpected validation issue occurred. Ask the user to restate "
                "what 'good enough' means for this week. Do not suggest."
            )
            action = "ASK_CLARIFYING"

        logger.info("commit_good_enough.rejected",
                    error_type=error_type, action=action)

        structured = {
            "error": error_type,
            "details": error_details,
            "assistant_guidance": {
                "action": action,
                "instruction": guidance,
            },
        }
        if error_type == "confidence_too_low":
            structured["confidence_provided"] = validated_request.confidence

        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=error_details or f"Good enough issue: {error_type}",
            )],
            structuredContent=structured,
            isError=True,
        )

    # Valid — return confirmed stopping line
    sharpened = result["sharpened_scope"]

    logger.info("commit_good_enough.complete",
                focus=sharpened["focus_deliverable"]["name"],
                good_enough=sharpened["good_enough_definition"][:50],
                confidence="high")

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Sharpened. Focus: {sharpened['focus_deliverable']['name']}. "
                 f"Good enough this week: {sharpened['good_enough_definition']}",
        )],
        structuredContent={
            "sharpened_scope": sharpened,
            "confidence": "high",
            "confirmed": True,
            "assistant_guidance": {
                "action": "SHARPEN_COMPLETE",
                "instruction": GUIDANCE_CONFIRMED,
            },
        },
    )


# ============================================================================
# Self-register at import time
# ============================================================================

register_tool(ToolDefinition(
    name="commit_good_enough",
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    handle=handle,
    read_only_hint=False,
    destructive_hint=False,
    open_world_hint=False,
))
```

---

## Change 4: `tool_logic.py`

Add new validation function for Step 3.

### Add `validate_good_enough()` function

```python
def validate_good_enough(
    framing: dict | None,
    focus: dict | None,
    good_enough: str | None,
    confidence: str | None,
) -> dict:
    """
    Validate Step 3: good enough stopping line.
    
    Returns:
        dict with keys:
        - valid: bool
        - error_type: str | None
        - error_details: str | None
        - sharpened_scope: dict | None (if valid)
    """
    # Check confidence first
    if confidence != "high":
        return {
            "valid": False,
            "error_type": "confidence_too_low",
            "error_details": f"Confidence '{confidence}' rejected. Only 'high' accepted.",
            "sharpened_scope": None,
        }
    
    # Check framing exists
    if not framing:
        return {
            "valid": False,
            "error_type": "missing_framing",
            "error_details": "Initiative framing required. Complete Step 1 first.",
            "sharpened_scope": None,
        }
    
    # Check framing has required fields
    required_framing = ["who", "what", "constraint_type", "constraint_value", "definition_of_finished"]
    missing_framing = [f for f in required_framing if not framing.get(f)]
    if missing_framing:
        return {
            "valid": False,
            "error_type": "missing_framing",
            "error_details": f"Initiative framing incomplete. Missing: {', '.join(missing_framing)}",
            "sharpened_scope": None,
        }
    
    # Check focus exists
    if not focus:
        return {
            "valid": False,
            "error_type": "missing_focus",
            "error_details": "Focus deliverable required. Complete Step 2 first.",
            "sharpened_scope": None,
        }
    
    # Check focus has name
    if not focus.get("name"):
        return {
            "valid": False,
            "error_type": "missing_focus",
            "error_details": "Focus deliverable name required.",
            "sharpened_scope": None,
        }
    
    # Check good_enough exists and is non-empty
    if not good_enough or not good_enough.strip():
        return {
            "valid": False,
            "error_type": "empty_definition",
            "error_details": "Good enough definition required.",
            "sharpened_scope": None,
        }
    
    # All valid — build sharpened scope
    return {
        "valid": True,
        "error_type": None,
        "error_details": None,
        "sharpened_scope": {
            "initiative_framing": framing,
            "focus_deliverable": focus,
            "good_enough_definition": good_enough.strip(),
        },
    }
```

---

## Change 5: Register the new tool

In `mcp_server/sharpen/tools/__init__.py`, ensure the new tool is imported.

Add import:
```python
from . import commit_good_enough  # noqa: F401
```

---

## Verification Checklist

After implementation:

### identify_e2e_deliverables.py
- [ ] `GUIDANCE_CONFIRMED` no longer mentions T-shirt sizing
- [ ] `GUIDANCE_CONFIRMED` includes `[constraint_type]`, `[constraint_value]`, `[definition_of_finished]`
- [ ] `GUIDANCE_CONFIRMED` includes escape hatch for "none fit"

### select_cutoff_deliverable.py
- [ ] DESCRIPTION examples use constraint-driven language
- [ ] `GUIDANCE_NO_METHOD` uses constraint in question
- [ ] `build_confirmed_guidance()` points to `commit_good_enough` (not work items)

### commit_good_enough.py
- [ ] File exists and follows same patterns as other tools
- [ ] DESCRIPTION includes SHARPEN MODE binding rules
- [ ] Single question: "What would be good enough to stop this week?"
- [ ] Guidance constants defined for all error states
- [ ] Success guidance presents full sharpened scope

### tool_logic.py
- [ ] `validate_good_enough()` function exists
- [ ] Validates: confidence, framing, focus, good_enough definition
- [ ] Returns sharpened_scope on success

### tools/__init__.py
- [ ] `commit_good_enough` is imported

---

## Unit Tests

### New test file: `tests/sharpen/test_commit_good_enough.py`

Test cases:
1. **Happy path**: valid framing + focus + good_enough + confidence=high → success
2. **Confidence rejection**: confidence=low → error
3. **Missing framing**: no framing → error
4. **Missing focus**: no focus → error
5. **Empty definition**: empty string → error
6. **Whitespace definition**: "   " → error (trimmed to empty)

### Update existing tests

- `test_identify_e2e_deliverables.py`: No changes needed (logic unchanged)
- `test_select_cutoff_deliverable.py`: No changes needed (logic unchanged)

---

## Integration Test Script

Test the full flow manually:

```
User: "My team needs to work on improving our onboarding process"
→ Step 1 (WHO, WHAT, constraint, definition of finished)
→ Step 2.1 (E2E deliverables)
→ Step 2.2 (Constraint-driven cutoff: "Given 3 hours/week, which ONE...")
→ Step 3 ("What would be good enough to stop this week?")
→ SHARPEN COMPLETE
```

Verify:
1. T-shirt sizing never appears
2. Cutoff question includes actual constraint values
3. "None fit" escape hatch works if tested
4. Step 3 asks single question
5. Final output shows full sharpened scope

---

## Out of Scope

- Step 1 tools (unchanged)
- Schema changes beyond new tool
- Database/persistence (Sharpen V1 is stateless)
- Widget changes

---

**Document Status:** Ready for Claude Code execution
