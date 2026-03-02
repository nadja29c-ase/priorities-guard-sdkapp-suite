# Claude Code Briefing: Onboarding Phase 2 Hardening

## Context

`onboarding_calendar_setup` is the Phase 2 onboarding tool for Priority Guardian. It has three phases called in sequence: `keyword_education` → `first_weekly_report` → `reflection_setup`. The tool is deployed and being tested in ChatGPT developer mode. Testing revealed multiple issues with widget rendering, LLM output quality, and guidance accuracy that need coordinated fixes.

## Files to Modify

- `mcp_server/priority_guardian/tools/onboarding_calendar_setup.py` — main tool file
- `mcp_server/priority_guardian/tools/__init__.py` — registry (invocation messages only)
- `tests/unit/mcp_pg/test_onboarding_calendar_setup.py` — unit tests

## Important: Do NOT Change

- Backend endpoints or services
- Other tool files (get_weekly_report, create_priority, etc.)
- Widget HTML files
- Any database models or migrations

---

## Change 1: Remove Widget Rendering from Tool Definition

### Problem
`ONBOARDING_CALENDAR_SETUP` ToolDefinition has `widget_uri=WIDGET_URI`. The registry's `list_tools()` uses this to advertise `openai/outputTemplate` and `resultCanProduceWidget` at the tool level. ChatGPT then renders the dashboard widget on EVERY phase call — including `keyword_education` and `reflection_setup` which are purely conversational.

### What to Do
- In the `ONBOARDING_CALENDAR_SETUP` ToolDefinition at the bottom of the file, set `widget_uri=None`
- Confirm `_meta` blocks with `openai/outputTemplate` are already removed from `_handle_keyword_education` and `_handle_reflection_setup` structuredContent (they should be based on prior edits — verify)
- ALSO remove the `_meta` block from `_handle_first_weekly_report` structuredContent. This phase should NOT attempt to render a widget itself. Instead, the LLM will call `get_weekly_report` (a separate tool that already has widget rendering) to show the pie chart.

### Why
When `widget_uri=None`, `list_tools()` won't advertise widget capability for this tool. Only `first_weekly_report`'s guidance will instruct the LLM to call `get_weekly_report` for the visual. This is structurally reliable — `get_weekly_report` is already advertised as widget-producing and tested.

---

## Change 2: Remove Status Fields from first_weekly_report Response

### Problem
`_handle_first_weekly_report` includes `flexStatus` and `pacingStatus` in `normalized_priorities`. During onboarding with test events, these are meaningless (1.5h vs 20h target = always "behind") and create false anxiety.

### What to Do
Remove these two lines from the `normalized_priorities` list comprehension in `_handle_first_weekly_report`:
```python
"flexStatus": p.get("flex_status"),
"pacingStatus": p.get("pacing_status"),
```

---

## Change 3: Tool Description and Guidance Wording — DO NOT MODIFY

### ⚠️ CRITICAL: The DESCRIPTION string and all `instruction` / `assistant_guidance` text strings have been manually crafted and iterated on. Do NOT rewrite, rephrase, reformat, or "improve" any of these strings. The owner will adjust wording manually after this briefing is applied.

### What to Do
- Only make the minimum mechanical changes needed within these strings: replace `first_snapshot` with `first_weekly_report` where it appears in phase references
- Do NOT change any other wording, punctuation, tone, or phrasing in DESCRIPTION, instruction strings, deliverable_education, transition_prompt messages, or any assistant_guidance text
- If a string doesn't need a mechanical rename, leave it exactly as-is

---

## Change 4: keyword_education Guidance — WORDING PROTECTED

The `instruction` string in `_handle_keyword_education` has been manually iterated. Do NOT modify its wording. Only make the mechanical rename from `first_snapshot` to `first_weekly_report` in `next_phase` if not already done.

---

## Change 5: first_weekly_report Guidance — STRUCTURAL CHANGES ONLY

### ⚠️ Do NOT modify any `instruction`, `message`, or descriptive text strings. Wording is manually crafted.

