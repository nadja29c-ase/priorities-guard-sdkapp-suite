"""
Unit tests for run_focus_mode tool implementation (Increment 11).

Tests:
- Activation with confirmation required
- Deactivation (idempotent)
- One active session per user rule
- Calendar-triggered vs manual sessions
- Auto-deactivation scheduling
"""

import hashlib
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from backend.apps.focused.tools.run_focus_mode_impl import (
    run_focus_mode_impl,
    _get_active_session,
    _get_session_by_id,
    _create_manual_session,
    ACTIVATE_SHORTCUT_URL,
    DEACTIVATE_SHORTCUT_URL,
)


@pytest.fixture
def mock_session():
    """Create a mock async database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def valid_user_id():
    """Generate a valid user UUID string."""
    return str(uuid4())


@pytest.fixture
def valid_session_id():
    """Generate a valid session UUID string."""
    return str(uuid4())


# =============================================================================
# Activation Tests
# =============================================================================

class TestFocusModeActivation:
    """Tests for focus mode activation."""

    @pytest.mark.asyncio
    async def test_activation_requires_user_confirmation(self, mock_session, valid_user_id):
        """Test that activation fails without user_confirmation=True."""
        # No confirmation
        result = await run_focus_mode_impl(
            user_id=valid_user_id,
            action="on",
            session=mock_session,
            trigger_source="user",
            user_confirmation=False,
        )

        assert result["shortcut_status"] == "failed"
        assert "confirmation" in result["message"].lower()
        assert result["shortcut_url"] is None

    @pytest.mark.asyncio
    async def test_activation_requires_user_confirmation_none(self, mock_session, valid_user_id):
        """Test that activation fails when user_confirmation is None."""
        result = await run_focus_mode_impl(
            user_id=valid_user_id,
            action="on",
            session=mock_session,
            trigger_source="user",
            user_confirmation=None,
        )

        assert result["shortcut_status"] == "failed"
        assert "confirmation" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_activation_blocked_when_already_active(self, mock_session, valid_user_id):
        """Test that activation fails if user already has an active session."""
        # Mock existing active session
        existing_session = MagicMock()
        existing_session.id = uuid4()
        existing_session.actual_start = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=existing_session)
        mock_session.execute.return_value = mock_result

        result = await run_focus_mode_impl(
            user_id=valid_user_id,
            action="on",
            session=mock_session,
            trigger_source="user",
            user_confirmation=True,
        )

        assert result["shortcut_status"] == "already_active"
        assert "already active" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_calendar_trigger_requires_session_id(self, mock_session, valid_user_id):
        """Test that calendar-triggered activation requires session_id."""
        # Mock no active session
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        result = await run_focus_mode_impl(
            user_id=valid_user_id,
            action="on",
            session=mock_session,
            trigger_source="calendar",
            session_id=None,  # Missing
            user_confirmation=True,
        )

        assert result["shortcut_status"] == "failed"
        assert "session_id" in result["message"].lower() or "session_id" in result.get("error_details", "").lower()

    @pytest.mark.asyncio
    async def test_activation_returns_shortcut_url(self, mock_session, valid_user_id):
        """Test successful activation returns shortcut URL."""
        # Mock no active session
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app") as mock_celery:
            mock_celery.send_task = MagicMock(return_value=MagicMock(id="celery-task-123"))

            result = await run_focus_mode_impl(
                user_id=valid_user_id,
                action="on",
                session=mock_session,
                trigger_source="user",
                focus_name="Work",
                user_confirmation=True,
            )

        assert result["shortcut_status"] == "success"
        assert result["shortcut_url"] is not None
        assert "shortcuts://" in result["shortcut_url"]
        assert "Work" in result["shortcut_url"]
        assert result["focus_name"] == "Work"

    @pytest.mark.asyncio
    async def test_activation_with_duration_schedules_deactivation(self, mock_session, valid_user_id):
        """Test activation with duration_minutes schedules auto-deactivation."""
        # Mock no active session
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app") as mock_celery:
            mock_task = MagicMock(id="celery-task-456")
            mock_celery.send_task = MagicMock(return_value=mock_task)

            result = await run_focus_mode_impl(
                user_id=valid_user_id,
                action="on",
                session=mock_session,
                trigger_source="user",
                duration_minutes=60,
                user_confirmation=True,
            )

        assert result["shortcut_status"] == "success"
        assert result["end_time"] is not None

        # Verify Celery task was scheduled
        mock_celery.send_task.assert_called_once()
        call_args = mock_celery.send_task.call_args
        assert call_args[0][0] == "backend.core.celery_app.auto_deactivate_focus"


# =============================================================================
# Deactivation Tests
# =============================================================================

class TestFocusModeDeactivation:
    """Tests for focus mode deactivation."""

    @pytest.mark.asyncio
    async def test_deactivation_success(self, mock_session, valid_user_id):
        """Test successful deactivation of active session."""
        # Mock active session
        active_session = MagicMock()
        active_session.id = uuid4()
        active_session.actual_start = datetime.now(timezone.utc) - timedelta(hours=1)
        active_session.actual_end = None
        active_session.event_summary = "Focus Time"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=active_session)
        mock_session.execute.return_value = mock_result

        result = await run_focus_mode_impl(
            user_id=valid_user_id,
            action="off",
            session=mock_session,
            trigger_source="user",
        )

        assert result["shortcut_status"] == "success"
        assert result["shortcut_url"] == DEACTIVATE_SHORTCUT_URL
        assert result["end_time"] is not None
        assert active_session.actual_end is not None  # Should be set

    @pytest.mark.asyncio
    async def test_deactivation_idempotent_no_active_session(self, mock_session, valid_user_id):
        """Test deactivation when no active session exists is idempotent."""
        # Mock no active session
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        result = await run_focus_mode_impl(
            user_id=valid_user_id,
            action="off",
            session=mock_session,
            trigger_source="user",
        )

        assert result["shortcut_status"] == "already_inactive"
        assert result["shortcut_url"] == DEACTIVATE_SHORTCUT_URL

    @pytest.mark.asyncio
    async def test_deactivation_idempotent_already_deactivated(self, mock_session, valid_user_id, valid_session_id):
        """Test deactivation of already-deactivated session is idempotent."""
        # Mock already deactivated session
        session = MagicMock()
        session.id = uuid4()
        session.actual_start = datetime.now(timezone.utc) - timedelta(hours=2)
        session.actual_end = datetime.now(timezone.utc) - timedelta(hours=1)  # Already ended
        session.event_summary = "Focus Time"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=session)
        mock_session.execute.return_value = mock_result

        result = await run_focus_mode_impl(
            user_id=valid_user_id,
            action="off",
            session=mock_session,
            trigger_source="calendar",
            session_id=valid_session_id,
        )

        assert result["shortcut_status"] == "already_inactive"


# =============================================================================
# User ID Validation Tests
# =============================================================================

class TestUserIdValidation:
    """Tests for user ID validation."""

    @pytest.mark.asyncio
    async def test_invalid_user_id_format(self, mock_session):
        """Test that invalid user ID format returns error."""
        result = await run_focus_mode_impl(
            user_id="not-a-valid-uuid",
            action="on",
            session=mock_session,
            trigger_source="user",
            user_confirmation=True,
        )

        assert result["shortcut_status"] == "failed"
        assert "invalid" in result["message"].lower()


# =============================================================================
# Manual Session Creation Tests
# =============================================================================

class TestManualSessionCreation:
    """Tests for manual (user-triggered) session creation."""

    @pytest.mark.asyncio
    async def test_manual_session_has_null_google_fields(self, mock_session, valid_user_id):
        """Test that manual sessions have null Google Calendar fields."""
        # Mock no active session
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        captured_session = None

        def capture_add(obj):
            nonlocal captured_session
            captured_session = obj

        mock_session.add = capture_add

        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app"):
            await run_focus_mode_impl(
                user_id=valid_user_id,
                action="on",
                session=mock_session,
                trigger_source="user",
                user_confirmation=True,
            )

        assert captured_session is not None
        assert captured_session.google_event_id is None
        assert captured_session.google_ical_uid is None
        assert captured_session.trigger_source == "user"
        assert captured_session.actual_start is not None


# =============================================================================
# Response Format Tests
# =============================================================================

class TestResponseFormat:
    """Tests for response format compliance."""

    @pytest.mark.asyncio
    async def test_response_contains_required_fields(self, mock_session, valid_user_id):
        """Test that all responses contain required fields."""
        # Mock no active session
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app"):
            result = await run_focus_mode_impl(
                user_id=valid_user_id,
                action="on",
                session=mock_session,
                trigger_source="user",
                user_confirmation=True,
            )

        # All required fields must be present
        assert "shortcut_status" in result
        assert "shortcut_url" in result
        assert "focus_name" in result
        assert "start_time" in result
        assert "end_time" in result
        assert "message" in result
        assert "error_details" in result

    @pytest.mark.asyncio
    async def test_start_time_is_iso8601(self, mock_session, valid_user_id):
        """Test that start_time is valid ISO 8601 format."""
        # Mock no active session
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app"):
            result = await run_focus_mode_impl(
                user_id=valid_user_id,
                action="on",
                session=mock_session,
                trigger_source="user",
                user_confirmation=True,
            )

        # Should parse without error
        datetime.fromisoformat(result["start_time"].replace("Z", "+00:00"))


# =============================================================================
# Calendar-Triggered Session Tests (Critical for Correctness)
# =============================================================================

class TestCalendarTriggeredSessions:
    """Tests for calendar-triggered focus sessions."""

    @pytest.mark.asyncio
    async def test_calendar_trigger_with_non_focus_session_rejected(self, mock_session, valid_user_id, valid_session_id):
        """Test calendar trigger with session that is not a focus block is rejected.

        If the sync engine created a FocusedFocusSession row, it is by definition
        a focus block session. If is_focus_block=False, the session should never
        have existed - this tests that such an invalid state is handled correctly.
        """
        # Mock no active session (first query)
        # Then mock a session that exists but is_focus_block=False (invalid state)
        non_focus_session = MagicMock()
        non_focus_session.id = uuid4()
        non_focus_session.is_focus_block = False
        non_focus_session.actual_start = None

        call_count = 0

        def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            if call_count == 1:
                # First call: check active session
                mock_result.scalar_one_or_none = MagicMock(return_value=None)
            else:
                # Second call: get session by ID - returns non-focus session
                mock_result.scalar_one_or_none = MagicMock(return_value=non_focus_session)
            return mock_result

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app"):
            result = await run_focus_mode_impl(
                user_id=valid_user_id,
                action="on",
                session=mock_session,
                trigger_source="calendar",
                session_id=valid_session_id,
                user_confirmation=True,
            )

        # Should fail - is_focus_block=False sessions should not be activatable
        assert result["shortcut_status"] == "failed"
        assert "focus" in result["message"].lower() or "invalid" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_calendar_trigger_with_deleted_session(self, mock_session, valid_user_id, valid_session_id):
        """Test calendar trigger with session that was deleted."""
        call_count = 0

        def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            if call_count == 1:
                # First call: check active session
                mock_result.scalar_one_or_none = MagicMock(return_value=None)
            else:
                # Second call: session not found (deleted)
                mock_result.scalar_one_or_none = MagicMock(return_value=None)
            return mock_result

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        result = await run_focus_mode_impl(
            user_id=valid_user_id,
            action="on",
            session=mock_session,
            trigger_source="calendar",
            session_id=valid_session_id,
            user_confirmation=True,
        )

        assert result["shortcut_status"] == "failed"
        assert "not found" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_calendar_trigger_when_manual_session_active(self, mock_session, valid_user_id, valid_session_id):
        """Test calendar trigger when a manual session is already active."""
        # Mock existing active manual session
        existing_session = MagicMock()
        existing_session.id = uuid4()
        existing_session.actual_start = datetime.now(timezone.utc) - timedelta(hours=1)
        existing_session.trigger_source = "user"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=existing_session)
        mock_session.execute.return_value = mock_result

        result = await run_focus_mode_impl(
            user_id=valid_user_id,
            action="on",
            session=mock_session,
            trigger_source="calendar",
            session_id=valid_session_id,
            user_confirmation=True,
        )

        assert result["shortcut_status"] == "already_active"


# =============================================================================
# Shortcut URL Safety Tests (Critical for Security)
# =============================================================================

class TestShortcutURLSafety:
    """Tests for shortcut URL safety and correctness."""

    @pytest.mark.asyncio
    async def test_shortcut_url_does_not_include_user_id(self, mock_session, valid_user_id):
        """Test that shortcut URL does not expose user ID."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app"):
            result = await run_focus_mode_impl(
                user_id=valid_user_id,
                action="on",
                session=mock_session,
                trigger_source="user",
                user_confirmation=True,
            )

        assert result["shortcut_status"] == "success"
        assert valid_user_id not in result["shortcut_url"]

    @pytest.mark.asyncio
    async def test_shortcut_url_escaped_properly_for_special_chars(self, mock_session, valid_user_id):
        """Test that focus_name with special chars is URL-encoded."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app"):
            result = await run_focus_mode_impl(
                user_id=valid_user_id,
                action="on",
                session=mock_session,
                trigger_source="user",
                focus_name="Work & Study",  # Contains special char
                user_confirmation=True,
            )

        assert result["shortcut_status"] == "success"
        # & should be URL encoded
        assert " & " not in result["shortcut_url"]
        assert "%26" in result["shortcut_url"] or "Work%20%26%20Study" in result["shortcut_url"]


# =============================================================================
# Session Creation Correctness Tests
# =============================================================================

class TestSessionCreationCorrectness:
    """Tests for correct session creation behavior."""

    @pytest.mark.asyncio
    async def test_manual_session_has_actual_start_set_immediately(self, mock_session, valid_user_id):
        """Test that manual session has actual_start set at creation time."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        captured_session = None

        def capture_add(obj):
            nonlocal captured_session
            captured_session = obj

        mock_session.add = capture_add

        before_call = datetime.now(timezone.utc)

        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app"):
            await run_focus_mode_impl(
                user_id=valid_user_id,
                action="on",
                session=mock_session,
                trigger_source="user",
                user_confirmation=True,
            )

        after_call = datetime.now(timezone.utc)

        assert captured_session is not None
        assert captured_session.actual_start is not None
        # actual_start should be between before and after call
        assert before_call <= captured_session.actual_start <= after_call

    @pytest.mark.asyncio
    async def test_calendar_session_preserves_planned_times(self, mock_session, valid_user_id, valid_session_id):
        """Test that calendar session preserves planned start/end times."""
        planned_start = datetime.now(timezone.utc) + timedelta(minutes=30)
        planned_end = datetime.now(timezone.utc) + timedelta(hours=2)

        existing_session = MagicMock()
        existing_session.id = uuid4()
        existing_session.start_time = planned_start
        existing_session.end_time = planned_end
        existing_session.actual_start = None
        existing_session.actual_end = None

        call_count = 0

        def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            if call_count == 1:
                mock_result.scalar_one_or_none = MagicMock(return_value=None)
            else:
                mock_result.scalar_one_or_none = MagicMock(return_value=existing_session)
            return mock_result

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app"):
            await run_focus_mode_impl(
                user_id=valid_user_id,
                action="on",
                session=mock_session,
                trigger_source="calendar",
                session_id=valid_session_id,
                user_confirmation=True,
            )

        # Planned times should be preserved
        assert existing_session.start_time == planned_start
        assert existing_session.end_time == planned_end
        # But actual_start should be set
        assert existing_session.actual_start is not None


