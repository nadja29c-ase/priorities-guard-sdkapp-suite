# PG Increment 06: Weekly Report + Snapshot Pipeline

## Objective

After this increment: users can generate a weekly report in conversation, PG persists weekly snapshots for completed weeks (with backfill for missed weeks), running aggregates update on `pg_priorities`, and the dashboard displays streak count on flexible priority cards.

This increment connects five pieces: two new database tables (`pg_weekly_snapshots` + `pg_weekly_overview`), a new MCP tool (`get_weekly_report`), aggregate updates on the existing `pg_priorities` table, and a small widget change to render streak count.

---

## Product Context

Priority Guardian shows freelancers the gap between intention and reality. The weekly report is the core accountability loop — it surfaces what actually happened against what was declared, using calendar data. See `claude increments/PRIORITY_GUARDIAN/PG_context.md` for the full product briefing.

The report serves two audiences in one call:
- **The LLM** receives structured data to narrate the weekly reflection conversationally. The LLM does semantic grouping of non-priority events live in conversation — this is ephemeral in this increment (Increment 07 adds persistence via a separate tool).
- **The backend** persists the deterministic, keyword-matched data as a snapshot for week-over-week comparison.

---

## What Exists (read these files to understand the current state)

### Database
- `backend/apps/priority_guardian/db_models.py` — `PgPriority` has three placeholder aggregate columns: `streak_count` (default 0), `avg_hours_week` (nullable), `total_hours_invested` (default 0). Nothing writes to them yet.
- `PgDeliverable` — deliverables with binary `done` status, CASCADE delete with parent priority.

### Calendar Pipeline (Increment 05)
- `backend/apps/priority_guardian/services/calendar_service.py` — `compute_time_allocation()` fetches Google Calendar events for the current week, matches P1/P2/P3 keywords, returns hours per keyword. `compute_allocation_from_events()` is the pure computation function (no I/O). The weekly report builds on both.
- `backend/apps/priority_guardian/services/calendar_service.py` — `compute_week_boundaries()` computes Monday-to-Monday boundaries in user's timezone. Reusable for arbitrary weeks, not just current week.
- `backend/apps/priority_guardian/routers/calendar_router.py` — `GET /api/priority-guardian/calendar/time-allocation` endpoint.
- `backend/core/google_calendar.py` — `list_events()` fetches paginated events from Google Calendar API. Returns full event objects including `summary` (title) and `description`.
- `backend/core/google_calendar.py` — `get_user_timezone()` fetches user's IANA timezone.
- `backend/core/google_token_management.py` — `ensure_valid_access_token()`.
- `backend/apps/priority_guardian/pg_config.py` — `GOOGLE_CALENDAR_SCOPE` = `calendar.events.readonly` + `calendar.settings.readonly`. Both `summary` and `description` fields are available.

### MCP Server
- `mcp_server/priority_guardian/tools/get_priorities.py` — parallel fetches priorities + calendar data, merges `weeklyHourActual` per priority. This is the widget mount tool.
- `mcp_server/priority_guardian/tools/__init__.py` — explicit `TOOL_REGISTRY` dict. New tools must be added here.
- `mcp_server/priority_guardian/tools/base.py` — `ToolDefinition` dataclass, `ToolUsageError`.
- `mcp_server/priority_guardian/http_client.py` — `backend_get()`, `backend_post()` for backend communication.
- `doc/MCP Server Implementation Standard.md` — canonical dispatcher pattern, handler signature, error categories. All tools MUST follow this standard.

### Backend Priorities Response
- `backend/apps/priority_guardian/routers/priorities_router.py` — `build_priorities_response()` builds the canonical response. Currently does NOT include `streak_count`, `avg_hours_week`, or `total_hours_invested` in the serialized output.

### Widget
- `mcp_server/priority_guardian/widget-react/src/types.ts` — `Priority` interface. Does not have `streakCount`.
- `mcp_server/priority_guardian/widget-react/src/components/FlexibleCard.tsx` — renders flexible priority cards. No streak display.
- `mcp_server/priority_guardian/tools/get_priorities.py` — `_normalize_priority()` maps backend snake_case to camelCase. Does not map `streak_count`.

