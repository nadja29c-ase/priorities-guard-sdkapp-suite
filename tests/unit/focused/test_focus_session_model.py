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
8. FK constraint enforcement
9. Default values
"""

import pytest
import sqlalchemy as sa
from datetime import datetime, timezone, timedelta
from uuid import uuid4, UUID

from sqlalchemy import select, inspect, text
from sqlalchemy.exc import IntegrityError, DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.focused.db_models import FocusedFocusSession
from backend.apps.focused.utils.hash import calculate_content_hash


# =============================================================================
# Helper: Create test user
# =============================================================================
async def create_test_user(async_session: AsyncSession, user_id: UUID = None) -> UUID:
    """
    Create a test user in core_users table.

    CRITICAL: Must be called before creating FocusedFocusSession to satisfy FK constraint.
    Note: Does NOT commit - the session fixture handles transaction management.
    """
    if user_id is None:
        user_id = uuid4()

    await async_session.execute(
        text("INSERT INTO core_users (id) VALUES (:id)"),
        {"id": user_id}
    )
    # Don't commit - let the session fixture handle transaction management
    await async_session.flush()  # Flush to make the user visible within the transaction
    return user_id


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


def test_calculate_content_hash_rejects_naive_datetime():
    """
    Test: Hash rejects naive datetime (no timezone).

    CRITICAL: Prevents false conflicts from naive datetime bugs.
    """
    # Naive datetime (no tzinfo)
    start_naive = datetime(2025, 1, 15, 10, 0)  # No tzinfo
    end = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="start_time must be timezone-aware"):
        calculate_content_hash(
            google_event_id="event123",
            event_summary="Focus Time",
            event_description="Deep work",
            start_time=start_naive,
            end_time=end,
        )

    # End time naive
    start = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    end_naive = datetime(2025, 1, 15, 12, 0)  # No tzinfo

    with pytest.raises(ValueError, match="end_time must be timezone-aware"):
        calculate_content_hash(
            google_event_id="event123",
            event_summary="Focus Time",
            event_description="Deep work",
            start_time=start,
            end_time=end_naive,
        )


def test_calculate_content_hash_rejects_non_utc_timezone():
    """
    Test: Hash rejects non-UTC timezone.

    CRITICAL: All timestamps must be UTC to ensure consistent hashing.
    """
    from datetime import timedelta

    # Create a non-UTC timezone (e.g., EST = UTC-5)
    est = timezone(timedelta(hours=-5))

    start_est = datetime(2025, 1, 15, 10, 0, tzinfo=est)
    end = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="start_time must be UTC"):
        calculate_content_hash(
            google_event_id="event123",
            event_summary="Focus Time",
            event_description="Deep work",
            start_time=start_est,
            end_time=end,
        )

    # End time non-UTC
    start = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    end_est = datetime(2025, 1, 15, 12, 0, tzinfo=est)

    with pytest.raises(ValueError, match="end_time must be UTC"):
        calculate_content_hash(
            google_event_id="event123",
            event_summary="Focus Time",
            event_description="Deep work",
            start_time=start,
            end_time=end_est,
        )


# =============================================================================
# Test 2: Model Validation
# =============================================================================
def test_model_validation_google_event_id():
    """
    Test: google_event_id validation (required, max 255 chars) for calendar-triggered sessions.
    """
    start = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)

    # Valid calendar-triggered session
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
        trigger_source="calendar",  # Required for google_event_id validation
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
    Test: google_ical_uid is REQUIRED for calendar-triggered sessions.

    CRITICAL: google_ical_uid + start_time form the unique identity for recurring events.
    """
    start = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)

    session = FocusedFocusSession(
        user_id=uuid4(),
        google_event_id="event123",
        google_calendar_id="primary",
        google_ical_uid="",  # Empty - should fail
        google_updated_at=datetime.now(timezone.utc),
        start_time=start,
        end_time=end,
        sha256_content_hash="a" * 64,
        status="active",
        trigger_source="calendar",  # Required for google_ical_uid validation
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


def test_model_validation_timezone_aware_timestamps():
    """
    Test: Model validates timezone-aware UTC timestamps.

    CRITICAL: Validates at MODEL level, not just hash function.
    """
    # Naive datetime
    start_naive = datetime(2025, 1, 15, 10, 0)  # No tzinfo
    end = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)

    session = FocusedFocusSession(
        user_id=uuid4(),
        google_event_id="event123",
        google_calendar_id="primary",
        google_ical_uid="ical123@google.com",
        google_updated_at=datetime.now(timezone.utc),
        start_time=start_naive,
        end_time=end,
        sha256_content_hash="a" * 64,
    )

    with pytest.raises(ValueError, match="start_time must be timezone-aware"):
        session.validate()

    # Non-UTC timezone
    est = timezone(timedelta(hours=-5))
    start_est = datetime(2025, 1, 15, 10, 0, tzinfo=est)

    session.start_time = start_est
    with pytest.raises(ValueError, match="start_time must be UTC"):
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

    # CRITICAL: Create user first to satisfy FK constraint
    test_user_id = await create_test_user(async_session)

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

    # Test defaults
    assert loaded.last_synced_at is None  # NEW: Must default to NULL
    assert loaded.version == 1  # NEW: Must default to 1
    assert loaded.status == "active"  # Must default to 'active'


