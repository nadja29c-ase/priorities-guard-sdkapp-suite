# PG Increment 07: Weekly Report → Pie Chart Widget

**Status:** Ready for implementation  
**Created:** 2026-02-13  
**Depends on:** Increment 06 (simplified weekly report) — shipped  

---

## Goal

`get_weekly_report` renders a pie chart widget showing time allocation. On first call, it shows P1/P2/P3 + single "Other" slice. LLM narrates and proposes semantic groupings. On second call (with user-confirmed groupings passed as input), it re-renders the pie chart with "Other" broken into semantic categories. No persistence. No new tools. One tool, optional parameter.

## User Flow

1. User asks for weekly report
2. LLM calls `get_weekly_report()` → **Widget 1:** Pie chart with P1/P2/P3 + "Other" blob
3. LLM narrates per-priority results, proposes semantic groupings from event titles/descriptions
4. User confirms or adjusts groupings
5. LLM calls `get_weekly_report(semantic_groupings=[...])` → **Widget 2:** Pie chart with P1/P2/P3 + broken-out semantic slices
6. LLM makes a brief closing observation, asks what stands out

Two widget instances in conversation (SDK constraint — each tool call with `widget_uri` creates new instance). This is intentional: shows progression from rough to refined view.

---

## Part A: MCP Tool — `get_weekly_report`

### Input Schema Change

Add optional `semantic_groupings` parameter:

```
semantic_groupings:
  type: array (optional)
  items:
    category: string (required) — e.g. "Client calls", "Admin"
    hours: number (required) — hours in this category
    event_count: integer (required) — number of events
  description: "User-confirmed semantic categories for non-priority time. When provided, replaces the 'Other' slice in the pie chart with these categories."
```

`week_start` stays as-is (optional, defaults to current week).

### Tool Definition Changes

| Field | Before | After | Reason |
|-------|--------|-------|--------|
| `widget_uri` | `None` | `"ui://widget/pg-dashboard.html"` | Pie chart renders in the existing widget |
| `widget_accessible` | `False` | `True` | Widget can call this tool via `callTool` (needed for future 3-week nav per locked spec). Does NOT mean "LLM reads widget" — means widget can invoke the tool. |

Add to `TOOL_INVOCATION_MESSAGES` — the tool now produces a widget, so it needs invocation messages.

Annotations stay unchanged: `read_only_hint=False`, `destructive_hint=False`, `open_world_hint=True`.

### Handler Response Shape

The handler ALWAYS returns pie chart data (both with and without `semantic_groupings`). The response `structuredContent.data` must satisfy both:
- **Widget needs:** `slices`, `totalHours`, `weekStart`, `weekEnd` (matches existing `PieChartData` type in `types.ts`)
- **LLM needs:** `priorities`, `allEvents`, `isCurrentWeek` (for narration via `assistant_guidance`)

Include all fields in `structuredContent.data`. The widget reads `slices`/`totalHours`/`weekStart`/`weekEnd` via `isPieChartData()` type guard. The LLM reads everything via `assistant_guidance` context.

### Validation

When `semantic_groupings` is provided, validate before building slices:

1. **Over-allocation check:** If `sum(groupings.hours) > other_hours + 0.5`, return `isError=True` with message: "Grouped hours (Xh) exceed non-priority time (Yh) by more than rounding tolerance. Please adjust." The 0.5h absolute tolerance accounts for LLM estimation rounding — not percentage-based, keeps user-confirmed numbers untouched.
2. **No normalization.** Never silently scale user-confirmed hours. What the user confirms is what the chart shows. The remainder (if any) becomes "Uncategorized."
3. **Empty array:** Treat `semantic_groupings: []` same as not provided (show "Other" slice).

### Slice Construction Logic

**Always (from backend `time_allocation.keywords`):**
- For each active priority: `{ label: "{keyword}: {priority_name}", hours: X, type: "priority", keyword: "P1" }`
- Only include priorities with `hours > 0`

**Without `semantic_groupings` (first call):**
- Add single: `{ label: "Other", hours: other_hours, type: "semantic" }` (if `other_hours > 0`)

**With `semantic_groupings` (second call, after validation):**
- Add each category as-is: `{ label: category, hours: X, type: "semantic", eventCount: N }` — never modify user-confirmed hours
- **Remainder handling:** If `other_hours - sum(groupings.hours) >= 0.25`, add `{ label: "Uncategorized", hours: remainder, type: "semantic" }`. Users will naturally group the big chunks and ignore small stuff — this catches the rest. If remainder < 0.25h, skip it (rounding noise, absorbed visually).