### Structural changes to make:
1. Remove the `_meta` block from `structured_content` (no `openai/outputTemplate`)
2. Add `widget_instruction` key to `assistant_guidance` at the same level as `instruction`, `deliverable_education`, `transition_prompt`, and `next_phase`. Use the `week_start` value from the report data (`data.get("week_start")`) to populate the arguments:
```python
"widget_instruction": {
    "required": True,
    "tool": "get_weekly_report",
    "arguments": {"week_start": data.get("week_start")},
    "purpose": "After presenting the data and deliverable education, call get_weekly_report to render the weekly report pie chart. Then proceed to the transition prompt.",
},
```
3. Confirm `transition_prompt` exists with `required: True` (should already be present)
4. Update the `content` text in the return statement from:
```python
text=f"Here's your first weekly snapshot: {total_hours:.1f}h tracked this week.",
```
to:
```python
text=f"Here's your first weekly report: {total_hours:.1f}h tracked this week.",
```
5. Confirm `action` value is `"FIRST_WEEKLY_REPORT"` (should already be updated from rename)

---

## Change 6: reflection_setup Guidance — WORDING PROTECTED

The `instruction` string in `_handle_reflection_setup` has been manually iterated. Do NOT modify its wording. Only confirm `onboarding_complete: True` is present and no `_meta` block exists in structuredContent.

---

## Change 7: Update Registry Invocation Message

### What to Do
In `__init__.py`, update the `TOOL_INVOCATION_MESSAGES` for `onboarding_calendar_setup`:

```python
"onboarding_calendar_setup": (
    "Walking you through tracking setup...",
    "Here's your tracking guide.",
),
```

---

## Unit Tests

### Tests to UPDATE (existing tests that need modification)

1. **`test_tool_metadata`** — add assertion: `assert ONBOARDING_CALENDAR_SETUP.widget_uri is None`

2. **`test_first_weekly_report_returns_weekly_data`** — remove assertions for `flexStatus`/`pacingStatus` if any exist. Add assertions:
   - `assert "flexStatus" not in normalized_priority` for each priority in data
   - `assert "pacingStatus" not in normalized_priority` for each priority in data
   - `assert "widget_instruction" in guidance`
   - `assert guidance["widget_instruction"]["required"] is True`
   - `assert guidance["widget_instruction"]["tool"] == "get_weekly_report"`
   - `assert "week_start" in guidance["widget_instruction"]["arguments"]`
   - `assert "transition_prompt" in guidance`
   - `assert guidance["transition_prompt"]["required"] is True`
   - `assert "openai/outputTemplate" not in result.structuredContent.get("_meta", {})` (no widget rendering from this tool)

3. **`test_keyword_education_returns_priorities_with_keywords`** — add assertion:
   - `assert "openai/outputTemplate" not in result.structuredContent.get("_meta", {})`

4. **`test_reflection_setup_returns_guidance_only`** — add assertion:
   - `assert "openai/outputTemplate" not in result.structuredContent.get("_meta", {})`

### Tests to ADD (new tests)

5. **`test_first_weekly_report_no_status_fields_in_response`** — explicitly verify that `flexStatus` and `pacingStatus` are absent from every priority in the normalized response data. Use the existing `mock_weekly_report_with_keywords` fixture (which includes `flex_status` in the mock backend response) to confirm the fields are stripped during normalization.

6. **`test_keyword_education_instruction_contains_weekly_report_terminology`** — assert the instruction string in `assistant_guidance` contains `"weekly report"` and does NOT contain `"snapshot"` or `"allocation"`.

7. **`test_first_weekly_report_instruction_contains_weekly_report_terminology`** — same check for `first_weekly_report` phase instruction.

8. **`test_reflection_setup_instruction_no_motivational_filler`** — assert the instruction string does NOT contain `"big leverage"`, `"real insight"`, `"game changer"`.

---

## Acceptance Criteria

1. All existing tests pass after modifications
2. All new tests pass
3. `keyword_education` returns NO `_meta` in structuredContent — no widget renders
4. `first_weekly_report` returns NO `_meta` in structuredContent — widget comes from `get_weekly_report` tool call instructed via `widget_instruction`
5. `reflection_setup` returns NO `_meta` in structuredContent — no widget renders
6. `ONBOARDING_CALENDAR_SETUP.widget_uri is None`
7. No `flexStatus` or `pacingStatus` in any onboarding response data
8. All `instruction` strings use "weekly report" — never "snapshot", "allocation", or other variations
9. `transition_prompt` and `widget_instruction` are structurally present with `required: True`
10. Tool description first paragraph is user-friendly (used by ChatGPT for permission dialog)

## What NOT to Do

- Do not refactor the handler routing pattern
- Do not change backend API calls or endpoints
- Do not modify other tools
- Do not add new phases
- Do not change the phase enum values beyond the already-completed rename to `first_weekly_report`