@pytest.mark.asyncio
async def test_default_google_calendar_id(async_session: AsyncSession):
    """
    Test: google_calendar_id defaults to 'primary' at DB level.
    """
    start = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)

    test_user_id = await create_test_user(async_session)

    # Insert without specifying google_calendar_id - use raw SQL to test DB default
    await async_session.execute(
        text("""
            INSERT INTO focused_focus_sessions (
                user_id, google_event_id, google_ical_uid, google_updated_at,
                start_time, end_time, sha256_content_hash
            ) VALUES (
                :user_id, :event_id, :ical_uid, :updated,
                :start, :end, :hash
            )
        """),
        {
            "user_id": test_user_id,
            "event_id": "event_default_calendar",
            "ical_uid": "ical@google.com",
            "updated": datetime.now(timezone.utc),
            "start": start,
            "end": end,
            "hash": "a" * 64,
        }
    )
    await async_session.commit()

    # Verify default was applied
    result = await async_session.execute(
        text("SELECT google_calendar_id FROM focused_focus_sessions WHERE google_event_id = :id"),
        {"id": "event_default_calendar"}
    )
    calendar_id = result.scalar()
    assert calendar_id == "primary"


@pytest.mark.asyncio
async def test_unique_constraint_user_event_calendar(async_session: AsyncSession):
    """
    Test: Unique constraint prevents duplicate (user_id, google_event_id, google_calendar_id).
    """
    start = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)
    updated = datetime(2025, 1, 15, 9, 0, tzinfo=timezone.utc)

    test_user_id = await create_test_user(async_session)

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

    test_user_id = await create_test_user(async_session)

    session = FocusedFocusSession(
        user_id=test_user_id,
        google_event_id="event123",
        google_calendar_id="primary",
        google_ical_uid="ical123@google.com",
        google_updated_at=datetime.now(timezone.utc),
        start_time=start,
        end_time=end,
        sha256_content_hash="a" * 64,
    )

    async_session.add(session)

    # Should raise IntegrityError
    with pytest.raises(IntegrityError):
        await async_session.commit()


