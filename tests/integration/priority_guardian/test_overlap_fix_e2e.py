"""
End-to-end integration tests for calendar event overlap fix (Increment 82.2).

Tests verify the interval sweep allocation algorithm is correctly wired through:
1. GET /weekly-report (current week, live computation path)
2. GET /calendar/time-allocation
3. Snapshot writer (_create_snapshots_for_week)
4. Past-week report from snapshots

All tests use real test PostgreSQL. Google Calendar API is mocked.

Test event setup for overlap tests:
- P1 15:00-17:00 (2h, but 30min overlap with P2)
- P2 16:00-16:30 (30min, fully overlapping with P1)
- Untagged 18:00-19:00 (1h, no overlap)

Expected after overlap fix:
- P1: 1.75h (1.5h exclusive + 0.25h from 50/50 split of 30min overlap)
- P2: 0.25h (0h exclusive + 0.25h from 50/50 split)
- Other: 1.0h
- Total: 3.0h
"""

import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.priority_guardian.db_models import PgPriority
from backend.apps.priority_guardian.services.snapshot_service import (
    _create_snapshots_for_week,
)
from backend.core.models import CoreUser, CoreConnection


# =============================================================================
# Test Event Fixtures
# =============================================================================


def make_overlap_events(week_tuesday: str) -> list[dict]:
    """
    Create test events with known overlap pattern.

    Events are scheduled for the Tuesday of the target week:
    - P1 15:00-17:00 (2h)
    - P2 16:00-16:30 (30min, overlapping P1 by 30min)
    - Untagged 18:00-19:00 (1h)

    Expected allocation after overlap fix:
    - P1: 1.75h
    - P2: 0.25h
    - Other: 1.0h
    - Total: 3.0h
    """
    return [
        {
            "id": "event-p1",
            "summary": "[P1] Deep work",
            "start": {"dateTime": f"{week_tuesday}T15:00:00Z"},
            "end": {"dateTime": f"{week_tuesday}T17:00:00Z"},
            "status": "confirmed",
        },
        {
            "id": "event-p2",
            "summary": "[P2] Quick call",
            "start": {"dateTime": f"{week_tuesday}T16:00:00Z"},
            "end": {"dateTime": f"{week_tuesday}T16:30:00Z"},
            "status": "confirmed",
        },
        {
            "id": "event-other",
            "summary": "Team standup",
            "start": {"dateTime": f"{week_tuesday}T18:00:00Z"},
            "end": {"dateTime": f"{week_tuesday}T19:00:00Z"},
            "status": "confirmed",
        },
    ]


def make_same_priority_overlap_events(week_tuesday: str) -> list[dict]:
    """
    Create test events with same-priority overlap.

    Events:
    - P1 15:00-17:00 (2h)
    - P1 16:00-16:30 (30min, overlapping the first P1 event)

    Expected: P1 = 2.00h (not 2.50h — overlap within same priority is unioned, not double-counted)
    """
    return [
        {
            "id": "event-p1-a",
            "summary": "[P1] Project work",
            "start": {"dateTime": f"{week_tuesday}T15:00:00Z"},
            "end": {"dateTime": f"{week_tuesday}T17:00:00Z"},
            "status": "confirmed",
        },
        {
            "id": "event-p1-b",
            "summary": "[P1] Quick follow-up",
            "start": {"dateTime": f"{week_tuesday}T16:00:00Z"},
            "end": {"dateTime": f"{week_tuesday}T16:30:00Z"},
            "status": "confirmed",
        },
    ]


# =============================================================================
# Test 1: Weekly Report Endpoint (Live Computation)
# =============================================================================


