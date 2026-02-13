"""
Unit tests for simplified weekly report service (Increment 06-S).

Tests the generate_weekly_report() function after persistence was stripped:
- Always returns snapshot_saved: false
- Always returns weeks_backfilled: 0
- Always returns previous_week: null
- is_current_week flag computed correctly
- Pure computation functions still work
"""

import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from backend.apps.priority_guardian.services.weekly_report_service import (
    generate_weekly_report,
    is_week_complete,
    compute_flex_status,
    compute_pacing_status,
    process_events_for_report,
    _empty_report,
)


class TestIsWeekComplete:
    """Tests for is_week_complete() function."""

    def test_current_week_is_not_complete(self):
        """Current week returns False."""
        # Get this Monday
        today = date.today()
        days_since_monday = today.weekday()
        this_monday = today - timedelta(days=days_since_monday)

        assert is_week_complete(this_monday, "UTC") is False

    def test_last_week_is_complete(self):
        """Last week returns True."""
        # Get last Monday
        today = date.today()
        days_since_monday = today.weekday()
        last_monday = today - timedelta(days=days_since_monday + 7)

        assert is_week_complete(last_monday, "UTC") is True

    def test_future_week_is_not_complete(self):
        """Future week returns False."""
        # Get next Monday
        today = date.today()
        days_until_monday = (7 - today.weekday()) % 7 or 7
        next_monday = today + timedelta(days=days_until_monday)

        assert is_week_complete(next_monday, "UTC") is False

    def test_handles_invalid_timezone_gracefully(self):
        """Falls back to UTC for invalid timezone."""
        last_monday = date.today() - timedelta(days=14)
        # Should not raise, should fall back to UTC
        result = is_week_complete(last_monday, "Invalid/Timezone")
        assert result is True


class TestComputeFlexStatus:
    """Tests for compute_flex_status() function."""

    def test_ahead_when_over_110_percent(self):
        """Returns 'ahead' when >= 110% of target."""
        assert compute_flex_status(11.0, 10.0) == "ahead"
        assert compute_flex_status(12.0, 10.0) == "ahead"
        assert compute_flex_status(11.5, 10.0) == "ahead"

    def test_on_track_between_80_and_110_percent(self):
        """Returns 'on_track' when 80-110% of target."""
        assert compute_flex_status(10.0, 10.0) == "on_track"  # 100%
        assert compute_flex_status(8.0, 10.0) == "on_track"   # 80%
        assert compute_flex_status(10.9, 10.0) == "on_track"  # 109%
        assert compute_flex_status(9.0, 10.0) == "on_track"   # 90%

    def test_behind_when_under_80_percent(self):
        """Returns 'behind' when < 80% of target."""
        assert compute_flex_status(7.9, 10.0) == "behind"
        assert compute_flex_status(5.0, 10.0) == "behind"
        assert compute_flex_status(0.0, 10.0) == "behind"

    def test_zero_target_returns_on_track(self):
        """Returns 'on_track' when target is 0 (avoid division by zero)."""
        assert compute_flex_status(5.0, 0.0) == "on_track"
        assert compute_flex_status(0.0, 0.0) == "on_track"


class TestComputePacingStatus:
    """Tests for compute_pacing_status() function."""

    def test_completed_when_all_deliverables_done(self):
        """Returns 'completed' when all deliverables are done."""
        created = datetime(2026, 1, 1)
        deadline = date(2026, 2, 1)
        week_end = date(2026, 1, 15)

        assert compute_pacing_status(5, 5, created, deadline, week_end) == "completed"
        assert compute_pacing_status(10, 10, created, deadline, week_end) == "completed"

    def test_on_track_when_no_deliverables(self):
        """Returns 'on_track' when there are no deliverables."""
        created = datetime(2026, 1, 1)
        deadline = date(2026, 2, 1)
        week_end = date(2026, 1, 15)

        assert compute_pacing_status(0, 0, created, deadline, week_end) == "on_track"

    def test_ahead_when_completion_exceeds_time_ratio(self):
        """Returns 'ahead' when completion ratio > time ratio."""
        created = datetime(2026, 1, 1)
        deadline = date(2026, 2, 1)  # 31 days total
        week_end = date(2026, 1, 10)  # 9 days elapsed (~29% of time)

        # 50% complete with only 29% of time elapsed = ahead
        assert compute_pacing_status(5, 10, created, deadline, week_end) == "ahead"

    def test_behind_when_completion_below_threshold(self):
        """Returns 'behind' when completion ratio < 80% of time ratio."""
        created = datetime(2026, 1, 1)
        deadline = date(2026, 2, 1)  # 31 days total
        week_end = date(2026, 1, 25)  # 24 days elapsed (~77% of time)

        # 10% complete with 77% of time elapsed = behind
        assert compute_pacing_status(1, 10, created, deadline, week_end) == "behind"


