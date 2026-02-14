# ADR-001: Running Aggregates & Data Architecture

**Status:** Accepted (amended 2026-02-14)  
**Date:** 2026-02-12  

---

## Decisions

1. **Aggregates on `pg_priorities`:** `streak_count`, `avg_hours_week`, `total_hours_invested` stored as columns, updated once per week when a snapshot is finalized — not computed on-the-fly. `streak_count` is on the dashboard hot path (every widget mount, zero extra queries); the other two are weekly-report-only convenience columns that already exist in the schema.

2. **Streak = binary (hours > 0):** Not tied to `weekly_hour_target`. Any time invested keeps the streak; zero hours breaks it. Target measures pace, streak measures attention — different dimensions. Threshold-based alternatives rejected as punishing for freelancers with variable weeks.

3. **Semantic grouping in `pg_weekly_overview`**, not on `pg_weekly_snapshots`. Grouping is a user-week fact, not a priority-week fact — storing on snapshot rows would duplicate the same JSONB across 1-3 rows with no schema-enforced consistency. `UNIQUE(user_id, week_start)` enforces one row, one truth. Grouping is optional enrichment — LLM proposes, user confirms, depth is opt-in.

4. **Dashboard and weekly report must never share a cache.** Dashboard (`get_priorities` → `compute_time_allocation()`) hits Google Calendar API live on every widget mount (~5 API calls). Weekly report computes fresh 1-3 times per week. At current scale neither path is under load pressure — caching becomes relevant around 10K-20K DAU (see `pg_backlog_dashboard_caching.md`). The separation is a **correctness constraint**: if dashboard data is ever cached, the weekly report must still read fresh from Google to produce accurate snapshots. Dashboard will hit caching pressure first (higher frequency per user), but the rule exists to prevent stale data from contaminating the canonical record.

5. **Opportunistic snapshotting on dashboard load, not background jobs.** Snapshots are created when the user engages — `get_priorities` calls `ensure_snapshots_up_to_date(user_id)` which checks for missing completed weeks, backfills from Google Calendar, and updates aggregates. Idempotent (`UNIQUE(priority_id, week_start)`), non-blocking (failure logs but never breaks dashboard), capped at 3 weeks backfill (reasonable recovery window without excessive API calls). Background Celery job rejected: it snapshots for users who aren't engaging, which is monitoring, not coaching. PG meets users where they are — snapshot depth reflects engagement pattern, not UI navigation (see #10). `ensure_snapshots_up_to_date` is extracted as a callable function so it can move to Celery later if a real need emerges.

6. **Weekly report: on-demand read, always.** Available anytime the user asks — no frequency limit. Pure compute (fetch calendar via Google API, compute, display). Weekly report does NOT write snapshots — that's the dashboard path. Semantic grouping persistence (future) is the only write triggered via weekly report. Weekly reflection cadence is coached by the LLM via `assistant_guidance`, not enforced by the system.

7. **Display:** `streak_count`, `avg_hours_week`, and `total_hours_invested` on FlexibleCard only. Flexible cards show cumulative percentage and total hours. Deadline cards show neutral progress bar (`done_count / total_count`) — no aggregate hours because there's no target to benchmark against; the deliverable ratio is the actionable signal. *(Amended 2026-02-14: moved from weekly-report-only to dashboard after Inc 09 eliminated status labels. Further amended: dropped aggregates from DeadlineCard as noise.)*

8. **No categorical labels on dashboard.** `flex_status` and `pacing_status` are NOT surfaced on the live dashboard. "Behind" is interpretation; "4/7 done · 27d left" is fact. Dashboard = what IS. Weekly report = what it MEANS. Status fields still exist in `weekly_report_service` and are still captured in `pg_weekly_snapshots` by the snapshot service — they may be used in weekly report narration.

9. **Cumulative over current-week for flexible progress.** Current-week actual vs target is noise mid-week (Wednesday with 2h of 5h tells you nothing). The accountability signal is cumulative: `avg_hours_week / weekly_hour_target`. HourRing still shows current-week as a visual glance — different time horizons, complementary.

10. **Week navigator dropped from dashboard.** Cumulative `avg_hours_week` answers "Am I consistently investing?" without browsing individual weeks. Per-week snapshot data (`pg_weekly_snapshots`) is still captured and available for future weekly-report history views triggered conversationally.
