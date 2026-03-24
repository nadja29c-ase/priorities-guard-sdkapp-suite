# PG Increment 08: Opportunistic Snapshot Persistence

## Objective

After this increment: weekly snapshots are created automatically when the user opens the PG dashboard. No user action required beyond normal usage. Running aggregates (`streak_count`, `avg_hours_week`, `total_hours_invested`) update on `pg_priorities`. The system backfills up to 3 completed weeks of missing snapshots. Snapshot creation never blocks or breaks the dashboard.

---

## Product Context

PG shows freelancers where their time actually goes. The dashboard (via `get_priorities`) is the daily view. The weekly report is the reflection tool. Both currently compute live from Google Calendar — no history persists.

This increment adds the persistence layer. When the user opens the dashboard, the system opportunistically checks for missing completed-week snapshots and fills them in. This enables 3-week historical comparison (future widget increment) and populates running aggregates that the widget already renders conditionally (streak count on FlexibleCard).

**Why opportunistic, not background jobs:** PG is a coaching tool, not a monitoring tool. Snapshotting is tied to user engagement — the system remembers as far back as the user's engagement pattern warrants. A user who disappears for 2 weeks and returns gets seamless backfill. No Celery task, no cron, no silent background work for disengaged users. See ADR-001 Decision 5.

**Why dashboard load, not weekly report:** The weekly report is a pure read path (ADR-001 Decision 6). Snapshot writes happen on the dashboard path because it fires on every widget mount — the most reliable trigger for catching completed weeks.

---

## Architecture Decision References (read, inform reasoning, don't import as rules)

- `doc/ADR_001_running_aggregates_on_pg_priorities.md` — Decisions 1-7 govern this increment directly
- `Shared_Backend_Architecture_Design.pdf` (project knowledge) — shared backend conventions, app isolation
- `Data_Retention_Strategy_Shared_Backend.pdf` (project knowledge) — retention policies per table type
- `doc/MCP Server Implementation Standard.md` — dispatcher pattern, handler signature, error categories

---

## What Exists (read these files to understand current state)

### Database — tables already migrated, currently empty
- `backend/apps/priority_guardian/db_models.py` — `PgWeeklySnapshot` model with all columns (priority_id, user_id, week_start, week_end, actual_hours, event_count, deadline-specific fields, flex-specific fields, streak_at_snapshot, created_at). UNIQUE constraint on `(priority_id, week_start)` defined in migration.
- `backend/apps/priority_guardian/db_models.py` — `PgWeeklyOverview` model. NOT written to by this increment — stays empty until semantic grouping persistence ships.
- `backend/apps/priority_guardian/db_models.py` — `PgPriority` model has `streak_count` (default 0), `avg_hours_week` (nullable), `total_hours_invested` (default 0). Nothing writes to them yet.
- Migration `p6k7l8m9n0o1_add_pg_weekly_snapshot_tables.py` — tables exist in production DB.

### Calendar Pipeline (reuse these)
- `backend/apps/priority_guardian/services/calendar_service.py` — `compute_allocation_from_events()` (pure computation, no I/O), `compute_week_boundaries()` (Monday-to-Monday in user timezone), event filtering helpers (`is_all_day_event`, `is_declined_event`, `is_cancelled_event`, `match_keywords`, `compute_event_duration_hours`), `to_rfc3339()`.
- `backend/core/google_calendar.py` — `list_events()` fetches paginated events, `get_user_timezone()`.
- `backend/core/google_token_management.py` — `ensure_valid_access_token()`.

### Weekly Report Service (reuse pure functions)
- `backend/apps/priority_guardian/services/weekly_report_service.py` — `is_week_complete()` (timezone-aware), `compute_flex_status()` (80%/110% thresholds), `compute_pacing_status()` (deliverable completion vs time ratio). These are pure functions, no persistence side effects.

### MCP Handler — current get_priorities flow
- `mcp_server/priority_guardian/tools/get_priorities.py` — parallel fetches `GET /priorities` + `GET /calendar/time-allocation`. Merges calendar hours into priorities. Returns `structuredContent` with widget data. Currently `read_only_hint=True`.

### Backend — current priorities endpoint
- `backend/apps/priority_guardian/routers/priorities_router.py` — `build_priorities_response()` queries `PgPriority` with deliverables, builds response including `streak_count` for flexible priorities (currently always 0).

