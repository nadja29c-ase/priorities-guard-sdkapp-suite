# SHARPEN V1 — INCREMENT 3: Step 2 High-Level Deliverable Identification

## Claude Code Briefing

---

## Objective

Implement the two MCP tools for Sharpen Step 2: High-Level Deliverable Identification. These tools enforce structured conversation to identify WHAT must exist and WHERE to stop before any work breakdown begins.

---

## Increment 3 Intent

This increment proves:
1. Step 2 requires confirmed Step 1 framing (initiative_framing object)
2. Deliverables are validated as concrete outputs, not activities
3. Unordered set semantics work (no implicit priority)
4. Single cutoff selection forces subtractive commitment
5. Confidence gating is consistent with Step 1 (only high accepted)

This increment is NOT about:
- Widgets or visual output
- Step 3 (work breakdown)
- Export functionality
- Ordering or sequencing deliverables

---

## Context

### Sharpen Philosophy (Must Inform Implementation)

Step 2 exists to answer one question only:

**"What must exist for this initiative to be considered done — and where do we intentionally stop?"**

Step 2:
- decides existence, not sequence
- creates filters, not plans
- exposes dependency chains without committing to them
- prevents premature execution thinking

**If Step 2 introduces timelines, ordering, estimates, or task breakdowns → Sharpen is broken.**

### Subtractive Facilitation (Core Mechanism)

Step 2 applies continuous pressure to **eliminate work before commitment**.

The flow:
1. Tool 2.1: Surface what COULD exist (bounded, unordered set)
2. Tool 2.2: Force user to choose WHERE TO STOP

This is the scalpel. Make the full shape visible, then cut.

### FACILITATOR ROLE (Enforce Everywhere)

**Prohibited LLM behaviors:**
- Suggesting what deliverables should be
- Ordering or prioritizing deliverables
- Recommending which deliverable to select
- Offering "you could also..." alternatives
- Estimating effort or time

**Required LLM behaviors:**
- Ask questions to surface concrete outputs
- Reflect back what user said
- Flag vague or activity-based deliverables without solving
- Wait for user's words and confirmation

If Sharpen ever "suggests" instead of "asks", it's broken.

### Building on Increment 2

- Increment 2 established: `frame_initiative_intent`, `frame_initiative_constraints`
- Increment 3 adds: two new tools following identical patterns
- Reuse: confidence gating, validation patterns, assistant_guidance structure, tool registration
- Step 2 tools require confirmed Step 1 output as input

---

## Directory Structure (No Changes)

Tools go in existing structure:

```
mcp_server/sharpen/
├── tools/
│   ├── __init__.py                       # Add imports for new tools
│   ├── base.py                           # Existing (no changes)
│   ├── export_checklist.py               # Existing (no changes)
│   ├── frame_initiative_intent.py        # Existing (no changes)
│   ├── frame_initiative_constraints.py   # Existing (no changes)
│   ├── identify_e2e_deliverables.py      # NEW
│   └── select_cutoff_deliverable.py      # NEW
├── tool_logic.py                         # Add new pure functions
└── tests/
    └── ... (test files)
```

---

## Step 2 Input Contract (Hard Requirement)

All Step 2 tools require confirmed Step 1 framing:

```json
{
  "initiative_framing": {
    "who": "string",
    "what": "string",
    "why": "string | null",
    "constraint_type": "time | capacity | budget | forced_mvp",
    "constraint_value": "string",
    "definition_of_finished": "string"
  }
}
```

If this object is missing, incomplete, or has empty required fields → tool must refuse with `isError=True`.

---

## Tool 2.1: `identify_e2e_deliverables`

### Purpose

Validate and confirm an unordered, bounded set of end-to-end deliverables that must exist for the initiative to be done.

Pattern: LLM facilitates → user states deliverables → LLM extracts → Tool validates/confirms.

### Tool Description (for ChatGPT discovery)

```
Records confirmed end-to-end deliverables for an initiative. Deliverables must be concrete outputs (things that exist), not activities. Returns an unordered set with no prioritization or sequencing. Requires confirmed initiative framing from Step 1 and confidence="high".

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
```

### Tool Annotations

```python
read_only_hint=False      # Produces structured output for user
destructive_hint=False    # No data modification
open_world_hint=False     # No external API calls
```

### Input Schema

