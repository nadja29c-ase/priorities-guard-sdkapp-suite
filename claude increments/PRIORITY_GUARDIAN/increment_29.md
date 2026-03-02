# Claude Code Briefing: `inspect_adapt` MCP Tool

## Increment Context

This is a new MCP tool for the Priority Guardian SDK app. It implements a lightweight inspect & adapt flow after the weekly report, helping users derive 1-3 small, concrete action steps for the next week.

**No backend endpoint needed.** No data to fetch, no persistence. It shapes the LLM's conversational behavior through schema constraints, provenance validation, and `assistant_guidance`.

**No widget.** The LLM narrates the entire flow conversationally.

---

## Architecture

- **File:** `mcp_server/priority_guardian/tools/inspect_adapt.py`
- **Pattern:** Same as all PG tools — `ToolDefinition` constant, explicit registry, standard handler signature
- **Auth:** `required_scopes = ["pg.access"]`
- **Two-call conversation flow** enforced by schema (call 1 = start, call 2 = commit)

### Validation Model (same as create_priority)

Three-layer validation:
1. **JSON Schema:** Structural gate (required fields, enums, array bounds)
2. **MCP handler (provenance):** Behavioral gate — verbatim fields must be non-empty. Forces the LLM to gather user input before calling.
3. **Guidance:** Shapes tone and conversational behavior after structural gates pass.

---

## Tool Metadata

### NAME
`inspect_adapt`

### DESCRIPTION

```
Facilitate a focused inspect & adapt after presenting the weekly report.
Helps the user identify what specifically helped or hindered progress,
then derive 1-3 small, concrete action steps for next week.

CALL PRECONDITIONS — DO NOT CALL unless ALL are true:
- Phase 'start': weekly_context_summary derived from the weekly report data already in conversation
- Phase 'commit': ALL verbatim fields gathered from user's own words during reflection conversation

Call this tool:
- After presenting the weekly report, when the user wants to reflect
- When the user says "yes" to the reflection nudge from the weekly report
- When the user asks "what should I do differently next week?"

Do NOT call this tool:
- Before the weekly report has been presented in this conversation
- During onboarding or priority setup
- When the user is asking about patterns or trends (use get_patterns instead)
- If you already completed an inspect & adapt in this conversation (phase='commit' succeeded)

INSPECT & ADAPT BINDING RULES: When facilitating inspect & adapt, your default behavior is SUSPENDED. You are a facilitator, not an advisor. Flow: Ask ONE question → wait for user's response → reflect/get specific → confirm → gather next item or move to action steps. NEVER ask for multiple reflections at once. NEVER call this tool with phase='commit' until ALL reflection items and action steps are gathered from the user's own words and confirmed.
```

### INPUT_SCHEMA

```json
{
  "type": "object",
  "properties": {
    "phase": {
      "type": "string",
      "enum": ["start", "commit"],
      "description": "Which phase of the inspect & adapt flow. 'start' = begin the reflection. 'commit' = record confirmed action steps."
    },
    "weekly_context_summary": {
      "type": "string",
      "description": "Phase 'start' only. Brief summary of weekly report context: which priorities had progress, which didn't, any notable patterns. 2-3 sentences max. Must come from the weekly report data already in conversation, not invented.",
      "minLength": 1
    },
    "reflection_items": {
      "type": "array",
      "description": "Phase 'commit' only. 1-3 specific behaviors, rituals, or decisions the user named during reflection.",
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
      "description": "Phase 'commit' only. 1-3 small, concrete action steps for next week. Each must link to a reflection item by id.",
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
      "description": "Phase 'commit' only. Must be true — indicates the user explicitly confirmed these action steps. Do NOT set to true unless the user has seen and agreed to the specific actions."
    }
  },
  "required": ["phase"],
  "additionalProperties": false
}
```

---

## Provenance Guidance Messages

Following the `create_priority` pattern: each provenance failure returns `isError: true` with corrective `assistant_guidance` that tells the LLM exactly what to gather from the user before retrying.

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

### GUIDANCE_START

