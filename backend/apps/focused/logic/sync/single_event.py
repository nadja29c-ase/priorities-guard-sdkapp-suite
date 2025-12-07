"""
Single event processing logic for sync operations.

Handles:
- Parsing individual Google Calendar events
- Timestamp validation
- Content hashing
- Keyword matching
- Conflict detection
- SQL upsert with conflict resolution
- Explicit deletions (status='cancelled')
"""

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.focused.db_models import FocusedFocusSession
from backend.apps.focused.utils.hash import calculate_content_hash
from backend.apps.focused.logic import matches_focus_keywords
from backend.apps.focused.logic.sync.sync_conflicts import should_accept_update, should_accept_deletion

logger = logging.getLogger(__name__)


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
        "inserted", "updated", "deleted", or "skipped"

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
    google_status = event.get("status", "confirmed")  # Default to "confirmed" if missing

    # Increment 6D: Handle explicit cancellations (status='cancelled')
    if google_status == "cancelled":
        return await _process_cancelled_event(
            user_id=user_id,
            event=event,
            google_event_id=google_event_id,
            google_calendar_id=google_calendar_id,
            session=session
        )

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

    # Increment 6D: Query local event for conflict detection
    # Required to get structured logging with proper conflict reasons
    query_local_stmt = text("""
        SELECT sha256_content_hash, google_updated_at, status
        FROM focused_focus_sessions
        WHERE user_id = :user_id
          AND google_event_id = :google_event_id
          AND google_calendar_id = :google_calendar_id
    """)

    local_event_data = None
    try:
        check_result = await session.execute(
            query_local_stmt,
            {
                "user_id": UUID(user_id),
                "google_event_id": google_event_id,
                "google_calendar_id": google_calendar_id
            }
        )
        existing_row = check_result.fetchone()

        if existing_row:
            local_event_data = {
                "sha256_content_hash": existing_row[0],
                "google_updated_at": existing_row[1],
                "status": existing_row[2]
            }

    except Exception as e:
        logger.warning(f"[sync] Error querying local event for conflict detection: {e}")
        # Continue with upsert - let SQL handle conflict resolution

    # Increment 6D: Apply conflict detection logic for structured logging
    conflict_reason = None  # Track reason for logging

    # Create minimal local_event object for conflict detection
    if local_event_data:
        # Mock object with only needed fields
        class LocalEvent:
            def __init__(self, data):
                self.sha256_content_hash = data["sha256_content_hash"]
                self.google_updated_at = data["google_updated_at"]
                self.status = data["status"]

        local_event_obj = LocalEvent(local_event_data)
        should_update, conflict_reason = should_accept_update(
            local_event_obj,
            google_updated_at,
            sha256_content_hash
        )

        # Structured logging with granular conflict reasons
        if not should_update:
            logger.info(
                "focused.sync.conflict.rejected",
                extra={
                    "user_id": str(user_id),
                    "event_id": google_event_id,
                    "calendar_id": google_calendar_id,
                    "event_summary": event_summary,
                    "reason": conflict_reason,
                    "google_updated_at": google_updated_at.isoformat(),
                    "local_updated_at": local_event_data["google_updated_at"].isoformat(),
                    "google_hash": sha256_content_hash,
                    "local_hash": local_event_data["sha256_content_hash"]
                }
            )
            return "skipped"

        # Log acceptance reason
        logger.info(
            "focused.sync.conflict.accepted",
            extra={
                "user_id": str(user_id),
                "event_id": google_event_id,
                "calendar_id": google_calendar_id,
                "event_summary": event_summary,
                "reason": conflict_reason,
                "google_updated_at": google_updated_at.isoformat(),
                "local_updated_at": local_event_data["google_updated_at"].isoformat() if local_event_data else None,
                "google_hash": sha256_content_hash,
                "local_hash": local_event_data["sha256_content_hash"] if local_event_data else None
            }
        )

    else:
        # New event
        conflict_reason = "new_event"
        logger.info(
            "focused.sync.conflict.accepted",
            extra={
                "user_id": str(user_id),
                "event_id": google_event_id,
                "calendar_id": google_calendar_id,
                "event_summary": event_summary,
                "reason": conflict_reason,
                "google_updated_at": google_updated_at.isoformat(),
                "google_hash": sha256_content_hash
            }
        )

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
        ON CONFLICT (user_id, google_ical_uid, start_time)
        DO UPDATE SET
            -- Only update mutable fields. Identity fields (user_id, google_ical_uid, start_time)
            -- are part of the conflict key and must NOT be updated.
            google_updated_at = EXCLUDED.google_updated_at,
            google_event_id = EXCLUDED.google_event_id,
            google_calendar_id = EXCLUDED.google_calendar_id,
            event_summary = EXCLUDED.event_summary,
            event_description = EXCLUDED.event_description,
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

            -- 1. Google timestamp is newer (includes valid resurrections with newer timestamp)
            focused_focus_sessions.google_updated_at < EXCLUDED.google_updated_at

            -- 2. Timestamps equal but content changed (includes valid resurrections with hash change)
            OR (focused_focus_sessions.google_updated_at = EXCLUDED.google_updated_at
                AND focused_focus_sessions.sha256_content_hash != EXCLUDED.sha256_content_hash)

            -- NOTE: No separate resurrection clause needed.
            -- Conditions 1 & 2 already handle ALL valid resurrection cases:
            -- - Resurrection with newer timestamp: Condition #1
            -- - Resurrection with equal timestamp + hash change: Condition #2
            -- - Resurrection with equal timestamp + same hash: CORRECTLY REJECTED (no change)
            -- This prevents stale "confirmed" webhooks from incorrectly resurrecting deleted events.

        RETURNING id, version, start_time, is_focus_block
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

        # Fetch the result from RETURNING clause
        # CRITICAL: Do NOT rely on result.rowcount with PostgreSQL async - it's unreliable
        # Instead, check if RETURNING gave us a row
        row = result.fetchone()

        if not row:
            # This should rarely happen since we pre-check with should_accept_update()
            # But SQL WHERE clause can still reject (e.g., race condition)
            logger.warning(
                "focused.sync.sql_rejected",
                extra={
                    "user_id": str(user_id),
                    "event_id": google_event_id,
                    "calendar_id": google_calendar_id,
                    "event_summary": event_summary,
                    "google_updated_at": google_updated_at.isoformat(),
                    "google_hash": sha256_content_hash
                }
            )
            return "skipped"

        # Unpack RETURNING values: id, version, start_time, is_focus_block
        session_id, version, db_start_time, db_is_focus_block = row

        # Determine operation type from version
        if version == 1:
            # New insert (version starts at 1)
            logger.info(
                "focused.sync.event.inserted",
                extra={
                    "user_id": str(user_id),
                    "event_id": google_event_id,
                    "calendar_id": google_calendar_id,
                    "event_summary": event_summary,
                    "version": version,
                    "reason": "new_event",
                    "google_hash": sha256_content_hash
                }
            )
            operation = "inserted"
        else:
            # Update (version > 1)
            # Reason already logged in conflict.accepted above
            logger.info(
                "focused.sync.event.updated",
                extra={
                    "user_id": str(user_id),
                    "event_id": google_event_id,
                    "calendar_id": google_calendar_id,
                    "event_summary": event_summary,
                    "new_version": version,
                    "reason": conflict_reason if conflict_reason else "unknown",
                    "google_hash": sha256_content_hash,
                    "local_hash": local_event_data["sha256_content_hash"] if local_event_data else None
                }
            )
            operation = "updated"

        # =========================================================================
        # Increment 20: Schedule focus activation for new/updated focus blocks
        # =========================================================================
        if db_is_focus_block and db_start_time:
            from backend.apps.focused.logic.sync.activation_scheduler import (
                schedule_focus_activation,
                reschedule_activation,
            )

            user_uuid = UUID(user_id)

            if operation == "inserted":
                # New focus block: schedule activation
                await schedule_focus_activation(
                    user_id=user_uuid,
                    session_id=session_id,
                    event_start_time=db_start_time,
                    db=session,
                )
            elif operation == "updated":
                # Updated focus block: reschedule (handles time changes)
                # This cancels any existing job and creates a new one
                await reschedule_activation(
                    user_id=user_uuid,
                    session_id=session_id,
                    new_event_start_time=db_start_time,
                    db=session,
                )

        return operation

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


