# Claude Code Briefing: `inspect_adapt` MCP Tool — v3

## Increment Context

This is a **rewrite** of the existing `inspect_adapt` tool. The current implementation has two phases (start/commit) and a `weekly_context_summary` field. Both are unnecessary. This version simplifies to a **single-call tool** where the entire reflection conversation is LLM-facilitated and the tool call is purely the commit gate.

**What changes from current implementation:**
- Remove `phase` enum entirely
- Remove `weekly_context_summary` field
- Remove `_handle_start` function and all start-phase logic
- Remove `GUIDANCE_START` from structuredContent (move to DESCRIPTION)
- Single handler path: validate provenance → return success or error
- Pydantic models `ReflectionItem` and `ActionStep` are unused — remove them

**What stays the same:**
- Provenance enforcement pattern (verbatim fields, ID linkage)
- Three-tier validation (provenance → soft block → defensive)
- `_build_provenance_error` and `_build_soft_block` helpers
- All provenance guidance constants
- Registration, auth, ToolDefinition

---

## Architecture

- **File:** `mcp_server/priority_guardian/tools/inspect_adapt.py`
- **Pattern:** Same as all PG tools — `ToolDefinition` constant, explicit registry, standard handler signature
- **Auth:** `required_scopes = ["pg.access"]`
- **Single-call tool** — LLM facilitates the full conversation, then calls once to commit

### Validation Model (same as create_priority)

Three-layer validation:
1. **JSON Schema:** Structural gate (required fields, enums, array bounds)
2. **MCP handler (provenance):** Behavioral gate — verbatim fields must be non-empty. Forces the LLM to gather user input before calling.
3. **Guidance:** Shapes tone and conversational behavior after structural gates pass.

---

## Conversation Flow (LLM-facilitated, not tool-controlled)

The DESCRIPTION tells the LLM how to facilitate. The tool call happens only at step 7.

```
1. LLM picks ONE opening question based on context:
   - If progress visible: "What specifically helped you make progress?"
   - If priorities got less time: "What got in the way?"
   - If mixed: default to obstacle lens
   
2. User reflects → identifies what helped or hindered

3. LLM helps user get specific (if vague, ask follow-up)
   → confirms up to 3 specific behaviors/rituals/decisions

4. LLM asks: "Anything you want to keep as a habit or do differently next week?"

5. User names action steps (up to 3)

6. LLM quality-checks:
   - Small? Incremental? Max 3?
   - Only rephrases user's behaviors — no new proposals
   - Pushes back if steps are too big or too many
   → User confirms / adjusts

7. LLM calls inspect_adapt ONCE with all provenance data
```

---

## Tool Metadata

### NAME
`inspect_adapt`

### DESCRIPTION

```
Record confirmed action steps from an inspect & adapt reflection.
Call this tool ONCE after facilitating the full reflection conversation.

CALL PRECONDITIONS — DO NOT CALL unless ALL are true:
- User has identified 1-3 specific behaviors/rituals/decisions (helped or hindered)
- User has named 1-3 concrete action steps for next week
- All verbatim fields contain the user's exact words
- User has explicitly confirmed the action steps

INSPECT & ADAPT FACILITATION — BINDING RULES:
When the user wants to reflect on their week, your default behavior is SUSPENDED.
You are a facilitator, not an advisor.

FORBIDDEN:
- Proposing new actions the user didn't imply
- Batching multiple questions
- Inferring what the user 'probably means'

REQUIRED FLOW:
1. Ask ONE opening question based on conversation context:
   - If user made progress: 'What specifically helped — a routine, a decision, a boundary you held?'
   - If priorities got less time: 'What was the biggest thing that got in the way — what actually happened?'
   - If mixed context: default to the obstacle lens — it yields more concrete adjustments.
   Ask. Stop. Wait.

2. Help user get specific. If vague ('I just focused more'), follow up:
   'What did that look like — what did you do differently?'
   If already specific, reflect back and confirm.
   Gather up to 3 confirmed behaviors/rituals/decisions.

3. Ask: 'Anything you want to keep as a habit next week, or do differently?'
   Wait for user's answer.

4. User names action steps (up to 3). Quality-check each:
   - Small — doable in one week without heroic effort
   - Close to existing habits — adjustments, not overhauls
   - Concrete — 'block 90 min for P1 Tuesday and Thursday mornings' not 'focus more on P1'
   Only rephrase user's described behaviors into commitments.
   Do NOT propose new actions the user didn't imply.
   Push back if steps are too big, too vague, or more than 3.

5. Confirm action steps with user. Then call this tool with all data.

After this tool returns successfully, briefly mention the user can schedule
these as calendar events if they want to lock in the time.
```

