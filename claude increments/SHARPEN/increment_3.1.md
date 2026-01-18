# SHARPEN V1 — INCREMENT 3.1: Sculpted Deliverable Support

## Claude Code Briefing

---

## Objective

Extend `select_cutoff_deliverable` to allow users to sculpt a new focus deliverable by merging or reshaping confirmed deliverables, rather than being forced to select an exact match.

---

## Why This Change

Current limitation: Tool requires exact name match from `confirmed_deliverables`. This fails when:

- Deliverables have natural coupling ("API + minimal docs" is really one shippable thing)
- User realizes at selection time that scope should be tighter
- Contract work requires delivering multiple items together

**Sharpen philosophy:** If the user realizes "these two are actually one deliverable" — that's facilitated insight. Current tool blocks it.

**Subtractive facilitation:** Merging 3 deliverables → 1 is MORE subtractive, not less. Tool should enable this.

**CRITICAL INVARIANT — No Scope Expansion:**
A sculpted deliverable may ONLY combine or reduce scope from the deliverables it replaces. It must not introduce new outcomes, audiences, or success criteria beyond what was already confirmed. Sculpting tightens scope — it never expands it.

---

## Design Change

Allow either:
1. **Select existing** (current behavior) — pick one by exact name
2. **Sculpt new** — define a new focus deliverable that replaces one or more confirmed deliverables

User provides ONE of these, not both.

---

## Updated Input Schema for `select_cutoff_deliverable`

```json
{
  "type": "object",
  "properties": {
    "initiative_framing": {
      "type": "object",
      "description": "Confirmed Step 1 framing (required).",
      "properties": {
        "who": { "type": "string" },
        "what": { "type": "string" },
        "why": { "type": "string" },
        "constraint_type": {
          "type": "string",
          "enum": ["time", "capacity", "budget", "forced_mvp"]
        },
        "constraint_value": { "type": "string" },
        "definition_of_finished": { "type": "string" }
      },
      "required": ["who", "what", "constraint_type", "constraint_value", "definition_of_finished"]
    },
    "confirmed_deliverables": {
      "type": "array",
      "description": "Confirmed deliverables from identify_e2e_deliverables.",
      "items": {
        "type": "object",
        "properties": {
          "name": { "type": "string" },
          "description": { "type": "string" }
        },
        "required": ["name"]
      },
      "minItems": 1
    },
    "selected_deliverable_name": {
      "type": "string",
      "description": "Select ONE existing deliverable by exact name. Use this OR sculpted_deliverable, not both. ACCORDING TO THE USER."
    },
    "sculpted_deliverable": {
      "type": "object",
      "description": "Define a NEW focus deliverable that combines or reshapes existing ones. Use this OR selected_deliverable_name, not both. ACCORDING TO THE USER.",
      "properties": {
        "name": {
          "type": "string",
          "description": "Name for the sculpted deliverable. Must be concrete, not activity-based."
        },
        "description": {
          "type": "string",
          "description": "What this sculpted deliverable includes."
        },
        "replaces": {
          "type": "array",
          "items": { "type": "string" },
          "description": "Names of confirmed deliverables this replaces. All names must exist in confirmed_deliverables.",
          "minItems": 1
        }
      },
      "required": ["name", "replaces"]
    },
    "confidence": {
      "type": "string",
      "enum": ["high", "medium", "low"],
      "description": "Your confidence that the selection/sculpt is user-confirmed. Must be 'high' to proceed."
    }
  },
  "required": ["initiative_framing", "confirmed_deliverables", "confidence"],
  "additionalProperties": false
}
```

**Note:** JSON Schema `oneOf` is not used — validation logic handles mutual exclusivity.

---

## Updated Tool Description

Replace the existing DESCRIPTION with:

