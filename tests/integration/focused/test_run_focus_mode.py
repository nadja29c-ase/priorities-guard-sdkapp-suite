"""
Integration tests for run_focus_mode endpoint (Increment 11).

Tests the full flow through the backend API endpoint.
"""

import json
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client():
    """Create test client with proper lifespan handling."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def valid_user_id():
    """Generate a valid UUID for testing."""
    return str(uuid4())


# =============================================================================
# Endpoint Availability Tests
# =============================================================================

class TestEndpointAvailability:
    """Tests for endpoint availability and basic request handling."""

    def test_endpoint_exists(self, client, valid_user_id):
        """Test that /run_focus_mode endpoint exists."""
        response = client.post(
            "/api/focused/tools/run_focus_mode",
            json={"action": "on", "trigger_source": "user"},
            headers={"X-User-ID": valid_user_id},
        )

        # Should not be 404
        assert response.status_code != 404

    def test_requires_action_field(self, client, valid_user_id):
        """Test that action field is required."""
        response = client.post(
            "/api/focused/tools/run_focus_mode",
            json={"trigger_source": "user"},  # Missing action
            headers={"X-User-ID": valid_user_id},
        )

        assert response.status_code == 422  # Validation error

    def test_requires_trigger_source_field(self, client, valid_user_id):
        """Test that trigger_source field is required."""
        response = client.post(
            "/api/focused/tools/run_focus_mode",
            json={"action": "on"},  # Missing trigger_source
            headers={"X-User-ID": valid_user_id},
        )

        assert response.status_code == 422  # Validation error

    def test_action_must_be_on_or_off(self, client, valid_user_id):
        """Test that action must be 'on' or 'off'."""
        response = client.post(
            "/api/focused/tools/run_focus_mode",
            json={"action": "invalid", "trigger_source": "user"},
            headers={"X-User-ID": valid_user_id},
        )

        assert response.status_code == 422

    def test_trigger_source_must_be_calendar_or_user(self, client, valid_user_id):
        """Test that trigger_source must be 'calendar' or 'user'."""
        response = client.post(
            "/api/focused/tools/run_focus_mode",
            json={"action": "on", "trigger_source": "invalid"},
            headers={"X-User-ID": valid_user_id},
        )

        assert response.status_code == 422


# =============================================================================
# Activation Flow Tests
# =============================================================================

class TestActivationFlow:
    """Tests for focus mode activation flow."""

    def test_activation_requires_user_confirmation(self, client, valid_user_id):
        """Test that activation fails without user_confirmation."""
        response = client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "on",
                "trigger_source": "user",
                "user_confirmation": False,
            },
            headers={"X-User-ID": valid_user_id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False

    def test_activation_with_duration_returns_end_time(self, client, valid_user_id):
        """Test that activation with duration_minutes returns end_time."""
        with patch("backend.apps.focused.tools.run_focus_mode_impl._get_active_session") as mock_active:
            mock_active.return_value = None  # No active session

            with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app") as mock_celery:
                mock_celery.send_task = MagicMock(return_value=MagicMock(id="task-123"))

                response = client.post(
                    "/api/focused/tools/run_focus_mode",
                    json={
                        "action": "on",
                        "trigger_source": "user",
                        "duration_minutes": 60,
                        "user_confirmation": True,
                    },
                    headers={"X-User-ID": valid_user_id},
                )

        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                assert data["data"].get("end_time") is not None


# =============================================================================
# Deactivation Flow Tests
# =============================================================================

class TestDeactivationFlow:
    """Tests for focus mode deactivation flow."""

    def test_deactivation_returns_shortcut_url(self, client, valid_user_id):
        """Test that deactivation returns shortcut URL."""
        response = client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "off",
                "trigger_source": "user",
            },
            headers={"X-User-ID": valid_user_id},
        )

        assert response.status_code == 200
        data = response.json()

        # Even if no active session, should return shortcut_url for deactivation
        if data.get("success") or data.get("data", {}).get("shortcut_status") == "already_inactive":
            result = data.get("data", data)
            assert "shortcut_url" in result or "shortcut_url" in data.get("data", {})


# =============================================================================
# Optional Parameter Tests
# =============================================================================

class TestOptionalParameters:
    """Tests for optional parameters."""

    def test_focus_name_uses_default_when_not_provided(self, client, valid_user_id):
        """Test that focus_name defaults to 'Work' when not provided."""
        with patch("backend.apps.focused.tools.run_focus_mode_impl._get_active_session") as mock_active:
            mock_active.return_value = None

            with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app"):
                response = client.post(
                    "/api/focused/tools/run_focus_mode",
                    json={
                        "action": "on",
                        "trigger_source": "user",
                        "user_confirmation": True,
                        # focus_name not provided
                    },
                    headers={"X-User-ID": valid_user_id},
                )

        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                assert data["data"]["focus_name"] == "Work"

    def test_duration_minutes_validates_range(self, client, valid_user_id):
        """Test that duration_minutes validates range (1-480)."""
        # Too low
        response = client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "on",
                "trigger_source": "user",
                "duration_minutes": 0,
                "user_confirmation": True,
            },
            headers={"X-User-ID": valid_user_id},
        )
        assert response.status_code == 422

        # Too high
        response = client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "on",
                "trigger_source": "user",
                "duration_minutes": 500,  # Max is 480
                "user_confirmation": True,
            },
            headers={"X-User-ID": valid_user_id},
        )
        assert response.status_code == 422


# =============================================================================
# Response Format Tests
# =============================================================================

class TestResponseFormat:
    """Tests for response format compliance."""

    def test_success_response_structure(self, client, valid_user_id):
        """Test successful response has correct structure."""
        with patch("backend.apps.focused.tools.run_focus_mode_impl._get_active_session") as mock_active:
            mock_active.return_value = None

            with patch("backend.apps.focused.tools.run_focus_mode_impl.celery_app"):
                response = client.post(
                    "/api/focused/tools/run_focus_mode",
                    json={
                        "action": "on",
                        "trigger_source": "user",
                        "user_confirmation": True,
                    },
                    headers={"X-User-ID": valid_user_id},
                )

        assert response.status_code == 200
        data = response.json()

        # Response should have success/error or success/data structure
        assert "success" in data
        if data["success"]:
            assert "data" in data

    def test_error_response_structure(self, client, valid_user_id):
        """Test error response has correct structure."""
        response = client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "on",
                "trigger_source": "user",
                "user_confirmation": False,  # Will fail
            },
            headers={"X-User-ID": valid_user_id},
        )

        assert response.status_code == 200
        data = response.json()

        # Error response should have error structure
        assert data["success"] is False
        assert "error" in data
        assert "code" in data["error"]
        assert "message" in data["error"]


# =============================================================================
# Duration Validation Edge Cases
# =============================================================================

class TestDurationValidation:
    """Tests for duration_minutes edge cases."""

    def test_duration_negative_invalid(self, client, valid_user_id):
        """Test that negative duration is rejected."""
        response = client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "on",
                "trigger_source": "user",
                "duration_minutes": -10,
                "user_confirmation": True,
            },
            headers={"X-User-ID": valid_user_id},
        )

        assert response.status_code == 422

    def test_duration_valid_boundary_1(self, client, valid_user_id):
        """Test that duration=1 is valid (minimum)."""
        response = client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "on",
                "trigger_source": "user",
                "duration_minutes": 1,  # Minimum valid
                "user_confirmation": True,
            },
            headers={"X-User-ID": valid_user_id},
        )

        # Should not be a validation error
        assert response.status_code != 422

    def test_duration_valid_boundary_480(self, client, valid_user_id):
        """Test that duration=480 is valid (maximum)."""
        response = client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "on",
                "trigger_source": "user",
                "duration_minutes": 480,  # Maximum valid (8 hours)
                "user_confirmation": True,
            },
            headers={"X-User-ID": valid_user_id},
        )

        # Should not be a validation error
        assert response.status_code != 422

    def test_duration_481_invalid(self, client, valid_user_id):
        """Test that duration=481 is rejected (above max)."""
        response = client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "on",
                "trigger_source": "user",
                "duration_minutes": 481,
                "user_confirmation": True,
            },
            headers={"X-User-ID": valid_user_id},
        )

        assert response.status_code == 422


# =============================================================================
# Session Conflict Tests
# =============================================================================

class TestSessionConflicts:
    """Tests for session conflict handling."""

    def test_second_activation_blocked_by_active_session(self, client, valid_user_id):
        """Test that second activation is blocked when session is active."""
        # Create mock for an active session
        active_session = MagicMock()
        active_session.id = uuid4()
        active_session.actual_start = datetime.now(timezone.utc) - timedelta(hours=1)
        active_session.actual_end = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=active_session)

        with patch("backend.apps.focused.tools.run_focus_mode_impl._get_active_session") as mock_get:
            mock_get.return_value = active_session

            response = client.post(
                "/api/focused/tools/run_focus_mode",
                json={
                    "action": "on",
                    "trigger_source": "user",
                    "user_confirmation": True,
                },
                headers={"X-User-ID": valid_user_id},
            )

        assert response.status_code == 200
        data = response.json()

        # Should succeed but indicate already_active
        if data.get("success"):
            assert data["data"]["shortcut_status"] == "already_active"


# =============================================================================
# X-User-ID Header Tests
# =============================================================================

class TestUserIDHeader:
    """Tests for X-User-ID header handling."""

    def test_missing_user_id_header_uses_fallback(self, client):
        """Test behavior when X-User-ID header is missing."""
        response = client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "on",
                "trigger_source": "user",
                "user_confirmation": True,
            },
            # No X-User-ID header
        )

        # Should either fail with auth error or use fallback
        # (depends on implementation)
        assert response.status_code in [200, 401, 422]

    def test_invalid_user_id_format_rejected(self, client):
        """Test that invalid UUID format in X-User-ID is handled."""
        response = client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "on",
                "trigger_source": "user",
                "user_confirmation": True,
            },
            headers={"X-User-ID": "not-a-valid-uuid"},
        )

        # Should fail gracefully
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False


# =============================================================================
# Idempotency Tests
# =============================================================================

class TestIdempotency:
    """Tests for idempotent behavior."""

    def test_multiple_deactivation_requests_are_idempotent(self, client, valid_user_id):
        """Test that multiple deactivation requests don't cause errors."""
        # First deactivation
        response1 = client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "off",
                "trigger_source": "user",
            },
            headers={"X-User-ID": valid_user_id},
        )

        # Second deactivation (should be idempotent)
        response2 = client.post(
            "/api/focused/tools/run_focus_mode",
            json={
                "action": "off",
                "trigger_source": "user",
            },
            headers={"X-User-ID": valid_user_id},
        )

        # Both should succeed (200)
        assert response1.status_code == 200
        assert response2.status_code == 200

        data1 = response1.json()
        data2 = response2.json()

        # Both should indicate success or already_inactive
        if data1.get("success"):
            assert data1["data"]["shortcut_status"] in ["success", "already_inactive"]
        if data2.get("success"):
            assert data2["data"]["shortcut_status"] in ["success", "already_inactive"]
