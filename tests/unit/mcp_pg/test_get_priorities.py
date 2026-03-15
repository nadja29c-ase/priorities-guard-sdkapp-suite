"""
Unit tests for get_priorities MCP tool (Widget Increment A).

Tests:
- Priority field normalization (snake_case to camelCase)
- Google connection status inclusion
- Widget metadata (_meta.openai/outputTemplate)
- Response format compliance with spec
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from mcp_server.priority_guardian.tools.get_priorities import (
    handle,
    _normalize_priority,
    NAME,
    DESCRIPTION,
    INPUT_SCHEMA,
    REQUIRED_SCOPES,
    WIDGET_URI,
    GET_PRIORITIES,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_backend_priority():
    """Return a sample priority as returned by the backend (snake_case)."""
    return {
        "id": "pri-123",
        "name": "Launch feature X",
        "type": "deadline",
        "calendar_keyword": "P1",
        "status": "active",
        "deadline": "2025-02-15",
        "weekly_hour_target": 10,
        "weekly_hour_actual": 8,
        "checkpoint_date": None,
        "deliverables": [
            {"id": "del-1", "name": "Design doc", "done": True},
            {"id": "del-2", "name": "Implementation", "done": False},
        ],
        "goals": [],
        "created_at": "2025-01-01T10:00:00Z",
        "updated_at": "2025-01-10T15:30:00Z",
    }


@pytest.fixture
def sample_flexible_priority():
    """Return a sample flexible priority (snake_case)."""
    return {
        "id": "pri-456",
        "name": "Learn Rust",
        "type": "flexible",
        "calendar_keyword": "P2",
        "status": "active",
        "deadline": None,
        "weekly_hour_target": 5,
        "weekly_hour_actual": 3,
        "checkpoint_date": "2025-02-28",
        "deliverables": [],
        "goals": [
            {"id": "goal-1", "text": "Complete first 10 chapters", "achieved": False},
            {"id": "goal-2", "text": "Build sample project", "achieved": True},
        ],
        "created_at": "2025-01-05T09:00:00Z",
        "updated_at": "2025-01-12T11:00:00Z",
    }


# =============================================================================
# _normalize_priority Tests
# =============================================================================

class TestNormalizePriority:
    """Tests for _normalize_priority helper function."""

    def test_converts_calendar_keyword_to_camel_case(self, sample_backend_priority):
        """Test calendar_keyword becomes calendarKeyword."""
        result = _normalize_priority(sample_backend_priority)
        assert "calendarKeyword" in result
        assert result["calendarKeyword"] == "P1"
        assert "calendar_keyword" not in result

    def test_converts_weekly_hour_target(self, sample_backend_priority):
        """Test weekly_hour_target becomes weeklyHourTarget."""
        result = _normalize_priority(sample_backend_priority)
        assert result["weeklyHourTarget"] == 10
        assert "weekly_hour_target" not in result

    def test_weekly_hour_actual_none_without_calendar_hours(self, sample_backend_priority):
        """Test weeklyHourActual is None when no calendar_hours provided."""
        result = _normalize_priority(sample_backend_priority)
        assert result["weeklyHourActual"] is None

    def test_weekly_hour_actual_from_calendar_hours(self, sample_backend_priority):
        """Test weeklyHourActual is populated from calendar_hours dict."""
        calendar_hours = {"P1": 8.5, "P2": 3.0, "P3": 0.0}
        result = _normalize_priority(sample_backend_priority, calendar_hours)
        assert result["weeklyHourActual"] == 8.5  # P1 hours since priority has calendar_keyword="P1"

    def test_converts_checkpoint_date(self, sample_flexible_priority):
        """Test checkpoint_date becomes checkpointDate."""
        result = _normalize_priority(sample_flexible_priority)
        assert result["checkpointDate"] == "2025-02-28"
        assert "checkpoint_date" not in result

    def test_normalizes_goals(self, sample_flexible_priority):
        """Test goals array is normalized with id, text, achieved fields."""
        result = _normalize_priority(sample_flexible_priority)
        goals = result["goals"]
        assert len(goals) == 2
        assert goals[0] == {"id": "goal-1", "text": "Complete first 10 chapters", "achieved": False}
        assert goals[1] == {"id": "goal-2", "text": "Build sample project", "achieved": True}

    def test_excludes_timestamps(self, sample_backend_priority):
        """Test createdAt and updatedAt are excluded from output (output minimization)."""
        result = _normalize_priority(sample_backend_priority)
        assert "createdAt" not in result
        assert "updatedAt" not in result
        assert "created_at" not in result
        assert "updated_at" not in result

    def test_preserves_simple_fields(self, sample_backend_priority):
        """Test simple fields like id, name, type, status are preserved."""
        result = _normalize_priority(sample_backend_priority)
        assert result["id"] == "pri-123"
        assert result["name"] == "Launch feature X"
        assert result["type"] == "deadline"
        assert result["status"] == "active"
        assert result["deadline"] == "2025-02-15"

    def test_normalizes_deliverables(self, sample_backend_priority):
        """Test deliverables are normalized with id, name, done fields."""
        result = _normalize_priority(sample_backend_priority)
        deliverables = result["deliverables"]
        assert len(deliverables) == 2
        assert deliverables[0] == {"id": "del-1", "name": "Design doc", "done": True}
        assert deliverables[1] == {"id": "del-2", "name": "Implementation", "done": False}

    def test_handles_missing_optional_fields(self):
        """Test handles priorities with missing optional fields."""
        minimal_priority = {
            "id": "pri-min",
            "name": "Minimal",
            "type": "deadline",
            "status": "active",
            "deliverables": [],
        }
        result = _normalize_priority(minimal_priority)
        assert result["id"] == "pri-min"
        assert result["calendarKeyword"] is None
        assert result["deadline"] is None
        assert result["weeklyHourTarget"] is None
        assert result["weeklyHourActual"] is None
        assert result["checkpointDate"] is None
        assert result["deliverables"] == []
        assert result["goals"] == []

    def test_handles_empty_deliverables(self, sample_flexible_priority):
        """Test handles empty deliverables list."""
        result = _normalize_priority(sample_flexible_priority)
        assert result["deliverables"] == []

    def test_deliverable_done_defaults_to_false(self):
        """Test deliverable done field defaults to False if missing."""
        priority = {
            "id": "pri-1",
            "name": "Test",
            "type": "deadline",
            "status": "active",
            "deliverables": [
                {"id": "d1", "name": "No done field"},
            ],
        }
        result = _normalize_priority(priority)
        assert result["deliverables"][0]["done"] is False


# =============================================================================
# handle() Function Tests
# =============================================================================

class TestHandleFunction:
    """Tests for the handle() async function."""

    @pytest.mark.asyncio
    async def test_returns_call_tool_result(self, sample_backend_priority):
        """Test handle returns a CallToolResult."""
        mock_response = {
            "data": {
                "priorities": [sample_backend_priority],
                "google_connection": {"connected": True, "connected_at": "2025-01-01"},
            }
        }

        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await handle(
                user_id="user-123",
                correlation_id="corr-456",
                arguments={},
            )

        # Check it's a CallToolResult
        from mcp import types as mcp_types
        assert isinstance(result, mcp_types.CallToolResult)

    @pytest.mark.asyncio
    async def test_calls_backend_with_correct_paths(self, sample_backend_priority):
        """Test handle calls both priorities and calendar endpoints."""
        mock_priorities_response = {
            "success": True,
            "data": {
                "priorities": [sample_backend_priority],
                "google_connection": {"connected": False},
            }
        }
        mock_calendar_response = {
            "success": True,
            "data": {
                "keywords": {"P1": {"hours": 8.5, "event_count": 5}},
                "total_tracked_hours": 20.0,
            }
        }

        # Mock returns different responses for different paths
        async def mock_backend_get(path, user_id, correlation_id):
            if "calendar" in path:
                return mock_calendar_response
            return mock_priorities_response

        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get",
            side_effect=mock_backend_get,
        ):
            await handle(
                user_id="user-123",
                correlation_id="corr-456",
                arguments={},
            )

        # Verify both endpoints were called (can't use assert_called_once since there are 2 calls)

    @pytest.mark.asyncio
    async def test_includes_widget_uri_in_meta(self, sample_backend_priority):
        """Test response includes widget URI in _meta."""
        mock_response = {
            "data": {
                "priorities": [sample_backend_priority],
                "google_connection": {"connected": True, "connected_at": "2025-01-01"},
            }
        }

        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await handle(
                user_id="user-123",
                correlation_id="corr-456",
                arguments={},
            )

        structured = result.structuredContent
        assert structured["_meta"]["openai/outputTemplate"] == "ui://widget/pg-dashboard-v9.html"

    @pytest.mark.asyncio
    async def test_includes_google_connection_status(self, sample_backend_priority):
        """Test response includes Google connection status (without connected_at timestamp)."""
        mock_response = {
            "data": {
                "priorities": [sample_backend_priority],
                "google_connection": {
                    "connected": True,
                    "connected_at": "2025-01-15T10:30:00Z",
                },
            }
        }

        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await handle(
                user_id="user-123",
                correlation_id="corr-456",
                arguments={},
            )

        structured = result.structuredContent
        assert structured["data"]["google_connected"] is True
        # google_connected_at excluded for output minimization
        assert "google_connected_at" not in structured["data"]

    @pytest.mark.asyncio
    async def test_google_connected_defaults_to_false(self, sample_backend_priority):
        """Test google_connected defaults to False if missing."""
        mock_response = {
            "data": {
                "priorities": [sample_backend_priority],
                "google_connection": {},  # Missing 'connected' key
            }
        }

        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await handle(
                user_id="user-123",
                correlation_id="corr-456",
                arguments={},
            )

        structured = result.structuredContent
        assert structured["data"]["google_connected"] is False

    @pytest.mark.asyncio
    async def test_normalizes_priorities_to_camel_case(
        self, sample_backend_priority, sample_flexible_priority
    ):
        """Test all priorities are normalized to camelCase."""
        mock_response = {
            "data": {
                "priorities": [sample_backend_priority, sample_flexible_priority],
                "google_connection": {"connected": False},
            }
        }

        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await handle(
                user_id="user-123",
                correlation_id="corr-456",
                arguments={},
            )

        structured = result.structuredContent
        priorities = structured["data"]["priorities"]

        assert len(priorities) == 2

        # Check first priority has camelCase fields
        assert priorities[0]["calendarKeyword"] == "P1"
        assert priorities[0]["weeklyHourTarget"] == 10

        # Check second priority has camelCase fields and goals
        assert priorities[1]["calendarKeyword"] == "P2"
        assert priorities[1]["checkpointDate"] == "2025-02-28"
        assert len(priorities[1]["goals"]) == 2
        assert priorities[1]["goals"][0]["text"] == "Complete first 10 chapters"

    @pytest.mark.asyncio
    async def test_text_content_for_active_priorities(self, sample_backend_priority):
        """Test text content summarizes active priorities."""
        mock_response = {
            "data": {
                "priorities": [sample_backend_priority],
                "google_connection": {"connected": True, "connected_at": "2025-01-01"},
            }
        }

        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await handle(
                user_id="user-123",
                correlation_id="corr-456",
                arguments={},
            )

        text = result.content[0].text
        assert "1 active priority" in text

    @pytest.mark.asyncio
    async def test_text_content_for_no_priorities(self):
        """Test text content when no priorities exist."""
        mock_response = {
            "data": {
                "priorities": [],
                "google_connection": {"connected": True, "connected_at": "2025-01-01"},
            }
        }

        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await handle(
                user_id="user-123",
                correlation_id="corr-456",
                arguments={},
            )

        text = result.content[0].text
        assert "don't have any priorities" in text

    @pytest.mark.asyncio
    async def test_text_content_mentions_google_not_connected(
        self, sample_backend_priority
    ):
        """Test text mentions Google Calendar when not connected."""
        mock_response = {
            "data": {
                "priorities": [sample_backend_priority],
                "google_connection": {"connected": False},
            }
        }

        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await handle(
                user_id="user-123",
                correlation_id="corr-456",
                arguments={},
            )

        text = result.content[0].text
        assert "Google Calendar is not connected" in text

    @pytest.mark.asyncio
    async def test_includes_assistant_guidance(self, sample_backend_priority):
        """Test response includes assistant guidance."""
        mock_response = {
            "data": {
                "priorities": [sample_backend_priority],
                "google_connection": {"connected": True, "connected_at": "2025-01-01"},
            }
        }

        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await handle(
                user_id="user-123",
                correlation_id="corr-456",
                arguments={},
            )

        structured = result.structuredContent
        assert "assistant_guidance" in structured
        assert "widget displays them" in structured["assistant_guidance"]

    @pytest.mark.asyncio
    async def test_success_true_in_structured_content(self, sample_backend_priority):
        """Test structuredContent.success is True."""
        mock_response = {
            "data": {
                "priorities": [sample_backend_priority],
                "google_connection": {"connected": False},
            }
        }

        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await handle(
                user_id="user-123",
                correlation_id="corr-456",
                arguments={},
            )

        assert result.structuredContent["success"] is True


# =============================================================================
# Tool Definition Tests
# =============================================================================

class TestToolDefinition:
    """Tests for GET_PRIORITIES ToolDefinition."""

    def test_name_is_get_priorities(self):
        """Test tool name is get_priorities."""
        assert NAME == "get_priorities"
        assert GET_PRIORITIES.name == "get_priorities"

    def test_description_mentions_priorities(self):
        """Test description mentions priorities."""
        assert "priorities" in DESCRIPTION.lower()
        assert "priorities" in GET_PRIORITIES.description.lower()

    def test_input_schema_has_no_required_fields(self):
        """Test input schema has no required fields."""
        assert INPUT_SCHEMA["required"] == []
        assert GET_PRIORITIES.input_schema["required"] == []

    def test_required_scopes_includes_pg_access(self):
        """Test required scopes includes pg.access."""
        assert "pg.access" in REQUIRED_SCOPES
        assert "pg.access" in GET_PRIORITIES.required_scopes

    def test_widget_uri_is_correct(self):
        """Test widget URI points to dashboard."""
        assert WIDGET_URI == "ui://widget/pg-dashboard-v9.html"
        assert GET_PRIORITIES.widget_uri == "ui://widget/pg-dashboard-v9.html"

    def test_read_only_hint_is_false(self):
        """Test read_only_hint is False (triggers snapshot writes)."""
        assert GET_PRIORITIES.read_only_hint is False

    def test_destructive_hint_is_false(self):
        """Test destructive_hint is False."""
        assert GET_PRIORITIES.destructive_hint is False

    def test_widget_accessible_is_true(self):
        """Test widget_accessible is True (widget can call this tool)."""
        assert GET_PRIORITIES.widget_accessible is True

    def test_open_world_hint_is_true(self):
        """Test open_world_hint is True (calls Google Calendar API via backend)."""
        assert GET_PRIORITIES.open_world_hint is True


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_handles_empty_data_response(self):
        """Test handles response with empty data."""
        mock_response = {"data": {}}

        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await handle(
                user_id="user-123",
                correlation_id="corr-456",
                arguments={},
            )

        structured = result.structuredContent
        assert structured["data"]["priorities"] == []
        assert structured["data"]["google_connected"] is False

    @pytest.mark.asyncio
    async def test_handles_missing_google_connection(self):
        """Test handles response without google_connection field."""
        mock_response = {
            "data": {
                "priorities": [],
            }
        }

        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await handle(
                user_id="user-123",
                correlation_id="corr-456",
                arguments={},
            )

        structured = result.structuredContent
        assert structured["data"]["google_connected"] is False
        # google_connected_at excluded for output minimization
        assert "google_connected_at" not in structured["data"]

    @pytest.mark.asyncio
    async def test_plural_priorities_text(self):
        """Test text uses correct plural for multiple priorities."""
        priorities = [
            {
                "id": "p1",
                "name": "Priority 1",
                "type": "deadline",
                "status": "active",
                "deliverables": [],
            },
            {
                "id": "p2",
                "name": "Priority 2",
                "type": "flexible",
                "status": "active",
                "deliverables": [],
            },
            {
                "id": "p3",
                "name": "Priority 3",
                "type": "deadline",
                "status": "archived",  # Not active
                "deliverables": [],
            },
        ]
        mock_response = {
            "data": {
                "priorities": priorities,
                "google_connection": {"connected": True, "connected_at": "2025-01-01"},
            }
        }

        with patch(
            "mcp_server.priority_guardian.tools.get_priorities.backend_get",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await handle(
                user_id="user-123",
                correlation_id="corr-456",
                arguments={},
            )

        text = result.content[0].text
        assert "2 active priorities" in text  # Plural
