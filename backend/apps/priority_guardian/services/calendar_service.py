"""
Calendar service for Priority Guardian.

Computes per-priority time allocation from Google Calendar events.
This is the core business logic for the time tracking pipeline.
"""

import re
import structlog
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.models import CoreConnection
from backend.core.google_calendar import fetch_events, get_user_timezone, list_events
from backend.core.google_token_management import ensure_valid_access_token
from backend.apps.priority_guardian.pg_config import PG_KEYWORDS

logger = structlog.get_logger(__name__)

# Word-boundary regex for P1/P2/P3 matching
# Matches "P1", "P2", "P3" as standalone tokens
# Rejects: "AP1", "P10", "StepP1X" (no word boundary)
# Accepts: "P1 meeting", "[P1] sync", "P1:", "Chapter P1"
KEYWORD_PATTERN = re.compile(r"\bP[123]\b", re.IGNORECASE)


# ============================================================================
# Week Boundary Computation
# ============================================================================


def compute_week_boundaries(timezone_str: str) -> tuple[datetime, datetime]:
    """
    Compute Monday 00:00 to next Monday 00:00 in the given timezone.

    Uses zoneinfo.ZoneInfo for proper DST handling. Never use manual
    UTC offset math - DST transitions create 23h or 25h days.

    Args:
        timezone_str: IANA timezone string (e.g., "Europe/Berlin")

    Returns:
        Tuple of (week_start, week_end) as timezone-aware datetimes
        Both are in the specified timezone, suitable for conversion to UTC
    """
    try:
        tz = ZoneInfo(timezone_str)
    except Exception:
        logger.warning(f"Invalid timezone '{timezone_str}', using UTC")
        tz = ZoneInfo("UTC")

    # Get current time in user's timezone
    now = datetime.now(tz)

    # Find Monday 00:00 of current week
    # weekday() returns 0 for Monday
    days_since_monday = now.weekday()
    monday_this_week = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_since_monday)

    # Next Monday 00:00 (exclusive end for timeMax)
    monday_next_week = monday_this_week + timedelta(days=7)

    return monday_this_week, monday_next_week


def to_rfc3339(dt: datetime) -> str:
    """Convert datetime to RFC3339 string for Google Calendar API."""
    return dt.isoformat()


# ============================================================================
# Event Filtering
# ============================================================================


def is_all_day_event(event: dict) -> bool:
    """
    Check if event is an all-day event.

    All-day events have 'date' instead of 'dateTime' in start/end.
    """
    start = event.get("start", {})
    return "date" in start and "dateTime" not in start


def is_declined_event(event: dict) -> bool:
    """
    Check if user declined this event.

    Looks for attendee with self=true and responseStatus="declined".
    Events with no attendees array are solo calendar events (included).
    """
    attendees = event.get("attendees", [])
    for attendee in attendees:
        if attendee.get("self") and attendee.get("responseStatus") == "declined":
            return True
    return False


def is_cancelled_event(event: dict) -> bool:
    """Check if event is cancelled."""
    return event.get("status") == "cancelled"


def compute_event_duration_hours(event: dict) -> float:
    """
    Compute event duration in hours.

    Args:
        event: Google Calendar event dict

    Returns:
        Duration in hours (float, 2 decimal places), or 0.0 if invalid
    """
    start_str = event.get("start", {}).get("dateTime")
    end_str = event.get("end", {}).get("dateTime")

    if not start_str or not end_str:
        return 0.0

    try:
        start_dt = datetime.fromisoformat(start_str)
        end_dt = datetime.fromisoformat(end_str)

        # Handle zero-duration events
        if start_dt >= end_dt:
            return 0.0

        duration = end_dt - start_dt
        hours = duration.total_seconds() / 3600
        return round(hours, 2)

    except (ValueError, TypeError):
        return 0.0


def match_keywords(event_title: str) -> list[str]:
    """
    Match P1/P2/P3 keywords in event title using word-boundary regex.

    Args:
        event_title: Event summary/title

    Returns:
        List of matched keywords (e.g., ["P1"], ["P1", "P2"], [])
        Keywords are uppercase and in order found.
    """
    if not event_title:
        return []

    matches = KEYWORD_PATTERN.findall(event_title)
    # Uppercase for consistency
    return [m.upper() for m in matches]


