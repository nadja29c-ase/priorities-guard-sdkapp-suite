Here's everything Claude Code needs to fix, consolidated:

FILE 1: backend/apps/priority_guardian/services/snapshot_service.py
Fix A — _update_aggregates(): Replace += with SUM for total_hours_invested
Current:
pythontotal_hours_invested = total_hours_invested + :hours
Change to: query SUM(actual_hours) from snapshots (same pattern as AVG already does), then SET the value directly. This eliminates drift on re-runs or backfill changes.
Fix B — _update_aggregates(): avg_hours falsy check drops zero
Current:
python"avg_hours": Decimal(str(avg_hours)) if avg_hours else None,
Fix:
python"avg_hours": Decimal(str(avg_hours)) if avg_hours is not None else None,

FILE 2: backend/apps/priority_guardian/db_models.py
Fix C — PgWeeklySnapshot: Add UniqueConstraint to __table_args__
Add to existing __table_args__:
pythonUniqueConstraint("priority_id", "week_start", name="<match migration name exactly>"),
Check p6k7l8m9n0o1_add_pg_weekly_snapshot_tables.py for the exact constraint name.
Fix D — PgWeeklyOverview: Add __table_args__ with UniqueConstraint
Currently has no __table_args__. Add:
python__table_args__ = (
    UniqueConstraint("user_id", "week_start", name="<match migration name exactly>"),
)
Check the migration for the exact constraint name.
Fix E — PgPriority.streak_count: Fix stale comment
Current: comment="Future: consecutive weeks meeting target"
Fix: comment="Consecutive weeks with hours > 0 (binary streak rule, see ADR-001)"
Fix F — PgWeeklySnapshot class docstring: Stale creation path
Replace Created when a completed week is finalized via the get_weekly_report tool. with Created opportunistically on dashboard load via ensure_snapshots_up_to_date(). See ADR-001 Decision 5.
Replace Immutable after creation (no overwrites). with Immutable after creation — INSERT ON CONFLICT DO NOTHING, no updates.

FILE 3: backend/apps/priority_guardian/routers/priorities_router.py
Fix G — build_priorities_response(): Active-first ordering is reversed
Current:
python.order_by(PgPriority.status.desc(), PgPriority.created_at.asc())
Fix:
python.order_by(PgPriority.status.asc(), PgPriority.created_at.asc())
"active" < "retired" alphabetically, so ASC puts active first.
Fix H — avg_hours_week falsy check
Current:
pythonpriority_data["avg_hours_week"] = float(p.avg_hours_week) if p.avg_hours_week else None
Fix:
pythonpriority_data["avg_hours_week"] = float(p.avg_hours_week) if p.avg_hours_week is not None else None
Fix I — weekly_hour_target falsy check (consistency)
Current:
python"weekly_hour_target": float(p.weekly_hour_target) if p.weekly_hour_target else None,
Fix:
python"weekly_hour_target": float(p.weekly_hour_target) if p.weekly_hour_target is not None else None,

Add UniqueConstraint to imports in db_models.py:
pythonfrom sqlalchemy import UniqueConstraint
Do NOT generate a new migration. These constraints already exist in the DB. Run alembic check after — should detect no diff. If it does, constraint names don't match the migration.
Do NOT change snapshot service structure, backfill logic, streak logic, error handling, MCP handler, or widget code.
Tests: Add one test to test_priorities_router.py asserting active priorities appear before retired. Ensure Inc 08 test suite (still pending) covers the SUM-based total_hours_invested and the is not None avg behavior.