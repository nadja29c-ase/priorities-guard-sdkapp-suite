# Increment 77 — Two-Tool Split: `get_priority_events` + `render_weekly_report`

## Context and problem

The current `get_weekly_report` tool has `widget_uri=WIDGET_URI` registered on its
`ToolDefinition`. This causes ChatGPT to surface a widget card for EVERY call to the
tool — including call 2b (silent event-fetch), which is a data-only intermediate call
with no chart to show. This is host-level behaviour: `resourceUri` /
`openai/outputTemplate` on the tool descriptor is fixed per-tool and cannot be
suppressed per-call from the response side.

Result: user sees two widgets when asking for a P1 breakdown — a stale/empty one from
call 2b, then the correct exploded chart.

The OpenAI SDK explicitly documents the correct fix as the "decoupled pattern":
- **Data tools**: no widget template on descriptor. Return structuredContent only.
- **Render tools**: widget template on descriptor. Called only when there is something
  to show.

Source: developers.openai.com/apps-sdk/build/chatgpt-ui/#decoupled-pattern

---

## Solution: split into two tools

### Tool 1: `get_priority_events` (data tool — NO widget)

**Purpose:** Call 2b only. Fetches events for a specific priority keyword so the model
can read them and immediately group them. No widget card ever appears.

**`ToolDefinition`:**
- `name`: `"get_priority_events"`
- `widget_uri`: `None` — critical, this is what prevents the widget card
- `widget_accessible`: `False`
- `read_only_hint`: `True`
- `destructive_hint`: `False`
- `open_world_hint`: `True` (calls Google Calendar via backend)
- `required_scopes`: `["pg.access"]`
- `visibility`: `"public"` (LLM must be able to call it)

**INPUT_SCHEMA parameters:**
- `semantic_target` (required): `enum ["P1", "P2", "P3"]` — which priority's events to
  fetch. Description: "Priority keyword to fetch events for. Returns that priority's
  calendar events so you can group them into subcategories. After reading the events,
  IMMEDIATELY call render_weekly_report with semantic_groupings and
  semantic_target to render the breakdown chart. No user confirmation needed."
- `week_start` (optional): same as current tool — ISO date, Monday only.

**Handler logic:** Extract call 2b path from current `get_weekly_report.handle()` — the
`if has_priority_breakdown:` block. Move it verbatim into the new handler. Return
exactly what call 2b currently returns:
```python
structuredContent={
    "success": True,
    "data": {
        "weekStart": ...,
        "weekEnd": ...,
        "slices": [],
        "totalHours": ...,
        "isCurrentWeek": ...,
        "priorities": normalized_priorities,
        "timeAllocation": normalized_time_allocation,
        "priorityEvents": priority_events,
        "otherEvents": [],
    },
    "assistant_guidance": ...,
    # No _meta — no widget
}
```

No `_meta` in response. No `openai/outputTemplate`. No widget ever.

**CRITICAL: `get_priority_events` must NEVER include `_meta` in its response under any
condition** — not in the success path, not in error paths, not in edge cases. Any
accidental `_meta` on the response will cause ChatGPT to re-associate the tool with the
widget template and re-introduce the ghost card. Verify every return statement in the
handler has no `_meta` key.

**DESCRIPTION for LLM:**
```
Fetch calendar events for a specific priority to enable a breakdown chart.

Call this tool ONLY when the user asks to break down or analyse their time within
a single priority (e.g. "break down my P1 time", "what's in my P2 this week?").

After calling this tool, read the priorityEvents and IMMEDIATELY call
render_weekly_report with semantic_groupings and semantic_target to render the chart.
Do NOT propose groupings to the user first. Do NOT ask for confirmation. Just call
render_weekly_report.

Do NOT call this tool for the initial weekly report — use render_weekly_report directly.
Do NOT call this tool for past weeks (no event data available).
```

---

### Tool 2: `render_weekly_report` (render tool — HAS widget)

**Purpose:** All calls that produce a widget — call 1 (basic report), call 2 (other
breakdown confirmed), final priority breakdown render.

