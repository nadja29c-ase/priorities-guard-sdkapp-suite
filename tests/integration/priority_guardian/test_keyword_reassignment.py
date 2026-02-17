"""
Integration tests for keyword reassignment (Increment 13).

Tests verify actual DB state after keyword operations, not just API responses.
These tests exercise the 3-step NULL intermediary swap against the real
partial unique index and CHECK constraint.
"""

import pytest
from datetime import date, timedelta
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError


class TestKeywordChoiceOnCreation:
    """Tests for user-chosen keyword on priority creation."""

    @pytest.mark.asyncio
    async def test_choose_keyword_on_creation(self, client, async_session: AsyncSession):
        """User can choose a specific keyword when creating a priority."""
        user_id = uuid4()
        await async_session.execute(
            text("INSERT INTO core_users (id) VALUES (:id)"),
            {"id": user_id},
        )
        await async_session.commit()

        future_date = (date.today() + timedelta(days=30)).isoformat()

        # Request P3 specifically instead of auto-assigned P1
        response = await client.post(
            "/api/priority-guardian/priorities",
            json={
                "name": "Important Project",
                "type": "deadline",
                "deadline": future_date,
                "calendar_keyword": "P3",
            },
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["data"]["priority"]["calendar_keyword"] == "P3"

        # Verify DB state directly
        result = await async_session.execute(
            text("SELECT calendar_keyword FROM pg_priorities WHERE user_id = :uid"),
            {"uid": user_id},
        )
        row = result.fetchone()
        assert row[0] == "P3"

    @pytest.mark.asyncio
    async def test_choose_unavailable_keyword_returns_409(self, client, async_session: AsyncSession):
        """Choosing a keyword held by another priority returns 409."""
        user_id = uuid4()
        await async_session.execute(
            text("INSERT INTO core_users (id) VALUES (:id)"),
            {"id": user_id},
        )
        await async_session.commit()

        future_date = (date.today() + timedelta(days=30)).isoformat()

        # Create first priority with P1
        response1 = await client.post(
            "/api/priority-guardian/priorities",
            json={"name": "First", "type": "deadline", "deadline": future_date},
            headers={"X-User-ID": str(user_id)},
        )
        assert response1.status_code == 201
        assert response1.json()["data"]["priority"]["calendar_keyword"] == "P1"

        # Try to create second priority also requesting P1
        response2 = await client.post(
            "/api/priority-guardian/priorities",
            json={
                "name": "Second",
                "type": "deadline",
                "deadline": future_date,
                "calendar_keyword": "P1",  # Already taken
            },
            headers={"X-User-ID": str(user_id)},
        )

        assert response2.status_code == 409
        assert response2.json()["error"]["code"] == "KEYWORD_CONFLICT"


class TestKeywordReassignmentDisplacement:
    """Tests for keyword reassignment with displacement (3-step swap)."""

    @pytest.mark.asyncio
    async def test_displacement_swap_db_state(self, client, async_session: AsyncSession):
        """
        After reassigning P2→P1 (displacing existing P1→P2), verify actual DB state.

        This is the critical test: the 3-step NULL intermediary swap must work
        against the real partial unique index without IntegrityError.
        """
        user_id = uuid4()
        await async_session.execute(
            text("INSERT INTO core_users (id) VALUES (:id)"),
            {"id": user_id},
        )
        await async_session.commit()

        future_date = (date.today() + timedelta(days=30)).isoformat()

        # Create two priorities: P1 and P2
        resp1 = await client.post(
            "/api/priority-guardian/priorities",
            json={"name": "Original P1", "type": "deadline", "deadline": future_date},
            headers={"X-User-ID": str(user_id)},
        )
        assert resp1.status_code == 201
        p1_id = resp1.json()["data"]["priority"]["id"]

        resp2 = await client.post(
            "/api/priority-guardian/priorities",
            json={"name": "Original P2", "type": "deadline", "deadline": future_date},
            headers={"X-User-ID": str(user_id)},
        )
        assert resp2.status_code == 201
        p2_id = resp2.json()["data"]["priority"]["id"]

        # Reassign P2's priority to P1 (displacement)
        resp_update = await client.put(
            f"/api/priority-guardian/priorities/{p2_id}",
            json={"calendar_keyword": "P1"},
            headers={"X-User-ID": str(user_id)},
        )

        assert resp_update.status_code == 200, f"Expected 200, got {resp_update.status_code}: {resp_update.text}"

        # Query DB directly to verify state
        result = await async_session.execute(
            text("""
                SELECT id, calendar_keyword
                FROM pg_priorities
                WHERE user_id = :uid AND status = 'active'
                ORDER BY calendar_keyword
            """),
            {"uid": user_id},
        )
        rows = result.fetchall()

        assert len(rows) == 2

        # Both rows must have non-NULL keywords
        keywords = {str(row[0]): row[1] for row in rows}
        assert keywords[p2_id] == "P1", f"P2 priority should now be P1, got {keywords[p2_id]}"
        assert keywords[p1_id] == "P2", f"P1 priority should now be P2, got {keywords[p1_id]}"

    @pytest.mark.asyncio
    async def test_no_null_leak_after_displacement(self, client, async_session: AsyncSession):
        """After displacement, no rows should have NULL calendar_keyword."""
        user_id = uuid4()
        await async_session.execute(
            text("INSERT INTO core_users (id) VALUES (:id)"),
            {"id": user_id},
        )
        await async_session.commit()

        future_date = (date.today() + timedelta(days=30)).isoformat()

        # Create three priorities
        for name in ["First", "Second", "Third"]:
            resp = await client.post(
                "/api/priority-guardian/priorities",
                json={"name": name, "type": "deadline", "deadline": future_date},
                headers={"X-User-ID": str(user_id)},
            )
            assert resp.status_code == 201

        # Get priority IDs
        result = await async_session.execute(
            text("""
                SELECT id, calendar_keyword
                FROM pg_priorities
                WHERE user_id = :uid AND status = 'active'
            """),
            {"uid": user_id},
        )
        rows = result.fetchall()
        p3_id = next(str(r[0]) for r in rows if r[1] == "P3")

        # Reassign P3 to P1 (displaces P1 to P3)
        resp_update = await client.put(
            f"/api/priority-guardian/priorities/{p3_id}",
            json={"calendar_keyword": "P1"},
            headers={"X-User-ID": str(user_id)},
        )
        assert resp_update.status_code == 200

        # Verify no NULL keywords exist
        null_count = await async_session.execute(
            text("""
                SELECT COUNT(*)
                FROM pg_priorities
                WHERE user_id = :uid AND calendar_keyword IS NULL
            """),
            {"uid": user_id},
        )
        count = null_count.scalar()
        assert count == 0, f"Found {count} rows with NULL calendar_keyword after displacement"

    @pytest.mark.asyncio
    async def test_unique_index_integrity_after_swap(self, client, async_session: AsyncSession):
        """
        After displacement, the unique index should still prevent duplicates.

        Attempt INSERT with a duplicate active keyword - must raise IntegrityError.
        """
        user_id = uuid4()
        await async_session.execute(
            text("INSERT INTO core_users (id) VALUES (:id)"),
            {"id": user_id},
        )
        await async_session.commit()

        future_date = date.today() + timedelta(days=30)

        # Create two priorities via API
        for name in ["First", "Second"]:
            resp = await client.post(
                "/api/priority-guardian/priorities",
                json={"name": name, "type": "deadline", "deadline": future_date.isoformat()},
                headers={"X-User-ID": str(user_id)},
            )
            assert resp.status_code == 201

        # Get P2's ID
        result = await async_session.execute(
            text("""
                SELECT id FROM pg_priorities
                WHERE user_id = :uid AND calendar_keyword = 'P2' AND status = 'active'
            """),
            {"uid": user_id},
        )
        p2_id = str(result.scalar())

        # Swap P2 to P1
        resp_update = await client.put(
            f"/api/priority-guardian/priorities/{p2_id}",
            json={"calendar_keyword": "P1"},
            headers={"X-User-ID": str(user_id)},
        )
        assert resp_update.status_code == 200

        # Now try to manually INSERT a duplicate P1 - should fail
        with pytest.raises(IntegrityError) as exc_info:
            await async_session.execute(
                text("""
                    INSERT INTO pg_priorities
                    (id, user_id, name, type, calendar_keyword, status, deadline)
                    VALUES (gen_random_uuid(), :user_id, 'Duplicate', 'deadline', 'P1', 'active', :deadline)
                """),
                {"user_id": user_id, "deadline": future_date},
            )
            await async_session.flush()

        assert "idx_pg_priorities_user_keyword_active" in str(exc_info.value).lower() or \
               "unique" in str(exc_info.value).lower()

        await async_session.rollback()

    @pytest.mark.asyncio
    async def test_three_step_flush_no_integrity_error(self, client, async_session: AsyncSession):
        """
        Critical test: perform displacement via API against real DB with real constraints.

        If this passes without IntegrityError, the NULL intermediary approach is proven.
        If it throws, the swap logic is broken.
        """
        user_id = uuid4()
        await async_session.execute(
            text("INSERT INTO core_users (id) VALUES (:id)"),
            {"id": user_id},
        )
        await async_session.commit()

        future_date = (date.today() + timedelta(days=30)).isoformat()

        # Create all three priorities
        resp1 = await client.post(
            "/api/priority-guardian/priorities",
            json={"name": "Priority A", "type": "deadline", "deadline": future_date},
            headers={"X-User-ID": str(user_id)},
        )
        assert resp1.status_code == 201
        p1_id = resp1.json()["data"]["priority"]["id"]

        resp2 = await client.post(
            "/api/priority-guardian/priorities",
            json={"name": "Priority B", "type": "deadline", "deadline": future_date},
            headers={"X-User-ID": str(user_id)},
        )
        assert resp2.status_code == 201

        resp3 = await client.post(
            "/api/priority-guardian/priorities",
            json={"name": "Priority C", "type": "deadline", "deadline": future_date},
            headers={"X-User-ID": str(user_id)},
        )
        assert resp3.status_code == 201
        p3_id = resp3.json()["data"]["priority"]["id"]

        # Perform swap: P3 → P1 (this exercises the 3-step NULL intermediary)
        resp_swap = await client.put(
            f"/api/priority-guardian/priorities/{p3_id}",
            json={"calendar_keyword": "P1"},
            headers={"X-User-ID": str(user_id)},
        )

        # This MUST succeed - if it fails with IntegrityError, the swap logic is broken
        assert resp_swap.status_code == 200, \
            f"3-step swap failed with {resp_swap.status_code}: {resp_swap.text}"

        # Verify final state
        data = resp_swap.json()
        priorities = data["data"]["priorities"]

        keyword_map = {p["id"]: p["calendar_keyword"] for p in priorities}
        assert keyword_map[p3_id] == "P1", "P3 should now have P1"
        assert keyword_map[p1_id] == "P3", "P1 should now have P3"


class TestFreeKeywordReassignment:
    """Tests for reassigning to a free keyword (Case 1 - no displacement)."""

    @pytest.mark.asyncio
    async def test_free_reassignment_only_updates_requesting_row(
        self, client, async_session: AsyncSession
    ):
        """
        Free reassignment (P1→P3 when P3 is available) should only update
        the requesting row. Other rows should have identical updated_at.
        """
        user_id = uuid4()
        await async_session.execute(
            text("INSERT INTO core_users (id) VALUES (:id)"),
            {"id": user_id},
        )
        await async_session.commit()

        future_date = (date.today() + timedelta(days=30)).isoformat()

        # Create two priorities (P1 and P2)
        resp1 = await client.post(
            "/api/priority-guardian/priorities",
            json={"name": "First", "type": "deadline", "deadline": future_date},
            headers={"X-User-ID": str(user_id)},
        )
        assert resp1.status_code == 201
        p1_id = resp1.json()["data"]["priority"]["id"]

        resp2 = await client.post(
            "/api/priority-guardian/priorities",
            json={"name": "Second", "type": "deadline", "deadline": future_date},
            headers={"X-User-ID": str(user_id)},
        )
        assert resp2.status_code == 201
        p2_id = resp2.json()["data"]["priority"]["id"]

        # Capture updated_at timestamps before reassignment
        result = await async_session.execute(
            text("""
                SELECT id, updated_at
                FROM pg_priorities
                WHERE user_id = :uid AND status = 'active'
            """),
            {"uid": user_id},
        )
        timestamps_before = {str(r[0]): r[1] for r in result.fetchall()}

        # Small delay to ensure timestamp difference is detectable
        import asyncio
        await asyncio.sleep(0.1)

        # Reassign P1 to P3 (free keyword - no displacement)
        resp_update = await client.put(
            f"/api/priority-guardian/priorities/{p1_id}",
            json={"calendar_keyword": "P3"},
            headers={"X-User-ID": str(user_id)},
        )
        assert resp_update.status_code == 200

        # Verify only P1's row was updated
        result = await async_session.execute(
            text("""
                SELECT id, calendar_keyword, updated_at
                FROM pg_priorities
                WHERE user_id = :uid AND status = 'active'
            """),
            {"uid": user_id},
        )
        rows = result.fetchall()

        for row in rows:
            row_id = str(row[0])
            keyword = row[1]
            updated_at = row[2]

            if row_id == p1_id:
                # Requesting row should have new keyword and updated timestamp
                assert keyword == "P3"
                assert updated_at > timestamps_before[row_id], \
                    "Requesting row updated_at should have changed"
            else:
                # Other row should be untouched
                assert keyword == "P2"
                assert updated_at == timestamps_before[row_id], \
                    f"Non-requesting row {row_id} should not have been modified"

    @pytest.mark.asyncio
    async def test_reassign_to_same_keyword_is_noop(self, client, async_session: AsyncSession):
        """Reassigning to the same keyword should be a no-op."""
        user_id = uuid4()
        await async_session.execute(
            text("INSERT INTO core_users (id) VALUES (:id)"),
            {"id": user_id},
        )
        await async_session.commit()

        future_date = (date.today() + timedelta(days=30)).isoformat()

        resp = await client.post(
            "/api/priority-guardian/priorities",
            json={"name": "Test", "type": "deadline", "deadline": future_date},
            headers={"X-User-ID": str(user_id)},
        )
        assert resp.status_code == 201
        priority_id = resp.json()["data"]["priority"]["id"]

        # Capture state before
        result = await async_session.execute(
            text("SELECT updated_at FROM pg_priorities WHERE id = :pid"),
            {"pid": priority_id},
        )
        updated_at_before = result.scalar()

        # Reassign P1 to P1 (same keyword)
        resp_update = await client.put(
            f"/api/priority-guardian/priorities/{priority_id}",
            json={"calendar_keyword": "P1"},
            headers={"X-User-ID": str(user_id)},
        )
        assert resp_update.status_code == 200

        # Verify no DB change (updated_at unchanged)
        result = await async_session.execute(
            text("SELECT updated_at FROM pg_priorities WHERE id = :pid"),
            {"pid": priority_id},
        )
        updated_at_after = result.scalar()

        assert updated_at_after == updated_at_before, \
            "Reassigning to same keyword should not update the row"


class TestNoNullLeakInvariant:
    """Tests ensuring NULL keyword never persists after any reassignment."""

    @pytest.mark.asyncio
    async def test_no_null_after_multiple_swaps(self, client, async_session: AsyncSession):
        """After multiple chained swaps, no NULL keywords should exist."""
        user_id = uuid4()
        await async_session.execute(
            text("INSERT INTO core_users (id) VALUES (:id)"),
            {"id": user_id},
        )
        await async_session.commit()

        future_date = (date.today() + timedelta(days=30)).isoformat()

        # Create three priorities
        ids = []
        for name in ["A", "B", "C"]:
            resp = await client.post(
                "/api/priority-guardian/priorities",
                json={"name": name, "type": "deadline", "deadline": future_date},
                headers={"X-User-ID": str(user_id)},
            )
            assert resp.status_code == 201
            ids.append(resp.json()["data"]["priority"]["id"])

        # Get initial keywords
        result = await async_session.execute(
            text("""
                SELECT id, calendar_keyword
                FROM pg_priorities
                WHERE user_id = :uid AND status = 'active'
            """),
            {"uid": user_id},
        )
        initial = {str(r[0]): r[1] for r in result.fetchall()}

        # Chain of swaps: P3→P1, then P2→P3
        p3_id = next(k for k, v in initial.items() if v == "P3")
        p2_id = next(k for k, v in initial.items() if v == "P2")

        # Swap 1: P3 → P1
        resp1 = await client.put(
            f"/api/priority-guardian/priorities/{p3_id}",
            json={"calendar_keyword": "P1"},
            headers={"X-User-ID": str(user_id)},
        )
        assert resp1.status_code == 200

        # Verify no NULL after first swap
        null_count = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_priorities WHERE user_id = :uid AND calendar_keyword IS NULL"),
            {"uid": user_id},
        )
        assert null_count.scalar() == 0, "NULL found after first swap"

        # Swap 2: P2 → P3
        resp2 = await client.put(
            f"/api/priority-guardian/priorities/{p2_id}",
            json={"calendar_keyword": "P3"},
            headers={"X-User-ID": str(user_id)},
        )
        assert resp2.status_code == 200

        # Verify no NULL after second swap
        null_count = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_priorities WHERE user_id = :uid AND calendar_keyword IS NULL"),
            {"uid": user_id},
        )
        assert null_count.scalar() == 0, "NULL found after second swap"

        # Final verification: all three priorities have valid keywords
        result = await async_session.execute(
            text("""
                SELECT calendar_keyword
                FROM pg_priorities
                WHERE user_id = :uid AND status = 'active'
            """),
            {"uid": user_id},
        )
        keywords = sorted([r[0] for r in result.fetchall()])
        assert keywords == ["P1", "P2", "P3"], f"Keywords should be P1, P2, P3 but got {keywords}"


