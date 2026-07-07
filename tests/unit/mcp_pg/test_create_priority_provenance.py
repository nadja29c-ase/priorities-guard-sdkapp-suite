"""
Unit tests for create_priority MCP tool provenance validation (Increment 16).

Tests:
- Provenance field validation (verbatim fields non-empty)
- Flexible type requires goal_verbatim and initial_goal_text
- Deadline type does not require goal fields
- Verbatim fields not sent to backend
- Widget rendering after successful creation
- Structured assistant_guidance for success and error cases
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from mcp import types as mcp_types

from mcp_server.priority_guardian.tools.create_priority import (
    handle,
    NAME,
    DESCRIPTION,
    INPUT_SCHEMA,
    REQUIRED_SCOPES,
    WIDGET_URI,
    CREATE_PRIORITY,
    GUIDANCE_EMPTY_NAME_VERBATIM,
    GUIDANCE_EMPTY_NAME,
    GUIDANCE_EMPTY_TYPE_VERBATIM,
    GUIDANCE_EMPTY_GOAL_VERBATIM,
    GUIDANCE_EMPTY_GOAL_TEXT,
    # Action constants
    ACTION_PRIORITY_CREATED,
    ACTION_ASK_CLARIFYING,
    ACTION_RETRY,
    ACTION_MAX_REACHED,
    ACTION_ERROR,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def valid_deadline_args():
    """Return valid arguments for a deadline priority."""
    return {
        "user_priority_name_verbatim": "I want to track my thesis writing",
        "name": "Thesis Writing",
        "user_priority_type_verbatim": "it has a hard deadline in June",
        "type": "deadline",
        "deadline": "2026-06-01",
    }


@pytest.fixture
def valid_flexible_args():
    """Return valid arguments for a flexible priority."""
    return {
        "user_priority_name_verbatim": "I want to learn Spanish",
        "name": "Learn Spanish",
        "user_priority_type_verbatim": "it's more of an ongoing thing, maybe 5 hours a week",
        "type": "flexible",
        "weekly_hour_target": 5,
        "checkpoint_date": "2026-03-15",
        "user_goal_verbatim": "I want to be able to hold a basic conversation",
        "initial_goal_text": "Hold a basic conversation in Spanish",
    }


@pytest.fixture
def mock_backend_success_response():
    """Return a mock successful backend response."""
    return {
        "success": True,
        "data": {
            "priority": {
                "id": "pri-123",
                "name": "Thesis Writing",
                "type": "deadline",
                "calendar_keyword": "P1",
                "status": "active",
                "deadline": "2026-06-01",
                "created_at": "2026-02-18T10:00:00Z",
            },
            "active_priority_count": 1,
            "available_keywords": ["P2", "P3"],
        },
    }


@pytest.fixture
def mock_get_priorities_response():
    """Return a mock GET priorities response for widget rendering."""
    return {
        "success": True,
        "data": {
            "priorities": [
                {
                    "id": "pri-123",
                    "name": "Thesis Writing",
                    "type": "deadline",
                    "calendar_keyword": "P1",
                    "status": "active",
                    "deadline": "2026-06-01",
                    "deliverables": [],
                    "goals": [],
                    "created_at": "2026-02-18T10:00:00Z",
                    "updated_at": "2026-02-18T10:00:00Z",
                },
            ],
            "google_connection": {"connected": False},
            "available_keywords": ["P2", "P3"],
        },
    }


# =============================================================================
# Provenance Validation Tests
# =============================================================================

class TestProvenanceValidation:
    """Tests for provenance field validation."""

    @pytest.mark.asyncio
    async def test_empty_name_verbatim_returns_error(self):
        """Call handler with empty user_priority_name_verbatim returns structured error."""
        result = await handle(
            user_id="user-123",
            correlation_id="corr-123",
            arguments={
                "user_priority_name_verbatim": "",
                "name": "Test Priority",
                "user_priority_type_verbatim": "deadline",
                "type": "deadline",
            },
        )

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_name_verbatim"
        assert result.structuredContent["assistant_guidance"]["action"] == ACTION_ASK_CLARIFYING
        assert "user_priority_name_verbatim" in result.structuredContent["assistant_guidance"]["instruction"]

    @pytest.mark.asyncio
    async def test_whitespace_only_name_verbatim_returns_error(self):
        """Call handler with whitespace-only user_priority_name_verbatim returns error."""
        result = await handle(
            user_id="user-123",
            correlation_id="corr-123",
            arguments={
                "user_priority_name_verbatim": "   ",
                "name": "Test Priority",
                "user_priority_type_verbatim": "deadline",
                "type": "deadline",
            },
        )

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_name_verbatim"

    @pytest.mark.asyncio
    async def test_empty_name_returns_error(self):
        """Call handler with empty name returns structured error."""
        result = await handle(
            user_id="user-123",
            correlation_id="corr-123",
            arguments={
                "user_priority_name_verbatim": "I want to track my project",
                "name": "",
                "user_priority_type_verbatim": "deadline",
                "type": "deadline",
            },
        )

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_name"

    @pytest.mark.asyncio
    async def test_empty_type_verbatim_returns_error(self):
        """Call handler with empty user_priority_type_verbatim returns error."""
        result = await handle(
            user_id="user-123",
            correlation_id="corr-123",
            arguments={
                "user_priority_name_verbatim": "I want to track my project",
                "name": "My Project",
                "user_priority_type_verbatim": "",
                "type": "deadline",
            },
        )

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_type_verbatim"
        assert result.structuredContent["assistant_guidance"]["action"] == ACTION_ASK_CLARIFYING

    @pytest.mark.asyncio
    async def test_invalid_type_returns_error(self):
        """Call handler with invalid type returns error."""
        result = await handle(
            user_id="user-123",
            correlation_id="corr-123",
            arguments={
                "user_priority_name_verbatim": "I want to track my project",
                "name": "My Project",
                "user_priority_type_verbatim": "it's urgent",
                "type": "urgent",  # Invalid type
            },
        )

        assert result.isError is True
        assert result.structuredContent["error"] == "missing_type"
        assert result.structuredContent["assistant_guidance"]["action"] == ACTION_ASK_CLARIFYING

    @pytest.mark.asyncio
    async def test_missing_type_returns_error(self):
        """Call handler with missing type returns error."""
        result = await handle(
            user_id="user-123",
            correlation_id="corr-123",
            arguments={
                "user_priority_name_verbatim": "I want to track my project",
                "name": "My Project",
                "user_priority_type_verbatim": "it's a deadline",
                # type is missing
            },
        )

        assert result.isError is True
        assert result.structuredContent["error"] == "missing_type"

    @pytest.mark.asyncio
    async def test_deadline_missing_deadline_field_returns_error(self):
        """Deadline type without deadline field returns error."""
        result = await handle(
            user_id="user-123",
            correlation_id="corr-123",
            arguments={
                "user_priority_name_verbatim": "I need to ship the feature",
                "name": "Ship Feature",
                "user_priority_type_verbatim": "it has a hard deadline",
                "type": "deadline",
                # deadline field is missing
            },
        )

        assert result.isError is True
        assert result.structuredContent["error"] == "missing_deadline"
        assert "due date" in result.structuredContent["assistant_guidance"]["instruction"].lower()

    @pytest.mark.asyncio
    async def test_deadline_empty_deadline_field_returns_error(self):
        """Deadline type with empty deadline field returns error."""
        result = await handle(
            user_id="user-123",
            correlation_id="corr-123",
            arguments={
                "user_priority_name_verbatim": "I need to ship the feature",
                "name": "Ship Feature",
                "user_priority_type_verbatim": "it has a hard deadline",
                "type": "deadline",
                "deadline": "",
            },
        )

        assert result.isError is True
        assert result.structuredContent["error"] == "missing_deadline"

    @pytest.mark.asyncio
    async def test_flexible_missing_weekly_hour_target_returns_error(self):
        """Flexible type without weekly_hour_target returns error."""
        result = await handle(
            user_id="user-123",
            correlation_id="corr-123",
            arguments={
                "user_priority_name_verbatim": "I want to learn Spanish",
                "name": "Learn Spanish",
                "user_priority_type_verbatim": "it's ongoing",
                "type": "flexible",
                # weekly_hour_target missing
                "checkpoint_date": "2026-03-15",
                "user_goal_verbatim": "hold a conversation",
                "initial_goal_text": "Hold a conversation",
            },
        )

        assert result.isError is True
        assert result.structuredContent["error"] == "missing_weekly_hours"
        assert "hours per week" in result.structuredContent["assistant_guidance"]["instruction"].lower()

    @pytest.mark.asyncio
    async def test_flexible_missing_checkpoint_date_returns_error(self):
        """Flexible type without checkpoint_date returns error."""
        result = await handle(
            user_id="user-123",
            correlation_id="corr-123",
            arguments={
                "user_priority_name_verbatim": "I want to learn Spanish",
                "name": "Learn Spanish",
                "user_priority_type_verbatim": "it's ongoing",
                "type": "flexible",
                "weekly_hour_target": 5,
                # checkpoint_date missing
                "user_goal_verbatim": "hold a conversation",
                "initial_goal_text": "Hold a conversation",
            },
        )

        assert result.isError is True
        assert result.structuredContent["error"] == "missing_checkpoint"
        assert "check in" in result.structuredContent["assistant_guidance"]["instruction"].lower()

    @pytest.mark.asyncio
    async def test_flexible_empty_checkpoint_date_returns_error(self):
        """Flexible type with empty checkpoint_date returns error."""
        result = await handle(
            user_id="user-123",
            correlation_id="corr-123",
            arguments={
                "user_priority_name_verbatim": "I want to learn Spanish",
                "name": "Learn Spanish",
                "user_priority_type_verbatim": "it's ongoing",
                "type": "flexible",
                "weekly_hour_target": 5,
                "checkpoint_date": "",
                "user_goal_verbatim": "hold a conversation",
                "initial_goal_text": "Hold a conversation",
            },
        )

        assert result.isError is True
        assert result.structuredContent["error"] == "missing_checkpoint"

    @pytest.mark.asyncio
    async def test_flexible_empty_goal_verbatim_returns_error(self):
        """Flexible type with empty user_goal_verbatim returns error."""
        result = await handle(
            user_id="user-123",
            correlation_id="corr-123",
            arguments={
                "user_priority_name_verbatim": "I want to learn Spanish",
                "name": "Learn Spanish",
                "user_priority_type_verbatim": "it's ongoing",
                "type": "flexible",
                "weekly_hour_target": 5,
                "checkpoint_date": "2026-03-15",
                "user_goal_verbatim": "",
                "initial_goal_text": "Hold a conversation",
            },
        )

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_goal_verbatim"

    @pytest.mark.asyncio
    async def test_flexible_empty_initial_goal_text_returns_error(self):
        """Flexible type with empty initial_goal_text returns error."""
        result = await handle(
            user_id="user-123",
            correlation_id="corr-123",
            arguments={
                "user_priority_name_verbatim": "I want to learn Spanish",
                "name": "Learn Spanish",
                "user_priority_type_verbatim": "it's ongoing",
                "type": "flexible",
                "weekly_hour_target": 5,
                "checkpoint_date": "2026-03-15",
                "user_goal_verbatim": "I want to hold a conversation",
                "initial_goal_text": "",
            },
        )

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_goal_text"

    @pytest.mark.asyncio
    async def test_flexible_whitespace_initial_goal_text_returns_error(self):
        """Flexible type with whitespace-only initial_goal_text returns error."""
        result = await handle(
            user_id="user-123",
            correlation_id="corr-123",
            arguments={
                "user_priority_name_verbatim": "I want to learn Spanish",
                "name": "Learn Spanish",
                "user_priority_type_verbatim": "it's ongoing",
                "type": "flexible",
                "weekly_hour_target": 5,
                "checkpoint_date": "2026-03-15",
                "user_goal_verbatim": "I want to hold a conversation",
                "initial_goal_text": "   ",
            },
        )

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_goal_text"

    @pytest.mark.asyncio
    async def test_deadline_type_does_not_require_goal_verbatim(
        self, valid_deadline_args, mock_backend_success_response, mock_get_priorities_response
    ):
        """Deadline type passes provenance validation without user_goal_verbatim."""
        with patch(
            "mcp_server.priority_guardian.tools.create_priority.backend_post"
        ) as mock_post, patch(
            "mcp_server.priority_guardian.tools.create_priority.backend_get"
        ) as mock_get:
            mock_post.return_value = mock_backend_success_response
            mock_get.return_value = mock_get_priorities_response

            result = await handle(
                user_id="user-123",
                correlation_id="corr-123",
                arguments=valid_deadline_args,
            )

            # Should succeed (no provenance error)
            assert result.isError is not True
            mock_post.assert_called_once()


# =============================================================================
# Backend Call Tests
# =============================================================================

class TestBackendCalls:
    """Tests for backend API calls."""

    @pytest.mark.asyncio
    async def test_valid_deadline_provenance_calls_backend(
        self, valid_deadline_args, mock_backend_success_response, mock_get_priorities_response
    ):
        """Valid deadline args passes provenance and calls backend."""
        with patch(
            "mcp_server.priority_guardian.tools.create_priority.backend_post"
        ) as mock_post, patch(
            "mcp_server.priority_guardian.tools.create_priority.backend_get"
        ) as mock_get:
            mock_post.return_value = mock_backend_success_response
            mock_get.return_value = mock_get_priorities_response

            result = await handle(
                user_id="user-123",
                correlation_id="corr-123",
                arguments=valid_deadline_args,
            )

            # Verify backend_post was called
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            payload = call_args[0][1]

            # Verify payload has correct fields
            assert payload["name"] == "Thesis Writing"
            assert payload["type"] == "deadline"
            assert payload["deadline"] == "2026-06-01"

            # Verify backend_get was called for fresh priorities
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_valid_flexible_provenance_calls_backend(
        self, valid_flexible_args, mock_get_priorities_response
    ):
        """Valid flexible args passes provenance and calls backend with initial_goal_text."""
        mock_response = {
            "success": True,
            "data": {
                "priority": {
                    "id": "pri-456",
                    "name": "Learn Spanish",
                    "type": "flexible",
                    "calendar_keyword": "P1",
                    "status": "active",
                    "weekly_hour_target": 5,
                    "checkpoint_date": "2026-03-15",
                    "goals": [{"id": "goal-1", "text": "Hold a basic conversation in Spanish", "achieved": False}],
                    "created_at": "2026-02-18T10:00:00Z",
                },
                "active_priority_count": 1,
                "available_keywords": ["P2", "P3"],
            },
        }

        with patch(
            "mcp_server.priority_guardian.tools.create_priority.backend_post"
        ) as mock_post, patch(
            "mcp_server.priority_guardian.tools.create_priority.backend_get"
        ) as mock_get:
            mock_post.return_value = mock_response
            mock_get.return_value = mock_get_priorities_response

            result = await handle(
                user_id="user-123",
                correlation_id="corr-123",
                arguments=valid_flexible_args,
            )

            # Verify backend_post was called with initial_goal_text
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            payload = call_args[0][1]

            assert payload["initial_goal_text"] == "Hold a basic conversation in Spanish"
            assert payload["weekly_hour_target"] == 5
            assert payload["checkpoint_date"] == "2026-03-15"

            # inc_96: Widget binding moved to top-level _meta
            assert result.meta is not None
            assert result.meta["ui"]["resourceUri"] == WIDGET_URI
            assert result.meta["openai/outputTemplate"] == WIDGET_URI

    @pytest.mark.asyncio
    async def test_verbatim_fields_not_sent_to_backend(
        self, valid_flexible_args, mock_get_priorities_response
    ):
        """Verbatim fields are NOT included in backend payload."""
        mock_response = {
            "success": True,
            "data": {
                "priority": {
                    "id": "pri-456",
                    "name": "Learn Spanish",
                    "type": "flexible",
                    "calendar_keyword": "P1",
                    "status": "active",
                    "created_at": "2026-02-18T10:00:00Z",
                },
                "active_priority_count": 1,
                "available_keywords": ["P2", "P3"],
            },
        }

        with patch(
            "mcp_server.priority_guardian.tools.create_priority.backend_post"
        ) as mock_post, patch(
            "mcp_server.priority_guardian.tools.create_priority.backend_get"
        ) as mock_get:
            mock_post.return_value = mock_response
            mock_get.return_value = mock_get_priorities_response

            await handle(
                user_id="user-123",
                correlation_id="corr-123",
                arguments=valid_flexible_args,
            )

            # Verify verbatim fields not in payload
            call_args = mock_post.call_args
            payload = call_args[0][1]

            assert "user_priority_name_verbatim" not in payload
            assert "user_priority_type_verbatim" not in payload
            assert "user_goal_verbatim" not in payload


# =============================================================================
# Success Response Tests
# =============================================================================

class TestSuccessResponse:
    """Tests for successful creation responses."""

    @pytest.mark.asyncio
    async def test_success_response_includes_widget_template(
        self, valid_deadline_args, mock_backend_success_response, mock_get_priorities_response
    ):
        """Successful creation includes widget template in _meta."""
        with patch(
            "mcp_server.priority_guardian.tools.create_priority.backend_post"
        ) as mock_post, patch(
            "mcp_server.priority_guardian.tools.create_priority.backend_get"
        ) as mock_get:
            mock_post.return_value = mock_backend_success_response
            mock_get.return_value = mock_get_priorities_response

            result = await handle(
                user_id="user-123",
                correlation_id="corr-123",
                arguments=valid_deadline_args,
            )

            # inc_96: Widget binding moved to top-level _meta
            assert result.meta is not None
            assert result.meta["ui"]["resourceUri"] == "ui://widget/pg-dashboard-v12.html"
            assert result.meta["openai/outputTemplate"] == "ui://widget/pg-dashboard-v12.html"

    @pytest.mark.asyncio
    async def test_success_guidance_has_remaining_slots_when_under_3(
        self, valid_deadline_args, mock_get_priorities_response
    ):
        """Success with active_priority_count=1 returns remaining_slots=2."""
        mock_response = {
            "success": True,
            "data": {
                "priority": {
                    "id": "pri-123",
                    "name": "Thesis Writing",
                    "type": "deadline",
                    "calendar_keyword": "P1",
                    "status": "active",
                    "created_at": "2026-02-18T10:00:00Z",
                },
                "active_priority_count": 1,
                "available_keywords": ["P2", "P3"],
            },
        }

        with patch(
            "mcp_server.priority_guardian.tools.create_priority.backend_post"
        ) as mock_post, patch(
            "mcp_server.priority_guardian.tools.create_priority.backend_get"
        ) as mock_get:
            mock_post.return_value = mock_response
            mock_get.return_value = mock_get_priorities_response

            result = await handle(
                user_id="user-123",
                correlation_id="corr-123",
                arguments=valid_deadline_args,
            )

            guidance = result.structuredContent["assistant_guidance"]
            assert guidance["action"] == ACTION_PRIORITY_CREATED
            assert guidance["remaining_slots"] == 2

    @pytest.mark.asyncio
    async def test_success_guidance_zero_remaining_when_no_keywords_available(
        self, valid_deadline_args
    ):
        """Success with empty available_keywords returns remaining_slots=0."""
        mock_response = {
            "success": True,
            "data": {
                "priority": {
                    "id": "pri-123",
                    "name": "Thesis Writing",
                    "type": "deadline",
                    "calendar_keyword": "P3",
                    "status": "active",
                    "created_at": "2026-02-18T10:00:00Z",
                },
            },
        }

        # GET response with empty available_keywords (all 3 slots filled)
        mock_get_response = {
            "success": True,
            "data": {
                "priorities": [
                    {"id": "pri-1", "name": "P1", "calendar_keyword": "P1", "type": "deadline",
                     "deliverables": [], "goals": [], "status": "active"},
                    {"id": "pri-2", "name": "P2", "calendar_keyword": "P2", "type": "deadline",
                     "deliverables": [], "goals": [], "status": "active"},
                    {"id": "pri-3", "name": "P3", "calendar_keyword": "P3", "type": "deadline",
                     "deliverables": [], "goals": [], "status": "active"},
                ],
                "google_connection": {"connected": False},
                "available_keywords": [],  # No slots left
            },
        }

        with patch(
            "mcp_server.priority_guardian.tools.create_priority.backend_post"
        ) as mock_post, patch(
            "mcp_server.priority_guardian.tools.create_priority.backend_get"
        ) as mock_get:
            mock_post.return_value = mock_response
            mock_get.return_value = mock_get_response

            result = await handle(
                user_id="user-123",
                correlation_id="corr-123",
                arguments=valid_deadline_args,
            )

            guidance = result.structuredContent["assistant_guidance"]
            assert guidance["action"] == ACTION_PRIORITY_CREATED
            assert guidance["remaining_slots"] == 0

    @pytest.mark.asyncio
    async def test_success_guidance_defensive_when_available_keywords_missing(
        self, valid_deadline_args
    ):
        """Missing available_keywords returns safe guidance without crashing."""
        mock_response = {
            "success": True,
            "data": {
                "priority": {
                    "id": "pri-123",
                    "name": "Thesis Writing",
                    "type": "deadline",
                    "calendar_keyword": "P1",
                    "status": "active",
                    "created_at": "2026-02-18T10:00:00Z",
                },
            },
        }

        # GET response with missing available_keywords
        mock_get_response = {
            "success": True,
            "data": {
                "priorities": [
                    {"id": "pri-123", "name": "Thesis Writing", "calendar_keyword": "P1",
                     "type": "deadline", "deliverables": [], "goals": [], "status": "active"},
                ],
                "google_connection": {"connected": False},
                # available_keywords intentionally missing
            },
        }

        with patch(
            "mcp_server.priority_guardian.tools.create_priority.backend_post"
        ) as mock_post, patch(
            "mcp_server.priority_guardian.tools.create_priority.backend_get"
        ) as mock_get:
            mock_post.return_value = mock_response
            mock_get.return_value = mock_get_response

            result = await handle(
                user_id="user-123",
                correlation_id="corr-123",
                arguments=valid_deadline_args,
            )

            guidance = result.structuredContent["assistant_guidance"]
            assert guidance["action"] == ACTION_PRIORITY_CREATED
            # remaining_slots should be absent when available_keywords is missing
            assert "remaining_slots" not in guidance


# =============================================================================
# Backend Error Tests
# =============================================================================

class TestBackendErrors:
    """Tests for backend error responses."""

    @pytest.mark.asyncio
    async def test_backend_error_max_priorities_returns_structured_error(
        self, valid_deadline_args
    ):
        """MAX_PRIORITIES_REACHED error returns structured guidance."""
        mock_response = {
            "success": False,
            "error": {
                "code": "MAX_PRIORITIES_REACHED",
                "message": "Maximum of 3 active priorities reached",
            },
        }

        with patch(
            "mcp_server.priority_guardian.tools.create_priority.backend_post"
        ) as mock_post:
            mock_post.return_value = mock_response

            result = await handle(
                user_id="user-123",
                correlation_id="corr-123",
                arguments=valid_deadline_args,
            )

            assert result.isError is True
            assert result.structuredContent["error"]["code"] == "MAX_PRIORITIES_REACHED"
            guidance = result.structuredContent["assistant_guidance"]
            assert "retire" in guidance["instruction"].lower() or "delete" in guidance["instruction"].lower()

    @pytest.mark.asyncio
    async def test_backend_error_keyword_conflict_returns_retry_guidance(
        self, valid_deadline_args
    ):
        """KEYWORD_CONFLICT error returns retry guidance."""
        mock_response = {
            "success": False,
            "error": {
                "code": "KEYWORD_CONFLICT",
                "message": "Keyword P1 already in use",
            },
        }

        with patch(
            "mcp_server.priority_guardian.tools.create_priority.backend_post"
        ) as mock_post:
            mock_post.return_value = mock_response

            result = await handle(
                user_id="user-123",
                correlation_id="corr-123",
                arguments=valid_deadline_args,
            )

            assert result.isError is True
            guidance = result.structuredContent["assistant_guidance"]
            assert guidance["action"] == ACTION_RETRY
            assert "retry" in guidance["instruction"].lower()

    @pytest.mark.asyncio
    async def test_validation_error_guidance_does_not_leak_backend_field_names(
        self, valid_deadline_args
    ):
        """VALIDATION_ERROR guidance does NOT leak raw backend field names."""
        # Backend returns 422 with raw Pydantic field names in the message
        mock_response = {
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "weekly_hour_target is required when type is 'flexible'. "
                           "checkpoint_date must be in the future.",
            },
        }

        with patch(
            "mcp_server.priority_guardian.tools.create_priority.backend_post"
        ) as mock_post:
            mock_post.return_value = mock_response

            result = await handle(
                user_id="user-123",
                correlation_id="corr-123",
                arguments=valid_deadline_args,
            )

            assert result.isError is True
            guidance = result.structuredContent["assistant_guidance"]
            assert guidance["action"] == ACTION_ASK_CLARIFYING

            # Guidance instruction should NOT contain backend field names
            instruction = guidance["instruction"]
            assert "weekly_hour_target" not in instruction
            assert "checkpoint_date" not in instruction
            assert "type is 'flexible'" not in instruction

            # Should have generic guidance instead
            assert "missing or invalid" in instruction.lower() or "re-confirm" in instruction.lower()


# =============================================================================
# GET Failure After POST Success Tests
# =============================================================================

class TestGetFailureAfterPostSuccess:
    """Tests for GET failure after POST success (fallback behavior)."""

    @pytest.mark.asyncio
    async def test_get_failure_after_post_success_uses_post_response_data(
        self, valid_deadline_args
    ):
        """When GET fails after POST succeeds, handler uses POST response data."""
        # POST succeeds
        mock_post_response = {
            "success": True,
            "data": {
                "priority": {
                    "id": "pri-123",
                    "name": "Thesis Writing",
                    "type": "deadline",
                    "calendar_keyword": "P1",
                    "status": "active",
                    "deadline": "2026-06-01",
                    "deliverables": [],
                    "goals": [],
                    "created_at": "2026-02-18T10:00:00Z",
                },
                "active_priority_count": 1,
                "available_keywords": ["P2", "P3"],
            },
        }

        with patch(
            "mcp_server.priority_guardian.tools.create_priority.backend_post"
        ) as mock_post, patch(
            "mcp_server.priority_guardian.tools.create_priority.backend_get"
        ) as mock_get:
            mock_post.return_value = mock_post_response
            # GET raises an exception
            mock_get.side_effect = Exception("Network timeout")

            result = await handle(
                user_id="user-123",
                correlation_id="corr-123",
                arguments=valid_deadline_args,
            )

            # Should NOT crash - should return success with POST data
            assert result.isError is not True
            assert result.structuredContent["success"] is True

            # Should have the created priority in the data
            priorities = result.structuredContent["data"]["priorities"]
            assert len(priorities) == 1
            assert priorities[0]["name"] == "Thesis Writing"
            assert priorities[0]["calendarKeyword"] == "P1"

            # Should still have widget template
            # inc_96: Widget binding moved to top-level _meta
            assert result.meta is not None
            assert result.meta["ui"]["resourceUri"] == WIDGET_URI
            assert result.meta["openai/outputTemplate"] == WIDGET_URI

            # Guidance should use defensive fallback (no remaining_slots)
            guidance = result.structuredContent["assistant_guidance"]
            assert guidance["action"] == ACTION_PRIORITY_CREATED
            # remaining_slots absent when available_keywords is None
            assert "remaining_slots" not in guidance

    @pytest.mark.asyncio
    async def test_get_failure_logs_warning_and_continues(
        self, valid_deadline_args
    ):
        """When GET fails, handler logs warning but returns success."""
        mock_post_response = {
            "success": True,
            "data": {
                "priority": {
                    "id": "pri-456",
                    "name": "Thesis Writing",
                    "type": "deadline",
                    "calendar_keyword": "P2",
                    "status": "active",
                    "deadline": "2026-06-01",
                    "deliverables": [],
                    "goals": [],
                    "created_at": "2026-02-18T10:00:00Z",
                },
            },
        }

        with patch(
            "mcp_server.priority_guardian.tools.create_priority.backend_post"
        ) as mock_post, patch(
            "mcp_server.priority_guardian.tools.create_priority.backend_get"
        ) as mock_get, patch(
            "mcp_server.priority_guardian.tools.create_priority.logger"
        ) as mock_logger:
            mock_post.return_value = mock_post_response
            mock_get.side_effect = ConnectionError("Backend unreachable")

            result = await handle(
                user_id="user-123",
                correlation_id="corr-123",
                arguments=valid_deadline_args,
            )

            # Should log warning about GET failure
            mock_logger.warning.assert_called()
            call_args = mock_logger.warning.call_args
            assert "get_after_post_failed" in str(call_args)

            # Should still return success
            assert result.structuredContent["success"] is True


# =============================================================================
# Additional Provenance Tests
# =============================================================================

class TestAdditionalProvenance:
    """Additional provenance validation edge cases."""

    @pytest.mark.asyncio
    async def test_whitespace_only_goal_verbatim_returns_provenance_error(self):
        """Whitespace-only user_goal_verbatim returns provenance error."""
        result = await handle(
            user_id="user-123",
            correlation_id="corr-123",
            arguments={
                "user_priority_name_verbatim": "I want to learn Spanish",
                "name": "Learn Spanish",
                "user_priority_type_verbatim": "it's ongoing",
                "type": "flexible",
                "weekly_hour_target": 5,
                "checkpoint_date": "2026-03-15",
                "user_goal_verbatim": "   ",  # Whitespace only
                "initial_goal_text": "Hold a conversation",
            },
        )

        assert result.isError is True
        assert result.structuredContent["error"] == "empty_goal_verbatim"
        assert result.structuredContent["assistant_guidance"]["action"] == ACTION_ASK_CLARIFYING
