"""
Unit tests for Clarity MCP tool dispatcher.

Tests fail-closed behavior and security boundaries at the dispatcher level.
"""

import pytest
from unittest.mock import ANY, MagicMock, patch

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


def assert_error(result):
    """Assert result is an error with content."""
    assert result.isError is True
    assert result.content


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

        assert_error(result)

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

        assert_error(result)

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

        assert_error(result)


class TestDispatcherAuthBoundary:
    """Tests authentication boundary at dispatcher level."""

    @pytest.mark.asyncio
    async def test_known_tool_calls_authenticate(self):
        """Known tools must go through authentication."""
        req = _make_call_tool_request(
            tool_name="organize_thoughts",
            arguments={"thoughts_exhausted": True, "clusters": []},
            meta={"headers": {"authorization": "Bearer test-token"}},
        )

        with patch("mcp_server.clarity.handlers.tools.authenticate_request") as mock_auth:
            # Simulate auth failure to prevent actual tool execution
            from mcp_server.clarity.mcp_auth import UnauthorizedError
            mock_auth.side_effect = UnauthorizedError("invalid_token", "Test auth failure")

            result = await call_tool_request(req)

            # authenticate_request WAS called with correct tool name
            mock_auth.assert_called_once_with("organize_thoughts", ANY)

        assert_error(result)

    @pytest.mark.asyncio
    async def test_auth_failure_prevents_tool_execution(self):
        """Auth failure must prevent tool handler execution."""
        req = _make_call_tool_request(
            tool_name="organize_thoughts",
            arguments={"thoughts_exhausted": True, "clusters": []},
        )

        # Create a mock tool definition with a mock handle
        from mcp_server.clarity.tools import TOOL_REGISTRY
        from mcp_server.clarity.tools.base import ToolDefinition
        from unittest.mock import AsyncMock

        mock_handle = AsyncMock()
        mock_tool = ToolDefinition(
            name="organize_thoughts",
            description="Test tool",
            input_schema={},
            required_scopes=["clarity.write"],
            widget_uri=None,
            handle=mock_handle,
        )

        with patch("mcp_server.clarity.handlers.tools.authenticate_request") as mock_auth:
            from mcp_server.clarity.mcp_auth import UnauthorizedError
            mock_auth.side_effect = UnauthorizedError("invalid_token", "Test auth failure")

            with patch.dict(TOOL_REGISTRY, {"organize_thoughts": mock_tool}):
                result = await call_tool_request(req)

                # Tool handler should NOT be called after auth failure
                mock_handle.assert_not_called()

        assert_error(result)
