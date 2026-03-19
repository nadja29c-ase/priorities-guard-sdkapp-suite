"""
Integration tests for timeout handling in Priority Guardian MCP tools.

Tests:
- render_weekly_report returns error result on timeout via dispatcher
- onboarding_calendar_setup critical paths return error on timeout
- Widget tools return error results on timeout
"""

import asyncio
from unittest.mock import patch

import pytest
from mcp import types as mcp_types

from mcp_server.priority_guardian.tools import TOOL_REGISTRY
from mcp_server.priority_guardian.tools.base import ToolUsageError


# =============================================================================
# render_weekly_report Integration Tests
# =============================================================================


class TestRenderWeeklyReportTimeoutIntegration:
    """Integration tests for render_weekly_report timeout handling."""

    @pytest.mark.asyncio
    async def test_timeout_returns_error_via_handler(self):
        """Backend timeout should raise ToolUsageError that dispatcher can catch."""
        tool_def = TOOL_REGISTRY.get("render_weekly_report")
        assert tool_def is not None

        async def raise_timeout(*args, **kwargs):
            raise asyncio.TimeoutError()

        with patch(
            "mcp_server.priority_guardian.tools.render_weekly_report.backend_get",
            side_effect=raise_timeout,
        ):
            with pytest.raises(ToolUsageError) as exc_info:
                await tool_def.handle(
                    user_id="user-123",
                    correlation_id="corr-456",
                    arguments={},
                )

            error = exc_info.value
            assert "timed out" in str(error).lower()
            assert "Please try again" in str(error)


# =============================================================================
# onboarding_calendar_setup Integration Tests
# =============================================================================


class TestOnboardingCalendarSetupTimeoutIntegration:
    """Integration tests for onboarding_calendar_setup timeout handling."""

    @pytest.mark.asyncio
    async def test_keyword_education_critical_timeout(self):
        """Critical priorities fetch timeout should raise ToolUsageError."""
        tool_def = TOOL_REGISTRY.get("onboarding_calendar_setup")
        assert tool_def is not None

        call_count = 0

        async def mock_backend_get(path, user_id, correlation_id):
            nonlocal call_count
            call_count += 1
            if "week_start=" in path:
                # Past report check - return success (silent path)
                return {"success": True, "data": {"snapshot_saved": False}}
            # Priorities fetch - simulate timeout
            raise asyncio.TimeoutError()

        with patch(
            "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
            side_effect=mock_backend_get,
        ):
            with pytest.raises(ToolUsageError) as exc_info:
                await tool_def.handle(
                    user_id="user-123",
                    correlation_id="corr-456",
                    arguments={"phase": "keyword_education"},
                )

            assert "timed out" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_first_weekly_report_critical_timeout(self):
        """Critical weekly report fetch timeout should raise ToolUsageError."""
        tool_def = TOOL_REGISTRY.get("onboarding_calendar_setup")
        assert tool_def is not None

        async def mock_backend_get(path, user_id, correlation_id):
            if "week_start=" in path:
                # Past report check - return success
                return {"success": True, "data": {"snapshot_saved": False}}
            # Current week report - simulate timeout
            raise asyncio.TimeoutError()

        with patch(
            "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
            side_effect=mock_backend_get,
        ):
            with pytest.raises(ToolUsageError) as exc_info:
                await tool_def.handle(
                    user_id="user-123",
                    correlation_id="corr-456",
                    arguments={"phase": "first_weekly_report"},
                )

            assert "timed out" in str(exc_info.value).lower()


# =============================================================================
# Widget Tool Integration Tests
# =============================================================================


class TestWidgetToolTimeoutIntegration:
    """Integration tests for widget tool timeout handling."""

    @pytest.mark.asyncio
    async def test_add_priority_timeout(self):
        """add_priority timeout should raise ToolUsageError."""
        tool_def = TOOL_REGISTRY.get("add_priority")
        assert tool_def is not None

        async def raise_timeout(*args, **kwargs):
            raise asyncio.TimeoutError()

        with patch(
            "mcp_server.priority_guardian.tools.widget_tools.add_priority.backend_post",
            side_effect=raise_timeout,
        ):
            with pytest.raises(ToolUsageError) as exc_info:
                await tool_def.handle(
                    user_id="user-123",
                    correlation_id="corr-456",
                    arguments={
                        "name": "Test Priority",
                        "type": "deadline",
                        "deadline": "2025-03-15",
                    },
                )

            assert "timed out" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_connect_google_calendar_timeout(self):
        """connect_google_calendar timeout should raise ToolUsageError."""
        tool_def = TOOL_REGISTRY.get("connect_google_calendar")
        assert tool_def is not None

        async def raise_timeout(*args, **kwargs):
            raise asyncio.TimeoutError()

        with patch(
            "mcp_server.priority_guardian.tools.widget_tools.connect_google_calendar.backend_get",
            side_effect=raise_timeout,
        ):
            with pytest.raises(ToolUsageError) as exc_info:
                await tool_def.handle(
                    user_id="user-123",
                    correlation_id="corr-456",
                    arguments={},
                )

            assert "timed out" in str(exc_info.value).lower()


# =============================================================================
# Silent Branch Integration Tests
# =============================================================================


class TestSilentBranchTimeoutIntegration:
    """Integration tests for silent branches that should NOT raise on timeout."""

    @pytest.mark.asyncio
    async def test_keyword_education_silent_branch_continues(self):
        """Silent past_report check should allow handler to continue."""
        tool_def = TOOL_REGISTRY.get("onboarding_calendar_setup")
        assert tool_def is not None

        call_count = 0

        async def mock_backend_get(path, user_id, correlation_id):
            nonlocal call_count
            call_count += 1
            if "week_start=" in path:
                # Past report check - simulate timeout (should be swallowed)
                raise asyncio.TimeoutError()
            # Priorities fetch - return valid data
            return {
                "success": True,
                "data": {
                    "priorities": [
                        {
                            "id": "pri-1",
                            "name": "Test Priority",
                            "type": "deadline",
                            "calendar_keyword": "P1",
                            "status": "active",
                            "deadline": "2025-03-15",
                            "deliverables": [],
                        }
                    ],
                    "google_connection": {"connected": True},
                    "available_keywords": ["P2", "P3"],
                },
            }

        with patch(
            "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
            side_effect=mock_backend_get,
        ):
            # Should NOT raise - timeout in silent branch is swallowed
            result = await tool_def.handle(
                user_id="user-123",
                correlation_id="corr-456",
                arguments={"phase": "keyword_education"},
            )

            # Should return a valid CallToolResult
            assert isinstance(result, mcp_types.CallToolResult)
            # Both backend calls should have been attempted
            assert call_count == 2