### Existing Tests
- `tests/unit/mcp_pg/test_get_priorities.py` — unit tests for MCP handler
- `tests/unit/priority_guardian/test_calendar_service.py` — calendar computation tests
- `tests/unit/priority_guardian/test_weekly_report_service.py` — report service pure function tests
- `tests/integration/priority_guardian/test_weekly_report_simplified.py` — integration tests including pie chart data shape tests

---

## Part A: Backend Service — `ensure_snapshots_up_to_date()`

### New file: `backend/apps/priority_guardian/services/snapshot_service.py`

This is the core of the increment. A single async function that:

1. Determines which completed weeks need snapshots (max 3)
2. For each missing week: fetches calendar events from Google, computes allocation, writes snapshot rows, updates aggregates
3. Is idempotent, non-blocking, and failure-tolerant

### Function signature

```
async def ensure_snapshots_up_to_date(
    user_id: UUID,
    session: AsyncSession,
    http_client: httpx.AsyncClient,
    correlation_id: str | None = None,
) -> dict
```

Returns: `{"checked": int, "created": int, "errors": int}` — informational only, caller ignores failures.

### Algorithm

**Step 1 — Determine completed weeks to check:**
- Get user's timezone from Google Calendar API (`get_user_timezone`)
- Compute the last 3 completed Mondays relative to `now()` in user timezone
  - A week is complete when `now() >= next_monday_00:00` in user timezone (reuse `is_week_complete()`)
  - If today is Monday, the most recent completed week started last Monday
  - Result: a list of 0-3 `date` objects (each a Monday)

**Step 2 — Find which weeks already have snapshots:**
- Query: `SELECT DISTINCT week_start FROM pg_weekly_snapshots WHERE user_id = ? AND week_start IN (?)`
- Compare against the 3 target weeks. Missing weeks need backfill.
- If all exist → fast exit, return `{"checked": 3, "created": 0, "errors": 0}`

**Step 3 — For each missing week (chronological order, oldest first):**
- Get Google connection + ensure valid access token
  - If no connection or token refresh fails → log warning, return partial result, stop
- Compute week boundaries via `compute_week_boundaries(timezone_str, week_start_date)`
- Fetch events from Google Calendar for that week via `list_events()`
- Compute allocation via `compute_allocation_from_events()`
- Load active priorities for the user (with deliverables for deadline priorities)
- For each active priority:
  - Extract keyword hours + event count from allocation
  - Compute type-specific fields (flex_status / pacing_status / deliverables count)
  - Compute streak: query the previous week's snapshot for this priority to get `streak_at_snapshot`, then apply binary rule (hours > 0 → previous + 1, hours == 0 → 0). If no previous snapshot exists, streak = 1 if hours > 0, else 0.
  - INSERT into `pg_weekly_snapshots` with all fields. Use `INSERT ... ON CONFLICT (priority_id, week_start) DO NOTHING RETURNING id`. If no row returned (conflict = already exists), skip aggregate update for this priority-week entirely.
  - Only if INSERT returned a row: UPDATE `pg_priorities` SET streak_count, avg_hours_week, total_hours_invested WHERE id = priority_id AND status = 'active'. This guards against double-counting on concurrent calls or retries.

**Aggregate update rules (per priority):**
- `streak_count` = `streak_at_snapshot` value just computed for this week
- `total_hours_invested` = `total_hours_invested + actual_hours` for this week
- `avg_hours_week` = recompute from all snapshots for this priority: `SELECT AVG(actual_hours) FROM pg_weekly_snapshots WHERE priority_id = ?`

**Step 4 — Return summary:**
- `{"checked": N, "created": M, "errors": E}`

### Error handling

- Token refresh fails → stop backfill, return partial. Dashboard will try again next load.
- Google Calendar API fails for one week → log, skip that week, continue to next. Don't let one week's failure block others.
- DB write fails (constraint violation = already exists, which is fine) → catch IntegrityError, treat as success (idempotent)
- Any unexpected exception → log with `structlog`, return partial result. NEVER raise — caller must not break.

### Concurrency safety

Multiple widget mounts could call this concurrently for the same user. The `INSERT ... ON CONFLICT DO NOTHING RETURNING id` pattern ensures only the winning insert triggers aggregate updates. Losing concurrent calls see no returned row and skip aggregates entirely — no double-counting. Worst case: duplicate Google API calls for the same week, but only one snapshot row gets created and aggregates update exactly once. This is acceptable at current scale.

