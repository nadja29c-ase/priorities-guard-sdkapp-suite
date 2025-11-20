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


ConflictReason = Literal["new_event", "google_newer", "hash_changed", "stale_google", "no_change", "resurrection"]


def should_accept_update(
    local_event: FocusedFocusSession | None,
    google_updated_at: datetime,
    google_hash: str
) -> tuple[bool, ConflictReason]:
    """
    Determine if a Google Calendar event update should be accepted.
    
    “Accept the event” simply means:
    Apply the Google update to your database.
    Insert it if its new, or update the existing row if it already exists.
    
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
        - "resurrection": Local event is deleted (RESURRECT)
        - "google_newer": Google timestamp is newer (ACCEPT UPDATE)
        - "hash_changed": Timestamps equal but content differs (ACCEPT UPDATE)
        - "stale_google": Google timestamp is older (REJECT UPDATE)
        - "no_change": Timestamps equal and content same (SKIP UPDATE)

    Rules:
        1. If local_event is None → Accept (new event)
        2. If google_updated_at > local.google_updated_at → Accept (Google newer)
           - If local status is 'deleted' → Mark as "resurrection"
        3. If google_updated_at < local.google_updated_at → Reject (stale Google)
           - This includes stale resurrection attempts
        4. If timestamps equal:
           - If hashes differ → Accept (content changed)
             * If local status is 'deleted' → Mark as "resurrection"
           - If hashes same → Reject (no change)

    Critical Design Notes:
        - Always compare timestamps FIRST (not hashes, not local fields)
        - Resurrection requires Google timestamp >= local timestamp (no stale resurrection)
        - Google Calendar is the single source of truth
        - This handles:
          * Out-of-order webhooks (webhook A v102, then webhook B v101)
          * Stale API responses during sync
          * Stale resurrection attempts (deleted event with old confirmed webhook)
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

    # Rule 2: Google timestamp is newer → accept update (including resurrection)
    if google_updated_at > local_event.google_updated_at:
        # Check if this is a resurrection (deleted → active with newer timestamp)
        if local_event.status == "deleted":
            return (True, "resurrection")
        return (True, "google_newer")

    # Rule 3: Google timestamp is older → reject (stale)
    # CRITICAL: This rejects stale resurrection attempts
    # Example: Event deleted at 10:50, old "confirmed" webhook arrives with 10:40 timestamp
    if google_updated_at < local_event.google_updated_at:
        return (False, "stale_google")

    # Rule 4: Timestamps equal → check hash
    # This handles:
    # - Google clock drift
    # - Rapid updates within same second
    # - Description cleanup (NULL local description, recalculated hash differs)
    # - Resurrection with equal timestamp (rare but possible)
    if google_hash != local_event.sha256_content_hash:
        # Check if this is a resurrection with equal timestamp but hash change
        if local_event.status == "deleted":
            return (True, "resurrection")
        return (True, "hash_changed")

    # No change needed
    return (False, "no_change")


def should_accept_deletion(
    local_event: FocusedFocusSession | None,
    google_updated_at: datetime | None = None,
    missing_in_sync: bool = False
) -> tuple[bool, str]:
    """
    Determine if a deletion should be accepted.

    Used in two scenarios:
    1. Explicit Google cancellation: status='cancelled' with deletion timestamp
    2. Event missing from sync: Event disappeared from Google list (no timestamp)

    Args:
        local_event: Existing event from DB (None if already deleted)
        google_updated_at: Timestamp of deletion signal (None for missing_in_sync)
        missing_in_sync: True if event is missing from Google sync results

    Returns:
        Tuple of (should_delete: bool, reason: str)

    Reasons:
        - "no_local_event": Event doesn't exist locally
        - "missing_in_sync": Event absent from Google list (unconditional accept)
        - "google_deletion_newer": Google deletion timestamp ≥ local timestamp
        - "stale_deletion": Google deletion timestamp < local timestamp

    Rules:
        - If no local event → Don't delete (already gone or never existed)
        - If missing_in_sync → Accept (Google list is source of truth)
        - If google_updated_at >= local.google_updated_at → Accept deletion
        - If google_updated_at < local.google_updated_at → Reject (stale deletion signal)

    Critical:
        - missing_in_sync bypasses timestamp checks (fresh list always wins)
        - Protects against out-of-order deletion + update events
        - Example: Update event (v102) arrives, then delete event (v101) arrives late
          → Deletion rejected because local is already at v102
    """
    if local_event is None:
        return (False, "no_local_event")

    # Rule 1: Event missing from sync → unconditionally accept
    # Google list is the source of truth, no timestamp comparison needed
    if missing_in_sync:
        return (True, "missing_in_sync")

    # Defensive check: Ensure google_updated_at is provided for explicit deletions
    if google_updated_at is None and not missing_in_sync:
        logger.warning(
            "[conflict] Deletion called without google_updated_at and not marked missing_in_sync. "
            "This indicates a bug in the caller."
        )
        return (False, "invalid_deletion_call")

    # Rule 2: Explicit deletion with timestamp comparison
    # Accept deletion if Google timestamp is same or newer
    if google_updated_at >= local_event.google_updated_at:
        return (True, "google_deletion_newer")

    # Reject stale deletion
    return (False, "stale_deletion")