```
Records the user's focus deliverable — either by selecting an existing one OR sculpting a new one that combines/reshapes confirmed deliverables. This defines the current scope boundary. No ordering, scheduling, or planning allowed. Requires confirmed deliverables from Step 2.1 and confidence="high".

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
  You: "Looking at these deliverables, what's the minimum shippable scope?"
  User: "Just the API — docs can wait"
  You: "So 'Deployed REST API' is the focus. Documentation is deferred. Correct?"
  User: "Yes"
  → Call with selected_deliverable_name="Deployed REST API", confidence="high"

EXAMPLE CONVERSATION (Sculpting):
  You: "Looking at these deliverables, what's the minimum shippable scope?"
  User: "I can't ship API without at least basic docs"
  You: "So API and Documentation are really one deliverable. What would you call this combined scope?"
  User: "Deployed API with endpoint reference"
  You: "So 'Deployed API with endpoint reference' replaces both 'REST API' and 'API Documentation'. The Admin Dashboard is deferred. Correct?"
  User: "Yes"
  → Call with sculpted_deliverable={name="Deployed API with endpoint reference", replaces=["REST API", "API Documentation"]}, confidence="high"
```

---

## Updated Validation Logic (`tool_logic.py`)

### Update `validate_cutoff_selection` signature:

```python
def validate_cutoff_selection(
    framing: dict | None,
    deliverables: list[dict] | None,
    selected_name: str | None,
    sculpted: dict | None,  # NEW
    confidence: str | None,
) -> dict[str, Any]:
```

### Validation order:

1. Confidence must be "high"
2. Framing must be complete
3. Deliverables must exist and not be empty
4. Duplicate deliverable names check
5. **Mutual exclusivity:** exactly one of `selected_name` or `sculpted` must be provided
6. If `selected_name`: validate exact match (existing logic)
7. If `sculpted`: validate sculpt (new logic)

### New validation for sculpted deliverable:

```python
# 5. Mutual exclusivity check
has_selected = selected_name is not None and selected_name.strip()
has_sculpted = sculpted is not None

if has_selected and has_sculpted:
    return {
        "valid": False,
        "error_type": "both_selection_methods",
        "error_details": "Provide selected_deliverable_name OR sculpted_deliverable, not both.",
        "focus_deliverable": None,
        "deferred_deliverables": None,
    }

if not has_selected and not has_sculpted:
    return {
        "valid": False,
        "error_type": "no_selection_method",
        "error_details": "Provide selected_deliverable_name OR sculpted_deliverable.",
        "focus_deliverable": None,
        "deferred_deliverables": None,
    }

# 6. Selection path (existing)
if has_selected:
    # ... existing selection logic ...

# 7. Sculpt path (NEW)
if has_sculpted:
    sculpt_name = (sculpted.get("name") or "").strip()
    sculpt_description = (sculpted.get("description") or "").strip()
    replaces = sculpted.get("replaces") or []

    # Validate sculpt name not empty
    if not sculpt_name:
        return {
            "valid": False,
            "error_type": "empty_sculpt_name",
            "error_details": "Sculpted deliverable must have a name.",
            "focus_deliverable": None,
            "deferred_deliverables": None,
        }

    # Validate replaces not empty
    if not replaces:
        return {
            "valid": False,
            "error_type": "empty_replaces",
            "error_details": "Sculpted deliverable must replace at least one confirmed deliverable.",
            "focus_deliverable": None,
            "deferred_deliverables": None,
        }

    # Validate all replaces exist in confirmed_deliverables
    confirmed_names = {d.get("name", "") for d in deliverables}
    invalid_replaces = [r for r in replaces if r not in confirmed_names]
    if invalid_replaces:
        return {
            "valid": False,
            "error_type": "invalid_replaces",
            "error_details": f"These names are not in confirmed deliverables: {', '.join(invalid_replaces)}",
            "focus_deliverable": None,
            "deferred_deliverables": None,
        }

    # Build focus (clean output — no process metadata)
    # Note: replaces is used internally to compute deferred, but NOT passed to Step 3
    focus = {
        "name": sculpt_name,
        "description": sculpt_description,
    }

    # Compute deferred using replaces (internal bookkeeping)
    deferred = [
        {"name": d.get("name", ""), "description": d.get("description", "")}
        for d in deliverables
        if d.get("name", "") not in replaces
    ]

    return {
        "valid": True,
        "error_type": None,
        "error_details": None,
        "focus_deliverable": focus,
        "deferred_deliverables": deferred,
        "_internal_replaces": replaces,  # For handler guidance only, not in Step 3 contract
    }
```

