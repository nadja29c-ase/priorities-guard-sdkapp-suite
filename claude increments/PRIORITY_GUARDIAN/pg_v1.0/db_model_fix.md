# DB Hardening — CheckConstraints for Data Integrity

## Goal

Add database-level CheckConstraints to enforce business rules that are currently only validated at the API layer. This prevents invalid states from entering the database through migration mistakes, direct DB writes, or future code paths that bypass existing validation.

This is a pure schema migration. No application logic changes.

---

## Context

The following invariants are documented in the codebase and enforced at API level, but not at DB level:

1. Deadline priorities must have `deadline IS NOT NULL` and must not have `weekly_hour_target` or `checkpoint_date`
2. Flexible priorities must have `weekly_hour_target IS NOT NULL` and `checkpoint_date IS NOT NULL` and must not have `deadline`
3. `weekly_hour_target` must be > 0 when set
4. `status='retired'` must have `retired_at IS NOT NULL`, and `status='active'` must have `retired_at IS NULL`
5. `week_end` must equal `week_start + 6 days` on snapshots
6. `target_hours` on snapshots must be >= 0 when set

All constraints use `ALTER TABLE ... ADD CONSTRAINT` so they can be applied to existing data. If any existing rows violate the constraints, the migration will fail — this is intentional (forces data cleanup first).

---

## Constraints to Add

### PgPriority (`pg_priorities`)

**1. Type-field consistency**
```sql
CHECK (
    (type = 'deadline' AND deadline IS NOT NULL AND weekly_hour_target IS NULL AND checkpoint_date IS NULL)
    OR
    (type = 'flexible' AND weekly_hour_target IS NOT NULL AND checkpoint_date IS NOT NULL AND deadline IS NULL)
)
```
Name: `ck_pg_priorities_type_field_consistency`

**2. Weekly hour target positive**
```sql
CHECK (weekly_hour_target IS NULL OR weekly_hour_target > 0)
```
Name: `ck_pg_priorities_weekly_target_positive`

**3. Retirement consistency**
```sql
CHECK (
    (status = 'active' AND retired_at IS NULL)
    OR
    (status = 'retired' AND retired_at IS NOT NULL)
)
```
Name: `ck_pg_priorities_retirement_consistency`

### PgWeeklySnapshot (`pg_weekly_snapshots`)

**4. Week end consistency**
```sql
CHECK (week_end = week_start + INTERVAL '6 days')
```
Name: `ck_pg_weekly_snapshots_week_consistency`

**5. Target hours non-negative**
```sql
CHECK (target_hours IS NULL OR target_hours >= 0)
```
Name: `ck_pg_weekly_snapshots_target_hours_non_negative`

---

## Files Modified

| File | Change |
|---|---|
| `backend/apps/priority_guardian/db_models.py` | Add 5 CheckConstraints to `__table_args__` of PgPriority and PgWeeklySnapshot |
| `backend/alembic/versions/u1v2w3x4y5z6_add_check_constraints.py` | New migration adding all 5 constraints |

---

## Implementation Notes

- Add all 5 constraints in a single migration file
- Migration must have a `downgrade()` that drops all 5 constraints
- Follow existing migration naming convention (see `backend/alembic/versions/`)
- The constraints in `db_models.py` must match the migration SQL exactly
- Constraint names must match between model and migration

---

## Unit Tests

**File:** Appropriate test location following existing conventions

1. **Type-field consistency — valid deadline:** `type='deadline'`, `deadline` set, `weekly_hour_target=NULL`, `checkpoint_date=NULL` → insert succeeds
2. **Type-field consistency — invalid deadline (no deadline date):** `type='deadline'`, `deadline=NULL` → insert fails with IntegrityError
3. **Type-field consistency — invalid deadline (has weekly_hour_target):** `type='deadline'`, `deadline` set, `weekly_hour_target` set → insert fails
4. **Type-field consistency — valid flexible:** `type='flexible'`, `weekly_hour_target` set, `checkpoint_date` set, `deadline=NULL` → insert succeeds
5. **Type-field consistency — invalid flexible (no target):** `type='flexible'`, `weekly_hour_target=NULL` → insert fails
6. **Type-field consistency — invalid flexible (has deadline):** `type='flexible'`, all flexible fields set, `deadline` also set → insert fails
7. **Weekly target positive — valid:** `weekly_hour_target=0.5` → insert succeeds
8. **Weekly target positive — zero:** `weekly_hour_target=0` → insert fails
9. **Weekly target positive — negative:** `weekly_hour_target=-1` → insert fails
10. **Weekly target positive — NULL (deadline type):** `weekly_hour_target=NULL` → insert succeeds
11. **Retirement consistency — active with no retired_at:** `status='active'`, `retired_at=NULL` → succeeds
12. **Retirement consistency — retired with retired_at:** `status='retired'`, `retired_at` set → succeeds
13. **Retirement consistency — retired without retired_at:** `status='retired'`, `retired_at=NULL` → insert fails
14. **Retirement consistency — active with retired_at:** `status='active'`, `retired_at` set → insert fails
15. **Week consistency — valid:** `week_end = week_start + 6 days` → insert succeeds
16. **Week consistency — invalid:** `week_end = week_start + 5 days` → insert fails
17. **Target hours non-negative — valid:** `target_hours=0` → insert succeeds
18. **Target hours non-negative — valid NULL:** `target_hours=NULL` → insert succeeds
19. **Target hours non-negative — negative:** `target_hours=-1` → insert fails

All tests must use actual DB operations (not mocks) to verify the constraints work at the database level. Use the existing test database fixture.

---

## Integration Tests

No integration tests needed. These are DB-level constraints verified by unit tests that hit the actual database.

---

## Pre-Migration Data Validation

Before running the migration, verify no existing rows violate the new constraints:

```sql
-- Check 1: Type-field inconsistency
SELECT id, type, deadline, weekly_hour_target, checkpoint_date
FROM pg_priorities
WHERE NOT (
    (type = 'deadline' AND deadline IS NOT NULL AND weekly_hour_target IS NULL AND checkpoint_date IS NULL)
    OR
    (type = 'flexible' AND weekly_hour_target IS NOT NULL AND checkpoint_date IS NOT NULL AND deadline IS NULL)
);

-- Check 2: Zero/negative weekly targets
SELECT id, weekly_hour_target FROM pg_priorities WHERE weekly_hour_target IS NOT NULL AND weekly_hour_target <= 0;

-- Check 3: Retirement inconsistency
SELECT id, status, retired_at FROM pg_priorities WHERE (status = 'retired' AND retired_at IS NULL) OR (status = 'active' AND retired_at IS NOT NULL);

-- Check 4: Week end inconsistency
SELECT id, week_start, week_end FROM pg_weekly_snapshots WHERE week_end != week_start + INTERVAL '6 days';

-- Check 5: Negative target hours
SELECT id, target_hours FROM pg_weekly_snapshots WHERE target_hours IS NOT NULL AND target_hours < 0;
```

If any rows are returned, fix them before running the migration.

---

## Out of Scope

- Deliverables-only-for-deadline enforcement (cross-table check, API-layer is sufficient)
- Max 3 goals per priority enforcement (API-layer is sufficient, can't easily do row-count constraints in SQL)
- Snapshot immutability (service-layer discipline is sufficient)
- Application logic changes (this is schema-only)