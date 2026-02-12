"""
Weekly report service for Priority Guardian.

Computes weekly report data, persists snapshots for completed weeks,
updates running aggregates on priorities, and handles backfill for
missed weeks.
"""

import structlog
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select, func, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.models import CoreConnection
from backend.core.google_calendar import list_events, get_user_timezone
from backend.core.google_token_management import ensure_valid_access_token
from backend.apps.priority_guardian.db_models import (
    PgPriority,
    PgDeliverable,
    PgWeeklySnapshot,
    PgWeeklyOverview,
)
from backend.apps.priority_guardian.services.calendar_service import (
    compute_week_boundaries,
    compute_allocation_from_events,
    to_rfc3339,
    match_keywords,
    is_all_day_event,
    is_declined_event,
    is_cancelled_event,
    compute_event_duration_hours,
)

logger = structlog.get_logger(__name__)

# Maximum weeks to backfill in one request (one checkpoint cycle)
MAX_BACKFILL_WEEKS = 12


# ============================================================================
# Week Completion Check
# ============================================================================


def is_week_complete(week_start: date, timezone_str: str) -> bool:
    """
    Check if a week is complete (past).

    A week is complete when now() >= next Monday 00:00 in user's timezone.

    Args:
        week_start: Monday of the week to check
        timezone_str: User's IANA timezone

    Returns:
        True if the week is complete, False if current/future
    """
    try:
        tz = ZoneInfo(timezone_str)
    except Exception:
        tz = ZoneInfo("UTC")

    # Next Monday 00:00 marks the end of this week
    next_monday = datetime(
        week_start.year,
        week_start.month,
        week_start.day,
        hour=0, minute=0, second=0, microsecond=0,
        tzinfo=tz,
    ) + timedelta(days=7)

    now = datetime.now(tz)
    return now >= next_monday


# ============================================================================
# Status Computation
# ============================================================================


def compute_flex_status(actual_hours: float, target_hours: float) -> str:
    """
    Compute flex status based on 80%/110% thresholds.

    Args:
        actual_hours: Hours worked this week
        target_hours: Weekly hour target

    Returns:
        'ahead', 'on_track', or 'behind'
    """
    if target_hours <= 0:
        return "on_track"

    ratio = actual_hours / target_hours

    if ratio >= 1.1:
        return "ahead"
    elif ratio >= 0.8:
        return "on_track"
    else:
        return "behind"


def compute_pacing_status(
    deliverables_completed: int,
    deliverables_total: int,
    created_at: datetime,
    deadline: date,
    week_end: date,
) -> str:
    """
    Compute pacing status for deadline priorities.

    Args:
        deliverables_completed: Count of done deliverables
        deliverables_total: Total deliverable count
        created_at: When priority was created
        deadline: Priority's deadline date
        week_end: Sunday of the reporting week

    Returns:
        'completed', 'ahead', 'on_track', or 'behind'
    """
    # No deliverables → always on_track
    if deliverables_total == 0:
        return "on_track"

    completion_ratio = deliverables_completed / deliverables_total

    # All done → completed
    if completion_ratio >= 1.0:
        return "completed"

    # Compute time ratio
    created_date = created_at.date() if isinstance(created_at, datetime) else created_at
    total_days = (deadline - created_date).days
    elapsed_days = (week_end - created_date).days

    # Guard against division by zero (same-day deadline)
    if total_days <= 0:
        # Same-day deadline with unfinished work is behind
        return "completed" if completion_ratio >= 1.0 else "behind"

    time_ratio = elapsed_days / total_days

    if completion_ratio >= time_ratio:
        return "ahead"
    elif completion_ratio >= time_ratio * 0.8:
        return "on_track"
    else:
        return "behind"


# ============================================================================
# Snapshot and Aggregate Persistence
# ============================================================================


