# SHARPEN V1 — INCREMENT 3.5: Make WHY Mandatory, Remove definition_of_finished

## Claude Code Briefing

---

## Objective

Simplify Step 1 framing to two cutting axes:
1. **Value** → `why` (mandatory)
2. **Reality** → `constraint` (mandatory)

Remove `definition_of_finished` — it was doing the wrong job and has been replaced by:
- Step 2 cutoff: "Which ONE would still move you toward [why]?"
- Step 3 stopping: "What's good enough to stop this week?"

---

## Design Rationale

### Why `definition_of_finished` Can Go

Users either:
- Rephrased the deliverable ("API is deployed")
- Described idealized end states ("Everyone loves it")
- Added process criteria ("Tested and documented")

None helped with selection. The new cutoff question does this better.

### Why `why` Must Be Mandatory

`why` is now actively used as a filter in:
- Step 2: "Which ONE would still move you toward [why]?"
- Step 2 escape hatch: "Is there a simpler approach to [why]?"
- Step 3: Implicit anchor for "good enough"

Without mandatory `why`, these questions have no anchor.

### Enforcement for Vague `why`

Same pattern as vague deliverables:
> "That's too abstract. What changes for someone if this works?"

Good: "So new hires can start contributing without constant interruptions"
Bad: "Because onboarding matters"
Bad: "So we can have a checklist" ← This restates WHAT, not WHY

---

## Files to Modify

1. `mcp_server/sharpen/tools/frame_initiative_intent.py`
2. `mcp_server/sharpen/tools/frame_initiative_constraints.py`
3. `mcp_server/sharpen/tools/identify_e2e_deliverables.py`
4. `mcp_server/sharpen/tools/select_cutoff_deliverable.py`
5. `mcp_server/sharpen/tools/commit_good_enough.py`
6. `mcp_server/sharpen/tool_logic.py`

---

## Change 1: `frame_initiative_intent.py`

### Update INPUT_SCHEMA `why` description

Find:
```python
"why": {
    "type": "string",
    "description": "Optional: So that the beneficiary benefits in what specific way? ACCORDING TO THE USER. Used to find the value of the output (WHAT), this creates the outcome-focus.",
},
```

Replace with:
```python
"why": {
    "type": "string",
    "description": "So that WHO benefits HOW? Must be outcome-phrased (what changes for the WHO/ what is the benefit for the WHO), not motivation-phrased (why it matters). Do not restate WHAT — describe the change or benefit if this succeeds. ACCORDING TO THE USER.",
},
```

### Update INPUT_SCHEMA `required` array

Find:
```python
"required": ["who", "what", "confidence"],
```

Replace with:
```python
"required": ["who", "what", "why", "confidence"],
```

### Update CONFIDENCE EXAMPLES in DESCRIPTION

Find the CONFIDENCE EXAMPLES section and replace with:
```python
CONFIDENCE EXAMPLES:
  HIGH: who="The sales team" what="A CRM integration that syncs contacts daily" why="So sales reps spend less time on data entry". User confirmed, outcome-phrased.
  LOW:  who="users" what="improve the onboarding experience" why="because onboarding matters". Vague WHO, activity-based WHAT, motivation-phrased WHY.
  LOW:  who="New hires" what="A checklist" why="So we can have a checklist". WHY restates WHAT — not valid.
```

### Update GUIDANCE_CONFIRMED

Find:
```python
GUIDANCE_CONFIRMED = (
    "Intent confirmed. "
    "Ask ONE question: 'What's the one constraint that limits this most — a deadline, limited hours, or a budget cap?' "
    "Then stop and wait. Do not suggest constraints.\n\n"
    "When user answers constraint → ask: 'How will you know this is truly finished?' Then stop and wait.\n"
    "When user answers definition of finished → call frame_initiative_constraints with constraint + definition_of_finished."
)
```

Replace with:
```python
GUIDANCE_CONFIRMED = (
    "Intent confirmed. "
    "Ask ONE question: 'What's the one constraint that limits this most — a deadline, limited hours, or a budget cap?' "
    "Then stop and wait. Do not suggest constraints.\n\n"
    "When user answers constraint → call frame_initiative_constraints with constraint_type + constraint_value."
)
```

### Update EXAMPLE CONVERSATION in DESCRIPTION

Find the example conversation and update to include mandatory WHY elicitation:

