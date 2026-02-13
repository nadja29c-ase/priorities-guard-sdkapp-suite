"""
Integration tests for snapshot persistence (Increment 08).

Tests the full flow:
- Dashboard load triggers snapshot creation
- Backfill creates snapshots for missing weeks
- Aggregates update correctly
- Streak computation across weeks
- Idempotency
"""

import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from uuid import uuid4

from backend.apps.priority_guardian.services.snapshot_service import (
    ensure_snapshots_up_to_date,
)


def create_mock_session():
    """Create a properly configured mock async session."""
    session = MagicMock()
    # execute returns awaitable
    session.execute = AsyncMock()
    # flush and commit are async
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    # add is NOT async - but no longer used in new flow
    session.add = MagicMock()
    return session


@pytest.fixture
def mock_session():
    """Create a mock async session."""
    return create_mock_session()


@pytest.fixture
def mock_http_client():
    """Create a mock HTTP client."""
    return AsyncMock()


@pytest.fixture
def mock_google_connection():
    """Create a mock Google connection."""
    conn = MagicMock()
    conn.provider = "google"
    conn.connection_type = "google"
    conn.revoked_at = None
    return conn


@pytest.fixture
def mock_flexible_priority():
    """Create a mock flexible priority."""
    p = MagicMock()
    p.id = uuid4()
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
def mock_deadline_priority():
    """Create a mock deadline priority."""
    p = MagicMock()
    p.id = uuid4()
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


@pytest.fixture
def mock_calendar_events():
    """Create mock calendar events."""
    now = datetime.now()
    return [
        {
            "id": "event1",
            "summary": "P1 - Work session",
            "start": {"dateTime": (now - timedelta(hours=3)).isoformat()},
            "end": {"dateTime": now.isoformat()},
            "status": "confirmed",
        },
        {
            "id": "event2",
            "summary": "P2 - Deadline work",
            "start": {"dateTime": (now - timedelta(hours=5)).isoformat()},
            "end": {"dateTime": (now - timedelta(hours=3)).isoformat()},
            "status": "confirmed",
        },
        {
            "id": "event3",
            "summary": "Team meeting",
            "start": {"dateTime": (now - timedelta(hours=6)).isoformat()},
            "end": {"dateTime": (now - timedelta(hours=5)).isoformat()},
            "status": "confirmed",
        },
    ]


class TestFullFlow:
    """Tests for full dashboard load → snapshot creation flow."""

    @pytest.mark.asyncio
    async def test_dashboard_load_creates_snapshots(
        self,
        mock_http_client,
        mock_google_connection,
        mock_flexible_priority,
        mock_calendar_events,
    ):
        """
        Dashboard load triggers snapshot creation for missing weeks.
        """
        user_id = uuid4()
        mock_session = create_mock_session()

        # Setup mock results
        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = mock_google_connection

        existing_result = MagicMock()
        existing_result.fetchall.return_value = []  # No existing snapshots

        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [mock_flexible_priority]

        streak_result = MagicMock()
        streak_result.fetchone.return_value = None  # No previous snapshot

        # INSERT ... RETURNING id returns a row (insert succeeded)
        insert_result = MagicMock()
        insert_result.fetchone.return_value = (uuid4(),)

        avg_result = MagicMock()
        avg_result.scalar.return_value = Decimal("3.0")

        update_result = MagicMock()  # For the UPDATE statement

        # New flow execute order:
        # 1. connection, 2. existing weeks, 3. priorities
        # Then for each priority: streak, INSERT, avg, UPDATE
        mock_session.execute.side_effect = [
            conn_result,
            existing_result,
            priorities_result,
            streak_result,
            insert_result,
            avg_result,
            update_result,
        ]

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
            mock_weeks.return_value = [date(2026, 2, 2)]
            mock_events.return_value = (mock_calendar_events, 0)

            result = await ensure_snapshots_up_to_date(
                user_id=user_id,
                session=mock_session,
                http_client=mock_http_client,
            )

        assert result["checked"] == 1
        assert result["created"] == 1
        assert mock_session.commit.called


class TestBackfill:
    """Tests for backfill of multiple missing weeks."""

    @pytest.mark.asyncio
    async def test_backfill_three_weeks_creates_three_snapshots(
        self,
        mock_http_client,
        mock_google_connection,
        mock_flexible_priority,
        mock_calendar_events,
    ):
        """
        Backfilling 3 weeks for 1 priority creates 3 snapshot rows.
        """
        user_id = uuid4()
        mock_session = create_mock_session()

        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = mock_google_connection

        existing_result = MagicMock()
        existing_result.fetchall.return_value = []

        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [mock_flexible_priority]

        streak_result = MagicMock()
        streak_result.fetchone.return_value = None

        insert_result = MagicMock()
        insert_result.fetchone.return_value = (uuid4(),)  # Insert succeeded

        avg_result = MagicMock()
        avg_result.scalar.return_value = Decimal("3.0")

        update_result = MagicMock()

        # 3 weeks × 1 priority = 3 iterations
        # Each iteration: streak, INSERT, avg, update
        mock_session.execute.side_effect = [
            conn_result,
            existing_result,
            priorities_result,
        ] + [streak_result, insert_result, avg_result, update_result] * 3

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
            mock_tz.return_value = "UTC"
            mock_weeks.return_value = [
                date(2026, 1, 19),
                date(2026, 1, 26),
                date(2026, 2, 2),
            ]
            mock_events.return_value = (mock_calendar_events, 0)

            result = await ensure_snapshots_up_to_date(
                user_id=user_id,
                session=mock_session,
                http_client=mock_http_client,
            )

        assert result["checked"] == 3
        assert result["created"] == 3


