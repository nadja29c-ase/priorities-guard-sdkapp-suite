# Increment 35B: Token Refresh Lock — TTL-Based Eviction

## Context

Shared backend infrastructure. `backend/core/google_token_management.py` is used by all SDK apps with Google OAuth.

Increment 35 introduced per-user `asyncio.Lock` to deduplicate concurrent Google token refreshes. The eviction strategy clears **all** locks atomically when the dict exceeds 10,000 entries. This creates a brief thundering herd window where every user simultaneously loses deduplication.

**Decision documented in:** `doc/ADR_002_token_refresh_lock_eviction.md`

## Problem (Specific)

```python
if len(_user_refresh_locks) > 10000:
    _user_refresh_locks.clear()
```

Atomic clear = all users lose lock protection simultaneously. If multiple users happen to refresh during this window, each gets redundant concurrent Google API calls.

## Fix

Replace atomic clear with **lazy TTL-based eviction**. Each lock entry tracks its last-used timestamp. Stale entries (unused for 30 minutes) are evicted individually on access. Google access tokens expire after 60 minutes — a lock unused for 30 minutes is provably stale.

## What to Change

**File:** `backend/core/google_token_management.py`

### Data structure change

Replace:
```python
_user_refresh_locks: dict[str, asyncio.Lock] = {}
```

With a dict storing `(lock, last_used_timestamp)` tuples using `time.monotonic()`:
```python
_user_refresh_locks: dict[str, tuple[asyncio.Lock, float]] = {}
```

### Constants to add

```
LOCK_TTL_SECONDS = 1800       # 30 minutes
MAX_LOCK_ENTRIES = 10000
EVICTION_TARGET_RATIO = 0.8   # evict down to 80% of max
```

### Eviction logic (replaces the `if len > 10000: clear()` block)

Eviction is called in exactly ONE place: **before inserting a new key, when `len(_user_refresh_locks) >= MAX_LOCK_ENTRIES`**. Updating the timestamp of an existing entry never triggers eviction.

`_evict_stale_locks()` algorithm:
1. **TTL pass**: Snapshot keys via `list(_user_refresh_locks.items())` before iterating. Remove all entries where `now - last_used > LOCK_TTL_SECONDS` AND `lock.locked() is False`. Never mutate dict while iterating directly over `.items()`.
2. **Hard cap pass** (only if still `>= MAX_LOCK_ENTRIES` after step 1): Build a list of unheld entries (`lock.locked() is False`), sorted by `last_used` ascending. Pop from that list until `len(_user_refresh_locks) <= MAX_LOCK_ENTRIES * EVICTION_TARGET_RATIO` or list exhausted. This guarantees termination.
3. **Graceful degradation**: If insufficient unheld entries exist to reach target ratio, eviction stops. Never evict held locks. Never loop indefinitely.
4. **Bounded insert**: After `_evict_stale_locks()` returns, re-check `len(_user_refresh_locks)`. If still `>= MAX_LOCK_ENTRIES`, do NOT insert a new lock entry. Instead, create a local `asyncio.Lock()` (not stored in the dict) and use it for this call only. The user loses cross-coroutine dedup for this single call — acceptable tradeoff for bounded memory.

### Type alias

Define at module level for readability:
```python
LockEntry = tuple[asyncio.Lock, float]  # (lock, last_used_monotonic)
```

Use `LockEntry` in the type annotation and throughout.

### Get-or-create pattern update

The existing get-then-set pattern stays, but now stores the tuple. **Important:** run eviction *before* inserting a new key to avoid transient growth above `MAX_LOCK_ENTRIES`:

```python
user_key = str(connection.user_id)
entry = _user_refresh_locks.get(user_key)
if entry is not None:
    lock, _ = entry
    _user_refresh_locks[user_key] = (lock, time.monotonic())  # update timestamp
else:
    # Run eviction BEFORE insert if at or above MAX_LOCK_ENTRIES
    if len(_user_refresh_locks) >= MAX_LOCK_ENTRIES:
        _evict_stale_locks()
    if len(_user_refresh_locks) >= MAX_LOCK_ENTRIES:
        # Eviction couldn't free space — use local lock, don't grow dict
        lock = asyncio.Lock()
        # NOT stored in _user_refresh_locks
    else:
        lock = asyncio.Lock()
        _user_refresh_locks[user_key] = (lock, time.monotonic())
```

### Eviction must be synchronous (non-async)

The eviction function must NOT contain any `await` calls. This prevents task-switching mid-mutation and keeps the dict consistent under asyncio concurrency. Pure synchronous iteration + deletion only.

### Import needed

Add `import time` (for `time.monotonic()`). `asyncio` is already imported.

## What NOT to Change

- Function signature and return contract of `ensure_valid_access_token` — unchanged
- The `async with lock:` block and everything inside it — unchanged
- `session.refresh(connection)` pattern inside lock — unchanged
- Callers (calendar_service.py, weekly_report_service.py) — unchanged
- No new dependencies

