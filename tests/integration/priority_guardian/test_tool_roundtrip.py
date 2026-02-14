"""
Integration tests for Priority Guardian tool roundtrip.

Tests full dispatcher flow with mocked auth and backend:
- CallToolRequest → dispatcher → handler → CallToolResult
- Verifies response structure matches expectations
- CRUD cycle tests for Widget B private tools
"""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from mcp import types as mcp_types


class TestCreatePriorityRoundtrip:
    """Full roundtrip tests for create_priority tool."""

    @pytest.fixture
    def mock_auth_context(self):
        """Auth context returned by authenticate_request."""
        return {
            "user_id": str(uuid4()),
            "correlation_id": "test-correlation-id",
        }

    @pytest.fixture
    def mock_backend_success(self):
        """Successful backend response for create_priority."""
        return {
            "success": True,
            "data": {
                "priority": {
                    "id": str(uuid4()),
                    "name": "Ship MVP",
                    "type": "deadline",
                    "calendar_keyword": "P1",
                    "status": "active",
                    "deadline": "2026-03-15",
                    "weekly_hour_target": None,
                    "checkpoint_date": None,
                    "desired_result": None,
                    "deliverables": [],
                    "created_at": "2026-02-09T12:00:00Z",
                },
                "active_priority_count": 1,
                "available_keywords": ["P2", "P3"],
            },
        }

    @pytest.mark.asyncio
    async def test_create_priority_returns_structured_content(
        self, mock_auth_context, mock_backend_success
    ):
        """create_priority returns CallToolResult with structuredContent and assistant_guidance."""
        from mcp_server.priority_guardian.handlers.tools import call_tool_request

        request = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(
                name="create_priority",
                arguments={
                    "name": "Ship MVP",
                    "type": "deadline",
                    "deadline": "2026-03-15",
                },
            ),
        )

        with patch(
            "mcp_server.priority_guardian.handlers.tools.authenticate_request",
            new_callable=AsyncMock,
            return_value=mock_auth_context,
        ), patch(
            "mcp_server.priority_guardian.tools.create_priority.backend_post",
            new_callable=AsyncMock,
            return_value=mock_backend_success,
        ):
            result = await call_tool_request(request)

        # Verify structure
        assert isinstance(result, mcp_types.CallToolResult)
        assert result.isError is None or result.isError is False

        # Verify structuredContent
        sc = result.structuredContent
        assert sc is not None
        assert "priority" in sc
        assert "assistant_guidance" in sc
        assert sc["priority"]["calendar_keyword"] == "P1"

        # Verify content text
        assert len(result.content) == 1
        assert "Ship MVP" in result.content[0].text


class TestConnectGoogleCalendarRoundtrip:
    """Full roundtrip tests for connect_google_calendar tool."""

    @pytest.fixture
    def mock_auth_context(self):
        return {
            "user_id": str(uuid4()),
            "correlation_id": "test-correlation-id",
        }

    @pytest.mark.asyncio
    async def test_returns_connect_url_when_not_connected(self, mock_auth_context):
        """connect_google_calendar returns connect_url when not connected."""
        from mcp_server.priority_guardian.handlers.tools import call_tool_request

        request = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(
                name="connect_google_calendar",
                arguments={},
            ),
        )

        # Mock: not connected, return connect URL
        status_response = {"connected": False}
        initiate_response = {
            "connect_url": "https://example.com/oauth/connect?token=abc123",
            "token": "abc123",
            "expires_in": 600,
        }

        with patch(
            "mcp_server.priority_guardian.handlers.tools.authenticate_request",
            new_callable=AsyncMock,
            return_value=mock_auth_context,
        ), patch(
            "mcp_server.priority_guardian.tools.widget_tools.connect_google_calendar.backend_get",
            new_callable=AsyncMock,
            return_value=status_response,
        ), patch(
            "mcp_server.priority_guardian.tools.widget_tools.connect_google_calendar.backend_post",
            new_callable=AsyncMock,
            return_value=initiate_response,
        ):
            result = await call_tool_request(request)

        assert isinstance(result, mcp_types.CallToolResult)
        assert result.structuredContent["data"]["connect_url"] == initiate_response["connect_url"]

    @pytest.mark.asyncio
    async def test_returns_already_connected_when_connected(self, mock_auth_context):
        """connect_google_calendar returns already connected message."""
        from mcp_server.priority_guardian.handlers.tools import call_tool_request

        request = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(
                name="connect_google_calendar",
                arguments={},
            ),
        )

        # Mock: already connected
        status_response = {"connected": True, "connected_at": "2026-01-01T00:00:00Z"}

        with patch(
            "mcp_server.priority_guardian.handlers.tools.authenticate_request",
            new_callable=AsyncMock,
            return_value=mock_auth_context,
        ), patch(
            "mcp_server.priority_guardian.tools.widget_tools.connect_google_calendar.backend_get",
            new_callable=AsyncMock,
            return_value=status_response,
        ):
            result = await call_tool_request(request)

        assert isinstance(result, mcp_types.CallToolResult)
        assert result.structuredContent["data"]["status"] == "connected"


