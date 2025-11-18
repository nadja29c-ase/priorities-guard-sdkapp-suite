"""
Increment 6A: FocusedFocusSession Model and Migration Tests

Tests:
1. SHA256 hash generation (includes description)
2. Model validation (field lengths, constraints)
3. Database constraints (FK, unique, check)
4. ENUM type enforcement
5. Timezone handling (UTC only)
6. Index creation
7. Soft delete behavior
"""

import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4, UUID

from sqlalchemy import select, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.focused.db_models import FocusedFocusSession
from backend.apps.focused.utils.hash import calculate_content_hash


# =============================================================================
# Test 1: SHA256 Hash Generation
# =============================================================================
def test_calculate_content_hash_includes_description():
    """
    Test 1: SHA256 hash includes ALL fields from spec.

    CRITICAL: Description MUST be included to detect description-only updates.
    """
    # Create hash with all fields
    start = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)

    hash1 = calculate_content_hash(
        google_event_id="event123",
        event_summary="Focus Time",
        event_description="Deep work session",
        start_time=start,
        end_time=end,
    )

    # Change ONLY description -> hash should change
    hash2 = calculate_content_hash(
        google_event_id="event123",
        event_summary="Focus Time",
        event_description="Different description",  # Changed
        start_time=start,
        end_time=end,
    )

    # Verify hashes are different (description change detected)
    assert hash1 != hash2

    # Verify hash is 64 characters (SHA256)
    assert len(hash1) == 64
    assert len(hash2) == 64


def test_calculate_content_hash_handles_none_values():
    """
    Test: Hash handles None/empty values correctly.
    """
    start = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)

    # None values should be treated as empty strings
    hash1 = calculate_content_hash(
        google_event_id="event123",
        event_summary=None,
        event_description=None,
        start_time=start,
        end_time=end,
    )

    hash2 = calculate_content_hash(
        google_event_id="event123",
        event_summary="",
        event_description="",
        start_time=start,
        end_time=end,
    )

    # None and empty string should produce same hash
    assert hash1 == hash2


def test_calculate_content_hash_deterministic():
    """
    Test: Hash is deterministic (same inputs = same hash).
    """
    start = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)

    hash1 = calculate_content_hash(
        google_event_id="event123",
        event_summary="Focus Time",
        event_description="Deep work",
        start_time=start,
        end_time=end,
    )

    hash2 = calculate_content_hash(
        google_event_id="event123",
        event_summary="Focus Time",
        event_description="Deep work",
        start_time=start,
        end_time=end,
    )

    # Same inputs should produce same hash
    assert hash1 == hash2


# =============================================================================
# Test 2: Model Validation
# =============================================================================
def test_model_validation_google_event_id():
    """
    Test: google_event_id validation (required, max 255 chars).
    """
    start = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)

    # Valid
    session = FocusedFocusSession(
        user_id=uuid4(),
        google_event_id="event123",
        google_calendar_id="primary",
        google_ical_uid="ical123@google.com",
        google_updated_at=datetime.now(timezone.utc),
        start_time=start,
        end_time=end,
        sha256_content_hash="a" * 64,
        status="active",
    )
    session.validate()  # Should not raise

    # Too long
    session.google_event_id = "x" * 256
    with pytest.raises(ValueError, match="google_event_id must be 1-255 characters"):
        session.validate()

    # Empty
    session.google_event_id = ""
    with pytest.raises(ValueError, match="google_event_id must be 1-255 characters"):
        session.validate()


def test_model_validation_google_ical_uid_required():
    """
    Test: google_ical_uid is REQUIRED (not nullable).

    CRITICAL: Claude often forgets this.
    """
    start = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)

    session = FocusedFocusSession(
        user_id=uuid4(),
        google_event_id="event123",
        google_calendar_id="primary",
        google_ical_uid="",  # Empty
        google_updated_at=datetime.now(timezone.utc),
        start_time=start,
        end_time=end,
        sha256_content_hash="a" * 64,
        status="active",
    )

    with pytest.raises(ValueError, match="google_ical_uid is required"):
        session.validate()


def test_model_validation_event_description_length():
    """
    Test: event_description max 8192 chars (Google Calendar limit).
    """
    start = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)

    session = FocusedFocusSession(
        user_id=uuid4(),
        google_event_id="event123",
        google_calendar_id="primary",
        google_ical_uid="ical123@google.com",
        google_updated_at=datetime.now(timezone.utc),
        start_time=start,
        end_time=end,
        event_description="x" * 8193,  # Too long
        sha256_content_hash="a" * 64,
        status="active",
    )

    with pytest.raises(ValueError, match="event_description must be <= 8192 characters"):
        session.validate()

    # Exactly 8192 should pass
    session.event_description = "x" * 8192
    session.validate()  # Should not raise


