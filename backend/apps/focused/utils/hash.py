"""
SHA256 content hashing for calendar events.

Used for change detection and conflict resolution in the Focused app.Webhooks are unreliable — but still FAR better than every alternative.
"""

import hashlib
import json
from datetime import datetime


def calculate_content_hash(
    google_event_id: str,
    event_summary: str | None,
    event_description: str | None,
    start_time: datetime,
    end_time: datetime,
) -> str:
    """
    Calculate SHA256 hash for event content.

    Used to detect changes in event data (summary, description, timing).
    Critical for conflict detection in Increment 7.

    Args:
        google_event_id: Google's event.id
        event_summary: Event title (can be None or empty)
        event_description: Event description (can be None or empty)
        start_time: Event start time (MUST be UTC timezone-aware)
        end_time: Event end time (MUST be UTC timezone-aware)

    Returns:
        64-character hex string (SHA256 hash)

    Raises:
        ValueError: If timestamps are not timezone-aware or not UTC

    Example:
        >>> from datetime import datetime, timezone
        >>> calculate_content_hash(
        ...     google_event_id="abc123",
        ...     event_summary="Focus Time",
        ...     event_description="Deep work session",
        ...     start_time=datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc),
        ...     end_time=datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)
        ... )
        '...'
    """
    # Normalize event ID to string (Google sometimes sends non-string IDs)
    google_event_id = str(google_event_id)

    # CRITICAL: Enforce timezone-aware UTC timestamps
    # Prevents false conflicts from naive datetime bugs
    if start_time.tzinfo is None or start_time.utcoffset() is None:
        raise ValueError("start_time must be timezone-aware (UTC)")
    if end_time.tzinfo is None or end_time.utcoffset() is None:
        raise ValueError("end_time must be timezone-aware (UTC)")

    # Verify UTC (offset must be 0)
    from datetime import timedelta
    if start_time.utcoffset() != timedelta(0):
        raise ValueError("start_time must be UTC (offset must be 0)")
    if end_time.utcoffset() != timedelta(0):
        raise ValueError("end_time must be UTC (offset must be 0)")

    # Normalize summary and description (strip trailing whitespace)
    # Prevents spurious hash changes from Google API whitespace quirks
    summary = (event_summary or "").strip()
    description = (event_description or "").strip()

    # Build canonical dict for hashing
    # Order matters for consistent hashing
    # Empty strings for None values (consistent with spec)
    hash_dict = {
        "id": google_event_id,
        "summary": summary,
        "description": description,  # CRITICAL: Must include description
        "start": start_time.isoformat(),
        "end": end_time.isoformat(),
    }

    # Serialize to JSON with sorted keys for deterministic output
    canonical_json = json.dumps(hash_dict, sort_keys=True)

    # Calculate SHA256
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
