"""
Timeout compliance tests for Priority Guardian MCP tools.

Tests:
- Backend calls properly raise ToolUsageError on timeout
- Silent branches continue without raising on timeout
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from mcp_server.priority_guardian.tools.base import ToolUsageError


# =============================================================================
# get_patterns Timeout Tests
# =============================================================================


class TestGetPatternsTimeout:
    """Test timeout handling in get_patterns."""

    @pytest.mark.asyncio
    async def test_backend_timeout_raises_tool_usage_error(self):
        """Backend timeout should raise ToolUsageError."""
        from mcp_server.priority_guardian.tools.get_patterns import handle

        async def raise_timeout(*args, **kwargs):
            raise asyncio.TimeoutError()

        with patch(
            "mcp_server.priority_guardian.tools.get_patterns.backend_get",
            side_effect=raise_timeout,
        ):
            with pytest.raises(ToolUsageError) as exc_info:
                await handle(
                    user_id="user-123",
                    correlation_id="corr-456",
                    _arguments={},
                )

            assert "timed out" in str(exc_info.value).lower()


# =============================================================================
# get_weekly_report Timeout Tests
# =============================================================================


class TestGetWeeklyReportTimeout:
    """Test timeout handling in get_weekly_report."""

    @pytest.mark.asyncio
    async def test_backend_timeout_raises_tool_usage_error(self):
        """Backend timeout should raise ToolUsageError."""
        from mcp_server.priority_guardian.tools.get_weekly_report import handle

        async def raise_timeout(*args, **kwargs):
            raise asyncio.TimeoutError()

        with patch(
            "mcp_server.priority_guardian.tools.get_weekly_report.backend_get",
            side_effect=raise_timeout,
        ):
            with pytest.raises(ToolUsageError) as exc_info:
                await handle(
                    user_id="user-123",
                    correlation_id="corr-456",
                    arguments={},
                )

            assert "timed out" in str(exc_info.value).lower()


# =============================================================================
# onboarding_calendar_setup Timeout Tests
# =============================================================================


class TestOnboardingCalendarSetupTimeout:
    """Test timeout handling in onboarding_calendar_setup."""

    @pytest.mark.asyncio
    async def test_past_report_check_continues_on_timeout(self):
        """Silent past_report check should continue without raising on timeout."""
        from mcp_server.priority_guardian.tools.onboarding_calendar_setup import (
            _handle_keyword_education,
        )

        call_count = 0

        async def mock_backend_get(path, user_id, correlation_id):
            nonlocal call_count
            call_count += 1
            if "week_start=" in path:
                # Past report check - simulate timeout
                raise asyncio.TimeoutError()
            # Return valid priorities response for the critical call
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
            # Should NOT raise - past_report check is silent
            result = await _handle_keyword_education(
                user_id="user-123",
                correlation_id="corr-456",
            )

            # Should have completed successfully
            assert result is not None
            # Both calls should have been made (past_report + priorities)
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_priorities_fetch_raises_on_timeout(self):
        """Critical priorities fetch should raise ToolUsageError on timeout."""
        from mcp_server.priority_guardian.tools.onboarding_calendar_setup import (
            _handle_keyword_education,
        )

        async def mock_backend_get(path, user_id, correlation_id):
            if "week_start=" in path:
                # Past report check - return success
                return {"success": True, "data": {"snapshot_saved": False}}
            # Priorities fetch - simulate timeout
            raise asyncio.TimeoutError()

        with patch(
            "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
            side_effect=mock_backend_get,
        ):
            with pytest.raises(ToolUsageError) as exc_info:
                await _handle_keyword_education(
                    user_id="user-123",
                    correlation_id="corr-456",
                )

            assert "timed out" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_first_weekly_report_past_check_continues_on_timeout(self):
        """Silent past_report check in first_weekly_report should continue."""
        from mcp_server.priority_guardian.tools.onboarding_calendar_setup import (
            _handle_first_weekly_report,
        )

        call_count = 0

        async def mock_backend_get(path, user_id, correlation_id):
            nonlocal call_count
            call_count += 1
            if "week_start=" in path:
                # Past report check - simulate timeout
                raise asyncio.TimeoutError()
            # Current week report - return valid data
            return {
                "success": True,
                "data": {
                    "week_start": "2025-03-03",
                    "week_end": "2025-03-09",
                    "snapshot_saved": False,
                    "keywords": {
                        "P1": {"hours": 10.0, "event_count": 5},
                    },
                    "priorities": [
                        {
                            "id": "pri-1",
                            "name": "Test",
                            "calendar_keyword": "P1",
                            "type": "deadline",
                        }
                    ],
                },
            }

        with patch(
            "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
            side_effect=mock_backend_get,
        ):
            # Should NOT raise - past_report check is silent
            result = await _handle_first_weekly_report(
                user_id="user-123",
                correlation_id="corr-456",
            )

            assert result is not None
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_first_weekly_report_fetch_raises_on_timeout(self):
        """Critical weekly_report fetch should raise ToolUsageError on timeout."""
        from mcp_server.priority_guardian.tools.onboarding_calendar_setup import (
            _handle_first_weekly_report,
        )

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
                await _handle_first_weekly_report(
                    user_id="user-123",
                    correlation_id="corr-456",
                )

            assert "timed out" in str(exc_info.value).lower()


# =============================================================================
# Widget Tool Timeout Tests
# =============================================================================


class TestWidgetToolTimeouts:
    """Test timeout handling in widget tools."""

    @pytest.mark.asyncio
    async def test_add_priority_backend_post_timeout(self):
        """add_priority should raise ToolUsageError on backend_post timeout."""
        from mcp_server.priority_guardian.tools.widget_tools.add_priority import handle

        async def raise_timeout(*args, **kwargs):
            raise asyncio.TimeoutError()

        with patch(
            "mcp_server.priority_guardian.tools.widget_tools.add_priority.backend_post",
            side_effect=raise_timeout,
        ):
            with pytest.raises(ToolUsageError) as exc_info:
                await handle(
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
    async def test_update_priority_timeout(self):
        """update_priority should raise ToolUsageError on timeout."""
        from mcp_server.priority_guardian.tools.widget_tools.update_priority import handle

        async def raise_timeout(*args, **kwargs):
            raise asyncio.TimeoutError()

        with patch(
            "mcp_server.priority_guardian.tools.widget_tools.update_priority.backend_put",
            side_effect=raise_timeout,
        ):
            with pytest.raises(ToolUsageError) as exc_info:
                await handle(
                    user_id="user-123",
                    correlation_id="corr-456",
                    arguments={
                        "priority_id": "pri-123",
                        "name": "Updated Name",
                    },
                )

            assert "timed out" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_delete_priority_timeout(self):
        """delete_priority should raise ToolUsageError on timeout."""
        from mcp_server.priority_guardian.tools.widget_tools.delete_priority import handle

        async def raise_timeout(*args, **kwargs):
            raise asyncio.TimeoutError()

        with patch(
            "mcp_server.priority_guardian.tools.widget_tools.delete_priority.backend_delete",
            side_effect=raise_timeout,
        ):
            with pytest.raises(ToolUsageError) as exc_info:
                await handle(
                    user_id="user-123",
                    correlation_id="corr-456",
                    arguments={
                        "priority_id": "pri-123",
                        "confirm": True,
                    },
                )

            assert "timed out" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_connect_google_calendar_timeout(self):
        """connect_google_calendar should raise ToolUsageError on timeout."""
        from mcp_server.priority_guardian.tools.widget_tools.connect_google_calendar import handle

        async def raise_timeout(*args, **kwargs):
            raise asyncio.TimeoutError()

        with patch(
            "mcp_server.priority_guardian.tools.widget_tools.connect_google_calendar.backend_get",
            side_effect=raise_timeout,
        ):
            with pytest.raises(ToolUsageError) as exc_info:
                await handle(
                    user_id="user-123",
                    correlation_id="corr-456",
                    arguments={},
                )

            assert "timed out" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_disconnect_google_calendar_timeout(self):
        """disconnect_google_calendar should raise ToolUsageError on timeout."""
        from mcp_server.priority_guardian.tools.widget_tools.disconnect_google_calendar import handle

        async def raise_timeout(*args, **kwargs):
            raise asyncio.TimeoutError()

        with patch(
            "mcp_server.priority_guardian.tools.widget_tools.disconnect_google_calendar.backend_get",
            side_effect=raise_timeout,
        ):
            with pytest.raises(ToolUsageError) as exc_info:
                await handle(
                    user_id="user-123",
                    correlation_id="corr-456",
                    arguments={"confirm": True},
                )

            assert "timed out" in str(exc_info.value).lower()


# =============================================================================
# TIMEOUT_S Constant Tests
# =============================================================================


class TestTimeoutConstants:
    """Test that TIMEOUT_S is properly defined in all files."""

    def test_get_patterns_timeout_constant(self):
        """get_patterns should have TIMEOUT_S = 8.0."""
        from mcp_server.priority_guardian.tools import get_patterns

        assert hasattr(get_patterns, "TIMEOUT_S")
        assert get_patterns.TIMEOUT_S == 8.0

    def test_get_weekly_report_timeout_constant(self):
        """get_weekly_report should have TIMEOUT_S = 8.0."""
        from mcp_server.priority_guardian.tools import get_weekly_report

        assert hasattr(get_weekly_report, "TIMEOUT_S")
        assert get_weekly_report.TIMEOUT_S == 8.0

    def test_onboarding_calendar_setup_timeout_constant(self):
        """onboarding_calendar_setup should have TIMEOUT_S = 8.0."""
        from mcp_server.priority_guardian.tools import onboarding_calendar_setup

        assert hasattr(onboarding_calendar_setup, "TIMEOUT_S")
        assert onboarding_calendar_setup.TIMEOUT_S == 8.0

    def test_widget_tools_have_timeout_constant(self):
        """All widget tools should have TIMEOUT_S = 8.0."""
        from mcp_server.priority_guardian.tools.widget_tools import (
            add_priority,
            update_priority,
            delete_priority,
            add_deliverable,
            update_deliverable,
            delete_deliverable,
            add_goal,
            update_goal,
            delete_goal,
            connect_google_calendar,
            disconnect_google_calendar,
        )

        widget_modules = [
            add_priority,
            update_priority,
            delete_priority,
            add_deliverable,
            update_deliverable,
            delete_deliverable,
            add_goal,
            update_goal,
            delete_goal,
            connect_google_calendar,
            disconnect_google_calendar,
        ]

        for module in widget_modules:
            assert hasattr(module, "TIMEOUT_S"), f"{module.__name__} missing TIMEOUT_S"
            assert module.TIMEOUT_S == 8.0, f"{module.__name__} TIMEOUT_S != 8.0"


# =============================================================================
# No BACKEND_TIMEOUT Tests
# =============================================================================


class TestNoBackendTimeout:
    """Test that BACKEND_TIMEOUT has been removed from all files."""

    def test_get_weekly_report_no_backend_timeout(self):
        """get_weekly_report should not have BACKEND_TIMEOUT."""
        from mcp_server.priority_guardian.tools import get_weekly_report

        assert not hasattr(get_weekly_report, "BACKEND_TIMEOUT")

    def test_onboarding_calendar_setup_no_backend_timeout(self):
        """onboarding_calendar_setup should not have BACKEND_TIMEOUT."""
        from mcp_server.priority_guardian.tools import onboarding_calendar_setup

        assert not hasattr(onboarding_calendar_setup, "BACKEND_TIMEOUT")


# =============================================================================
# Static Check: No Bare Backend Calls
# =============================================================================


class TestNoBareBackendCalls:
    """
    ADR-mandated static check: all backend_get/backend_post/backend_put/backend_delete
    calls must be wrapped with asyncio.wait_for or _call_with_timeout.

    This prevents future regressions where a tool file has a bare backend call
    that falls through to the default httpx timeout.

    Exemptions:
    - get_priorities.py: Uses its own _fetch_with_timeout helper with parallel gather
    """

    def test_all_tool_files_have_timeout_wrapped_backend_calls(self):
        """Every tool file with backend calls must have asyncio.wait_for or _call_with_timeout."""
        from pathlib import Path
        import re

        tools_dir = Path(__file__).parent.parent.parent.parent / "mcp_server" / "priority_guardian" / "tools"

        # Files that are exempt from this check
        exempt_files = {
            "__init__.py",  # No handler
            "base.py",  # No handler
            "get_priorities.py",  # Uses _fetch_with_timeout with asyncio.gather
        }

        # Patterns to detect backend calls
        backend_call_pattern = re.compile(
            r"await\s+backend_(get|post|put|delete)\s*\("
        )

        # Patterns that indicate proper timeout wrapping
        timeout_wrapper_patterns = [
            re.compile(r"asyncio\.wait_for"),
            re.compile(r"_call_with_timeout"),
            re.compile(r"_fetch_with_timeout"),
        ]

        violations = []

        # Check main tools directory
        for file_path in tools_dir.glob("*.py"):
            if file_path.name in exempt_files:
                continue

            content = file_path.read_text()

            # Check if file has any backend calls
            has_backend_calls = bool(backend_call_pattern.search(content))

            if has_backend_calls:
                # Check if file has timeout wrapper
                has_timeout_wrapper = any(
                    pattern.search(content)
                    for pattern in timeout_wrapper_patterns
                )

                if not has_timeout_wrapper:
                    violations.append(f"{file_path.name}: has backend calls but no timeout wrapper")

        # Check widget_tools directory
        widget_tools_dir = tools_dir / "widget_tools"
        if widget_tools_dir.exists():
            for file_path in widget_tools_dir.glob("*.py"):
                if file_path.name == "__init__.py":
                    continue

                content = file_path.read_text()

                has_backend_calls = bool(backend_call_pattern.search(content))

                if has_backend_calls:
                    has_timeout_wrapper = any(
                        pattern.search(content)
                        for pattern in timeout_wrapper_patterns
                    )

                    if not has_timeout_wrapper:
                        violations.append(
                            f"widget_tools/{file_path.name}: has backend calls but no timeout wrapper"
                        )

        if violations:
            pytest.fail(
                "The following tool files have bare backend calls without timeout wrapping:\n"
                + "\n".join(f"  - {v}" for v in violations)
            )
