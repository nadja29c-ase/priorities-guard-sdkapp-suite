# SHARPEN V1 — INCREMENT 2: Step 1 Facilitated Initiative Framing

## Claude Code Briefing

---

## Objective

Implement the two MCP tools for Sharpen Step 1: Facilitated Initiative Framing. These tools enforce structured conversation to capture WHO, WHAT, CONSTRAINT, and DEFINITION OF FINISHED before any planning begins.

--- 

## Increment 2 Intent

This increment proves:
1. Sharpen can enforce sequential tool dependencies (Tool 2 requires Tool 1 output)
2. Iterative clarification loops work (call until confidence = high)
3. Constraint forcing logic works (reject "no constraints")
4. User confirmation gates work (no skipping ahead)

This increment is NOT about:
- Widgets or visual output
- Step 2 (deliverable identification)
- Export functionality
- Polish or UX refinement

---

## Context

### Sharpen Philosophy (Must Inform Implementation)

Sharpen's core stance is **subtractive facilitation** — helping users eliminate work before commitment.

Step 1 exists to create **filters**, not artifacts. The framing constrains everything that follows.

**CRITICAL — FACILITATOR ROLE (Enforce Everywhere):**

The LLM's role is to **facilitate the user's thinking**, NEVER to tell the user what to do.

This must be reinforced at EVERY touchpoint:
- Tool descriptions
- assistant_guidance instructions
- Error messages
- Clarifying question prompts

**Prohibited LLM behaviors:**
- Suggesting what WHO/WHAT/CONSTRAINT should be
- Offering examples unprompted
- Recommending priorities
- Filling in blanks for the user
- Giving advice of any kind

**Required LLM behaviors:**
- Ask questions
- Reflect back what user said
- Flag vagueness without solving it
- Wait for user's words

If Sharpen ever "tells" instead of "asks", it's broken.

Design principles that must be enforced:
- If the user hasn't confirmed framing, the model must not move on
- No deliverables without constraints
- No constraints without intent
- Sharpen decides nothing for the user — but refuses to proceed without decisions

### Building on Increment 1

- Increment 1 established: server, config, tool registry, dispatcher, export_checklist tool
- Increment 2 adds: two new tools following same patterns
- Reuse: tool registration, validation patterns, error handling, structuredContent format

---

## Directory Structure (No Changes)

Tools go in existing structure:

```
mcp_server/sharpen/
├── tools/
│   ├── __init__.py              # Add imports for new tools
│   ├── base.py                  # Existing (no changes)
│   ├── export_checklist.py      # Existing (no changes)
│   ├── frame_initiative_intent.py      # NEW
│   └── frame_initiative_constraints.py # NEW
├── tool_logic.py                # Add new pure functions
└── tests/
    ├── test_export_checklist.py # Existing
    ├── test_frame_initiative_intent.py      # NEW
    └── test_frame_initiative_constraints.py # NEW
```

---

## Tool 1: `frame_initiative_intent`

### Purpose

Capture WHO benefits and WHAT must exist. WHY is optional and used only to stress-test WHAT, never as a blocking requirement.

### Tool Description (for ChatGPT discovery)

```
Capture the beneficiary and intended outcome of an initiative. Call iteratively until confidence is high. FACILITATOR ROLE: Ask questions to draw out user's thinking. Never suggest what WHO or WHAT should be. Never give advice.
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
    "who": {
      "type": "string",
      "description": "Who is supposed to benefit from this work getting done first and foremost?"
    },
    "what": {
      "type": "string",
      "description": "What artifact, deliverable, or handoff must exist?"
    },
    "why": {
      "type": "string",
      "description": "Optional: So that the beneficiary benefits in what specific way? Used to test clarity of WHAT, not required."
    }
  },
  "additionalProperties": false
}
```

### Output (structuredContent)

