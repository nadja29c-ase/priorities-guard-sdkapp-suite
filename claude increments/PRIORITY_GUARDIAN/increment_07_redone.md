# PG Increment 07: Semantic Grouping + Time Allocation Pie Chart

## Objective

After this increment: users can discuss their non-priority time allocation with the LLM, correct misinterpretations, and save finalized semantic groupings to their weekly snapshot. A pie chart widget view visualizes the full week's time allocation — priorities as deterministic slices, non-priority time exploded into user-confirmed semantic categories.

---

## Dependency

**Requires Increment 06 complete.** This increment builds on:
- `pg_weekly_overview` table with nullable `semantic_grouping` JSONB column (created in Inc 06, always `null`)
- `pg_weekly_snapshots` table (per-priority hours, used for priority slices in pie chart)
- `get_weekly_report` MCP tool (returns `all_events` with titles + descriptions)
- The conversational weekly report flow (LLM narrates, proposes groupings)

---

## Product Context

The weekly report (Increment 06) shows the user their numbers — hours per priority, streaks, week-over-week comparison. But numbers alone don't explain *why* priorities got the time they did. The user's non-priority time is a black box labeled "other: 18.25h."

Semantic grouping breaks that black box open. The LLM proposes categories based on event titles and descriptions. The user discusses and corrects them. The finalized groupings persist on the snapshot and render as a pie chart showing the full picture: priorities + everything else, one visual.

This is the reflection layer. The coaching value is in the conversation — the user actively interprets their time rather than passively reading a report.

---

## What Exists After Increment 06

- `pg_weekly_overview` table with `semantic_grouping` JSONB column (nullable, always `null`), UNIQUE(user_id, week_start)
- `pg_weekly_snapshots` table with per-priority hours, counts, status (no semantic grouping — that’s on `pg_weekly_overview`)
- `get_weekly_report` tool returns `all_events` with `title` (summary) and `description` per event
- LLM narrates the weekly report including proposed semantic groupings of non-priority events
- Snapshots persist deterministic data (hours, counts, status, aggregates)
- `assistant_guidance` in `get_weekly_report` already tells the LLM to propose semantic groupings and ask if the user wants to save them

---

## Part A: MCP Tool — `save_semantic_grouping`

### Tool Definition

- **Name:** `save_semantic_grouping`
- **Description:** Goal-oriented: saves the user's confirmed time allocation categories to their weekly snapshot, enabling a visual breakdown of where their entire week went. Called after the user has reviewed and optionally corrected the LLM's proposed groupings during the weekly report conversation.
- **Input Schema:**
  ```json
  {
    "type": "object",
    "properties": {
      "week_start": {
        "type": "string",
        "description": "Monday of the week being saved (ISO date, e.g., '2026-02-09'). Must match an existing snapshot."
      },
      "groupings": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "category": { "type": "string" },
            "hours": { "type": "number" },
            "event_count": { "type": "integer" }
          },
          "required": ["category", "hours", "event_count"]
        },
        "description": "Finalized non-priority time categories confirmed by the user."
      }
    },
    "required": ["week_start", "groupings"]
  }
  ```
