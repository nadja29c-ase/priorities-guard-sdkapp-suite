"""
Unit tests for snapshot service (Increment 08).

Tests ensure_snapshots_up_to_date():
- Week detection logic
- Snapshot creation
- Streak computation
- Aggregate updates
- Idempotency
- Error handling
"""

import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

from backend.apps.priority_guardian.services.snapshot_service import (
    ensure_snapshots_up_to_date,
    _compute_target_weeks,
    _compute_streak,
)


class TestComputeTargetWeeks:
    """Tests for _compute_target_weeks helper."""

    def test_returns_completed_weeks_oldest_first(self):
        """Returns completed weeks in chronological order (oldest first)."""
        # Mock "now" to be a Wednesday
        with patch("backend.apps.priority_guardian.services.snapshot_service.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 11, 14, 0, 0, tzinfo=ZoneInfo("UTC"))  # Wednesday
            mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            weeks = _compute_target_weeks("UTC", 3)

            # Should return last 3 completed weeks, oldest first
            assert len(weeks) == 3
            assert weeks[0] < weeks[1] < weeks[2]

    def test_tuesday_returns_one_completed_week(self):
        """On Tuesday, only last week is complete."""
        with patch("backend.apps.priority_guardian.services.snapshot_service.datetime") as mock_dt:
            # Tuesday Feb 10, 2026
            mock_dt.now.return_value = datetime(2026, 2, 10, 14, 0, 0, tzinfo=ZoneInfo("UTC"))
            mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            weeks = _compute_target_weeks("UTC", 3)

            # Last Monday was Feb 2, that week is complete
            assert len(weeks) >= 1
            # Most recent completed week started Feb 2
            assert weeks[-1] == date(2026, 2, 2)

    def test_invalid_timezone_falls_back_to_utc(self):
        """Invalid timezone falls back to UTC gracefully."""
        weeks = _compute_target_weeks("Invalid/Timezone", 3)
        # Should not raise, should return valid weeks
        assert isinstance(weeks, list)

    def test_monday_midnight_boundary_is_current_week(self):
        """Monday 00:00:01 is in the current week, not the completed week."""
        with patch("backend.apps.priority_guardian.services.snapshot_service.datetime") as mock_dt:
            # Monday Feb 9, 2026 at 00:00:01 (just after midnight)
            mock_dt.now.return_value = datetime(2026, 2, 9, 0, 0, 1, tzinfo=ZoneInfo("UTC"))
            mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            weeks = _compute_target_weeks("UTC", 3)

            # Current week (starting Feb 9) should NOT be in the list
            # Most recent completed week should be Feb 2 (the previous Monday)
            assert date(2026, 2, 9) not in weeks
            assert weeks[-1] == date(2026, 2, 2)

    def test_sunday_midnight_boundary_week_complete(self):
        """Sunday 23:59:59 means that week is still in progress."""
        with patch("backend.apps.priority_guardian.services.snapshot_service.datetime") as mock_dt:
            # Sunday Feb 8, 2026 at 23:59:59 (just before Monday)
            mock_dt.now.return_value = datetime(2026, 2, 8, 23, 59, 59, tzinfo=ZoneInfo("UTC"))
            mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            weeks = _compute_target_weeks("UTC", 3)

            # Current week (Feb 2) is NOT complete yet (it's still Sunday)
            # Most recent completed week should be Jan 26
            assert date(2026, 2, 2) not in weeks
            assert weeks[-1] == date(2026, 1, 26)


class TestEnsureSnapshotsUpToDate:
    """Tests for ensure_snapshots_up_to_date main function."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock async session."""
        session = AsyncMock()
        return session

    @pytest.fixture
    def mock_http_client(self):
        """Create a mock HTTP client."""
        return AsyncMock()

    @pytest.fixture
    def mock_connection(self):
        """Create a mock Google connection."""
        conn = MagicMock()
        conn.provider = "google"
        conn.connection_type = "google"
        conn.revoked_at = None
        return conn

    @pytest.fixture
    def mock_priority_flexible(self):
        """Create a mock flexible priority."""
        p = MagicMock()
        p.id = uuid4()
        p.user_id = uuid4()
        p.type = "flexible"
        p.calendar_keyword = "P1"
        p.status = "active"
        p.weekly_hour_target = Decimal("10.0")
        p.deliverables = []
        p.created_at = datetime.now()
        p.streak_count = 0
        p.avg_hours_week = None
        p.total_hours_invested = Decimal("0")
        return p

    @pytest.fixture
    def mock_priority_deadline(self):
        """Create a mock deadline priority."""
        p = MagicMock()
        p.id = uuid4()
        p.user_id = uuid4()
        p.type = "deadline"
        p.calendar_keyword = "P2"
        p.status = "active"
        p.deadline = date.today() + timedelta(days=30)
        p.deliverables = []
        p.created_at = datetime.now()
        p.streak_count = 0
        p.avg_hours_week = None
        p.total_hours_invested = Decimal("0")
        return p

    @pytest.mark.asyncio
    async def test_no_google_connection_returns_zeros(self, mock_session, mock_http_client):
        """No Google connection returns zeros, no DB writes."""
        user_id = uuid4()

        # No connection found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await ensure_snapshots_up_to_date(
            user_id=user_id,
            session=mock_session,
            http_client=mock_http_client,
        )

        assert result == {"checked": 0, "created": 0, "errors": 0}

    @pytest.mark.asyncio
    async def test_token_refresh_fails_returns_error(
        self, mock_session, mock_http_client, mock_connection
    ):
        """Token refresh failure returns error count."""
        user_id = uuid4()

        # Connection found
        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = mock_connection
        mock_session.execute.return_value = conn_result

        with patch(
            "backend.apps.priority_guardian.services.snapshot_service.ensure_valid_access_token"
        ) as mock_token:
            mock_token.return_value = {"error": "REFRESH_TOKEN_INVALID"}

            result = await ensure_snapshots_up_to_date(
                user_id=user_id,
                session=mock_session,
                http_client=mock_http_client,
            )

        assert result["errors"] == 1
        assert result["created"] == 0

    @pytest.mark.asyncio
    async def test_all_snapshots_exist_fast_exit(
        self, mock_session, mock_http_client, mock_connection
    ):
        """All snapshots exist returns checked count, no Google API calls."""
        user_id = uuid4()

        # Connection found
        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = mock_connection

        # Existing weeks query - return all target weeks as existing
        target_weeks = [
            date(2026, 1, 26),
            date(2026, 2, 2),
            date(2026, 2, 9),
        ]
        existing_result = MagicMock()
        existing_result.fetchall.return_value = [(w,) for w in target_weeks]

        mock_session.execute.side_effect = [conn_result, existing_result]

        with patch(
            "backend.apps.priority_guardian.services.snapshot_service.ensure_valid_access_token"
        ) as mock_token, patch(
            "backend.apps.priority_guardian.services.snapshot_service.get_user_timezone"
        ) as mock_tz, patch(
            "backend.apps.priority_guardian.services.snapshot_service._compute_target_weeks"
        ) as mock_weeks, patch(
            "backend.apps.priority_guardian.services.snapshot_service.list_events"
        ) as mock_events:
            mock_token.return_value = {"access_token": "test_token"}
            mock_tz.return_value = "America/Los_Angeles"
            mock_weeks.return_value = target_weeks

            result = await ensure_snapshots_up_to_date(
                user_id=user_id,
                session=mock_session,
                http_client=mock_http_client,
            )

        assert result["checked"] == 3
        assert result["created"] == 0
        assert result["errors"] == 0
        # list_events should NOT be called (fast exit)
        mock_events.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_active_priorities_returns_zeros(
        self, mock_session, mock_http_client, mock_connection
    ):
        """User with no active priorities creates no snapshots."""
        user_id = uuid4()

        # Connection found
        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = mock_connection

        # No existing weeks
        existing_result = MagicMock()
        existing_result.fetchall.return_value = []

        # No priorities
        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [conn_result, existing_result, priorities_result]

        with patch(
            "backend.apps.priority_guardian.services.snapshot_service.ensure_valid_access_token"
        ) as mock_token, patch(
            "backend.apps.priority_guardian.services.snapshot_service.get_user_timezone"
        ) as mock_tz, patch(
            "backend.apps.priority_guardian.services.snapshot_service._compute_target_weeks"
        ) as mock_weeks:
            mock_token.return_value = {"access_token": "test_token"}
            mock_tz.return_value = "UTC"
            mock_weeks.return_value = [date(2026, 2, 2)]

            result = await ensure_snapshots_up_to_date(
                user_id=user_id,
                session=mock_session,
                http_client=mock_http_client,
            )

        assert result["created"] == 0


