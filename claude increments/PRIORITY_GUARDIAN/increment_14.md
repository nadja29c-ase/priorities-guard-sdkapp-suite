# Briefing: Startup Schema Validation

## Context

Production ran for weeks with 6 missing CHECK constraints due to a migration branch fork. The application-level validation was the only guard. This was caught by a manual schema diff, not by any automated system.

This increment adds a startup schema validator that runs during application boot. If the production database schema doesn't match expectations, the app refuses to start and logs exactly what's wrong. This makes schema drift impossible to miss.

## Scope

**One new module:** `backend/core/schema_validator.py`
**Two integration points in `backend/main.py`:**
1. `validate_schema()` called from `lifespan()`, after `test_connection()` succeeds
2. Global unhandled exception handler added via `@app.exception_handler(Exception)`

**One fix:** Convert `backend/apps/priority_guardian/routers/offboarding_router.py` from stdlib `logging` to `structlog`

## What the Validator Checks

The validator runs a single SQL query against PostgreSQL system catalogs and verifies:

### A. Required CHECK Constraints on `pg_priorities`

| Constraint Name | Purpose |
|---|---|
| `ck_pg_priorities_keyword` | calendar_keyword IN ('P1','P2','P3') or NULL |
| `ck_pg_priorities_type` | type IN ('deadline','flexible') |
| `ck_pg_priorities_status` | status IN ('active','retired') |
| `ck_pg_priorities_type_field_consistency` | deadline↔flexible field exclusivity |
| `ck_pg_priorities_weekly_target_positive` | weekly_hour_target > 0 |
| `ck_pg_priorities_retirement_consistency` | active↔retired_at consistency |

### B. Required Constraints on `pg_weekly_snapshots`

**CHECK constraints:**

| Constraint Name | Purpose |
|---|---|
| `ck_pg_weekly_snapshots_actual_hours_non_negative` | actual_hours >= 0 |
| `ck_pg_weekly_snapshots_week_consistency` | week_end = week_start + 6 |
| `ck_pg_weekly_snapshots_week_start_monday` | week_start is a Monday |
| `ck_pg_weekly_snapshots_target_hours_non_negative` | target_hours >= 0 |

**UNIQUE constraint:**

| Constraint Name | Purpose |
|---|---|
| `uq_pg_weekly_snapshots_priority_week` | Unique on (priority_id, week_start) — prevents duplicate snapshots |

### C. Required Indexes

| Index Name | Purpose |
|---|---|
| `idx_pg_priorities_user_keyword_active` | Partial unique index for keyword uniqueness (WHERE status = 'active') |

Note: `uq_pg_weekly_snapshots_priority_week` is a UNIQUE constraint, not a standalone index. It is validated in `pg_constraint` (contype='u'), not in `pg_indexes`.

### D. Alembic Version

Query `alembic_version` table:
- Verify exactly 1 row exists (no multiple heads applied)
- Verify `version_num` is a non-empty string
- Log the actual revision at INFO level as `schema.alembic_revision` (gives visibility without brittle coupling to a specific expected head)

## Implementation Requirements

### `backend/core/schema_validator.py`

**Function:** `async def validate_schema(session: AsyncSession) -> None`

- Accepts an async session
- Wraps all queries in `async with session.begin():` — required because `SET LOCAL` only works inside a transaction block (silently no-ops otherwise)
- Sets `statement_timeout = '5s'` via `SET LOCAL` as the first statement inside the transaction
- Queries `alembic_version` first and logs the revision as `schema.alembic_revision` BEFORE running validation checks (so the revision is visible even if validation fails)
- Queries `pg_constraint` with `pg_get_constraintdef(oid)` and `pg_indexes` system catalogs
- For each expected constraint: verifies name exists, AND for simple constraints only, verifies definition (lowercased) contains expected semantic fragments. Complex constraints are validated by name only.
- For each expected index: verifies name exists AND `indexdef` (lowercased) contains expected semantic fragments (filtered by `schemaname = 'public'`)
- Verifies `alembic_version` has exactly 1 row with non-empty `version_num`
- If all match: logs `schema.validation.passed` at INFO level and returns
- If any missing or wrong definition: raises `RuntimeError` with a message listing every missing/invalid constraint or index by name
- Uses `structlog` (not stdlib logging) for consistency