- **Required Scopes:** `["pg.access"]`
- **Read-only hint:** `false` — writes to snapshot
- **Destructive hint:** `false` — enriches existing data, doesn't delete
- **Open world hint:** `false` — no external API calls
- **Widget URI:** The pie chart widget URI (this tool's response renders the pie chart)
- **Widget accessible:** `true` — the pie chart is a widget view

### Handler Behavior

The MCP tool handler calls `backend_post("/api/priority-guardian/weekly-report/semantic-grouping", json=payload)`. The backend validates that snapshots exist for this `week_start` + user (proving the week was reported), then UPSERT into `pg_weekly_overview` to set the `semantic_grouping` JSONB.

**On success:** Returns `structuredContent` with the full time allocation data (priorities from snapshots + semantic categories from the just-saved overview) formatted for the pie chart widget, plus `assistant_guidance` confirming the save.

**`assistant_guidance` on success:** Brief confirmation. Do not re-narrate the entire report. Something like "Your time allocation categories have been saved for this week" is sufficient.

**Error cases:**
- No snapshot exists for `week_start` → `ToolUsageError`: "No weekly report found for this week. Generate your weekly report first."
- Invalid `week_start` (not a Monday) → `ToolUsageError`
- Empty groupings array → `ToolUsageError`
- `sum(grouping hours) > other_hours + 0.5` → 400 error: grouping hours exceed non-priority time. The 0.5h epsilon accounts for rounding differences between LLM estimates and precise calendar math. This prevents the LLM from hallucinating impossible hours.
- `other_hours <= 0.01` with non-empty groupings → 400 error: no non-priority time to categorize.
- Per-category validation: `hours >= 0`, `event_count >= 0`, `category.strip()` non-empty. Reject if any fail.
- Duplicate category names within payload → 400 error. Categories must be unique (case-insensitive comparison after strip).

### Overwrite Behavior

If `semantic_grouping` is already populated on the `pg_weekly_overview` row, overwrite it. The user may want to refine their categories across multiple conversations. Last write wins. `updated_at` timestamp reflects the most recent save.

---

## Part B: Backend — Semantic Grouping Endpoint

### New Endpoint: `POST /api/priority-guardian/weekly-report/semantic-grouping`

**Purpose:** Attach semantic grouping data to an existing weekly snapshot.

**Request:**
```json
{
  "week_start": "2026-02-09",
  "groupings": [
    {"category": "Client calls", "hours": 8.0, "event_count": 5},
    {"category": "Tax & accounting", "hours": 4.0, "event_count": 3},
    {"category": "Admin", "hours": 3.25, "event_count": 4}
  ]
}
```

**Behavior:**
1. Validate `week_start` is a Monday
2. Verify at least one snapshot row exists for this user + `week_start` (proves the week was reported)
3. If no snapshots found → 404
4. UPSERT into `pg_weekly_overview`: if row exists for `(user_id, week_start)`, update `semantic_grouping` + `updated_at`. If not, INSERT new row. This handles both first-time save and overwrite cleanly.
5. Load priority hours from `pg_weekly_snapshots` for this user + week
6. Return the complete time allocation data (priority slices from snapshots + semantic slices from overview) for the pie chart

**Response:**
```json
{
  "success": true,
  "data": {
    "week_start": "2026-02-09",
    "week_end": "2026-02-15",
    "slices": [
      {"label": "P1 — Marketing Site Launch", "hours": 10.5, "type": "priority", "keyword": "P1"},
      {"label": "P2 — LinkedIn Presence", "hours": 3.0, "type": "priority", "keyword": "P2"},
      {"label": "Client calls", "hours": 8.0, "type": "semantic", "event_count": 5},
      {"label": "Tax & accounting", "hours": 4.0, "type": "semantic", "event_count": 3},
      {"label": "Admin", "hours": 3.25, "type": "semantic", "event_count": 4}
    ],
    "total_hours": 28.75
  }
}
```

The `slices` array is pre-formatted for the pie chart. Priority slices come from the snapshot's per-priority `actual_hours`. Semantic slices come from the just-saved grouping. The `type` field distinguishes them for visual treatment (priority slices get keyword colors, semantic slices get neutral/secondary colors).

**Incomplete grouping is allowed.** The user may categorize 12h out of 18h non-priority time. The remaining 6h simply doesn't appear as a semantic slice. `total_hours` in the response = sum of priority hours + sum of categorized semantic hours, which may be less than total calendar hours. The pie chart shows what was categorized, not the full calendar.

**Note on scope:** Semantic grouping is about the USER's non-priority time, not about individual priorities. It lives on `pg_weekly_overview` (one row per user per week), completely separate from per-priority `pg_weekly_snapshots`. This avoids duplicating the same JSONB across multiple snapshot rows and enforces the single-source-of-truth invariant via UNIQUE(user_id, week_start). See ADR-001 for full rationale.

---

## Part C: Widget — Pie Chart View

### Widget Architecture

The pie chart is a separate view within the existing PG widget, not visible by default. It renders when `save_semantic_grouping` returns data via `structuredContent`.

**When the pie chart renders:**
- `save_semantic_grouping` tool returns with `widget_uri` → widget receives the `slices` data (priority hours from `pg_weekly_snapshots` + semantic categories from `pg_weekly_overview`) → renders pie chart

**Visual Design:**
- Pie chart showing the full week's time allocation
- Priority slices: use existing priority colors (P1, P2, P3 from the design system)
- Semantic category slices: neutral/secondary palette — visually distinct from priority colors
- Each slice shows: label + hours + percentage of total
- Legend below or beside the chart
- Total hours displayed in the center or as a header

**Not visible by default:** The dashboard (FlexibleCard view) remains the default widget view. The pie chart only appears when `save_semantic_grouping` returns data. The user navigates back to the dashboard via normal widget interaction.

### Data Shape for Widget

The `structuredContent.data` from the `save_semantic_grouping` tool response provides the `slices` array directly. The widget renders this without additional computation.

```typescript
interface PieSlice {
  label: string
  hours: number
  type: 'priority' | 'semantic'
  keyword?: string      // P1/P2/P3 for priority slices
  eventCount?: number   // for semantic slices
}

interface PieChartData {
  weekStart: string
  weekEnd: string
  slices: PieSlice[]
  totalHours: number
}
```

### Design Constraints

- Follow OpenAI SDK UI design tokens
- Use existing color system — priority colors from the design system, semantic categories in neutral palette
- Responsive: must render well in both inline and pip display modes
- Accessible: proper ARIA labels on chart segments
- No external charting library unless already in the widget's dependency tree — prefer CSS/SVG pie chart or a lightweight solution

---

## What This Increment Does NOT Include

- Retroactive semantic grouping for snapshots created before this increment (old snapshots stay `null`)
- Automatic semantic grouping without user review (grouping always flows through conversation)
- Per-priority semantic sub-categories (e.g., "within P1: 4h design, 6h code") — this is the within-priority breakdown from the spec, a future enhancement
- Week-over-week semantic grouping comparison ("you spent 8h on client calls this week vs 12h last week") — requires stable category names across weeks, a future challenge
- Category suggestions based on past groupings — future UX improvement

---

## Unit Tests

### `save_semantic_grouping` MCP Tool Handler
- Valid groupings + existing snapshot → `CallToolResult` with `structuredContent` containing pie chart data
- No snapshot for `week_start` → `ToolUsageError` with "generate your weekly report first" message
- Invalid `week_start` (not a Monday) → `ToolUsageError`
- Empty groupings array → `ToolUsageError`
- Overwrite: grouping already exists → replaced with new data, `updated_at` refreshed
- Grouping hours exceed `other_hours + 0.5` → error returned (hallucination guard)
- Grouping hours within epsilon of `other_hours` → accepted
- `other_hours` is 0 with non-empty groupings → error
- Category with negative hours → error
- Category with empty name (whitespace only) → error
- Duplicate category names (case-insensitive) → error
- Category with `event_count < 0` → error

### Backend Endpoint
- Valid request + existing snapshot → 200 with `slices` array
- No snapshot for week → 404
- `semantic_grouping` written to `pg_weekly_overview` (UPSERT), NOT to snapshot rows
- `pg_weekly_overview` row has correct `user_id`, `week_start`, and `semantic_grouping` JSONB
- `slices` response includes both priority slices (from `pg_weekly_snapshots` `actual_hours`) and semantic slices (from `pg_weekly_overview`)
- Priority slices correctly labeled with priority name and keyword
- `total_hours` = sum of all slice hours
- UNIQUE(user_id, week_start) constraint prevents duplicate overview rows

### JSONB Storage on `pg_weekly_overview`
- Valid grouping stored and retrievable as structured data
- UPSERT: first save creates row, second save updates existing row
- Null → populated transition works
- Populated → different populated transition works (overwrite)

### Widget — Pie Chart Rendering
- `slices` with 3 priority + 4 semantic categories → renders 7 slices
- Priority slices use priority keyword colors
- Semantic slices use neutral palette
- Each slice shows label, hours, percentage
- Total hours displayed
- Empty `slices` → appropriate empty state
- Single slice (only one priority, no semantic) → renders correctly

---

## Integration Tests

### Full Flow: Report → Discussion → Save → Pie Chart
- `get_weekly_report` returns data with `all_events` → LLM proposes groupings → `save_semantic_grouping` called with user-confirmed categories → `pg_weekly_overview` row created with `semantic_grouping` → response joins snapshot priority hours + overview semantic categories → correctly formatted `slices` for pie chart

### Idempotency: Multiple Saves
- Call `save_semantic_grouping` twice with different groupings → second call UPSERTs (overwrites) the `pg_weekly_overview` row → pie chart reflects latest data

### Cross-Increment: Snapshot Without Grouping
- Snapshot created by Inc 06 `get_weekly_report` → no `pg_weekly_overview` row exists (or row exists with `semantic_grouping: null`) → no pie chart available → `save_semantic_grouping` creates/updates overview row → pie chart now renderable

### Data Isolation: Snapshots vs Overview
- `pg_weekly_snapshots` contains NO semantic grouping data — only priority-scoped hours, counts, status
- `pg_weekly_overview` contains semantic grouping — user-week-scoped, one row, one source of truth
- Deleting and re-saving semantic grouping does not affect snapshot rows

---

## Production Readiness (Increment Context)

### Scalability
- `save_semantic_grouping` writes to one `pg_weekly_overview` row (UPSERT). Single row operation. Negligible DB load.
- Pie chart assembly requires one query to `pg_weekly_snapshots` (priority hours) + one read of `pg_weekly_overview` (semantic categories). Two simple queries, no joins required.
- JSONB column size: ~200 bytes for typical grouping (5-8 categories). Well within PostgreSQL JSONB performance bounds.
- Pie chart rendering is client-side. No backend load.

### GDPR / Data Retention
- Semantic grouping stores user-confirmed category labels and hours. These are abstractions ("Client calls", "Admin"), not raw event data. No PII.
- Categories are user-confirmed — the user explicitly approved what gets stored.
- Deletion: CASCADE from `core_users` → `pg_weekly_overview` handles cleanup. Separate from snapshot deletion path but same user deletion trigger.

### OpenAI SDK Compliance
- New MCP tool follows all compliance requirements from `compliance_master_FINAL.md`
- Tool annotations set correctly
- Widget renders using OpenAI SDK design tokens
- Pie chart is accessible (ARIA labels)

### Load Behavior
- `save_semantic_grouping` is called 0-1 times per weekly report (user opt-in). Lighter than the report itself.
- JSONB update is a single-row operation per snapshot. Sub-millisecond.

---

## Validation Criteria (Definition of Done)

1. `save_semantic_grouping` MCP tool registered, authenticated, follows MCP Server Implementation Standard
2. `POST /api/priority-guardian/weekly-report/semantic-grouping` validates input, updates `semantic_grouping` JSONB on snapshot rows
3. Overwrite behavior: subsequent saves replace previous grouping
4. Response includes pre-formatted `slices` array with priority + semantic slices
5. Pie chart widget view renders from `slices` data
6. Priority slices use keyword colors, semantic slices use neutral palette
7. Pie chart shows labels, hours, percentages, total hours
8. Pie chart not visible by default — only appears on `save_semantic_grouping` response
9. All unit tests pass
10. All integration tests pass
11. Deployed to Render and verifiable via MCP Inspector