async def save_snapshot_and_update_aggregates(
    session: AsyncSession,
    priority: PgPriority,
    week_start: date,
    week_end: date,
    actual_hours: Decimal,
    event_count: int,
) -> PgWeeklySnapshot:
    """
    Save a weekly snapshot for a priority and update running aggregates.

    Creates the snapshot row and updates streak_count, avg_hours_week,
    and total_hours_invested on the priority.

    Args:
        session: Database session (must be in a transaction)
        priority: The priority to snapshot
        week_start: Monday of the week
        week_end: Sunday of the week
        actual_hours: Hours worked this week
        event_count: Number of keyword-matched events

    Returns:
        The created PgWeeklySnapshot
    """
    # Build snapshot data based on priority type
    snapshot_data = {
        "priority_id": priority.id,
        "user_id": priority.user_id,
        "week_start": week_start,
        "week_end": week_end,
        "actual_hours": actual_hours,
        "event_count": event_count,
    }

    if priority.type == "deadline":
        # Deadline-specific fields
        snapshot_data["deadline_date"] = priority.deadline
        if priority.deadline:
            snapshot_data["days_remaining"] = (priority.deadline - week_end).days

        # Count deliverables
        done_count = sum(1 for d in priority.deliverables if d.done)
        total_count = len(priority.deliverables)
        snapshot_data["deliverables_completed"] = done_count
        snapshot_data["deliverables_total"] = total_count

        # Compute pacing status
        if priority.deadline:
            snapshot_data["pacing_status"] = compute_pacing_status(
                done_count, total_count, priority.created_at, priority.deadline, week_end
            )
        else:
            snapshot_data["pacing_status"] = "on_track"

    elif priority.type == "flexible":
        # Flexible-specific fields
        snapshot_data["target_hours"] = priority.weekly_hour_target

        # Compute flex status
        target = float(priority.weekly_hour_target or 0)
        snapshot_data["flex_status"] = compute_flex_status(float(actual_hours), target)

        # Compute new streak count
        if actual_hours > 0:
            new_streak = priority.streak_count + 1
        else:
            new_streak = 0

        snapshot_data["streak_at_snapshot"] = new_streak

    # Create snapshot
    snapshot = PgWeeklySnapshot(**snapshot_data)
    session.add(snapshot)

    # Flush to ensure snapshot is visible for avg computation
    await session.flush()

    # Update aggregates on priority using SQL UPDATE with status guard
    # Defense-in-depth: both Python check AND SQL WHERE clause
    if priority.status == "active":
        # Compute avg_hours_week from all snapshots (including new one)
        avg_result = await session.execute(
            select(func.avg(PgWeeklySnapshot.actual_hours))
            .where(PgWeeklySnapshot.priority_id == priority.id)
        )
        avg_hours = avg_result.scalar()
        avg_hours_decimal = Decimal(str(round(float(avg_hours), 2))) if avg_hours else None

        # Build update values
        update_values = {
            "total_hours_invested": PgPriority.total_hours_invested + actual_hours,
        }
        if avg_hours_decimal is not None:
            update_values["avg_hours_week"] = avg_hours_decimal

        # Add streak_count for flexible priorities
        if priority.type == "flexible":
            if actual_hours > 0:
                update_values["streak_count"] = PgPriority.streak_count + 1
            else:
                update_values["streak_count"] = 0

        # Execute SQL UPDATE with status = 'active' guard
        # This provides defense-in-depth: even if a race condition changes
        # status to retired between the Python check and this UPDATE,
        # the WHERE clause ensures we don't modify retired priorities
        await session.execute(
            update(PgPriority)
            .where(
                PgPriority.id == priority.id,
                PgPriority.status == "active",
            )
            .values(**update_values)
        )

        # Refresh the ORM object to reflect the updated values
        await session.refresh(priority)

    return snapshot


async def get_most_recent_snapshot_week(
    session: AsyncSession,
    user_id: UUID,
) -> date | None:
    """
    Get the most recent snapshot week_start for a user.

    Returns:
        The most recent week_start date, or None if no snapshots exist
    """
    result = await session.execute(
        select(func.max(PgWeeklySnapshot.week_start))
        .where(PgWeeklySnapshot.user_id == user_id)
    )
    return result.scalar()


