"""
Integration tests for run_focus_mode endpoint (Increment 11).

Tests the full flow through the backend API endpoint with REAL database.
Only external services (Celery) are mocked.
"""

import hashlib
import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
from uuid import uuid4, UUID

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.focused.db_models import (
    FocusedFocusSession,
    FocusedScheduledJob,
)
from backend.core.models import CoreUser as User


def _make_content_hash(user_id: UUID, timestamp: datetime) -> str:
    """Generate content hash for test fixtures."""
    content = f"test:{user_id}:{timestamp.isoformat()}"
    return hashlib.sha256(content.encode()).hexdigest()


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest_asyncio.fixture
async def test_user(async_session: AsyncSession):
    """Create a test user in the database."""
    user = User(id=uuid4())
    async_session.add(user)
    await async_session.commit()
    return user


@pytest_asyncio.fixture
async def active_session(async_session: AsyncSession, test_user: User):
    """Create an active focus session for the test user."""
    now = datetime.now(timezone.utc) - timedelta(hours=1)

    session = FocusedFocusSession(
        id=uuid4(),
        user_id=test_user.id,
        google_event_id=None,
        google_calendar_id="primary",
        google_ical_uid=None,
        event_summary="Work",
        start_time=now,
        end_time=now + timedelta(hours=2),
        is_focus_block=True,
        sha256_content_hash=_make_content_hash(test_user.id, now),
        trigger_source="user",
        actual_start=now,
        actual_end=None,  # Active session
    )
    async_session.add(session)
    await async_session.commit()
    return session


# =============================================================================
# Endpoint Availability Tests
# =============================================================================

