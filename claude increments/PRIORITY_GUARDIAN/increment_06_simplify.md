# PG Increment 06-S: Simplify Weekly Report to Live Computation Only

## Objective

Strip `get_weekly_report` down to its core: compute live report data from Google Calendar, return it, done. Remove all snapshot persistence, backfill logic, aggregate updates, and the `save_semantic_grouping` tool. The database tables stay (already migrated) but nothing writes to them until a future persistence increment.

This is a simplification of the existing Increment 06/07 implementation, not a new feature.

---

## Why

The current `get_weekly_report` carries persistence complexity that serves a future flow (weekly snapshots, backfill, aggregate tracking, semantic grouping save). That persistence layer is being deferred. Right now the persistence code creates a broken user flow: `assistant_guidance` proposes saving semantic groupings for current-week reports, but the backend rejects the save because no snapshot exists for incomplete weeks. Stripping persistence removes the broken path and leaves a clean, working computation tool.

The weekly report's value in v1.0 is the live narration — the LLM reads calendar data, assesses progress, and proposes semantic groupings conversationally. Persistence adds week-over-week comparison and saved groupings, which come later.

---

## Design Decision (Product)

- Weekly report = live computation every time it's called. No caching, no persistence.
- Semantic groupings = proposed by LLM in conversation text only. Not saved. Not rendered in a widget.
- Dashboard progress bar (via `get_priorities` → `compute_time_allocation`) remains the daily driver for "where am I."
- Weekly report is the once-per-week reflection tool for "what does it mean."
- `save_semantic_grouping` tool is disabled (removed from TOOL_REGISTRY) until persistence increment ships.

---

## What Exists (read these files)

### Backend — current state (over-engineered for v1.0)
- `backend/apps/priority_guardian/services/weekly_report_service.py` — `generate_weekly_report()` currently has: snapshot persistence for completed weeks, backfill logic for up to 12 missed weeks, aggregate updates (streak, avg_hours, total_hours) on `pg_priorities`, idempotency checks for existing snapshots, `other_hours` caching on `pg_weekly_overview`. All of this serves the deferred persistence layer.
- `backend/apps/priority_guardian/services/weekly_report_service.py` — `save_semantic_grouping()` function. Being deferred entirely.
- `backend/apps/priority_guardian/routers/weekly_report_router.py` — Two endpoints: `GET /weekly-report` and `POST /weekly-report/semantic-grouping`. The POST endpoint is being deferred.

### Backend — reusable (keep these)
- `backend/apps/priority_guardian/services/calendar_service.py` — `compute_allocation_from_events()`, `compute_week_boundaries()`, `list_events()`, event filtering helpers. All pure computation, no persistence. This is the core the weekly report builds on.
- `backend/apps/priority_guardian/services/weekly_report_service.py` — `compute_flex_status()`, `compute_pacing_status()`, `process_events_for_report()`, `is_week_complete()`. Pure functions, keep them.

### MCP Tools — current state
- `mcp_server/priority_guardian/tools/get_weekly_report.py` — Handler calls backend, normalizes response, builds `assistant_guidance`. The guidance currently references snapshots, backfill, saving semantic groupings — all broken for current-week requests.
- `mcp_server/priority_guardian/tools/save_semantic_grouping.py` — Entire tool is being disabled.
- `mcp_server/priority_guardian/tools/__init__.py` — `TOOL_REGISTRY` dict where tools are registered.

### Database tables (already migrated, leave in place)
- `pg_weekly_snapshots` — exists, stays empty. No writes until persistence increment.
- `pg_weekly_overview` — exists, stays empty. No writes until persistence increment.
- `pg_priorities` — `streak_count`, `avg_hours_week`, `total_hours_invested` columns exist as placeholders. Nothing writes to them until persistence increment.

### Architecture References (read, don't import as rules)
- `doc/ADR_001_running_aggregates_on_pg_priorities.md` — explains streak definition, display decisions, semantic grouping strategy. Still valid for the future persistence increment. Not actionable now.
- `doc/MCP Server Implementation Standard.md` — canonical dispatcher pattern, handler signature, error categories. All tools MUST follow this standard.

