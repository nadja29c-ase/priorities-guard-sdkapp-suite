"""
Calendar service for Priority Guardian.

Computes per-priority time allocation from Google Calendar events.
This is the core business logic for the time tracking pipeline.
"""

import re
import structlog
from datetime import datetime, timedelta, date, timezone
from fractions import Fraction
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


def compute_week_boundaries(
    timezone_str: str,
    target_date: date | None = None,
) -> tuple[datetime, datetime]:
    """
    Compute Monday 00:00 to next Monday 00:00 in the given timezone.

    Uses zoneinfo.ZoneInfo for proper DST handling. Never use manual
    UTC offset math - DST transitions create 23h or 25h days.

    Args:
        timezone_str: IANA timezone string (e.g., "Europe/Berlin")
        target_date: Optional date within the target week. If provided,
            computes boundaries for the week containing that date.
            If the date is a Monday, returns that week's boundaries.
            If None, computes boundaries for the current week.

    Returns:
        Tuple of (week_start, week_end) as timezone-aware datetimes
        Both are in the specified timezone, suitable for conversion to UTC

    Raises:
        ValueError: If target_date is provided but is not a Monday
    """
    try:
        tz = ZoneInfo(timezone_str)
    except Exception:
        logger.warning("calendar.invalid_timezone", timezone=timezone_str, fallback="UTC")
        tz = ZoneInfo("UTC")

    if target_date is not None:
        # Validate target_date is a Monday (weekday() == 0)
        if target_date.weekday() != 0:
            raise ValueError(f"target_date must be a Monday, got {target_date} (weekday={target_date.weekday()})")

        # Create Monday 00:00 from the target date
        monday_this_week = datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            hour=0, minute=0, second=0, microsecond=0,
            tzinfo=tz,
        )
    else:
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

    Uses interval sweep + distinct bucket attribution to correctly handle
    overlapping events. Every wall-clock second covered by at least one
    filtered-in event contributes to total_tracked_hours exactly once;
    that time is divided evenly across the distinct claimant buckets.

    Bucket model:
    - Four buckets: P1, P2, P3, other
    - Event title matches one keyword → claims that priority bucket
    - Event title matches multiple keywords → claims each matched bucket
    - Event title matches no keyword → claims "other"

    Filtering rules:
    - Exclude all-day events
    - Exclude declined events
    - Exclude cancelled events
    - Exclude zero-duration events

    Args:
        events: List of Google Calendar event dicts

    Returns:
        Dict with:
        - keywords: {P1: {hours, event_count}, P2: {...}, P3: {...}}
        - other_hours: float
        - total_tracked_hours: float
        - total_events_scanned: int
        - bar_segments: {P1, P2, P3, other} mirrors keyword_hours + other_hours
        - overlap_segment_count: int (segments where >1 bucket shared time; ops telemetry)
    """
    total_events_scanned = len(events)

    # Track event counts per keyword (independent of hour attribution)
    keyword_event_counts: dict[str, int] = {"P1": 0, "P2": 0, "P3": 0}

    # Build list of (start_epoch, end_epoch, claims) for filtered events
    # claims is a frozenset of bucket names
    intervals: list[tuple[int, int, frozenset[str]]] = []

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

        # Get start/end datetimes
        start_str = event.get("start", {}).get("dateTime")
        end_str = event.get("end", {}).get("dateTime")
        if not start_str or not end_str:
            continue

        try:
            start_dt = datetime.fromisoformat(start_str)
            end_dt = datetime.fromisoformat(end_str)
        except (ValueError, TypeError):
            continue

        # Skip zero or negative duration
        if start_dt >= end_dt:
            continue

        # Convert to UTC epoch seconds (integer)
        start_epoch = int(start_dt.timestamp())
        end_epoch = int(end_dt.timestamp())

        # Match keywords to determine claims
        title = event.get("summary", "")
        matched_keywords = match_keywords(title)

        # Update event counts (per matched keyword, dedupe to avoid double-counting
        # titles like "P1 P1 planning" as two P1 events)
        for kw in set(matched_keywords):
            if kw in keyword_event_counts:
                keyword_event_counts[kw] += 1

        # Warn if event has no ID (defensive: malformed API response signal)
        if not event.get("id"):
            logger.warning("calendar.event_missing_id")

        # Determine bucket claims for this event
        if matched_keywords:
            claims = frozenset(kw for kw in matched_keywords if kw in ("P1", "P2", "P3"))
        else:
            claims = frozenset(["other"])

        intervals.append((start_epoch, end_epoch, claims))

    # Handle empty case
    if not intervals:
        return {
            "keywords": {
                "P1": {"hours": 0.0, "event_count": 0},
                "P2": {"hours": 0.0, "event_count": 0},
                "P3": {"hours": 0.0, "event_count": 0},
            },
            "other_hours": 0.0,
            "total_tracked_hours": 0.0,
            "total_events_scanned": total_events_scanned,
            "bar_segments": {"P1": 0.0, "P2": 0.0, "P3": 0.0, "other": 0.0},
            "overlap_segment_count": 0,
        }

    # Build sorted list of boundary points
    boundaries: set[int] = set()
    for start_epoch, end_epoch, _ in intervals:
        boundaries.add(start_epoch)
        boundaries.add(end_epoch)
    sorted_boundaries = sorted(boundaries)

    # Accumulate seconds per bucket using Fraction for exact arithmetic
    bucket_seconds: dict[str, Fraction] = {
        "P1": Fraction(0),
        "P2": Fraction(0),
        "P3": Fraction(0),
        "other": Fraction(0),
    }
    total_seconds = Fraction(0)
    overlap_segment_count = 0  # Count segments with >1 distinct bucket claim

    # Sweep through adjacent boundary pairs
    for i in range(len(sorted_boundaries) - 1):
        seg_start = sorted_boundaries[i]
        seg_end = sorted_boundaries[i + 1]
        seg_length = seg_end - seg_start

        if seg_length <= 0:
            continue

        # Find all distinct bucket claims covering this segment
        distinct_claims: set[str] = set()
        for start_epoch, end_epoch, claims in intervals:
            if start_epoch <= seg_start and end_epoch >= seg_end:
                distinct_claims.update(claims)

        if not distinct_claims:
            continue

        # Track segments where multiple buckets share time (overlap indicator)
        if len(distinct_claims) > 1:
            overlap_segment_count += 1

        # Split segment equally across distinct claimant buckets
        num_claimants = len(distinct_claims)
        share = Fraction(seg_length, num_claimants)

        for bucket in distinct_claims:
            bucket_seconds[bucket] += share

        total_seconds += seg_length

    # Convert to hours (divide by 3600) and round to 2 decimals
    p1_hours = round(float(bucket_seconds["P1"]) / 3600, 2)
    p2_hours = round(float(bucket_seconds["P2"]) / 3600, 2)
    p3_hours = round(float(bucket_seconds["P3"]) / 3600, 2)
    other_hours = round(float(bucket_seconds["other"]) / 3600, 2)
    total_tracked_hours = round(float(total_seconds) / 3600, 2)

    return {
        "keywords": {
            "P1": {"hours": p1_hours, "event_count": keyword_event_counts["P1"]},
            "P2": {"hours": p2_hours, "event_count": keyword_event_counts["P2"]},
            "P3": {"hours": p3_hours, "event_count": keyword_event_counts["P3"]},
        },
        "other_hours": other_hours,
        "total_tracked_hours": total_tracked_hours,
        "total_events_scanned": total_events_scanned,
        "bar_segments": {
            "P1": p1_hours,
            "P2": p2_hours,
            "P3": p3_hours,
            "other": other_hours,
        },
        "overlap_segment_count": overlap_segment_count,
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
        logger.warning("calendar.token_error", error_code=error_code, **log_context)

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

    # Update last_used_at after successful Google API call (Increment 39)
    # Per architectural rule: update immediately after each successful response
    connection.last_used_at = datetime.now(timezone.utc)

    # -------------------------------------------------------------------------
    # Step 4: Compute week boundaries
    # -------------------------------------------------------------------------
    week_start, week_end = compute_week_boundaries(timezone_str)

    # Convert to RFC3339 for Google API
    time_min = to_rfc3339(week_start)
    time_max = to_rfc3339(week_end)

    logger.info(
        "calendar.fetching_events",
        time_min=time_min,
        time_max=time_max,
        timezone=timezone_str,
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
            logger.warning("calendar.pages_failed", pages_failed=pages_failed, **log_context)

        # Update last_used_at after successful Google API call (Increment 39)
        # Per architectural rule: update immediately after each successful response
        connection.last_used_at = datetime.now(timezone.utc)

    except ValueError as e:
        # API errors (401, 403, etc.)
        logger.error("calendar.fetch_events_failed", error=str(e), **log_context)
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
        "calendar.allocation_computed",
        total_events=allocation["total_events_scanned"],
        total_hours=allocation["total_tracked_hours"],
        p1_hours=allocation["keywords"]["P1"]["hours"],
        p2_hours=allocation["keywords"]["P2"]["hours"],
        p3_hours=allocation["keywords"]["P3"]["hours"],
        other_hours=allocation["other_hours"],
        overlap_segment_count=allocation.get("overlap_segment_count", 0),
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
        "overlap_segment_count": 0,
    }
