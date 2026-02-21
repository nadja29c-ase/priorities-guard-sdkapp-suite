"""
Integration tests for Priority Guardian mutation endpoints (Widget B).

Tests PUT/DELETE endpoints for priorities and deliverables:
- PUT /api/priority-guardian/priorities/{priority_id}
- DELETE /api/priority-guardian/priorities/{priority_id}
- POST /api/priority-guardian/priorities/{priority_id}/deliverables
- PUT /api/priority-guardian/deliverables/{deliverable_id}
- DELETE /api/priority-guardian/deliverables/{deliverable_id}
"""

import pytest
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.priority_guardian.db_models import PgPriority, PgDeliverable, PgGoal, PgWeeklySnapshot


# ==============================================================================
# Helper functions
# ==============================================================================


async def create_test_user(async_session: AsyncSession):
    """Create a test user and return their UUID."""
    user_id = uuid4()
    await async_session.execute(
        text("INSERT INTO core_users (id) VALUES (:id)"),
        {"id": user_id},
    )
    await async_session.commit()
    return user_id


async def create_test_priority(
    async_session: AsyncSession,
    user_id,
    name="Test Priority",
    priority_type="deadline",
    keyword="P1",
    **kwargs,
):
    """Create a test priority and return it."""
    future_date = date.today() + timedelta(days=30)  # Keep as date object for DB

    priority_data = {
        "user_id": user_id,
        "name": name,
        "type": priority_type,
        "calendar_keyword": keyword,
        "status": "active",
    }

    if priority_type == "deadline":
        deadline_val = kwargs.get("deadline", future_date)
        # Convert string to date if needed
        if isinstance(deadline_val, str):
            deadline_val = date.fromisoformat(deadline_val)
        priority_data["deadline"] = deadline_val
    else:
        priority_data["weekly_hour_target"] = kwargs.get("weekly_hour_target", Decimal("10.0"))
        checkpoint_val = kwargs.get("checkpoint_date", future_date)
        # Convert string to date if needed
        if isinstance(checkpoint_val, str):
            checkpoint_val = date.fromisoformat(checkpoint_val)
        priority_data["checkpoint_date"] = checkpoint_val

    priority = PgPriority(**priority_data)
    async_session.add(priority)
    await async_session.commit()
    await async_session.refresh(priority)
    return priority


async def create_test_deliverable(async_session: AsyncSession, priority_id, name="Test Deliverable", done=False):
    """Create a test deliverable and return it."""
    deliverable = PgDeliverable(
        priority_id=priority_id,
        name=name,
        done=done,
    )
    async_session.add(deliverable)
    await async_session.commit()
    await async_session.refresh(deliverable)
    return deliverable


# ==============================================================================
# PUT /api/priority-guardian/priorities/{priority_id}
# ==============================================================================


