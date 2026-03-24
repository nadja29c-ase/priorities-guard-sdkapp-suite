# Briefing: Two Quick Fixes from DB Test Review

## Fix 1: Add zero boundary test for weekly_hour_target

The constraint `ck_pg_priorities_weekly_target_positive` enforces `weekly_hour_target > 0`. Current tests cover negative values but not zero. Zero should be rejected.

Add one test to `TestCheckConstraints` in `tests/integration/priority_guardian/test_db_integrity.py`:

**Test:** `test_zero_weekly_hour_target_rejected`
- Create a user
- Raw SQL INSERT a flexible priority with `weekly_hour_target = 0`
- Assert `IntegrityError` is raised
- Follow the same pattern as `test_negative_weekly_hour_target_rejected` (test 3f)

## Fix 2: Verify no SQLite fallback in test config

Check all test configuration files (`conftest.py`, `pytest.ini`, `pyproject.toml`, any test settings) and confirm:

- Test database URL always points to PostgreSQL
- There is no `sqlite://` fallback or default anywhere
- If the PostgreSQL URL is missing, tests should fail — not silently fall back to SQLite

If a SQLite fallback exists, remove it. If none exists, no action needed — just confirm.

## Acceptance Criteria

- [ ] Zero `weekly_hour_target` rejected by CHECK constraint (new integration test passes)
- [ ] No SQLite fallback in test configuration (confirmed or removed)
- [ ] All existing tests still pass