---

## Updated Handler (`select_cutoff_deliverable.py`)

### Update Pydantic models:

```python
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
    sculpted_deliverable: Optional[SculptedDeliverable] = None  # NEW
    confidence: Optional[Literal["high", "medium", "low"]] = None
```

### Update handler to pass sculpted to logic:

```python
sculpted_dict = validated_request.sculpted_deliverable.model_dump() if validated_request.sculpted_deliverable else None

result = validate_cutoff_selection(
    framing=framing_dict,
    deliverables=deliverables_list,
    selected_name=validated_request.selected_deliverable_name,
    sculpted=sculpted_dict,  # NEW
    confidence=validated_request.confidence,
)
```

### Add new guidance messages:

```python
GUIDANCE_BOTH_METHODS = (
    "Provide either selected_deliverable_name OR sculpted_deliverable, not both. "
    "Ask the user: 'Are you selecting an existing deliverable as-is, or combining "
    "multiple into a tighter scope?' Wait for clarification."
)

GUIDANCE_NO_METHOD = (
    "No focus deliverable specified. Ask: 'Looking at these deliverables, what's "
    "the minimum shippable scope? You can pick one as-is or combine multiple into "
    "a tighter focus.' Wait for the user's answer. Do not suggest."
)

GUIDANCE_EMPTY_SCULPT_NAME = (
    "Sculpted deliverable needs a name. Ask: 'What would you call this combined "
    "scope?' Use the user's exact words. Do not suggest a name."
)

GUIDANCE_EMPTY_REPLACES = (
    "Sculpted deliverable must replace at least one confirmed deliverable. "
    "Ask: 'Which of the confirmed deliverables does this replace?' "
    "Wait for the user's answer."
)

GUIDANCE_INVALID_REPLACES = (
    "Some names in 'replaces' don't match confirmed deliverables. "
    "Present the confirmed deliverable names and ask the user to clarify "
    "which ones the sculpted deliverable replaces."
)
```

### Update error handling in handler:

```python
elif error_type == "both_selection_methods":
    guidance = GUIDANCE_BOTH_METHODS
    action = "ASK_CLARIFYING"
elif error_type == "no_selection_method":
    guidance = GUIDANCE_NO_METHOD
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
```

### Update success guidance builder:

```python
def build_confirmed_guidance(focus_name: str, deferred_names: list[str], replaces: list[str] | None = None) -> str:
    """Build guidance for confirmed selection/sculpt.
    
    Args:
        focus_name: Name of the focus deliverable
        deferred_names: Names of deferred deliverables
        replaces: If sculpted, the names that were replaced (for guidance only)
    """
    if replaces:
        replaces_str = ", ".join(replaces)
        scope_intro = f"Sculpted focus: '{focus_name}' (replaces: {replaces_str})."
    else:
        scope_intro = f"Focus deliverable: '{focus_name}'."
    
    if deferred_names:
        deferred_str = ", ".join(deferred_names)
        return (
            f"Scope boundary confirmed. {scope_intro} "
            f"Deferred for now: {deferred_str}. "
            f"Proceed to Step 3: work breakdown for '{focus_name}' only. "
            f"Do not discuss deferred items. Do not suggest tasks. "
            f"Ask: 'What work items must be completed to produce {focus_name}?'"
        )
    else:
        return (
            f"Scope boundary confirmed. {scope_intro} "
            f"Nothing deferred — all confirmed deliverables are replaced by this focus. "
            f"Proceed to Step 3: work breakdown for '{focus_name}' only. "
            f"Do not suggest tasks. "
            f"Ask: 'What work items must be completed to produce {focus_name}?'"
        )
```

### Update handler success path to call guidance builder:

```python
# In handler, after validation succeeds:
focus = result["focus_deliverable"]
deferred = result["deferred_deliverables"]
deferred_names = [d["name"] for d in deferred]

# Get replaces from internal field (only present for sculpted)
replaces = result.get("_internal_replaces")  # None for selection path

guidance = build_confirmed_guidance(
    focus_name=focus["name"],
    deferred_names=deferred_names,
    replaces=replaces,
)
```