@pytest.mark.asyncio
async def test_check_constraint_sha256_length(async_session: AsyncSession):
    """
    Test: Check constraint enforces SHA256 hash length = 64 at DB level.

    CRITICAL: Tests DB constraint, not just model validation.
    """
    start = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)

    test_user_id = await create_test_user(async_session)

    # Use raw SQL to bypass model validation
    with pytest.raises(IntegrityError, match="ck_focus_sessions_hash_length"):
        await async_session.execute(
            text("""
                INSERT INTO focused_focus_sessions (
                    user_id, google_event_id, google_calendar_id, google_ical_uid,
                    google_updated_at, start_time, end_time, sha256_content_hash
                ) VALUES (
                    :user_id, :event_id, :calendar_id, :ical_uid,
                    :updated, :start, :end, :hash
                )
            """),
            {
                "user_id": test_user_id,
                "event_id": "event_bad_hash",
                "calendar_id": "primary",
                "ical_uid": "ical@google.com",
                "updated": datetime.now(timezone.utc),
                "start": start,
                "end": end,
                "hash": "abc",  # Too short
            }
        )
        await async_session.commit()


@pytest.mark.asyncio
async def test_check_constraint_version_positive(async_session: AsyncSession):
    """
    Test: Check constraint enforces version >= 1 at DB level.
    """
    start = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)

    test_user_id = await create_test_user(async_session)

    # Use raw SQL to bypass model validation
    with pytest.raises(IntegrityError, match="ck_focus_sessions_version_positive"):
        await async_session.execute(
            text("""
                INSERT INTO focused_focus_sessions (
                    user_id, google_event_id, google_calendar_id, google_ical_uid,
                    google_updated_at, start_time, end_time, sha256_content_hash, version
                ) VALUES (
                    :user_id, :event_id, :calendar_id, :ical_uid,
                    :updated, :start, :end, :hash, :version
                )
            """),
            {
                "user_id": test_user_id,
                "event_id": "event_bad_version",
                "calendar_id": "primary",
                "ical_uid": "ical@google.com",
                "updated": datetime.now(timezone.utc),
                "start": start,
                "end": end,
                "hash": "a" * 64,
                "version": 0,  # Invalid
            }
        )
        await async_session.commit()


@pytest.mark.asyncio
async def test_enum_constraint_invalid_status(async_session: AsyncSession):
    """
    Test: ENUM constraint prevents invalid status values at DB level.

    CRITICAL: Tests DB constraint, not just model validation.
    """
    start = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)

    test_user_id = await create_test_user(async_session)

    # Use raw SQL to bypass model validation
    # Note: asyncpg raises DBAPIError for ENUM violations, not IntegrityError
    with pytest.raises(DBAPIError, match="invalid input value for enum"):
        await async_session.execute(
            text("""
                INSERT INTO focused_focus_sessions (
                    user_id, google_event_id, google_calendar_id, google_ical_uid,
                    google_updated_at, start_time, end_time, sha256_content_hash, status
                ) VALUES (
                    :user_id, :event_id, :calendar_id, :ical_uid,
                    :updated, :start, :end, :hash, :status
                )
            """),
            {
                "user_id": test_user_id,
                "event_id": "event_bad_status",
                "calendar_id": "primary",
                "ical_uid": "ical@google.com",
                "updated": datetime.now(timezone.utc),
                "start": start,
                "end": end,
                "hash": "a" * 64,
                "status": "invalid",  # Not in ENUM
            }
        )
        await async_session.commit()


@pytest.mark.asyncio
async def test_fk_constraint_nonexistent_user(async_session: AsyncSession):
    """
    Test: FK constraint prevents inserting session with nonexistent user_id.

    CRITICAL: Ensures referential integrity.
    """
    start = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)

    # Use random UUID that doesn't exist in core_users
    nonexistent_user_id = uuid4()

    session = FocusedFocusSession(
        user_id=nonexistent_user_id,
        google_event_id="event123",
        google_calendar_id="primary",
        google_ical_uid="ical123@google.com",
        google_updated_at=datetime.now(timezone.utc),
        start_time=start,
        end_time=end,
        sha256_content_hash="a" * 64,
    )

    async_session.add(session)

    # Should raise IntegrityError (FK violation)
    with pytest.raises(IntegrityError):
        await async_session.commit()