class TestDisconnectGoogleCalendarRoundtrip:
    """Full roundtrip tests for disconnect_google_calendar tool."""

    @pytest.fixture
    def mock_auth_context(self):
        return {
            "user_id": str(uuid4()),
            "correlation_id": "test-correlation-id",
        }

    @pytest.mark.asyncio
    async def test_requires_confirmation(self, mock_auth_context):
        """disconnect_google_calendar requires confirm=true."""
        from mcp_server.priority_guardian.handlers.tools import call_tool_request

        request = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(
                name="disconnect_google_calendar",
                arguments={"confirm": False},
            ),
        )

        with patch(
            "mcp_server.priority_guardian.handlers.tools.authenticate_request",
            new_callable=AsyncMock,
            return_value=mock_auth_context,
        ):
            result = await call_tool_request(request)

        assert isinstance(result, mcp_types.CallToolResult)
        # Should return error asking for confirmation
        assert result.isError is True
        assert result.structuredContent["error"]["code"] == "CONFIRMATION_REQUIRED"

    @pytest.mark.asyncio
    async def test_disconnects_when_confirmed(self, mock_auth_context):
        """disconnect_google_calendar disconnects when confirmed."""
        from mcp_server.priority_guardian.handlers.tools import call_tool_request

        request = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(
                name="disconnect_google_calendar",
                arguments={"confirm": True},
            ),
        )

        # Mock: connected, then disconnect succeeds
        status_response = {"connected": True}
        disconnect_response = {"success": True}

        with patch(
            "mcp_server.priority_guardian.handlers.tools.authenticate_request",
            new_callable=AsyncMock,
            return_value=mock_auth_context,
        ), patch(
            "mcp_server.priority_guardian.tools.widget_tools.disconnect_google_calendar.backend_get",
            new_callable=AsyncMock,
            return_value=status_response,
        ), patch(
            "mcp_server.priority_guardian.tools.widget_tools.disconnect_google_calendar.backend_post",
            new_callable=AsyncMock,
            return_value=disconnect_response,
        ):
            result = await call_tool_request(request)

        assert isinstance(result, mcp_types.CallToolResult)
        assert result.structuredContent["data"]["status"] == "disconnected"


# ==============================================================================
# Widget B CRUD Tool Roundtrip Tests
# ==============================================================================


class TestAddPriorityRoundtrip:
    """Full roundtrip tests for add_priority (widget-only) tool."""

    @pytest.fixture
    def mock_auth_context(self):
        return {
            "user_id": str(uuid4()),
            "correlation_id": "test-correlation-id",
        }

    @pytest.fixture
    def mock_priority_id(self):
        return str(uuid4())

    @pytest.mark.asyncio
    async def test_add_priority_returns_fresh_list(self, mock_auth_context, mock_priority_id):
        """add_priority returns fresh priority list with new priority."""
        from mcp_server.priority_guardian.handlers.tools import call_tool_request

        request = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(
                name="add_priority",
                arguments={
                    "name": "New Priority",
                    "type": "deadline",
                    "deadline": "2026-04-15",
                },
            ),
        )

        create_response = {
            "success": True,
            "data": {
                "priority": {
                    "id": mock_priority_id,
                    "calendar_keyword": "P1",
                },
            },
        }

        fresh_list_response = {
            "success": True,
            "data": {
                "priorities": [
                    {
                        "id": mock_priority_id,
                        "name": "New Priority",
                        "type": "deadline",
                        "calendar_keyword": "P1",
                        "status": "active",
                        "deadline": "2026-04-15",
                        "weekly_hour_target": None,
                        "checkpoint_date": None,
                        "desired_result": None,
                        "deliverables": [],
                        "created_at": "2026-02-10T12:00:00Z",
                    },
                ],
                "google_connection": {"connected": True},
                "available_keywords": ["P2", "P3"],
            },
        }

        with patch(
            "mcp_server.priority_guardian.handlers.tools.authenticate_request",
            new_callable=AsyncMock,
            return_value=mock_auth_context,
        ), patch(
            "mcp_server.priority_guardian.tools.widget_tools.add_priority.backend_post",
            new_callable=AsyncMock,
            return_value=create_response,
        ), patch(
            "mcp_server.priority_guardian.http_client.backend_get",
            new_callable=AsyncMock,
            return_value=fresh_list_response,
        ):
            result = await call_tool_request(request)

        assert isinstance(result, mcp_types.CallToolResult)
        assert result.isError is None or result.isError is False
        assert result.structuredContent["success"] is True
        assert len(result.structuredContent["data"]["priorities"]) == 1
        assert result.structuredContent["data"]["priorities"][0]["name"] == "New Priority"


