# Briefing: Store Other Hours and Total Tracked Hours in Snapshots

## Context

Snapshot-based past week reports currently return `other_hours = 0.0` and `total_tracked_hours = sum of priority hours only`. This makes the pie chart misleading for historical weeks — it shows only the P1/P2/P3 split without the untagged time that dominated the user's actual week.

The values `other_hours` and `total_tracked_hours` are already computed at snapshot creation time from `compute_allocation_from_events()`. They just aren't persisted.

## Design Decision: Denormalize on Snapshot Rows

These are per-week values, not per-priority. But rather than creating a separate `pg_weekly_summary` table, store them on every `pg_weekly_snapshots` row for that week. Same value across all priority snapshots in the same week.

Rationale:
- Snapshots are immutable (INSERT ON CONFLICT DO NOTHING) — redundancy can't drift
- No extra join needed when building snapshot-based reports
- At most 3 snapshot rows per week (3 priorities) — trivial redundancy
- Avoids a new table, new migration chain, new query patterns

## Changes

### Migration: Add two columns to `pg_weekly_snapshots`

- `other_hours`: `Numeric(6, 2)`, nullable=True, comment: "Untagged calendar hours for this week. Same value across all snapshots in the same week. NULL for pre-migration snapshots."
- `total_tracked_hours`: `Numeric(8, 2)`, nullable=True, comment: "Total tracked hours (all events) for this week. Same value across all snapshots in the same week. NULL for pre-migration snapshots."

Both nullable for backward compatibility with existing snapshots.

Add CHECK constraints:
- `ck_pg_weekly_snapshots_other_hours_non_negative`: `other_hours IS NULL OR other_hours >= 0`
- `ck_pg_weekly_snapshots_total_hours_non_negative`: `total_tracked_hours IS NULL OR total_tracked_hours >= 0`

### Model: `db_models.py` — `PgWeeklySnapshot`

Add two columns:

```python
other_hours: Mapped[Decimal | None] = mapped_column(
    Numeric(6, 2),
    nullable=True,
    comment="Untagged calendar hours for this week. Same value across all snapshots in the same week. NULL for pre-migration snapshots.",
)

total_tracked_hours: Mapped[Decimal | None] = mapped_column(
    Numeric(8, 2),
    nullable=True,
    comment="Total tracked hours (all events) for this week. Same value across all snapshots in the same week. NULL for pre-migration snapshots.",
)
```

Add the two CHECK constraints to `__table_args__`.

Update the class docstring to note these fields are denormalized per-week values.

### Service: `snapshot_service.py` — `_create_snapshots_for_week()`

The `allocation` dict is already computed before the priority loop. Extract `other_hours` and `total_tracked_hours` once, then pass to every priority's insert_params:

```python
# Before the priority loop:
week_other_hours = Decimal(str(allocation["other_hours"])).quantize(Decimal("0.01"))
week_total_tracked_hours = Decimal(str(allocation["total_tracked_hours"])).quantize(Decimal("0.01"))

# Inside insert_params for each priority:
"other_hours": week_other_hours,
"total_tracked_hours": week_total_tracked_hours,
```

### Service: `weekly_report_service.py` — `_build_report_from_snapshots()`

Replace the hardcoded `other_hours = 0.0` and sum-based `total_tracked_hours` with snapshot values:

```python
# After building priority_data, read from first snapshot row (all rows have same value):
first_snapshot = snapshot_rows[0][0]  # (snapshot, priority) tuple
snapshot_other_hours = float(first_snapshot.other_hours or Decimal("0"))
snapshot_total_tracked = float(first_snapshot.total_tracked_hours or Decimal("0"))
```

Use these in the `time_allocation` dict:
```python
"other_hours": snapshot_other_hours,
"total_tracked_hours": snapshot_total_tracked,
```

The `or Decimal("0")` handles pre-migration snapshots where these columns are NULL.

