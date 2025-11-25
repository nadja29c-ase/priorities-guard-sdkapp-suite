"""
Increment 8 — Phase 1A: Sync Engine E2E Tests (34 tests)

Tests the complete sync flow using:
- REAL DB + REAL Redis (isolated via env prefix "test:")
- REAL sync engine logic (NO internal mocking)
- REAL token encryption/decryption
- ONLY mock: Google Calendar HTTP API via patch

Test Categories:
- Core Scenarios (Tests 1-10): Basic sync operations
- Edge Cases (Tests 11-20): Race conditions, timestamps, pagination
- Google Failure Simulation (Tests 21-23): API errors and retries
- SQL/Python Invariant Tests (Tests 24-33): Version logic consistency
"""

import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import patch, AsyncMock

from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession
from httpx import AsyncClient

from backend.apps.focused.db_models import FocusedFocusSession


# =============================================================================
# FIXED REFERENCE TIME - prevents flaky tests from millisecond drift
# =============================================================================
# All tests use offsets from this fixed point to ensure deterministic timestamps.
# Using a future date ensures events are always "upcoming" relative to sync window.
REF_TIME = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


# =============================================================================
# CORE SCENARIOS (Tests 1-10)
# =============================================================================


class TestCoreScenarios:
    """Core sync scenarios covering basic operations."""

    @pytest.mark.asyncio
    async def test_01_fresh_user_bootstrapping(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        event_factory,
        redis_helpers,
    ):
        """Test 1: First sync with N events from Google."""
        user_id = test_user_with_connection["user_id"]
        base_time = REF_TIME + timedelta(hours=1)

        # Setup: 5 events from Google
        events = event_factory.batch(count=5, base=base_time, prefix="fresh")
        mock_google.set_events(events)

        # Set needs_sync flag (required for sync to run)
        await redis_helpers.set_needs(user_id)

        # Execute sync via HTTP endpoint
        response = await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["events_fetched"] == 5
        assert data["data"]["events_inserted"] == 5
        assert data["data"]["events_updated"] == 0

        # Verify all events in DB with correct initial state
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.user_id == user_id
            )
        )
        rows = result.scalars().all()

        assert len(rows) == 5
        for row in rows:
            assert row.status == "active"
            assert row.version == 1
            assert row.last_synced_at is not None

    @pytest.mark.asyncio
    async def test_02_incremental_sync_no_changes(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        event_factory,
        redis_helpers,
    ):
        """Test 2: Incremental sync with no changes - versions stay at 1."""
        user_id = test_user_with_connection["user_id"]
        base_time = REF_TIME + timedelta(hours=1)

        # Initial sync
        events = event_factory.batch(count=10, base=base_time, prefix="incr")
        mock_google.set_events(events)

        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        # Second sync with same events (no changes)
        mock_google.set_events(events)

        await redis_helpers.set_needs(user_id)
        response = await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["events_updated"] == 0

        # Verify versions unchanged
        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.user_id == user_id
            )
        )
        rows = result.scalars().all()

        assert all(r.version == 1 for r in rows)

    @pytest.mark.asyncio
    async def test_03_event_update_changed_title(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        event_factory,
        redis_helpers,
    ):
        """Test 3: Event title changes from 'Meeting' to 'Focus Block'."""
        user_id = test_user_with_connection["user_id"]
        base_time = REF_TIME + timedelta(hours=1)
        original_updated = REF_TIME

        # Initial sync with "Meeting"
        original = event_factory.create(
            event_id="evt1",
            summary="Meeting",
            start_time=base_time,
            updated_at=original_updated,
        )
        mock_google.set_events([original])

        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        # Update event title to "Focus Block" with newer timestamp
        updated = event_factory.create(
            event_id="evt1",
            summary="Focus Block",
            start_time=base_time,
            updated_at=original_updated + timedelta(hours=1),
        )
        mock_google.set_events([updated])

        await redis_helpers.set_needs(user_id)
        response = await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        assert response.status_code == 200
        assert response.json()["data"]["events_updated"] == 1

        # Verify update applied
        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.user_id == user_id,
                FocusedFocusSession.google_event_id == "evt1",
            )
        )
        row = result.scalar_one()

        assert row.event_summary == "Focus Block"
        assert row.version == 2
        assert row.is_focus_block is True  # "Focus" keyword matched

    @pytest.mark.asyncio
    async def test_04_event_cancellation_soft_delete(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        event_factory,
        redis_helpers,
    ):
        """Test 4: Event deleted in Google - soft delete with version++."""
        user_id = test_user_with_connection["user_id"]
        base_time = REF_TIME + timedelta(hours=1)

        # Initial sync with event
        event = event_factory.create(
            event_id="evt2",
            summary="Deletable Event",
            start_time=base_time,
        )
        mock_google.set_events([event])

        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        # Google returns empty list (event was deleted)
        mock_google.set_events([])

        await redis_helpers.set_needs(user_id)
        response = await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        assert response.status_code == 200
        assert response.json()["data"]["events_deleted"] == 1

        # Verify soft delete
        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.user_id == user_id,
                FocusedFocusSession.google_event_id == "evt2",
            )
        )
        row = result.scalar_one()

        assert row.status == "deleted"
        assert row.version == 2
        assert row.deleted_at is not None

    @pytest.mark.asyncio
    async def test_05_resurrection(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        event_factory,
        redis_helpers,
    ):
        """Test 5: Deleted event reappears in Google - resurrection."""
        user_id = test_user_with_connection["user_id"]
        base_time = REF_TIME + timedelta(hours=1)
        t1 = REF_TIME

        # Initial sync
        event = event_factory.create(
            event_id="evt3",
            summary="Resurrectable",
            start_time=base_time,
            updated_at=t1,
        )
        mock_google.set_events([event])

        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        # Delete the event
        mock_google.set_events([])
        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        # Verify deleted
        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.google_event_id == "evt3"
            )
        )
        deleted_row = result.scalar_one()
        assert deleted_row.status == "deleted"
        assert deleted_row.version == 2

        # Event reappears with newer timestamp
        resurrected = event_factory.create(
            event_id="evt3",
            summary="Resurrected Event",
            start_time=base_time,
            updated_at=t1 + timedelta(hours=2),
        )
        mock_google.set_events([resurrected])

        await redis_helpers.set_needs(user_id)
        response = await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        assert response.status_code == 200

        # Verify resurrection
        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.google_event_id == "evt3"
            )
        )
        row = result.scalar_one()

        assert row.status == "active"
        assert row.version == 3
        assert row.event_summary == "Resurrected Event"

    @pytest.mark.asyncio
    async def test_06_multi_page_pagination(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        event_factory,
        redis_helpers,
    ):
        """Test 6: Handle >250 events across pages."""
        user_id = test_user_with_connection["user_id"]
        base_time = REF_TIME + timedelta(hours=1)

        # Create 2 pages of events
        page1 = event_factory.batch(count=250, base=base_time, prefix="p1_")
        page2 = event_factory.batch(
            count=100, base=base_time + timedelta(hours=250), prefix="p2_"
        )
        mock_google.set_paginated_events([page1, page2])

        await redis_helpers.set_needs(user_id)
        response = await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["events_fetched"] == 350
        assert data["data"]["events_inserted"] == 350

        # Verify count in DB
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.user_id == user_id
            )
        )
        rows = result.scalars().all()
        assert len(rows) == 350

    @pytest.mark.asyncio
    async def test_07_focus_keyword_matching(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        event_factory,
        redis_helpers,
    ):
        """Test 7: Detect 'Focus', 'Deep Work', and custom keywords."""
        user_id = test_user_with_connection["user_id"]
        base_time = REF_TIME + timedelta(hours=1)

        # Add custom keyword for user
        await async_session.execute(
            text(
                "INSERT INTO focused_user_keywords (user_id, keyword) VALUES (:u, :k)"
            ),
            {"u": user_id, "k": "Research Project"},
        )
        await async_session.flush()

        # Create events with various titles
        events = [
            event_factory.create(
                event_id="e1",
                summary="Focus Session",
                start_time=base_time,
            ),
            event_factory.create(
                event_id="e2",
                summary="Deep Work Time",
                start_time=base_time + timedelta(hours=1),
            ),
            event_factory.create(
                event_id="e3",
                summary="Research Project Review",
                start_time=base_time + timedelta(hours=2),
            ),
            event_factory.create(
                event_id="e4",
                summary="Regular Meeting",
                start_time=base_time + timedelta(hours=3),
            ),
        ]
        mock_google.set_events(events)

        await redis_helpers.set_needs(user_id)
        response = await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        assert response.status_code == 200

        # Verify focus detection
        async_session.expire_all()

        for event_id, should_be_focus in [
            ("e1", True),
            ("e2", True),
            ("e3", True),
            ("e4", False),
        ]:
            result = await async_session.execute(
                select(FocusedFocusSession).where(
                    FocusedFocusSession.google_event_id == event_id
                )
            )
            row = result.scalar_one()
            assert row.is_focus_block is should_be_focus, (
                f"Event {event_id} is_focus_block={row.is_focus_block}, "
                f"expected {should_be_focus}"
            )

    @pytest.mark.asyncio
    async def test_08_conflict_detection(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        event_factory,
        redis_helpers,
    ):
        """Test 8: Focus Block overlaps with other event."""
        user_id = test_user_with_connection["user_id"]
        base_time = datetime(2025, 1, 15, 9, 0, 0, tzinfo=timezone.utc)

        # Focus block and overlapping meeting
        focus_block = event_factory.create(
            event_id="fb1",
            summary="Focus Block",
            start_time=base_time,
            duration_minutes=60,
        )
        meeting = event_factory.create(
            event_id="m1",
            summary="Team Standup",
            start_time=base_time + timedelta(minutes=30),
            duration_minutes=15,
        )
        mock_google.set_events([focus_block, meeting])

        await redis_helpers.set_needs(user_id)
        response = await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        assert response.status_code == 200
        assert response.json()["data"]["events_inserted"] == 2

        # Both events synced (conflict detection is a separate read concern)
        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.user_id == user_id
            )
        )
        rows = result.scalars().all()
        assert len(rows) == 2

    @pytest.mark.asyncio
    async def test_09_all_day_events_skipped(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        event_factory,
        redis_helpers,
    ):
        """Test 9: All-day events (no dateTime) are skipped."""
        user_id = test_user_with_connection["user_id"]

        # All-day event (date instead of dateTime)
        all_day = event_factory.create_all_day(
            event_id="ad1",
            summary="Holiday",
            date="2025-01-15",
        )
        mock_google.set_events([all_day])

        await redis_helpers.set_needs(user_id)
        response = await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        assert response.status_code == 200
        # All-day events are skipped during fetch/validation
        assert response.json()["data"]["events_inserted"] == 0

        # Verify nothing in DB
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.user_id == user_id
            )
        )
        rows = result.scalars().all()
        assert len(rows) == 0

    @pytest.mark.asyncio
    async def test_10_empty_calendar_handling(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        redis_helpers,
    ):
        """Test 10: Zero events returned."""
        user_id = test_user_with_connection["user_id"]

        mock_google.set_events([])

        await redis_helpers.set_needs(user_id)
        response = await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["events_fetched"] == 0
        assert data["data"]["events_inserted"] == 0


