"""
Batch processing logic for sync operations.

Handles:
- Validating events before processing
- Processing events in batches of 100
- Transaction boundaries for each batch
- Error handling and recovery
- Batch failure tracking
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.focused.logic.sync.tx import transaction_scope
from backend.apps.focused.logic.sync.utils import is_valid_event
from backend.apps.focused.logic.sync.single_event import process_single_event

logger = logging.getLogger(__name__)


async def process_event_batches(
    user_id: str,
    events: list[dict[str, Any]],
    keywords: list[str],
    session: AsyncSession
) -> tuple[int, int, int, int]:
    """
    Process events in batches of 100 with upsert logic.

    Args:
        user_id: User ID (UUID as string)
        events: List of Google Calendar events
        keywords: Focus keywords for matching
        session: Database session

    Returns:
        Tuple of (events_inserted, events_updated, events_deleted, batches_failed)

    Critical:
        - Batch size 100 events per transaction
        - Commit after each batch
        - Continue processing if batch fails
        - Track batch failures for needs_sync flag decision
        - Skip invalid events silently
        - Track explicit deletions (status='cancelled')
    """
    events_inserted = 0
    events_updated = 0
    events_deleted = 0
    batches_failed = 0

    # Filter and validate events
    valid_events = []
    for event in events:
        is_valid, skip_reason = is_valid_event(event)
        if not is_valid:
            logger.debug(f"[sync] Skipping event {event.get('id')}: {skip_reason}")
            continue
        valid_events.append(event)

    logger.info(f"[sync] Processing {len(valid_events)} valid events (out of {len(events)} total)")

    # Process in batches of 100
    batch_size = 100
    for batch_start in range(0, len(valid_events), batch_size):
        batch = valid_events[batch_start:batch_start + batch_size]
        batch_num = (batch_start // batch_size) + 1
        total_batches = (len(valid_events) + batch_size - 1) // batch_size

        logger.info(f"[sync] Processing batch {batch_num}/{total_batches} ({len(batch)} events)")

        try:
            # 6B MANDATORY: Wrap batch in transaction boundary
            async with transaction_scope(session):
                for event in batch:
                    try:
                        result = await process_single_event(
                            user_id=user_id,
                            event=event,
                            keywords=keywords,
                            session=session
                        )

                        if result == "inserted":
                            events_inserted += 1
                        elif result == "updated":
                            events_updated += 1
                        elif result == "deleted":
                            events_deleted += 1

                    except Exception as e:
                        # Skip individual event errors
                        logger.warning(
                            f"[sync] Error processing event {event.get('id')}: {e}"
                        )
                        continue

                # Commit happens automatically on successful exit from context
                logger.info(f"[sync] Batch {batch_num} committed successfully")

            # Flush to ensure ORM session is aware of changes
            await session.flush()

        except Exception as e:
            # Rollback automatic on exception
            logger.error(f"[sync] Batch {batch_num} failed: {e}")
            batches_failed += 1
            # Continue with next batch

    return events_inserted, events_updated, events_deleted, batches_failed