---

## Part A: Backend — Simplify `generate_weekly_report()`

### What to remove from the service

The `generate_weekly_report()` function in `weekly_report_service.py` must be stripped to:

1. Validate `week_start` (if provided, must be a Monday)
2. Get Google connection + valid access token
3. Get user timezone
4. Compute week boundaries
5. Load active priorities with deliverables from DB
6. Fetch calendar events from Google
7. Compute time allocation via `compute_allocation_from_events()`
8. Build per-priority report data (hours, event counts, status indicators)
9. Return the report

**Remove these code paths entirely:**
- Checking for existing snapshots (idempotency check)
- The `if not is_current:` persistence block (snapshot save, aggregate updates, `other_hours` caching on `pg_weekly_overview`)
- Backfill detection and execution (gap computation, multi-week calendar fetches, `MAX_BACKFILL_WEEKS`)
- `save_snapshot_and_update_aggregates()` function — not called, can stay in the file as dead code OR be removed. Either way, no code path should reach it.
- `get_most_recent_snapshot_week()` — only used by backfill
- `snapshot_exists()` — only used by backfill
- `_build_report_from_snapshots()` — only used by idempotent return path

**Keep these pure functions (still needed by live computation):**
- `is_week_complete()` — still used to set `is_current_week` flag in response
- `compute_flex_status()` — computes flexible priority status from live hours
- `compute_pacing_status()` — computes deadline priority status from deliverables
- `process_events_for_report()` — filters events and matches keywords

**Remove these calls from the computation path:**
- `get_previous_week_snapshot()` — remove the call entirely. No snapshots exist, so it always returns `null`. Hardcode `previous_week: null` on every priority in the response. When persistence ships, re-add the query. Don't keep a DB query that returns nothing by design — it's confusing, not just wasteful.

### What to remove from the router

- Remove the `POST /weekly-report/semantic-grouping` endpoint entirely — delete the route handler, don't comment it out. A dangling endpoint that returns 500 or "not implemented" is worse than no endpoint.
- The `SemanticCategory` and `SemanticGroupingRequest` Pydantic models: remove. No code references them.
- The `GET /weekly-report` endpoint stays, but its docstring should reflect the simplified behavior (no snapshot persistence, no backfill).

### Response shape (keep identical for forward compatibility)

The response shape MUST NOT change. Future persistence increment will re-add the write paths and the response already has the right fields:

```json
{
  "success": true,
  "data": {
    "week_start": "2026-02-09",
    "week_end": "2026-02-15",
    "is_current_week": true,
    "snapshot_saved": false,
    "weeks_backfilled": 0,
    "backfill_truncated": false,
    "priorities": [...],
    "time_allocation": {...},
    "all_events": [...]
  }
}
```

`snapshot_saved` will always be `false`. `weeks_backfilled` will always be `0`. `backfill_truncated` will always be `false`. `previous_week` on each priority will always be `null`. These fields stay in the response — they're inert but maintain contract stability.

**Cache separation:** When the dashboard caching increment ships (Redis cache-aside for `compute_time_allocation()`), the weekly report computation path must NOT read from that cache. Weekly report always computes fresh from Google Calendar API. Dashboard reads cached. These are separate paths with separate data freshness guarantees.

### Semantic grouping code in the service

`save_semantic_grouping()` function and `SemanticGroupingError` class: leave in the file or remove. No code path calls them. The function is dead until the persistence increment re-enables it.

---

## Part B: MCP Tool — Simplify `get_weekly_report`

### Tool annotations update

```
read_only_hint=False   # Stays False. No snapshot writes, but token refresh can write to core_connections (access_token, token_expires_at).
open_world_hint=True   # Still True. Calls Google Calendar API.
widget_accessible=False # Stays False. Conversational tool.
widget_uri=None        # Stays None. No widget.
```