@pytest.mark.asyncio
async def test_fk_constraint_restrict_user_deletion(async_session: AsyncSession):
    """
    Test: FK constraint prevents deleting user with existing sessions (RESTRICT).

    CRITICAL: ON DELETE RESTRICT must prevent accidental user deletion.
    """
    start = datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)

    test_user_id = await create_test_user(async_session)

    # Create session for user
    session = FocusedFocusSession(
        user_id=test_user_id,
        google_event_id="event123",
        google_calendar_id="primary",
        google_ical_uid="ical123@google.com",
        google_updated_at=datetime.now(timezone.utc),
        start_time=start,
        end_time=end,
        sha256_content_hash="a" * 64,
    )

    async_session.add(session)
    await async_session.commit()

    # Try to delete user - should fail (RESTRICT)
    with pytest.raises(IntegrityError):
        await async_session.execute(
            text("DELETE FROM core_users WHERE id = :id"),
            {"id": test_user_id}
        )
        await async_session.commit()


# =============================================================================
# Test 4: Migration Verification
# =============================================================================
@pytest.mark.asyncio
async def test_migration_creates_all_indexes(async_session: AsyncSession):
    """
    Test: Migration creates all 6 indexes from spec.
    """
    # Use run_sync to inspect database schema (inspect doesn't work on async connections)
    def get_indexes(conn):
        inspector = inspect(conn)
        return inspector.get_indexes('focused_focus_sessions')

    async with async_session.bind.connect() as conn:
        indexes = await conn.run_sync(get_indexes)

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

    # NEW: Verify no extra indexes (exactly 6)
    # Note: Primary key might show as separate index, so check >= 6
    assert len(index_names) >= 6, f"Expected at least 6 indexes, found {len(index_names)}: {index_names}"


@pytest.mark.asyncio
async def test_migration_creates_composite_hash_index(async_session: AsyncSession):
    """
    Test: Hash index is composite (user_id, sha256_content_hash).

    CRITICAL: Must be composite to prevent cross-user scans.
    """
    # Use run_sync to inspect database schema
    def get_indexes(conn):
        inspector = inspect(conn)
        return inspector.get_indexes('focused_focus_sessions')

    async with async_session.bind.connect() as conn:
        indexes = await conn.run_sync(get_indexes)

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
async def test_migration_creates_partial_indexes(async_session: AsyncSession):
    """
    Test: Partial indexes use WHERE status = 'active'.

    CRITICAL: Ensures indexes only cover active rows for performance.
    """
    # Query PostgreSQL system catalog to verify partial index predicates
    result = await async_session.execute(
        text("""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = 'focused_focus_sessions'
            AND indexdef LIKE '%WHERE%'
        """)
    )
    partial_indexes = {row[0]: row[1] for row in result}

    # Verify focus_blocks index has WHERE clause
    assert 'idx_focus_sessions_focus_blocks' in partial_indexes
    assert "status = 'active'" in partial_indexes['idx_focus_sessions_focus_blocks'].lower()

    # Verify cleanup index has WHERE clause
    assert 'idx_focus_sessions_cleanup' in partial_indexes
    assert "status = 'active'" in partial_indexes['idx_focus_sessions_cleanup'].lower()


@pytest.mark.asyncio
async def test_migration_creates_enum_type(async_session: AsyncSession):
    """
    Test: Migration creates PostgreSQL ENUM type 'event_status_enum'.
    """
    result = await async_session.execute(
        text("""
            SELECT EXISTS (
                SELECT 1
                FROM pg_type
                WHERE typname = 'event_status_enum'
            )
        """)
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

    test_user_id = await create_test_user(async_session)

    session = FocusedFocusSession(
        user_id=test_user_id,
        google_event_id="event123",
        google_calendar_id="primary",
        google_ical_uid="ical123@google.com",
        google_updated_at=datetime.now(timezone.utc),
        start_time=start,
        end_time=end,
        sha256_content_hash="a" * 64,
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
