# Cleanup: Remove Orphaned Data, Columns, Computation, and Passthrough Code

## Goal

Remove all data, columns, code, and passthrough that is stored or computed but never consumed by any reader. After this cleanup, every database column must have a clear consumer, every computation must feed a display or storage path, and every table must have a descriptive purpose statement.

This is a **deletion-only** task. No new features. No behavioral changes to what the user sees.

---

## Context

The weekly report history feature (browsing past weeks from stored snapshots) has been killed. Several columns on `pg_weekly_snapshots` were written for that future feature and have no reader. Additionally, `avg_hours_week` on `pg_priorities` was replaced by `avg_target_achievement` but never removed. The `pg_weekly_overview` table was created for semantic grouping persistence but is never written to or read by any service code.

---

## What the User Currently Sees (Must Not Change)

**FlexibleCard displays:**
- HourRing (weeklyHourActual vs weeklyHourTarget) — live from Google Calendar
- 🔥 streak badge (streakCount) — from pg_priorities.streak_count
- `~X% of weekly target on avg` (avgTargetAchievement) — from pg_priorities.avg_target_achievement
- `Xh invested total` (totalHoursInvested) — from pg_priorities.total_hours_invested

**DeadlineCard displays:**
- Progress bar (doneCount/totalCount) — from deliverables relationship
- `X of Y done · Nd left` — computed from deliverables + deadline

**Weekly report (pie chart + LLM narration):**
- Live computation from Google Calendar. No change.

---

## Deletion Scope

### A. Drop `pg_weekly_overview` Table

**Reason:** Created in Inc 06 migration for future semantic grouping persistence. No service code imports `PgWeeklyOverview`. No service writes to or reads from this table. Zero rows in production.

**Files:**
- `db_models.py`: Delete entire `PgWeeklyOverview` class. Remove from module docstring.
- Migration: New alembic migration drops the table and its trigger (`trg_pg_weekly_overview_updated_at`).

### B. Drop 7 Orphaned Columns from `pg_weekly_snapshots`

These columns were written during snapshot creation but never read by any consumer. The weekly report computes live from Google Calendar and never queries snapshot history.

