# Briefing: Redesign `create_priority` MCP Tool — Conversational Onboarding with Structural Enforcement

## Context

The current `create_priority` tool has `required: ["name", "type"]` with optional conditional fields. In production, the LLM asks for all 3 priorities and all fields upfront — overwhelming the user. The tool description tries to enforce conversational flow via long text instructions, but the LLM ignores them because the schema permits calling with minimal data.

**Core principle from Sharpen:** Structure beats instruction. The input schema IS the quality gate for structural enforcement. If the schema allows premature calls, the LLM will make premature calls regardless of what the description says.

## Goal

Redesign `create_priority` so that:

1. The LLM gathers ONE priority at a time through conversation before calling
2. The tool renders the dashboard widget after each priority creation
3. The tool's `assistant_guidance` drives the iterative flow (gather P2 after P1, etc.)
4. Structural enforcement via verbatim fields prevents the LLM from skipping conversational steps

## What Changes

### MCP tool only — no backend changes

The backend `POST /api/priority-guardian/priorities` endpoint and `CreatePriorityRequest` model are unchanged. The backend already validates all conditional fields correctly. This increment only changes `mcp_server/priority_guardian/tools/create_priority.py`.

### Changes summary

1. **Input schema** — add verbatim provenance fields, keep all existing fields
2. **Tool description** — rewrite for Sharpen-style preconditions (shorter, structured)
3. **Handler** — add provenance validation before backend call, add widget rendering after success, restructure `assistant_guidance` into structured format
4. **Widget rendering** — add `WIDGET_URI`, fetch fresh priorities after creation, return `structuredContent` with `openai/outputTemplate`
5. **Tool definition** — update `widget_uri`
6. **Registry** — update invocation messages

## Design Decisions

### Three-layer validation model

This tool uses three distinct validation layers. Each has a different purpose:

| Layer | Purpose | What it enforces |
|-------|---------|-----------------|
| **JSON Schema** | Structural gate — prevents calls without required fields | `user_priority_name_verbatim`, `user_type_choice_verbatim`, `name`, `type` are always required |
| **MCP handler (provenance)** | Behavioral gate — ensures conversational flow happened | Verbatim fields non-empty after strip. For flexible: `user_goal_verbatim` AND `initial_goal_text` non-empty |
| **Backend (domain)** | Domain gate — enforces business rules | Conditional field requirements (deadline date for deadline type, hours/checkpoint/goal for flexible type), future date validation, max 3 priorities |

**Critical dependency:** Conditional field enforcement (e.g., "deadline is required when type=deadline") relies on backend validation via `CreatePriorityRequest` Pydantic model. The MCP schema does NOT use JSON Schema `if/then` for conditional requirements because LLM support for these constructs is unreliable. If backend validation is ever relaxed, the MCP layer will not catch the gap. Do not remove backend conditional validation without adding equivalent MCP-layer checks.

### Verbatim fields as quality gates (not booleans)

The LLM fabricates boolean confirmation fields (`user_confirmed_type: true`) without actually having asked the user. Verbatim fields cannot be faked — the LLM must copy-paste from the user's actual chat message.

Caveat: verbatim provenance is behavioral discouragement, not cryptographic proof. The LLM can still fabricate plausible text. The enforcement here is that non-empty verbatim is a stronger signal than a boolean — it's harder to produce coherent fake verbatim than to flip `true`. This is the same trade-off Sharpen makes.

Required verbatim fields:
- `user_priority_name_verbatim` — user's exact words for what they want to track
- `user_type_choice_verbatim` — user's exact words when choosing deadline vs flexible (e.g., "it has a hard deadline" or "it's more of an ongoing thing, like 5 hours a week")

For flexible priorities only:
- `user_goal_verbatim` — user's exact words for the 1-month goal (e.g., "I want to have 3 client meetings booked by then")

