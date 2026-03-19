"""
Unit tests for get_priority_events MCP handler (Increment 77).

Tests:
- Fetching priority events for breakdown
- No _meta in responses (data tool, no widget)
- Error handling for past weeks
- Guidance template formatting
"""

from unittest.mock import AsyncMock, patch

import pytest

from mcp_server.priority_guardian.tools.get_priority_events import (
    handle,
    GUIDANCE_PRIORITY_BREAKDOWN_TEMPLATE,
)
from mcp_server.priority_guardian.tools.normalize import (
    normalize_priority_report,
    normalize_time_allocation,
    normalize_event,
)


class TestGetPriorityEventsHandler:
    """Tests for get_priority_events handler."""

    @pytest.mark.asyncio
    async def test_returns_priority_events_only(self):
        """Handler returns only events matching the requested priority."""
        mock_response = {
            "success": True,
            "data": {
                "week_start": "2026-03-16",
                "week_end": "2026-03-22",
                "is_current_week": True,
                "priorities": [
                    {
                        "id": "p1",
                        "name": "Ship v1.0",
                        "type": "flexible",
                        "calendar_keyword": "P1",
                        "actual_hours": 10.0,
                        "event_count": 3,
                        "target_hours": 10.0,
                    },
                    {
                        "id": "p2",
                        "name": "Client Work",
                        "type": "flexible",
                        "calendar_keyword": "P2",
                        "actual_hours": 5.0,
                        "event_count": 2,
                        "target_hours": 5.0,
                    },
                ],
                "time_allocation": {
                    "total_tracked_hours": 18.0,
                    "keywords": {
                        "P1": {"hours": 10.0, "event_count": 3},
                        "P2": {"hours": 5.0, "event_count": 2},
                    },
                    "other_hours": 3.0,
                },
                "all_events": [
                    {"title": "P1 Feature work", "matched_keywords": ["P1"], "start": "2026-03-16T09:00:00Z", "end": "2026-03-16T12:00:00Z"},
                    {"title": "P1 Bug fixes", "matched_keywords": ["P1"], "start": "2026-03-16T13:00:00Z", "end": "2026-03-16T15:00:00Z"},
                    {"title": "P2 Client call", "matched_keywords": ["P2"], "start": "2026-03-16T15:00:00Z", "end": "2026-03-16T16:00:00Z"},
                    {"title": "Team Lunch", "matched_keywords": [], "start": "2026-03-16T12:00:00Z", "end": "2026-03-16T13:00:00Z"},
                ],
            },
        }

        with patch(
            "mcp_server.priority_guardian.tools.get_priority_events.backend_get",
            new_callable=AsyncMock,
        ) as mock_backend:
            mock_backend.return_value = mock_response

            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={"semantic_target": "P1"},
            )

        data = result.structuredContent["data"]
        # priorityEvents should only contain P1-matched events
        assert len(data["priorityEvents"]) == 2
        assert all("P1" in e.get("matchedKeywords", []) for e in data["priorityEvents"])
        # otherEvents should be empty (data minimization)
        assert data["otherEvents"] == []

    @pytest.mark.asyncio
    async def test_has_no_meta_widget_render(self):
        """get_priority_events response has no _meta — no widget card ever."""
        mock_response = {
            "success": True,
            "data": {
                "week_start": "2026-03-16",
                "week_end": "2026-03-22",
                "is_current_week": True,
                "priorities": [
                    {
                        "id": "p1",
                        "name": "Ship v1.0",
                        "type": "flexible",
                        "calendar_keyword": "P1",
                        "actual_hours": 10.0,
                        "event_count": 5,
                        "target_hours": 10.0,
                    }
                ],
                "time_allocation": {
                    "total_tracked_hours": 15.0,
                    "keywords": {"P1": {"hours": 10.0, "event_count": 5}},
                    "other_hours": 5.0,
                },
                "all_events": [
                    {"title": "P1: Feature work", "start": "2026-03-16T10:00:00",
                     "end": "2026-03-16T12:00:00", "matched_keywords": ["P1"]},
                ],
            },
        }

        with patch(
            "mcp_server.priority_guardian.tools.get_priority_events.backend_get",
            new_callable=AsyncMock,
        ) as mock_backend:
            mock_backend.return_value = mock_response

            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={"semantic_target": "P1"},
            )

        assert result.isError is not True
        assert result.structuredContent["success"] is True
        # CRITICAL: No _meta — this is a data tool
        assert "_meta" not in result.structuredContent
        # But should have priorityEvents for the model to read
        assert len(result.structuredContent["data"]["priorityEvents"]) == 1

    @pytest.mark.asyncio
    async def test_past_week_error_has_no_meta(self):
        """Past week error responses have no _meta — critical for data tools."""
        mock_response = {
            "success": True,
            "data": {
                "week_start": "2026-03-09",
                "week_end": "2026-03-15",
                "is_current_week": False,  # Past week
                "priorities": [
                    {
                        "id": "p1",
                        "name": "Ship v1.0",
                        "type": "flexible",
                        "calendar_keyword": "P1",
                        "actual_hours": 10.0,
                        "event_count": 5,
                        "target_hours": 10.0,
                    }
                ],
                "time_allocation": {
                    "total_tracked_hours": 15.0,
                    "keywords": {"P1": {"hours": 10.0, "event_count": 5}},
                    "other_hours": 5.0,
                },
                "all_events": [],  # Past week has no events
            },
        }

        with patch(
            "mcp_server.priority_guardian.tools.get_priority_events.backend_get",
            new_callable=AsyncMock,
        ) as mock_backend:
            mock_backend.return_value = mock_response

            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={"semantic_target": "P1"},
            )

        # Should return structured error
        assert result.isError is True
        assert result.structuredContent["success"] is False
        # CRITICAL: No _meta even in error response
        assert "_meta" not in result.structuredContent

    @pytest.mark.asyncio
    async def test_past_week_returns_error(self):
        """Past week (no event data) returns clean structured error."""
        mock_response = {
            "success": True,
            "data": {
                "week_start": "2026-03-09",
                "week_end": "2026-03-15",
                "is_current_week": False,
                "priorities": [
                    {
                        "id": "p1",
                        "name": "Ship v1.0",
                        "type": "flexible",
                        "calendar_keyword": "P1",
                        "actual_hours": 10.0,
                        "event_count": 5,
                        "target_hours": 10.0,
                    }
                ],
                "time_allocation": {
                    "total_tracked_hours": 15.0,
                    "keywords": {"P1": {"hours": 10.0, "event_count": 5}},
                    "other_hours": 5.0,
                },
                "all_events": [],  # Past week has no events
            },
        }

        with patch(
            "mcp_server.priority_guardian.tools.get_priority_events.backend_get",
            new_callable=AsyncMock,
        ) as mock_backend:
            mock_backend.return_value = mock_response

            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={"semantic_target": "P1"},
            )

        assert result.isError is True
        assert result.structuredContent["success"] is False
        assert result.structuredContent["error"] == "priority_breakdown_unavailable"
        assert "P1" in result.structuredContent["assistant_guidance"]
        assert "past weeks" in result.structuredContent["assistant_guidance"]

    @pytest.mark.asyncio
    async def test_current_week_with_no_events_succeeds(self):
        """Current week with no events should succeed (not blocked)."""
        mock_response = {
            "success": True,
            "data": {
                "week_start": "2026-03-16",
                "week_end": "2026-03-22",
                "is_current_week": True,  # Current week
                "priorities": [
                    {
                        "id": "p1",
                        "name": "Ship v1.0",
                        "type": "flexible",
                        "calendar_keyword": "P1",
                        "actual_hours": 0.0,
                        "event_count": 0,
                        "target_hours": 10.0,
                    }
                ],
                "time_allocation": {
                    "total_tracked_hours": 0.0,
                    "keywords": {"P1": {"hours": 0.0, "event_count": 0}},
                    "other_hours": 0.0,
                },
                "all_events": [],  # No events but current week
            },
        }

        with patch(
            "mcp_server.priority_guardian.tools.get_priority_events.backend_get",
            new_callable=AsyncMock,
        ) as mock_backend:
            mock_backend.return_value = mock_response

            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={"semantic_target": "P1"},
            )

        # Should succeed - current week is allowed even with no events
        assert result.isError is not True
        assert result.structuredContent["success"] is True
        # priorityEvents will be empty but that's OK
        assert result.structuredContent["data"]["priorityEvents"] == []

    @pytest.mark.asyncio
    async def test_guidance_references_render_weekly_report(self):
        """Guidance instructs model to call render_weekly_report (not get_weekly_report)."""
        mock_response = {
            "success": True,
            "data": {
                "week_start": "2026-03-16",
                "week_end": "2026-03-22",
                "is_current_week": True,
                "priorities": [
                    {
                        "id": "p1",
                        "name": "Ship v1.0",
                        "type": "flexible",
                        "calendar_keyword": "P1",
                        "actual_hours": 10.0,
                        "event_count": 3,
                        "target_hours": 10.0,
                    },
                ],
                "time_allocation": {
                    "total_tracked_hours": 15.0,
                    "keywords": {"P1": {"hours": 10.0, "event_count": 3}},
                    "other_hours": 5.0,
                },
                "all_events": [
                    {"title": "P1 Feature work", "matched_keywords": ["P1"], "start": "2026-03-16T09:00:00Z", "end": "2026-03-16T12:00:00Z"},
                ],
            },
        }

        with patch(
            "mcp_server.priority_guardian.tools.get_priority_events.backend_get",
            new_callable=AsyncMock,
        ) as mock_backend:
            mock_backend.return_value = mock_response

            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={"semantic_target": "P1"},
            )

        guidance = result.structuredContent["assistant_guidance"]
        # Guidance should reference the new tool name
        assert "render_weekly_report" in guidance
        # Should NOT reference old tool name
        assert "get_weekly_report" not in guidance

    @pytest.mark.asyncio
    async def test_includes_aggregates(self):
        """Response includes priorities and timeAllocation aggregates."""
        mock_response = {
            "success": True,
            "data": {
                "week_start": "2026-03-16",
                "week_end": "2026-03-22",
                "is_current_week": True,
                "priorities": [
                    {
                        "id": "p1",
                        "name": "Ship v1.0",
                        "type": "flexible",
                        "calendar_keyword": "P1",
                        "actual_hours": 10.0,
                        "event_count": 5,
                        "target_hours": 10.0,
                    }
                ],
                "time_allocation": {
                    "total_tracked_hours": 15.0,
                    "keywords": {"P1": {"hours": 10.0, "event_count": 5}},
                    "other_hours": 5.0,
                },
                "all_events": [
                    {"title": "P1 Feature work", "matched_keywords": ["P1"], "start": "2026-03-16T09:00:00Z", "end": "2026-03-16T12:00:00Z"},
                ],
            },
        }

        with patch(
            "mcp_server.priority_guardian.tools.get_priority_events.backend_get",
            new_callable=AsyncMock,
        ) as mock_backend:
            mock_backend.return_value = mock_response

            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={"semantic_target": "P1"},
            )

        data = result.structuredContent["data"]
        # Aggregates always present
        assert "priorities" in data
        assert len(data["priorities"]) == 1
        assert "timeAllocation" in data
        assert data["timeAllocation"]["totalTrackedHours"] == 15.0

    @pytest.mark.asyncio
    async def test_returns_empty_slices(self):
        """Response includes empty slices array (no chart to render)."""
        mock_response = {
            "success": True,
            "data": {
                "week_start": "2026-03-16",
                "week_end": "2026-03-22",
                "is_current_week": True,
                "priorities": [
                    {
                        "id": "p1",
                        "name": "Ship v1.0",
                        "type": "flexible",
                        "calendar_keyword": "P1",
                        "actual_hours": 10.0,
                        "event_count": 5,
                        "target_hours": 10.0,
                    }
                ],
                "time_allocation": {
                    "total_tracked_hours": 15.0,
                    "keywords": {"P1": {"hours": 10.0, "event_count": 5}},
                    "other_hours": 5.0,
                },
                "all_events": [
                    {"title": "P1 Feature work", "matched_keywords": ["P1"], "start": "2026-03-16T09:00:00Z", "end": "2026-03-16T12:00:00Z"},
                ],
            },
        }

        with patch(
            "mcp_server.priority_guardian.tools.get_priority_events.backend_get",
            new_callable=AsyncMock,
        ) as mock_backend:
            mock_backend.return_value = mock_response

            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={"semantic_target": "P1"},
            )

        data = result.structuredContent["data"]
        # Slices should be empty — no chart rendered
        assert data["slices"] == []