```python
GUIDANCE_START = (
    "You are facilitating an inspect & adapt — not therapy, not coaching, not advice. "
    "Your job: ask ONE question, wait, help distill, confirm. "
    "\n\n"
    "BINDING RULES:\n"
    "- Ask ONE question at a time. Wait for the answer.\n"
    "- Do NOT propose new actions, solutions, or options the user didn't imply.\n"
    "- NEVER batch multiple questions.\n"
    "- NEVER infer what the user 'probably means.'\n"
    "\n"
    "DIRECTION: Based on the weekly context, pick ONE of these questions — never both:\n"
    "- If the user made visible progress on most priorities: "
    "'What specifically helped you make progress this week — a routine, a decision, a boundary you held?'\n"
    "- If most priorities got less time than intended: "
    "'What was the biggest thing that got in the way this week — what actually happened?'\n"
    "- If the weekly context is mixed (some progress, some behind): "
    "default to the obstacle lens — it yields more concrete adjustments.\n"
    "\n"
    "Pick the direction that fits the data. Ask the question. Stop. Wait for the user's response.\n"
    "\n"
    "After the user responds, your job is to help them get specific. "
    "If their answer is vague ('I just focused more'), ask a follow-up like "
    "'What did that actually look like — what did you do differently on Monday vs. the week before?' "
    "If their answer is already specific ('I blocked 2 hours every morning before checking email'), "
    "reflect it back and confirm: 'So the morning block before email was the key thing — is that right?'\n"
    "\n"
    "Once you have 1-3 specific, confirmed behaviors/rituals/decisions from the user, "
    "help them turn these into action steps for next week. "
    "Only rephrase the user's described behaviors into next-week commitments. "
    "Do NOT propose new actions the user didn't imply. "
    "The action steps MUST be:\n"
    "- Small — doable in one week without heroic effort\n"
    "- Close to existing habits — adjustments, not overhauls\n"
    "- Concrete — 'block 90 min for P1 on Tuesday and Thursday mornings' not 'focus more on P1'\n"
    "- Maximum 3 action steps. Fewer is better.\n"
    "\n"
    "Confirm the action steps with the user, then call inspect_adapt again with phase='commit'.\n"
    "\n"
    "At the end, briefly mention the user can schedule these as calendar events if they want to."
)
```

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

Same pattern as `create_priority._build_provenance_error`:

```python
def _build_provenance_error(error_code: str, instruction: str) -> mcp_types.CallToolResult:
    """Build a structured error response for provenance validation failure."""
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Provenance validation failed: {error_code}"
        )],
        structuredContent={
            "success": False,
            "error": error_code,
            "assistant_guidance": {
                "action": "ASK_CLARIFYING",
                "instruction": instruction,
            },
        },
        isError=True,
    )
```

### Phase: `start`

1. Validate `weekly_context_summary` is present and non-empty.
   - If missing or empty → `ToolUsageError("weekly_context_summary is required for phase 'start'.")`
   - This is a hard error — the LLM is misbehaving (calling start without data).
2. Return `CallToolResult` with:
   - `content`: `TextContent` with text "Starting inspect & adapt."
   - `structuredContent`:
     ```json
     {
       "success": true,
       "phase": "start",
       "weekly_context_summary": "<from input>",
       "assistant_guidance": "<GUIDANCE_START>"
     }
     ```
   - No `_meta.openai/outputTemplate` (no widget)

### Phase: `commit`

Two categories of validation:

**A. Provenance validation (behavioral gate) → `_build_provenance_error` (isError: true)**

These catch the LLM calling the tool without having gathered user input:

1. `reflection_items` missing or empty → provenance error with `GUIDANCE_EMPTY_REFLECTION_VERBATIM`
2. `reflection_items` has > 3 items → `ToolUsageError` (schema should prevent, defensive guard)
3. For each reflection item:
   - `user_reflection_verbatim` empty → provenance error with `GUIDANCE_EMPTY_REFLECTION_VERBATIM`
   - `description` empty → provenance error with `GUIDANCE_EMPTY_REFLECTION_DESCRIPTION`
   - `lens` not in ["helped", "hindered"] → `ToolUsageError` (schema should prevent)
   - `id` missing or empty → `ToolUsageError` (schema should prevent)
4. `action_steps` missing or empty → provenance error with `GUIDANCE_EMPTY_ACTION_VERBATIM`
5. `action_steps` has > 3 items → `ToolUsageError` (defensive guard)
6. For each action step:
   - `user_action_verbatim` empty → provenance error with `GUIDANCE_EMPTY_ACTION_VERBATIM`
   - `action` empty → provenance error with `GUIDANCE_EMPTY_ACTION`
   - `derived_from_id` does not match any reflection item `id` → provenance error with `GUIDANCE_INVALID_DERIVED_FROM_ID`

**B. Conversational guardrail (soft block) → `isError: false` with `structuredContent`**

These are conversational corrections, not tool misuse:

7. `user_confirmed` is false or missing → return `structuredContent` with `GUIDANCE_USER_NOT_CONFIRMED`, `isError: false`

**C. Success path**

If all validation passes, return `CallToolResult` with:
- `content`: `TextContent` with text "Inspect & adapt complete. {n} action step(s) confirmed."
- `structuredContent`:
  ```json
  {
    "success": true,
    "phase": "commit",
    "completed": true,
    "reflection_items": "<from input>",
    "action_steps": "<from input>",
    "assistant_guidance": "<GUIDANCE_COMMIT_SUCCESS>"
  }
  ```

Note: `"completed": true` gives the LLM an explicit signal not to call again.

---

## Registration

### In `tools/__init__.py`:

- Import `INSPECT_ADAPT` from `inspect_adapt.py`
- Add to `TOOL_REGISTRY`
- Add invocation messages to `TOOL_INVOCATION_MESSAGES`:
  ```python
  "inspect_adapt": (
      "Setting up inspect & adapt...",
      "Ready to reflect.",
  ),
  ```

### ToolDefinition:

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

### Phase: `start` — all failures → `ToolUsageError` (hard error)

