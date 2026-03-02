# Priority Guardian — Pattern Recognition Engine

**Increment type:** Feature (new MCP tool + backend service + backend endpoint)
**Prerequisite:** Soft delete increment (completed)
**Production-readiness context:** Increment-level. No new migration. No new data stored. Read-only queries on existing tables.

---

## 1. What This Increment Delivers

A new public MCP tool `get_patterns` that computes behavioral patterns from the user's existing snapshot history and priority metadata. The LLM calls this tool during weekly reflection, when the user asks "how am I doing?", or when the user explicitly asks about trends. Returns all applicable patterns in one call — the LLM picks which to narrate.

**No new database tables. No new migrations. No new data stored.** All patterns are computed at read time from existing `pg_weekly_snapshots` and `pg_priorities` tables.

---

## 2. V1.0 Patterns — Complete Specification

### Global Rules

- **Minimum data floor:** 4 completed weeks of snapshot data. "Completed weeks" = count of distinct `week_start` values in `pg_weekly_snapshots` for this user WHERE `week_start < current_week_start` (current week excluded — it's incomplete) AND within the rolling window. Below 4 completed weeks, `get_patterns` returns an empty pattern list with a `data_insufficient` flag and the number of weeks available. **Note:** This measures snapshot availability, not tracking quality — keyword usage may still be sparse. Snapshots can be created by dashboard loads even if the user hasn't meaningfully tracked. This is accepted: patterns will self-filter (e.g., abandoned priority won't fire if hours are 0 across the board).
- **`current_week_start` definition:** Implement a new pure helper `get_current_week_start_utc()` in `backend/apps/priority_guardian/services/utils.py`. Logic: `date.today(UTC)` → subtract `weekday()` days → return a `date` (always Monday). This helper must be pure (no I/O, no external calls, no database queries) and deterministic. Do NOT reuse `calendar_service.compute_week_boundaries()` if it depends on user timezone or Google API. `current_week_start` must be computed once at the start of `compute_patterns()` and used consistently in all queries within that call. **Timezone sharp edge:** Around Sunday/Monday midnight in the user's local timezone, UTC may disagree on which week is "current" — this may exclude or include the most recent completed week for a few hours. Accepted tradeoff: snapshots' stored `week_start` dates remain the source of truth for all per-priority computations.
- **Rolling window:** Compute `window_start_date` in Python as `current_week_start - relativedelta(months=6)` (a `date`). All pattern queries filter `week_start >= window_start_date`. Do NOT use SQL `interval '6 months'` — avoid dialect-dependent casting issues between dates and timestamps. `window_start_date` is computed once alongside `current_week_start` and used consistently. Data older than the window exists in DB but is never queried for patterns.
- **Retired priorities:** Included in pattern computation. Their historical snapshots are valid data. But patterns about retired priorities must be labeled as such in the response so the LLM can frame them appropriately.
- **Retired priority keyword resolution:** After soft delete, `priority.calendar_keyword` is NULL. Implement a shared helper `resolve_keyword(priority, snapshots_for_priority)` that encapsulates this logic: if `priority.status == 'active'` and `priority.calendar_keyword` is not NULL, return it; if `priority.status == 'active'` and `priority.calendar_keyword` IS NULL (bug/partial update), log `patterns.keyword_missing_active_priority` at warning level and return `None`; if `priority.status == 'retired'`, return the `calendar_keyword_at_snapshot` from the most recent snapshot (by `week_start`) within the rolling window that has a non-NULL value; if no such snapshot exists, return `None`. **All patterns use this helper. Never read `calendar_keyword` from the priority row for retired priorities.** Test this helper once in isolation, then trust it across patterns.
- **Pre-migration / edge-case NULL handling:** Some snapshots pre-date migrations that added `total_tracked_hours`, `other_hours`, and `calendar_keyword_at_snapshot`. These fields may be NULL. Additionally, `actual_hours` and `streak_at_snapshot` could be NULL in edge cases (bad legacy rows, partial inserts). **Rule: any snapshot where a field required by the current computation is NULL must be skipped for that computation, never treated as 0.** This applies to all patterns, not just Pattern 4.
- **Snapshot row invariant:** `pg_weekly_snapshots` stores one row per priority per week (enforced by `uq_pg_weekly_snapshots_priority_week` unique constraint). Per-priority computations rely on this invariant — one snapshot row = one data point for that priority for that week. When counting "completed weeks" across all priorities, use distinct `week_start` (multiple rows per week are expected — one per active priority).

### Pattern 1: Consistency Streak (flexible priorities only)

**What it detects:** Consecutive weeks where a flexible priority had hours > 0.

**Data source:** `streak_at_snapshot` field on `PgWeeklySnapshot`. This is already computed and stored by `snapshot_service._update_aggregates()` every time a snapshot is created. Confirm during implementation that: (a) `streak_at_snapshot` is populated on snapshot insert for flexible priorities, and (b) aggregates stop updating after retirement — meaning the most recent `streak_at_snapshot` for a retired priority reflects the streak at time of retirement, not a "current" streak.

**Minimum data:** 4 completed weeks (global floor).

**Computation:** For each flexible priority (active or retired) with ≥4 completed-week snapshots in the rolling window: read the most recent `streak_at_snapshot` value (skipping NULL). If ≥4, surface it. **Fallback:** If `streak_at_snapshot` is NULL on all snapshots for a priority (missing data, schema issue), compute streak manually: count consecutive weeks (ordered by `week_start` descending from most recent) where `actual_hours > 0`. This ensures Pattern 1 is never silently broken by missing aggregate data.

**Retired priority behavior:** Aggregates stop updating after retirement. The most recent `streak_at_snapshot` for a retired priority reflects the streak at time of retirement — it is not a "current" streak. The `priority_status: "retired"` flag enables appropriate framing by the LLM. **Defensive guard:** For retired priorities, Pattern 1 must only consider snapshots where `week_start <= retirement_week_start`, where `retirement_week_start` is derived as: `priority.retired_at.astimezone(UTC).date()` → subtract `weekday()` days → Monday. If `retired_at` is mid-week (e.g., Wednesday), `retirement_week_start` is the Monday of that week — snapshots from that week are included, snapshots from later weeks are excluded. If any snapshots exist after retirement (due to bugs or race conditions), they must be excluded from streak computation. This prevents the fallback from accidentally computing a post-retirement "streak."

**Response shape per pattern instance:**
```json
{
  "pattern_type": "consistency_streak",
  "narration_label": "Consistency streak",
  "priority_id": "uuid",
  "priority_name": "Client outreach",
  "priority_status": "active",
  "calendar_keyword": "P2",
  "streak_weeks": 8,
  "streak_source": "snapshot",
  "detail": "8 consecutive weeks with logged hours"
}
```

**`streak_source`:** `"snapshot"` when read from `streak_at_snapshot`, `"computed"` when fallback was used (all `streak_at_snapshot` values were NULL). Internal debugging field — `assistant_guidance` already forbids mentioning internal fields.

**`calendar_keyword` resolution:** Via shared `resolve_keyword()` helper. Can be `null` for retired priorities where no snapshot has a non-NULL `calendar_keyword_at_snapshot`. When `null`, LLM should refer to the priority by name only.

**Positive framing only.** This pattern only surfaces when the streak is notable (≥4). Broken streaks are NOT surfaced — that's absence of a pattern, not a pattern worth narrating.

### Pattern 2: Abandoned Priority Signal

**What it detects:** A priority that consistently gets near-zero hours, suggesting the user has deprioritized it in practice.

**Data source:** `actual_hours` from `PgWeeklySnapshot`. Skip snapshots where `actual_hours` is NULL.

**Minimum data:** 4 completed weeks (global floor). The average uses the most recent 4 snapshots with non-NULL `actual_hours` (ordered by `week_start` descending) — not "the last 4 calendar weeks." If NULLs exist, the window expands to find 4 qualifying snapshots within the rolling window.

**Computation:** For each active priority with ≥4 qualifying snapshots in the rolling window: compute average `actual_hours` over the last 4. If average < 1.0 hour/week, surface it.

**Why active only:** Retired priorities are already acknowledged as deprioritized. This pattern's value is catching priorities the user still *claims* to care about but isn't investing in.

**Response shape:**
```json
{
  "pattern_type": "abandoned_priority",
  "narration_label": "Low investment",
  "priority_id": "uuid",
  "priority_name": "Blog writing",
  "priority_status": "active",
  "calendar_keyword": "P3",
  "avg_hours_last_4_weeks": 0.5,
  "detail": "Averaging 0.5h/week over the last 4 weeks"
}
```

**Neutral framing.** This is an observation, not a judgment. The LLM should present the data and let the user decide whether to recommit, retire, or replace.

### Pattern 3: Priority Switching Frequency

**What it detects:** Frequent retire-and-replace cycles, which may indicate indecision or difficulty committing.

**Data source:** `pg_priorities` table — `created_at`, `retired_at`, `status` columns. No snapshots needed.

**Minimum data:** 4 completed weeks (global floor, checked via snapshot count as usual). This is intentional — don't surface any patterns until the user has real tracking data. Priority churn before tracking is established is setup behavior, not a pattern worth commenting on.

**Computation:** Count priorities where `retired_at` falls within the rolling window (last 6 months). Count priorities where `created_at` falls within the rolling window. **Threshold is on retirements only:** if retirements ≥ 3 within the window, surface the pattern. `creations_in_window` is included in the response as informational context — it is NOT part of the threshold logic.

**This is a cross-priority pattern** — one instance per user, not per priority.

**Response shape:**
```json
{
  "pattern_type": "priority_switching",
  "narration_label": "Priority changes",
  "retirements_in_window": 4,
  "creations_in_window": 5,
  "window_weeks": 26,
  "detail": "4 priorities retired and 5 created in the last 6 months"
}
```

**Careful framing required.** Switching can be healthy (pivoting based on learning) or unhealthy (thrashing). The LLM should present the data and offer both interpretations. `assistant_guidance` must instruct: "Present this observation neutrally. Acknowledge that switching can be a sign of healthy iteration OR difficulty committing. Ask the user what's driving the changes rather than assuming."

### Pattern 4: Priority Protection

**What it detects:** A priority whose hours remained stable or grew even as total calendar pressure changed.

**Data source:** `actual_hours` and `total_tracked_hours` from `PgWeeklySnapshot`. Skip snapshots where either field is NULL.

**Minimum data: 8 completed weeks** (with non-NULL `actual_hours` AND `total_tracked_hours`). This pattern compares two 4-week periods (recent vs prior) and needs enough data for both periods to be meaningful. If a priority has fewer than 8 qualifying snapshots in the rolling window, skip this pattern for that priority.

**Computation:** For each priority (active or retired) with ≥8 qualifying snapshots in the rolling window:
1. Order qualifying snapshots by `week_start` descending.
2. "Recent period" = last 4 snapshots. "Prior period" = 4 snapshots before that.
3. **Period qualification guard:** Both periods must have exactly 4 qualifying snapshots each. If NULL-skipping causes either period to have fewer than 4, skip this pattern for this priority. Note: "last 4 qualifying snapshots" may span more than 4 calendar weeks if NULLs were skipped — this is the same behavior as Pattern 2.
4. Compute `prior_priority_avg` and `recent_priority_avg` = average `actual_hours` for each period.
5. Compute `prior_total_avg` and `recent_total_avg` = average `total_tracked_hours` for each period.
6. **Guard: if `prior_total_avg` < 5.0 or `prior_total_avg` == 0, skip.** Prevents division-by-zero and low-baseline noise.
7. **Guard: if `prior_priority_avg` == 0, skip.** Cannot compute relative stability on a zero baseline.
8. Compute `total_hours_change_pct = ((recent_total_avg - prior_total_avg) / prior_total_avg) * 100` (result is a percentage, e.g., 22.5 means 22.5%).
9. Compute `total_hours_delta = recent_total_avg - prior_total_avg` (absolute hours/week).
10. Compute `priority_hours_change_pct = ((recent_priority_avg - prior_priority_avg) / prior_priority_avg) * 100`.
11. Surface pattern if ALL of: `total_hours_change_pct >= 15.0` AND `total_hours_delta >= 2.0` AND (`priority_hours_change_pct >= -10.0`) — i.e., priority hours dropped by no more than 10% relative, or grew.
12. Set `priority_hours_trend` to `"stable"` if `abs(priority_hours_change_pct) <= 10.0`, otherwise `"growing"`.

**Response shape:**
```json
{
  "pattern_type": "priority_protection",
  "narration_label": "Priority protection",
  "priority_id": "uuid",
  "priority_name": "Product development",
  "priority_status": "active",
  "calendar_keyword": "P1",
  "priority_hours_trend": "stable",
  "total_hours_change_pct": 22.5,
  "detail": "P1 hours stayed stable at ~12h/week despite total calendar growing 22%"
}
```

**`detail` string construction:** The `detail` field is built by the backend. If `calendar_keyword` is `null` — for ANY reason (retired with no snapshot keyword, active with NULL keyword due to bug) — `detail` must use `priority_name` instead. Example: `"Product development hours stayed stable at ~12h/week despite total calendar growing 22%"`. Never hardcode a keyword into `detail` without checking for null first. This rule applies universally to all patterns.

**`calendar_keyword` resolution:** Via shared `resolve_keyword()` helper. Same nullability rules as Pattern 1.

**Positive framing.** This is always a good signal — the user is successfully protecting what matters.

---

## 3. Architecture

### Layer 1: Backend Service

New file: `backend/apps/priority_guardian/services/pattern_service.py`

**Single public function:** `compute_patterns(user_id, session, correlation_id) -> dict`

This function:
1. Compute `current_week_start` via `get_current_week_start_utc()` and `window_start_date` via `current_week_start - relativedelta(months=6)` — both are `date` objects, computed once
2. Queries `pg_weekly_snapshots` for user with `week_start >= window_start_date` AND `week_start < current_week_start`
3. Queries `pg_priorities` for user (both active and retired)
4. Computes `weeks_available` = count of distinct `week_start` values from step 2
5. Checks global floor (`weeks_available` < 4 → return early with `data_insufficient: true`)
6. Runs each pattern computation
7. Returns `{"success": True, "data": {...}}` — data only, no `assistant_guidance`

**Shared helpers:**
- `get_current_week_start_utc() -> date` — pure, no I/O, returns UTC Monday
- `resolve_keyword(priority, snapshots_for_priority) -> str | None` — keyword resolution for active vs retired

**Computation rules:**
- Use `Decimal` end-to-end for all hour/percentage computations. **Conversion point:** the service returns dicts with `Decimal` values; the router MUST run `decimal_to_float_recursive(data)` over the entire `data` dict before returning the response. Implement this as a shared utility in `utils.py`. Never mix `Decimal` and `float` in intermediate arithmetic — `Decimal + float` silently coerces to `float`. Without the recursive converter, you'll get intermittent `TypeError: Object of type Decimal is not JSON serializable`.
- Return patterns in deterministic order: sort by `(pattern_type, priority_id, (priority_name or "").casefold())` for per-priority patterns. Cross-priority patterns (priority_switching) sort by `pattern_type` only. Stable identifiers (`pattern_type`, `priority_id`) come first to avoid rounding-drift issues; `priority_name` is tertiary. `casefold()` handles unicode edge cases. The `or ""` guard prevents exceptions on NULL/empty names from bad legacy rows.
- Every pattern instance includes `narration_label` — a human-friendly category name the LLM can use instead of `pattern_type`. This reduces the chance the model parrots internal identifiers. Labels: `"Consistency streak"`, `"Low investment"`, `"Priority changes"`, `"Priority protection"`.

**No caching.** Pattern computation is a few SQL queries over a small dataset (max 3 priorities × 26 weeks = 78 rows). No Redis, no background job. Compute on demand.

**No new database tables or migrations.** Reads only from `pg_weekly_snapshots` and `pg_priorities`.

### Layer 2: Backend Router

New file: `backend/apps/priority_guardian/routers/pattern_router.py`

**Single endpoint:** `GET /api/priority-guardian/patterns`

Follow the same URL prefix as all PG endpoints (`/api/priority-guardian/`). MCP tool calls `backend_get("/api/priority-guardian/patterns", user_id, correlation_id)`.

- Authenticated via `X-User-ID` header — use the same `validate_user_id_header` dependency as all other PG endpoints
- Extract `correlation_id` from `request.state.correlation_id` (same pattern as `weekly_report_router.py`)
- Pass `correlation_id` into `compute_patterns()` for traceability
- Returns `{"success": True, "data": {...}}` — **no `assistant_guidance` in backend response**

**Error handling:** Follow the same error envelope as all PG routers. On internal error, return `{"success": false, "error": {"code": "PATTERN_COMPUTE_ERROR", "message": "Pattern computation failed. Please try again."}}` with HTTP 500. **The message must be a hardcoded constant — never include exception strings, stack traces, or dynamic error details.** Log full error details server-side via `patterns.error` event. On missing/invalid user header, return 401 (handled by `validate_user_id_header`). MCP tool converts backend error responses into a `CallToolResult` with `isError=True` and a non-leaky message (never expose internal details to LLM).

**Canonical logging events:**
- `patterns.request.received` — user_id, correlation_id (request entry)
- `patterns.compute.done` — user_id, correlation_id, weeks_available, pattern_count (success)
- `patterns.data_insufficient` — user_id, correlation_id, weeks_available (below floor)
- `patterns.error` — user_id, correlation_id, error, error_type (unexpected failure)

### Layer 3: MCP Tool

New file: `mcp_server/priority_guardian/tools/get_patterns.py`

- Public tool, LLM-callable
- `read_only_hint: True`, `destructive_hint: False`, `open_world_hint: False` (no external API calls — pattern computation is purely database reads)
- `widget_uri: None` — no widget, LLM narrates patterns conversationally
- `widget_accessible: False` — no reason for widget to call this
- Required scopes: `["pg.access"]`
- Forwards to backend `GET /patterns` via `backend_get`
- **MCP tool layer adds `assistant_guidance`** based on the backend response data (patterns found / insufficient data / empty). Backend returns data only; MCP tool adds LLM behavior guidance. This keeps the backend API clean and follows the same separation pattern as other PG tools.
- Returns `structuredContent` with `data` + `assistant_guidance` as sibling top-level keys

**`assistant_guidance` placement:** Top-level key in `structuredContent`, NOT inside `_meta`. Convention: `_meta` is reserved for OpenAI transport fields (e.g., `openai/outputTemplate`). Follow the exact pattern used in `get_weekly_report.py` and `onboarding_calendar_setup.py`.

### Layer 4: Registration

**Backend router wiring:** Add `pattern_router` to the PG app's router include list (wherever `priorities_router`, `weekly_report_router`, `snapshot_router` etc. are mounted — check `backend/apps/priority_guardian/__init__.py` or the main app factory). Without this step, the endpoint will 404 even if the router file exists.

**MCP tool registration:**
- Add `GET_PATTERNS` to `TOOL_REGISTRY` in `tools/__init__.py`
- Add to `TOOL_INVOCATION_MESSAGES`: `"get_patterns": ("Analyzing your tracking patterns...", "Here's what I found in your history.")`
- Import follows existing pattern

---

## 4. Tool Description (controls WHEN LLM calls it)

```
Returns behavioral patterns detected from your priority tracking history. 
Patterns include consistency streaks, low-investment priorities, priority switching frequency, 
and priority protection under calendar pressure. Requires at least 4 weeks of tracking data.

Call this tool:
- During weekly reflection after presenting the weekly report
- When the user asks "how am I doing?", "any trends?", "what patterns do you see?"
- When the user asks about their tracking behavior over time

Do NOT call this tool:
- During onboarding (not enough data)
- When the user is doing CRUD operations on priorities
- If you already called it in this conversation and data hasn't changed
```

---

## 5. assistant_guidance (controls WHAT LLM says after)

Added by the MCP tool layer (not the backend). Include as top-level key in `structuredContent["assistant_guidance"]`. The guidance text varies by response state:

**When patterns found:**
```
Present these patterns as observations about how the user has been spending their time — based on what was actually logged and tagged in their calendar. Do not coach, judge, or prescribe. For positive signals (consistency streaks, priority protection), acknowledge warmly in one sentence. For neutral signals (low-investment priorities), state the numbers and ask what the user wants to do. For priority switching, present both interpretations — healthy pivoting or difficulty committing — and ask what's driving the changes. Keep it conversational. No bullet points, no headers, no numbered lists. Weave patterns into a natural narrative. Observed numbers ("0.5h/week", "8-week streak", "22% growth") are good — state them. Internal thresholds and rules must never be mentioned. Do not use the word "abandoned" — paraphrase neutrally (e.g., "getting very little time lately"). Do not repeat any internal field names or identifiers from the data verbatim — use the narration_label or your own phrasing instead. If a pattern has `calendar_keyword: null`, refer to the priority by name only — do not mention a keyword. For retired priorities, frame the pattern as historical ("before you retired it" or "when it was active") — do not imply the pattern is ongoing. Do not compute or invent patterns beyond what this response contains.
```

**When data insufficient:**
```
The user has [N] weeks of tracking data. We wait for at least 4 completed weeks of tracking snapshots before surfacing patterns. Mention this briefly and move on. Do not apologize or over-explain.
```

**When no patterns detected:**
```
No notable patterns detected yet. Mention this briefly. Do not fill with generic advice.
```

---

## 6. Response Shape

### Backend response (from `GET /patterns`):
Backend returns data only — no `assistant_guidance`. Includes `pattern_engine_version` for forward compatibility and `reason` enum for deterministic downstream behavior.
```json
{
  "success": true,
  "data": {
    "pattern_engine_version": "1.0",
    "reason": "PATTERNS_FOUND",
    "data_insufficient": false,
    "weeks_available": 12,
    "rolling_window_months": 6,
    "patterns": [
      { "pattern_type": "consistency_streak", ... },
      { "pattern_type": "abandoned_priority", ... }
    ],
    "pattern_count": 2
  }
}
```

**`reason` values:** `"INSUFFICIENT_WEEKS"` (below 4-week floor), `"NO_PATTERNS"` (enough data, nothing surfaced), `"PATTERNS_FOUND"` (at least one pattern). MCP tool uses `reason` to select the appropriate `assistant_guidance` variant — no prose parsing needed.

### MCP tool `structuredContent` (what LLM sees):
MCP tool takes backend data (including version) and adds `assistant_guidance`.
```json
{
  "success": true,
  "data": {
    "pattern_engine_version": "1.0",
    "reason": "PATTERNS_FOUND",
    "data_insufficient": false,
    "weeks_available": 12,
    "rolling_window_months": 6,
    "patterns": [
      { "pattern_type": "consistency_streak", ... },
      { "pattern_type": "abandoned_priority", ... }
    ],
    "pattern_count": 2
  },
  "assistant_guidance": "Present these patterns as observations..."
}
```

### MCP tool — insufficient data:
```json
{
  "success": true,
  "data": {
    "pattern_engine_version": "1.0",
    "reason": "INSUFFICIENT_WEEKS",
    "data_insufficient": true,
    "weeks_available": 2,
    "rolling_window_months": 6,
    "patterns": [],
    "pattern_count": 0
  },
  "assistant_guidance": "The user has 2 weeks of tracking data. We wait for at least 4 completed weeks of tracking snapshots before surfacing patterns. Mention this briefly and move on. Do not apologize or over-explain."
}
```

### MCP tool — enough data, no patterns:
```json
{
  "success": true,
  "data": {
    "pattern_engine_version": "1.0",
    "reason": "NO_PATTERNS",
    "data_insufficient": false,
    "weeks_available": 6,
    "rolling_window_months": 6,
    "patterns": [],
    "pattern_count": 0
  },
  "assistant_guidance": "No notable patterns detected yet. Mention this briefly. Do not fill with generic advice."
}
```

---

## 7. What's NOT in Scope

- No widget rendering (patterns are narrated by LLM)
- No new database tables or migrations
- No caching layer (dataset too small to warrant it)
- No pattern persistence (computed fresh each call)
- No pattern history ("you had this pattern last month too")
- No GDPR impact (read-only on existing data, no new data stored)
- No Celery background job
- No changes to existing tools (weekly report, onboarding, etc.)

---

## 8. Testing

### Unit Tests (pattern_service)

Test each pattern computation function in isolation with synthetic snapshot data.

**Shared helper tests:**
1. `resolve_keyword()` with active priority → returns `priority.calendar_keyword`
2. `resolve_keyword()` with retired priority → returns most recent non-NULL `calendar_keyword_at_snapshot`
3. `resolve_keyword()` with retired priority where all snapshots have NULL `calendar_keyword_at_snapshot` → returns `None`

**Consistency streak tests:**
4. Flexible priority with 6 consecutive weeks, latest `streak_at_snapshot` = 6 → pattern surfaced
5. Flexible priority with `streak_at_snapshot` = 2 → not surfaced (below 4 threshold)
6. Deadline priority with high streak → not surfaced (flexible only)
7. Retired flexible priority with streak ≥ 4 → surfaced with `priority_status: "retired"` and keyword from snapshot
8. Snapshot with NULL `streak_at_snapshot` → skipped, next non-NULL used
9. All snapshots have NULL `streak_at_snapshot` → fallback: compute streak from consecutive `actual_hours > 0`

**Abandoned priority tests:**
10. Active priority averaging 0.3h/week over last 4 completed weeks → surfaced
11. Active priority averaging 2.0h/week → not surfaced
12. Retired priority averaging 0.3h/week → NOT surfaced (retired is already acknowledged)
13. Active priority with only 3 qualifying snapshots → not surfaced (below 4-week floor)
14. Snapshot with NULL `actual_hours` → skipped in average computation

**Priority switching tests:**
15. 4 retirements in 6 months → surfaced
16. 1 retirement in 6 months → not surfaced (below 3 threshold)
17. Retirements older than 6 months → excluded from count
18. Only counts `retired_at` within window, not `created_at` for the threshold

**Priority protection tests:**
19. Priority hours stable, total hours grew 25%, 8+ qualifying snapshots → surfaced
20. Priority hours stable, total hours stable → not surfaced (no pressure change)
21. Priority hours dropped, total hours grew → not surfaced (not protecting)
22. Total hours grew by only 5% → not surfaced (below 15% threshold)
23. Priority with only 4 qualifying snapshots → skipped (needs 8 minimum for this pattern)
24. Snapshots with NULL `total_tracked_hours` or NULL `actual_hours` excluded from qualification count; if remaining < 8 → pattern skipped
25. Prior period `total_tracked_hours` avg < 5h/week → pattern skipped (low baseline guard)
26. 8 qualifying snapshots but NULL-skipping causes prior period to have only 3 → pattern skipped (per-period guard)
27. Boundary: `priority_hours_change_pct` = +10.0 → trend `"stable"`, surfaced. +10.01 → trend `"growing"`, surfaced. -10.0 → trend `"stable"`, surfaced. -10.01 → not surfaced (below -10% threshold).

**Detail string tests:**
28. Pattern with non-null `calendar_keyword` → `detail` includes keyword (e.g., "P1 hours stayed stable...")
29. Pattern with null `calendar_keyword` (retired, no snapshot keyword) → `detail` uses `priority_name` instead, never contains "None" or "null"
30. Active priority with NULL `calendar_keyword` (bug path) → `detail` uses `priority_name`, warning logged

**Defensive sorting tests:**
31. Priority with NULL `priority_name` → sorting doesn't crash, pattern still returned
32. Patterns returned in deterministic order regardless of insertion order

**Retirement boundary tests:**
33. Retired priority with `retired_at` on Wednesday → snapshots from that week (Monday `week_start`) included; snapshots from following week excluded
34. Retired priority with buggy post-retirement snapshots → excluded from Pattern 1 fallback computation

**Completed weeks computation tests:**
35. Snapshots from current week excluded from `weeks_available` count
36. `weeks_available` = distinct `week_start` count where `week_start < current_week_start`
37. Multiple snapshot rows per week (one per priority) counted as one week
38. `current_week_start` computed once and used consistently for both snapshot and priority queries
39. `get_current_week_start_utc()` returns Monday for known UTC dates: a Wednesday → previous Monday; a Monday → that Monday; a Sunday → previous Monday (critical boundary). Assert weekday() == 0 for all results.

**Global rules tests:**
40. User with 3 completed weeks of snapshots → `data_insufficient: true`, empty pattern list
41. User with 0 priorities → `data_insufficient: true`
42. User with 12 completed weeks → patterns computed normally
43. Snapshots older than 6 months excluded from all computations
44. Multiple patterns can be returned simultaneously
45. `weeks_available` >= 4 but all `actual_hours` NULL or zero across all priorities → no patterns surfaced, no crash
46. 3 retirements exist but `weeks_available` = 0 → `data_insufficient: true`, Pattern 3 NOT computed (floor enforced before any pattern logic)

**Pattern 1 fallback guard test:**
47. Deadline priority with NULL `streak_at_snapshot` on all snapshots AND `actual_hours > 0` → NOT surfaced (fallback still gates to flexible only)

### Integration Tests (backend endpoint + MCP tool)

**Backend endpoint tests:**
48. `GET /api/priority-guardian/patterns` returns 200 with `{"success": true, "data": {...}}` — no `assistant_guidance` in response
49. `GET /api/priority-guardian/patterns` returns 200 with `data_insufficient: true` for new user
50. `GET /api/priority-guardian/patterns` returns 401 without `X-User-ID` header
51. `correlation_id` is logged on request entry and passed to `compute_patterns()`
52. Backend error returns `{"success": false, "error": {"code": "PATTERN_COMPUTE_ERROR", "message": "Pattern computation failed. Please try again."}}` with 500 status — message is hardcoded constant
53. Response includes `pattern_engine_version: "1.0"` and `reason` enum in data
54. **E2E retired keyword flow:** Create priority with keyword, create 4+ weeks of snapshots, retire priority (keyword becomes NULL), call `GET /api/priority-guardian/patterns` — verify patterns return keyword resolved from snapshot, no crash, no NULL keyword in response for that priority
55. **Decimal serialization E2E:** Backend returns response with nested Decimal values inside patterns → JSON serialization succeeds, no `TypeError`, all numeric fields are floats in response. Converter must not corrupt `date` objects, `None` values, or strings.

**MCP tool tests:**
56. `get_patterns` tool registered in `TOOL_REGISTRY`
57. Tool forwards to backend, adds `assistant_guidance`, returns `structuredContent` with `assistant_guidance` as top-level key
58. Tool returns appropriate error when backend returns HTTP 200 with `success: false` — error output does NOT contain `PATTERN_COMPUTE_ERROR` or any backend error code
59. Tool returns appropriate error when backend returns HTTP 5xx or network error — same non-leaky output as test 58
60. Tool appears in `list_tools()` with correct metadata (readOnlyHint=true, open_world_hint=false, no widget_uri, no `_meta.openai/outputTemplate`)
61. `assistant_guidance` text varies by response state — MCP uses `reason` enum, not prose parsing
62. `assistant_guidance` does not contain the word "abandoned" or any `pattern_type` string verbatim

---

## 9. Pre-Deploy Checklist

- [ ] Read OPERATIONS.md for any additional pre-deploy tasks
- [ ] All tests pass (unit + integration)
- [ ] No new migration needed (verify)
- [ ] `get_patterns` appears in tool listing with correct metadata (no `_meta.openai/outputTemplate` since no widget)
- [ ] Backend response contains NO `assistant_guidance` (data only)
- [ ] MCP tool adds `assistant_guidance` as top-level key in `structuredContent` in all response paths
- [ ] Rolling window filter present in ALL pattern queries (6 months)
- [ ] Current week excluded from completed-weeks count
- [ ] `resolve_keyword()` helper used by all per-priority patterns; retired keywords never read from priority row
- [ ] NULL handling: any NULL required field causes snapshot to be skipped in that computation (all patterns)
- [ ] Pattern 4 requires 8 qualifying snapshots (not 4)
- [ ] Pattern 4 skips when prior period `total_tracked_hours` avg < 5h/week
- [ ] Pattern 4 percentage computed as `(recent - prior) / prior` — no division by zero possible due to 5h floor
- [ ] `current_week_start` computed via `get_current_week_start_utc()` (pure UTC, no external calls); computed once per request
- [ ] `correlation_id` logged and passed through from router to service
- [ ] Canonical logging events used: `patterns.request.received`, `patterns.compute.done`, `patterns.data_insufficient`, `patterns.error`
- [ ] Error envelope matches PG convention: `{"success": false, "error": {"code", "message"}}` — message is hardcoded constant, never dynamic
- [ ] `pattern_router` added to PG app router include list (same place as priorities_router, weekly_report_router, etc.)
- [ ] `pattern_engine_version: "1.0"` present in all backend data responses
- [ ] Pattern 1 fallback (compute streak from `actual_hours > 0`) works when `streak_at_snapshot` is all NULL
- [ ] Pattern 3 threshold uses retirements only; creations are informational
- [ ] Pattern 4 requires 4 qualifying snapshots in each period (recent and prior)
- [ ] `assistant_guidance` does not mention internal field names, thresholds, or computation details
- [ ] `assistant_guidance` does not use the word "abandoned" or repeat any `pattern_type` string verbatim
- [ ] Tool DESCRIPTION uses "low-investment priorities" not "abandoned priorities"
- [ ] Tool invocation messages registered: `("Analyzing your tracking patterns...", "Here's what I found in your history.")`
- [ ] No new environment variables needed
- [ ] Endpoint path is `/api/priority-guardian/patterns` — consistent with MCP tool `backend_get` call and integration tests
- [ ] `assistant_guidance` instructs LLM to frame retired priority patterns as historical (not ongoing)
- [ ] `calendar_keyword` is nullable in all pattern response shapes; LLM guidance handles null case
- [ ] `detail` strings use `priority_name` when `calendar_keyword` is null — never contain "None" or hardcoded keyword for retired priorities
- [ ] `decimal_to_float_recursive()` runs on entire `data` dict before JSON response; handles nested patterns, doesn't corrupt dates or strings
- [ ] MCP tool error output does not contain backend error codes (e.g., `PATTERN_COMPUTE_ERROR`) — keeps user-facing message generic

---

## 10. Compliance Notes

- **GDPR:** Read-only derived insights from existing tracking data. No new data categories stored. No new personal data collected. Privacy policy / DPAs should already cover analytics/insights derived from tracking data — this feature operates within that scope.
- **Data retention:** Rolling window (6 months) is query-side only — no data deletion.
- **OpenAI SDK:** Public tool with standard MCP response format. No widget. `assistant_guidance` follows established PG convention (top-level in `structuredContent`, added at MCP tool layer).
- **Scalability:** Pattern computation is O(priorities × weeks). Max 3 active + N retired priorities × 26 weeks. Negligible load. No caching needed at current scale.
- **Information leakage:** `assistant_guidance` explicitly instructs LLM not to mention internal field names, thresholds, or computation logic. The word "abandoned" (internal `pattern_type`) is paraphrased neutrally in user-facing narration. Observed numbers are allowed; internal rules are not.