### INPUT_SCHEMA

```json
{
  "type": "object",
  "properties": {
    "reflection_items": {
      "type": "array",
      "description": "1-3 specific behaviors, rituals, or decisions the user named during reflection.",
      "items": {
        "type": "object",
        "properties": {
          "id": {
            "type": "string",
            "description": "Stable identifier for this reflection item. Use 'r1', 'r2', 'r3'. Referenced by action_steps.derived_from_id."
          },
          "user_reflection_verbatim": {
            "type": "string",
            "description": "Copy-paste the user's exact words describing this behavior, ritual, or decision. Must be non-empty. Do NOT paraphrase or infer — use the user's actual statement.",
            "minLength": 1
          },
          "description": {
            "type": "string",
            "description": "Derived from user_reflection_verbatim — normalized for clarity. Do not invent specificity the user did not state."
          },
          "lens": {
            "type": "string",
            "enum": ["helped", "hindered"],
            "description": "Whether this item helped progress or hindered it. Derived from the user's framing."
          }
        },
        "required": ["id", "user_reflection_verbatim", "description", "lens"]
      },
      "minItems": 1,
      "maxItems": 3
    },
    "action_steps": {
      "type": "array",
      "description": "1-3 small, concrete action steps for next week. Each must link to a reflection item by id.",
      "items": {
        "type": "object",
        "properties": {
          "user_action_verbatim": {
            "type": "string",
            "description": "Copy-paste the user's exact words for what they will do next week. Must be non-empty. Do NOT propose new actions the user didn't imply — only rephrase the user's described behaviors into next-week commitments.",
            "minLength": 1
          },
          "action": {
            "type": "string",
            "description": "Derived from user_action_verbatim — normalized for clarity. Must be concrete enough to do in one week. Close to user's existing habits — adjustment, not overhaul."
          },
          "derived_from_id": {
            "type": "string",
            "description": "The 'id' of the reflection item this action connects to. Must exactly match an id from reflection_items (e.g., 'r1')."
          }
        },
        "required": ["user_action_verbatim", "action", "derived_from_id"]
      },
      "minItems": 1,
      "maxItems": 3
    },
    "user_confirmed": {
      "type": "boolean",
      "description": "Must be true — indicates the user explicitly confirmed these action steps. Do NOT set to true unless the user has seen and agreed to the specific actions."
    }
  },
  "required": ["reflection_items", "action_steps", "user_confirmed"],
  "additionalProperties": false
}
```

Note: all three top-level fields are now `required`. The LLM cannot call this tool without all data.

---

## Provenance Guidance Messages

Same pattern as create_priority: each provenance failure returns `isError: true` with corrective `assistant_guidance`.

```python
GUIDANCE_EMPTY_REFLECTION_VERBATIM = (
    "user_reflection_verbatim is empty for one or more reflection items. "
    "Do not call this tool until the user has stated what helped or hindered their progress. "
    "Ask ONE question and wait for their answer. Store their exact words in user_reflection_verbatim."
)

GUIDANCE_EMPTY_REFLECTION_DESCRIPTION = (
    "description is empty for one or more reflection items. "
    "Derive from user_reflection_verbatim — normalize for clarity but do not invent specificity."
)

GUIDANCE_EMPTY_ACTION_VERBATIM = (
    "user_action_verbatim is empty for one or more action steps. "
    "Do not call this tool until the user has stated what they will do next week. "
    "Only rephrase the user's described behaviors into next-week commitments. "
    "Do NOT propose new actions the user didn't imply. "
    "Store their exact words in user_action_verbatim."
)

GUIDANCE_EMPTY_ACTION = (
    "action is empty for one or more action steps. "
    "Derive from user_action_verbatim — normalize for clarity but do not invent specificity."
)

GUIDANCE_INVALID_DERIVED_FROM_ID = (
    "derived_from_id does not match any reflection item id. "
    "Each action step must reference a valid reflection item id (e.g., 'r1', 'r2', 'r3')."
)

GUIDANCE_USER_NOT_CONFIRMED = (
    "user_confirmed must be true. "
    "Present the action steps to the user and ask for explicit confirmation before calling again."
)
```