class TestStreakComputation:
    """Tests for streak computation across weeks."""

    @pytest.mark.asyncio
    async def test_streak_continues_across_weeks(
        self,
        mock_http_client,
        mock_google_connection,
        mock_flexible_priority,
    ):
        """
        Consecutive weeks with hours > 0 continue the streak.
        """
        user_id = uuid4()
        mock_session = create_mock_session()

        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = mock_google_connection

        existing_result = MagicMock()
        existing_result.fetchall.return_value = []

        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [mock_flexible_priority]

        # Week 1: No previous snapshot, streak starts at 1
        streak_result_1 = MagicMock()
        streak_result_1.fetchone.return_value = None

        # Week 2: Previous snapshot with streak=1, becomes streak=2
        streak_result_2 = MagicMock()
        streak_result_2.fetchone.return_value = (1,)

        # Week 3: Previous snapshot with streak=2, becomes streak=3
        streak_result_3 = MagicMock()
        streak_result_3.fetchone.return_value = (2,)

        insert_result = MagicMock()
        insert_result.fetchone.return_value = (uuid4(),)

        avg_result = MagicMock()
        avg_result.scalar.return_value = Decimal("5.0")

        update_result = MagicMock()

        events_with_hours = [
            {
                "id": "event1",
                "summary": "P1 - Work",
                "start": {"dateTime": "2026-02-10T09:00:00-08:00"},
                "end": {"dateTime": "2026-02-10T12:00:00-08:00"},
                "status": "confirmed",
            }
        ]

        mock_session.execute.side_effect = [
            conn_result,
            existing_result,
            priorities_result,
            streak_result_1, insert_result, avg_result, update_result,  # Week 1
            streak_result_2, insert_result, avg_result, update_result,  # Week 2
            streak_result_3, insert_result, avg_result, update_result,  # Week 3
        ]

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
            mock_tz.return_value = "UTC"
            mock_weeks.return_value = [
                date(2026, 1, 19),
                date(2026, 1, 26),
                date(2026, 2, 2),
            ]
            mock_events.return_value = (events_with_hours, 0)

            result = await ensure_snapshots_up_to_date(
                user_id=user_id,
                session=mock_session,
                http_client=mock_http_client,
            )

        assert result["created"] == 3

    @pytest.mark.asyncio
    async def test_streak_breaks_on_zero_hours(
        self,
        mock_http_client,
        mock_google_connection,
        mock_flexible_priority,
    ):
        """
        Week with zero hours breaks the streak.
        """
        user_id = uuid4()
        mock_session = create_mock_session()

        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = mock_google_connection

        existing_result = MagicMock()
        existing_result.fetchall.return_value = []

        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [mock_flexible_priority]

        # When hours=0, _compute_streak returns 0 without querying DB
        # So no streak_result needed

        insert_result = MagicMock()
        insert_result.fetchone.return_value = (uuid4(),)

        avg_result = MagicMock()
        avg_result.scalar.return_value = Decimal("0.0")

        update_result = MagicMock()

        # Empty events - no hours for this priority
        empty_events = []

        # When hours=0, no streak query is made (returns early)
        mock_session.execute.side_effect = [
            conn_result,
            existing_result,
            priorities_result,
            # No streak query (hours=0 returns early)
            insert_result,
            avg_result,
            update_result,
        ]

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
            mock_tz.return_value = "UTC"
            mock_weeks.return_value = [date(2026, 2, 2)]
            mock_events.return_value = (empty_events, 0)

            result = await ensure_snapshots_up_to_date(
                user_id=user_id,
                session=mock_session,
                http_client=mock_http_client,
            )

        assert result["created"] == 1  # Snapshot still created (with streak=0)


