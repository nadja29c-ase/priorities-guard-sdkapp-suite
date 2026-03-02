# Increment 35: Google Token Refresh Race Condition Fix

## Context

This fixes a race condition in `backend/core/google_token_management.py`, which is **shared backend infrastructure** used by all SDK apps that integrate Google Calendar. Currently only Priority Guardian calls it (via `calendar_service.py` and `weekly_report_service.py`), but Focused also imports it.

## Problem

`ensure_valid_access_token()` has no concurrency protection. When two concurrent requests for the same user both detect an expired token, both execute the full refresh flow independently:

```
Request A: check expiry → expired → decrypt refresh token → call Google refresh API → encrypt new token → session.commit()
Request B: check expiry → expired → decrypt refresh token → call Google refresh API → encrypt new token → session.commit()
```

### Impact assessment (corrected)

**Google does NOT invalidate refresh tokens on use** for server-side apps. Both refreshes will succeed and return valid (different) access tokens. So this is NOT a "one fails with REFRESH_TOKEN_INVALID" scenario.

The actual problems are:

1. **Redundant API calls under load** — N concurrent expired-token requests = N Google API calls. Google enforces per-user rate limits on token refreshes. Under load (e.g., snapshot scheduler running for many users), this burns quota unnecessarily.

2. **Stale token overwrite** — Request A refreshes first, gets token with `expires_in=3599`. Request B refreshes second, gets token with `expires_in=3600`. But if Request A's `session.commit()` runs AFTER Request B's, it writes the older token. The overwritten token is still valid (both are fresh), so this is a minor inefficiency, not a correctness bug.

3. **Wasted compute** — Each refresh involves decryption, HTTP call with potential retries, encryption, and a DB write. Doing this N times when once suffices is wasteful.

### Severity

Moderate. Not a security vulnerability or data loss risk. It's a resource waste and potential rate-limit issue under concurrent load. Worth fixing because the shared backend is designed for multiple SDK apps, and the problem scales with concurrent users.

## How concurrency happens

In PG today, concurrent calls to `ensure_valid_access_token` for the same user can occur when:

- `weekly_report_service` and `calendar_service` are called simultaneously (e.g., user triggers weekly report while widget refreshes priorities)
- Future: snapshot scheduler processes a user while they're also using the app
- Future: multiple SDK apps share the same Google connection

All callers load their own `CoreConnection` instance via `select(...).where(user_id=X, provider="google")`. In FastAPI with dependency injection, each request gets its own `AsyncSession`, so concurrent requests have separate session and ORM instances pointing at the same DB row. The `session.refresh(connection)` inside the lock re-reads the row from DB, picking up any commit from another session.

## Fix: Per-user asyncio lock

Add a per-user `asyncio.Lock` in `google_token_management.py`. When multiple coroutines try to refresh the same user's token concurrently, only the first acquires the lock and performs the refresh. The rest wait, then find a fresh token and skip the refresh.

### Why asyncio.Lock (not Redis lock)

- The backend runs as a single async process (uvicorn). All concurrent requests for one user are coroutines in the same event loop.
- Redis distributed locks add complexity, latency, and a Redis dependency for a problem that exists within a single process.
- If the backend scales to multiple workers/processes in the future, upgrade to Redis lock then. The interface (acquire lock → check → refresh → release) stays the same.

### Implementation approach

Add a module-level dict of per-user locks:

```python
_user_refresh_locks: dict[str, asyncio.Lock] = {}
```

At the start of `ensure_valid_access_token`, before checking expiry:

1. Get or create a lock for `connection.user_id` — use explicit get-then-set (do NOT use `setdefault(key, asyncio.Lock())` — it allocates a throwaway Lock on every call even when the key exists):
   ```python
   user_key = str(connection.user_id)
   lock = _user_refresh_locks.get(user_key)
   if lock is None:
       lock = asyncio.Lock()
       _user_refresh_locks[user_key] = lock
   ```
2. Acquire the lock
3. Inside the lock, **refresh the SQLAlchemy object from DB**: `await session.refresh(connection)` — this is critical because the second coroutine holds a stale object from before the first coroutine's `session.commit()`. Without this, the re-check reads stale `token_expires_at` and the double-check pattern is defeated.
4. Re-check `connection.token_expires_at` — if another coroutine already refreshed, it will now be in the future
5. If still expired, proceed with refresh as before
6. If now valid (another coroutine refreshed), decrypt and return the fresh token

The lock dict will grow unboundedly if not cleaned. However, in practice the number of concurrent users is bounded by active connections. For production safety, add a simple size check: if the dict exceeds 10,000 entries, clear it entirely (locks are cheap to recreate, and a stale lock just means one redundant refresh).

