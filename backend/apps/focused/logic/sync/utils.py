"""
Utility functions for event sync operations.

Provides helpers for:
- ISO timestamp parsing and normalization
- Event validation
- Google event data normalization
"""

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


def parse_iso_timestamp(iso_string: str) -> datetime | None:
    """
    Parse ISO 8601 timestamp string to datetime with UTC timezone.

    Handles Google Calendar timestamp format (RFC 3339 with 'Z' suffix).

    Args:
        iso_string: ISO timestamp string (e.g., "2025-01-15T10:30:00Z")

    Returns:
        datetime object with UTC timezone, or None if parsing fails
    """
    try:
        return datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def is_valid_event(event: dict[str, Any]) -> tuple[bool, str | None]:
    """
    Validate a Google Calendar event for sync processing.

    Args:
        event: Google Calendar event dictionary

    Returns:
        Tuple of (is_valid: bool, skip_reason: str | None)

    Skip reasons:
        - "missing_start_end": Event missing start or end fields
        - "all_day_event": Event is all-day (no dateTime field)
        - "missing_updated": Event missing updated timestamp
        - "missing_identifiers": Event missing id or iCalUID
    """
    # Skip events missing start or end fields entirely
    if "start" not in event or "end" not in event:
        return (False, "missing_start_end")

    # Skip all-day events (no dateTime field)
    if "dateTime" not in event["start"] or "dateTime" not in event["end"]:
        return (False, "all_day_event")

    # Skip events missing updated field
    if "updated" not in event:
        return (False, "missing_updated")

    # Skip events with missing id or iCalUID
    if not event.get("id") or not event.get("iCalUID"):
        return (False, "missing_identifiers")

    return (True, None)


def normalize_event_summary(summary: str | None) -> str | None:
    """
    Normalize event summary for consistent storage.

    Args:
        summary: Raw summary from Google Calendar (can be None)

    Returns:
        Normalized summary or None
    """
    if summary is None:
        return None
    return summary.strip() if summary.strip() else None


def normalize_event_description(description: str | None, max_length: int = 8192) -> str:
    """
    Normalize and truncate event description.

    Args:
        description: Raw description from Google Calendar (can be None)
        max_length: Maximum length to truncate to (default: 8192)

    Returns:
        Normalized description (empty string if None)
    """
    if description is None:
        return ""
    return description[:max_length]
