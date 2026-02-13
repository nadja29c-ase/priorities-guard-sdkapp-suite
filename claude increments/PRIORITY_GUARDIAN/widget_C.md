# Widget Increment C: Time Allocation Bar

## Objective

Add the Time Allocation Bar section to the PG widget, rendering calendar-based time tracking data above the priority cards. After this increment: users see a stacked horizontal bar showing how their week's calendar time breaks down across P1/P2/P3 and "other" — the core visual feedback loop of Priority Guardian.

This is a **widget-only increment**. No backend or MCP changes. The data already flows via `data.timeAllocation` from the MCP `get_priorities` tool response (built in Increment 05).

---

## Prerequisites (must be done before E2E testing)

These are NOT part of this increment but block live calendar data:

1. **Scope fix:** `pg_config.py` — `GOOGLE_CALENDAR_SCOPE` must include both `calendar.events.readonly` AND `calendar.settings.readonly` (space-separated string). Without this, timezone fetch returns 403 → UTC fallback → wrong week boundaries for non-UTC users.
2. **Shared backend deploy:** Increment 05 backend code must be deployed to Render. Without it, `/api/priority-guardian/calendar/time-allocation` endpoint doesn't exist → MCP graceful degradation → `timeAllocation` absent → bar doesn't render.
3. **Google reconnection:** After scope change, user must disconnect and reconnect Google Calendar to get a token with the new scope.

Widget C can be built and visually tested with **hardcoded mock data** before these prerequisites are resolved.

---

## What Exists

### Widget (current state)
- `App.tsx` — Main component. Renders: error banner → priority cards → add priority form/button → connection status. No time allocation section.
- `types.ts` — `ToolOutputData` has `priorities`, `google_connected`, `available_keywords`. No `timeAllocation` type.
- `constants.ts` — Badge color classes: P1 = `bg-info-soft-alpha text-info`, P2 = `bg-discovery-soft-alpha text-discovery`, P3 = `bg-caution-soft-alpha text-caution`.
- `utils.ts` — `getToolOutput()` extracts `data` from `toolOutput`. Already returns full `data` object — `timeAllocation` will be accessible without changes to extraction logic.
- `main.css` — Imports Tailwind + SDK UI CSS. Has `main[role="main"]` padding override.

### MCP Data Shape (already flowing)

`get_priorities` returns `structuredContent.data.timeAllocation` when calendar data is available:

```json
{
  "timeAllocation": {
    "weekStart": "2026-02-09T00:00:00+01:00",
    "weekEnd": "2026-02-16T00:00:00+01:00",
    "totalTrackedHours": 31.75,
    "keywords": {
      "P1": { "hours": 10.5, "eventCount": 6 },
      "P2": { "hours": 3.0, "eventCount": 2 },
      "P3": { "hours": 0.0, "eventCount": 0 }
    },
    "otherHours": 18.25,
    "barSegments": {
      "P1": 10.5,
      "P2": 3.0,
      "P3": 0.0,
      "other": 18.25
    }
  }
}
```

**`timeAllocation` is absent (not null, not empty — absent from the object) when:**
- Google Calendar not connected
- Calendar endpoint failed (MCP graceful degradation)
- Calendar returned all zeros with null week dates (no connection)

**`timeAllocation` is present with all zeros when:**
- Google connected but no events this week

---

## What to Build

### New Component: `TimeAllocationBar`

**File:** `src/components/TimeAllocationBar.tsx`

**Placement in App.tsx:** ABOVE the priority cards section, BELOW the error banner. This is the first visual element users see — it answers "where did my time go this week?"

### Layout (from widget spec)

```
┌──────────────────────────────────────────────┐
│  Your time this week                  31.75h │
│  Feb 9 – Feb 15                              │
│                                              │
│  ┌─────────────────────────────────────────┐ │
│  │ P1 █████████  P2 ███  P3    other █████ │ │
│  └─────────────────────────────────────────┘ │
│                                              │
│  ● P1  10.5h   ● P2  3.0h   ● P3  0h       │
│  ● other  18.25h                             │
└──────────────────────────────────────────────┘
```

### Design Spec

**Header row:**
- Left: "Your time this week" — `text-sm font-medium text-default`
- Right: total tracked hours — `text-sm font-semibold text-default` (e.g., "31.75h")
- Below left: date range — `text-xs text-secondary` (e.g., "Feb 9 – Feb 15")

