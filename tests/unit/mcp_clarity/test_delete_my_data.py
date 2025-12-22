"""
Unit tests for delete_my_data MCP tool.

Tests:
1. Tool has correct annotations
2. Tool input schema requires confirm
3. Tool description is accurate
4. Confirm check happens before backend call
5. Response formats for all statuses
"""

import pytest
from unittest.mock import AsyncMock, patch

from mcp_server.clarity.tools.delete_my_data import (
    handle,
    NAME,
    DESCRIPTION,
    INPUT_SCHEMA,
    REQUIRED_SCOPES,
)
from mcp_server.clarity.tools import get_tool


# ============================================================================
# Tool Registration Tests
# ============================================================================


class TestToolRegistration:
    """Tests for tool registration and metadata."""

    def test_tool_is_registered(self):
        """Tool is registered in the registry."""
        tool = get_tool("delete_my_data")
        assert tool is not None
        assert tool.name == "delete_my_data"

    def test_tool_has_correct_annotations(self):
        """Tool has correct compliance annotations."""
        tool = get_tool("delete_my_data")
        assert tool.read_only_hint is False  # Mutates state
        assert tool.destructive_hint is True  # Permanently deletes
        assert tool.open_world_hint is False  # Only own backend

    def test_tool_description_contains_required_text(self):
        """Tool description mentions permanent deletion and confirm."""
        assert "permanently" in DESCRIPTION.lower()
        assert "confirm" in DESCRIPTION.lower()

    def test_input_schema_requires_confirm(self):
        """Input schema has confirm as required boolean."""
        assert "confirm" in INPUT_SCHEMA["properties"]
        assert INPUT_SCHEMA["properties"]["confirm"]["type"] == "boolean"
        assert "confirm" in INPUT_SCHEMA["required"]

    def test_required_scope_is_clarity_write(self):
        """Tool requires clarity.write scope."""
        assert "clarity.write" in REQUIRED_SCOPES


# ============================================================================
# Confirmation Logic Tests
# ============================================================================


class TestConfirmationLogic:
    """Tests for confirmation check behavior."""

    @pytest.mark.asyncio
    async def test_confirm_false_returns_rejected(self):
        """confirm=false returns rejected status without calling backend."""
        with patch("mcp_server.clarity.tools.delete_my_data.delete_cluster") as mock_delete:
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={"confirm": False},
            )

        # Backend should NOT be called
        mock_delete.assert_not_called()

        # Response should be rejected
        assert result.isError is False or result.isError is None  # Not an error
        assert result.structuredContent["status"] == "rejected"
        assert "confirm=true" in result.structuredContent["message"]

    @pytest.mark.asyncio
    async def test_confirm_missing_returns_rejected(self):
        """Missing confirm parameter returns rejected status."""
        with patch("mcp_server.clarity.tools.delete_my_data.delete_cluster") as mock_delete:
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={},  # No confirm
            )

        # Backend should NOT be called
        mock_delete.assert_not_called()

        # Response should be rejected
        assert result.structuredContent["status"] == "rejected"

    @pytest.mark.asyncio
    async def test_confirm_true_calls_backend(self):
        """confirm=true calls the backend."""
        mock_response = {
            "status": "deleted",
            "message": "Your saved Clarity board has been permanently deleted.",
            "deleted": {"boards": 1},
        }
        with patch("mcp_server.clarity.tools.delete_my_data.delete_cluster", new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = mock_response
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={"confirm": True},
            )

        # Backend SHOULD be called
        mock_delete.assert_called_once_with(user_id="test-user", correlation_id="test-corr")


# ============================================================================
# Response Format Tests
# ============================================================================


class TestResponseFormats:
    """Tests for response format based on backend status."""

    @pytest.mark.asyncio
    async def test_deleted_status_response(self):
        """Deleted status returns proper response."""
        mock_response = {
            "status": "deleted",
            "message": "Your saved Clarity board has been permanently deleted.",
            "deleted": {"boards": 1},
        }
        with patch("mcp_server.clarity.tools.delete_my_data.delete_cluster", new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = mock_response
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={"confirm": True},
            )

        assert result.isError is None or result.isError is False
        assert result.structuredContent["status"] == "deleted"
        assert result.structuredContent["deleted"] == {"boards": 1}
        assert "assistant_guidance" in result.structuredContent

    @pytest.mark.asyncio
    async def test_no_data_status_response(self):
        """No data status returns proper response."""
        mock_response = {
            "status": "no_data",
            "message": "No saved board found. Nothing to delete.",
        }
        with patch("mcp_server.clarity.tools.delete_my_data.delete_cluster", new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = mock_response
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={"confirm": True},
            )

        assert result.isError is None or result.isError is False
        assert result.structuredContent["status"] == "no_data"
        assert "assistant_guidance" in result.structuredContent

    @pytest.mark.asyncio
    async def test_error_status_response(self):
        """Error status returns proper error response."""
        mock_response = {
            "status": "error",
            "message": "Failed to delete data. Please try again.",
        }
        with patch("mcp_server.clarity.tools.delete_my_data.delete_cluster", new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = mock_response
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={"confirm": True},
            )

        assert result.isError is True
        assert result.structuredContent["status"] == "error"
        assert "assistant_guidance" in result.structuredContent


# ============================================================================
# Idempotency Tests
# ============================================================================


class TestIdempotency:
    """Tests for idempotent behavior."""

    @pytest.mark.asyncio
    async def test_double_delete_returns_no_data(self):
        """Calling delete twice returns no_data on second call (idempotent)."""
        # First call: deleted
        mock_deleted = {
            "status": "deleted",
            "message": "Your saved Clarity board has been permanently deleted.",
            "deleted": {"boards": 1},
        }
        # Second call: no_data
        mock_no_data = {
            "status": "no_data",
            "message": "No saved board found. Nothing to delete.",
        }

        with patch("mcp_server.clarity.tools.delete_my_data.delete_cluster", new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = mock_deleted
            result1 = await handle(
                user_id="test-user",
                correlation_id="test-corr-1",
                arguments={"confirm": True},
            )

            mock_delete.return_value = mock_no_data
            result2 = await handle(
                user_id="test-user",
                correlation_id="test-corr-2",
                arguments={"confirm": True},
            )

        assert result1.structuredContent["status"] == "deleted"
        assert result2.structuredContent["status"] == "no_data"
        # Neither should be an error
        assert result1.isError is None or result1.isError is False
        assert result2.isError is None or result2.isError is False
