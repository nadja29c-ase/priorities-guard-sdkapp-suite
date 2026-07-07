"""
Unit tests for get_priorities calendar merge logic.

Tests the MCP handler's parallel fetch, timeout handling, graceful degradation,
calendar-hours-to-priority mapping, timeAllocation block construction, and
None week_start guard.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from mcp_server.priority_guardian.tools.get_priorities import (
    handle,
    _normalize_priority,
    _fetch_with_timeout,
    TIMEOUT_S,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_priorities_response():
    """Standard priorities response from backend."""
    return {
        "success": True,
        "data": {
            "priorities": [
                {
                    "id": "p1-id",
                    "name": "Ship feature X",
                    "type": "deadline",
                    "calendar_keyword": "P1",
                    "status": "active",
                    "deadline": "2026-02-28",
                    "weekly_hour_target": None,
                    "created_at": "2026-02-01T10:00:00Z",
                    "deliverables": [],
                },
                {
                    "id": "p2-id",
                    "name": "Learn Rust",
                    "type": "flexible",
                    "calendar_keyword": "P2",
                    "status": "active",
                    "deadline": None,
                    "weekly_hour_target": 5.0,
                    "created_at": "2026-02-02T10:00:00Z",
                    "deliverables": [],
                },
            ],
            "google_connection": {"connected": True, "connected_at": "2026-01-15T10:00:00Z"},
            "available_keywords": ["P3"],
        },
    }


@pytest.fixture
def mock_calendar_response():
    """Standard calendar response from backend."""
    return {
        "success": True,
        "data": {
            "week_start": "2026-02-09T00:00:00+01:00",
            "week_end": "2026-02-16T00:00:00+01:00",
            "timezone": "Europe/Berlin",
            "keywords": {
                "P1": {"hours": 10.5, "event_count": 6},
                "P2": {"hours": 3.0, "event_count": 2},
                "P3": {"hours": 0.0, "event_count": 0},
            },
            "other_hours": 18.25,
            "total_tracked_hours": 31.75,
            "total_events_scanned": 42,
            "bar_segments": {"P1": 10.5, "P2": 3.0, "P3": 0.0, "other": 18.25},
        },
    }


@pytest.fixture
def mock_calendar_no_connection_response():
    """Calendar response when user has no Google connection."""
    return {
        "success": True,
        "data": {
            "week_start": None,
            "week_end": None,
            "timezone": "UTC",
            "keywords": {
                "P1": {"hours": 0.0, "event_count": 0},
                "P2": {"hours": 0.0, "event_count": 0},
                "P3": {"hours": 0.0, "event_count": 0},
            },
            "other_hours": 0.0,
            "total_tracked_hours": 0.0,
            "total_events_scanned": 0,
            "bar_segments": {"P1": 0.0, "P2": 0.0, "P3": 0.0, "other": 0.0},
        },
    }


# =============================================================================
# Calendar Data Merged Tests
# =============================================================================

class TestCalendarDataMerged:
    """Tests for when calendar data is successfully merged."""

    @pytest.mark.asyncio
    async def test_weekly_hour_actual_populated(
        self, mock_priorities_response, mock_calendar_response
    ):
        """weeklyHourActual is populated from calendar data."""
        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get",
            new_callable=AsyncMock,
        ) as mock_backend:
            mock_backend.side_effect = [mock_priorities_response, mock_calendar_response]

            result = await handle("user-123", "corr-123", {})

        priorities = result.structuredContent["data"]["priorities"]

        # P1 priority should have weeklyHourActual = 10.5
        p1 = next(p for p in priorities if p["calendarKeyword"] == "P1")
        assert p1["weeklyHourActual"] == 10.5

        # P2 priority should have weeklyHourActual = 3.0
        p2 = next(p for p in priorities if p["calendarKeyword"] == "P2")
        assert p2["weeklyHourActual"] == 3.0

    @pytest.mark.asyncio
    async def test_time_allocation_block_present(
        self, mock_priorities_response, mock_calendar_response
    ):
        """timeAllocation block is present when calendar succeeds."""
        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get",
            new_callable=AsyncMock,
        ) as mock_backend:
            mock_backend.side_effect = [mock_priorities_response, mock_calendar_response]

            result = await handle("user-123", "corr-123", {})

        data = result.structuredContent["data"]
        assert "timeAllocation" in data

        time_alloc = data["timeAllocation"]
        assert time_alloc["weekStart"] == "2026-02-09T00:00:00+01:00"
        assert time_alloc["weekEnd"] == "2026-02-16T00:00:00+01:00"
        assert time_alloc["totalTrackedHours"] == 31.75
        assert time_alloc["keywords"]["P1"]["hours"] == 10.5
        assert time_alloc["keywords"]["P1"]["eventCount"] == 6
        assert time_alloc["otherHours"] == 18.25
        assert "barSegments" in time_alloc

    @pytest.mark.asyncio
    async def test_bar_segments_in_time_allocation(
        self, mock_priorities_response, mock_calendar_response
    ):
        """barSegments is included in timeAllocation."""
        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get",
            new_callable=AsyncMock,
        ) as mock_backend:
            mock_backend.side_effect = [mock_priorities_response, mock_calendar_response]

            result = await handle("user-123", "corr-123", {})

        bar_segments = result.structuredContent["data"]["timeAllocation"]["barSegments"]
        assert bar_segments == {"P1": 10.5, "P2": 3.0, "P3": 0.0, "other": 18.25}


# =============================================================================
# Calendar Endpoint Fails Tests
# =============================================================================

class TestCalendarEndpointFails:
    """Tests for graceful degradation when calendar endpoint fails."""

    @pytest.mark.asyncio
    async def test_priorities_still_returned_on_calendar_failure(
        self, mock_priorities_response
    ):
        """Priorities are still returned when calendar fails."""
        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get",
            new_callable=AsyncMock,
        ) as mock_backend:
            # First call succeeds (priorities), second fails (calendar)
            mock_backend.side_effect = [
                mock_priorities_response,
                Exception("Calendar API error"),
            ]

            result = await handle("user-123", "corr-123", {})

        # Should succeed
        assert result.structuredContent["success"] is True

        # Priorities should be present
        priorities = result.structuredContent["data"]["priorities"]
        assert len(priorities) == 2

    @pytest.mark.asyncio
    async def test_weekly_hour_actual_none_on_calendar_failure(
        self, mock_priorities_response
    ):
        """weeklyHourActual is None when calendar fails."""
        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get",
            new_callable=AsyncMock,
        ) as mock_backend:
            mock_backend.side_effect = [
                mock_priorities_response,
                Exception("Calendar API error"),
            ]

            result = await handle("user-123", "corr-123", {})

        priorities = result.structuredContent["data"]["priorities"]
        for p in priorities:
            assert p["weeklyHourActual"] is None

    @pytest.mark.asyncio
    async def test_no_time_allocation_block_on_calendar_failure(
        self, mock_priorities_response
    ):
        """No timeAllocation block when calendar fails."""
        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get",
            new_callable=AsyncMock,
        ) as mock_backend:
            mock_backend.side_effect = [
                mock_priorities_response,
                Exception("Calendar API error"),
            ]

            result = await handle("user-123", "corr-123", {})

        data = result.structuredContent["data"]
        assert "timeAllocation" not in data


# =============================================================================
# Calendar Returns All Zeros (No Connection) Tests
# =============================================================================

class TestCalendarNoConnection:
    """Tests for when calendar returns all zeros (no Google connection)."""

    @pytest.mark.asyncio
    async def test_weekly_hour_actual_none_when_no_connection(
        self, mock_priorities_response, mock_calendar_no_connection_response
    ):
        """weeklyHourActual is None when week_start is None."""
        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get",
            new_callable=AsyncMock,
        ) as mock_backend:
            mock_backend.side_effect = [
                mock_priorities_response,
                mock_calendar_no_connection_response,
            ]

            result = await handle("user-123", "corr-123", {})

        priorities = result.structuredContent["data"]["priorities"]
        for p in priorities:
            assert p["weeklyHourActual"] is None

    @pytest.mark.asyncio
    async def test_no_time_allocation_block_when_no_connection(
        self, mock_priorities_response, mock_calendar_no_connection_response
    ):
        """No timeAllocation block when week_start is None."""
        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get",
            new_callable=AsyncMock,
        ) as mock_backend:
            mock_backend.side_effect = [
                mock_priorities_response,
                mock_calendar_no_connection_response,
            ]

            result = await handle("user-123", "corr-123", {})

        data = result.structuredContent["data"]
        assert "timeAllocation" not in data

    @pytest.mark.asyncio
    async def test_priorities_still_returned_when_no_connection(
        self, mock_priorities_response, mock_calendar_no_connection_response
    ):
        """Priorities are still returned when no Google connection."""
        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get",
            new_callable=AsyncMock,
        ) as mock_backend:
            mock_backend.side_effect = [
                mock_priorities_response,
                mock_calendar_no_connection_response,
            ]

            result = await handle("user-123", "corr-123", {})

        assert result.structuredContent["success"] is True
        priorities = result.structuredContent["data"]["priorities"]
        assert len(priorities) == 2


# =============================================================================
# Calendar Timeout Tests
# =============================================================================

class TestCalendarTimeout:
    """Tests for calendar timeout handling."""

    @pytest.mark.asyncio
    async def test_calendar_timeout_returns_priorities_without_calendar(
        self, mock_priorities_response
    ):
        """Calendar timeout still returns priorities without calendar data."""
        async def slow_calendar(*args, **kwargs):
            await asyncio.sleep(10)  # Will be cancelled by timeout
            return {"success": True, "data": {}}

        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get",
            new_callable=AsyncMock,
        ) as mock_backend:
            # First call returns immediately, second times out
            async def mock_get(path, *args, **kwargs):
                if "priorities" in path:
                    return mock_priorities_response
                else:
                    await asyncio.sleep(10)  # Will timeout
                    return {}

            mock_backend.side_effect = mock_get

            # Use a shorter timeout for testing
            with patch(
                "mcp_server.priority_guardian.tools.get_priorities.TIMEOUT_S",
                0.1,  # 100ms timeout
            ):
                result = await handle("user-123", "corr-123", {})

        # Should still succeed
        assert result.structuredContent["success"] is True

        # Priorities should be present
        priorities = result.structuredContent["data"]["priorities"]
        assert len(priorities) == 2

        # No calendar data
        assert "timeAllocation" not in result.structuredContent["data"]

    @pytest.mark.asyncio
    async def test_weekly_hour_actual_none_on_timeout(self, mock_priorities_response):
        """weeklyHourActual is None when calendar times out."""
        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get",
            new_callable=AsyncMock,
        ) as mock_backend:
            async def mock_get(path, *args, **kwargs):
                if "priorities" in path:
                    return mock_priorities_response
                else:
                    await asyncio.sleep(10)
                    return {}

            mock_backend.side_effect = mock_get

            with patch(
                "mcp_server.priority_guardian.tools.get_priorities.TIMEOUT_S",
                0.1,
            ):
                result = await handle("user-123", "corr-123", {})

        priorities = result.structuredContent["data"]["priorities"]
        for p in priorities:
            assert p["weeklyHourActual"] is None


# =============================================================================
# Priorities Failure Tests
# =============================================================================

class TestPrioritiesFailure:
    """Tests for when priorities endpoint fails."""

    @pytest.mark.asyncio
    async def test_raises_when_priorities_fails(self, mock_calendar_response):
        """Raises ToolUsageError when priorities endpoint fails."""
        from mcp_server.priority_guardian.tools.base import ToolUsageError

        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get",
            new_callable=AsyncMock,
        ) as mock_backend:
            mock_backend.side_effect = [
                Exception("Priorities API error"),
                mock_calendar_response,
            ]

            with pytest.raises(ToolUsageError) as exc_info:
                await handle("user-123", "corr-123", {})

            assert "Unable to load priorities" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_raises_when_priorities_times_out(self, mock_calendar_response):
        """Raises ToolUsageError when priorities endpoint times out."""
        from mcp_server.priority_guardian.tools.base import ToolUsageError

        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get",
            new_callable=AsyncMock,
        ) as mock_backend:
            async def mock_get(path, *args, **kwargs):
                if "priorities" in path:
                    await asyncio.sleep(10)  # Will timeout
                    return {}
                else:
                    return mock_calendar_response

            mock_backend.side_effect = mock_get

            with patch(
                "mcp_server.priority_guardian.tools.get_priorities.TIMEOUT_S",
                0.1,
            ):
                with pytest.raises(ToolUsageError) as exc_info:
                    await handle("user-123", "corr-123", {})

            assert "Unable to load priorities" in str(exc_info.value)


# =============================================================================
# _fetch_with_timeout Tests
# =============================================================================

class TestFetchWithTimeout:
    """Tests for the _fetch_with_timeout helper."""

    @pytest.mark.asyncio
    async def test_returns_result_on_success(self):
        """Returns coroutine result on success."""
        async def successful_coro():
            return {"data": "value"}

        result = await _fetch_with_timeout(
            successful_coro(), 5.0, "test", "corr-123"
        )

        assert result == {"data": "value"}

    @pytest.mark.asyncio
    async def test_returns_timeout_error_on_timeout(self):
        """Returns TimeoutError on timeout."""
        async def slow_coro():
            await asyncio.sleep(10)
            return {"data": "value"}

        result = await _fetch_with_timeout(
            slow_coro(), 0.1, "test", "corr-123"
        )

        assert isinstance(result, TimeoutError)
        assert "test timed out" in str(result)

    @pytest.mark.asyncio
    async def test_returns_exception_on_error(self):
        """Returns Exception on error."""
        async def failing_coro():
            raise ValueError("Something went wrong")

        result = await _fetch_with_timeout(
            failing_coro(), 5.0, "test", "corr-123"
        )

        assert isinstance(result, ValueError)
        assert "Something went wrong" in str(result)


# =============================================================================
# _normalize_priority Tests
# =============================================================================

class TestNormalizePriorityWithCalendar:
    """Tests for _normalize_priority with calendar data."""

    def test_populates_weekly_hour_actual_from_calendar_hours(self):
        """Populates weeklyHourActual from calendar_hours mapping."""
        priority = {
            "id": "p1",
            "name": "Test",
            "type": "deadline",
            "calendar_keyword": "P1",
            "status": "active",
            "deliverables": [],
        }
        calendar_hours = {"P1": 10.5, "P2": 3.0, "P3": 0.0}

        result = _normalize_priority(priority, calendar_hours)

        assert result["weeklyHourActual"] == 10.5

    def test_weekly_hour_actual_none_when_no_calendar_hours(self):
        """weeklyHourActual is None when calendar_hours is None."""
        priority = {
            "id": "p1",
            "name": "Test",
            "type": "deadline",
            "calendar_keyword": "P1",
            "status": "active",
            "deliverables": [],
        }

        result = _normalize_priority(priority, None)

        assert result["weeklyHourActual"] is None

    def test_weekly_hour_actual_none_when_keyword_not_in_calendar(self):
        """weeklyHourActual is None when keyword not in calendar_hours."""
        priority = {
            "id": "p1",
            "name": "Test",
            "type": "deadline",
            "calendar_keyword": "P3",
            "status": "active",
            "deliverables": [],
        }
        calendar_hours = {"P1": 10.5, "P2": 3.0}  # No P3

        result = _normalize_priority(priority, calendar_hours)

        assert result["weeklyHourActual"] is None

    def test_weekly_hour_actual_zero_is_valid(self):
        """weeklyHourActual can be 0.0 (valid value, not None)."""
        priority = {
            "id": "p1",
            "name": "Test",
            "type": "deadline",
            "calendar_keyword": "P3",
            "status": "active",
            "deliverables": [],
        }
        calendar_hours = {"P1": 10.5, "P2": 3.0, "P3": 0.0}

        result = _normalize_priority(priority, calendar_hours)

        assert result["weeklyHourActual"] == 0.0


# =============================================================================
# Response Shape Tests
# =============================================================================

class TestResponseShape:
    """Tests for overall response shape."""

    @pytest.mark.asyncio
    async def test_structured_content_shape(
        self, mock_priorities_response, mock_calendar_response
    ):
        """Verifies complete structuredContent shape."""
        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get",
            new_callable=AsyncMock,
        ) as mock_backend:
            mock_backend.side_effect = [mock_priorities_response, mock_calendar_response]

            result = await handle("user-123", "corr-123", {})

        sc = result.structuredContent

        # Top-level keys in structuredContent
        assert sc["success"] is True
        assert "data" in sc
        assert "assistant_guidance" in sc
        # inc_96: _meta moved to top-level result (not nested in structuredContent)
        assert "_meta" not in sc
        assert result.meta is not None
        assert result.meta["ui"]["resourceUri"] is not None
        assert result.meta["openai/outputTemplate"] is not None

        # Data keys
        data = sc["data"]
        assert "google_connected" in data
        # google_connected_at excluded for output minimization
        assert "google_connected_at" not in data
        assert "priorities" in data
        assert "available_keywords" in data
        assert "timeAllocation" in data

    @pytest.mark.asyncio
    async def test_text_content_summary(
        self, mock_priorities_response, mock_calendar_response
    ):
        """Verifies text content summary."""
        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get",
            new_callable=AsyncMock,
        ) as mock_backend:
            mock_backend.side_effect = [mock_priorities_response, mock_calendar_response]

            result = await handle("user-123", "corr-123", {})

        # Should have text content
        assert len(result.content) == 1
        assert result.content[0].type == "text"
        assert "2 active priorities" in result.content[0].text
