# PG Calendar Increment: Time Allocation Pipeline

## Objective

Build the backend calendar data pipeline that computes per-priority time allocation from Google Calendar events. After this increment: the MCP `get_priorities` tool response includes `weeklyHourActual` per priority and a `timeAllocation` block. The backend `GET /priorities` endpoint remains unchanged (DB-only, no calendar calls). No widget changes — data flows but is not yet rendered.

This is the **prerequisite for Widget Increment C** (Time Allocation Bar).

---

## What Exists

### Shared Core (reuse directly)
- `backend/core/google_calendar.py` — `fetch_events()`: fetches events from Google Calendar API with retry logic, rate limit handling, auth error detection. **Fully reusable as-is.**
- `backend/core/models.py` — `CoreConnection` model: stores Google OAuth tokens (encrypted), scopes, `token_expires_at`, `revoked_at`.
- `backend/core/encryption.py` — `decrypt_token()`, `encrypt_token()`: AES-256-GCM token encryption. Used by Focused, reusable.

### Focused App (pattern to adapt, NOT import)
- `backend/apps/focused/logic_googletokens.py` — `ensure_valid_access_token()`: checks expiry, auto-refreshes via `refresh_access_token()`, updates DB. **This function is app-agnostic** (operates on `CoreConnection`, no Focused-specific imports). It needs to be extracted to shared core so PG can use it without cross-app imports.
- `backend/apps/focused/tools/check_calendar_impl.py` — Focused's calendar pipeline: load connection → ensure token → fetch events → match keywords → return blocks. **PG follows the same flow** but with different matching logic and duration computation.
- `backend/apps/focused/tools/helpers/keyword_utils.py` — `normalize()` and `matches_focus_keywords()`: case-insensitive keyword matching against event titles. PG reuses `normalize()` for whitespace handling but replaces Focused's substring `in` check with word-boundary regex (`\bP[123]\b`) to prevent false positives like "AP1" or "P10".

### PG Backend (current state)
- `backend/apps/priority_guardian/routers/priorities_router.py` — `GET /priorities` with `build_priorities_response()`. Currently returns `weekly_hour_actual: None` (placeholder). This increment populates it.
- `backend/apps/priority_guardian/pg_config.py` — `GOOGLE_CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events.readonly"` (already defined).
- `backend/apps/priority_guardian/db_models.py` — `PgPriority` has `calendar_keyword` field (P1/P2/P3).

### PG MCP Server (current state)
- `mcp_server/priority_guardian/tools/get_priorities.py` — `_normalize_priority()` maps `weekly_hour_actual` from backend. Currently always None.

---

## Architecture Decision: Where Calendar Logic Lives

**Calendar data is computed in a separate backend endpoint, not inline in `build_priorities_response()`.**

Rationale: `build_priorities_response()` is called by every mutation endpoint (create, update, delete priority/deliverable). Hitting Google Calendar API on every checkbox toggle would be wasteful and slow. Calendar data is only needed on initial widget load and explicit refresh.

**Flow:**
1. MCP `get_priorities` tool handler calls two backend endpoints:
   - `GET /api/priority-guardian/priorities` (existing — returns priorities + connection status)
   - `GET /api/priority-guardian/calendar/time-allocation` (new — returns hours per keyword for current week)
2. MCP handler merges: injects `hoursThisWeek` into each priority + adds `timeAllocation` block to response
3. Widget mutation tools (add/update/delete) continue to call only the priorities endpoint — no calendar fetch on CRUD

This means the Google Calendar API is only hit when the widget mounts or the user explicitly refreshes. CRUD operations remain fast.

---

## Shared Core Extraction: `ensure_valid_access_token`

`ensure_valid_access_token()` currently lives in `backend/apps/focused/logic_googletokens.py` but has **zero Focused-specific dependencies**. It operates on `CoreConnection` (core model), calls `refresh_access_token()` (core module), and uses `encrypt_token()`/`decrypt_token()` (core module).

**Extract to:** `backend/core/google_token_management.py`

After extraction, both Focused and PG import from core. Update Focused's imports to use the new location. This is a refactor — no behavior change.