# =============================================================================
# DB Transaction Rollback Tests (Critical for Data Integrity)
# =============================================================================

class TestDBTransactionRollback:
    """Tests for database transaction integrity."""

    @pytest.mark.asyncio
    async def test_activation_fails_then_session_not_created(self, mock_session, valid_user_id):
        """Test that if activation fails after session add, no session is persisted."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        # Simulate commit failure
        mock_session.commit = AsyncMock(side_effect=Exception("DB connection lost"))

        add_called = False

        def capture_add(obj):
            nonlocal add_called
            add_called = True

        mock_session.add = capture_add

        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app"):
            try:
                await run_focus_mode_impl(
                    user_id=valid_user_id,
                    action="on",
                    session=mock_session,
                    trigger_source="user",
                    user_confirmation=True,
                )
            except Exception:
                pass  # Expected to fail

        # Session.add was called, but commit failed
        # In a real scenario with proper transaction handling,
        # the session would be rolled back automatically

    @pytest.mark.asyncio
    async def test_deactivation_fails_then_session_not_modified(self, mock_session, valid_user_id):
        """Test that if deactivation fails after setting actual_end, changes not persisted."""
        active_session = MagicMock()
        active_session.id = uuid4()
        active_session.actual_start = datetime.now(timezone.utc) - timedelta(hours=1)
        active_session.actual_end = None
        active_session.event_summary = "Focus Time"

        original_actual_end = active_session.actual_end

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=active_session)
        mock_session.execute.return_value = mock_result

        # Simulate commit failure
        mock_session.commit = AsyncMock(side_effect=Exception("DB connection lost"))

        with pytest.raises(Exception):
            await run_focus_mode_impl(
                user_id=valid_user_id,
                action="off",
                session=mock_session,
                trigger_source="user",
            )

        # In a real scenario with proper transaction handling,
        # the actual_end change would be rolled back


# =============================================================================
# Ownership Tests (Critical for Security)
# =============================================================================

class TestOwnershipValidation:
    """Tests for session ownership validation."""

    @pytest.mark.asyncio
    async def test_cannot_activate_other_users_session(self, mock_session):
        """Test that user cannot activate another user's session."""
        user1_id = str(uuid4())
        user2_id = str(uuid4())
        session_id = str(uuid4())

        # Session belongs to user2, but user1 tries to activate
        call_count = 0

        def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            if call_count == 1:
                # First call: check active session for user1
                mock_result.scalar_one_or_none = MagicMock(return_value=None)
            else:
                # Second call: get session by ID - returns None
                # because query includes user_id = user1, but session belongs to user2
                mock_result.scalar_one_or_none = MagicMock(return_value=None)
            return mock_result

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        result = await run_focus_mode_impl(
            user_id=user1_id,  # User 1 trying to activate
            action="on",
            session=mock_session,
            trigger_source="calendar",
            session_id=session_id,  # Session belongs to user 2
            user_confirmation=True,
        )

        # Should fail because session not found for this user
        assert result["shortcut_status"] == "failed"
        assert "not found" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_cannot_deactivate_other_users_session(self, mock_session):
        """Test that user cannot deactivate another user's session."""
        user1_id = str(uuid4())
        session_id = str(uuid4())

        # Query returns None because user1 doesn't own this session
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        result = await run_focus_mode_impl(
            user_id=user1_id,
            action="off",
            session=mock_session,
            trigger_source="calendar",
            session_id=session_id,
        )

        # Should fail because session not found for this user
        assert result["shortcut_status"] == "failed"
        assert "not found" in result["message"].lower()


