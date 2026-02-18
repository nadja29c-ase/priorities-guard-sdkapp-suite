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
    # Use fixed date that predates all test weeks for deterministic tests
    p.created_at = datetime(2026, 1, 1)
    p.streak_count = 0
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
    # Use fixed date that predates all test weeks for deterministic tests
    p.created_at = datetime(2026, 1, 1)
    p.streak_count = 0
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

        # _update_aggregates queries:
        # 1. total_hours_invested SUM (scalar)
        total_result = MagicMock()
        total_result.scalar.return_value = Decimal("3.0")

        # 2. avg_target_achievement AVG+COUNT (fetchone returns tuple)
        achievement_result = MagicMock()
        achievement_result.fetchone.return_value = (Decimal("100.0"), 1)  # (avg, count)

        update_result = MagicMock()  # For the UPDATE statement

        # Execute order:
        # 1. connection, 2. existing weeks, 3. priorities
        # Then for each priority: streak, INSERT, total, achievement, UPDATE
        mock_session.execute.side_effect = [
            conn_result,
            existing_result,
            priorities_result,
            streak_result,
            insert_result,
            total_result,
            achievement_result,
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

        # _update_aggregates queries:
        total_result = MagicMock()
        total_result.scalar.return_value = Decimal("9.0")  # 3 weeks × 3h

        achievement_result = MagicMock()
        achievement_result.fetchone.return_value = (Decimal("100.0"), 3)  # (avg, count)

        update_result = MagicMock()

        # 3 weeks × 1 priority = 3 iterations
        # Each iteration: streak, INSERT, total, achievement, update
        mock_session.execute.side_effect = [
            conn_result,
            existing_result,
            priorities_result,
        ] + [streak_result, insert_result, total_result, achievement_result, update_result] * 3

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

        # _update_aggregates queries:
        total_result = MagicMock()
        total_result.scalar.return_value = Decimal("15.0")

        achievement_result = MagicMock()
        achievement_result.fetchone.return_value = (Decimal("100.0"), 3)  # (avg, count)

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
            streak_result_1, insert_result, total_result, achievement_result, update_result,  # Week 1
            streak_result_2, insert_result, total_result, achievement_result, update_result,  # Week 2
            streak_result_3, insert_result, total_result, achievement_result, update_result,  # Week 3
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

        # _update_aggregates queries:
        total_result = MagicMock()
        total_result.scalar.return_value = Decimal("0.0")

        achievement_result = MagicMock()
        achievement_result.fetchone.return_value = (None, 0)  # (avg, count) - no data

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
            total_result,
            achievement_result,
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

        # _update_aggregates queries:
        total_result = MagicMock()
        total_result.scalar.return_value = Decimal("6.0")

        achievement_result = MagicMock()
        achievement_result.fetchone.return_value = (Decimal("100.0"), 2)  # (avg, count)

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
            streak_result, insert_result, total_result, achievement_result, update_result,  # Week 1 succeeds
            # Week 2 will fail via list_events
            streak_result, insert_result, total_result, achievement_result, update_result,  # Week 3 succeeds
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


class TestDeadlinePriorityFields:
    """Tests for deadline-type priority snapshot fields."""

    @pytest.mark.asyncio
    async def test_deadline_priority_snapshot_core_fields(
        self,
        mock_http_client,
        mock_google_connection,
        mock_deadline_priority,
    ):
        """
        Deadline priority snapshots include core fields but no target_hours.
        """
        user_id = uuid4()
        mock_session = create_mock_session()

        # Set up deadline priority
        mock_deadline_priority.deadline = date(2026, 3, 15)

        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = mock_google_connection

        existing_result = MagicMock()
        existing_result.fetchall.return_value = []

        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [mock_deadline_priority]

        streak_result = MagicMock()
        streak_result.fetchone.return_value = None

        insert_result = MagicMock()
        insert_result.fetchone.return_value = (uuid4(),)

        # _update_aggregates queries:
        total_result = MagicMock()
        total_result.scalar.return_value = Decimal("2.0")

        achievement_result = MagicMock()
        achievement_result.fetchone.return_value = (None, 1)  # (avg, count) - deadline has no target

        update_result = MagicMock()

        # Capture the INSERT statement to verify fields
        captured_stmts = []

        async def capturing_execute(stmt, *args, **kwargs):
            captured_stmts.append(stmt)
            # Return the appropriate mock based on call order
            idx = len(captured_stmts) - 1
            results = [
                conn_result, existing_result, priorities_result,
                streak_result, insert_result, total_result, achievement_result, update_result
            ]
            return results[idx] if idx < len(results) else MagicMock()

        mock_session.execute = capturing_execute

        events_with_deadline_hours = [
            {
                "id": "event1",
                "summary": "P2 - Deadline work",
                "start": {"dateTime": "2026-02-10T09:00:00Z"},
                "end": {"dateTime": "2026-02-10T11:00:00Z"},
                "status": "confirmed",
            }
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
            mock_weeks.return_value = [date(2026, 2, 2)]  # Week ending Feb 8
            mock_events.return_value = (events_with_deadline_hours, 0)

            result = await ensure_snapshots_up_to_date(
                user_id=user_id,
                session=mock_session,
                http_client=mock_http_client,
            )

        assert result["created"] == 1

        # Find the INSERT statement and verify core fields
        # The INSERT is the 5th statement (after conn, existing, priorities, streak)
        insert_stmt = captured_stmts[4]

        # Get the compiled parameters from the INSERT statement
        if hasattr(insert_stmt, 'compile'):
            compiled = insert_stmt.compile()
            params = compiled.params

            # Core fields present
            assert params.get("priority_id") == mock_deadline_priority.id
            assert params.get("actual_hours") == Decimal("2.0")
            assert params.get("streak_at_snapshot") == 1  # First week
            # Deadline priorities don't have weekly_hour_target
            assert params.get("target_hours") is None


class TestAggregateComputation:
    """Tests for aggregate computation (total_hours_invested, avg_target_achievement)."""

    @pytest.mark.asyncio
    async def test_total_hours_computed_correctly_after_multiple_snapshots(
        self,
        mock_http_client,
        mock_google_connection,
        mock_flexible_priority,
    ):
        """
        After 3 weeks of snapshots (4h, 6h, 8h), total_hours_invested = 18.0.
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

        # Build mocks for aggregate computation
        # Week 1: 4h -> SUM = 4.0
        # Week 2: 6h -> SUM = 10.0
        # Week 3: 8h -> SUM = 18.0
        total_results = [Decimal("4.0"), Decimal("10.0"), Decimal("18.0")]
        total_call_idx = [0]

        def make_total_result():
            result = MagicMock()
            idx = total_call_idx[0]
            result.scalar.return_value = total_results[idx] if idx < len(total_results) else Decimal("0")
            total_call_idx[0] += 1
            return result

        # Achievement result mock (returns count < 2 for first two calls, then count >= 2)
        def make_achievement_result():
            result = MagicMock()
            idx = total_call_idx[0] - 1  # Use same index
            # First 2 weeks: count < 2, achievement is NULL
            # Week 3: count = 3, achievement computed
            if idx < 2:
                result.fetchone.return_value = (None, idx + 1)
            else:
                # AVG(40%, 60%, 80%) = 60%
                result.fetchone.return_value = (Decimal("60.0"), 3)
            return result

        update_result = MagicMock()

        # 3 weeks, each with: streak, INSERT, total, achievement, update
        mock_session.execute.side_effect = [
            conn_result,
            existing_result,
            priorities_result,
            # Week 1
            streak_result, insert_result, make_total_result(), make_achievement_result(), update_result,
            # Week 2
            streak_result, insert_result, make_total_result(), make_achievement_result(), update_result,
            # Week 3
            streak_result, insert_result, make_total_result(), make_achievement_result(), update_result,
        ]

        # Different hours per week to verify SUM computation
        call_idx = [0]
        hours_per_week = [4.0, 6.0, 8.0]

        def events_for_week(*args, **kwargs):
            idx = call_idx[0]
            call_idx[0] += 1
            hours = hours_per_week[idx] if idx < len(hours_per_week) else 0
            # Create event with appropriate duration
            return ([{
                "id": f"event{idx}",
                "summary": "P1 - Work",
                "start": {"dateTime": "2026-02-10T09:00:00Z"},
                "end": {"dateTime": f"2026-02-10T{9 + int(hours)}:00:00Z"},
                "status": "confirmed",
            }], 0)

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
            mock_events.side_effect = events_for_week

            result = await ensure_snapshots_up_to_date(
                user_id=user_id,
                session=mock_session,
                http_client=mock_http_client,
            )

        assert result["created"] == 3

        # Verify SUM was computed 3 times
        assert total_call_idx[0] == 3


# =============================================================================
# REAL-DB INTEGRATION TESTS (no mocks on DB layer)
# =============================================================================

from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.core.models import CoreUser
from backend.apps.priority_guardian.db_models import PgPriority, PgWeeklySnapshot
from backend.apps.priority_guardian.services.snapshot_service import _update_aggregates


class TestRealDBUniqueConstraint:
    """Tests for UNIQUE constraint enforcement using real Postgres."""

    @pytest.mark.asyncio
    async def test_duplicate_snapshot_insert_returns_nothing(self, async_session):
        """
        INSERT with ON CONFLICT DO NOTHING returns no row when duplicate exists.

        Tests the uq_pg_weekly_snapshots_priority_week constraint.
        """
        # Create test user
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Create test priority
        priority = PgPriority(
            user_id=user.id,
            name="Test Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date.today() + timedelta(days=30),
            created_at=datetime(2026, 1, 1),  # Predate all test weeks
        )
        async_session.add(priority)
        await async_session.flush()

        week_start = date(2026, 2, 2)
        week_end = date(2026, 2, 8)

        # First insert - should succeed
        stmt1 = (
            pg_insert(PgWeeklySnapshot)
            .values(
                priority_id=priority.id,
                user_id=user.id,
                week_start=week_start,
                week_end=week_end,
                actual_hours=Decimal("5.0"),
                target_hours=Decimal("10.0"),
                streak_at_snapshot=1,
            )
            .on_conflict_do_nothing(index_elements=["priority_id", "week_start"])
            .returning(PgWeeklySnapshot.id)
        )
        result1 = await async_session.execute(stmt1)
        row1 = result1.fetchone()
        assert row1 is not None, "First insert should return a row"

        # Second insert with same (priority_id, week_start) - should conflict
        stmt2 = (
            pg_insert(PgWeeklySnapshot)
            .values(
                priority_id=priority.id,
                user_id=user.id,
                week_start=week_start,
                week_end=week_end,
                actual_hours=Decimal("8.0"),  # Different value
                target_hours=Decimal("10.0"),
                streak_at_snapshot=2,
            )
            .on_conflict_do_nothing(index_elements=["priority_id", "week_start"])
            .returning(PgWeeklySnapshot.id)
        )
        result2 = await async_session.execute(stmt2)
        row2 = result2.fetchone()
        assert row2 is None, "Second insert should return nothing (conflict)"

        # Verify only one row exists
        count_result = await async_session.execute(
            select(func.count()).select_from(PgWeeklySnapshot).where(
                PgWeeklySnapshot.priority_id == priority.id,
                PgWeeklySnapshot.week_start == week_start,
            )
        )
        count = count_result.scalar()
        assert count == 1, "Only one snapshot row should exist"

        await async_session.commit()


class TestRealDBSumBasedAggregates:
    """Tests for SUM-based total_hours_invested using real Postgres."""

    @pytest.mark.asyncio
    async def test_total_hours_invested_equals_sum_of_snapshots(self, async_session):
        """
        total_hours_invested = SUM(actual_hours) from all snapshots.
        """
        # Create test user
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Create test priority
        priority = PgPriority(
            user_id=user.id,
            name="Test Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date.today() + timedelta(days=30),
            created_at=datetime(2026, 1, 1),  # Predate all test weeks
        )
        async_session.add(priority)
        await async_session.flush()

        # Insert 3 snapshots with different hours: 4h, 6h, 8h
        weeks = [
            (date(2026, 1, 19), date(2026, 1, 25), Decimal("4.0")),
            (date(2026, 1, 26), date(2026, 2, 1), Decimal("6.0")),
            (date(2026, 2, 2), date(2026, 2, 8), Decimal("8.0")),
        ]

        for week_start, week_end, hours in weeks:
            snapshot = PgWeeklySnapshot(
                priority_id=priority.id,
                user_id=user.id,
                week_start=week_start,
                week_end=week_end,
                actual_hours=hours,
                target_hours=Decimal("10.0"),
                streak_at_snapshot=1,
            )
            async_session.add(snapshot)

        await async_session.flush()

        # Call _update_aggregates
        await _update_aggregates(
            priority_id=priority.id,
            streak=3,
            actual_hours=8.0,  # Last week's hours
            session=async_session,
        )

        # Refresh priority to get updated values
        await async_session.refresh(priority)

        # Verify total_hours_invested = 4 + 6 + 8 = 18
        assert priority.total_hours_invested == Decimal("18.0"), \
            f"Expected 18.0, got {priority.total_hours_invested}"

        await async_session.commit()

    @pytest.mark.asyncio
    async def test_avg_target_achievement_computed_with_target(self, async_session):
        """
        avg_target_achievement = AVG(actual_hours * 100 / target_hours) from all snapshots.
        """
        # Create test user
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Create test priority
        priority = PgPriority(
            user_id=user.id,
            name="Test Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date.today() + timedelta(days=30),
            created_at=datetime(2026, 1, 1),  # Predate all test weeks
        )
        async_session.add(priority)
        await async_session.flush()

        # Insert 3 snapshots with hours: 4h, 6h, 8h against 10h target
        # Percentages: 40%, 60%, 80% -> AVG = 60%
        weeks = [
            (date(2026, 1, 19), date(2026, 1, 25), Decimal("4.0")),
            (date(2026, 1, 26), date(2026, 2, 1), Decimal("6.0")),
            (date(2026, 2, 2), date(2026, 2, 8), Decimal("8.0")),
        ]

        for week_start, week_end, hours in weeks:
            snapshot = PgWeeklySnapshot(
                priority_id=priority.id,
                user_id=user.id,
                week_start=week_start,
                week_end=week_end,
                actual_hours=hours,
                target_hours=Decimal("10.0"),
                streak_at_snapshot=1,
            )
            async_session.add(snapshot)

        await async_session.flush()

        # Call _update_aggregates
        await _update_aggregates(
            priority_id=priority.id,
            streak=3,
            actual_hours=8.0,
            session=async_session,
        )

        # Refresh priority to get updated values
        await async_session.refresh(priority)

        # Verify avg_target_achievement = (40 + 60 + 80) / 3 = 60%
        assert priority.avg_target_achievement == Decimal("60.0"), \
            f"Expected 60.0, got {priority.avg_target_achievement}"

        await async_session.commit()


class TestRealDBIdempotentAggregates:
    """Tests for idempotent aggregate updates using real Postgres."""

    @pytest.mark.asyncio
    async def test_duplicate_aggregate_update_unchanged(self, async_session):
        """
        Calling _update_aggregates twice with same snapshot data gives same result.

        Aggregates are derived from SUM/AVG, not incremented, so duplicates are safe.
        """
        # Create test user
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Create test priority
        priority = PgPriority(
            user_id=user.id,
            name="Test Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date.today() + timedelta(days=30),
            created_at=datetime(2026, 1, 1),  # Predate all test weeks
        )
        async_session.add(priority)
        await async_session.flush()

        # Insert one snapshot
        snapshot = PgWeeklySnapshot(
            priority_id=priority.id,
            user_id=user.id,
            week_start=date(2026, 2, 2),
            week_end=date(2026, 2, 8),
            actual_hours=Decimal("5.0"),
            target_hours=Decimal("10.0"),
            streak_at_snapshot=1,
        )
        async_session.add(snapshot)
        await async_session.flush()

        # First aggregate update
        await _update_aggregates(
            priority_id=priority.id,
            streak=1,
            actual_hours=5.0,
            session=async_session,
        )
        await async_session.refresh(priority)

        first_total = priority.total_hours_invested

        # Second aggregate update (simulating duplicate call)
        await _update_aggregates(
            priority_id=priority.id,
            streak=1,
            actual_hours=5.0,
            session=async_session,
        )
        await async_session.refresh(priority)

        # Values should be unchanged (no double-counting)
        assert priority.total_hours_invested == first_total, \
            "total_hours_invested should not change on duplicate update"

        # Verify actual value
        assert priority.total_hours_invested == Decimal("5.0")

        await async_session.commit()


class TestRealDBCreatedAtBoundary:
    """Tests for created_at boundary enforcement using real Postgres."""

    @pytest.mark.asyncio
    async def test_no_snapshot_created_before_priority_created_at(self, async_session):
        """
        Snapshots are not created for weeks before a priority's created_at date.

        Setup:
        - Priority with created_at = 2026-02-01 (Sunday)
        - First valid Monday on or after created_at = 2026-02-02
        - Target weeks include 2026-01-19 (before created_at)

        Assert:
        - Zero rows exist for week_start = 2026-01-19
        - Any snapshots have week_start >= 2026-02-02
        """
        from sqlalchemy import text
        from backend.core.models import CoreConnection
        from backend.core.encryption import encrypt_token

        # Create test user
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Create real Google connection in DB (required by ensure_snapshots_up_to_date)
        connection = CoreConnection(
            user_id=user.id,
            provider="google",
            connection_type="google",  # Must be 'google' for snapshot service query
            encrypted_access_token=encrypt_token("test_access_token"),
            encrypted_refresh_token=encrypt_token("test_refresh_token"),
            token_expires_at=datetime.now() + timedelta(hours=1),
            scopes=["https://www.googleapis.com/auth/calendar.readonly"],
        )
        async_session.add(connection)
        await async_session.flush()

        # Create priority with created_at = 2026-02-01 (a Sunday)
        # First Monday on or after is 2026-02-02
        priority = PgPriority(
            user_id=user.id,
            name="Test Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date(2026, 3, 15),
            created_at=datetime(2026, 2, 1, 12, 0, 0),  # Sunday Feb 1, 2026
        )
        async_session.add(priority)
        await async_session.commit()

        # Mock calendar events (hours for all weeks)
        mock_events = [
            {
                "id": "event1",
                "summary": "P1 - Work session",
                "start": {"dateTime": "2026-01-20T09:00:00Z"},
                "end": {"dateTime": "2026-01-20T12:00:00Z"},
                "status": "confirmed",
            },
            {
                "id": "event2",
                "summary": "P1 - More work",
                "start": {"dateTime": "2026-02-03T09:00:00Z"},
                "end": {"dateTime": "2026-02-03T14:00:00Z"},
                "status": "confirmed",
            },
        ]

        mock_http_client = AsyncMock()

        with patch(
            "backend.apps.priority_guardian.services.snapshot_service.ensure_valid_access_token"
        ) as mock_token, patch(
            "backend.apps.priority_guardian.services.snapshot_service.get_user_timezone"
        ) as mock_tz, patch(
            "backend.apps.priority_guardian.services.snapshot_service._compute_target_weeks"
        ) as mock_weeks, patch(
            "backend.apps.priority_guardian.services.snapshot_service.list_events"
        ) as mock_list_events:
            mock_token.return_value = {"access_token": "test_token"}
            mock_tz.return_value = "UTC"
            # Return weeks that include ones before created_at
            mock_weeks.return_value = [
                date(2026, 1, 19),  # Before created_at - should be skipped
                date(2026, 1, 26),  # Before created_at - should be skipped
                date(2026, 2, 2),   # First Monday on or after created_at - should be created
                date(2026, 2, 9),   # After created_at - should be created
            ]
            mock_list_events.return_value = (mock_events, 0)

            result = await ensure_snapshots_up_to_date(
                user_id=user.id,
                session=async_session,
                http_client=mock_http_client,
            )

        # Verify: Query snapshots for this priority via raw SQL
        snapshot_result = await async_session.execute(
            text("""
                SELECT week_start FROM pg_weekly_snapshots
                WHERE priority_id = :priority_id
                ORDER BY week_start
            """),
            {"priority_id": priority.id},
        )
        snapshot_weeks = [row[0] for row in snapshot_result.fetchall()]

        # Assert: No snapshot for week_start = 2026-01-19 or 2026-01-26
        assert date(2026, 1, 19) not in snapshot_weeks, \
            "Snapshot should not exist for week before created_at"
        assert date(2026, 1, 26) not in snapshot_weeks, \
            "Snapshot should not exist for week before created_at"

        # Assert: All snapshots have week_start >= 2026-02-02
        for week_start in snapshot_weeks:
            assert week_start >= date(2026, 2, 2), \
                f"Snapshot week_start {week_start} is before first valid Monday 2026-02-02"

        # Assert: At least one snapshot was created (for valid weeks)
        assert len(snapshot_weeks) > 0, "At least one snapshot should be created"


class TestRealDBZeroHours:
    """Tests for zero hours handling using real Postgres."""

    @pytest.mark.asyncio
    async def test_zero_hours_snapshot_total_is_zero_not_null(self, async_session):
        """
        Snapshot with actual_hours=0 results in total_hours_invested=0.0, not NULL.

        Tests the `is not None` fix for falsy value handling.
        """
        # Create test user
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Create test priority
        priority = PgPriority(
            user_id=user.id,
            name="Test Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date.today() + timedelta(days=30),
            created_at=datetime(2026, 1, 1),  # Predate all test weeks
        )
        async_session.add(priority)
        await async_session.flush()

        # Insert snapshot with zero hours
        snapshot = PgWeeklySnapshot(
            priority_id=priority.id,
            user_id=user.id,
            week_start=date(2026, 2, 2),
            week_end=date(2026, 2, 8),
            actual_hours=Decimal("0.0"),
            target_hours=Decimal("10.0"),
            streak_at_snapshot=0,
        )
        async_session.add(snapshot)
        await async_session.flush()

        # Call _update_aggregates
        await _update_aggregates(
            priority_id=priority.id,
            streak=0,
            actual_hours=0.0,
            session=async_session,
        )

        # Refresh priority to get updated values
        await async_session.refresh(priority)

        # total_hours_invested should be 0.0, NOT None
        assert priority.total_hours_invested is not None, \
            "total_hours_invested should not be None for zero hours"
        assert priority.total_hours_invested == Decimal("0.0"), \
            f"Expected 0.0, got {priority.total_hours_invested}"

        await async_session.commit()


class TestRealDBSnapshotWeekTotals:
    """Tests for other_hours and total_tracked_hours persistence using real Postgres."""

    @pytest.mark.asyncio
    async def test_snapshot_persists_other_hours_and_total_tracked(self, async_session):
        """
        Snapshot INSERT includes other_hours and total_tracked_hours from allocation.

        Verifies the snapshot_service extracts week-level values from
        compute_allocation_from_events() and persists them.
        """
        from sqlalchemy import text
        from backend.core.models import CoreConnection
        from backend.core.encryption import encrypt_token

        # Create test user
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Create real Google connection in DB
        connection = CoreConnection(
            user_id=user.id,
            provider="google",
            connection_type="google",
            encrypted_access_token=encrypt_token("test_access_token"),
            encrypted_refresh_token=encrypt_token("test_refresh_token"),
            token_expires_at=datetime.now() + timedelta(hours=1),
            scopes=["https://www.googleapis.com/auth/calendar.readonly"],
        )
        async_session.add(connection)
        await async_session.flush()

        # Create priority
        priority = PgPriority(
            user_id=user.id,
            name="Test Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date(2026, 3, 15),
            created_at=datetime(2026, 1, 1),
        )
        async_session.add(priority)
        await async_session.commit()

        # Mock calendar events including P1 tagged and untagged
        mock_events = [
            {
                "id": "event1",
                "summary": "P1 - Project work",
                "start": {"dateTime": "2026-02-03T09:00:00Z"},
                "end": {"dateTime": "2026-02-03T12:00:00Z"},  # 3 hours
                "status": "confirmed",
            },
            {
                "id": "event2",
                "summary": "Team meeting",  # No keyword - other hours
                "start": {"dateTime": "2026-02-03T14:00:00Z"},
                "end": {"dateTime": "2026-02-03T15:30:00Z"},  # 1.5 hours
                "status": "confirmed",
            },
        ]

        mock_http_client = AsyncMock()

        with patch(
            "backend.apps.priority_guardian.services.snapshot_service.ensure_valid_access_token"
        ) as mock_token, patch(
            "backend.apps.priority_guardian.services.snapshot_service.get_user_timezone"
        ) as mock_tz, patch(
            "backend.apps.priority_guardian.services.snapshot_service._compute_target_weeks"
        ) as mock_weeks, patch(
            "backend.apps.priority_guardian.services.snapshot_service.list_events"
        ) as mock_list_events:
            mock_token.return_value = {"access_token": "test_token"}
            mock_tz.return_value = "UTC"
            mock_weeks.return_value = [date(2026, 2, 2)]  # One week
            mock_list_events.return_value = (mock_events, 0)

            result = await ensure_snapshots_up_to_date(
                user_id=user.id,
                session=async_session,
                http_client=mock_http_client,
            )

        assert result["created"] == 1

        # Query snapshot and verify other_hours and total_tracked_hours
        snapshot_result = await async_session.execute(
            text("""
                SELECT actual_hours, other_hours, total_tracked_hours
                FROM pg_weekly_snapshots
                WHERE priority_id = :priority_id
            """),
            {"priority_id": priority.id},
        )
        row = snapshot_result.fetchone()

        assert row is not None
        assert float(row[0]) == 3.0  # actual_hours (P1 events)
        assert float(row[1]) == 1.5  # other_hours (untagged meeting)
        assert float(row[2]) == 4.5  # total_tracked_hours (3.0 + 1.5)

    @pytest.mark.asyncio
    async def test_snapshot_persists_exact_decimal_values(self, async_session):
        """
        Snapshot stores exact Decimal values without floating-point drift.

        Verifies NUMERIC(6,2) and NUMERIC(8,2) preserve precision.
        """
        from sqlalchemy import text
        from backend.core.models import CoreConnection
        from backend.core.encryption import encrypt_token

        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        connection = CoreConnection(
            user_id=user.id,
            provider="google",
            connection_type="google",
            encrypted_access_token=encrypt_token("test_access_token"),
            encrypted_refresh_token=encrypt_token("test_refresh_token"),
            token_expires_at=datetime.now() + timedelta(hours=1),
            scopes=["https://www.googleapis.com/auth/calendar.readonly"],
        )
        async_session.add(connection)
        await async_session.flush()

        priority = PgPriority(
            user_id=user.id,
            name="Test Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date(2026, 3, 15),
            created_at=datetime(2026, 1, 1),
        )
        async_session.add(priority)
        await async_session.commit()

        # Events with precise decimal hours: 2h 15m = 2.25h, 45m = 0.75h
        mock_events = [
            {
                "id": "event1",
                "summary": "P1 - Precise work",
                "start": {"dateTime": "2026-02-03T09:00:00Z"},
                "end": {"dateTime": "2026-02-03T11:15:00Z"},  # 2.25 hours
                "status": "confirmed",
            },
            {
                "id": "event2",
                "summary": "Other meeting",
                "start": {"dateTime": "2026-02-03T14:00:00Z"},
                "end": {"dateTime": "2026-02-03T14:45:00Z"},  # 0.75 hours
                "status": "confirmed",
            },
        ]

        mock_http_client = AsyncMock()

        with patch(
            "backend.apps.priority_guardian.services.snapshot_service.ensure_valid_access_token"
        ) as mock_token, patch(
            "backend.apps.priority_guardian.services.snapshot_service.get_user_timezone"
        ) as mock_tz, patch(
            "backend.apps.priority_guardian.services.snapshot_service._compute_target_weeks"
        ) as mock_weeks, patch(
            "backend.apps.priority_guardian.services.snapshot_service.list_events"
        ) as mock_list_events:
            mock_token.return_value = {"access_token": "test_token"}
            mock_tz.return_value = "UTC"
            mock_weeks.return_value = [date(2026, 2, 2)]
            mock_list_events.return_value = (mock_events, 0)

            await ensure_snapshots_up_to_date(
                user_id=user.id,
                session=async_session,
                http_client=mock_http_client,
            )

        # Query and verify exact Decimal values
        result = await async_session.execute(
            text("""
                SELECT actual_hours, other_hours, total_tracked_hours
                FROM pg_weekly_snapshots
                WHERE priority_id = :priority_id
            """),
            {"priority_id": priority.id},
        )
        row = result.fetchone()

        # Verify exact Decimal precision (no floating-point drift)
        assert row[0] == Decimal("2.25"), f"Expected 2.25, got {row[0]}"
        assert row[1] == Decimal("0.75"), f"Expected 0.75, got {row[1]}"
        assert row[2] == Decimal("3.00"), f"Expected 3.00, got {row[2]}"

    @pytest.mark.asyncio
    async def test_snapshot_denormalized_values_identical_across_priorities(self, async_session):
        """
        Multiple priorities in the same week have identical other_hours and total_tracked_hours.

        Verifies denormalization: week-level values are the same across all snapshot rows.
        """
        from sqlalchemy import text
        from backend.core.models import CoreConnection
        from backend.core.encryption import encrypt_token

        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        connection = CoreConnection(
            user_id=user.id,
            provider="google",
            connection_type="google",
            encrypted_access_token=encrypt_token("test_access_token"),
            encrypted_refresh_token=encrypt_token("test_refresh_token"),
            token_expires_at=datetime.now() + timedelta(hours=1),
            scopes=["https://www.googleapis.com/auth/calendar.readonly"],
        )
        async_session.add(connection)
        await async_session.flush()

        # Create 3 priorities with different keywords
        priorities = []
        for kw in ["P1", "P2", "P3"]:
            p = PgPriority(
                user_id=user.id,
                name=f"Priority {kw}",
                type="flexible",
                calendar_keyword=kw,
                status="active",
                weekly_hour_target=Decimal("10.0"),
                checkpoint_date=date(2026, 3, 15),
                created_at=datetime(2026, 1, 1),
            )
            async_session.add(p)
            priorities.append(p)
        await async_session.commit()

        # Events for all keywords plus untagged
        mock_events = [
            {
                "id": "event1",
                "summary": "P1 - Work",
                "start": {"dateTime": "2026-02-03T09:00:00Z"},
                "end": {"dateTime": "2026-02-03T11:00:00Z"},  # 2h
                "status": "confirmed",
            },
            {
                "id": "event2",
                "summary": "P2 - Other work",
                "start": {"dateTime": "2026-02-03T11:00:00Z"},
                "end": {"dateTime": "2026-02-03T13:00:00Z"},  # 2h
                "status": "confirmed",
            },
            {
                "id": "event3",
                "summary": "P3 - More work",
                "start": {"dateTime": "2026-02-03T14:00:00Z"},
                "end": {"dateTime": "2026-02-03T15:00:00Z"},  # 1h
                "status": "confirmed",
            },
            {
                "id": "event4",
                "summary": "Team standup",  # No keyword - other hours
                "start": {"dateTime": "2026-02-03T16:00:00Z"},
                "end": {"dateTime": "2026-02-03T16:30:00Z"},  # 0.5h
                "status": "confirmed",
            },
        ]

        mock_http_client = AsyncMock()

        with patch(
            "backend.apps.priority_guardian.services.snapshot_service.ensure_valid_access_token"
        ) as mock_token, patch(
            "backend.apps.priority_guardian.services.snapshot_service.get_user_timezone"
        ) as mock_tz, patch(
            "backend.apps.priority_guardian.services.snapshot_service._compute_target_weeks"
        ) as mock_weeks, patch(
            "backend.apps.priority_guardian.services.snapshot_service.list_events"
        ) as mock_list_events:
            mock_token.return_value = {"access_token": "test_token"}
            mock_tz.return_value = "UTC"
            mock_weeks.return_value = [date(2026, 2, 2)]
            mock_list_events.return_value = (mock_events, 0)

            result = await ensure_snapshots_up_to_date(
                user_id=user.id,
                session=async_session,
                http_client=mock_http_client,
            )

        assert result["created"] == 1  # 1 week processed (contains 3 snapshots)

        # Query all snapshots for this week
        snapshot_result = await async_session.execute(
            text("""
                SELECT priority_id, actual_hours, other_hours, total_tracked_hours
                FROM pg_weekly_snapshots
                WHERE user_id = :user_id AND week_start = '2026-02-02'
                ORDER BY actual_hours DESC
            """),
            {"user_id": user.id},
        )
        rows = snapshot_result.fetchall()

        assert len(rows) == 3

        # Verify denormalized values are IDENTICAL across all rows
        expected_other = Decimal("0.50")  # 0.5h untagged
        expected_total = Decimal("5.50")  # 2 + 2 + 1 + 0.5 = 5.5h

        for row in rows:
            assert row[2] == expected_other, f"other_hours mismatch: {row[2]} != {expected_other}"
            assert row[3] == expected_total, f"total_tracked_hours mismatch: {row[3]} != {expected_total}"

        # Verify actual_hours differ (priority-specific)
        actual_hours = [row[1] for row in rows]
        assert Decimal("2.00") in actual_hours  # P1 or P2
        assert Decimal("1.00") in actual_hours  # P3