class TestEndpointAvailability:
    """Tests for endpoint availability and basic request handling."""

    @pytest.mark.asyncio
    async def test_endpoint_exists(self, client: AsyncClient, test_user: User):
        """Test that /run_focus_mode endpoint exists."""
        response = await client.post(
            "/api/focused/tools/run_focus_mode",
            json={"action": "on", "trigger_source": "user"},
            headers={"X-User-ID": str(test_user.id)},
        )

        # Should not be 404
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_requires_action_field(self, client: AsyncClient, test_user: User):
        """Test that action field is required."""
        response = await client.post(
            "/api/focused/tools/run_focus_mode",
            json={"trigger_source": "user"},  # Missing action
            headers={"X-User-ID": str(test_user.id)},
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_requires_trigger_source_field(self, client: AsyncClient, test_user: User):
        """Test that trigger_source field is required."""
        response = await client.post(
            "/api/focused/tools/run_focus_mode",
            json={"action": "on"},  # Missing trigger_source
            headers={"X-User-ID": str(test_user.id)},
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_action_must_be_on_or_off(self, client: AsyncClient, test_user: User):
        """Test that action must be 'on' or 'off'."""
        response = await client.post(
            "/api/focused/tools/run_focus_mode",
            json={"action": "invalid", "trigger_source": "user"},
            headers={"X-User-ID": str(test_user.id)},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_trigger_source_must_be_calendar_or_user(self, client: AsyncClient, test_user: User):
        """Test that trigger_source must be 'calendar' or 'user'."""
        response = await client.post(
            "/api/focused/tools/run_focus_mode",
            json={"action": "on", "trigger_source": "invalid"},
            headers={"X-User-ID": str(test_user.id)},
        )

        assert response.status_code == 422


# =============================================================================
# Activation Flow Tests (Real DB)
# =============================================================================

class TestActivationFlow:
    """Tests for focus mode activation flow with real database."""

    @pytest.mark.asyncio
    async def test_activation_requires_user_confirmation(self, client: AsyncClient, test_user: User):
        """Test that activation fails without user_confirmation."""
        response = await client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "on",
                "trigger_source": "user",
                "user_confirmation": False,
            },
            headers={"X-User-ID": str(test_user.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_activation_creates_session_in_db(
        self, client: AsyncClient, async_session: AsyncSession, test_user: User
    ):
        """Test that activation creates a real focus session in the database."""
        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app") as mock_celery:
            mock_celery.send_task = MagicMock(return_value=MagicMock(id="task-123"))

            response = await client.post(
                "/api/focused/tools/run_focus_mode",
                json={
                    "action": "on",
                    "trigger_source": "user",
                    "session_title": "Deep Work",
                    "user_confirmation": True,
                },
                headers={"X-User-ID": str(test_user.id)},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify session was created in DB
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.user_id == test_user.id,
                FocusedFocusSession.actual_end.is_(None),
            )
        )
        session = result.scalar_one_or_none()

        assert session is not None
        assert session.event_summary == "Deep Work"
        assert session.trigger_source == "user"
        assert session.actual_start is not None
        assert session.actual_end is None

    @pytest.mark.asyncio
    async def test_activation_with_duration_creates_scheduled_job(
        self, client: AsyncClient, async_session: AsyncSession, test_user: User
    ):
        """Test that activation with duration creates a scheduled job in DB."""
        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app") as mock_celery:
            mock_celery.send_task = MagicMock(return_value=MagicMock(id="celery-task-456"))

            response = await client.post(
                "/api/focused/tools/run_focus_mode",
                json={
                    "action": "on",
                    "trigger_source": "user",
                    "duration_minutes": 60,
                    "user_confirmation": True,
                },
                headers={"X-User-ID": str(test_user.id)},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify scheduled job was created
        result = await async_session.execute(
            select(FocusedScheduledJob).where(
                FocusedScheduledJob.user_id == test_user.id,
                FocusedScheduledJob.job_type == "focus_deactivate",
            )
        )
        job = result.scalar_one_or_none()

        assert job is not None
        assert job.status == "pending"
        assert job.celery_task_id == "celery-task-456"

    @pytest.mark.asyncio
    async def test_second_activation_blocked_by_active_session(
        self, client: AsyncClient, test_user: User, active_session: FocusedFocusSession
    ):
        """Test that second activation is blocked when session already active."""
        # active_session fixture creates an active session for test_user
        _ = active_session  # Mark as used

        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app"):
            response = await client.post(
                "/api/focused/tools/run_focus_mode",
                json={
                    "action": "on",
                    "trigger_source": "user",
                    "user_confirmation": True,
                },
                headers={"X-User-ID": str(test_user.id)},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["shortcut_status"] == "already_active"


# =============================================================================
# Deactivation Flow Tests (Real DB)
# =============================================================================

class TestDeactivationFlow:
    """Tests for focus mode deactivation flow with real database."""

    @pytest.mark.asyncio
    async def test_deactivation_closes_active_session(
        self, client: AsyncClient, async_session: AsyncSession, test_user: User, active_session: FocusedFocusSession
    ):
        """Test that deactivation sets actual_end on active session."""
        response = await client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "off",
                "trigger_source": "user",
                "session_id": str(active_session.id),
            },
            headers={"X-User-ID": str(test_user.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Refresh session from DB
        await async_session.refresh(active_session)

        # Verify session was closed
        assert active_session.actual_end is not None

    @pytest.mark.asyncio
    async def test_deactivation_without_active_session_returns_already_inactive(
        self, client: AsyncClient, test_user: User
    ):
        """Test that deactivation with no active session returns already_inactive."""
        response = await client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "off",
                "trigger_source": "user",
            },
            headers={"X-User-ID": str(test_user.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["shortcut_status"] == "already_inactive"
        assert "shortcut_url" in data["data"]

    @pytest.mark.asyncio
    async def test_deactivation_cancels_scheduled_job(
        self, client: AsyncClient, async_session: AsyncSession, test_user: User
    ):
        """Test that manual deactivation cancels any pending auto-deactivate job."""
        # First activate with duration
        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app") as mock_celery:
            mock_celery.send_task = MagicMock(return_value=MagicMock(id="celery-task-789"))

            activate_response = await client.post(
                "/api/focused/tools/run_focus_mode",
                json={
                    "action": "on",
                    "trigger_source": "user",
                    "duration_minutes": 60,
                    "user_confirmation": True,
                },
                headers={"X-User-ID": str(test_user.id)},
            )

        assert activate_response.status_code == 200
        assert activate_response.json()["success"] is True

        # Get the created session
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.user_id == test_user.id,
                FocusedFocusSession.actual_end.is_(None),
            )
        )
        session = result.scalar_one()

        # Now deactivate manually
        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app") as mock_celery:
            mock_celery.control = MagicMock()
            mock_celery.control.revoke = MagicMock()

            deactivate_response = await client.post(
                "/api/focused/tools/run_focus_mode",
                json={
                    "action": "off",
                    "trigger_source": "user",
                    "session_id": str(session.id),
                },
                headers={"X-User-ID": str(test_user.id)},
            )

            assert deactivate_response.status_code == 200
            assert deactivate_response.json()["success"] is True

            # Verify celery.control.revoke was called
            mock_celery.control.revoke.assert_called()


# =============================================================================
# Duration Validation Tests
# =============================================================================

class TestDurationValidation:
    """Tests for duration_minutes validation."""

    @pytest.mark.asyncio
    async def test_duration_negative_invalid(self, client: AsyncClient, test_user: User):
        """Test that negative duration is rejected."""
        response = await client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "on",
                "trigger_source": "user",
                "duration_minutes": -10,
                "user_confirmation": True,
            },
            headers={"X-User-ID": str(test_user.id)},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_duration_zero_invalid(self, client: AsyncClient, test_user: User):
        """Test that zero duration is rejected."""
        response = await client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "on",
                "trigger_source": "user",
                "duration_minutes": 0,
                "user_confirmation": True,
            },
            headers={"X-User-ID": str(test_user.id)},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_duration_1_valid(self, client: AsyncClient, test_user: User):
        """Test that duration=1 (minimum) is valid."""
        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app") as mock_celery:
            mock_celery.send_task = MagicMock(return_value=MagicMock(id="test-task-id"))
            response = await client.post(
                "/api/focused/tools/run_focus_mode",
                json={
                    "action": "on",
                    "trigger_source": "user",
                    "duration_minutes": 1,
                    "user_confirmation": True,
                },
                headers={"X-User-ID": str(test_user.id)},
            )

        assert response.status_code == 200
        assert response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_duration_480_valid(self, client: AsyncClient, test_user: User):
        """Test that duration=480 (maximum, 8 hours) is valid."""
        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app") as mock_celery:
            mock_celery.send_task = MagicMock(return_value=MagicMock(id="test-task-id"))
            response = await client.post(
                "/api/focused/tools/run_focus_mode",
                json={
                    "action": "on",
                    "trigger_source": "user",
                    "duration_minutes": 480,
                    "user_confirmation": True,
                },
                headers={"X-User-ID": str(test_user.id)},
            )

        assert response.status_code == 200
        assert response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_duration_481_invalid(self, client: AsyncClient, test_user: User):
        """Test that duration=481 (above max) is rejected."""
        response = await client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "on",
                "trigger_source": "user",
                "duration_minutes": 481,
                "user_confirmation": True,
            },
            headers={"X-User-ID": str(test_user.id)},
        )

        assert response.status_code == 422


# =============================================================================
# Response Format Tests
# =============================================================================

class TestResponseFormat:
    """Tests for response format compliance."""

    @pytest.mark.asyncio
    async def test_success_response_structure(self, client: AsyncClient, test_user: User):
        """Test successful response has correct structure."""
        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app"):
            response = await client.post(
                "/api/focused/tools/run_focus_mode",
                json={
                    "action": "on",
                    "trigger_source": "user",
                    "user_confirmation": True,
                },
                headers={"X-User-ID": str(test_user.id)},
            )

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True
        assert "data" in data

    @pytest.mark.asyncio
    async def test_error_response_structure(self, client: AsyncClient, test_user: User):
        """Test error response has correct structure."""
        response = await client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "on",
                "trigger_source": "user",
                "user_confirmation": False,  # Will fail
            },
            headers={"X-User-ID": str(test_user.id)},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is False
        assert "error" in data
        assert "code" in data["error"]
        assert "message" in data["error"]