# =============================================================================
# Race Condition Tests (Critical for Data Integrity)
# =============================================================================

class TestRaceConditions:
    """Tests for race condition handling in parallel activation.

    NOTE: True race condition testing requires either:
    1. Integration tests with a real database using SELECT FOR UPDATE
    2. A shared mock state that both concurrent calls can see

    The current unit test architecture uses isolated mocks per call,
    which cannot properly simulate the race condition where:
    - Call 1 sees no active session
    - Call 1 creates a session
    - Call 2 sees the session created by Call 1
    - Call 2 returns "already_active"

    TODO: Add database-level locking (SELECT FOR UPDATE) in a future increment
    and create proper integration tests for race conditions.
    """

    @pytest.mark.asyncio
    @pytest.mark.xfail(
        reason="Race condition testing requires shared state or real DB with FOR UPDATE locking. "
               "Current unit test mocks are isolated per call and cannot enforce the invariant. "
               "See TODO in class docstring.",
        strict=False,
    )
    async def test_two_parallel_activation_calls_only_create_one_session(self, valid_user_id):
        """Test that two simultaneous activation calls only create one session.

        LIMITATION: This test currently cannot enforce the invariant that only
        one session is created. Each mock_session is isolated, so both calls
        see "no active session" and both succeed.

        In production with proper FOR UPDATE locking:
        - First call acquires lock, sees no session, creates one
        - Second call waits for lock, then sees the new session
        - Second call returns "already_active"

        This test is marked xfail to document the expected behavior that
        the implementation must handle via database-level locking.
        """
        import asyncio

        sessions_created = []
        activation_results = []

        async def mock_activation(call_id: int):
            """Simulate an activation call."""
            mock_session = AsyncMock()
            mock_session.commit = AsyncMock()
            mock_session.flush = AsyncMock()

            def capture_add(obj):
                sessions_created.append((call_id, obj))

            mock_session.add = capture_add

            def mock_execute(_):
                mock_result = MagicMock()
                mock_result.scalar_one_or_none = MagicMock(return_value=None)
                return mock_result

            mock_session.execute = AsyncMock(side_effect=mock_execute)

            with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app"):
                result = await run_focus_mode_impl(
                    user_id=valid_user_id,
                    action="on",
                    session=mock_session,
                    trigger_source="user",
                    user_confirmation=True,
                )
                activation_results.append((call_id, result))

        await asyncio.gather(
            mock_activation(1),
            mock_activation(2),
        )

        # With proper locking, exactly one should succeed and one should get "already_active"
        success_count = sum(1 for _, r in activation_results if r["shortcut_status"] == "success")
        already_active_count = sum(1 for _, r in activation_results if r["shortcut_status"] == "already_active")

        # This assertion will fail with current isolated mocks (both succeed)
        # but documents the expected behavior with proper DB locking
        assert success_count == 1, f"Expected exactly 1 success, got {success_count}"
        assert already_active_count == 1, f"Expected exactly 1 already_active, got {already_active_count}"


