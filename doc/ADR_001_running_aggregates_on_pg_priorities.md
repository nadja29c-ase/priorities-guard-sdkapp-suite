# ADR-001: Running Aggregates & Data Architecture

**Status:** Accepted (amended 2026-02-13)  
**Date:** 2026-02-12  

---

## Decisions

1. **Aggregates on `pg_priorities`:** `streak_count`, `avg_hours_week`, `total_hours_invested` stored as columns, updated once per week when a snapshot is finalized — not computed on-the-fly. `streak_count` is on the dashboard hot path (every widget mount, zero extra queries); the other two are weekly-report-only convenience columns that already exist in the schema.

2. **Streak = binary (hours > 0):** Not tied to `weekly_hour_target`. Any time invested keeps the streak; zero hours breaks it. Target measures pace, streak measures attention — different dimensions. Threshold-based alternatives rejected as punishing for freelancers with variable weeks.

3. **Semantic grouping in `pg_weekly_overview`**, not on `pg_weekly_snapshots`. Grouping is a user-week fact, not a priority-week fact — storing on snapshot rows would duplicate the same JSONB across 1-3 rows with no schema-enforced consistency. `UNIQUE(user_id, week_start)` enforces one row, one truth. Grouping is optional enrichment — LLM proposes, user confirms, depth is opt-in.

4. **Dashboard and weekly report must never share a cache.** Dashboard (`get_priorities` → `compute_time_allocation()`) hits Google Calendar API live on every widget mount (~5 API calls). Weekly report computes fresh 1-3 times per week. At current scale neither path is under load pressure — caching becomes relevant around 10K-20K DAU (see `pg_backlog_dashboard_caching.md`). The separation is a **correctness constraint**: if dashboard data is ever cached, the weekly report must still read fresh from Google to produce accurate snapshots. Dashboard will hit caching pressure first (higher frequency per user), but the rule exists to prevent stale data from contaminating the canonical record.

5. **Opportunistic snapshotting on dashboard load, not background jobs.** Snapshots are created when the user engages — `get_priorities` calls `ensure_snapshots_up_to_date(user_id)` which checks for missing completed weeks, backfills from Google Calendar, and updates aggregates. Idempotent (`UNIQUE(priority_id, week_start)`), non-blocking (failure logs but never breaks dashboard), capped at 3 weeks backfill (matches UI history depth). Background Celery job rejected: it snapshots for users who aren't engaging, which is monitoring, not coaching. PG meets users where they are — history depth reflects engagement pattern. `ensure_snapshots_up_to_date` is extracted as a callable function so it can move to Celery later if a real need emerges.

6. **Weekly report: on-demand read, always.** Available anytime the user asks — no frequency limit. Pure compute (fetch calendar via Google API, compute, display). Weekly report does NOT write snapshots — that's the dashboard path. Semantic grouping persistence (future) is the only write triggered via weekly report. Weekly reflection cadence is coached by the LLM via `assistant_guidance`, not enforced by the system.

7. **Display:** `streak_count` on dashboard FlexibleCard. `avg_hours_week` and `total_hours_invested` in weekly report LLM narration only — too noisy for dashboard.