def test_model_validation_start_end_time_order():
    """
    Test: start_time must be < end_time.
    """
    start = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)  # Before start!

    session = FocusedFocusSession(
        user_id=uuid4(),
        google_event_id="event123",
        google_calendar_id="primary",
        google_ical_uid="ical123@google.com",
        google_updated_at=datetime.now(timezone.utc),
        start_time=start,
        end_time=end,
        sha256_content_hash="a" * 64,
        status="active",
    )

    with pytest.raises(ValueError, match="start_time must be < end_time"):
        session.validate()


def test_model_validation_sha256_hash_length():
    """
    Test: SHA256 hash must be exactly 64 hex characters.
    """
    start = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)

    session = FocusedFocusSession(
        user_id=uuid4(),
        google_event_id="event123",
        google_calendar_id="primary",
        google_ical_uid="ical123@google.com",
        google_updated_at=datetime.now(timezone.utc),
        start_time=start,
        end_time=end,
        sha256_content_hash="abc",  # Too short
        status="active",
    )

    with pytest.raises(ValueError, match="sha256_content_hash must be exactly 64 hex characters"):
        session.validate()


def test_model_validation_status_enum():
    """
    Test: status must be 'active' or 'deleted'.
    """
    start = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)

    session = FocusedFocusSession(
        user_id=uuid4(),
        google_event_id="event123",
        google_calendar_id="primary",
        google_ical_uid="ical123@google.com",
        google_updated_at=datetime.now(timezone.utc),
        start_time=start,
        end_time=end,
        sha256_content_hash="a" * 64,
        status="invalid",  # Invalid status
    )

    with pytest.raises(ValueError, match="status must be 'active' or 'deleted'"):
        session.validate()


def test_model_validation_version_positive():
    """
    Test: version must be >= 1.
    """
    start = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)

    session = FocusedFocusSession(
        user_id=uuid4(),
        google_event_id="event123",
        google_calendar_id="primary",
        google_ical_uid="ical123@google.com",
        google_updated_at=datetime.now(timezone.utc),
        start_time=start,
        end_time=end,
        sha256_content_hash="a" * 64,
        status="active",
        version=0,  # Invalid
    )

    with pytest.raises(ValueError, match="version must be >= 1"):
        session.validate()


# =============================================================================
# Test 3: Database Integration (requires running DB)
# =============================================================================
@pytest.mark.asyncio
async def test_model_creates_successfully(async_session: AsyncSession):
    """
    Test: Model can be created in database with all fields.
    """
    start = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)
    updated = datetime(2025, 1, 15, 9, 0, tzinfo=timezone.utc)

    # Create a test user_id (assuming core_users exists)
    test_user_id = uuid4()

    session = FocusedFocusSession(
        user_id=test_user_id,
        google_event_id="event123",
        google_calendar_id="primary",
        google_ical_uid="ical123@google.com",
        google_updated_at=updated,
        event_summary="Focus Time",
        event_description="Deep work session",
        start_time=start,
        end_time=end,
        is_focus_block=True,
        matched_keyword="focus",
        sha256_content_hash=calculate_content_hash(
            google_event_id="event123",
            event_summary="Focus Time",
            event_description="Deep work session",
            start_time=start,
            end_time=end,
        ),
        status="active",
    )

    async_session.add(session)
    await async_session.commit()

    # Verify it was created
    stmt = select(FocusedFocusSession).where(FocusedFocusSession.google_event_id == "event123")
    result = await async_session.execute(stmt)
    loaded = result.scalar_one_or_none()

    assert loaded is not None
    assert loaded.google_event_id == "event123"
    assert loaded.is_focus_block is True
    assert loaded.matched_keyword == "focus"


