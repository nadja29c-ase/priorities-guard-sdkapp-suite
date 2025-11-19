"""
Increment 6B: Event Ingestion Pipeline

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
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.google_calendar import list_events
from backend.core.models import CoreConnection
from backend.core.redis_client import get_needs_sync, delete_needs_sync
from backend.apps.focused.db_models import FocusedFocusSession, FocusedUserKeyword
from backend.apps.focused.utils.hash import calculate_content_hash
from backend.apps.focused.logic import matches_focus_keywords, load_user_custom_keywords
from backend.apps.focused.logic_tokens import ensure_valid_access_token
from backend.apps.focused.focused_config import get_default_keywords

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Transaction Helper
# ---------------------------------------------------------------------
@asynccontextmanager
async def transaction_scope(session: AsyncSession):
    """
    Smart transaction context manager.

    - If no transaction active: starts new transaction with session.begin()
    - If transaction already active: uses nested transaction (savepoint) with session.begin_nested()

    This allows production code to use explicit transaction boundaries
    while still working correctly in test environments where the test
    fixture provides a session with an active transaction.
    """
    if session.in_transaction():
        # Already in transaction (test environment or nested call)
        # Use savepoint for nested transaction
        async with session.begin_nested():
            yield
    else:
        # Not in transaction (production environment)
        # Start new transaction
        async with session.begin():
            yield


# ---------------------------------------------------------------------
# Main Sync Orchestrator
# ---------------------------------------------------------------------
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
        events_inserted, events_updated, batches_failed = await process_event_batches(
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

            # Step 6: Detect and soft-delete orphaned events
            events_deleted = await detect_deleted_events(
                user_id=user_id,
                fetched_event_ids=fetched_event_ids,
                session=session
            )

            # Step 7: Update last_synced_at for all active events
            await update_last_synced_timestamp(user_id=user_id, session=session)

            # Transaction commits automatically on successful exit

    except Exception as e:
        logger.error(f"[sync] Error in cleanup operations for user {user_id}: {e}")
        partial_failure = True
        events_deleted = 0

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


# ---------------------------------------------------------------------
# Event Processing (Batch Upserts)
# ---------------------------------------------------------------------
async def process_event_batches(
    user_id: str,
    events: list[dict[str, Any]],
    keywords: list[str],
    session: AsyncSession
) -> tuple[int, int, int]:
    """
    Process events in batches of 100 with upsert logic.

    Args:
        user_id: User ID (UUID as string)
        events: List of Google Calendar events
        keywords: Focus keywords for matching
        session: Database session

    Returns:
        Tuple of (events_inserted, events_updated, batches_failed)

    Critical:
        - Batch size 100 events per transaction
        - Commit after each batch
        - Continue processing if batch fails
        - Track batch failures for needs_sync flag decision
        - Skip invalid events silently
    """
    events_inserted = 0
    events_updated = 0
    batches_failed = 0

    # Filter and validate events
    valid_events = []
    for event in events:
        # Skip events missing start or end fields entirely
        if "start" not in event or "end" not in event:
            logger.debug(f"[sync] Skipping event with missing start/end: {event.get('id')}")
            continue

        # Skip all-day events (no dateTime field)
        if "dateTime" not in event["start"] or "dateTime" not in event["end"]:
            logger.debug(f"[sync] Skipping all-day event: {event.get('id')}")
            continue

        # Skip events missing updated field
        if "updated" not in event:
            logger.debug(f"[sync] Skipping event without updated field: {event.get('id')}")
            continue

        # Skip events with missing id or iCalUID
        if not event.get("id") or not event.get("iCalUID"):
            logger.debug(f"[sync] Skipping event with missing id/iCalUID")
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

    return events_inserted, events_updated, batches_failed


# ---------------------------------------------------------------------
# Single Event Processing
# ---------------------------------------------------------------------
async def process_single_event(
    user_id: str,
    event: dict[str, Any],
    keywords: list[str],
    session: AsyncSession
) -> str:
    """
    Process a single event using SQL ON CONFLICT ... DO UPDATE.

    6B MANDATORY: Uses SQL-level upsert with deterministic conflict resolution.
    No Python-level SELECT-then-UPDATE to avoid race conditions.

    Args:
        user_id: User ID (UUID as string)
        event: Google Calendar event
        keywords: Focus keywords for matching
        session: Database session

    Returns:
        "inserted", "updated", or "skipped"

    Critical:
        - Parse timestamps with timezone awareness
        - Calculate SHA256 hash
        - Match focus keywords
        - Use ON CONFLICT ... DO UPDATE (SQL-level)
        - Conflict resolution in SQL WHERE clause:
          * Google timestamp newer, OR
          * Timestamps equal + hash changed, OR
          * Status = 'deleted' (resurrection)
    """
    # Extract fields
    google_event_id = event["id"]
    google_ical_uid = event["iCalUID"]
    google_calendar_id = "primary"

    # Parse timestamps (convert to UTC)
    try:
        start_time = datetime.fromisoformat(
            event["start"]["dateTime"].replace("Z", "+00:00")
        )
        end_time = datetime.fromisoformat(
            event["end"]["dateTime"].replace("Z", "+00:00")
        )
        google_updated_at = datetime.fromisoformat(
            event["updated"].replace("Z", "+00:00")
        )
    except (ValueError, KeyError) as e:
        logger.warning(f"[sync] Invalid timestamp in event {google_event_id}: {e}")
        return "skipped"

    # Validate start < end
    if start_time >= end_time:
        logger.warning(f"[sync] Invalid time range in event {google_event_id}")
        return "skipped"

    # Extract summary and description
    event_summary = event.get("summary")  # Can be None
    event_description = (event.get("description") or "")[:8192]  # Truncate to 8192

    # Calculate SHA256 hash
    try:
        sha256_content_hash = calculate_content_hash(
            google_event_id=google_event_id,
            event_summary=event_summary,
            event_description=event_description,
            start_time=start_time,
            end_time=end_time
        )
    except Exception as e:
        logger.warning(f"[sync] Hash calculation error for event {google_event_id}: {e}")
        return "skipped"

    # Focus keyword matching
    matched_keyword = matches_focus_keywords(event.get('summary', ''), keywords)
    is_focus_block = matched_keyword is not None

    # Increment 6C: Check if local description is NULL (cleaned by 72h TTL)
    # If NULL, recalculate hash and compare to detect real changes
    check_null_desc_stmt = text("""
        SELECT sha256_content_hash, event_description
        FROM focused_focus_sessions
        WHERE user_id = :user_id
          AND google_event_id = :google_event_id
          AND google_calendar_id = :google_calendar_id
          AND status = 'active'
    """)

    try:
        check_result = await session.execute(
            check_null_desc_stmt,
            {
                "user_id": UUID(user_id),
                "google_event_id": google_event_id,
                "google_calendar_id": google_calendar_id
            }
        )
        existing_row = check_result.fetchone()

        # If event exists and description is NULL (cleaned), check if hash changed
        if existing_row and existing_row[1] is None:  # event_description IS NULL
            stored_hash = existing_row[0]

            # Hash was calculated from Google's full data (including description)
            # If fresh hash == stored hash, nothing changed -> skip
            if sha256_content_hash == stored_hash:
                logger.debug(
                    f"[sync] Event {google_event_id} has NULL description but hash unchanged - skipping"
                )
                return "skipped"

            # Hash differs -> real change detected, proceed with update
            logger.debug(
                f"[sync] Event {google_event_id} has NULL description and hash changed - updating"
            )

    except Exception as e:
        logger.warning(f"[sync] Error checking NULL description for {google_event_id}: {e}")
        # Continue with normal upsert logic if check fails

    # 6B MANDATORY: SQL ON CONFLICT ... DO UPDATE
    # All conflict resolution happens in SQL WHERE clause
    upsert_stmt = text("""
        INSERT INTO focused_focus_sessions (
            user_id, google_event_id, google_calendar_id, google_ical_uid,
            google_updated_at, event_summary, event_description,
            start_time, end_time, is_focus_block, matched_keyword,
            sha256_content_hash, status
        ) VALUES (
            :user_id, :google_event_id, :google_calendar_id, :google_ical_uid,
            :google_updated_at, :event_summary, :event_description,
            :start_time, :end_time, :is_focus_block, :matched_keyword,
            :sha256_content_hash, 'active'
        )
        ON CONFLICT (user_id, google_event_id, google_calendar_id)
        DO UPDATE SET
            google_updated_at = EXCLUDED.google_updated_at,
            google_ical_uid = EXCLUDED.google_ical_uid,
            event_summary = EXCLUDED.event_summary,
            event_description = EXCLUDED.event_description,
            start_time = EXCLUDED.start_time,
            end_time = EXCLUDED.end_time,
            is_focus_block = EXCLUDED.is_focus_block,
            matched_keyword = EXCLUDED.matched_keyword,
            sha256_content_hash = EXCLUDED.sha256_content_hash,
            status = 'active'::event_status_enum,
            deleted_at = NULL,
            updated_at = NOW(),
            version = focused_focus_sessions.version + 1
        WHERE
            -- Increment 6D conflict resolution (SQL-level):
            -- Accept update if ANY of these conditions are true:

            -- 1. Google timestamp is newer
            focused_focus_sessions.google_updated_at < EXCLUDED.google_updated_at

            -- 2. Timestamps equal but content changed (hash differs)
            OR (focused_focus_sessions.google_updated_at = EXCLUDED.google_updated_at
                AND focused_focus_sessions.sha256_content_hash != EXCLUDED.sha256_content_hash)

            -- 3. Event was deleted (resurrection: deleted → active)
            OR focused_focus_sessions.status = 'deleted'::event_status_enum

        RETURNING version
    """)

    try:
        result = await session.execute(
            upsert_stmt,
            {
                "user_id": UUID(user_id),
                "google_event_id": google_event_id,
                "google_calendar_id": google_calendar_id,
                "google_ical_uid": google_ical_uid,
                "google_updated_at": google_updated_at,
                "event_summary": event_summary,
                "event_description": event_description,
                "start_time": start_time,
                "end_time": end_time,
                "is_focus_block": is_focus_block,
                "matched_keyword": matched_keyword,
                "sha256_content_hash": sha256_content_hash
            }
        )

        # Fetch the version from RETURNING clause
        # CRITICAL: Do NOT rely on result.rowcount with PostgreSQL async - it's unreliable
        # Instead, check if RETURNING gave us a row
        row = result.fetchone()

        if not row:
            # ON CONFLICT WHERE clause rejected update (stale data or no change)
            logger.debug(
                "focused.sync.conflict.stale_or_unchanged",
                extra={
                    "user_id": user_id,
                    "event_id": google_event_id,
                    "google_updated_at": google_updated_at.isoformat()
                }
            )
            return "skipped"

        version = row[0]

        # Determine operation type from version
        if version == 1:
            # New insert (version starts at 1)
            logger.info(
                "focused.sync.event.inserted",
                extra={
                    "user_id": user_id,
                    "event_id": google_event_id,
                    "version": version
                }
            )
            return "inserted"
        else:
            # Update (version > 1)
            logger.info(
                "focused.sync.event.updated",
                extra={
                    "user_id": user_id,
                    "event_id": google_event_id,
                    "new_version": version
                }
            )
            return "updated"

    except Exception as e:
        logger.error(
            "focused.sync.upsert_error",
            extra={
                "user_id": user_id,
                "event_id": google_event_id,
                "error": str(e)
            }
        )
        return "skipped"


# ---------------------------------------------------------------------
# Deleted Event Detection
# ---------------------------------------------------------------------
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


# ---------------------------------------------------------------------
# Batch Update last_synced_at
# ---------------------------------------------------------------------
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
