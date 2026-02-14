"""
Unit tests for get_priorities MCP handler snapshot integration (Increment 08).

Tests:
- Snapshot endpoint called in parallel
- Snapshot failures don't break dashboard
- read_only_hint is False
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4


class TestSnapshotEndpointIntegration:
    """Tests for snapshot endpoint being called in parallel."""

    @pytest.mark.asyncio
    async def test_snapshot_endpoint_called_in_parallel(self):
        """Snapshot endpoint is called alongside priorities and calendar."""
        from mcp_server.priority_guardian.tools.get_priorities import handle

        user_id = str(uuid4())
        correlation_id = "test-corr-id"

        # Mock all three backend calls
        priorities_response = {
            "success": True,
            "data": {
                "priorities": [],
                "google_connection": {"connected": True, "connected_at": "2026-01-01T00:00:00Z"},
                "available_keywords": ["P1", "P2", "P3"],
            },
        }
        calendar_response = {
            "success": True,
            "data": {
                "week_start": "2026-02-09T00:00:00-08:00",
                "week_end": "2026-02-16T00:00:00-08:00",
                "keywords": {
                    "P1": {"hours": 0.0, "event_count": 0},
                    "P2": {"hours": 0.0, "event_count": 0},
                    "P3": {"hours": 0.0, "event_count": 0},
                },
                "other_hours": 0.0,
                "total_tracked_hours": 0.0,
            },
        }
        snapshot_response = {
            "success": True,
            "data": {"checked": 3, "created": 0, "errors": 0},
        }

        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get"
        ) as mock_get, patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_post"
        ) as mock_post:
            mock_get.side_effect = [priorities_response, calendar_response]
            mock_post.return_value = snapshot_response

            result = await handle(user_id, correlation_id, {})

            # Verify backend_post was called for snapshots
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "/snapshots/ensure" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_snapshot_failure_doesnt_break_dashboard(self):
        """Snapshot endpoint failure doesn't prevent dashboard from rendering."""
        from mcp_server.priority_guardian.tools.get_priorities import handle

        user_id = str(uuid4())
        correlation_id = "test-corr-id"

        priorities_response = {
            "success": True,
            "data": {
                "priorities": [],
                "google_connection": {"connected": True, "connected_at": "2026-01-01T00:00:00Z"},
                "available_keywords": ["P1", "P2", "P3"],
            },
        }
        calendar_response = {
            "success": True,
            "data": {
                "week_start": "2026-02-09T00:00:00-08:00",
                "week_end": "2026-02-16T00:00:00-08:00",
                "keywords": {
                    "P1": {"hours": 0.0, "event_count": 0},
                    "P2": {"hours": 0.0, "event_count": 0},
                    "P3": {"hours": 0.0, "event_count": 0},
                },
                "other_hours": 0.0,
                "total_tracked_hours": 0.0,
            },
        }

        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get"
        ) as mock_get, patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_post"
        ) as mock_post:
            mock_get.side_effect = [priorities_response, calendar_response]
            # Snapshot endpoint fails
            mock_post.side_effect = Exception("Snapshot service unavailable")

            # Should NOT raise - dashboard renders normally
            result = await handle(user_id, correlation_id, {})

            # Dashboard rendered successfully
            assert result.structuredContent["success"] is True

    @pytest.mark.asyncio
    async def test_snapshot_timeout_doesnt_break_dashboard(self):
        """Snapshot endpoint timeout doesn't prevent dashboard from rendering."""
        from mcp_server.priority_guardian.tools.get_priorities import handle
        import asyncio

        user_id = str(uuid4())
        correlation_id = "test-corr-id"

        priorities_response = {
            "success": True,
            "data": {
                "priorities": [],
                "google_connection": {"connected": True, "connected_at": "2026-01-01T00:00:00Z"},
                "available_keywords": ["P1", "P2", "P3"],
            },
        }
        calendar_response = {
            "success": True,
            "data": {
                "week_start": "2026-02-09T00:00:00-08:00",
                "week_end": "2026-02-16T00:00:00-08:00",
                "keywords": {
                    "P1": {"hours": 0.0, "event_count": 0},
                    "P2": {"hours": 0.0, "event_count": 0},
                    "P3": {"hours": 0.0, "event_count": 0},
                },
                "other_hours": 0.0,
                "total_tracked_hours": 0.0,
            },
        }

        async def slow_snapshot(*args, **kwargs):
            await asyncio.sleep(100)  # Very slow
            return {"success": True, "data": {"checked": 0, "created": 0, "errors": 0}}

        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get"
        ) as mock_get, patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_post"
        ) as mock_post, patch(
            "mcp_server.priority_guardian.tools.get_priorities.BACKEND_TIMEOUT", 0.01
        ):
            mock_get.side_effect = [priorities_response, calendar_response]
            mock_post.side_effect = slow_snapshot

            # Should NOT raise - dashboard renders normally (timeout handled)
            result = await handle(user_id, correlation_id, {})

            # Dashboard rendered successfully
            assert result.structuredContent["success"] is True


