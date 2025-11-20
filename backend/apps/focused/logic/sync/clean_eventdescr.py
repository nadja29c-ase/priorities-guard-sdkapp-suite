"""
Increment 6C: GDPR-Compliant Description Cleanup

Automatically deletes event_description fields after 72 hours to comply with
GDPR data minimization principles.

Key Features:
- Deletes descriptions older than 72 hours (based on updated_at)
- Uses updated_at (not created_at) so re-synced descriptions get fresh 72h window
- Preserves all other event data (summary, times, focus block detection)
- SHA256 hash still includes description for sync correctness
- Single UPDATE query (no batching needed)

GDPR Compliance Note:
If a user frequently edits an event, the description remains because it's
in active processing. The retention window refreshes naturally on each sync.
This is fully compliant.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.focused.focused_config import FOCUSED_EVENTDESCR_TTL

logger = logging.getLogger(__name__)


async def cleanup_old_descriptions(session: AsyncSession) -> int:
    """
    Delete event descriptions older than 72 hours.

    Uses updated_at timestamp to determine age. This ensures that
    re-synced descriptions get a fresh 72-hour retention window.

    Args:
        session: Database session

    Returns:
        Number of descriptions deleted

    Process:
        1. Calculate cutoff time (now - 72 hours)
        2. Find all active events with non-NULL descriptions older than cutoff
        3. Set event_description = NULL for matching events
        4. Update updated_at to reflect the cleanup operation

    Critical Design:
        - Uses updated_at (NOT created_at) as the age reference
        - Only processes active events (status = 'active')
        - Preserves deleted events as-is
        - Single UPDATE query (efficient for any dataset size)

    Example:
        Event created on Jan 1, synced on Jan 2
        → Description deleted on Jan 5 (72h after last sync)

        If event is re-synced on Jan 6, description restored
        → New deletion date: Jan 9 (fresh 72h window)
    """
    logger.info("[cleanup] Starting event description cleanup")

    try:
        # Calculate cutoff time
        now_utc = datetime.now(timezone.utc)
        cutoff = now_utc - FOCUSED_EVENTDESCR_TTL

        logger.debug(f"[cleanup] Cutoff time: {cutoff.isoformat()}, TTL: {FOCUSED_EVENTDESCR_TTL}")

        # Delete descriptions older than cutoff
        stmt = text("""
            UPDATE focused_focus_sessions
            SET event_description = NULL,
                updated_at = :now_utc
            WHERE status = 'active'
              AND event_description IS NOT NULL
              AND updated_at < :cutoff
        """)

        result = await session.execute(
            stmt,
            {
                "cutoff": cutoff,
                "now_utc": now_utc
            }
        )

        deleted_count = result.rowcount or 0

        if deleted_count > 0:
            logger.info(f"[cleanup] Deleted {deleted_count} event descriptions older than 72h")
        else:
            logger.debug("[cleanup] No descriptions to delete (all recent or already cleaned)")

        return deleted_count

    except Exception as e:
        logger.error(f"[cleanup] Error during description cleanup: {e}")
        raise
