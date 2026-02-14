# ADR-001: PG V1.0 Product Design and Architectural Decisions

**Date last update:** 2026-02-14

---

## Decisions

1. **Aggregates on `pg_priorities`:** `streak_count`, `avg_target_achievement`, `total_hours_invested` stored as columns, updated once per week when a snapshot is finalized — not computed on-the-fly. All three are on the dashboard hot path (every widget mount, zero extra queries).

2. **Streak = binary (hours > 0):** Not tied to `weekly_hour_target`. Any time invested keeps the streak; zero hours breaks it. Target measures pace, streak measures attention — different dimensions. Threshold-based alternatives rejected as punishing for freelancers with variable weeks.

3. **Semantic grouping in `pg_weekly_overview`**, not on `pg_weekly_snapshots`. Grouping is a user-week fact, not a priority-week fact — storing on snapshot rows would duplicate the same JSONB across 1-3 rows with no schema-enforced consistency. `UNIQUE(user_id, week_start)` enforces one row, one truth. Grouping is optional enrichment — LLM proposes, user confirms, depth is opt-in. *(Note: Table `pg_weekly_overview` was dropped in cleanup migration s9t0u1v2w3x4 — semantic grouping persistence deferred indefinitely.)*

4. **Dashboard and weekly report must never share a cache.** Dashboard (`get_priorities` → `compute_time_allocation()`) hits Google Calendar API live on every widget mount (~5 API calls). Weekly report computes fresh 1-3 times per week. At current scale neither path is under load pressure — caching becomes relevant around 10K-20K DAU (see `pg_backlog_dashboard_caching.md`). The separation is a **correctness constraint**: if dashboard data is ever cached, the weekly report must still read fresh from Google to produce accurate snapshots. Dashboard will hit caching pressure first (higher frequency per user), but the rule exists to prevent stale data from contaminating the canonical record.

5. **Opportunistic snapshotting on dashboard load, not background jobs.** Snapshots are created when the user engages — `get_priorities` calls `ensure_snapshots_up_to_date(user_id)` which checks for missing completed weeks, backfills from Google Calendar, and updates aggregates. Idempotent (`UNIQUE(priority_id, week_start)`), non-blocking (failure logs but never breaks dashboard), capped at 3 weeks backfill (reasonable recovery window without excessive API calls). Background Celery job rejected: it snapshots for users who aren't engaging, which is monitoring, not coaching. PG meets users where they are — snapshot depth reflects engagement pattern, not UI navigation (see #10). `ensure_snapshots_up_to_date` is extracted as a callable function so it can move to Celery later if a real need emerges.

6. **Weekly report: on-demand read, always.** Available anytime the user asks — no frequency limit. Pure compute (fetch calendar via Google API, compute, display). Weekly report does NOT write snapshots — that's the dashboard path. Semantic grouping persistence (future) is the only write triggered via weekly report. Weekly reflection cadence is coached by the LLM via `assistant_guidance`, not enforced by the system.

8. **FLEXIBLE PRIO: Lead and Lag Measures.** Current-week actual vs target is a LEAD MEASURE mid-week (Wednesday with 2h of 5h tells you still 3 hours more to plan/invest); displayed via HourRing. LAG MEASURE: The accountability signal is cumulative: `avg_target_achievement`. Computation Logic: per-snapshot `actual_hours / target_hours * 100` using that snapshot's target (not current target), then `AVG()` across ALL snapshotted weeks — zero-hours weeks contribute 0%, pulling the average down. Minimum 2 snapshotted weeks to display (NULL until then). See #10 for full design rationale.

9. **`avg_target_achievement` replaces widget-side percentage computation.** Per-snapshot achievement = `actual_hours / target_hours * 100` using that week's target (not current target). Aggregated server-side as unweighted arithmetic mean across ALL snapshotted weeks — including zero-hours weeks (0% contribution). Stored on `pg_priorities`. Fixes target-change bug where changing weekly target retroactively skewed all historical percentages. Design choices: unweighted average (consistency signal, not volume ratio), zero-hours weeks INCLUDED (if you commit 5h/week and don't show up, the number must drop — that's accountability; streak tracks current momentum, achievement tracks cumulative commitment fulfillment), no cap at 100% (overinvestment is real data), minimum 2 snapshotted weeks before displaying (NULL until then, widget shows placeholder). *(Added 2026-02-14)*