```json
{
  "framing_intent": {
    "who": "string",
    "what": "string",
    "why": "string | null"
  },
  "confidence": "high | medium | low",
  "needs_clarification": "boolean",
  "clarify": {
    "type": "WHO | WHAT"
  },
  "assistant_guidance": {
    "action": "ASK_CLARIFYING | CONFIRM_AND_PROCEED",
    "instruction": "string"
  }
}
```

Note: `clarify` object only present when `needs_clarification = true`.

### Validation Logic (Pure Function)

| Condition | Confidence | Clarify |
|-----------|------------|---------|
| `who` empty or < 3 chars | low | WHO |
| `what` empty or < 5 chars | low | WHAT |
| `what` contains vague words: "improve", "better", "fix", "work on", "handle" | medium | WHAT |
| `what` is activity-based (starts with verb like "do", "make", "create" without concrete noun) | medium | WHAT |
| `why` empty | No impact | — |
| `who` valid + `what` valid | high | — |

Vague word detection should be case-insensitive and match partial words.

### assistant_guidance Instructions

**When clarify.type = WHO:**
```
Ask ONE question to clarify who benefits from this work. Do not suggest who it should be. Do not give examples. Do not ask about constraints or deliverables yet. Your role is to facilitate their thinking, not direct it. Call this tool again with updated components.
```

**When clarify.type = WHAT:**
```
Ask ONE question to clarify what must exist. Focus on artifact/deliverable, not activity. Do not suggest what it should be. Do not offer examples. Do not ask about constraints yet. Reflect their words back and ask them to sharpen. Call this tool again with updated components.
```

**When confidence = high:**
```
Present the intent: '[WHO] needs [WHAT]' (include 'so that [WHY]' only if WHY was provided). Ask user to confirm — do not rephrase or improve their words. If confirmed, call frame_initiative_constraints with confirmed_intent. Do not skip to deliverables. Do not offer suggestions for next steps beyond the constraint question.
```

---

## Tool 2: `frame_initiative_constraints`

### Purpose

Capture ONE dominant constraint (time/capacity/budget) and definition of finished. Requires confirmed intent from Tool 1. Rejects "no constraints" — forces user to identify MVP.

### Tool Description (for ChatGPT discovery)

```
Capture the dominant constraint and definition of finished for an initiative. Requires confirmed intent. Rejects empty constraints. FACILITATOR ROLE: Ask questions to surface user's real limits. Never suggest constraints. Never give advice.
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
    "confirmed_intent": {
      "type": "object",
      "description": "Confirmed output from frame_initiative_intent (required)",
      "properties": {
        "who": {
          "type": "string"
        },
        "what": {
          "type": "string"
        },
        "why": {
          "type": "string"
        }
      },
      "required": ["who", "what"]
    },
    "constraint_type": {
      "type": "string",
      "enum": ["time", "capacity", "budget"],
      "description": "Which constraint dominates: time (deadline), capacity (hours or focused sessions per week available), or budget?"
    },
    "constraint_value": {
      "type": "string",
      "description": "The specific constraint in the user's own words."
    },
    "definition_of_finished": {
      "type": "string",
      "description": "How will you know the WHAT is finished? Concrete, verifiable condition."
    },
    "user_claims_no_constraints": {
      "type": "boolean",
      "description": "Set true if user explicitly claims no constraints exist. Triggers forcing logic."
    }
  },
  "required": ["confirmed_intent"],
  "additionalProperties": false
}
```

