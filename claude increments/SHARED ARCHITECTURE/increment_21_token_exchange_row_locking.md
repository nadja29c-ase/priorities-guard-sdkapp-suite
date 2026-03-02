# Increment 21: Token Exchange Row Locking

## Context

Shared backend infrastructure. `backend/core/oauth_provider/services/token_service.py` handles two token exchange flows:

1. **Authorization code → tokens** (`exchange_authorization_code`)
2. **Refresh token → new tokens** (`exchange_refresh_token`)

Both flows have a read-then-write race condition: two concurrent requests can both read the same row as valid (`used=False` / `revoked=False`), pass all validation, and both issue tokens before either commits the revocation/usage flag.

**Audit source:** HIGH-001 from OAuth security audit (2026-03-01)

## Problem

### Refresh token race (primary concern)

Current flow in `exchange_refresh_token`:
1. `SELECT ... WHERE refresh_token_hash = :hash` — reads row
2. Check `revoked == False` — passes for both concurrent callers
3. Set `revoked = True` — both callers do this
4. Insert new access + refresh token — both callers do this
5. `COMMIT` — both succeed

Result: two valid access tokens + two valid refresh tokens issued from a single refresh token. Breaks the "single successor" invariant of refresh token rotation.

With the fix, the second caller's `SELECT ... WHERE revoked = false FOR UPDATE` either blocks (until the first commits, then sees zero rows) or immediately returns zero rows — correctly rejecting the duplicate.

### Authorization code race (same pattern, lower risk)

Current flow in `exchange_authorization_code`:
1. `SELECT ... WHERE code = :code` — reads row
2. Check `used == False` — passes for both
3. Set `used = True` + commit
4. Issue tokens

Lower risk because exploiting this requires knowing the `code_verifier` (PKCE), and auth codes are consumed immediately by the OAuth client. But the fix is the same and should be applied for correctness.

## Fix

Add `FOR UPDATE` to the SELECT queries in both functions. This acquires a row-level lock in PostgreSQL that blocks the second concurrent reader until the first transaction commits. The second reader then sees `revoked=True` / `used=True` and correctly rejects.

### File: `backend/core/oauth_provider/services/token_service.py`

**In `exchange_refresh_token`**, change the SELECT:

```python
# BEFORE
result = await db.execute(
    select(OAuthAccessToken).where(
        OAuthAccessToken.refresh_token_hash == refresh_token_hashed
    )
)

# AFTER  
result = await db.execute(
    select(OAuthAccessToken)
    .where(
        OAuthAccessToken.refresh_token_hash == refresh_token_hashed,
        OAuthAccessToken.revoked == False,
    )
    .with_for_update()
)
```

**In `exchange_authorization_code`**, change the SELECT:

```python
# BEFORE
result = await db.execute(
    select(OAuthAuthorizationCode).where(
        OAuthAuthorizationCode.code == code
    )
)

# AFTER
result = await db.execute(
    select(OAuthAuthorizationCode)
    .where(OAuthAuthorizationCode.code == code)
    .with_for_update()
)
```

### What `.with_for_update()` does

- SQLAlchemy translates this to `SELECT ... FOR UPDATE` in PostgreSQL
- Acquires an exclusive row-level lock on the matched row
- Other transactions attempting `SELECT ... FOR UPDATE` on the same row BLOCK until the lock is released (on `COMMIT` or `ROLLBACK`)
- No table-level locking — only the specific row is locked
- No schema changes, no migrations, no new dependencies

### What NOT to change

- No migration needed — this is a query-level change only
- No changes to the OAuthAccessToken or OAuthAuthorizationCode models
- No changes to token creation/storage logic
- No changes to the `/token` endpoint HTTP layer
- No new dependencies

### Performance impact

Negligible. `FOR UPDATE` adds a row-level lock that lasts from SELECT to COMMIT. In normal operation (no concurrent requests for the same token), there is no contention and no measurable overhead. Under concurrent requests for the same token (the attack scenario), the second request waits ~milliseconds for the first to commit — correct behavior.

## Unit Tests

**File: `tests/unit/core/test_token_service_locking.py`** (new)

### Test approach