---

## Guidance Constants

### GUIDANCE_COMMIT_SUCCESS

```python
GUIDANCE_COMMIT_SUCCESS = (
    "The user's action steps have been confirmed. "
    "Present a brief, clean summary of what they committed to. "
    "Mention they can add these to their calendar if they want to lock in the time. "
    "Do NOT add more advice. Do NOT expand on the steps. Keep it to 2-3 sentences max."
)
```

### GUIDANCE_COMMIT_VALIDATION_ERROR

```python
GUIDANCE_COMMIT_VALIDATION_ERROR = (
    "The commit could not be recorded. Tell the user what was missing and ask them to confirm again."
)
```

---

## Handler Logic

### Helper: `_build_provenance_error`

Same pattern as `create_priority._build_provenance_error`.

### Helper: `_build_soft_block`

Same as current implementation.

### Single handler path

```
handle(user_id, correlation_id, arguments):

  1. Provenance validation (behavioral gate) → _build_provenance_error (isError: true)
     - reflection_items missing or empty → GUIDANCE_EMPTY_REFLECTION_VERBATIM
     - reflection_items > 3 → ToolUsageError (defensive)
     - For each reflection item:
       - id missing/empty → ToolUsageError (defensive)
       - id already seen (duplicate) → ToolUsageError (defensive)
       - user_reflection_verbatim empty/whitespace → GUIDANCE_EMPTY_REFLECTION_VERBATIM
       - description empty/whitespace → GUIDANCE_EMPTY_REFLECTION_DESCRIPTION
       - lens not in ["helped", "hindered"] → ToolUsageError (defensive)
     - action_steps missing or empty → GUIDANCE_EMPTY_ACTION_VERBATIM
     - action_steps > 3 → ToolUsageError (defensive)
     - For each action step:
       - user_action_verbatim empty/whitespace → GUIDANCE_EMPTY_ACTION_VERBATIM
       - action empty/whitespace → GUIDANCE_EMPTY_ACTION
       - derived_from_id not in collected reflection ids → GUIDANCE_INVALID_DERIVED_FROM_ID

  2. Conversational guardrail (soft block) → isError: false
     - user_confirmed false or missing → _build_soft_block(GUIDANCE_USER_NOT_CONFIRMED)

  3. Success
     - Return CallToolResult:
       content: "Inspect & adapt complete. {n} action step(s) confirmed."
       structuredContent:
         success: true
         completed: true
         reflection_items: <from input>
         action_steps: <from input>
         assistant_guidance: GUIDANCE_COMMIT_SUCCESS
```

---

## What to Remove from Current Implementation

- `phase` property from INPUT_SCHEMA
- `weekly_context_summary` property from INPUT_SCHEMA
- `_handle_start` function
- `_handle_commit` function (merge logic into single `handle`)
- `GUIDANCE_START` constant (conversation flow now lives in DESCRIPTION)
- `ReflectionItem` Pydantic model (unused)
- `ActionStep` Pydantic model (unused)
- Phase routing in `handle` (`if phase == "start"` / `elif phase == "commit"`)
- All start-phase related tests

---

## Registration

No changes needed — tool is already registered. Update invocation messages:

```python
"inspect_adapt": (
    "Recording your action steps...",
    "Action steps confirmed.",
),
```

### ToolDefinition (no changes):

```python
INSPECT_ADAPT = ToolDefinition(
    name=NAME,
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=None,
    handle=handle,
    read_only_hint=True,
    destructive_hint=False,
    open_world_hint=False,
    widget_accessible=False,
)
```

---

## Validation Rules (handler must enforce)

### Provenance failures → `_build_provenance_error` (isError: true)

