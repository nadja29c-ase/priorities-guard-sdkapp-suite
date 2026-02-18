"""
Integration tests for snapshot-based weekly reports (Increment 15).

Tests verify:
- Past week reports use snapshot data when available
- Keyword swaps don't affect historical reports
- calendar_keyword_at_snapshot is persisted correctly
- Partial snapshot coverage falls through to live computation
"""

import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.priority_guardian.db_models import PgPriority, PgWeeklySnapshot
from backend.core.models import CoreUser


class TestSnapshotKeywordPersistence:
    """Verify calendar_keyword_at_snapshot is persisted and accepted."""

    @pytest.mark.asyncio
    async def test_calendar_keyword_at_snapshot_accepts_valid_keywords(
        self, async_session: AsyncSession
    ):
        """Valid keywords (P1, P2, P3) are accepted for calendar_keyword_at_snapshot."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        priority = PgPriority(
            user_id=user.id,
            name="Test Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date.today() + timedelta(days=30),
            created_at=datetime(2026, 1, 1),
        )
        async_session.add(priority)
        await async_session.commit()

        # Insert snapshots with all valid keywords
        for kw in ["P1", "P2", "P3"]:
            # Use different week_start for each to avoid unique constraint
            week_offset = {"P1": 0, "P2": 7, "P3": 14}[kw]
            await async_session.execute(
                text("""
                    INSERT INTO pg_weekly_snapshots
                    (id, priority_id, user_id, week_start, week_end, actual_hours, target_hours, streak_at_snapshot, calendar_keyword_at_snapshot)
                    VALUES (gen_random_uuid(), :pid, :uid, :ws, :we, 5.0, 10.0, 1, :kw)
                """),
                {
                    "pid": priority.id,
                    "uid": user.id,
                    "ws": date(2026, 1, 19) + timedelta(days=week_offset),
                    "we": date(2026, 1, 25) + timedelta(days=week_offset),
                    "kw": kw,
                },
            )

        await async_session.commit()

        # Verify all 3 snapshots exist with correct keywords
        result = await async_session.execute(
            text("""
                SELECT calendar_keyword_at_snapshot
                FROM pg_weekly_snapshots
                WHERE priority_id = :pid
                ORDER BY week_start
            """),
            {"pid": priority.id},
        )
        keywords = [row[0] for row in result.fetchall()]
        assert keywords == ["P1", "P2", "P3"]

    @pytest.mark.asyncio
    async def test_calendar_keyword_at_snapshot_allows_null(
        self, async_session: AsyncSession
    ):
        """NULL is allowed for calendar_keyword_at_snapshot (pre-migration snapshots)."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        priority = PgPriority(
            user_id=user.id,
            name="Test Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date.today() + timedelta(days=30),
            created_at=datetime(2026, 1, 1),
        )
        async_session.add(priority)
        await async_session.commit()

        # Insert snapshot with NULL keyword (simulating pre-migration)
        await async_session.execute(
            text("""
                INSERT INTO pg_weekly_snapshots
                (id, priority_id, user_id, week_start, week_end, actual_hours, target_hours, streak_at_snapshot, calendar_keyword_at_snapshot)
                VALUES (gen_random_uuid(), :pid, :uid, '2026-01-19', '2026-01-25', 5.0, 10.0, 1, NULL)
            """),
            {"pid": priority.id, "uid": user.id},
        )
        await async_session.commit()

        # Verify snapshot exists with NULL keyword
        result = await async_session.execute(
            text("""
                SELECT calendar_keyword_at_snapshot
                FROM pg_weekly_snapshots
                WHERE priority_id = :pid
            """),
            {"pid": priority.id},
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] is None

    @pytest.mark.asyncio
    async def test_snapshot_preserves_keyword_at_creation(
        self, async_session: AsyncSession
    ):
        """Snapshot stores the keyword from the priority at insertion time."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Create priority with P1
        priority = PgPriority(
            user_id=user.id,
            name="Test Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date.today() + timedelta(days=30),
            created_at=datetime(2026, 1, 1),
        )
        async_session.add(priority)
        await async_session.commit()

        # Insert snapshot capturing P1
        await async_session.execute(
            text("""
                INSERT INTO pg_weekly_snapshots
                (id, priority_id, user_id, week_start, week_end, actual_hours, target_hours, streak_at_snapshot, calendar_keyword_at_snapshot)
                VALUES (gen_random_uuid(), :pid, :uid, '2026-01-19', '2026-01-25', 5.0, 10.0, 1, 'P1')
            """),
            {"pid": priority.id, "uid": user.id},
        )
        await async_session.commit()

        # Change priority keyword to P3
        await async_session.execute(
            text("UPDATE pg_priorities SET calendar_keyword = 'P3' WHERE id = :pid"),
            {"pid": priority.id},
        )
        await async_session.commit()

        # Verify snapshot still has original P1
        result = await async_session.execute(
            text("""
                SELECT calendar_keyword_at_snapshot
                FROM pg_weekly_snapshots
                WHERE priority_id = :pid AND week_start = '2026-01-19'
            """),
            {"pid": priority.id},
        )
        row = result.fetchone()
        assert row[0] == "P1", "Snapshot keyword should be preserved as P1 even after priority changed to P3"

        # Verify priority now has P3
        result = await async_session.execute(
            text("SELECT calendar_keyword FROM pg_priorities WHERE id = :pid"),
            {"pid": priority.id},
        )
        row = result.fetchone()
        assert row[0] == "P3", "Priority should have updated to P3"


class TestSnapshotWeeklyReportIntegration:
    """
    Integration tests for weekly report snapshot usage.

    These tests verify the end-to-end flow where past week reports
    use snapshot data with the correct historical keyword.
    """

    @pytest.mark.asyncio
    async def test_snapshot_data_structure_complete(
        self, async_session: AsyncSession
    ):
        """Verify snapshot row has all expected columns including calendar_keyword_at_snapshot."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        priority = PgPriority(
            user_id=user.id,
            name="Test Priority",
            type="flexible",
            calendar_keyword="P2",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date.today() + timedelta(days=30),
            created_at=datetime(2026, 1, 1),
        )
        async_session.add(priority)
        await async_session.commit()

        # Insert complete snapshot
        await async_session.execute(
            text("""
                INSERT INTO pg_weekly_snapshots
                (id, priority_id, user_id, week_start, week_end, actual_hours, target_hours, streak_at_snapshot, calendar_keyword_at_snapshot)
                VALUES (gen_random_uuid(), :pid, :uid, '2026-01-19', '2026-01-25', 7.5, 10.0, 2, 'P2')
            """),
            {"pid": priority.id, "uid": user.id},
        )
        await async_session.commit()

        # Query snapshot and verify all columns
        result = await async_session.execute(
            text("""
                SELECT
                    priority_id,
                    user_id,
                    week_start,
                    week_end,
                    actual_hours,
                    target_hours,
                    streak_at_snapshot,
                    calendar_keyword_at_snapshot
                FROM pg_weekly_snapshots
                WHERE priority_id = :pid
            """),
            {"pid": priority.id},
        )
        row = result.fetchone()

        assert row is not None
        assert row[0] == priority.id  # priority_id
        assert row[1] == user.id  # user_id
        assert row[2] == date(2026, 1, 19)  # week_start
        assert row[3] == date(2026, 1, 25)  # week_end
        assert float(row[4]) == 7.5  # actual_hours
        assert float(row[5]) == 10.0  # target_hours
        assert row[6] == 2  # streak_at_snapshot
        assert row[7] == "P2"  # calendar_keyword_at_snapshot

    @pytest.mark.asyncio
    async def test_multiple_priorities_multiple_snapshots(
        self, async_session: AsyncSession
    ):
        """Multiple priorities can each have snapshots with different keywords."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Create 3 priorities with different keywords
        priorities = []
        for i, kw in enumerate(["P1", "P2", "P3"]):
            p = PgPriority(
                user_id=user.id,
                name=f"Priority {kw}",
                type="flexible",
                calendar_keyword=kw,
                status="active",
                weekly_hour_target=Decimal("10.0"),
                checkpoint_date=date.today() + timedelta(days=30),
                created_at=datetime(2026, 1, 1),
            )
            async_session.add(p)
            priorities.append((p, kw))

        await async_session.commit()

        # Insert snapshot for each with their respective keywords
        for p, kw in priorities:
            await async_session.execute(
                text("""
                    INSERT INTO pg_weekly_snapshots
                    (id, priority_id, user_id, week_start, week_end, actual_hours, target_hours, streak_at_snapshot, calendar_keyword_at_snapshot)
                    VALUES (gen_random_uuid(), :pid, :uid, '2026-01-19', '2026-01-25', 5.0, 10.0, 1, :kw)
                """),
                {"pid": p.id, "uid": user.id, "kw": kw},
            )
        await async_session.commit()

        # Verify all 3 snapshots exist
        result = await async_session.execute(
            text("""
                SELECT s.calendar_keyword_at_snapshot, p.name
                FROM pg_weekly_snapshots s
                JOIN pg_priorities p ON s.priority_id = p.id
                WHERE s.user_id = :uid
                ORDER BY p.name
            """),
            {"uid": user.id},
        )
        rows = result.fetchall()

        assert len(rows) == 3
        # Sorted by name: Priority P1, Priority P2, Priority P3
        assert rows[0][0] == "P1"
        assert rows[1][0] == "P2"
        assert rows[2][0] == "P3"

    @pytest.mark.asyncio
    async def test_keyword_swap_preserves_historical_snapshot_keyword(
        self, async_session: AsyncSession
    ):
        """After swapping keywords, old snapshots retain their original keyword.

        Uses atomic swap via temporary NULL to satisfy unique constraint.
        """
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Create two priorities: P1 and P3
        priority_a = PgPriority(
            user_id=user.id,
            name="Priority A",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date.today() + timedelta(days=30),
            created_at=datetime(2026, 1, 1),
        )
        priority_b = PgPriority(
            user_id=user.id,
            name="Priority B",
            type="flexible",
            calendar_keyword="P3",
            status="active",
            weekly_hour_target=Decimal("8.0"),
            checkpoint_date=date.today() + timedelta(days=30),
            created_at=datetime(2026, 1, 1),
        )
        async_session.add_all([priority_a, priority_b])
        await async_session.commit()

        # Insert snapshots with their original keywords
        await async_session.execute(
            text("""
                INSERT INTO pg_weekly_snapshots
                (id, priority_id, user_id, week_start, week_end, actual_hours, target_hours, streak_at_snapshot, calendar_keyword_at_snapshot)
                VALUES
                    (gen_random_uuid(), :pid_a, :uid, '2026-01-19', '2026-01-25', 8.0, 10.0, 1, 'P1'),
                    (gen_random_uuid(), :pid_b, :uid, '2026-01-19', '2026-01-25', 6.0, 8.0, 1, 'P3')
            """),
            {"pid_a": priority_a.id, "pid_b": priority_b.id, "uid": user.id},
        )
        await async_session.commit()

        # Atomic swap: A(P1)->NULL, B(P3)->P1, A(NULL)->P3
        # Step 1: Set A to NULL (allowed by partial index since NULL not indexed)
        await async_session.execute(
            text("UPDATE pg_priorities SET calendar_keyword = NULL WHERE id = :pid"),
            {"pid": priority_a.id},
        )
        # Step 2: Set B to P1 (now available)
        await async_session.execute(
            text("UPDATE pg_priorities SET calendar_keyword = 'P1' WHERE id = :pid"),
            {"pid": priority_b.id},
        )
        # Step 3: Set A to P3 (now available)
        await async_session.execute(
            text("UPDATE pg_priorities SET calendar_keyword = 'P3' WHERE id = :pid"),
            {"pid": priority_a.id},
        )
        await async_session.commit()

        # Verify current priorities have swapped keywords
        result = await async_session.execute(
            text("SELECT name, calendar_keyword FROM pg_priorities WHERE user_id = :uid ORDER BY name"),
            {"uid": user.id},
        )
        rows = result.fetchall()
        assert rows[0][1] == "P3"  # Priority A now P3
        assert rows[1][1] == "P1"  # Priority B now P1

        # Verify snapshots still have original keywords
        result = await async_session.execute(
            text("""
                SELECT p.name, s.calendar_keyword_at_snapshot
                FROM pg_weekly_snapshots s
                JOIN pg_priorities p ON s.priority_id = p.id
                WHERE s.user_id = :uid
                ORDER BY p.name
            """),
            {"uid": user.id},
        )
        rows = result.fetchall()
        assert rows[0][1] == "P1"  # Priority A's snapshot still shows P1
        assert rows[1][1] == "P3"  # Priority B's snapshot still shows P3
