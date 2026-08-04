# ADR-002: Per-User Token Refresh Lock Eviction Strategy

**Date:** 2026-03-01

**Scope:** Shared Backend (`backend/core/google_token_management.py`) — affects all SDK apps using Google OAuth (Priority Guardian, potentially Clarity, Focused)

**Status:** Accepted

---

## Context

`ensure_valid_access_token()` uses an in-memory `dict[str, asyncio.Lock]` to deduplicate concurrent Google token refresh calls for the same user. Without locking, N concurrent coroutines detecting an expired token would all call Google's token endpoint simultaneously — wasteful and risks rate limiting.

The dict grows by one entry per unique user who triggers a token refresh during the process lifetime. The current eviction strategy clears *all* locks atomically when the dict exceeds 10,000 entries:

```python
if len(_user_refresh_locks) > 10000:
    _user_refresh_locks.clear()
```

**Problem:** The atomic clear creates a brief window where *all* users simultaneously lose deduplication protection. If multiple users happen to refresh tokens during this window, each gets redundant concurrent calls — a thundering herd. The probability is low at small scale but violates correctness under high load.

## Decision

**Replace atomic clear with time-based LRU eviction.**

Each lock entry tracks its last-used timestamp. On every access, entries older than `LOCK_TTL` (30 minutes) are lazily evicted. Google access tokens expire after 1 hour; a lock unused for 30 minutes is provably stale (the token it protected has either been refreshed or the user is inactive).

**Eviction rules:**
1. **On access**: Record `last_used` timestamp for the accessed user's lock.
2. **On access (lazy cleanup)**: If dict size exceeds `MAX_LOCK_ENTRIES` (10,000), evict all entries with `last_used` older than `LOCK_TTL` (30 minutes).
3. **Hard cap**: If after TTL eviction the dict still exceeds `MAX_LOCK_ENTRIES`, evict oldest entries until at `MAX_LOCK_ENTRIES * 0.8` (8,000). This handles the theoretical edge case of 10,000+ users all active within the TTL window.
4. **No lock is ever evicted while held** (asyncio.Lock with `locked()` check before eviction).
5. **Bounded insert**: If eviction cannot free space (all locks held), no new entry is stored. A local lock is used for that call only — the user loses cross-coroutine dedup for one call, but memory stays bounded.

**Why not LRU cache / `cachetools.TTLCache`?**
- `functools.lru_cache` doesn't support TTL.
- `cachetools.TTLCache` is a new dependency for one dict. The eviction logic is ~15 lines — simpler to inline.

**Why not Redis distributed lock?**
- Redis lock would be correct across multiple workers/containers, but adds latency to every token check (Redis round-trip vs in-memory dict lookup).
- Current deployment is single-worker on Render. When horizontal scaling is needed, this should be revisited (see "Scaling Note" below).
- The Shared Backend Architecture diagram mentions "distributed Redis lock to prevent race conditions" — this is aspirational for multi-worker deployment, not current implementation.

## Consequences

- **No thundering herd window.** Locks are evicted individually based on staleness, never all at once.
- **Bounded memory.** Hard cap at 10,000 entries with soft eviction at 30-minute TTL. Dict never grows past MAX even under pathological load (failed eviction → local lock fallback).
- **Negligible overhead.** Lazy eviction only triggers when dict exceeds threshold. Timestamp check is O(n) but n ≤ 10,000 and runs infrequently.
- **Single-process only.** This remains an in-process optimization. Multiple workers will have independent lock dicts — acceptable for current scale (redundant refreshes across workers are rare and harmless).

## Scaling Note

When deploying multiple workers (Render auto-scaling, multiple containers), the per-user lock should migrate to a Redis-based pattern (e.g., `SET user:{id}:refresh_lock NX EX 30`). This ADR will be superseded at that point. The threshold for this migration is when redundant cross-worker refresh calls cause observable Google API rate limiting — estimated at 1,000+ concurrent users.

## Implementation

- **File:** `backend/core/google_token_management.py`
- **Data structure:** `dict[str, tuple[asyncio.Lock, float]]` where float is `time.monotonic()` timestamp
- **Constants:** `LOCK_TTL_SECONDS = 1800` (30 min), `MAX_LOCK_ENTRIES = 10000`, `EVICTION_TARGET_RATIO = 0.8`
