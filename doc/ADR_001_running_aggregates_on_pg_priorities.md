# ADR-001: Running Aggregates Stored on pg_priorities

**Status:** Accepted (amended 2026-02-13)  
**Date:** 2026-02-12  
**Context:** Priority Guardian v1.0 — Weekly Snapshot & Progress Tracking  

---

## Decision

Store `streak_count`, `avg_hours_week`, and `total_hours_invested` as columns on the `pg_priorities` table, updated when a weekly snapshot is finalized. Do not compute them on-the-fly from `pg_weekly_snapshots`.

## Context

PG tracks weekly progress per priority. Three aggregate values support the widget and LLM coaching:

- **streak_count** — consecutive weeks with any time invested (hours > 0). Binary: did you show up at all? Measures sustained attention, not performance. A 30-minute investment against a 10h target keeps the streak alive. Zero hours breaks it. The coaching value is in the break — it confronts the user with "if you can't invest even 30 minutes, is this honestly a priority?" This aligns with PG's subtractive facilitation philosophy.
- **avg_hours_week** — rolling average hours/week since last checkpoint. Not displayed on dashboard (too much noise). Used in weekly report narration to show pace over time. Resets when user renews at a checkpoint.
- **total_hours_invested** — cumulative hours across priority lifetime. Never resets. Used in LLM narration ("you've invested 47h in this so far"). Not needed for any computation — purely motivational context.

## Display Decisions

| Column | Dashboard card | Weekly report |
|--------|---------------|---------------|
| `streak_count` | **Yes** — FlexibleCard shows streak | Yes — narrated by LLM |
| `avg_hours_week` | **No** — too detailed, noise | Yes — pace context for LLM |
| `total_hours_invested` | **No** — motivational only | Yes — narrated by LLM |

These display decisions drive the performance justification. `streak_count` is on the hot read path (every widget mount). The other two are read once per week during report generation.

## Reason: Performance (for streak_count)

`get_priorities` runs on every widget mount. It loads all `pg_priorities` rows. `streak_count` as a column on that row comes for free — zero additional queries.

Computing streak from snapshots would require loading all recent snapshots per priority, walking backward to find the first zero-hour week. Unnecessary work on the most frequent read path.

## Reason: Convenience (for avg_hours_week, total_hours_invested)

These two columns are only read during weekly report generation (once/week). Computing them from snapshots at that point would be equally acceptable — the report flow already does heavier work (calendar fetch, snapshot save). However: the columns already exist in the schema (added as placeholders in Increment 02), they cost nothing to maintain (one UPDATE per week alongside the snapshot save), and removing them would require a migration for zero gain. They stay as convenience, not performance.

## Streak Definition

Streak = consecutive weeks where `actual_hours > 0` for the priority.

- Hours > 0 → streak continues (+1)
- Hours = 0 → streak resets to 0
- Applies to both flexible and deadline priority types
- Binary: did you invest any time at all, regardless of target

This is intentionally not tied to `weekly_hour_target`. The hour target measures performance (pace). The streak measures attention (consistency). These are different dimensions:

- **Target:** "Am I investing enough?" → answered by HourRing + avg_hours_week
- **Streak:** "Am I showing up at all?" → answered by streak_count

A freelancer who logs 1h against a 10h target in a chaotic week keeps their streak. The target signals they're behind on pace. Both are true simultaneously.

## Semantic Grouping

Non-priority calendar time is semantically grouped by the LLM during the weekly report conversation. This grouping is **not part of the initial snapshot save** — it requires LLM analysis and optionally user correction.

### Domain Analysis

Semantic grouping describes all non-priority calendar time for a user in a specific week. Its natural key is `(user_id, week_start)`. It does NOT describe a priority or a priority-week relationship. Storing it on `pg_weekly_snapshots` (keyed by `priority_id, week_start`) would duplicate the same JSONB blob across 1-3 snapshot rows per week — the same fact copied multiple times, creating multiple sources of truth with no schema-enforced invariant preventing divergence.

### Storage: Separate Table

`pg_weekly_overview` — one row per user per week. Owns the semantic grouping. Created in Increment 06 migration alongside `pg_weekly_snapshots`. Populated by Increment 07's `save_semantic_grouping` tool.

