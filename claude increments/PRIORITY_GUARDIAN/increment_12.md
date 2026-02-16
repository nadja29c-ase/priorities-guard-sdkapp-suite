# Briefing: Lower avg_target_achievement Threshold from ≥2 to ≥1

## Context
Users must currently complete 2 full weeks before seeing their average target achievement percentage. With only 1 completed week, the widget shows an hourglass + "Complete your first week to see your pattern." This delays the most motivating feedback signal by an extra week. A single-week result IS mathematically a valid average — showing it immediately rewards the user for their first week of tracking.

## What to Change

### 1. Backend: `snapshot_service.py`
**File:** `backend/apps/priority_guardian/services/snapshot_service.py`
**Function:** `_update_aggregates()`

Change the threshold from `>= 2` to `>= 1`:

```python
# CURRENT:
if snapshot_count is not None and snapshot_count >= 2 and avg_achievement_raw is not None:

# CHANGE TO:
if snapshot_count is not None and snapshot_count >= 1 and avg_achievement_raw is not None:
```

No other backend changes needed. The SQL queries, phantom filtering, and aggregate computation logic remain identical.

### 2. DB model comment: `db_models.py`
**File:** `backend/apps/priority_guardian/db_models.py`
**Column:** `PgPriority.avg_target_achievement`

Update the comment from:
```python
comment="Average % of weekly target achieved across all snapshotted weeks. NULL when < 2 data points.",
```
to:
```python
comment="Average % of weekly target achieved across all snapshotted weeks. NULL when no valid snapshots exist.",
```

### 3. Widget copy: `FlexibleCard.tsx`
**File:** `mcp_server/priority_guardian/widget-react/src/components/FlexibleCard.tsx`

The hourglass fallback text currently says "Complete your first week to see your pattern." With the ≥1 threshold, users will see the average after their first completed week. The only time they'd see the hourglass is before any week completes.

Change from:
```
Complete your first week to see your pattern.
```
to:
```
Tracking in progress — your average builds after this week.
```

### 4. Production data fix
After deploying, trigger a snapshot refresh for existing users (open dashboard) so the aggregate recalculates with the new ≥1 threshold. No migration needed — the threshold is in application logic, not in DB constraints.

## Unit Tests

**File:** `tests/unit/priority_guardian/test_snapshot_service.py`

### Tests to update:

1. **`TestAvgTargetAchievementComputation::test_null_when_fewer_than_two_snapshots`**
   - Rename to `test_set_with_one_snapshot`
   - Change assertion: with 1 snapshot and avg=80.0, `avg_target_achievement` should now be `Decimal("80.0")`, NOT `None`

2. **Add new test: `test_null_when_zero_snapshots`**
   - Mock achievement query returning `(None, 0)` — zero valid snapshots
   - Assert `avg_target_achievement` is `None`

### Tests that should NOT change (verify they still pass as-is):
- `test_correctly_averaged_with_two_or_more_snapshots` — still valid
- `test_zero_hour_week_contributes_zero_percent` — still valid
- `test_over_100_percent_allowed` — still valid
- `test_zero_target_hours_excluded_from_average` — still valid
- All `TestPhantomSnapshotPrevention` tests — still valid
- All `TestComputeStreak` tests — unrelated

## Integration Tests
No integration test changes needed. The snapshot persistence integration tests don't assert the ≥2 threshold directly.

## Acceptance Criteria
- [ ] `_update_aggregates` uses `>= 1` threshold
- [ ] db_models comment updated
- [ ] FlexibleCard hourglass text updated
- [ ] Renamed unit test asserts avg is set with 1 snapshot
- [ ] New unit test asserts avg is NULL with 0 snapshots
- [ ] All existing snapshot tests pass unchanged
- [ ] Widget rebuilt (`npm run build` in widget-react)

## Risk
Minimal. Single-line threshold change with defense-in-depth phantom filtering already in place. The mathematical computation is identical — only the minimum sample size changes.