These fields are validated server-side as non-empty strings. The `name` field is the LLM's cleaned-up version (normalized for clarity), derived from `user_priority_name_verbatim` — same pattern as Sharpen's `who` derived from `user_who_verbatim`.

### Widget rendering on create_priority

Currently only `get_priorities` has `WIDGET_URI`. After this change, `create_priority` also produces a widget. The handler fetches the fresh priority list after successful creation (same pattern as `add_priority` widget tool) and returns it with `openai/outputTemplate`.

This eliminates the need for the LLM to chain `create_priority` → `get_priorities`. One call = persist + render.

The widget mounts, calls `get_priorities` on mount anyway (per widget spec), so even if the inline data is slightly stale, it self-corrects.

**`widget_accessible` stays False.** The tool needs `widget_uri` to render a widget, but does NOT need `widget_accessible=True`. These are separate concerns:
- `widget_uri` → tool renders a widget when called
- `widget_accessible` → widget can call this tool via `callTool`

Making `create_priority` widget-accessible would be a footgun: the widget form cannot populate provenance verbatim fields, so widget calls would always fail MCP provenance validation. Post-onboarding widget-based creation uses the existing `add_priority` private tool which has no provenance requirements.

### Structured assistant_guidance

Replace free-text guidance strings with structured objects. The `assistant_guidance` key in `structuredContent` becomes:

```json
{
  "action": "PRIORITY_CREATED",
  "remaining_slots": 2,
  "instruction": "..."
}
```

**Action naming convention:** Action names are long-term contracts — they become part of the tool's behavioral API. Use neutral, state-describing names (`PRIORITY_CREATED`) rather than flow-assuming names (`GATHER_NEXT_PRIORITY`). The `instruction` field carries the contextual guidance about what to do next. This keeps the action enum stable even if the surrounding flow changes.

Possible actions after successful creation:
- `PRIORITY_CREATED` — always returned on success. `remaining_slots` indicates how many more can be added (0, 1, or 2).

Possible actions on provenance failure:
- `ASK_CLARIFYING` — returned when a provenance check fails. `instruction` tells the LLM exactly what question to ask.

### Path A (conversational) vs Path B (widget)

