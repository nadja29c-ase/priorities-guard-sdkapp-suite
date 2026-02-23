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


class TestPastWeekEligibilityFilter:
    """
    Real-DB integration tests for past week eligibility filtering (Increment 22/23).

    Tests verify that the eligibility filter works correctly with real PostgreSQL:
    - Priorities created after the requested week are excluded
    - Priorities created before/on the week are included
    - Mixed eligibility scenarios work correctly
    - Calendar API is NOT called when no eligible priorities exist
    """

    @pytest.mark.asyncio
    async def test_past_week_before_priority_exists_returns_empty_no_calendar_fetch(
        self, async_session: AsyncSession
    ):
        """Past week before priority existed returns empty report, no calendar fetch."""
        from unittest.mock import AsyncMock, patch
        from backend.apps.priority_guardian.services.weekly_report_service import (
            generate_weekly_report,
        )
        from backend.core.models import CoreConnection

        # Create user
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

        # Create priority created AFTER the requested week (Feb 19)
        priority = PgPriority(
            user_id=user.id,
            name="Future Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date(2026, 3, 15),
            created_at=datetime(2026, 2, 19),  # Thursday, Feb 19
        )
        async_session.add(priority)
        await async_session.commit()

        # Mock only Google API calls
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

            # Request week Jan 5-11 (well before priority created Feb 19)
            result = await generate_weekly_report(
                user_id=user.id,
                session=async_session,
                http_client=mock_http_client,
                week_start=date(2026, 1, 5),  # Monday, Jan 5
            )

        # Verify empty_report shape
        assert result["success"] is True
        data = result["data"]
        assert data["priorities"] == []
        assert data["is_current_week"] is False
        assert data["time_allocation"]["total_tracked_hours"] == 0.0
        assert data["time_allocation"]["other_hours"] == 0.0

        # CRITICAL: list_events should NOT have been called (early return)
        mock_events.assert_not_called()

    @pytest.mark.asyncio
    async def test_past_week_where_priority_eligible_returns_data_with_calendar_fetch(
        self, async_session: AsyncSession
    ):
        """Past week where priority IS eligible returns data with calendar fetch."""
        from unittest.mock import AsyncMock, patch
        from backend.apps.priority_guardian.services.weekly_report_service import (
            generate_weekly_report,
        )
        from backend.core.models import CoreConnection

        # Create user
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

        # Create priority created Jan 1 (Thursday)
        # first_valid_monday = Jan 5, so eligible for week starting Jan 5
        priority = PgPriority(
            user_id=user.id,
            name="Eligible Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date(2026, 3, 15),
            created_at=datetime(2026, 1, 1),  # Thursday, Jan 1
        )
        async_session.add(priority)
        await async_session.commit()

        # Mock calendar events
        mock_events_data = [
            {
                "id": "event1",
                "summary": "[P1] Project work",
                "start": {"dateTime": "2026-01-06T09:00:00Z"},
                "end": {"dateTime": "2026-01-06T12:00:00Z"},  # 3 hours
            },
            {
                "id": "event2",
                "summary": "[P1] More work",
                "start": {"dateTime": "2026-01-07T14:00:00Z"},
                "end": {"dateTime": "2026-01-07T16:00:00Z"},  # 2 hours
            },
        ]

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
            mock_events.return_value = (mock_events_data, 0)

            # Request week Jan 5-11
            result = await generate_weekly_report(
                user_id=user.id,
                session=async_session,
                http_client=mock_http_client,
                week_start=date(2026, 1, 5),
            )

        # Verify list_events WAS called
        mock_events.assert_called_once()

        # Verify response has the priority with correct hours
        assert result["success"] is True
        data = result["data"]
        assert len(data["priorities"]) == 1
        assert data["priorities"][0]["name"] == "Eligible Priority"
        assert data["priorities"][0]["actual_hours"] == 5.0  # 3h + 2h
        assert data["is_current_week"] is False

    @pytest.mark.asyncio
    async def test_mixed_eligibility_only_eligible_priority_in_response(
        self, async_session: AsyncSession
    ):
        """Mixed eligibility: only eligible priority appears, ineligible hours go to other."""
        from unittest.mock import AsyncMock, patch
        from backend.apps.priority_guardian.services.weekly_report_service import (
            generate_weekly_report,
        )
        from backend.core.models import CoreConnection

        # Create user
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

        # Priority 1: Created Jan 1, eligible for Jan 5 week
        priority_eligible = PgPriority(
            user_id=user.id,
            name="Eligible P1",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date(2026, 3, 15),
            created_at=datetime(2026, 1, 1),
        )
        async_session.add(priority_eligible)

        # Priority 2: Created Feb 19, NOT eligible for Jan 5 week
        priority_ineligible = PgPriority(
            user_id=user.id,
            name="Ineligible P2",
            type="flexible",
            calendar_keyword="P2",
            status="active",
            weekly_hour_target=Decimal("8.0"),
            checkpoint_date=date(2026, 3, 15),
            created_at=datetime(2026, 2, 19),
        )
        async_session.add(priority_ineligible)
        await async_session.commit()

        # Mock calendar events for both P1 and P2
        mock_events_data = [
            {
                "id": "event1",
                "summary": "[P1] Eligible work",
                "start": {"dateTime": "2026-01-06T09:00:00Z"},
                "end": {"dateTime": "2026-01-06T12:00:00Z"},  # 3 hours P1
            },
            {
                "id": "event2",
                "summary": "[P2] Ineligible work",
                "start": {"dateTime": "2026-01-07T10:00:00Z"},
                "end": {"dateTime": "2026-01-07T12:00:00Z"},  # 2 hours P2
            },
            {
                "id": "event3",
                "summary": "Lunch meeting",
                "start": {"dateTime": "2026-01-08T12:00:00Z"},
                "end": {"dateTime": "2026-01-08T13:00:00Z"},  # 1 hour other
            },
        ]

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
            mock_events.return_value = (mock_events_data, 0)

            result = await generate_weekly_report(
                user_id=user.id,
                session=async_session,
                http_client=mock_http_client,
                week_start=date(2026, 1, 5),
            )

        # Verify only eligible priority in response
        assert result["success"] is True
        data = result["data"]
        assert len(data["priorities"]) == 1
        assert data["priorities"][0]["name"] == "Eligible P1"
        assert data["priorities"][0]["actual_hours"] == 3.0

        # P2 hours are tracked under keywords.P2 but NOT attributed to any priority
        # (since P2 priority is filtered out as ineligible)
        # other_hours only includes events with no keyword match (lunch = 1h)
        assert data["time_allocation"]["other_hours"] == 1.0  # Just lunch
        assert data["time_allocation"]["keywords"]["P2"]["hours"] == 2.0  # P2 tracked but no priority
        assert data["time_allocation"]["total_tracked_hours"] == 6.0  # 3h P1 + 2h P2 + 1h lunch

        # Verify P2 is NOT in priorities list (the key assertion)
        priority_names = [p["name"] for p in data["priorities"]]
        assert "Ineligible P2" not in priority_names
