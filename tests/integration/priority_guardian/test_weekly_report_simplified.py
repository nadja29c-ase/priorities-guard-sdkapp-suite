"""
Integration tests for simplified weekly report (Increment 06-S).

Tests the full flow with mocked Google Calendar API:
- Live computation flow
- Past week no-persistence verification
- Calendar failure handling
- Response structure validation
"""

import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from backend.apps.priority_guardian.services.weekly_report_service import (
    generate_weekly_report,
)


@pytest.fixture
def mock_session():
    """Mock database session."""
    return AsyncMock()


@pytest.fixture
def mock_http_client():
    """Mock HTTP client for Google API calls."""
    return AsyncMock()


@pytest.fixture
def mock_google_connection():
    """Mock Google connection."""
    connection = MagicMock()
    connection.provider = "google"
    connection.connection_type = "google"
    connection.revoked_at = None
    return connection


@pytest.fixture
def mock_flexible_priority():
    """Mock flexible priority."""
    priority = MagicMock()
    priority.id = uuid4()
    priority.name = "Side Project"
    priority.type = "flexible"
    priority.calendar_keyword = "P1"
    priority.status = "active"
    priority.weekly_hour_target = Decimal("10.0")
    priority.deliverables = []
    priority.created_at = datetime.now() - timedelta(days=30)
    return priority


@pytest.fixture
def mock_deadline_priority():
    """Mock deadline priority."""
    priority = MagicMock()
    priority.id = uuid4()
    priority.name = "Product Launch"
    priority.type = "deadline"
    priority.calendar_keyword = "P2"
    priority.status = "active"
    priority.deadline = date.today() + timedelta(days=14)
    priority.deliverables = [
        MagicMock(done=True),
        MagicMock(done=False),
        MagicMock(done=False),
    ]
    priority.created_at = datetime.now() - timedelta(days=30)
    return priority


@pytest.fixture
def mock_calendar_events():
    """Mock Google Calendar events."""
    return [
        {
            "id": "event1",
            "summary": "[P1] Work on side project",
            "start": {"dateTime": "2026-02-10T09:00:00Z"},
            "end": {"dateTime": "2026-02-10T12:00:00Z"},
        },
        {
            "id": "event2",
            "summary": "[P1] More project work",
            "start": {"dateTime": "2026-02-11T14:00:00Z"},
            "end": {"dateTime": "2026-02-11T16:00:00Z"},
        },
        {
            "id": "event3",
            "summary": "[P2] Launch prep",
            "start": {"dateTime": "2026-02-12T10:00:00Z"},
            "end": {"dateTime": "2026-02-12T14:00:00Z"},
        },
        {
            "id": "event4",
            "summary": "Team lunch",
            "start": {"dateTime": "2026-02-10T12:00:00Z"},
            "end": {"dateTime": "2026-02-10T13:00:00Z"},
        },
        {
            "id": "event5",
            "summary": "Client call",
            "start": {"dateTime": "2026-02-11T11:00:00Z"},
            "end": {"dateTime": "2026-02-11T12:00:00Z"},
        },
    ]