### Output (structuredContent)

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
  "confidence": "high | medium | low",
  "needs_clarification": "boolean",
  "clarify": {
    "type": "CONSTRAINT | FINISHED"
  },
  "force_constraint": "boolean",
  "assistant_guidance": {
    "action": "ASK_CLARIFYING | FORCE_CONSTRAINT | CONFIRM_FRAMING_COMPLETE",
    "instruction": "string"
  }
}
```

Notes:
- `clarify` object only present when `needs_clarification = true`
- `force_constraint` only present and true when user claims no constraints
- `initiative_framing` contains complete framing (merges Tool 1 output with Tool 2 additions)

### Validation Logic (Pure Function)

| Condition | Result |
|-----------|--------|
| `confirmed_intent` missing | Return error, do not process |
| `confirmed_intent.who` or `confirmed_intent.what` empty | Return error, do not process |
| `user_claims_no_constraints = true` | Set `force_constraint = true`, return FORCE_CONSTRAINT action |
| `constraint_type` provided but `constraint_value` empty | low confidence, clarify CONSTRAINT |
| `constraint_value` vague: "soon", "flexible", "not sure", "whenever", "no rush" | medium confidence, clarify CONSTRAINT |
| `definition_of_finished` empty | low confidence, clarify FINISHED |
| `definition_of_finished` vague: "done", "complete", "finished", "ready", "working" | medium confidence, clarify FINISHED |
| All valid | high confidence |

### assistant_guidance Instructions

**When confirmed_intent missing or invalid:**
```
Intent framing must be confirmed before capturing constraints. Call frame_initiative_intent first and get user confirmation. Do not assume or infer the intent — the user must state it.
```

**When force_constraint = true:**
```
User claims no constraints. Ask: 'What is the smallest concrete result that would make this initiative worth continuing?' Wait for their answer — do not suggest what it might be. That result becomes the constraint. Do not accept 'no constraints'. Call this tool again with the answer.
```

**When clarify.type = CONSTRAINT:**
```
Ask ONE question to clarify the constraint. For time: 'By when?' For capacity: 'How many hours or focused sessions per week can you realistically invest?' For budget: 'What's the maximum spend?' Do not suggest values. Do not estimate for them. Wait for their number. Call this tool again with updated value.
```

**When clarify.type = FINISHED:**
```
Ask ONE question to clarify definition of finished. Push for concrete and verifiable: 'How will you know [WHAT] is actually done — what will you see or be able to do?' Do not suggest criteria. Do not give examples. Reflect their vague answer back and ask them to make it concrete. Call this tool again with updated value.
```

**When confidence = high:**
```
Present complete initiative framing using their exact words: '[WHO] needs [WHAT]. Constraint: [CONSTRAINT_TYPE] — [CONSTRAINT_VALUE]. Finished when: [DEFINITION_OF_FINISHED].' Ask user to confirm. Do not rephrase, improve, or add to their words. Only after confirmation, proceed to Step 2 (deliverable identification). Do not suggest what deliverables might be.
```

---

## Pure Business Logic (`tool_logic.py`)

### Functions to Implement

**`validate_initiative_intent(who: str, what: str, why: str | None) -> dict`**

Returns:
```python
{
    "framing_intent": {"who": str, "what": str, "why": str | None},
    "confidence": "high" | "medium" | "low",
    "needs_clarification": bool,
    "clarify_type": "WHO" | "WHAT" | None,
}
```

Logic:
- Normalize inputs (strip whitespace)
- Check WHO validity (not empty, >= 3 chars)
- Check WHAT validity (not empty, >= 5 chars, no vague words, not activity-based)
- WHY never affects confidence
- Return appropriate confidence and clarify_type

**`validate_initiative_constraints(confirmed_intent: dict, constraint_type: str | None, constraint_value: str | None, definition_of_finished: str | None, user_claims_no_constraints: bool) -> dict`**

Returns:
```python
{
    "initiative_framing": {
        "who": str,
        "what": str, 
        "why": str | None,
        "constraint_type": str,
        "constraint_value": str,
        "definition_of_finished": str,
    },
    "confidence": "high" | "medium" | "low",
    "needs_clarification": bool,
    "clarify_type": "CONSTRAINT" | "FINISHED" | None,
    "force_constraint": bool,
    "intent_missing": bool,
}
```

Logic:
- First validate confirmed_intent exists and has required fields
- If user_claims_no_constraints, set force_constraint=True, return early
- Check constraint_value validity
- Check definition_of_finished validity
- Merge confirmed_intent with constraint data into initiative_framing
- Return appropriate confidence and clarify_type

### Vague Word Lists (Constants)

```python
VAGUE_WHAT_WORDS = ["improve", "better", "fix", "work on", "handle", "deal with", "address"]
VAGUE_CONSTRAINT_WORDS = ["soon", "flexible", "not sure", "whenever", "no rush", "asap", "when possible"]
VAGUE_FINISHED_WORDS = ["done", "complete", "finished", "ready", "working", "good", "acceptable"]
```

---

## Handler Implementation Pattern

Follow the pattern established in `export_checklist.py`:

1. Pydantic models for input validation
2. Handler receives `arguments: dict`
3. Validate with Pydantic
4. Call pure logic function
5. Build assistant_guidance based on result
6. Return CallToolResult with content + structuredContent

### Error Handling

- Pydantic validation failure → Return `isError=True` with human-readable message + structured details
- Missing confirmed_intent in Tool 2 → Return `isError=True` with instruction to call Tool 1 first
- Unexpected exceptions → Log and return generic error message

---

## Unit Tests

### `test_frame_initiative_intent.py`

**Pure Logic Tests:**

1. `test_valid_who_and_what_returns_high_confidence`
   - Input: who="My team", what="A project dashboard"
   - Assert: confidence="high", needs_clarification=False

2. `test_empty_who_returns_low_confidence`
   - Input: who="", what="A dashboard"
   - Assert: confidence="low", clarify_type="WHO"

3. `test_short_who_returns_low_confidence`
   - Input: who="Me", what="A dashboard"
   - Assert: confidence="low", clarify_type="WHO"

4. `test_empty_what_returns_low_confidence`
   - Input: who="My team", what=""
   - Assert: confidence="low", clarify_type="WHAT"

5. `test_vague_what_returns_medium_confidence`
   - Input: who="My team", what="Improve the process"
   - Assert: confidence="medium", clarify_type="WHAT"

6. `test_activity_based_what_returns_medium_confidence`
   - Input: who="My team", what="Work on the backend"
   - Assert: confidence="medium", clarify_type="WHAT"

7. `test_empty_why_does_not_affect_confidence`
   - Input: who="My team", what="A project dashboard", why=""
   - Assert: confidence="high"

8. `test_why_is_included_when_provided`
   - Input: who="My team", what="A dashboard", why="so we can track progress"
   - Assert: framing_intent.why = "so we can track progress"

**Handler Tests:**

9. `test_valid_input_returns_confirm_action`
   - Assert: assistant_guidance.action = "CONFIRM_AND_PROCEED"

10. `test_invalid_input_returns_clarifying_action`
    - Assert: assistant_guidance.action = "ASK_CLARIFYING"

11. `test_missing_all_fields_returns_error`
    - Input: {}
    - Assert: isError=True

### `test_frame_initiative_constraints.py`

**Pure Logic Tests:**

1. `test_valid_constraint_and_finished_returns_high_confidence`
   - Input: valid confirmed_intent, constraint_type="time", constraint_value="by end of Q1", definition_of_finished="Dashboard deployed and team trained"
   - Assert: confidence="high"

2. `test_missing_confirmed_intent_returns_intent_missing`
   - Input: confirmed_intent=None
   - Assert: intent_missing=True

3. `test_empty_confirmed_intent_who_returns_intent_missing`
   - Input: confirmed_intent={"who": "", "what": "something"}
   - Assert: intent_missing=True

4. `test_user_claims_no_constraints_returns_force_constraint`
   - Input: user_claims_no_constraints=True
   - Assert: force_constraint=True

5. `test_empty_constraint_value_returns_low_confidence`
   - Input: constraint_type="time", constraint_value=""
   - Assert: confidence="low", clarify_type="CONSTRAINT"

6. `test_vague_constraint_value_returns_medium_confidence`
   - Input: constraint_type="time", constraint_value="soon"
   - Assert: confidence="medium", clarify_type="CONSTRAINT"

7. `test_empty_definition_of_finished_returns_low_confidence`
   - Input: valid constraint, definition_of_finished=""
   - Assert: confidence="low", clarify_type="FINISHED"

8. `test_vague_definition_of_finished_returns_medium_confidence`
   - Input: valid constraint, definition_of_finished="when it's done"
   - Assert: confidence="medium", clarify_type="FINISHED"

9. `test_initiative_framing_merges_intent_and_constraints`
   - Assert: initiative_framing contains all fields from confirmed_intent plus constraint fields

**Handler Tests:**

10. `test_valid_input_returns_confirm_framing_complete`
    - Assert: assistant_guidance.action = "CONFIRM_FRAMING_COMPLETE"

11. `test_force_constraint_returns_force_constraint_action`
    - Input: user_claims_no_constraints=True
    - Assert: assistant_guidance.action = "FORCE_CONSTRAINT"

12. `test_missing_confirmed_intent_returns_error`
    - Input: {} (no confirmed_intent)
    - Assert: isError=True with instruction to call Tool 1

---

## Integration Tests

### `test_step1_flow.py`

1. `test_tool1_listed_in_registry`
   - Assert: "frame_initiative_intent" in tool list

2. `test_tool2_listed_in_registry`
   - Assert: "frame_initiative_constraints" in tool list

3. `test_tool1_has_correct_annotations`
   - Assert: readOnlyHint=False, destructiveHint=False, openWorldHint=False

4. `test_tool2_has_correct_annotations`
   - Assert: same as Tool 1

5. `test_tool2_input_schema_requires_confirmed_intent`
   - Assert: "confirmed_intent" in required fields

---

## Success Criteria

1. ✅ Both tools registered and discoverable via tools/list
2. ✅ Tool 1 validates WHO and WHAT, ignores WHY for confidence
3. ✅ Tool 1 returns appropriate confidence and clarify type
4. ✅ Tool 2 requires confirmed_intent, rejects calls without it
5. ✅ Tool 2 rejects "no constraints" and triggers forcing logic
6. ✅ Tool 2 validates constraint_value and definition_of_finished
7. ✅ Tool 2 returns complete initiative_framing with merged data
8. ✅ assistant_guidance contains correct action and instruction for each state
9. ✅ All unit tests pass
10. ✅ All integration tests pass

---

## Out of Scope (This Increment)

- Step 2 tools (deliverable identification)
- Widget/visual output for framing
- Persistence of framing data
- Export of framing summary
- Refinement of export_checklist

---

## OpenAI Compliance Checklist

| Requirement | Tool 1 | Tool 2 |
|-------------|--------|--------|
| Description is factual, single purpose | ✅ | ✅ |
| inputSchema complete with descriptions | ✅ | ✅ |
| Annotations present (readOnlyHint, etc.) | ✅ | ✅ |
| securitySchemes: [noauth] | ✅ | ✅ |
| structuredContent follows schema | ✅ | ✅ |
| assistant_guidance provides LLM instructions | ✅ | ✅ |
| No behavioral instructions in description | ✅ | ✅ |

---

## Notes for Claude Code

1. **Follow existing patterns.** Look at `export_checklist.py` for structure. Copy that pattern.

2. **Pure logic in `tool_logic.py`.** Validation functions return plain dicts. No MCP types in logic layer.

3. **Handler builds guidance.** The handler maps logic output to assistant_guidance strings. Logic layer only returns action type, handler provides full instruction text.

4. **Tool 2 depends on Tool 1.** This is enforced by requiring `confirmed_intent` in input schema and validating it in logic.

5. **Self-registration.** Both tools self-register at import time. Add imports to `tools/__init__.py`.

6. **Vague word matching.** Use case-insensitive substring matching for vague word detection.

7. **Error messages.** When returning isError=True, provide human-readable message in content and structured details in structuredContent.

8. **Test isolation.** Unit tests for logic functions should not import handler. Handler tests can mock logic if needed.

9. **FACILITATOR ROLE IS NON-NEGOTIABLE.** Every assistant_guidance instruction must reinforce: ask questions, never suggest, never advise, use user's exact words. If any guidance tells the LLM to suggest, recommend, or offer examples — it's wrong. Review every instruction string for this.

---

**Document Status:** Ready for Claude Code execution
