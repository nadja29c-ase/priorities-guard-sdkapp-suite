# SHARPEN V1 — INCREMENT 3.7: Structural Enforcement of Realism/Value Loop

## Claude Code Briefing

---

## Objective

Structurally enforce the realism/value evaluation loop by requiring `deferred_deliverables` as an explicit input to `select_focus_deliverable`. This prevents semantic inversion errors and makes the "maximize work not done" methodology auditable.

**Current state:** User picks focus → system computes deferred (passive, error-prone)

**New state:** User explicitly names deferrals → system validates → remaining becomes candidate pool for focus selection (active, enforced)

---

## Design Rationale

### Problem

The realism/value evaluation loop between `identify_e2e_deliverables` and `select_focus_deliverable` exists only in DESCRIPTION guidance. ChatGPT can:
- Skip the loop entirely
- Ask "what to remove?" then invert the answer when filling `selected_deliverable_name`
- Call focus selection without accounting for what was consciously cut

### Solution

Make `deferred_deliverables` a required artifact of the loop:
- If the loop ran, it produced deferrals (even if empty after explicit "all are realistic" confirmation)
- `select_focus_deliverable` cannot be called without accounting for deferrals
- Validation computes `remaining = confirmed - deferred` and enforces selection from that pool

### Behavioral Change

| Before | After |
|--------|-------|
| `selected_deliverable_name` picks from `confirmed_deliverables` | `selected_deliverable_name` picks from `remaining` (confirmed minus deferred) |
| Deferred list computed as side-effect | Deferred list is explicit input |
| Loop enforcement via prompt only | Loop enforcement via schema + validation |

---

## Files to Modify

1. `mcp_server/sharpen/tools/select_focus_deliverable.py`
2. `mcp_server/sharpen/tool_logic.py`
3. `tests/unit/mcp_sharpen/test_select_focus_deliverable.py`

---

## Change 1: `select_focus_deliverable.py` — Schema Update

### Update INPUT_SCHEMA

Add `deferred_deliverables` field after `confirmed_deliverables`:

```python
"deferred_deliverables": {
    "type": "array",
    "description": "Deliverables explicitly deferred during realism/value evaluation. Names must match confirmed_deliverables. Can be empty ONLY after explicit confirmation that all deliverables are realistic within the constraint. ACCORDING TO THE USER — never infer deferrals.",
    "items": {"type": "string"},
},
```

Update `required` array to include it:

```python
"required": ["initiative_framing", "confirmed_deliverables", "deferred_deliverables", "confidence"],
```

### Update Pydantic Model