# ============================================================================
# Time Allocation Computation
# ============================================================================


def compute_allocation_from_events(events: list[dict]) -> dict[str, Any]:
    """
    Compute time allocation from a list of Google Calendar events.

    Implements all time computation rules from the spec:
    - Filter out all-day, declined, cancelled, zero-duration events
    - Match P1/P2/P3 keywords with word-boundary regex
    - Multi-match events counted for EACH keyword (overlapping)
    - bar_segments assigns multi-match to highest priority (P1 > P2 > P3)
    - totalTrackedHours is deduplicated by event ID

    Args:
        events: List of Google Calendar event dicts

    Returns:
        Dict with:
        - keywords: {P1: {hours, event_count}, P2: {...}, P3: {...}}
        - other_hours: float
        - total_tracked_hours: float
        - total_events_scanned: int
        - bar_segments: {P1, P2, P3, other} summing to total_tracked_hours
    """
    # Initialize keyword buckets
    keyword_hours: dict[str, float] = {"P1": 0.0, "P2": 0.0, "P3": 0.0}
    keyword_event_counts: dict[str, int] = {"P1": 0, "P2": 0, "P3": 0}

    # Bar segments (exclusive allocation for stacked bar)
    bar_segments: dict[str, float] = {"P1": 0.0, "P2": 0.0, "P3": 0.0, "other": 0.0}

    # Track unique events for totalTrackedHours (deduplicated)
    seen_event_ids: set[str] = set()
    total_tracked_hours = 0.0
    other_hours = 0.0
    total_events_scanned = len(events)

    for event in events:
        # Skip all-day events
        if is_all_day_event(event):
            continue

        # Skip declined events
        if is_declined_event(event):
            continue

        # Skip cancelled events
        if is_cancelled_event(event):
            continue

        # Compute duration
        duration = compute_event_duration_hours(event)
        if duration <= 0:
            continue

        # Get event ID for deduplication
        event_id = event.get("id")
        if not event_id:
            logger.warning("Event missing ID, skipping from total")
            continue

        # Match keywords
        title = event.get("summary", "")
        matched_keywords = match_keywords(title)

        # Add to totalTrackedHours (deduplicated)
        if event_id not in seen_event_ids:
            seen_event_ids.add(event_id)
            total_tracked_hours += duration

        if matched_keywords:
            # Add duration to EACH matched keyword bucket (overlapping)
            for kw in matched_keywords:
                if kw in keyword_hours:
                    keyword_hours[kw] += duration
                    keyword_event_counts[kw] += 1

            # Bar segment: assign to FIRST matched keyword (highest priority)
            # Keywords come out in order found, but we need priority order
            # P1 > P2 > P3
            for priority_kw in PG_KEYWORDS:  # ["P1", "P2", "P3"]
                if priority_kw in matched_keywords:
                    bar_segments[priority_kw] += duration
                    break
        else:
            # No keyword match → "other" hours
            other_hours += duration
            bar_segments["other"] += duration

    # Round all values to 2 decimal places
    return {
        "keywords": {
            "P1": {
                "hours": round(keyword_hours["P1"], 2),
                "event_count": keyword_event_counts["P1"],
            },
            "P2": {
                "hours": round(keyword_hours["P2"], 2),
                "event_count": keyword_event_counts["P2"],
            },
            "P3": {
                "hours": round(keyword_hours["P3"], 2),
                "event_count": keyword_event_counts["P3"],
            },
        },
        "other_hours": round(other_hours, 2),
        "total_tracked_hours": round(total_tracked_hours, 2),
        "total_events_scanned": total_events_scanned,
        "bar_segments": {
            "P1": round(bar_segments["P1"], 2),
            "P2": round(bar_segments["P2"], 2),
            "P3": round(bar_segments["P3"], 2),
            "other": round(bar_segments["other"], 2),
        },
    }


# ============================================================================
# Main Entry Point
# ============================================================================


