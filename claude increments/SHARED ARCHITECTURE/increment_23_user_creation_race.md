# Increment 23: Fix Concurrent User Creation Race Condition

## Context

Shared backend. `backend/core/oauth_provider/authorize.py`, function `_resolve_user_identity`.

`core_users.chatgpt_user_id` has a `UNIQUE` constraint. When two concurrent `/authorize` requests arrive with the same `login_hint` for a first-time user, both see no existing row, both attempt INSERT, and the second hits `IntegrityError` → unhandled 500.

## Problem

Current flow in `_resolve_user_identity` (Priority 1 branch):

1. `SELECT ... WHERE chatgpt_user_id = :id` → returns None (user doesn't exist yet)
2. `CoreUser(chatgpt_user_id=chatgpt_user_id)` → create new
3. `db.add(user)` + `await db.commit()` → INSERT

If two requests execute step 1 before either reaches step 3, both see None and both attempt INSERT. The second commit violates the UNIQUE constraint on `chatgpt_user_id` and raises `sqlalchemy.exc.IntegrityError`. This propagates as a 500 to the user.

Probability is low at current scale but non-zero — OpenAI can retry `/authorize` or a user can double-click.

## Fix

Catch `IntegrityError` on the INSERT, rollback, and re-fetch the row that the other transaction already created.

**File:** `backend/core/oauth_provider/authorize.py`

Add `IntegrityError` to imports:

```python
from sqlalchemy.exc import IntegrityError
```

In `_resolve_user_identity`, replace the user creation block in Priority 1:

**Current code:**
```python
# Create new user with chatgpt_user_id
user = CoreUser(chatgpt_user_id=chatgpt_user_id)
db.add(user)
await db.commit()
await db.refresh(user)
```

**New code (same location):**
```python
# Create new user with chatgpt_user_id
# Handle race: concurrent request may have created this user between
# our SELECT and INSERT. Catch UNIQUE violation, rollback, re-fetch.
try:
    user = CoreUser(chatgpt_user_id=chatgpt_user_id)
    db.add(user)
    await db.commit()
    await db.refresh(user)
except IntegrityError:
    await db.rollback()
    result = await db.execute(
        select(CoreUser).where(CoreUser.chatgpt_user_id == chatgpt_user_id)
    )
    user = result.scalar_one()
    request_logger.info(
        "oauth.authorize.user_found_after_race",
        user_id=str(user.id),
        identity_source="login_hint",
    )
    return user
```

The `scalar_one()` (not `scalar_one_or_none()`) is intentional — if we got an IntegrityError, the row MUST exist. If it doesn't, something is seriously wrong and we should fail loudly.

### What NOT to change

- Priority 2 (session cookie) and Priority 3 (anonymous user) branches — anonymous users have `chatgpt_user_id=NULL`, and PostgreSQL allows multiple NULLs in a UNIQUE column, so no race there
- No model changes, no migration
- No changes to session service, token service, or consent endpoint
- No new dependencies (IntegrityError is already in sqlalchemy)

## Unit Tests

**File:** `tests/unit/core/test_user_creation_race.py` (new)

### 1. test_concurrent_login_hint_second_request_succeeds

Mock `db.commit()` to raise `IntegrityError` on first call (simulating the losing racer). Mock a second `db.execute()` call to return a valid `CoreUser`. Call `_resolve_user_identity` with a `chatgpt_user_id`. Assert:
- `db.rollback()` was called exactly once
- Function returns a valid `CoreUser` (not an exception)
- The returned user has the correct `chatgpt_user_id`

### 2. test_normal_first_time_user_no_race

Mock `db.commit()` to succeed normally. Call `_resolve_user_identity` with a `chatgpt_user_id` that doesn't exist. Assert:
- `db.rollback()` was NOT called
- Function returns a new `CoreUser`
- `db.add()` was called

### 3. test_existing_user_no_insert_attempted

Mock `db.execute()` to return an existing `CoreUser` on the initial SELECT. Call `_resolve_user_identity`. Assert:
- `db.add()` was NOT called
- `db.commit()` was NOT called (no write needed)
- Function returns the existing user

## Integration Tests

No new integration test needed. The unit tests cover the logic branch. A real concurrent test would require two async sessions hitting the same database simultaneously — that's infrastructure-heavy for a low-probability edge case that the unit tests already validate.

## Acceptance Criteria

- [ ] `IntegrityError` import added
- [ ] User creation in Priority 1 branch wrapped in try/except IntegrityError
- [ ] On IntegrityError: rollback, re-fetch with `scalar_one()`, return user
- [ ] Log event `oauth.authorize.user_found_after_race` on race recovery
- [ ] Priority 2 and Priority 3 branches unchanged
- [ ] No model changes, no migration
- [ ] 3 unit tests pass
- [ ] All existing authorize tests pass (no regression)

## Files to Modify

| File | Change |
|---|---|
| `backend/core/oauth_provider/authorize.py` | Add IntegrityError import, wrap user creation in try/except |
| `tests/unit/core/test_user_creation_race.py` | 3 new unit tests |

## Files NOT to Touch

- `backend/core/models.py`
- `backend/core/oauth_provider/consent_ui.py`
- `backend/core/oauth_provider/services/token_service.py`
- `backend/core/oauth_provider/services/session_service.py`
- Any MCP server code
- Any migration

## Pre-Deploy

Read `doc/OPERATIONS_PREDEPLOY.md` and check for additional pre-deploy tasks.

## Risk

Minimal. The happy path is unchanged. The new code only executes when an IntegrityError occurs — which means a concurrent INSERT already succeeded. The rollback + re-fetch is the standard PostgreSQL pattern for this scenario.