async def _process_cancelled_event(
    user_id: str,
    event: dict[str, Any],
    google_event_id: str,
    google_calendar_id: str,
    session: AsyncSession
) -> str:
    """
    Process an explicitly cancelled event (status='cancelled').

    Args:
        user_id: User ID (UUID as string)
        event: Google Calendar event
        google_event_id: Google event ID
        google_calendar_id: Google calendar ID
        session: Database session

    Returns:
        "deleted" or "skipped"
    """
    # Extract summary for logging
    event_summary = event.get("summary")

    # Parse deletion timestamp
    try:
        google_updated_at = datetime.fromisoformat(
            event["updated"].replace("Z", "+00:00")
        )
    except (ValueError, KeyError) as e:
        logger.warning(f"[sync] Invalid timestamp in cancelled event {google_event_id}: {e}")
        return "skipped"

    # Query local event for conflict detection
    # Increment 20: Also get id for cancellation of scheduled jobs
    query_stmt = text("""
        SELECT id, google_updated_at, version
        FROM focused_focus_sessions
        WHERE user_id = :user_id
          AND google_event_id = :google_event_id
          AND google_calendar_id = :google_calendar_id
          AND status = 'active'
    """)

    try:
        result = await session.execute(
            query_stmt,
            {
                "user_id": UUID(user_id),
                "google_event_id": google_event_id,
                "google_calendar_id": google_calendar_id
            }
        )
        local_row = result.fetchone()

        if not local_row:
            logger.debug(f"[sync] Cancelled event {google_event_id} not found or already deleted - skipping")
            return "skipped"

        # Unpack: id, google_updated_at, version
        session_id = local_row[0]
        local_updated_at = local_row[1]
        old_version = local_row[2]

        # Mock local event for conflict detection
        class LocalEvent:
            def __init__(self, updated_at):
                self.google_updated_at = updated_at

        local_event = LocalEvent(local_updated_at)

        # Apply deletion conflict logic
        should_delete, reason = should_accept_deletion(
            local_event,
            google_updated_at=google_updated_at,
            missing_in_sync=False
        )

        if not should_delete:
            logger.info(
                "focused.sync.deletion.rejected",
                extra={
                    "user_id": str(user_id),
                    "event_id": google_event_id,
                    "calendar_id": google_calendar_id,
                    "event_summary": event_summary,
                    "reason": reason,
                    "google_updated_at": google_updated_at.isoformat(),
                    "local_updated_at": local_updated_at.isoformat()
                }
            )
            return "skipped"

        # Accept deletion - soft delete with version increment
        logger.info(
            "focused.sync.deletion.accepted",
            extra={
                "user_id": str(user_id),
                "event_id": google_event_id,
                "calendar_id": google_calendar_id,
                "event_summary": event_summary,
                "reason": reason,
                "google_updated_at": google_updated_at.isoformat(),
                "local_updated_at": local_updated_at.isoformat()
            }
        )

        # =========================================================================
        # Increment 20: Cancel any pending activation job for this event
        # =========================================================================
        from backend.apps.focused.logic.sync.activation_scheduler import (
            cancel_scheduled_activation,
        )

        await cancel_scheduled_activation(
            user_id=UUID(user_id),
            session_id=session_id,
            db=session,
            reason="event_deleted",
        )

        delete_stmt = text("""
            UPDATE focused_focus_sessions
            SET status = 'deleted',
                deleted_at = NOW(),
                updated_at = NOW(),
                version = :new_version
            WHERE user_id = :user_id
              AND google_event_id = :google_event_id
              AND google_calendar_id = :google_calendar_id
        """)

        await session.execute(
            delete_stmt,
            {
                "user_id": UUID(user_id),
                "google_event_id": google_event_id,
                "google_calendar_id": google_calendar_id,
                "new_version": old_version + 1
            }
        )

        logger.info(
            "focused.sync.event.deleted",
            extra={
                "user_id": str(user_id),
                "event_id": google_event_id,
                "calendar_id": google_calendar_id,
                "event_summary": event_summary,
                "new_version": old_version + 1,
                "reason": reason
            }
        )

        return "deleted"

    except Exception as e:
        logger.error(f"[sync] Error processing cancelled event {google_event_id}: {e}")
        return "skipped"