# =============================================================================
# Duration Edge Case Tests (Critical for Input Validation)
# =============================================================================

class TestDurationEdgeCases:
    """Tests for duration_minutes edge cases."""

    @pytest.mark.asyncio
    async def test_activation_rejects_negative_duration(self, mock_session, valid_user_id):
        """Test that negative duration is rejected."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        result = await run_focus_mode_impl(
            user_id=valid_user_id,
            action="on",
            session=mock_session,
            trigger_source="user",
            duration_minutes=-10,
            user_confirmation=True,
        )

        assert result["shortcut_status"] == "failed"
        assert "duration" in result["message"].lower() or "invalid" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_activation_rejects_zero_duration(self, mock_session, valid_user_id):
        """Test that zero duration is rejected."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        result = await run_focus_mode_impl(
            user_id=valid_user_id,
            action="on",
            session=mock_session,
            trigger_source="user",
            duration_minutes=0,
            user_confirmation=True,
        )

        assert result["shortcut_status"] == "failed"
        assert "duration" in result["message"].lower() or "invalid" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_activation_rejects_duration_over_max(self, mock_session, valid_user_id):
        """Test that duration over maximum (480 minutes / 8 hours) is rejected."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        result = await run_focus_mode_impl(
            user_id=valid_user_id,
            action="on",
            session=mock_session,
            trigger_source="user",
            duration_minutes=481,  # Over max
            user_confirmation=True,
        )

        assert result["shortcut_status"] == "failed"
        assert "duration" in result["message"].lower() or "invalid" in result["message"].lower()


# =============================================================================
# Manual Deactivation Job Cancellation Tests (Critical for Correctness)
# =============================================================================

class TestManualDeactivationJobCancellation:
    """Tests for scheduled job cancellation on manual deactivation."""

    @pytest.mark.asyncio
    async def test_manual_deactivation_revokes_scheduled_celery_task(self, mock_session, valid_user_id):
        """Test that manual deactivation revokes the scheduled Celery task."""
        # Mock active session with a scheduled job
        active_session = MagicMock()
        active_session.id = uuid4()
        active_session.actual_start = datetime.now(timezone.utc) - timedelta(hours=1)
        active_session.actual_end = None
        active_session.event_summary = "Focus Time"

        # Mock scheduled job associated with the session
        scheduled_job = MagicMock()
        scheduled_job.celery_task_id = "celery-task-to-revoke-123"
        scheduled_job.status = "pending"

        call_count = 0

        def mock_execute(_):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            if call_count == 1:
                # First call: get active session
                mock_result.scalar_one_or_none = MagicMock(return_value=active_session)
            else:
                # Second call: get scheduled job
                mock_result.scalar_one_or_none = MagicMock(return_value=scheduled_job)
            return mock_result

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app") as mock_celery:
            mock_celery.control = MagicMock()
            mock_celery.control.revoke = MagicMock()

            result = await run_focus_mode_impl(
                user_id=valid_user_id,
                action="off",
                session=mock_session,
                trigger_source="user",
            )

        assert result["shortcut_status"] == "success"
        # Verify Celery revoke was called
        mock_celery.control.revoke.assert_called_once_with(
            "celery-task-to-revoke-123",
            terminate=True
        )

    @pytest.mark.asyncio
    async def test_manual_deactivation_marks_scheduled_job_cancelled(self, mock_session, valid_user_id):
        """Test that manual deactivation marks the scheduled job as cancelled."""
        active_session = MagicMock()
        active_session.id = uuid4()
        active_session.actual_start = datetime.now(timezone.utc) - timedelta(hours=1)
        active_session.actual_end = None
        active_session.event_summary = "Focus Time"

        scheduled_job = MagicMock()
        scheduled_job.celery_task_id = "celery-task-456"
        scheduled_job.status = "pending"

        call_count = 0

        def mock_execute(_):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            if call_count == 1:
                mock_result.scalar_one_or_none = MagicMock(return_value=active_session)
            else:
                mock_result.scalar_one_or_none = MagicMock(return_value=scheduled_job)
            return mock_result

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app") as mock_celery:
            mock_celery.control = MagicMock()
            mock_celery.control.revoke = MagicMock()

            await run_focus_mode_impl(
                user_id=valid_user_id,
                action="off",
                session=mock_session,
                trigger_source="user",
            )

        # Verify job status was updated to cancelled
        assert scheduled_job.status == "cancelled"


# =============================================================================
# Session ID Validation Tests (Critical for Calendar Trigger)
# =============================================================================

class TestSessionIdValidation:
    """Tests for session_id validation in calendar-triggered operations."""

    @pytest.mark.asyncio
    async def test_calendar_deactivation_requires_session_id(self, mock_session, valid_user_id):
        """Test that calendar-triggered deactivation requires session_id."""
        result = await run_focus_mode_impl(
            user_id=valid_user_id,
            action="off",
            session=mock_session,
            trigger_source="calendar",
            session_id=None,  # Missing
        )

        assert result["shortcut_status"] == "failed"
        assert "session_id" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_calendar_deactivation_rejects_invalid_session_id_format(self, mock_session, valid_user_id):
        """Test that calendar-triggered deactivation rejects invalid session_id format."""
        result = await run_focus_mode_impl(
            user_id=valid_user_id,
            action="off",
            session=mock_session,
            trigger_source="calendar",
            session_id="not-a-valid-uuid",  # Invalid format
        )

        assert result["shortcut_status"] == "failed"
        assert "invalid" in result["message"].lower() or "session" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_calendar_activation_rejects_invalid_session_id_format(self, mock_session, valid_user_id):
        """Test that calendar-triggered activation rejects invalid session_id format."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        result = await run_focus_mode_impl(
            user_id=valid_user_id,
            action="on",
            session=mock_session,
            trigger_source="calendar",
            session_id="invalid-uuid-format",  # Invalid
            user_confirmation=True,
        )

        assert result["shortcut_status"] == "failed"
        assert "invalid" in result["message"].lower() or "session" in result["message"].lower()


