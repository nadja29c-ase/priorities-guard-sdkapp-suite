"""
Unit tests for Priority Guardian priorities router.

Tests the build_priorities_response function and related logic.
Focuses on response building, ordering, and data conversion.
"""

import pytest
from datetime import datetime, date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from backend.apps.priority_guardian.routers.priorities_router import (
    build_priorities_response,
    compute_available_keywords,
)


class TestComputeAvailableKeywords:
    """Tests for keyword availability computation."""

    def test_all_keywords_available_when_none_used(self):
        """All keywords available when no priorities exist."""
        available = compute_available_keywords([])
        assert available == ["P1", "P2", "P3"]

    def test_p2_p3_available_when_p1_used(self):
        """P2 and P3 available when P1 is in use."""
        available = compute_available_keywords(["P1"])
        assert available == ["P2", "P3"]

    def test_p1_p3_available_when_p2_used(self):
        """P1 and P3 available when only P2 is in use."""
        available = compute_available_keywords(["P2"])
        assert available == ["P1", "P3"]

    def test_no_keywords_available_when_all_used(self):
        """No keywords available when all three are in use."""
        available = compute_available_keywords(["P1", "P2", "P3"])
        assert available == []


class TestBuildPrioritiesResponseFiltering:
    """Tests for priority filtering in build_priorities_response."""

    @pytest.mark.asyncio
    async def test_only_active_priorities_returned(self):
        """build_priorities_response only returns active priorities.

        Retired priorities are excluded from the widget response.
        The pattern engine (future) will query retired priorities directly.
        """
        user_id = uuid4()

        # Create mock active priority
        active_priority = MagicMock()
        active_priority.id = uuid4()
        active_priority.user_id = user_id
        active_priority.name = "Active Project"
        active_priority.type = "flexible"
        active_priority.calendar_keyword = "P1"
        active_priority.status = "active"
        active_priority.deadline = None
        active_priority.weekly_hour_target = Decimal("10.0")
        active_priority.checkpoint_date = date.today() + timedelta(days=30)
        active_priority.desired_result = "Complete milestone"
        active_priority.deliverables = []
        active_priority.goals = []
        active_priority.created_at = datetime(2024, 2, 1, 10, 0, 0)
        active_priority.updated_at = datetime(2024, 2, 1, 10, 0, 0)
        active_priority.streak_count = 3
        active_priority.total_hours_invested = Decimal("25.5")
        active_priority.avg_target_achievement = Decimal("85.0")

        # Mock session with query results
        # The query only returns active priorities (DB filters by status='active')
        mock_session = AsyncMock()

        # Priority query result (only active priorities from DB)
        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [active_priority]

        # Google connection query result
        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = None  # No Google connection

        mock_session.execute.side_effect = [priorities_result, conn_result]

        # Call function
        response = await build_priorities_response(mock_session, user_id)

        # Verify only active priorities returned
        assert response["success"] is True
        priorities = response["data"]["priorities"]
        assert len(priorities) == 1
        assert priorities[0]["name"] == "Active Project"
        assert priorities[0]["status"] == "active"

    @pytest.mark.asyncio
    async def test_retired_priority_not_in_response(self):
        """Retired priorities are excluded from build_priorities_response.

        This test verifies that after retirement, the response only contains
        active priorities. The retired keyword should be in available_keywords.
        """
        user_id = uuid4()

        # Mock session returns empty list (all priorities retired)
        mock_session = AsyncMock()

        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = []

        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = None

        mock_session.execute.side_effect = [priorities_result, conn_result]

        response = await build_priorities_response(mock_session, user_id)

        # No priorities in response
        assert response["success"] is True
        assert response["data"]["priorities"] == []
        # All keywords available (none in use by active priorities)
        assert response["data"]["available_keywords"] == ["P1", "P2", "P3"]


