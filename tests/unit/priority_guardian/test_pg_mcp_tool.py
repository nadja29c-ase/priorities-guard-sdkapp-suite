"""
Unit tests for Priority Guardian MCP tool response transformation.

Tests the create_priority MCP tool in isolation — mocks backend_post and authenticate_request
to verify:
- Success response has correct structuredContent shape with assistant_guidance
- Guidance differs when active_priority_count < 3 vs == 3
- Error responses (409, 422) produce correct error-specific guidance
"""

import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

import httpx


class TestCreatePriorityMCPTool:
    """Tests for create_priority MCP tool response transformation."""

    @pytest.fixture
    def mock_auth_context(self):
        """Standard auth context returned by authenticate_request."""
        return {
            "user_id": str(uuid4()),
            "correlation_id": "test-correlation-id",
            "scopes": ["pg.access"],
        }

    @pytest.fixture
    def mock_priority_response(self):
        """Factory for backend success responses."""
        def _make_response(keyword="P1", active_count=1, available=None):
            if available is None:
                available = ["P2", "P3"] if keyword == "P1" else ["P3"] if keyword == "P2" else []
            return {
                "success": True,
                "data": {
                    "priority": {
                        "id": str(uuid4()),
                        "name": "Test Priority",
                        "type": "deadline",
                        "calendar_keyword": keyword,
                        "status": "active",
                        "deadline": "2026-03-15",
                        "weekly_hour_target": None,
                        "checkpoint_date": None,
                        "desired_result": None,
                        "deliverables": [],
                        "created_at": "2026-02-08T12:00:00Z",
                    },
                    "active_priority_count": active_count,
                    "available_keywords": available,
                },
            }
        return _make_response

    @pytest.mark.asyncio
    async def test_success_response_has_correct_structure(
        self, mock_auth_context, mock_priority_response
    ):
        """Success response includes structuredContent with priority, count, keywords, and guidance."""
        from mcp_server.priority_guardian.server import create_priority

        backend_response = mock_priority_response(keyword="P1", active_count=1)

        with patch(
            "mcp_server.priority_guardian.server.authenticate_request",
            new_callable=AsyncMock,
            return_value=mock_auth_context,
        ), patch(
            "mcp_server.priority_guardian.server.backend_post",
            new_callable=AsyncMock,
            return_value=backend_response,
        ):
            result = await create_priority(
                name="Test Priority",
                type="deadline",
                deadline="2026-03-15",
                meta={"headers": {"authorization": "Bearer test"}},
            )

        parsed = json.loads(result)

        # Verify structuredContent shape
        assert "structuredContent" in parsed
        sc = parsed["structuredContent"]
        assert "priority" in sc
        assert "active_priority_count" in sc
        assert "available_keywords" in sc
        assert "assistant_guidance" in sc

        # Verify priority data passed through
        assert sc["priority"]["calendar_keyword"] == "P1"
        assert sc["active_priority_count"] == 1
        assert sc["available_keywords"] == ["P2", "P3"]

        # Schema stability: verify priority has exactly expected keys (no leakage, no missing)
        expected_priority_keys = {
            "id", "name", "type", "calendar_keyword", "status",
            "deadline", "weekly_hour_target", "checkpoint_date",
            "desired_result", "deliverables", "created_at"
        }
        assert set(sc["priority"].keys()) == expected_priority_keys, (
            f"Priority schema mismatch. "
            f"Extra: {set(sc['priority'].keys()) - expected_priority_keys}, "
            f"Missing: {expected_priority_keys - set(sc['priority'].keys())}"
        )

        # Verify content array
        assert "content" in parsed
        assert len(parsed["content"]) == 1
        assert parsed["content"][0]["type"] == "text"
        assert "Test Priority" in parsed["content"][0]["text"]
        assert "P1" in parsed["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_guidance_when_under_3_priorities(
        self, mock_auth_context, mock_priority_response
    ):
        """When active_priority_count < 3, guidance asks about additional priorities."""
        from mcp_server.priority_guardian.server import create_priority

        backend_response = mock_priority_response(keyword="P2", active_count=2)

        with patch(
            "mcp_server.priority_guardian.server.authenticate_request",
            new_callable=AsyncMock,
            return_value=mock_auth_context,
        ), patch(
            "mcp_server.priority_guardian.server.backend_post",
            new_callable=AsyncMock,
            return_value=backend_response,
        ):
            result = await create_priority(
                name="Test Priority",
                type="deadline",
                deadline="2026-03-15",
                meta={"headers": {"authorization": "Bearer test"}},
            )

        parsed = json.loads(result)
        guidance = parsed["structuredContent"]["assistant_guidance"]

        # Should ask about additional priorities
        assert "another priority" in guidance.lower()
        assert "1 more" in guidance  # 3 - 2 = 1 remaining

    @pytest.mark.asyncio
    async def test_guidance_when_at_3_priorities(
        self, mock_auth_context, mock_priority_response
    ):
        """When active_priority_count == 3, guidance mentions dashboard."""
        from mcp_server.priority_guardian.server import create_priority

        backend_response = mock_priority_response(keyword="P3", active_count=3, available=[])

        with patch(
            "mcp_server.priority_guardian.server.authenticate_request",
            new_callable=AsyncMock,
            return_value=mock_auth_context,
        ), patch(
            "mcp_server.priority_guardian.server.backend_post",
            new_callable=AsyncMock,
            return_value=backend_response,
        ):
            result = await create_priority(
                name="Test Priority",
                type="deadline",
                deadline="2026-03-15",
                meta={"headers": {"authorization": "Bearer test"}},
            )

        parsed = json.loads(result)
        guidance = parsed["structuredContent"]["assistant_guidance"]

        # Should mention all 3 set up and dashboard
        assert "all 3 priorities" in guidance.lower()
        assert "dashboard" in guidance.lower()
        assert "get_priorities" in guidance

    @pytest.mark.asyncio
    async def test_error_max_priorities_reached_guidance(self, mock_auth_context):
        """409 MAX_PRIORITIES_REACHED returns correct error-specific guidance."""
        from mcp_server.priority_guardian.server import create_priority

        # Create mock HTTP error response
        mock_response = MagicMock()
        mock_response.status_code = 409
        mock_response.json.return_value = {
            "success": False,
            "error": {
                "code": "MAX_PRIORITIES_REACHED",
                "message": "You already have 3 active priorities.",
            },
        }

        http_error = httpx.HTTPStatusError(
            "409 Conflict",
            request=MagicMock(),
            response=mock_response,
        )

        with patch(
            "mcp_server.priority_guardian.server.authenticate_request",
            new_callable=AsyncMock,
            return_value=mock_auth_context,
        ), patch(
            "mcp_server.priority_guardian.server.backend_post",
            new_callable=AsyncMock,
            side_effect=http_error,
        ):
            result = await create_priority(
                name="Test Priority",
                type="deadline",
                deadline="2026-03-15",
                meta={"headers": {"authorization": "Bearer test"}},
            )

        parsed = json.loads(result)

        # Verify error structure
        assert "structuredContent" in parsed
        sc = parsed["structuredContent"]
        assert "error" in sc
        assert sc["error"]["code"] == "MAX_PRIORITIES_REACHED"

        # Verify guidance mentions max reached
        guidance = sc["assistant_guidance"]
        assert "3 active priorities" in guidance.lower()
        assert "retire" in guidance.lower() or "delete" in guidance.lower()

    @pytest.mark.asyncio
    async def test_error_keyword_conflict_guidance(self, mock_auth_context):
        """409 KEYWORD_CONFLICT returns retry guidance."""
        from mcp_server.priority_guardian.server import create_priority

        mock_response = MagicMock()
        mock_response.status_code = 409
        mock_response.json.return_value = {
            "success": False,
            "error": {
                "code": "KEYWORD_CONFLICT",
                "message": "A race condition occurred.",
            },
        }

        http_error = httpx.HTTPStatusError(
            "409 Conflict",
            request=MagicMock(),
            response=mock_response,
        )

        with patch(
            "mcp_server.priority_guardian.server.authenticate_request",
            new_callable=AsyncMock,
            return_value=mock_auth_context,
        ), patch(
            "mcp_server.priority_guardian.server.backend_post",
            new_callable=AsyncMock,
            side_effect=http_error,
        ):
            result = await create_priority(
                name="Test Priority",
                type="deadline",
                deadline="2026-03-15",
                meta={"headers": {"authorization": "Bearer test"}},
            )

        parsed = json.loads(result)
        guidance = parsed["structuredContent"]["assistant_guidance"]

        # Should mention retry
        assert "retry" in guidance.lower()
        assert "race condition" in guidance.lower()

    @pytest.mark.asyncio
    async def test_error_validation_error_guidance(self, mock_auth_context):
        """422 VALIDATION_ERROR returns guidance to ask user for correct info."""
        from mcp_server.priority_guardian.server import create_priority

        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.json.return_value = {
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "deadline is required when type is 'deadline'",
            },
        }

        http_error = httpx.HTTPStatusError(
            "422 Unprocessable Entity",
            request=MagicMock(),
            response=mock_response,
        )

        with patch(
            "mcp_server.priority_guardian.server.authenticate_request",
            new_callable=AsyncMock,
            return_value=mock_auth_context,
        ), patch(
            "mcp_server.priority_guardian.server.backend_post",
            new_callable=AsyncMock,
            side_effect=http_error,
        ):
            result = await create_priority(
                name="Test Priority",
                type="deadline",
                # Missing deadline
                meta={"headers": {"authorization": "Bearer test"}},
            )

        parsed = json.loads(result)
        guidance = parsed["structuredContent"]["assistant_guidance"]

        # Should tell LLM to ask user for correct info
        assert "ask" in guidance.lower() or "provide" in guidance.lower()
        assert "do not guess" in guidance.lower()

    @pytest.mark.asyncio
    async def test_guidance_includes_calendar_keyword_tagging_reminder(
        self, mock_auth_context, mock_priority_response
    ):
        """Success guidance includes reminder to tag calendar events with keyword."""
        from mcp_server.priority_guardian.server import create_priority

        backend_response = mock_priority_response(keyword="P1", active_count=1)

        with patch(
            "mcp_server.priority_guardian.server.authenticate_request",
            new_callable=AsyncMock,
            return_value=mock_auth_context,
        ), patch(
            "mcp_server.priority_guardian.server.backend_post",
            new_callable=AsyncMock,
            return_value=backend_response,
        ):
            result = await create_priority(
                name="Test Priority",
                type="deadline",
                deadline="2026-03-15",
                meta={"headers": {"authorization": "Bearer test"}},
            )

        parsed = json.loads(result)
        guidance = parsed["structuredContent"]["assistant_guidance"]

        # Should remind about tagging calendar events
        assert "tag" in guidance.lower()
        assert "calendar" in guidance.lower()
        assert "P1" in guidance

    @pytest.mark.asyncio
    async def test_malformed_backend_error_handled_gracefully(self, mock_auth_context):
        """
        HTTPStatusError with malformed response (missing error.code) doesn't crash.

        Covers the fallback branch in the inner except httpx.HTTPStatusError handler
        when the backend returns unexpected JSON structure.
        """
        from mcp_server.priority_guardian.server import create_priority

        # Create mock HTTP error with response missing the expected error.code field
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {
            # Malformed: missing "error" object entirely
            "success": False,
            "message": "Internal server error",
        }

        http_error = httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=MagicMock(),
            response=mock_response,
        )

        with patch(
            "mcp_server.priority_guardian.server.authenticate_request",
            new_callable=AsyncMock,
            return_value=mock_auth_context,
        ), patch(
            "mcp_server.priority_guardian.server.backend_post",
            new_callable=AsyncMock,
            side_effect=http_error,
        ):
            result = await create_priority(
                name="Test Priority",
                type="deadline",
                deadline="2026-03-15",
                meta={"headers": {"authorization": "Bearer test"}},
            )

        # Should return valid JSON, not crash
        parsed = json.loads(result)

        # Verify error structure exists
        assert "structuredContent" in parsed
        sc = parsed["structuredContent"]
        assert "error" in sc
        assert "assistant_guidance" in sc

        # Guidance should be present (even if generic)
        assert len(sc["assistant_guidance"]) > 0

    @pytest.mark.asyncio
    async def test_backend_error_with_invalid_json_handled(self, mock_auth_context):
        """
        HTTPStatusError with non-JSON response doesn't crash.

        Covers edge case where backend returns HTML error page or malformed content.
        """
        from mcp_server.priority_guardian.server import create_priority

        # Create mock HTTP error where json() raises an exception
        mock_response = MagicMock()
        mock_response.status_code = 502
        mock_response.json.side_effect = json.JSONDecodeError("Expecting value", "", 0)
        mock_response.text = "<html>Bad Gateway</html>"

        http_error = httpx.HTTPStatusError(
            "502 Bad Gateway",
            request=MagicMock(),
            response=mock_response,
        )

        with patch(
            "mcp_server.priority_guardian.server.authenticate_request",
            new_callable=AsyncMock,
            return_value=mock_auth_context,
        ), patch(
            "mcp_server.priority_guardian.server.backend_post",
            new_callable=AsyncMock,
            side_effect=http_error,
        ):
            result = await create_priority(
                name="Test Priority",
                type="deadline",
                deadline="2026-03-15",
                meta={"headers": {"authorization": "Bearer test"}},
            )

        # Should return valid JSON, not crash
        parsed = json.loads(result)

        # Verify error structure exists
        assert "structuredContent" in parsed
        sc = parsed["structuredContent"]
        assert "error" in sc
        assert "assistant_guidance" in sc