**Stacked bar:**
- Single horizontal bar, full width
- Height: 12px (`h-3`)
- Border radius: `rounded-full` on container
- Segments: percentage-based widths derived from `barSegments` values divided by `totalTrackedHours`
- Each segment uses the **same color** as its corresponding badge in the priority cards
- "Other" segment: `bg-surface-tertiary` (neutral gray)
- When `totalTrackedHours` is 0: show empty bar placeholder — single gray bar at full width

**Legend:**
- Row(s) of color dots + keyword + hours
- Dot: 8px circle (`w-2 h-2 rounded-full`), same color as bar segment
- Text: keyword label + hours — `text-xs text-secondary`
- Wrap naturally if more than one row needed
- Only show keywords that have active priorities (not all three always). If user only has P1 and P3, don't show P2 in legend.
- "Other" always shown (even if 0h) using italic text — `text-xs text-secondary italic`

**Container:**
- Same card style as priority cards: `bg-surface rounded-xl border border-default p-4`
- No shadow (consistent with card style)

### Color Mapping for Bar Segments

Bar segment colors MUST match the badge colors already defined in `constants.ts`. Do NOT use success/warning/danger semantic colors for the bar — the spec explicitly says "no judgment" colors on the dashboard.

For the **bar segment fills and legend dots**, use the `-soft-alpha` backgrounds:
- P1: `bg-info-soft-alpha` (muted blue)
- P2: `bg-discovery-soft-alpha` (muted purple)  
- P3: `bg-caution-soft-alpha` (muted amber/yellow)
- Other: `bg-surface-tertiary` (neutral gray)

**Problem:** The `-soft-alpha` tokens may be too light/transparent for a thin 12px bar to be visually distinguishable. If so, use the solid midtone tokens instead:
- P1: `bg-info-solid` or CSS `var(--color-background-info-solid)`
- P2: `bg-discovery-solid` or CSS `var(--color-background-discovery-solid)`
- P3: `bg-caution-solid` or CSS `var(--color-background-caution-solid)`

Test both in light and dark themes. The bar must be clearly readable in both. Pick whichever provides better contrast on the 12px bar height. Define the chosen colors as constants in `constants.ts` alongside the existing `BADGE_COLORS` (e.g., `BAR_COLORS`).

### Date Range Formatting

- Extract start/end dates from `weekStart` and `weekEnd` ISO strings
- Format: "Feb 9 – Feb 15" (month abbreviated, no year if same year as now)
- Use `window.openai?.locale` if available, fallback to `'en-US'`
- The week end in the API response is exclusive (next Monday 00:00). Display the **inclusive** end: subtract 1 day for display (show Sunday, not Monday).

### Conditional Rendering Rules

| State | Behavior |
|-------|----------|
| `timeAllocation` absent from data | Don't render the bar section at all. No placeholder, no "connect calendar" message (that's handled by ConnectionStatus at bottom). |
| `timeAllocation` present, `totalTrackedHours === 0` | Render the section with header, empty gray bar, legend with all 0h values. This is a valid state — "you have a connected calendar but no events this week." |
| `timeAllocation` present, normal data | Full render: header, stacked bar, legend. |

### When CRUD Updates Data

Mutation tools (`add_priority`, `update_priority`, `delete_priority`, etc.) return fresh priority data but do NOT include `timeAllocation` (they call only the priorities endpoint, not the calendar endpoint). 

**Behavior after CRUD:** Preserve the last-known `timeAllocation` from the initial load or last `get_priorities` call. Do NOT clear it. The calendar data doesn't change when priorities are edited — it only changes when calendar events change.

This means `App.tsx` needs to handle `timeAllocation` separately from the rest of `data` — CRUD responses update priorities but leave `timeAllocation` untouched.

---

## Files to Create

| File | Purpose |
|------|---------|
| `src/components/TimeAllocationBar.tsx` | Stacked bar component |

## Files to Modify

| File | Change |
|------|--------|
| `src/types.ts` | Add `TimeAllocation` interface, add `timeAllocation?` to `ToolOutputData` |
| `src/constants.ts` | Add `BAR_COLORS` mapping for segment fill colors |
| `src/App.tsx` | Import and render `TimeAllocationBar` above priority cards. Preserve `timeAllocation` across CRUD updates. |

## Files NOT to Modify

- No backend files
- No MCP files
- `src/utils.ts` — extraction logic already returns full `data` object
- `src/main.css` — no custom CSS needed if SDK tokens suffice