The function signature stays identical:
```python
async def ensure_valid_access_token(
    connection: CoreConnection,
    session: AsyncSession,
    http_client: httpx.AsyncClient,
) -> dict[str, str]:
    # Returns {"access_token": "..."} or {"error": "ERROR_CODE"}
```

---

## New Backend Endpoint

### `GET /api/priority-guardian/calendar/time-allocation`

**Purpose:** Fetch Google Calendar events for the current week, match P1/P2/P3 keywords, compute duration per keyword.

**Request:** No body. User identified via `X-User-ID` header (same trust boundary as all PG endpoints).

**Response shape:**
```json
{
  "success": true,
  "data": {
    "week_start": "2026-02-09T00:00:00+01:00",
    "week_end": "2026-02-16T00:00:00+01:00",
    "timezone": "Europe/Berlin",
    "keywords": {
      "P1": { "hours": 10.5, "event_count": 6 },
      "P2": { "hours": 3.0, "event_count": 2 },
      "P3": { "hours": 0.0, "event_count": 0 }
    },
    "other_hours": 18.25,
    "total_tracked_hours": 31.75,
    "total_events_scanned": 42,
    "bar_segments": {
      "P1": 10.5,
      "P2": 3.0,
      "P3": 0.0,
      "other": 18.25
    }
  }
}
```