```python
EXAMPLE CONVERSATION:
  User: "I want to improve our onboarding"
  You: "Who specifically will benefit most from this improved onboarding?"
  User: "New engineering hires"
  You: "What concrete thing will exist that doesn't exist today?"
  User: "A checklist they can follow in their first week"
  You: "So that new engineering hires benefit how?"
  User: "So they can start contributing without constant interruptions"
  You: "To confirm: New engineering hires need a first-week checklist so they can start contributing without constant interruptions. Correct?"
  User: "Yes"
  → Now call frame_initiative_intent with who="New engineering hires", what="A first-week onboarding checklist", why="So they can start contributing without constant interruptions", confidence="high".
```

### Vague WHY Handling

No special guidance constant needed. Vague WHY is caught by confidence rejection:
- Missing WHY → `GUIDANCE_MISSING_FIELDS` (structural)
- Vague WHY → LLM calls with confidence != "high" → `GUIDANCE_CONFIDENCE_REJECTED`

The LLM's job is to recognize vague WHY and either ask clarifying questions or call with low confidence.

---

## Change 2: `frame_initiative_constraints.py`

### Update DESCRIPTION

Remove all references to "definition of finished". 

Find docstring:
```python
"""
Frame Initiative Constraints Tool.

Captures the dominant constraint and definition of finished.
Requires confirmed intent from frame_initiative_intent.
Self-registers at import time.
"""
```

Replace with:
```python
"""
Frame Initiative Constraints Tool.

Captures the dominant constraint (time, capacity, budget, or forced_mvp).
Requires confirmed intent from frame_initiative_intent.
Self-registers at import time.
"""
```

Find DESCRIPTION opening:
```python
DESCRIPTION = """Records confirmed CONSTRAINT and DEFINITION OF FINISHED for an initiative. Without a clear constraint, scope expands endlessly. Without a definition of finished, work is never done. So this is an additional filter to maximize work not done later. Requires confidence="high".
```

Replace with:
```python
DESCRIPTION = """Records confirmed CONSTRAINT for an initiative. Without a clear constraint, scope expands endlessly. The constraint becomes the reality filter for all subsequent scope decisions. Requires confidence="high".
```

### Remove `definition_of_finished` from INPUT_SCHEMA

Find and remove:
```python
"definition_of_finished": {
    "type": "string",
    "description": "How will you know the WHAT is finished? Concrete, verifiable condition (not 'done' or 'ready'). ACCORDING TO THE USER.",
},
```

### Update CONFIDENCE EXAMPLES in DESCRIPTION

Find:
```python
CONFIDENCE EXAMPLES:
  HIGH: constraint_type="time" constraint_value="by March 15" definition_of_finished="Dashboard deployed and accessible to team". These are user confirmed.
  LOW:  constraint_type="time" constraint_value="soon" definition_of_finished="when it's done"
  HIGH: constraint_type="capacity" constraint_value="4 hours per week" definition_of_finished="API returns valid responses for all endpoints". These are user confirmed.
  LOW:  constraint_type="budget" constraint_value="flexible" definition_of_finished="ready to use"
```

Replace with:
```python
CONFIDENCE EXAMPLES:
  HIGH: constraint_type="time" constraint_value="by March 15". User confirmed.
  LOW:  constraint_type="time" constraint_value="soon". Too vague.
  HIGH: constraint_type="capacity" constraint_value="4 hours per week". User confirmed.
  LOW:  constraint_type="budget" constraint_value="flexible". Too vague.
```

### Update EXAMPLE CONVERSATION in DESCRIPTION

Find:
```python
EXAMPLE CONVERSATION:
  You: "What's the one constraint that limits this initiative most — a deadline, limited hours per week, or a budget cap?"
  User: "I only have about 3 hours a week to work on this"
  You: "3 hours per week — got it. How will you know the checklist is truly finished?"
  User: "When a new hire has used it and said it was helpful"
  You: "So it's finished when at least one new hire has used the checklist and confirmed it was helpful. Is that right?"
  User: "Yes"
  → Now call frame_initiative_constraints with constraint_type="capacity", constraint_value="3 hours per week", definition_of_finished="At least one new hire has used the checklist and confirmed it was helpful", confidence="high".
```