### `_meta` and `outputTemplate`

When the handler returns slices, include `_meta.openai/outputTemplate` pointing to the widget URI. This tells the SDK to render the widget.

The existing `save_semantic_grouping.py` handler shows the correct pattern for including `_meta` in structuredContent (see line with `"openai/outputTemplate": WIDGET_URI`).

### `assistant_guidance` — Two Modes

**Mode 1: No `semantic_groupings` provided (first call)**

Guidance must instruct the LLM to:
- Narrate per-priority results (hours, flex_status or pacing_status, comparison to target). Include ALL active priorities — if a priority has zero hours, say so explicitly ("You didn't log any P3 time this week"). Zero-hour priorities are excluded from pie slices but must still be narrated.
- Propose approximate semantic categories for non-priority time based on the `allEvents` array in `structuredContent.data` (titles and descriptions are there — do NOT duplicate event titles into guidance text, keep guidance lean)
- Frame groupings as an observation: "Your non-priority time looks like it breaks down to roughly: Client calls ~8h, Admin ~3h, Tax prep ~2h"
- Ask user if this grouping looks right or if they'd adjust it
- If user confirms: call `get_weekly_report` again with `semantic_groupings` parameter containing the confirmed categories

**Mode 2: `semantic_groupings` provided (second call)**

Guidance must instruct the LLM to:
- NOT repeat or list the categories — the pie chart displays them
- Make a brief coaching observation about the overall distribution
- Ask what stands out or what they'd like to adjust next week
- Keep it short — the visual does the heavy lifting

### Backend Call

Both call 1 and call 2 hit the same backend endpoint (`GET /api/priority-guardian/weekly-report`). Call 2 is a redundant fetch (same data as call 1). Acceptable at once-per-week frequency. The `semantic_groupings` parameter is MCP-level only — never sent to the backend.

### Priority Name Resolution

The handler needs priority names for slice labels (e.g., "P1: Build PG" not just "P1"). The backend response includes `priorities[].name` and `priorities[].calendar_keyword`. Map these to build labels.

---

## Part B: `save_semantic_grouping` — Delete

This tool is fully replaced by the `semantic_groupings` parameter on `get_weekly_report`. 

**Delete the file:** `mcp_server/priority_guardian/tools/save_semantic_grouping.py`

**Clean up `__init__.py`:** Remove the commented import line referencing `save_semantic_grouping`.

The backend endpoint `POST /weekly-report/semantic-grouping` was already removed in Increment 06. The Pydantic models were already removed. This just cleans up the MCP tool file.

---

## Part C: Widget — Verify Compatibility

The existing widget infrastructure should work without changes. Verify:

1. **`isPieChartData()` type guard** in `types.ts` triggers on `'slices' in data` — the new response shape includes `slices`, so this will route to `PieChart` view correctly.

2. **`PieChart.tsx` component** already handles both `priority` and `semantic` slice types with correct colors and legend.

3. **`App.tsx`** already has the `isPieChartData` branch that renders `<PieChart>`.

4. **Extra fields in data** (`priorities`, `allEvents`, `isCurrentWeek`) — the widget ignores them but TypeScript will flag them. Extend the type in `types.ts`:

```typescript
export interface PieChartData {
  weekStart: string
  weekEnd: string
  slices: PieSlice[]
  totalHours: number
  // Extra fields from get_weekly_report (widget ignores, LLM uses)
  priorities?: unknown[]
  allEvents?: unknown[]
  isCurrentWeek?: boolean
  [key: string]: unknown  // Forward-compatible with future fields
}
```

The `isPieChartData` guard (`'slices' in data`) remains correct.

---

## Part D: No Backend Changes

The backend weekly report endpoint already returns everything needed. No router, service, or model changes required.

---

## Existing File Reference

| File | Role |
|------|------|
| `mcp_server/priority_guardian/tools/get_weekly_report.py` | Tool definition + handler — main changes here |
| `mcp_server/priority_guardian/tools/__init__.py` | Registry — update invocation messages, remove save_semantic_grouping comment |
| `mcp_server/priority_guardian/tools/save_semantic_grouping.py` | DELETE this file |
| `mcp_server/priority_guardian/widget-react/src/types.ts` | May need PieChartData type extension |
| `mcp_server/priority_guardian/widget-react/src/components/PieChart.tsx` | Existing — verify compatibility |
| `mcp_server/priority_guardian/widget-react/src/App.tsx` | Existing — verify isPieChartData routing |

