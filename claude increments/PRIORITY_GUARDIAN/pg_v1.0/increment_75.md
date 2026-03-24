# Increment 75 — Data Minimization: `get_weekly_report` Event Filtering

## Context

**Compliance driver:** OpenAI App Submission Guidelines — Response Minimization rule:
> "Tool responses must return only data that is directly relevant to the user's request and the tool's stated purpose."

**Current violation:** `get_weekly_report` sends ALL calendar events (P1 + P2 + P3 + other) to the model on every call, including calls where P1/P2/P3 events serve no purpose. This is a data minimization violation.

**Root cause:** `allEvents` is a flat list of all filtered events for the week, placed in `structuredContent` unconditionally. The model receives every event title, description, and timestamp regardless of what the call actually needs.

**No DB changes. No backend changes. MCP server layer only.**

---

## Redesigned Call Flow

### Call 1 — Basic weekly report (`semantic_groupings=None`, `semantic_target=None`)

**LLM receives in `structuredContent`:**
- Per-priority aggregates: name, keyword, actual hours, event count, type-specific fields (deadline date, days remaining, deliverables for deadline; target hours for flexible)
- Time allocation totals: P1/P2/P3 hours, `other` hours, total calendar hours
- `otherEvents` — only non-priority events (`matchedKeywords == []`) — for semantic grouping proposal
- `priorityEvents` — empty list `[]`
- `assistant_guidance` referencing `otherEvents` (not `allEvents`)

**LLM does NOT receive:** P1/P2/P3 individual events

---

### Call 2 — User confirms `other` breakdown (`semantic_groupings` provided, `semantic_target="other"`)

**LLM receives in `structuredContent`:**
- Same per-priority aggregates and time allocation totals as call 1 — widget needs these to render non-exploded slices; model must not rely on memory for these values
- `otherEvents` — empty list `[]` — groupings already passed back as `semantic_groupings` input
- `priorityEvents` — empty list `[]`
- `assistant_guidance` directing model to brief neutral observation only

---

### Call 2b — User asks to break down a specific priority (`semantic_target = "P1" | "P2" | "P3"`, no `semantic_groupings`)

**LLM receives in `structuredContent`:**
- Same per-priority aggregates and time allocation totals — widget needs these for all non-exploded slices
- `otherEvents` — empty list `[]`
- `priorityEvents` — only events matching the requested keyword, filtered in the MCP layer using `matchedKeywords`
- `assistant_guidance` for within-priority semantic grouping (same pattern as `other` grouping on call 1)

**Important:** `semantic_target` already exists in the current `INPUT_SCHEMA` with enum `["P1", "P2", "P3", "other"]`. **No schema change in this increment.** Only handler logic changes.

`semantic_target` has a dual role after this increment:
- When `semantic_groupings` is also provided: selects which pie slice to explode (existing behaviour)
- When `semantic_groupings` is absent and value is `"P1"`/`"P2"`/`"P3"`: triggers priority event fetch for breakdown proposal (new behaviour)

This dual role is resolved cleanly by call type detection — no ambiguity at runtime.

---

## Changes Required

### 1. Call type detection logic

Replace the current single `has_semantic_groupings` flag with explicit three-way call type detection. All three cases must be mutually exclusive and exhaustive:

```python
has_semantic_groupings = semantic_groupings is not None and len(semantic_groupings) > 0
is_other_target = semantic_target == "other"
has_priority_breakdown = (
    semantic_target in ("P1", "P2", "P3")
    and not has_semantic_groupings
)
is_call1 = (
    not has_semantic_groupings
    and not has_priority_breakdown
)
# Note: semantic_target="other" with no semantic_groupings falls into is_call1 (correct —
# "other" without groupings means no breakdown has been requested yet)
```

**Mutual exclusion validation** — return a structured error response (do not raise), consistent with how all other validation errors are handled in this codebase:

```python
if has_semantic_groupings and semantic_target in ("P1", "P2", "P3"):
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="Invalid parameters.")],
        structuredContent={
            "success": False,
            "error": "invalid_parameters",
            "assistant_guidance": (
                "semantic_groupings and a priority semantic_target cannot be used together. "
                "Use semantic_target alone to request priority events for breakdown, "
                "then semantic_groupings to confirm the categorisation."
            ),
        },
        isError=True,
    )
```

---

### 2. Event filtering — MCP layer, no backend change

The backend still returns the full `all_events` list. Filtering happens after normalization in the tool handler:

```python
normalized_events = [_normalize_event(e) for e in all_events]

# Filter by call type
if is_call1:
    other_events = [e for e in normalized_events if not e.get("matchedKeywords")]
    priority_events = []
elif has_priority_breakdown:
    other_events = []
    priority_events = [
        e for e in normalized_events
        if semantic_target in e.get("matchedKeywords", [])
    ]
else:  # has_semantic_groupings
    other_events = []
    priority_events = []
```

---

### 3. `structuredContent` — fixed keys, always present

Replace `allEvents` with two fixed keys, always included, populated only when relevant. Fixed keys prevent model confusion and make tests deterministic:

```python
structured_content = {
    "success": True,
    "data": {
        # Pie chart fields (widget uses these — always present)
        "weekStart": ...,
        "weekEnd": ...,
        "slices": slices,
        "totalHours": total_hours,
        "semanticTarget": semantic_target,
        "semanticTargetLabel": semantic_target_label,
        # Aggregate fields (always present — widget and model need these on every call)
        "isCurrentWeek": ...,
        "priorities": normalized_priorities,
        "timeAllocation": normalized_time_allocation,
        # Event fields — fixed keys, populated only for relevant call type
        "otherEvents": other_events,       # non-empty on call 1 only
        "priorityEvents": priority_events, # non-empty on call 2b only
    },
    "_meta": {
        "openai/outputTemplate": WIDGET_URI,
    },
    "assistant_guidance": assistant_guidance,
}
```

`allEvents` is removed entirely. No other field names change.

---

### 4. `assistant_guidance` — update all references from `allEvents`

Update `_build_assistant_guidance` and all guidance template strings:

- Replace all references to `allEvents` with `otherEvents` in call 1 guidance
- Replace all references to `allEvents` with `priorityEvents` in call 2b guidance
- Call 2 guidance (`GUIDANCE_SEMANTIC_PROVIDED`) does not reference event lists — unchanged

Specific changes:

**`GUIDANCE_SEMANTIC_PROPOSAL_TEMPLATE`** — currently references `allEvents`:
```python
# Before:
"Based on the event titles and descriptions in allEvents, propose approximate semantic categories."
# After:
"Based on the event titles and descriptions in otherEvents, propose approximate semantic categories."
```

**`GUIDANCE_WITHIN_PRIORITY_BREAKDOWN`** — currently a passive mention, upgrade to active instruction:
```python
# Before:
"You can also propose a within-priority breakdown for any single priority."
# After:
"You can also propose a within-priority breakdown for any single priority. "
"To do so, call get_weekly_report again with semantic_target set to the priority keyword "
"(e.g. 'P1'). The tool will return that priority's events in priorityEvents for you to categorise."
```

Add a new guidance template for call 2b (within-priority breakdown):

```python
GUIDANCE_PRIORITY_BREAKDOWN_TEMPLATE = (
    "The user wants to see how their {keyword} time breaks down. "
    "Based on the event titles and descriptions in priorityEvents, propose approximate "
    "semantic subcategories. Frame it as a NEUTRAL observation: "
    "'Your {keyword} time looks like it breaks down to roughly: [category] ~Xh, etc.' "
    "Ask if this grouping looks right. "
    "CRITICAL: NEVER interpret or judge priority time. "
    "If they confirm OR express any intent to see the breakdown, "
    "IMMEDIATELY call get_weekly_report again with semantic_groupings containing your "
    "proposed categories and semantic_target='{keyword}'. "
    "Do NOT ask again. Just call the tool."
)
```

Update `_build_assistant_guidance` to use this template when `has_priority_breakdown` is True.

