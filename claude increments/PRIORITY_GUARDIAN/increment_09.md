# Increment 09 — Display Snapshot Data in Dashboard UI

## Goal

Surface aggregate data and visual progress on the Priorities Dashboard cards. No categorical labels. No hidden thresholds. Raw numbers only — the user interprets them.

Flexible cards: cumulative investment percentage (`avgHoursWeek / weeklyHourTarget`).
Deadline cards: neutral progress bar for deliverables (pure completion ratio).
Both: `totalHoursInvested` and `avgHoursWeek` display.

**Design philosophy:** Dashboard = what IS. "4/7 done · 27d left" is factual. "Behind" is interpretation. The user sees the numbers and does the math themselves. Status labels (`pacing_status`, `flex_status`) exist in the snapshot/weekly report layer for historical records — they don't surface on the live dashboard.

---

## Architecture Decisions (Locked In)

| Card type | Progress indicator | Computed where | Why |
|---|---|---|---|
| Deadline | Neutral progress bar (doneCount/totalCount) | Widget (pure rendering) | Already has the counts. Just a visual bar. |
| Flexible | Raw percentage: `avgHoursWeek / weeklyHourTarget * 100` | Widget (pure rendering) | Both values already in response. No business logic — just division. |

**What's eliminated:**
- ~~flex_status computation anywhere in the dashboard flow~~
- ~~pacing_status computation in backend router / MCP passthrough~~
- ~~All threshold logic on dashboard~~
- ~~All categorical labels (ahead/on_track/behind) on dashboard~~
- ~~Color-coded progress bar fills~~

**What still exists unchanged (not part of this increment):**
- `compute_flex_status` and `compute_pacing_status` in `weekly_report_service` — used by snapshot_service (Inc 08) and weekly report generation. Already built, already capturing per-week data to `PgWeeklySnapshot.flex_status` and `PgWeeklySnapshot.pacing_status` columns. Not touched.

**Separation of concerns:**
- Backend = source of truth (aggregates already flowing: avg_hours_week, total_hours_invested, streak_count)
- MCP = transport + normalization only (passes through existing fields, zero new computation)
- Widget = pure rendering logic (division for percentage, bar width for progress)

---

## Layer 1: Backend — priorities_router.py

**No changes required.**

All fields needed (`avg_hours_week`, `total_hours_invested`, `streak_count`) are already included in `build_priorities_response` from Inc 08. No `pacing_status` computation needed for the dashboard.

---

## Layer 2: MCP — get_priorities.py

**File:** `mcp_server/priority_guardian/tools/get_priorities.py`

**No changes required.**

Verify these fields are already in `_normalize_priority` result dict (from Inc 08):
- `"streakCount": p.get("streak_count", 0)`
- `"avgHoursWeek": p.get("avg_hours_week")`
- `"totalHoursInvested": p.get("total_hours_invested", 0.0)`

If present, nothing to add.

---

## Layer 3: Widget Types — types.ts

**File:** `mcp_server/priority_guardian/widget-react/src/types.ts`

### Add to Priority interface (if missing from Inc 08)

```typescript
// Aggregate fields (flowing from Inc 08, ensure typed)
avgHoursWeek?: number | null
totalHoursInvested?: number
```

**Note:** `streakCount` is already typed. Check if `avgHoursWeek` and `totalHoursInvested` are in the interface — they were added to the MCP response in Inc 08 but may not be in types.ts yet. Add them if missing.

---

## Layer 4: Widget UI — Card Components

### Design Token Reference

Use semantic text colors: `text-secondary` for data values, `text-tertiary` for labels/empty states.

Progress bar uses neutral colors only — no pacing-based color mapping.

### FlexibleCard.tsx changes

**File:** `mcp_server/priority_guardian/widget-react/src/components/FlexibleCard.tsx`

**A. Cumulative investment percentage** — Display in non-edit mode, below the calendar keyword reminder (after the `mt-2 p-2 bg-surface-secondary` div).

Conditions:
- Show only when `priority.avgHoursWeek` is not null AND `priority.weeklyHourTarget` is not null and > 0
- If `avgHoursWeek` is null (no completed weeks yet): show "First week — tracking" in `text-xs text-tertiary`

Compute in render: `Math.round((avgHoursWeek / weeklyHourTarget) * 100)`

Display: `"~{pct}% of {target}h/week target on avg"` in `text-xs text-secondary`

Example: "~84% of 5h/week target on avg"

No badge. No color coding. Raw number.