class TestWeeklyReportEndpointOverlap:
    """Test that /weekly-report correctly applies overlap fix."""

    @pytest.mark.asyncio
    async def test_weekly_report_endpoint_overlap_corrected(
        self, client, async_session: AsyncSession
    ):
        """
        GET /weekly-report for current week uses corrected overlap allocation.

        Setup: P1 15-17, P2 16-16:30, untagged 18-19
        Expected: P1=1.75h, P2=0.25h, other=1.0h, total=3.0h
        """
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

        # Create P1 priority (created well before test week)
        priority_p1 = PgPriority(
            user_id=user.id,
            name="P1 Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date(2026, 6, 15),
            created_at=datetime(2025, 12, 1),
        )
        async_session.add(priority_p1)

        # Create P2 priority
        priority_p2 = PgPriority(
            user_id=user.id,
            name="P2 Priority",
            type="flexible",
            calendar_keyword="P2",
            status="active",
            weekly_hour_target=Decimal("5.0"),
            checkpoint_date=date(2026, 6, 15),
            created_at=datetime(2025, 12, 1),
        )
        async_session.add(priority_p2)
        await async_session.commit()

        # Compute current week's Tuesday for event dates
        today = date.today()
        # Find Monday of current week
        monday = today - timedelta(days=today.weekday())
        tuesday = monday + timedelta(days=1)
        tuesday_str = tuesday.isoformat()

        mock_events = make_overlap_events(tuesday_str)

        # Mock at list_events level to exercise the real compute_allocation_from_events algorithm
        # Note: encrypted_access_token is a literal string that won't decrypt correctly,
        # but ensure_valid_access_token is mocked so decryption is never attempted.
        with patch(
            "backend.apps.priority_guardian.services.weekly_report_service.ensure_valid_access_token",
            new_callable=AsyncMock,
            return_value={"access_token": "test_token"},
        ), patch(
            "backend.apps.priority_guardian.services.weekly_report_service.get_user_timezone",
            new_callable=AsyncMock,
            return_value="UTC",
        ), patch(
            "backend.apps.priority_guardian.services.weekly_report_service.list_events",
            new_callable=AsyncMock,
            return_value=(mock_events, 0),
        ):
            response = await client.get(
                "/api/priority-guardian/weekly-report",
                headers={"X-User-ID": str(user.id)},
            )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["data"]["is_current_week"] is True

        # Extract priorities and time_allocation
        priorities = {p["calendar_keyword"]: p for p in data["data"]["priorities"]}
        time_alloc = data["data"]["time_allocation"]

        # Assert corrected overlap values
        assert priorities["P1"]["actual_hours"] == pytest.approx(1.75, abs=0.01)
        assert priorities["P2"]["actual_hours"] == pytest.approx(0.25, abs=0.01)
        assert time_alloc["other_hours"] == pytest.approx(1.0, abs=0.01)
        assert time_alloc["total_tracked_hours"] == pytest.approx(3.0, abs=0.01)


# =============================================================================
# Test 2: Calendar Time Allocation Endpoint
# =============================================================================


class TestCalendarTimeAllocationEndpointOverlap:
    """Test that /calendar/time-allocation correctly applies overlap fix."""

    @pytest.mark.asyncio
    async def test_calendar_time_allocation_endpoint_overlap_corrected(
        self, client, async_session: AsyncSession
    ):
        """
        GET /calendar/time-allocation returns corrected overlap allocation.

        Setup: P1 15-17, P2 16-16:30, untagged 18-19
        Expected: P1=1.75h, P2=0.25h, other=1.0h, total=3.0h
        Also: bar_segments mirrors keywords + other
        """
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

        # Create P1 and P2 priorities
        priority_p1 = PgPriority(
            user_id=user.id,
            name="P1 Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date(2026, 6, 15),
            created_at=datetime(2025, 12, 1),
        )
        async_session.add(priority_p1)

        priority_p2 = PgPriority(
            user_id=user.id,
            name="P2 Priority",
            type="flexible",
            calendar_keyword="P2",
            status="active",
            weekly_hour_target=Decimal("5.0"),
            checkpoint_date=date(2026, 6, 15),
            created_at=datetime(2025, 12, 1),
        )
        async_session.add(priority_p2)
        await async_session.commit()

        # Compute current week's Tuesday
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        tuesday = monday + timedelta(days=1)
        tuesday_str = tuesday.isoformat()

        mock_events = make_overlap_events(tuesday_str)

        # Mock at list_events level to exercise the real compute_allocation_from_events algorithm
        # Note: encrypted_access_token is a literal string that won't decrypt correctly,
        # but ensure_valid_access_token is mocked so decryption is never attempted.
        with patch(
            "backend.apps.priority_guardian.services.calendar_service.ensure_valid_access_token",
            new_callable=AsyncMock,
            return_value={"access_token": "test_token"},
        ), patch(
            "backend.apps.priority_guardian.services.calendar_service.get_user_timezone",
            new_callable=AsyncMock,
            return_value="UTC",
        ), patch(
            "backend.apps.priority_guardian.services.calendar_service.list_events",
            new_callable=AsyncMock,
            return_value=(mock_events, 0),
        ):
            response = await client.get(
                "/api/priority-guardian/calendar/time-allocation",
                headers={"X-User-ID": str(user.id)},
            )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True

        # Assert corrected values
        assert data["data"]["keywords"]["P1"]["hours"] == pytest.approx(1.75, abs=0.01)
        assert data["data"]["keywords"]["P2"]["hours"] == pytest.approx(0.25, abs=0.01)
        assert data["data"]["other_hours"] == pytest.approx(1.0, abs=0.01)
        assert data["data"]["total_tracked_hours"] == pytest.approx(3.0, abs=0.01)

        # Assert bar_segments mirrors keywords + other (per part 1 invariant 13)
        assert data["data"]["bar_segments"]["P1"] == pytest.approx(1.75, abs=0.01)
        assert data["data"]["bar_segments"]["P2"] == pytest.approx(0.25, abs=0.01)
        assert data["data"]["bar_segments"]["other"] == pytest.approx(1.0, abs=0.01)

        # Regression guard: overlap_segment_count is internal telemetry and must not
        # be exposed in the public response. The router (calendar_router.py) strips
        # this field before returning. If this assertion fails, someone removed the
        # strip — restore it before merging.
        assert "overlap_segment_count" not in data["data"]


