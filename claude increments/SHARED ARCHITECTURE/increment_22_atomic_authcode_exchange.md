# Increment 22: Atomic Authorization Code Exchange

## Context

Shared backend. `backend/core/oauth_provider/services/token_service.py`.

Increment 21 added `FOR UPDATE` row locking to both token exchange flows. The refresh token flow (`exchange_refresh_token`) is already atomic — lock, revoke, insert new token, single commit. The authorization code flow (`exchange_authorization_code`) is not: it commits twice.

## Problem

Current `exchange_authorization_code` flow:

1. `SELECT ... FOR UPDATE` — lock auth code row
2. Validate (expiry, used, PKCE, client_id, redirect_uri)
3. Mark `auth_code.used = True`
4. **`await db.commit()`** ← first commit (releases lock)
5. Generate access token + refresh token
6. Insert `OAuthAccessToken` record
7. **`await db.commit()`** ← second commit

If step 6 or 7 fails (DB error, constraint violation, connection drop):
- Auth code is permanently marked `used = True` (commit 1 succeeded)
- No tokens are issued to the client
- Client receives an error
- User must restart the entire OAuth flow (re-authorize)

This is not a security vulnerability. It is a resilience gap. The refresh token flow does not have this problem because it uses a single commit.

## Fix

Merge both commits into one. Mark `used = True`, generate tokens, insert token record, then commit once. If anything fails, the entire transaction rolls back — auth code stays `used = False`, user can retry.

### File: `backend/core/oauth_provider/services/token_service.py`

**In `exchange_authorization_code`**, remove the first `await db.commit()` after `auth_code.used = True`. The single commit at the end (after `db.add(access_token_record)`) handles everything atomically.

**Before (two commits):**
```
auth_code.used = True
await db.commit()          # ← REMOVE THIS

# ... generate tokens ...

db.add(access_token_record)
await db.commit()
```

**After (single commit):**
```
auth_code.used = True

# ... generate tokens ...

db.add(access_token_record)
await db.commit()          # ← single atomic commit
```

This matches the pattern already used in `exchange_refresh_token`.

### What NOT to change

- `exchange_refresh_token` — already atomic, do not touch
- No model changes
- No migration
- No new dependencies
- No changes to validation logic
- No changes to token generation logic
- `FOR UPDATE` stays exactly as-is

## Unit Tests

**File: `tests/unit/core/test_token_service_atomicity.py`** (new)

### 1. test_authcode_exchange_single_commit

Call `exchange_authorization_code` with a valid mocked auth code. Count the number of `db.commit()` calls. Assert exactly 1 commit call.

### 2. test_authcode_exchange_rollback_on_token_insert_failure

Mock `db.add()` to raise an exception (simulating token insert failure). Call `exchange_authorization_code`. Assert that `auth_code.used` is still `False` (the transaction was not committed). Assert the function returns an error tuple.

**Implementation note for test 2:** Since SQLAlchemy tracks dirty attributes in-memory before commit, `auth_code.used` will be `True` in the Python object even if the commit never happens. The real assertion is that `db.commit()` was never called (0 commit calls). Alternatively, wrap in a try/except that calls `db.rollback()` and verify the rollback path. Choose whichever pattern matches the existing test infrastructure.

### 3. test_refresh_token_exchange_still_single_commit

Regression guard. Call `exchange_refresh_token` with a valid mocked token. Assert exactly 1 commit call. This ensures nobody accidentally introduces a second commit in the refresh flow.

## Integration Tests

No new integration tests needed. The existing concurrent exchange integration test from Increment 21 (`test_concurrent_refresh_token_exchange_one_succeeds`) already validates locking correctness. This increment only changes commit boundaries, not locking behavior.

## Acceptance Criteria

- [ ] `exchange_authorization_code` has exactly ONE `await db.commit()` call
- [ ] The single commit occurs AFTER both `auth_code.used = True` AND `db.add(access_token_record)`
- [ ] `exchange_refresh_token` remains unchanged (already correct)
- [ ] Unit test: single commit count verified
- [ ] Unit test: no commit on token insert failure
- [ ] Unit test: refresh flow still single commit (regression guard)
- [ ] All existing token exchange tests pass (no regression)
- [ ] No new dependencies, no migration, no model changes

## Files to Modify

| File | Change |
|---|---|
| `backend/core/oauth_provider/services/token_service.py` | Remove first `await db.commit()` in `exchange_authorization_code` |
| `tests/unit/core/test_token_service_atomicity.py` | 3 new unit tests |

## Files NOT to Touch

- `exchange_refresh_token` in same file — already atomic
- `backend/core/oauth_provider/models.py`
- `backend/core/oauth_provider/token_endpoint.py`
- `backend/alembic/versions/`
- Any MCP server code
- Any test files from Increment 21

## Pre-Deploy

Read `doc/OPERATIONS_PREDEPLOY.md` and check for additional pre-deploy tasks.

## Risk

Minimal. This removes one line (`await db.commit()`) and relies on the existing second commit to handle everything. The `FOR UPDATE` lock is held slightly longer (from SELECT until the single commit instead of releasing at the first commit), but this is negligible — token generation is sub-millisecond.