Replace with:
```python
EXAMPLE CONVERSATION:
  You: "What's the one constraint that limits this initiative most — a deadline, limited hours per week, or a budget cap?"
  User: "I only have about 3 hours a week to work on this"
  You: "3 hours per week. Is that the main constraint?"
  User: "Yes"
  → Now call frame_initiative_constraints with constraint_type="capacity", constraint_value="3 hours per week", confidence="high".
```

### Update FrameConstraintsRequest Pydantic model

Find:
```python
class FrameConstraintsRequest(BaseModel):
    """Expected input structure from ChatGPT."""
    constraint_type: Optional[Literal["time", "capacity", "budget", "forced_mvp"]] = None
    constraint_value: Optional[str] = None
    definition_of_finished: Optional[str] = None
    user_claims_no_constraints: bool = False
    confidence: Optional[Literal["high", "medium", "low"]] = None
```

Replace with:
```python
class FrameConstraintsRequest(BaseModel):
    """Expected input structure from ChatGPT."""
    constraint_type: Optional[Literal["time", "capacity", "budget", "forced_mvp"]] = None
    constraint_value: Optional[str] = None
    user_claims_no_constraints: bool = False
    confidence: Optional[Literal["high", "medium", "low"]] = None
```

### Update GUIDANCE_CONFIDENCE_REJECTED

Find:
```python
GUIDANCE_CONFIDENCE_REJECTED = (
    "SHARPEN MODE STILL BINDING. "
    "Ask ONE question about CONSTRAINT or DEFINITION OF FINISHED (whichever is vaguer). "
    "Then stop and wait. Do not explain, suggest, or plan."
)
```

Replace with:
```python
GUIDANCE_CONFIDENCE_REJECTED = (
    "SHARPEN MODE STILL BINDING. "
    "Ask ONE question about the CONSTRAINT (type or value, whichever is vaguer). "
    "Then stop and wait. Do not explain, suggest, or plan."
)
```

### Update GUIDANCE_CONFIRMED

Find:
```python
GUIDANCE_CONFIRMED = (
    "Present the complete framing using the user's exact words: "
    "WHO, WHAT, WHY (if any), CONSTRAINT, DEFINITION OF FINISHED. "
    "Then ask: 'Is this correct?' Stop and wait. Do not elaborate or add context.\n\n"
    "If user confirms → ask: 'What needs to exist for this initiative to be done? Don't filter — just name everything.' "
    "Then stop and wait. When user answers → call identify_e2e_deliverables with framing + deliverables.\n"
    "If user corrects → update the framing and re-confirm."
)
```

Replace with:
```python
GUIDANCE_CONFIRMED = (
    "Present the complete framing using the user's exact words: "
    "WHO, WHAT, WHY, CONSTRAINT. "
    "Then ask: 'Is this correct?' Stop and wait. Do not elaborate or add context.\n\n"
    "If user confirms → ask: 'What needs to exist for this initiative to be done? Don't filter — just name everything.' "
    "Then stop and wait. When user answers → call identify_e2e_deliverables with framing + deliverables.\n"
    "If user corrects → update the framing and re-confirm."
)
```

### Update handler to not pass definition_of_finished

Find:
```python
# Structural validation
result = validate_initiative_constraints(
    constraint_type=validated_request.constraint_type,
    constraint_value=validated_request.constraint_value,
    definition_of_finished=validated_request.definition_of_finished,
    user_claims_no_constraints=validated_request.user_claims_no_constraints,
)
```

Replace with:
```python
# Structural validation
result = validate_initiative_constraints(
    constraint_type=validated_request.constraint_type,
    constraint_value=validated_request.constraint_value,
    user_claims_no_constraints=validated_request.user_claims_no_constraints,
)
```

### Update success response text

Find:
```python
return mcp_types.CallToolResult(
    content=[mcp_types.TextContent(
        type="text",
        text=f"Constraints confirmed: {framing['constraint_type']} — {framing['constraint_value']}. "
             f"Finished when: {framing['definition_of_finished']}",
    )],
```

Replace with:
```python
return mcp_types.CallToolResult(
    content=[mcp_types.TextContent(
        type="text",
        text=f"Constraint confirmed: {framing['constraint_type']} — {framing['constraint_value']}",
    )],
```

---

## Change 3: `tool_logic.py`

### Update `validate_initiative_intent`

Find:
```python
def validate_initiative_intent(
    who: str | None,
    what: str | None,
    why: str | None = None,
) -> dict[str, Any]:
```