class TestBuildPrioritiesResponseFalsyConversion:
    """Tests for falsy value handling in build_priorities_response.

    Regression tests for Fixes 2-4 in fix_priorities_router_ordering.md:
    Decimal("0") is falsy in Python, so `if value` would incorrectly
    return None instead of 0.0.
    """

    @pytest.mark.asyncio
    async def test_zero_weekly_hour_target_preserved(self):
        """weekly_hour_target of 0 is preserved as 0.0, not None.

        Note: Pydantic validation currently rejects 0, but the conversion
        logic should handle it correctly regardless.
        """
        user_id = uuid4()

        # Create mock priority with zero weekly_hour_target
        priority = MagicMock()
        priority.id = uuid4()
        priority.user_id = user_id
        priority.name = "Test Priority"
        priority.type = "flexible"
        priority.calendar_keyword = "P1"
        priority.status = "active"
        priority.deadline = None
        priority.weekly_hour_target = Decimal("0")  # Zero value
        priority.checkpoint_date = date.today() + timedelta(days=30)
        priority.desired_result = "Test"
        priority.deliverables = []
        priority.created_at = datetime(2024, 1, 1, 10, 0, 0)
        priority.updated_at = datetime(2024, 1, 1, 10, 0, 0)
        priority.streak_count = 0
        priority.total_hours_invested = Decimal("0")
        priority.avg_target_achievement = None

        mock_session = AsyncMock()
        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [priority]
        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = None
        mock_session.execute.side_effect = [priorities_result, conn_result]

        response = await build_priorities_response(mock_session, user_id)

        # Zero should be preserved, not converted to None
        assert response["data"]["priorities"][0]["weekly_hour_target"] == 0.0

    @pytest.mark.asyncio
    async def test_zero_avg_target_achievement_preserved(self):
        """avg_target_achievement of 0 is preserved as 0.0, not None."""
        user_id = uuid4()

        priority = MagicMock()
        priority.id = uuid4()
        priority.user_id = user_id
        priority.name = "Test Priority"
        priority.type = "flexible"
        priority.calendar_keyword = "P1"
        priority.status = "active"
        priority.deadline = None
        priority.weekly_hour_target = Decimal("10.0")
        priority.checkpoint_date = date.today() + timedelta(days=30)
        priority.desired_result = "Test"
        priority.deliverables = []
        priority.created_at = datetime(2024, 1, 1, 10, 0, 0)
        priority.updated_at = datetime(2024, 1, 1, 10, 0, 0)
        priority.streak_count = 0
        priority.total_hours_invested = Decimal("10.0")
        priority.avg_target_achievement = Decimal("0")  # Zero value

        mock_session = AsyncMock()
        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [priority]
        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = None
        mock_session.execute.side_effect = [priorities_result, conn_result]

        response = await build_priorities_response(mock_session, user_id)

        # Zero should be preserved, not converted to None
        assert response["data"]["priorities"][0]["avg_target_achievement"] == 0.0

    @pytest.mark.asyncio
    async def test_zero_total_hours_invested_preserved(self):
        """total_hours_invested of 0 is preserved as 0.0, not None."""
        user_id = uuid4()

        priority = MagicMock()
        priority.id = uuid4()
        priority.user_id = user_id
        priority.name = "Test Priority"
        priority.type = "deadline"
        priority.calendar_keyword = "P1"
        priority.status = "active"
        priority.deadline = date.today() + timedelta(days=30)
        priority.weekly_hour_target = None
        priority.checkpoint_date = None
        priority.desired_result = None
        priority.deliverables = []
        priority.created_at = datetime(2024, 1, 1, 10, 0, 0)
        priority.updated_at = datetime(2024, 1, 1, 10, 0, 0)
        priority.streak_count = 0
        priority.total_hours_invested = Decimal("0")  # Zero value
        priority.avg_target_achievement = None

        mock_session = AsyncMock()
        priorities_result = MagicMock()
        priorities_result.scalars.return_value.all.return_value = [priority]
        conn_result = MagicMock()
        conn_result.scalar_one_or_none.return_value = None
        mock_session.execute.side_effect = [priorities_result, conn_result]

        response = await build_priorities_response(mock_session, user_id)

        # Zero should be preserved as 0.0, not None
        assert response["data"]["priorities"][0]["total_hours_invested"] == 0.0