class TestErrorCases:
    """Tests for error handling during keyword reassignment."""

    @pytest.mark.asyncio
    async def test_reassign_invalid_keyword_returns_422(self, client, async_session: AsyncSession):
        """Reassigning to invalid keyword (not P1/P2/P3) returns 422."""
        user_id = uuid4()
        await async_session.execute(
            text("INSERT INTO core_users (id) VALUES (:id)"),
            {"id": user_id},
        )
        await async_session.commit()

        future_date = (date.today() + timedelta(days=30)).isoformat()

        resp = await client.post(
            "/api/priority-guardian/priorities",
            json={"name": "Test", "type": "deadline", "deadline": future_date},
            headers={"X-User-ID": str(user_id)},
        )
        assert resp.status_code == 201
        priority_id = resp.json()["data"]["priority"]["id"]

        # Try invalid keyword
        resp_update = await client.put(
            f"/api/priority-guardian/priorities/{priority_id}",
            json={"calendar_keyword": "P4"},  # Invalid
            headers={"X-User-ID": str(user_id)},
        )

        assert resp_update.status_code == 422

    @pytest.mark.asyncio
    async def test_reassign_nonexistent_priority_returns_404(self, client, async_session: AsyncSession):
        """Reassigning keyword on non-existent priority returns 404."""
        user_id = uuid4()
        await async_session.execute(
            text("INSERT INTO core_users (id) VALUES (:id)"),
            {"id": user_id},
        )
        await async_session.commit()

        fake_id = str(uuid4())

        resp = await client.put(
            f"/api/priority-guardian/priorities/{fake_id}",
            json={"calendar_keyword": "P1"},
            headers={"X-User-ID": str(user_id)},
        )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_reassign_retired_priority_returns_404(self, client, async_session: AsyncSession):
        """Reassigning keyword on retired priority returns 404."""
        user_id = uuid4()
        await async_session.execute(
            text("INSERT INTO core_users (id) VALUES (:id)"),
            {"id": user_id},
        )
        await async_session.commit()

        future_date = (date.today() + timedelta(days=30)).isoformat()

        # Create and then delete priority
        resp = await client.post(
            "/api/priority-guardian/priorities",
            json={"name": "Test", "type": "deadline", "deadline": future_date},
            headers={"X-User-ID": str(user_id)},
        )
        assert resp.status_code == 201
        priority_id = resp.json()["data"]["priority"]["id"]

        # Delete (retire) the priority
        del_resp = await client.delete(
            f"/api/priority-guardian/priorities/{priority_id}",
            headers={"X-User-ID": str(user_id)},
        )
        assert del_resp.status_code == 200

        # Try to reassign keyword on retired priority
        resp_update = await client.put(
            f"/api/priority-guardian/priorities/{priority_id}",
            json={"calendar_keyword": "P2"},
            headers={"X-User-ID": str(user_id)},
        )

        assert resp_update.status_code == 404


