"""
Unit tests for Clarity MCP tool dispatcher.

Tests fail-closed behavior and security boundaries at the dispatcher level.
"""

import pytest
from unittest.mock import MagicMock, patch

from mcp_server.clarity.handlers.tools import call_tool_request


def _make_call_tool_request(tool_name: str, arguments: dict = None, meta: dict = None):
    """Build a mock CallToolRequest."""
    params = MagicMock()
    params.name = tool_name
    params.arguments = arguments or {}
    params._meta = meta or {}

    req = MagicMock()
    req.params = params
    return req


class TestUnknownToolFailsClosed:
    """Tests that unknown tools fail closed at dispatcher boundary."""

    @pytest.mark.asyncio
    async def test_unknown_tool_fails_closed_at_dispatcher(self):
        """Unknown tools must fail closed before authentication."""
        req = _make_call_tool_request(
            tool_name="nonexistent_tool_that_does_not_exist",
            arguments={"some": "data"},
        )

        result = await call_tool_request(req)

        assert result.isError is True
        assert "Unknown tool" in result.content[0].text

    @pytest.mark.asyncio
    async def test_unknown_tool_never_calls_authenticate(self):
        """Unknown tools must not reach authentication logic."""
        req = _make_call_tool_request(
            tool_name="nonexistent_tool",
            arguments={},
        )

        with patch("mcp_server.clarity.handlers.tools.authenticate_request") as mock_auth:
            result = await call_tool_request(req)

            # authenticate_request should NOT be called for unknown tools
            mock_auth.assert_not_called()

        assert result.isError is True

    @pytest.mark.asyncio
    async def test_unknown_tool_never_reaches_handler(self):
        """Unknown tools must never reach any tool handler."""
        req = _make_call_tool_request(
            tool_name="fake_tool",
            arguments={"data": "test"},
        )

        # Patch the tool registry's get_tool to track calls
        with patch("mcp_server.clarity.handlers.tools.get_tool") as mock_get_tool:
            mock_get_tool.return_value = None  # Tool not found

            result = await call_tool_request(req)

            # get_tool was called (to check if tool exists)
            mock_get_tool.assert_called_once_with("fake_tool")

        # But result is an error
        assert result.isError is True
        assert "Unknown tool" in result.content[0].text

    @pytest.mark.asyncio
    async def test_unknown_tool_does_not_trigger_persistence(self):
        """Unknown tools must never trigger persistence."""
        req = _make_call_tool_request(
            tool_name="unknown_tool",
            arguments={},
        )

        with patch("mcp_server.clarity.persistence.persist_cluster") as mock_persist:
            result = await call_tool_request(req)

            # persist_cluster should NOT be called
            mock_persist.assert_not_called()

        assert result.isError is True


class TestDispatcherAuthBoundary:
    """Tests authentication boundary at dispatcher level."""

    @pytest.mark.asyncio
    async def test_known_tool_calls_authenticate(self):
        """Known tools must go through authentication."""
        req = _make_call_tool_request(
            tool_name="cluster_raw_thoughts",
            arguments={"thoughts_exhausted": True, "clusters": []},
            meta={"headers": {"authorization": "Bearer test-token"}},
        )

        with patch("mcp_server.clarity.handlers.tools.authenticate_request") as mock_auth:
            # Simulate auth failure to prevent actual tool execution
            from mcp_server.clarity.mcp_auth import UnauthorizedError
            mock_auth.side_effect = UnauthorizedError("invalid_token", "Test auth failure")

            result = await call_tool_request(req)

            # authenticate_request WAS called for known tool
            mock_auth.assert_called_once()

        assert result.isError is True

    @pytest.mark.asyncio
    async def test_auth_failure_prevents_tool_execution(self):
        """Auth failure must prevent tool handler execution."""
        req = _make_call_tool_request(
            tool_name="cluster_raw_thoughts",
            arguments={"thoughts_exhausted": True, "clusters": []},
        )

        with patch("mcp_server.clarity.handlers.tools.authenticate_request") as mock_auth:
            from mcp_server.clarity.mcp_auth import UnauthorizedError
            mock_auth.side_effect = UnauthorizedError("invalid_token", "Test auth failure")

            with patch("mcp_server.clarity.tools.cluster_raw_thoughts.handle") as mock_handle:
                result = await call_tool_request(req)

                # Tool handler should NOT be called after auth failure
                mock_handle.assert_not_called()

        assert result.isError is True
