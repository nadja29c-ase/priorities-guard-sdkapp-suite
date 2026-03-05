"""
Output minimization tests for widget tools (compliance item #28).

Verifies that google_connected_at is not returned in any widget tool response,
even when the backend includes it.
"""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def user_id():
    return "user-123"


@pytest.fixture
def correlation_id():
    return "corr-456"


@pytest.fixture
def mock_fresh_priority_list():
    """Returns a factory that creates a mock backend response with google_connected_at."""
    def _make_response():
        return {
            "success": True,
            "data": {
                "priorities": [
                    {
                        "id": str(uuid4()),
                        "name": "Test Priority",
                        "type": "deadline",
                        "calendar_keyword": "P1",
                        "status": "active",
                        "deadline": "2026-03-15",
                        "deliverables": [],
                        "goals": [],
                    }
                ],
                "google_connection": {
                    "connected": True,
                    "connected_at": "2026-01-15T10:30:00Z",  # This should be filtered out
                },
                "available_keywords": ["P2", "P3"],
            }
        }
    return _make_response


# =============================================================================
# Output minimization: google_connected_at must not appear in any tool response
# =============================================================================

class TestOutputMinimization:
    """Verify google_connected_at is never returned in widget tool responses (compliance #28)."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tool_module,tool_func,arguments,backend_patch,backend_method", [
        (
            "mcp_server.priority_guardian.tools.widget_tools.add_deliverable",
            "handle",
            lambda uid: {"priority_id": uid, "name": "Task"},
            "mcp_server.priority_guardian.tools.widget_tools.add_deliverable.backend_post",
            "post",
        ),
        (
            "mcp_server.priority_guardian.tools.widget_tools.update_deliverable",
            "handle",
            lambda uid: {"deliverable_id": uid, "done": True},
            "mcp_server.priority_guardian.tools.widget_tools.update_deliverable.backend_put",
            "put",
        ),
        (
            "mcp_server.priority_guardian.tools.widget_tools.delete_deliverable",
            "handle",
            lambda uid: {"deliverable_id": uid, "confirm": True},
            "mcp_server.priority_guardian.tools.widget_tools.delete_deliverable.backend_delete",
            "delete",
        ),
        (
            "mcp_server.priority_guardian.tools.widget_tools.update_priority",
            "handle",
            lambda uid: {"priority_id": uid, "name": "Updated"},
            "mcp_server.priority_guardian.tools.widget_tools.update_priority.backend_put",
            "put",
        ),
        (
            "mcp_server.priority_guardian.tools.widget_tools.delete_priority",
            "handle",
            lambda uid: {"priority_id": uid, "confirm": True},
            "mcp_server.priority_guardian.tools.widget_tools.delete_priority.backend_delete",
            "delete",
        ),
        (
            "mcp_server.priority_guardian.tools.widget_tools.add_goal",
            "handle",
            lambda uid: {"priority_id": uid, "text": "Goal text"},
            "mcp_server.priority_guardian.tools.widget_tools.add_goal.backend_post",
            "post",
        ),
        (
            "mcp_server.priority_guardian.tools.widget_tools.update_goal",
            "handle",
            lambda uid: {"goal_id": uid, "achieved": True},
            "mcp_server.priority_guardian.tools.widget_tools.update_goal.backend_put",
            "put",
        ),
        (
            "mcp_server.priority_guardian.tools.widget_tools.delete_goal",
            "handle",
            lambda uid: {"goal_id": uid, "confirm": True},
            "mcp_server.priority_guardian.tools.widget_tools.delete_goal.backend_delete",
            "delete",
        ),
    ])
    async def test_google_connected_at_absent(
        self,
        user_id,
        correlation_id,
        mock_fresh_priority_list,
        tool_module,
        tool_func,
        arguments,
        backend_patch,
        backend_method,
    ):
        """google_connected_at must not appear in structuredContent.data for any widget tool."""
        import importlib
        module = importlib.import_module(tool_module)
        handle = getattr(module, tool_func)

        with patch(backend_patch, new_callable=AsyncMock, return_value=mock_fresh_priority_list()):
            result = await handle(
                user_id=user_id,
                correlation_id=correlation_id,
                arguments=arguments(str(uuid4())),
            )

        assert "google_connected_at" not in result.structuredContent["data"]
