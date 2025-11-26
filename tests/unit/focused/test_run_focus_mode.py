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
    DEFAULT_FOCUS_NAME,
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

    @pytest.mark.asyncio
    async def test_default_focus_name_is_work(self, mock_session, valid_user_id):
        """Test that default focus_name is 'Work'."""
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
                focus_name=None,  # Not specified
                user_confirmation=True,
            )

        assert result["focus_name"] == DEFAULT_FOCUS_NAME