**`ToolDefinition`:**
- `name`: `"render_weekly_report"`
- `widget_uri`: `WIDGET_URI` — carries the widget card
- `widget_accessible`: `True` (future 3-week nav)
- `read_only_hint`: `True`
- `destructive_hint`: `False`
- `open_world_hint`: `True`
- `required_scopes`: `["pg.access"]`
- `visibility`: `"public"`

**INPUT_SCHEMA parameters:** Identical to current `get_weekly_report` INPUT_SCHEMA
minus the call 2b path — i.e. `week_start`, `semantic_groupings`, `semantic_target`
with the same descriptions. Update `semantic_target` description to remove any reference
to fetching events (that is now `get_priority_events`'s job).

Updated `semantic_target` description:
```
With semantic_groupings: replaces that category's slice in the chart with subcategory
slices. For 'other', pass after user confirms your proposed groupings. For P1/P2/P3,
pass immediately after calling get_priority_events — no user confirmation needed.
```

**Handler logic:** Take current `get_weekly_report.handle()` and remove the call 2b
path entirely (the `if has_priority_breakdown:` block). The handler now only handles:
- Call 1: basic report, returns full chart, includes `otherEvents`
- Call 2: groupings confirmed for `other` or priority, returns exploded chart

Call type detection simplifies to two states:
```python
has_semantic_groupings = semantic_groupings is not None and len(semantic_groupings) > 0
is_call1 = not has_semantic_groupings
```

Remove `has_priority_breakdown` and `is_call1` three-way detection entirely. Remove the
`has_priority_breakdown and not all_events` guard (no longer needed — that case now goes
to `get_priority_events` which handles it separately).

`_meta` is always present on render responses — never conditional:
```python
"_meta": {
    "openai/outputTemplate": WIDGET_URI,
}
```

**DESCRIPTION for LLM:**
```
Get your weekly report showing time invested in each priority, rendered as a pie chart.

Call this tool:
- When the user asks about their week, progress, or hours
- When the user says "how did I do?", "show my report", "weekly summary"
- At the start of a reflection or check-in conversation
- After calling get_priority_events: immediately call this tool with semantic_groupings
  and semantic_target to render the P1/P2/P3 breakdown chart

Do NOT call this tool:
- During onboarding or priority setup
- When the user is asking about patterns or trends over time (use get_patterns instead)
- To fetch events for a breakdown — use get_priority_events first, then call this tool
```

Update `GUIDANCE_WITHIN_PRIORITY_BREAKDOWN` inside the handler to reflect the new tool
name:
```python
GUIDANCE_WITHIN_PRIORITY_BREAKDOWN = (
    "You can also break down any single priority's time into subcategories. "
    "To do so, call get_priority_events with semantic_target set to the priority keyword "
    "(e.g. 'P1'). The tool will return that priority's events — immediately group them "
    "and call render_weekly_report with semantic_groupings to render the breakdown. "
    "No confirmation needed."
)
```

Also update `GUIDANCE_SEMANTIC_PROPOSAL_TEMPLATE` — the "call get_weekly_report again"
instruction must become "call render_weekly_report again":
```python
"IMMEDIATELY call render_weekly_report with the semantic_groupings parameter ..."
```

And `GUIDANCE_PRIORITY_BREAKDOWN_TEMPLATE` (still used in `get_priority_events`):
```python
"IMMEDIATELY call render_weekly_report again with semantic_groupings containing your "
"categories and semantic_target='{keyword}'. "
```

---

## File structure

**New files:**
- `mcp_server/priority_guardian/tools/get_priority_events.py` — new data tool
- Contains: `NAME`, `DESCRIPTION`, `INPUT_SCHEMA`, handler, `GET_PRIORITY_EVENTS`
  ToolDefinition

**Modified files:**
- `mcp_server/priority_guardian/tools/get_weekly_report.py` — renamed to
  `render_weekly_report.py`. Update `NAME = "render_weekly_report"`, update all
  guidance strings referencing `get_weekly_report` to `render_weekly_report`, remove
  call 2b path, simplify call type detection.
- `mcp_server/priority_guardian/tools/__init__.py` — import both new tools, register
  both in `TOOL_REGISTRY`, add invocation messages for both:
  ```python
  "get_priority_events": (
      "Fetching priority events...",
      "Events retrieved.",
  ),
  "render_weekly_report": (
      "Generating your weekly report...",
      "Here's your weekly time allocation.",
  ),
  ```
  Remove import and registry entry for `GET_WEEKLY_REPORT` / `get_weekly_report`.
- `doc/annotation_definitions.md` — add entries for both new tools following the
  existing format.

---

## What does NOT change

- Backend — no changes
- Widget (`App.tsx`) — no changes. Revert the `return <></>` guard if it was not
  already reverted (commit 825509d). Widget should be back to its pre-76b state:
  `if (isPieChartData(data) && data.slices.length > 0)`.
- DB — no changes
- OAuth — no changes
- `_build_pie_slices`, `_normalize_*` helpers — move to `render_weekly_report.py`
  unchanged
- `GUIDANCE_NO_PRIORITIES`, `GUIDANCE_CURRENT_WEEK`, `GUIDANCE_COMPLETED_WEEK`,
  `GUIDANCE_SEMANTIC_PROVIDED`, `GUIDANCE_CLOSING` — move unchanged
- All existing call 1 and call 2 test coverage — update tool name references only

---

## Call flow after this increment

```
User: "show my weekly report"
→ model calls render_weekly_report()
→ ONE widget, full pie chart ✅

User: "break down my P1 time"
→ model calls get_priority_events(semantic_target="P1")
→ NO widget card — data tool, no resourceUri on descriptor
→ model reads priorityEvents, groups them
→ model calls render_weekly_report(semantic_groupings=[...], semantic_target="P1")
→ ONE widget, P1 exploded ✅

User: "what's in my other time?"
→ model already has otherEvents from render_weekly_report call 1
→ model proposes groupings, user confirms
→ model calls render_weekly_report(semantic_groupings=[...], semantic_target="other")
→ ONE widget, other exploded ✅
```

---

## Compliance notes

- `get_priority_events` with `widget_uri=None` produces no `resourceUri` and no
  `openai/outputTemplate` in the tool descriptor — verified against `list_tools()` in
  `__init__.py`. This is the mechanism that prevents the widget card.
- Both tools require `readOnlyHint=True`, `destructiveHint=False`,
  `openWorldHint=True` — same as current `get_weekly_report`.
- Both tools require `securitySchemes: [{"type": "oauth2", "scopes": ["pg.access"]}]`
  — handled automatically by `list_tools()` from `required_scopes`.
- `annotation_definitions.md` must be updated — it is a canonical reference doc.
- `ANNOTATION_JUSTIFICATIONS.md` — if this file exists, add entries for both new tools
  before submission.

---

## Unit tests

Update existing `tests/unit/mcp_pg/test_weekly_report_handler.py`:
- Rename to `test_render_weekly_report_handler.py` or add new file
  `test_get_priority_events_handler.py`
- All existing call 2b tests move to `get_priority_events` test file
- All existing call 1 and call 2 tests stay with `render_weekly_report`
- `test_call2b_has_no_meta_widget_render` — verify `get_priority_events` response has
  no `_meta` key at any level
- `test_render_weekly_report_always_has_meta` — verify every non-error response from
  `render_weekly_report` includes `_meta["openai/outputTemplate"]`
- Remove any tests for the old mutual exclusion error (already removed in Inc 76)

No integration tests required — no backend or DB changes.

---

## Pre-deploy checklist

Read `OPERATIONS_PREDEPLOY.md` before committing.

Smoke tests after deploy:
1. "Show my weekly report" → one widget, full chart
2. "Break down my P1 time" → zero intermediate widgets, one exploded chart
3. "What's in my other time?" → proposal, confirm, one widget with other exploded
4. Past week → "not available" message for both tools
5. Refresh app connector in ChatGPT after deploy (tool descriptor changed)