class TestUpdatePriorityEndpoint:
    """Tests for PUT /api/priority-guardian/priorities/{priority_id}."""

    @pytest.mark.asyncio
    async def test_update_name_success(self, client, async_session: AsyncSession):
        """Update name successfully returns fresh priority list."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id)

        response = await client.put(
            f"/api/priority-guardian/priorities/{priority.id}",
            json={"name": "Updated Name"},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]["priorities"]) == 1
        assert data["data"]["priorities"][0]["name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_update_deadline_for_deadline_type(self, client, async_session: AsyncSession):
        """Update deadline for deadline-type priority."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id, priority_type="deadline")

        new_deadline = (date.today() + timedelta(days=60)).isoformat()
        response = await client.put(
            f"/api/priority-guardian/priorities/{priority.id}",
            json={"deadline": new_deadline},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 200
        assert response.json()["data"]["priorities"][0]["deadline"] == new_deadline

    @pytest.mark.asyncio
    async def test_update_flexible_fields(self, client, async_session: AsyncSession):
        """Update flexible-specific fields for flexible-type priority."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id, priority_type="flexible")

        new_date = (date.today() + timedelta(days=45)).isoformat()
        response = await client.put(
            f"/api/priority-guardian/priorities/{priority.id}",
            json={
                "weekly_hour_target": 15.0,
                "checkpoint_date": new_date,
            },
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 200
        updated = response.json()["data"]["priorities"][0]
        assert updated["weekly_hour_target"] == 15.0
        assert updated["checkpoint_date"] == new_date

    @pytest.mark.asyncio
    async def test_ignores_update_to_type_field(self, client, async_session: AsyncSession):
        """Type field in update request is silently ignored (immutable)."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id, priority_type="deadline")

        # Sending type field is silently ignored (Pydantic ignores extra fields by default)
        response = await client.put(
            f"/api/priority-guardian/priorities/{priority.id}",
            json={"type": "flexible", "name": "Updated"},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 200
        # Type should remain deadline (unchanged)
        assert response.json()["data"]["priorities"][0]["type"] == "deadline"
        assert response.json()["data"]["priorities"][0]["name"] == "Updated"

    @pytest.mark.asyncio
    async def test_allows_update_to_calendar_keyword(self, client, async_session: AsyncSession):
        """calendar_keyword can be updated to a free keyword (Inc 13 keyword reassignment)."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id, keyword="P1")

        # Request reassignment to P2 (which is free) along with name update
        response = await client.put(
            f"/api/priority-guardian/priorities/{priority.id}",
            json={"calendar_keyword": "P2", "name": "Updated"},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 200
        # calendar_keyword should now be P2 (free reassignment)
        assert response.json()["data"]["priorities"][0]["calendar_keyword"] == "P2"
        assert response.json()["data"]["priorities"][0]["name"] == "Updated"

    @pytest.mark.asyncio
    async def test_rejects_cross_type_field_deadline_to_flexible(self, client, async_session: AsyncSession):
        """Cannot add flexible fields to deadline-type priority."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id, priority_type="deadline")

        response = await client.put(
            f"/api/priority-guardian/priorities/{priority.id}",
            json={"weekly_hour_target": 10.0},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert detail["code"] == "VALIDATION_ERROR"
        assert "weekly_hour_target" in detail["message"] and "deadline" in detail["message"]

    @pytest.mark.asyncio
    async def test_rejects_cross_type_field_flexible_to_deadline(self, client, async_session: AsyncSession):
        """Cannot add deadline fields to flexible-type priority."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id, priority_type="flexible")

        new_deadline = (date.today() + timedelta(days=30)).isoformat()
        response = await client.put(
            f"/api/priority-guardian/priorities/{priority.id}",
            json={"deadline": new_deadline},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_returns_404_for_nonexistent_priority(self, client, async_session: AsyncSession):
        """Returns 404 for non-existent priority_id."""
        user_id = await create_test_user(async_session)
        fake_id = uuid4()

        response = await client.put(
            f"/api/priority-guardian/priorities/{fake_id}",
            json={"name": "Updated"},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_404_for_different_user(self, client, async_session: AsyncSession):
        """Returns 404 when priority belongs to different user."""
        user1 = await create_test_user(async_session)
        user2 = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user1)

        response = await client.put(
            f"/api/priority-guardian/priorities/{priority.id}",
            json={"name": "Hacked"},
            headers={"X-User-ID": str(user2)},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_partial_update_only_changes_provided_fields(self, client, async_session: AsyncSession):
        """Partial update only changes fields present in request body."""
        user_id = await create_test_user(async_session)
        original_deadline = (date.today() + timedelta(days=30)).isoformat()
        priority = await create_test_priority(
            async_session, user_id,
            name="Original Name",
            priority_type="deadline",
            deadline=original_deadline,
        )

        response = await client.put(
            f"/api/priority-guardian/priorities/{priority.id}",
            json={"name": "Updated Name"},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 200
        updated = response.json()["data"]["priorities"][0]
        assert updated["name"] == "Updated Name"
        assert updated["deadline"] == original_deadline  # Unchanged

    @pytest.mark.asyncio
    async def test_empty_body_returns_200_noop(self, client, async_session: AsyncSession):
        """Empty {} body triggers has_updates()=False, returns current state unchanged."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(
            async_session, user_id,
            name="Unchanged Name",
            priority_type="deadline",
        )

        response = await client.put(
            f"/api/priority-guardian/priorities/{priority.id}",
            json={},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 200
        returned = response.json()["data"]["priorities"][0]
        assert returned["name"] == "Unchanged Name"


# ==============================================================================
# DELETE /api/priority-guardian/priorities/{priority_id} (Soft Delete)
# ==============================================================================


class TestDeletePriorityEndpoint:
    """Tests for DELETE /api/priority-guardian/priorities/{priority_id} (soft delete)."""

    @pytest.mark.asyncio
    async def test_delete_priority_soft_deletes(self, client, async_session: AsyncSession):
        """Soft delete sets status='retired', retired_at, clears keyword. Data preserved."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id, keyword="P1")
        priority_id = priority.id

        # Add deliverables and goals to verify they're preserved
        await create_test_deliverable(async_session, priority_id, "Deliverable 1")
        await create_test_deliverable(async_session, priority_id, "Deliverable 2")

        response = await client.delete(
            f"/api/priority-guardian/priorities/{priority_id}",
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Priority should NOT appear in response (only active priorities returned)
        assert len(data["data"]["priorities"]) == 0
        # Freed keyword should be available
        assert "P1" in data["data"]["available_keywords"]

        # Verify DB state: priority row still exists with status='retired'
        result = await async_session.execute(
            text("SELECT status, retired_at, calendar_keyword FROM pg_priorities WHERE id = :id"),
            {"id": priority_id},
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == "retired"
        assert row[1] is not None  # retired_at is set
        assert row[2] is None  # calendar_keyword is NULL

        # Verify deliverables still exist
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_deliverables WHERE priority_id = :id"),
            {"id": priority_id},
        )
        assert result.scalar() == 2

    @pytest.mark.asyncio
    async def test_delete_retired_priority_is_idempotent(self, client, async_session: AsyncSession):
        """Calling delete on already-retired priority returns 200, no state change."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id, keyword="P1")
        priority_id = priority.id

        # First delete (retires the priority)
        response1 = await client.delete(
            f"/api/priority-guardian/priorities/{priority_id}",
            headers={"X-User-ID": str(user_id)},
        )
        assert response1.status_code == 200

        # Get retired_at timestamp
        result = await async_session.execute(
            text("SELECT retired_at FROM pg_priorities WHERE id = :id"),
            {"id": priority_id},
        )
        original_retired_at = result.scalar()

        # Second delete (idempotent - should return 200 with no change)
        response2 = await client.delete(
            f"/api/priority-guardian/priorities/{priority_id}",
            headers={"X-User-ID": str(user_id)},
        )
        assert response2.status_code == 200

        # Verify retired_at unchanged
        result = await async_session.execute(
            text("SELECT retired_at FROM pg_priorities WHERE id = :id"),
            {"id": priority_id},
        )
        assert result.scalar() == original_retired_at

    @pytest.mark.asyncio
    async def test_soft_deleted_priority_frees_keyword_for_reuse(self, client, async_session: AsyncSession):
        """After soft delete, the freed keyword can be assigned to a new priority."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id, keyword="P1")

        # Soft delete the P1 priority
        response = await client.delete(
            f"/api/priority-guardian/priorities/{priority.id}",
            headers={"X-User-ID": str(user_id)},
        )
        assert response.status_code == 200
        assert "P1" in response.json()["data"]["available_keywords"]

        # Create a new priority - should be able to get P1
        future_date = (date.today() + timedelta(days=30)).isoformat()
        create_response = await client.post(
            "/api/priority-guardian/priorities",
            json={
                "name": "New Priority",
                "type": "deadline",
                "deadline": future_date,
            },
            headers={"X-User-ID": str(user_id)},
        )
        assert create_response.status_code == 201
        # Should have gotten P1 (first available after soft delete freed it)
        assert create_response.json()["data"]["priority"]["calendar_keyword"] == "P1"

    @pytest.mark.asyncio
    async def test_soft_deleted_priority_snapshots_preserved(self, client, async_session: AsyncSession):
        """Soft delete preserves weekly snapshots with calendar_keyword_at_snapshot."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id, keyword="P1")
        priority_id = priority.id

        # Create a snapshot for this priority
        # Calculate last Monday properly
        today = date.today()
        days_since_monday = today.weekday()  # Monday=0, Sunday=6
        this_monday = today - timedelta(days=days_since_monday)
        week_start = this_monday - timedelta(days=7)  # Last Monday
        await async_session.execute(
            text("""
                INSERT INTO pg_weekly_snapshots
                (user_id, priority_id, week_start, week_end, actual_hours, target_hours,
                 calendar_keyword_at_snapshot, streak_at_snapshot)
                VALUES (:user_id, :priority_id, :week_start, :week_end, :actual_hours,
                        :target_hours, :keyword, :streak)
            """),
            {
                "user_id": user_id,
                "priority_id": priority_id,
                "week_start": week_start,
                "week_end": week_start + timedelta(days=6),
                "actual_hours": Decimal("8.5"),
                "target_hours": Decimal("10.0"),
                "keyword": "P1",
                "streak": 1,
            },
        )
        await async_session.commit()

        # Soft delete the priority
        response = await client.delete(
            f"/api/priority-guardian/priorities/{priority_id}",
            headers={"X-User-ID": str(user_id)},
        )
        assert response.status_code == 200

        # Verify snapshot still exists with preserved keyword
        result = await async_session.execute(
            text("""
                SELECT calendar_keyword_at_snapshot, actual_hours
                FROM pg_weekly_snapshots
                WHERE priority_id = :id
            """),
            {"id": priority_id},
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == "P1"  # calendar_keyword_at_snapshot preserved
        assert row[1] == Decimal("8.5")

    @pytest.mark.asyncio
    async def test_returns_404_for_nonexistent(self, client, async_session: AsyncSession):
        """Returns 404 for non-existent priority_id."""
        user_id = await create_test_user(async_session)
        fake_id = uuid4()

        response = await client.delete(
            f"/api/priority-guardian/priorities/{fake_id}",
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_404_for_different_user(self, client, async_session: AsyncSession):
        """Returns 404 when priority belongs to different user."""
        user1 = await create_test_user(async_session)
        user2 = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user1)

        response = await client.delete(
            f"/api/priority-guardian/priorities/{priority.id}",
            headers={"X-User-ID": str(user2)},
        )

        assert response.status_code == 404


# ==============================================================================
# DELETE /api/priority-guardian/priorities/{priority_id}/permanent (Hard Delete)
# ==============================================================================


class TestPermanentDeletePriorityEndpoint:
    """Tests for DELETE /api/priority-guardian/priorities/{priority_id}/permanent."""

    @pytest.mark.asyncio
    async def test_permanent_delete_cascades(self, client, async_session: AsyncSession):
        """Permanent delete cascade-deletes priority, deliverables, goals, snapshots."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id, keyword="P1")
        priority_id = priority.id

        # Add deliverables
        await create_test_deliverable(async_session, priority_id, "Deliverable 1")
        await create_test_deliverable(async_session, priority_id, "Deliverable 2")

        response = await client.delete(
            f"/api/priority-guardian/priorities/{priority_id}/permanent",
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]["priorities"]) == 0

        # Verify priority row is gone
        result = await async_session.execute(
            text("SELECT id FROM pg_priorities WHERE id = :id"),
            {"id": priority_id},
        )
        assert result.fetchone() is None

        # Verify deliverables are gone (cascade deleted)
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_deliverables WHERE priority_id = :id"),
            {"id": priority_id},
        )
        assert result.scalar() == 0

    @pytest.mark.asyncio
    async def test_permanent_delete_works_on_retired_priority(self, client, async_session: AsyncSession):
        """Permanent delete works on already-retired priorities."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id)
        priority_id = priority.id

        # First soft delete (retire)
        await client.delete(
            f"/api/priority-guardian/priorities/{priority_id}",
            headers={"X-User-ID": str(user_id)},
        )

        # Verify it's retired
        result = await async_session.execute(
            text("SELECT status FROM pg_priorities WHERE id = :id"),
            {"id": priority_id},
        )
        assert result.scalar() == "retired"

        # Now permanent delete
        response = await client.delete(
            f"/api/priority-guardian/priorities/{priority_id}/permanent",
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 200

        # Verify it's gone
        result = await async_session.execute(
            text("SELECT id FROM pg_priorities WHERE id = :id"),
            {"id": priority_id},
        )
        assert result.fetchone() is None

    @pytest.mark.asyncio
    async def test_permanent_delete_nonexistent_returns_404(self, client, async_session: AsyncSession):
        """Returns 404 for non-existent priority_id."""
        user_id = await create_test_user(async_session)
        fake_id = uuid4()

        response = await client.delete(
            f"/api/priority-guardian/priorities/{fake_id}/permanent",
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_permanent_delete_different_user_returns_404(self, client, async_session: AsyncSession):
        """Returns 404 when priority belongs to different user."""
        user1 = await create_test_user(async_session)
        user2 = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user1)

        response = await client.delete(
            f"/api/priority-guardian/priorities/{priority.id}/permanent",
            headers={"X-User-ID": str(user2)},
        )

        assert response.status_code == 404


# ==============================================================================
# POST /api/priority-guardian/priorities/{priority_id}/deliverables
# ==============================================================================


class TestCreateDeliverableEndpoint:
    """Tests for POST /api/priority-guardian/priorities/{priority_id}/deliverables."""

    @pytest.mark.asyncio
    async def test_create_deliverable_success(self, client, async_session: AsyncSession):
        """Create deliverable returns fresh priority list with new deliverable."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id)

        response = await client.post(
            f"/api/priority-guardian/priorities/{priority.id}/deliverables",
            json={"name": "New Deliverable"},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        deliverables = data["data"]["priorities"][0]["deliverables"]
        assert len(deliverables) == 1
        assert deliverables[0]["name"] == "New Deliverable"
        assert deliverables[0]["done"] is False

    @pytest.mark.asyncio
    async def test_returns_404_for_nonexistent_priority(self, client, async_session: AsyncSession):
        """Returns 404 for non-existent parent priority."""
        user_id = await create_test_user(async_session)
        fake_id = uuid4()

        response = await client.post(
            f"/api/priority-guardian/priorities/{fake_id}/deliverables",
            json={"name": "Deliverable"},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_404_for_different_user(self, client, async_session: AsyncSession):
        """Returns 404 when parent priority belongs to different user."""
        user1 = await create_test_user(async_session)
        user2 = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user1)

        response = await client.post(
            f"/api/priority-guardian/priorities/{priority.id}/deliverables",
            json={"name": "Deliverable"},
            headers={"X-User-ID": str(user2)},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_422_for_missing_name(self, client, async_session: AsyncSession):
        """Returns 422 for missing name."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id)

        response = await client.post(
            f"/api/priority-guardian/priorities/{priority.id}/deliverables",
            json={},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_returns_422_for_long_name(self, client, async_session: AsyncSession):
        """Returns 422 for name exceeding 200 chars."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id)

        long_name = "x" * 201
        response = await client.post(
            f"/api/priority-guardian/priorities/{priority.id}/deliverables",
            json={"name": long_name},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_deliverable_on_deadline_priority_succeeds(self, client, async_session: AsyncSession):
        """Creating deliverable on deadline priority returns 201."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id, priority_type="deadline")

        response = await client.post(
            f"/api/priority-guardian/priorities/{priority.id}/deliverables",
            json={"name": "Deadline Deliverable"},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        deliverables = data["data"]["priorities"][0]["deliverables"]
        assert len(deliverables) == 1
        assert deliverables[0]["name"] == "Deadline Deliverable"

    @pytest.mark.asyncio
    async def test_create_deliverable_on_flexible_priority_returns_422(self, client, async_session: AsyncSession):
        """Creating deliverable on flexible priority returns 422 VALIDATION_ERROR."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id, priority_type="flexible")

        response = await client.post(
            f"/api/priority-guardian/priorities/{priority.id}/deliverables",
            json={"name": "Invalid Deliverable"},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 422
        data = response.json()
        assert data["detail"]["code"] == "VALIDATION_ERROR"
        assert "deadline" in data["detail"]["message"].lower()


# ==============================================================================
# PUT /api/priority-guardian/deliverables/{deliverable_id}
# ==============================================================================


class TestUpdateDeliverableEndpoint:
    """Tests for PUT /api/priority-guardian/deliverables/{deliverable_id}."""

    @pytest.mark.asyncio
    async def test_toggle_done_to_true(self, client, async_session: AsyncSession):
        """Toggle done to true returns fresh list."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id)
        deliverable = await create_test_deliverable(async_session, priority.id, done=False)

        response = await client.put(
            f"/api/priority-guardian/deliverables/{deliverable.id}",
            json={"done": True},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 200
        updated_deliverable = response.json()["data"]["priorities"][0]["deliverables"][0]
        assert updated_deliverable["done"] is True

    @pytest.mark.asyncio
    async def test_toggle_done_to_false(self, client, async_session: AsyncSession):
        """Toggle done to false returns fresh list."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id)
        deliverable = await create_test_deliverable(async_session, priority.id, done=True)

        response = await client.put(
            f"/api/priority-guardian/deliverables/{deliverable.id}",
            json={"done": False},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 200
        updated_deliverable = response.json()["data"]["priorities"][0]["deliverables"][0]
        assert updated_deliverable["done"] is False

    @pytest.mark.asyncio
    async def test_update_name(self, client, async_session: AsyncSession):
        """Update name returns fresh list."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id)
        deliverable = await create_test_deliverable(async_session, priority.id, name="Original")

        response = await client.put(
            f"/api/priority-guardian/deliverables/{deliverable.id}",
            json={"name": "Updated Name"},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 200
        updated_deliverable = response.json()["data"]["priorities"][0]["deliverables"][0]
        assert updated_deliverable["name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_returns_404_for_nonexistent(self, client, async_session: AsyncSession):
        """Returns 404 for non-existent deliverable_id."""
        user_id = await create_test_user(async_session)
        fake_id = uuid4()

        response = await client.put(
            f"/api/priority-guardian/deliverables/{fake_id}",
            json={"done": True},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_404_for_different_user(self, client, async_session: AsyncSession):
        """Returns 404 when parent priority belongs to different user."""
        user1 = await create_test_user(async_session)
        user2 = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user1)
        deliverable = await create_test_deliverable(async_session, priority.id)

        response = await client.put(
            f"/api/priority-guardian/deliverables/{deliverable.id}",
            json={"done": True},
            headers={"X-User-ID": str(user2)},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_empty_body_returns_200_noop(self, client, async_session: AsyncSession):
        """Empty {} body triggers has_updates()=False, returns current state unchanged."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id)
        deliverable = await create_test_deliverable(async_session, priority.id, name="Unchanged", done=False)

        response = await client.put(
            f"/api/priority-guardian/deliverables/{deliverable.id}",
            json={},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 200
        returned_deliverable = response.json()["data"]["priorities"][0]["deliverables"][0]
        assert returned_deliverable["name"] == "Unchanged"
        assert returned_deliverable["done"] is False


# ==============================================================================
# DELETE /api/priority-guardian/deliverables/{deliverable_id}
# ==============================================================================


class TestDeleteDeliverableEndpoint:
    """Tests for DELETE /api/priority-guardian/deliverables/{deliverable_id}."""

    @pytest.mark.asyncio
    async def test_delete_deliverable_success(self, client, async_session: AsyncSession):
        """Delete deliverable returns fresh list without it."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id)
        deliverable = await create_test_deliverable(async_session, priority.id)

        response = await client.delete(
            f"/api/priority-guardian/deliverables/{deliverable.id}",
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 200
        assert len(response.json()["data"]["priorities"][0]["deliverables"]) == 0

    @pytest.mark.asyncio
    async def test_returns_404_for_nonexistent(self, client, async_session: AsyncSession):
        """Returns 404 for non-existent deliverable_id."""
        user_id = await create_test_user(async_session)
        fake_id = uuid4()

        response = await client.delete(
            f"/api/priority-guardian/deliverables/{fake_id}",
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_404_for_different_user(self, client, async_session: AsyncSession):
        """Returns 404 when parent priority belongs to different user."""
        user1 = await create_test_user(async_session)
        user2 = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user1)
        deliverable = await create_test_deliverable(async_session, priority.id)

        response = await client.delete(
            f"/api/priority-guardian/deliverables/{deliverable.id}",
            headers={"X-User-ID": str(user2)},
        )

        assert response.status_code == 404


# ==============================================================================
# POST /api/priority-guardian/priorities (CreatePriorityRequest validation)
# ==============================================================================


class TestCreatePriorityEndpoint:
    """Tests for POST /api/priority-guardian/priorities validation."""

    @pytest.mark.asyncio
    async def test_negative_weekly_hour_target_returns_422(self, client, async_session: AsyncSession):
        """Pydantic gt=0 enforcement: negative weekly_hour_target returns 422."""
        user_id = await create_test_user(async_session)
        future_date = (date.today() + timedelta(days=30)).isoformat()

        response = await client.post(
            "/api/priority-guardian/priorities",
            json={
                "name": "Test Flexible",
                "type": "flexible",
                "weekly_hour_target": -5,
                "checkpoint_date": future_date,
                "initial_goal_text": "Some goal",
            },
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 422
