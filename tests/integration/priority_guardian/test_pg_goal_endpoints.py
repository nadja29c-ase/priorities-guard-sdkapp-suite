"""
Integration tests for Priority Guardian goal endpoints (Widget D).

Tests POST/PUT/DELETE endpoints for goals:
- POST /api/priority-guardian/priorities/{priority_id}/goals
- PUT /api/priority-guardian/goals/{goal_id}
- DELETE /api/priority-guardian/goals/{goal_id}
"""

import pytest
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.priority_guardian.db_models import PgPriority, PgGoal


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
    priority_type="flexible",
    keyword="P1",
    **kwargs,
):
    """Create a test priority and return it."""
    future_date = date.today() + timedelta(days=30)

    priority_data = {
        "user_id": user_id,
        "name": name,
        "type": priority_type,
        "calendar_keyword": keyword,
        "status": "active",
    }

    if priority_type == "deadline":
        deadline_val = kwargs.get("deadline", future_date)
        if isinstance(deadline_val, str):
            deadline_val = date.fromisoformat(deadline_val)
        priority_data["deadline"] = deadline_val
    else:
        priority_data["weekly_hour_target"] = kwargs.get("weekly_hour_target", Decimal("10.0"))
        checkpoint_val = kwargs.get("checkpoint_date", future_date)
        if isinstance(checkpoint_val, str):
            checkpoint_val = date.fromisoformat(checkpoint_val)
        priority_data["checkpoint_date"] = checkpoint_val

    priority = PgPriority(**priority_data)
    async_session.add(priority)
    await async_session.commit()
    await async_session.refresh(priority)
    return priority


async def create_test_goal(
    async_session: AsyncSession,
    priority_id,
    text_value="Test goal",
    achieved=False,
):
    """Create a test goal and return it."""
    goal = PgGoal(
        priority_id=priority_id,
        goal_text=text_value,
        achieved=achieved,
    )
    async_session.add(goal)
    await async_session.commit()
    await async_session.refresh(goal)
    return goal


# ==============================================================================
# POST /api/priority-guardian/priorities/{priority_id}/goals
# ==============================================================================