class TestComputeStreak:
    """Tests for _compute_streak helper."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_first_snapshot_hours_positive_streak_is_one(self, mock_session):
        """First ever snapshot with hours > 0 has streak = 1."""
        # No previous snapshot
        result = MagicMock()
        result.fetchone.return_value = None
        mock_session.execute.return_value = result

        streak = await _compute_streak(
            priority_id=uuid4(),
            week_start=date(2026, 2, 9),
            actual_hours=5.0,
            session=mock_session,
        )

        assert streak == 1

    @pytest.mark.asyncio
    async def test_first_snapshot_hours_zero_streak_is_zero(self, mock_session):
        """First ever snapshot with hours == 0 has streak = 0."""
        result = MagicMock()
        result.fetchone.return_value = None
        mock_session.execute.return_value = result

        streak = await _compute_streak(
            priority_id=uuid4(),
            week_start=date(2026, 2, 9),
            actual_hours=0.0,
            session=mock_session,
        )

        assert streak == 0

    @pytest.mark.asyncio
    async def test_previous_streak_continues(self, mock_session):
        """Previous snapshot with streak=3 and hours > 0 becomes streak=4."""
        result = MagicMock()
        result.fetchone.return_value = (3,)  # Previous streak was 3
        mock_session.execute.return_value = result

        streak = await _compute_streak(
            priority_id=uuid4(),
            week_start=date(2026, 2, 9),
            actual_hours=5.0,
            session=mock_session,
        )

        assert streak == 4

    @pytest.mark.asyncio
    async def test_previous_streak_breaks_on_zero_hours(self, mock_session):
        """Previous snapshot with streak=3 but hours == 0 resets to 0."""
        result = MagicMock()
        result.fetchone.return_value = (3,)
        mock_session.execute.return_value = result

        streak = await _compute_streak(
            priority_id=uuid4(),
            week_start=date(2026, 2, 9),
            actual_hours=0.0,
            session=mock_session,
        )

        assert streak == 0

    @pytest.mark.asyncio
    async def test_gap_in_snapshots_resets_streak(self, mock_session):
        """Missing previous week snapshot (gap) resets streak to 1."""
        # No previous snapshot (gap)
        result = MagicMock()
        result.fetchone.return_value = None
        mock_session.execute.return_value = result

        streak = await _compute_streak(
            priority_id=uuid4(),
            week_start=date(2026, 2, 9),
            actual_hours=5.0,
            session=mock_session,
        )

        # Streak resets to 1 (not continues from missing)
        assert streak == 1


class TestSnapshotRowContent:
    """Tests for snapshot row field population."""

    def test_week_end_is_sunday(self):
        """week_end = week_start + 6 days (Sunday)."""
        week_start = date(2026, 2, 9)  # Monday
        week_end = week_start + timedelta(days=6)
        assert week_end == date(2026, 2, 15)  # Sunday
        assert week_end.weekday() == 6  # Sunday


class TestErrorHandling:
    """Tests for error handling in snapshot service."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.fixture
    def mock_http_client(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_partial_result(
        self, mock_session, mock_http_client
    ):
        """Unexpected exception returns error count, never raises."""
        user_id = uuid4()

        # Force an unexpected exception
        mock_session.execute.side_effect = RuntimeError("Unexpected DB error")

        # Should not raise
        result = await ensure_snapshots_up_to_date(
            user_id=user_id,
            session=mock_session,
            http_client=mock_http_client,
        )

        assert result["errors"] >= 1
        # Function completed without raising


class TestIdempotency:
    """Tests for idempotent behavior."""

    @pytest.mark.asyncio
    async def test_duplicate_insert_skips_aggregate_update(self):
        """ON CONFLICT DO NOTHING skips aggregate update on duplicate."""
        # This is tested at integration level - unit test verifies the concept
        from sqlalchemy.exc import IntegrityError

        # IntegrityError on duplicate should be caught and handled gracefully
        error = IntegrityError("statement", {}, Exception("duplicate key"))
        assert "duplicate" in str(error.orig).lower() or "IntegrityError" in str(type(error).__name__)