@pytest.mark.asyncio
async def test_unique_constraint_user_event_calendar(async_session: AsyncSession):
    """
    Test: Unique constraint prevents duplicate (user_id, google_event_id, google_calendar_id).
    """
    start = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)
    updated = datetime(2025, 1, 15, 9, 0, tzinfo=timezone.utc)

    test_user_id = uuid4()

    # Create first session
    session1 = FocusedFocusSession(
        user_id=test_user_id,
        google_event_id="event123",
        google_calendar_id="primary",
        google_ical_uid="ical123@google.com",
        google_updated_at=updated,
        start_time=start,
        end_time=end,
        sha256_content_hash="a" * 64,
        status="active",
    )

    async_session.add(session1)
    await async_session.commit()

    # Try to create duplicate
    session2 = FocusedFocusSession(
        user_id=test_user_id,  # Same user
        google_event_id="event123",  # Same event
        google_calendar_id="primary",  # Same calendar
        google_ical_uid="ical123@google.com",
        google_updated_at=updated,
        start_time=start,
        end_time=end,
        sha256_content_hash="b" * 64,
        status="active",
    )

    async_session.add(session2)

    # Should raise IntegrityError
    with pytest.raises(IntegrityError):
        await async_session.commit()


@pytest.mark.asyncio
async def test_check_constraint_time_order(async_session: AsyncSession):
    """
    Test: Check constraint enforces start_time < end_time at DB level.
    """
    start = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)  # Before start!

    test_user_id = uuid4()

    session = FocusedFocusSession(
        user_id=test_user_id,
        google_event_id="event123",
        google_calendar_id="primary",
        google_ical_uid="ical123@google.com",
        google_updated_at=datetime.now(timezone.utc),
        start_time=start,
        end_time=end,
        sha256_content_hash="a" * 64,
        status="active",
    )

    async_session.add(session)

    # Should raise IntegrityError
    with pytest.raises(IntegrityError):
        await async_session.commit()


# =============================================================================
# Test 4: Migration Verification
# =============================================================================
@pytest.mark.asyncio
async def test_migration_creates_all_indexes(async_session: AsyncSession):
    """
    Test: Migration creates all 6 indexes from spec.
    """
    inspector = inspect(async_session.bind)
    indexes = inspector.get_indexes('focused_focus_sessions')

    # Get index names
    index_names = {idx['name'] for idx in indexes}

    # Verify all 6 indexes exist
    expected_indexes = {
        'idx_focus_sessions_start_time',
        'idx_focus_sessions_end_time',
        'idx_focus_sessions_focus_blocks',
        'idx_focus_sessions_user_hash',
        'idx_focus_sessions_cleanup',
        'idx_focus_sessions_ical_uid',
    }

    assert expected_indexes.issubset(index_names), f"Missing indexes: {expected_indexes - index_names}"


@pytest.mark.asyncio
async def test_migration_creates_composite_hash_index(async_session: AsyncSession):
    """
    Test: Hash index is composite (user_id, sha256_content_hash).

    CRITICAL: Must be composite to prevent cross-user scans.
    """
    inspector = inspect(async_session.bind)
    indexes = inspector.get_indexes('focused_focus_sessions')

    # Find user_hash index
    user_hash_index = next(
        (idx for idx in indexes if idx['name'] == 'idx_focus_sessions_user_hash'),
        None
    )

    assert user_hash_index is not None
    assert len(user_hash_index['column_names']) == 2
    assert 'user_id' in user_hash_index['column_names']
    assert 'sha256_content_hash' in user_hash_index['column_names']


@pytest.mark.asyncio
async def test_migration_creates_enum_type(async_session: AsyncSession):
    """
    Test: Migration creates PostgreSQL ENUM type 'event_status_enum'.
    """
    result = await async_session.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_type
            WHERE typname = 'event_status_enum'
        )
        """
    )
    enum_exists = result.scalar()

    assert enum_exists is True


# =============================================================================
# Test 5: Soft Delete Behavior
# =============================================================================
@pytest.mark.asyncio
async def test_soft_delete_sets_status_and_timestamp(async_session: AsyncSession):
    """
    Test: Soft delete sets status='deleted' and deleted_at timestamp.
    """
    start = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)

    test_user_id = uuid4()

    session = FocusedFocusSession(
        user_id=test_user_id,
        google_event_id="event123",
        google_calendar_id="primary",
        google_ical_uid="ical123@google.com",
        google_updated_at=datetime.now(timezone.utc),
        start_time=start,
        end_time=end,
        sha256_content_hash="a" * 64,
        status="active",
    )

    async_session.add(session)
    await async_session.commit()

    # Soft delete
    session.status = "deleted"
    session.deleted_at = datetime.now(timezone.utc)
    await async_session.commit()

    # Verify
    stmt = select(FocusedFocusSession).where(FocusedFocusSession.id == session.id)
    result = await async_session.execute(stmt)
    loaded = result.scalar_one()

    assert loaded.status == "deleted"
    assert loaded.deleted_at is not None