async def compute_time_allocation(
    user_id: UUID,
    session: AsyncSession,
    http_client: httpx.AsyncClient,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """
    Compute time allocation for a user from their Google Calendar.

    This is the main entry point called by the calendar router.

    Flow:
    1. Load Google connection from DB
    2. Ensure valid access token (auto-refresh if needed)
    3. Fetch user's timezone from Google Calendar settings
    4. Compute week boundaries in user's timezone
    5. Fetch events for the week
    6. Filter and match keywords
    7. Compute hours per keyword + bar segments

    Args:
        user_id: User ID (UUID)
        session: Database session
        http_client: HTTP client for Google API calls
        correlation_id: Optional correlation ID for logging

    Returns:
        Dict with time allocation data, or all-zeros on graceful failure

    Raises:
        ValueError: If token refresh fails (propagate as 503)
        Exception: If Google Calendar API fails after retries (propagate as 502)
    """
    log_context = {"user_id": str(user_id), "correlation_id": correlation_id}

    # -------------------------------------------------------------------------
    # Step 1: Load Google connection
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
        logger.info("No Google connection found, returning zeros", **log_context)
        return _empty_allocation()

    # -------------------------------------------------------------------------
    # Step 2: Ensure valid access token
    # -------------------------------------------------------------------------
    token_result = await ensure_valid_access_token(connection, session, http_client)

    if "error" in token_result:
        error_code = token_result["error"]
        logger.warning(f"Token error: {error_code}", **log_context)

        if error_code == "REFRESH_TOKEN_INVALID":
            # User needs to reconnect - return zeros gracefully
            return _empty_allocation()

        # Other token errors - raise for 503
        raise ValueError(f"Token error: {error_code}")

    access_token = token_result["access_token"]

    # -------------------------------------------------------------------------
    # Step 3: Fetch user's timezone
    # -------------------------------------------------------------------------
    timezone_str = await get_user_timezone(http_client, access_token, correlation_id)

    # -------------------------------------------------------------------------
    # Step 4: Compute week boundaries
    # -------------------------------------------------------------------------
    week_start, week_end = compute_week_boundaries(timezone_str)

    # Convert to RFC3339 for Google API
    time_min = to_rfc3339(week_start)
    time_max = to_rfc3339(week_end)

    logger.info(
        f"Fetching events for week: {time_min} to {time_max} ({timezone_str})",
        **log_context
    )

    # -------------------------------------------------------------------------
    # Step 5: Fetch events
    # -------------------------------------------------------------------------
    try:
        # Use list_events for pagination support (handles >50 events)
        events, pages_failed = await list_events(
            http_client,
            access_token,
            time_min,
            time_max,
            max_results_per_page=250,
            max_pages=10,  # Up to 2500 events
        )

        if pages_failed > 0:
            logger.warning(f"{pages_failed} page(s) failed during event fetch", **log_context)

    except ValueError as e:
        # API errors (401, 403, etc.)
        logger.error(f"Failed to fetch events: {e}", **log_context)
        raise

    # -------------------------------------------------------------------------
    # Step 6: Compute allocation
    # -------------------------------------------------------------------------
    allocation = compute_allocation_from_events(events)

    # Add week metadata
    allocation["week_start"] = time_min
    allocation["week_end"] = time_max
    allocation["timezone"] = timezone_str

    logger.info(
        "Time allocation computed",
        total_events=allocation["total_events_scanned"],
        total_hours=allocation["total_tracked_hours"],
        p1_hours=allocation["keywords"]["P1"]["hours"],
        p2_hours=allocation["keywords"]["P2"]["hours"],
        p3_hours=allocation["keywords"]["P3"]["hours"],
        other_hours=allocation["other_hours"],
        **log_context
    )

    return allocation


def _empty_allocation() -> dict[str, Any]:
    """Return an all-zeros allocation for graceful degradation."""
    return {
        "week_start": None,
        "week_end": None,
        "timezone": "UTC",
        "keywords": {
            "P1": {"hours": 0.0, "event_count": 0},
            "P2": {"hours": 0.0, "event_count": 0},
            "P3": {"hours": 0.0, "event_count": 0},
        },
        "other_hours": 0.0,
        "total_tracked_hours": 0.0,
        "total_events_scanned": 0,
        "bar_segments": {
            "P1": 0.0,
            "P2": 0.0,
            "P3": 0.0,
            "other": 0.0,
        },
    }
