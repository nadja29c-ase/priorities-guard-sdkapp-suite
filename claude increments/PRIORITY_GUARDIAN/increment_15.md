# Briefing: Past Week Reports From Snapshots

## Context

When a user requests a weekly report for a past (completed) week, the service computes hours from live Google Calendar events using **current** keyword assignments. If the user has swapped keywords since that week, the report shows wrong priority-hour mappings.

Example: Priority "Ship v1.0" had P3 last week, user swapped to P2 since then. The weekly report now assigns last week's P3-tagged hours to whatever currently holds P3 — wrong name, wrong hours, wrong pie chart.

Snapshots already capture the correct data at the time of the week's completion. They store `actual_hours` per `priority_id` (not per keyword), so they are immune to keyword swaps.

## The Fix

When `generate_weekly_report()` is called for a **completed week**, check if snapshots exist for that week. If they do, build the report from snapshot data instead of live calendar computation.

Current week always uses live calendar computation (snapshots don't exist yet for incomplete weeks).

## Changes

### New Migration: Add `calendar_keyword_at_snapshot`

Add `calendar_keyword_at_snapshot` column to `pg_weekly_snapshots`:
- Type: `String(2)`, nullable=True
- No CHECK constraint (the value is captured from `pg_priorities.calendar_keyword` which already has its own CHECK)
- Nullable because existing snapshots were created before this column existed. No backfill needed — snapshots are at most 3 weeks old, and the null fallback handles them gracefully.

Also add the column to `PgWeeklySnapshot` in `db_models.py`:
```python
calendar_keyword_at_snapshot: Mapped[str | None] = mapped_column(
    String(2),
    nullable=True,
    comment="Calendar keyword (P1/P2/P3) at time of snapshot creation. NULL for pre-migration snapshots.",
)
```

### Modified: `snapshot_service.py` — `_create_snapshots_for_week()`

In the `insert_params` dict, add:
```python
"calendar_keyword_at_snapshot": priority.calendar_keyword,
```

This captures the keyword at snapshot creation time. No other snapshot service changes needed.

### Shared Helper: `priority_eligible_for_week()`

Extract the first-eligible-Monday logic into a shared helper used by both snapshot_service and the partial coverage guard. This prevents drift between the two code paths.

**Location:** `backend/apps/priority_guardian/services/snapshot_service.py` (or a shared utils module if preferred)

```python
def priority_eligible_for_week(created_at: date, week_start: date) -> bool:
    """
    Check if a priority should have a snapshot for the given week.
    
    A priority is eligible if the week_start is on or after the first
    Monday on or after the priority's created_at date (full weeks only).
    """
    days_until_monday = (7 - created_at.weekday()) % 7
    first_valid_monday = created_at + timedelta(days=days_until_monday)
    return week_start >= first_valid_monday
```

Use this in:
- `_create_snapshots_for_week()` — replace the inline first-eligible-Monday calculation
- `_build_report_from_snapshots()` — use it in the partial coverage guard to count expected priorities

### Modified: `weekly_report_service.py` — New snapshot-based report path

**File:** `backend/apps/priority_guardian/services/weekly_report_service.py`

### Modified: `generate_weekly_report()`

After Step 3 (compute week boundaries and determine `is_current`), add a new branch:

```
if not is_current:
    # Try to build report from snapshots
    snapshot_report = await _build_report_from_snapshots(
        user_id=user_id,
        week_start=actual_week_start,
        week_end=actual_week_end,
        session=session,
        correlation_id=correlation_id,
    )
    if snapshot_report is not None:
        return snapshot_report
    # Fall through to live computation if no snapshots exist
```

If `_build_report_from_snapshots` returns `None` (no snapshots found for that week), fall through to existing live computation. This handles the case where the user requests a past week that hasn't been snapshotted yet.

### New: `_build_report_from_snapshots()`

```python
async def _build_report_from_snapshots(
    user_id: UUID,
    week_start: date,
    week_end: date,
    session: AsyncSession,
    correlation_id: str | None = None,
) -> dict[str, Any] | None:
```

**What it does:**

1. Query `pg_weekly_snapshots` joined with `pg_priorities` for this user and `week_start`
2. If zero rows returned, return `None` (fall through to live computation)
3. **Partial snapshot guard:** Count how many active priorities existed during that week: `created_at <= week_end AND (retired_at IS NULL OR retired_at > week_end)`. The `retired_at IS NULL` clause includes currently-active priorities. If snapshot row count < expected priority count, return `None` — partial data is worse than live computation with potentially stale keywords. Log `snapshot.partial_coverage` at WARNING level with expected vs actual counts. Note: snapshot service creates rows for all active priorities including zero-hour ones. The only skip condition is partial weeks (priority created after week_start), which the expected count query must also account for using the same first-eligible-Monday logic from snapshot_service.
4. For each snapshot row, build the priority data dict using:
   - `snapshot.calendar_keyword_at_snapshot` — the keyword assigned to this priority at the time the snapshot was created. Use this for pie chart labels and time allocation breakdown. If null (pre-migration snapshots), fall back to `priority.calendar_keyword`.
   - `priority.name`, `priority.type` — these don't change on keyword swap
   - `snapshot.actual_hours` — the correct hours for this priority this week
   - `snapshot.target_hours` — the target at time of snapshot
   - `snapshot.streak_at_snapshot` — streak value at that point in time
   - For deadline priorities: load `priority.deliverables` for current deliverable counts, `priority.deadline` for pacing
   - For flexible priorities: compute `flex_status` from `snapshot.actual_hours` and `snapshot.target_hours`
4. Build `time_allocation` from snapshot data: sum hours per keyword, compute other_hours as 0 (we don't have "other" hours in snapshots — this is a known limitation)
5. Return the report dict

**Important: `time_allocation` limitation.** Snapshots don't store "other" hours or total tracked hours — only per-priority hours. Two options:

- **Option A:** Set `other_hours = 0` and `total_tracked_hours = sum of all snapshot actual_hours`. The pie chart won't show "other" for past weeks. This is acceptable — the user cares about priority hours, not untagged time.
- **Option B:** Still fetch calendar events for past weeks to get "other" hours, but use snapshot data for priority-hour mappings. More accurate but requires Google API call, defeating part of the purpose.

**Go with Option A.** Simpler, no API call needed, and the primary bug (wrong priority-hour mapping) is fixed. If users complain about missing "other" hours in past reports, revisit.

**Important: Deliverable state.** Snapshot doesn't capture deliverable completion status at the time of the snapshot. Using current deliverable state for `pacing_status` on past weeks is slightly inaccurate (deliverables completed after that week will count). This is a known and acceptable limitation — deliverable state tracking per-snapshot would require a separate table. Note this in a code comment.

### Query for snapshots

```sql
SELECT s.actual_hours, s.target_hours, s.streak_at_snapshot,
       s.calendar_keyword_at_snapshot,
       p.id, p.name, p.type, p.calendar_keyword, p.deadline,
       p.weekly_hour_target, p.created_at
FROM pg_weekly_snapshots s
JOIN pg_priorities p ON s.priority_id = p.id
WHERE s.user_id = :user_id AND s.week_start = :week_start
ORDER BY p.created_at
```

For the keyword label in the report, use: `snapshot.calendar_keyword_at_snapshot or priority.calendar_keyword` (null fallback for pre-migration snapshots).

Load deliverables for deadline priorities via a second query or eager load on the priority relationship.

**Decimal handling:** `actual_hours` and `target_hours` come from the DB as `Decimal`. Keep them as `Decimal` through all computation (flex_status, totals). Convert to `float` only at final JSON serialization. This prevents rounding drift that causes flaky test assertions.

### Response shape

Must match the existing `generate_weekly_report` return shape exactly so the MCP tool and widget don't need changes. Key fields:

- `is_current_week`: `False`
- `snapshot_saved`: `True` (indicates data came from snapshots)
- `priorities[].actual_hours`: from snapshot
- `priorities[].target_hours`: from snapshot (flexible only)
- `priorities[].streak_count`: from `streak_at_snapshot`
- `priorities[].total_hours_invested`: from `priority.total_hours_invested` (current aggregate — acceptable approximation)
- `priorities[].flex_status`: computed from snapshot actual_hours vs snapshot target_hours
- `priorities[].pacing_status`: computed from current deliverable state (known limitation)
- `priorities[].previous_week`: `None` (same as current behavior)
- `time_allocation.total_tracked_hours`: sum of all snapshot actual_hours
- `priorities[].calendar_keyword`: from `snapshot.calendar_keyword_at_snapshot`, falling back to `priority.calendar_keyword` if null
- `time_allocation.keywords`: hours grouped by `calendar_keyword_at_snapshot` (with fallback), not by current keyword
- `time_allocation.other_hours`: `0.0`
- `all_events`: `[]` (no event data from snapshots — LLM won't have events for semantic grouping on past weeks)

## What This Does NOT Change

- Current week reports — always live from Google Calendar
- Widget rendering — unchanged (same response shape)
- MCP tools — unchanged (same response shape)
- Existing snapshots — no backfill, null fallback handles them

## Unit Tests

**File:** `tests/unit/test_weekly_report_service.py` (or new file)

1. **test_past_week_uses_snapshots** — Mock session with snapshot rows for a completed week. Verify `generate_weekly_report` returns data from snapshots, not from calendar. Verify `actual_hours` matches snapshot values.
2. **test_past_week_no_snapshots_falls_through** — Mock session with zero snapshot rows for a completed week. Verify the function falls through to live calendar computation (existing behavior).
3. **test_current_week_ignores_snapshots** — Even if snapshots exist for current week's Monday, verify live computation is used.
4. **test_snapshot_report_response_shape** — Verify the return dict matches the expected shape (all required keys present, types correct).
5. **test_snapshot_report_flex_status_computation** — Verify `flex_status` is computed from snapshot's `actual_hours` and `target_hours`, not from live calendar.
6. **test_snapshot_report_other_hours_zero** — Verify `other_hours` is `0.0` and `total_tracked_hours` equals sum of snapshot hours.
7. **test_partial_snapshots_fall_through** — Mock session with 3 active priorities that existed during the week but only 2 snapshot rows. Verify the function returns `None` (falls through to live computation), not partial data.

## Integration Tests

**File:** `tests/integration/priority_guardian/test_weekly_report_snapshots.py`

1. **test_past_week_report_uses_snapshot_data** — Create a user, priority, and snapshot row in the test DB. Call `generate_weekly_report` for that completed week. Verify returned `actual_hours` matches snapshot, not any calendar computation.
2. **test_keyword_swap_does_not_affect_snapshot_report** — Create user, priority with P1, create snapshot (with `calendar_keyword_at_snapshot = 'P1'`). Then update priority's `calendar_keyword` to P3. Request past week report. Verify `actual_hours` correct from snapshot AND `calendar_keyword` in response is `'P1'` (historical, from snapshot), not `'P3'` (current).
3. **test_partial_snapshots_fall_through_to_live** — Create 3 active priorities but only 2 snapshot rows for the target week. Verify the function falls through to live computation (returns data for all 3 priorities, not just the 2 with snapshots).

**File:** `tests/integration/priority_guardian/test_db_integrity.py` (add to existing)

4. **test_calendar_keyword_at_snapshot_accepts_valid_keywords** — Raw SQL INSERT a snapshot row with `calendar_keyword_at_snapshot = 'P1'`. Verify row created successfully.
5. **test_calendar_keyword_at_snapshot_allows_null** — Raw SQL INSERT a snapshot row with `calendar_keyword_at_snapshot = NULL`. Verify row created (backward compatibility for pre-migration snapshots).
6. **test_snapshot_preserves_keyword_at_creation** — Create a priority with `calendar_keyword = 'P2'`, create a snapshot via the snapshot service. Query the snapshot row directly via raw SQL. Verify `calendar_keyword_at_snapshot = 'P2'`. Then update the priority's keyword to `'P3'`. Query the snapshot again. Verify `calendar_keyword_at_snapshot` is still `'P2'` (immutable after creation).

## Acceptance Criteria

- [ ] Completed weeks with snapshots return data from `pg_weekly_snapshots`, not live calendar
- [ ] Completed weeks without snapshots fall through to live calendar computation
- [ ] Partial snapshot coverage (fewer rows than expected priorities) falls through to live computation
- [ ] Current week always uses live calendar computation
- [ ] Response shape is identical whether data comes from snapshots or live computation
- [ ] `other_hours` is `0.0` for snapshot-based reports (documented limitation)
- [ ] `all_events` is `[]` for snapshot-based reports (documented limitation)
- [ ] `flex_status` computed from snapshot's actual/target hours
- [ ] No Google API call made when snapshots are available for past weeks
- [ ] New migration adds `calendar_keyword_at_snapshot` (String(2), nullable) to `pg_weekly_snapshots`
- [ ] Snapshot creation populates `calendar_keyword_at_snapshot` from `priority.calendar_keyword`
- [ ] Past week reports use `calendar_keyword_at_snapshot` for pie chart labels (fallback to `priority.calendar_keyword` if null)
- [ ] Code comment documents: pacing_status uses current deliverable state, not historical (known limitation)
- [ ] Deliverables eager loaded — no N+1 queries
- [ ] All existing tests still pass
