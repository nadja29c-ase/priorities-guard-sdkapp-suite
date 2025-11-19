"""
Sync cleanup operations: deletion detection and timestamp updates.

Handles:
- Detecting events that no longer exist in Google Calendar (orphaned events)
- Soft-deleting orphaned events
- Updating last_synced_at timestamp for all active events
"""

import logging
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.focused.db_models import FocusedFocusSession

logger = logging.getLogger(__name__)


async def detect_deleted_events(
    user_id: str,
    fetched_event_ids: list[str],
    session: AsyncSession
) -> int:
    """
    Detect and soft-delete events that no longer exist in Google Calendar.

    Args:
        user_id: User ID (UUID as string)
        fetched_event_ids: List of event IDs from Google API
        session: Database session

    Returns:
        Number of events soft-deleted

    Critical:
        - Only soft-delete (set status='deleted', deleted_at=NOW())
        - Never physically delete events
        - Only check active events
        - MUST be called within an active transaction (enforced by assertion)
    """
    # Safety guard: Ensure this function is called within a transaction
    # This prevents partial deletion failures from leaving inconsistent state
    assert session.in_transaction(), (
        "detect_deleted_events must be called within an active transaction"
    )

    logger.info(f"[sync] Detecting deleted events for user {user_id}")

    # If no events fetched, all active events should be soft-deleted
    if fetched_event_ids:
        stmt = select(FocusedFocusSession.google_event_id).where(
            FocusedFocusSession.user_id == UUID(user_id),
            FocusedFocusSession.google_calendar_id == "primary",
            FocusedFocusSession.status == "active",
            FocusedFocusSession.google_event_id.notin_(fetched_event_ids)
        )
    else:
        # No events fetched - all active events are orphaned
        stmt = select(FocusedFocusSession.google_event_id).where(
            FocusedFocusSession.user_id == UUID(user_id),
            FocusedFocusSession.google_calendar_id == "primary",
            FocusedFocusSession.status == "active"
        )

    result = await session.execute(stmt)
    orphaned_ids = [row[0] for row in result.fetchall()]

    if not orphaned_ids:
        logger.info(f"[sync] No orphaned events for user {user_id}")
        return 0

    logger.info(f"[sync] Found {len(orphaned_ids)} orphaned events, soft-deleting")

    # Soft-delete orphaned events (Increment 6D: increment version on deletion)
    deleted_count = 0

    for orphan_id in orphaned_ids:
        # Load event to get current version
        event_stmt = select(FocusedFocusSession).where(
            FocusedFocusSession.user_id == UUID(user_id),
            FocusedFocusSession.google_calendar_id == "primary",
            FocusedFocusSession.google_event_id == orphan_id
        )
        event_result = await session.execute(event_stmt)
        orphan_event = event_result.scalar_one_or_none()

        if not orphan_event:
            continue  # Event already deleted

        old_version = orphan_event.version

        update_stmt = (
            text("""
                UPDATE focused_focus_sessions
                SET status = 'deleted',
                    deleted_at = NOW(),
                    updated_at = NOW(),
                    version = :new_version
                WHERE user_id = :user_id
                  AND google_calendar_id = 'primary'
                  AND google_event_id = :event_id
            """)
        )

        await session.execute(
            update_stmt,
            {
                "user_id": UUID(user_id),
                "event_id": orphan_id,
                "new_version": old_version + 1
            }
        )

        logger.info(
            "focused.sync.event.deleted",
            extra={
                "user_id": user_id,
                "event_id": orphan_id,
                "reason": "orphaned",
                "old_version": old_version,
                "new_version": old_version + 1
            }
        )

        deleted_count += 1

    if deleted_count > 0:
        logger.info(
            "focused.sync.deletion_summary",
            extra={
                "user_id": user_id,
                "deleted_count": deleted_count
            }
        )

    return deleted_count


async def update_last_synced_timestamp(
    user_id: str,
    session: AsyncSession
) -> None:
    """
    Update last_synced_at for all active events.

    Called ONLY after successful sync completion.
    Updates all active events with identical timestamp.

    Args:
        user_id: User ID (UUID as string)
        session: Database session

    Critical:
        - Update ONCE per sync run
        - Only update active events
        - Use single SQL statement
        - MUST be called within an active transaction (enforced by assertion)
    """
    # Safety guard: Ensure this function is called within a transaction
    # This ensures atomicity with deletion detection
    assert session.in_transaction(), (
        "update_last_synced_timestamp must be called within an active transaction"
    )

    logger.info(f"[sync] Updating last_synced_at for user {user_id}")

    stmt = text("""
        UPDATE focused_focus_sessions
        SET last_synced_at = NOW()
        WHERE user_id = :user_id
          AND google_calendar_id = 'primary'
          AND status = 'active'
    """)

    result = await session.execute(stmt, {"user_id": UUID(user_id)})
    updated_count = result.rowcount

    logger.info(f"[sync] Updated last_synced_at for {updated_count} events")