**Key distinction:**
- `keywords.P1.hours` = true hours toward P1 (may overlap with other keywords)
- `bar_segments.P1` = exclusive hours for stacked bar rendering (multi-match events assigned to highest-priority keyword: P1 > P2 > P3)
- `bar_segments` values sum to exactly `total_tracked_hours`
- `keywords` values may sum to more than `total_tracked_hours` if multi-match events exist
```

**Error responses:**
- `200 + data` with all zeros when Google not connected (graceful degradation — widget shows empty bar, not error)
- `200 + data` with all zeros when no events found (valid result, not error)
- `401` if X-User-ID missing/invalid
- `502` if Google Calendar API fails after retries (upstream error)
- `503` if token refresh fails (temporary — user may need to reconnect)

**Error shape requirement:** All 5xx responses must use standardized error shape: `{"success": false, "error": {"code": "UPSTREAM_ERROR", "message": "Calendar data temporarily unavailable"}}`. Never leak raw Google error messages, stack traces, or internal details in response bodies. Log full error details server-side with correlation_id.

**Why 200 with zeros instead of error for "not connected":** The widget renders the time allocation bar regardless. Zero hours is a valid state (user just started, or no events this week). The widget checks `google_connected` from the priorities response to show the connection prompt — calendar endpoint doesn't need to duplicate that logic.

---

## Time Computation Rules (from Progress Tracking V1.0 spec)

These are non-negotiable — they define correctness:

1. **Week boundary:** Monday 00:00 to next Monday 00:00 (exclusive end) in user's timezone. Google Calendar API `timeMax` is exclusive — using `Sunday 23:59:59` risks missing edge-case events. The correct pattern is `timeMin = this Monday 00:00`, `timeMax = next Monday 00:00`.
2. **Duration:** `event.end` minus `event.start` (in hours, as float, rounded to 2 decimal places)
3. **Keyword matching:** Case-insensitive **word-boundary** match of P1/P2/P3 against event `summary` (title) only. Use regex `\bP[123]\b` (with `re.IGNORECASE`). This matches "P1 Marketing", "[P1] standup", "P1: design" but rejects "AP1", "P10", "StepP1X". Reuse Focused's `normalize()` for whitespace handling, but replace Focused's substring `in` check with regex boundary matching. **Note:** Progress Tracking V1.0 §2.1 mentions matching against "titles AND descriptions" — this is a spec error. Matching is title-only by design.
4. **All-day events:** Exclude from time calculation entirely (no meaningful hour count). Detection: event has `start.date` instead of `start.dateTime`.
5. **Declined events:** Exclude. Check `attendees` array for self (`self: true`) with `responseStatus: "declined"`.
6. **Recurring events:** `singleEvents=true` in Google Calendar API query expands recurring events into individual instances. Each instance counted separately. Already handled by `fetch_events()`.
7. **Multi-priority events:** One event can match multiple keywords. If event title contains both "P1" and "P2", duration is counted for BOTH keyword buckets. Spec explicitly allows this. This means P1_hours + P2_hours + P3_hours can exceed `totalTrackedHours`.
8. **`totalTrackedHours`:** Sum of unique event durations (deduplicated by event ID). An event matching P1 and P2 contributes its duration once to totalTrackedHours, but to both keyword buckets. This is not a math error — per-keyword hours answer "how much time went toward this priority" while totalTrackedHours answers "how many hours were scheduled this week."
9. **Bar rendering allocation (for Widget Inc C):** Since keyword hours can overlap, the stacked bar cannot naively sum keyword hours. For visual rendering: each multi-match event is assigned to its **first matched keyword** (P1 > P2 > P3 priority order) for bar segment sizing. The per-keyword hour labels in the legend show true (overlapping) hours. The bar segments + "other" segment sum to exactly `totalTrackedHours`.
10. **"Other" hours:** Sum duration of events that match NO keyword (P1/P2/P3). This is all remaining calendar time.
11. **Events with no duration:** If `start == end` (zero-duration events), skip. Don't divide by zero.
12. **Cancelled events:** Exclude events with `status: "cancelled"` (Google sends these for deleted recurring instances).

### Timezone Handling

**v1 approach:** Derive timezone from Google Calendar settings API (`GET /users/me/settings/timezone`). This is one API call, cacheable. Returns IANA timezone string (e.g., "Europe/Berlin").

If timezone fetch fails: fall back to UTC. Log warning with correlation_id and HTTP status. Do not fail the entire request. This applies to any failure mode: 401, 403 (insufficient scopes), network error, unexpected response shape, timeout.

The `calendar.events.readonly` scope is expected to include read access to calendar settings — but if this turns out to be wrong in production, the UTC fallback ensures the endpoint still works.

**Week boundary computation:** Given timezone, compute this Monday 00:00 and next Monday 00:00 in that timezone, then convert to UTC for the Google Calendar API `timeMin`/`timeMax` parameters (`timeMax` is exclusive). **DST requirement:** Must use `zoneinfo.ZoneInfo` for timezone-aware datetime computation. Do NOT use manual UTC offset math — DST transitions (e.g., Europe/Berlin spring/fall) create 23h or 25h days, and naive offset calculation will produce incorrect week boundaries. Use `datetime.datetime(..., tzinfo=ZoneInfo("Europe/Berlin"))` and let Python handle the conversion.

---

## Implementation: Calendar Service Module

**File:** `backend/apps/priority_guardian/services/calendar_service.py`

This is the core business logic module, equivalent to Focused's `check_calendar_impl.py`. It follows the same structural pattern:

1. Load Google connection from DB
2. Ensure valid access token (via shared core function)
3. Fetch user's timezone from Google Calendar settings
4. Compute week boundaries in user's timezone
5. Call `fetch_events()` with week boundaries
6. Filter: exclude all-day events, exclude declined events
7. Match P1/P2/P3 keywords against event titles (word-boundary regex)
8. Compute duration per keyword + "other" hours (events matching no keyword)
9. Return structured result

**Dependencies (all existing):**
- `backend.core.google_calendar.fetch_events` — event fetching
- `backend.core.google_token_management.ensure_valid_access_token` — token refresh (after extraction)
- `backend.core.models.CoreConnection` — DB model
- `backend.core.database.get_db` — session factory
- `httpx.AsyncClient` — HTTP client (for Google API calls)

**New dependency:**
- Google Calendar Settings API call to get user timezone. This is a simple GET request: `GET https://www.googleapis.com/calendar/v3/users/me/settings/timezone` with bearer token. Add a function to `backend/core/google_calendar.py` for this (keeps all Google Calendar API calls in one place).

---

## MCP Tool Enrichment

`get_priorities` tool handler (`mcp_server/priority_guardian/tools/get_priorities.py`) currently calls one backend endpoint. After this increment, it calls two and merges:

**Current:**
```
backend_get("/api/priority-guardian/priorities") → response
```

**After:**
```
# Parallel calls with individual timeouts
priorities_response, calendar_response = await asyncio.gather(
    backend_get("/api/priority-guardian/priorities"),
    backend_get("/api/priority-guardian/calendar/time-allocation"),
    return_exceptions=True
)
# If calendar_response is an exception → treat as failed, continue with priorities only
```