After creating P1, the guidance offers the user two paths for remaining priorities:
- **Path A**: Continue conversationally (LLM gathers info → calls `create_priority` again)
- **Path B**: Add via widget form (user uses the dashboard's "Add priority" button, then writes "done" in chat when finished)

The guidance explicitly instructs the LLM to present both options. If user chooses Path B and later writes "done," the LLM already knows `active_priority_count` from the last `create_priority` response — no need to call `get_priorities`.

## Architectural Edge Cases — Conscious Decisions

### Edge case 1: Type ↔ verbatim semantic mismatch

The LLM could set `type: "deadline"` while `user_type_choice_verbatim` contains "it's an ongoing thing." MCP provenance validates non-empty, not semantic consistency. Backend enforces the structural consequence (missing deadline field → 422).

**Decision: Accept.** The verbatim exists to prove the user was asked, not to validate the LLM's interpretation. Adding NLP matching in the MCP layer would be over-engineering. If the LLM misinterprets, the backend catches the structural consequence.

### Edge case 2: LLM early-call with missing conditional fields

Even with provenance enforcement, the LLM could gather name + type + verbatim, then call immediately without the deadline date or hours/week. MCP provenance passes (verbatim fields present). Backend rejects (missing conditional field → 422).

**Decision: Accept.** This is an occasional wasted HTTP call. The backend returns a clean validation error, the MCP handler returns it as structured guidance. Adding MCP-level conditional validation (e.g., "if type==deadline and not deadline, reject") would duplicate backend logic and create a maintenance burden. The three-layer model intentionally delegates this to the backend.

### Edge case 3: `active_priority_count` missing from response

The handler's guidance branching depends on `active_priority_count` from the backend response. If the response shape changes or the field is missing, the handler must not crash or produce broken guidance.

**Decision: Guard with defensive null check.** See handler changes below — if `active_priority_count` is None, log error and default to safe generic guidance.

### Edge case 4: Action enum as long-term contract

Action names in `assistant_guidance` become part of the tool's behavioral API. Renaming them later breaks any LLM behavior that was calibrated to the current names.

**Decision: Use neutral, state-describing names.** `PRIORITY_CREATED` instead of `GATHER_NEXT_PRIORITY`. The instruction field carries flow-specific context. Action names describe what happened, not what should happen next.

## Input Schema (New)

```python
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "user_priority_name_verbatim": {
            "type": "string",
            "description": "Copy-paste user's exact words for their priority. Must be non-empty.",
            "minLength": 1,
        },
        "name": {
            "type": "string",
            "description": "Priority name derived from verbatim — normalized for clarity (max 100 chars). Do not invent specificity the user did not state.",
            "maxLength": 100,
        },
        "user_type_choice_verbatim": {
            "type": "string",
            "description": "Copy-paste user's exact words when choosing deadline vs flexible. Must be non-empty.",
            "minLength": 1,
        },
        "type": {
            "type": "string",
            "enum": ["deadline", "flexible"],
            "description": "Priority type derived from user's verbatim choice.",
        },
        "calendar_keyword": {
            "type": "string",
            "enum": ["P1", "P2", "P3"],
            "description": "Preferred keyword (optional). Omit to auto-assign next available.",
        },
        "deadline": {
            "type": "string",
            "description": "ISO date (YYYY-MM-DD). Required when type=deadline.",
        },
        "weekly_hour_target": {
            "type": "number",
            "description": "Hours per week commitment. Required when type=flexible.",
            "exclusiveMinimum": 0,
        },
        "checkpoint_date": {
            "type": "string",
            "description": "ISO date (YYYY-MM-DD) ~1 month out. Required when type=flexible.",
        },
        "user_goal_verbatim": {
            "type": "string",
            "description": "Copy-paste user's exact words for 1-month goal. Required when type=flexible. Must be non-empty.",
            "minLength": 1,
        },
        "initial_goal_text": {
            "type": "string",
            "description": "Goal text derived from user_goal_verbatim — normalized for clarity (max 200 chars). Required when type=flexible.",
            "maxLength": 200,
        },
    },
    "required": [
        "user_priority_name_verbatim",
        "name",
        "user_type_choice_verbatim",
        "type",
    ],
    "additionalProperties": False,
}
```

**Note on `additionalProperties: false`:** This follows the Sharpen pattern. The LLM cannot inject extra fields the schema doesn't define.

## Tool Description (New)

The description must be concise. No long ONBOARDING CONTEXT paragraphs. The schema enforces what the description cannot.

```python
DESCRIPTION = """Creates ONE priority for time tracking. Call once per priority — user sets up 1–3 priorities iteratively.

CALL PRECONDITIONS — DO NOT CALL unless ALL are true:
- user_priority_name_verbatim: non-empty, user's exact words
- name: derived from verbatim, normalized for clarity
- user_type_choice_verbatim: non-empty, user's exact words choosing deadline or flexible
- type: derived from user's choice
- For deadline: deadline date gathered from user
- For flexible: weekly_hour_target, checkpoint_date, user_goal_verbatim, AND initial_goal_text all gathered from user

ONBOARDING FLOW: For each priority, gather information conversationally ONE question at a time:
1. Ask what priority the user wants to track → store verbatim
2. Explain deadline vs flexible concept → ask which applies → store verbatim
3. Ask for type-specific fields (deadline date OR hours/week + 1-month goal + check-in date)
4. Call this tool with ALL gathered data

After the tool returns, follow the assistant_guidance for next steps. Do NOT deviate from the guided flow."""
```

## Provenance Validation (Server-Side)

Before calling the backend, the handler validates provenance fields. This is the behavioral enforcement layer — if the LLM calls with empty verbatim fields, the tool rejects with explicit guidance.

Validation checks (in order):
1. `user_priority_name_verbatim` is non-empty after strip
2. `name` is non-empty after strip
3. `user_type_choice_verbatim` is non-empty after strip
4. If `type == "flexible"`:
   - `user_goal_verbatim` is non-empty after strip
   - `initial_goal_text` is non-empty after strip

Each check returns `isError=True` with structured `assistant_guidance` telling the LLM exactly what to ask next. Same pattern as Sharpen's `GUIDANCE_EMPTY_PAIN_VERBATIM`.

**Important:** These validations happen in the MCP tool handler before the backend HTTP call. The backend never sees invalid requests from this tool. This keeps the backend clean and the behavioral enforcement in the MCP layer where it belongs.

## Assistant Guidance Messages

Define as module-level constants (Sharpen pattern):

```python
GUIDANCE_EMPTY_NAME_VERBATIM = (
    "user_priority_name_verbatim is empty. Do not call this tool until user has stated a priority. "
    "Ask: 'What is the #1 priority you want to lock in and track your time against?' "
    "Then store their exact answer in user_priority_name_verbatim."
)

GUIDANCE_EMPTY_NAME = (
    "name is empty. Derive from user_priority_name_verbatim — "
    "normalize for clarity but do not invent specificity."
)

GUIDANCE_EMPTY_TYPE_VERBATIM = (
    "user_type_choice_verbatim is empty. Do not call this tool until user has chosen deadline or flexible. "
    "Explain: Deadline priorities have a hard end date. Flexible priorities are ongoing commitments "
    "with a weekly hour target. "
    "Ask: 'Does this priority have a hard deadline, or is it more of an ongoing commitment?' "
    "Then store their exact answer in user_type_choice_verbatim."
)

GUIDANCE_EMPTY_GOAL_VERBATIM = (
    "user_goal_verbatim is empty. Do not call this tool until user has stated a 1-month goal. "
    "Explain: The 1-month goal anchors your time investment to a concrete outcome. "
    "Ask: 'What would success look like in one month? One sentence — specific enough "
    "that you will know whether it happened.' "
    "Then store their exact answer in user_goal_verbatim."
)

GUIDANCE_EMPTY_GOAL_TEXT = (
    "initial_goal_text is empty. Derive from user_goal_verbatim — "
    "normalize for clarity but do not invent specificity."
)
```

For successful creation, guidance uses neutral `PRIORITY_CREATED` action with `remaining_slots`:

```python
def _build_success_guidance(keyword, priority_name, active_count, available_keywords):
    """Build structured guidance after successful priority creation.

    Uses defensive null check on active_count — if backend response shape
    changes, falls back to safe generic guidance rather than crashing.
    """
    if active_count is None:
        # Defensive: backend response shape may have changed
        logger.error(
            "tool.create_priority.missing_active_count",
            correlation_id=correlation_id,
        )
        return {
            "action": "PRIORITY_CREATED",
            "instruction": (
                f"Priority created: {priority_name} is now tracked as {keyword}. "
                "The dashboard now shows the user's priorities. "
                "Do NOT repeat priority details — the widget displays them.\n\n"
                f"Remind user: tag calendar events with {keyword} to track time "
                f"(e.g., '{keyword}: Meeting name')."
            ),
        }

    remaining = 3 - active_count

    if remaining > 0:
        next_slot = available_keywords[0] if available_keywords else None
        return {
            "action": "PRIORITY_CREATED",
            "remaining_slots": remaining,
            "next_available_keyword": next_slot,
            "instruction": (
                f"Priority created: {priority_name} is now tracked as {keyword}. "
                "The dashboard now shows the user's priorities. "
                "Do NOT repeat priority details — the widget displays them.\n\n"
                f"Remind user: tag calendar events with {keyword} to track time "
                f"(e.g., '{keyword}: Meeting name').\n\n"
                "Offer two paths for remaining priorities:\n"
                "- Continue conversationally: 'What is your next priority?'\n"
                "- Use the dashboard: 'Or add priorities directly in the dashboard above. "
                "Just let me know when you are done.'\n\n"
                "If user continues conversationally, gather the next priority ONE question at a time. "
                "If user says 'done' or signals completion after using the widget, "
                "acknowledge and proceed to next onboarding step."
            ),
        }
    else:
        return {
            "action": "PRIORITY_CREATED",
            "remaining_slots": 0,
            "instruction": (
                f"Priority created: {priority_name} is now tracked as {keyword}. "
                "All 3 priority slots are filled. The dashboard shows the complete setup. "
                "Do NOT repeat priority details — the widget displays them.\n\n"
                "Remind user how calendar keyword tagging works for each priority. "
                "Tell user they can say 'show my priorities' anytime to see their dashboard, "
                "and that their data is saved across conversations."
            ),
        }
```

## Handler Changes

The handler's logic flow becomes:

1. **Extract arguments**
2. **Provenance validation** — check verbatim fields non-empty, check `initial_goal_text` non-empty for flexible, return structured error if any fail
3. **Build backend payload** — only the fields the backend expects (name, type, calendar_keyword, deadline, weekly_hour_target, checkpoint_date, initial_goal_text). Verbatim fields are NOT sent to backend — they are MCP-layer provenance only.
4. **Call backend** `POST /api/priority-guardian/priorities` — unchanged
5. **On success: extract `active_priority_count` and `available_keywords`** from backend response. Guard with defensive null check on `active_priority_count`.
6. **Fetch fresh priorities** — call `GET /api/priority-guardian/priorities` to get full priority list for widget rendering (same pattern as `add_priority` widget tool)
7. **Build `structuredContent`** with:
   - `success: True`
   - `data` block with `priorities`, `google_connected`, `available_keywords` (same shape as `get_priorities` response)
   - `_meta.openai/outputTemplate` pointing to widget URI
   - `assistant_guidance` structured object from `_build_success_guidance()`
8. **On error: return structured error** — same pattern as current implementation but with structured guidance

## Fresh Priority Fetch After Creation

After successful backend creation, the handler must fetch the full priority list to populate the widget. Use the same pattern as `add_priority` widget tool:

```python
from mcp_server.priority_guardian.http_client import backend_get
from mcp_server.priority_guardian.tools.get_priorities import _normalize_priority

fresh_response = await backend_get(
    "/api/priority-guardian/priorities",
    user_id,
    correlation_id
)

data = fresh_response.get("data", {})
raw_priorities = data.get("priorities", [])
google_connection = data.get("google_connection", {"connected": False})
available_keywords = data.get("available_keywords", [])

priorities = [_normalize_priority(p) for p in raw_priorities]
```

## Tool Definition Changes

```python
WIDGET_URI = "ui://widget/pg-dashboard.html"

CREATE_PRIORITY = ToolDefinition(
    name=NAME,
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=WIDGET_URI,
    handle=handle,
    read_only_hint=False,
    destructive_hint=False,
    open_world_hint=False,
    # widget_accessible intentionally NOT set (defaults False):
    # This tool requires verbatim provenance fields that widgets cannot provide.
    # Post-onboarding widget creation uses add_priority (private) which has no provenance gates.
)
```

## Registry Changes

In `mcp_server/priority_guardian/tools/__init__.py`:

Update `TOOL_INVOCATION_MESSAGES` for `create_priority`:

```python
"create_priority": (
    "Setting up your priority...",
    "Here's your Priority Guardian dashboard.",
),
```

The `list_tools()` function already handles `widget_uri` correctly — the `_meta` will automatically include `openai/outputTemplate` and `openai/resultCanProduceWidget` because `widget_uri` is now set. No `widget_accessible` needed for widget rendering.

## Files Modified

1. `mcp_server/priority_guardian/tools/create_priority.py` — full rewrite of schema, description, handler, tool definition
2. `mcp_server/priority_guardian/tools/__init__.py` — update invocation message text only

## Files NOT Modified

- Backend router, models, DB — no changes
- Widget HTML — no changes (widget already calls `get_priorities` on mount)
- `get_priorities.py` — no changes
- `handlers/tools.py` — no changes (dispatcher pattern unchanged)
- Widget tools (`add_priority.py` etc.) — no changes

## Unit Tests

**File:** `tests/unit/mcp_pg/test_create_priority_provenance.py` (new file)

Tests for provenance validation logic:

1. **test_empty_name_verbatim_returns_error** — call handler with `user_priority_name_verbatim: ""`. Assert `isError=True`, assert `structuredContent.error` is `"empty_name_verbatim"`, assert `structuredContent.assistant_guidance.action` is `"ASK_CLARIFYING"`.

2. **test_whitespace_only_name_verbatim_returns_error** — call handler with `user_priority_name_verbatim: "   "`. Assert same error as test 1.

3. **test_empty_type_verbatim_returns_error** — call handler with valid name verbatim but `user_type_choice_verbatim: ""`. Assert `error` is `"empty_type_verbatim"`.

4. **test_flexible_empty_goal_verbatim_returns_error** — call handler with valid name/type verbatim, `type: "flexible"`, but `user_goal_verbatim: ""`. Assert `error` is `"empty_goal_verbatim"`.

5. **test_flexible_empty_initial_goal_text_returns_error** — call handler with valid name/type verbatim, `type: "flexible"`, valid `user_goal_verbatim`, but `initial_goal_text: ""`. Assert `error` is `"empty_goal_text"`.

6. **test_flexible_whitespace_initial_goal_text_returns_error** — call handler with `initial_goal_text: "   "`. Assert same error as test 5.

7. **test_deadline_type_does_not_require_goal_verbatim** — call handler with valid name/type verbatim, `type: "deadline"`, `deadline: "2026-06-01"`, no `user_goal_verbatim`. Mock backend to return success. Assert no provenance error.

8. **test_valid_deadline_provenance_calls_backend** — provide all required verbatim fields for deadline type. Mock `backend_post` and `backend_get`. Assert `backend_post` called with correct payload (no verbatim fields in payload). Assert `backend_get` called to fetch fresh priorities.

9. **test_valid_flexible_provenance_calls_backend** — provide all required verbatim fields for flexible type including `initial_goal_text`. Mock `backend_post` and `backend_get`. Assert `backend_post` called with payload including `initial_goal_text`. Assert response includes widget URI in `_meta`.

10. **test_verbatim_fields_not_sent_to_backend** — provide all fields including verbatim. Mock `backend_post`. Assert the payload sent to backend does NOT contain `user_priority_name_verbatim`, `user_type_choice_verbatim`, or `user_goal_verbatim`.

11. **test_success_response_includes_widget_template** — mock successful creation + fresh fetch. Assert `structuredContent._meta["openai/outputTemplate"]` equals `"ui://widget/pg-dashboard.html"`.

12. **test_success_guidance_has_remaining_slots_when_under_3** — mock backend returning `active_priority_count: 1`. Assert `assistant_guidance.action` is `"PRIORITY_CREATED"`, assert `assistant_guidance.remaining_slots` is `2`.

13. **test_success_guidance_zero_remaining_when_3** — mock backend returning `active_priority_count: 3`. Assert `assistant_guidance.action` is `"PRIORITY_CREATED"`, assert `assistant_guidance.remaining_slots` is `0`.

14. **test_success_guidance_defensive_when_active_count_missing** — mock backend returning response without `active_priority_count` key. Assert `assistant_guidance.action` is `"PRIORITY_CREATED"`, assert no crash, assert `remaining_slots` key is absent.

15. **test_backend_error_max_priorities_returns_structured_error** — mock `backend_post` raising `HTTPStatusError` with 409 / `MAX_PRIORITIES_REACHED`. Assert `isError=True`, assert structured guidance tells user to retire/delete.

16. **test_backend_error_keyword_conflict_returns_retry_guidance** — mock `backend_post` raising `HTTPStatusError` with 409 / `KEYWORD_CONFLICT`. Assert guidance says retry.

**File:** `tests/unit/priority_guardian/test_tool_definitions.py` (add to existing)

17. **test_create_priority_has_widget_uri** — assert `CREATE_PRIORITY.widget_uri == "ui://widget/pg-dashboard.html"`.

18. **test_create_priority_not_widget_accessible** — assert `CREATE_PRIORITY.widget_accessible is not True` (default is falsy/not set).

19. **test_create_priority_schema_has_additional_properties_false** — assert `CREATE_PRIORITY.input_schema["additionalProperties"] is False`.

20. **test_create_priority_schema_requires_verbatim_fields** — assert `"user_priority_name_verbatim"` and `"user_type_choice_verbatim"` are in `required` list.

## Integration Tests

**File:** `tests/integration/priority_guardian/test_tool_roundtrip.py` (add to existing)

21. **test_create_priority_roundtrip_with_widget_data** — create a user, call `create_priority` handler with valid deadline arguments (including verbatim fields), assert response `structuredContent.data.priorities` contains the created priority with correct `calendarKeyword`, assert `_meta.openai/outputTemplate` is set.

22. **test_create_priority_roundtrip_flexible_with_goal** — create a user, call `create_priority` handler with valid flexible arguments (including `user_goal_verbatim` and `initial_goal_text`), assert response includes the priority with a goal in the `goals` array.

23. **test_create_priority_duplicate_name_creates_second_priority** — create a user, call `create_priority` twice with identical name but different verbatim. Assert both succeed, second priority gets next available keyword, `active_priority_count` is 2.

24. **test_create_priority_fourth_call_returns_max_reached** — create 3 priorities for a user, then attempt a fourth. Assert backend returns 409 `MAX_PRIORITIES_REACHED`. Assert structured error guidance in `assistant_guidance`.

## Acceptance Criteria

- [ ] `create_priority` input schema includes `user_priority_name_verbatim`, `user_type_choice_verbatim`, and `user_goal_verbatim` (flexible only) as provenance fields
- [ ] `additionalProperties: false` on schema
- [ ] Tool handler validates provenance fields before calling backend — returns structured error with `assistant_guidance` if empty
- [ ] For flexible type: handler validates both `user_goal_verbatim` AND `initial_goal_text` non-empty
- [ ] Verbatim fields are NOT forwarded to backend — they stay in the MCP layer
- [ ] Successful creation fetches fresh priority list and returns it with `openai/outputTemplate` for widget rendering
- [ ] `assistant_guidance` uses `action: "PRIORITY_CREATED"` (neutral, state-describing) with `remaining_slots` count
- [ ] Defensive null check on `active_priority_count` — falls back to safe guidance if missing
- [ ] Guidance after creation offers Path A (conversational) and Path B (widget) for remaining priorities
- [ ] Tool definition has `widget_uri` set, `widget_accessible` is NOT set (defaults False)
- [ ] Registry `list_tools()` produces correct `_meta` with `resultCanProduceWidget` (via `widget_uri` presence)
- [ ] Three-layer validation model is respected: schema → MCP provenance → backend domain
- [ ] All existing tests still pass
- [ ] New unit tests cover provenance validation, widget rendering, guidance branching, and defensive fallback
- [ ] New integration tests cover full roundtrip with widget data and duplicate/max-limit scenarios

## Pre-Deploy

Read OPERATIONS.md and check for additional pre-deploy tasks.