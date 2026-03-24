# Increment 76 — Priority Breakdown: Immediate Render (Remove Confirmation Dance)

## Problem

When a user explicitly asks to break down a priority (e.g. "break down my P1 time"), the
current implementation requires a confirmation dance:

1. Model calls `get_weekly_report(semantic_target="P1")` — receives events, renders normal chart
2. Model proposes groupings, asks user "does this look right?"
3. User confirms
4. Model calls again with `semantic_groupings` — chart finally renders exploded

This is wrong. The user **explicitly requested** the breakdown. The model has the events. It
should group them immediately and render the exploded chart in the same turn — no proposal,
no confirmation, no waiting.

**Contrast with `other` slice:** The confirmation dance is correct for `other` because the
model is making an educated guess about opaque non-priority time. The user may want to adjust
the groupings before rendering. That interaction is an invitation to engage.

Priority breakdown is different — the user already knows what P1 is. They asked for the
breakdown. Just do it.

## Correct Call Flow After This Increment

**User:** "break down my P1 time" (or any equivalent phrasing)

**Turn 1 — model fetches events (silent, no widget):**
- Model calls `get_weekly_report(semantic_target="P1")`
- Tool returns `priorityEvents` only — **no `_meta` widget render on this call**
- Model reads event titles and descriptions, groups them into subcategories

**Turn 1 continued — model immediately renders breakdown (same turn):**
- Model calls `get_weekly_report(semantic_groupings=[...], semantic_target="P1")`
- Tool returns exploded slices — widget renders with P1 broken down
- Model makes brief neutral observation about the breakdown

Two tool calls in one turn. The user sees one widget with the exploded chart. No
confirmation step.

---

## Changes Required

### 1. Call 2b: suppress widget render

When `has_priority_breakdown=True` (call 2b — fetching events only), remove `_meta` from
`structuredContent`. This prevents a stale unexploded chart from flashing before the final
exploded render.

In the handler, where `structured_content` is built, make `_meta` conditional:

```python
# Only include _meta widget render when there is something to show
# Call 2b (has_priority_breakdown=True) is a data-fetch only — no widget render
if not has_priority_breakdown:
    structured_content["_meta"] = {
        "openai/outputTemplate": WIDGET_URI,
    }
```

Call 1, call 2 (other confirmed), and the final priority breakdown call all retain `_meta`
and render the widget. Only call 2b loses it.

**Critical:** `_meta` must remain at the same level as before — top level of `structured_content`,
not nested inside `data`. Do not change the position of `_meta`, only make it conditional.
Wrong placement causes silent widget failures.

### 2. Remove the mutual exclusion error for priority + groupings

Currently the handler returns an error when `semantic_groupings` is provided together with
a priority `semantic_target`:

```python
if has_semantic_groupings and semantic_target in ("P1", "P2", "P3"):
    return ... isError=True ...
```

**Remove this error entirely.** The correct final call IS `semantic_groupings + semantic_target="P1"`.
This combination is valid and required for the breakdown to render. The mutual exclusion was
designed for a different (now-abandoned) flow.

After removal, the call type detection remains:
- `has_semantic_groupings=True` → call 2 (groupings confirmed, render chart) — works for
  both `other` and priority targets
- `has_priority_breakdown=True` (semantic_target in P1/P2/P3, no groupings) → call 2b
  (fetch events, no widget)
- `is_call1` → basic weekly report

No change to call type detection logic needed.

**Valid parameter combinations after this increment:**

| semantic_target | semantic_groupings | valid | result |
|---|---|---|---|
| None | None | ✅ | call 1 — basic report |
| `"other"` | None | ✅ | call 1 — basic report (other not yet broken down) |
| `"other"` | provided | ✅ | call 2 — render exploded other slice |
| `"P1"/"P2"/"P3"` | None | ✅ | call 2b — fetch events, no widget |
| `"P1"/"P2"/"P3"` | provided | ✅ | final call — render exploded priority slice |
| None | provided | ✅ | call 2 — defaults to `"other"` (backwards compat, existing behaviour) |

No new validation required. Existing backwards compatibility for `semantic_groupings` without
`semantic_target` is intentional — `_build_pie_slices` already defaults it to `"other"`.

### 3. Update `GUIDANCE_PRIORITY_BREAKDOWN_TEMPLATE`

Replace the current template that proposes, asks, and waits for confirmation with one that
instructs the model to act immediately:

```python
GUIDANCE_PRIORITY_BREAKDOWN_TEMPLATE = (
    "The user asked to break down their {keyword} time. "
    "Based on the event titles and descriptions in priorityEvents, group the events into "
    "semantic subcategories and assign approximate hours to each (category, hours, event_count). "
    "IMMEDIATELY call get_weekly_report again with semantic_groupings containing your "
    "categories and semantic_target='{keyword}'. "
    "Do NOT propose first. Do NOT ask for confirmation. Do NOT narrate the groupings. "
    "Just call the tool — the chart will show the breakdown."
)
```

### 4. Update `GUIDANCE_WITHIN_PRIORITY_BREAKDOWN`

The hint on call 1 that tells the model it can offer a priority breakdown should reflect the
new immediate flow:

```python
GUIDANCE_WITHIN_PRIORITY_BREAKDOWN = (
    "You can also break down any single priority's time into subcategories. "
    "To do so, call get_weekly_report with semantic_target set to the priority keyword "
    "(e.g. 'P1'). The tool will return that priority's events — immediately group them "
    "and call get_weekly_report again with semantic_groupings to render the breakdown. "
    "No confirmation needed."
)
```

### 5. Update `INPUT_SCHEMA` descriptions

**`semantic_groupings` description** — remove "Only pass this after user confirms groupings"
since priority breakdown no longer requires user confirmation:

```python
"description": (
    "Semantic categories for the target slice. "
    "When provided together with semantic_target, replaces that category's slice "
    "in the pie chart with these subcategory slices. "
    "For 'other' breakdown: pass after user confirms your proposed groupings. "
    "For priority breakdown (P1/P2/P3): pass immediately after reading priorityEvents — "
    "no user confirmation needed."
),
```

**`semantic_target` description** — update to reflect that the final priority breakdown
call uses `semantic_groupings + semantic_target` together:

```python
"description": (
    "Specifies which category to target. Two usage patterns: "
    "(1) Without semantic_groupings: setting to 'P1', 'P2', or 'P3' fetches that "
    "priority's events into priorityEvents for grouping. No widget rendered. "
    "(2) With semantic_groupings: the named category is replaced by its subcategory "
    "slices in the chart. For 'other', pass after user confirms. "
    "For P1/P2/P3, pass immediately after reading priorityEvents."
),
```

---

## What Does NOT Change

- Call 1 (basic weekly report) — unchanged
- Call 2 for `other` slice — unchanged: proposal → user confirms → render. The confirmation
  flow for `other` is correct and stays.
- `_build_pie_slices` — unchanged
- `slice_semantic_target = None if has_priority_breakdown else semantic_target` — unchanged:
  call 2b still renders normal chart (now without `_meta`); final call has
  `has_priority_breakdown=False` so `slice_semantic_target = semantic_target = "P1"` and
  P1 is correctly exploded
- Event filtering logic — unchanged
- Backend, widget, DB — unchanged

---

## Tests

### Unit tests (`tests/unit/mcp_pg/test_weekly_report_handler.py`)

- `test_call2b_has_no_meta_widget_render`: verify that when `semantic_target="P1"` and no
  `semantic_groupings`, `_meta` is absent from `structuredContent`
- `test_call1_has_meta_widget_render`: verify call 1 still has `_meta`
- `test_priority_groupings_confirmed_has_meta`: verify that `semantic_groupings +
  semantic_target="P1"` returns success with `_meta` present and slices exploded
- `test_priority_groupings_no_longer_blocked`: verify that `semantic_groupings +
  semantic_target="P1"` does NOT return `isError=True` (mutual exclusion removed)
- Update `test_mutual_exclusion_returns_error`: this test must be deleted or repurposed —
  the mutual exclusion no longer exists

### Integration tests

None required — no backend or DB changes.

---

## Pre-Deploy Checklist

Read `OPERATIONS_PREDEPLOY.md` before committing. No DB migrations. No OAuth changes.

Smoke test with test account (`review@priority-guard.com`):
1. Call `get_weekly_report` (call 1) → confirm widget renders, `_meta` present
2. Ask model to "break down P1" → confirm:
   - Call 2b fires (no widget flash)
   - Model immediately fires final call with `semantic_groupings + semantic_target="P1"`
   - Single widget renders with P1 exploded
   - No confirmation step, no proposal text before chart
3. Ask model to break down `other` → confirm confirmation flow still works as before
4. Past week → confirm "not available" message still fires correctly for priority breakdown
