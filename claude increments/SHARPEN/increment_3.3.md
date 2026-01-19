# SHARPEN V1 — INCREMENT 3.3: Assistant Guidance Hardening

## Claude Code Briefing

---

## Objective

Strengthen all `assistant_guidance` messages across Sharpen tools to prevent LLM fallback to "helpful consultant" mode after tool errors.

**Root cause**: DESCRIPTION binding rules control entry behavior. But after a tool error, the LLM's immediate context is the `assistant_guidance` — which was too soft and allowed mode drift.

---

## The Pattern

**Current (too soft):**
```python
"Ask clarifying questions until [X] is specific. Get user confirmation..."
```

**Required (firm):**
```python
"SHARPEN MODE STILL ACTIVE. Ask ONE question about [specific field]. Then stop and wait. Do not explain, suggest, or plan."
```

Key elements:
1. **Mode reminder**: "SHARPEN MODE STILL ACTIVE"
2. **Singular action**: "ONE question" (not "questions")
3. **Hard stop**: "Then stop and wait"
4. **Explicit prohibition**: "Do not explain, suggest, or plan"

---

## Files to Modify

1. `mcp_server/sharpen/tools/frame_initiative_intent.py`
2. `mcp_server/sharpen/tools/frame_initiative_constraints.py`
3. `mcp_server/sharpen/tools/identify_e2e_deliverables.py`
4. `mcp_server/sharpen/tools/select_cutoff_deliverable.py`

---

## Tool 1: `frame_initiative_intent.py`

### Guidance: confidence_too_low (inline in handler)

**Current:**
```python
"assistant_guidance": {
    "instruction": "STAY IN YOUR FACILITATOR ROLE and ask the user clarifying questions until WHO is specific and WHAT is a concrete artifact. Get user confirmation, then call with confidence='high'.",
},
```

**Replace with:**
```python
"assistant_guidance": {
    "action": "ASK_CLARIFYING",
    "instruction": "SHARPEN MODE STILL ACTIVE. Ask ONE question about WHO or WHAT (whichever is vaguer). Then stop and wait. Do not explain, suggest, or plan.",
},
```

### Guidance: missing_fields (inline in handler)

**Current:**
```python
"assistant_guidance": {
    "instruction": "Ask the user to provide the missing information. Do not suggest what it should be.",
},
```

**Replace with:**
```python
"assistant_guidance": {
    "action": "ASK_CLARIFYING",
    "instruction": "SHARPEN MODE STILL ACTIVE. Ask ONE question about the missing field. Then stop and wait. Do not explain, suggest, or plan.",
},
```

### Guidance: success (proceed to constraints)

**Current:**
```python
"assistant_guidance": {
    "instruction": "Proceed with further framing the initiative and capture the one most dominant initiative constraint by calling frame_initiative_constraints. NEVER suggest what constraints might be — ask the user.",
},
```

**Replace with:**
```python
"assistant_guidance": {
    "action": "PROCEED_TO_CONSTRAINTS",
    "instruction": "Intent confirmed. Ask ONE question: 'What's the one constraint that limits this most — a deadline, limited hours, or a budget cap?' Then stop and wait. Do not suggest constraints.",
},
```

---

## Tool 2: `frame_initiative_constraints.py`

### Guidance: confidence_too_low (inline in handler)

**Current:**
```python
"assistant_guidance": {
    "instruction": "Ask clarifying questions until CONSTRAINT is specific and DEFINITION OF FINISHED is verifiable. Get user confirmation, then call with confidence='high'.",
},
```

**Replace with:**
```python
"assistant_guidance": {
    "action": "ASK_CLARIFYING",
    "instruction": "SHARPEN MODE STILL ACTIVE. Ask ONE question about CONSTRAINT or DEFINITION OF FINISHED (whichever is vaguer). Then stop and wait. Do not explain, suggest, or plan.",
},
```

### Guidance: force_constraint (user claims no constraints)

**Current:**
```python
"assistant_guidance": {
    "instruction": "Ask: 'What's the first small win that would prove this is working as intended?' Wait for their answer — do not suggest. Use their answer as constraint_type='forced_mvp' and constraint_value=their answer. Then call this tool again with confidence='high'.",
},
```

**Replace with:**
```python
"assistant_guidance": {
    "action": "ASK_CLARIFYING",
    "instruction": "SHARPEN MODE STILL ACTIVE. Ask exactly: 'What's the smallest result that would make this worth continuing?' Then stop and wait. Do not suggest examples. Use their answer as forced_mvp.",
},
```

### Guidance: missing_fields (inline in handler)

**Current:**
```python
"assistant_guidance": {
    "instruction": "Ask the user to provide the missing information. Do not suggest what it should be. Do not estimate for them.",
},
```

**Replace with:**
```python
"assistant_guidance": {
    "action": "ASK_CLARIFYING",
    "instruction": "SHARPEN MODE STILL ACTIVE. Ask ONE question about the missing field. Then stop and wait. Do not explain, suggest, or plan.",
},
```

### Guidance: success (proceed to deliverables)

**Current:**
```python
"assistant_guidance": {
    "instruction": "Consolidate the outputs from frame_initiative_intent (WHO, WHAT, WHY) and frame_initiative_constraints (CONSTRAINT, DEFINITION OF FINISHED). Present the complete initiative framing to the user using their exact words and ask for final confirmation before proceeding.",
},
```

**Replace with:**
```python
"assistant_guidance": {
    "action": "CONFIRM_FRAMING",
    "instruction": "Present the complete framing using the user's exact words: WHO, WHAT, WHY (if any), CONSTRAINT, DEFINITION OF FINISHED. Then ask: 'Is this correct?' Stop and wait. Do not elaborate or add context.",
},
```

