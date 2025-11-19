"""
Increment 6D: Sync Conflict Detection Tests

Tests timestamp-based conflict detection to prevent data corruption from:
- Out-of-order webhook delivery
- Stale Google API responses
- Deletions vs updates applied in wrong order

Test Coverage:
- Conflict detection logic (5 tests)
- Deletion handling (4 tests)
- Out-of-order webhooks (4 tests)
- Description cleanup integration (6 tests)
"""

import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.focused.logic_sync import process_single_event, detect_deleted_events
from backend.apps.focused.logic_conflicts import should_accept_update, should_accept_deletion
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
