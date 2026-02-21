"""
Unit tests for weekly report service.

Tests the generate_weekly_report() function:
- Snapshot-based reports for past weeks
- Live calendar computation for current weeks
- Fallback to live computation when no snapshots exist
- Pure computation functions (flex_status, pacing_status, etc.)
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
    _build_report_from_snapshots,
)
from backend.apps.priority_guardian.services.utils import priority_eligible_for_week


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


class TestPriorityEligibleForWeek:
    """Tests for priority_eligible_for_week() helper."""

    def test_priority_created_on_monday_eligible_same_week(self):
        """Priority created on Monday is eligible for that week."""
        created = date(2026, 2, 9)  # Monday
        week_start = date(2026, 2, 9)  # Same Monday
        assert priority_eligible_for_week(created, week_start) is True

    def test_priority_created_on_tuesday_not_eligible_same_week(self):
        """Priority created on Tuesday is NOT eligible for that week (partial week)."""
        created = date(2026, 2, 10)  # Tuesday
        week_start = date(2026, 2, 9)  # Monday of same week
        assert priority_eligible_for_week(created, week_start) is False

    def test_priority_created_on_tuesday_eligible_next_week(self):
        """Priority created on Tuesday IS eligible for the following week."""
        created = date(2026, 2, 10)  # Tuesday
        week_start = date(2026, 2, 16)  # Next Monday
        assert priority_eligible_for_week(created, week_start) is True

    def test_priority_created_on_sunday_eligible_next_week(self):
        """Priority created on Sunday is eligible for the next week."""
        created = date(2026, 2, 15)  # Sunday
        week_start = date(2026, 2, 16)  # Next Monday
        assert priority_eligible_for_week(created, week_start) is True

    def test_priority_created_before_week_start(self):
        """Priority created well before week_start is eligible."""
        created = date(2026, 1, 1)  # Wednesday
        week_start = date(2026, 2, 16)  # Monday many weeks later
        assert priority_eligible_for_week(created, week_start) is True


class TestBuildReportFromSnapshots:
    """Tests for _build_report_from_snapshots() function."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_snapshots(self):
        """Returns None when no snapshot rows exist for the week."""
        user_id = uuid4()
        week_start = date(2026, 2, 9)
        week_end = date(2026, 2, 15)

        mock_session = AsyncMock()

        # First query: snapshots - returns empty
        snapshot_result = MagicMock()
        snapshot_result.all.return_value = []

        mock_session.execute.return_value = snapshot_result

        result = await _build_report_from_snapshots(
            user_id=user_id,
            week_start=week_start,
            week_end=week_end,
            session=mock_session,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_report_with_snapshot_data(self):
        """Returns report dict when snapshots exist with full coverage."""
        user_id = uuid4()
        priority_id = uuid4()
        week_start = date(2026, 2, 9)
        week_end = date(2026, 2, 15)

        mock_session = AsyncMock()

        # Create mock snapshot and priority
        mock_snapshot = MagicMock()
        mock_snapshot.actual_hours = Decimal("7.5")
        mock_snapshot.target_hours = Decimal("10.0")
        mock_snapshot.streak_at_snapshot = 3
        mock_snapshot.calendar_keyword_at_snapshot = "P1"
        mock_snapshot.other_hours = Decimal("2.5")
        mock_snapshot.total_tracked_hours = Decimal("10.0")

        mock_priority = MagicMock()
        mock_priority.id = priority_id
        mock_priority.name = "Test Priority"
        mock_priority.type = "flexible"
        mock_priority.calendar_keyword = "P2"  # Current keyword (different from snapshot)
        mock_priority.weekly_hour_target = Decimal("10.0")
        mock_priority.total_hours_invested = Decimal("50.0")
        mock_priority.deliverables = []
        mock_priority.created_at = datetime(2026, 1, 1)
        mock_priority.retired_at = None

        # First query: snapshots with priorities
        snapshot_result = MagicMock()
        snapshot_result.all.return_value = [(mock_snapshot, mock_priority)]

        # Second query: all priorities for expected count
        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [mock_priority]

        mock_session.execute.side_effect = [snapshot_result, priorities_result]

        result = await _build_report_from_snapshots(
            user_id=user_id,
            week_start=week_start,
            week_end=week_end,
            session=mock_session,
        )

        assert result is not None
        assert result["success"] is True
        data = result["data"]
        assert data["is_current_week"] is False
        assert data["snapshot_saved"] is True  # Indicates data came from snapshots
        assert data["all_events"] == []  # No event data from snapshots
        assert data["time_allocation"]["other_hours"] == 2.5
        assert data["time_allocation"]["total_tracked_hours"] == 10.0

        # Check priority data uses snapshot keyword, not current
        priority_data = data["priorities"][0]
        assert priority_data["calendar_keyword"] == "P1"  # From snapshot
        assert priority_data["actual_hours"] == 7.5
        assert priority_data["streak_count"] == 3

    @pytest.mark.asyncio
    async def test_flex_status_computed_from_snapshot_hours(self):
        """flex_status is computed from snapshot actual/target hours."""
        user_id = uuid4()
        week_start = date(2026, 2, 9)
        week_end = date(2026, 2, 15)

        mock_session = AsyncMock()

        # 120% of target = ahead
        mock_snapshot = MagicMock()
        mock_snapshot.actual_hours = Decimal("12.0")
        mock_snapshot.target_hours = Decimal("10.0")
        mock_snapshot.streak_at_snapshot = 1
        mock_snapshot.calendar_keyword_at_snapshot = "P1"
        mock_snapshot.other_hours = None
        mock_snapshot.total_tracked_hours = None

        mock_priority = MagicMock()
        mock_priority.id = uuid4()
        mock_priority.name = "Test"
        mock_priority.type = "flexible"
        mock_priority.calendar_keyword = "P1"
        mock_priority.total_hours_invested = Decimal("0")
        mock_priority.deliverables = []
        mock_priority.created_at = datetime(2026, 1, 1)
        mock_priority.retired_at = None

        snapshot_result = MagicMock()
        snapshot_result.all.return_value = [(mock_snapshot, mock_priority)]

        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [mock_priority]

        mock_session.execute.side_effect = [snapshot_result, priorities_result]

        result = await _build_report_from_snapshots(
            user_id=user_id,
            week_start=week_start,
            week_end=week_end,
            session=mock_session,
        )

        assert result["data"]["priorities"][0]["flex_status"] == "ahead"

    @pytest.mark.asyncio
    async def test_snapshot_report_uses_stored_other_hours(self):
        """Snapshot report uses stored other_hours and total_tracked_hours values."""
        user_id = uuid4()
        week_start = date(2026, 2, 9)
        week_end = date(2026, 2, 15)

        mock_session = AsyncMock()

        mock_snapshot = MagicMock()
        mock_snapshot.actual_hours = Decimal("5.0")
        mock_snapshot.target_hours = Decimal("10.0")
        mock_snapshot.streak_at_snapshot = 1
        mock_snapshot.calendar_keyword_at_snapshot = "P1"
        mock_snapshot.other_hours = Decimal("12.5")  # Stored value
        mock_snapshot.total_tracked_hours = Decimal("25.0")  # Stored value

        mock_priority = MagicMock()
        mock_priority.id = uuid4()
        mock_priority.name = "Test"
        mock_priority.type = "flexible"
        mock_priority.calendar_keyword = "P1"
        mock_priority.total_hours_invested = Decimal("0")
        mock_priority.deliverables = []
        mock_priority.created_at = datetime(2026, 1, 1)
        mock_priority.retired_at = None

        snapshot_result = MagicMock()
        snapshot_result.all.return_value = [(mock_snapshot, mock_priority)]

        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [mock_priority]

        mock_session.execute.side_effect = [snapshot_result, priorities_result]

        result = await _build_report_from_snapshots(
            user_id=user_id,
            week_start=week_start,
            week_end=week_end,
            session=mock_session,
        )

        # Should use stored values, not computed zeros
        assert result["data"]["time_allocation"]["other_hours"] == 12.5
        assert result["data"]["time_allocation"]["total_tracked_hours"] == 25.0

    @pytest.mark.asyncio
    async def test_snapshot_report_null_other_hours_defaults_to_zero(self):
        """Pre-migration snapshots with NULL other_hours default to 0.0."""
        user_id = uuid4()
        week_start = date(2026, 2, 9)
        week_end = date(2026, 2, 15)

        mock_session = AsyncMock()

        mock_snapshot = MagicMock()
        mock_snapshot.actual_hours = Decimal("5.0")
        mock_snapshot.target_hours = Decimal("10.0")
        mock_snapshot.streak_at_snapshot = 1
        mock_snapshot.calendar_keyword_at_snapshot = "P1"
        mock_snapshot.other_hours = None  # Pre-migration
        mock_snapshot.total_tracked_hours = None  # Pre-migration

        mock_priority = MagicMock()
        mock_priority.id = uuid4()
        mock_priority.name = "Test"
        mock_priority.type = "flexible"
        mock_priority.calendar_keyword = "P1"
        mock_priority.total_hours_invested = Decimal("0")
        mock_priority.deliverables = []
        mock_priority.created_at = datetime(2026, 1, 1)
        mock_priority.retired_at = None

        snapshot_result = MagicMock()
        snapshot_result.all.return_value = [(mock_snapshot, mock_priority)]

        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [mock_priority]

        mock_session.execute.side_effect = [snapshot_result, priorities_result]

        result = await _build_report_from_snapshots(
            user_id=user_id,
            week_start=week_start,
            week_end=week_end,
            session=mock_session,
        )

        # Pre-migration: other_hours defaults to 0, total_tracked_hours computed from priority hours
        assert result["data"]["time_allocation"]["other_hours"] == 0.0
        # total_tracked_hours should be 5.0 (priority hours) + 0.0 (other) since stored was None
        assert result["data"]["time_allocation"]["total_tracked_hours"] == 5.0

    @pytest.mark.asyncio
    async def test_partial_snapshots_returns_none(self):
        """Returns None when snapshot count < expected priority count."""
        user_id = uuid4()
        week_start = date(2026, 2, 9)
        week_end = date(2026, 2, 15)

        mock_session = AsyncMock()

        # Only one snapshot exists
        mock_snapshot = MagicMock()
        mock_snapshot.actual_hours = Decimal("5.0")
        mock_snapshot.target_hours = Decimal("10.0")
        mock_snapshot.streak_at_snapshot = 1
        mock_snapshot.calendar_keyword_at_snapshot = "P1"
        mock_snapshot.other_hours = None
        mock_snapshot.total_tracked_hours = None

        mock_priority1 = MagicMock()
        mock_priority1.id = uuid4()
        mock_priority1.name = "Priority 1"
        mock_priority1.type = "flexible"
        mock_priority1.calendar_keyword = "P1"
        mock_priority1.deliverables = []
        mock_priority1.created_at = datetime(2026, 1, 1)  # Created before week
        mock_priority1.retired_at = None

        # Second priority also should have snapshot but doesn't
        mock_priority2 = MagicMock()
        mock_priority2.id = uuid4()
        mock_priority2.name = "Priority 2"
        mock_priority2.type = "flexible"
        mock_priority2.calendar_keyword = "P2"
        mock_priority2.deliverables = []
        mock_priority2.created_at = datetime(2026, 1, 1)  # Created before week
        mock_priority2.retired_at = None

        # Only 1 snapshot row
        snapshot_result = MagicMock()
        snapshot_result.all.return_value = [(mock_snapshot, mock_priority1)]

        # But 2 priorities should have snapshots
        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [mock_priority1, mock_priority2]

        mock_session.execute.side_effect = [snapshot_result, priorities_result]

        result = await _build_report_from_snapshots(
            user_id=user_id,
            week_start=week_start,
            week_end=week_end,
            session=mock_session,
        )

        # Should return None due to partial coverage
        assert result is None

    @pytest.mark.asyncio
    async def test_uses_current_keyword_when_snapshot_keyword_null(self):
        """Falls back to current keyword when calendar_keyword_at_snapshot is null."""
        user_id = uuid4()
        week_start = date(2026, 2, 9)
        week_end = date(2026, 2, 15)

        mock_session = AsyncMock()

        # Pre-migration snapshot without calendar_keyword_at_snapshot
        mock_snapshot = MagicMock()
        mock_snapshot.actual_hours = Decimal("5.0")
        mock_snapshot.target_hours = Decimal("10.0")
        mock_snapshot.streak_at_snapshot = 1
        mock_snapshot.calendar_keyword_at_snapshot = None  # Pre-migration
        mock_snapshot.other_hours = None
        mock_snapshot.total_tracked_hours = None

        mock_priority = MagicMock()
        mock_priority.id = uuid4()
        mock_priority.name = "Test"
        mock_priority.type = "flexible"
        mock_priority.calendar_keyword = "P3"  # Current keyword
        mock_priority.total_hours_invested = Decimal("0")
        mock_priority.deliverables = []
        mock_priority.created_at = datetime(2026, 1, 1)
        mock_priority.retired_at = None

        snapshot_result = MagicMock()
        snapshot_result.all.return_value = [(mock_snapshot, mock_priority)]

        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [mock_priority]

        mock_session.execute.side_effect = [snapshot_result, priorities_result]

        result = await _build_report_from_snapshots(
            user_id=user_id,
            week_start=week_start,
            week_end=week_end,
            session=mock_session,
        )

        # Should use current keyword P3 as fallback
        assert result["data"]["priorities"][0]["calendar_keyword"] == "P3"

    @pytest.mark.asyncio
    async def test_response_shape_matches_live_report(self):
        """Snapshot report has same shape as live computation report."""
        user_id = uuid4()
        week_start = date(2026, 2, 9)
        week_end = date(2026, 2, 15)

        mock_session = AsyncMock()

        mock_snapshot = MagicMock()
        mock_snapshot.actual_hours = Decimal("8.0")
        mock_snapshot.target_hours = Decimal("10.0")
        mock_snapshot.streak_at_snapshot = 2
        mock_snapshot.calendar_keyword_at_snapshot = "P1"
        mock_snapshot.other_hours = Decimal("3.0")
        mock_snapshot.total_tracked_hours = Decimal("11.0")

        mock_priority = MagicMock()
        mock_priority.id = uuid4()
        mock_priority.name = "Flexible Priority"
        mock_priority.type = "flexible"
        mock_priority.calendar_keyword = "P1"
        mock_priority.total_hours_invested = Decimal("25.0")
        mock_priority.deliverables = []
        mock_priority.created_at = datetime(2026, 1, 1)
        mock_priority.retired_at = None

        snapshot_result = MagicMock()
        snapshot_result.all.return_value = [(mock_snapshot, mock_priority)]

        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [mock_priority]

        mock_session.execute.side_effect = [snapshot_result, priorities_result]

        result = await _build_report_from_snapshots(
            user_id=user_id,
            week_start=week_start,
            week_end=week_end,
            session=mock_session,
        )

        # Verify all required top-level keys
        assert "success" in result
        assert "data" in result

        data = result["data"]
        required_keys = [
            "week_start", "week_end", "is_current_week", "snapshot_saved",
            "weeks_backfilled", "backfill_truncated", "priorities",
            "time_allocation", "all_events"
        ]
        for key in required_keys:
            assert key in data, f"Missing key: {key}"

        # Verify priority shape
        priority = data["priorities"][0]
        priority_keys = [
            "id", "name", "type", "calendar_keyword", "actual_hours",
            "event_count", "target_hours", "flex_status", "streak_count",
            "total_hours_invested", "previous_week"
        ]
        for key in priority_keys:
            assert key in priority, f"Missing priority key: {key}"

        # Verify time_allocation shape
        ta = data["time_allocation"]
        assert "total_tracked_hours" in ta
        assert "keywords" in ta
        assert "other_hours" in ta
        for kw in ["P1", "P2", "P3"]:
            assert kw in ta["keywords"]
            assert "hours" in ta["keywords"][kw]
            assert "event_count" in ta["keywords"][kw]


class TestRetiredPriorityHandlingInReports:
    """Tests for retired priority handling in weekly reports.

    These tests verify:
    - Current week reports exclude retired priorities
    - Past week reports include retired priorities' historical data from snapshots
    - Keyword comes from snapshot, not from (now NULL) priority.calendar_keyword
    """

    @pytest.mark.asyncio
    async def test_weekly_report_excludes_retired_from_current_week(self):
        """generate_weekly_report() for current week excludes retired priorities.

        The priority query filters by status='active', so retired priorities
        should not appear in current week reports.
        """
        user_id = uuid4()

        mock_session = AsyncMock()
        mock_connection = MagicMock()
        mock_connection.provider = "google"

        # Create active priority
        active_priority = MagicMock()
        active_priority.id = uuid4()
        active_priority.name = "Active Priority"
        active_priority.type = "flexible"
        active_priority.calendar_keyword = "P1"
        active_priority.status = "active"
        active_priority.weekly_hour_target = Decimal("10.0")
        active_priority.deliverables = []

        # Retired priority should NOT be returned by the query
        # (because the query filters by status='active')
        # So we don't include it in mock results

        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = mock_connection

        priorities_result = MagicMock()
        # Only active priority returned (retired filtered out by query)
        priorities_result.scalars.return_value.all.return_value = [active_priority]

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

        # Only active priority in report
        assert len(result["data"]["priorities"]) == 1
        assert result["data"]["priorities"][0]["name"] == "Active Priority"

    @pytest.mark.asyncio
    async def test_past_week_report_includes_retired_priority_snapshots(self):
        """_build_report_from_snapshots() returns data for retired priorities.

        When a priority is retired but has snapshots from a past week,
        those snapshots should still be included in past-week reports.
        The priority row still exists (just status='retired').
        """
        user_id = uuid4()
        priority_id = uuid4()
        week_start = date(2026, 2, 9)
        week_end = date(2026, 2, 15)

        mock_session = AsyncMock()

        # Snapshot created before retirement
        mock_snapshot = MagicMock()
        mock_snapshot.actual_hours = Decimal("8.5")
        mock_snapshot.target_hours = Decimal("10.0")
        mock_snapshot.streak_at_snapshot = 5
        mock_snapshot.calendar_keyword_at_snapshot = "P1"  # Preserved from when active
        mock_snapshot.other_hours = Decimal("2.0")
        mock_snapshot.total_tracked_hours = Decimal("10.5")

        # Priority is now retired (but row still exists)
        mock_priority = MagicMock()
        mock_priority.id = priority_id
        mock_priority.name = "Now Retired Priority"
        mock_priority.type = "flexible"
        mock_priority.calendar_keyword = None  # NULL after retirement
        mock_priority.status = "retired"
        mock_priority.total_hours_invested = Decimal("50.0")
        mock_priority.deliverables = []
        mock_priority.created_at = datetime(2026, 1, 1)
        mock_priority.retired_at = datetime(2026, 2, 20)  # Retired after the week

        # Snapshot query returns the snapshot+priority pair
        snapshot_result = MagicMock()
        snapshot_result.all.return_value = [(mock_snapshot, mock_priority)]

        # Priority count query (for coverage check) should count priorities
        # that WERE active during that week based on created_at/retired_at
        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [mock_priority]

        mock_session.execute.side_effect = [snapshot_result, priorities_result]

        result = await _build_report_from_snapshots(
            user_id=user_id,
            week_start=week_start,
            week_end=week_end,
            session=mock_session,
        )

        # Report should include the retired priority's historical data
        assert result is not None
        assert result["success"] is True
        assert len(result["data"]["priorities"]) == 1

        priority_data = result["data"]["priorities"][0]
        assert priority_data["name"] == "Now Retired Priority"
        assert priority_data["actual_hours"] == 8.5
        assert priority_data["streak_count"] == 5

    @pytest.mark.asyncio
    async def test_past_week_report_keyword_from_snapshot_not_priority(self):
        """Past-week report uses calendar_keyword_at_snapshot, not priority.calendar_keyword.

        After retirement, priority.calendar_keyword is NULL. The past-week
        report must use the snapshot's calendar_keyword_at_snapshot value
        so that keyword hours are correctly attributed.
        """
        user_id = uuid4()
        week_start = date(2026, 2, 9)
        week_end = date(2026, 2, 15)

        mock_session = AsyncMock()

        # Snapshot has the keyword value from when priority was active
        mock_snapshot = MagicMock()
        mock_snapshot.actual_hours = Decimal("6.0")
        mock_snapshot.target_hours = Decimal("10.0")
        mock_snapshot.streak_at_snapshot = 2
        mock_snapshot.calendar_keyword_at_snapshot = "P1"  # CAPTURED AT SNAPSHOT TIME
        mock_snapshot.other_hours = Decimal("4.0")
        mock_snapshot.total_tracked_hours = Decimal("10.0")

        # Priority is now retired with NULL keyword
        mock_priority = MagicMock()
        mock_priority.id = uuid4()
        mock_priority.name = "Retired P1 Priority"
        mock_priority.type = "flexible"
        mock_priority.calendar_keyword = None  # NULL after retirement
        mock_priority.status = "retired"
        mock_priority.total_hours_invested = Decimal("30.0")
        mock_priority.deliverables = []
        mock_priority.created_at = datetime(2026, 1, 1)
        mock_priority.retired_at = datetime(2026, 2, 18)

        snapshot_result = MagicMock()
        snapshot_result.all.return_value = [(mock_snapshot, mock_priority)]

        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [mock_priority]

        mock_session.execute.side_effect = [snapshot_result, priorities_result]

        result = await _build_report_from_snapshots(
            user_id=user_id,
            week_start=week_start,
            week_end=week_end,
            session=mock_session,
        )

        assert result is not None

        # Critical assertion: keyword should be P1 (from snapshot), NOT NULL
        priority_data = result["data"]["priorities"][0]
        assert priority_data["calendar_keyword"] == "P1"
        assert priority_data["calendar_keyword"] is not None

        # And the time_allocation should have P1 hours attributed
        time_alloc = result["data"]["time_allocation"]
        assert time_alloc["keywords"]["P1"]["hours"] == 6.0
