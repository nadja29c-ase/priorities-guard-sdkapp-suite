# Fix: snapshot_service.py + db_models.py — Aggregate drift, avg bug, stale docstring

## Fix 1: total_hours_invested — derive from SUM, not increment

**File:** `backend/apps/priority_guardian/services/snapshot_service.py`
**Function:** `_update_aggregates()`

Current pattern:
```python
total_hours_invested = total_hours_invested + :hours
```

Replace with derived SUM, same as avg_hours_week already does:

```python
total_result = await session.execute(
    select(func.sum(PgWeeklySnapshot.actual_hours)).where(
        PgWeeklySnapshot.priority_id == priority_id,
    )
)
total_hours = total_result.scalar()
```

Then in the UPDATE statement, change from:
```python
total_hours_invested = total_hours_invested + :hours,
```
to:
```python
total_hours_invested = :total_hours,
```

With parameter:
```python
"total_hours": Decimal(str(total_hours)) if total_hours is not None else Decimal("0"),
```

**Why:** Increment-based accumulation drifts if snapshots are ever re-run, backfill depth changes, or DB is partially restored. SUM from snapshots is the source of truth — same pattern already used for avg_hours_week. Negligible cost at current scale.

## Fix 2: avg_hours_week — falsy check drops zero

**File:** `backend/apps/priority_guardian/services/snapshot_service.py`
**Function:** `_update_aggregates()`

Current:
```python
"avg_hours": Decimal(str(avg_hours)) if avg_hours else None,
```

Fix:
```python
"avg_hours": Decimal(str(avg_hours)) if avg_hours is not None else None,
```

**Why:** `if avg_hours else` is falsy for `0` and `Decimal("0")`. A priority with zero hours every week would store NULL instead of 0.0. Use explicit `is not None` check.

## Fix 3: PgWeeklySnapshot docstring — stale creation path

**File:** `backend/apps/priority_guardian/db_models.py`
**Class:** `PgWeeklySnapshot`

Current docstring says:
```
Created when a completed week is finalized via the get_weekly_report tool.
```

Replace with:
```
Created opportunistically on dashboard load via ensure_snapshots_up_to_date().
See ADR-001 Decision 5 for rationale.
```

Also replace:
```
Immutable after creation (no overwrites).
```
With:
```
Immutable after creation — INSERT ON CONFLICT DO NOTHING, no updates.
```

## What NOT to do

- Do NOT change the AVG query — it's already correct
- Do NOT change the RETURNING id pattern — it's correct
- Do NOT change streak logic, backfill logic, or error handling

## Tests to update

The `_update_aggregates` change affects any unit test that asserts on `total_hours_invested` computation. If existing tests mock or assert the raw SQL parameters, update them to expect `:total_hours` (set value) instead of `total_hours_invested + :hours` (increment). If no such tests exist yet (Inc 08 tests still pending), ensure the new tests use the SUM pattern.