**Timeout requirement:** Each backend call must have an individual timeout (8 seconds recommended — leaves headroom within MCP's 10-second tool timeout). Use `asyncio.wait_for()` wrapping each call, or configure httpx client timeout. If one call hangs, the other must still resolve. Never `await asyncio.gather()` without `return_exceptions=True` — a single failure must not crash both.

**If calendar endpoint fails:** Log warning with correlation_id and error type. Return priorities without calendar data (`weeklyHourActual: None`, no `timeAllocation` block). Calendar failure must not break the entire widget. The MCP tool always succeeds if priorities load — calendar data is best-effort enrichment.

**`timeAllocation` block in structuredContent:**
```json
{
  "timeAllocation": {
    "weekStart": "2026-02-09",
    "weekEnd": "2026-02-16",
    "totalTrackedHours": 31.75,
    "keywords": {
      "P1": { "hours": 10.5, "eventCount": 6 },
      "P2": { "hours": 3.0, "eventCount": 2 },
      "P3": { "hours": 0.0, "eventCount": 0 }
    },
    "otherHours": 18.25,
    "barSegments": {
      "P1": 10.5,
      "P2": 3.0,
      "P3": 0.0,
      "other": 18.25
    }
  }
}
```

`barSegments` values sum to `totalTrackedHours`. Widget Inc C uses `barSegments` for stacked bar sizing and `keywords` for legend labels.

---

## Files to Create

| File | Purpose |
|------|---------|
| `backend/core/google_token_management.py` | Extracted `ensure_valid_access_token()` from Focused |
| `backend/apps/priority_guardian/services/__init__.py` | Package init |
| `backend/apps/priority_guardian/services/calendar_service.py` | Core time allocation computation logic |
| `backend/apps/priority_guardian/routers/calendar_router.py` | `GET /calendar/time-allocation` endpoint |

## Files to Modify

| File | Change |
|------|--------|
| `backend/core/google_calendar.py` | Add `get_user_timezone()` function |
| `backend/apps/focused/logic_googletokens.py` | Replace body with import from `backend.core.google_token_management` (backward-compatible re-export) |
| `backend/apps/priority_guardian/pg_config.py` | Add `PG_KEYWORDS = ["P1", "P2", "P3"]` constant |
| `backend/main.py` | Register `calendar_router` under PG app prefix |
| `mcp_server/priority_guardian/tools/get_priorities.py` | Add calendar endpoint call + merge logic |
| `mcp_server/priority_guardian/http_client.py` | No changes needed (already has `backend_get`) |

---

## What This Increment Does NOT Include

- Widget UI changes (no TimeAllocationBar — that's Widget Inc C)
- Caching of calendar data (future optimization — Redis cache with 5-min TTL)
- Incremental sync tokens (future optimization — reduces API calls)
- Weekly report generation
- Snapshot storage
- Semantic grouping of non-priority events (LLM-side, live in conversation)

---

## Unit Tests

### `backend/core/google_token_management.py`
- Token not expired → returns decrypted access token without refresh
- Token expired → calls refresh, updates DB, returns new token
- Refresh fails with invalid refresh token → returns `REFRESH_TOKEN_INVALID`
- Refresh fails with quota exceeded → returns `API_QUOTA_EXCEEDED`
- Decryption failure → returns `TOKEN_DECRYPTION_FAILED`

*Note: These tests validate the extraction is behavior-preserving. Focused's existing tests should still pass after the refactor.*

### `backend/core/google_calendar.py` — `get_user_timezone()`
- Returns timezone string on 200
- Returns "UTC" fallback on 401 (expired token)
- Returns "UTC" fallback on 403 (insufficient scopes)
- Returns "UTC" fallback on network error
- Returns "UTC" fallback on timeout
- Returns "UTC" fallback on unexpected response shape

### `backend/apps/priority_guardian/services/calendar_service.py`

**Keyword matching:**
- "P1 Marketing meeting" matches P1
- "Weekly P2 review" matches P2
- "p1 standup" matches P1 (case-insensitive)
- "[P1] design sync" matches P1 (brackets don't break word boundary)
- "P1: copywriting" matches P1 (colon after keyword)
- "Sprint planning" matches nothing → counted as "other"
- "P1 and P2 sync" matches BOTH P1 and P2 (duration counted for each)
- "" (empty title) matches nothing
- "AP1 budget" does NOT match P1 (word boundary rejects — "P1" is not a standalone token)
- "P10 rollout" does NOT match P1 (word boundary rejects — "P10" ≠ "P1")
- "StepP1X" does NOT match P1 (no word boundary before or after)
- "Chapter P1" DOES match P1 (space is a word boundary)

**Duration computation:**
- 2-hour event (10:00–12:00) → 2.0 hours
- 90-minute event → 1.5 hours
- Cross-midnight event (23:00–01:00 next day) → 2.0 hours
- Zero-duration event (start == end) → skipped, 0.0 hours

**Event filtering:**
- All-day event (has `start.date`, no `start.dateTime`) → excluded from all calculations
- Declined event (self attendee `responseStatus: "declined"`) → excluded
- Cancelled event (`status: "cancelled"`) → excluded
- Tentative event → included (only declined and cancelled are excluded)
- Event with no attendees array → included (solo calendar events)

**Multi-match bar segment allocation:**
- Event "P1 P2 sync" (2h) → P1 gets 2h, P2 gets 2h in keyword buckets. bar_segments: P1 gets 2h (highest priority wins), P2 gets 0h from this event.
- totalTrackedHours = 2h (deduplicated). P1_hours + P2_hours = 4h (overlapping). bar_segments sum = 2h (correct).
- Three events: "P1 work" (3h), "P1 P2 sync" (2h), "P2 review" (1h) → keyword P1=5h, P2=3h. bar_segments: P1=5h, P2=1h (only "P2 review" exclusively). totalTrackedHours=6h.

**Week boundary:**
- For timezone "Europe/Berlin": Monday 00:00 CET → next Monday 00:00 CET, converted to UTC for API params
- For timezone "America/New_York": Monday 00:00 EST → next Monday 00:00 EST
- UTC fallback: Monday 00:00 UTC → next Monday 00:00 UTC
- DST transition week (e.g., March clock change in Europe/Berlin): week boundary still computed correctly using `zoneinfo.ZoneInfo`, not naive offset math
- `timeMax` is exclusive — events ending exactly at next Monday 00:00 are excluded (correct: they belong to next week)

**Logging:**
- Log at INFO level on each request: user_id, week_start, timezone, total_events_scanned, per-keyword hours, total_tracked_hours
- Log at WARNING level: timezone fetch failure (with fallback to UTC), token refresh triggered
- Log at ERROR level: Google API failure, token decryption failure
- All logs include correlation_id
- **Never log event summaries, descriptions, or attendee data** (PII risk). Log only counts, totals, week range, timezone, and error codes.

**Deduplication:**
- `totalTrackedHours` deduplicates by `event.id`. With `singleEvents=true`, each recurring instance gets a unique ID.
- Defensively handle events with missing or null `id` field — skip them from total (log warning, don't crash).

**Aggregation:**
- 3 P1 events (2h, 3h, 1.5h) → P1 keyword hours = 6.5h
- 2 non-keyword events (1h, 2h) → other = 3.0h
- `totalTrackedHours` = sum of unique event durations = 9.5h (5 events, no overlap in this example)
- `bar_segments` sum = `totalTrackedHours` = 9.5h
- Multi-match example: 3 P1 events (6.5h) + 1 "P1 P2" event (2h) + 1 P2-only event (1h) + 2 other (3h) → keyword P1=8.5h, keyword P2=3h, other=3h, `totalTrackedHours`=12.5h, `bar_segments`: P1=8.5h, P2=1h (only P2-exclusive), other=3h, sum=12.5h
- No events at all → all zeros, success response

**Error handling:**
- Google not connected (no CoreConnection row) → returns all-zeros response, no error
- Token refresh fails → raises appropriate error (propagated to router as 503)
- `fetch_events()` fails → raises error (propagated to router as 502)

### `calendar_router.py`
- Returns 200 with time allocation data (mock calendar_service)
- Returns 200 with all zeros when user has no Google connection
- Returns 401 for missing X-User-ID
- Returns 502 when Google Calendar API fails
- Returns 503 when token refresh fails

### MCP `get_priorities` handler (updated tests)
- With calendar data: `weeklyHourActual` populated per priority, `timeAllocation` block present
- Calendar endpoint fails: `weeklyHourActual` is None, no `timeAllocation` block, priorities still returned successfully
- Calendar endpoint returns all zeros: `weeklyHourActual` is 0.0 per priority, `timeAllocation` block present with zeros
- Google not connected: same as all zeros (graceful)

---

## Integration Tests

### Calendar Service + Real DB
- Create user with Google connection → mock Google Calendar API → compute time allocation → verify response shape and values
- User with expired token → verify auto-refresh is called → verify fresh token used for calendar fetch
- User with revoked connection (`revoked_at` set) → returns all-zeros gracefully

### Full Stack: MCP → Backend → Calendar
- MCP `get_priorities` → backend priorities + calendar endpoints → merged response with correct `hoursThisWeek` values and `timeAllocation` block
- Calendar endpoint down → MCP still returns priorities without calendar data (degraded but functional)

### Focused Regression
- Verify Focused's `check_calendar_impl` still works after `ensure_valid_access_token` extraction (import path changed but behavior identical)
- Run existing Focused calendar tests — must all pass

---

## Production Readiness (Increment Context)

### Scalability
- Google Calendar API: 5 QPS per user, 10 QPS per project. One `fetch_events()` call per widget mount is well within limits.
- `get_user_timezone()` is one additional API call per widget mount. Total: 2 Google API calls per widget load.
- Future optimization: cache timezone (changes rarely) and cache time allocation (5-min TTL in Redis). Not in this increment.

### GDPR / Data Retention
- Calendar events are NOT stored. Fetched, computed, returned in response, discarded. No new database tables.
- User timezone is NOT stored (fetched live from Google each time). Privacy-preserving.
- This increment adds no new PII storage. Data Retention Strategy unchanged.

### Load Behavior
- Calendar endpoint adds ~500-1500ms to initial widget load (Google API round-trip). Acceptable for dashboard load.
- CRUD operations unaffected (don't call calendar endpoint).
- If Google API is slow: MCP tool has 10-second timeout. Calendar failure → graceful degradation.

---

## Implementation Notes (for Claude Code)

**Correlation ID propagation:** Verify that `correlation_id` flows end-to-end: MCP handler → `backend_get` headers → calendar router → calendar service → Google API wrapper logs. The existing `http_client.py` already forwards correlation_id. Confirm this survives the extraction of `ensure_valid_access_token` to core.

**Regex known limitation:** `\bP[123]\b` will NOT match `P1-DeepWork` or `P1/Review` because `-` and `/` are not word boundary triggers in the same way as spaces or brackets. This is acceptable — users are instructed to tag with "P1" as a standalone prefix. If adoption data shows users commonly use hyphenated tags, revisit with `(?<![A-Za-z0-9])P[123](?![A-Za-z0-9])`.

**Multi-match bar_segments assignment must be deterministic:** Iterate keywords in fixed order `["P1", "P2", "P3"]`. Assign each multi-match event to the first keyword that matches. Do NOT rely on dictionary iteration order, regex findall order, or set operations. Explicit loop with break.

**Token refresh concurrency:** `ensure_valid_access_token` checks `token_expires_at` before refreshing. Two concurrent calls with an expired token may both attempt refresh — this is safe because Google accepts multiple refresh calls and each returns a valid access token. The last DB write wins with a valid token. Not perfectly atomic, but idempotent. Verify this behavior is preserved after extracting to `backend/core/google_token_management.py`.

---

## Validation Criteria (Definition of Done)

1. `ensure_valid_access_token` extracted to `backend/core/` — Focused still works
2. `GET /api/priority-guardian/calendar/time-allocation` returns correct time data for mocked calendar events
3. All-day events excluded, declined events excluded, multi-keyword events counted for each keyword
4. Week boundaries computed correctly for non-UTC timezones
5. MCP `get_priorities` returns `weeklyHourActual` per priority and `timeAllocation` block
6. Calendar failure → MCP tool still returns priorities (graceful degradation)
7. All unit tests pass
8. All integration tests pass
9. Focused regression tests pass (no breakage from extraction)
10. Deployed to Render and verifiable via MCP Inspector
