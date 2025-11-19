"""
Increment 6B: Event Ingestion Pipeline - Main Orchestrator

Syncs Google Calendar events into focused_focus_sessions table when needs_sync flag is set.

Key Features:
- Full resync (timeMin=-1day, timeMax=+30days)
- Pagination support (up to 10 pages, 250 events/page)
- Batch upserts (100 events per transaction)
- Focus keyword matching (reuses Increment 4 logic)
- SHA256 content hashing for change detection
- Soft delete for orphaned events
- last_synced_at batch update after successful sync

Critical Rules:
- Skip all-day events (no dateTime field)
- Skip events missing updated field
- Update based on google_updated_at OR hash change
- Commit every 100 events
- Continue if page fails (process successful pages)
- Only clear needs_sync if 100% pages succeeded
- Use UTC timezone everywhere
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.google_calendar import list_events
from backend.core.models import CoreConnection
from backend.core.redis_client import get_needs_sync, delete_needs_sync
from backend.apps.focused.logic_tokens import ensure_valid_access_token
from backend.apps.focused.focused_config import get_default_keywords
from backend.apps.focused.logic import load_user_custom_keywords
from backend.apps.focused.logic_sync.tx import transaction_scope
from backend.apps.focused.logic_sync.batches import process_event_batches
from backend.apps.focused.logic_sync.cleanup import detect_deleted_events, update_last_synced_timestamp

logger = logging.getLogger(__name__)


async def sync_calendar_events(
    user_id: str,
    session: AsyncSession,
    http_client: httpx.AsyncClient,
) -> dict[str, Any]:
    """
    Sync Google Calendar events into focused_focus_sessions table.

    Triggered when needs_sync Redis flag exists.
    Performs full resync (no incremental syncToken).

    Args:
        user_id: User ID (UUID as string)
        session: Database session
        http_client: HTTP client for API calls

    Returns:
        Dict with sync results:
        {
            "success": bool,
            "events_fetched": int,
            "events_inserted": int,
            "events_updated": int,
            "events_deleted": int,
            "error": str (if failed)
        }

    Process:
        1. Check needs_sync flag
        2. Fetch all events from Google (timeMin=-1d, timeMax=+30d)
        3. Process events in batches of 100 (upsert)
        4. Detect and soft-delete orphaned events
        5. Update last_synced_at for all active events
        6. Clear needs_sync flag (only if 100% successful)
    """
    logger.info(f"[sync] Starting calendar sync for user {user_id}")

    # Step 1: Check needs_sync flag
    needs_sync = await get_needs_sync(user_id)
    if not needs_sync:
        logger.info(f"[sync] No needs_sync flag for user {user_id}, skipping sync")
        return {
            "success": True,
            "events_fetched": 0,
            "events_inserted": 0,
            "events_updated": 0,
            "events_deleted": 0,
            "message": "No sync needed"
        }

    # Step 2: Load connection and ensure valid token
    try:
        stmt = select(CoreConnection).where(
            CoreConnection.user_id == user_id,
            CoreConnection.provider == "google",
        )
        result = await session.execute(stmt)
        connection = result.scalar_one_or_none()

        if connection is None:
            logger.error(f"[sync] No Google connection for user {user_id}")
            return {
                "success": False,
                "error": "USER_NOT_CONNECTED"
            }

        # Ensure valid access token (auto-refresh if needed)
        token_result = await ensure_valid_access_token(connection, session, http_client)
        if "error" in token_result:
            logger.error(f"[sync] Token error for user {user_id}: {token_result['error']}")
            return {
                "success": False,
                "error": token_result["error"]
            }

        access_token = token_result["access_token"]

    except Exception as e:
        logger.error(f"[sync] Error loading connection for user {user_id}: {e}")
        return {
            "success": False,
            "error": f"Database error: {type(e).__name__}"
        }

    # Step 3: Fetch events from Google Calendar
    # Track partial failures to determine if needs_sync should be cleared
    partial_failure = False

    try:
        now = datetime.now(timezone.utc)
        time_min = (now - timedelta(days=1)).isoformat().replace("+00:00", "Z")
        time_max = (now + timedelta(days=30)).isoformat().replace("+00:00", "Z")

        logger.info(f"[sync] Fetching events from {time_min} to {time_max}")

        all_events, pages_failed = await list_events(
            http_client=http_client,
            access_token=access_token,
            time_min=time_min,
            time_max=time_max,
            max_results_per_page=250,
            max_pages=10
        )

        events_fetched = len(all_events)
        logger.info(
            f"[sync] Fetched {events_fetched} events from Google Calendar "
            f"(pages failed: {pages_failed})"
        )

        if pages_failed > 0:
            partial_failure = True
            logger.warning(
                f"[sync] {pages_failed} page(s) failed during fetch for user {user_id}. "
                f"needs_sync flag will be preserved for retry."
            )

    except Exception as e:
        logger.error(f"[sync] Error fetching events for user {user_id}: {e}")
        return {
            "success": False,
            "error": f"Google API error: {type(e).__name__}"
        }

    # Step 4: Load user keywords for focus block detection
    try:
        system_defaults = get_default_keywords()
        user_custom = await load_user_custom_keywords(str(user_id), session)
        combined = system_defaults + (user_custom or [])
        effective_keywords = list(
            {k.strip(): None for k in combined if isinstance(k, str) and k.strip()}.keys()
        )

        logger.info(f"[sync] Using keywords: {effective_keywords}")

    except Exception as e:
        logger.error(f"[sync] Error loading keywords for user {user_id}: {e}")
        # Continue with defaults only
        effective_keywords = get_default_keywords()

    # Step 5: Process events in batches
    try:
        events_inserted, events_updated, events_deleted, batches_failed = await process_event_batches(
            user_id=user_id,
            events=all_events,
            keywords=effective_keywords,
            session=session
        )

        if batches_failed > 0:
            partial_failure = True
            logger.warning(
                f"[sync] {batches_failed} batch(es) failed for user {user_id}. "
                f"needs_sync flag will be preserved for retry."
            )

    except Exception as e:
        logger.error(f"[sync] Error processing events for user {user_id}: {e}")
        return {
            "success": False,
            "error": f"Event processing error: {type(e).__name__}"
        }

    # Step 6 & 7: Cleanup operations (deletion + last_synced_at) in single transaction
    # These must be atomic - either both succeed or both fail
    try:
        async with transaction_scope(session):
            fetched_event_ids = [
                event.get("id") for event in all_events
                if event.get("id")
            ]

            # Step 6: Detect and soft-delete orphaned events (missing from sync)
            orphaned_deleted = await detect_deleted_events(
                user_id=user_id,
                fetched_event_ids=fetched_event_ids,
                session=session
            )

            # Total deletions = explicit (status='cancelled') + orphaned (missing from sync)
            events_deleted += orphaned_deleted

            # Step 7: Update last_synced_at for all active events
            await update_last_synced_timestamp(user_id=user_id, session=session)

            # Transaction commits automatically on successful exit

    except Exception as e:
        logger.error(f"[sync] Error in cleanup operations for user {user_id}: {e}")
        partial_failure = True
        # Keep explicit deletions from batch processing, but orphaned detection failed
        # events_deleted already contains explicit deletions from process_event_batches

    # Step 8: Clear needs_sync flag ONLY if 100% successful
    if not partial_failure:
        await delete_needs_sync(str(user_id))
        logger.info(f"[sync] Cleared needs_sync flag for user {user_id} (100% successful)")
    else:
        logger.warning(
            f"[sync] Preserving needs_sync flag for user {user_id} due to partial failures. "
            f"Sync will be retried on next webhook."
        )

    logger.info(
        f"[sync] Sync completed for user {user_id}: "
        f"fetched={events_fetched}, inserted={events_inserted}, "
        f"updated={events_updated}, deleted={events_deleted}, "
        f"partial_failure={partial_failure}"
    )

    # Expire all ORM objects to ensure subsequent queries see fresh data
    # This is necessary because we use raw SQL which doesn't update the ORM cache
    session.expire_all()

    return {
        "success": not partial_failure,
        "events_fetched": events_fetched,
        "events_inserted": events_inserted,
        "events_updated": events_updated,
        "events_deleted": events_deleted,
        "partial_failure": partial_failure
    }