### Architecture References (read, don't import as rules)
- `Shared_Backend_Architecture_Design.pdf` (project knowledge) — shared backend conventions, app isolation patterns.
- `Data_Retention_Strategy_Shared_Backend.pdf` (project knowledge) — retention policies per table type.
- `doc/ADR_001_running_aggregates_on_pg_priorities.md` — explains why aggregates live on the priority row, streak definition, display decisions, semantic grouping strategy, backfill logic.

---

## ADR-001 Decisions (binding for this increment)

These decisions are documented in `doc/ADR_001_running_aggregates_on_pg_priorities.md`:

**Streak definition:** Consecutive weeks where `actual_hours > 0` for the priority. Binary — did you invest any time at all. Not tied to `weekly_hour_target`. Hours > 0 = streak continues. Hours = 0 = streak resets to 0.

**Display decisions:**
| Column | Dashboard card | Weekly report |
|--------|---------------|---------------|
| `streak_count` | Yes — FlexibleCard | Yes |
| `avg_hours_week` | No — too noisy | Yes |
| `total_hours_invested` | No | Yes |

**Semantic grouping:** Stored on separate `pg_weekly_overview` table (one row per user per week), NOT on `pg_weekly_snapshots`. Semantic grouping is a user-week-level fact, not a priority-week-level fact. The `pg_weekly_overview` table is created in this increment, populated by Increment 07.

**Backfill:** `get_weekly_report` backfills missing intermediate weeks before saving the requested week. Prevents streak breaks from missed reviews.

---

## Part A: Database — `pg_weekly_snapshots` Table

### New Table: `pg_weekly_snapshots`

Stores one snapshot per priority per week. The snapshot captures the deterministic, keyword-matched data at the time of finalization.

**Columns (from Progress Tracking V1.0 spec, Section 8.3):**

