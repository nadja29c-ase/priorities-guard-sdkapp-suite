"""
Increment 6D: Sync Conflict Detection Tests

Tests timestamp-based conflict detection to prevent data corruption from:
- Out-of-order webhook delivery
- Stale Google API responses
- Deletions vs updates applied in wrong order
- Stale resurrection attempts

Test Coverage:
- Conflict detection logic (5 tests)
- Deletion handling (2 tests)
- Out-of-order webhooks (1 test)
- Description cleanup integration (1 test)
- Conflict logic helpers (1 test)
- Resurrection logic with timestamp checks (4 tests) - BUG 3 fix
- Explicit cancellation integration (3 tests) - status='cancelled' path
- 6C cleanup edge case (1 test)
"""

import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.focused.logic.sync.single_event import process_single_event
from backend.apps.focused.logic.sync.cleanup import detect_deleted_events
from backend.apps.focused.logic.sync.sync_conflicts import should_accept_update, should_accept_deletion
from backend.apps.focused.db_models import FocusedFocusSession


# =============================================================================
# Helper: Create test user
# =============================================================================
async def create_test_user_and_connection(session: AsyncSession, user_id: str = None):
    """Create a test user and Google connection."""
    if user_id is None:
        user_id = str(uuid4())

    # Create user
    await session.execute(
        text("INSERT INTO core_users (id) VALUES (:id)"),
        {"id": user_id}
    )

    # Create Google connection
    await session.execute(
        text("""
            INSERT INTO core_connections (
                user_id, provider, encrypted_access_token, encrypted_refresh_token,
                token_expires_at, scopes
            ) VALUES (
                :user_id, 'google', 'encrypted_token', 'encrypted_refresh',
                :expires, ARRAY['calendar.readonly']::text[]
            )
        """),
        {
            "user_id": user_id,
            "expires": datetime.now(timezone.utc) + timedelta(hours=1)
        }
    )

    await session.flush()
    return user_id


# =============================================================================
# Conflict Detection Tests (5 tests)
# =============================================================================