# =============================================================================
# Idempotency Tests
# =============================================================================

class TestIdempotency:
    """Tests for idempotent behavior."""

    @pytest.mark.asyncio
    async def test_multiple_deactivation_requests_are_idempotent(
        self, client: AsyncClient, test_user: User
    ):
        """Test that multiple deactivation requests don't cause errors."""
        # First deactivation (no active session)
        response1 = await client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "off",
                "trigger_source": "user",
            },
            headers={"X-User-ID": str(test_user.id)},
        )

        # Second deactivation (should be idempotent)
        response2 = await client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "off",
                "trigger_source": "user",
            },
            headers={"X-User-ID": str(test_user.id)},
        )

        # Both should succeed (200)
        assert response1.status_code == 200
        assert response2.status_code == 200

        data1 = response1.json()
        data2 = response2.json()

        # Both should succeed with already_inactive status
        assert data1["success"] is True
        assert data1["data"]["shortcut_status"] == "already_inactive"
        assert data2["success"] is True
        assert data2["data"]["shortcut_status"] == "already_inactive"


# =============================================================================
# One Active Session Per User Tests
# =============================================================================

class TestOneActiveSessionPerUser:
    """Tests for the 'one active session per user' invariant."""

    @pytest.mark.asyncio
    async def test_only_one_session_created_on_activation(
        self, client: AsyncClient, async_session: AsyncSession, test_user: User
    ):
        """Test that activation creates exactly one session row."""
        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app"):
            response = await client.post(
                "/api/focused/tools/run_focus_mode",
                json={
                    "action": "on",
                    "trigger_source": "user",
                    "user_confirmation": True,
                },
                headers={"X-User-ID": str(test_user.id)},
            )

        assert response.status_code == 200
        assert response.json()["success"] is True

        # Count sessions for this user
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.user_id == test_user.id
            )
        )
        sessions = result.scalars().all()

        assert len(sessions) == 1

    @pytest.mark.asyncio
    async def test_user_cannot_have_two_active_sessions(
        self, client: AsyncClient, async_session: AsyncSession, test_user: User, active_session: FocusedFocusSession
    ):
        """Test that user cannot have two active sessions simultaneously."""
        # active_session fixture creates an active session for test_user
        _ = active_session  # Mark as used

        # Try to activate again
        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app"):
            response = await client.post(
                "/api/focused/tools/run_focus_mode",
                json={
                    "action": "on",
                    "trigger_source": "user",
                    "user_confirmation": True,
                },
                headers={"X-User-ID": str(test_user.id)},
            )

        assert response.status_code == 200
        data = response.json()
        # Should return success=True with already_active, not create a new session
        assert data["success"] is True
        assert data["data"]["shortcut_status"] == "already_active"

        # Count active sessions - should still be exactly one
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.user_id == test_user.id,
                FocusedFocusSession.actual_end.is_(None),
            )
        )
        active_sessions = result.scalars().all()

        assert len(active_sessions) == 1


# =============================================================================
# User ID Header Tests
# =============================================================================

class TestUserIDHeader:
    """Tests for X-User-ID header handling.

    NOTE: Current implementation returns 200 with success=False for invalid user IDs.
    Ideally this should return 401 Unauthorized, but that requires changes to
    extract_user_id() to raise an exception instead of using fallback chain.
    """

    @pytest.mark.asyncio
    async def test_invalid_user_id_format_rejected(self, client: AsyncClient):
        """Test that invalid UUID format in X-User-ID is rejected."""
        response = await client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "on",
                "trigger_source": "user",
                "user_confirmation": True,
            },
            headers={"X-User-ID": "not-a-valid-uuid"},
        )

        # Current behavior: returns 200 with success=False
        # TODO: Should return 401 Unauthorized
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "error" in data

    @pytest.mark.asyncio
    async def test_missing_user_id_header_rejected(self, client: AsyncClient):
        """Test that missing X-User-ID header is rejected."""
        response = await client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "on",
                "trigger_source": "user",
                "user_confirmation": True,
            },
            # No X-User-ID header
        )

        # Current behavior: falls back to "test_user" which is invalid UUID
        # TODO: Should return 401 Unauthorized
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "error" in data