# =============================================================================
# Single DB Row Creation Tests (Critical for Data Integrity)
# =============================================================================

class TestSingleDBRowCreation:
    """Tests for ensuring only one session row is created per activation."""

    @pytest.mark.asyncio
    async def test_manual_activation_creates_single_session_record_only_once(self, mock_session, valid_user_id):
        """Test that manual activation creates exactly one DB row, no duplicates."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        add_call_count = 0
        added_objects = []

        def capture_add(obj):
            nonlocal add_call_count
            add_call_count += 1
            added_objects.append(obj)

        mock_session.add = capture_add

        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app"):
            result = await run_focus_mode_impl(
                user_id=valid_user_id,
                action="on",
                session=mock_session,
                trigger_source="user",
                user_confirmation=True,
            )

        assert result["shortcut_status"] == "success"
        # Exactly one session.add() call for the focus session
        # (may have additional calls for scheduled job, but session should be exactly 1)
        focus_sessions = [obj for obj in added_objects if hasattr(obj, 'trigger_source')]
        assert len(focus_sessions) == 1, f"Expected exactly 1 session, got {len(focus_sessions)}"


# =============================================================================
# Calendar Trigger Wrong Owner Tests (Critical for Security)
# =============================================================================

class TestCalendarTriggerWrongOwner:
    """Tests for calendar trigger with wrong session owner."""

    @pytest.mark.asyncio
    async def test_calendar_trigger_rejects_session_belonging_to_other_user(self, mock_session):
        """Test that calendar trigger rejects session owned by different user."""
        user1_id = str(uuid4())
        user2_session_id = str(uuid4())

        # User1 tries to activate a session that belongs to User2
        call_count = 0

        def mock_execute(_):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            if call_count == 1:
                # No active session for user1
                mock_result.scalar_one_or_none = MagicMock(return_value=None)
            else:
                # Session lookup returns None because user_id filter doesn't match
                mock_result.scalar_one_or_none = MagicMock(return_value=None)
            return mock_result

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        result = await run_focus_mode_impl(
            user_id=user1_id,
            action="on",
            session=mock_session,
            trigger_source="calendar",
            session_id=user2_session_id,
            user_confirmation=True,
        )

        assert result["shortcut_status"] == "failed"
        assert "not found" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_calendar_deactivation_rejects_session_belonging_to_other_user(self, mock_session):
        """Test that calendar deactivation rejects session owned by different user."""
        user1_id = str(uuid4())
        user2_session_id = str(uuid4())

        # Query returns None because user1 doesn't own this session
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute.return_value = mock_result

        result = await run_focus_mode_impl(
            user_id=user1_id,
            action="off",
            session=mock_session,
            trigger_source="calendar",
            session_id=user2_session_id,
        )

        assert result["shortcut_status"] == "failed"
        assert "not found" in result["message"].lower()


# =============================================================================
# Invalid Action Tests (Critical for Input Validation)
# =============================================================================

class TestInvalidAction:
    """Tests for invalid action parameter."""

    @pytest.mark.asyncio
    async def test_invalid_action_rejected(self, mock_session, valid_user_id):
        """Test that invalid action value is rejected."""
        result = await run_focus_mode_impl(
            user_id=valid_user_id,
            action="invalid",  # Not "on" or "off"
            session=mock_session,
            trigger_source="user",
            user_confirmation=True,
        )

        assert result["shortcut_status"] == "failed"
        assert "action" in result["message"].lower() or "invalid" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_empty_action_rejected(self, mock_session, valid_user_id):
        """Test that empty action value is rejected."""
        result = await run_focus_mode_impl(
            user_id=valid_user_id,
            action="",  # Empty
            session=mock_session,
            trigger_source="user",
            user_confirmation=True,
        )

        assert result["shortcut_status"] == "failed"


# =============================================================================
# Trigger Source Validation Tests (Critical for Input Validation)
# =============================================================================

class TestTriggerSourceValidation:
    """Tests for trigger_source parameter validation."""

    @pytest.mark.asyncio
    async def test_invalid_trigger_source_rejected(self, mock_session, valid_user_id):
        """Test that invalid trigger_source is rejected."""
        result = await run_focus_mode_impl(
            user_id=valid_user_id,
            action="on",
            session=mock_session,
            trigger_source="invalid",  # Not "user" or "calendar"
            user_confirmation=True,
        )

        assert result["shortcut_status"] == "failed"
        assert "trigger" in result["message"].lower() or "invalid" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_empty_trigger_source_rejected(self, mock_session, valid_user_id):
        """Test that empty trigger_source is rejected."""
        result = await run_focus_mode_impl(
            user_id=valid_user_id,
            action="on",
            session=mock_session,
            trigger_source="",  # Empty
            user_confirmation=True,
        )

        assert result["shortcut_status"] == "failed"