class TestLiveComputationFlow:
    """Integration tests for live computation flow."""

    @pytest.mark.asyncio
    async def test_full_flow_with_priorities_and_events(
        self,
        mock_session,
        mock_http_client,
        mock_google_connection,
        mock_flexible_priority,
        mock_deadline_priority,
        mock_calendar_events,
    ):
        """
        Full integration test: Create user with Google connection + priorities.
        Mock calendar events. Verify response structure.
        """
        user_id = uuid4()

        # Setup mock session returns
        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = mock_google_connection

        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [
            mock_flexible_priority,
            mock_deadline_priority,
        ]

        mock_session.execute.side_effect = [conn_result, priorities_result]

        with patch(
            "backend.apps.priority_guardian.services.weekly_report_service.ensure_valid_access_token"
        ) as mock_token, patch(
            "backend.apps.priority_guardian.services.weekly_report_service.get_user_timezone"
        ) as mock_tz, patch(
            "backend.apps.priority_guardian.services.weekly_report_service.list_events"
        ) as mock_events:
            mock_token.return_value = {"access_token": "test_token"}
            mock_tz.return_value = "America/Los_Angeles"
            mock_events.return_value = (mock_calendar_events, 0)

            result = await generate_weekly_report(
                user_id=user_id,
                session=mock_session,
                http_client=mock_http_client,
            )

        # Verify success
        assert result["success"] is True

        data = result["data"]

        # Verify response structure
        assert "week_start" in data
        assert "week_end" in data
        assert "is_current_week" in data
        assert "priorities" in data
        assert "time_allocation" in data
        assert "all_events" in data

        # Verify persistence fields are inert
        assert data["snapshot_saved"] is False
        assert data["weeks_backfilled"] == 0
        assert data["backfill_truncated"] is False

        # Verify priorities data
        assert len(data["priorities"]) == 2

        # Verify P1 priority has hours (3h + 2h = 5h)
        p1_priority = next(p for p in data["priorities"] if p["calendar_keyword"] == "P1")
        assert p1_priority["actual_hours"] == 5.0
        assert p1_priority["previous_week"] is None  # Always null

        # Verify P2 priority has hours (4h)
        p2_priority = next(p for p in data["priorities"] if p["calendar_keyword"] == "P2")
        assert p2_priority["actual_hours"] == 4.0
        assert p2_priority["previous_week"] is None  # Always null

        # Verify time allocation
        assert data["time_allocation"]["total_tracked_hours"] > 0
        assert data["time_allocation"]["other_hours"] == 2.0  # Lunch + client call

        # Verify all_events includes non-priority events for LLM
        assert len(data["all_events"]) == 5

    @pytest.mark.asyncio
    async def test_flexible_priority_status_computation(
        self,
        mock_session,
        mock_http_client,
        mock_google_connection,
        mock_flexible_priority,
    ):
        """Flexible priority flex_status is computed correctly."""
        user_id = uuid4()

        # Set target to 10 hours
        mock_flexible_priority.weekly_hour_target = Decimal("10.0")

        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = mock_google_connection

        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [mock_flexible_priority]

        mock_session.execute.side_effect = [conn_result, priorities_result]

        # 8 hours of P1 work (80% = on_track threshold)
        events = [
            {
                "id": "event-p1-work",
                "summary": "[P1] Work",
                "start": {"dateTime": "2026-02-10T09:00:00Z"},
                "end": {"dateTime": "2026-02-10T17:00:00Z"},  # 8 hours
            },
        ]

        with patch(
            "backend.apps.priority_guardian.services.weekly_report_service.ensure_valid_access_token"
        ) as mock_token, patch(
            "backend.apps.priority_guardian.services.weekly_report_service.get_user_timezone"
        ) as mock_tz, patch(
            "backend.apps.priority_guardian.services.weekly_report_service.list_events"
        ) as mock_events:
            mock_token.return_value = {"access_token": "test_token"}
            mock_tz.return_value = "UTC"
            mock_events.return_value = (events, 0)

            result = await generate_weekly_report(
                user_id=user_id,
                session=mock_session,
                http_client=mock_http_client,
            )

        priority = result["data"]["priorities"][0]
        assert priority["flex_status"] == "on_track"  # 80% is on_track


class TestPastWeekNoPersistence:
    """Integration tests verifying no persistence for past weeks."""

    @pytest.mark.asyncio
    async def test_past_week_returns_snapshot_saved_false(
        self,
        mock_session,
        mock_http_client,
        mock_google_connection,
        mock_flexible_priority,
    ):
        """Past week reports still return snapshot_saved=False."""
        user_id = uuid4()

        # Get last Monday
        today = date.today()
        days_since_monday = today.weekday()
        last_monday = today - timedelta(days=days_since_monday + 7)

        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = mock_google_connection

        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [mock_flexible_priority]

        mock_session.execute.side_effect = [conn_result, priorities_result]

        with patch(
            "backend.apps.priority_guardian.services.weekly_report_service.ensure_valid_access_token"
        ) as mock_token, patch(
            "backend.apps.priority_guardian.services.weekly_report_service.get_user_timezone"
        ) as mock_tz, patch(
            "backend.apps.priority_guardian.services.weekly_report_service.list_events"
        ) as mock_events:
            mock_token.return_value = {"access_token": "test_token"}
            mock_tz.return_value = "UTC"
            mock_events.return_value = ([], 0)

            result = await generate_weekly_report(
                user_id=user_id,
                session=mock_session,
                http_client=mock_http_client,
                week_start=last_monday,
            )

        # Even for past weeks, no persistence
        assert result["data"]["snapshot_saved"] is False
        assert result["data"]["weeks_backfilled"] == 0
        assert result["data"]["is_current_week"] is False

    @pytest.mark.asyncio
    async def test_past_week_no_database_writes(
        self,
        mock_session,
        mock_http_client,
        mock_google_connection,
        mock_flexible_priority,
    ):
        """Past week reports do not write to database."""
        user_id = uuid4()

        # Get last Monday
        today = date.today()
        days_since_monday = today.weekday()
        last_monday = today - timedelta(days=days_since_monday + 7)

        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = mock_google_connection

        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [mock_flexible_priority]

        mock_session.execute.side_effect = [conn_result, priorities_result]

        with patch(
            "backend.apps.priority_guardian.services.weekly_report_service.ensure_valid_access_token"
        ) as mock_token, patch(
            "backend.apps.priority_guardian.services.weekly_report_service.get_user_timezone"
        ) as mock_tz, patch(
            "backend.apps.priority_guardian.services.weekly_report_service.list_events"
        ) as mock_events:
            mock_token.return_value = {"access_token": "test_token"}
            mock_tz.return_value = "UTC"
            mock_events.return_value = ([], 0)

            await generate_weekly_report(
                user_id=user_id,
                session=mock_session,
                http_client=mock_http_client,
                week_start=last_monday,
            )

        # Verify no commits (no persistence)
        mock_session.commit.assert_not_called()
        mock_session.add.assert_not_called()