```json
{
  "type": "object",
  "properties": {
    "initiative_framing": {
      "type": "object",
      "description": "Confirmed Step 1 framing (required). Must include who, what, constraint_type, constraint_value, definition_of_finished.",
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
    "candidate_deliverables": {
      "type": "array",
      "description": "Unordered list of deliverables. Array order has no meaning. Max 10 items.",
      "items": {
        "type": "object",
        "properties": {
          "name": { 
            "type": "string",
            "description": "Concrete deliverable name — a thing that exists, not an activity. ACCORDING TO THE USER."
          },
          "description": { 
            "type": "string",
            "description": "Brief description clarifying what this deliverable is. ACCORDING TO THE USER."
          }
        },
        "required": ["name"]
      },
      "minItems": 1,
      "maxItems": 10
    },
    "confidence": {
      "type": "string",
      "enum": ["high", "medium", "low"],
      "description": "Your confidence that all deliverables are user-confirmed concrete outputs. Must be 'high' to proceed."
    }
  },
  "required": ["initiative_framing", "candidate_deliverables", "confidence"],
  "additionalProperties": false
}
```

### Output (structuredContent)

**Success case (confidence=high, all valid):**
```json
{
  "confirmed_deliverables": [
    {
      "name": "string",
      "description": "string"
    }
  ],
  "count": "number",
  "confidence": "high",
  "confirmed": true,
  "assistant_guidance": {
    "action": "PROCEED_TO_CUTOFF",
    "instruction": "string"
  }
}
```

**Rejection case (confidence < high):**
```json
{
  "error": "confidence_too_low",
  "confidence_provided": "medium | low",
  "assistant_guidance": {
    "action": "ASK_CLARIFYING",
    "instruction": "string"
  }
}
```

**Validation failure (missing framing, invalid deliverables):**
```json
{
  "error": "validation_error | missing_framing | too_many_deliverables | activity_based_deliverable",
  "details": "...",
  "assistant_guidance": {
    "action": "REFUSE | ASK_CLARIFYING",
    "instruction": "string"
  }
}
```

### Validation Rules (Structural Only)

| Condition | Result |
|-----------|--------|
| `confidence` != "high" | Reject with ASK_CLARIFYING |
| `initiative_framing` missing or incomplete | Reject with REFUSE |
| `candidate_deliverables` empty | Reject with ASK_CLARIFYING |
| `candidate_deliverables` > 10 items | Reject with REFUSE (hard cap) |
| Any deliverable missing `name` | Reject with validation_error |
| Any deliverable `name` is empty | Reject with ASK_CLARIFYING |
| All valid | Return confirmed_deliverables |

**Note:** Activity-based detection (verbs like "improve", "build", "work on") is NOT enforced structurally. The tool description instructs the LLM to flag these during facilitation. Semantic quality is the LLM's job.

### assistant_guidance Instructions

**When confidence rejected:**
```
STAY IN YOUR FACILITATOR ROLE. Deliverables are not yet concrete or user-confirmed. Ask clarifying questions to turn activities into outputs. For each vague item, ask: 'What will exist after this is done?' Do not suggest what the deliverable should be. Get user confirmation, then call with confidence='high'.
```

**When framing missing:**
```
Initiative framing must be confirmed before identifying deliverables. Complete Step 1 first using frame_initiative_intent and frame_initiative_constraints. Do not proceed without confirmed framing.
```

**When too many deliverables:**
```
Maximum 10 deliverables allowed. This is a forcing function — if more exist, the initiative may need decomposition. Ask: 'Which of these are truly essential for the initiative to be considered done?' Do not suggest which to keep.
```

**When confirmed (success):**
```
Deliverables confirmed. Present them back to the user as an unordered list — no numbering, no priority implied. Then proceed to select the cutoff deliverable by asking: 'If you could only complete one of these right now, which would still make the initiative worth doing?' Do not suggest which to select. Call select_cutoff_deliverable with the user's choice.
```

---

## Tool 2.2: `select_cutoff_deliverable`

### Purpose

Force a deliberate stopping point. This tool selects WHERE work intentionally stops, not "what's next."

The canonical question: **"If you stopped after this deliverable, would the initiative still be worth doing?"**

### Tool Description (for ChatGPT discovery)

```
Records the user's selected cutoff deliverable — the point where work intentionally stops for now. This defines the current scope boundary. No ordering, scheduling, or planning allowed. Requires confirmed deliverables from Step 2.1 and confidence="high".

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
```

### Tool Annotations

```python
read_only_hint=False      # Produces structured output for user
destructive_hint=False    # No data modification
open_world_hint=False     # No external API calls
```