class TestProcessEventsForReport:
    """Tests for process_events_for_report() function."""

    def test_filters_all_day_events(self):
        """All-day events are excluded."""
        events = [
            {"summary": "P1 Meeting", "start": {"date": "2026-02-10"}},  # All-day
            {"summary": "P2 Work", "start": {"dateTime": "2026-02-10T10:00:00Z"},
             "end": {"dateTime": "2026-02-10T11:00:00Z"}},
        ]

        allocation, filtered = process_events_for_report(events)

        # Only the timed event should appear
        assert len(filtered) == 1
        assert filtered[0]["title"] == "P2 Work"

    def test_filters_declined_events(self):
        """Declined events are excluded."""
        events = [
            {
                "summary": "P1 Meeting",
                "start": {"dateTime": "2026-02-10T10:00:00Z"},
                "end": {"dateTime": "2026-02-10T11:00:00Z"},
                "attendees": [{"self": True, "responseStatus": "declined"}],
            },
        ]

        allocation, filtered = process_events_for_report(events)

        assert len(filtered) == 0

    def test_matches_keywords_in_title(self):
        """Keywords (P1, P2, P3) are matched in event titles."""
        events = [
            {"summary": "[P1] Important work",
             "start": {"dateTime": "2026-02-10T10:00:00Z"},
             "end": {"dateTime": "2026-02-10T11:00:00Z"}},
            {"summary": "Random meeting",
             "start": {"dateTime": "2026-02-10T11:00:00Z"},
             "end": {"dateTime": "2026-02-10T12:00:00Z"}},
        ]

        allocation, filtered = process_events_for_report(events)

        assert filtered[0]["matched_keywords"] == ["P1"]
        assert filtered[1]["matched_keywords"] == []

    def test_includes_event_description_for_semantic_grouping(self):
        """Event descriptions are included for LLM semantic grouping."""
        events = [
            {
                "summary": "Team Meeting",
                "description": "Q1 revenue review with finance team - discuss budget allocation",
                "start": {"dateTime": "2026-02-10T10:00:00Z"},
                "end": {"dateTime": "2026-02-10T11:00:00Z"},
            },
            {
                "summary": "Client call",
                "description": "",  # Empty description
                "start": {"dateTime": "2026-02-10T14:00:00Z"},
                "end": {"dateTime": "2026-02-10T15:00:00Z"},
            },
            {
                "summary": "Quick sync",
                # No description field at all
                "start": {"dateTime": "2026-02-10T16:00:00Z"},
                "end": {"dateTime": "2026-02-10T16:30:00Z"},
            },
        ]

        allocation, filtered = process_events_for_report(events)

        # Description included for semantic grouping context
        assert filtered[0]["description"] == "Q1 revenue review with finance team - discuss budget allocation"
        assert filtered[1]["description"] == ""
        assert filtered[2]["description"] == ""  # Defaults to empty string


class TestEmptyReport:
    """Tests for _empty_report() helper."""

    def test_returns_correct_structure(self):
        """Empty report has correct structure with inert persistence fields."""
        week_start = date(2026, 2, 10)
        week_end = date(2026, 2, 16)

        report = _empty_report(week_start, week_end, is_current=True)

        assert report["success"] is True
        data = report["data"]
        assert data["week_start"] == "2026-02-10"
        assert data["week_end"] == "2026-02-16"
        assert data["is_current_week"] is True
        assert data["snapshot_saved"] is False
        assert data["weeks_backfilled"] == 0
        assert data["backfill_truncated"] is False
        assert data["priorities"] == []

    def test_past_week_empty_report(self):
        """Past week empty report has is_current_week=False."""
        week_start = date(2026, 2, 3)
        week_end = date(2026, 2, 9)

        report = _empty_report(week_start, week_end, is_current=False)

        assert report["data"]["is_current_week"] is False
        assert report["data"]["snapshot_saved"] is False  # Still false - no persistence