| Rule | Error behavior | Message |
|------|---------------|---------|
| `weekly_context_summary` required and non-empty | ToolUsageError | "weekly_context_summary is required for phase 'start'." |

### Phase: `commit` — Provenance failures → `_build_provenance_error` (isError: true)

| Rule | Error code | Guidance constant |
|------|-----------|-------------------|
| `reflection_items` missing or empty | `empty_reflection_verbatim` | GUIDANCE_EMPTY_REFLECTION_VERBATIM |
| Any `user_reflection_verbatim` empty | `empty_reflection_verbatim` | GUIDANCE_EMPTY_REFLECTION_VERBATIM |
| Any `description` empty | `empty_reflection_description` | GUIDANCE_EMPTY_REFLECTION_DESCRIPTION |
| `action_steps` missing or empty | `empty_action_verbatim` | GUIDANCE_EMPTY_ACTION_VERBATIM |
| Any `user_action_verbatim` empty | `empty_action_verbatim` | GUIDANCE_EMPTY_ACTION_VERBATIM |
| Any `action` empty | `empty_action` | GUIDANCE_EMPTY_ACTION |
| Any `derived_from_id` doesn't match a reflection item `id` | `invalid_derived_from_id` | GUIDANCE_INVALID_DERIVED_FROM_ID |

### Phase: `commit` — Conversational guardrails → `isError: false`

| Rule | Guidance constant |
|------|-------------------|
| `user_confirmed` false or missing | GUIDANCE_USER_NOT_CONFIRMED |

### Phase: `commit` — Defensive guards → `ToolUsageError`

| Rule | Message |
|------|---------|
| `reflection_items` > 3 items | "reflection_items must contain 1-3 items." |
| `action_steps` > 3 items | "action_steps must contain 1-3 items." |
| `lens` not in ["helped", "hindered"] | "lens must be 'helped' or 'hindered'." |
| `id` missing or empty on reflection item | "Each reflection item must have an 'id'." |

---

## What NOT to Build

- No backend endpoint
- No database table
- No widget
- No persistence of action steps

### Internal Pydantic models

Use small internal Pydantic models for commit-phase validation (not exposed externally). The nested objects with ID linkage and conditional phase requirements justify typed validation over manual dict checks. Define models for `ReflectionItem`, `ActionStep`, and `CommitInput` within the tool module. Use them in the handler to parse and validate the commit arguments before provenance checks. This reduces boilerplate, centralizes validation, and makes tests cleaner.

---

## Unit Tests

File: `tests/unit/mcp_server/priority_guardian/tools/test_inspect_adapt.py`

### Phase start tests:
1. `test_start_returns_guidance` — valid start call returns success with GUIDANCE_START
2. `test_start_missing_context` — missing weekly_context_summary raises ToolUsageError
3. `test_start_empty_context` — empty string weekly_context_summary raises ToolUsageError

### Phase commit — provenance validation tests (isError: true):
4. `test_commit_success` — valid commit with all fields returns success with GUIDANCE_COMMIT_SUCCESS and `completed: true`
5. `test_commit_missing_reflection_items` — returns provenance error
6. `test_commit_empty_reflection_items` — empty array returns provenance error
7. `test_commit_reflection_verbatim_empty` — empty user_reflection_verbatim returns provenance error
8. `test_commit_reflection_description_empty` — empty description returns provenance error
9. `test_commit_reflection_item_invalid_lens` — lens not in ["helped", "hindered"] raises ToolUsageError
10. `test_commit_missing_action_steps` — returns provenance error
11. `test_commit_empty_action_steps` — empty array returns provenance error
12. `test_commit_action_verbatim_empty` — empty user_action_verbatim returns provenance error
13. `test_commit_action_empty` — empty action returns provenance error
14. `test_commit_invalid_derived_from_id` — derived_from_id doesn't match any reflection item id, returns provenance error
15. `test_commit_valid_derived_from_id_linkage` — derived_from_id correctly matches reflection item ids, succeeds

### Phase commit — conversational guardrail tests (isError: false):
16. `test_commit_user_not_confirmed` — user_confirmed=false returns soft block with GUIDANCE_USER_NOT_CONFIRMED, isError=false
17. `test_commit_user_confirmed_missing` — user_confirmed not provided returns soft block, isError=false

### Phase commit — defensive guard tests (ToolUsageError):
18. `test_commit_too_many_reflection_items` — 4+ items raises ToolUsageError
19. `test_commit_too_many_action_steps` — 4+ items raises ToolUsageError
20. `test_commit_whitespace_only_verbatim` — user_reflection_verbatim or user_action_verbatim containing only whitespace returns provenance error

### Integration tests (separate file):

File: `tests/integration/mcp_server/priority_guardian/tools/test_inspect_adapt_integration.py`

21. `test_tool_registered` — INSPECT_ADAPT appears in TOOL_REGISTRY
22. `test_tool_listed` — inspect_adapt appears in list_tools() output with correct metadata
23. `test_full_flow_start_then_commit` — call start, then call commit with valid data including proper id linkage, both succeed