**B. Aggregate stats line** — Below the percentage (or as part of same section):
- `totalHoursInvested` → "{X.X}h invested total" (show only if > 0)

Format: `text-xs text-secondary`

Example: "12.5h invested total"

**C. Streak display** — Already displayed. No change needed.

### DeadlineCard.tsx changes

**File:** `mcp_server/priority_guardian/widget-react/src/components/DeadlineCard.tsx`

**A. Progress bar** — Add a neutral visual progress bar for deliverables below the existing "X of Y done · Nd left" text:

- Width: full card width within the existing progress info section
- Height: 6px, rounded-full
- Track background: `bg-surface-tertiary`
- Fill: neutral color `bg-[color:var(--gray-400)]` — same color regardless of pace
- Fill percentage: `(doneCount / totalCount) * 100`, clamped 0-100
- Only render when `totalCount > 0`
- Accessibility: `role="progressbar"` with `aria-valuenow={doneCount}`, `aria-valuemin={0}`, `aria-valuemax={totalCount}`
- Transition: `transition-all duration-300 ease-out` on the fill width for smooth updates after toggling deliverables

No pacing-based colors. The bar is a pure visual representation of completion ratio.

**B. Aggregate stats line** — Below calendar keyword reminder, non-edit mode only:
- `totalHoursInvested` → "{X.X}h invested total" (show only if > 0)
- `avgHoursWeek` → "~{X.X}h avg/week" (show only if not null)

Format: `text-xs text-secondary`, separated by " · "

Example: "8.0h invested total · ~2.7h avg/week"

**C. Existing "X of Y done · Nd left"** — Already displayed. No change needed. This is the primary progress signal.

### What NOT to change

- No week navigator (deferred to Inc 10)
- No pacing_status badges anywhere
- No flex_status badges anywhere
- No color-coded progress indicators
- No changes to TimeAllocationBar, PieChart, HourRing, ConnectionStatus
- No changes to AddPriorityForm or AddDeliverableInput
- No changes to edit mode layout
- No changes to delete confirmation flow

---

## Unit Tests

### Widget: test rendering

**File:** `mcp_server/priority_guardian/widget-react/src/__tests__/` (add to existing or new test files)

**FlexibleCard tests:**
1. Renders cumulative percentage when `avgHoursWeek` and `weeklyHourTarget` are both set
2. Shows "First week — tracking" when `avgHoursWeek` is null
3. Hides percentage section when `weeklyHourTarget` is null or 0
4. Shows `totalHoursInvested` when > 0
5. Hides total when `totalHoursInvested` is 0
6. Percentage math is correct: `avgHoursWeek=4.2, weeklyHourTarget=5` → "~84%"
7. No percentage/stats shown in edit mode

**DeadlineCard tests:**
1. Renders progress bar when deliverables exist
2. Hides progress bar when 0 deliverables
3. Progress bar width matches `doneCount / totalCount` ratio (e.g. 3/7 → ~42.8%)
4. Progress bar has neutral color (not conditionally colored)
5. Progress bar has correct ARIA attributes
6. Shows `totalHoursInvested` when > 0
7. Shows `avgHoursWeek` when not null
8. Hides aggregate line when both values are 0/null
9. No stats shown in edit mode

---

## Integration Tests

**No new integration tests needed for Inc 09.**

- No backend changes → no backend integration tests
- Widget rendering tests are unit tests (mock props, check output)
- Aggregate data flow (backend → MCP → widget) already covered by Inc 08 integration tests

---

## Files Modified (Summary)

| File | Change |
|---|---|
| `mcp_server/.../widget-react/src/types.ts` | Add avgHoursWeek, totalHoursInvested to Priority type (if missing) |
| `mcp_server/.../widget-react/src/components/FlexibleCard.tsx` | Cumulative percentage display, aggregate stats |
| `mcp_server/.../widget-react/src/components/DeadlineCard.tsx` | Neutral progress bar, aggregate stats |
| `mcp_server/.../widget-react/src/__tests__/` | Rendering tests for both card types |

---

## Out of Scope

- Week navigator / historical browsing (Inc 10)
- ~~flex_status / pacing_status labels on dashboard~~ (eliminated — raw numbers only)
- ~~Threshold logic~~ (eliminated)
- ~~Backend router changes~~ (not needed)
- ~~MCP layer changes~~ (not needed beyond verifying existing passthrough)
- Weekly report persistence
- Week-over-week trend display (depends on Inc 10)
- Changes to PieChart, TimeAllocationBar, HourRing components