Replace with:
```python
def validate_initiative_intent(
    who: str | None,
    what: str | None,
    why: str | None,
) -> dict[str, Any]:
```

Update validation logic:
```python
# Structural validation only
valid = bool(who) and bool(what)

missing = []
if not who:
    missing.append("who")
if not what:
    missing.append("what")
```

Replace with:
```python
# Structural validation only — all three required
valid = bool(who) and bool(what) and bool(why)

missing = []
if not who:
    missing.append("who")
if not what:
    missing.append("what")
if not why:
    missing.append("why")
```

Update docstring:
```python
"""
Validate structure of WHO, WHAT, and WHY for initiative intent.

Structural validation only — semantic quality is LLM's job.

Args:
    who: Who benefits from this work?
    what: What artifact/deliverable must exist?
    why: So that WHO benefits HOW? (outcome-phrased, mandatory)

Returns:
    framing_intent dict + valid flag
"""
```

### Update `validate_initiative_constraints`

Find:
```python
def validate_initiative_constraints(
    constraint_type: str | None = None,
    constraint_value: str | None = None,
    definition_of_finished: str | None = None,
    user_claims_no_constraints: bool = False,
) -> dict[str, Any]:
```

Replace with:
```python
def validate_initiative_constraints(
    constraint_type: str | None = None,
    constraint_value: str | None = None,
    user_claims_no_constraints: bool = False,
) -> dict[str, Any]:
```

Update the function body — remove all `definition_of_finished` references:

Find:
```python
# Normalize inputs
constraint_type = (constraint_type or "").strip() or None
constraint_value = (constraint_value or "").strip() or None
definition_of_finished = (definition_of_finished or "").strip() or None

# Build constraint framing
constraint_framing = {
    "constraint_type": constraint_type,
    "constraint_value": constraint_value,
    "definition_of_finished": definition_of_finished,
}

# Structural validation
valid = bool(constraint_type) and bool(constraint_value) and bool(definition_of_finished)

missing = []
if not constraint_type:
    missing.append("constraint_type")
if not constraint_value:
    missing.append("constraint_value")
if not definition_of_finished:
    missing.append("definition_of_finished")
```

Replace with:
```python
# Normalize inputs
constraint_type = (constraint_type or "").strip() or None
constraint_value = (constraint_value or "").strip() or None

# Build constraint framing
constraint_framing = {
    "constraint_type": constraint_type,
    "constraint_value": constraint_value,
}

# Structural validation
valid = bool(constraint_type) and bool(constraint_value)

missing = []
if not constraint_type:
    missing.append("constraint_type")
if not constraint_value:
    missing.append("constraint_value")
```

Update docstring to remove `definition_of_finished` parameter.

### Update `validate_initiative_framing_complete`

Find:
```python
required_fields = [
    "who",
    "what",
    "constraint_type",
    "constraint_value",
    "definition_of_finished",
]
```

Replace with:
```python
# Assumes Step 1 completed fully (who, what, why, constraint).
# All downstream tools (identify_e2e_deliverables, select_cutoff, commit_good_enough)
# depend on this validation passing.
required_fields = [
    "who",
    "what",
    "why",
    "constraint_type",
    "constraint_value",
]
```

Update docstring:
```python
"""
Validate that initiative_framing from Step 1 is complete.

Required fields: who, what, why, constraint_type, constraint_value

Args:
    framing: Combined initiative_framing object from Step 1

Returns:
    {"valid": bool, "missing": list[str]}
"""
```

### Update `validate_good_enough`

Find:
```python
# Check framing has required fields
required_framing = ["who", "what", "constraint_type", "constraint_value", "definition_of_finished"]
```

Replace with:
```python
# Check framing has required fields
required_framing = ["who", "what", "why", "constraint_type", "constraint_value"]
```

---

## Change 4: `identify_e2e_deliverables.py`

### Update INPUT_SCHEMA initiative_framing

Find:
```python
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
```

Replace with:
```python
"initiative_framing": {
    "type": "object",
    "description": "Confirmed Step 1 framing (required). Must include who, what, why, constraint_type, constraint_value.",
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
```

### Update InitiativeFraming Pydantic model

Find:
```python
class InitiativeFraming(BaseModel):
    """Step 1 framing object."""
    who: Optional[str] = None
    what: Optional[str] = None
    why: Optional[str] = None
    constraint_type: Optional[Literal["time", "capacity", "budget", "forced_mvp"]] = None
    constraint_value: Optional[str] = None
    definition_of_finished: Optional[str] = None
```