---

## Unit Tests to Add

### `test_select_cutoff_deliverable.py`

**Pure Logic Tests (sculpt path):**

```python
def test_sculpted_deliverable_returns_focus_and_deferred(self, valid_framing, valid_deliverables):
    """Valid sculpted deliverable returns focus with replaces and deferred."""
    sculpted = {
        "name": "API with basic docs",
        "description": "Combined scope",
        "replaces": ["Deployed REST API", "OpenAPI spec"],
    }
    
    result = validate_cutoff_selection(
        framing=valid_framing,
        deliverables=valid_deliverables,
        selected_name=None,
        sculpted=sculpted,
        confidence="high",
    )
    
    assert result["valid"] is True
    assert result["focus_deliverable"]["name"] == "API with basic docs"
    assert result["focus_deliverable"].get("sculpted") is None  # No process metadata in output
    assert result["_internal_replaces"] == ["Deployed REST API", "OpenAPI spec"]  # Internal only
    assert len(result["deferred_deliverables"]) == 1  # Integration tests

def test_both_methods_rejects(self, valid_framing, valid_deliverables):
    """Providing both selection methods is rejected."""
    result = validate_cutoff_selection(
        framing=valid_framing,
        deliverables=valid_deliverables,
        selected_name="Deployed REST API",
        sculpted={"name": "Combined", "replaces": ["Deployed REST API"]},
        confidence="high",
    )
    
    assert result["valid"] is False
    assert result["error_type"] == "both_selection_methods"

def test_no_method_rejects(self, valid_framing, valid_deliverables):
    """Providing neither selection method is rejected."""
    result = validate_cutoff_selection(
        framing=valid_framing,
        deliverables=valid_deliverables,
        selected_name=None,
        sculpted=None,
        confidence="high",
    )
    
    assert result["valid"] is False
    assert result["error_type"] == "no_selection_method"

def test_empty_sculpt_name_rejects(self, valid_framing, valid_deliverables):
    """Sculpted deliverable with empty name is rejected."""
    result = validate_cutoff_selection(
        framing=valid_framing,
        deliverables=valid_deliverables,
        selected_name=None,
        sculpted={"name": "", "replaces": ["Deployed REST API"]},
        confidence="high",
    )
    
    assert result["valid"] is False
    assert result["error_type"] == "empty_sculpt_name"

def test_empty_replaces_rejects(self, valid_framing, valid_deliverables):
    """Sculpted deliverable with empty replaces is rejected."""
    result = validate_cutoff_selection(
        framing=valid_framing,
        deliverables=valid_deliverables,
        selected_name=None,
        sculpted={"name": "Combined", "replaces": []},
        confidence="high",
    )
    
    assert result["valid"] is False
    assert result["error_type"] == "empty_replaces"

def test_invalid_replaces_rejects(self, valid_framing, valid_deliverables):
    """Sculpted deliverable with non-existent replaces is rejected."""
    result = validate_cutoff_selection(
        framing=valid_framing,
        deliverables=valid_deliverables,
        selected_name=None,
        sculpted={"name": "Combined", "replaces": ["Nonexistent"]},
        confidence="high",
    )
    
    assert result["valid"] is False
    assert result["error_type"] == "invalid_replaces"

def test_sculpt_replaces_all_returns_empty_deferred(self, valid_framing, valid_deliverables):
    """Sculpted deliverable replacing all confirmed returns empty deferred."""
    all_names = [d["name"] for d in valid_deliverables]
    
    result = validate_cutoff_selection(
        framing=valid_framing,
        deliverables=valid_deliverables,
        selected_name=None,
        sculpted={"name": "Everything combined", "replaces": all_names},
        confidence="high",
    )
    
    assert result["valid"] is True
    assert result["deferred_deliverables"] == []
```

**Handler Tests (sculpt path):**