**Definition normalization:** Always call `.lower()` on `pg_get_constraintdef()` and `indexdef` output before checking fragments. PostgreSQL may format expressions with varying whitespace, parenthesization, or casing across versions. Fragment checks must be on semantic tokens only (e.g., `'calendar_keyword'`, `'p1'`, `'status'`, `'active'`), never full string equality.

**Query approach:** Check both name AND definition to catch constraints that exist with wrong expressions. Use a single query per check category to minimize DB round-trips. Set a **5-second statement timeout** on the validator session to fail fast if the DB is in a bad state.

```sql
-- CHECK and UNIQUE constraints: name + definition (schema-qualified)
SELECT conname, pg_get_constraintdef(oid), contype
FROM pg_constraint 
WHERE conrelid = 'public.{table_name}'::regclass AND contype IN ('c', 'u');

-- Indexes (for partial unique index only): name + definition, schema-qualified
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE tablename = '{table_name}' AND schemaname = 'public';

-- Alembic head count + revision logging
SELECT version_num FROM alembic_version;
```

**CHECK constraints** (`contype='c'`) and **UNIQUE constraints** (`contype='u'`) both live in `pg_constraint`. The snapshot's `uq_pg_weekly_snapshots_priority_week` is a UNIQUE constraint, not just an index — so it must be validated via `pg_constraint`, not `pg_indexes`.

**`pg_indexes`** is only used for `idx_pg_priorities_user_keyword_active`, which is a partial unique index (created via `CREATE UNIQUE INDEX ... WHERE status = 'active'`). Partial indexes are not constraints — they only appear in `pg_indexes`.

**Definition validation — simple vs complex constraints:**

Some CHECK constraints use functions/operators (`extract(isodow ...)`, date arithmetic) whose text representation varies across PostgreSQL versions. Fragment matching on these would cause false deploy failures from harmless formatting differences.

**Rule:**
- **Simple constraints** (enum checks, positive value checks): validate name exists AND definition fragments match
- **Complex constraints** (Monday check, week consistency, type-field consistency, retirement consistency): validate **name exists only** — no definition fragment matching

| Constraint | Validation Level |
|---|---|
| `ck_pg_priorities_keyword` | Name + fragments: `calendar_keyword`, `'p1'`, `'p2'`, `'p3'` |
| `ck_pg_priorities_type` | Name + fragments: `type`, `'deadline'`, `'flexible'` |
| `ck_pg_priorities_status` | Name + fragments: `status`, `'active'`, `'retired'` |
| `ck_pg_priorities_type_field_consistency` | **Name only** (complex cross-field logic) |
| `ck_pg_priorities_weekly_target_positive` | Name + fragments: `weekly_hour_target`, `0` |
| `ck_pg_priorities_retirement_consistency` | **Name only** (complex cross-field logic) |
| `ck_pg_weekly_snapshots_actual_hours_non_negative` | Name + fragments: `actual_hours`, `0` |
| `ck_pg_weekly_snapshots_week_consistency` | **Name only** (date arithmetic) |
| `ck_pg_weekly_snapshots_week_start_monday` | **Name only** (extract/date_part) |
| `ck_pg_weekly_snapshots_target_hours_non_negative` | Name + fragments: `target_hours`, `0` |
| `uq_pg_weekly_snapshots_priority_week` | Name + fragments: `priority_id`, `week_start` |
| `idx_pg_priorities_user_keyword_active` | Name + indexdef fragments: `status`, `'active'` |

**Statement timeout:** Before running queries, execute `SET LOCAL statement_timeout = '5s'` on the session. If catalog queries hang due to DB issues, startup fails fast instead of blocking indefinitely.

**Configuration:** The expected constraints and their definition fragments are defined as constants at the top of the module. This list is intentionally limited to safety-critical constraints that protect data integrity — not every index or constraint in the schema. When a future migration adds a new safety-critical constraint, the developer adds its name and expected definition fragments to the constant. If they forget, the validator won't check for it — but that's acceptable. The goal is catching drift on critical invariants, not enforcing completeness.

### Integration in `backend/main.py`

Call `validate_schema()` inside `lifespan()`, after `test_connection()`:

```python
# Test database connection
try:
    await test_connection()
except Exception as e:
    logger.warning(f"Database connection failed: {e}")
    raise

# Validate schema integrity (blocks startup if drift detected)
from backend.core.schema_validator import validate_schema
from backend.core.database import async_session_factory
async with async_session_factory() as session:
    await validate_schema(session)  # Internally uses session.begin() for SET LOCAL
```