@pytest.mark.asyncio
async def test_conflict_detection_new_event(async_session: AsyncSession):
    """
    Test 1: New event → version=1
    - No local event exists
    - Google event inserted with version=1
    """
    user_id = await create_test_user_and_connection(async_session)
    now = datetime.now(timezone.utc)

    google_event = {
        "id": "new_event",
        "iCalUID": "new@google.com",
        "summary": "New Event",
        "description": "Description",
        "updated": now.isoformat().replace("+00:00", "Z"),
        "start": {"dateTime": now.isoformat().replace("+00:00", "Z")},
        "end": {"dateTime": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")}
    }

    result = await process_single_event(
        user_id=str(user_id),
        event=google_event,
        keywords=["focus"],
        session=async_session
    )

    assert result == "inserted"

    # Verify version=1
    await async_session.flush()
    async_session.expire_all()

    stmt = select(FocusedFocusSession).where(
        FocusedFocusSession.user_id == user_id,
        FocusedFocusSession.google_event_id == "new_event"
    )
    db_result = await async_session.execute(stmt)
    event = db_result.scalar_one()

    assert event.version == 1


@pytest.mark.asyncio
async def test_conflict_detection_google_newer(async_session: AsyncSession):
    """
    Test 2: Google newer → update accepted, version+=1
    - Local event exists with older timestamp
    - Google event has newer timestamp
    - Update accepted, version increments
    """
    user_id = await create_test_user_and_connection(async_session)
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(hours=1)

    # Create existing event with old timestamp
    from backend.apps.focused.utils.hash import calculate_content_hash

    old_hash = calculate_content_hash(
        google_event_id="event1",
        event_summary="Old Title",
        event_description="Old desc",
        start_time=now,
        end_time=now + timedelta(hours=1)
    )

    existing = FocusedFocusSession(
        user_id=user_id,
        google_event_id="event1",
        google_calendar_id="primary",
        google_ical_uid="event1@google.com",
        google_updated_at=old_time,  # Old timestamp
        event_summary="Old Title",
        event_description="Old desc",
        start_time=now,
        end_time=now + timedelta(hours=1),
        sha256_content_hash=old_hash,
        status="active",
        version=1
    )
    async_session.add(existing)
    await async_session.flush()

    # Google event with newer timestamp
    google_event = {
        "id": "event1",
        "iCalUID": "event1@google.com",
        "summary": "New Title",
        "description": "New desc",
        "updated": now.isoformat().replace("+00:00", "Z"),  # Newer
        "start": {"dateTime": now.isoformat().replace("+00:00", "Z")},
        "end": {"dateTime": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")}
    }

    result = await process_single_event(
        user_id=str(user_id),
        event=google_event,
        keywords=["focus"],
        session=async_session
    )

    assert result == "updated"

    # Verify version incremented
    await async_session.flush()
    async_session.expire_all()

    stmt = select(FocusedFocusSession).where(
        FocusedFocusSession.user_id == user_id,
        FocusedFocusSession.google_event_id == "event1"
    )
    db_result = await async_session.execute(stmt)
    event = db_result.scalar_one()

    assert event.version == 2
    assert event.event_summary == "New Title"


@pytest.mark.asyncio
async def test_conflict_detection_google_stale(async_session: AsyncSession):
    """
    Test 3: Google stale → update skipped, version unchanged
    - Local event exists with newer timestamp
    - Google event has older timestamp
    - Update rejected (stale)
    """
    user_id = await create_test_user_and_connection(async_session)
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(hours=1)

    from backend.apps.focused.utils.hash import calculate_content_hash

    current_hash = calculate_content_hash(
        google_event_id="event1",
        event_summary="Current Title",
        event_description="Current desc",
        start_time=now,
        end_time=now + timedelta(hours=1)
    )

    # Create existing event with NEWER timestamp
    existing = FocusedFocusSession(
        user_id=user_id,
        google_event_id="event1",
        google_calendar_id="primary",
        google_ical_uid="event1@google.com",
        google_updated_at=now,  # Newer (local is fresher)
        event_summary="Current Title",
        event_description="Current desc",
        start_time=now,
        end_time=now + timedelta(hours=1),
        sha256_content_hash=current_hash,
        status="active",
        version=5
    )
    async_session.add(existing)
    await async_session.flush()

    # Stale Google event with OLDER timestamp
    google_event = {
        "id": "event1",
        "iCalUID": "event1@google.com",
        "summary": "Stale Title",
        "description": "Stale desc",
        "updated": old_time.isoformat().replace("+00:00", "Z"),  # Older (stale)
        "start": {"dateTime": now.isoformat().replace("+00:00", "Z")},
        "end": {"dateTime": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")}
    }

    result = await process_single_event(
        user_id=str(user_id),
        event=google_event,
        keywords=["focus"],
        session=async_session
    )

    assert result == "skipped"

    # Verify version unchanged, data unchanged
    await async_session.flush()
    async_session.expire_all()

    stmt = select(FocusedFocusSession).where(
        FocusedFocusSession.user_id == user_id,
        FocusedFocusSession.google_event_id == "event1"
    )
    db_result = await async_session.execute(stmt)
    event = db_result.scalar_one()

    assert event.version == 5  # Unchanged
    assert event.event_summary == "Current Title"  # Not overwritten


@pytest.mark.asyncio
async def test_conflict_detection_equal_timestamps_hash_changed(async_session: AsyncSession):
    """
    Test 4: Timestamps equal, hash changed → update accepted, version+=1
    - Local and Google have same timestamp
    - Content differs (hash mismatch)
    - Update accepted (Google is source of truth)
    """
    user_id = await create_test_user_and_connection(async_session)
    now = datetime.now(timezone.utc)

    from backend.apps.focused.utils.hash import calculate_content_hash

    old_hash = calculate_content_hash(
        google_event_id="event1",
        event_summary="Title V1",
        event_description="Desc V1",
        start_time=now,
        end_time=now + timedelta(hours=1)
    )

    # Create existing event
    existing = FocusedFocusSession(
        user_id=user_id,
        google_event_id="event1",
        google_calendar_id="primary",
        google_ical_uid="event1@google.com",
        google_updated_at=now,  # Same timestamp
        event_summary="Title V1",
        event_description="Desc V1",
        start_time=now,
        end_time=now + timedelta(hours=1),
        sha256_content_hash=old_hash,
        status="active",
        version=3
    )
    async_session.add(existing)
    await async_session.flush()

    # Google event with SAME timestamp but DIFFERENT content
    google_event = {
        "id": "event1",
        "iCalUID": "event1@google.com",
        "summary": "Title V2",  # Changed
        "description": "Desc V2",  # Changed
        "updated": now.isoformat().replace("+00:00", "Z"),  # Same timestamp
        "start": {"dateTime": now.isoformat().replace("+00:00", "Z")},
        "end": {"dateTime": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")}
    }

    result = await process_single_event(
        user_id=str(user_id),
        event=google_event,
        keywords=["focus"],
        session=async_session
    )

    assert result == "updated"

    # Verify version incremented
    await async_session.flush()
    async_session.expire_all()

    stmt = select(FocusedFocusSession).where(
        FocusedFocusSession.user_id == user_id,
        FocusedFocusSession.google_event_id == "event1"
    )
    db_result = await async_session.execute(stmt)
    event = db_result.scalar_one()

    assert event.version == 4
    assert event.event_summary == "Title V2"


@pytest.mark.asyncio
async def test_conflict_detection_equal_timestamps_no_change(async_session: AsyncSession):
    """
    Test 5: Timestamps equal, hash same → no update, version unchanged
    - Local and Google have same timestamp
    - Content identical (hash match)
    - Update skipped (no change)
    """
    user_id = await create_test_user_and_connection(async_session)
    now = datetime.now(timezone.utc)

    from backend.apps.focused.utils.hash import calculate_content_hash

    same_hash = calculate_content_hash(
        google_event_id="event1",
        event_summary="Same Title",
        event_description="Same Desc",
        start_time=now,
        end_time=now + timedelta(hours=1)
    )

    # Create existing event
    existing = FocusedFocusSession(
        user_id=user_id,
        google_event_id="event1",
        google_calendar_id="primary",
        google_ical_uid="event1@google.com",
        google_updated_at=now,
        event_summary="Same Title",
        event_description="Same Desc",
        start_time=now,
        end_time=now + timedelta(hours=1),
        sha256_content_hash=same_hash,
        status="active",
        version=7
    )
    async_session.add(existing)
    await async_session.flush()

    # Google event with same timestamp and same content
    google_event = {
        "id": "event1",
        "iCalUID": "event1@google.com",
        "summary": "Same Title",
        "description": "Same Desc",
        "updated": now.isoformat().replace("+00:00", "Z"),
        "start": {"dateTime": now.isoformat().replace("+00:00", "Z")},
        "end": {"dateTime": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")}
    }

    result = await process_single_event(
        user_id=str(user_id),
        event=google_event,
        keywords=["focus"],
        session=async_session
    )

    assert result == "skipped"

    # Verify version unchanged
    await async_session.flush()
    async_session.expire_all()

    stmt = select(FocusedFocusSession).where(
        FocusedFocusSession.user_id == user_id,
        FocusedFocusSession.google_event_id == "event1"
    )
    db_result = await async_session.execute(stmt)
    event = db_result.scalar_one()

    assert event.version == 7  # Unchanged


# =============================================================================
# Deletion Tests (4 tests)
# =============================================================================

@pytest.mark.asyncio
async def test_deletion_google_newer(async_session: AsyncSession):
    """
    Test 6: Google deletion newer → soft delete, version+=1
    - Event exists with older timestamp
    - Google signals deletion (missing from sync)
    - Soft delete accepted, version increments
    """
    user_id = await create_test_user_and_connection(async_session)
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(hours=1)

    from backend.apps.focused.utils.hash import calculate_content_hash

    event_hash = calculate_content_hash(
        google_event_id="event1",
        event_summary="To Delete",
        event_description="",
        start_time=now,
        end_time=now + timedelta(hours=1)
    )

    # Create event with old timestamp
    existing = FocusedFocusSession(
        user_id=user_id,
        google_event_id="event1",
        google_calendar_id="primary",
        google_ical_uid="event1@google.com",
        google_updated_at=old_time,
        event_summary="To Delete",
        start_time=now,
        end_time=now + timedelta(hours=1),
        sha256_content_hash=event_hash,
        status="active",
        version=2
    )
    async_session.add(existing)
    await async_session.flush()

    # Sync returns empty list (event deleted)
    deleted_count = await detect_deleted_events(
        user_id=str(user_id),
        fetched_event_ids=[],  # Event missing
        session=async_session
    )

    assert deleted_count == 1

    # Verify soft delete and version increment
    await async_session.flush()
    async_session.expire_all()

    stmt = select(FocusedFocusSession).where(
        FocusedFocusSession.user_id == user_id,
        FocusedFocusSession.google_event_id == "event1"
    )
    db_result = await async_session.execute(stmt)
    event = db_result.scalar_one()

    assert event.status == "deleted"
    assert event.deleted_at is not None
    assert event.version == 3


@pytest.mark.asyncio
async def test_deletion_logic_helper():
    """
    Test 7: Deletion logic helper - should_accept_deletion()
    - Test the logic helper function directly
    """
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(hours=1)

    # Mock local event
    from backend.apps.focused.db_models import FocusedFocusSession
    local_event = FocusedFocusSession(
        google_updated_at=old_time,
        version=5
    )

    # Newer deletion should be accepted
    should_delete, reason = should_accept_deletion(local_event, now)
    assert should_delete is True
    assert reason == "google_deletion_newer"

    # Older deletion should be rejected
    should_delete, reason = should_accept_deletion(local_event, old_time - timedelta(hours=1))
    assert should_delete is False
    assert reason == "stale_deletion"

    # No local event
    should_delete, reason = should_accept_deletion(None, now)
    assert should_delete is False
    assert reason == "no_local_event"

    # Missing from sync (unconditional accept, bypasses timestamp check)
    should_delete, reason = should_accept_deletion(local_event, missing_in_sync=True)
    assert should_delete is True
    assert reason == "missing_in_sync"

    # Missing from sync with stale timestamp (still accepts - list is source of truth)
    should_delete, reason = should_accept_deletion(
        local_event,
        google_updated_at=old_time - timedelta(hours=2),
        missing_in_sync=True
    )
    assert should_delete is True
    assert reason == "missing_in_sync"

    # Invalid call: No timestamp and not marked as missing_in_sync (defensive check)
    should_delete, reason = should_accept_deletion(
        local_event,
        google_updated_at=None,
        missing_in_sync=False
    )
    assert should_delete is False
    assert reason == "invalid_deletion_call"


# =============================================================================
# Out-of-Order Webhook Tests (4 tests)
# =============================================================================

@pytest.mark.asyncio
async def test_out_of_order_webhook_newer_then_older(async_session: AsyncSession):
    """
    Test 10-13: Out-of-order webhooks
    - Webhook A (v102, newer) arrives first → accepted
    - Webhook B (v101, older) arrives second → rejected (stale)
    - Version stays at 102 state
    """
    user_id = await create_test_user_and_connection(async_session)
    now = datetime.now(timezone.utc)

    time_v101 = now - timedelta(minutes=10)
    time_v102 = now

    # Webhook A arrives (v102 - newer)
    google_event_v102 = {
        "id": "event1",
        "iCalUID": "event1@google.com",
        "summary": "Version 102",
        "description": "Newer version",
        "updated": time_v102.isoformat().replace("+00:00", "Z"),
        "start": {"dateTime": now.isoformat().replace("+00:00", "Z")},
        "end": {"dateTime": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")}
    }

    result_a = await process_single_event(
        user_id=str(user_id),
        event=google_event_v102,
        keywords=["focus"],
        session=async_session
    )

    assert result_a == "inserted"

    await async_session.flush()
    async_session.expire_all()

    # Verify v102 inserted
    stmt = select(FocusedFocusSession).where(
        FocusedFocusSession.user_id == user_id,
        FocusedFocusSession.google_event_id == "event1"
    )
    db_result = await async_session.execute(stmt)
    event = db_result.scalar_one()

    assert event.version == 1
    assert event.event_summary == "Version 102"
    version_after_102 = event.version

    # Webhook B arrives late (v101 - older)
    google_event_v101 = {
        "id": "event1",
        "iCalUID": "event1@google.com",
        "summary": "Version 101",
        "description": "Older version (should be rejected)",
        "updated": time_v101.isoformat().replace("+00:00", "Z"),  # Older!
        "start": {"dateTime": now.isoformat().replace("+00:00", "Z")},
        "end": {"dateTime": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")}
    }

    result_b = await process_single_event(
        user_id=str(user_id),
        event=google_event_v101,
        keywords=["focus"],
        session=async_session
    )

    assert result_b == "skipped"  # Rejected (stale)

    await async_session.flush()
    async_session.expire_all()

    # Verify state unchanged (still v102)
    stmt = select(FocusedFocusSession).where(
        FocusedFocusSession.user_id == user_id,
        FocusedFocusSession.google_event_id == "event1"
    )
    db_result = await async_session.execute(stmt)
    event = db_result.scalar_one()

    assert event.version == version_after_102  # Unchanged
    assert event.event_summary == "Version 102"  # Not overwritten


# =============================================================================
# Description Cleanup Integration (6 tests)
# =============================================================================

@pytest.mark.asyncio
async def test_description_cleanup_integration_sync_with_null_description(async_session: AsyncSession):
    """
    Test 14-19: Description cleanup integration
    - Event synced with description
    - Description cleaned (NULL) after 72h
    - Google changes description
    - Verify: update accepted (timestamp check)
    - Verify: new description persists
    - Verify: version increments
    """
    user_id = await create_test_user_and_connection(async_session)
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(hours=80)

    from backend.apps.focused.utils.hash import calculate_content_hash

    # Original hash (with description)
    original_hash = calculate_content_hash(
        google_event_id="event1",
        event_summary="Title",
        event_description="Original description",
        start_time=now,
        end_time=now + timedelta(hours=1)
    )

    # Capture old timestamp for comparison later
    old_updated_at = now - timedelta(hours=80)

    # Create event with NULL description (cleaned up)
    existing = FocusedFocusSession(
        user_id=user_id,
        google_event_id="event1",
        google_calendar_id="primary",
        google_ical_uid="event1@google.com",
        google_updated_at=old_time,
        event_summary="Title",
        event_description=None,  # Cleaned up
        start_time=now,
        end_time=now + timedelta(hours=1),
        sha256_content_hash=original_hash,  # Hash included original description
        status="active",
        version=10,
        updated_at=old_updated_at
    )
    async_session.add(existing)
    await async_session.flush()

    # Google event with changed description
    google_event = {
        "id": "event1",
        "iCalUID": "event1@google.com",
        "summary": "Title",
        "description": "New description",  # Changed
        "updated": now.isoformat().replace("+00:00", "Z"),  # Newer timestamp
        "start": {"dateTime": now.isoformat().replace("+00:00", "Z")},
        "end": {"dateTime": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")}
    }

    result = await process_single_event(
        user_id=str(user_id),
        event=google_event,
        keywords=["focus"],
        session=async_session
    )

    assert result == "updated"

    # Verify update accepted, description restored, version incremented
    await async_session.flush()
    async_session.expire_all()

    stmt = select(FocusedFocusSession).where(
        FocusedFocusSession.user_id == user_id,
        FocusedFocusSession.google_event_id == "event1"
    )
    db_result = await async_session.execute(stmt)
    event = db_result.scalar_one()

    assert event.event_description == "New description"  # Restored
    assert event.version == 11  # Incremented
    assert event.updated_at > old_updated_at  # Fresh timestamp (compare against captured value)


@pytest.mark.asyncio
async def test_conflict_logic_helper():
    """
    Test: Conflict detection helper - should_accept_update()
    - Test the logic helper function directly
    """
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(hours=1)

    # Test 1: New event
    should_update, reason = should_accept_update(None, now, "hash123")
    assert should_update is True
    assert reason == "new_event"

    # Test 2: Google newer
    from backend.apps.focused.db_models import FocusedFocusSession
    local = FocusedFocusSession(
        google_updated_at=old_time,
        sha256_content_hash="old_hash"
    )
    should_update, reason = should_accept_update(local, now, "new_hash")
    assert should_update is True
    assert reason == "google_newer"

    # Test 3: Google stale
    should_update, reason = should_accept_update(local, old_time - timedelta(hours=1), "new_hash")
    assert should_update is False
    assert reason == "stale_google"

    # Test 4: Equal timestamps, hash changed
    should_update, reason = should_accept_update(local, old_time, "different_hash")
    assert should_update is True
    assert reason == "hash_changed"

    # Test 5: Equal timestamps, hash same
    should_update, reason = should_accept_update(local, old_time, "old_hash")
    assert should_update is False
    assert reason == "no_change"


# =============================================================================
# Resurrection Tests (Increment 6D Bug 3 Fix)
# =============================================================================

@pytest.mark.asyncio
async def test_stale_resurrection_rejected(async_session: AsyncSession):
    """
    Test: Stale resurrection rejected
    - Event deleted at 10:50 (version=8, google_updated_at=10:50)
    - Old "confirmed" webhook arrives with 10:40 timestamp
    - Resurrection REJECTED (stale timestamp)
    - Event remains deleted
    - Version unchanged

    This tests BUG 3 fix: Resurrection must respect timestamp-first rule.
    """
    user_id = await create_test_user_and_connection(async_session)
    now = datetime.now(timezone.utc)

    deletion_time = now  # 10:50
    old_webhook_time = now - timedelta(minutes=10)  # 10:40 (stale)

    from backend.apps.focused.utils.hash import calculate_content_hash

    event_hash = calculate_content_hash(
        google_event_id="event1",
        event_summary="Deleted Event",
        event_description="Should stay deleted",
        start_time=now,
        end_time=now + timedelta(hours=1)
    )

    # Create DELETED event with newer timestamp
    existing = FocusedFocusSession(
        user_id=user_id,
        google_event_id="event1",
        google_calendar_id="primary",
        google_ical_uid="event1@google.com",
        google_updated_at=deletion_time,  # 10:50 (newer)
        event_summary="Deleted Event",
        event_description="Should stay deleted",
        start_time=now,
        end_time=now + timedelta(hours=1),
        sha256_content_hash=event_hash,
        status="deleted",  # Already deleted
        deleted_at=deletion_time,
        version=8
    )
    async_session.add(existing)
    await async_session.flush()

    # Old "confirmed" webhook arrives with STALE timestamp
    google_event_stale = {
        "id": "event1",
        "iCalUID": "event1@google.com",
        "summary": "Deleted Event",
        "description": "Should stay deleted",
        "status": "confirmed",  # Trying to resurrect
        "updated": old_webhook_time.isoformat().replace("+00:00", "Z"),  # 10:40 (STALE)
        "start": {"dateTime": now.isoformat().replace("+00:00", "Z")},
        "end": {"dateTime": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")}
    }

    result = await process_single_event(
        user_id=str(user_id),
        event=google_event_stale,
        keywords=["focus"],
        session=async_session
    )

    # CRITICAL: Stale resurrection must be rejected
    assert result == "skipped"

    # Verify event remains deleted, version unchanged
    await async_session.flush()
    async_session.expire_all()

    stmt = select(FocusedFocusSession).where(
        FocusedFocusSession.user_id == user_id,
        FocusedFocusSession.google_event_id == "event1"
    )
    db_result = await async_session.execute(stmt)
    event = db_result.scalar_one()

    assert event.status == "deleted"  # Still deleted
    assert event.version == 8  # Unchanged
    assert event.deleted_at == deletion_time  # Unchanged


@pytest.mark.asyncio
async def test_valid_resurrection_with_newer_timestamp(async_session: AsyncSession):
    """
    Test: Valid resurrection with newer timestamp
    - Event deleted at 10:40 (version=5, google_updated_at=10:40)
    - Google restores event at 10:50 (newer timestamp)
    - Resurrection ACCEPTED
    - Event restored to active
    - Version incremented
    """
    user_id = await create_test_user_and_connection(async_session)
    now = datetime.now(timezone.utc)

    deletion_time = now - timedelta(minutes=10)  # 10:40
    restoration_time = now  # 10:50 (newer)

    from backend.apps.focused.utils.hash import calculate_content_hash

    event_hash = calculate_content_hash(
        google_event_id="event1",
        event_summary="Restored Event",
        event_description="Will be restored",
        start_time=now,
        end_time=now + timedelta(hours=1)
    )

    # Create DELETED event with older timestamp
    existing = FocusedFocusSession(
        user_id=user_id,
        google_event_id="event1",
        google_calendar_id="primary",
        google_ical_uid="event1@google.com",
        google_updated_at=deletion_time,  # 10:40 (older)
        event_summary="Restored Event",
        event_description="Will be restored",
        start_time=now,
        end_time=now + timedelta(hours=1),
        sha256_content_hash=event_hash,
        status="deleted",  # Deleted
        deleted_at=deletion_time,
        version=5
    )
    async_session.add(existing)
    await async_session.flush()

    # Google restores event with NEWER timestamp
    google_event_restored = {
        "id": "event1",
        "iCalUID": "event1@google.com",
        "summary": "Restored Event",
        "description": "Will be restored",
        "status": "confirmed",  # Restored
        "updated": restoration_time.isoformat().replace("+00:00", "Z"),  # 10:50 (NEWER)
        "start": {"dateTime": now.isoformat().replace("+00:00", "Z")},
        "end": {"dateTime": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")}
    }

    result = await process_single_event(
        user_id=str(user_id),
        event=google_event_restored,
        keywords=["focus"],
        session=async_session
    )

    # Resurrection accepted
    assert result == "updated"

    # Verify event restored to active, version incremented
    await async_session.flush()
    async_session.expire_all()

    stmt = select(FocusedFocusSession).where(
        FocusedFocusSession.user_id == user_id,
        FocusedFocusSession.google_event_id == "event1"
    )
    db_result = await async_session.execute(stmt)
    event = db_result.scalar_one()

    assert event.status == "active"  # Restored
    assert event.version == 6  # Incremented
    assert event.deleted_at is None  # Cleared


@pytest.mark.asyncio
async def test_valid_resurrection_equal_timestamp_hash_changed(async_session: AsyncSession):
    """
    Test: Valid resurrection with equal timestamp but hash changed
    - Event deleted at 10:40 (version=3, hash=ABC)
    - Google restores event at 10:40 (same timestamp, hash=DEF)
    - Resurrection ACCEPTED (hash differs)
    - Event restored to active
    - Version incremented

    This handles rare case where Google restoration doesn't bump timestamp
    but content changed (detected via hash).
    """
    user_id = await create_test_user_and_connection(async_session)
    now = datetime.now(timezone.utc)

    from backend.apps.focused.utils.hash import calculate_content_hash

    # Old hash (deleted version)
    old_hash = calculate_content_hash(
        google_event_id="event1",
        event_summary="Event Title",
        event_description="Old description",
        start_time=now,
        end_time=now + timedelta(hours=1)
    )

    # Create DELETED event
    existing = FocusedFocusSession(
        user_id=user_id,
        google_event_id="event1",
        google_calendar_id="primary",
        google_ical_uid="event1@google.com",
        google_updated_at=now,  # Same timestamp
        event_summary="Event Title",
        event_description="Old description",
        start_time=now,
        end_time=now + timedelta(hours=1),
        sha256_content_hash=old_hash,
        status="deleted",  # Deleted
        deleted_at=now,
        version=3
    )
    async_session.add(existing)
    await async_session.flush()

    # Google restores event with SAME timestamp but DIFFERENT content
    google_event_restored = {
        "id": "event1",
        "iCalUID": "event1@google.com",
        "summary": "Event Title",
        "description": "New description",  # Changed (hash will differ)
        "status": "confirmed",  # Restored
        "updated": now.isoformat().replace("+00:00", "Z"),  # Same timestamp
        "start": {"dateTime": now.isoformat().replace("+00:00", "Z")},
        "end": {"dateTime": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")}
    }

    result = await process_single_event(
        user_id=str(user_id),
        event=google_event_restored,
        keywords=["focus"],
        session=async_session
    )

    # Resurrection accepted (hash differs)
    assert result == "updated"

    # Verify event restored, version incremented
    await async_session.flush()
    async_session.expire_all()

    stmt = select(FocusedFocusSession).where(
        FocusedFocusSession.user_id == user_id,
        FocusedFocusSession.google_event_id == "event1"
    )
    db_result = await async_session.execute(stmt)
    event = db_result.scalar_one()

    assert event.status == "active"  # Restored
    assert event.version == 4  # Incremented
    assert event.deleted_at is None  # Cleared
    assert event.event_description == "New description"  # Updated


@pytest.mark.asyncio
async def test_resurrection_logic_helper_with_deleted_status():
    """
    Test: Resurrection in logic helper - should_accept_update()
    - Test resurrection scenarios in the helper function directly
    """
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(hours=1)

    from backend.apps.focused.db_models import FocusedFocusSession

    # Test 1: Resurrection with newer timestamp → accepted
    local_deleted = FocusedFocusSession(
        google_updated_at=old_time,
        sha256_content_hash="hash123",
        status="deleted"
    )
    should_update, reason = should_accept_update(local_deleted, now, "hash123")
    assert should_update is True
    assert reason == "resurrection"

    # Test 2: Stale resurrection (older timestamp) → rejected
    should_update, reason = should_accept_update(
        local_deleted,
        old_time - timedelta(hours=1),  # Even older
        "hash123"
    )
    assert should_update is False
    assert reason == "stale_google"

    # Test 3: Resurrection with equal timestamp and hash change → accepted
    should_update, reason = should_accept_update(
        local_deleted,
        old_time,  # Same timestamp
        "different_hash"  # Hash differs
    )
    assert should_update is True
    assert reason == "resurrection"

    # Test 4: Resurrection with equal timestamp and same hash → rejected
    should_update, reason = should_accept_update(
        local_deleted,
        old_time,  # Same timestamp
        "hash123"  # Same hash
    )
    assert should_update is False
    assert reason == "no_change"


# =============================================================================
# Explicit Cancellation Integration Tests (status='cancelled' path)
# =============================================================================

@pytest.mark.asyncio
async def test_explicit_cancellation_with_newer_timestamp(async_session: AsyncSession):
    """
    Test: Explicit cancellation with newer timestamp
    - Local: status='active', google_updated_at=10:40, version=3
    - Incoming: status='cancelled', updated=10:50 (newer)
    - Expect: Deletion accepted
    - Result: status='deleted', version=4, deleted_at set

    This tests the explicit cancellation branch in process_single_event():
        if google_status == "cancelled":
            ...
            should_delete, reason = should_accept_deletion(
                local_event, google_updated_at=..., missing_in_sync=False
            )
    """
    user_id = await create_test_user_and_connection(async_session)
    now = datetime.now(timezone.utc)

    old_time = now - timedelta(minutes=10)  # 10:40
    cancellation_time = now  # 10:50 (newer)

    from backend.apps.focused.utils.hash import calculate_content_hash

    event_hash = calculate_content_hash(
        google_event_id="event1",
        event_summary="Event to Cancel",
        event_description="Will be cancelled",
        start_time=now,
        end_time=now + timedelta(hours=1)
    )

    # Create active event with older timestamp
    existing = FocusedFocusSession(
        user_id=user_id,
        google_event_id="event1",
        google_calendar_id="primary",
        google_ical_uid="event1@google.com",
        google_updated_at=old_time,  # 10:40
        event_summary="Event to Cancel",
        event_description="Will be cancelled",
        start_time=now,
        end_time=now + timedelta(hours=1),
        sha256_content_hash=event_hash,
        status="active",
        version=3
    )
    async_session.add(existing)
    await async_session.flush()

    # Google sends explicit cancellation with newer timestamp
    google_event_cancelled = {
        "id": "event1",
        "iCalUID": "event1@google.com",
        "summary": "Event to Cancel",
        "description": "Will be cancelled",
        "status": "cancelled",  # Explicit cancellation
        "updated": cancellation_time.isoformat().replace("+00:00", "Z"),  # 10:50 (NEWER)
        "start": {"dateTime": now.isoformat().replace("+00:00", "Z")},
        "end": {"dateTime": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")}
    }

    result = await process_single_event(
        user_id=str(user_id),
        event=google_event_cancelled,
        keywords=["focus"],
        session=async_session
    )

    # CRITICAL: Cancellation accepted
    assert result == "deleted"

    # Verify soft deletion and version increment
    await async_session.flush()
    async_session.expire_all()

    stmt = select(FocusedFocusSession).where(
        FocusedFocusSession.user_id == user_id,
        FocusedFocusSession.google_event_id == "event1"
    )
    db_result = await async_session.execute(stmt)
    event = db_result.scalar_one()

    assert event.status == "deleted"  # Soft deleted
    assert event.version == 4  # Incremented from 3
    assert event.deleted_at is not None  # Timestamp set


@pytest.mark.asyncio
async def test_explicit_cancellation_with_stale_timestamp(async_session: AsyncSession):
    """
    Test: Explicit cancellation with stale timestamp
    - Local: status='active', google_updated_at=10:50, version=5
    - Incoming: status='cancelled', updated=10:40 (older/stale)
    - Expect: Deletion rejected (stale signal)
    - Result: status='active', version=5 unchanged

    This prevents out-of-order cancellation webhooks from deleting
    events that have been updated more recently.
    """
    user_id = await create_test_user_and_connection(async_session)
    now = datetime.now(timezone.utc)

    recent_update = now  # 10:50
    stale_cancellation = now - timedelta(minutes=10)  # 10:40 (stale)

    from backend.apps.focused.utils.hash import calculate_content_hash

    event_hash = calculate_content_hash(
        google_event_id="event1",
        event_summary="Recent Event",
        event_description="Should not be deleted",
        start_time=now,
        end_time=now + timedelta(hours=1)
    )

    # Create active event with RECENT timestamp
    existing = FocusedFocusSession(
        user_id=user_id,
        google_event_id="event1",
        google_calendar_id="primary",
        google_ical_uid="event1@google.com",
        google_updated_at=recent_update,  # 10:50 (newer)
        event_summary="Recent Event",
        event_description="Should not be deleted",
        start_time=now,
        end_time=now + timedelta(hours=1),
        sha256_content_hash=event_hash,
        status="active",
        version=5
    )
    async_session.add(existing)
    await async_session.flush()

    # Google sends STALE cancellation (old webhook arriving late)
    google_event_cancelled = {
        "id": "event1",
        "iCalUID": "event1@google.com",
        "summary": "Recent Event",
        "description": "Should not be deleted",
        "status": "cancelled",  # Cancellation signal
        "updated": stale_cancellation.isoformat().replace("+00:00", "Z"),  # 10:40 (STALE)
        "start": {"dateTime": now.isoformat().replace("+00:00", "Z")},
        "end": {"dateTime": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")}
    }

    result = await process_single_event(
        user_id=str(user_id),
        event=google_event_cancelled,
        keywords=["focus"],
        session=async_session
    )

    # CRITICAL: Stale cancellation rejected
    assert result == "skipped"

    # Verify event remains active, version unchanged
    await async_session.flush()
    async_session.expire_all()

    stmt = select(FocusedFocusSession).where(
        FocusedFocusSession.user_id == user_id,
        FocusedFocusSession.google_event_id == "event1"
    )
    db_result = await async_session.execute(stmt)
    event = db_result.scalar_one()

    assert event.status == "active"  # Still active
    assert event.version == 5  # Unchanged
    assert event.deleted_at is None  # Not deleted


@pytest.mark.asyncio
async def test_explicit_cancellation_for_already_deleted_event(async_session: AsyncSession):
    """
    Test: Cancelled webhook for already-deleted event is a no-op
    - Local: status='deleted', google_updated_at=10:40, version=6
    - Incoming: status='cancelled', updated=10:50
    - Expect: Query filters by status='active', finds nothing
    - Result: Returns "skipped", no changes, version unchanged

    This tests the defensive filter in the cancellation query:
        WHERE ... AND status = 'active'

    Prevents double-deletion and spurious version bumps.
    """
    user_id = await create_test_user_and_connection(async_session)
    now = datetime.now(timezone.utc)

    deletion_time = now - timedelta(minutes=10)  # 10:40
    cancellation_time = now  # 10:50

    from backend.apps.focused.utils.hash import calculate_content_hash

    event_hash = calculate_content_hash(
        google_event_id="event1",
        event_summary="Already Deleted",
        event_description="",
        start_time=now,
        end_time=now + timedelta(hours=1)
    )

    # Create DELETED event
    existing = FocusedFocusSession(
        user_id=user_id,
        google_event_id="event1",
        google_calendar_id="primary",
        google_ical_uid="event1@google.com",
        google_updated_at=deletion_time,  # 10:40
        event_summary="Already Deleted",
        start_time=now,
        end_time=now + timedelta(hours=1),
        sha256_content_hash=event_hash,
        status="deleted",  # Already deleted
        deleted_at=deletion_time,
        version=6
    )
    async_session.add(existing)
    await async_session.flush()

    # Google sends cancellation for already-deleted event
    google_event_cancelled = {
        "id": "event1",
        "iCalUID": "event1@google.com",
        "summary": "Already Deleted",
        "status": "cancelled",
        "updated": cancellation_time.isoformat().replace("+00:00", "Z"),  # 10:50
        "start": {"dateTime": now.isoformat().replace("+00:00", "Z")},
        "end": {"dateTime": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")}
    }

    result = await process_single_event(
        user_id=str(user_id),
        event=google_event_cancelled,
        keywords=["focus"],
        session=async_session
    )

    # CRITICAL: Skipped (query found no active event)
    assert result == "skipped"

    # Verify no changes: version unchanged, deleted_at unchanged
    await async_session.flush()
    async_session.expire_all()

    stmt = select(FocusedFocusSession).where(
        FocusedFocusSession.user_id == user_id,
        FocusedFocusSession.google_event_id == "event1"
    )
    db_result = await async_session.execute(stmt)
    event = db_result.scalar_one()

    assert event.status == "deleted"  # Still deleted
    assert event.version == 6  # Unchanged (no double-bump)
    assert event.deleted_at == deletion_time  # Unchanged


# =============================================================================
# 6C Cleanup Edge Case
# =============================================================================

@pytest.mark.asyncio
async def test_cleanup_null_description_no_google_change(async_session: AsyncSession):
    """
    Test: 6C cleanup with no Google change
    - Event synced with description, hash=ABC, updated=T
    - 6C cleanup: description=NULL (but hash preserved), google_updated_at=T
    - Google still has same payload (description, updated=T)
    - Expect: No update (timestamps equal, hashes equal)
    - Result: version unchanged, description stays NULL

    This is a regression test proving:
    "Cleanup does not cause spurious updates when Google hasn't changed"

    Critical design: 6C sets event_description=NULL but PRESERVES sha256_content_hash.
    """
    user_id = await create_test_user_and_connection(async_session)
    now = datetime.now(timezone.utc)

    from backend.apps.focused.utils.hash import calculate_content_hash

    # Hash includes original description
    original_hash = calculate_content_hash(
        google_event_id="event1",
        event_summary="Event Title",
        event_description="Original description",
        start_time=now,
        end_time=now + timedelta(hours=1)
    )

    # Create event with NULL description (cleaned by 6C)
    # BUT hash is preserved (includes original description)
    existing = FocusedFocusSession(
        user_id=user_id,
        google_event_id="event1",
        google_calendar_id="primary",
        google_ical_uid="event1@google.com",
        google_updated_at=now,  # Same timestamp
        event_summary="Event Title",
        event_description=None,  # Cleaned up by 6C
        start_time=now,
        end_time=now + timedelta(hours=1),
        sha256_content_hash=original_hash,  # Hash PRESERVED by 6C
        status="active",
        version=10
    )
    async_session.add(existing)
    await async_session.flush()

    # Google still has original payload (hasn't changed)
    google_event = {
        "id": "event1",
        "iCalUID": "event1@google.com",
        "summary": "Event Title",
        "description": "Original description",  # Same as original
        "updated": now.isoformat().replace("+00:00", "Z"),  # Same timestamp
        "start": {"dateTime": now.isoformat().replace("+00:00", "Z")},
        "end": {"dateTime": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")}
    }

    result = await process_single_event(
        user_id=str(user_id),
        event=google_event,
        keywords=["focus"],
        session=async_session
    )

    # CRITICAL: No update (timestamps equal, hashes equal)
    assert result == "skipped"

    # Verify no changes: version unchanged, description stays NULL
    await async_session.flush()
    async_session.expire_all()

    stmt = select(FocusedFocusSession).where(
        FocusedFocusSession.user_id == user_id,
        FocusedFocusSession.google_event_id == "event1"
    )
    db_result = await async_session.execute(stmt)
    event = db_result.scalar_one()

    assert event.event_description is None  # Still NULL (6C cleanup preserved)
    assert event.version == 10  # Unchanged
    assert event.sha256_content_hash == original_hash  # Hash unchanged