These tests verify that the SELECT queries use `FOR UPDATE`. Since unit tests with mocked DB sessions can't test actual PostgreSQL locking behavior, the tests verify the query contains the `FOR UPDATE` clause.

1. **test_refresh_token_exchange_uses_for_update** — Call `exchange_refresh_token` with a mock DB session. Capture the first `db.execute()` call argument. Compile the query using PostgreSQL dialect (`statement.compile(dialect=postgresql.dialect())`) and assert the compiled SQL string contains `FOR UPDATE`. Do NOT compile with the default dialect (SQLite won't emit `FOR UPDATE`).

2. **test_authorization_code_exchange_uses_for_update** — Call `exchange_authorization_code` with a mock DB session. Capture the first `db.execute()` call argument. Assert the compiled SQL string contains `FOR UPDATE`.

3. **test_refresh_token_revoked_after_lock** — Mock DB returns a token row with `revoked=False`. After `exchange_refresh_token` completes, assert `matching_token.revoked == True` and `matching_token.revoked_at` is set. This confirms the read-lock-validate-revoke sequence is intact.

4. **test_authorization_code_used_after_lock** — Mock DB returns a code row with `used=False`. After `exchange_authorization_code` completes, assert `auth_code.used == True`. Same validation for the auth code path.

## Integration Tests

5. **test_concurrent_refresh_token_exchange_one_succeeds** — This is the critical race condition test. Requires a real database (or at minimum, a database that supports `FOR UPDATE`).

Setup: Create a valid OAuthAccessToken row with a known refresh token hash.

Test: Launch two concurrent `exchange_refresh_token` calls with the same refresh token and client_id using `asyncio.gather`. **Each call MUST use its own independent `AsyncSession` instance** — if they share a session, they share a transaction and `FOR UPDATE` is never exercised.

Assert: Exactly one call returns a success dict with `access_token`. The other returns `("invalid_grant", "Invalid refresh token")` (because the `revoked == False` filter now excludes it). Assert only one new OAuthAccessToken row was created.

**Note for Claude Code**: This test requires the actual async database session (not a mock) to validate PostgreSQL row locking. If the test infrastructure doesn't support real DB integration tests, this test can be marked `@pytest.mark.integration` and skipped in unit test runs.

## Acceptance Criteria

- [ ] `exchange_refresh_token` SELECT uses `.with_for_update()` and filters `revoked == False`
- [ ] `exchange_authorization_code` SELECT uses `.with_for_update()`
- [ ] No schema changes, no migrations
- [ ] No changes to token creation/storage logic
- [ ] Unit tests verify `FOR UPDATE` in compiled SQL (2 tests)
- [ ] Unit tests verify revocation/usage flag set after exchange (2 tests)
- [ ] Integration test verifies concurrent refresh → only one succeeds (1 test, may be marked integration-only)
- [ ] All existing token exchange tests pass (no regression)
- [ ] No new dependencies

## Files to Modify

| File | Change |
|---|---|
| `backend/core/oauth_provider/services/token_service.py` | Add `.with_for_update()` to two SELECT queries |
| `tests/unit/core/test_token_service_locking.py` | 4 new unit tests |
| `tests/integration/test_token_concurrent.py` | 1 new integration test (optional if no DB test infra) |

## Files NOT to Touch

- `backend/core/oauth_provider/models.py` — no model changes
- `backend/core/oauth_provider/token_endpoint.py` — HTTP layer unchanged
- `backend/alembic/versions/` — no migration needed
- Any MCP server code
- Any other OAuth endpoint

## ADR

No ADR needed. `SELECT ... FOR UPDATE` is the standard PostgreSQL solution for read-then-write race conditions. No alternative approaches were seriously considered because this is the canonical fix.

## Reference

- **Audit source:** HIGH-001 from automated security audit + ChatGPT/Claude review confirmation
- **PostgreSQL docs:** [Explicit Locking — Row-Level Locks](https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-ROWS)
- **SQLAlchemy docs:** [Query.with_for_update()](https://docs.sqlalchemy.org/en/20/orm/queryguide/api.html#sqlalchemy.orm.Query.with_for_update)