---

### 5. `onboarding_calendar_setup` — filter to non-priority events only

`_handle_first_weekly_report` has the same violation: P1/P2/P3 events go to the model when only `other` events are needed for the semantic grouping explanation.

**Field name stays `allEvents`** — the onboarding tool does not change its response structure. Only the contents are filtered.

One-liner change in `_handle_first_weekly_report`:

```python
# Before:
normalized_events = [
    {
        "title": e.get("title", ""),
        "description": e.get("description", ""),
        "start": e.get("start"),
        "end": e.get("end"),
        "matchedKeywords": e.get("matched_keywords", []),
    }
    for e in all_events
]

# After:
normalized_events = [
    {
        "title": e.get("title", ""),
        "description": e.get("description", ""),
        "start": e.get("start"),
        "end": e.get("end"),
        "matchedKeywords": e.get("matched_keywords", []),
    }
    for e in all_events
    if not e.get("matched_keywords")  # non-priority events only
]
```

No structural change to the onboarding response. No rename. The onboarding assistant_guidance already references `allEvents` — that reference remains correct since the field name is unchanged there.

---

## What Does NOT Change

- Backend service (`weekly_report_service.py`) — unchanged, still returns full `all_events`
- `_normalize_event` function — unchanged
- `_normalize_priority_report` — unchanged
- `_normalize_time_allocation` — unchanged
- `_build_pie_slices` — unchanged (uses `semantic_groupings` + `semantic_target`, already present)
- Widget (`App.tsx`, `PieChart.tsx`) — unchanged; widget reads `slices` for rendering, not event lists
- All other tools — unchanged
- `semantic_target` input parameter — already exists, not added or renamed

---

## Tests

### Unit tests (`tests/unit/`)

- `test_call1_returns_other_events_only`: verify call 1 (no `semantic_groupings`, no `semantic_target`) returns only non-priority events in `otherEvents` and empty `priorityEvents`
- `test_call1_always_includes_aggregates`: verify `priorities` and `timeAllocation` present on call 1
- `test_call2_returns_no_events`: verify call 2 with `semantic_groupings` returns empty `otherEvents` and empty `priorityEvents`
- `test_call2_always_includes_aggregates`: verify `priorities` and `timeAllocation` present on call 2
- `test_call2b_returns_priority_events_only`: verify `semantic_target="P1"` (no `semantic_groupings`) returns only P1-matched events in `priorityEvents` and empty `otherEvents`
- `test_call2b_always_includes_aggregates`: verify `priorities` and `timeAllocation` present on call 2b
- `test_mutual_exclusion_returns_error`: verify that `semantic_groupings` + priority `semantic_target` together returns structured error with `isError=True`, does not raise
- `test_other_target_with_groupings_not_blocked`: verify `semantic_groupings` + `semantic_target="other"` is valid (existing call 2 behaviour)
- `test_onboarding_other_events_only`: verify `_handle_first_weekly_report` returns only non-priority events in `allEvents`

### Integration tests

None required — no backend or DB changes.

---

## Pre-Deploy Checklist

Before deploying, read `OPERATIONS_PREDEPLOY.md` and verify:

- No DB migrations — skip migration checks
- No OAuth config changes — skip OAuth discovery verification
- Smoke test against production with test account (`review@priority-guard.com`):
  1. Call `get_weekly_report` (no params) → verify `otherEvents` contains only non-priority events, `priorityEvents` is empty, aggregates present
  2. Confirm other grouping → verify both event lists empty, aggregates present, pie chart renders correctly
  3. Call `get_weekly_report` with `semantic_target="P1"` → verify `priorityEvents` contains only P1-matched events, `otherEvents` empty, aggregates present
  4. Call with `semantic_groupings` + `semantic_target="P1"` → verify structured error returned, `isError=True`
  5. Trigger onboarding `first_weekly_report` phase → verify `allEvents` contains only non-priority events

---

## Compliance Reference

- OpenAI Submission Guidelines: Response Minimization
- `compliance_master_1.3.26.md` items D1, D2