class TestSnapshotsUnaffectedByReassignment:
    """Test that historical snapshots are unaffected by keyword reassignment."""

    @pytest.mark.asyncio
    async def test_snapshots_reference_priority_id_not_keyword(
        self, client, async_session: AsyncSession
    ):
        """
        Snapshots are keyed by priority_id, not keyword.
        After reassignment, existing snapshots still reference the correct priority.
        """
        user_id = uuid4()
        await async_session.execute(
            text("INSERT INTO core_users (id) VALUES (:id)"),
            {"id": user_id},
        )
        await async_session.commit()

        future_date = (date.today() + timedelta(days=30)).isoformat()

        # Create a priority
        resp = await client.post(
            "/api/priority-guardian/priorities",
            json={"name": "Test Priority", "type": "deadline", "deadline": future_date},
            headers={"X-User-ID": str(user_id)},
        )
        assert resp.status_code == 201
        priority_id = resp.json()["data"]["priority"]["id"]
        original_keyword = resp.json()["data"]["priority"]["calendar_keyword"]
        assert original_keyword == "P1"

        # Manually insert a snapshot for this priority
        # Week must start on Monday and end on Sunday (7 days later)
        # Find last Monday
        today = date.today()
        days_since_monday = today.weekday()  # Monday = 0
        last_monday = today - timedelta(days=days_since_monday + 7)
        last_sunday = last_monday + timedelta(days=6)

        await async_session.execute(
            text("""
                INSERT INTO pg_weekly_snapshots
                (id, priority_id, user_id, week_start, week_end, actual_hours, target_hours)
                VALUES (gen_random_uuid(), :pid, :uid, :week_start, :week_end, 5.0, 10.0)
            """),
            {
                "pid": priority_id,
                "uid": user_id,
                "week_start": last_monday,
                "week_end": last_sunday,
            },
        )
        await async_session.commit()

        # Reassign keyword from P1 to P3
        resp_update = await client.put(
            f"/api/priority-guardian/priorities/{priority_id}",
            json={"calendar_keyword": "P3"},
            headers={"X-User-ID": str(user_id)},
        )
        assert resp_update.status_code == 200

        # Verify snapshot still references the same priority_id
        result = await async_session.execute(
            text("""
                SELECT priority_id, actual_hours, target_hours
                FROM pg_weekly_snapshots
                WHERE priority_id = :pid
            """),
            {"pid": priority_id},
        )
        snapshot = result.fetchone()

        assert snapshot is not None, "Snapshot should still exist"
        assert str(snapshot[0]) == priority_id, "Snapshot should reference same priority_id"
        assert float(snapshot[1]) == 5.0, "Snapshot data should be unchanged"
        assert float(snapshot[2]) == 10.0, "Snapshot data should be unchanged"

        # Verify the priority now has P3
        result = await async_session.execute(
            text("SELECT calendar_keyword FROM pg_priorities WHERE id = :pid"),
            {"pid": priority_id},
        )
        new_keyword = result.scalar()
        assert new_keyword == "P3", "Priority should now have P3 keyword"