Replace with:
```python
class InitiativeFraming(BaseModel):
    """Step 1 framing object."""
    who: Optional[str] = None
    what: Optional[str] = None
    why: Optional[str] = None
    constraint_type: Optional[Literal["time", "capacity", "budget", "forced_mvp"]] = None
    constraint_value: Optional[str] = None
```

### Update GUIDANCE_CONFIRMED

Find:
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

Replace with:
```python
GUIDANCE_CONFIRMED = (
    "SHARPEN MODE STILL BINDING.\n"
    "Deliverables confirmed. Present them as an unordered list (no numbering).\n\n"
    "CRITICAL: THE KNIFE MUST BE USED HERE — RIGOROUSLY.\n"
    "The E2E deliverables encode an implicit solution and scope size. Both must be challenged.\n"
    "Goal: Cut until realistic AND until best scope-to-value ratio is achieved.\n"
    "The knife has two edges:\n"
    "  - CONSTRAINT edge: Does this fit within [constraint_value]?\n"
    "  - VALUE edge: Is this the simplest scope that still delivers [why]?\n\n"
    "REALITY CHECK:\n"
    "Ask: 'You have [N] deliverables. Your constraint is [constraint_type]: [constraint_value]. How realistic does this feel?'\n"
    "Stop and wait.\n\n"
    "PATH A — SCOPE TOO BIG (user says 'ambitious', 'a lot', hesitates):\n"
    "Ask: 'What could be removed and still move you toward [why]?'\n"
    "When user removes items → reflect updated list → repeat reality check.\n"
    "Loop until user confirms it feels realistic.\n\n"
    "PATH B — SOLUTION MISMATCH (user says 'none of this fits', 'completely unrealistic', or you sense the whole approach is overengineered):\n"
    "Challenge the solution itself: 'These deliverables assume a certain approach. Is there a simpler way to achieve [why] within [constraint_value]?'\n"
    "If user proposes simpler solution → elicit new deliverables for that approach (restart Step 2).\n"
    "If user insists current approach is right → proceed to cutoff.\n\n"
    "PATH C — REALISTIC (user confirms 'doable', 'realistic'):\n"
    "Proceed to cutoff question.\n\n"
    "CUTOFF QUESTION (clean slice — no more cutting):\n"
    "The list is already realistic. Now just sequence.\n"
    "Ask: 'Which ONE of these would you start with?'\n"
    "Stop and wait. Do not challenge. Do not re-cut.\n\n"
    "When user selects → call select_cutoff_deliverable with their choice."
)
```

---

## Change 5: `select_cutoff_deliverable.py`

### Update INPUT_SCHEMA initiative_framing

Same pattern as identify_e2e_deliverables — remove `definition_of_finished`, add `why` to required.

Find and replace the initiative_framing schema to match:
```python
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
```

### Update InitiativeFraming Pydantic model

Remove `definition_of_finished` field (same as identify_e2e_deliverables).

### Update DESCRIPTION examples

Find:
```python
EXAMPLE CONVERSATION (Selection):
  You: "Your constraint is capacity: 3 hours per week. Which ONE of these can you realistically finish within that AND would still count as done?"
```

Replace with:
```python
EXAMPLE CONVERSATION (Selection):
  You: "Your constraint is capacity: 3 hours per week. Which ONE of these can you realistically finish within that AND would still move you toward your goal?"
```

Find:
```python
EXAMPLE CONVERSATION (None fit — escape hatch):
  You: "Your constraint is time: 2 weeks. Which ONE of these can you realistically finish within that?"
  User: "Honestly, none of them fit in 2 weeks"
  You: "Is there a simpler approach to reach 'new hire completes first week confidently' within 2 weeks?"
```

Replace with:
```python
EXAMPLE CONVERSATION (None fit — escape hatch):
  You: "Your constraint is time: 2 weeks. Which ONE of these can you realistically finish within that AND would still move you toward your goal?"
  User: "Honestly, none of them fit in 2 weeks"
  You: "Is there a simpler approach to achieve [why] within 2 weeks?"
```

### Update GUIDANCE_NO_METHOD