# =============================================================================
# Test 3: Snapshot Writer Persists Corrected Hours
# =============================================================================


class TestSnapshotWriterOverlap:
    """Test that snapshot creation uses corrected overlap allocation."""

    @pytest.mark.asyncio
    async def test_snapshot_writer_persists_corrected_hours(
        self, async_session: AsyncSession
    ):
        """
        Snapshot writer persists corrected hours for same-priority overlap.

        Setup: P1 15-17, P1 16-16:30 (same-priority overlap)
        Expected: actual_hours = 2.00 (not 2.50)

        Note: overlap_segment_count telemetry is returned by compute_allocation_from_events
        but only logged in compute_time_allocation. Endpoint tests (1, 2, 5) exercise
        the logging path; this test verifies the algorithm correctness at the DB layer.
        """
        # Create user
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Create P1 priority (created well before test week)
        priority = PgPriority(
            user_id=user.id,
            name="P1 Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date(2026, 3, 15),
            created_at=datetime(2025, 12, 1),
        )
        async_session.add(priority)
        await async_session.commit()

        # Past week: Jan 5, 2026 (Monday)
        past_week_start = date(2026, 1, 5)
        past_tuesday = "2026-01-06"

        mock_events = make_same_priority_overlap_events(past_tuesday)

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
                week_start=past_week_start,
                timezone_str="UTC",
                priorities=[priority],
                access_token="test_token",
                session=async_session,
                http_client=mock_http_client,
                log=log,
            )

        assert result is True

        # Query the snapshot
        snap_result = await async_session.execute(
            text("""
                SELECT actual_hours, other_hours, total_tracked_hours
                FROM pg_weekly_snapshots
                WHERE priority_id = :pid AND week_start = :ws
            """),
            {"pid": priority.id, "ws": past_week_start},
        )
        row = snap_result.fetchone()

        assert row is not None
        # Same-priority overlap: 2h total (not 2.5h)
        assert row[0] == Decimal("2.00"), f"Expected 2.00, got {row[0]}"
        assert row[1] == Decimal("0.00"), f"Expected 0.00 other_hours, got {row[1]}"
        assert row[2] == Decimal("2.00"), f"Expected 2.00 total, got {row[2]}"


# =============================================================================
# Test 4: Snapshot-Based Past Week Report
# =============================================================================


class TestSnapshotBasedReportOverlap:
    """Test that past-week reports built from snapshots use corrected values."""

    @pytest.mark.asyncio
    async def test_snapshot_based_past_week_report_uses_corrected_persisted_hours(
        self, client, async_session: AsyncSession
    ):
        """
        Past-week report uses corrected hours from snapshot data.

        Verifies that GET /weekly-report?week_start=<past_monday> returns the
        snapshot path (snapshot_saved=true) and surfaces the persisted corrected
        hours. The snapshot row is inserted directly via raw SQL to keep this test
        independent of snapshot-creation logic (which is covered separately by
        test_snapshot_writer_persists_corrected_hours).
        """
        # Create user
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Create Google connection (needed for the endpoint)
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

        # Create P1 priority
        priority = PgPriority(
            user_id=user.id,
            name="P1 Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date(2026, 3, 15),
            created_at=datetime(2025, 12, 1),
        )
        async_session.add(priority)
        await async_session.flush()

        # Insert snapshot with corrected hours directly
        past_week_start = date(2026, 1, 5)
        past_week_end = date(2026, 1, 11)

        await async_session.execute(
            text("""
                INSERT INTO pg_weekly_snapshots
                (id, priority_id, user_id, week_start, week_end, actual_hours, target_hours,
                 streak_at_snapshot, calendar_keyword_at_snapshot, other_hours, total_tracked_hours)
                VALUES
                (gen_random_uuid(), :pid, :uid, :ws, :we, 2.00, 10.00, 1, 'P1', 0.00, 2.00)
            """),
            {
                "pid": priority.id,
                "uid": user.id,
                "ws": past_week_start,
                "we": past_week_end,
            },
        )
        await async_session.commit()

        # Mock token validation (needed for endpoint auth)
        with patch(
            "backend.apps.priority_guardian.services.weekly_report_service.ensure_valid_access_token",
            new_callable=AsyncMock,
            return_value={"access_token": "test_token"},
        ), patch(
            "backend.apps.priority_guardian.services.weekly_report_service.get_user_timezone",
            new_callable=AsyncMock,
            return_value="UTC",
        ):
            response = await client.get(
                f"/api/priority-guardian/weekly-report?week_start={past_week_start}",
                headers={"X-User-ID": str(user.id)},
            )

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["data"]["snapshot_saved"] is True

        # Find P1 priority in response
        p1_data = next(
            (p for p in data["data"]["priorities"] if p["calendar_keyword"] == "P1"),
            None,
        )
        assert p1_data is not None
        assert p1_data["actual_hours"] == pytest.approx(2.0, abs=0.01)


