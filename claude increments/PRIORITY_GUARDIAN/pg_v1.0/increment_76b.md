# Increment 76b — Widget: suppress render when slices are empty (call 2b)

## Problem

ChatGPT loads the widget on every `get_weekly_report` call because widget loading
is tied to the tool registration, not the response payload. Call 2b returns
`slices: []` (silent event-fetch, no chart to show). The widget receives this,
`isPieChartData` returns true (because `slices` key is present), but
`data.slices.length > 0` is false so the pie chart branch is skipped.
The widget falls through to the dashboard branch and renders a stale dashboard.

Result: user sees two widgets — a stale/empty one from call 2b, then the correct
exploded chart from the final call.

## Fix

**File:** `mcp_server/priority_guardian/widget-react/src/App.tsx`  
**One change only.**

Find this exact line in App.tsx:

```tsx
if (isPieChartData(data) && data.slices.length > 0) {
```

Replace the entire pie chart render branch with a restructured version that
handles the empty slices case explicitly, BEFORE any fallthrough to the dashboard:

```tsx
if (isPieChartData(data)) {
  if (!data.slices || data.slices.length === 0) {
    return <></>  // call 2b: silent event-fetch, render nothing
  }
  return (
    <main
      role="main"
      aria-label="Time Allocation Pie Chart"
      className={`bg-surface-secondary rounded-2xl p-4 pb-2${!isInline ? ' max-w-2xl mx-auto' : ''}`}
      style={!isInline ? { paddingBottom: `calc(2rem + ${hostBottomInset}px)` } : undefined}
    >
      <PieChart
        slices={data.slices}
        totalHours={data.totalHours}
        weekStart={data.weekStart}
        weekEnd={data.weekEnd}
        semanticTargetLabel={data.semanticTargetLabel}
      />
    </main>
  )
}
```

**Critical placement rule:** The `return <></>` guard must be INSIDE the
`isPieChartData(data)` block and BEFORE the dashboard fallthrough. The dashboard
branch (`const dashboardData = data as DashboardData | null`) must only be
reached when `isPieChartData` is false. If the guard is placed anywhere else,
the dashboard will still render for call 2b.

Use `return <></>` rather than `return null` — React-safe, avoids layout
wrapper issues.

## What does NOT change

- No MCP server changes
- No backend changes
- No DB changes
- No tool schema changes
- No structuredContent shape changes
- No compliance impact

## After the change

Rebuild the widget and copy to widgets directory:

```bash
cd mcp_server/priority_guardian/widget-react
npm run build
cp dist/pg-dashboard.html ../widgets/pg-dashboard-v12.html
```

## Smoke tests

1. Ask "break down P1":
   - Zero intermediate widgets rendered
   - One widget appears with P1 exploded into subcategories
2. Ask for a plain weekly report (call 1) — widget renders normally with full pie chart
3. Ask to break down `other` — confirm/other flow still renders correctly

## Read `OPERATIONS_PREDEPLOY.md` before deploying