class TestUpdatePriorityRoundtrip:
    """Full roundtrip tests for update_priority (widget-only) tool."""

    @pytest.fixture
    def mock_auth_context(self):
        return {
            "user_id": str(uuid4()),
            "correlation_id": "test-correlation-id",
        }

    @pytest.fixture
    def mock_priority_id(self):
        return str(uuid4())

    @pytest.mark.asyncio
    async def test_update_priority_returns_fresh_list(self, mock_auth_context, mock_priority_id):
        """update_priority returns fresh priority list with updated data."""
        from mcp_server.priority_guardian.handlers.tools import call_tool_request

        request = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(
                name="update_priority",
                arguments={
                    "priority_id": mock_priority_id,
                    "name": "Updated Name",
                },
            ),
        )

        # Backend PUT returns full priority list directly
        update_response = {
            "success": True,
            "data": {
                "priorities": [
                    {
                        "id": mock_priority_id,
                        "name": "Updated Name",
                        "type": "deadline",
                        "calendar_keyword": "P1",
                        "status": "active",
                        "deadline": "2026-04-15",
                        "weekly_hour_target": None,
                        "checkpoint_date": None,
                        "desired_result": None,
                        "deliverables": [],
                        "created_at": "2026-02-10T12:00:00Z",
                    },
                ],
                "google_connection": {"connected": True},
                "available_keywords": ["P2", "P3"],
            },
        }

        with patch(
            "mcp_server.priority_guardian.handlers.tools.authenticate_request",
            new_callable=AsyncMock,
            return_value=mock_auth_context,
        ), patch(
            "mcp_server.priority_guardian.tools.widget_tools.update_priority.backend_put",
            new_callable=AsyncMock,
            return_value=update_response,
        ):
            result = await call_tool_request(request)

        assert isinstance(result, mcp_types.CallToolResult)
        assert result.structuredContent["success"] is True
        assert result.structuredContent["data"]["priorities"][0]["name"] == "Updated Name"


class TestDeletePriorityRoundtrip:
    """Full roundtrip tests for delete_priority (widget-only) tool."""

    @pytest.fixture
    def mock_auth_context(self):
        return {
            "user_id": str(uuid4()),
            "correlation_id": "test-correlation-id",
        }

    @pytest.fixture
    def mock_priority_id(self):
        return str(uuid4())

    @pytest.mark.asyncio
    async def test_delete_priority_returns_fresh_empty_list(self, mock_auth_context, mock_priority_id):
        """delete_priority returns fresh (empty) priority list."""
        from mcp_server.priority_guardian.handlers.tools import call_tool_request

        request = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(
                name="delete_priority",
                arguments={
                    "priority_id": mock_priority_id,
                    "confirm": True,
                },
            ),
        )

        # Backend DELETE returns full priority list directly
        delete_response = {
            "success": True,
            "data": {
                "priorities": [],
                "google_connection": {"connected": True},
                "available_keywords": ["P1", "P2", "P3"],
            },
        }

        with patch(
            "mcp_server.priority_guardian.handlers.tools.authenticate_request",
            new_callable=AsyncMock,
            return_value=mock_auth_context,
        ), patch(
            "mcp_server.priority_guardian.tools.widget_tools.delete_priority.backend_delete",
            new_callable=AsyncMock,
            return_value=delete_response,
        ):
            result = await call_tool_request(request)

        assert isinstance(result, mcp_types.CallToolResult)
        assert result.structuredContent["success"] is True
        assert len(result.structuredContent["data"]["priorities"]) == 0