| Rule | Error code | Guidance constant |
|------|-----------|-------------------|
| `reflection_items` missing or empty | `empty_reflection_verbatim` | GUIDANCE_EMPTY_REFLECTION_VERBATIM |
| Any `user_reflection_verbatim` empty/whitespace | `empty_reflection_verbatim` | GUIDANCE_EMPTY_REFLECTION_VERBATIM |
| Any `description` empty/whitespace | `empty_reflection_description` | GUIDANCE_EMPTY_REFLECTION_DESCRIPTION |
| `action_steps` missing or empty | `empty_action_verbatim` | GUIDANCE_EMPTY_ACTION_VERBATIM |
| Any `user_action_verbatim` empty/whitespace | `empty_action_verbatim` | GUIDANCE_EMPTY_ACTION_VERBATIM |
| Any `action` empty/whitespace | `empty_action` | GUIDANCE_EMPTY_ACTION |
| Any `derived_from_id` doesn't match a reflection item `id` | `invalid_derived_from_id` | GUIDANCE_INVALID_DERIVED_FROM_ID |

### Conversational guardrails → `isError: false`

| Rule | Guidance constant |
|------|-------------------|
| `user_confirmed` false or missing | GUIDANCE_USER_NOT_CONFIRMED |

### Defensive guards → `ToolUsageError`

| Rule | Message |
|------|---------|
| `reflection_items` > 3 items | "reflection_items must contain 1-3 items." |
| `action_steps` > 3 items | "action_steps must contain 1-3 items." |
| `lens` not in ["helped", "hindered"] | "lens must be 'helped' or 'hindered'." |
| `id` missing or empty on reflection item | "Each reflection item must have an 'id'." |
| Duplicate `id` across reflection items | "Duplicate reflection item id: '{id}'." |

---

## What NOT to Build

- No backend endpoint
- No database table
- No widget
- No Pydantic models (manual dict validation is better here — each field check maps to a specific provenance error with targeted guidance)
- No persistence of action steps
- No phases

---

## Unit Tests

File: `tests/unit/mcp_pg/test_inspect_adapt.py`

**Rewrite all tests** — remove phase start tests, update all commit tests to use new schema without `phase` field.

### Success tests:
1. `test_commit_success` — valid call with all fields returns success with GUIDANCE_COMMIT_SUCCESS and `completed: true`
2. `test_commit_multiple_items` — multiple reflection items and action steps succeed
3. `test_commit_valid_derived_from_id_linkage` — derived_from_id correctly matches reflection item ids

### Provenance validation tests (isError: true):
4. `test_missing_reflection_items` — returns provenance error
5. `test_empty_reflection_items` — empty array returns provenance error
6. `test_reflection_verbatim_empty` — empty user_reflection_verbatim returns provenance error
7. `test_reflection_description_empty` — empty description returns provenance error
8. `test_missing_action_steps` — returns provenance error
9. `test_empty_action_steps` — empty array returns provenance error
10. `test_action_verbatim_empty` — empty user_action_verbatim returns provenance error
11. `test_action_empty` — empty action returns provenance error
12. `test_invalid_derived_from_id` — derived_from_id doesn't match any reflection item id
13. `test_whitespace_only_reflection_verbatim` — whitespace-only returns provenance error
14. `test_whitespace_only_action_verbatim` — whitespace-only returns provenance error

### Conversational guardrail tests (isError: false):
15. `test_user_not_confirmed` — user_confirmed=false returns soft block, isError=false
16. `test_user_confirmed_missing` — user_confirmed not provided returns soft block, isError=false

### Defensive guard tests (ToolUsageError):
17. `test_too_many_reflection_items` — 4+ items raises ToolUsageError
18. `test_too_many_action_steps` — 4+ items raises ToolUsageError
19. `test_reflection_item_invalid_lens` — raises ToolUsageError
20. `test_reflection_item_missing_id` — raises ToolUsageError
21. `test_reflection_item_empty_id` — raises ToolUsageError
22. `test_reflection_item_duplicate_id` — two items with same id raises ToolUsageError

### Integration tests (separate file):

File: `tests/integration/mcp_pg/test_inspect_adapt_integration.py`

23. `test_tool_registered` — INSPECT_ADAPT appears in TOOL_REGISTRY
24. `test_tool_listed` — inspect_adapt appears in list_tools() output with correct metadata
25. `test_full_flow` — call with valid data including proper id linkage, succeeds
