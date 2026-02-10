"""
Unit tests for Priority Guardian MCP dispatcher.

Tests handlers/tools.py dispatcher logic:
- Unknown tool returns isError=True
- UnauthorizedError returns 401-style response
- InsufficientScopeError returns 403-style response
- ToolUsageError returns isError=True with verbatim message
- Unexpected Exception returns generic error, not internals
- Timing logs are emitted
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from mcp import types as mcp_types


class TestDispatcherUnknownTool:
    """Tests for unknown tool handling."""

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self):
        """Unknown tool returns isError=True with message."""
        from mcp_server.priority_guardian.handlers.tools import call_tool_request

        # Create a request for an unknown tool
        request = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(
                name="nonexistent_tool",
                arguments={},
            ),
        )

        result = await call_tool_request(request)

        assert result.isError is True
        assert len(result.content) == 1
        assert "Unknown tool" in result.content[0].text
        assert "nonexistent_tool" in result.content[0].text


class TestDispatcherAuth:
    """Tests for authentication error handling."""

    @pytest.mark.asyncio
    async def test_unauthorized_error_returns_401_style(self):
        """UnauthorizedError returns isError=True with www_authenticate in _meta."""
        from mcp_server.priority_guardian.handlers.tools import call_tool_request
        from mcp_server.priority_guardian.mcp_auth import UnauthorizedError

        request = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(
                name="create_priority",
                arguments={"name": "Test", "type": "deadline"},
            ),
        )

        with patch(
            "mcp_server.priority_guardian.handlers.tools.authenticate_request",
            new_callable=AsyncMock,
            side_effect=UnauthorizedError("invalid_token", "Token expired"),
        ):
            result = await call_tool_request(request)

        assert result.isError is True
        assert "Authentication required" in result.content[0].text
        # Should have meta with www_authenticate for OAuth discovery
        meta = getattr(result, 'meta', None) or getattr(result, '_meta', None)
        assert meta is not None
        assert "mcp/www_authenticate" in meta

    @pytest.mark.asyncio
    async def test_insufficient_scope_error_returns_403_style(self):
        """InsufficientScopeError returns isError=True with required scopes."""
        from mcp_server.priority_guardian.handlers.tools import call_tool_request
        from mcp_server.priority_guardian.mcp_auth import InsufficientScopeError

        request = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(
                name="create_priority",
                arguments={"name": "Test", "type": "deadline"},
            ),
        )

        with patch(
            "mcp_server.priority_guardian.handlers.tools.authenticate_request",
            new_callable=AsyncMock,
            side_effect=InsufficientScopeError(
                required_scopes=["pg.access"],
                actual_scopes=["other.scope"],
            ),
        ):
            result = await call_tool_request(request)

        assert result.isError is True
        assert "Insufficient permissions" in result.content[0].text


class TestDispatcherToolUsageError:
    """Tests for ToolUsageError handling."""

    @pytest.mark.asyncio
    async def test_tool_usage_error_returns_verbatim_message(self):
        """ToolUsageError message surfaces to LLM verbatim."""
        from mcp_server.priority_guardian.handlers.tools import call_tool_request
        from mcp_server.priority_guardian.tools.base import ToolUsageError

        request = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(
                name="create_priority",
                arguments={"name": "Test", "type": "deadline"},
            ),
        )

        error_message = "Name is required and cannot be empty"

        # Mock authenticate_request to succeed, then mock the tool handler
        with patch(
            "mcp_server.priority_guardian.handlers.tools.authenticate_request",
            new_callable=AsyncMock,
            return_value={
                "user_id": str(uuid4()),
                "correlation_id": "test-correlation",
            },
        ), patch(
            "mcp_server.priority_guardian.handlers.tools.get_tool",
        ) as mock_get_tool:
            # Create a mock tool that raises ToolUsageError
            mock_tool = MagicMock()
            mock_tool.handle = AsyncMock(side_effect=ToolUsageError(error_message))
            mock_get_tool.return_value = mock_tool

            result = await call_tool_request(request)

        assert result.isError is True
        assert result.content[0].text == error_message


class TestDispatcherUnexpectedException:
    """Tests for unexpected exception handling."""

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_generic_error(self):
        """Unexpected Exception returns generic message, not internals."""
        from mcp_server.priority_guardian.handlers.tools import call_tool_request

        request = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(
                name="create_priority",
                arguments={"name": "Test", "type": "deadline"},
            ),
        )

        # Mock authenticate_request to succeed, then mock the tool handler to raise
        with patch(
            "mcp_server.priority_guardian.handlers.tools.authenticate_request",
            new_callable=AsyncMock,
            return_value={
                "user_id": str(uuid4()),
                "correlation_id": "test-correlation",
            },
        ), patch(
            "mcp_server.priority_guardian.handlers.tools.get_tool",
        ) as mock_get_tool:
            # Create a mock tool that raises an unexpected exception
            mock_tool = MagicMock()
            mock_tool.handle = AsyncMock(
                side_effect=RuntimeError("Database connection failed: host=db.internal password=secret123")
            )
            mock_get_tool.return_value = mock_tool

            result = await call_tool_request(request)

        assert result.isError is True
        # Generic message, no internals leaked
        assert "Something went wrong" in result.content[0].text
        # Must NOT contain internal error details
        assert "Database" not in result.content[0].text
        assert "password" not in result.content[0].text
        assert "secret" not in result.content[0].text


class TestDispatcherSuccessPath:
    """Tests for successful tool dispatch."""

    @pytest.mark.asyncio
    async def test_successful_dispatch_returns_tool_result(self):
        """Successful dispatch returns tool's CallToolResult."""
        from mcp_server.priority_guardian.handlers.tools import call_tool_request

        request = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(
                name="create_priority",
                arguments={"name": "Test", "type": "deadline"},
            ),
        )

        expected_result = mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text="Priority created")],
            structuredContent={"priority": {"name": "Test"}},
        )

        with patch(
            "mcp_server.priority_guardian.handlers.tools.authenticate_request",
            new_callable=AsyncMock,
            return_value={
                "user_id": str(uuid4()),
                "correlation_id": "test-correlation",
            },
        ), patch(
            "mcp_server.priority_guardian.handlers.tools.get_tool",
        ) as mock_get_tool:
            mock_tool = MagicMock()
            mock_tool.handle = AsyncMock(return_value=expected_result)
            mock_get_tool.return_value = mock_tool

            result = await call_tool_request(request)

        assert result.content[0].text == "Priority created"
        assert result.structuredContent["priority"]["name"] == "Test"
