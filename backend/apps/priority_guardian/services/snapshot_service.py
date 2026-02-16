"""
Snapshot service for Priority Guardian.

Creates weekly snapshots opportunistically when the user opens the dashboard.
Updates running aggregates (streak_count, total_hours_invested, avg_target_achievement)
on pg_priorities.

See ADR-001 for design rationale and increment_08_snapshots.md for full spec.
"""

import structlog
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select, func, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.models import CoreConnection
from backend.core.google_calendar import list_events, get_user_timezone
from backend.core.google_token_management import ensure_valid_access_token
from backend.apps.priority_guardian.db_models import PgPriority, PgWeeklySnapshot
from backend.apps.priority_guardian.services.calendar_service import (
    compute_week_boundaries,
    compute_allocation_from_events,
    to_rfc3339,
)
from backend.apps.priority_guardian.services.weekly_report_service import (
    is_week_complete,
)

logger = structlog.get_logger(__name__)

# Maximum weeks to backfill (per spec)
MAX_BACKFILL_WEEKS = 3


async def ensure_snapshots_up_to_date(
    user_id: UUID,
    session: AsyncSession,
    http_client: httpx.AsyncClient,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """
    Ensure weekly snapshots are up to date for a user.

    Called opportunistically on dashboard load. Creates missing snapshots for
    up to 3 completed weeks, updates running aggregates on pg_priorities.

    This function is:
    - Idempotent: duplicate calls produce no duplicate rows
    - Non-blocking: failures don't propagate to caller
    - Failure-tolerant: partial success is reported, not raised

    Args:
        user_id: User ID (UUID)
        session: Database session
        http_client: HTTP client for Google API calls
        correlation_id: Optional correlation ID for logging

    Returns:
        {"checked": int, "created": int, "errors": int}
    """
    log = {"user_id": str(user_id), "correlation_id": correlation_id}

    try:
        return await _ensure_snapshots_impl(user_id, session, http_client, log)
    except Exception as e:
        # NEVER raise - caller must not break
        logger.error(
            "snapshot.unexpected_error",
            error=str(e),
            error_type=type(e).__name__,
            **log
        )
        return {"checked": 0, "created": 0, "errors": 1}


async def _ensure_snapshots_impl(
    user_id: UUID,
    session: AsyncSession,
    http_client: httpx.AsyncClient,
    log: dict,
) -> dict[str, Any]:
    """
    Implementation of ensure_snapshots_up_to_date.

    Separated for cleaner error handling wrapper.
    """
    # -------------------------------------------------------------------------
    # Step 1: Get Google connection and timezone
    # -------------------------------------------------------------------------
    result = await session.execute(
        select(CoreConnection).where(
            CoreConnection.user_id == user_id,
            CoreConnection.provider == "google",
            CoreConnection.connection_type == "google",
            CoreConnection.revoked_at.is_(None),
        )
    )
    connection = result.scalar_one_or_none()

    if not connection:
        logger.info("snapshot.no_google_connection", **log)
        return {"checked": 0, "created": 0, "errors": 0}

    # Ensure valid access token
    token_result = await ensure_valid_access_token(connection, session, http_client)
    if "error" in token_result:
        logger.warning(
            "snapshot.token_error",
            error_code=token_result["error"],
            **log
        )
        return {"checked": 0, "created": 0, "errors": 1}

    access_token = token_result["access_token"]

    # Get user's timezone
    timezone_str = await get_user_timezone(http_client, access_token, log.get("correlation_id"))

    # -------------------------------------------------------------------------
    # Step 2: Determine completed weeks to check (max 3)
    # -------------------------------------------------------------------------
    target_weeks = _compute_target_weeks(timezone_str, MAX_BACKFILL_WEEKS)

    if not target_weeks:
        logger.info("snapshot.no_completed_weeks", **log)
        return {"checked": 0, "created": 0, "errors": 0}

    # -------------------------------------------------------------------------
    # Step 3: Find which weeks already have snapshots
    # -------------------------------------------------------------------------
    existing_result = await session.execute(
        select(PgWeeklySnapshot.week_start)
        .where(
            PgWeeklySnapshot.user_id == user_id,
            PgWeeklySnapshot.week_start.in_(target_weeks),
        )
        .distinct()
    )
    existing_weeks = {row[0] for row in existing_result.fetchall()}

    missing_weeks = [w for w in target_weeks if w not in existing_weeks]

    if not missing_weeks:
        logger.info(
            "snapshot.all_exist",
            checked=len(target_weeks),
            **log
        )
        return {"checked": len(target_weeks), "created": 0, "errors": 0}

    logger.info(
        "snapshot.backfill_needed",
        target_weeks=[str(w) for w in target_weeks],
        missing_weeks=[str(w) for w in missing_weeks],
        **log
    )

    # -------------------------------------------------------------------------
    # Step 4: Load active priorities (once, reused for all weeks)
    # -------------------------------------------------------------------------
    priorities_result = await session.execute(
        select(PgPriority)
        .where(
            PgPriority.user_id == user_id,
            PgPriority.status == "active",
        )
    )
    priorities = list(priorities_result.scalars().all())

    if not priorities:
        logger.info("snapshot.no_active_priorities", **log)
        return {"checked": len(target_weeks), "created": 0, "errors": 0}

    # -------------------------------------------------------------------------
    # Step 5: Process missing weeks (chronological order, oldest first)
    # -------------------------------------------------------------------------
    created_count = 0
    error_count = 0

    for week_start in sorted(missing_weeks):
        try:
            week_created = await _create_snapshots_for_week(
                user_id=user_id,
                week_start=week_start,
                timezone_str=timezone_str,
                priorities=priorities,
                access_token=access_token,
                session=session,
                http_client=http_client,
                log=log,
            )
            if week_created:
                created_count += 1
        except Exception as e:
            logger.warning(
                "snapshot.week_failed",
                week_start=str(week_start),
                error=str(e),
                error_type=type(e).__name__,
                **log
            )
            error_count += 1
            # Continue to next week - don't let one week's failure block others

    logger.info(
        "snapshot.complete",
        checked=len(target_weeks),
        created=created_count,
        errors=error_count,
        **log
    )

    return {"checked": len(target_weeks), "created": created_count, "errors": error_count}


def _compute_target_weeks(timezone_str: str, max_weeks: int) -> list[date]:
    """
    Compute the last N completed week Mondays relative to now in user timezone.

    A week is complete when now() >= next Monday 00:00 in user timezone.

    Args:
        timezone_str: IANA timezone string
        max_weeks: Maximum number of weeks to return

    Returns:
        List of Monday dates (oldest first), up to max_weeks
    """
    try:
        tz = ZoneInfo(timezone_str)
    except Exception:
        tz = ZoneInfo("UTC")

    now = datetime.now(tz)

    # Find this week's Monday
    days_since_monday = now.weekday()
    this_monday = (now - timedelta(days=days_since_monday)).date()

    # Check completed weeks going backward
    completed_weeks = []
    for i in range(1, max_weeks + 1):
        candidate_monday = this_monday - timedelta(weeks=i)
        if is_week_complete(candidate_monday, timezone_str):
            completed_weeks.append(candidate_monday)

    # Return oldest first (for chronological processing)
    return list(reversed(completed_weeks))


async def _create_snapshots_for_week(
    user_id: UUID,
    week_start: date,
    timezone_str: str,
    priorities: list[PgPriority],
    access_token: str,
    session: AsyncSession,
    http_client: httpx.AsyncClient,
    log: dict,
) -> bool:
    """
    Create snapshot rows for all active priorities for a specific week.

    Returns True if at least one snapshot was created, False otherwise.
    """
    # Compute week boundaries
    week_start_dt, week_end_dt = compute_week_boundaries(timezone_str, week_start)
    week_end = week_start + timedelta(days=6)  # Sunday for display

    # Fetch events from Google Calendar
    time_min = to_rfc3339(week_start_dt)
    time_max = to_rfc3339(week_end_dt)

    events, pages_failed = await list_events(
        http_client,
        access_token,
        time_min,
        time_max,
        max_results_per_page=250,
        max_pages=10,
    )

    if pages_failed > 0:
        logger.warning(
            "snapshot.pages_failed",
            week_start=str(week_start),
            pages_failed=pages_failed,
            **log
        )

    # Compute allocation
    allocation = compute_allocation_from_events(events)
    keywords_data = allocation["keywords"]

    # Create snapshots for each priority
    any_created = False

    for priority in priorities:
        # Skip if priority didn't exist during this week
        # week_end < created_at means the entire week ended before priority was created
        priority_created_date = priority.created_at.date()
        if week_end < priority_created_date:
            logger.debug(
                "snapshot.skip_pre_creation_week",
                priority_id=str(priority.id),
                week_start=str(week_start),
                week_end=str(week_end),
                priority_created=str(priority_created_date),
                **log
            )
            continue

        kw = priority.calendar_keyword
        kw_data = keywords_data.get(kw, {"hours": 0.0, "event_count": 0})
        actual_hours = kw_data["hours"]

        # Compute streak
        streak = await _compute_streak(
            priority_id=priority.id,
            week_start=week_start,
            actual_hours=actual_hours,
            session=session,
        )

        # Build insert params
        insert_params = {
            "priority_id": priority.id,
            "user_id": user_id,
            "week_start": week_start,
            "week_end": week_end,
            "actual_hours": Decimal(str(actual_hours)),
            "streak_at_snapshot": streak,
            # target_hours only set for flexible priorities
            "target_hours": priority.weekly_hour_target if priority.type == "flexible" else None,
        }

        # INSERT with ON CONFLICT DO NOTHING RETURNING id
        # If RETURNING returns a row, insert succeeded. If empty, row already existed.
        stmt = (
            insert(PgWeeklySnapshot)
            .values(**insert_params)
            .on_conflict_do_nothing(index_elements=["priority_id", "week_start"])
            .returning(PgWeeklySnapshot.id)
        )
        result = await session.execute(stmt)
        inserted_row = result.fetchone()

        if inserted_row:
            # Insert succeeded - update aggregates
            await _update_aggregates(
                priority_id=priority.id,
                streak=streak,
                actual_hours=actual_hours,
                session=session,
            )
            any_created = True

            logger.debug(
                "snapshot.row_created",
                priority_id=str(priority.id),
                week_start=str(week_start),
                actual_hours=actual_hours,
                streak=streak,
                **log
            )
        else:
            # Row already existed - skip aggregate update
            logger.debug(
                "snapshot.row_exists",
                priority_id=str(priority.id),
                week_start=str(week_start),
                **log
            )

    # Commit all changes for this week
    await session.commit()

    return any_created


async def _compute_streak(
    priority_id: UUID,
    week_start: date,
    actual_hours: float,
    session: AsyncSession,
) -> int:
    """
    Compute streak value for this week's snapshot.

    Rules:
    - hours > 0 and previous snapshot exists: previous streak + 1
    - hours > 0 and no previous snapshot: 1
    - hours == 0: 0 (streak broken)
    """
    if actual_hours <= 0:
        return 0

    # Look for previous week's snapshot
    previous_week = week_start - timedelta(weeks=1)
    result = await session.execute(
        select(PgWeeklySnapshot.streak_at_snapshot).where(
            PgWeeklySnapshot.priority_id == priority_id,
            PgWeeklySnapshot.week_start == previous_week,
        )
    )
    row = result.fetchone()

    if row and row[0] is not None:
        return row[0] + 1
    else:
        # No previous snapshot (gap or first ever) - streak starts at 1
        return 1


async def _update_aggregates(
    priority_id: UUID,
    streak: int,
    actual_hours: float,
    session: AsyncSession,
) -> None:
    """
    Update running aggregates on pg_priorities.

    - streak_count = streak_at_snapshot just computed
    - total_hours_invested = SUM of all snapshots for this priority
    - avg_target_achievement = AVG of (actual_hours / target_hours * 100) for all snapshots
      with valid target_hours, NULL if < 2 data points
    """
    # Compute total_hours_invested from all valid snapshots (exclude phantom snapshots)
    # A snapshot is valid if week_end >= priority.created_at (week includes/follows creation)
    total_result = await session.execute(
        text("""
            SELECT COALESCE(SUM(s.actual_hours), 0)
            FROM pg_weekly_snapshots s
            JOIN pg_priorities p ON s.priority_id = p.id
            WHERE s.priority_id = :priority_id
              AND s.week_end >= p.created_at::date
        """),
        {"priority_id": priority_id}
    )
    total_hours = total_result.scalar()

    # Compute avg_target_achievement: AVG(actual_hours * 100.0 / target_hours)
    # Only for valid snapshots with target_hours > 0, requires >= 2 data points
    # Excludes phantom snapshots (week_end < created_at)
    achievement_result = await session.execute(
        text("""
            SELECT AVG(s.actual_hours * 100.0 / NULLIF(s.target_hours, 0)), COUNT(*)
            FROM pg_weekly_snapshots s
            JOIN pg_priorities p ON s.priority_id = p.id
            WHERE s.priority_id = :priority_id
              AND s.target_hours IS NOT NULL
              AND s.target_hours > 0
              AND s.week_end >= p.created_at::date
        """),
        {"priority_id": priority_id}
    )
    row = achievement_result.fetchone()
    avg_achievement_raw, snapshot_count = row if row else (None, 0)

    # Only set avg_target_achievement if we have >= 1 data point
    avg_target_achievement = None
    if snapshot_count is not None and snapshot_count >= 1 and avg_achievement_raw is not None:
        avg_target_achievement = Decimal(str(avg_achievement_raw))

    # Update priority aggregates (only if still active - defense in depth)
    await session.execute(
        text("""
            UPDATE pg_priorities
            SET
                streak_count = :streak,
                total_hours_invested = :total_hours,
                avg_target_achievement = :avg_target_achievement,
                updated_at = NOW()
            WHERE id = :priority_id AND status = 'active'
        """),
        {
            "streak": streak,
            "total_hours": Decimal(str(total_hours)) if total_hours is not None else Decimal("0"),
            "avg_target_achievement": avg_target_achievement,
            "priority_id": priority_id,
        }
    )