class TestCreateGoalEndpoint:
    """Tests for POST /api/priority-guardian/priorities/{priority_id}/goals."""

    @pytest.mark.asyncio
    async def test_create_goal_on_flexible_priority(self, client, async_session: AsyncSession):
        """Happy path: goal created on flexible priority, returned in priorities response."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id, priority_type="flexible")

        response = await client.post(
            f"/api/priority-guardian/priorities/{priority.id}/goals",
            json={"text": "Complete sprint review"},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        goals = data["data"]["priorities"][0]["goals"]
        assert len(goals) == 1
        assert goals[0]["text"] == "Complete sprint review"
        assert goals[0]["achieved"] is False
        assert "id" in goals[0]

    @pytest.mark.asyncio
    async def test_create_goal_on_deadline_priority_returns_422(self, client, async_session: AsyncSession):
        """Type enforcement: goals only allowed for flexible priorities."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id, priority_type="deadline")

        response = await client.post(
            f"/api/priority-guardian/priorities/{priority.id}/goals",
            json={"text": "Should fail"},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert detail["code"] == "VALIDATION_ERROR"
        assert "flexible" in detail["message"].lower()

    @pytest.mark.asyncio
    async def test_max_goals_returns_409(self, client, async_session: AsyncSession):
        """Limit enforcement: max 3 goals per priority."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id, priority_type="flexible")

        # Create 3 goals directly in DB
        await create_test_goal(async_session, priority.id, "Goal 1")
        await create_test_goal(async_session, priority.id, "Goal 2")
        await create_test_goal(async_session, priority.id, "Goal 3")

        # Attempt to create 4th goal via API
        response = await client.post(
            f"/api/priority-guardian/priorities/{priority.id}/goals",
            json={"text": "Goal 4 should fail"},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 409
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "MAX_GOALS_REACHED"

    @pytest.mark.asyncio
    async def test_returns_404_for_nonexistent_priority(self, client, async_session: AsyncSession):
        """FK validation: 404 for non-existent priority."""
        user_id = await create_test_user(async_session)
        fake_id = uuid4()

        response = await client.post(
            f"/api/priority-guardian/priorities/{fake_id}/goals",
            json={"text": "Some goal"},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_404_for_different_user(self, client, async_session: AsyncSession):
        """Ownership enforcement: 404 when priority belongs to different user."""
        user1 = await create_test_user(async_session)
        user2 = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user1, priority_type="flexible")

        response = await client.post(
            f"/api/priority-guardian/priorities/{priority.id}/goals",
            json={"text": "Hacked goal"},
            headers={"X-User-ID": str(user2)},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_422_for_missing_text(self, client, async_session: AsyncSession):
        """Pydantic validation on empty body."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id, priority_type="flexible")

        response = await client.post(
            f"/api/priority-guardian/priorities/{priority.id}/goals",
            json={},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_returns_422_for_long_text(self, client, async_session: AsyncSession):
        """Max length validation: 201 chars returns 422."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id, priority_type="flexible")

        long_text = "x" * 201
        response = await client.post(
            f"/api/priority-guardian/priorities/{priority.id}/goals",
            json={"text": long_text},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_returns_422_for_whitespace_only_text(self, client, async_session: AsyncSession):
        """Whitespace validation: empty after trim returns 422."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id, priority_type="flexible")

        response = await client.post(
            f"/api/priority-guardian/priorities/{priority.id}/goals",
            json={"text": "   "},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 422


# ==============================================================================
# PUT /api/priority-guardian/goals/{goal_id}
# ==============================================================================


class TestUpdateGoalEndpoint:
    """Tests for PUT /api/priority-guardian/goals/{goal_id}."""

    @pytest.mark.asyncio
    async def test_toggle_achieved_to_true(self, client, async_session: AsyncSession):
        """Happy path: toggle achieved to true."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id, priority_type="flexible")
        goal = await create_test_goal(async_session, priority.id, achieved=False)

        response = await client.put(
            f"/api/priority-guardian/goals/{goal.id}",
            json={"achieved": True},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 200
        updated_goal = response.json()["data"]["priorities"][0]["goals"][0]
        assert updated_goal["achieved"] is True

    @pytest.mark.asyncio
    async def test_toggle_achieved_to_false(self, client, async_session: AsyncSession):
        """Reverse toggle: achieved back to false."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id, priority_type="flexible")
        goal = await create_test_goal(async_session, priority.id, achieved=True)

        response = await client.put(
            f"/api/priority-guardian/goals/{goal.id}",
            json={"achieved": False},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 200
        updated_goal = response.json()["data"]["priorities"][0]["goals"][0]
        assert updated_goal["achieved"] is False

    @pytest.mark.asyncio
    async def test_rename_goal(self, client, async_session: AsyncSession):
        """Text update: rename goal."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id, priority_type="flexible")
        goal = await create_test_goal(async_session, priority.id, text_value="Original text")

        response = await client.put(
            f"/api/priority-guardian/goals/{goal.id}",
            json={"text": "Updated text"},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 200
        updated_goal = response.json()["data"]["priorities"][0]["goals"][0]
        assert updated_goal["text"] == "Updated text"

    @pytest.mark.asyncio
    async def test_empty_body_returns_200_noop(self, client, async_session: AsyncSession):
        """has_updates() returns False on empty body, returns current state."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id, priority_type="flexible")
        goal = await create_test_goal(async_session, priority.id, text_value="Unchanged", achieved=False)

        response = await client.put(
            f"/api/priority-guardian/goals/{goal.id}",
            json={},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 200
        returned_goal = response.json()["data"]["priorities"][0]["goals"][0]
        assert returned_goal["text"] == "Unchanged"
        assert returned_goal["achieved"] is False

    @pytest.mark.asyncio
    async def test_returns_404_for_nonexistent(self, client, async_session: AsyncSession):
        """UUID validation: 404 for non-existent goal."""
        user_id = await create_test_user(async_session)
        fake_id = uuid4()

        response = await client.put(
            f"/api/priority-guardian/goals/{fake_id}",
            json={"achieved": True},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_404_for_different_user(self, client, async_session: AsyncSession):
        """Ownership enforcement via parent priority JOIN."""
        user1 = await create_test_user(async_session)
        user2 = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user1, priority_type="flexible")
        goal = await create_test_goal(async_session, priority.id)

        response = await client.put(
            f"/api/priority-guardian/goals/{goal.id}",
            json={"achieved": True},
            headers={"X-User-ID": str(user2)},
        )

        assert response.status_code == 404


# ==============================================================================
# DELETE /api/priority-guardian/goals/{goal_id}
# ==============================================================================


class TestDeleteGoalEndpoint:
    """Tests for DELETE /api/priority-guardian/goals/{goal_id}."""

    @pytest.mark.asyncio
    async def test_delete_goal_success(self, client, async_session: AsyncSession):
        """Happy path: goal removed from response."""
        user_id = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user_id, priority_type="flexible")
        goal = await create_test_goal(async_session, priority.id)

        response = await client.delete(
            f"/api/priority-guardian/goals/{goal.id}",
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 200
        goals = response.json()["data"]["priorities"][0]["goals"]
        assert len(goals) == 0

    @pytest.mark.asyncio
    async def test_returns_404_for_nonexistent(self, client, async_session: AsyncSession):
        """UUID validation: 404 for non-existent goal."""
        user_id = await create_test_user(async_session)
        fake_id = uuid4()

        response = await client.delete(
            f"/api/priority-guardian/goals/{fake_id}",
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_404_for_different_user(self, client, async_session: AsyncSession):
        """Ownership enforcement: 404 when goal belongs to different user."""
        user1 = await create_test_user(async_session)
        user2 = await create_test_user(async_session)
        priority = await create_test_priority(async_session, user1, priority_type="flexible")
        goal = await create_test_goal(async_session, priority.id)

        response = await client.delete(
            f"/api/priority-guardian/goals/{goal.id}",
            headers={"X-User-ID": str(user2)},
        )

        assert response.status_code == 404