- `id` — UUID primary key, server-generated
- `priority_id` — FK to `pg_priorities.id`, CASCADE delete
- `user_id` — FK to `core_users.id`, CASCADE delete (denormalized for query efficiency — avoids join through `pg_priorities` when loading user's snapshots)
- `week_start` — DATE, Monday of the reporting week (e.g., 2026-02-09). Combined with `priority_id`, forms the natural unique key.
- `week_end` — DATE, Sunday of the reporting week (e.g., 2026-02-15). Stored for convenience, always `week_start + 6 days`.
- `actual_hours` — NUMERIC(6,2), keyword-matched hours for this priority this week
- `event_count` — INTEGER, number of keyword-matched events
- **Deadline-specific** (nullable, only populated for deadline priorities):
  - `deadline_date` — DATE, the priority's deadline at time of snapshot
  - `days_remaining` — INTEGER, calendar days from `week_end` to `deadline_date`
  - `deliverables_completed` — INTEGER, count of `done=true` deliverables
  - `deliverables_total` — INTEGER, total deliverable count
  - `pacing_status` — VARCHAR(20), one of: 'on_track', 'behind', 'ahead', 'completed'
- **Flexible-specific** (nullable, only populated for flexible priorities):
  - `target_hours` — NUMERIC(6,2), the `weekly_hour_target` at time of snapshot
  - `flex_status` — VARCHAR(20), one of: 'ahead', 'on_track', 'behind' (based on 80%/110% thresholds from spec Section 10)
  - `streak_at_snapshot` — INTEGER, the `streak_count` value AFTER this week's update (snapshot records the result, not the input)
- `created_at` — TIMESTAMP WITH TIME ZONE, when snapshot was saved

**Constraints:**
- Unique: `(priority_id, week_start)` — one snapshot per priority per week
- Check: `actual_hours >= 0`
- Check: `event_count >= 0`

**Indexes:**
- `(user_id, week_start DESC)` — for loading recent snapshots by user
- `(priority_id, week_start DESC)` — for loading history of a specific priority

**Retention:** 90 days minimum after priority retirement. CASCADE delete with parent priority handles active deletion. A future cleanup job will handle post-retirement expiry (not in this increment).

### New Table: `pg_weekly_overview`

Stores user-week-level data that does not belong on per-priority snapshot rows. Created now, populated by Increment 07.

Semantic grouping describes all non-priority calendar time for a user in a specific week. Its natural key is `(user_id, week_start)` — it does NOT describe a priority or a priority-week relationship. Storing it on `pg_weekly_snapshots` (keyed by `priority_id, week_start`) would duplicate the same fact across 1-3 rows per week with no schema-enforced invariant preventing divergence. See ADR-001 for full rationale.

**Columns:**

- `id` — UUID primary key, server-generated
- `user_id` — FK to `core_users.id`, CASCADE delete
- `week_start` — DATE, Monday of the reporting week
- `semantic_grouping` — JSONB, nullable. Always `null` in this increment. Populated by Increment 07's `save_semantic_grouping` tool. Shape: `[{"category": "...", "hours": N, "event_count": N}, ...]`
- `created_at` — TIMESTAMP WITH TIME ZONE
- `updated_at` — TIMESTAMP WITH TIME ZONE

**Constraints:**
- UNIQUE: `(user_id, week_start)` — one overview per user per week. Invariant enforced by schema.

**Retention:** Same lifecycle as snapshots. CASCADE delete from `core_users` handles user deletion.

### Alembic Migration

Single migration file following existing naming convention (see `backend/alembic/versions/` for pattern). The migration creates BOTH tables (`pg_weekly_snapshots` + `pg_weekly_overview`), constraints, and indexes. No data backfill needed — both tables start empty.

---

## Part B: Backend — Weekly Report Endpoint + Snapshot Persistence

### New Endpoint: `GET /api/priority-guardian/weekly-report`

**Purpose:** Compute the weekly report data. For the current (incomplete) week, returns live data without persisting. For a completed past week, persists the snapshot + updates aggregates (with backfill for any missing intermediate weeks), then returns the report.

**Request:** No body. `X-User-ID` header for user identification. Optional query parameter `week_start` (ISO date, must be a Monday) to request a specific past week. Default: current week.

**Behavioral Split:**

A week is "complete" when `now() >= next Monday 00:00` in the user's timezone.

- **Current week (incomplete):** Compute live calendar data. Return report. Do NOT persist snapshot. Do NOT update aggregates.
- **Completed week (past):** Check if snapshot exists for `(priority_id, week_start)`. If snapshot exists: return existing snapshot data (idempotent). If no snapshot: backfill any missing intermediate weeks first, then persist this week's snapshot + update aggregates.

**Why not overwrite past snapshots:** Once a week is finalized, the aggregates were updated based on that snapshot's data. Overwriting without recalculating all downstream aggregates creates inconsistency. Immutable-after-finalization is simpler and safer.

### Backfill Logic

When saving a snapshot for week Y, the endpoint checks: what is the most recent existing snapshot for this user? If the gap between that snapshot's `week_start` and week Y is more than one week, intermediate weeks need backfilling.

For each missing week (in chronological order):
1. Compute week boundaries for that week
2. Fetch calendar events from Google for that date range
3. Compute per-priority hours via `compute_allocation_from_events()`
4. INSERT snapshot row + UPDATE aggregates on `pg_priorities`

All backfilled weeks are persisted in a single transaction with the requested week.

**Edge cases:**
- First report ever (no previous snapshots): no backfill needed, just save.
- User created priorities 3 weeks ago, never reviewed: backfill all 3 weeks.
- Backfill cap: maximum 12 weeks backfill (one checkpoint cycle). If the gap is larger, backfill the most recent 12 weeks and log a warning. This prevents a single request from making 50+ Google API calls.
- Gap > 12 weeks: streak resets to 0 at the start of the backfill window. The 12 backfilled weeks build streak from scratch. This is correct behavior — a 30-week absence means the streak IS zero. The backfill captures recent work only. The response should include a flag (e.g., `backfill_truncated: true`) so the LLM can mention that older weeks were not captured.
- **Aggregate consistency under truncation:** When gap > 12, `total_hours_invested` and `avg_hours_week` only reflect hours from backfilled snapshots — not the user's true lifetime. This is correct. These aggregates track "hours the system has recorded," not "hours the user actually worked." No snapshots existed before the backfill window, so there is no data to count. Do NOT attempt to estimate or infer pre-cap hours.

**Response shape:**

```json
{
  "success": true,
  "data": {
    "week_start": "2026-02-09",
    "week_end": "2026-02-15",
    "is_current_week": false,
    "snapshot_saved": true,
    "weeks_backfilled": 1,
    "priorities": [
      {
        "id": "uuid",
        "name": "Marketing Site Launch",
        "type": "deadline",
        "calendar_keyword": "P1",
        "actual_hours": 10.5,
        "event_count": 6,
        "deadline_date": "2026-03-15",
        "days_remaining": 27,
        "deliverables_completed": 3,
        "deliverables_total": 5,
        "pacing_status": "on_track",
        "previous_week": {
          "actual_hours": 8.0,
          "event_count": 5,
          "delta_hours": 2.5
        }
      },
      {
        "id": "uuid",
        "name": "LinkedIn Presence",
        "type": "flexible",
        "calendar_keyword": "P2",
        "actual_hours": 3.0,
        "event_count": 2,
        "target_hours": 5.0,
        "flex_status": "behind",
        "streak_count": 4,
        "avg_hours_week": 4.2,
        "total_hours_invested": 47.0,
        "previous_week": {
          "actual_hours": 5.5,
          "event_count": 3,
          "delta_hours": -2.5
        }
      }
    ],
    "time_allocation": {
      "total_tracked_hours": 31.75,
      "keywords": {
        "P1": { "hours": 10.5, "event_count": 6 },
        "P2": { "hours": 3.0, "event_count": 2 },
        "P3": { "hours": 0.0, "event_count": 0 }
      },
      "other_hours": 18.25
    },
    "all_events": [
      {
        "title": "P1 Design review",
        "description": "Review landing page mockups with design team",
        "start": "2026-02-10T10:00:00+01:00",
        "end": "2026-02-10T11:30:00+01:00",
        "matched_keywords": ["P1"]
      }
    ]
  }
}
```

**`previous_week`:** Loaded from `pg_weekly_snapshots` for the week immediately before the requested week. If no snapshot exists (first report ever), `previous_week` is `null`. The `delta_hours` is `current_actual_hours - previous_actual_hours`.

**`all_events`:** The full list of non-declined, non-cancelled, non-all-day events for the week. Includes event title (`summary`) AND description for richer LLM semantic grouping. No attendees (PII minimization). Matched keywords included per event so the LLM knows which are priority vs non-priority. These events are NOT persisted — they flow to the LLM for conversational narration only.

### Snapshot Persistence Logic (within the weekly-report endpoint)

When persisting a snapshot for a completed week, for each active priority:

1. **INSERT into `pg_weekly_snapshots`:** One row per priority with the computed data.

2. **UPDATE `pg_priorities` aggregates:** In the same transaction:
   - `total_hours_invested += this_week_actual_hours`
   - `streak_count`: if `this_week_actual_hours > 0` → `streak_count + 1`. If `this_week_actual_hours == 0` → `0`.
   - `avg_hours_week`: query all snapshots for this priority since last checkpoint (or since creation if no checkpoint). Compute average of `actual_hours`. This is the only query within the write path — acceptable because it runs once per week per priority and the snapshot count is bounded (~12 weeks max between checkpoints). **Note:** Checkpoint is not implemented yet. Until it ships, average ALL snapshots for the priority. Do not pre-optimize for checkpoint scoping.

3. **Guard: retired priorities.** Two layers of defense:
   - **Application level:** The Python loop skips priorities with `status = 'retired'`.
   - **SQL level:** The UPDATE query for aggregates must include `AND status = 'active'` in the WHERE clause. This prevents race conditions where a priority is retired between the Python check and the SQL execution. If the UPDATE affects 0 rows, that's expected — log it, don't fail.

4. **Atomicity:** All INSERTs + UPDATEs (including backfill) in one database transaction. If any fail, rollback everything. Partial snapshot state is worse than no snapshot.

### New Service Module

The computation logic for the weekly report lives in a service module, not in the router. The router handles HTTP concerns (request parsing, response serialization, error mapping). The service handles business logic (calendar data computation, snapshot persistence, aggregate updates, backfill).

**Reuse from Increment 05:** The existing `calendar_service.py` — specifically `compute_allocation_from_events()` — computes per-keyword hours. The weekly report service calls this, then enriches with per-priority data, previous-week comparison, and event list for LLM grouping. `compute_week_boundaries()` needs to be generalized to accept an arbitrary Monday date, not just compute the current week.

### Pacing Status Computation

**Deadline priorities — `pacing_status`:**
- No deliverables → always `'on_track'` (no tracking mechanism beyond hours)
- With deliverables: `completion_ratio = completed / total`. `time_ratio = elapsed_days / total_days` (from priority `created_at` to `deadline`). If `completion_ratio >= 1.0` → `'completed'`. If `completion_ratio >= time_ratio` → `'ahead'`. If `completion_ratio >= time_ratio * 0.8` → `'on_track'`. Else → `'behind'`.

**Flexible priorities — `flex_status`:**
- From Progress Tracking spec Section 10: 80%/110% thresholds.
- `actual_hours >= target * 1.1` → `'ahead'`
- `actual_hours >= target * 0.8` → `'on_track'`
- `actual_hours < target * 0.8` → `'behind'`

---

## Part C: MCP Tool — `get_weekly_report`

### Tool Definition

- **Name:** `get_weekly_report`
- **Description:** Goal-oriented description explaining the value: helps the user see their weekly time allocation against declared priorities, with week-over-week comparison. The LLM uses this to narrate the weekly reflection.
- **Input Schema:** Optional `week_start` parameter (ISO date string, must be a Monday). Default: current week.
- **Required Scopes:** `["pg.access"]`
- **Read-only hint:** `false` — can persist snapshots and update aggregates
- **Destructive hint:** `false` — snapshot save is additive
- **Open world hint:** `true` — calls Google Calendar API
- **Widget URI:** `null` — this tool produces data for LLM narration, not widget output. (Increment 07 adds a pie chart widget view for semantic grouping.)
- **Widget accessible:** `false` — LLM-only tool. The weekly report is a conversational experience.

### Handler Behavior

The MCP tool handler calls `backend_get("/api/priority-guardian/weekly-report")` (with optional `?week_start=` query param). The response flows to the LLM via `structuredContent` with `assistant_guidance` directing the narration.

**`assistant_guidance` content should direct the LLM to:**
- Narrate the per-priority results conversationally (hours, comparison to last week, status)
- For flexible priorities: mention streak count and pace
- Semantically group the non-priority events from `all_events` based on titles and descriptions into approximate categories (e.g., "Client calls ~8h, Admin ~3h") — this is live LLM analysis, not stored yet
- Frame the total time allocation: priority time vs other time
- If `is_current_week: true`: note that this is a mid-week preview and numbers will change
- If `snapshot_saved: true`: note that this week is now finalized
- If `weeks_backfilled > 0`: briefly mention that previous weeks were also captured
- If first report (no `previous_week` for any priority): welcome framing, explain that comparison data starts next week
- Do NOT repeat raw numbers verbatim — present insights and patterns
- After presenting the report, ask the user if they want to save their time allocation categories for this week (leads to Increment 07's `save_semantic_grouping` flow)

**`content` (text):** Brief human-readable summary (e.g., "Here's your weekly report for Feb 9-15. You invested 13.5 hours across your priorities this week.").

### Registration

Add to `TOOL_REGISTRY` in `mcp_server/priority_guardian/tools/__init__.py`. Add invocation messages to `TOOL_INVOCATION_MESSAGES`.

---

## Part D: Widget — Streak Display on FlexibleCard

### Data Flow Changes

1. **Backend:** `build_priorities_response()` in `priorities_router.py` must include `streak_count` in the serialized priority data.

2. **MCP:** `_normalize_priority()` in `get_priorities.py` must map `streak_count` → `streakCount`.

3. **Widget types:** `Priority` interface in `types.ts` must add `streakCount?: number`.

4. **FlexibleCard:** Display streak count. Only show when `streakCount > 0` (zero streak = no display, avoids dead "0 weeks" noise for new priorities or broken streaks). Visual treatment: small, secondary — this is a supporting signal, not a primary metric. The HourRing remains the dominant visual element.

### Design Constraints

- Follow OpenAI SDK UI design tokens (`mcp_server/priority_guardian/widget-react/docs/SDK_UI_TOKENS.md` and `DESIGN_GUIDELINES.md`)
- Use existing badge/text patterns from FlexibleCard — no new component needed
- Streak is only meaningful for flexible priorities. Deadline priorities do not display streak.

---

## What This Increment Does NOT Include

- Semantic grouping persistence (Increment 07 — `save_semantic_grouping` tool)
- Pie chart widget for time allocation visualization (Increment 07)
- Monthly checkpoint flow (separate increment)
- Priority retirement flow (separate increment)
- Snapshot cleanup job for post-retirement 90-day expiry (future)
- Backend pre-computation of weekly reports via Celery (rejected for v1.0)
- Email delivery of reports
- Widget for displaying the weekly report (report is conversational, not widget-rendered — pie chart comes in Increment 07)

---

## Unit Tests

### `pg_weekly_snapshots` DB Model
- Model creates valid snapshot with all fields populated
- Unique constraint `(priority_id, week_start)` enforced — second INSERT for same priority+week raises IntegrityError
- CASCADE delete: deleting priority cascades to its snapshots
- CASCADE delete: deleting user cascades through priority to snapshots
- Nullable fields: deadline-specific fields are null for flexible priorities and vice versa

### Weekly Report Service — Snapshot Persistence
- Completed week with no existing snapshot → snapshot created, aggregates updated, returns `snapshot_saved: true`
- Completed week with existing snapshot → returns existing data, no overwrite, `snapshot_saved: true` (idempotent)
- Current week → no snapshot created, aggregates not updated, returns `snapshot_saved: false`
- Retired priority → skipped in snapshot loop, no INSERT, no aggregate update
- Transaction atomicity: if one priority's snapshot fails, entire transaction rolls back (no partial state)

### Backfill Logic
- Gap of 1 week → 1 week backfilled before saving requested week
- Gap of 3 weeks → 3 weeks backfilled in chronological order
- No gap (consecutive weeks) → no backfill, direct save
- First report ever → no backfill needed, direct save
- Gap of 15 weeks → capped at 12 weeks backfill, warning logged, `backfill_truncated: true` in response
- Gap > 12 weeks → streak resets to 0 at start of backfill window, builds from scratch within backfilled weeks
- Backfilled snapshots have correct `streak_count` progression (computed sequentially, not in parallel)

### Streak Logic
- First week, 3 hours logged → `streak_count` becomes 1
- Second week, 1 hour logged → `streak_count` becomes 2
- Third week, 0 hours logged → `streak_count` resets to 0
- Fourth week, 5 hours logged → `streak_count` becomes 1 (fresh start)
- 0.01 hours (any positive amount) → streak continues (binary: > 0)
- Backfilled weeks: streak computed sequentially across backfilled weeks

### Average Computation
- 4 snapshots with hours [5, 6, 3, 8] → `avg_hours_week` = 5.50
- Single snapshot with 10 hours → `avg_hours_week` = 10.0
- No snapshots yet (first week) → `avg_hours_week` = value of this week's hours

### Pacing Status
- Deadline priority: 3/5 deliverables done, 60% time elapsed → ahead
- Deadline priority: 1/5 deliverables done, 80% time elapsed → behind
- Deadline priority: 5/5 deliverables done → completed
- Deadline priority: no deliverables → on_track
- Flexible priority: 6h actual, 5h target → ahead (≥ 110%)
- Flexible priority: 4.5h actual, 5h target → on_track (≥ 80%)
- Flexible priority: 3h actual, 5h target → behind (< 80%)

### Previous Week Comparison
- Previous snapshot exists → `delta_hours` computed correctly
- No previous snapshot (first report) → `previous_week` is null

### Event Data for LLM
- `all_events` includes event `title` (summary) AND `description`
- Declined events excluded
- Cancelled events excluded
- All-day events excluded
- `matched_keywords` correctly populated per event

### MCP Tool Handler
- Successful report → `CallToolResult` with `structuredContent` containing report data + `assistant_guidance`
- Backend returns `is_current_week: true` → guidance mentions mid-week preview
- Backend returns `snapshot_saved: true` → guidance mentions finalization
- Backend returns `weeks_backfilled > 0` → guidance mentions backfill
- Backend returns error → `isError=True` with user-facing message
- Invalid `week_start` (not a Monday) → `ToolUsageError`

### Widget — Streak Display
- `streakCount` of 5 → renders streak indicator
- `streakCount` of 0 → no streak indicator rendered
- `streakCount` undefined/null → no streak indicator rendered
- Deadline priority → no streak indicator regardless of value

---

## Integration Tests

### Full Stack: Weekly Report Flow
- Create user with Google connection + 2 active priorities (1 deadline, 1 flexible) → mock Google Calendar API with keyword-matched events → call `GET /api/priority-guardian/weekly-report` for a completed past week → verify: snapshot rows created for both priorities, `streak_count` updated on flexible priority, response contains `previous_week: null` (first report), `snapshot_saved: true`

### Snapshot Idempotency
- Call weekly report twice for the same completed week → second call returns same data, no duplicate snapshot rows, aggregates unchanged

### Backfill Integration
- Create user with no snapshots, request report for 3 weeks after priority creation → verify 3 snapshot rows exist (2 backfilled + 1 requested), streaks computed sequentially, Google Calendar API called 3 times (once per week)

### Streak Across Weeks
- Create snapshots for weeks 1, 2, 3 with hours [5, 3, 0] → verify `streak_count` is 2 after week 2, then 0 after week 3

### Dashboard Reflects Aggregates
- After snapshot saved → `GET /api/priority-guardian/priorities` response includes updated `streak_count` → MCP `get_priorities` returns `streakCount` in normalized response

### Calendar Failure Graceful Degradation
- Google Calendar API fails → weekly report endpoint returns appropriate error (502/503) → MCP tool returns `isError=True` with user-facing message

---

## Production Readiness (Increment Context)

### Scalability
- Weekly report generates 1-2 Google Calendar API calls per invocation (timezone + events). Backfill adds N additional event fetches (capped at 12).
- Snapshot persistence: 1-3 INSERT + 1-3 UPDATE per week per finalization. Negligible DB load.
- `avg_hours_week` recomputation queries ~4-12 snapshot rows per priority. Bounded by checkpoint cycle length.
- Backfill cap (12 weeks) prevents runaway API usage.

### GDPR / Data Retention
- `pg_weekly_snapshots` stores hours, event counts, dates, statuses. No event titles, descriptions, or attendee data. No PII by design.
- `pg_weekly_overview` stores only user-confirmed category abstractions ("Client calls") — no raw event data. No PII.
- `all_events` in the response contains event titles and descriptions — these flow to the LLM for semantic grouping but are NOT persisted. Ephemeral in this increment.
- Snapshot retention: 90 days post-retirement (matching Data Retention Strategy). Cleanup job is a future increment.
- User deletion: CASCADE from `core_users` → `pg_priorities` → `pg_weekly_snapshots`, and CASCADE from `core_users` → `pg_weekly_overview`. Existing offboarding endpoint covers this.

### OpenAI SDK Compliance
- New MCP tool follows all compliance requirements from `compliance_master_FINAL.md`
- Tool annotations (readOnlyHint, destructiveHint, openWorldHint) set correctly
- Required scopes declared (`pg.access`)
- Error responses follow MCP standard (isError, text content, structured meta)

### Load Behavior
- Weekly report is called once per week per user (intentional cadence). Not a hot path.
- Snapshot persistence + backfill adds ~50-500ms to the response depending on gap size. Acceptable for a weekly operation.
- Dashboard widget mount unaffected — `get_priorities` adds `streak_count` to existing query, zero additional DB calls.

---

## Validation Criteria (Definition of Done)

1. `pg_weekly_snapshots` table created via Alembic migration (no semantic grouping column — that lives on `pg_weekly_overview`)
2. `pg_weekly_overview` table created in same migration with `semantic_grouping` JSONB column (nullable), UNIQUE(user_id, week_start)
3. `GET /api/priority-guardian/weekly-report` returns correct report data with per-priority breakdown
4. `all_events` includes event title AND description
5. Completed week → snapshot persisted + aggregates updated in single transaction
6. Current week → no persistence, live data only
7. Existing snapshot for completed week → idempotent (no overwrite)
8. Backfill: missing intermediate weeks automatically filled before saving requested week
9. Backfill capped at 12 weeks
10. Streak logic: hours > 0 = continue, hours = 0 = reset
11. `get_weekly_report` MCP tool registered, authenticated, returns `structuredContent` with `assistant_guidance`
12. `get_priorities` response includes `streak_count` → MCP normalizes to `streakCount` → widget type updated
13. FlexibleCard renders streak when `streakCount > 0`
14. All unit tests pass
15. All integration tests pass
16. Deployed to Render and verifiable via MCP Inspector
