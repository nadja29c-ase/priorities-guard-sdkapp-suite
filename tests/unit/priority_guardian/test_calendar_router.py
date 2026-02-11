"""
Unit tests for calendar_router.py.

Tests the GET /calendar/time-allocation endpoint responses.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID

from fastapi.testclient import TestClient
from fastapi import FastAPI

from backend.apps.priority_guardian.routers.calendar_router import router, validate_user_id_header


# =============================================================================
# Test App Setup
# =============================================================================

def create_test_app():
    """Create a FastAPI app with the calendar router for testing."""
    app = FastAPI()
    app.include_router(router, prefix="/api/priority-guardian")

    # Mock the app state http_client
    app.state.http_client = AsyncMock()

    return app


# =============================================================================
# Header Validation Tests
# =============================================================================

class TestHeaderValidation:
    """Tests for X-User-ID header validation."""

    def test_missing_header_returns_401(self):
        """Missing X-User-ID header returns 401."""
        app = create_test_app()

        with patch(
            "backend.apps.priority_guardian.routers.calendar_router.compute_time_allocation",
            new_callable=AsyncMock,
        ):
            with TestClient(app) as client:
                response = client.get("/api/priority-guardian/calendar/time-allocation")

        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "UNAUTHORIZED"

    def test_invalid_uuid_returns_401(self):
        """Invalid UUID in X-User-ID header returns 401."""
        app = create_test_app()

        with patch(
            "backend.apps.priority_guardian.routers.calendar_router.compute_time_allocation",
            new_callable=AsyncMock,
        ):
            with TestClient(app) as client:
                response = client.get(
                    "/api/priority-guardian/calendar/time-allocation",
                    headers={"X-User-ID": "not-a-valid-uuid"}
                )

        assert response.status_code == 401
        assert "UUID" in response.json()["detail"]["message"]

    def test_valid_uuid_accepted(self):
        """Valid UUID in X-User-ID header is accepted."""
        app = create_test_app()
        user_id = str(uuid4())

        mock_allocation = {
            "keywords": {"P1": {"hours": 0.0, "event_count": 0}},
            "total_tracked_hours": 0.0,
        }

        with patch(
            "backend.apps.priority_guardian.routers.calendar_router.compute_time_allocation",
            new_callable=AsyncMock,
            return_value=mock_allocation,
        ), patch(
            "backend.apps.priority_guardian.routers.calendar_router.get_db",
            return_value=AsyncMock(),
        ):
            with TestClient(app) as client:
                response = client.get(
                    "/api/priority-guardian/calendar/time-allocation",
                    headers={"X-User-ID": user_id}
                )

        assert response.status_code == 200


# =============================================================================
# Success Response Tests
# =============================================================================

class TestSuccessResponses:
    """Tests for successful time allocation responses."""

    def test_returns_200_with_allocation_data(self):
        """Returns 200 with time allocation data."""
        app = create_test_app()
        user_id = str(uuid4())

        mock_allocation = {
            "week_start": "2026-02-09T00:00:00+01:00",
            "week_end": "2026-02-16T00:00:00+01:00",
            "timezone": "Europe/Berlin",
            "keywords": {
                "P1": {"hours": 10.5, "event_count": 6},
                "P2": {"hours": 3.0, "event_count": 2},
                "P3": {"hours": 0.0, "event_count": 0},
            },
            "other_hours": 18.25,
            "total_tracked_hours": 31.75,
            "total_events_scanned": 42,
            "bar_segments": {"P1": 10.5, "P2": 3.0, "P3": 0.0, "other": 18.25},
        }

        with patch(
            "backend.apps.priority_guardian.routers.calendar_router.compute_time_allocation",
            new_callable=AsyncMock,
            return_value=mock_allocation,
        ), patch(
            "backend.apps.priority_guardian.routers.calendar_router.get_db",
            return_value=AsyncMock(),
        ):
            with TestClient(app) as client:
                response = client.get(
                    "/api/priority-guardian/calendar/time-allocation",
                    headers={"X-User-ID": user_id}
                )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["keywords"]["P1"]["hours"] == 10.5
        assert data["data"]["total_tracked_hours"] == 31.75

    def test_returns_200_with_zeros_for_no_connection(self):
        """Returns 200 with all zeros when user has no Google connection."""
        app = create_test_app()
        user_id = str(uuid4())

        # Empty allocation returned when no connection
        mock_allocation = {
            "week_start": None,
            "week_end": None,
            "timezone": "UTC",
            "keywords": {
                "P1": {"hours": 0.0, "event_count": 0},
                "P2": {"hours": 0.0, "event_count": 0},
                "P3": {"hours": 0.0, "event_count": 0},
            },
            "other_hours": 0.0,
            "total_tracked_hours": 0.0,
            "total_events_scanned": 0,
            "bar_segments": {"P1": 0.0, "P2": 0.0, "P3": 0.0, "other": 0.0},
        }

        with patch(
            "backend.apps.priority_guardian.routers.calendar_router.compute_time_allocation",
            new_callable=AsyncMock,
            return_value=mock_allocation,
        ), patch(
            "backend.apps.priority_guardian.routers.calendar_router.get_db",
            return_value=AsyncMock(),
        ):
            with TestClient(app) as client:
                response = client.get(
                    "/api/priority-guardian/calendar/time-allocation",
                    headers={"X-User-ID": user_id}
                )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["total_tracked_hours"] == 0.0


# =============================================================================
# Error Response Tests
# =============================================================================

class TestErrorResponses:
    """Tests for error responses."""

    def test_returns_503_on_token_error(self):
        """Returns 503 when token refresh fails."""
        app = create_test_app()
        user_id = str(uuid4())

        with patch(
            "backend.apps.priority_guardian.routers.calendar_router.compute_time_allocation",
            new_callable=AsyncMock,
            side_effect=ValueError("Token error: REFRESH_TOKEN_INVALID"),
        ), patch(
            "backend.apps.priority_guardian.routers.calendar_router.get_db",
            return_value=AsyncMock(),
        ):
            with TestClient(app) as client:
                response = client.get(
                    "/api/priority-guardian/calendar/time-allocation",
                    headers={"X-User-ID": user_id}
                )

        assert response.status_code == 503
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "TOKEN_ERROR"

    def test_returns_502_on_upstream_error(self):
        """Returns 502 when Google Calendar API fails."""
        app = create_test_app()
        user_id = str(uuid4())

        with patch(
            "backend.apps.priority_guardian.routers.calendar_router.compute_time_allocation",
            new_callable=AsyncMock,
            side_effect=Exception("Google API error"),
        ), patch(
            "backend.apps.priority_guardian.routers.calendar_router.get_db",
            return_value=AsyncMock(),
        ):
            with TestClient(app) as client:
                response = client.get(
                    "/api/priority-guardian/calendar/time-allocation",
                    headers={"X-User-ID": user_id}
                )

        assert response.status_code == 502
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "UPSTREAM_ERROR"

    def test_error_response_has_standardized_shape(self):
        """Error responses use standardized shape."""
        app = create_test_app()
        user_id = str(uuid4())

        with patch(
            "backend.apps.priority_guardian.routers.calendar_router.compute_time_allocation",
            new_callable=AsyncMock,
            side_effect=Exception("Some error"),
        ), patch(
            "backend.apps.priority_guardian.routers.calendar_router.get_db",
            return_value=AsyncMock(),
        ):
            with TestClient(app) as client:
                response = client.get(
                    "/api/priority-guardian/calendar/time-allocation",
                    headers={"X-User-ID": user_id}
                )

        data = response.json()
        # Verify standardized error shape
        assert "success" in data
        assert data["success"] is False
        assert "error" in data
        assert "code" in data["error"]
        assert "message" in data["error"]
        # Verify no sensitive data leaked
        assert "Google API error" not in data["error"]["message"]