# =============================================================================
# Test 5: Two Endpoints Agree on Same Calendar
# =============================================================================


class TestEndpointAgreement:
    """Test that endpoints produce consistent results from same calendar data."""

    @pytest.mark.asyncio
    async def test_two_endpoints_agree_on_same_calendar(
        self, client, async_session: AsyncSession
    ):
        """
        Both /weekly-report and /calendar/time-allocation produce matching values.

        This test verifies endpoint-level cross-consumer agreement.
        """
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

        # Create P1 and P2 priorities
        priority_p1 = PgPriority(
            user_id=user.id,
            name="P1 Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date(2026, 6, 15),
            created_at=datetime(2025, 12, 1),
        )
        async_session.add(priority_p1)

        priority_p2 = PgPriority(
            user_id=user.id,
            name="P2 Priority",
            type="flexible",
            calendar_keyword="P2",
            status="active",
            weekly_hour_target=Decimal("5.0"),
            checkpoint_date=date(2026, 6, 15),
            created_at=datetime(2025, 12, 1),
        )
        async_session.add(priority_p2)
        await async_session.commit()

        # Compute current week's Tuesday
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        tuesday = monday + timedelta(days=1)
        tuesday_str = tuesday.isoformat()

        mock_events = make_overlap_events(tuesday_str)

        # Call weekly-report endpoint
        with patch(
            "backend.apps.priority_guardian.services.weekly_report_service.ensure_valid_access_token",
            new_callable=AsyncMock,
            return_value={"access_token": "test_token"},
        ), patch(
            "backend.apps.priority_guardian.services.weekly_report_service.get_user_timezone",
            new_callable=AsyncMock,
            return_value="UTC",
        ), patch(
            "backend.apps.priority_guardian.services.weekly_report_service.list_events",
            new_callable=AsyncMock,
            return_value=(mock_events, 0),
        ):
            weekly_response = await client.get(
                "/api/priority-guardian/weekly-report",
                headers={"X-User-ID": str(user.id)},
            )

        assert weekly_response.status_code == 200
        weekly_data = weekly_response.json()

        # Call calendar/time-allocation endpoint
        with patch(
            "backend.apps.priority_guardian.services.calendar_service.ensure_valid_access_token",
            new_callable=AsyncMock,
            return_value={"access_token": "test_token"},
        ), patch(
            "backend.apps.priority_guardian.services.calendar_service.get_user_timezone",
            new_callable=AsyncMock,
            return_value="UTC",
        ), patch(
            "backend.apps.priority_guardian.services.calendar_service.list_events",
            new_callable=AsyncMock,
            return_value=(mock_events, 0),
        ):
            calendar_response = await client.get(
                "/api/priority-guardian/calendar/time-allocation",
                headers={"X-User-ID": str(user.id)},
            )

        assert calendar_response.status_code == 200
        calendar_data = calendar_response.json()

        # Extract comparable values
        weekly_total = weekly_data["data"]["time_allocation"]["total_tracked_hours"]
        calendar_total = calendar_data["data"]["total_tracked_hours"]

        weekly_p1 = weekly_data["data"]["time_allocation"]["keywords"]["P1"]["hours"]
        calendar_p1 = calendar_data["data"]["keywords"]["P1"]["hours"]

        weekly_p2 = weekly_data["data"]["time_allocation"]["keywords"]["P2"]["hours"]
        calendar_p2 = calendar_data["data"]["keywords"]["P2"]["hours"]

        weekly_other = weekly_data["data"]["time_allocation"]["other_hours"]
        calendar_other = calendar_data["data"]["other_hours"]

        # Assert agreement
        assert weekly_total == pytest.approx(calendar_total, abs=0.01)
        assert weekly_p1 == pytest.approx(calendar_p1, abs=0.01)
        assert weekly_p2 == pytest.approx(calendar_p2, abs=0.01)
        assert weekly_other == pytest.approx(calendar_other, abs=0.01)