async def snapshot_exists(
    session: AsyncSession,
    priority_id: UUID,
    week_start: date,
) -> bool:
    """Check if a snapshot already exists for this priority+week."""
    result = await session.execute(
        select(PgWeeklySnapshot.id)
        .where(
            PgWeeklySnapshot.priority_id == priority_id,
            PgWeeklySnapshot.week_start == week_start,
        )
        .limit(1)
    )
    return result.scalar() is not None


async def get_previous_week_snapshot(
    session: AsyncSession,
    priority_id: UUID,
    current_week_start: date,
) -> PgWeeklySnapshot | None:
    """Get the snapshot for the week before the given week."""
    previous_week_start = current_week_start - timedelta(days=7)
    result = await session.execute(
        select(PgWeeklySnapshot)
        .where(
            PgWeeklySnapshot.priority_id == priority_id,
            PgWeeklySnapshot.week_start == previous_week_start,
        )
    )
    return result.scalar_one_or_none()


# ============================================================================
# Event Processing for Weekly Report
# ============================================================================


def process_events_for_report(events: list[dict]) -> tuple[dict[str, Any], list[dict]]:
    """
    Process events for the weekly report.

    Returns both the time allocation and the list of filtered events
    with matched keywords for LLM semantic grouping.

    Args:
        events: Raw events from Google Calendar API

    Returns:
        Tuple of (time_allocation, filtered_events_for_llm)
    """
    allocation = compute_allocation_from_events(events)

    # Build filtered event list for LLM (includes title + description)
    filtered_events = []
    for event in events:
        # Apply same filters as compute_allocation_from_events
        if is_all_day_event(event):
            continue
        if is_declined_event(event):
            continue
        if is_cancelled_event(event):
            continue

        duration = compute_event_duration_hours(event)
        if duration <= 0:
            continue

        title = event.get("summary", "")
        matched = match_keywords(title)

        filtered_events.append({
            "title": title,
            "description": event.get("description", ""),
            "start": event.get("start", {}).get("dateTime"),
            "end": event.get("end", {}).get("dateTime"),
            "matched_keywords": matched,
        })

    return allocation, filtered_events


# ============================================================================
# Main Entry Point
# ============================================================================


