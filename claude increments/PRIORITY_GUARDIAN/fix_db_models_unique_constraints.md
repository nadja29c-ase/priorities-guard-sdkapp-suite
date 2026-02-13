# Fix: db_models.py — Unique constraints + stale comment

**File:** `backend/apps/priority_guardian/db_models.py`

## Fix 1: PgWeeklySnapshot — add UniqueConstraint to `__table_args__`

The UNIQUE(priority_id, week_start) constraint exists in the migration but is not declared in the model. This creates drift risk — if someone runs `alembic revision --autogenerate`, SQLAlchemy won't see the constraint and could generate a migration that drops it.

Add `UniqueConstraint` to the existing `__table_args__` tuple:

```python
from sqlalchemy import UniqueConstraint
```

In `PgWeeklySnapshot.__table_args__`, add:

```python
UniqueConstraint(
    "priority_id", "week_start",
    name="uq_pg_weekly_snapshots_priority_week",
),
```

Keep the two existing CheckConstraints. The constraint name must match the migration — check `p6k7l8m9n0o1_add_pg_weekly_snapshot_tables.py` for the actual name used and use that exact name. If the migration used a different name, use the migration's name.

## Fix 2: PgWeeklyOverview — add UniqueConstraint to `__table_args__`

Same issue. UNIQUE(user_id, week_start) only in migration.

`PgWeeklyOverview` currently has no `__table_args__`. Add one:

```python
__table_args__ = (
    UniqueConstraint(
        "user_id", "week_start",
        name="uq_pg_weekly_overview_user_week",
    ),
)
```

Same rule: check the migration for the actual constraint name and match it exactly.

## Fix 3: PgPriority.streak_count — fix misleading comment

Current comment:
```python
comment="Future: consecutive weeks meeting target",
```

Change to:
```python
comment="Consecutive weeks with hours > 0 (binary streak rule, see ADR-001)",
```

## What NOT to do

- Do NOT generate a new migration. These constraints already exist in the DB via existing migrations. The model changes are declarative only — they make SQLAlchemy aware of what the migration already created.
- Do NOT touch any other model, field, or constraint.

## Verification

After changes, run:
```bash
alembic check
```
This should report no new changes detected (because the constraints already exist in the DB). If alembic detects a diff, the constraint names don't match — fix the names to match the migration exactly.
