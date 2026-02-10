"""
Unit tests for Priority Guardian private MCP tool handlers (Widget B).

Tests the 6 private widget-only tools in isolation by mocking backend calls:
- add_priority: Creates new priority via widget
- update_priority: Edits priority fields
- delete_priority: Removes priority
- add_deliverable: Adds deliverable to priority
- update_deliverable: Edits deliverable (toggle done, rename)
- delete_deliverable: Removes deliverable
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4
import httpx

from mcp import types as mcp_types


def make_http_status_error(status_code: int, message: str = "") -> httpx.HTTPStatusError:
    """Create a mock HTTPStatusError for testing."""
    mock_response = MagicMock()
    mock_response.status_code = status_code
    return httpx.HTTPStatusError(
        message=message or f"{status_code} Error",
        request=MagicMock(),
        response=mock_response,
    )


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def user_id():
    """Test user ID."""
    return str(uuid4())


@pytest.fixture
def correlation_id():
    """Test correlation ID."""
    return "test-correlation-id"


@pytest.fixture
def mock_fresh_priority_list():
    """Factory for fresh priority list response (from GET endpoint)."""
    def _make_response(priorities=None, google_connected=True):
        if priorities is None:
            priorities = [{
                "id": str(uuid4()),
                "name": "Test Priority",
                "type": "deadline",
                "calendar_keyword": "P1",
                "status": "active",
                "deadline": "2026-03-15",
                "weekly_hour_target": None,
                "checkpoint_date": None,
                "desired_result": None,
                "deliverables": [],
                "created_at": "2026-02-08T12:00:00Z",
            }]
        return {
            "success": True,
            "data": {
                "priorities": priorities,
                "google_connection": {
                    "connected": google_connected,
                    "connected_at": "2026-01-01T00:00:00Z" if google_connected else None,
                },
                "available_keywords": ["P2", "P3"],
            },
        }
    return _make_response


@pytest.fixture
def mock_create_response():
    """Factory for create priority backend response."""
    def _make_response(keyword="P1"):
        return {
            "success": True,
            "data": {
                "priority": {
                    "id": str(uuid4()),
                    "calendar_keyword": keyword,
                },
            },
        }
    return _make_response


# ==============================================================================
# add_priority tool tests
# ==============================================================================


class TestAddPriorityTool:
    """Tests for add_priority MCP tool handler."""

    @pytest.mark.asyncio
    async def test_success_returns_fresh_list(
        self, user_id, correlation_id, mock_create_response, mock_fresh_priority_list
    ):
        """Success response returns fresh priority list with widget template."""
        from mcp_server.priority_guardian.tools.add_priority import handle

        with patch(
            "mcp_server.priority_guardian.tools.add_priority.backend_post",
            new_callable=AsyncMock,
            return_value=mock_create_response(keyword="P1"),
        ), patch(
            "mcp_server.priority_guardian.http_client.backend_get",
            new_callable=AsyncMock,
            return_value=mock_fresh_priority_list(),
        ):
            result = await handle(
                user_id=user_id,
                correlation_id=correlation_id,
                arguments={
                    "name": "Test Priority",
                    "type": "deadline",
                    "deadline": "2026-03-15",
                },
            )

        assert isinstance(result, mcp_types.CallToolResult)
        assert result.structuredContent["success"] is True
        assert "data" in result.structuredContent
        assert "priorities" in result.structuredContent["data"]
        assert "_meta" in result.structuredContent
        assert result.structuredContent["_meta"]["openai/outputTemplate"] == "ui://widget/pg-dashboard.html"

    @pytest.mark.asyncio
    async def test_missing_name_raises_tool_usage_error(self, user_id, correlation_id):
        """Missing name raises ToolUsageError."""
        from mcp_server.priority_guardian.tools.add_priority import handle
        from mcp_server.priority_guardian.tools.base import ToolUsageError

        with pytest.raises(ToolUsageError, match="name is required"):
            await handle(
                user_id=user_id,
                correlation_id=correlation_id,
                arguments={"type": "deadline", "deadline": "2026-03-15"},
            )

    @pytest.mark.asyncio
    async def test_missing_type_raises_tool_usage_error(self, user_id, correlation_id):
        """Missing type raises ToolUsageError."""
        from mcp_server.priority_guardian.tools.add_priority import handle
        from mcp_server.priority_guardian.tools.base import ToolUsageError

        with pytest.raises(ToolUsageError, match="type is required"):
            await handle(
                user_id=user_id,
                correlation_id=correlation_id,
                arguments={"name": "Test"},
            )

    @pytest.mark.asyncio
    async def test_deadline_type_missing_deadline_raises_error(self, user_id, correlation_id):
        """Deadline type without deadline raises ToolUsageError."""
        from mcp_server.priority_guardian.tools.add_priority import handle
        from mcp_server.priority_guardian.tools.base import ToolUsageError

        with pytest.raises(ToolUsageError, match="deadline is required"):
            await handle(
                user_id=user_id,
                correlation_id=correlation_id,
                arguments={"name": "Test", "type": "deadline"},
            )

    @pytest.mark.asyncio
    async def test_flexible_type_missing_fields_raises_error(self, user_id, correlation_id):
        """Flexible type without required fields raises ToolUsageError."""
        from mcp_server.priority_guardian.tools.add_priority import handle
        from mcp_server.priority_guardian.tools.base import ToolUsageError

        with pytest.raises(ToolUsageError, match="weekly_hour_target is required"):
            await handle(
                user_id=user_id,
                correlation_id=correlation_id,
                arguments={"name": "Test", "type": "flexible"},
            )

    @pytest.mark.asyncio
    async def test_max_priorities_reached_returns_user_message(
        self, user_id, correlation_id
    ):
        """409 MAX_PRIORITIES_REACHED returns friendly error message."""
        from mcp_server.priority_guardian.tools.add_priority import handle
        from mcp_server.priority_guardian.tools.base import ToolUsageError

        with patch(
            "mcp_server.priority_guardian.tools.add_priority.backend_post",
            new_callable=AsyncMock,
            side_effect=make_http_status_error(409, "MAX_PRIORITIES_REACHED"),
        ):
            with pytest.raises(ToolUsageError, match="already have 3 active priorities"):
                await handle(
                    user_id=user_id,
                    correlation_id=correlation_id,
                    arguments={
                        "name": "Test",
                        "type": "deadline",
                        "deadline": "2026-03-15",
                    },
                )


# ==============================================================================
# update_priority tool tests
# ==============================================================================


class TestUpdatePriorityTool:
    """Tests for update_priority MCP tool handler."""

    @pytest.mark.asyncio
    async def test_success_returns_fresh_list(
        self, user_id, correlation_id, mock_fresh_priority_list
    ):
        """Success response returns fresh priority list from mutation response."""
        from mcp_server.priority_guardian.tools.update_priority import handle

        # Mutation endpoints now return the full priority list directly
        with patch(
            "mcp_server.priority_guardian.tools.update_priority.backend_put",
            new_callable=AsyncMock,
            return_value=mock_fresh_priority_list(),
        ):
            result = await handle(
                user_id=user_id,
                correlation_id=correlation_id,
                arguments={
                    "priority_id": str(uuid4()),
                    "name": "Updated Name",
                },
            )

        assert isinstance(result, mcp_types.CallToolResult)
        assert result.structuredContent["success"] is True
        assert "data" in result.structuredContent

    @pytest.mark.asyncio
    async def test_missing_priority_id_raises_error(self, user_id, correlation_id):
        """Missing priority_id raises ToolUsageError."""
        from mcp_server.priority_guardian.tools.update_priority import handle
        from mcp_server.priority_guardian.tools.base import ToolUsageError

        with pytest.raises(ToolUsageError, match="priority_id is required"):
            await handle(
                user_id=user_id,
                correlation_id=correlation_id,
                arguments={"name": "Updated"},
            )

    @pytest.mark.asyncio
    async def test_404_returns_not_found_message(self, user_id, correlation_id):
        """404 returns 'Priority not found' message."""
        from mcp_server.priority_guardian.tools.update_priority import handle
        from mcp_server.priority_guardian.tools.base import ToolUsageError

        with patch(
            "mcp_server.priority_guardian.tools.update_priority.backend_put",
            new_callable=AsyncMock,
            side_effect=make_http_status_error(404, "Not Found"),
        ):
            with pytest.raises(ToolUsageError, match="Priority not found"):
                await handle(
                    user_id=user_id,
                    correlation_id=correlation_id,
                    arguments={
                        "priority_id": str(uuid4()),
                        "name": "Updated",
                    },
                )

    @pytest.mark.asyncio
    async def test_422_returns_validation_message(self, user_id, correlation_id):
        """422 returns 'Invalid field' message."""
        from mcp_server.priority_guardian.tools.update_priority import handle
        from mcp_server.priority_guardian.tools.base import ToolUsageError

        with patch(
            "mcp_server.priority_guardian.tools.update_priority.backend_put",
            new_callable=AsyncMock,
            side_effect=make_http_status_error(422, "Unprocessable Entity"),
        ):
            with pytest.raises(ToolUsageError, match="Invalid field"):
                await handle(
                    user_id=user_id,
                    correlation_id=correlation_id,
                    arguments={
                        "priority_id": str(uuid4()),
                        "weekly_hour_target": 10.0,  # Wrong type
                    },
                )


# ==============================================================================
# delete_priority tool tests
# ==============================================================================


class TestDeletePriorityTool:
    """Tests for delete_priority MCP tool handler."""

    @pytest.mark.asyncio
    async def test_success_returns_fresh_list(
        self, user_id, correlation_id, mock_fresh_priority_list
    ):
        """Success response returns fresh (empty) priority list from mutation response."""
        from mcp_server.priority_guardian.tools.delete_priority import handle

        empty_list = mock_fresh_priority_list(priorities=[])

        # Mutation endpoints now return the full priority list directly
        with patch(
            "mcp_server.priority_guardian.tools.delete_priority.backend_delete",
            new_callable=AsyncMock,
            return_value=empty_list,
        ):
            result = await handle(
                user_id=user_id,
                correlation_id=correlation_id,
                arguments={
                    "priority_id": str(uuid4()),
                    "confirm": True,
                },
            )

        assert isinstance(result, mcp_types.CallToolResult)
        assert result.structuredContent["success"] is True
        assert len(result.structuredContent["data"]["priorities"]) == 0

    @pytest.mark.asyncio
    async def test_missing_priority_id_raises_error(self, user_id, correlation_id):
        """Missing priority_id raises ToolUsageError."""
        from mcp_server.priority_guardian.tools.delete_priority import handle
        from mcp_server.priority_guardian.tools.base import ToolUsageError

        with pytest.raises(ToolUsageError, match="priority_id is required"):
            await handle(
                user_id=user_id,
                correlation_id=correlation_id,
                arguments={"confirm": True},
            )

    @pytest.mark.asyncio
    async def test_missing_confirm_raises_error(self, user_id, correlation_id):
        """Missing confirm raises ToolUsageError."""
        from mcp_server.priority_guardian.tools.delete_priority import handle
        from mcp_server.priority_guardian.tools.base import ToolUsageError

        with pytest.raises(ToolUsageError, match="confirm"):
            await handle(
                user_id=user_id,
                correlation_id=correlation_id,
                arguments={"priority_id": str(uuid4())},
            )

    @pytest.mark.asyncio
    async def test_404_returns_not_found_message(self, user_id, correlation_id):
        """404 returns 'Priority not found' message."""
        from mcp_server.priority_guardian.tools.delete_priority import handle
        from mcp_server.priority_guardian.tools.base import ToolUsageError

        with patch(
            "mcp_server.priority_guardian.tools.delete_priority.backend_delete",
            new_callable=AsyncMock,
            side_effect=make_http_status_error(404, "Not Found"),
        ):
            with pytest.raises(ToolUsageError, match="Priority not found"):
                await handle(
                    user_id=user_id,
                    correlation_id=correlation_id,
                    arguments={
                        "priority_id": str(uuid4()),
                        "confirm": True,
                    },
                )


# ==============================================================================
# add_deliverable tool tests
# ==============================================================================


class TestAddDeliverableTool:
    """Tests for add_deliverable MCP tool handler."""

    @pytest.mark.asyncio
    async def test_success_returns_fresh_list(
        self, user_id, correlation_id, mock_fresh_priority_list
    ):
        """Success response returns fresh priority list with new deliverable."""
        from mcp_server.priority_guardian.tools.add_deliverable import handle

        # Response with deliverable added - mutation endpoints return full list
        priority_with_deliverable = mock_fresh_priority_list()
        priority_with_deliverable["data"]["priorities"][0]["deliverables"] = [
            {"id": str(uuid4()), "name": "New Task", "done": False}
        ]

        with patch(
            "mcp_server.priority_guardian.tools.add_deliverable.backend_post",
            new_callable=AsyncMock,
            return_value=priority_with_deliverable,
        ):
            result = await handle(
                user_id=user_id,
                correlation_id=correlation_id,
                arguments={
                    "priority_id": str(uuid4()),
                    "name": "New Task",
                },
            )

        assert isinstance(result, mcp_types.CallToolResult)
        assert result.structuredContent["success"] is True
        deliverables = result.structuredContent["data"]["priorities"][0]["deliverables"]
        assert len(deliverables) == 1
        assert deliverables[0]["name"] == "New Task"

    @pytest.mark.asyncio
    async def test_missing_priority_id_raises_error(self, user_id, correlation_id):
        """Missing priority_id raises ToolUsageError."""
        from mcp_server.priority_guardian.tools.add_deliverable import handle
        from mcp_server.priority_guardian.tools.base import ToolUsageError

        with pytest.raises(ToolUsageError, match="priority_id is required"):
            await handle(
                user_id=user_id,
                correlation_id=correlation_id,
                arguments={"name": "Task"},
            )

    @pytest.mark.asyncio
    async def test_missing_name_raises_error(self, user_id, correlation_id):
        """Missing name raises ToolUsageError."""
        from mcp_server.priority_guardian.tools.add_deliverable import handle
        from mcp_server.priority_guardian.tools.base import ToolUsageError

        with pytest.raises(ToolUsageError, match="name is required"):
            await handle(
                user_id=user_id,
                correlation_id=correlation_id,
                arguments={"priority_id": str(uuid4())},
            )


# ==============================================================================
# update_deliverable tool tests
# ==============================================================================


class TestUpdateDeliverableTool:
    """Tests for update_deliverable MCP tool handler."""

    @pytest.mark.asyncio
    async def test_toggle_done_success(
        self, user_id, correlation_id, mock_fresh_priority_list
    ):
        """Toggling done returns fresh list from mutation response."""
        from mcp_server.priority_guardian.tools.update_deliverable import handle

        response = mock_fresh_priority_list()
        response["data"]["priorities"][0]["deliverables"] = [
            {"id": str(uuid4()), "name": "Task", "done": True}
        ]

        # Mutation endpoints now return the full priority list directly
        with patch(
            "mcp_server.priority_guardian.tools.update_deliverable.backend_put",
            new_callable=AsyncMock,
            return_value=response,
        ):
            result = await handle(
                user_id=user_id,
                correlation_id=correlation_id,
                arguments={
                    "deliverable_id": str(uuid4()),
                    "done": True,
                },
            )

        assert isinstance(result, mcp_types.CallToolResult)
        assert result.structuredContent["success"] is True

    @pytest.mark.asyncio
    async def test_missing_deliverable_id_raises_error(self, user_id, correlation_id):
        """Missing deliverable_id raises ToolUsageError."""
        from mcp_server.priority_guardian.tools.update_deliverable import handle
        from mcp_server.priority_guardian.tools.base import ToolUsageError

        with pytest.raises(ToolUsageError, match="deliverable_id is required"):
            await handle(
                user_id=user_id,
                correlation_id=correlation_id,
                arguments={"done": True},
            )

    @pytest.mark.asyncio
    async def test_404_returns_not_found_message(self, user_id, correlation_id):
        """404 returns 'Deliverable not found' message."""
        from mcp_server.priority_guardian.tools.update_deliverable import handle
        from mcp_server.priority_guardian.tools.base import ToolUsageError

        with patch(
            "mcp_server.priority_guardian.tools.update_deliverable.backend_put",
            new_callable=AsyncMock,
            side_effect=make_http_status_error(404, "Not Found"),
        ):
            with pytest.raises(ToolUsageError, match="Deliverable not found"):
                await handle(
                    user_id=user_id,
                    correlation_id=correlation_id,
                    arguments={
                        "deliverable_id": str(uuid4()),
                        "done": True,
                    },
                )


# ==============================================================================
# delete_deliverable tool tests
# ==============================================================================


class TestDeleteDeliverableTool:
    """Tests for delete_deliverable MCP tool handler."""

    @pytest.mark.asyncio
    async def test_success_returns_fresh_list(
        self, user_id, correlation_id, mock_fresh_priority_list
    ):
        """Success returns fresh list without deleted deliverable from mutation response."""
        from mcp_server.priority_guardian.tools.delete_deliverable import handle

        # Mutation endpoints now return the full priority list directly
        with patch(
            "mcp_server.priority_guardian.tools.delete_deliverable.backend_delete",
            new_callable=AsyncMock,
            return_value=mock_fresh_priority_list(),
        ):
            result = await handle(
                user_id=user_id,
                correlation_id=correlation_id,
                arguments={
                    "deliverable_id": str(uuid4()),
                    "confirm": True,
                },
            )

        assert isinstance(result, mcp_types.CallToolResult)
        assert result.structuredContent["success"] is True

    @pytest.mark.asyncio
    async def test_missing_deliverable_id_raises_error(self, user_id, correlation_id):
        """Missing deliverable_id raises ToolUsageError."""
        from mcp_server.priority_guardian.tools.delete_deliverable import handle
        from mcp_server.priority_guardian.tools.base import ToolUsageError

        with pytest.raises(ToolUsageError, match="deliverable_id is required"):
            await handle(
                user_id=user_id,
                correlation_id=correlation_id,
                arguments={"confirm": True},
            )

    @pytest.mark.asyncio
    async def test_missing_confirm_raises_error(self, user_id, correlation_id):
        """Missing confirm raises ToolUsageError."""
        from mcp_server.priority_guardian.tools.delete_deliverable import handle
        from mcp_server.priority_guardian.tools.base import ToolUsageError

        with pytest.raises(ToolUsageError, match="confirm"):
            await handle(
                user_id=user_id,
                correlation_id=correlation_id,
                arguments={"deliverable_id": str(uuid4())},
            )

    @pytest.mark.asyncio
    async def test_404_returns_not_found_message(self, user_id, correlation_id):
        """404 returns 'Deliverable not found' message."""
        from mcp_server.priority_guardian.tools.delete_deliverable import handle
        from mcp_server.priority_guardian.tools.base import ToolUsageError

        with patch(
            "mcp_server.priority_guardian.tools.delete_deliverable.backend_delete",
            new_callable=AsyncMock,
            side_effect=make_http_status_error(404, "Not Found"),
        ):
            with pytest.raises(ToolUsageError, match="Deliverable not found"):
                await handle(
                    user_id=user_id,
                    correlation_id=correlation_id,
                    arguments={
                        "deliverable_id": str(uuid4()),
                        "confirm": True,
                    },
                )