async def generate_weekly_report(
    user_id: UUID,
    session: AsyncSession,
    http_client: httpx.AsyncClient,
    week_start: date | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """
    Generate a weekly report for a user.

    For current (incomplete) week: returns live data, no persistence.
    For completed past week: persists snapshot + updates aggregates (with backfill).

    Args:
        user_id: User ID
        session: Database session
        http_client: HTTP client for Google API
        week_start: Optional Monday date for specific week. None = current week.
        correlation_id: Request correlation ID

    Returns:
        Weekly report data dict

    Raises:
        ValueError: If week_start is not a Monday, or token/API errors
    """
    log = {"user_id": str(user_id), "correlation_id": correlation_id}

    # -------------------------------------------------------------------------
    # Step 1: Validate week_start if provided
    # -------------------------------------------------------------------------
    if week_start is not None and week_start.weekday() != 0:
        raise ValueError(f"week_start must be a Monday, got {week_start}")

    # -------------------------------------------------------------------------
    # Step 2: Get Google connection and timezone
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
        raise ValueError("Google Calendar not connected")

    # Ensure valid access token
    token_result = await ensure_valid_access_token(connection, session, http_client)
    if "error" in token_result:
        raise ValueError(f"Token error: {token_result['error']}")

    access_token = token_result["access_token"]

    # Get user's timezone
    timezone_str = await get_user_timezone(http_client, access_token, correlation_id)

    # -------------------------------------------------------------------------
    # Step 3: Compute week boundaries
    # -------------------------------------------------------------------------
    week_start_dt, week_end_dt = compute_week_boundaries(timezone_str, week_start)

    # Extract date components
    actual_week_start = week_start_dt.date()
    actual_week_end = (week_end_dt - timedelta(days=1)).date()  # Sunday

    is_current = not is_week_complete(actual_week_start, timezone_str)

    logger.info(
        "weekly_report.generating",
        week_start=str(actual_week_start),
        week_end=str(actual_week_end),
        is_current_week=is_current,
        **log
    )

    # -------------------------------------------------------------------------
    # Step 4: Check for existing snapshots (idempotency for past weeks)
    # -------------------------------------------------------------------------
    # Load active priorities with deliverables
    priorities_result = await session.execute(
        select(PgPriority)
        .options(selectinload(PgPriority.deliverables))
        .where(
            PgPriority.user_id == user_id,
            PgPriority.status == "active",
        )
        .order_by(PgPriority.created_at)
    )
    priorities = list(priorities_result.scalars().all())

    if not priorities:
        return _empty_report(actual_week_start, actual_week_end, is_current)

    # Check if snapshots already exist for this week
    existing_snapshots: dict[UUID, PgWeeklySnapshot] = {}
    if not is_current:
        for p in priorities:
            snap_result = await session.execute(
                select(PgWeeklySnapshot)
                .where(
                    PgWeeklySnapshot.priority_id == p.id,
                    PgWeeklySnapshot.week_start == actual_week_start,
                )
            )
            snap = snap_result.scalar_one_or_none()
            if snap:
                existing_snapshots[p.id] = snap

        # If ALL priorities have snapshots, return existing data (idempotent)
        if len(existing_snapshots) == len(priorities):
            logger.info("weekly_report.returning_existing", **log)
            return await _build_report_from_snapshots(
                session, priorities, existing_snapshots,
                actual_week_start, actual_week_end, timezone_str
            )

    # -------------------------------------------------------------------------
    # Step 5: Fetch calendar events
    # -------------------------------------------------------------------------
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
        logger.warning("weekly_report.pages_failed", pages_failed=pages_failed, **log)

    # Process events
    allocation, all_events = process_events_for_report(events)

    # -------------------------------------------------------------------------
    # Step 6: Build per-priority hours from allocation
    # -------------------------------------------------------------------------
    # Map keyword to hours
    keyword_hours = {
        kw: allocation["keywords"][kw]["hours"]
        for kw in ["P1", "P2", "P3"]
    }
    keyword_event_counts = {
        kw: allocation["keywords"][kw]["event_count"]
        for kw in ["P1", "P2", "P3"]
    }

    # -------------------------------------------------------------------------
    # Step 7: Persist snapshots for completed weeks (with backfill)
    # -------------------------------------------------------------------------
    snapshot_saved = False
    weeks_backfilled = 0
    backfill_truncated = False

    if not is_current:
        # Check for backfill need
        most_recent = await get_most_recent_snapshot_week(session, user_id)

        if most_recent is not None:
            # Calculate gap
            gap_weeks = (actual_week_start - most_recent).days // 7 - 1

            if gap_weeks > 0:
                # Need to backfill
                if gap_weeks > MAX_BACKFILL_WEEKS:
                    backfill_truncated = True
                    # Reset streak at start of backfill window
                    for p in priorities:
                        if p.type == "flexible":
                            p.streak_count = 0
                    gap_weeks = MAX_BACKFILL_WEEKS

                logger.info(
                    "weekly_report.backfilling",
                    gap_weeks=gap_weeks,
                    truncated=backfill_truncated,
                    **log
                )

                # Backfill each missing week
                for i in range(gap_weeks, 0, -1):
                    backfill_week_start = actual_week_start - timedelta(days=7 * i)
                    backfill_week_end = backfill_week_start + timedelta(days=6)

                    # Fetch events for this week
                    bf_start_dt, bf_end_dt = compute_week_boundaries(timezone_str, backfill_week_start)
                    bf_time_min = to_rfc3339(bf_start_dt)
                    bf_time_max = to_rfc3339(bf_end_dt)

                    bf_events, _ = await list_events(
                        http_client, access_token, bf_time_min, bf_time_max
                    )
                    bf_allocation, _ = process_events_for_report(bf_events)

                    # Save snapshots for each priority
                    for p in priorities:
                        if await snapshot_exists(session, p.id, backfill_week_start):
                            continue  # Already exists

                        kw = p.calendar_keyword
                        hours = Decimal(str(bf_allocation["keywords"].get(kw, {}).get("hours", 0)))
                        count = bf_allocation["keywords"].get(kw, {}).get("event_count", 0)

                        await save_snapshot_and_update_aggregates(
                            session, p, backfill_week_start, backfill_week_end, hours, count
                        )

                    weeks_backfilled += 1

        # Save current week's snapshots
        for p in priorities:
            if p.id in existing_snapshots:
                continue  # Already exists

            kw = p.calendar_keyword
            hours = Decimal(str(keyword_hours.get(kw, 0)))
            count = keyword_event_counts.get(kw, 0)

            await save_snapshot_and_update_aggregates(
                session, p, actual_week_start, actual_week_end, hours, count
            )

        await session.commit()
        snapshot_saved = True

        logger.info(
            "weekly_report.saved",
            priorities_count=len(priorities),
            weeks_backfilled=weeks_backfilled,
            **log
        )

    # -------------------------------------------------------------------------
    # Step 8: Build response
    # -------------------------------------------------------------------------
    # Get previous week snapshots for comparison
    previous_snapshots: dict[UUID, PgWeeklySnapshot] = {}
    for p in priorities:
        prev = await get_previous_week_snapshot(session, p.id, actual_week_start)
        if prev:
            previous_snapshots[p.id] = prev

    # Build priority data
    priority_data = []
    for p in priorities:
        kw = p.calendar_keyword
        actual = keyword_hours.get(kw, 0)
        count = keyword_event_counts.get(kw, 0)

        pdata = {
            "id": str(p.id),
            "name": p.name,
            "type": p.type,
            "calendar_keyword": kw,
            "actual_hours": actual,
            "event_count": count,
        }

        if p.type == "deadline":
            pdata["deadline_date"] = str(p.deadline) if p.deadline else None
            pdata["days_remaining"] = (p.deadline - actual_week_end).days if p.deadline else None
            done_count = sum(1 for d in p.deliverables if d.done)
            total_count = len(p.deliverables)
            pdata["deliverables_completed"] = done_count
            pdata["deliverables_total"] = total_count
            if p.deadline:
                pdata["pacing_status"] = compute_pacing_status(
                    done_count, total_count, p.created_at, p.deadline, actual_week_end
                )
            else:
                pdata["pacing_status"] = "on_track"

        elif p.type == "flexible":
            target = float(p.weekly_hour_target or 0)
            pdata["target_hours"] = target
            pdata["flex_status"] = compute_flex_status(actual, target)
            pdata["streak_count"] = p.streak_count
            pdata["avg_hours_week"] = float(p.avg_hours_week) if p.avg_hours_week else None
            pdata["total_hours_invested"] = float(p.total_hours_invested)

        # Previous week comparison
        if p.id in previous_snapshots:
            prev = previous_snapshots[p.id]
            pdata["previous_week"] = {
                "actual_hours": float(prev.actual_hours),
                "event_count": prev.event_count,
                "delta_hours": round(actual - float(prev.actual_hours), 2),
            }
        else:
            pdata["previous_week"] = None

        priority_data.append(pdata)

    return {
        "success": True,
        "data": {
            "week_start": str(actual_week_start),
            "week_end": str(actual_week_end),
            "is_current_week": is_current,
            "snapshot_saved": snapshot_saved,
            "weeks_backfilled": weeks_backfilled,
            "backfill_truncated": backfill_truncated,
            "priorities": priority_data,
            "time_allocation": {
                "total_tracked_hours": allocation["total_tracked_hours"],
                "keywords": allocation["keywords"],
                "other_hours": allocation["other_hours"],
            },
            "all_events": all_events,
        },
    }


async def _build_report_from_snapshots(
    session: AsyncSession,
    priorities: list[PgPriority],
    snapshots: dict[UUID, PgWeeklySnapshot],
    week_start: date,
    week_end: date,
    timezone_str: str,
) -> dict[str, Any]:
    """Build report response from existing snapshots (idempotent return)."""
    # Get previous week snapshots for comparison
    previous_snapshots: dict[UUID, PgWeeklySnapshot] = {}
    for p in priorities:
        prev = await get_previous_week_snapshot(session, p.id, week_start)
        if prev:
            previous_snapshots[p.id] = prev

    priority_data = []
    total_hours = 0.0
    keyword_hours = {"P1": 0.0, "P2": 0.0, "P3": 0.0}
    keyword_counts = {"P1": 0, "P2": 0, "P3": 0}

    for p in priorities:
        snap = snapshots[p.id]
        kw = p.calendar_keyword
        actual = float(snap.actual_hours)

        keyword_hours[kw] = actual
        keyword_counts[kw] = snap.event_count
        total_hours += actual

        pdata = {
            "id": str(p.id),
            "name": p.name,
            "type": p.type,
            "calendar_keyword": kw,
            "actual_hours": actual,
            "event_count": snap.event_count,
        }

        if p.type == "deadline":
            pdata["deadline_date"] = str(snap.deadline_date) if snap.deadline_date else None
            pdata["days_remaining"] = snap.days_remaining
            pdata["deliverables_completed"] = snap.deliverables_completed
            pdata["deliverables_total"] = snap.deliverables_total
            pdata["pacing_status"] = snap.pacing_status

        elif p.type == "flexible":
            pdata["target_hours"] = float(snap.target_hours) if snap.target_hours else None
            pdata["flex_status"] = snap.flex_status
            pdata["streak_count"] = snap.streak_at_snapshot
            pdata["avg_hours_week"] = float(p.avg_hours_week) if p.avg_hours_week else None
            pdata["total_hours_invested"] = float(p.total_hours_invested)

        # Previous week comparison
        if p.id in previous_snapshots:
            prev = previous_snapshots[p.id]
            pdata["previous_week"] = {
                "actual_hours": float(prev.actual_hours),
                "event_count": prev.event_count,
                "delta_hours": round(actual - float(prev.actual_hours), 2),
            }
        else:
            pdata["previous_week"] = None

        priority_data.append(pdata)

    return {
        "success": True,
        "data": {
            "week_start": str(week_start),
            "week_end": str(week_end),
            "is_current_week": False,
            "snapshot_saved": True,  # Already saved
            "weeks_backfilled": 0,
            "backfill_truncated": False,
            "priorities": priority_data,
            "time_allocation": {
                "total_tracked_hours": total_hours,
                "keywords": {
                    kw: {"hours": keyword_hours[kw], "event_count": keyword_counts[kw]}
                    for kw in ["P1", "P2", "P3"]
                },
                "other_hours": 0.0,  # Can't compute without events
            },
            "all_events": [],  # Not stored, can't retrieve
        },
    }


def _empty_report(week_start: date, week_end: date, is_current: bool) -> dict[str, Any]:
    """Return an empty report when user has no active priorities."""
    return {
        "success": True,
        "data": {
            "week_start": str(week_start),
            "week_end": str(week_end),
            "is_current_week": is_current,
            "snapshot_saved": False,
            "weeks_backfilled": 0,
            "backfill_truncated": False,
            "priorities": [],
            "time_allocation": {
                "total_tracked_hours": 0.0,
                "keywords": {
                    "P1": {"hours": 0.0, "event_count": 0},
                    "P2": {"hours": 0.0, "event_count": 0},
                    "P3": {"hours": 0.0, "event_count": 0},
                },
                "other_hours": 0.0,
            },
            "all_events": [],
        },
    }


# ============================================================================
# Semantic Grouping (Increment 07)
# ============================================================================


class SemanticGroupingError(Exception):
    """Error during semantic grouping save."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


async def save_semantic_grouping(
    user_id: UUID,
    session: AsyncSession,
    http_client: httpx.AsyncClient,
    week_start: date,
    groupings: list[dict],
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """
    Save user-confirmed semantic groupings for a weekly snapshot.

    Validates the groupings, computes other_hours from calendar data,
    UPSERTs into pg_weekly_overview, and returns pie chart slices.

    Args:
        user_id: User ID
        session: Database session
        http_client: HTTP client for Google API
        week_start: Monday of the week
        groupings: List of {category, hours, event_count}
        correlation_id: Request correlation ID

    Returns:
        Pie chart data with slices

    Raises:
        SemanticGroupingError: If validation fails
    """
    log = {"user_id": str(user_id), "correlation_id": correlation_id}

    # -------------------------------------------------------------------------
    # Step 1: Validate week_start is a Monday
    # -------------------------------------------------------------------------
    if week_start.weekday() != 0:
        raise SemanticGroupingError(
            "NOT_A_MONDAY",
            f"week_start must be a Monday, got {week_start}"
        )

    week_end = week_start + timedelta(days=6)  # Sunday

    # -------------------------------------------------------------------------
    # Step 2: Validate groupings array
    # -------------------------------------------------------------------------
    if not groupings:
        raise SemanticGroupingError(
            "EMPTY_GROUPINGS",
            "At least one category is required"
        )

    # Check for duplicates (case-insensitive)
    seen_categories = set()
    validated_groupings = []

    for g in groupings:
        category = (g.get("category") or "").strip()
        hours = g.get("hours", 0)
        event_count = g.get("event_count", 0)

        # Validate category
        if not category:
            raise SemanticGroupingError(
                "INVALID_CATEGORY",
                "Category name cannot be empty"
            )

        # Check duplicates
        category_lower = category.lower()
        if category_lower in seen_categories:
            raise SemanticGroupingError(
                "DUPLICATE_CATEGORY",
                f"Duplicate category name: {category}"
            )
        seen_categories.add(category_lower)

        # Validate hours
        if not isinstance(hours, (int, float)) or hours < 0:
            raise SemanticGroupingError(
                "INVALID_HOURS",
                f"Hours must be non-negative, got {hours} for {category}"
            )

        # Validate event_count
        if not isinstance(event_count, int) or event_count < 0:
            raise SemanticGroupingError(
                "INVALID_EVENT_COUNT",
                f"Event count must be non-negative integer, got {event_count} for {category}"
            )

        validated_groupings.append({
            "category": category,
            "hours": round(float(hours), 2),
            "event_count": int(event_count),
        })

    # -------------------------------------------------------------------------
    # Step 3: Check snapshots exist for this week
    # -------------------------------------------------------------------------
    result = await session.execute(
        select(PgWeeklySnapshot)
        .where(
            PgWeeklySnapshot.user_id == user_id,
            PgWeeklySnapshot.week_start == week_start,
        )
    )
    snapshots = list(result.scalars().all())

    if not snapshots:
        raise SemanticGroupingError(
            "NO_SNAPSHOT",
            "No weekly report found for this week. Generate your weekly report first."
        )

    logger.info(
        "semantic_grouping.snapshots_found",
        count=len(snapshots),
        **log
    )

    # -------------------------------------------------------------------------
    # Step 4: Fetch calendar data to compute other_hours for validation
    # -------------------------------------------------------------------------
    # Get Google connection
    conn_result = await session.execute(
        select(CoreConnection).where(
            CoreConnection.user_id == user_id,
            CoreConnection.provider == "google",
            CoreConnection.connection_type == "google",
            CoreConnection.revoked_at.is_(None),
        )
    )
    connection = conn_result.scalar_one_or_none()

    if not connection:
        raise SemanticGroupingError(
            "GOOGLE_NOT_CONNECTED",
            "Google Calendar is not connected"
        )

    # Get valid access token
    token_result = await ensure_valid_access_token(connection, session, http_client)
    if "error" in token_result:
        raise SemanticGroupingError(
            "TOKEN_ERROR",
            "Unable to access Google Calendar. Please reconnect."
        )

    access_token = token_result["access_token"]
    timezone_str = await get_user_timezone(http_client, access_token, correlation_id)

    # Compute week boundaries
    week_start_dt, week_end_dt = compute_week_boundaries(timezone_str, week_start)
    time_min = to_rfc3339(week_start_dt)
    time_max = to_rfc3339(week_end_dt)

    # Fetch events
    events, _ = await list_events(
        http_client,
        access_token,
        time_min,
        time_max,
        max_results_per_page=250,
        max_pages=10,
    )

    # Compute allocation
    allocation = compute_allocation_from_events(events)
    other_hours = allocation["other_hours"]

    # -------------------------------------------------------------------------
    # Step 5: Validate groupings don't exceed other_hours
    # -------------------------------------------------------------------------
    total_grouped_hours = sum(g["hours"] for g in validated_groupings)
    epsilon = 0.5  # Tolerance for rounding differences

    if other_hours <= 0.01 and len(validated_groupings) > 0:
        raise SemanticGroupingError(
            "NO_OTHER_HOURS",
            "No non-priority time to categorize for this week"
        )

    if total_grouped_hours > other_hours + epsilon:
        raise SemanticGroupingError(
            "EXCEEDS_OTHER_HOURS",
            f"Grouped hours ({total_grouped_hours:.2f}) exceed non-priority time ({other_hours:.2f})"
        )

    logger.info(
        "semantic_grouping.validated",
        total_grouped_hours=total_grouped_hours,
        other_hours=other_hours,
        **log
    )

    # -------------------------------------------------------------------------
    # Step 6: UPSERT into pg_weekly_overview
    # -------------------------------------------------------------------------
    # Check if overview row exists
    overview_result = await session.execute(
        select(PgWeeklyOverview).where(
            PgWeeklyOverview.user_id == user_id,
            PgWeeklyOverview.week_start == week_start,
        )
    )
    overview = overview_result.scalar_one_or_none()

    if overview:
        # Update existing row
        overview.semantic_grouping = validated_groupings
        # updated_at is handled by onupdate
    else:
        # Insert new row
        overview = PgWeeklyOverview(
            user_id=user_id,
            week_start=week_start,
            semantic_grouping=validated_groupings,
        )
        session.add(overview)

    await session.flush()

    logger.info(
        "semantic_grouping.saved",
        overview_id=str(overview.id),
        category_count=len(validated_groupings),
        **log
    )

    # -------------------------------------------------------------------------
    # Step 7: Build pie chart slices
    # -------------------------------------------------------------------------
    # Load priority names for labels (need to join with priorities)
    priority_ids = [s.priority_id for s in snapshots]
    priorities_result = await session.execute(
        select(PgPriority).where(PgPriority.id.in_(priority_ids))
    )
    priorities_map = {p.id: p for p in priorities_result.scalars().all()}

    slices = []
    total_hours = 0.0

    # Priority slices (from snapshots)
    for snap in snapshots:
        priority = priorities_map.get(snap.priority_id)
        if not priority:
            continue

        hours = float(snap.actual_hours)
        if hours <= 0:
            continue

        slices.append({
            "label": f"{priority.calendar_keyword} — {priority.name}",
            "hours": round(hours, 2),
            "type": "priority",
            "keyword": priority.calendar_keyword,
        })
        total_hours += hours

    # Semantic slices (from just-saved groupings)
    for g in validated_groupings:
        if g["hours"] <= 0:
            continue

        slices.append({
            "label": g["category"],
            "hours": g["hours"],
            "type": "semantic",
            "eventCount": g["event_count"],
        })
        total_hours += g["hours"]

    # Sort slices: priorities first (by keyword), then semantic (by hours descending)
    priority_slices = [s for s in slices if s["type"] == "priority"]
    semantic_slices = [s for s in slices if s["type"] == "semantic"]

    priority_slices.sort(key=lambda s: s.get("keyword", ""))
    semantic_slices.sort(key=lambda s: s["hours"], reverse=True)

    slices = priority_slices + semantic_slices

    return {
        "success": True,
        "data": {
            "week_start": str(week_start),
            "week_end": str(week_end),
            "slices": slices,
            "total_hours": round(total_hours, 2),
        },
    }
