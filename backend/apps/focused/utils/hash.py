"""
SHA256 content hashing for calendar events.

Used for change detection and conflict resolution in the Focused app.
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
        start_time: Event start time (UTC)
        end_time: Event end time (UTC)

    Returns:
        64-character hex string (SHA256 hash)

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
    # Build canonical dict for hashing
    # Order matters for consistent hashing
    # Empty strings for None values (consistent with spec)
    hash_dict = {
        "id": google_event_id,
        "summary": event_summary or "",
        "description": event_description or "",  # CRITICAL: Must include description
        "start": start_time.isoformat(),
        "end": end_time.isoformat(),
    }

    # Serialize to JSON with sorted keys for deterministic output
    canonical_json = json.dumps(hash_dict, sort_keys=True)

    # Calculate SHA256
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