class TestCalendarFailureHandling:
    """Integration tests for calendar failure handling."""

    @pytest.mark.asyncio
    async def test_raises_error_when_google_not_connected(
        self,
        mock_session,
        mock_http_client,
    ):
        """Raises ValueError when Google is not connected."""
        user_id = uuid4()

        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = None  # No connection

        mock_session.execute.return_value = conn_result

        with pytest.raises(ValueError, match="Google Calendar not connected"):
            await generate_weekly_report(
                user_id=user_id,
                session=mock_session,
                http_client=mock_http_client,
            )

    @pytest.mark.asyncio
    async def test_raises_error_on_token_failure(
        self,
        mock_session,
        mock_http_client,
        mock_google_connection,
    ):
        """Raises ValueError on token refresh failure."""
        user_id = uuid4()

        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = mock_google_connection

        mock_session.execute.return_value = conn_result

        with patch(
            "backend.apps.priority_guardian.services.weekly_report_service.ensure_valid_access_token"
        ) as mock_token:
            mock_token.return_value = {"error": "token_expired"}

            with pytest.raises(ValueError, match="Token error"):
                await generate_weekly_report(
                    user_id=user_id,
                    session=mock_session,
                    http_client=mock_http_client,
                )

    @pytest.mark.asyncio
    async def test_handles_calendar_api_error_gracefully(
        self,
        mock_session,
        mock_http_client,
        mock_google_connection,
        mock_flexible_priority,
    ):
        """Calendar API errors propagate as exceptions."""
        user_id = uuid4()

        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = mock_google_connection

        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [mock_flexible_priority]

        mock_session.execute.side_effect = [conn_result, priorities_result]

        with patch(
            "backend.apps.priority_guardian.services.weekly_report_service.ensure_valid_access_token"
        ) as mock_token, patch(
            "backend.apps.priority_guardian.services.weekly_report_service.get_user_timezone"
        ) as mock_tz, patch(
            "backend.apps.priority_guardian.services.weekly_report_service.list_events"
        ) as mock_events:
            mock_token.return_value = {"access_token": "test_token"}
            mock_tz.return_value = "UTC"
            mock_events.side_effect = Exception("Calendar API error")

            with pytest.raises(Exception, match="Calendar API error"):
                await generate_weekly_report(
                    user_id=user_id,
                    session=mock_session,
                    http_client=mock_http_client,
                )


class TestResponseStructure:
    """Integration tests for response structure validation."""

    @pytest.mark.asyncio
    async def test_empty_report_when_no_priorities(
        self,
        mock_session,
        mock_http_client,
        mock_google_connection,
    ):
        """Returns empty report when user has no active priorities."""
        user_id = uuid4()

        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = mock_google_connection

        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = []  # No priorities

        mock_session.execute.side_effect = [conn_result, priorities_result]

        with patch(
            "backend.apps.priority_guardian.services.weekly_report_service.ensure_valid_access_token"
        ) as mock_token, patch(
            "backend.apps.priority_guardian.services.weekly_report_service.get_user_timezone"
        ) as mock_tz:
            mock_token.return_value = {"access_token": "test_token"}
            mock_tz.return_value = "UTC"

            result = await generate_weekly_report(
                user_id=user_id,
                session=mock_session,
                http_client=mock_http_client,
            )

        assert result["success"] is True
        assert result["data"]["priorities"] == []
        assert result["data"]["snapshot_saved"] is False
        assert result["data"]["weeks_backfilled"] == 0

    @pytest.mark.asyncio
    async def test_deadline_priority_includes_pacing_status(
        self,
        mock_session,
        mock_http_client,
        mock_google_connection,
        mock_deadline_priority,
    ):
        """Deadline priorities include pacing_status computation."""
        user_id = uuid4()

        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = mock_google_connection

        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [mock_deadline_priority]

        mock_session.execute.side_effect = [conn_result, priorities_result]

        with patch(
            "backend.apps.priority_guardian.services.weekly_report_service.ensure_valid_access_token"
        ) as mock_token, patch(
            "backend.apps.priority_guardian.services.weekly_report_service.get_user_timezone"
        ) as mock_tz, patch(
            "backend.apps.priority_guardian.services.weekly_report_service.list_events"
        ) as mock_events:
            mock_token.return_value = {"access_token": "test_token"}
            mock_tz.return_value = "UTC"
            mock_events.return_value = ([], 0)

            result = await generate_weekly_report(
                user_id=user_id,
                session=mock_session,
                http_client=mock_http_client,
            )

        priority = result["data"]["priorities"][0]
        assert "pacing_status" in priority
        assert priority["pacing_status"] in ["completed", "ahead", "on_track", "behind"]
        assert "deliverables_completed" in priority
        assert "deliverables_total" in priority
        assert "days_remaining" in priority