### Retired priorities

Snapshot currently active priorities only. The `WHERE status = 'active'` filter on the priorities query handles this. If a user retires a priority before the next dashboard load, past uncaptured weeks for that priority are lost. This is intentional — retired priorities freeze their state, and creating snapshots for a just-retired priority contradicts the "retired = frozen" invariant. Partial-week data for mid-week retirements is ambiguous anyway. **Known limitation:** if the user wants last week's data captured, at least one dashboard load must occur before retiring the priority. Document in product notes.

### Week boundary convention

`compute_week_boundaries()` returns `(monday_00:00, next_monday_00:00)` as timezone-aware datetimes — these are the Google Calendar API query bounds (exclusive end). The `week_end` column on `pg_weekly_snapshots` stores `week_start + 6 days` (Sunday) as a date label for display purposes. These are different representations: one is a time range for API queries, the other is a human-readable date on a DB record. They are never compared against each other.

### Backfilled deadline snapshots

As documented in ADR-001 known limitations: backfilled deadline snapshots use current deliverable state (`deliverables_completed`, `deliverables_total`). Cannot reconstruct historical deliverable state. Slight inaccuracy accepted.

---

## Part B: Backend Endpoint

### New endpoint: `POST /api/priority-guardian/snapshots/ensure`

**Purpose:** Exposes `ensure_snapshots_up_to_date()` to the MCP handler.

**Location:** New router file `backend/apps/priority_guardian/routers/snapshot_router.py`, mounted in the PG app.

**Request:** No body. User ID from `X-User-ID` header (same trust boundary as all PG endpoints).

**Response:**
```json
{"success": true, "data": {"checked": 3, "created": 1, "errors": 0}}
```

