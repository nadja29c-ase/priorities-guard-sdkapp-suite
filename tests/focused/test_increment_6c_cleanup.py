"""
Increment 6C: Description Cleanup & Sync Correctness Tests

Tests GDPR-compliant description retention and sync behavior with NULL descriptions.

Test Scenarios:
1. Cleanup deletes descriptions older than 72 hours
2. Cleanup preserves recent descriptions
3. CRITICAL: Re-synced descriptions get fresh 72h window (uses updated_at)
4. Sync detects changes when local description is NULL
5. New description respects 72h TTL after restore
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.focused.logic_cleanup import cleanup_old_descriptions
from backend.apps.focused.logic_sync import process_single_event
from backend.apps.focused.db_models import FocusedFocusSession
from backend.apps.focused.focused_config import FOCUSED_EVENTDESCR_TTL


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
# Test 1: Cleanup deletes descriptions older than 72 hours
# =============================================================================
@pytest.mark.asyncio
async def test_cleanup_deletes_old_descriptions(async_session: AsyncSession):
    """
    Test 1: Cleanup deletes descriptions >72h old
    - Create event with description updated_at 73 hours ago
    - Run cleanup
    - Verify description is NULL
    """
    user_id = await create_test_user_and_connection(async_session)

    # Create event with old description (73 hours ago)
    now = datetime.now(timezone.utc)
    old_updated_at = now - timedelta(hours=73)

    old_event = FocusedFocusSession(
        user_id=user_id,
        google_event_id="old_event",
        google_calendar_id="primary",
        google_ical_uid="old@google.com",
        google_updated_at=now,
        event_summary="Old Event",
        event_description="This description should be deleted",
        start_time=now,
        end_time=now + timedelta(hours=1),
        sha256_content_hash="a" * 64,
        status="active",
        updated_at=old_updated_at  # 73 hours ago
    )
    async_session.add(old_event)
    await async_session.flush()

    # Run cleanup
    deleted_count = await cleanup_old_descriptions(async_session)

    assert deleted_count == 1

    # Verify description is NULL
    async_session.expire_all()
    stmt = select(FocusedFocusSession).where(
        FocusedFocusSession.user_id == user_id,
        FocusedFocusSession.google_event_id == "old_event"
    )
    result = await async_session.execute(stmt)
    event = result.scalar_one()

    assert event.event_description is None
    assert event.event_summary == "Old Event"  # Summary preserved
    assert event.updated_at > old_updated_at  # updated_at refreshed


# =============================================================================
# Test 2: Cleanup preserves recent descriptions
# =============================================================================
@pytest.mark.asyncio
async def test_cleanup_preserves_recent_descriptions(async_session: AsyncSession):
    """
    Test 2: Cleanup preserves recent descriptions
    - Create event with description updated 71 hours ago (within TTL)
    - Run cleanup
    - Verify description is NOT deleted
    """
    user_id = await create_test_user_and_connection(async_session)

    # Create event with recent description (71 hours ago - within TTL)
    now = datetime.now(timezone.utc)
    recent_updated_at = now - timedelta(hours=71)

    recent_event = FocusedFocusSession(
        user_id=user_id,
        google_event_id="recent_event",
        google_calendar_id="primary",
        google_ical_uid="recent@google.com",
        google_updated_at=now,
        event_summary="Recent Event",
        event_description="This description should be kept",
        start_time=now,
        end_time=now + timedelta(hours=1),
        sha256_content_hash="b" * 64,
        status="active",
        updated_at=recent_updated_at  # 71 hours ago (within 72h TTL)
    )
    async_session.add(recent_event)
    await async_session.flush()

    # Run cleanup
    deleted_count = await cleanup_old_descriptions(async_session)

    assert deleted_count == 0

    # Verify description is still present
    async_session.expire_all()
    stmt = select(FocusedFocusSession).where(
        FocusedFocusSession.user_id == user_id,
        FocusedFocusSession.google_event_id == "recent_event"
    )
    result = await async_session.execute(stmt)
    event = result.scalar_one()

    assert event.event_description == "This description should be kept"


# =============================================================================
# Test 3: CRITICAL - Re-synced descriptions get fresh 72h window
# =============================================================================
@pytest.mark.asyncio
async def test_resynced_descriptions_get_fresh_ttl(async_session: AsyncSession):
    """
    Test 3: CRITICAL - Re-synced descriptions get fresh 72h window
    - Create event with NULL description and old hash
    - Sync event with new description
    - Verify description restored with fresh updated_at
    - Verify description NOT deleted immediately after
    """
    user_id = await create_test_user_and_connection(async_session)

    # Create event with NULL description (cleaned up)
    now = datetime.now(timezone.utc)
    old_updated_at = now - timedelta(hours=80)  # Very old

    event = FocusedFocusSession(
        user_id=user_id,
        google_event_id="resync_event",
        google_calendar_id="primary",
        google_ical_uid="resync@google.com",
        google_updated_at=now - timedelta(days=1),
        event_summary="Event Title",
        event_description=None,  # Cleaned up
        start_time=now,
        end_time=now + timedelta(hours=1),
        sha256_content_hash="a" * 64,  # Old hash (64 chars)
        status="active",
        updated_at=old_updated_at
    )
    async_session.add(event)
    await async_session.flush()

    # Mock Google event with description
    google_event = {
        "id": "resync_event",
        "iCalUID": "resync@google.com",
        "summary": "Event Title",
        "description": "Restored description",
        "updated": now.isoformat().replace("+00:00", "Z"),
        "start": {"dateTime": now.isoformat().replace("+00:00", "Z")},
        "end": {"dateTime": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")}
    }

    # Process event (should restore description)
    result = await process_single_event(
        user_id=str(user_id),
        event=google_event,
        keywords=["focus"],
        session=async_session
    )

    assert result == "updated"

    # Flush changes to DB
    await async_session.flush()

    # Verify description restored with fresh updated_at
    async_session.expire_all()
    stmt = select(FocusedFocusSession).where(
        FocusedFocusSession.user_id == user_id,
        FocusedFocusSession.google_event_id == "resync_event"
    )
    db_result = await async_session.execute(stmt)
    updated_event = db_result.scalar_one()

    assert updated_event.event_description == "Restored description"
    assert updated_event.updated_at > old_updated_at  # Fresh timestamp
    assert updated_event.updated_at >= now - timedelta(seconds=5)  # Very recent

    # Run cleanup immediately - should NOT delete (fresh TTL)
    deleted_count = await cleanup_old_descriptions(async_session)
    assert deleted_count == 0

    # Verify description still present
    async_session.expire_all()
    stmt = select(FocusedFocusSession).where(
        FocusedFocusSession.user_id == user_id,
        FocusedFocusSession.google_event_id == "resync_event"
    )
    db_result = await async_session.execute(stmt)
    final_event = db_result.scalar_one()

    assert final_event.event_description == "Restored description"


# =============================================================================
# Test 4: Sync detects changes when local description is NULL
# =============================================================================
@pytest.mark.asyncio
async def test_sync_detects_changes_with_null_description(async_session: AsyncSession):
    """
    Test 4: Sync detects changes when local description is NULL
    - Create event with NULL description
    - Sync with changed Google event (different summary)
    - Verify update detected via hash comparison
    """
    user_id = await create_test_user_and_connection(async_session)

    now = datetime.now(timezone.utc)

    # Calculate hash for OLD event (with "Old Title")
    from backend.apps.focused.utils.hash import calculate_content_hash

    old_hash = calculate_content_hash(
        google_event_id="null_desc_event",
        event_summary="Old Title",
        event_description="Some description",
        start_time=now,
        end_time=now + timedelta(hours=1)
    )

    # Create event with NULL description and hash that included original description
    event = FocusedFocusSession(
        user_id=user_id,
        google_event_id="null_desc_event",
        google_calendar_id="primary",
        google_ical_uid="nulldesc@google.com",
        google_updated_at=now - timedelta(days=1),
        event_summary="Old Title",
        event_description=None,  # Cleaned up
        start_time=now,
        end_time=now + timedelta(hours=1),
        sha256_content_hash=old_hash,  # Hash with OLD title
        status="active",
        updated_at=now - timedelta(hours=80)
    )
    async_session.add(event)
    await async_session.flush()

    # Mock Google event with changed title
    google_event = {
        "id": "null_desc_event",
        "iCalUID": "nulldesc@google.com",
        "summary": "New Title",  # Changed!
        "description": "Some description",
        "updated": now.isoformat().replace("+00:00", "Z"),
        "start": {"dateTime": now.isoformat().replace("+00:00", "Z")},
        "end": {"dateTime": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")}
    }

    # Process event (should detect change via hash)
    result = await process_single_event(
        user_id=str(user_id),
        event=google_event,
        keywords=["focus"],
        session=async_session
    )

    assert result == "updated"

    # Flush changes to DB
    await async_session.flush()

    # Verify event updated
    async_session.expire_all()
    stmt = select(FocusedFocusSession).where(
        FocusedFocusSession.user_id == user_id,
        FocusedFocusSession.google_event_id == "null_desc_event"
    )
    db_result = await async_session.execute(stmt)
    updated_event = db_result.scalar_one()

    assert updated_event.event_summary == "New Title"
    assert updated_event.event_description == "Some description"


# =============================================================================
# Test 5: No false positives - NULL description with unchanged event
# =============================================================================
@pytest.mark.asyncio
async def test_no_false_positives_with_null_description(async_session: AsyncSession):
    """
    Test 5: No false positives - NULL description with unchanged event
    - Create event with NULL description
    - Sync with unchanged Google event
    - Verify NO update (hash same)
    """
    user_id = await create_test_user_and_connection(async_session)

    now = datetime.now(timezone.utc)

    # Calculate correct hash for event
    from backend.apps.focused.utils.hash import calculate_content_hash

    correct_hash = calculate_content_hash(
        google_event_id="unchanged_event",
        event_summary="Unchanged Title",
        event_description="Unchanged description",
        start_time=now,
        end_time=now + timedelta(hours=1)
    )

    # Create event with NULL description but correct hash
    event = FocusedFocusSession(
        user_id=user_id,
        google_event_id="unchanged_event",
        google_calendar_id="primary",
        google_ical_uid="unchanged@google.com",
        google_updated_at=now - timedelta(days=1),
        event_summary="Unchanged Title",
        event_description=None,  # Cleaned up
        start_time=now,
        end_time=now + timedelta(hours=1),
        sha256_content_hash=correct_hash,  # Hash includes original description
        status="active",
        updated_at=now - timedelta(hours=80)
    )
    async_session.add(event)
    await async_session.flush()

    # Mock Google event with same data
    google_event = {
        "id": "unchanged_event",
        "iCalUID": "unchanged@google.com",
        "summary": "Unchanged Title",
        "description": "Unchanged description",
        "updated": (now - timedelta(days=1)).isoformat().replace("+00:00", "Z"),
        "start": {"dateTime": now.isoformat().replace("+00:00", "Z")},
        "end": {"dateTime": (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")}
    }

    # Process event (should skip - no changes)
    result = await process_single_event(
        user_id=str(user_id),
        event=google_event,
        keywords=["focus"],
        session=async_session
    )

    assert result == "skipped"


# =============================================================================
# Test 6: Cleanup respects status (only active events)
# =============================================================================
@pytest.mark.asyncio
async def test_cleanup_only_affects_active_events(async_session: AsyncSession):
    """
    Test 6: Cleanup only affects active events
    - Create old deleted event with description
    - Run cleanup
    - Verify deleted event description NOT cleaned
    """
    user_id = await create_test_user_and_connection(async_session)

    now = datetime.now(timezone.utc)
    old_updated_at = now - timedelta(hours=80)

    # Create deleted event with old description
    deleted_event = FocusedFocusSession(
        user_id=user_id,
        google_event_id="deleted_event",
        google_calendar_id="primary",
        google_ical_uid="deleted@google.com",
        google_updated_at=now,
        event_summary="Deleted Event",
        event_description="Should not be cleaned (event is deleted)",
        start_time=now,
        end_time=now + timedelta(hours=1),
        sha256_content_hash="c" * 64,
        status="deleted",  # Not active
        deleted_at=now,
        updated_at=old_updated_at
    )
    async_session.add(deleted_event)
    await async_session.flush()

    # Run cleanup
    deleted_count = await cleanup_old_descriptions(async_session)

    assert deleted_count == 0  # Should not clean deleted events

    # Verify description still present
    async_session.expire_all()
    stmt = select(FocusedFocusSession).where(
        FocusedFocusSession.user_id == user_id,
        FocusedFocusSession.google_event_id == "deleted_event"
    )
    result = await async_session.execute(stmt)
    event = result.scalar_one()

    assert event.event_description == "Should not be cleaned (event is deleted)"


# =============================================================================
# Test 7: Verify TTL constant is 72 hours
# =============================================================================
@pytest.mark.asyncio
async def test_ttl_constant_is_72_hours():
    """
    Test 7: Verify TTL constant is 72 hours
    - Ensure FOCUSED_EVENTDESCR_TTL is exactly 72 hours
    """
    assert FOCUSED_EVENTDESCR_TTL == timedelta(hours=72)


# =============================================================================
# Test A: Mixed set cleanup (CRITICAL multi-event test)
# =============================================================================
@pytest.mark.asyncio
async def test_mixed_set_cleanup(async_session: AsyncSession):
    """
    Test A: Mixed set cleanup - multiple events with different statuses and ages

    Tests SQL filter correctness across multiple rows in a single cleanup run.

    Scenario:
    - Event 1: old active with description → SHOULD be cleaned
    - Event 2: recent active with description → SHOULD stay
    - Event 3: old deleted with description → SHOULD stay (not active)
    - Event 4: recent deleted with description → SHOULD stay (not active)

    Expected:
    - Only Event 1 cleaned
    - deleted_count = 1
    - Events 2, 3, 4 descriptions preserved
    """
    user_id = await create_test_user_and_connection(async_session)

    now = datetime.now(timezone.utc)
    old_time = now - timedelta(hours=73)  # > 72h
    recent_time = now - timedelta(hours=71)  # < 72h

    # Event 1: old active → should be cleaned
    event1 = FocusedFocusSession(
        user_id=user_id,
        google_event_id="event1_old_active",
        google_calendar_id="primary",
        google_ical_uid="event1@google.com",
        google_updated_at=now,
        event_summary="Old Active Event",
        event_description="Should be deleted",
        start_time=now,
        end_time=now + timedelta(hours=1),
        sha256_content_hash="a" * 64,
        status="active",
        updated_at=old_time
    )

    # Event 2: recent active → should stay
    event2 = FocusedFocusSession(
        user_id=user_id,
        google_event_id="event2_recent_active",
        google_calendar_id="primary",
        google_ical_uid="event2@google.com",
        google_updated_at=now,
        event_summary="Recent Active Event",
        event_description="Should be kept",
        start_time=now,
        end_time=now + timedelta(hours=1),
        sha256_content_hash="b" * 64,
        status="active",
        updated_at=recent_time
    )

    # Event 3: old deleted → should stay (not active)
    event3 = FocusedFocusSession(
        user_id=user_id,
        google_event_id="event3_old_deleted",
        google_calendar_id="primary",
        google_ical_uid="event3@google.com",
        google_updated_at=now,
        event_summary="Old Deleted Event",
        event_description="Should be kept (deleted status)",
        start_time=now,
        end_time=now + timedelta(hours=1),
        sha256_content_hash="c" * 64,
        status="deleted",
        deleted_at=now,
        updated_at=old_time
    )

    # Event 4: recent deleted → should stay (not active)
    event4 = FocusedFocusSession(
        user_id=user_id,
        google_event_id="event4_recent_deleted",
        google_calendar_id="primary",
        google_ical_uid="event4@google.com",
        google_updated_at=now,
        event_summary="Recent Deleted Event",
        event_description="Should be kept (deleted status)",
        start_time=now,
        end_time=now + timedelta(hours=1),
        sha256_content_hash="d" * 64,
        status="deleted",
        deleted_at=now,
        updated_at=recent_time
    )

    async_session.add_all([event1, event2, event3, event4])
    await async_session.flush()

    # Run cleanup
    deleted_count = await cleanup_old_descriptions(async_session)

    assert deleted_count == 1

    # Verify Event 1 cleaned
    async_session.expire_all()
    stmt = select(FocusedFocusSession).where(
        FocusedFocusSession.user_id == user_id,
        FocusedFocusSession.google_event_id == "event1_old_active"
    )
    result = await async_session.execute(stmt)
    e1 = result.scalar_one()
    assert e1.event_description is None
    assert e1.updated_at > old_time  # Refreshed

    # Verify Event 2 preserved
    stmt = select(FocusedFocusSession).where(
        FocusedFocusSession.user_id == user_id,
        FocusedFocusSession.google_event_id == "event2_recent_active"
    )
    result = await async_session.execute(stmt)
    e2 = result.scalar_one()
    assert e2.event_description == "Should be kept"
    assert e2.updated_at == recent_time  # Unchanged

    # Verify Event 3 preserved
    stmt = select(FocusedFocusSession).where(
        FocusedFocusSession.user_id == user_id,
        FocusedFocusSession.google_event_id == "event3_old_deleted"
    )
    result = await async_session.execute(stmt)
    e3 = result.scalar_one()
    assert e3.event_description == "Should be kept (deleted status)"

    # Verify Event 4 preserved
    stmt = select(FocusedFocusSession).where(
        FocusedFocusSession.user_id == user_id,
        FocusedFocusSession.google_event_id == "event4_recent_deleted"
    )
    result = await async_session.execute(stmt)
    e4 = result.scalar_one()
    assert e4.event_description == "Should be kept (deleted status)"


# =============================================================================
# Test B: Multiple deletions with correct count
# =============================================================================
@pytest.mark.asyncio
async def test_cleanup_multiple_deletions_with_correct_count(async_session: AsyncSession):
    """
    Test B: Cleanup returns correct count when multiple rows deleted

    Verifies:
    - Correct deleted_count when >1 row cleaned
    - updated_at refreshed on each cleaned row
    - All old descriptions cleaned atomically

    Scenario:
    - 3 old active events with descriptions → all cleaned
    - 2 recent active events with descriptions → all preserved
    """
    user_id = await create_test_user_and_connection(async_session)

    now = datetime.now(timezone.utc)
    old_time = now - timedelta(hours=75)  # > 72h
    recent_time = now - timedelta(hours=70)  # < 72h

    # 3 old events → should all be cleaned
    old_events = []
    for i in range(3):
        event = FocusedFocusSession(
            user_id=user_id,
            google_event_id=f"old_event_{i}",
            google_calendar_id="primary",
            google_ical_uid=f"old{i}@google.com",
            google_updated_at=now,
            event_summary=f"Old Event {i}",
            event_description=f"Old description {i}",
            start_time=now,
            end_time=now + timedelta(hours=1),
            sha256_content_hash=f"{i}" * 64,
            status="active",
            updated_at=old_time - timedelta(minutes=i)  # Slightly different times
        )
        old_events.append(event)

    # 2 recent events → should be preserved
    recent_events = []
    for i in range(2):
        event = FocusedFocusSession(
            user_id=user_id,
            google_event_id=f"recent_event_{i}",
            google_calendar_id="primary",
            google_ical_uid=f"recent{i}@google.com",
            google_updated_at=now,
            event_summary=f"Recent Event {i}",
            event_description=f"Recent description {i}",
            start_time=now,
            end_time=now + timedelta(hours=1),
            sha256_content_hash=f"{i+3}" * 64,
            status="active",
            updated_at=recent_time
        )
        recent_events.append(event)

    async_session.add_all(old_events + recent_events)
    await async_session.flush()

    # Run cleanup
    deleted_count = await cleanup_old_descriptions(async_session)

    # Verify correct count
    assert deleted_count == 3

    # Verify all old events cleaned with refreshed updated_at
    async_session.expire_all()
    for i in range(3):
        stmt = select(FocusedFocusSession).where(
            FocusedFocusSession.user_id == user_id,
            FocusedFocusSession.google_event_id == f"old_event_{i}"
        )
        result = await async_session.execute(stmt)
        event = result.scalar_one()
        assert event.event_description is None
        assert event.updated_at > old_time  # Refreshed
        assert event.event_summary == f"Old Event {i}"  # Summary preserved

    # Verify all recent events preserved with unchanged updated_at
    for i in range(2):
        stmt = select(FocusedFocusSession).where(
            FocusedFocusSession.user_id == user_id,
            FocusedFocusSession.google_event_id == f"recent_event_{i}"
        )
        result = await async_session.execute(stmt)
        event = result.scalar_one()
        assert event.event_description == f"Recent description {i}"
        assert event.updated_at == recent_time  # Unchanged