Find:
```python
GUIDANCE_NO_METHOD = (
    "SHARPEN MODE STILL BINDING. "
    "Ask: 'Given [constraint_type]: [constraint_value], which ONE of these can you realistically finish "
    "AND would still count as [definition_of_finished]?' "
    "Then stop and wait. Do not suggest."
)
```

Replace with:
```python
GUIDANCE_NO_METHOD = (
    "SHARPEN MODE STILL BINDING. "
    "Ask: 'Given [constraint_type]: [constraint_value], which ONE of these can you realistically finish "
    "AND would still move you toward [why]?' "
    "Then stop and wait. Do not suggest."
)
```

---

## Change 6: `commit_good_enough.py`

### Update INPUT_SCHEMA initiative_framing

Same pattern — remove `definition_of_finished`, add `why` to required.

### Update InitiativeFraming Pydantic model

Remove `definition_of_finished` field.

### Update GUIDANCE_CONFIRMED

Find:
```python
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
```

Replace with:
```python
GUIDANCE_CONFIRMED = (
    "SHARPEN COMPLETE.\n\n"
    "Present the full sharpened scope:\n"
    "- WHO: [who]\n"
    "- WHAT: [what]\n"
    "- WHY: [why]\n"
    "- CONSTRAINT: [constraint_type]: [constraint_value]\n"
    "- FOCUS DELIVERABLE: [focus_deliverable]\n"
    "- THIS WEEK'S GOOD ENOUGH: [good_enough_definition]\n\n"
    "Then say: 'You're sharpened. When you hit [good_enough_definition], you can stop for the week.'\n"
    "Do not add tasks. Do not suggest next steps. Do not offer to help plan."
)
```

---

## Verification Checklist

After implementation:

### frame_initiative_intent.py
- [ ] `why` is in required array
- [ ] `why` description includes "Do not restate WHAT"
- [ ] Confidence examples include WHY (good and bad)
- [ ] GUIDANCE_CONFIRMED no longer mentions "definition of finished"
- [ ] Example conversation includes WHY elicitation

### frame_initiative_constraints.py
- [ ] `definition_of_finished` removed from INPUT_SCHEMA
- [ ] `definition_of_finished` removed from Pydantic model
- [ ] DESCRIPTION no longer mentions "definition of finished"
- [ ] GUIDANCE_CONFIRMED shows "WHO, WHAT, WHY, CONSTRAINT" (no definition_of_finished)
- [ ] Handler doesn't pass definition_of_finished to validate function

### tool_logic.py
- [ ] `validate_initiative_intent` requires `why`
- [ ] `validate_initiative_constraints` has no `definition_of_finished` parameter
- [ ] `validate_initiative_framing_complete` has comment explaining downstream dependencies
- [ ] `validate_initiative_framing_complete` checks for `why`, not `definition_of_finished`
- [ ] `validate_good_enough` checks for `why`, not `definition_of_finished`

### identify_e2e_deliverables.py
- [ ] INPUT_SCHEMA requires `why`, not `definition_of_finished`
- [ ] GUIDANCE_CONFIRMED uses `[why]` in cutoff question
- [ ] GUIDANCE_CONFIRMED uses `[why]` in escape hatch

### select_cutoff_deliverable.py
- [ ] INPUT_SCHEMA requires `why`, not `definition_of_finished`
- [ ] GUIDANCE_NO_METHOD uses `[why]`
- [ ] DESCRIPTION examples use `[why]`

### commit_good_enough.py
- [ ] INPUT_SCHEMA requires `why`, not `definition_of_finished`
- [ ] GUIDANCE_CONFIRMED presents WHY in final scope

---

## Unit Test Updates

### test_tool_logic.py

Update tests for:
- `validate_initiative_intent` — now requires `why`
- `validate_initiative_constraints` — no longer takes `definition_of_finished`
- `validate_initiative_framing_complete` — checks `why` instead of `definition_of_finished`
- `validate_good_enough` — framing must have `why`

### CRITICAL: All tests that build `initiative_framing` must now include `why`

This affects any test that manually constructs framing dicts for:
- `identify_e2e_deliverables`
- `select_cutoff_deliverable`
- `commit_good_enough`

**Search pattern:** Find all occurrences of `"definition_of_finished"` in test files and replace with `"why"`.

---

## Out of Scope

- Step 3 changes (already done in 3.4)
- Widget changes
- Database/persistence

---

**Document Status:** Ready for Claude Code execution
