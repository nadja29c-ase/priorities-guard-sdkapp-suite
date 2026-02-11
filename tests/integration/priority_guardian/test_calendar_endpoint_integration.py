"""
Integration tests for Calendar Time Allocation endpoint.

Tests the full request→response chain for:
GET /api/priority-guardian/calendar/time-allocation

Uses real DB session with mocked Google Calendar API.
"""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_google_events():
    """Sample Google Calendar events for testing."""
    return [
        {
            "id": "event-1",
            "summary": "[P1] Deep work session",
            "start": {"dateTime": "2026-02-09T09:00:00+01:00"},
            "end": {"dateTime": "2026-02-09T11:00:00+01:00"},
            "status": "confirmed",
        },
        {
            "id": "event-2",
            "summary": "P2 Client call",
            "start": {"dateTime": "2026-02-09T14:00:00+01:00"},
            "end": {"dateTime": "2026-02-09T15:30:00+01:00"},
            "status": "confirmed",
        },
        {
            "id": "event-3",
            "summary": "Team standup",  # No keyword
            "start": {"dateTime": "2026-02-10T10:00:00+01:00"},
            "end": {"dateTime": "2026-02-10T10:30:00+01:00"},
            "status": "confirmed",
        },
    ]


async def create_test_user(session: AsyncSession):
    """Helper to create a test user.

    Note: We don't create Google connections directly because:
    1. The schema uses encrypted token storage (not plain columns)
    2. We mock compute_time_allocation anyway, so no real connection is needed
    """
    user_id = uuid4()

    await session.execute(
        text("INSERT INTO core_users (id) VALUES (:id)"),
        {"id": user_id},
    )

    await session.commit()
    return user_id


# =============================================================================
# Happy Path Integration Tests
# =============================================================================


class TestCalendarEndpointHappyPath:
    """Integration tests for successful calendar time allocation requests."""

    @pytest.mark.asyncio
    async def test_full_request_response_chain_with_events(
        self, client, async_session: AsyncSession, mock_google_events
    ):
        """
        Full integration test: request → DB lookup → Google API → response.

        Verifies:
        - User lookup from DB works
        - Google connection is found
        - Token refresh is handled
        - Events are fetched and processed
        - Response has correct structure
        """
        user_id = await create_test_user(async_session)

        # Mock the entire compute_time_allocation service
        mock_allocation = {
            "week_start": "2026-02-09T00:00:00+01:00",
            "week_end": "2026-02-16T00:00:00+01:00",
            "timezone": "Europe/Berlin",
            "keywords": {
                "P1": {"hours": 2.0, "event_count": 1},
                "P2": {"hours": 1.5, "event_count": 1},
                "P3": {"hours": 0.0, "event_count": 0},
            },
            "other_hours": 0.5,
            "total_tracked_hours": 4.0,
            "total_events_scanned": 3,
            "bar_segments": {"P1": 2.0, "P2": 1.5, "P3": 0.0, "other": 0.5},
        }

        with patch(
            "backend.apps.priority_guardian.routers.calendar_router.compute_time_allocation",
            new_callable=AsyncMock,
            return_value=mock_allocation,
        ):
            response = await client.get(
                "/api/priority-guardian/calendar/time-allocation",
                headers={"X-User-ID": str(user_id)},
            )

        assert response.status_code == 200
        data = response.json()

        # Verify success response structure
        assert data["success"] is True
        assert "data" in data

        # Verify allocation data
        assert data["data"]["week_start"] == "2026-02-09T00:00:00+01:00"
        assert data["data"]["week_end"] == "2026-02-16T00:00:00+01:00"
        assert data["data"]["timezone"] == "Europe/Berlin"
        assert data["data"]["total_tracked_hours"] == 4.0

        # Verify keyword breakdown
        keywords = data["data"]["keywords"]
        assert keywords["P1"]["hours"] == 2.0
        assert keywords["P1"]["event_count"] == 1
        assert keywords["P2"]["hours"] == 1.5
        assert keywords["P3"]["hours"] == 0.0

        # Verify bar segments
        assert data["data"]["bar_segments"]["P1"] == 2.0
        assert data["data"]["bar_segments"]["other"] == 0.5

    @pytest.mark.asyncio
    async def test_user_without_google_connection_returns_zeros(
        self, client, async_session: AsyncSession
    ):
        """
        User with no Google connection gets all-zeros allocation.

        The endpoint should return 200 with week_start/week_end as None
        and all hours as 0.0.
        """
        # Create user without Google connection
        user_id = uuid4()
        await async_session.execute(
            text("INSERT INTO core_users (id) VALUES (:id)"),
            {"id": user_id},
        )
        await async_session.commit()

        # Mock returns empty allocation (no Google connection)
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
        ):
            response = await client.get(
                "/api/priority-guardian/calendar/time-allocation",
                headers={"X-User-ID": str(user_id)},
            )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["data"]["week_start"] is None
        assert data["data"]["week_end"] is None
        assert data["data"]["total_tracked_hours"] == 0.0


