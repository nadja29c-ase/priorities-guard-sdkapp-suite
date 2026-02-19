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
    """Full roundtrip tests for create_priority tool (Increment 16)."""

    @pytest.fixture
    def mock_auth_context(self):
        """Auth context returned by authenticate_request."""
        return {
            "user_id": str(uuid4()),
            "correlation_id": "test-correlation-id",
        }

    @pytest.fixture
    def mock_priority_id(self):
        return str(uuid4())

    @pytest.fixture
    def mock_backend_success(self, mock_priority_id):
        """Successful backend response for create_priority."""
        return {
            "success": True,
            "data": {
                "priority": {
                    "id": mock_priority_id,
                    "name": "Ship MVP",
                    "type": "deadline",
                    "calendar_keyword": "P1",
                    "status": "active",
                    "deadline": "2026-03-15",
                    "weekly_hour_target": None,
                    "checkpoint_date": None,
                    "deliverables": [],
                    "goals": [],
                    "created_at": "2026-02-09T12:00:00Z",
                },
                "active_priority_count": 1,
                "available_keywords": ["P2", "P3"],
            },
        }

    @pytest.fixture
    def mock_get_priorities_response(self, mock_priority_id):
        """Mock GET priorities response for widget rendering."""
        return {
            "success": True,
            "data": {
                "priorities": [
                    {
                        "id": mock_priority_id,
                        "name": "Ship MVP",
                        "type": "deadline",
                        "calendar_keyword": "P1",
                        "status": "active",
                        "deadline": "2026-03-15",
                        "deliverables": [],
                        "goals": [],
                        "created_at": "2026-02-09T12:00:00Z",
                        "updated_at": "2026-02-09T12:00:00Z",
                    },
                ],
                "google_connection": {"connected": False},
                "available_keywords": ["P2", "P3"],
            },
        }

    @pytest.mark.asyncio
    async def test_create_priority_roundtrip_with_widget_data(
        self, mock_auth_context, mock_backend_success, mock_get_priorities_response
    ):
        """create_priority returns widget data with correct calendarKeyword and _meta."""
        from mcp_server.priority_guardian.handlers.tools import call_tool_request

        request = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(
                name="create_priority",
                arguments={
                    "user_priority_name_verbatim": "I need to ship the MVP by March",
                    "name": "Ship MVP",
                    "user_priority_type_verbatim": "it has a hard deadline",
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
        ), patch(
            "mcp_server.priority_guardian.tools.create_priority.backend_get",
            new_callable=AsyncMock,
            return_value=mock_get_priorities_response,
        ):
            result = await call_tool_request(request)

        # Verify structure
        assert isinstance(result, mcp_types.CallToolResult)
        assert not result.isError

        # Verify structuredContent
        sc = result.structuredContent
        assert sc is not None
        assert sc["success"] is True
        assert "data" in sc
        assert "priorities" in sc["data"]
        assert sc["data"]["priorities"][0]["calendarKeyword"] == "P1"

        # Verify _meta with widget template
        assert sc["_meta"]["openai/outputTemplate"] == "ui://widget/pg-dashboard.html"

        # Verify assistant_guidance
        assert "assistant_guidance" in sc
        assert sc["assistant_guidance"]["action"] == "PRIORITY_CREATED"
        assert sc["assistant_guidance"]["remaining_slots"] == 2

        # Verify content text
        assert len(result.content) == 1
        assert "Ship MVP" in result.content[0].text

    @pytest.mark.asyncio
    async def test_create_priority_roundtrip_flexible_with_goal(
        self, mock_auth_context
    ):
        """create_priority for flexible type includes goal in response."""
        from mcp_server.priority_guardian.handlers.tools import call_tool_request

        priority_id = str(uuid4())
        goal_id = str(uuid4())

        mock_backend_success = {
            "success": True,
            "data": {
                "priority": {
                    "id": priority_id,
                    "name": "Learn Spanish",
                    "type": "flexible",
                    "calendar_keyword": "P1",
                    "status": "active",
                    "weekly_hour_target": 5,
                    "checkpoint_date": "2026-03-15",
                    "goals": [{"id": goal_id, "text": "Hold basic conversation", "achieved": False}],
                    "created_at": "2026-02-09T12:00:00Z",
                },
                "active_priority_count": 1,
                "available_keywords": ["P2", "P3"],
            },
        }

        mock_get_priorities = {
            "success": True,
            "data": {
                "priorities": [
                    {
                        "id": priority_id,
                        "name": "Learn Spanish",
                        "type": "flexible",
                        "calendar_keyword": "P1",
                        "status": "active",
                        "weekly_hour_target": 5,
                        "checkpoint_date": "2026-03-15",
                        "deliverables": [],
                        "goals": [{"id": goal_id, "text": "Hold basic conversation", "achieved": False}],
                        "created_at": "2026-02-09T12:00:00Z",
                        "updated_at": "2026-02-09T12:00:00Z",
                    },
                ],
                "google_connection": {"connected": False},
                "available_keywords": ["P2", "P3"],
            },
        }

        request = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(
                name="create_priority",
                arguments={
                    "user_priority_name_verbatim": "I want to learn Spanish",
                    "name": "Learn Spanish",
                    "user_priority_type_verbatim": "it's an ongoing commitment",
                    "type": "flexible",
                    "weekly_hour_target": 5,
                    "checkpoint_date": "2026-03-15",
                    "user_goal_verbatim": "I want to hold a basic conversation",
                    "initial_goal_text": "Hold basic conversation",
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
        ), patch(
            "mcp_server.priority_guardian.tools.create_priority.backend_get",
            new_callable=AsyncMock,
            return_value=mock_get_priorities,
        ):
            result = await call_tool_request(request)

        assert isinstance(result, mcp_types.CallToolResult)
        assert not result.isError

        # Verify goals in response
        priorities = result.structuredContent["data"]["priorities"]
        assert len(priorities) == 1
        assert len(priorities[0]["goals"]) == 1
        assert priorities[0]["goals"][0]["text"] == "Hold basic conversation"

    @pytest.mark.asyncio
    async def test_create_priority_duplicate_name_creates_second_priority(
        self, mock_auth_context
    ):
        """Creating two priorities with same name succeeds with different keywords."""
        from mcp_server.priority_guardian.handlers.tools import call_tool_request

        # Second creation gets P2
        mock_backend_success = {
            "success": True,
            "data": {
                "priority": {
                    "id": str(uuid4()),
                    "name": "Ship MVP",
                    "type": "deadline",
                    "calendar_keyword": "P2",
                    "status": "active",
                    "deadline": "2026-03-15",
                    "created_at": "2026-02-09T12:00:00Z",
                },
                "active_priority_count": 2,
                "available_keywords": ["P3"],
            },
        }

        mock_get_priorities = {
            "success": True,
            "data": {
                "priorities": [
                    {"id": str(uuid4()), "name": "Ship MVP", "calendar_keyword": "P1", "status": "active",
                     "type": "deadline", "deliverables": [], "goals": [], "created_at": "2026-02-09T12:00:00Z"},
                    {"id": str(uuid4()), "name": "Ship MVP", "calendar_keyword": "P2", "status": "active",
                     "type": "deadline", "deliverables": [], "goals": [], "created_at": "2026-02-09T12:00:00Z"},
                ],
                "google_connection": {"connected": False},
                "available_keywords": ["P3"],
            },
        }

        request = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(
                name="create_priority",
                arguments={
                    "user_priority_name_verbatim": "I need to ship the MVP",
                    "name": "Ship MVP",
                    "user_priority_type_verbatim": "it has a hard deadline",
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
        ), patch(
            "mcp_server.priority_guardian.tools.create_priority.backend_get",
            new_callable=AsyncMock,
            return_value=mock_get_priorities,
        ):
            result = await call_tool_request(request)

        assert result.structuredContent["assistant_guidance"]["remaining_slots"] == 1
        assert result.structuredContent["data"]["available_keywords"] == ["P3"]

    @pytest.mark.asyncio
    async def test_create_priority_fourth_call_returns_max_reached(
        self, mock_auth_context
    ):
        """Fourth priority creation returns MAX_PRIORITIES_REACHED error."""
        from mcp_server.priority_guardian.handlers.tools import call_tool_request

        mock_backend_error = {
            "success": False,
            "error": {
                "code": "MAX_PRIORITIES_REACHED",
                "message": "Maximum of 3 active priorities reached",
            },
        }

        request = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(
                name="create_priority",
                arguments={
                    "user_priority_name_verbatim": "fourth priority",
                    "name": "Fourth Priority",
                    "user_priority_type_verbatim": "deadline",
                    "type": "deadline",
                    "deadline": "2026-04-15",
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
            return_value=mock_backend_error,
        ):
            result = await call_tool_request(request)

        assert result.isError is True
        assert result.structuredContent["error"]["code"] == "MAX_PRIORITIES_REACHED"
        assert "assistant_guidance" in result.structuredContent


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
        assert not result.isError
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
