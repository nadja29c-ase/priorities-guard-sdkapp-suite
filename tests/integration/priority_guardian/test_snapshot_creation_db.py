"""
Real-DB integration tests for snapshot creation service (Increment 24).

Tests verify actual PostgreSQL behavior:
- INSERT ON CONFLICT DO NOTHING (idempotency)
- Streak computation via subquery
- Aggregate UPDATE statements (streak_count, total_hours_invested, avg_target_achievement)
- priority_eligible_for_week filtering

All tests use real test PostgreSQL - Google Calendar API is mocked.
"""

import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.priority_guardian.db_models import PgPriority, PgWeeklySnapshot
from backend.apps.priority_guardian.services.snapshot_service import (
    _create_snapshots_for_week,
    ensure_snapshots_up_to_date,
)
from backend.core.models import CoreUser, CoreConnection


class TestSnapshotCreationDB:
    """
    Real-DB integration tests for snapshot creation.

    Tests _create_snapshots_for_week directly for Tests 1-9 (core DB write logic).
    Tests ensure_snapshots_up_to_date for Test 10 (multi-week backfill orchestration).
    """

    @pytest.mark.asyncio
    async def test_basic_snapshot_creation_single_priority(
        self, async_session: AsyncSession
    ):
        """Test 1: Basic snapshot creation — single priority, single week."""
        # Create user
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Create flexible priority (created well before test week)
        priority = PgPriority(
            user_id=user.id,
            name="Test Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date(2026, 3, 15),
            created_at=datetime(2025, 12, 1),  # Well before Jan 5 week
        )
        async_session.add(priority)
        await async_session.commit()

        # Mock calendar events: 5h of P1 work
        mock_events = [
            {
                "id": "event1",
                "summary": "[P1] Project work",
                "start": {"dateTime": "2026-01-06T09:00:00Z"},
                "end": {"dateTime": "2026-01-06T14:00:00Z"},  # 5 hours
            },
        ]

        mock_http_client = AsyncMock()
        log = {"user_id": str(user.id), "correlation_id": "test"}

        with patch(
            "backend.apps.priority_guardian.services.snapshot_service.list_events"
        ) as mock_list_events, patch(
            "backend.apps.priority_guardian.services.snapshot_service.compute_week_boundaries"
        ) as mock_boundaries, patch(
            "backend.apps.priority_guardian.services.snapshot_service.to_rfc3339"
        ) as mock_rfc:
            mock_list_events.return_value = (mock_events, 0)
            mock_boundaries.return_value = (
                datetime(2026, 1, 5, 0, 0),
                datetime(2026, 1, 12, 0, 0),
            )
            mock_rfc.side_effect = lambda dt: dt.isoformat() + "Z"

            result = await _create_snapshots_for_week(
                user_id=user.id,
                week_start=date(2026, 1, 5),
                timezone_str="UTC",
                priorities=[priority],
                access_token="test_token",
                session=async_session,
                http_client=mock_http_client,
                log=log,
            )

        # Verify function returned True (snapshot created)
        assert result is True

        # Query snapshot directly
        snap_result = await async_session.execute(
            text("""
                SELECT priority_id, week_start, actual_hours, target_hours,
                       calendar_keyword_at_snapshot, other_hours, total_tracked_hours,
                       streak_at_snapshot
                FROM pg_weekly_snapshots
                WHERE priority_id = :pid AND week_start = :ws
            """),
            {"pid": priority.id, "ws": date(2026, 1, 5)},
        )
        row = snap_result.fetchone()

        assert row is not None
        assert row[0] == priority.id  # priority_id
        assert row[1] == date(2026, 1, 5)  # week_start
        assert row[2] == Decimal("5.00")  # actual_hours
        assert row[3] == Decimal("10.00")  # target_hours
        assert row[4] == "P1"  # calendar_keyword_at_snapshot
        assert row[5] == Decimal("0.00")  # other_hours
        assert row[6] == Decimal("5.00")  # total_tracked_hours
        assert row[7] == 1  # streak_at_snapshot (first week)

        # Query priority aggregates
        prio_result = await async_session.execute(
            text("SELECT streak_count, total_hours_invested FROM pg_priorities WHERE id = :pid"),
            {"pid": priority.id},
        )
        prio_row = prio_result.fetchone()
        assert prio_row[0] == 1  # streak_count
        assert prio_row[1] == Decimal("5.00")  # total_hours_invested

    @pytest.mark.asyncio
    async def test_streak_continuation_across_two_weeks(
        self, async_session: AsyncSession
    ):
        """Test 2: Streak continuation across two consecutive weeks."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        priority = PgPriority(
            user_id=user.id,
            name="Streak Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date(2026, 3, 15),
            created_at=datetime(2025, 12, 1),
        )
        async_session.add(priority)
        await async_session.commit()

        mock_http_client = AsyncMock()
        log = {"user_id": str(user.id), "correlation_id": "test"}

        # Week 1: Jan 5
        mock_events_w1 = [
            {
                "id": "event1",
                "summary": "[P1] Work",
                "start": {"dateTime": "2026-01-06T09:00:00Z"},
                "end": {"dateTime": "2026-01-06T12:00:00Z"},  # 3 hours
            },
        ]

        with patch(
            "backend.apps.priority_guardian.services.snapshot_service.list_events"
        ) as mock_list_events, patch(
            "backend.apps.priority_guardian.services.snapshot_service.compute_week_boundaries"
        ) as mock_boundaries, patch(
            "backend.apps.priority_guardian.services.snapshot_service.to_rfc3339"
        ) as mock_rfc:
            mock_list_events.return_value = (mock_events_w1, 0)
            mock_boundaries.return_value = (
                datetime(2026, 1, 5, 0, 0),
                datetime(2026, 1, 12, 0, 0),
            )
            mock_rfc.side_effect = lambda dt: dt.isoformat() + "Z"

            await _create_snapshots_for_week(
                user_id=user.id,
                week_start=date(2026, 1, 5),
                timezone_str="UTC",
                priorities=[priority],
                access_token="test_token",
                session=async_session,
                http_client=mock_http_client,
                log=log,
            )

        # Verify week 1 streak
        snap1 = await async_session.execute(
            text("SELECT streak_at_snapshot FROM pg_weekly_snapshots WHERE priority_id = :pid AND week_start = :ws"),
            {"pid": priority.id, "ws": date(2026, 1, 5)},
        )
        assert snap1.scalar() == 1

        # Week 2: Jan 12
        mock_events_w2 = [
            {
                "id": "event2",
                "summary": "[P1] More work",
                "start": {"dateTime": "2026-01-13T10:00:00Z"},
                "end": {"dateTime": "2026-01-13T14:00:00Z"},  # 4 hours
            },
        ]

        with patch(
            "backend.apps.priority_guardian.services.snapshot_service.list_events"
        ) as mock_list_events, patch(
            "backend.apps.priority_guardian.services.snapshot_service.compute_week_boundaries"
        ) as mock_boundaries, patch(
            "backend.apps.priority_guardian.services.snapshot_service.to_rfc3339"
        ) as mock_rfc:
            mock_list_events.return_value = (mock_events_w2, 0)
            mock_boundaries.return_value = (
                datetime(2026, 1, 12, 0, 0),
                datetime(2026, 1, 19, 0, 0),
            )
            mock_rfc.side_effect = lambda dt: dt.isoformat() + "Z"

            await _create_snapshots_for_week(
                user_id=user.id,
                week_start=date(2026, 1, 12),
                timezone_str="UTC",
                priorities=[priority],
                access_token="test_token",
                session=async_session,
                http_client=mock_http_client,
                log=log,
            )

        # Verify week 2 streak
        snap2 = await async_session.execute(
            text("SELECT streak_at_snapshot FROM pg_weekly_snapshots WHERE priority_id = :pid AND week_start = :ws"),
            {"pid": priority.id, "ws": date(2026, 1, 12)},
        )
        assert snap2.scalar() == 2

        # Verify priority streak_count
        prio_result = await async_session.execute(
            text("SELECT streak_count FROM pg_priorities WHERE id = :pid"),
            {"pid": priority.id},
        )
        assert prio_result.scalar() == 2

    @pytest.mark.asyncio
    async def test_streak_broken_by_zero_hour_week(
        self, async_session: AsyncSession
    ):
        """Test 3: Streak broken by zero-hour week."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        priority = PgPriority(
            user_id=user.id,
            name="Broken Streak",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date(2026, 3, 15),
            created_at=datetime(2025, 12, 1),
        )
        async_session.add(priority)
        await async_session.commit()

        mock_http_client = AsyncMock()
        log = {"user_id": str(user.id), "correlation_id": "test"}

        # Week 1: Create snapshot with hours > 0 (streak=1)
        mock_events_w1 = [
            {
                "id": "event1",
                "summary": "[P1] Work",
                "start": {"dateTime": "2026-01-06T09:00:00Z"},
                "end": {"dateTime": "2026-01-06T12:00:00Z"},
            },
        ]

        with patch(
            "backend.apps.priority_guardian.services.snapshot_service.list_events"
        ) as mock_list_events, patch(
            "backend.apps.priority_guardian.services.snapshot_service.compute_week_boundaries"
        ) as mock_boundaries, patch(
            "backend.apps.priority_guardian.services.snapshot_service.to_rfc3339"
        ) as mock_rfc:
            mock_list_events.return_value = (mock_events_w1, 0)
            mock_boundaries.return_value = (
                datetime(2026, 1, 5, 0, 0),
                datetime(2026, 1, 12, 0, 0),
            )
            mock_rfc.side_effect = lambda dt: dt.isoformat() + "Z"

            await _create_snapshots_for_week(
                user_id=user.id,
                week_start=date(2026, 1, 5),
                timezone_str="UTC",
                priorities=[priority],
                access_token="test_token",
                session=async_session,
                http_client=mock_http_client,
                log=log,
            )

        # Week 2: 0 hours (no P1 events)
        with patch(
            "backend.apps.priority_guardian.services.snapshot_service.list_events"
        ) as mock_list_events, patch(
            "backend.apps.priority_guardian.services.snapshot_service.compute_week_boundaries"
        ) as mock_boundaries, patch(
            "backend.apps.priority_guardian.services.snapshot_service.to_rfc3339"
        ) as mock_rfc:
            mock_list_events.return_value = ([], 0)  # No events
            mock_boundaries.return_value = (
                datetime(2026, 1, 12, 0, 0),
                datetime(2026, 1, 19, 0, 0),
            )
            mock_rfc.side_effect = lambda dt: dt.isoformat() + "Z"

            await _create_snapshots_for_week(
                user_id=user.id,
                week_start=date(2026, 1, 12),
                timezone_str="UTC",
                priorities=[priority],
                access_token="test_token",
                session=async_session,
                http_client=mock_http_client,
                log=log,
            )

        # Verify week 2 streak is 0 (broken)
        snap2 = await async_session.execute(
            text("SELECT streak_at_snapshot FROM pg_weekly_snapshots WHERE priority_id = :pid AND week_start = :ws"),
            {"pid": priority.id, "ws": date(2026, 1, 12)},
        )
        assert snap2.scalar() == 0

        # Verify priority streak_count is 0
        prio_result = await async_session.execute(
            text("SELECT streak_count FROM pg_priorities WHERE id = :pid"),
            {"pid": priority.id},
        )
        assert prio_result.scalar() == 0

    @pytest.mark.asyncio
    async def test_idempotency_no_duplicate_snapshots(
        self, async_session: AsyncSession
    ):
        """Test 4: Idempotency — calling twice for same week creates no duplicate."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        priority = PgPriority(
            user_id=user.id,
            name="Idempotent Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date(2026, 3, 15),
            created_at=datetime(2025, 12, 1),
        )
        async_session.add(priority)
        await async_session.commit()

        mock_http_client = AsyncMock()
        log = {"user_id": str(user.id), "correlation_id": "test"}

        mock_events = [
            {
                "id": "event1",
                "summary": "[P1] Work",
                "start": {"dateTime": "2026-01-06T09:00:00Z"},
                "end": {"dateTime": "2026-01-06T12:00:00Z"},
            },
        ]

        # First call
        with patch(
            "backend.apps.priority_guardian.services.snapshot_service.list_events"
        ) as mock_list_events, patch(
            "backend.apps.priority_guardian.services.snapshot_service.compute_week_boundaries"
        ) as mock_boundaries, patch(
            "backend.apps.priority_guardian.services.snapshot_service.to_rfc3339"
        ) as mock_rfc:
            mock_list_events.return_value = (mock_events, 0)
            mock_boundaries.return_value = (
                datetime(2026, 1, 5, 0, 0),
                datetime(2026, 1, 12, 0, 0),
            )
            mock_rfc.side_effect = lambda dt: dt.isoformat() + "Z"

            result1 = await _create_snapshots_for_week(
                user_id=user.id,
                week_start=date(2026, 1, 5),
                timezone_str="UTC",
                priorities=[priority],
                access_token="test_token",
                session=async_session,
                http_client=mock_http_client,
                log=log,
            )

        assert result1 is True  # First call creates snapshot

        # Second call (same week)
        with patch(
            "backend.apps.priority_guardian.services.snapshot_service.list_events"
        ) as mock_list_events, patch(
            "backend.apps.priority_guardian.services.snapshot_service.compute_week_boundaries"
        ) as mock_boundaries, patch(
            "backend.apps.priority_guardian.services.snapshot_service.to_rfc3339"
        ) as mock_rfc:
            mock_list_events.return_value = (mock_events, 0)
            mock_boundaries.return_value = (
                datetime(2026, 1, 5, 0, 0),
                datetime(2026, 1, 12, 0, 0),
            )
            mock_rfc.side_effect = lambda dt: dt.isoformat() + "Z"

            result2 = await _create_snapshots_for_week(
                user_id=user.id,
                week_start=date(2026, 1, 5),
                timezone_str="UTC",
                priorities=[priority],
                access_token="test_token",
                session=async_session,
                http_client=mock_http_client,
                log=log,
            )

        assert result2 is False  # Second call returns False (ON CONFLICT DO NOTHING)

        # Verify exactly 1 row exists
        count_result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_weekly_snapshots WHERE priority_id = :pid AND week_start = :ws"),
            {"pid": priority.id, "ws": date(2026, 1, 5)},
        )
        assert count_result.scalar() == 1

    @pytest.mark.asyncio
    async def test_partial_week_skipped_priority_created_mid_week(
        self, async_session: AsyncSession
    ):
        """Test 5: Partial week skipped — priority created mid-week."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Priority created on Thursday of test week (Jan 8, 2026)
        # Week starts Jan 5 (Monday), so priority is NOT eligible
        priority = PgPriority(
            user_id=user.id,
            name="Mid-week Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date(2026, 3, 15),
            created_at=datetime(2026, 1, 8),  # Thursday of week starting Jan 5
        )
        async_session.add(priority)
        await async_session.commit()

        mock_http_client = AsyncMock()
        log = {"user_id": str(user.id), "correlation_id": "test"}

        mock_events = [
            {
                "id": "event1",
                "summary": "[P1] Work",
                "start": {"dateTime": "2026-01-09T09:00:00Z"},
                "end": {"dateTime": "2026-01-09T12:00:00Z"},
            },
        ]

        with patch(
            "backend.apps.priority_guardian.services.snapshot_service.list_events"
        ) as mock_list_events, patch(
            "backend.apps.priority_guardian.services.snapshot_service.compute_week_boundaries"
        ) as mock_boundaries, patch(
            "backend.apps.priority_guardian.services.snapshot_service.to_rfc3339"
        ) as mock_rfc:
            mock_list_events.return_value = (mock_events, 0)
            mock_boundaries.return_value = (
                datetime(2026, 1, 5, 0, 0),
                datetime(2026, 1, 12, 0, 0),
            )
            mock_rfc.side_effect = lambda dt: dt.isoformat() + "Z"

            result = await _create_snapshots_for_week(
                user_id=user.id,
                week_start=date(2026, 1, 5),  # Week starts Jan 5
                timezone_str="UTC",
                priorities=[priority],
                access_token="test_token",
                session=async_session,
                http_client=mock_http_client,
                log=log,
            )

        # Verify function returns False (no snapshot created)
        assert result is False

        # Verify 0 rows created
        count_result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_weekly_snapshots WHERE priority_id = :pid"),
            {"pid": priority.id},
        )
        assert count_result.scalar() == 0

    @pytest.mark.asyncio
    async def test_multiple_priorities_each_gets_snapshot(
        self, async_session: AsyncSession
    ):
        """Test 6: Multiple priorities — each gets its own snapshot with correct keyword hours."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # P1 flexible priority
        priority_p1 = PgPriority(
            user_id=user.id,
            name="P1 Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date(2026, 3, 15),
            created_at=datetime(2025, 12, 1),
        )
        async_session.add(priority_p1)

        # P2 deadline priority
        priority_p2 = PgPriority(
            user_id=user.id,
            name="P2 Priority",
            type="deadline",
            calendar_keyword="P2",
            status="active",
            deadline=date(2026, 3, 15),
            created_at=datetime(2025, 12, 1),
        )
        async_session.add(priority_p2)
        await async_session.commit()

        mock_http_client = AsyncMock()
        log = {"user_id": str(user.id), "correlation_id": "test"}

        # Events: P1 gets 5h, P2 gets 3h, Other gets 2h
        mock_events = [
            {
                "id": "event1",
                "summary": "[P1] Project work",
                "start": {"dateTime": "2026-01-06T09:00:00Z"},
                "end": {"dateTime": "2026-01-06T14:00:00Z"},  # 5 hours
            },
            {
                "id": "event2",
                "summary": "[P2] Deadline work",
                "start": {"dateTime": "2026-01-07T10:00:00Z"},
                "end": {"dateTime": "2026-01-07T13:00:00Z"},  # 3 hours
            },
            {
                "id": "event3",
                "summary": "Team meeting",
                "start": {"dateTime": "2026-01-08T14:00:00Z"},
                "end": {"dateTime": "2026-01-08T16:00:00Z"},  # 2 hours other
            },
        ]

        with patch(
            "backend.apps.priority_guardian.services.snapshot_service.list_events"
        ) as mock_list_events, patch(
            "backend.apps.priority_guardian.services.snapshot_service.compute_week_boundaries"
        ) as mock_boundaries, patch(
            "backend.apps.priority_guardian.services.snapshot_service.to_rfc3339"
        ) as mock_rfc:
            mock_list_events.return_value = (mock_events, 0)
            mock_boundaries.return_value = (
                datetime(2026, 1, 5, 0, 0),
                datetime(2026, 1, 12, 0, 0),
            )
            mock_rfc.side_effect = lambda dt: dt.isoformat() + "Z"

            await _create_snapshots_for_week(
                user_id=user.id,
                week_start=date(2026, 1, 5),
                timezone_str="UTC",
                priorities=[priority_p1, priority_p2],
                access_token="test_token",
                session=async_session,
                http_client=mock_http_client,
                log=log,
            )

        # Query snapshots
        snap_result = await async_session.execute(
            text("""
                SELECT p.name, s.actual_hours, s.target_hours, s.other_hours, s.total_tracked_hours
                FROM pg_weekly_snapshots s
                JOIN pg_priorities p ON s.priority_id = p.id
                WHERE s.user_id = :uid AND s.week_start = :ws
                ORDER BY p.name
            """),
            {"uid": user.id, "ws": date(2026, 1, 5)},
        )
        rows = snap_result.fetchall()

        assert len(rows) == 2

        # P1 Priority
        assert rows[0][0] == "P1 Priority"
        assert rows[0][1] == Decimal("5.00")  # actual_hours
        assert rows[0][2] == Decimal("10.00")  # target_hours (flexible)
        assert rows[0][3] == Decimal("2.00")  # other_hours (denormalized)
        assert rows[0][4] == Decimal("10.00")  # total_tracked_hours (5+3+2)

        # P2 Priority
        assert rows[1][0] == "P2 Priority"
        assert rows[1][1] == Decimal("3.00")  # actual_hours
        assert rows[1][2] is None  # target_hours (deadline = NULL)
        assert rows[1][3] == Decimal("2.00")  # other_hours (same, denormalized)
        assert rows[1][4] == Decimal("10.00")  # total_tracked_hours (same)

        # Verify denormalization invariant: sum(priority actual_hours) + other_hours == total_tracked_hours
        total_priority_hours = sum(row[1] for row in rows)  # actual_hours from all priority snapshots
        other_hours = rows[0][3]  # other_hours (same denormalized value on all rows)
        total_tracked = rows[0][4]  # total_tracked_hours (same denormalized value on all rows)
        assert total_priority_hours + other_hours == total_tracked, (
            f"Allocation invariant violated: {total_priority_hours} + {other_hours} != {total_tracked}"
        )

    @pytest.mark.asyncio
    async def test_avg_target_achievement_computed_after_two_weeks(
        self, async_session: AsyncSession
    ):
        """Test 7: Aggregate avg_target_achievement computed correctly after 2 weeks."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        priority = PgPriority(
            user_id=user.id,
            name="Achievement Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date(2026, 3, 15),
            created_at=datetime(2025, 12, 1),
        )
        async_session.add(priority)
        await async_session.commit()

        mock_http_client = AsyncMock()
        log = {"user_id": str(user.id), "correlation_id": "test"}

        # Week 1: 8h (80% of 10h target)
        mock_events_w1 = [
            {
                "id": "event1",
                "summary": "[P1] Work",
                "start": {"dateTime": "2026-01-06T09:00:00Z"},
                "end": {"dateTime": "2026-01-06T17:00:00Z"},  # 8 hours
            },
        ]

        with patch(
            "backend.apps.priority_guardian.services.snapshot_service.list_events"
        ) as mock_list_events, patch(
            "backend.apps.priority_guardian.services.snapshot_service.compute_week_boundaries"
        ) as mock_boundaries, patch(
            "backend.apps.priority_guardian.services.snapshot_service.to_rfc3339"
        ) as mock_rfc:
            mock_list_events.return_value = (mock_events_w1, 0)
            mock_boundaries.return_value = (
                datetime(2026, 1, 5, 0, 0),
                datetime(2026, 1, 12, 0, 0),
            )
            mock_rfc.side_effect = lambda dt: dt.isoformat() + "Z"

            await _create_snapshots_for_week(
                user_id=user.id,
                week_start=date(2026, 1, 5),
                timezone_str="UTC",
                priorities=[priority],
                access_token="test_token",
                session=async_session,
                http_client=mock_http_client,
                log=log,
            )

        # Week 2: 12h (120% of 10h target)
        mock_events_w2 = [
            {
                "id": "event2",
                "summary": "[P1] Work",
                "start": {"dateTime": "2026-01-13T08:00:00Z"},
                "end": {"dateTime": "2026-01-13T20:00:00Z"},  # 12 hours
            },
        ]

        with patch(
            "backend.apps.priority_guardian.services.snapshot_service.list_events"
        ) as mock_list_events, patch(
            "backend.apps.priority_guardian.services.snapshot_service.compute_week_boundaries"
        ) as mock_boundaries, patch(
            "backend.apps.priority_guardian.services.snapshot_service.to_rfc3339"
        ) as mock_rfc:
            mock_list_events.return_value = (mock_events_w2, 0)
            mock_boundaries.return_value = (
                datetime(2026, 1, 12, 0, 0),
                datetime(2026, 1, 19, 0, 0),
            )
            mock_rfc.side_effect = lambda dt: dt.isoformat() + "Z"

            await _create_snapshots_for_week(
                user_id=user.id,
                week_start=date(2026, 1, 12),
                timezone_str="UTC",
                priorities=[priority],
                access_token="test_token",
                session=async_session,
                http_client=mock_http_client,
                log=log,
            )

        # Query priority aggregates
        prio_result = await async_session.execute(
            text("SELECT avg_target_achievement, total_hours_invested FROM pg_priorities WHERE id = :pid"),
            {"pid": priority.id},
        )
        row = prio_result.fetchone()

        # avg_target_achievement = (80 + 120) / 2 = 100
        assert row[0] == pytest.approx(100.0, rel=0.01)
        # total_hours_invested = 8 + 12 = 20
        assert row[1] == Decimal("20.00")

    @pytest.mark.asyncio
    async def test_deadline_priority_target_hours_null(
        self, async_session: AsyncSession
    ):
        """Test 8: Deadline priority — target_hours is NULL in snapshot."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        priority = PgPriority(
            user_id=user.id,
            name="Deadline Priority",
            type="deadline",
            calendar_keyword="P1",
            status="active",
            deadline=date(2026, 3, 15),
            created_at=datetime(2025, 12, 1),
        )
        async_session.add(priority)
        await async_session.commit()

        mock_http_client = AsyncMock()
        log = {"user_id": str(user.id), "correlation_id": "test"}

        mock_events = [
            {
                "id": "event1",
                "summary": "[P1] Deadline work",
                "start": {"dateTime": "2026-01-06T09:00:00Z"},
                "end": {"dateTime": "2026-01-06T12:00:00Z"},
            },
        ]

        with patch(
            "backend.apps.priority_guardian.services.snapshot_service.list_events"
        ) as mock_list_events, patch(
            "backend.apps.priority_guardian.services.snapshot_service.compute_week_boundaries"
        ) as mock_boundaries, patch(
            "backend.apps.priority_guardian.services.snapshot_service.to_rfc3339"
        ) as mock_rfc:
            mock_list_events.return_value = (mock_events, 0)
            mock_boundaries.return_value = (
                datetime(2026, 1, 5, 0, 0),
                datetime(2026, 1, 12, 0, 0),
            )
            mock_rfc.side_effect = lambda dt: dt.isoformat() + "Z"

            await _create_snapshots_for_week(
                user_id=user.id,
                week_start=date(2026, 1, 5),
                timezone_str="UTC",
                priorities=[priority],
                access_token="test_token",
                session=async_session,
                http_client=mock_http_client,
                log=log,
            )

        # Query snapshot
        snap_result = await async_session.execute(
            text("SELECT target_hours FROM pg_weekly_snapshots WHERE priority_id = :pid"),
            {"pid": priority.id},
        )
        assert snap_result.scalar() is None  # target_hours IS NULL for deadline

        # Query priority — avg_target_achievement should stay NULL
        prio_result = await async_session.execute(
            text("SELECT avg_target_achievement FROM pg_priorities WHERE id = :pid"),
            {"pid": priority.id},
        )
        assert prio_result.scalar() is None

    @pytest.mark.asyncio
    async def test_keyword_preserved_at_snapshot_time(
        self, async_session: AsyncSession
    ):
        """Test 9: calendar_keyword_at_snapshot preserves keyword at creation time."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        priority = PgPriority(
            user_id=user.id,
            name="Keyword Swap Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date(2026, 3, 15),
            created_at=datetime(2025, 12, 1),
        )
        async_session.add(priority)
        await async_session.commit()

        mock_http_client = AsyncMock()
        log = {"user_id": str(user.id), "correlation_id": "test"}

        # Week 1: Priority has P1
        mock_events_w1 = [
            {
                "id": "event1",
                "summary": "[P1] Work",
                "start": {"dateTime": "2026-01-06T09:00:00Z"},
                "end": {"dateTime": "2026-01-06T12:00:00Z"},
            },
        ]

        with patch(
            "backend.apps.priority_guardian.services.snapshot_service.list_events"
        ) as mock_list_events, patch(
            "backend.apps.priority_guardian.services.snapshot_service.compute_week_boundaries"
        ) as mock_boundaries, patch(
            "backend.apps.priority_guardian.services.snapshot_service.to_rfc3339"
        ) as mock_rfc:
            mock_list_events.return_value = (mock_events_w1, 0)
            mock_boundaries.return_value = (
                datetime(2026, 1, 5, 0, 0),
                datetime(2026, 1, 12, 0, 0),
            )
            mock_rfc.side_effect = lambda dt: dt.isoformat() + "Z"

            await _create_snapshots_for_week(
                user_id=user.id,
                week_start=date(2026, 1, 5),
                timezone_str="UTC",
                priorities=[priority],
                access_token="test_token",
                session=async_session,
                http_client=mock_http_client,
                log=log,
            )

        # Change priority keyword to P2 (simulate swap)
        await async_session.execute(
            text("UPDATE pg_priorities SET calendar_keyword = 'P2' WHERE id = :pid"),
            {"pid": priority.id},
        )
        await async_session.commit()

        # Reload priority to get updated keyword
        await async_session.refresh(priority)

        # Week 2: Priority now has P2
        mock_events_w2 = [
            {
                "id": "event2",
                "summary": "[P2] Work",
                "start": {"dateTime": "2026-01-13T09:00:00Z"},
                "end": {"dateTime": "2026-01-13T12:00:00Z"},
            },
        ]

        with patch(
            "backend.apps.priority_guardian.services.snapshot_service.list_events"
        ) as mock_list_events, patch(
            "backend.apps.priority_guardian.services.snapshot_service.compute_week_boundaries"
        ) as mock_boundaries, patch(
            "backend.apps.priority_guardian.services.snapshot_service.to_rfc3339"
        ) as mock_rfc:
            mock_list_events.return_value = (mock_events_w2, 0)
            mock_boundaries.return_value = (
                datetime(2026, 1, 12, 0, 0),
                datetime(2026, 1, 19, 0, 0),
            )
            mock_rfc.side_effect = lambda dt: dt.isoformat() + "Z"

            await _create_snapshots_for_week(
                user_id=user.id,
                week_start=date(2026, 1, 12),
                timezone_str="UTC",
                priorities=[priority],
                access_token="test_token",
                session=async_session,
                http_client=mock_http_client,
                log=log,
            )

        # Query both snapshots
        snap_result = await async_session.execute(
            text("""
                SELECT week_start, calendar_keyword_at_snapshot
                FROM pg_weekly_snapshots
                WHERE priority_id = :pid
                ORDER BY week_start
            """),
            {"pid": priority.id},
        )
        rows = snap_result.fetchall()

        assert len(rows) == 2
        assert rows[0][0] == date(2026, 1, 5)
        assert rows[0][1] == "P1"  # Week 1 preserved P1
        assert rows[1][0] == date(2026, 1, 12)
        assert rows[1][1] == "P2"  # Week 2 has new P2

    @pytest.mark.asyncio
    async def test_backfill_multiple_weeks_via_ensure_snapshots(
        self, async_session: AsyncSession
    ):
        """Test 10: Backfill multiple missing weeks via ensure_snapshots_up_to_date."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Create Google connection
        connection = CoreConnection(
            user_id=user.id,
            provider="google",
            connection_type="google",
            encrypted_access_token="encrypted_test_token",
            token_expires_at=datetime.now() + timedelta(hours=1),
            scopes=["https://www.googleapis.com/auth/calendar.readonly"],
            revoked_at=None,
        )
        async_session.add(connection)

        # Create priority (well before all test weeks)
        priority = PgPriority(
            user_id=user.id,
            name="Backfill Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date(2026, 3, 15),
            created_at=datetime(2025, 12, 1),
        )
        async_session.add(priority)
        await async_session.commit()

        mock_http_client = AsyncMock()

        # Target weeks: Jan 5, Jan 12, Jan 19
        target_weeks = [date(2026, 1, 5), date(2026, 1, 12), date(2026, 1, 19)]

        # Events per week: week 1: 5h, week 2: 8h, week 3: 0h
        def mock_list_events_side_effect(http_client, token, time_min, time_max, **kwargs):
            if "2026-01-05" in time_min or "2026-01-06" in time_min:
                return ([{
                    "id": "w1",
                    "summary": "[P1] Week 1",
                    "start": {"dateTime": "2026-01-06T09:00:00Z"},
                    "end": {"dateTime": "2026-01-06T14:00:00Z"},  # 5h
                }], 0)
            elif "2026-01-12" in time_min or "2026-01-13" in time_min:
                return ([{
                    "id": "w2",
                    "summary": "[P1] Week 2",
                    "start": {"dateTime": "2026-01-13T08:00:00Z"},
                    "end": {"dateTime": "2026-01-13T16:00:00Z"},  # 8h
                }], 0)
            else:
                return ([], 0)  # Week 3: 0h

        with patch(
            "backend.apps.priority_guardian.services.snapshot_service.ensure_valid_access_token"
        ) as mock_token, patch(
            "backend.apps.priority_guardian.services.snapshot_service.get_user_timezone"
        ) as mock_tz, patch(
            "backend.apps.priority_guardian.services.snapshot_service._compute_target_weeks"
        ) as mock_weeks, patch(
            "backend.apps.priority_guardian.services.snapshot_service.list_events"
        ) as mock_list_events, patch(
            "backend.apps.priority_guardian.services.snapshot_service.compute_week_boundaries"
        ) as mock_boundaries, patch(
            "backend.apps.priority_guardian.services.snapshot_service.to_rfc3339"
        ) as mock_rfc:
            mock_token.return_value = {"access_token": "test_token"}
            mock_tz.return_value = "UTC"
            mock_weeks.return_value = target_weeks
            mock_list_events.side_effect = mock_list_events_side_effect

            def boundaries_side_effect(tz, week_start):
                ws = datetime.combine(week_start, datetime.min.time())
                we = ws + timedelta(days=7)
                return (ws, we)

            mock_boundaries.side_effect = boundaries_side_effect
            mock_rfc.side_effect = lambda dt: dt.isoformat() + "Z"

            result = await ensure_snapshots_up_to_date(
                user_id=user.id,
                session=async_session,
                http_client=mock_http_client,
            )

        # Verify return value
        assert result["checked"] == 3
        assert result["created"] == 3  # All 3 weeks get snapshots (including 0h week)
        assert result["errors"] == 0

        # Query all snapshots
        snap_result = await async_session.execute(
            text("""
                SELECT week_start, actual_hours, streak_at_snapshot
                FROM pg_weekly_snapshots
                WHERE priority_id = :pid
                ORDER BY week_start
            """),
            {"pid": priority.id},
        )
        rows = snap_result.fetchall()

        assert len(rows) == 3
        # Week 1: 5h, streak=1
        assert rows[0][0] == date(2026, 1, 5)
        assert rows[0][1] == Decimal("5.00")
        assert rows[0][2] == 1
        # Week 2: 8h, streak=2
        assert rows[1][0] == date(2026, 1, 12)
        assert rows[1][1] == Decimal("8.00")
        assert rows[1][2] == 2
        # Week 3: 0h, streak=0 (broken)
        assert rows[2][0] == date(2026, 1, 19)
        assert rows[2][1] == Decimal("0.00")
        assert rows[2][2] == 0

        # Verify priority aggregates
        prio_result = await async_session.execute(
            text("SELECT streak_count, total_hours_invested FROM pg_priorities WHERE id = :pid"),
            {"pid": priority.id},
        )
        prio_row = prio_result.fetchone()
        assert prio_row[0] == 0  # streak_count = last week's streak (0)
        assert prio_row[1] == Decimal("13.00")  # total = 5 + 8 + 0

        # Call again — idempotent
        with patch(
            "backend.apps.priority_guardian.services.snapshot_service.ensure_valid_access_token"
        ) as mock_token, patch(
            "backend.apps.priority_guardian.services.snapshot_service.get_user_timezone"
        ) as mock_tz, patch(
            "backend.apps.priority_guardian.services.snapshot_service._compute_target_weeks"
        ) as mock_weeks, patch(
            "backend.apps.priority_guardian.services.snapshot_service.list_events"
        ) as mock_list_events, patch(
            "backend.apps.priority_guardian.services.snapshot_service.compute_week_boundaries"
        ) as mock_boundaries, patch(
            "backend.apps.priority_guardian.services.snapshot_service.to_rfc3339"
        ) as mock_rfc:
            mock_token.return_value = {"access_token": "test_token"}
            mock_tz.return_value = "UTC"
            mock_weeks.return_value = target_weeks
            mock_list_events.side_effect = mock_list_events_side_effect
            mock_boundaries.side_effect = boundaries_side_effect
            mock_rfc.side_effect = lambda dt: dt.isoformat() + "Z"

            result2 = await ensure_snapshots_up_to_date(
                user_id=user.id,
                session=async_session,
                http_client=mock_http_client,
            )

        assert result2["checked"] == 3
        assert result2["created"] == 0  # Idempotent - no new snapshots
        assert result2["errors"] == 0