# =============================================================================
# Calendar-Triggered Activation Tests
# =============================================================================

class TestCalendarTriggeredActivation:
    """Tests for calendar-triggered focus mode activation."""

    @pytest_asyncio.fixture
    async def calendar_session(self, async_session: AsyncSession, test_user: User):
        """Create a calendar-synced focus session (not yet activated)."""
        now = datetime.now(timezone.utc)
        session = FocusedFocusSession(
            id=uuid4(),
            user_id=test_user.id,
            google_event_id="test_event_1",
            google_calendar_id="primary",
            google_ical_uid="test_ical_1",
            event_summary="Meeting Focus",
            trigger_source="calendar",
            is_focus_block=True,
            start_time=now - timedelta(minutes=5),
            end_time=now + timedelta(hours=1),
            sha256_content_hash=_make_content_hash(test_user.id, now),
            actual_start=None,  # Not yet activated
            actual_end=None,
        )
        async_session.add(session)
        await async_session.commit()
        return session

    @pytest_asyncio.fixture
    async def other_user(self, async_session: AsyncSession):
        """Create another test user."""
        user = User(id=uuid4())
        async_session.add(user)
        await async_session.commit()
        return user

    @pytest.mark.asyncio
    async def test_calendar_activation_requires_session_id(
        self, client: AsyncClient, test_user: User
    ):
        """Test that calendar-triggered activation requires session_id."""
        response = await client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "on",
                "trigger_source": "calendar",
                "user_confirmation": True,  # Bypass confirmation check to test session_id requirement
                # Missing session_id
            },
            headers={"X-User-ID": str(test_user.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "session_id" in data["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_calendar_activation_rejects_wrong_owner(
        self, client: AsyncClient, async_session: AsyncSession, test_user: User, other_user: User
    ):
        """Test that calendar activation rejects session owned by different user."""
        # Create session owned by other_user
        now = datetime.now(timezone.utc)
        other_session = FocusedFocusSession(
            id=uuid4(),
            user_id=other_user.id,
            google_event_id="other_event",
            google_calendar_id="primary",
            google_ical_uid="other_ical",
            event_summary="Other's Meeting",
            trigger_source="calendar",
            is_focus_block=True,
            start_time=now,
            end_time=now + timedelta(hours=1),
            sha256_content_hash=_make_content_hash(other_user.id, now),
        )
        async_session.add(other_session)
        await async_session.commit()

        # Try to activate as test_user
        response = await client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "on",
                "trigger_source": "calendar",
                "session_id": str(other_session.id),
            },
            headers={"X-User-ID": str(test_user.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_calendar_activation_requires_is_focus_block_true(
        self, client: AsyncClient, async_session: AsyncSession, test_user: User
    ):
        """Test that calendar activation requires is_focus_block=True."""
        # Create session with is_focus_block=False
        now = datetime.now(timezone.utc)
        non_focus_session = FocusedFocusSession(
            id=uuid4(),
            user_id=test_user.id,
            google_event_id="non_focus_event",
            google_calendar_id="primary",
            google_ical_uid="non_focus_ical",
            event_summary="Regular Meeting",
            trigger_source="calendar",
            is_focus_block=False,  # Not a focus block
            start_time=now,
            end_time=now + timedelta(hours=1),
            sha256_content_hash=_make_content_hash(test_user.id, now),
        )
        async_session.add(non_focus_session)
        await async_session.commit()

        response = await client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "on",
                "trigger_source": "calendar",
                "session_id": str(non_focus_session.id),
            },
            headers={"X-User-ID": str(test_user.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_calendar_activation_preserves_planned_times(
        self, client: AsyncClient, async_session: AsyncSession, test_user: User, calendar_session: FocusedFocusSession
    ):
        """Test that calendar activation preserves start_time and end_time."""
        original_start_time = calendar_session.start_time
        original_end_time = calendar_session.end_time

        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app"):
            response = await client.post(
                "/api/focused/tools/run_focus_mode",
                json={
                    "action": "on",
                    "trigger_source": "calendar",
                    "session_id": str(calendar_session.id),
                    "user_confirmation": True,
                },
                headers={"X-User-ID": str(test_user.id)},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Refresh from DB
        await async_session.refresh(calendar_session)

        # Verify planned times are preserved
        assert calendar_session.start_time == original_start_time
        assert calendar_session.end_time == original_end_time
        # But actual_start is now set
        assert calendar_session.actual_start is not None

    @pytest.mark.asyncio
    async def test_calendar_activation_sets_actual_start(
        self, client: AsyncClient, async_session: AsyncSession, test_user: User, calendar_session: FocusedFocusSession
    ):
        """Test that calendar activation sets actual_start timestamp."""
        assert calendar_session.actual_start is None  # Precondition

        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app"):
            response = await client.post(
                "/api/focused/tools/run_focus_mode",
                json={
                    "action": "on",
                    "trigger_source": "calendar",
                    "session_id": str(calendar_session.id),
                    "user_confirmation": True,
                },
                headers={"X-User-ID": str(test_user.id)},
            )

        assert response.status_code == 200
        assert response.json()["success"] is True

        await async_session.refresh(calendar_session)
        assert calendar_session.actual_start is not None
        # Verify it's timezone-aware UTC
        assert calendar_session.actual_start.tzinfo is not None


# =============================================================================
# Manual vs Calendar Conflict Resolution Tests
# =============================================================================

class TestManualCalendarConflicts:
    """Tests for conflict resolution between manual and calendar activations."""

    @pytest_asyncio.fixture
    async def manual_active_session(self, async_session: AsyncSession, test_user: User):
        """Create an active manual focus session."""
        now = datetime.now(timezone.utc) - timedelta(minutes=30)
        session = FocusedFocusSession(
            id=uuid4(),
            user_id=test_user.id,
            google_calendar_id="primary",
            event_summary="Manual Focus",
            start_time=now,
            end_time=now + timedelta(hours=2),
            is_focus_block=True,
            sha256_content_hash=_make_content_hash(test_user.id, now),
            trigger_source="user",
            actual_start=now,
            actual_end=None,
        )
        async_session.add(session)
        await async_session.commit()
        return session

    @pytest_asyncio.fixture
    async def calendar_active_session(self, async_session: AsyncSession, test_user: User):
        """Create an active calendar focus session."""
        now = datetime.now(timezone.utc) - timedelta(minutes=30)
        session = FocusedFocusSession(
            id=uuid4(),
            user_id=test_user.id,
            google_event_id="cal_active_event",
            google_calendar_id="primary",
            google_ical_uid="cal_active_ical",
            event_summary="Calendar Focus",
            trigger_source="calendar",
            is_focus_block=True,
            start_time=now,
            end_time=now + timedelta(hours=1),
            sha256_content_hash=_make_content_hash(test_user.id, now),
            actual_start=now,
            actual_end=None,
        )
        async_session.add(session)
        await async_session.commit()
        return session

    @pytest_asyncio.fixture
    async def upcoming_calendar_session(self, async_session: AsyncSession, test_user: User):
        """Create an upcoming (not yet active) calendar focus session."""
        now = datetime.now(timezone.utc) + timedelta(hours=1)
        session = FocusedFocusSession(
            id=uuid4(),
            user_id=test_user.id,
            google_event_id="upcoming_event",
            google_calendar_id="primary",
            google_ical_uid="upcoming_ical",
            event_summary="Upcoming Meeting",
            trigger_source="calendar",
            is_focus_block=True,
            start_time=now,
            end_time=now + timedelta(hours=1),
            sha256_content_hash=_make_content_hash(test_user.id, now),
            actual_start=None,  # Not yet activated
            actual_end=None,
        )
        async_session.add(session)
        await async_session.commit()
        return session

    @pytest.mark.asyncio
    async def test_manual_active_blocks_calendar_activation(
        self, client: AsyncClient, async_session: AsyncSession, test_user: User, manual_active_session: FocusedFocusSession
    ):
        """Test that calendar activation is blocked when manual session is active."""
        # Create a calendar session to try to activate
        now = datetime.now(timezone.utc)
        calendar_session = FocusedFocusSession(
            id=uuid4(),
            user_id=test_user.id,
            google_event_id="blocked_event",
            google_calendar_id="primary",
            google_ical_uid="blocked_ical",
            event_summary="Meeting",
            trigger_source="calendar",
            is_focus_block=True,
            start_time=now,
            end_time=now + timedelta(hours=1),
            sha256_content_hash=_make_content_hash(test_user.id, now),
        )
        async_session.add(calendar_session)
        await async_session.commit()

        _ = manual_active_session  # Mark as used

        response = await client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "on",
                "trigger_source": "calendar",
                "session_id": str(calendar_session.id),
                "user_confirmation": True,
            },
            headers={"X-User-ID": str(test_user.id)},
        )

        assert response.status_code == 200
        data = response.json()
        # Should indicate that there's already an active session
        assert data["success"] is False or data["data"]["shortcut_status"] == "already_active"

    @pytest.mark.asyncio
    async def test_calendar_active_blocks_manual_activation(
        self, client: AsyncClient, test_user: User, calendar_active_session: FocusedFocusSession
    ):
        """Test that manual activation is blocked when calendar session is active."""
        _ = calendar_active_session  # Mark as used

        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app"):
            response = await client.post(
                "/api/focused/tools/run_focus_mode",
                json={
                    "action": "on",
                    "trigger_source": "user",
                    "user_confirmation": True,
                },
                headers={"X-User-ID": str(test_user.id)},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["shortcut_status"] == "already_active"

    @pytest.mark.asyncio
    async def test_manual_activation_allowed_with_upcoming_calendar_session(
        self, client: AsyncClient, test_user: User, upcoming_calendar_session: FocusedFocusSession
    ):
        """Test that manual activation is allowed when calendar session is upcoming (not active)."""
        _ = upcoming_calendar_session  # Mark as used - it exists but is not active

        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app"):
            response = await client.post(
                "/api/focused/tools/run_focus_mode",
                json={
                    "action": "on",
                    "trigger_source": "user",
                    "user_confirmation": True,
                },
                headers={"X-User-ID": str(test_user.id)},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["shortcut_status"] == "success"


# =============================================================================
# Scheduled Job DB Entry Tests
# =============================================================================

class TestScheduledJobDBEntries:
    """Tests for scheduled job database entries."""

    @pytest.mark.asyncio
    async def test_activation_with_duration_creates_job_with_correct_fields(
        self, client: AsyncClient, async_session: AsyncSession, test_user: User
    ):
        """Test that scheduled job has correct fields in DB."""
        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app") as mock_celery:
            mock_celery.send_task = MagicMock(return_value=MagicMock(id="celery-task-abc123"))

            response = await client.post(
                "/api/focused/tools/run_focus_mode",
                json={
                    "action": "on",
                    "trigger_source": "user",
                    "duration_minutes": 90,
                    "user_confirmation": True,
                },
                headers={"X-User-ID": str(test_user.id)},
            )

        assert response.status_code == 200
        assert response.json()["success"] is True

        # Query the scheduled job
        result = await async_session.execute(
            select(FocusedScheduledJob).where(
                FocusedScheduledJob.user_id == test_user.id
            )
        )
        job = result.scalar_one()

        # Verify all fields
        assert job.job_type == "focus_deactivate"
        assert job.status == "pending"
        assert job.celery_task_id == "celery-task-abc123"
        assert job.scheduled_at is not None
        # scheduled_at should be ~90 minutes from now
        expected_time = datetime.now(timezone.utc) + timedelta(minutes=90)
        time_diff = abs((job.scheduled_at - expected_time).total_seconds())
        assert time_diff < 60  # Within 1 minute tolerance

    @pytest.mark.asyncio
    async def test_deactivation_updates_job_status_to_cancelled(
        self, client: AsyncClient, async_session: AsyncSession, test_user: User
    ):
        """Test that manual deactivation updates job status to cancelled."""
        # Activate with duration
        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app") as mock_celery:
            mock_celery.send_task = MagicMock(return_value=MagicMock(id="celery-task-xyz"))

            await client.post(
                "/api/focused/tools/run_focus_mode",
                json={
                    "action": "on",
                    "trigger_source": "user",
                    "duration_minutes": 60,
                    "user_confirmation": True,
                },
                headers={"X-User-ID": str(test_user.id)},
            )

        # Get the session
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.user_id == test_user.id,
                FocusedFocusSession.actual_end.is_(None),
            )
        )
        session = result.scalar_one()

        # Deactivate manually
        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app") as mock_celery:
            mock_celery.control = MagicMock()
            mock_celery.control.revoke = MagicMock()

            await client.post(
                "/api/focused/tools/run_focus_mode",
                json={
                    "action": "off",
                    "trigger_source": "user",
                    "session_id": str(session.id),
                },
                headers={"X-User-ID": str(test_user.id)},
            )

        # Check job status
        result = await async_session.execute(
            select(FocusedScheduledJob).where(
                FocusedScheduledJob.user_id == test_user.id
            )
        )
        job = result.scalar_one()

        assert job.status == "cancelled"

    @pytest.mark.asyncio
    async def test_deactivation_calls_celery_revoke(
        self, client: AsyncClient, async_session: AsyncSession, test_user: User
    ):
        """Test that deactivation calls celery.control.revoke with correct task ID."""
        task_id = "celery-task-to-revoke"

        # Activate with duration
        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app") as mock_celery:
            mock_celery.send_task = MagicMock(return_value=MagicMock(id=task_id))

            await client.post(
                "/api/focused/tools/run_focus_mode",
                json={
                    "action": "on",
                    "trigger_source": "user",
                    "duration_minutes": 60,
                    "user_confirmation": True,
                },
                headers={"X-User-ID": str(test_user.id)},
            )

        # Get the session
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.user_id == test_user.id,
                FocusedFocusSession.actual_end.is_(None),
            )
        )
        session = result.scalar_one()

        # Deactivate and verify revoke is called with correct task ID
        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app") as mock_celery:
            mock_celery.control = MagicMock()
            mock_celery.control.revoke = MagicMock()

            await client.post(
                "/api/focused/tools/run_focus_mode",
                json={
                    "action": "off",
                    "trigger_source": "user",
                    "session_id": str(session.id),
                },
                headers={"X-User-ID": str(test_user.id)},
            )

            # Verify revoke was called with the task ID
            mock_celery.control.revoke.assert_called_once()
            call_args = mock_celery.control.revoke.call_args
            assert task_id in str(call_args)


# =============================================================================
# API Response Format Tests
# =============================================================================

class TestAPIResponseFormat:
    """Tests for API response format compliance."""

    @pytest.mark.asyncio
    async def test_success_response_has_required_structure(
        self, client: AsyncClient, test_user: User
    ):
        """Test that success response has { success: true, data: {...} }."""
        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app"):
            response = await client.post(
                "/api/focused/tools/run_focus_mode",
                json={
                    "action": "on",
                    "trigger_source": "user",
                    "user_confirmation": True,
                },
                headers={"X-User-ID": str(test_user.id)},
            )

        assert response.status_code == 200
        data = response.json()

        # Verify structure
        assert "success" in data
        assert data["success"] is True
        assert "data" in data
        assert isinstance(data["data"], dict)

        # Verify data fields
        assert "shortcut_status" in data["data"]
        assert "shortcut_url" in data["data"]
        assert "session_title" in data["data"]
        assert "message" in data["data"]

    @pytest.mark.asyncio
    async def test_error_response_has_required_structure(
        self, client: AsyncClient, test_user: User
    ):
        """Test that error response has { success: false, error: {code, message} }."""
        response = await client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "on",
                "trigger_source": "user",
                "user_confirmation": False,  # Will fail
            },
            headers={"X-User-ID": str(test_user.id)},
        )

        assert response.status_code == 200
        data = response.json()

        # Verify structure
        assert "success" in data
        assert data["success"] is False
        assert "error" in data
        assert isinstance(data["error"], dict)
        assert "code" in data["error"]
        assert "message" in data["error"]

    @pytest.mark.asyncio
    async def test_success_response_never_has_error_field(
        self, client: AsyncClient, test_user: User
    ):
        """Test that success response does not have 'error' field."""
        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app"):
            response = await client.post(
                "/api/focused/tools/run_focus_mode",
                json={
                    "action": "on",
                    "trigger_source": "user",
                    "user_confirmation": True,
                },
                headers={"X-User-ID": str(test_user.id)},
            )

        data = response.json()
        assert data["success"] is True
        assert "error" not in data

    @pytest.mark.asyncio
    async def test_error_response_never_has_data_field(
        self, client: AsyncClient, test_user: User
    ):
        """Test that error response does not have 'data' field."""
        response = await client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "on",
                "trigger_source": "user",
                "user_confirmation": False,
            },
            headers={"X-User-ID": str(test_user.id)},
        )

        data = response.json()
        assert data["success"] is False
        assert "data" not in data