**Implementation note:** `_build_report_from_snapshots()` uses ORM query returning `(PgWeeklySnapshot, PgPriority)` tuples (already implemented in previous increment). Access via `snapshot.other_hours` is correct ORM attribute access.

**Consistency guard:** Before using `first_snapshot` values, verify all snapshot rows for the week have matching `other_hours` AND `total_tracked_hours`. Check both fields. If any row has a non-null value that differs from another row's non-null value, or if some rows are NULL while others are not, log `snapshot_report.inconsistent_week_totals` at WARNING and fall through to live computation (return None). This catches corruption from partial snapshot creation bugs.

**Decimal precision:** `compute_allocation_from_events()` returns Python floats. When writing to snapshots, quantize: `Decimal(str(value)).quantize(Decimal("0.01"))`. Keep as Decimal through all computation in `_build_report_from_snapshots()`, convert to float only at final JSON serialization.

### Schema Validator

Add the two new CHECK constraints to `PG_SNAPSHOTS_CHECK_CONSTRAINTS` in `schema_validator.py`:

```python
("ck_pg_weekly_snapshots_other_hours_non_negative", ["other_hours", "0"]),
("ck_pg_weekly_snapshots_total_hours_non_negative", ["total_tracked_hours", "0"]),
```

### Pre-Deploy

Read OPERATIONS.md and check for additional pre-deploy tasks.

## Unit Tests

**File:** `tests/unit/priority_guardian/test_weekly_report_service.py`

1. **test_snapshot_report_uses_stored_other_hours** — Mock snapshot with `other_hours = Decimal("12.5")` and `total_tracked_hours = Decimal("25.0")`. Verify report returns these values, not computed zeros.
2. **test_snapshot_report_null_other_hours_defaults_to_zero** — Mock snapshot with `other_hours = None` (pre-migration). Verify report returns `0.0` for other_hours.

## Integration Tests

**File:** `tests/integration/priority_guardian/test_db_integrity.py` (add to existing)

3. **test_other_hours_non_negative_constraint** — Raw SQL INSERT with `other_hours = -1`. Verify CHECK constraint rejects it.
4. **test_total_tracked_hours_non_negative_constraint** — Raw SQL INSERT with `total_tracked_hours = -1`. Verify CHECK constraint rejects it.
5. **test_other_hours_null_accepted** — Raw SQL INSERT with `other_hours = NULL`. Verify accepted (pre-migration compatibility).
6. **test_other_hours_persisted_correctly** — Insert snapshot with `other_hours = 5.25` and `total_tracked_hours = 22.75`. Query back and verify exact Decimal values.
7. **test_denormalized_values_identical_across_week** — Insert 3 snapshots for same week (3 different priorities). All have `other_hours = 4.5` and `total_tracked_hours = 18.0`. Query all 3 rows and verify values are identical.

**File:** `tests/integration/priority_guardian/test_snapshot_persistence.py` (add to existing)

8. **test_snapshot_service_populates_other_and_total_hours** — Create user + 2 priorities. Mock `compute_allocation_from_events()` to return known values (`other_hours=4.5`, `total_tracked_hours=18.0`). Run `_create_snapshots_for_week()`. Query the inserted snapshot rows via raw SQL. Assert all rows have `other_hours == Decimal("4.50")` and `total_tracked_hours == Decimal("18.00")`, identical across rows. This proves the write path, not just DB schema.

## Acceptance Criteria

- [ ] New migration adds `other_hours` (Numeric(6,2), nullable) and `total_tracked_hours` (Numeric(8,2), nullable) to `pg_weekly_snapshots`
- [ ] CHECK constraints prevent negative values for both columns
- [ ] Schema validator checks new constraints at startup
- [ ] Snapshot creation populates both columns from `compute_allocation_from_events()` result
- [ ] Past week snapshot-based reports use stored `other_hours` and `total_tracked_hours`
- [ ] Pre-migration snapshots (NULL values) default to `0.0` in report output
- [ ] DB integrity tests verify constraint enforcement
- [ ] All existing tests still pass