---

## Type Definitions

Add to `types.ts`:

```typescript
export interface TimeAllocationKeyword {
  hours: number
  eventCount: number
}

export interface TimeAllocation {
  weekStart: string    // ISO datetime
  weekEnd: string      // ISO datetime (exclusive — next Monday 00:00)
  totalTrackedHours: number
  keywords: {
    P1: TimeAllocationKeyword
    P2: TimeAllocationKeyword
    P3: TimeAllocationKeyword
  }
  otherHours: number
  barSegments: {
    P1: number
    P2: number
    P3: number
    other: number
  }
}
```

Update `ToolOutputData`:

```typescript
export interface ToolOutputData {
  google_connected: boolean
  google_connected_at?: string
  priorities: Priority[]
  available_keywords?: string[]
  timeAllocation?: TimeAllocation  // ← add
}
```

---

## Unit Tests

**File:** `src/__tests__/TimeAllocationBar.test.tsx`

Test framework: whatever is already set up in the widget test directory (check `src/__tests__/` or `src/test/` for existing patterns, likely Vitest + React Testing Library given the Vite setup).

### Rendering tests
- Renders nothing when `timeAllocation` is undefined (component receives undefined prop → returns null)
- Renders header with total hours when data present
- Renders date range formatted correctly (Feb 9 – Feb 15, not Feb 9 – Feb 16)
- Renders stacked bar with correct proportional widths
- Renders legend dots matching active priorities only
- Renders "other" in legend always (even when 0)

### Edge cases
- `totalTrackedHours` is 0 → renders empty gray bar, all legend items show 0h
- Only one priority exists (e.g., P1 only) → bar is P1 segment + other, legend shows only P1 + other
- All time is "other" (no keyword matches) → bar is entirely gray, legend shows only "other" with hours
- Very small segment (< 2% of total) → still visible (minimum width for segment, e.g., 2px or 1%)
- Large numbers: 168h tracked (extreme full-week case) → renders correctly, no overflow

### Color tests
- P1 segment uses P1 bar color
- P2 segment uses P2 bar color  
- P3 segment uses P3 bar color
- "other" segment uses neutral gray

### Accessibility
- Bar has `role="img"` and descriptive `aria-label` (e.g., "Time allocation: P1 10.5 hours, P2 3 hours, other 18.25 hours")
- Legend items are semantic (not just visual dots)

---

## Integration Tests

No integration tests needed — this is a pure UI component with no API calls, no callTool usage, no backend interaction.

The `TimeAllocationBar` receives a prop and renders. Integration testing of the data pipeline (MCP → widget) was covered in Increment 05.

---

## What This Increment Does NOT Include

- Weekly report link ("View weekly report →") — Weekly Report is a future increment. Do NOT add a placeholder link.
- `sendFollowUpMessage` bridge for reports
- Time allocation caching or refresh button (future)
- 3-week navigation / historical view
- Pie chart or alternative visualizations
- Animations on bar segments

---

## Design Principles (from widget spec)

**Dashboard = What IS (factual, no judgment)**
- No "on track" / "behind" / "at risk" labels
- No success/danger colors on the bar (use neutral, distinguishable palette)
- Pure information: hours, counts, date range
- The bar shows facts. Assessment lives in the Weekly Report (future).

**OpenAI UI guidelines compliance:**
- Use system font stack (inherited)
- Use SDK design tokens for all colors, spacing, border radius
- No custom gradients or patterns
- Respect dark mode: all semantic tokens auto-switch via `data-theme`
- Maintain WCAG AA contrast ratio on bar segments against card background
- Support text resizing without layout break

---

## Validation Criteria (Definition of Done)

1. `TimeAllocationBar` renders above priority cards when `timeAllocation` present
2. `TimeAllocationBar` renders nothing when `timeAllocation` absent
3. Stacked bar widths match `barSegments` proportions
4. Bar segment colors match priority badge colors (neutral palette, no judgment)
5. Date range shows inclusive end (Sunday, not Monday)
6. Legend shows only active priorities + "other"
7. Zero-hours state renders correctly (empty gray bar, 0h in legend)
8. CRUD operations preserve `timeAllocation` (don't clear it)
9. Correct rendering in both light and dark themes
10. All unit tests pass
11. Widget builds without errors (`npm run build`)
12. Accessible: `aria-label` on bar, semantic legend
