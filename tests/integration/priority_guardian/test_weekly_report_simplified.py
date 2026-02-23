"""
Integration tests for simplified weekly report (Increment 06-S).

Tests the full flow with mocked Google Calendar API:
- Live computation flow
- Past week no-persistence verification
- Calendar failure handling
- Response structure validation
- Pie chart slice building (Increment 07)
"""

import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from backend.apps.priority_guardian.services.weekly_report_service import (
    generate_weekly_report,
)
from mcp_server.priority_guardian.tools.get_weekly_report import (
    _build_pie_slices,
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

        # Empty snapshot result (no snapshots found, falls through to live computation)
        snapshot_result = MagicMock()
        snapshot_result.all.return_value = []

        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [mock_flexible_priority]

        mock_session.execute.side_effect = [conn_result, snapshot_result, priorities_result]

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

        # Empty snapshot result (no snapshots found, falls through to live computation)
        snapshot_result = MagicMock()
        snapshot_result.all.return_value = []

        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [mock_flexible_priority]

        mock_session.execute.side_effect = [conn_result, snapshot_result, priorities_result]

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


class TestPieChartIntegration:
    """
    Integration tests for pie chart slice building (Increment 07).

    Tests the round-trip: service fetches calendar data → _build_pie_slices creates
    slices from that data. This verifies the handler layer correctly transforms
    service output into pie chart format.
    """

    @pytest.mark.asyncio
    async def test_without_semantic_groupings_returns_priority_and_other_slices(
        self,
        mock_session,
        mock_http_client,
        mock_google_connection,
        mock_flexible_priority,
        mock_deadline_priority,
        mock_calendar_events,
    ):
        """
        Round-trip: Service data + no semantic_groupings → priority slices + Other slice.
        """
        user_id = uuid4()

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

        # Service returns success
        assert result["success"] is True
        data = result["data"]

        # Build pie slices from service data (as handler does)
        priorities = data["priorities"]
        time_allocation = data["time_allocation"]

        slices, error = _build_pie_slices(priorities, time_allocation, None, None)

        # No error
        assert error is None

        # Should have P1 slice, P2 slice, and Other slice
        slice_labels = [s["label"] for s in slices]
        # Priority slices are labeled "P1: Name", "P2: Name"
        assert any("P1" in label for label in slice_labels)
        assert any("P2" in label for label in slice_labels)
        assert "Other" in slice_labels

        # Verify slice types
        for s in slices:
            if s.get("keyword") in ["P1", "P2", "P3"]:
                assert s["type"] == "priority"
            elif s["label"] == "Other":
                assert s["type"] == "semantic"

        # Verify totalHours equals sum of all slices
        total_hours = time_allocation["total_tracked_hours"]
        slice_sum = sum(s["hours"] for s in slices)
        assert abs(total_hours - slice_sum) < 0.01

    @pytest.mark.asyncio
    async def test_with_semantic_groupings_replaces_other_with_categories(
        self,
        mock_session,
        mock_http_client,
        mock_google_connection,
        mock_flexible_priority,
        mock_calendar_events,
    ):
        """
        Round-trip: Service data + semantic_groupings → priority slices + category slices.
        """
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
            mock_tz.return_value = "America/Los_Angeles"
            mock_events.return_value = (mock_calendar_events, 0)

            result = await generate_weekly_report(
                user_id=user_id,
                session=mock_session,
                http_client=mock_http_client,
            )

        data = result["data"]
        other_hours = data["time_allocation"]["other_hours"]

        # Semantic groupings that add up to the "other" time
        semantic_groupings = [
            {"category": "Team meetings", "hours": other_hours / 2, "event_count": 1},
            {"category": "Client calls", "hours": other_hours / 2, "event_count": 1},
        ]

        # Build slices with semantic groupings
        slices, error = _build_pie_slices(
            data["priorities"],
            data["time_allocation"],
            semantic_groupings,
            None,
        )

        # No error
        assert error is None

        # Should NOT have "Other" slice when semantic groupings provided
        slice_labels = [s["label"] for s in slices]
        assert "Other" not in slice_labels

        # Should have semantic category slices
        assert "Team meetings" in slice_labels
        assert "Client calls" in slice_labels

        # Verify semantic slices have type "semantic"
        for s in slices:
            if s["label"] in ["Team meetings", "Client calls"]:
                assert s["type"] == "semantic"

    @pytest.mark.asyncio
    async def test_over_allocation_returns_error(
        self,
        mock_session,
        mock_http_client,
        mock_google_connection,
        mock_flexible_priority,
        mock_calendar_events,
    ):
        """
        Round-trip: Semantic groupings exceeding other_hours + 0.5h returns validation error.
        """
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
            mock_tz.return_value = "America/Los_Angeles"
            mock_events.return_value = (mock_calendar_events, 0)

            result = await generate_weekly_report(
                user_id=user_id,
                session=mock_session,
                http_client=mock_http_client,
            )

        data = result["data"]
        other_hours = data["time_allocation"]["other_hours"]

        # Semantic groupings that exceed other_hours by more than 0.5h tolerance
        semantic_groupings = [
            {"category": "Meetings", "hours": other_hours + 1.0, "event_count": 3},
        ]

        # Build slices - should raise ToolUsageError
        from mcp_server.priority_guardian.tools.base import ToolUsageError
        with pytest.raises(ToolUsageError) as exc_info:
            _build_pie_slices(
                data["priorities"],
                data["time_allocation"],
                semantic_groupings,
                None,
            )

        # Should contain "exceed" in error message
        assert "exceed" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_total_hours_mathematically_correct(
        self,
        mock_session,
        mock_http_client,
        mock_google_connection,
        mock_flexible_priority,
        mock_deadline_priority,
        mock_calendar_events,
    ):
        """
        totalHours from service equals sum of priority hours + other hours.
        """
        user_id = uuid4()

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

        data = result["data"]
        time_allocation = data["time_allocation"]
        total_hours = time_allocation["total_tracked_hours"]

        # Verify components add up
        keywords = time_allocation.get("keywords", {})
        priority_hours = sum(
            keywords.get(kw, {}).get("hours", 0)
            for kw in ["P1", "P2", "P3"]
        )
        other_hours = time_allocation["other_hours"]
        assert abs(total_hours - (priority_hours + other_hours)) < 0.01

        # Build slices and verify slice sum equals total_hours
        slices, error = _build_pie_slices(data["priorities"], time_allocation, None, None)
        assert error is None
        slice_sum = sum(s["hours"] for s in slices)
        assert abs(total_hours - slice_sum) < 0.01

    @pytest.mark.asyncio
    async def test_slight_overshoot_within_tolerance_no_negative_slices(
        self,
        mock_session,
        mock_http_client,
        mock_google_connection,
        mock_flexible_priority,
        mock_calendar_events,
    ):
        """
        When semantic groupings slightly exceed other_hours (within 0.5h tolerance),
        no negative Uncategorized slice is created.
        """
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
            mock_tz.return_value = "America/Los_Angeles"
            mock_events.return_value = (mock_calendar_events, 0)

            result = await generate_weekly_report(
                user_id=user_id,
                session=mock_session,
                http_client=mock_http_client,
            )

        data = result["data"]
        other_hours = data["time_allocation"]["other_hours"]

        # Exceed by 0.3h (within 0.5h tolerance)
        semantic_groupings = [
            {"category": "Team meetings", "hours": other_hours * 0.6 + 0.15, "event_count": 1},
            {"category": "Client calls", "hours": other_hours * 0.4 + 0.15, "event_count": 1},
        ]

        slices, error = _build_pie_slices(
            data["priorities"],
            data["time_allocation"],
            semantic_groupings,
            None,
        )

        # Should succeed (within tolerance)
        assert error is None

        # No Uncategorized slice (remainder clamped to 0)
        assert not any(s["label"] == "Uncategorized" for s in slices)

        # All slice hours are non-negative
        for s in slices:
            assert s["hours"] >= 0, f"Slice {s['label']} has negative hours: {s['hours']}"

    @pytest.mark.asyncio
    async def test_week_start_and_week_end_in_service_response(
        self,
        mock_session,
        mock_http_client,
        mock_google_connection,
        mock_flexible_priority,
        mock_calendar_events,
    ):
        """
        Service response includes week_start and week_end for pie chart rendering.
        """
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
            mock_tz.return_value = "America/Los_Angeles"
            mock_events.return_value = (mock_calendar_events, 0)

            result = await generate_weekly_report(
                user_id=user_id,
                session=mock_session,
                http_client=mock_http_client,
            )

        data = result["data"]

        # Service returns snake_case keys
        assert "week_start" in data
        assert "week_end" in data

        # Verify dates are ISO format strings
        assert isinstance(data["week_start"], str)
        assert isinstance(data["week_end"], str)

    @pytest.mark.asyncio
    async def test_uncategorized_slice_when_remainder_significant(
        self,
        mock_session,
        mock_http_client,
        mock_google_connection,
        mock_flexible_priority,
        mock_calendar_events,
    ):
        """
        When semantic groupings leave >= 0.25h remainder, Uncategorized slice is added.
        """
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
            mock_tz.return_value = "America/Los_Angeles"
            mock_events.return_value = (mock_calendar_events, 0)

            result = await generate_weekly_report(
                user_id=user_id,
                session=mock_session,
                http_client=mock_http_client,
            )

        data = result["data"]
        other_hours = data["time_allocation"]["other_hours"]

        # Leave 0.5h uncategorized (significant remainder)
        semantic_groupings = [
            {"category": "Team meetings", "hours": other_hours - 0.5, "event_count": 1},
        ]

        slices, error = _build_pie_slices(
            data["priorities"],
            data["time_allocation"],
            semantic_groupings,
            None,
        )

        assert error is None

        # Should have Uncategorized slice
        slice_labels = [s["label"] for s in slices]
        assert "Uncategorized" in slice_labels

        # Uncategorized slice has the remainder hours
        uncategorized = next(s for s in slices if s["label"] == "Uncategorized")
        assert uncategorized["hours"] == 0.5
        assert uncategorized["type"] == "semantic"


class TestPastWeekBeforePrioritiesExisted:
    """
    Integration tests for past week reports before any priorities existed.

    Increment 22 fix: When requesting a report for a past week where no
    priorities existed (all current priorities were created after that week),
    return _empty_report shape with no calendar API call.
    """

    @pytest.mark.asyncio
    async def test_past_week_before_priorities_returns_empty_report_shape(
        self,
        mock_session,
        mock_http_client,
        mock_google_connection,
    ):
        """
        Past week before any priorities existed returns empty_report shape:
        - empty priorities list
        - all time_allocation values zero
        - is_current_week: False
        """
        user_id = uuid4()
        # Request report for Feb 9, 2026 (a Monday)
        week_start = date(2026, 2, 9)

        # Priority created AFTER the requested week
        mock_priority = MagicMock()
        mock_priority.id = uuid4()
        mock_priority.name = "Future Priority"
        mock_priority.type = "flexible"
        mock_priority.calendar_keyword = "P1"
        mock_priority.status = "active"
        mock_priority.weekly_hour_target = Decimal("10.0")
        mock_priority.deliverables = []
        mock_priority.created_at = datetime(2026, 2, 19)  # Created Feb 19, after Feb 9-15 week

        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = mock_google_connection

        # Empty snapshot result (no snapshots for that week)
        snapshot_result = MagicMock()
        snapshot_result.all.return_value = []

        # Priorities query returns the future-created priority
        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [mock_priority]

        mock_session.execute.side_effect = [conn_result, snapshot_result, priorities_result]

        with patch(
            "backend.apps.priority_guardian.services.weekly_report_service.ensure_valid_access_token"
        ) as mock_token, patch(
            "backend.apps.priority_guardian.services.weekly_report_service.get_user_timezone"
        ) as mock_tz, patch(
            "backend.apps.priority_guardian.services.weekly_report_service.is_week_complete"
        ) as mock_complete, patch(
            "backend.apps.priority_guardian.services.weekly_report_service.list_events"
        ) as mock_events:
            mock_token.return_value = {"access_token": "test_token"}
            mock_tz.return_value = "UTC"
            mock_complete.return_value = True  # Past week
            mock_events.return_value = ([], 0)

            result = await generate_weekly_report(
                user_id=user_id,
                session=mock_session,
                http_client=mock_http_client,
                week_start=week_start,
            )

        # Verify empty_report shape
        assert result["success"] is True
        data = result["data"]

        # Empty priorities list
        assert data["priorities"] == []

        # is_current_week: False
        assert data["is_current_week"] is False

        # All time_allocation values zero
        assert data["time_allocation"]["total_tracked_hours"] == 0.0
        assert data["time_allocation"]["other_hours"] == 0.0
        for kw in ["P1", "P2", "P3"]:
            assert data["time_allocation"]["keywords"][kw]["hours"] == 0.0
            assert data["time_allocation"]["keywords"][kw]["event_count"] == 0

        # No events
        assert data["all_events"] == []

        # Calendar API should NOT have been called (early return)
        mock_events.assert_not_called()