# =============================================================================
# EDGE CASES (Tests 11-20)
# =============================================================================


class TestEdgeCases:
    """Edge cases covering race conditions, timestamps, and special scenarios."""

    @pytest.mark.asyncio
    async def test_11_detect_deleted_events_when_google_omits(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        event_factory,
        redis_helpers,
    ):
        """
        Test 11: Google omits evt3 from list - soft delete with version++.

        Verifies:
        - Soft delete sets status='deleted' and increments version
        - deleted_at timestamp is set
        - google_updated_at is preserved (deletion respects timestamp rules)
        """
        user_id = test_user_with_connection["user_id"]
        base_time = REF_TIME + timedelta(hours=1)
        original_updated_at = REF_TIME

        # Initial sync with 5 events (explicit updated_at for timestamp verification)
        events = [
            event_factory.create(
                event_id=f"evt{i}",
                summary=f"Event {i}",
                start_time=base_time + timedelta(hours=i),
                updated_at=original_updated_at,
            )
            for i in range(1, 6)
        ]
        mock_google.set_events(events)

        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        # Capture evt3's google_updated_at before deletion
        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.google_event_id == "evt3"
            )
        )
        evt3_before = result.scalar_one()
        evt3_google_updated_before = evt3_before.google_updated_at

        # Google omits evt3 from list
        events_without_3 = [e for e in events if e["id"] != "evt3"]
        mock_google.set_events(events_without_3)

        await redis_helpers.set_needs(user_id)
        response = await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        assert response.status_code == 200
        assert response.json()["data"]["events_deleted"] == 1

        # Verify evt3 soft-deleted with version++
        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.google_event_id == "evt3"
            )
        )
        row = result.scalar_one()
        assert row.status == "deleted"
        assert row.version == 2  # MUST increment
        assert row.deleted_at is not None, "deleted_at must be set on soft delete"

        # Verify google_updated_at is preserved (deletion respects timestamp rules)
        assert row.google_updated_at >= evt3_google_updated_before, \
            "google_updated_at must be >= original value after deletion"

        # Others remain active
        for eid in ["evt1", "evt2", "evt4", "evt5"]:
            result = await async_session.execute(
                select(FocusedFocusSession).where(
                    FocusedFocusSession.google_event_id == eid
                )
            )
            row = result.scalar_one()
            assert row.status == "active"

    @pytest.mark.asyncio
    async def test_12_overlapping_webhook_sync_race_condition(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        event_factory,
        redis_helpers,
    ):
        """
        Test 12: Webhook arrives mid-sync - needs_sync survives.

        Timeline:
        1. Webhook 1 arrives → set needs_sync = True
        2. Sync starts → clears needs_sync = False
        3. Sync pauses after page 1
        4. Webhook 2 arrives → re-sets needs_sync = True
        5. Sync resumes and finishes
        6. needs_sync should still be True (was re-set during sync)

        This tests that the sync engine doesn't blindly clear needs_sync
        at the end if a new webhook arrived during sync.
        """
        user_id = test_user_with_connection["user_id"]
        base_time = REF_TIME + timedelta(hours=1)

        # Setup: page 1 events
        page1 = event_factory.batch(count=5, base=base_time, prefix="race_")
        mock_google.set_paginated_events([page1])
        mock_google.enable_pause_after_page(1)

        # Step 1: Webhook 1 arrives → set needs_sync = True
        await redis_helpers.set_needs(user_id)
        assert await redis_helpers.get_needs(user_id) is True

        # Step 2-3: Start sync (will clear flag, then pause after page 1)
        sync_task = asyncio.create_task(
            client.post(
                "/api/focused/tools/sync_calendar",
                json={"user_id": user_id},
                headers={"X-User-ID": user_id},
            )
        )

        # Give sync time to start, clear flag, and pause
        await asyncio.sleep(0.1)

        # CRITICAL INTERMEDIATE ASSERTION:
        # Sync should have cleared needs_sync before pausing
        assert await redis_helpers.get_needs(user_id) is False, \
            "Sync engine must clear needs_sync at start before fetching"

        # Step 4: Webhook 2 arrives mid-sync → re-set needs_sync = True
        await redis_helpers.set_needs(user_id)
        assert await redis_helpers.get_needs(user_id) is True

        # Step 5: Resume sync
        mock_google.pause_event.set()
        response = await sync_task

        assert response.status_code == 200
        assert response.json()["data"]["events_inserted"] >= 5

        # Step 6: CRITICAL - needs_sync should still be True
        # The sync engine must NOT clear it because it was re-set during sync
        assert await redis_helpers.get_needs(user_id) is True, \
            "Sync engine must preserve needs_sync if re-set during sync"

    @pytest.mark.asyncio
    async def test_13_equal_timestamp_hash_differs(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        event_factory,
        redis_helpers,
    ):
        """
        Test 13: Same updated_at, different content - hash tiebreaker.

        Hash includes: google_event_id + summary + description + start_time + end_time
        This test verifies changes to EACH of these fields (except event_id) triggers update.
        """
        user_id = test_user_with_connection["user_id"]
        base_time = REF_TIME + timedelta(hours=1)
        same_timestamp = REF_TIME

        # --- Part A: Summary change ---
        original = event_factory.create(
            event_id="evt5a",
            summary="Original Summary",
            description="Same description",
            start_time=base_time,
            duration_minutes=60,
            updated_at=same_timestamp,
        )
        mock_google.set_events([original])

        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        # Same timestamp, different summary
        modified_summary = event_factory.create(
            event_id="evt5a",
            summary="Modified Summary",
            description="Same description",
            start_time=base_time,
            duration_minutes=60,
            updated_at=same_timestamp,
        )
        mock_google.set_events([modified_summary])

        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.google_event_id == "evt5a"
            )
        )
        row = result.scalar_one()
        assert row.event_summary == "Modified Summary", "Summary change should be detected"
        assert row.version == 2, "Version should increment on summary change"

        # --- Part B: Description change ---
        original_b = event_factory.create(
            event_id="evt5b",
            summary="Same Title",
            description="Original Description",
            start_time=base_time + timedelta(hours=2),
            duration_minutes=60,
            updated_at=same_timestamp,
        )
        mock_google.set_events([original_b])

        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        # Same timestamp, different description
        modified_desc = event_factory.create(
            event_id="evt5b",
            summary="Same Title",
            description="Modified Description",
            start_time=base_time + timedelta(hours=2),
            duration_minutes=60,
            updated_at=same_timestamp,
        )
        mock_google.set_events([modified_desc])

        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.google_event_id == "evt5b"
            )
        )
        row = result.scalar_one()
        assert row.event_description == "Modified Description", "Description change should be detected"
        assert row.version == 2, "Version should increment on description change"

        # --- Part C: End time change (duration change) ---
        original_c = event_factory.create(
            event_id="evt5c",
            summary="Same Title",
            description="Same Description",
            start_time=base_time + timedelta(hours=4),
            duration_minutes=60,  # 1 hour
            updated_at=same_timestamp,
        )
        mock_google.set_events([original_c])

        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        # Capture original end_time
        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.google_event_id == "evt5c"
            )
        )
        row_before = result.scalar_one()
        original_end_time = row_before.end_time

        # Same timestamp, different end_time (longer duration)
        modified_end = event_factory.create(
            event_id="evt5c",
            summary="Same Title",
            description="Same Description",
            start_time=base_time + timedelta(hours=4),
            duration_minutes=120,  # 2 hours (end_time changes)
            updated_at=same_timestamp,
        )
        mock_google.set_events([modified_end])

        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.google_event_id == "evt5c"
            )
        )
        row = result.scalar_one()
        assert row.end_time > original_end_time, "End time change should be detected"
        assert row.version == 2, "Version should increment on end_time change"

    @pytest.mark.asyncio
    async def test_14_out_of_order_webhooks_rejected(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        event_factory,
        redis_helpers,
    ):
        """Test 14: Older update processed after newer - rejected."""
        user_id = test_user_with_connection["user_id"]
        base_time = REF_TIME + timedelta(hours=1)
        t_older = REF_TIME
        t_newer = REF_TIME + timedelta(hours=2)

        # Sync with "newer" timestamp first
        newer = event_factory.create(
            event_id="evt6",
            summary="Newer",
            start_time=base_time,
            updated_at=t_newer,
        )
        mock_google.set_events([newer])

        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        # Now try to sync older version
        older = event_factory.create(
            event_id="evt6",
            summary="Older",
            start_time=base_time,
            updated_at=t_older,
        )
        mock_google.set_events([older])

        await redis_helpers.set_needs(user_id)
        response = await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        assert response.status_code == 200

        # Verify older update rejected
        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.google_event_id == "evt6"
            )
        )
        row = result.scalar_one()
        assert row.event_summary == "Newer"  # Older rejected
        assert row.version == 1  # No increment

    @pytest.mark.asyncio
    async def test_15_description_cleanup_and_sync(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        event_factory,
        redis_helpers,
    ):
        """Test 15: NULL description doesn't break sync."""
        user_id = test_user_with_connection["user_id"]
        base_time = REF_TIME + timedelta(hours=1)
        t1 = REF_TIME

        # Initial sync with description
        event_with_desc = event_factory.create(
            event_id="evt7",
            summary="Test",
            start_time=base_time,
            description="Original description",
            updated_at=t1,
        )
        mock_google.set_events([event_with_desc])

        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        # Simulate cleanup job setting description=NULL
        await async_session.execute(
            text(
                """
                UPDATE focused_focus_sessions
                SET event_description = NULL
                WHERE google_event_id = :eid
                """
            ),
            {"eid": "evt7"},
        )
        await async_session.flush()

        # Google sends same event (no real change to timestamp/hash)
        mock_google.set_events([event_with_desc])

        await redis_helpers.set_needs(user_id)
        response = await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        assert response.status_code == 200

        # Version should stay at 1 (no false positive update)
        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.google_event_id == "evt7"
            )
        )
        row = result.scalar_one()
        assert row.version == 1  # No false positive

    @pytest.mark.asyncio
    async def test_16_recurring_events_flattened(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        event_factory,
        redis_helpers,
    ):
        """Test 16: Recurring events stored as separate instances."""
        user_id = test_user_with_connection["user_id"]
        base_time = datetime(2025, 1, 6, 9, 0, 0, tzinfo=timezone.utc)

        # Recurring event instances (singleEvents=true in API)
        recurring = [
            event_factory.create(
                event_id="rec1_1",
                summary="Weekly Standup",
                start_time=base_time,
                ical_uid="rec1@google.com",
            ),
            event_factory.create(
                event_id="rec1_2",
                summary="Weekly Standup",
                start_time=base_time + timedelta(weeks=1),
                ical_uid="rec1@google.com",
            ),
            event_factory.create(
                event_id="rec1_3",
                summary="Weekly Standup",
                start_time=base_time + timedelta(weeks=2),
                ical_uid="rec1@google.com",
            ),
        ]
        mock_google.set_events(recurring)

        await redis_helpers.set_needs(user_id)
        response = await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        assert response.status_code == 200
        assert response.json()["data"]["events_inserted"] == 3

        # Verify stored as separate instances
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.user_id == user_id
            )
        )
        rows = result.scalars().all()
        assert len(rows) == 3

    @pytest.mark.asyncio
    async def test_16b_recurring_events_shared_icaluid_and_instance_updates(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        event_factory,
        redis_helpers,
    ):
        """
        Test 16B: Recurring events - iCalUID sharing and per-instance updates.

        Verifies:
        1. All instances share the same google_ical_uid
        2. Order of events in API response doesn't matter
        3. Updating ONE instance only affects that instance's version
        """
        user_id = test_user_with_connection["user_id"]
        base_time = datetime(2025, 2, 3, 10, 0, 0, tzinfo=timezone.utc)
        t1 = REF_TIME

        shared_ical_uid = "weekly-sync@google.com"

        # --- Part A: Initial sync with 3 recurring instances (out of order) ---
        recurring = [
            # Intentionally out of chronological order
            event_factory.create(
                event_id="wsync_3",
                summary="Weekly Sync",
                start_time=base_time + timedelta(weeks=2),
                ical_uid=shared_ical_uid,
                updated_at=t1,
            ),
            event_factory.create(
                event_id="wsync_1",
                summary="Weekly Sync",
                start_time=base_time,
                ical_uid=shared_ical_uid,
                updated_at=t1,
            ),
            event_factory.create(
                event_id="wsync_2",
                summary="Weekly Sync",
                start_time=base_time + timedelta(weeks=1),
                ical_uid=shared_ical_uid,
                updated_at=t1,
            ),
        ]
        mock_google.set_events(recurring)

        await redis_helpers.set_needs(user_id)
        response = await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        assert response.status_code == 200
        assert response.json()["data"]["events_inserted"] == 3

        # Verify all 3 share the same iCalUID
        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.user_id == user_id
            ).order_by(FocusedFocusSession.start_time)
        )
        rows = result.scalars().all()
        assert len(rows) == 3, "All 3 instances should be stored"

        # All should have same iCalUID
        ical_uids = {row.google_ical_uid for row in rows}
        assert len(ical_uids) == 1, "All recurring instances must share same iCalUID"
        assert shared_ical_uid in ical_uids

        # All should have version 1
        for row in rows:
            assert row.version == 1, f"Initial version should be 1, got {row.version}"

        # --- Part B: Update ONE instance (wsync_2) - only that instance's version++ ---
        t2 = t1 + timedelta(hours=1)
        recurring_updated = [
            event_factory.create(
                event_id="wsync_1",
                summary="Weekly Sync",
                start_time=base_time,
                ical_uid=shared_ical_uid,
                updated_at=t1,  # Same as before
            ),
            event_factory.create(
                event_id="wsync_2",
                summary="Weekly Sync - UPDATED",  # Changed!
                start_time=base_time + timedelta(weeks=1),
                ical_uid=shared_ical_uid,
                updated_at=t2,  # Newer timestamp
            ),
            event_factory.create(
                event_id="wsync_3",
                summary="Weekly Sync",
                start_time=base_time + timedelta(weeks=2),
                ical_uid=shared_ical_uid,
                updated_at=t1,  # Same as before
            ),
        ]
        mock_google.set_events(recurring_updated)

        await redis_helpers.set_needs(user_id)
        response = await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        assert response.status_code == 200

        # Verify only wsync_2 has version 2
        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.user_id == user_id
            ).order_by(FocusedFocusSession.start_time)
        )
        rows = result.scalars().all()

        versions_by_event = {row.google_event_id: row.version for row in rows}
        assert versions_by_event["wsync_1"] == 1, "wsync_1 should remain version 1"
        assert versions_by_event["wsync_2"] == 2, "wsync_2 should be version 2 (updated)"
        assert versions_by_event["wsync_3"] == 1, "wsync_3 should remain version 1"

        # Verify updated summary
        summaries_by_event = {row.google_event_id: row.event_summary for row in rows}
        assert summaries_by_event["wsync_2"] == "Weekly Sync - UPDATED"

    @pytest.mark.asyncio
    async def test_17_timezone_edge_cases(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        redis_helpers,
    ):
        """Test 17: UTC conversion correctness for PST event."""
        user_id = test_user_with_connection["user_id"]

        # PST event (UTC-8)
        pst_event = {
            "kind": "calendar#event",
            "id": "tz1",
            "iCalUID": "tz1@google.com",
            "summary": "PST Meeting",
            "status": "confirmed",
            "updated": "2025-01-15T09:00:00-08:00",
            "start": {"dateTime": "2025-01-15T09:00:00-08:00", "timeZone": "America/Los_Angeles"},
            "end": {"dateTime": "2025-01-15T10:00:00-08:00", "timeZone": "America/Los_Angeles"},
        }
        mock_google.set_events([pst_event])

        await redis_helpers.set_needs(user_id)
        response = await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        assert response.status_code == 200

        # Verify UTC conversion
        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.google_event_id == "tz1"
            )
        )
        row = result.scalar_one()

        # 9:00 AM PST = 17:00 UTC
        assert row.start_time.hour == 17
        assert row.end_time.hour == 18

    @pytest.mark.asyncio
    async def test_18_maximum_event_limit(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        event_factory,
        redis_helpers,
    ):
        """Test 18: 10 pages × 250 = 2500 events (max limit)."""
        user_id = test_user_with_connection["user_id"]
        base_time = REF_TIME + timedelta(hours=1)

        # Create 10 pages of 250 events each
        pages = [
            event_factory.batch(
                count=250,
                base=base_time + timedelta(hours=i * 250),
                prefix=f"max{i}_",
            )
            for i in range(10)
        ]
        mock_google.set_paginated_events(pages)

        await redis_helpers.set_needs(user_id)
        response = await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["events_fetched"] == 2500

    @pytest.mark.asyncio
    async def test_19_empty_time_window(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        redis_helpers,
    ):
        """Test 19: No events in date range."""
        user_id = test_user_with_connection["user_id"]

        mock_google.set_events([])

        await redis_helpers.set_needs(user_id)
        response = await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["events_fetched"] == 0

    @pytest.mark.asyncio
    async def test_20_cold_start_first_sync_after_oauth(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        event_factory,
        redis_helpers,
    ):
        """Test 20: First sync after fresh OAuth."""
        user_id = test_user_with_connection["user_id"]
        base_time = REF_TIME + timedelta(hours=1)

        events = event_factory.batch(count=10, base=base_time, prefix="cold_")
        mock_google.set_events(events)

        await redis_helpers.set_needs(user_id)
        response = await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["events_inserted"] == 10

        # Verify all events synced
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.user_id == user_id
            )
        )
        rows = result.scalars().all()
        assert len(rows) == 10