# =============================================================================
# DB Transaction Error Handling Tests
# =============================================================================

class TestDBTransactionErrors:
    """Tests for database transaction error handling."""

    @pytest.mark.asyncio
    async def test_db_error_returns_error_response(
        self, client: AsyncClient, test_user: User
    ):
        """Test that database errors are surfaced through API."""
        with patch("backend.apps.focused.tools.run_focus_mode_impl._get_active_session") as mock:
            mock.side_effect = Exception("Database connection lost")

            response = await client.post(
                "/api/focused/tools/run_focus_mode",
                json={
                    "action": "on",
                    "trigger_source": "user",
                    "user_confirmation": True,
                },
                headers={"X-User-ID": str(test_user.id)},
            )

        # Must be either 500 (unhandled) or 200 with error (handled)
        assert response.status_code in (200, 500), f"Unexpected status: {response.status_code}"

        if response.status_code == 200:
            data = response.json()
            assert data["success"] is False
            assert "error" in data

    @pytest.mark.asyncio
    async def test_commit_failure_surfaces_error(
        self, client: AsyncClient, test_user: User
    ):
        """Test that commit failures are surfaced through API.

        NOTE: We patch the database module's get_db dependency to inject
        a session that fails on commit, since the endpoint creates its own session.
        """
        from unittest.mock import AsyncMock

        # Create a mock session that fails on commit
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()
        mock_session.commit = AsyncMock(side_effect=Exception("Commit failed"))

        async def mock_get_db():
            yield mock_session

        from backend.main import app
        from backend.core.database import get_db

        app.dependency_overrides[get_db] = mock_get_db

        try:
            with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app"):
                response = await client.post(
                    "/api/focused/tools/run_focus_mode",
                    json={
                        "action": "on",
                        "trigger_source": "user",
                        "user_confirmation": True,
                    },
                    headers={"X-User-ID": str(test_user.id)},
                )
        finally:
            # Restore original dependency
            app.dependency_overrides.pop(get_db, None)

        # Must be either 500 (unhandled) or 200 with error (handled)
        assert response.status_code in (200, 500), f"Unexpected status: {response.status_code}"

        if response.status_code == 200:
            data = response.json()
            assert data["success"] is False


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and unusual scenarios."""

    @pytest_asyncio.fixture
    async def zombie_calendar_session(self, async_session: AsyncSession, test_user: User):
        """Create a 'zombie' calendar session - planned time passed but never activated.

        This happens when a webhook was late or missed.
        """
        now = datetime.now(timezone.utc) - timedelta(hours=2)
        session = FocusedFocusSession(
            id=uuid4(),
            user_id=test_user.id,
            google_event_id="zombie_event",
            google_calendar_id="primary",
            google_ical_uid="zombie_ical",
            event_summary="Missed Meeting",
            trigger_source="calendar",
            is_focus_block=True,
            start_time=now,
            end_time=now + timedelta(hours=1),  # Already ended
            sha256_content_hash=_make_content_hash(test_user.id, now),
            actual_start=None,  # Never activated
            actual_end=None,
        )
        async_session.add(session)
        await async_session.commit()
        return session

    @pytest.mark.asyncio
    async def test_zombie_calendar_block_does_not_prevent_manual_activation(
        self, client: AsyncClient, test_user: User, zombie_calendar_session: FocusedFocusSession
    ):
        """Test that expired calendar blocks don't prevent manual activation.

        Zombie blocks (end_time < now, never activated) should be treated as inactive.
        """
        _ = zombie_calendar_session  # Mark as used

        with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app"):
            response = await client.post(
                "/api/focused/tools/run_focus_mode",
                json={
                    "action": "on",
                    "trigger_source": "user",
                    "user_confirmation": True,
                },
                headers={"X-User-ID": str(test_user.id)},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["shortcut_status"] == "success"

    @pytest.mark.asyncio
    async def test_deactivation_without_session_id_infers_active_session(
        self, client: AsyncClient, async_session: AsyncSession, test_user: User
    ):
        """Test that deactivation without session_id infers the active session.

        When user sends action=off without session_id, the backend should
        find and close the currently active session.
        """
        # Create an active manual session
        now = datetime.now(timezone.utc) - timedelta(minutes=30)
        active = FocusedFocusSession(
            id=uuid4(),
            user_id=test_user.id,
            google_calendar_id="primary",
            event_summary="Active Work",
            start_time=now,
            end_time=now + timedelta(hours=2),
            is_focus_block=True,
            sha256_content_hash=_make_content_hash(test_user.id, now),
            trigger_source="user",
            actual_start=now,
            actual_end=None,
        )
        async_session.add(active)
        await async_session.commit()

        # Deactivate WITHOUT specifying session_id
        response = await client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "off",
                "trigger_source": "user",
                # No session_id - backend should infer
            },
            headers={"X-User-ID": str(test_user.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["shortcut_status"] == "success"

        # Verify session was closed
        await async_session.refresh(active)
        assert active.actual_end is not None

    @pytest.mark.asyncio
    async def test_session_id_invalid_uuid_format_rejected(
        self, client: AsyncClient, test_user: User
    ):
        """Test that invalid session_id UUID format is rejected for calendar-triggered deactivation.

        Note: For user-triggered deactivation, session_id is ignored (finds active session by user).
        Only calendar-triggered operations validate the session_id format.
        """
        response = await client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "off",
                "trigger_source": "calendar",  # Calendar trigger validates session_id
                "session_id": "not-a-valid-uuid",
            },
            headers={"X-User-ID": str(test_user.id)},
        )

        # Should be 422 (validation error) or 200 with success=False
        assert response.status_code in (200, 422), f"Unexpected status: {response.status_code}"

        if response.status_code == 200:
            data = response.json()
            assert data["success"] is False
            assert "error" in data


# =============================================================================
# Calendar-Triggered Deactivation Tests
# =============================================================================

class TestCalendarTriggeredDeactivation:
    """Tests for calendar-triggered deactivation."""

    @pytest_asyncio.fixture
    async def active_calendar_session(self, async_session: AsyncSession, test_user: User):
        """Create an active calendar focus session."""
        now = datetime.now(timezone.utc) - timedelta(hours=1)
        session = FocusedFocusSession(
            id=uuid4(),
            user_id=test_user.id,
            google_event_id="cal_deact_event",
            google_calendar_id="primary",
            google_ical_uid="cal_deact_ical",
            event_summary="Meeting",
            trigger_source="calendar",
            is_focus_block=True,
            start_time=now,
            end_time=now + timedelta(hours=1),  # Ending now
            sha256_content_hash=_make_content_hash(test_user.id, now),
            actual_start=now,
            actual_end=None,  # Still active
        )
        async_session.add(session)
        await async_session.commit()
        return session

    @pytest.mark.asyncio
    async def test_calendar_deactivation_requires_session_id(
        self, client: AsyncClient, test_user: User, active_calendar_session: FocusedFocusSession
    ):
        """Test that calendar-triggered deactivation requires session_id."""
        _ = active_calendar_session  # Mark as used

        response = await client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "off",
                "trigger_source": "calendar",
                # Missing session_id
            },
            headers={"X-User-ID": str(test_user.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "session_id" in data["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_calendar_deactivation_closes_specific_session(
        self, client: AsyncClient, async_session: AsyncSession, test_user: User, active_calendar_session: FocusedFocusSession
    ):
        """Test that calendar deactivation closes only the specified session."""
        response = await client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "off",
                "trigger_source": "calendar",
                "session_id": str(active_calendar_session.id),
            },
            headers={"X-User-ID": str(test_user.id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

        # Verify session was closed
        await async_session.refresh(active_calendar_session)
        assert active_calendar_session.actual_end is not None

    @pytest.mark.asyncio
    async def test_calendar_deactivation_does_not_affect_manual_session(
        self, client: AsyncClient, async_session: AsyncSession, test_user: User
    ):
        """Test that calendar deactivation doesn't close a manual override session.

        If user manually activated while a calendar block was scheduled,
        calendar-triggered deactivation should NOT close the manual session.
        """
        # Create an active manual session (user override)
        manual_now = datetime.now(timezone.utc) - timedelta(minutes=30)
        manual_session = FocusedFocusSession(
            id=uuid4(),
            user_id=test_user.id,
            google_calendar_id="primary",
            event_summary="Manual Override",
            start_time=manual_now,
            end_time=manual_now + timedelta(hours=2),
            is_focus_block=True,
            sha256_content_hash=_make_content_hash(test_user.id, manual_now),
            trigger_source="user",
            actual_start=manual_now,
            actual_end=None,
        )
        async_session.add(manual_session)

        # Create a calendar session that was never activated
        cal_now = datetime.now(timezone.utc) - timedelta(hours=1)
        calendar_session = FocusedFocusSession(
            id=uuid4(),
            user_id=test_user.id,
            google_event_id="scheduled_event",
            google_calendar_id="primary",
            google_ical_uid="scheduled_ical",
            event_summary="Scheduled Meeting",
            trigger_source="calendar",
            is_focus_block=True,
            start_time=cal_now,
            end_time=cal_now + timedelta(hours=1),
            sha256_content_hash=_make_content_hash(test_user.id, cal_now),
            actual_start=None,  # Never activated (manual override took precedence)
            actual_end=None,
        )
        async_session.add(calendar_session)
        await async_session.commit()

        # Calendar deactivation for the never-activated calendar session
        response = await client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "off",
                "trigger_source": "calendar",
                "session_id": str(calendar_session.id),
            },
            headers={"X-User-ID": str(test_user.id)},
        )

        assert response.status_code == 200

        # Manual session should still be active
        await async_session.refresh(manual_session)
        assert manual_session.actual_end is None  # Still active