**Columns:**
- `id` — UUID primary key
- `user_id` — FK to `core_users.id`, CASCADE delete
- `week_start` — DATE, Monday of the reporting week
- `semantic_grouping` — JSONB, nullable. `null` until user confirms groupings.
- `created_at` — TIMESTAMP WITH TIME ZONE
- `updated_at` — TIMESTAMP WITH TIME ZONE

**Constraints:**
- UNIQUE: `(user_id, week_start)` — one overview per user per week. Invariant enforced by schema.

This keeps `pg_weekly_snapshots` clean (priority-scoped data only) and gives semantic grouping a single authoritative row per user-week.

### Shape

```json
[
  {"category": "Client calls", "hours": 8.0, "event_count": 5},
  {"category": "Tax & accounting", "hours": 4.0, "event_count": 3},
  {"category": "Admin", "hours": 3.25, "event_count": 4}
]
```

### Grouping Inputs

Event title (`summary`) AND event description (`description`). Both are available via the `calendar.events.readonly` scope. Descriptions significantly improve grouping quality — "Meeting" is useless, "Meeting - Q1 revenue review with finance team" is not.

### Why Optional Enrichment, Not Required

The snapshot is complete and useful the moment `get_weekly_report` runs (hours, counts, streaks, status). The user who wants just the numbers gets them immediately. The user who wants to reflect and understand their time allocation patterns stays in conversation, discusses groupings with the LLM, and the finalized groupings get saved to `pg_weekly_overview`. Depth is opt-in.

### Pie Chart

When semantic grouping exists in `pg_weekly_overview` for a week, a pie chart can render: P1/P2/P3 as individual slices (from `pg_weekly_snapshots`) + each semantic category as its own slice (from `pg_weekly_overview`). Full week in one visual. This is a separate widget view, not visible by default — callable when the user wants to see it. Defined in Increment 07.

## Hot Path vs Cold Path

**Decision (2026-02-13):** The dashboard progress bar (`get_priorities` → `compute_time_allocation()`) is the hot path. The weekly report (`get_weekly_report`) is the cold path.

### Dashboard = Hot Path

`get_priorities` is called on every widget mount — every conversation, every "how am I doing," every CRUD operation that refreshes the widget. It fetches priorities from DB (fast) AND calls `compute_time_allocation()` which hits the Google Calendar API live (slow: timezone fetch + paginated event fetch + keyword matching).

This is the path that needs caching. Every dashboard open = 2-3 Google API round-trips minimum. Without caching, scaling is bounded by Google's per-user rate limits, not server capacity. The existing Redis infrastructure (`needs_sync` flag, webhook idempotency) is built but not yet wired into PG's time-allocation path. A separate infrastructure increment will add cache-aside to `compute_time_allocation()`: check Redis for `pg:allocation:{user_id}:{week_start}` → cache hit skips Google entirely → webhook invalidation clears cache on calendar changes.

### Weekly Report = Cold Path

**Decision (2026-02-13):** The weekly report is computed once per week, not on demand. It is a reflection ritual, not a monitoring tool.

The intended trigger is the user's weekly check-in (e.g., during a scheduled "Priority Guardian Weekly Check-in" calendar event). The dashboard progress bar handles the everyday "where am I" question. The weekly report handles the "what does it mean" question — with full LLM narration, semantic grouping of non-priority time, and coaching observations.

This means:
- Weekly report always computes fresh from Google Calendar API (no caching). Acceptable at once-per-week frequency.
- Dashboard path must be cached (high frequency, same expensive computation).
- These two paths must NEVER share a cache. Dashboard reads cached allocation. Weekly report computes authoritative allocation. If the weekly report eventually persists snapshots, those snapshots are the canonical record — not a cached approximation.

### Consequence for Persistence (Future)

When snapshot persistence ships, the weekly report becomes the only write path for snapshots and aggregate updates. Its once-per-week cadence means:
- Snapshot finalization happens once per week per user (low write frequency)
- Backfill for missed weeks adds N Google API calls (capped at 12) — acceptable as a rare catch-up path
- Aggregate columns (`streak_count`, `avg_hours_week`, `total_hours_invested`) update once per week per priority

The dashboard reads these aggregate values from `pg_priorities` rows (already loaded, zero additional queries). The weekly report writes them. Clean read/write separation.

## Tradeoff

`get_weekly_report` handles snapshot persistence as part of its flow. The snapshot finalization (after the week closes) requires: INSERT snapshot row + UPDATE three columns on `pg_priorities` in a single transaction. This adds complexity to the write path, but that path executes once per week per priority.