class TestDeliverableCrudRoundtrip:
    """Full roundtrip tests for deliverable CRUD tools."""

    @pytest.fixture
    def mock_auth_context(self):
        return {
            "user_id": str(uuid4()),
            "correlation_id": "test-correlation-id",
        }

    @pytest.fixture
    def mock_priority_id(self):
        return str(uuid4())

    @pytest.fixture
    def mock_deliverable_id(self):
        return str(uuid4())

    @pytest.mark.asyncio
    async def test_add_deliverable_returns_fresh_list(
        self, mock_auth_context, mock_priority_id, mock_deliverable_id
    ):
        """add_deliverable returns fresh list with new deliverable."""
        from mcp_server.priority_guardian.handlers.tools import call_tool_request

        request = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(
                name="add_deliverable",
                arguments={
                    "priority_id": mock_priority_id,
                    "name": "New Task",
                },
            ),
        )

        # Backend POST returns full priority list directly
        create_response = {
            "success": True,
            "data": {
                "priorities": [
                    {
                        "id": mock_priority_id,
                        "name": "Test Priority",
                        "type": "deadline",
                        "calendar_keyword": "P1",
                        "status": "active",
                        "deadline": "2026-04-15",
                        "deliverables": [
                            {"id": mock_deliverable_id, "name": "New Task", "done": False}
                        ],
                        "created_at": "2026-02-10T12:00:00Z",
                    },
                ],
                "google_connection": {"connected": True},
                "available_keywords": ["P2", "P3"],
            },
        }

        with patch(
            "mcp_server.priority_guardian.handlers.tools.authenticate_request",
            new_callable=AsyncMock,
            return_value=mock_auth_context,
        ), patch(
            "mcp_server.priority_guardian.tools.widget_tools.add_deliverable.backend_post",
            new_callable=AsyncMock,
            return_value=create_response,
        ):
            result = await call_tool_request(request)

        assert isinstance(result, mcp_types.CallToolResult)
        assert result.structuredContent["success"] is True
        deliverables = result.structuredContent["data"]["priorities"][0]["deliverables"]
        assert len(deliverables) == 1
        assert deliverables[0]["name"] == "New Task"

    @pytest.mark.asyncio
    async def test_update_deliverable_toggles_done(
        self, mock_auth_context, mock_priority_id, mock_deliverable_id
    ):
        """update_deliverable toggles done status."""
        from mcp_server.priority_guardian.handlers.tools import call_tool_request

        request = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(
                name="update_deliverable",
                arguments={
                    "deliverable_id": mock_deliverable_id,
                    "done": True,
                },
            ),
        )

        # Backend PUT returns full priority list directly
        update_response = {
            "success": True,
            "data": {
                "priorities": [
                    {
                        "id": mock_priority_id,
                        "name": "Test Priority",
                        "type": "deadline",
                        "calendar_keyword": "P1",
                        "status": "active",
                        "deliverables": [
                            {"id": mock_deliverable_id, "name": "Task", "done": True}
                        ],
                        "created_at": "2026-02-10T12:00:00Z",
                    },
                ],
                "google_connection": {"connected": True},
                "available_keywords": ["P2", "P3"],
            },
        }

        with patch(
            "mcp_server.priority_guardian.handlers.tools.authenticate_request",
            new_callable=AsyncMock,
            return_value=mock_auth_context,
        ), patch(
            "mcp_server.priority_guardian.tools.widget_tools.update_deliverable.backend_put",
            new_callable=AsyncMock,
            return_value=update_response,
        ):
            result = await call_tool_request(request)

        assert isinstance(result, mcp_types.CallToolResult)
        assert result.structuredContent["success"] is True
        deliverables = result.structuredContent["data"]["priorities"][0]["deliverables"]
        assert deliverables[0]["done"] is True

    @pytest.mark.asyncio
    async def test_delete_deliverable_removes_from_list(
        self, mock_auth_context, mock_priority_id, mock_deliverable_id
    ):
        """delete_deliverable removes deliverable from list."""
        from mcp_server.priority_guardian.handlers.tools import call_tool_request

        request = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(
                name="delete_deliverable",
                arguments={
                    "deliverable_id": mock_deliverable_id,
                    "confirm": True,
                },
            ),
        )

        # Backend DELETE returns full priority list directly
        delete_response = {
            "success": True,
            "data": {
                "priorities": [
                    {
                        "id": mock_priority_id,
                        "name": "Test Priority",
                        "type": "deadline",
                        "calendar_keyword": "P1",
                        "status": "active",
                        "deliverables": [],  # Empty after delete
                        "created_at": "2026-02-10T12:00:00Z",
                    },
                ],
                "google_connection": {"connected": True},
                "available_keywords": ["P2", "P3"],
            },
        }

        with patch(
            "mcp_server.priority_guardian.handlers.tools.authenticate_request",
            new_callable=AsyncMock,
            return_value=mock_auth_context,
        ), patch(
            "mcp_server.priority_guardian.tools.widget_tools.delete_deliverable.backend_delete",
            new_callable=AsyncMock,
            return_value=delete_response,
        ):
            result = await call_tool_request(request)

        assert isinstance(result, mcp_types.CallToolResult)
        assert result.structuredContent["success"] is True
        deliverables = result.structuredContent["data"]["priorities"][0]["deliverables"]
        assert len(deliverables) == 0