### Input Schema

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
      "description": "Name of the deliverable chosen as the cutoff point. Must match exactly one name in confirmed_deliverables. ACCORDING TO THE USER."
    },
    "confidence": {
      "type": "string",
      "enum": ["high", "medium", "low"],
      "description": "Your confidence that the selection is user-confirmed. Must be 'high' to proceed."
    }
  },
  "required": ["initiative_framing", "confirmed_deliverables", "selected_deliverable_name", "confidence"],
  "additionalProperties": false
}
```

### Output (structuredContent)

**Success case:**
```json
{
  "focus_deliverable": {
    "name": "string",
    "description": "string"
  },
  "scope_boundary": "explicit",
  "deferred_deliverables": [
    {
      "name": "string",
      "description": "string"
    }
  ],
  "confidence": "high",
  "confirmed": true,
  "assistant_guidance": {
    "action": "PROCEED_TO_STEP_3",
    "instruction": "string"
  }
}
```

**Rejection case (confidence < high):**
```json
{
  "error": "confidence_too_low",
  "confidence_provided": "medium | low",
  "assistant_guidance": {
    "action": "ASK_CLARIFYING",
    "instruction": "string"
  }
}
```

**Validation failure:**
```json
{
  "error": "validation_error | missing_framing | missing_deliverables | selection_not_found",
  "details": "...",
  "assistant_guidance": {
    "action": "REFUSE | ASK_CLARIFYING",
    "instruction": "string"
  }
}
```

### Validation Rules (Structural Only)

| Condition | Result |
|-----------|--------|
| `confidence` != "high" | Reject with ASK_CLARIFYING |
| `initiative_framing` missing or incomplete | Reject with REFUSE |
| `confirmed_deliverables` empty | Reject with REFUSE |
| `selected_deliverable_name` empty | Reject with ASK_CLARIFYING |
| `selected_deliverable_name` not in confirmed_deliverables | Reject with selection_not_found |
| All valid | Return focus_deliverable + deferred_deliverables |

### assistant_guidance Instructions

**When confidence rejected:**
```
STAY IN YOUR FACILITATOR ROLE. The selection is not yet user-confirmed. Ask: 'If you stopped after [their tentative choice], would the initiative still be worth doing?' Wait for their answer. Do not suggest which to select. Get explicit confirmation, then call with confidence='high'.
```

**When selection not found:**
```
The selected deliverable does not match any confirmed deliverable. Present the list of confirmed deliverables and ask the user to select one by name. Do not suggest which to select.
```

**When framing or deliverables missing:**
```
Cannot select cutoff without confirmed framing and deliverables. Complete Step 1 and Step 2.1 first.
```

**When confirmed (success):**
```
Scope boundary confirmed. Present: 'Focus deliverable: [NAME]. Deferred for now: [LIST].' Then proceed to Step 3: work breakdown for the focus deliverable only. Do not discuss deferred items. Do not suggest tasks. Ask: 'What work items must be completed to produce [FOCUS DELIVERABLE]?'
```

---

## Pure Business Logic (`tool_logic.py`)

### Functions to Implement

**`validate_initiative_framing_complete(framing: dict | None) -> dict`**

Returns:
```python
{
    "valid": bool,
    "missing": list[str],  # List of missing required fields
}
```

Logic:
- Check framing is not None
- Check required fields: who, what, constraint_type, constraint_value, definition_of_finished
- Each field must be non-empty string
- Return list of missing/empty fields

---

**`validate_e2e_deliverables(framing: dict | None, deliverables: list[dict] | None, confidence: str | None) -> dict`**

Returns:
```python
{
    "valid": bool,
    "error_type": str | None,  # "confidence_too_low" | "missing_framing" | "too_many_deliverables" | "empty_deliverables" | "invalid_deliverable" | None
    "error_details": str | None,
    "confirmed_deliverables": list[dict] | None,  # Only if valid
    "count": int,
}
```

Logic:
- First validate confidence == "high" (reject if not)
- Then validate framing is complete (use `validate_initiative_framing_complete`)
- Then validate deliverables:
  - Not None and not empty
  - Max 10 items
  - Each has non-empty `name`
  - Normalize: add empty `description` if missing
- Return confirmed_deliverables with normalized structure

---

**`validate_cutoff_selection(framing: dict | None, deliverables: list[dict] | None, selected_name: str | None, confidence: str | None) -> dict`**

Returns:
```python
{
    "valid": bool,
    "error_type": str | None,  # "confidence_too_low" | "missing_framing" | "missing_deliverables" | "selection_not_found" | "empty_selection" | None
    "error_details": str | None,
    "focus_deliverable": dict | None,  # Only if valid
    "deferred_deliverables": list[dict] | None,  # Only if valid
}
```

Logic:
- First validate confidence == "high" (reject if not)
- Then validate framing is complete
- Then validate deliverables exist and not empty
- Then validate selected_name:
  - Not None and not empty
  - Matches exactly one deliverable name (case-sensitive)
- If match found:
  - focus_deliverable = matched deliverable
  - deferred_deliverables = all others
- Return results

---

## Unit Tests

### `test_identify_e2e_deliverables.py`

**Pure Logic Tests (`validate_e2e_deliverables`):**

1. `test_valid_deliverables_returns_confirmed`
   - Input: valid framing, valid deliverables, confidence="high"
   - Assert: valid=True, confirmed_deliverables matches input

2. `test_confidence_low_rejects`
   - Input: valid framing, valid deliverables, confidence="low"
   - Assert: valid=False, error_type="confidence_too_low"

3. `test_confidence_medium_rejects`
   - Input: valid framing, valid deliverables, confidence="medium"
   - Assert: valid=False, error_type="confidence_too_low"

4. `test_missing_framing_rejects`
   - Input: framing=None, valid deliverables, confidence="high"
   - Assert: valid=False, error_type="missing_framing"

5. `test_incomplete_framing_rejects`
   - Input: framing missing constraint_type, valid deliverables, confidence="high"
   - Assert: valid=False, error_type="missing_framing"

6. `test_empty_deliverables_rejects`
   - Input: valid framing, deliverables=[], confidence="high"
   - Assert: valid=False, error_type="empty_deliverables"

7. `test_too_many_deliverables_rejects`
   - Input: valid framing, 11 deliverables, confidence="high"
   - Assert: valid=False, error_type="too_many_deliverables"

8. `test_deliverable_missing_name_rejects`
   - Input: valid framing, deliverable with name="", confidence="high"
   - Assert: valid=False, error_type="invalid_deliverable"

9. `test_deliverable_without_description_normalizes`
   - Input: valid framing, deliverable without description key, confidence="high"
   - Assert: valid=True, confirmed_deliverables[0].description = ""

10. `test_max_10_deliverables_allowed`
    - Input: valid framing, exactly 10 valid deliverables, confidence="high"
    - Assert: valid=True, count=10

**Handler Tests:**

11. `test_valid_input_returns_proceed_action`
    - Assert: assistant_guidance.action = "PROCEED_TO_CUTOFF"

12. `test_low_confidence_returns_clarifying_action`
    - Assert: assistant_guidance.action = "ASK_CLARIFYING"

13. `test_missing_framing_returns_refuse_action`
    - Assert: assistant_guidance.action = "REFUSE"

14. `test_too_many_deliverables_returns_refuse_action`
    - Assert: assistant_guidance.action = "REFUSE"

---

### `test_select_cutoff_deliverable.py`

**Pure Logic Tests (`validate_cutoff_selection`):**

1. `test_valid_selection_returns_focus_and_deferred`
   - Input: valid framing, 3 deliverables, select first, confidence="high"
   - Assert: valid=True, focus_deliverable=first, deferred_deliverables=[second, third]

2. `test_confidence_low_rejects`
   - Input: valid everything, confidence="low"
   - Assert: valid=False, error_type="confidence_too_low"

3. `test_missing_framing_rejects`
   - Input: framing=None
   - Assert: valid=False, error_type="missing_framing"

4. `test_missing_deliverables_rejects`
   - Input: valid framing, deliverables=None
   - Assert: valid=False, error_type="missing_deliverables"

5. `test_empty_deliverables_rejects`
   - Input: valid framing, deliverables=[]
   - Assert: valid=False, error_type="missing_deliverables"

6. `test_empty_selection_rejects`
   - Input: valid everything, selected_name=""
   - Assert: valid=False, error_type="empty_selection"

7. `test_selection_not_found_rejects`
   - Input: valid everything, selected_name="Nonexistent"
   - Assert: valid=False, error_type="selection_not_found"

8. `test_selection_is_case_sensitive`
   - Input: deliverable name="API Docs", selected_name="api docs"
   - Assert: valid=False, error_type="selection_not_found"

9. `test_single_deliverable_selection_returns_empty_deferred`
   - Input: 1 deliverable, select it
   - Assert: valid=True, deferred_deliverables=[]

10. `test_focus_deliverable_preserves_description`
    - Input: deliverable with description
    - Assert: focus_deliverable.description preserved

**Handler Tests:**

11. `test_valid_input_returns_proceed_to_step_3_action`
    - Assert: assistant_guidance.action = "PROCEED_TO_STEP_3"

12. `test_low_confidence_returns_clarifying_action`
    - Assert: assistant_guidance.action = "ASK_CLARIFYING"

13. `test_selection_not_found_returns_clarifying_action`
    - Assert: assistant_guidance.action = "ASK_CLARIFYING"

14. `test_missing_framing_returns_refuse_action`
    - Assert: assistant_guidance.action = "REFUSE"

---

## Integration Tests

### `test_step2_flow.py`

1. `test_tool_2_1_listed_in_registry`
   - Assert: "identify_e2e_deliverables" in tool list

2. `test_tool_2_2_listed_in_registry`
   - Assert: "select_cutoff_deliverable" in tool list

3. `test_tool_2_1_has_correct_annotations`
   - Assert: readOnlyHint=False, destructiveHint=False, openWorldHint=False

4. `test_tool_2_2_has_correct_annotations`
   - Assert: same as Tool 2.1

5. `test_tool_2_1_input_schema_requires_initiative_framing`
   - Assert: "initiative_framing" in required fields

6. `test_tool_2_1_input_schema_requires_confidence`
   - Assert: "confidence" in required fields

7. `test_tool_2_2_input_schema_requires_confirmed_deliverables`
   - Assert: "confirmed_deliverables" in required fields

8. `test_tool_2_2_input_schema_requires_selected_deliverable_name`
   - Assert: "selected_deliverable_name" in required fields

---

## Success Criteria

1. ✅ Both tools registered and discoverable via tools/list
2. ✅ Tool 2.1 requires initiative_framing, rejects if missing/incomplete
3. ✅ Tool 2.1 requires confidence="high", rejects if lower
4. ✅ Tool 2.1 enforces max 10 deliverables
5. ✅ Tool 2.1 returns unordered confirmed_deliverables
6. ✅ Tool 2.2 requires initiative_framing + confirmed_deliverables
7. ✅ Tool 2.2 requires confidence="high", rejects if lower
8. ✅ Tool 2.2 validates selection exists in confirmed_deliverables
9. ✅ Tool 2.2 returns focus_deliverable + deferred_deliverables
10. ✅ assistant_guidance contains correct action and instruction for each state
11. ✅ All unit tests pass
12. ✅ All integration tests pass

---

## Out of Scope (This Increment)

- Step 3 tools (work breakdown)
- Widget/visual output for deliverables
- Ordering or prioritization of deliverables
- Persistence of deliverable data
- Export functionality
- Activity-based detection (semantic, not structural — LLM's job)

---

## OpenAI Compliance Checklist

| Requirement | Tool 2.1 | Tool 2.2 |
|-------------|----------|----------|
| Description is factual, single purpose | ✅ | ✅ |
| inputSchema complete with descriptions | ✅ | ✅ |
| Annotations present (readOnlyHint, etc.) | ✅ | ✅ |
| securitySchemes: [noauth] | ✅ | ✅ |
| structuredContent follows schema | ✅ | ✅ |
| assistant_guidance provides LLM instructions | ✅ | ✅ |
| Tool names human-readable, descriptive | ✅ | ✅ |
| Tool inputs minimal — no "just in case" fields | ✅ | ✅ |

---

## Notes for Claude Code

1. **Follow existing patterns.** Look at `frame_initiative_intent.py` and `frame_initiative_constraints.py` for structure. Copy that pattern exactly.

2. **Confidence gating is non-negotiable.** Both tools must reject confidence < "high". This is the same pattern as Step 1.

3. **Pure logic in `tool_logic.py`.** Validation functions return plain dicts. No MCP types in logic layer.

4. **Handler builds guidance.** The handler maps logic output to assistant_guidance strings. Logic layer only returns error_type, handler provides full instruction text.

5. **Framing validation is reusable.** Create `validate_initiative_framing_complete()` as a shared helper — both tools need it.

6. **Deliverables are unordered.** Array order has no semantic meaning. This must be reflected in how Tool 2.1's success guidance presents them (no numbering, no "first").

7. **Selection is case-sensitive.** `selected_deliverable_name` must match exactly. This is intentional — forces precision.

8. **Self-registration.** Both tools self-register at import time. Add imports to `tools/__init__.py`.

9. **Error messages.** When returning isError=True, provide human-readable message in content and structured details in structuredContent.

10. **Test isolation.** Unit tests for logic functions should not import handler. Handler tests can mock logic if needed.

11. **FACILITATOR ROLE IS NON-NEGOTIABLE.** Every assistant_guidance instruction must reinforce: ask questions, never suggest, never recommend which deliverable to select, use user's exact words. If any guidance tells the LLM to suggest or recommend — it's wrong.

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

Nothing else. Deferred deliverables are explicitly out of scope for Step 3.

---

**Document Status:** Ready for Claude Code execution