class TestToolAnnotations:
    """Tests for tool annotation changes."""

    def test_read_only_hint_is_false(self):
        """get_priorities has read_only_hint=False (triggers writes)."""
        from mcp_server.priority_guardian.tools.get_priorities import GET_PRIORITIES

        assert GET_PRIORITIES.read_only_hint is False


class TestAggregateFieldMapping:
    """Tests for aggregate fields in _normalize_priority."""

    def test_normalize_priority_includes_all_aggregates(self):
        """_normalize_priority includes streakCount, totalHoursInvested, avgTargetAchievement."""
        from mcp_server.priority_guardian.tools.get_priorities import _normalize_priority

        priority = {
            "id": str(uuid4()),
            "name": "Test Priority",
            "type": "flexible",
            "calendar_keyword": "P1",
            "status": "active",
            "deadline": None,
            "weekly_hour_target": 10.0,
            "checkpoint_date": "2026-03-01",
            "desired_result": "Complete project",
            "deliverables": [],
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "streak_count": 5,
            "total_hours_invested": 42.5,
            "avg_target_achievement": 85.0,
        }

        result = _normalize_priority(priority)

        # All aggregate fields present
        assert result["streakCount"] == 5
        assert result["totalHoursInvested"] == 42.5
        assert result["avgTargetAchievement"] == 85.0

    def test_normalize_priority_defaults_for_missing_aggregates(self):
        """_normalize_priority provides defaults when aggregates are missing."""
        from mcp_server.priority_guardian.tools.get_priorities import _normalize_priority

        priority = {
            "id": str(uuid4()),
            "name": "Test Priority",
            "type": "deadline",
            "calendar_keyword": "P2",
            "status": "active",
            "deadline": "2026-03-15",
            "weekly_hour_target": None,
            "checkpoint_date": None,
            "desired_result": None,
            "deliverables": [],
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            # No aggregate fields
        }

        result = _normalize_priority(priority)

        # Default values
        assert result["streakCount"] == 0
        assert result["totalHoursInvested"] == 0.0
        assert result["avgTargetAchievement"] is None

    def test_aggregates_included_for_deadline_priorities(self):
        """Deadline priorities also get aggregate fields (Inc 08)."""
        from mcp_server.priority_guardian.tools.get_priorities import _normalize_priority

        priority = {
            "id": str(uuid4()),
            "name": "Ship Feature",
            "type": "deadline",
            "calendar_keyword": "P1",
            "status": "active",
            "deadline": "2026-03-15",
            "weekly_hour_target": None,
            "checkpoint_date": None,
            "desired_result": None,
            "deliverables": [],
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "streak_count": 3,
            "total_hours_invested": 36.0,
            "avg_target_achievement": 92.5,
        }

        result = _normalize_priority(priority)

        # Aggregates present for deadline type
        assert result["streakCount"] == 3
        assert result["totalHoursInvested"] == 36.0
        assert result["avgTargetAchievement"] == 92.5