class TestIdempotency:
    """Tests for idempotent behavior."""

    @pytest.mark.asyncio
    async def test_second_call_creates_zero_rows(
        self,
        mock_http_client,
        mock_google_connection,
        mock_flexible_priority,
    ):
        """
        Second call for same week creates no new rows.
        """
        user_id = uuid4()
        mock_session = create_mock_session()

        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = mock_google_connection

        # All weeks already have snapshots
        existing_result = MagicMock()
        existing_result.fetchall.return_value = [(date(2026, 2, 2),)]

        mock_session.execute.side_effect = [conn_result, existing_result]

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

        assert result["checked"] == 1
        assert result["created"] == 0

    @pytest.mark.asyncio
    async def test_insert_conflict_returns_no_row(
        self,
        mock_http_client,
        mock_google_connection,
        mock_flexible_priority,
        mock_calendar_events,
    ):
        """
        INSERT ... ON CONFLICT DO NOTHING returns None when row exists.
        """
        user_id = uuid4()
        mock_session = create_mock_session()

        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = mock_google_connection

        existing_result = MagicMock()
        existing_result.fetchall.return_value = []  # Looks empty but conflict will happen

        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [mock_flexible_priority]

        streak_result = MagicMock()
        streak_result.fetchone.return_value = None

        # INSERT returns no row (conflict - row already exists)
        insert_result = MagicMock()
        insert_result.fetchone.return_value = None  # No row = conflict

        mock_session.execute.side_effect = [
            conn_result,
            existing_result,
            priorities_result,
            streak_result,
            insert_result,
            # No avg/update calls because insert "failed" (conflict)
        ]

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
            mock_tz.return_value = "UTC"
            mock_weeks.return_value = [date(2026, 2, 2)]
            mock_events.return_value = (mock_calendar_events, 0)

            result = await ensure_snapshots_up_to_date(
                user_id=user_id,
                session=mock_session,
                http_client=mock_http_client,
            )

        # Week checked but no new row created (conflict)
        assert result["checked"] == 1
        assert result["created"] == 0


class TestPartialFailure:
    """Tests for partial failure handling."""

    @pytest.mark.asyncio
    async def test_one_week_failure_doesnt_block_others(
        self,
        mock_http_client,
        mock_google_connection,
        mock_flexible_priority,
    ):
        """
        Failure on week 2 doesn't block weeks 1 and 3.
        """
        user_id = uuid4()
        mock_session = create_mock_session()

        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = mock_google_connection

        existing_result = MagicMock()
        existing_result.fetchall.return_value = []

        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [mock_flexible_priority]

        streak_result = MagicMock()
        streak_result.fetchone.return_value = None

        insert_result = MagicMock()
        insert_result.fetchone.return_value = (uuid4(),)

        avg_result = MagicMock()
        avg_result.scalar.return_value = Decimal("3.0")

        update_result = MagicMock()

        events = [
            {
                "id": "event1",
                "summary": "P1 - Work",
                "start": {"dateTime": "2026-02-10T09:00:00Z"},
                "end": {"dateTime": "2026-02-10T12:00:00Z"},
                "status": "confirmed",
            }
        ]

        mock_session.execute.side_effect = [
            conn_result,
            existing_result,
            priorities_result,
            streak_result, insert_result, avg_result, update_result,  # Week 1 succeeds
            # Week 2 will fail via list_events
            streak_result, insert_result, avg_result, update_result,  # Week 3 succeeds
        ]

        call_count = [0]

        async def mock_list_events(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise Exception("Google API error for week 2")
            return (events, 0)

        with patch(
            "backend.apps.priority_guardian.services.snapshot_service.ensure_valid_access_token"
        ) as mock_token, patch(
            "backend.apps.priority_guardian.services.snapshot_service.get_user_timezone"
        ) as mock_tz, patch(
            "backend.apps.priority_guardian.services.snapshot_service._compute_target_weeks"
        ) as mock_weeks, patch(
            "backend.apps.priority_guardian.services.snapshot_service.list_events",
            side_effect=mock_list_events,
        ):
            mock_token.return_value = {"access_token": "test_token"}
            mock_tz.return_value = "UTC"
            mock_weeks.return_value = [
                date(2026, 1, 19),
                date(2026, 1, 26),
                date(2026, 2, 2),
            ]

            result = await ensure_snapshots_up_to_date(
                user_id=user_id,
                session=mock_session,
                http_client=mock_http_client,
            )

        # 2 weeks created (1 and 3), 1 error (week 2)
        assert result["created"] == 2
        assert result["errors"] == 1


class TestNoActivePriorities:
    """Tests when user has no active priorities."""

    @pytest.mark.asyncio
    async def test_no_priorities_returns_zero_created(
        self,
        mock_http_client,
        mock_google_connection,
    ):
        """
        User with Google connection but no active priorities creates no snapshots.
        """
        user_id = uuid4()
        mock_session = create_mock_session()

        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = mock_google_connection

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

        assert result["checked"] == 1
        assert result["created"] == 0
        assert result["errors"] == 0


class TestNoGoogleConnection:
    """Tests when user has no Google connection."""

    @pytest.mark.asyncio
    async def test_no_connection_returns_zeros(
        self,
        mock_http_client,
    ):
        """
        User without Google connection returns zeros immediately.
        """
        user_id = uuid4()
        mock_session = create_mock_session()

        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = None

        mock_session.execute.side_effect = [conn_result]

        result = await ensure_snapshots_up_to_date(
            user_id=user_id,
            session=mock_session,
            http_client=mock_http_client,
        )

        assert result == {"checked": 0, "created": 0, "errors": 0}
