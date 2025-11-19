"""
Increment 6D: Sync Conflict Detection Logic

Prevents data corruption from out-of-order webhook delivery and stale API responses.

Key Rules:
- Google Calendar is the single source of truth
- Use google_updated_at timestamp as primary conflict detector
- Fall back to hash comparison for equal timestamps
- Version field increments on accepted updates only

This module provides conflict resolution helpers that wrap the sync logic
from Increment 6B (event ingestion) with timestamp-based protection.
"""

import logging
from datetime import datetime
from typing import Literal

from backend.apps.focused.db_models import FocusedFocusSession

logger = logging.getLogger(__name__)


ConflictReason = Literal["new_event", "google_newer", "hash_changed", "stale_google", "no_change"]


def should_accept_update(
    local_event: FocusedFocusSession | None,
    google_updated_at: datetime,
    google_hash: str
) -> tuple[bool, ConflictReason]:
    """
    Determine if a Google Calendar event update should be accepted.

    This is the core conflict detection logic for Increment 6D.
    Prevents data corruption from:
    - Out-of-order webhook delivery
    - Stale Google API responses
    - Deletions vs updates applied in wrong order

    Args:
        local_event: Existing event from DB (None if new event)
        google_updated_at: Timestamp from Google event.updated field
        google_hash: SHA256 hash of Google event content

    Returns:
        Tuple of (should_update: bool, reason: ConflictReason)

    Reasons:
        - "new_event": No local event exists (INSERT)
        - "google_newer": Google timestamp is newer (ACCEPT UPDATE)
        - "hash_changed": Timestamps equal but content differs (ACCEPT UPDATE)
        - "stale_google": Google timestamp is older (REJECT UPDATE)
        - "no_change": Timestamps equal and content same (SKIP UPDATE)

    Rules:
        1. If local_event is None → Accept (new event)
        2. If google_updated_at > local.google_updated_at → Accept (Google newer)
        3. If google_updated_at < local.google_updated_at → Reject (stale Google)
        4. If timestamps equal:
           - If hashes differ → Accept (content changed)
           - If hashes same → Reject (no change)

    Critical Design Notes:
        - Always compare timestamps FIRST (not hashes, not local fields)
        - Google Calendar is the single source of truth
        - This handles:
          * Out-of-order webhooks (webhook A v102, then webhook B v101)
          * Stale API responses during sync
          * Description cleanup (NULL descriptions, handled separately in sync logic)
          * Clock drift (equal timestamps fall back to hash)

    Example:
        >>> local = FocusedFocusSession(google_updated_at=datetime(2025,1,15,10,0,0))
        >>> google_timestamp = datetime(2025,1,15,10,30,0)
        >>> should_update, reason = should_accept_update(local, google_timestamp, "hash123")
        >>> print(should_update, reason)
        True "google_newer"
    """
    # Rule 1: New event (no local record)
    if local_event is None:
        return (True, "new_event")

    # Rule 2: Google timestamp is newer → accept update
    if google_updated_at > local_event.google_updated_at:
        return (True, "google_newer")

    # Rule 3: Google timestamp is older → reject (stale)
    if google_updated_at < local_event.google_updated_at:
        return (False, "stale_google")

    # Rule 4: Timestamps equal → check hash
    # This handles:
    # - Google clock drift
    # - Rapid updates within same second
    # - Description cleanup (NULL local description, recalculated hash differs)
    if google_hash != local_event.sha256_content_hash:
        return (True, "hash_changed")

    # No change needed
    return (False, "no_change")


def should_accept_deletion(
    local_event: FocusedFocusSession | None,
    google_updated_at: datetime
) -> tuple[bool, str]:
    """
    Determine if a deletion should be accepted.

    Used when:
    - Google event has status='cancelled'
    - Event is missing from sync response (orphaned)

    Args:
        local_event: Existing event from DB (None if already deleted)
        google_updated_at: Timestamp of deletion signal

    Returns:
        Tuple of (should_delete: bool, reason: str)

    Reasons:
        - "no_local_event": Event doesn't exist locally
        - "google_deletion_newer": Google deletion timestamp ≥ local timestamp
        - "stale_deletion": Google deletion timestamp < local timestamp

    Rules:
        - If no local event → Don't delete (already gone or never existed)
        - If google_updated_at >= local.google_updated_at → Accept deletion
        - If google_updated_at < local.google_updated_at → Reject (stale deletion signal)

    Critical:
        - Protects against out-of-order deletion + update events
        - Example: Update event (v102) arrives, then delete event (v101) arrives late
          → Deletion rejected because local is already at v102
    """
    if local_event is None:
        return (False, "no_local_event")

    # Accept deletion if Google timestamp is same or newer
    if google_updated_at >= local_event.google_updated_at:
        return (True, "google_deletion_newer")

    # Reject stale deletion
    return (False, "stale_deletion")