## Unit Tests

**File:** `tests/unit/core/test_google_token_management.py`

Add a new test class `TestLockEviction`. These tests access the module-level `_user_refresh_locks` dict directly for setup and assertions.

**Important:** Use a pytest fixture (autouse within the test class or module-scoped) that clears `_user_refresh_locks` before and after each test. All time-dependent tests must use `monkeypatch` to patch `time.monotonic` for deterministic assertions — never assert "approximately now".

### Tests

**All tests must monkeypatch constants to small values** (e.g., `MAX_LOCK_ENTRIES=10`, `LOCK_TTL_SECONDS=30`) to keep runtime tiny and deterministic. Do not iterate over 10,000 entries in tests.

1. **test_stale_lock_evicted_on_overflow** — Populate dict with exactly `MAX_LOCK_ENTRIES` stale entries (all `last_used` expired via monkeypatched `time.monotonic`). Access a new user (triggers eviction-before-insert). Assert all stale entries removed. Assert the new user's lock exists.

2. **test_fresh_lock_not_evicted** — Populate dict with exactly `MAX_LOCK_ENTRIES` fresh entries. Access a new user. Assert hard cap fallback kicks in — oldest unheld entries evicted down to target ratio. Assert the new user's lock exists.

3. **test_held_lock_never_evicted** — Populate dict at capacity. Acquire one lock directly with `await lock.acquire()` (no background task — deterministic). Access a new user to trigger eviction. Assert the held lock survives eviction even if its timestamp is stale. Release lock in `finally` block.

4. **test_timestamp_updated_on_access** — Use `monkeypatch` to patch `time.monotonic` to return controlled values (e.g., 1000.0 then 2000.0). Create a lock entry at t=1000.0. Access the same user's lock at t=2000.0. Assert `last_used` timestamp equals exactly 2000.0. Assert no eviction ran (existing key path).

5. **test_eviction_does_not_run_below_threshold** — Populate dict with `MAX_LOCK_ENTRIES - 1` entries, some stale. Access a new user. Assert no stale entries were evicted (below capacity, no eviction triggered).

6. **test_no_insert_when_at_cap_and_all_held** — Populate dict at capacity with all locks acquired. Access a new user to trigger eviction. Assert: dict size unchanged (no new entry inserted). Assert: the function still returns a valid result (local lock used, no exception). Release all locks in `finally`.

6. **test_existing_concurrent_tests_still_pass** — This is not a new test, but a reminder: run all existing `TestConcurrentRefresh` tests to verify no regression.

## Integration Tests

None needed. This is an in-process memory management change with no external side effects.

## Acceptance Criteria

- [ ] `_user_refresh_locks` stores `tuple[asyncio.Lock, float]` (lock + monotonic timestamp)
- [ ] Timestamp updated on every lock access
- [ ] Eviction only triggers when inserting a new key AND `len >= MAX_LOCK_ENTRIES` (existing-key timestamp updates never trigger eviction)
- [ ] TTL eviction removes entries older than `LOCK_TTL_SECONDS` that are not held
- [ ] Hard cap fallback evicts oldest unheld entries to `EVICTION_TARGET_RATIO` of max
- [ ] Held locks (`lock.locked() is True`) are never evicted
- [ ] No atomic `clear()` anywhere in the module
- [ ] Constants defined at module level: `LOCK_TTL_SECONDS`, `MAX_LOCK_ENTRIES`, `EVICTION_TARGET_RATIO`
- [ ] All 6 new eviction tests pass
- [ ] Eviction never loops indefinitely; if insufficient evictable entries exist, it exits
- [ ] If dict still `>= MAX_LOCK_ENTRIES` after eviction, new entry is NOT inserted (local lock used instead)
- [ ] Dict size never exceeds `MAX_LOCK_ENTRIES` + number of concurrently held locks at time of last successful insert
- [ ] Eviction iterates over a snapshot (`list(...)`) — never mutates dict while iterating
- [ ] Eviction function is synchronous (no `await` calls)
- [ ] `LockEntry` type alias defined at module level
- [ ] Eviction runs before insert (not after) when at capacity
- [ ] All existing `TestConcurrentRefresh` tests pass (no regression)
- [ ] All existing `TestEnsureValidAccessToken` tests pass
- [ ] `import time` added
- [ ] No new external dependencies

## Files to Modify

| File | Change |
|---|---|
| `backend/core/google_token_management.py` | Replace atomic clear with TTL-based eviction, update data structure to store timestamps |
| `tests/unit/core/test_google_token_management.py` | Add `TestLockEviction` class with 6 tests |

## Files NOT to Touch

Everything else. This is a surgical change to one module's memory management.

## Reference

- **ADR:** `doc/ADR_002_token_refresh_lock_eviction.md`
- **Original increment:** `claude increments/SHARED ARCHITECTURE/google_token_refresh_race.md` (Increment 35)