### What changes in ensure_valid_access_token

The function signature and return contract stay identical. The only behavioral change is that concurrent calls for the same user are serialized.

**Before:**
```
check expiry → if expired → refresh → commit → return
```

**After:**
```
acquire user lock → session.refresh(connection) → re-check expiry → if still expired → refresh → commit → return → release lock
                                                                   → if now valid → decrypt → return → release lock
```

### Lock cleanup

Do NOT add a background task or TTL-based cleanup. A simple size-based eviction is sufficient:

```python
if len(_user_refresh_locks) > 10000:
    _user_refresh_locks.clear()
```

This runs before creating a new lock entry. The worst case is one redundant refresh after a clear — acceptable.

### What NOT to change

- Do NOT change `refresh_access_token` in `google_calendar.py`
- Do NOT change the callers (`calendar_service.py`, `weekly_report_service.py`)
- Do NOT add Redis dependency for this fix
- Do NOT change the function signature or return types of `ensure_valid_access_token`
- Do NOT add the lock import at the top level — `asyncio` is already imported in the module (verify; if not, add it)

### Constraint: No sensitive data in logs

The existing logging is fine. Do not add logging that includes token values, refresh tokens, or encrypted blobs. Logging `user_id` and "acquired lock" / "skipped refresh" events at `debug` level is acceptable.

---

## Unit Tests

### File: `tests/unit/core/test_google_token_management.py` (existing — add tests)

Add a new test class `TestConcurrentRefresh` to the existing file.

All tests mock `decrypt_token`, `refresh_access_token`, and `encrypt_token` as the existing tests do.

1. **test_concurrent_refresh_only_calls_google_once** — Create an expired connection. Launch two concurrent calls to `ensure_valid_access_token` using `asyncio.gather`. Mock `refresh_access_token` to track call count (add a small `asyncio.sleep(0.01)` inside the mock to simulate network latency and ensure both coroutines reach the lock). Assert `refresh_access_token` was called exactly **once**. Assert both calls return `{"access_token": ...}` (not an error).

2. **test_second_caller_gets_refreshed_token** — Create two separate expired connection mocks (simulating two requests loading the same DB row independently). The mock `refresh_access_token` returns `{"access_token": "new_token", "expires_in": 3600}`. Mock `session.refresh()` so that when the second caller's session refreshes its connection instance, `token_expires_at` is updated to a future time (simulating the first caller's DB commit being visible). Launch two concurrent calls. Assert `refresh_access_token` was called exactly **once**. Assert both calls return a valid access token.

3. **test_lock_does_not_block_different_users** — Create two expired connections for different user IDs. Launch concurrent refreshes for both. Assert `refresh_access_token` was called **twice** (once per user). Locks are per-user and should not interfere.

4. **test_lock_cleanup_on_overflow** — This is a functional test of the size-based eviction. Populate `_user_refresh_locks` with 10,001 entries. Call `ensure_valid_access_token` for a new user. Assert the dict was cleared and a new lock was created. (Access the module-level dict directly via `from backend.core.google_token_management import _user_refresh_locks`.)

---

## Acceptance Criteria

- [ ] `ensure_valid_access_token` uses per-user `asyncio.Lock` via get-then-set pattern (not `setdefault`)
- [ ] `await session.refresh(connection)` called inside lock before re-checking expiry
- [ ] Second concurrent caller re-checks expiry after acquiring lock and session refresh
- [ ] Lock dict has size-based eviction (10,000 threshold)
- [ ] `refresh_access_token` call count is 1 when two concurrent calls hit expired token
- [ ] Different users' refreshes are not blocked by each other
- [ ] Function signature and return contract unchanged
- [ ] No new dependencies added
- [ ] All existing `test_google_token_management.py` tests still pass
- [ ] 4 new concurrency tests pass
- [ ] No sensitive data in new log statements

## Files to Modify

| File | Change |
|---|---|
| `backend/core/google_token_management.py` | Add per-user lock dict, wrap refresh logic in lock, add re-check after lock acquisition, add size-based eviction |
| `tests/unit/core/test_google_token_management.py` | Add `TestConcurrentRefresh` class with 4 tests |

## Files NOT to Touch

- `backend/core/google_calendar.py` — refresh API logic unchanged
- `backend/apps/priority_guardian/services/calendar_service.py` — caller unchanged
- `backend/apps/priority_guardian/services/weekly_report_service.py` — caller unchanged
- `backend/core/redis_client.py` — no Redis involvement
- MCP server code — no changes
