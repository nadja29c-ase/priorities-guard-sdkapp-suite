"""
Weekly report service for Priority Guardian.

Generates weekly reports with per-priority hours, status indicators, and time allocation.

For past weeks with complete snapshot data, reports are built from pg_weekly_snapshots
via _build_report_from_snapshots(). This ensures accurate historical reports even after
keyword reassignments. Falls through to live calendar computation if snapshots are
missing or incomplete.

Current week reports always use live Google Calendar data.
"""

import structlog
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.models import CoreConnection
from backend.core.google_calendar import list_events, get_user_timezone
from backend.core.google_token_management import ensure_valid_access_token
from backend.apps.priority_guardian.db_models import PgPriority, PgWeeklySnapshot
from backend.apps.priority_guardian.services.utils import priority_eligible_for_week
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
# Snapshot-Based Report (for past weeks)
# ============================================================================


async def _build_report_from_snapshots(
    user_id: UUID,
    week_start: date,
    week_end: date,
    session: AsyncSession,
    correlation_id: str | None = None,
) -> dict[str, Any] | None:
    """
    Build a weekly report from snapshot data for a completed week.

    Returns None if no snapshots exist for this week, signaling the caller
    to fall through to live calendar computation.

    Args:
        user_id: User ID
        week_start: Monday of the week
        week_end: Sunday of the week
        session: Database session
        correlation_id: Request correlation ID

    Returns:
        Report dict if snapshots exist and have full coverage, None otherwise
    """
    log = {"user_id": str(user_id), "correlation_id": correlation_id}

    # -------------------------------------------------------------------------
    # Step 1: Query snapshots joined with priorities
    # -------------------------------------------------------------------------
    result = await session.execute(
        select(PgWeeklySnapshot, PgPriority)
        .join(PgPriority, PgWeeklySnapshot.priority_id == PgPriority.id)
        .options(selectinload(PgPriority.deliverables))
        .where(
            PgWeeklySnapshot.user_id == user_id,
            PgWeeklySnapshot.week_start == week_start,
        )
        .order_by(PgPriority.created_at)
    )
    snapshot_rows = list(result.all())

    # -------------------------------------------------------------------------
    # Step 2: If no snapshots, fall through to live computation
    # -------------------------------------------------------------------------
    if not snapshot_rows:
        logger.debug(
            "snapshot_report.no_snapshots",
            week_start=str(week_start),
            **log
        )
        return None

    # -------------------------------------------------------------------------
    # Step 3: Partial snapshot guard
    # Count how many active priorities should have snapshots for this week.
    # A priority should have a snapshot if:
    # - It was active during that week (created <= week_end, not yet retired or retired after week_end)
    # - It existed for the full week (priority_eligible_for_week)
    # -------------------------------------------------------------------------
    # Query all priorities that were active during the target week
    # Note: We need the next Monday (week_end + 1 day) as the exclusive end boundary
    week_end_exclusive = week_end + timedelta(days=1)

    priorities_result = await session.execute(
        select(PgPriority).where(
            PgPriority.user_id == user_id,
            PgPriority.created_at <= datetime.combine(week_end_exclusive, datetime.min.time()),
            # Not retired, or retired after the week ended
            (PgPriority.retired_at.is_(None)) | (PgPriority.retired_at > datetime.combine(week_end_exclusive, datetime.min.time())),
        )
    )
    all_priorities_in_week = list(priorities_result.scalars().all())

    # Filter to those eligible for this week (full weeks only)
    expected_count = sum(
        1 for p in all_priorities_in_week
        if priority_eligible_for_week(p.created_at.date(), week_start)
    )

    actual_count = len(snapshot_rows)

    if actual_count < expected_count:
        logger.warning(
            "snapshot_report.partial_coverage",
            week_start=str(week_start),
            expected=expected_count,
            actual=actual_count,
            **log
        )
        return None

    # -------------------------------------------------------------------------
    # Step 4: Build per-priority data from snapshots
    # -------------------------------------------------------------------------
    priority_data = []
    total_hours = Decimal("0")
    keyword_hours: dict[str, Decimal] = {"P1": Decimal("0"), "P2": Decimal("0"), "P3": Decimal("0")}

    for snapshot, priority in snapshot_rows:
        # Use snapshot keyword, fallback to current if null (pre-migration snapshots)
        kw = snapshot.calendar_keyword_at_snapshot or priority.calendar_keyword

        actual_hours = snapshot.actual_hours  # Keep as Decimal
        total_hours += actual_hours

        # Accumulate hours by keyword for time_allocation
        if kw in keyword_hours:
            keyword_hours[kw] += actual_hours

        pdata: dict[str, Any] = {
            "id": str(priority.id),
            "name": priority.name,
            "type": priority.type,
            "calendar_keyword": kw,
            "actual_hours": float(actual_hours),
            "event_count": 0,  # Not available from snapshots
        }

        if priority.type == "deadline":
            pdata["deadline_date"] = str(priority.deadline) if priority.deadline else None
            pdata["days_remaining"] = (priority.deadline - week_end).days if priority.deadline else None

            # Note: Using current deliverable state - known limitation documented in spec.
            # Deliverables completed after this week will be counted.
            done_count = sum(1 for d in priority.deliverables if d.done)
            total_count = len(priority.deliverables)
            pdata["deliverables_completed"] = done_count
            pdata["deliverables_total"] = total_count

            if priority.deadline:
                pdata["pacing_status"] = compute_pacing_status(
                    done_count, total_count, priority.created_at, priority.deadline, week_end
                )
            else:
                pdata["pacing_status"] = "on_track"

        elif priority.type == "flexible":
            target_hours = snapshot.target_hours or Decimal("0")
            pdata["target_hours"] = float(target_hours)
            pdata["flex_status"] = compute_flex_status(float(actual_hours), float(target_hours))
            pdata["streak_count"] = snapshot.streak_at_snapshot or 0
            # Use current aggregate as approximation (acceptable per spec)
            pdata["total_hours_invested"] = float(priority.total_hours_invested or Decimal("0"))

        # No previous week comparison from snapshots
        pdata["previous_week"] = None

        priority_data.append(pdata)

    # -------------------------------------------------------------------------
    # Step 5: Build time_allocation using stored week-level values
    # -------------------------------------------------------------------------
    # Read denormalized values from first snapshot (all rows have same value)
    first_snapshot = snapshot_rows[0][0]  # (snapshot, priority) tuple

    # Consistency guard: verify all rows have matching other_hours and total_tracked_hours
    # This catches corruption from partial snapshot creation bugs
    inconsistent = False
    ref_other = first_snapshot.other_hours
    ref_total = first_snapshot.total_tracked_hours

    for snapshot, _ in snapshot_rows[1:]:
        # Check for inconsistency: different non-null values, or mixed null/non-null
        if snapshot.other_hours != ref_other or snapshot.total_tracked_hours != ref_total:
            # Allow both being None (pre-migration), but not mixed states
            if not (snapshot.other_hours is None and ref_other is None):
                if snapshot.other_hours is not None or ref_other is not None:
                    inconsistent = True
                    break
            if not (snapshot.total_tracked_hours is None and ref_total is None):
                if snapshot.total_tracked_hours is not None or ref_total is not None:
                    inconsistent = True
                    break

    if inconsistent:
        logger.warning(
            "snapshot_report.inconsistent_week_totals",
            week_start=str(week_start),
            **log
        )
        return None

    # Use stored values, defaulting to 0 for pre-migration snapshots
    snapshot_other_hours = float(first_snapshot.other_hours or Decimal("0"))
    snapshot_total_tracked = float(first_snapshot.total_tracked_hours or Decimal("0"))

    # If stored total is 0 but we have priority hours, use computed sum
    # (handles pre-migration snapshots where total wasn't stored)
    if snapshot_total_tracked == 0 and float(total_hours) > 0:
        snapshot_total_tracked = float(total_hours) + snapshot_other_hours

    time_allocation = {
        "total_tracked_hours": snapshot_total_tracked,
        "keywords": {
            kw: {"hours": float(keyword_hours[kw]), "event_count": 0}
            for kw in ["P1", "P2", "P3"]
        },
        "other_hours": snapshot_other_hours,
    }

    logger.info(
        "snapshot_report.success",
        week_start=str(week_start),
        priority_count=len(priority_data),
        total_hours=float(total_hours),
        **log
    )

    return {
        "success": True,
        "data": {
            "week_start": str(week_start),
            "week_end": str(week_end),
            "is_current_week": False,
            "snapshot_saved": True,  # Indicates data came from snapshots
            "weeks_backfilled": 0,
            "backfill_truncated": False,
            "priorities": priority_data,
            "time_allocation": time_allocation,
            "all_events": [],  # No event data from snapshots
        },
    }


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

    Computes live data from Google Calendar. No persistence in this version.

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
    # Step 3b: For past weeks, try to build report from snapshots
    # -------------------------------------------------------------------------
    if not is_current:
        snapshot_report = await _build_report_from_snapshots(
            user_id=user_id,
            week_start=actual_week_start,
            week_end=actual_week_end,
            session=session,
            correlation_id=correlation_id,
        )
        if snapshot_report is not None:
            return snapshot_report
        # Fall through to live computation if no snapshots exist

    # -------------------------------------------------------------------------
    # Step 4: Load active priorities with deliverables
    # -------------------------------------------------------------------------
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
    keyword_hours = {
        kw: allocation["keywords"][kw]["hours"]
        for kw in ["P1", "P2", "P3"]
    }
    keyword_event_counts = {
        kw: allocation["keywords"][kw]["event_count"]
        for kw in ["P1", "P2", "P3"]
    }

    # -------------------------------------------------------------------------
    # Step 7: Build response (no persistence, no previous week comparison)
    # -------------------------------------------------------------------------
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
            # Aggregate fields stay at defaults (no snapshots to compute from)
            pdata["streak_count"] = 0
            pdata["total_hours_invested"] = 0.0

        # No previous week comparison (no snapshots)
        pdata["previous_week"] = None

        priority_data.append(pdata)

    logger.info(
        "weekly_report.success",
        priority_count=len(priorities),
        total_hours=allocation["total_tracked_hours"],
        **log
    )

    return {
        "success": True,
        "data": {
            "week_start": str(actual_week_start),
            "week_end": str(actual_week_end),
            "is_current_week": is_current,
            "snapshot_saved": False,  # Always false - no persistence
            "weeks_backfilled": 0,  # Always 0 - no backfill
            "backfill_truncated": False,  # Always false - no backfill
            "priorities": priority_data,
            "time_allocation": {
                "total_tracked_hours": allocation["total_tracked_hours"],
                "keywords": allocation["keywords"],
                "other_hours": allocation["other_hours"],
            },
            "all_events": all_events,
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