Add to `SelectCutoffRequest` (note: class name can stay as-is, it's internal):

```python
deferred_deliverables: List[str]
```

### Update handle() Function

Pass the new field to validation:

```python
# After Pydantic validation, extract deferred list
deferred_list = validated_request.deferred_deliverables or []

# Update the validate_cutoff_selection call
result = validate_cutoff_selection(
    framing=framing_dict,
    deliverables=deliverables_list,
    deferred=deferred_list,  # NEW PARAMETER
    selected_name=validated_request.selected_deliverable_name,
    sculpted=sculpted_dict,
    confidence=validated_request.confidence,
)
```

---

## Change 2: `select_focus_deliverable.py` — DESCRIPTION Update

Replace the entire DESCRIPTION with:

```python
DESCRIPTION = """Records the user's focus deliverable after the realism/value evaluation loop has run. Requires deferred_deliverables (output of the loop) + either selection or sculpting from remaining deliverables. Requires confidence="high".

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
  You: "Focus is 'API'. Deferred: 'Tests', 'Docs'. Correct?"
  User: "Yes"
  → Call with deferred_deliverables=["Tests", "Docs"], selected_deliverable_name="API", confidence="high"

EXAMPLE CONVERSATION (auto-select after deferrals):
  [After identify_e2e_deliverables confirmed: "Checklist", "RASCI doc", "Buddy program"]
  You: "Given 3 hours/week, can all three realistically be completed?"
  User: "No way — just the checklist maybe"
  You: "So 'RASCI doc' and 'Buddy program' are deferred. That leaves 'Checklist' as the only remaining deliverable — it becomes the focus. Correct?"
  User: "Yes"
  → Call with deferred_deliverables=["RASCI doc", "Buddy program"], selected_deliverable_name="Checklist", confidence="high"

EXAMPLE CONVERSATION (all realistic — explicit confirmation):
  [After identify_e2e_deliverables confirmed: "Landing page", "Contact form"]
  You: "Given your constraint of 1 month, can both realistically be completed?"
  User: "Yes, both are doable"
  You: "Confirming: no deferrals needed — both 'Landing page' and 'Contact form' fit within 1 month. Which ONE is the focus?"
  User: "Landing page"
  → Call with deferred_deliverables=[], selected_deliverable_name="Landing page", confidence="high"
"""
```

---

## Change 3: `select_focus_deliverable.py` — Guidance Constants

Add new guidance constants:

```python
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
```

Update handler error handling to use new error types (see Change 4 for error types).

---

## Change 4: `tool_logic.py` — Update `validate_cutoff_selection`

### Update Function Signature

```python
def validate_cutoff_selection(
    framing: dict | None,
    deliverables: list[dict] | None,
    deferred: list[str] | None,  # NEW PARAMETER
    selected_name: str | None,
    sculpted: dict | None,
    confidence: str | None,
) -> dict[str, Any]:
```

### Update Docstring

Add to Args:
```python
deferred: List of deliverable names explicitly deferred during realism/value loop
```

### Add Validation After Duplicate Check (after step 4, before mutual exclusivity)

```python
# 5. Deferred validation
if deferred is None:
    return {
        "valid": False,
        "error_type": "missing_deferred",
        "error_details": "deferred_deliverables parameter required. Run realism/value loop first.",
        "focus_deliverable": None,
        "deferred_deliverables": None,
    }

# Validate all deferred names exist in confirmed
confirmed_names_set = set(d.get("name", "") for d in deliverables)
invalid_deferred = [name for name in deferred if name not in confirmed_names_set]
if invalid_deferred:
    return {
        "valid": False,
        "error_type": "invalid_deferred",
        "error_details": f"These deferred names are not in confirmed deliverables: {', '.join(invalid_deferred)}",
        "focus_deliverable": None,
        "deferred_deliverables": None,
    }

# Compute remaining deliverables
deferred_set = set(deferred)
remaining = [d for d in deliverables if d.get("name", "") not in deferred_set]

# 6. Over-cutting check
if len(remaining) == 0:
    return {
        "valid": False,
        "error_type": "over_cutting",
        "error_details": "All deliverables were deferred. At least one must remain.",
        "focus_deliverable": None,
        "deferred_deliverables": None,
    }

# 7. Auto-select if only one remains
if len(remaining) == 1 and not selected_name and not sculpted:
    focus = {
        "name": remaining[0].get("name", ""),
        "description": remaining[0].get("description", ""),
    }
    # Deferred list includes both explicit deferrals and confirmed-but-not-remaining
    deferred_output = [
        {"name": d.get("name", ""), "description": d.get("description", "")}
        for d in deliverables
        if d.get("name", "") in deferred_set
    ]
    return {
        "valid": True,
        "error_type": None,
        "error_details": None,
        "focus_deliverable": focus,
        "deferred_deliverables": deferred_output,
        "auto_selected": True,
    }
```

### Update Mutual Exclusivity Check

Change the `no_selection_method` error to check against `remaining` count:

```python
# 8. Ambiguity check — multiple remaining but no selection
if not has_selected and not has_sculpted:
    if len(remaining) > 1:
        remaining_names = [d.get("name", "") for d in remaining]
        return {
            "valid": False,
            "error_type": "ambiguous_remaining",
            "error_details": f"Multiple deliverables remain: {', '.join(remaining_names)}. Select one.",
            "focus_deliverable": None,
            "deferred_deliverables": None,
            "remaining_names": remaining_names,
        }
```

### Update Selection Path

Change selection to validate against `remaining`, not `deliverables`:

```python
# 9. Selection path — validate against remaining
if has_selected:
    selected_name = selected_name.strip()
    remaining_names_set = set(d.get("name", "") for d in remaining)
    
    if selected_name not in remaining_names_set:
        # Check if it was deferred
        if selected_name in deferred_set:
            return {
                "valid": False,
                "error_type": "selection_was_deferred",
                "error_details": f"'{selected_name}' was deferred. Select from remaining: {', '.join(remaining_names_set)}",
                "focus_deliverable": None,
                "deferred_deliverables": None,
            }
        # Check if it exists at all
        if selected_name not in confirmed_names_set:
            return {
                "valid": False,
                "error_type": "selection_not_found",
                "error_details": f"'{selected_name}' does not match any confirmed deliverable.",
                "focus_deliverable": None,
                "deferred_deliverables": None,
            }
    
    # Find the selected deliverable
    focus = None
    for d in remaining:
        if d.get("name", "") == selected_name:
            focus = {
                "name": d.get("name", ""),
                "description": d.get("description", ""),
            }
            break
    
    # Compute deferred output: explicit deferrals + implicit deferrals (remaining but not selected)
    deferred_output = [
        {"name": d.get("name", ""), "description": d.get("description", "")}
        for d in deliverables
        if d.get("name", "") in deferred_set
           or (d.get("name", "") in remaining_names_set and d.get("name", "") != selected_name)
    ]
    
    return {
        "valid": True,
        "error_type": None,
        "error_details": None,
        "focus_deliverable": focus,
        "deferred_deliverables": deferred_output,
    }
```

### Update Sculpt Path

Change sculpt to validate `replaces` against `remaining`:

```python
# 10. Sculpt path — validate replaces against remaining
# ... existing name validation ...

# Validate all replaces exist in REMAINING (not just confirmed)
remaining_names_set = set(d.get("name", "") for d in remaining)
invalid_replaces = [r for r in replaces if r not in remaining_names_set]
if invalid_replaces:
    # Check if any were deferred
    deferred_in_replaces = [r for r in invalid_replaces if r in deferred_set]
    if deferred_in_replaces:
        return {
            "valid": False,
            "error_type": "replaces_includes_deferred",
            "error_details": f"Cannot sculpt from deferred deliverables: {', '.join(deferred_in_replaces)}",
            "focus_deliverable": None,
            "deferred_deliverables": None,
        }
    return {
        "valid": False,
        "error_type": "invalid_replaces",
        "error_details": f"These names are not in remaining deliverables: {', '.join(invalid_replaces)}",
        "focus_deliverable": None,
        "deferred_deliverables": None,
    }

# ... rest of sculpt logic, but compute deferred from remaining minus replaces ...
# Deferred = explicit deferrals + (remaining minus replaced)
replaces_set = set(replaces)
deferred_output = [
    {"name": d.get("name", ""), "description": d.get("description", "")}
    for d in deliverables
    if d.get("name", "") in deferred_set or (d.get("name", "") in remaining_names_set and d.get("name", "") not in replaces_set)
]
```

---

## Change 5: `select_focus_deliverable.py` — Handler Error Mapping

Add error type mappings in the handler's error handling section:

```python
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
    guidance = GUIDANCE_SELECTION_NOT_FOUND  # Reuse existing, or create specific
    action = "ASK_CLARIFYING"
elif error_type == "replaces_includes_deferred":
    guidance = GUIDANCE_INVALID_REPLACES  # Reuse existing
    action = "ASK_CLARIFYING"
```

Handle auto-select success case:

```python
# After valid result, check for auto-select
if result.get("auto_selected"):
    structured["auto_selected"] = True
    structured["assistant_guidance"]["instruction"] = GUIDANCE_AUTO_SELECTED
```

---

## Unit Tests

### `test_select_focus_deliverable.py` — Add New Test Class

```python
# ============================================================================
# Deferred Deliverables Validation Tests
# ============================================================================


class TestDeferredDeliverablesValidation:
    """Tests for deferred_deliverables parameter validation."""

    def test_missing_deferred_rejects(self, valid_framing, valid_deliverables):
        """Missing deferred_deliverables is rejected."""
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            deferred=None,
            selected_name="Deployed REST API",
            sculpted=None,
            confidence="high",
        )
        
        assert result["valid"] is False
        assert result["error_type"] == "missing_deferred"

    def test_empty_deferred_allowed(self, valid_framing, valid_deliverables):
        """Empty deferred list is allowed (all deliverables survived loop)."""
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            deferred=[],
            selected_name="Deployed REST API",
            sculpted=None,
            confidence="high",
        )
        
        assert result["valid"] is True
        assert result["focus_deliverable"]["name"] == "Deployed REST API"

    def test_invalid_deferred_name_rejects(self, valid_framing, valid_deliverables):
        """Deferred name not in confirmed deliverables is rejected."""
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            deferred=["Nonexistent Deliverable"],
            selected_name="Deployed REST API",
            sculpted=None,
            confidence="high",
        )
        
        assert result["valid"] is False
        assert result["error_type"] == "invalid_deferred"
        assert "Nonexistent" in result["error_details"]

    def test_over_cutting_all_deferred_rejects(self, valid_framing, valid_deliverables):
        """Deferring all deliverables is rejected."""
        all_names = [d["name"] for d in valid_deliverables]
        
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            deferred=all_names,
            selected_name=None,
            sculpted=None,
            confidence="high",
        )
        
        assert result["valid"] is False
        assert result["error_type"] == "over_cutting"

    def test_auto_select_single_remaining(self, valid_framing, valid_deliverables):
        """Single remaining deliverable is auto-selected."""
        # Defer all but one
        deferred = ["OpenAPI spec", "Integration tests"]
        
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            deferred=deferred,
            selected_name=None,
            sculpted=None,
            confidence="high",
        )
        
        assert result["valid"] is True
        assert result["auto_selected"] is True
        assert result["focus_deliverable"]["name"] == "Deployed REST API"

    def test_ambiguous_remaining_without_selection_rejects(self, valid_framing, valid_deliverables):
        """Multiple remaining without selection is rejected."""
        # Defer only one, leaving two
        deferred = ["Integration tests"]
        
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            deferred=deferred,
            selected_name=None,
            sculpted=None,
            confidence="high",
        )
        
        assert result["valid"] is False
        assert result["error_type"] == "ambiguous_remaining"
        assert "Deployed REST API" in result["remaining_names"]
        assert "OpenAPI spec" in result["remaining_names"]

    def test_selection_from_remaining_succeeds(self, valid_framing, valid_deliverables):
        """Selection from remaining deliverables succeeds."""
        deferred = ["Integration tests"]
        
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            deferred=deferred,
            selected_name="OpenAPI spec",
            sculpted=None,
            confidence="high",
        )
        
        assert result["valid"] is True
        assert result["focus_deliverable"]["name"] == "OpenAPI spec"

    def test_selection_of_deferred_deliverable_rejects(self, valid_framing, valid_deliverables):
        """Selecting a deferred deliverable is rejected."""
        deferred = ["Deployed REST API"]
        
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            deferred=deferred,
            selected_name="Deployed REST API",
            sculpted=None,
            confidence="high",
        )
        
        assert result["valid"] is False
        assert result["error_type"] == "selection_was_deferred"

    def test_deferred_output_includes_all_non_focus(self, valid_framing, valid_deliverables):
        """Deferred output includes explicit deferrals + remaining non-focus."""
        deferred = ["Integration tests"]
        
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            deferred=deferred,
            selected_name="Deployed REST API",
            sculpted=None,
            confidence="high",
        )
        
        assert result["valid"] is True
        deferred_names = [d["name"] for d in result["deferred_deliverables"]]
        assert "Integration tests" in deferred_names
        assert "OpenAPI spec" in deferred_names
        assert "Deployed REST API" not in deferred_names


class TestRemainingInvariant:
    """Tests for confirmed - deferred = remaining invariant."""

    def test_remaining_equals_confirmed_minus_deferred(self, valid_framing, valid_deliverables):
        """Verify remaining = confirmed - deferred invariant."""
        deferred = ["Integration tests"]
        confirmed_names = {d["name"] for d in valid_deliverables}
        expected_remaining = confirmed_names - set(deferred)
        
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            deferred=deferred,
            selected_name="Deployed REST API",
            sculpted=None,
            confidence="high",
        )
        
        assert result["valid"] is True
        # Focus + implicit deferrals = remaining
        focus_name = result["focus_deliverable"]["name"]
        deferred_names = {d["name"] for d in result["deferred_deliverables"]}
        actual_remaining = {focus_name} | (expected_remaining - {focus_name})
        assert actual_remaining == expected_remaining


class TestDeferredWithSculptPath:
    """Tests for deferred_deliverables with sculpt path."""

    def test_sculpt_from_remaining_succeeds(self, valid_framing, valid_deliverables):
        """Sculpting from remaining deliverables succeeds."""
        deferred = ["Integration tests"]
        
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            deferred=deferred,
            selected_name=None,
            sculpted={
                "name": "API with docs",
                "replaces": ["Deployed REST API", "OpenAPI spec"],
            },
            confidence="high",
        )
        
        assert result["valid"] is True
        assert result["focus_deliverable"]["name"] == "API with docs"

    def test_sculpt_including_deferred_rejects(self, valid_framing, valid_deliverables):
        """Sculpting that includes deferred deliverables is rejected."""
        deferred = ["Integration tests"]
        
        result = validate_cutoff_selection(
            framing=valid_framing,
            deliverables=valid_deliverables,
            deferred=deferred,
            selected_name=None,
            sculpted={
                "name": "Everything",
                "replaces": ["Deployed REST API", "Integration tests"],  # Includes deferred
            },
            confidence="high",
        )
        
        assert result["valid"] is False
        assert result["error_type"] == "replaces_includes_deferred"
```

### Update Existing Tests

All existing tests in `TestValidateCutoffSelection` and handler tests need `deferred=[]` added to their calls:

```python
# Example: Update test_valid_selection_returns_focus_and_deferred
def test_valid_selection_returns_focus_and_deferred(self, valid_framing, valid_deliverables):
    """Valid selection returns focus_deliverable and deferred_deliverables."""
    result = validate_cutoff_selection(
        framing=valid_framing,
        deliverables=valid_deliverables,
        deferred=[],  # ADD THIS
        selected_name="Deployed REST API",
        sculpted=None,
        confidence="high",
    )
    # ... rest unchanged
```

Handler tests need `deferred_deliverables: []` in arguments:

```python
# Example: Update test_valid_input_returns_proceed_to_step_3_action
arguments = {
    "initiative_framing": valid_framing,
    "confirmed_deliverables": valid_deliverables,
    "deferred_deliverables": [],  # ADD THIS
    "selected_deliverable_name": "Deployed REST API",
    "confidence": "high",
}
```

---

## Integration Test Considerations

No new integration tests required. The change is:
- Schema validation (covered by unit tests)
- Business logic (covered by unit tests)
- No external API calls
- No database changes
- No new endpoints

Manual testing via MCP Inspector recommended for LLM behavior validation.

---

## Out of Scope

- `identify_e2e_deliverables` changes (it already outputs confirmed list)
- Database schema changes
- Widget changes
- Other tools

---

## Verification Checklist

### Schema (`select_focus_deliverable.py`)
- [ ] INPUT_SCHEMA includes `deferred_deliverables` array field
- [ ] `required` array includes `"deferred_deliverables"`
- [ ] Pydantic model includes `deferred_deliverables: List[str]`

### DESCRIPTION (`select_focus_deliverable.py`)
- [ ] SUSPENDED BEHAVIORS includes "Asking what to REMOVE/cut during focus selection"
- [ ] REALISM/VALUE LOOP section explains the prerequisite
- [ ] Example conversations show explicit deferral flow
- [ ] Auto-select behavior documented

### Guidance Constants (`select_focus_deliverable.py`)
- [ ] GUIDANCE_MISSING_DEFERRED exists
- [ ] GUIDANCE_INVALID_DEFERRED exists
- [ ] GUIDANCE_OVER_CUTTING exists
- [ ] GUIDANCE_AUTO_SELECTED exists
- [ ] GUIDANCE_AMBIGUOUS_REMAINING exists

### Logic (`tool_logic.py`)
- [ ] `validate_cutoff_selection` accepts `deferred` parameter
- [ ] `missing_deferred` error type implemented
- [ ] `invalid_deferred` error type implemented
- [ ] `over_cutting` error type implemented
- [ ] `ambiguous_remaining` error type implemented
- [ ] `selection_was_deferred` error type implemented
- [ ] `replaces_includes_deferred` error type implemented
- [ ] Auto-select logic for single remaining
- [ ] Selection validates against remaining, not confirmed
- [ ] Sculpt validates replaces against remaining

### Tests
- [ ] All existing tests updated with `deferred=[]` / `deferred_deliverables: []`
- [ ] `TestDeferredDeliverablesValidation` class added
- [ ] `TestRemainingInvariant` class added
- [ ] `TestDeferredWithSculptPath` class added
- [ ] All tests pass

---

## Risk Assessment

**Medium risk.** This is a breaking schema change:
- Existing tool calls without `deferred_deliverables` will fail
- ChatGPT will need to learn the new required field

**Mitigation:**
- Clear error message guides LLM to run realism loop
- DESCRIPTION explains the prerequisite explicitly
- Auto-select reduces friction when only one remains

**Rollback:** Revert to previous increment if LLM struggles with the new flow.

---

**Document Status:** Ready for Claude Code execution