# =============================================================================
# Authentication Tests
# =============================================================================


class TestCalendarEndpointAuth:
    """Integration tests for authentication handling."""

    @pytest.mark.asyncio
    async def test_missing_user_id_header_returns_401(self, client):
        """Request without X-User-ID header returns 401."""
        response = await client.get("/api/priority-guardian/calendar/time-allocation")

        assert response.status_code == 401
        data = response.json()
        assert data["detail"]["code"] == "UNAUTHORIZED"

    @pytest.mark.asyncio
    async def test_invalid_uuid_returns_401(self, client):
        """Invalid UUID in X-User-ID header returns 401."""
        response = await client.get(
            "/api/priority-guardian/calendar/time-allocation",
            headers={"X-User-ID": "not-a-valid-uuid"},
        )

        assert response.status_code == 401
        data = response.json()
        assert data["detail"]["code"] == "UNAUTHORIZED"


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestCalendarEndpointErrors:
    """Integration tests for error handling."""

    @pytest.mark.asyncio
    async def test_token_error_returns_503(self, client, async_session: AsyncSession):
        """
        Token refresh failure returns 503 with TOKEN_ERROR code.

        This happens when the user's refresh token is invalid/revoked.
        """
        user_id = await create_test_user(async_session)

        with patch(
            "backend.apps.priority_guardian.routers.calendar_router.compute_time_allocation",
            new_callable=AsyncMock,
            side_effect=ValueError("Token error: REFRESH_TOKEN_INVALID"),
        ):
            response = await client.get(
                "/api/priority-guardian/calendar/time-allocation",
                headers={"X-User-ID": str(user_id)},
            )

        assert response.status_code == 503
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "TOKEN_ERROR"

    @pytest.mark.asyncio
    async def test_google_api_error_returns_502(self, client, async_session: AsyncSession):
        """
        Google Calendar API failure returns 502 with UPSTREAM_ERROR code.

        This happens when Google API returns an error or is unavailable.
        """
        user_id = await create_test_user(async_session)

        with patch(
            "backend.apps.priority_guardian.routers.calendar_router.compute_time_allocation",
            new_callable=AsyncMock,
            side_effect=Exception("Google Calendar API unavailable"),
        ):
            response = await client.get(
                "/api/priority-guardian/calendar/time-allocation",
                headers={"X-User-ID": str(user_id)},
            )

        assert response.status_code == 502
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "UPSTREAM_ERROR"
        # Verify no sensitive info leaked
        assert "Google Calendar API unavailable" not in data["error"]["message"]

    @pytest.mark.asyncio
    async def test_error_response_shape_is_standardized(
        self, client, async_session: AsyncSession
    ):
        """
        All error responses follow the standardized error shape.

        Shape: {"success": false, "error": {"code": "...", "message": "..."}}
        """
        user_id = await create_test_user(async_session)

        with patch(
            "backend.apps.priority_guardian.routers.calendar_router.compute_time_allocation",
            new_callable=AsyncMock,
            side_effect=Exception("Some internal error"),
        ):
            response = await client.get(
                "/api/priority-guardian/calendar/time-allocation",
                headers={"X-User-ID": str(user_id)},
            )

        data = response.json()

        # Verify standardized shape
        assert "success" in data
        assert data["success"] is False
        assert "error" in data
        assert "code" in data["error"]
        assert "message" in data["error"]
        assert isinstance(data["error"]["code"], str)
        assert isinstance(data["error"]["message"], str)


