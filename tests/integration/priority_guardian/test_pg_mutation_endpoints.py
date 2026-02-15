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

from backend.apps.priority_guardian.db_models import PgPriority, PgDeliverable


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
    async def test_ignores_update_to_calendar_keyword(self, client, async_session: AsyncSession):
        """calendar_keyword in update request is silently ignored (immutable)."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id, keyword="P1")

        # Sending calendar_keyword field is silently ignored
        response = await client.put(
            f"/api/priority-guardian/priorities/{priority.id}",
            json={"calendar_keyword": "P2", "name": "Updated"},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 200
        # calendar_keyword should remain P1 (unchanged)
        assert response.json()["data"]["priorities"][0]["calendar_keyword"] == "P1"
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
# DELETE /api/priority-guardian/priorities/{priority_id}
# ==============================================================================


class TestDeletePriorityEndpoint:
    """Tests for DELETE /api/priority-guardian/priorities/{priority_id}."""

    @pytest.mark.asyncio
    async def test_delete_priority_success(self, client, async_session: AsyncSession):
        """Delete priority returns fresh list without deleted priority."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id)

        response = await client.delete(
            f"/api/priority-guardian/priorities/{priority.id}",
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]["priorities"]) == 0

    @pytest.mark.asyncio
    async def test_delete_cascades_deliverables(self, client, async_session: AsyncSession):
        """Deleting priority cascades to its deliverables."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id)
        await create_test_deliverable(async_session, priority.id, "Deliverable 1")
        await create_test_deliverable(async_session, priority.id, "Deliverable 2")
        await create_test_deliverable(async_session, priority.id, "Deliverable 3")

        response = await client.delete(
            f"/api/priority-guardian/priorities/{priority.id}",
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 200
        assert len(response.json()["data"]["priorities"]) == 0

    @pytest.mark.asyncio
    async def test_delete_frees_keyword(self, client, async_session: AsyncSession):
        """After deletion, available_keywords includes the freed keyword."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id, keyword="P1")

        response = await client.delete(
            f"/api/priority-guardian/priorities/{priority.id}",
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 200
        assert "P1" in response.json()["data"]["available_keywords"]

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