If aggregate values drift out of sync with snapshot history (bug, partial failure), they can be recomputed from snapshots as a one-time repair. Snapshots are the source of truth for historical detail; aggregates are a read-optimized cache on the priority row.

## Backfill

When `get_weekly_report` runs for week Y, it checks if all intermediate weeks since the last snapshot have been captured. If week X has no snapshot, the report backfills week X first (fetches calendar data from Google for that week's date range, computes and saves snapshot + aggregates) before proceeding to week Y. This prevents streak breaks caused by missed reviews rather than missed work. The user never needs to know backfill happened.

**Risk:** Google Calendar data can be edited retroactively. Backfilled snapshots may not perfectly match what existed during the original week. This is an acceptable tradeoff — false streak breaks from missed reviews are worse than slight inaccuracy from retroactive edits.

## Alternatives Considered

**Compute all three from snapshots at read time.** Rejected for `streak_count` (hot path, every widget mount). Acceptable but unnecessary for the other two — columns already exist.

**Streak = hours ≥ weekly_hour_target.** Rejected. Punishing for freelancers with unpredictable weeks. A 4.5h week against a 5h target would break the streak. Discouraging rather than informative. The hour target already handles the "are you hitting your number" question via HourRing.

**Streak = hours ≥ 80% of target.** Rejected. Arbitrary threshold. Hard to explain to users. No clear advantage over binary.

**Store semantic grouping in initial snapshot.** Rejected. Grouping requires LLM analysis and optionally user correction. Blocking snapshot persistence on a conversational flow creates unnecessary coupling. The snapshot captures deterministic data immediately; semantic grouping enriches it later.

**Store semantic grouping as JSONB column on `pg_weekly_snapshots`.** Rejected. Semantic grouping is a user-week-level fact, not a priority-week-level fact. Storing it on snapshot rows (keyed by priority_id + week_start) duplicates the same data across 1-3 rows per week. No schema constraint can enforce consistency across those rows. Divergence requires developer discipline to prevent — and any architecture that requires discipline to stay correct will eventually break. A separate `pg_weekly_overview` table with UNIQUE(user_id, week_start) enforces the invariant by schema. One row, one fact, one source of truth.

**Backend pre-computes weekly reports via Celery.** Rejected for v1.0. Requires background token refresh, adds infrastructure complexity. Backfill-on-demand achieves the same data completeness without background jobs.

## Consequences

- `streak_count` displayed on FlexibleCard in the dashboard widget
- `avg_hours_week` and `total_hours_invested` NOT displayed on dashboard — weekly report only
- `get_weekly_report` tool handles snapshot persistence when the week is finalized
- `get_weekly_report` backfills any missing intermediate weeks before saving the requested week
- Streak reset logic (0 hours → reset) lives in the snapshot finalization path
- `avg_hours_week` recomputation requires querying recent snapshots at write time (acceptable — once/week)
- Retired priorities freeze all three columns; snapshot finalization guards at two levels: Python loop skips retired priorities, AND the SQL UPDATE includes `WHERE status = 'active'` as defense-in-depth against race conditions
- Backfill processes missing weeks in chronological order (oldest first), updating aggregates incrementally per week — not computed in parallel or from final state
- `pg_weekly_overview` table created in Increment 06 migration, populated by Increment 07's `save_semantic_grouping` tool
- `pg_weekly_snapshots` contains NO semantic grouping data — stays clean, priority-scoped only
- Pie chart widget view joins `pg_weekly_snapshots` (priority hours) + `pg_weekly_overview` (semantic categories) for the full picture (Increment 07)

## Known Limitations

1. **Backfilled deadline snapshots use current deliverable state.** When backfilling a snapshot for a past week (e.g., 3 weeks ago), `deliverables_completed` and `deliverables_total` are read from the live `priority.deliverables` collection — the current state, not the historical state. If the user completed 2 more deliverables since then, the backfilled snapshot records the current count. This means `pacing_status` for backfilled deadline priorities may be slightly inaccurate.

   This is an inherent limitation of backfill. We cannot reconstruct historical deliverable states from the available data — deliverable completion history is not stored. The tradeoff is acceptable: backfill's primary purpose is preventing false streak breaks from missed reviews, and the slight inaccuracy in deadline pacing status for historical weeks does not impact current coaching value. Do not attempt to "fix" this without adding deliverable history tracking, which would require schema changes and significantly more complexity.