```python
@pytest.mark.asyncio
async def test_sculpted_input_returns_proceed_action(self, valid_framing, valid_deliverables):
    """Valid sculpted input returns action='PROCEED_TO_STEP_3'."""
    arguments = {
        "initiative_framing": valid_framing,
        "confirmed_deliverables": valid_deliverables,
        "sculpted_deliverable": {
            "name": "Combined API",
            "replaces": ["Deployed REST API", "OpenAPI spec"],
        },
        "confidence": "high",
    }
    
    result = await handle(arguments)
    
    assert result.isError is not True
    assert result.structuredContent["confirmed"] is True
    assert result.structuredContent["assistant_guidance"]["action"] == "PROCEED_TO_STEP_3"

@pytest.mark.asyncio
async def test_both_methods_returns_clarifying_action(self, valid_framing, valid_deliverables):
    """Both selection methods returns action='ASK_CLARIFYING'."""
    arguments = {
        "initiative_framing": valid_framing,
        "confirmed_deliverables": valid_deliverables,
        "selected_deliverable_name": "Deployed REST API",
        "sculpted_deliverable": {"name": "Combined", "replaces": ["Deployed REST API"]},
        "confidence": "high",
    }
    
    result = await handle(arguments)
    
    assert result.isError is True
    assert result.structuredContent["error"] == "both_selection_methods"
    assert result.structuredContent["assistant_guidance"]["action"] == "ASK_CLARIFYING"
```

---

## Update Existing Tests

Existing tests for selection path must be updated to pass `sculpted=None`:

```python
# Before
result = validate_cutoff_selection(
    framing=valid_framing,
    deliverables=valid_deliverables,
    selected_name="Deployed REST API",
    confidence="high",
)

# After
result = validate_cutoff_selection(
    framing=valid_framing,
    deliverables=valid_deliverables,
    selected_name="Deployed REST API",
    sculpted=None,  # Add this
    confidence="high",
)
```

---

## Success Criteria

1. ✅ `selected_deliverable_name` still works (selection path unchanged)
2. ✅ `sculpted_deliverable` allows merging confirmed deliverables
3. ✅ Mutual exclusivity enforced (exactly one method)
4. ✅ `replaces` validated against confirmed_deliverables
5. ✅ Focus output is clean (no `sculpted` flag — process metadata stays internal)
6. ✅ Deferred correctly computed (confirmed minus replaced)
7. ✅ All existing tests pass (with updated signature)
8. ✅ All new tests pass
9. ✅ Guidance reflects sculpt vs selection appropriately

---

## Step 3 Contract (What This Produces)

When Step 2 completes, this is the handoff to Step 3:

```json
{
  "initiative_framing": {
    "who": "string",
    "what": "string",
    "why": "string | null",
    "constraint_type": "time | capacity | budget | forced_mvp",
    "constraint_value": "string",
    "definition_of_finished": "string"
  },
  "focus_deliverable": {
    "name": "string",
    "description": "string"
  }
}
```

**Clean contract:** Step 3 receives the same structure whether focus was selected or sculpted. No process metadata (`sculpted`, `replaces`) leaks into the domain model. Step 3 only cares about WHAT must be produced, not HOW the decision was made.

---

## Architecture Note: Error Taxonomy

This increment adds 5 new error types for sculpt validation:
- `both_selection_methods`
- `no_selection_method`
- `empty_sculpt_name`
- `empty_replaces`
- `invalid_replaces`

This is acceptable because:
- All map to `ASK_CLARIFYING` (user can always fix)
- All have facilitator-pure guidance
- None require `REFUSE`

If error taxonomy grows further in Step 3+, consider consolidation.

---

## Out of Scope (This Increment)

- Allowing sculpt at Step 2.1 (only at cutoff selection)
- Recursive sculpting (sculpt from sculpted)
- Validation that sculpted name is "concrete" (LLM's job)

---

## OpenAI Compliance

| Requirement | Status |
|-------------|--------|
| Tool inputs minimal | ✅ Two paths, user picks one |
| inputSchema complete | ✅ Both options documented |
| No behavioral instructions in description | ✅ |
| assistant_guidance for all states | ✅ |

---

**Document Status:** Ready for Claude Code execution