class TestNormalizationHelpers:
    """Tests for normalization helper functions (duplicated from render_weekly_report tests)."""

    def test_normalize_priority_report(self):
        """Flexible priority fields are normalized to camelCase."""
        priority = {
            "id": "test-id",
            "name": "Test Priority",
            "type": "flexible",
            "calendar_keyword": "P1",
            "actual_hours": 5.5,
            "event_count": 3,
            "target_hours": 10.0,
            "flex_status": "on_track",
        }

        result = normalize_priority_report(priority)

        assert result["calendarKeyword"] == "P1"
        assert result["actualHours"] == 5.5
        assert result["eventCount"] == 3
        assert result["targetHours"] == 10.0
        assert "flexStatus" not in result  # Intentionally excluded

    def test_normalize_time_allocation(self):
        """Time allocation fields are normalized to camelCase."""
        allocation = {
            "total_tracked_hours": 25.5,
            "keywords": {
                "P1": {"hours": 10.0, "event_count": 5},
            },
            "other_hours": 5.0,
        }

        result = normalize_time_allocation(allocation)

        assert result["totalTrackedHours"] == 25.5
        assert result["otherHours"] == 5.0
        assert result["keywords"]["P1"]["hours"] == 10.0
        assert result["keywords"]["P1"]["eventCount"] == 5

    def test_normalize_event(self):
        """Event fields are normalized to camelCase."""
        event = {
            "title": "Team Meeting",
            "description": "Weekly sync",
            "start": "2026-02-10T10:00:00Z",
            "end": "2026-02-10T11:00:00Z",
            "matched_keywords": ["P1"],
        }

        result = normalize_event(event)

        assert result["title"] == "Team Meeting"
        assert result["description"] == "Weekly sync"
        assert result["matchedKeywords"] == ["P1"]


class TestGuidanceTemplate:
    """Tests for guidance template."""

    def test_guidance_template_includes_keyword_placeholder(self):
        """Template has {keyword} placeholder that gets formatted."""
        guidance = GUIDANCE_PRIORITY_BREAKDOWN_TEMPLATE.format(keyword="P1")
        assert "P1" in guidance
        assert "render_weekly_report" in guidance
        assert "{keyword}" not in guidance  # Should be replaced