**Error responses:**
- No Google connection → `200` with `{"checked": 0, "created": 0, "errors": 0}` (not an error — user just hasn't connected Google yet)
- Token refresh fails → `200` with partial result (some weeks may have been created before failure)
- Unexpected error → `500` (but MCP handler ignores this)

**Why POST not GET:** This endpoint has side effects (writes snapshot rows, updates aggregates). POST is semantically correct even though the request has no body.

**Mount:** Add router to `backend/main.py` under `/api/priority-guardian` prefix, same pattern as existing PG routers.

---

## Part C: MCP Handler — Hook into `get_priorities`

### Change to `get_priorities.py`

Add a third parallel call alongside priorities and calendar:

```
snapshot_coro = backend_post(
    "/api/priority-guardian/snapshots/ensure",
    user_id,
    correlation_id,
    json={}
)
```

Fire it in the existing `asyncio.gather` alongside the other two. Wrap with `_fetch_with_timeout` using the same `BACKEND_TIMEOUT`.

**Handle result:** Log success/failure. Never use the result for widget data. The snapshot endpoint's job is to ensure DB state is up to date for *future* reads — the current dashboard load still gets its data from the priorities + calendar endpoints as before.

**Failure handling:** If the snapshot call fails or times out → log warning, continue. Dashboard renders normally. Snapshots will be attempted again next load.

### Tool annotation change

`read_only_hint` changes from `True` to `False`. The tool now triggers snapshot writes as a side effect. This is a semantic change for the MCP protocol — ChatGPT may choose to call read-only tools more eagerly.

---

## Part D: Backend Priorities Response — Include Aggregates

### Change to `build_priorities_response()` in `priorities_router.py`

Currently includes `streak_count` for flexible priorities only. Extend to include all three aggregates for all priority types:

- `streak_count` — already included for flexible, add for deadline
- `avg_hours_week` — not currently included. Add as `float | None`
- `total_hours_invested` — not currently included. Add as `float`

These flow through to the MCP handler's `_normalize_priority()` function.

### Change to `_normalize_priority()` in `get_priorities.py`

Map the new aggregate fields to camelCase:
- `streak_count` → `streakCount` (already mapped for flexible, extend to all types)
- `avg_hours_week` → `avgHoursWeek`
- `total_hours_invested` → `totalHoursInvested`

Include these on all priority types so the weekly report handler and future widget features can use them.

---

## What This Increment Does NOT Include

- Writing to `pg_weekly_overview` (semantic grouping persistence — separate increment)
- 3-week navigation in the dashboard widget (separate widget increment, consumes the snapshots this increment creates)
- Week-over-week comparison in the weekly report (the `previous_week` field stays `null` — the weekly report reads from Google, not snapshots, per ADR-001 Decision 6)
- Dashboard caching (separate backlog item, 10K+ DAU trigger)
- Background Celery snapshot job (rejected per ADR-001 Decision 5)
- Widget changes (FlexibleCard already renders streak when `streakCount > 0` — it will automatically start showing once aggregates are populated)

---

## Unit Tests

### File: `tests/unit/priority_guardian/test_snapshot_service.py`

#### `ensure_snapshots_up_to_date()` — core logic

- No Google connection → returns `{"checked": 0, "created": 0, "errors": 0}`, no DB writes
- All 3 completed weeks already have snapshots → fast exit, returns `{"checked": 3, "created": 0, "errors": 0}`, no Google API calls
- 1 of 3 weeks missing → creates 1 snapshot set (one row per active priority), returns `{"created": 1}`
- All 3 weeks missing → creates 3 snapshot sets in chronological order, returns `{"created": 3}`
- User has no active priorities → no snapshots created (nothing to snapshot)
- Today is Tuesday → only 1 completed week (last week). Not 0.
- Today is Monday before midnight in user timezone → last week is not yet complete (week ends next Monday 00:00)

#### Snapshot row content

- Flexible priority snapshot: `actual_hours`, `event_count`, `target_hours`, `flex_status` populated. Deadline-specific fields null.
- Deadline priority snapshot: `actual_hours`, `event_count`, `deadline_date`, `days_remaining`, `deliverables_completed`, `deliverables_total`, `pacing_status` populated. Flex-specific fields null.
- `week_end` = `week_start + 6 days` (Sunday)
- `streak_at_snapshot` correctly computed (see streak tests below)

#### Streak computation

- First ever snapshot, hours > 0 → `streak_at_snapshot = 1`
- First ever snapshot, hours == 0 → `streak_at_snapshot = 0`
- Previous week snapshot exists with `streak_at_snapshot = 3`, this week hours > 0 → `streak_at_snapshot = 4`
- Previous week snapshot exists with `streak_at_snapshot = 3`, this week hours == 0 → `streak_at_snapshot = 0`
- Previous week snapshot missing (gap), this week hours > 0 → `streak_at_snapshot = 1` (streak broken by gap)

#### Aggregate updates

- After snapshot creation: `pg_priorities.streak_count` matches `streak_at_snapshot`
- After snapshot creation: `pg_priorities.total_hours_invested` increased by this week's `actual_hours`
- After snapshot creation: `pg_priorities.avg_hours_week` = average of all snapshot `actual_hours` for this priority
- Retired priority: not snapshotted, aggregates frozen

#### Idempotency

- Call twice for the same week → second call: no new rows, no duplicate snapshots, aggregates unchanged
- Concurrent calls: ON CONFLICT DO NOTHING prevents duplicate rows

#### Error handling

- Google API fails on week 2 of 3 → week 1 snapshot saved, week 2 skipped, week 3 attempted. Returns `{"created": 2, "errors": 1}` (or similar)
- Token refresh fails → returns immediately with `{"checked": 0, "created": 0, "errors": 1}`
- DB IntegrityError on INSERT (race condition) → treated as success

### File: `tests/unit/mcp_pg/test_get_priorities_snapshots.py`

#### MCP handler changes

- Snapshot endpoint called in parallel with priorities + calendar
- Snapshot endpoint failure → dashboard renders normally, no error shown to user
- Snapshot endpoint timeout → dashboard renders normally
- `read_only_hint` is `False` on the tool definition

### File: `tests/unit/priority_guardian/test_snapshot_router.py`

#### Backend endpoint

- `POST /snapshots/ensure` with valid user → 200 with summary
- `POST /snapshots/ensure` with no Google connection → 200 with zeros
- Endpoint requires `X-User-ID` header (existing auth pattern)

---

## Integration Tests

### File: `tests/integration/priority_guardian/test_snapshot_persistence.py`

#### Full flow: dashboard load triggers snapshot

- Create user with Google connection + 2 active priorities (1 deadline, 1 flexible)
- Mock Google Calendar API with keyword-matched events for last completed week
- Call `POST /api/priority-guardian/snapshots/ensure`
- Verify: `pg_weekly_snapshots` has 2 rows (one per priority) for last completed week
- Verify: `pg_priorities.streak_count` updated (was 0, now 1)
- Verify: `pg_priorities.total_hours_invested` updated (was 0, now matches actual_hours)
- Verify: `pg_priorities.avg_hours_week` updated

#### Backfill: 3 weeks missing

- Mock Google Calendar API for 3 different weeks (with different event data per week)
- Call `POST /snapshots/ensure`
- Verify: 6 snapshot rows created (2 priorities × 3 weeks)
- Verify: snapshots created in chronological order (streak computed correctly across weeks)
- Verify: `streak_count` reflects 3-week streak (if all weeks have hours > 0)

#### Idempotency

- Call `POST /snapshots/ensure` twice → second call creates 0 new rows
- Verify row count unchanged after second call
- Verify aggregate values unchanged after second call

#### Streak break

- Week 1: priority has 5 hours → streak = 1
- Week 2: priority has 0 hours → streak = 0
- Week 3: priority has 3 hours → streak = 1
- Verify `pg_priorities.streak_count` = 1 (not 3)

#### Partial failure

- Mock Google Calendar API: succeeds for week 1, fails for week 2, succeeds for week 3
- Verify: week 1 and week 3 snapshots created, week 2 missing
- Verify: aggregates reflect weeks 1 and 3 only

#### No active priorities

- User with Google connection but 0 active priorities
- Call `POST /snapshots/ensure` → 200 with `{"created": 0}`
- Verify: no snapshot rows created

---

## Production Readiness (Increment Context)

### Scalability
- `ensure_snapshots_up_to_date` runs at most once per dashboard load. Common case (snapshots exist): 1 DB query (`SELECT DISTINCT week_start`), fast exit. Uncommon case (backfill): 1-3 Google API fetches + 1-9 DB inserts + 1-3 aggregate updates. All bounded.
- Google Calendar API calls: at most 3 per backfill (one per missing week). Each is 1-3 paginated requests. Well within per-user rate limits.
- DB writes: at most 9 snapshot rows (3 priorities × 3 weeks) + 3 aggregate updates per backfill event. Single-digit writes, not bulk.

### GDPR / Data Retention
- Snapshot data contains computed hours, event counts, status indicators. No raw event content, no PII. Derived from Google Calendar data that the user authorized PG to read.
- `pg_weekly_snapshots` CASCADE deletes with `core_users` — user deletion wipes all snapshots.
- `pg_priorities` aggregate columns are part of the priority row, already covered by priority deletion cascade.
- No new PII fields introduced.

### OpenAI SDK Compliance
- `get_priorities` tool annotation changes: `read_only_hint=False`. This is accurate — the tool now triggers writes.
- No new MCP tools added. No tool schema changes. No widget changes.

### Load Behavior
- Dashboard load: adds ~50ms latency in the common case (1 DB query, fast exit). Backfill case adds 1-5 seconds (Google API calls) but runs concurrently with existing priorities + calendar fetches — does not add to total wall time unless it's the slowest of the three parallel calls.
- Writes: bounded at 9 rows + 3 updates per backfill. Once per week per user in practice. Negligible DB load.

---

## Validation Criteria (Definition of Done)

1. `ensure_snapshots_up_to_date()` creates snapshot rows for missing completed weeks (max 3)
2. Snapshots contain correct per-priority data (hours, counts, type-specific fields, streak)
3. Running aggregates on `pg_priorities` updated after snapshot creation
4. Streak computation follows binary rule (hours > 0 = continues, hours == 0 = resets)
5. Idempotent: duplicate calls produce no duplicate rows, no aggregate drift
6. Non-blocking: snapshot failure does not break dashboard load
7. `POST /api/priority-guardian/snapshots/ensure` endpoint functional and mounted
8. `get_priorities` MCP handler calls snapshot endpoint in parallel, ignores failures
9. `get_priorities` tool definition has `read_only_hint=False`
10. Backend priorities response includes `streak_count`, `avg_hours_week`, `total_hours_invested` for all priority types
11. MCP `_normalize_priority()` maps all three aggregate fields to camelCase
12. All unit tests pass
13. All integration tests pass
14. No regressions on existing tests (priorities, calendar, weekly report)
15. FlexibleCard automatically shows streak when `streakCount > 0` (no widget code change needed — verify visually)