If `validate_schema` raises `RuntimeError`, the lifespan function propagates it, and FastAPI refuses to start. Render sees the process exit and marks the deploy as failed.

### Additional Fix: Global Unhandled Exception Handler

Add a catch-all exception handler in `backend/main.py` that ensures every unhandled 500 produces a structured log — even from endpoints that forget proper try/catch:

```python
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
```

This handler must:
- Re-raise `asyncio.CancelledError` immediately (swallowing it breaks graceful shutdown under load)
- Re-raise `HTTPException`, `RequestValidationError`, and `OAuthError` (those have their own handlers)
- For everything else: log `http.unhandled_exception` at ERROR level with: `path`, `method`, `correlation_id`, and `error_type` (class name only). Do NOT log `str(exc)` — SQLAlchemy exceptions include raw SQL with parameter values. Log only the exception class name.
- Return a generic JSON 500 response: `{"success": false, "error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred."}}`

This prevents the gap where a new endpoint added without proper error handling silently 500s with only uvicorn's unstructured stderr output.

### Additional Fix: Offboarding Router Logging

`backend/apps/priority_guardian/routers/offboarding_router.py` uses `import logging` (stdlib) instead of `structlog`. This means offboarding logs lack correlation IDs and JSON formatting.

**Fix:** Replace `import logging` / `logger = logging.getLogger(__name__)` with `import structlog` / `logger = structlog.get_logger(__name__)`. Update all `logger.info(f"...")` calls to use structlog keyword args pattern: `logger.info("event.name", key=value)`.

## What This Does NOT Do

- Does not check column types or nullability (too fragile across PG versions)
- Does not run on every request (only on startup)
- Does not auto-fix schema (fails loudly, human decides)
- Does not replace Alembic migrations (complementary guard)

## Unit Tests

Test file: `tests/unit/test_schema_validator.py`

1. **test_validate_schema_passes_with_all_constraints** — Mock session returning all expected constraint names with correct definition fragments, correct index names with correct definitions, and alembic count=1 → function returns without raising
2. **test_validate_schema_raises_on_missing_constraint** — Mock session returning partial list (missing one constraint) → raises `RuntimeError` containing the missing constraint name
3. **test_validate_schema_raises_on_wrong_constraint_definition** — Mock session returning correct constraint name but wrong definition (missing expected fragment) → raises `RuntimeError` mentioning the constraint name
4. **test_validate_schema_raises_on_missing_index** — Mock session returning constraints but missing an index → raises `RuntimeError` containing the missing index name
5. **test_validate_schema_raises_on_wrong_index_predicate** — Mock session returning index name but `indexdef` missing `active` predicate → raises `RuntimeError` mentioning the index name
6. **test_validate_schema_raises_on_multiple_alembic_heads** — Mock session returning 2 rows for alembic_version → raises `RuntimeError` mentioning multiple heads
7. **test_validate_schema_raises_on_empty_alembic_revision** — Mock session returning 1 row with empty version_num → raises `RuntimeError`
8. **test_validate_schema_logs_success** — Verify `schema.validation.passed` is logged at INFO level when all checks pass

## Integration Tests

Test file: `tests/integration/test_schema_validator.py`

1. **test_validate_schema_passes_on_real_db** — Run `validate_schema()` against the test database (which is built from all migrations) → should pass without raising. This proves the expected constant list matches what migrations actually create.

## Acceptance Criteria

- [ ] App refuses to start if any expected CHECK constraint is missing or has wrong definition
- [ ] App refuses to start if partial unique index is missing or has wrong predicate
- [ ] App refuses to start if alembic_version has multiple rows or empty revision
- [ ] Alembic revision logged as `schema.alembic_revision` BEFORE validation checks run
- [ ] Missing/invalid items are listed by name in the error message
- [ ] Validator queries wrapped in `session.begin()` with 5-second statement timeout via `SET LOCAL`
- [ ] Definition matching uses lowercased semantic fragments, never full string equality
- [ ] Successful validation logged as `schema.validation.passed`
- [ ] Global unhandled exception handler logs `http.unhandled_exception` for all uncaught 500s
- [ ] Global handler re-raises `asyncio.CancelledError` (does not swallow it)
- [ ] Global handler does not intercept HTTPException, RequestValidationError, or OAuthError
- [ ] Offboarding router converted from stdlib logging to structlog
- [ ] All existing tests still pass
- [ ] Integration test proves validator passes against migration-built DB