---

## Tool 3: `identify_e2e_deliverables.py`

### Define constants (replace existing)

```python
GUIDANCE_CONFIDENCE_REJECTED = (
    "SHARPEN MODE STILL ACTIVE. "
    "Ask ONE question to make the vaguest deliverable concrete: 'When [action] is done, what will exist?' "
    "Then stop and wait. Do not explain, suggest, or plan."
)

GUIDANCE_FRAMING_MISSING = (
    "SHARPEN MODE STILL ACTIVE. "
    "Step 1 framing required first. Ask: 'Before we identify deliverables, who benefits from this work?' "
    "Then stop and wait. Do not explain the process."
)

GUIDANCE_TOO_MANY_DELIVERABLES = (
    "SHARPEN MODE STILL ACTIVE. "
    "Ask ONE question: 'Which of these are truly essential for the initiative to be done?' "
    "Then stop and wait. Do not suggest which to remove."
)

GUIDANCE_EMPTY_DELIVERABLES = (
    "SHARPEN MODE STILL ACTIVE. "
    "Ask ONE question: 'What needs to exist for this initiative to be done?' "
    "Then stop and wait. Do not suggest deliverables."
)

GUIDANCE_INVALID_DELIVERABLE = (
    "SHARPEN MODE STILL ACTIVE. "
    "Ask ONE question about the empty deliverable name. "
    "Then stop and wait. Do not suggest what it should be."
)

GUIDANCE_CONFIRMED = (
    "Deliverables confirmed. Present them as an unordered list (no numbering). "
    "Then ask: 'Quick check — how big does this feel? XS / S / M / L / XL (gut feel only).' "
    "Stop and wait.\n\n"
    "If XS/S/M → ask: 'If you could only complete one right now, which would it be?'\n"
    "If L/XL → ask: 'That size sometimes means there's room to subtract. If this had to be M or smaller, what could be removed?'\n\n"
    "Then stop and wait. Do not suggest. Do not plan."
)
```

---

## Tool 4: `select_cutoff_deliverable.py`

### Define constants (replace existing)

```python
GUIDANCE_CONFIDENCE_REJECTED = (
    "SHARPEN MODE STILL ACTIVE. "
    "Ask ONE question: 'Which one deliverable must exist first?' "
    "Then stop and wait. Do not suggest which to select."
)

GUIDANCE_SELECTION_NOT_FOUND = (
    "SHARPEN MODE STILL ACTIVE. "
    "Present the confirmed deliverable names. Ask: 'Which of these is the focus?' "
    "Then stop and wait. Do not suggest."
)

GUIDANCE_MISSING_FRAMING = (
    "SHARPEN MODE STILL ACTIVE. "
    "Step 1 framing required. Ask: 'Before selecting focus, who benefits from this work?' "
    "Then stop and wait."
)

GUIDANCE_MISSING_DELIVERABLES = (
    "SHARPEN MODE STILL ACTIVE. "
    "Deliverables required first. Ask: 'What needs to exist for this initiative to be done?' "
    "Then stop and wait."
)

GUIDANCE_DUPLICATE_NAMES = (
    "SHARPEN MODE STILL ACTIVE. "
    "Ask: 'Two deliverables have the same name. Which ones are actually distinct?' "
    "Then stop and wait. Do not suggest names."
)

GUIDANCE_BOTH_METHODS = (
    "SHARPEN MODE STILL ACTIVE. "
    "Ask: 'Are you selecting one deliverable as-is, or combining multiple into a tighter scope?' "
    "Then stop and wait."
)

GUIDANCE_NO_METHOD = (
    "SHARPEN MODE STILL ACTIVE. "
    "Ask: 'If you could only complete one of these right now, which would it be?' "
    "Then stop and wait. Do not suggest."
)

GUIDANCE_EMPTY_SCULPT_NAME = (
    "SHARPEN MODE STILL ACTIVE. "
    "Ask: 'What would you call this combined scope?' "
    "Then stop and wait. Do not suggest a name."
)

GUIDANCE_EMPTY_REPLACES = (
    "SHARPEN MODE STILL ACTIVE. "
    "Ask: 'Which confirmed deliverables does this replace?' "
    "Then stop and wait."
)

GUIDANCE_INVALID_REPLACES = (
    "SHARPEN MODE STILL ACTIVE. "
    "Present the confirmed deliverable names. Ask: 'Which of these does the sculpted deliverable replace?' "
    "Then stop and wait."
)
```

### Update `build_confirmed_guidance` function

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

---

## Verification

After changes, confirm each guidance message:
1. ✅ Starts with "SHARPEN MODE STILL ACTIVE" (error states) or clear action (success states)
2. ✅ Contains "ONE question" or specific single question
3. ✅ Contains "stop and wait"
4. ✅ Contains "Do not" prohibition
5. ✅ No multi-step instructions
6. ✅ No explanatory content

---

## Success Criteria

1. ✅ All error guidance includes "SHARPEN MODE STILL ACTIVE"
2. ✅ All guidance specifies singular action ("ONE question" or exact question text)
3. ✅ All guidance includes hard stop ("Then stop and wait")
4. ✅ All guidance includes explicit prohibition
5. ✅ No guidance contains explanations, examples, or multi-step flows
6. ✅ All existing tests still pass

---

## Out of Scope

- DESCRIPTION changes (already correct)
- Logic changes (not needed)
- Schema changes (not needed)
- New tests (behavior is in guidance, not structure)

---

**Document Status:** Ready for Claude Code execution