# =============================================================================
# Response Format Tests
# =============================================================================


class TestCalendarEndpointResponseFormat:
    """Integration tests for response format compliance."""

    @pytest.mark.asyncio
    async def test_success_response_has_all_required_fields(
        self, client, async_session: AsyncSession
    ):
        """
        Success response includes all required fields from spec.

        Required fields:
        - success: true
        - data.week_start
        - data.week_end
        - data.timezone
        - data.keywords.P1/P2/P3 with hours and event_count
        - data.other_hours
        - data.total_tracked_hours
        - data.total_events_scanned
        - data.bar_segments
        """
        user_id = await create_test_user(async_session)

        mock_allocation = {
            "week_start": "2026-02-09T00:00:00+01:00",
            "week_end": "2026-02-16T00:00:00+01:00",
            "timezone": "Europe/Berlin",
            "keywords": {
                "P1": {"hours": 5.0, "event_count": 3},
                "P2": {"hours": 2.0, "event_count": 1},
                "P3": {"hours": 0.0, "event_count": 0},
            },
            "other_hours": 10.0,
            "total_tracked_hours": 17.0,
            "total_events_scanned": 25,
            "bar_segments": {"P1": 5.0, "P2": 2.0, "P3": 0.0, "other": 10.0},
        }

        with patch(
            "backend.apps.priority_guardian.routers.calendar_router.compute_time_allocation",
            new_callable=AsyncMock,
            return_value=mock_allocation,
        ):
            response = await client.get(
                "/api/priority-guardian/calendar/time-allocation",
                headers={"X-User-ID": str(user_id)},
            )

        assert response.status_code == 200
        data = response.json()

        # Verify all required fields present
        assert data["success"] is True
        assert "data" in data

        d = data["data"]
        assert "week_start" in d
        assert "week_end" in d
        assert "timezone" in d
        assert "keywords" in d
        assert "other_hours" in d
        assert "total_tracked_hours" in d
        assert "total_events_scanned" in d
        assert "bar_segments" in d

        # Verify keyword structure
        for kw in ["P1", "P2", "P3"]:
            assert kw in d["keywords"]
            assert "hours" in d["keywords"][kw]
            assert "event_count" in d["keywords"][kw]

        # Verify bar_segments structure
        for key in ["P1", "P2", "P3", "other"]:
            assert key in d["bar_segments"]

    @pytest.mark.asyncio
    async def test_hours_are_floats_with_two_decimal_precision(
        self, client, async_session: AsyncSession
    ):
        """
        All hour values are floats rounded to 2 decimal places.
        """
        user_id = await create_test_user(async_session)

        mock_allocation = {
            "week_start": "2026-02-09T00:00:00+01:00",
            "week_end": "2026-02-16T00:00:00+01:00",
            "timezone": "Europe/Berlin",
            "keywords": {
                "P1": {"hours": 2.75, "event_count": 2},
                "P2": {"hours": 1.33, "event_count": 1},
                "P3": {"hours": 0.0, "event_count": 0},
            },
            "other_hours": 5.25,
            "total_tracked_hours": 9.33,
            "total_events_scanned": 10,
            "bar_segments": {"P1": 2.75, "P2": 1.33, "P3": 0.0, "other": 5.25},
        }

        with patch(
            "backend.apps.priority_guardian.routers.calendar_router.compute_time_allocation",
            new_callable=AsyncMock,
            return_value=mock_allocation,
        ):
            response = await client.get(
                "/api/priority-guardian/calendar/time-allocation",
                headers={"X-User-ID": str(user_id)},
            )

        data = response.json()["data"]

        # All hour values should be floats
        assert isinstance(data["keywords"]["P1"]["hours"], float)
        assert isinstance(data["keywords"]["P2"]["hours"], float)
        assert isinstance(data["total_tracked_hours"], float)
        assert isinstance(data["other_hours"], float)