| Column | Why orphaned |
|---|---|
| `event_count` | Written but no reader. Dashboard doesn't show event counts from snapshots. |
| `flex_status` | Dashboard shows raw numbers, not categorical labels (ADR #8). Weekly report computes live. |
| `pacing_status` | Same reason as flex_status. |
| `deadline_date` | Snapshot of deadline at time of capture. No weekly history browser exists. |
| `days_remaining` | Same. |
| `deliverables_completed` | Same. |
| `deliverables_total` | Same. |

**Files:**
- `db_models.py` → `PgWeeklySnapshot`: Remove 7 column definitions. Remove `ck_pg_weekly_snapshots_event_count_non_negative` from `__table_args__`.
- Migration: Same new migration drops these columns.

**After cleanup, `PgWeeklySnapshot` retains exactly:**
- `id` (PK)
- `priority_id` (FK → pg_priorities)
- `user_id` (FK → core_users, denormalized)
- `week_start` (date — Monday)
- `week_end` (date — Sunday)
- `actual_hours` (Numeric(6,2) — keyword-matched hours)
- `target_hours` (Numeric(6,2), nullable — weekly_hour_target at snapshot time, flexible only)
- `streak_at_snapshot` (Integer, nullable — streak_count AFTER this week's update)
- `created_at` (DateTime)

### C. Drop `avg_hours_week` from `pg_priorities`

**Reason:** Replaced by `avg_target_achievement`. Computed by `_update_aggregates` but never displayed. FlexibleCard reads `avgTargetAchievement`. Weekly report hardcodes `None`.

**Files:**
- `db_models.py` → `PgPriority`: Remove `avg_hours_week` column definition.
- Migration: Same new migration drops this column.

---

## Code Cleanup (follows from schema changes)

### 1. `snapshot_service.py`

**`_create_snapshots_for_week`:**
- Remove `event_count` from `insert_params`
- Remove the entire deadline-specific block:
  - `insert_params["deadline_date"] = ...`
  - `insert_params["days_remaining"] = ...`
  - `done_count = sum(...)` loop
  - `insert_params["deliverables_completed"] = ...`
  - `insert_params["deliverables_total"] = ...`
  - `insert_params["pacing_status"] = compute_pacing_status(...)` and the else branch
- Remove `insert_params["flex_status"] = compute_flex_status(...)` from the flexible block
- Remove ALL None defaults for deleted columns from the `insert_params` dict. The remaining params should only set fields that exist in the slimmed schema.
- Remove the entire `selectinload(PgPriority.deliverables)` from the priorities query in `_ensure_snapshots_impl` Step 4 — deliverables are no longer needed for snapshot creation. (Deliverables are still loaded in `priorities_router` and `weekly_report_service` for their own purposes.)

**`_update_aggregates`:**
- Remove the `avg_hours_week` AVG query (the `avg_result = await session.execute(select(func.avg(...)))` block)
- Remove `avg_hours_week` from the UPDATE SET clause
- Remove the `avg_hours` bind parameter

**Imports:**
- Remove `compute_flex_status` and `compute_pacing_status` from the import of `weekly_report_service`. These functions remain in `weekly_report_service.py` — they are used by the live weekly report generation. Only the snapshot_service's *calls* to them are removed.

**Docstring:**
- Update module docstring: remove `avg_hours_week` from the aggregates list
- Update `_update_aggregates` docstring to list only: `streak_count`, `total_hours_invested`, `avg_target_achievement`

### 2. `snapshot_router.py`

- Update endpoint docstring: change "Updates running aggregates (streak_count, avg_hours_week, total_hours_invested)" → "Updates running aggregates (streak_count, total_hours_invested, avg_target_achievement)"

### 3. `priorities_router.py`

**`build_priorities_response`:**
- Remove the `avg_hours_week` line: `priority_data["avg_hours_week"] = float(p.avg_hours_week) if p.avg_hours_week is not None else None`

### 4. `get_priorities.py` (MCP tool)

**`_normalize_priority`:**
- Remove `"avgHoursWeek": p.get("avg_hours_week"),`

### 5. `get_weekly_report.py` (MCP tool)

**`_normalize_priority_report`:**
- Remove `result["avgHoursWeek"] = p.get("avg_hours_week")` from the flexible section

### 6. `weekly_report_service.py`

**`generate_weekly_report`:**
- Remove `pdata["avg_hours_week"] = None` from the flexible priority block

### 7. `types.ts` (widget)

- Remove `avgHoursWeek?: number | null` from the `Priority` interface

### 8. `db_models.py` — Docstring and Comment Updates

**Module docstring:** Update the "Currently:" list to:
- `PgPriority`: User's declared priorities with calendar keyword tracking and running aggregates
- `PgDeliverable`: Deliverables associated with deadline-type priorities
- `PgWeeklySnapshot`: Per-priority weekly data point for running aggregate computation

Remove `PgWeeklyOverview` from the list entirely.

**`PgPriority` docstring:**
- Replace "Aggregate columns (streak_count, avg_hours_week, total_hours_invested) are placeholders in Increment 02" with: "Aggregate columns (streak_count, avg_target_achievement, total_hours_invested) are updated by snapshot_service when weekly snapshots are finalized."
- Remove the "Future:" comments on the remaining aggregate columns. They are no longer future — they are active.

**`PgWeeklySnapshot` docstring:** Replace entirely with:
```
Per-priority weekly data point for running aggregate computation.

One row per priority per completed week. Created opportunistically on dashboard
load via ensure_snapshots_up_to_date(). Immutable after creation (INSERT ON
CONFLICT DO NOTHING).

Used exclusively by snapshot_service._update_aggregates() to compute:
- streak_count: from streak_at_snapshot chain
- total_hours_invested: SUM(actual_hours)
- avg_target_achievement: AVG(actual_hours / target_hours * 100)

Not queried directly for display. All consumer-facing data lives on pg_priorities.
```

**Column comments on `PgPriority`:**
- `streak_count`: keep as-is
- `total_hours_invested`: change from "Future: cumulative hours invested" → "Cumulative hours invested across all snapshotted weeks"
- `avg_target_achievement`: keep as-is

---

## Migration

**Single new alembic migration.** Name suggestion: `s9t0u1v2w3x4_cleanup_orphaned_columns.py`

`down_revision` must be `r8m9n0o1p2q3` (the avg_target_achievement migration).

**upgrade():**
1. `DROP TRIGGER IF EXISTS trg_pg_weekly_overview_updated_at ON pg_weekly_overview`
2. `DROP TABLE pg_weekly_overview`
3. Drop 7 columns from `pg_weekly_snapshots`: `event_count`, `flex_status`, `pacing_status`, `deadline_date`, `days_remaining`, `deliverables_completed`, `deliverables_total`
4. Drop constraint: `ck_pg_weekly_snapshots_event_count_non_negative` (may drop automatically with column — use `DROP CONSTRAINT IF EXISTS` defensively)
5. Drop column `avg_hours_week` from `pg_priorities`

**downgrade():** Reverse all operations (recreate table, add columns back). Include the trigger recreation for `pg_weekly_overview`. Use the exact types from the original migration `p6k7l8m9n0o1`.

---

## ADR-001 Updates

**Decision #1:** Remove "avg_hours_week is also stored but currently unused on the dashboard — retained for potential weekly report use." The column no longer exists.

**Decision #3:** Add note: "Table `pg_weekly_overview` was dropped in cleanup migration — semantic grouping persistence deferred indefinitely. Decision retained for historical context."

---

## What NOT to Change

- `compute_flex_status()` and `compute_pacing_status()` in `weekly_report_service.py` — still used by live weekly report
- `is_week_complete()` in `weekly_report_service.py` — still used by snapshot_service
- `weekly_report_router.py` — no changes needed (doesn't reference deleted columns)
- `get_weekly_report.py` MCP tool's `streakCount` and `totalHoursInvested` passthrough — these are hardcoded to 0/0.0 in weekly_report_service but the code path is exercised. Fixing their accuracy is a separate task.
- Widget components (`FlexibleCard.tsx`, `DeadlineCard.tsx`) — no changes needed, they don't reference `avgHoursWeek`
- `_compute_streak()` in snapshot_service — still used, reads `streak_at_snapshot` which is retained
- `check constraint ck_pg_weekly_snapshots_actual_hours_non_negative` — retained (actual_hours is retained)
- `UniqueConstraint uq_pg_weekly_snapshots_priority_week` — retained
- Indexes `idx_pg_weekly_snapshots_user_week` and `idx_pg_weekly_snapshots_priority_week` — retained

---

## Unit Tests

**File: `tests/unit/priority_guardian/test_snapshot_service.py`**

Tests that assert on deleted columns need updating. The test setup that mocks `insert_params` or asserts on snapshot row content must remove references to: `event_count`, `flex_status`, `pacing_status`, `deadline_date`, `days_remaining`, `deliverables_completed`, `deliverables_total`.

Tests for `_update_aggregates` that assert `avg_hours_week` is set must be updated to not assert on that field.

The `selectinload(PgPriority.deliverables)` removal means any test mocking that expects deliverables loading in the snapshot path should be updated.

Do NOT delete tests that verify retained behavior: streak computation, total_hours_invested aggregation, avg_target_achievement computation, idempotency, error handling.

**File: `tests/unit/priority_guardian/test_snapshot_router.py`**

Update any assertions that reference `avg_hours_week` in aggregate descriptions.

**File: `tests/unit/mcp_pg/test_get_priorities_snapshots.py`**

Remove assertions on `avgHoursWeek` field in normalized priority output.

**File: `tests/unit/mcp_pg/test_weekly_report_handler.py`**

Remove assertions on `avgHoursWeek` field in normalized priority report output.

**File: `mcp_server/priority_guardian/widget-react/src/__tests__/App.test.tsx`**

Remove any test data that sets `avgHoursWeek` on priority objects. Should not affect test logic since no component reads it.

---

## Integration Tests

**File: `tests/integration/priority_guardian/test_snapshot_persistence.py`**

This test creates real snapshots against a test database. Update:
- Remove assertions on deleted snapshot columns
- Remove assertions on `avg_hours_week` in priority aggregate checks
- The `cleanup_db` fixture's DELETE order must still delete `pg_weekly_snapshots` before `pg_priorities` (FK constraint). Remove `pg_weekly_overview` from the cleanup since the table no longer exists.

---

## Post-Cleanup Verification

After all changes, verify:
1. `alembic upgrade head` succeeds
2. All existing unit tests pass (with updates)
3. All existing integration tests pass (with updates)
4. Widget builds: `cd mcp_server/priority_guardian/widget-react && npm run build`
5. No Python file imports `PgWeeklyOverview`
6. No Python file references `avg_hours_week` (grep check)
7. No TypeScript file references `avgHoursWeek` (grep check)