---

## Unit Tests

### `tests/unit/mcp_pg/test_weekly_report_handler.py` (extend existing)

**Slice construction tests:**
- Without `semantic_groupings`: slices contain priority slices + single "Other" slice
- With `semantic_groupings`: slices contain priority slices + semantic category slices
- With partial `semantic_groupings` (sum < other_hours by ≥ 0.25h): "Uncategorized" remainder slice added
- With partial `semantic_groupings` (sum < other_hours by < 0.25h): no remainder, absorbed into largest slice
- Priority slices use `{keyword}: {name}` label format
- Zero-hour priorities excluded from slices
- Zero `other_hours` → no "Other" slice
- Empty `semantic_groupings` array → treated same as not provided (show "Other")

**Validation tests:**
- `sum(groupings.hours) > other_hours + 0.5` → returns `isError=True`
- `sum(groupings.hours) <= other_hours + 0.5` → accepted, hours shown as-is (no normalization)
- `sum(groupings.hours) < other_hours` with remainder ≥ 0.25h → "Uncategorized" slice added
- `sum(groupings.hours) < other_hours` with remainder < 0.25h → no remainder slice
- Total pie chart hours (priority slices + semantic slices + uncategorized) always equals `totalHours`

**Assistant guidance tests:**
- Without groupings: guidance mentions proposing categories, references `allEvents` abstractly (does NOT contain raw event titles), instructs to call again with `semantic_groupings`
- Without groupings: guidance instructs LLM to narrate ALL active priorities including zero-hour ones ("You didn't log any P3 time this week")
- With groupings: guidance says NOT to list categories, make brief observation
- Without groupings: guidance does NOT contain "save" or "snapshot" language
- With groupings: guidance does NOT contain "save" or "snapshot" language

**structuredContent tests:**
- `_meta.openai/outputTemplate` present and equals widget URI
- `data.slices` is array
- `data.totalHours` is number
- `data.priorities` included (for LLM narration)
- `data.allEvents` included (for LLM grouping proposal)

### `tests/unit/mcp_pg/test_save_semantic_grouping_disabled.py` → DELETE or rename

This test file verified that `save_semantic_grouping` was disabled from the registry. Since the tool is being deleted entirely, these tests need updating:
- Verify `save_semantic_grouping` is NOT in `TOOL_REGISTRY`
- Verify the file does NOT exist on disk
- Verify `list_tools()` does not include it
- Verify `get_weekly_report` IS still registered

### `tests/unit/mcp_pg/test_tool_registry.py` or `tests/unit/priority_guardian/test_tool_registry.py`

- Verify `get_weekly_report` has `widget_uri` set (not None)
- Verify `get_weekly_report` has `widget_accessible=True`
- Verify `get_weekly_report` has invocation messages in `TOOL_INVOCATION_MESSAGES`

---

## Integration Tests

### `tests/integration/priority_guardian/test_weekly_report_simplified.py` (extend existing)

**Pie chart data shape tests (mock Google Calendar):**
- Call without `semantic_groupings` → response has `slices` with priority + "Other"
- Call with `semantic_groupings` → response has `slices` with priority + semantic categories
- Call with partial `semantic_groupings` → "Uncategorized" remainder slice present
- Call with over-allocated `semantic_groupings` (>other_hours + 0.5h) → `isError=True`
- `totalHours` equals sum of all slice hours (mathematical correctness)
- Response includes both pie chart fields (`slices`) and report fields (`priorities`, `allEvents`)

**Round-trip test:**
- Call 1 (no groupings) → verify "Other" slice hours match `other_hours` from allocation
- Call 2 (with groupings) → verify semantic slice hours match input groupings
- Both calls return same `weekStart`/`weekEnd`

---

## Definition of Done

1. `get_weekly_report` accepts optional `semantic_groupings` parameter
2. Without groupings: returns pie chart with P1/P2/P3 + "Other" + widget renders
3. With groupings: returns pie chart with P1/P2/P3 + semantic slices + widget renders
4. `assistant_guidance` differs between mode 1 (propose groupings) and mode 2 (brief observation)
5. `save_semantic_grouping.py` file deleted, all references removed
6. `widget_uri` and `widget_accessible` updated on tool definition
7. Widget renders correctly for both modes (verify in MCP Inspector or ChatGPT)
8. All unit tests pass
9. All integration tests pass
10. No TypeScript build errors in widget-react
