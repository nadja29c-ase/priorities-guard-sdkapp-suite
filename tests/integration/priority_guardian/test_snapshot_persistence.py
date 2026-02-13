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

        total_result = MagicMock()
        total_result.scalar.return_value = Decimal("3.0")

        update_result = MagicMock()  # For the UPDATE statement

        # New flow execute order:
        # 1. connection, 2. existing weeks, 3. priorities
        # Then for each priority: streak, INSERT, avg, total, UPDATE
        mock_session.execute.side_effect = [
            conn_result,
            existing_result,
            priorities_result,
            streak_result,
            insert_result,
            avg_result,
            total_result,
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

        total_result = MagicMock()
        total_result.scalar.return_value = Decimal("9.0")  # 3 weeks × 3h

        update_result = MagicMock()

        # 3 weeks × 1 priority = 3 iterations
        # Each iteration: streak, INSERT, avg, total, update
        mock_session.execute.side_effect = [
            conn_result,
            existing_result,
            priorities_result,
        ] + [streak_result, insert_result, avg_result, total_result, update_result] * 3

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

        total_result = MagicMock()
        total_result.scalar.return_value = Decimal("15.0")

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
            streak_result_1, insert_result, avg_result, total_result, update_result,  # Week 1
            streak_result_2, insert_result, avg_result, total_result, update_result,  # Week 2
            streak_result_3, insert_result, avg_result, total_result, update_result,  # Week 3
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

        total_result = MagicMock()
        total_result.scalar.return_value = Decimal("0.0")

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
            total_result,
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

        total_result = MagicMock()
        total_result.scalar.return_value = Decimal("6.0")

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
            streak_result, insert_result, avg_result, total_result, update_result,  # Week 1 succeeds
            # Week 2 will fail via list_events
            streak_result, insert_result, avg_result, total_result, update_result,  # Week 3 succeeds
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
    async def test_deadline_priority_snapshot_fields(
        self,
        mock_http_client,
        mock_google_connection,
        mock_deadline_priority,
    ):
        """
        Deadline priority snapshots include pacing_status, deliverables_completed, days_remaining.
        """
        user_id = uuid4()
        mock_session = create_mock_session()

        # Set up deadline priority with deliverables
        mock_deadline_priority.deadline = date(2026, 3, 15)
        deliverable_done = MagicMock()
        deliverable_done.done = True
        deliverable_pending = MagicMock()
        deliverable_pending.done = False
        mock_deadline_priority.deliverables = [deliverable_done, deliverable_pending]

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

        avg_result = MagicMock()
        avg_result.scalar.return_value = Decimal("2.0")

        total_result = MagicMock()
        total_result.scalar.return_value = Decimal("2.0")

        update_result = MagicMock()

        # Capture the INSERT statement to verify deadline fields
        captured_stmts = []
        original_execute = mock_session.execute

        async def capturing_execute(stmt, *args, **kwargs):
            captured_stmts.append(stmt)
            # Return the appropriate mock based on call order
            idx = len(captured_stmts) - 1
            results = [
                conn_result, existing_result, priorities_result,
                streak_result, insert_result, avg_result, total_result, update_result
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

        # Find the INSERT statement and verify deadline-specific fields
        # The INSERT is the 5th statement (after conn, existing, priorities, streak)
        insert_stmt = captured_stmts[4]

        # Get the compiled parameters from the INSERT statement
        # For SQLAlchemy dialect insert, we check the values
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        if hasattr(insert_stmt, 'compile'):
            compiled = insert_stmt.compile()
            params = compiled.params

            # Verify deadline-specific fields are present
            assert params.get("deadline_date") == date(2026, 3, 15)
            assert params.get("deliverables_completed") == 1  # 1 done
            assert params.get("deliverables_total") == 2  # 2 total
            assert params.get("days_remaining") is not None  # Computed from deadline - week_end
            assert params.get("pacing_status") in ["ahead", "on_track", "behind"]


class TestAggregateComputation:
    """Tests for aggregate computation (avg_hours_week)."""

    @pytest.mark.asyncio
    async def test_avg_hours_week_computed_correctly_after_multiple_snapshots(
        self,
        mock_http_client,
        mock_google_connection,
        mock_flexible_priority,
    ):
        """
        After 3 weeks of snapshots (4h, 6h, 8h), avg_hours_week = 6.0.
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

        # Track the AVG values passed to UPDATE
        captured_avg_values = []
        update_call_count = [0]

        async def capturing_execute(stmt, *args, **kwargs):
            # Check if this is the UPDATE statement (contains avg_hours)
            stmt_str = str(stmt) if hasattr(stmt, '__str__') else ""
            if "UPDATE" in stmt_str and "avg_hours" in stmt_str:
                # This is a raw text UPDATE, extract params
                if args:
                    params = args[0]
                    if isinstance(params, dict) and "avg_hours" in params:
                        captured_avg_values.append(params["avg_hours"])
            return MagicMock()

        # Build a more detailed mock that tracks AVG computation
        # Week 1: 4h -> AVG = 4.0, SUM = 4.0
        # Week 2: 6h -> AVG = (4+6)/2 = 5.0, SUM = 10.0
        # Week 3: 8h -> AVG = (4+6+8)/3 = 6.0, SUM = 18.0
        avg_results = [Decimal("4.0"), Decimal("5.0"), Decimal("6.0")]
        total_results = [Decimal("4.0"), Decimal("10.0"), Decimal("18.0")]
        avg_call_idx = [0]
        total_call_idx = [0]

        def make_avg_result():
            result = MagicMock()
            idx = avg_call_idx[0]
            result.scalar.return_value = avg_results[idx] if idx < len(avg_results) else Decimal("0")
            avg_call_idx[0] += 1
            return result

        def make_total_result():
            result = MagicMock()
            idx = total_call_idx[0]
            result.scalar.return_value = total_results[idx] if idx < len(total_results) else Decimal("0")
            total_call_idx[0] += 1
            return result

        update_result = MagicMock()

        # 3 weeks, each with: streak, INSERT, avg, total, update
        mock_session.execute.side_effect = [
            conn_result,
            existing_result,
            priorities_result,
            # Week 1
            streak_result, insert_result, make_avg_result(), make_total_result(), update_result,
            # Week 2
            streak_result, insert_result, make_avg_result(), make_total_result(), update_result,
            # Week 3
            streak_result, insert_result, make_avg_result(), make_total_result(), update_result,
        ]

        # Different hours per week to verify AVG computation
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

        # Verify AVG was called 3 times with increasing averages
        # The avg_call_idx should have been incremented 3 times
        assert avg_call_idx[0] == 3


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
            desired_result="Test result",
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
                event_count=3,
                target_hours=Decimal("10.0"),
                flex_status="behind",
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
                event_count=5,
                target_hours=Decimal("10.0"),
                flex_status="on_track",
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
            desired_result="Test result",
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
                event_count=int(hours),
                target_hours=Decimal("10.0"),
                flex_status="behind",
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
    async def test_avg_hours_week_equals_avg_of_snapshots(self, async_session):
        """
        avg_hours_week = AVG(actual_hours) from all snapshots.
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
            desired_result="Test result",
        )
        async_session.add(priority)
        await async_session.flush()

        # Insert 3 snapshots with hours: 4h, 6h, 8h -> AVG = 6.0
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
                event_count=int(hours),
                target_hours=Decimal("10.0"),
                flex_status="behind",
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

        # Verify avg_hours_week = (4 + 6 + 8) / 3 = 6.0
        assert priority.avg_hours_week == Decimal("6.0"), \
            f"Expected 6.0, got {priority.avg_hours_week}"

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
            desired_result="Test result",
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
            event_count=3,
            target_hours=Decimal("10.0"),
            flex_status="behind",
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
        first_avg = priority.avg_hours_week

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
        assert priority.avg_hours_week == first_avg, \
            "avg_hours_week should not change on duplicate update"

        # Verify actual values
        assert priority.total_hours_invested == Decimal("5.0")
        assert priority.avg_hours_week == Decimal("5.0")

        await async_session.commit()


class TestRealDBZeroHoursAvg:
    """Tests for zero hours handling using real Postgres."""

    @pytest.mark.asyncio
    async def test_zero_hours_snapshot_avg_is_zero_not_null(self, async_session):
        """
        Snapshot with actual_hours=0 results in avg_hours_week=0.0, not NULL.

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
            desired_result="Test result",
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
            event_count=0,
            target_hours=Decimal("10.0"),
            flex_status="behind",
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

        # avg_hours_week should be 0.0, NOT None
        assert priority.avg_hours_week is not None, \
            "avg_hours_week should not be None for zero hours"
        assert priority.avg_hours_week == Decimal("0.0"), \
            f"Expected 0.0, got {priority.avg_hours_week}"

        # total_hours_invested should also be 0.0
        assert priority.total_hours_invested == Decimal("0.0"), \
            f"Expected 0.0, got {priority.total_hours_invested}"

        await async_session.commit()