### `assistant_guidance` rewrite

The current `_build_assistant_guidance()` function references snapshots, backfill, and saving semantic groupings. All of that is broken or deferred. Rewrite the guidance to reflect what the tool actually does now:

**Guidance must tell the LLM to:**
- Narrate per-priority results: hours invested, comparison to target (flex) or pacing (deadline)
- For flexible priorities: note if ahead/on_track/behind target. Mention that streaks and averages will be tracked once weekly snapshots are enabled (or just skip mentioning them — they're zero)
- If `is_current_week: true`: frame as a mid-week check-in, numbers will change
- If `is_current_week: false`: frame as a completed week reflection
- Semantically group non-priority events based on titles/descriptions into approximate categories. Present these conversationally (e.g., "Your non-priority time breaks down roughly as: Client calls ~8h, Admin ~3h, Learning ~2h")
- Do NOT propose saving the groupings. Do NOT ask if the user wants to save. Semantic groupings are conversational observations only in this version.
- Frame total time allocation: priority time vs non-priority time
- Keep tone reflective and coaching-oriented
- If this is the first report (no `previous_week` on any priority): welcome framing. Note that week-over-week comparison will be available once weekly snapshots are enabled.
- Do NOT repeat raw numbers verbatim — present insights and patterns

**Remove from guidance:**
- Any mention of snapshots being saved
- Any mention of backfill
- Any mention of "save_semantic_grouping" or saving categories
- Any ask about whether the user wants to save/confirm groupings

### Handler

The handler logic stays the same (call backend, normalize response, build structured content). Only the guidance content changes.

---

## Part C: Disable `save_semantic_grouping`

### TOOL_REGISTRY

Remove `save_semantic_grouping` from `TOOL_REGISTRY` in `mcp_server/priority_guardian/tools/__init__.py`. Also remove it from `TOOL_INVOCATION_MESSAGES` if present.

The tool file (`save_semantic_grouping.py`) can stay on disk. It's just not registered, so the dispatcher never routes to it.

### Why disable vs delete

The tool code is correct and tested for the future persistence flow. Keeping the file avoids rewriting it later. Removing from the registry is a one-line change that cleanly disables it.

---

## Part D: Widget — Streak Display (no change needed)

The FlexibleCard already renders streak when `streakCount > 0` and hides it when 0 or undefined. Since nothing writes to `streak_count` on `pg_priorities`, it stays at default (0). The widget will simply not show a streak indicator. This is correct behavior — no visual noise, no broken display.

When the persistence increment ships and starts writing `streak_count`, the widget will automatically start showing it. No widget change needed now or later.

---

## What This Increment Does NOT Touch

- Database tables (`pg_weekly_snapshots`, `pg_weekly_overview`) — already migrated, stay empty
- `pg_priorities` aggregate columns (`streak_count`, `avg_hours_week`, `total_hours_invested`) — stay at defaults
- `get_priorities` tool and dashboard widget — unchanged
- `compute_time_allocation()` in calendar service — unchanged
- Alembic migrations — no new migration needed
- OAuth / Google connection flow — unchanged
- Widget React code — no changes

---

## Unit Tests

### Backend Service — `generate_weekly_report()` (simplified)
- No active priorities → returns empty report with `snapshot_saved: false`
- Active priorities + Google Calendar returns events → report contains per-priority hours, event counts, correct `is_current_week` flag
- `snapshot_saved` is always `false` regardless of whether week is current or past
- `weeks_backfilled` is always `0`
- `previous_week` is always `null` on every priority (no snapshots to compare against)
- `all_events` includes event title and description, excludes declined/cancelled/all-day events
- `matched_keywords` correctly populated per event
- Google connection missing → appropriate error
- Token refresh failure → appropriate error

### Backend Service — Pure computation functions (existing, verify still passing)
- `compute_flex_status()`: 80%/110% thresholds
- `compute_pacing_status()`: deliverable completion vs time elapsed
- `process_events_for_report()`: filtering and keyword matching
- `is_week_complete()`: timezone-aware week completion check

### MCP Tool — `get_weekly_report` handler
- Successful report → `CallToolResult` with `structuredContent` containing report data + updated `assistant_guidance`
- `assistant_guidance` does NOT contain "save", "snapshot", "backfill", or "confirm" when referring to semantic groupings
- `assistant_guidance` DOES contain semantic grouping proposal as conversational narration
- Current week → guidance mentions mid-week preview
- Past completed week → guidance mentions completed week reflection
- Backend error → `isError=True` with user-facing message

### MCP Tool — `save_semantic_grouping` disabled
- `save_semantic_grouping` is NOT in `TOOL_REGISTRY`
- Dispatcher returns "unknown tool" error if somehow called

---

## Integration Tests

### Weekly Report — Live Computation Flow
- Create user with Google connection + 2 active priorities (1 deadline, 1 flexible) → mock Google Calendar API with keyword-matched events → call `GET /api/priority-guardian/weekly-report` → verify: response contains correct per-priority hours, `snapshot_saved: false`, `weeks_backfilled: 0`, `previous_week: null` on all priorities, `all_events` populated with titles and descriptions

### Weekly Report — Past Week (no persistence)
- Call `GET /api/priority-guardian/weekly-report?week_start=2026-02-03` (past completed Monday) → verify: response has `is_current_week: false`, `snapshot_saved: false`, NO rows created in `pg_weekly_snapshots`, NO rows created in `pg_weekly_overview`, `pg_priorities` aggregate columns unchanged

### Weekly Report — Calendar Failure
- Google Calendar API fails → endpoint returns 502/503 → MCP tool returns `isError=True`

### Tool Registry — save_semantic_grouping absent
- `save_semantic_grouping` not in `TOOL_REGISTRY` dict in code
- MCP `tools/list` response does not include `save_semantic_grouping` (verify at protocol level, not just code)

---

## Production Readiness (Increment Context)

### Scalability
- Every `get_weekly_report` call hits Google Calendar API (timezone + events). No caching. This is acceptable because the weekly report is a low-frequency path (once per week per user). The hot path is the dashboard via `get_priorities` → `compute_time_allocation()` — that's the path that needs caching (separate infrastructure increment).

### GDPR / Data Retention
- No new PG data written — no snapshots, no overview rows, no aggregate updates. Token refresh may update `core_connections` (existing OAuth maintenance, already covered by core retention policy). `all_events` with titles and descriptions flows to the LLM ephemerally and is not persisted anywhere.

### OpenAI SDK Compliance
- `save_semantic_grouping` removed from registry, no orphan tool visible to ChatGPT
- `read_only_hint` stays `False` on `get_weekly_report` (token refresh can write to `core_connections`)

### Load Behavior
- Weekly report: 1-3 Google API calls per invocation (timezone + events pages). Low frequency. No PG snapshot/overview/aggregate writes; token refresh may update `core_connections` (existing OAuth maintenance, not new data).
- Dashboard: unchanged, still the hot path.

---

## Validation Criteria (Definition of Done)

1. `generate_weekly_report()` returns correct live data for both current and past weeks
2. No writes to `pg_weekly_snapshots`, `pg_weekly_overview`, or `pg_priorities` aggregate columns from the weekly report path
3. Response shape unchanged (all fields present, persistence fields inert)
4. `get_weekly_report` MCP tool returns updated `assistant_guidance` with no persistence references
5. `assistant_guidance` proposes semantic groupings conversationally without asking to save
6. `save_semantic_grouping` not in `TOOL_REGISTRY`
7. `POST /weekly-report/semantic-grouping` route removed; endpoint returns 404 (not a custom handler, just unregistered)
8. No `get_previous_week_snapshot()` DB queries in the simplified computation path
9. All unit tests pass
10. All integration tests pass
11. Existing tests for pure computation functions (`compute_flex_status`, `compute_pacing_status`, etc.) still pass
12. No regressions on `get_priorities` / dashboard widget

