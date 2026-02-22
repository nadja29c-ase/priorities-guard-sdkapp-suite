"""
Pattern Recognition Engine for Priority Guardian.

Computes behavioral patterns from user's existing snapshot history and priority metadata.
Read-only queries on pg_weekly_snapshots and pg_priorities tables.
No new database tables, no new migrations, no data stored.

Patterns computed:
- Pattern 1: Consistency Streak (flexible priorities only)
- Pattern 2: Abandoned Priority Signal (active priorities only)
- Pattern 3: Priority Switching Frequency (cross-priority)
- Pattern 4: Priority Protection (stable hours under calendar pressure)

Implements increment_21 specification.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog
from dateutil.relativedelta import relativedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.priority_guardian.db_models import PgPriority, PgWeeklySnapshot

logger = structlog.get_logger(__name__)

# ============================================================================
# Constants
# ============================================================================

PATTERN_ENGINE_VERSION = "1.0"
MINIMUM_WEEKS_FLOOR = 4
ROLLING_WINDOW_MONTHS = 6

# Pattern thresholds
STREAK_THRESHOLD = 4
ABANDONED_AVG_THRESHOLD = Decimal("1.0")
ABANDONED_WEEKS_NEEDED = 4
SWITCHING_RETIREMENT_THRESHOLD = 3
PROTECTION_WEEKS_NEEDED = 8
PROTECTION_TOTAL_CHANGE_PCT_THRESHOLD = Decimal("15.0")
PROTECTION_TOTAL_DELTA_THRESHOLD = Decimal("2.0")
PROTECTION_PRIORITY_CHANGE_FLOOR = Decimal("-10.0")
PROTECTION_PRIOR_TOTAL_FLOOR = Decimal("5.0")


# ============================================================================
# Pure Helpers (no I/O)
# ============================================================================

def get_current_week_start_utc() -> date:
    """
    Get the Monday of the current week in UTC.

    Pure function, no I/O, no external calls, no database queries.
    Returns a date object representing Monday of the current UTC week.

    Returns:
        date: Monday of the current week (UTC)
    """
    today = datetime.now(timezone.utc).date()
    # weekday() returns 0 for Monday, 6 for Sunday
    days_since_monday = today.weekday()
    return today - relativedelta(days=days_since_monday)


def resolve_keyword(
    priority: PgPriority,
    snapshots_for_priority: list[PgWeeklySnapshot],
) -> str | None:
    """
    Resolve calendar keyword for a priority.

    For active priorities: return priority.calendar_keyword
    For retired priorities: return most recent non-NULL calendar_keyword_at_snapshot

    Args:
        priority: The priority model instance
        snapshots_for_priority: Snapshots for this priority within rolling window,
                                ordered by week_start descending (most recent first)

    Returns:
        Resolved keyword (P1/P2/P3) or None if unavailable
    """
    if priority.status == "active":
        if priority.calendar_keyword is not None:
            return priority.calendar_keyword
        # Bug path: active priority with NULL keyword
        logger.warning(
            "patterns.keyword_missing_active_priority",
            priority_id=str(priority.id),
            priority_name=priority.name,
        )
        return None

    # Retired priority: find most recent snapshot with non-NULL keyword
    for snapshot in snapshots_for_priority:
        if snapshot.calendar_keyword_at_snapshot is not None:
            return snapshot.calendar_keyword_at_snapshot

    return None


def decimal_to_float_recursive(obj: Any) -> Any:
    """
    Recursively convert Decimal values to float for JSON serialization.

    Handles nested dicts and lists. Preserves None, strings, dates, and other types.

    Args:
        obj: Any object (dict, list, Decimal, or other)

    Returns:
        Object with all Decimal values converted to float
    """
    if isinstance(obj, dict):
        return {k: decimal_to_float_recursive(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decimal_to_float_recursive(item) for item in obj]
    elif isinstance(obj, Decimal):
        return float(obj)
    else:
        return obj


def _get_retirement_week_start(retired_at: datetime) -> date:
    """
    Get the Monday of the week when a priority was retired.

    Args:
        retired_at: datetime when priority was retired (with timezone)

    Returns:
        date: Monday of the retirement week
    """
    retired_date = retired_at.astimezone(timezone.utc).date()
    days_since_monday = retired_date.weekday()
    return retired_date - relativedelta(days=days_since_monday)


def _build_detail_string(
    template: str,
    priority_name: str,
    calendar_keyword: str | None,
    **kwargs: Any,
) -> str:
    """
    Build detail string using keyword or priority name.

    If calendar_keyword is None, uses priority_name instead.

    Args:
        template: String with {identifier} placeholder
        priority_name: Priority name for fallback
        calendar_keyword: Resolved keyword or None
        **kwargs: Additional format arguments

    Returns:
        Formatted detail string
    """
    identifier = calendar_keyword if calendar_keyword else priority_name
    return template.format(identifier=identifier, **kwargs)


# ============================================================================
# Pattern Computation Functions
# ============================================================================

def _compute_consistency_streaks(
    priorities: list[PgPriority],
    snapshots_by_priority: dict[UUID, list[PgWeeklySnapshot]],
    current_week_start: date,
) -> list[dict]:
    """
    Compute Pattern 1: Consistency Streak for flexible priorities.

    Detects consecutive weeks where a flexible priority had hours > 0.
    Uses streak_at_snapshot from most recent snapshot, falls back to
    computing from actual_hours if all streak_at_snapshot values are NULL.

    Args:
        priorities: All user priorities (active and retired)
        snapshots_by_priority: Snapshots grouped by priority_id, ordered by week_start desc
        current_week_start: Monday of current week (for retirement boundary)

    Returns:
        List of consistency_streak pattern dicts
    """
    patterns = []

    for priority in priorities:
        # Pattern 1 is for flexible priorities only
        if priority.type != "flexible":
            continue

        snapshots = snapshots_by_priority.get(priority.id, [])

        # Need at least 4 completed-week snapshots
        if len(snapshots) < MINIMUM_WEEKS_FLOOR:
            continue

        # For retired priorities, exclude post-retirement snapshots
        if priority.status == "retired" and priority.retired_at:
            retirement_week_start = _get_retirement_week_start(priority.retired_at)
            snapshots = [s for s in snapshots if s.week_start <= retirement_week_start]
            if len(snapshots) < MINIMUM_WEEKS_FLOOR:
                continue

        # Try to read streak_at_snapshot from most recent non-NULL snapshot
        streak_value = None
        streak_source = "snapshot"

        for snapshot in snapshots:
            if snapshot.streak_at_snapshot is not None:
                streak_value = snapshot.streak_at_snapshot
                break

        # Fallback: compute streak from consecutive actual_hours > 0
        if streak_value is None:
            streak_source = "computed"
            streak_value = 0
            for snapshot in snapshots:
                if snapshot.actual_hours is not None and snapshot.actual_hours > 0:
                    streak_value += 1
                else:
                    break

        # Only surface if streak >= 4
        if streak_value < STREAK_THRESHOLD:
            continue

        # Resolve keyword
        keyword = resolve_keyword(priority, snapshots)

        # Build detail string
        detail = _build_detail_string(
            "{streak_weeks} consecutive weeks with logged hours",
            priority.name,
            keyword,
            streak_weeks=streak_value,
        )

        patterns.append({
            "pattern_type": "consistency_streak",
            "narration_label": "Consistency streak",
            "priority_id": str(priority.id),
            "priority_name": priority.name,
            "priority_status": priority.status,
            "calendar_keyword": keyword,
            "streak_weeks": streak_value,
            "streak_source": streak_source,
            "detail": detail,
        })

    return patterns


def _compute_abandoned_priorities(
    priorities: list[PgPriority],
    snapshots_by_priority: dict[UUID, list[PgWeeklySnapshot]],
) -> list[dict]:
    """
    Compute Pattern 2: Abandoned Priority Signal for active priorities.

    Detects active priorities that consistently get < 1.0h/week average
    over the last 4 snapshots with non-NULL actual_hours.

    Args:
        priorities: All user priorities
        snapshots_by_priority: Snapshots grouped by priority_id, ordered by week_start desc

    Returns:
        List of abandoned_priority pattern dicts
    """
    patterns = []

    for priority in priorities:
        # Pattern 2 is for active priorities only
        if priority.status != "active":
            continue

        snapshots = snapshots_by_priority.get(priority.id, [])

        # Filter to snapshots with non-NULL actual_hours
        qualifying_snapshots = [s for s in snapshots if s.actual_hours is not None]

        # Need at least 4 qualifying snapshots
        if len(qualifying_snapshots) < ABANDONED_WEEKS_NEEDED:
            continue

        # Take the last 4 qualifying snapshots
        last_4 = qualifying_snapshots[:ABANDONED_WEEKS_NEEDED]

        # Compute average
        total_hours = sum(s.actual_hours for s in last_4)
        avg_hours = total_hours / ABANDONED_WEEKS_NEEDED

        # Only surface if average < 1.0h/week
        if avg_hours >= ABANDONED_AVG_THRESHOLD:
            continue

        # Resolve keyword
        keyword = resolve_keyword(priority, snapshots)

        # Build detail string
        avg_rounded = round(float(avg_hours), 1)
        detail = f"Averaging {avg_rounded}h/week over the last 4 weeks"

        patterns.append({
            "pattern_type": "abandoned_priority",
            "narration_label": "Low investment",
            "priority_id": str(priority.id),
            "priority_name": priority.name,
            "priority_status": priority.status,
            "calendar_keyword": keyword,
            "avg_hours_last_4_weeks": avg_hours,
            "detail": detail,
        })

    return patterns


def _compute_priority_switching(
    priorities: list[PgPriority],
    window_start_date: date,
    current_week_start: date,
) -> list[dict]:
    """
    Compute Pattern 3: Priority Switching Frequency.

    Detects frequent retire-and-replace cycles (3+ retirements in 6 months).
    This is a cross-priority pattern - one instance per user.

    Args:
        priorities: All user priorities
        window_start_date: Start of rolling window
        current_week_start: Monday of current week (end of window)

    Returns:
        List with zero or one priority_switching pattern dict
    """
    # Count retirements within window
    retirements_in_window = 0
    creations_in_window = 0

    for priority in priorities:
        # Check retired_at
        if priority.retired_at:
            retired_date = priority.retired_at.astimezone(timezone.utc).date()
            if window_start_date <= retired_date < current_week_start:
                retirements_in_window += 1

        # Check created_at
        if priority.created_at:
            created_date = priority.created_at.astimezone(timezone.utc).date()
            if window_start_date <= created_date < current_week_start:
                creations_in_window += 1

    # Threshold is on retirements only
    if retirements_in_window < SWITCHING_RETIREMENT_THRESHOLD:
        return []

    # Compute window weeks (approximately 26 weeks for 6 months)
    window_weeks = (current_week_start - window_start_date).days // 7

    detail = (
        f"{retirements_in_window} priorities retired and "
        f"{creations_in_window} created in the last 6 months"
    )

    return [{
        "pattern_type": "priority_switching",
        "narration_label": "Priority changes",
        "retirements_in_window": retirements_in_window,
        "creations_in_window": creations_in_window,
        "window_weeks": window_weeks,
        "detail": detail,
    }]


def _compute_priority_protection(
    priorities: list[PgPriority],
    snapshots_by_priority: dict[UUID, list[PgWeeklySnapshot]],
) -> list[dict]:
    """
    Compute Pattern 4: Priority Protection.

    Detects priorities whose hours remained stable or grew even as total
    calendar pressure changed (total hours increased by 15%+).

    Requires 8 qualifying snapshots (with non-NULL actual_hours AND total_tracked_hours).

    Args:
        priorities: All user priorities
        snapshots_by_priority: Snapshots grouped by priority_id, ordered by week_start desc

    Returns:
        List of priority_protection pattern dicts
    """
    patterns = []

    for priority in priorities:
        snapshots = snapshots_by_priority.get(priority.id, [])

        # Filter to snapshots with both fields non-NULL
        qualifying_snapshots = [
            s for s in snapshots
            if s.actual_hours is not None and s.total_tracked_hours is not None
        ]

        # Need at least 8 qualifying snapshots
        if len(qualifying_snapshots) < PROTECTION_WEEKS_NEEDED:
            continue

        # Recent period: last 4 qualifying snapshots
        # Prior period: 4 snapshots before that
        recent_snapshots = qualifying_snapshots[:4]
        prior_snapshots = qualifying_snapshots[4:8]

        # Period qualification guard
        if len(recent_snapshots) < 4 or len(prior_snapshots) < 4:
            continue

        # Compute averages
        recent_priority_avg = sum(s.actual_hours for s in recent_snapshots) / 4
        prior_priority_avg = sum(s.actual_hours for s in prior_snapshots) / 4
        recent_total_avg = sum(s.total_tracked_hours for s in recent_snapshots) / 4
        prior_total_avg = sum(s.total_tracked_hours for s in prior_snapshots) / 4

        # Guard: prior_total_avg must be >= 5.0
        if prior_total_avg < PROTECTION_PRIOR_TOTAL_FLOOR:
            continue

        # Guard: prior_priority_avg must be > 0
        if prior_priority_avg == 0:
            continue

        # Compute changes
        total_hours_change_pct = ((recent_total_avg - prior_total_avg) / prior_total_avg) * 100
        total_hours_delta = recent_total_avg - prior_total_avg
        priority_hours_change_pct = ((recent_priority_avg - prior_priority_avg) / prior_priority_avg) * 100

        # Surface pattern if ALL conditions met:
        # - total_hours_change_pct >= 15.0
        # - total_hours_delta >= 2.0
        # - priority_hours_change_pct >= -10.0 (dropped by no more than 10%)
        if total_hours_change_pct < PROTECTION_TOTAL_CHANGE_PCT_THRESHOLD:
            continue
        if total_hours_delta < PROTECTION_TOTAL_DELTA_THRESHOLD:
            continue
        if priority_hours_change_pct < PROTECTION_PRIORITY_CHANGE_FLOOR:
            continue

        # Determine trend
        if abs(priority_hours_change_pct) <= Decimal("10.0"):
            priority_hours_trend = "stable"
        else:
            priority_hours_trend = "growing"

        # Resolve keyword
        keyword = resolve_keyword(priority, snapshots)

        # Build detail string
        recent_priority_rounded = round(float(recent_priority_avg), 0)
        total_change_rounded = round(float(total_hours_change_pct), 0)

        detail = _build_detail_string(
            "{identifier} hours stayed {trend} at ~{hours}h/week despite total calendar growing {pct}%",
            priority.name,
            keyword,
            trend=priority_hours_trend,
            hours=int(recent_priority_rounded),
            pct=int(total_change_rounded),
        )

        patterns.append({
            "pattern_type": "priority_protection",
            "narration_label": "Priority protection",
            "priority_id": str(priority.id),
            "priority_name": priority.name,
            "priority_status": priority.status,
            "calendar_keyword": keyword,
            "priority_hours_trend": priority_hours_trend,
            "total_hours_change_pct": total_hours_change_pct,
            "detail": detail,
        })

    return patterns


def _sort_patterns(patterns: list[dict]) -> list[dict]:
    """
    Sort patterns in deterministic order.

    Per-priority patterns: sort by (pattern_type, priority_id, priority_name.casefold())
    Cross-priority patterns: sort by pattern_type only

    Args:
        patterns: List of pattern dicts

    Returns:
        Sorted list of patterns
    """
    def sort_key(p: dict) -> tuple:
        pattern_type = p.get("pattern_type", "")
        priority_id = p.get("priority_id", "")
        priority_name = (p.get("priority_name") or "").casefold()
        return (pattern_type, priority_id, priority_name)

    return sorted(patterns, key=sort_key)


# ============================================================================
# Public Interface
# ============================================================================

async def compute_patterns(
    user_id: UUID,
    session: AsyncSession,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """
    Compute behavioral patterns from user's snapshot history.

    Main entry point for pattern recognition engine.
    Returns patterns computed at read time from existing tables.
    Never raises - returns error info in response dict on failure.

    Args:
        user_id: User UUID
        session: SQLAlchemy async session
        correlation_id: Optional correlation ID for logging

    Returns:
        dict with pattern data or error info
    """
    log = {"user_id": str(user_id), "correlation_id": correlation_id}

    logger.info("patterns.request.received", **log)

    try:
        return await _compute_patterns_impl(user_id, session, log)
    except Exception as e:
        logger.error(
            "patterns.error",
            error_type=type(e).__name__,
            **log,
        )
        # Return error response rather than raising
        return {
            "success": False,
            "error": {
                "code": "PATTERN_COMPUTE_ERROR",
                "message": "Pattern computation failed. Please try again.",
            },
        }


async def _compute_patterns_impl(
    user_id: UUID,
    session: AsyncSession,
    log: dict,
) -> dict[str, Any]:
    """
    Implementation of pattern computation.

    Separated from public function for error handling.
    """
    # Compute window boundaries once
    current_week_start = get_current_week_start_utc()
    window_start_date = current_week_start - relativedelta(months=ROLLING_WINDOW_MONTHS)

    # Query snapshots within rolling window, excluding current week
    snapshot_query = (
        select(PgWeeklySnapshot)
        .where(PgWeeklySnapshot.user_id == user_id)
        .where(PgWeeklySnapshot.week_start >= window_start_date)
        .where(PgWeeklySnapshot.week_start < current_week_start)
        .order_by(PgWeeklySnapshot.week_start.desc())
    )
    snapshot_result = await session.execute(snapshot_query)
    all_snapshots = list(snapshot_result.scalars().all())

    # Query all priorities (active and retired)
    priority_query = (
        select(PgPriority)
        .where(PgPriority.user_id == user_id)
    )
    priority_result = await session.execute(priority_query)
    all_priorities = list(priority_result.scalars().all())

    # Compute weeks_available = distinct week_start count
    weeks_available = len({s.week_start for s in all_snapshots})

    # Check global floor
    if weeks_available < MINIMUM_WEEKS_FLOOR:
        logger.info(
            "patterns.data_insufficient",
            weeks_available=weeks_available,
            **log,
        )
        return {
            "success": True,
            "data": {
                "pattern_engine_version": PATTERN_ENGINE_VERSION,
                "reason": "INSUFFICIENT_WEEKS",
                "data_insufficient": True,
                "weeks_available": weeks_available,
                "rolling_window_months": ROLLING_WINDOW_MONTHS,
                "patterns": [],
                "pattern_count": 0,
            },
        }

    # Group snapshots by priority_id (already ordered by week_start desc)
    snapshots_by_priority: dict[UUID, list[PgWeeklySnapshot]] = {}
    for snapshot in all_snapshots:
        if snapshot.priority_id not in snapshots_by_priority:
            snapshots_by_priority[snapshot.priority_id] = []
        snapshots_by_priority[snapshot.priority_id].append(snapshot)

    # Compute all patterns
    patterns: list[dict] = []

    # Pattern 1: Consistency Streak
    patterns.extend(_compute_consistency_streaks(
        all_priorities, snapshots_by_priority, current_week_start
    ))

    # Pattern 2: Abandoned Priority Signal
    patterns.extend(_compute_abandoned_priorities(
        all_priorities, snapshots_by_priority
    ))

    # Pattern 3: Priority Switching Frequency
    patterns.extend(_compute_priority_switching(
        all_priorities, window_start_date, current_week_start
    ))

    # Pattern 4: Priority Protection
    patterns.extend(_compute_priority_protection(
        all_priorities, snapshots_by_priority
    ))

    # Sort patterns deterministically
    patterns = _sort_patterns(patterns)

    # Convert Decimals to floats for JSON serialization
    patterns = decimal_to_float_recursive(patterns)

    # Determine reason
    if patterns:
        reason = "PATTERNS_FOUND"
    else:
        reason = "NO_PATTERNS"

    logger.info(
        "patterns.compute.done",
        weeks_available=weeks_available,
        pattern_count=len(patterns),
        **log,
    )

    return {
        "success": True,
        "data": {
            "pattern_engine_version": PATTERN_ENGINE_VERSION,
            "reason": reason,
            "data_insufficient": False,
            "weeks_available": weeks_available,
            "rolling_window_months": ROLLING_WINDOW_MONTHS,
            "patterns": patterns,
            "pattern_count": len(patterns),
        },
    }