class TestGenerateWeeklyReportSimplified:
    """Tests for generate_weekly_report() simplified (no persistence)."""

    @pytest.mark.asyncio
    async def test_always_returns_snapshot_saved_false(self):
        """snapshot_saved is always False in simplified version."""
        user_id = uuid4()

        # Mock session with connection and priorities
        mock_session = AsyncMock()
        mock_connection = MagicMock()
        mock_connection.provider = "google"

        mock_priority = MagicMock()
        mock_priority.id = uuid4()
        mock_priority.name = "Test Priority"
        mock_priority.type = "flexible"
        mock_priority.calendar_keyword = "P1"
        mock_priority.status = "active"
        mock_priority.weekly_hour_target = Decimal("10.0")
        mock_priority.deliverables = []

        # Setup execute return values
        mock_session.execute = AsyncMock()

        # First call: get connection
        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = mock_connection

        # Second call: get priorities
        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [mock_priority]

        mock_session.execute.side_effect = [conn_result, priorities_result]

        mock_http_client = AsyncMock()

        with patch(
            "backend.apps.priority_guardian.services.weekly_report_service.ensure_valid_access_token"
        ) as mock_token, patch(
            "backend.apps.priority_guardian.services.weekly_report_service.get_user_timezone"
        ) as mock_tz, patch(
            "backend.apps.priority_guardian.services.weekly_report_service.list_events"
        ) as mock_events:
            mock_token.return_value = {"access_token": "test_token"}
            mock_tz.return_value = "UTC"
            mock_events.return_value = ([], 0)  # No events

            result = await generate_weekly_report(
                user_id=user_id,
                session=mock_session,
                http_client=mock_http_client,
            )

        assert result["success"] is True
        assert result["data"]["snapshot_saved"] is False

    @pytest.mark.asyncio
    async def test_always_returns_weeks_backfilled_zero(self):
        """weeks_backfilled is always 0 in simplified version."""
        user_id = uuid4()

        mock_session = AsyncMock()
        mock_connection = MagicMock()
        mock_connection.provider = "google"

        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = mock_connection

        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = []  # No priorities

        mock_session.execute.side_effect = [conn_result, priorities_result]

        mock_http_client = AsyncMock()

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

        assert result["data"]["weeks_backfilled"] == 0
        assert result["data"]["backfill_truncated"] is False

    @pytest.mark.asyncio
    async def test_always_returns_previous_week_null(self):
        """previous_week is always null for all priorities in simplified version."""
        user_id = uuid4()

        mock_session = AsyncMock()
        mock_connection = MagicMock()
        mock_connection.provider = "google"

        mock_priority = MagicMock()
        mock_priority.id = uuid4()
        mock_priority.name = "Test Priority"
        mock_priority.type = "flexible"
        mock_priority.calendar_keyword = "P1"
        mock_priority.status = "active"
        mock_priority.weekly_hour_target = Decimal("10.0")
        mock_priority.deliverables = []

        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = mock_connection

        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [mock_priority]

        mock_session.execute.side_effect = [conn_result, priorities_result]

        mock_http_client = AsyncMock()

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

        # All priorities should have previous_week = None
        for priority in result["data"]["priorities"]:
            assert priority["previous_week"] is None

    @pytest.mark.asyncio
    async def test_validates_week_start_is_monday(self):
        """Raises ValueError if week_start is not a Monday."""
        user_id = uuid4()
        mock_session = AsyncMock()
        mock_http_client = AsyncMock()

        # Tuesday
        tuesday = date(2026, 2, 10)

        with pytest.raises(ValueError, match="must be a Monday"):
            await generate_weekly_report(
                user_id=user_id,
                session=mock_session,
                http_client=mock_http_client,
                week_start=tuesday,
            )

    @pytest.mark.asyncio
    async def test_raises_error_when_google_not_connected(self):
        """Raises ValueError when Google Calendar is not connected."""
        user_id = uuid4()

        mock_session = AsyncMock()
        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = None  # No connection
        mock_session.execute.return_value = conn_result

        mock_http_client = AsyncMock()

        with pytest.raises(ValueError, match="Google Calendar not connected"):
            await generate_weekly_report(
                user_id=user_id,
                session=mock_session,
                http_client=mock_http_client,
            )