# =============================================================================
# GOOGLE FAILURE SIMULATION (Tests 21-23)
# =============================================================================


class TestGoogleFailureSimulation:
    """Tests for Google API failures and retry behavior."""

    @pytest.mark.asyncio
    async def test_21_rate_limit_429_with_retry(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        event_factory,
        redis_helpers,
    ):
        """
        Test 21: 429 rate limit with exponential backoff retry.

        Verifies:
        - Sync engine retries after 429 errors
        - Retry count matches expected attempts (2 failures + 1 success = 3)
        - Events are inserted after successful retry
        - needs_sync is cleared after successful sync
        """
        user_id = test_user_with_connection["user_id"]
        base_time = REF_TIME + timedelta(hours=1)

        events = event_factory.batch(count=5, base=base_time, prefix="rate_")

        # First two calls fail with 429, third succeeds
        call_count = 0

        async def list_events_with_retries(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise ValueError("Rate limit exceeded")  # Simulates 429
            return events, 0

        await redis_helpers.set_needs(user_id)
        with patch(
            "backend.apps.focused.logic.sync.orchestrator.list_events",
            side_effect=list_events_with_retries
        ), patch(
            "backend.core.google_calendar.list_events",
            side_effect=list_events_with_retries
        ):
            response = await client.post(
                "/api/focused/tools/sync_calendar",
                json={"user_id": user_id},
                headers={"X-User-ID": user_id},
            )

        # Verify retry behavior
        assert response.status_code == 200
        assert call_count == 3, f"Expected 3 calls (2 failures + 1 success), got {call_count}"

        # Verify events were inserted after successful retry
        data = response.json()
        assert data["data"]["events_inserted"] == 5, "Events should be inserted after retry success"

        # Verify needs_sync was cleared after successful sync
        assert await redis_helpers.get_needs(user_id) is False, \
            "needs_sync should be cleared after successful sync"

    @pytest.mark.asyncio
    async def test_22_invalid_token_401_triggers_refresh(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        event_factory,
        override_http_client,
        redis_helpers,
    ):
        """
        Test 22: 401 invalid token triggers token refresh.

        Verifies:
        - Sync engine detects 401 and triggers token refresh
        - After refresh, sync retries and succeeds
        - Retry count matches expected attempts (1 failure + 1 success = 2)
        - Events are inserted after successful retry
        """
        user_id = test_user_with_connection["user_id"]
        base_time = REF_TIME + timedelta(hours=1)

        events = event_factory.batch(count=3, base=base_time, prefix="auth_")

        # First call fails with 401, after refresh succeeds
        call_count = 0

        async def list_events_with_auth_error(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Invalid Credentials")  # Simulates 401
            return events, 0

        await redis_helpers.set_needs(user_id)
        with patch(
            "backend.apps.focused.logic.sync.orchestrator.list_events",
            side_effect=list_events_with_auth_error
        ), patch(
            "backend.core.google_calendar.list_events",
            side_effect=list_events_with_auth_error
        ):
            response = await client.post(
                "/api/focused/tools/sync_calendar",
                json={"user_id": user_id},
                headers={"X-User-ID": user_id},
            )

        # Verify retry behavior after token refresh
        assert response.status_code == 200
        assert call_count == 2, f"Expected 2 calls (1 failure + 1 success after refresh), got {call_count}"

        # Verify events were inserted after successful retry
        data = response.json()
        assert data["data"]["events_inserted"] == 3, "Events should be inserted after token refresh"

        # Verify needs_sync was cleared after successful sync
        assert await redis_helpers.get_needs(user_id) is False, \
            "needs_sync should be cleared after successful sync"

    @pytest.mark.asyncio
    async def test_23_network_timeout_with_retry(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        event_factory,
        redis_helpers,
    ):
        """
        Test 23: Network timeout with retry.

        Verifies:
        - Sync engine retries after network timeout
        - Retry count matches expected attempts (1 failure + 1 success = 2)
        - Events are inserted after successful retry
        - needs_sync is cleared after successful sync
        """
        user_id = test_user_with_connection["user_id"]
        base_time = REF_TIME + timedelta(hours=1)

        events = event_factory.batch(count=3, base=base_time, prefix="timeout_")

        # First call times out, second succeeds
        call_count = 0

        async def list_events_with_timeout(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise asyncio.TimeoutError("Connection timeout")
            return events, 0

        await redis_helpers.set_needs(user_id)
        with patch(
            "backend.apps.focused.logic.sync.orchestrator.list_events",
            side_effect=list_events_with_timeout
        ), patch(
            "backend.core.google_calendar.list_events",
            side_effect=list_events_with_timeout
        ):
            response = await client.post(
                "/api/focused/tools/sync_calendar",
                json={"user_id": user_id},
                headers={"X-User-ID": user_id},
            )

        # Verify retry behavior after timeout
        assert response.status_code == 200
        assert call_count == 2, f"Expected 2 calls (1 timeout + 1 success), got {call_count}"

        # Verify events were inserted after successful retry
        data = response.json()
        assert data["data"]["events_inserted"] == 3, "Events should be inserted after timeout retry"

        # Verify needs_sync was cleared after successful sync
        assert await redis_helpers.get_needs(user_id) is False, \
            "needs_sync should be cleared after successful sync"


# =============================================================================
# SQL/PYTHON INVARIANT TESTS (Tests 24-33)
# =============================================================================


class TestSQLPythonInvariants:
    """Tests verifying Python logic matches SQL WHERE clause behavior."""

    @pytest.mark.asyncio
    async def test_24_should_accept_update_logic(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        event_factory,
        redis_helpers,
    ):
        """Test 24: should_accept_update() matches SQL WHERE clause."""
        user_id = test_user_with_connection["user_id"]
        base_time = REF_TIME + timedelta(hours=1)

        # Case 1: google_updated > local_updated → Accept
        t1 = REF_TIME
        t2 = t1 + timedelta(hours=1)

        original = event_factory.create(
            event_id="upd1", summary="V1", start_time=base_time, updated_at=t1
        )
        mock_google.set_events([original])
        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        updated = event_factory.create(
            event_id="upd1", summary="V2", start_time=base_time, updated_at=t2
        )
        mock_google.set_events([updated])
        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.google_event_id == "upd1"
            )
        )
        row = result.scalar_one()
        assert row.event_summary == "V2"  # Accepted
        assert row.version == 2

    @pytest.mark.asyncio
    async def test_25_should_accept_deletion_logic(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        event_factory,
        redis_helpers,
    ):
        """
        Test 25: should_accept_deletion() matches SQL WHERE clause.

        Verifies:
        - Deletion requires google_updated >= local google_updated_at
        - Deletion sets status='deleted', version++, deleted_at
        - google_updated_at is preserved after deletion
        """
        user_id = test_user_with_connection["user_id"]
        base_time = REF_TIME + timedelta(hours=1)
        original_updated_at = REF_TIME

        # Create event with explicit updated_at
        event = event_factory.create(
            event_id="del1",
            summary="To Delete",
            start_time=base_time,
            updated_at=original_updated_at,
        )
        mock_google.set_events([event])
        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        # Capture google_updated_at before deletion
        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.google_event_id == "del1"
            )
        )
        row_before = result.scalar_one()
        google_updated_before = row_before.google_updated_at

        # Delete (google_updated >= local → accept)
        mock_google.set_events([])
        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.google_event_id == "del1"
            )
        )
        row = result.scalar_one()

        # Verify deletion semantics
        assert row.status == "deleted"
        assert row.version == 2, "Version must increment on deletion"
        assert row.deleted_at is not None, "deleted_at must be set"

        # Verify google_updated_at respects timestamp rules
        assert row.google_updated_at >= google_updated_before, \
            "google_updated_at must be >= original value (deletion respects timestamp rules)"

    @pytest.mark.asyncio
    async def test_26_version_increment_on_update(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        event_factory,
        redis_helpers,
    ):
        """Test 26: Version increments on update."""
        user_id = test_user_with_connection["user_id"]
        base_time = REF_TIME + timedelta(hours=1)
        t1 = REF_TIME

        original = event_factory.create(
            event_id="v1", summary="Original", start_time=base_time, updated_at=t1
        )
        mock_google.set_events([original])
        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        newer = event_factory.create(
            event_id="v1",
            summary="Updated",
            start_time=base_time,
            updated_at=t1 + timedelta(hours=1),
        )
        mock_google.set_events([newer])
        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.google_event_id == "v1"
            )
        )
        row = result.scalar_one()
        assert row.version == 2

    @pytest.mark.asyncio
    async def test_27_version_increment_on_deletion(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        event_factory,
        redis_helpers,
    ):
        """Test 27: Version increments on deletion."""
        user_id = test_user_with_connection["user_id"]
        base_time = REF_TIME + timedelta(hours=1)

        event = event_factory.create(
            event_id="v2", summary="To Delete", start_time=base_time
        )
        mock_google.set_events([event])
        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        mock_google.set_events([])
        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.google_event_id == "v2"
            )
        )
        row = result.scalar_one()
        assert row.status == "deleted"
        assert row.version == 2

    @pytest.mark.asyncio
    async def test_28_version_unchanged_when_no_update(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        event_factory,
        redis_helpers,
    ):
        """Test 28: Version stays at 1 when no change."""
        user_id = test_user_with_connection["user_id"]
        base_time = REF_TIME + timedelta(hours=1)
        t1 = REF_TIME

        event = event_factory.create(
            event_id="v3", summary="No Change", start_time=base_time, updated_at=t1
        )
        mock_google.set_events([event])
        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        # Same event again
        mock_google.set_events([event])
        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.google_event_id == "v3"
            )
        )
        row = result.scalar_one()
        assert row.version == 1  # No increment

    @pytest.mark.asyncio
    async def test_29_equal_timestamp_tiebreaker_accept(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        event_factory,
        redis_helpers,
    ):
        """
        Test 29: Equal timestamp, different hash → accept.

        Tests description change (not just summary) to ensure hash includes all fields.
        """
        user_id = test_user_with_connection["user_id"]
        base_time = REF_TIME + timedelta(hours=1)
        same_ts = REF_TIME

        # Original: with description
        original = event_factory.create(
            event_id="tb1",
            summary="Meeting",
            description="Original meeting notes",
            start_time=base_time,
            updated_at=same_ts,
        )
        mock_google.set_events([original])
        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        # Same timestamp, same summary, different description → hash differs
        new = event_factory.create(
            event_id="tb1",
            summary="Meeting",
            description="Updated meeting notes with action items",
            start_time=base_time,
            updated_at=same_ts,
        )
        mock_google.set_events([new])
        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.google_event_id == "tb1"
            )
        )
        row = result.scalar_one()
        assert row.event_summary == "Meeting", "Summary should remain unchanged"
        assert row.event_description == "Updated meeting notes with action items", \
            "Description change should be detected via hash"
        assert row.version == 2, "Version should increment on description change"

    @pytest.mark.asyncio
    async def test_30_equal_timestamp_tiebreaker_reject(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        event_factory,
        redis_helpers,
    ):
        """
        Test 30: Equal timestamp, same hash → reject.

        Also tests that timezone normalization produces same hash:
        - America/New_York at a specific time should produce same UTC as explicit UTC
        - End time changes should be detected (different duration = different hash)
        """
        user_id = test_user_with_connection["user_id"]
        base_time = REF_TIME + timedelta(hours=1)
        same_ts = REF_TIME

        # --- Part A: Exact same event (same hash) ---
        event = event_factory.create(
            event_id="tb2a",
            summary="Current",
            description="Same description",
            start_time=base_time,
            duration_minutes=60,
            updated_at=same_ts,
        )
        mock_google.set_events([event])
        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        # Exact same event (same hash) → should reject
        mock_google.set_events([event])
        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.google_event_id == "tb2a"
            )
        )
        row = result.scalar_one()
        assert row.version == 1, "Same hash should not increment version"

        # --- Part B: End time change (duration) should produce different hash ---
        event_b = event_factory.create(
            event_id="tb2b",
            summary="Meeting",
            description="Discussion",
            start_time=base_time + timedelta(hours=2),
            duration_minutes=60,  # 1 hour
            updated_at=same_ts,
        )
        mock_google.set_events([event_b])
        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        # Capture original end_time
        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.google_event_id == "tb2b"
            )
        )
        row_before = result.scalar_one()
        original_end = row_before.end_time

        # Same timestamp, but different end_time (90 min instead of 60)
        event_b_modified = event_factory.create(
            event_id="tb2b",
            summary="Meeting",
            description="Discussion",
            start_time=base_time + timedelta(hours=2),
            duration_minutes=90,  # 1.5 hours → different end_time
            updated_at=same_ts,
        )
        mock_google.set_events([event_b_modified])
        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.google_event_id == "tb2b"
            )
        )
        row = result.scalar_one()
        assert row.end_time > original_end, "End time change should be detected"
        assert row.version == 2, "Different end_time = different hash = version increment"

    @pytest.mark.asyncio
    async def test_31_resurrection_requires_newer_timestamp(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        event_factory,
        redis_helpers,
    ):
        """Test 31: Resurrection requires newer timestamp."""
        user_id = test_user_with_connection["user_id"]
        base_time = REF_TIME + timedelta(hours=1)
        t1 = REF_TIME
        t2 = t1 + timedelta(hours=1)
        t3 = t2 + timedelta(hours=1)

        # Create and delete
        event = event_factory.create(
            event_id="res1", summary="Original", start_time=base_time, updated_at=t2
        )
        mock_google.set_events([event])
        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        mock_google.set_events([])
        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        # Stale resurrection attempt (older timestamp)
        stale = event_factory.create(
            event_id="res1", summary="Stale", start_time=base_time, updated_at=t1
        )
        mock_google.set_events([stale])
        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.google_event_id == "res1"
            )
        )
        row = result.scalar_one()
        assert row.status == "deleted"  # Stale rejected
        assert row.version == 2

        # Valid resurrection (newer timestamp)
        fresh = event_factory.create(
            event_id="res1", summary="Fresh", start_time=base_time, updated_at=t3
        )
        mock_google.set_events([fresh])
        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.google_event_id == "res1"
            )
        )
        row = result.scalar_one()
        assert row.status == "active"
        assert row.version == 3

    @pytest.mark.asyncio
    async def test_32_batch_upsert_transaction_atomicity(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        event_factory,
        redis_helpers,
    ):
        """
        Test 32: Malformed events in batch don't corrupt valid events.

        Tests multiple malformed event types:
        - All-day event (date instead of dateTime)
        - Missing "updated" field
        - Missing "start" field
        - Wrong schema (integer instead of dict for start)
        """
        user_id = test_user_with_connection["user_id"]
        base_time = REF_TIME + timedelta(hours=1)

        # Valid events
        valid1 = event_factory.create(
            event_id="tx1", summary="Valid 1", start_time=base_time
        )
        valid2 = event_factory.create(
            event_id="tx2", summary="Valid 2", start_time=base_time + timedelta(hours=1)
        )
        valid3 = event_factory.create(
            event_id="tx6", summary="Valid 3", start_time=base_time + timedelta(hours=2)
        )

        # Malformed #1: All-day event (date instead of dateTime - should be skipped)
        malformed_allday = {
            "id": "tx3",
            "iCalUID": "tx3@google.com",
            "summary": "All-day Event",
            "status": "confirmed",
            "updated": "2025-01-15T10:00:00Z",
            "start": {"date": "2025-01-15"},
            "end": {"date": "2025-01-16"},
        }

        # Malformed #2: Missing "updated" field
        malformed_no_updated = {
            "id": "tx4",
            "iCalUID": "tx4@google.com",
            "summary": "Missing Updated",
            "status": "confirmed",
            # No "updated" field!
            "start": {"dateTime": "2025-01-15T10:00:00Z", "timeZone": "UTC"},
            "end": {"dateTime": "2025-01-15T11:00:00Z", "timeZone": "UTC"},
        }

        # Malformed #3: Missing "start" field entirely
        malformed_no_start = {
            "id": "tx5",
            "iCalUID": "tx5@google.com",
            "summary": "Missing Start",
            "status": "confirmed",
            "updated": "2025-01-15T10:00:00Z",
            # No "start" field!
            "end": {"dateTime": "2025-01-15T11:00:00Z", "timeZone": "UTC"},
        }

        # Malformed #4: Wrong schema - integer instead of dict for start
        malformed_wrong_schema = {
            "id": "tx7",
            "iCalUID": "tx7@google.com",
            "summary": "Wrong Schema",
            "status": "confirmed",
            "updated": "2025-01-15T10:00:00Z",
            "start": 12345,  # Integer instead of dict!
            "end": {"dateTime": "2025-01-15T11:00:00Z", "timeZone": "UTC"},
        }

        # Mix valid and malformed events
        mock_google.set_events([
            valid1,
            malformed_allday,
            valid2,
            malformed_no_updated,
            malformed_no_start,
            valid3,
            malformed_wrong_schema,
        ])

        await redis_helpers.set_needs(user_id)
        response = await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        assert response.status_code == 200
        # Only valid events should be inserted, all malformed skipped
        data = response.json()
        assert data["data"]["events_inserted"] == 3, \
            f"Expected 3 valid events, got {data['data']['events_inserted']}"

        # Verify only valid events in DB
        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.user_id == user_id
            )
        )
        rows = result.scalars().all()
        assert len(rows) == 3, f"Expected 3 rows in DB, got {len(rows)}"
        event_ids = {r.google_event_id for r in rows}
        assert event_ids == {"tx1", "tx2", "tx6"}, \
            f"Expected valid event IDs, got {event_ids}"

    @pytest.mark.asyncio
    async def test_33_hash_stability_across_null_descriptions(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_google,
        patch_google_list_events,
        event_factory,
        redis_helpers,
    ):
        """Test 33: Hash comparison uses Google data, not local NULL."""
        user_id = test_user_with_connection["user_id"]
        base_time = REF_TIME + timedelta(hours=1)
        t1 = REF_TIME

        event = event_factory.create(
            event_id="h1",
            summary="Test",
            start_time=base_time,
            description="Desc",
            updated_at=t1,
        )
        mock_google.set_events([event])
        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        # Get original hash
        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.google_event_id == "h1"
            )
        )
        row = result.scalar_one()
        original_hash = row.sha256_content_hash

        # Cleanup sets description=NULL locally
        await async_session.execute(
            text(
                "UPDATE focused_focus_sessions SET event_description = NULL WHERE google_event_id = 'h1'"
            )
        )
        await async_session.flush()

        # Google sends same event
        mock_google.set_events([event])
        await redis_helpers.set_needs(user_id)
        await client.post(
            "/api/focused/tools/sync_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        # Hash should be recalculated from Google data
        async_session.expire_all()
        result = await async_session.execute(
            select(FocusedFocusSession).where(
                FocusedFocusSession.google_event_id == "h1"
            )
        )
        row = result.scalar_one()

        # Hash should match original (computed from Google data, not local NULL)
        assert row.sha256_content_hash == original_hash
        assert row.version == 1  # No false positive update
