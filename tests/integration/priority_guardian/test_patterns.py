"""
Integration tests for pattern recognition (Increment 21).

Tests the full flow:
- Backend endpoint returns correct response shape
- MCP tool adds assistant_guidance
- Error handling
- E2E retired keyword resolution
"""

import pytest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.apps.priority_guardian.routers.pattern_router import router


# ============================================================================
# Backend Endpoint Tests
# ============================================================================

@pytest.fixture
def app():
    """Create a FastAPI app with the pattern router."""
    app = FastAPI()
    app.include_router(router, prefix="/api/priority-guardian")
    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


class TestBackendEndpoint:
    """Tests for GET /api/priority-guardian/patterns endpoint."""

    def test_returns_200_with_success_shape(self, client):
        """Endpoint returns 200 with success: true and data."""
        user_id = uuid4()

        with patch("backend.apps.priority_guardian.routers.pattern_router.compute_patterns") as mock_compute:
            mock_compute.return_value = {
                "success": True,
                "data": {
                    "pattern_engine_version": "1.0",
                    "reason": "NO_PATTERNS",
                    "data_insufficient": False,
                    "weeks_available": 6,
                    "rolling_window_months": 6,
                    "patterns": [],
                    "pattern_count": 0,
                },
            }

            response = client.get(
                "/api/priority-guardian/patterns",
                headers={"X-User-ID": str(user_id)},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data
        assert "assistant_guidance" not in data  # Backend doesn't add guidance

    def test_returns_200_with_insufficient_data(self, client):
        """Endpoint returns 200 with data_insufficient: true for new user."""
        user_id = uuid4()

        with patch("backend.apps.priority_guardian.routers.pattern_router.compute_patterns") as mock_compute:
            mock_compute.return_value = {
                "success": True,
                "data": {
                    "pattern_engine_version": "1.0",
                    "reason": "INSUFFICIENT_WEEKS",
                    "data_insufficient": True,
                    "weeks_available": 2,
                    "rolling_window_months": 6,
                    "patterns": [],
                    "pattern_count": 0,
                },
            }

            response = client.get(
                "/api/priority-guardian/patterns",
                headers={"X-User-ID": str(user_id)},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["data_insufficient"] is True
        assert data["data"]["weeks_available"] == 2

    def test_returns_401_without_user_id(self, client):
        """Endpoint returns 401 without X-User-ID header."""
        response = client.get("/api/priority-guardian/patterns")

        assert response.status_code == 401

    def test_returns_500_on_service_error(self, client):
        """Endpoint returns 500 with hardcoded error message on service failure."""
        user_id = uuid4()

        with patch("backend.apps.priority_guardian.routers.pattern_router.compute_patterns") as mock_compute:
            mock_compute.return_value = {
                "success": False,
                "error": {
                    "code": "PATTERN_COMPUTE_ERROR",
                    "message": "Pattern computation failed. Please try again.",
                },
            }

            response = client.get(
                "/api/priority-guardian/patterns",
                headers={"X-User-ID": str(user_id)},
            )

        assert response.status_code == 500
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "PATTERN_COMPUTE_ERROR"
        # Message is hardcoded constant
        assert data["error"]["message"] == "Pattern computation failed. Please try again."

    def test_response_includes_version_and_reason(self, client):
        """Endpoint response includes pattern_engine_version and reason enum."""
        user_id = uuid4()

        with patch("backend.apps.priority_guardian.routers.pattern_router.compute_patterns") as mock_compute:
            mock_compute.return_value = {
                "success": True,
                "data": {
                    "pattern_engine_version": "1.0",
                    "reason": "PATTERNS_FOUND",
                    "data_insufficient": False,
                    "weeks_available": 8,
                    "rolling_window_months": 6,
                    "patterns": [{"pattern_type": "consistency_streak"}],
                    "pattern_count": 1,
                },
            }

            response = client.get(
                "/api/priority-guardian/patterns",
                headers={"X-User-ID": str(user_id)},
            )

        data = response.json()
        assert data["data"]["pattern_engine_version"] == "1.0"
        assert data["data"]["reason"] == "PATTERNS_FOUND"


# ============================================================================
# MCP Tool Tests
# ============================================================================

class TestMCPTool:
    """Tests for get_patterns MCP tool."""

    @pytest.mark.asyncio
    async def test_tool_registered_in_registry(self):
        """get_patterns tool is registered in TOOL_REGISTRY."""
        from mcp_server.priority_guardian.tools import TOOL_REGISTRY

        assert "get_patterns" in TOOL_REGISTRY

    @pytest.mark.asyncio
    async def test_tool_metadata_correct(self):
        """Tool has correct metadata (readOnlyHint=true, no widget)."""
        from mcp_server.priority_guardian.tools import TOOL_REGISTRY

        tool_def = TOOL_REGISTRY["get_patterns"]

        assert tool_def.read_only_hint is True
        assert tool_def.open_world_hint is False
        assert tool_def.widget_uri is None
        assert tool_def.widget_accessible is False

    @pytest.mark.asyncio
    async def test_tool_invocation_messages_registered(self):
        """Tool has invocation messages registered."""
        from mcp_server.priority_guardian.tools import TOOL_INVOCATION_MESSAGES

        assert "get_patterns" in TOOL_INVOCATION_MESSAGES
        invoking, invoked = TOOL_INVOCATION_MESSAGES["get_patterns"]
        assert invoking == "Analyzing your tracking patterns..."
        assert invoked == "Here's what I found in your history."

    @pytest.mark.asyncio
    async def test_tool_adds_assistant_guidance(self):
        """Tool adds assistant_guidance based on backend response."""
        from mcp_server.priority_guardian.tools.get_patterns import handle

        with patch("mcp_server.priority_guardian.tools.get_patterns.backend_get") as mock_backend:
            mock_backend.return_value = {
                "success": True,
                "data": {
                    "pattern_engine_version": "1.0",
                    "reason": "PATTERNS_FOUND",
                    "data_insufficient": False,
                    "weeks_available": 8,
                    "rolling_window_months": 6,
                    "patterns": [{"pattern_type": "consistency_streak"}],
                    "pattern_count": 1,
                },
            }

            result = await handle(
                user_id=str(uuid4()),
                correlation_id="test-123",
                arguments={},
            )

        # Check structuredContent has assistant_guidance
        assert result.structuredContent is not None
        assert "assistant_guidance" in result.structuredContent
        # Should use PATTERNS_FOUND guidance
        assert "Present these patterns" in result.structuredContent["assistant_guidance"]

    @pytest.mark.asyncio
    async def test_tool_guidance_varies_by_state(self):
        """assistant_guidance varies by response state (reason enum)."""
        from mcp_server.priority_guardian.tools.get_patterns import handle

        # Test INSUFFICIENT_WEEKS
        with patch("mcp_server.priority_guardian.tools.get_patterns.backend_get") as mock_backend:
            mock_backend.return_value = {
                "success": True,
                "data": {
                    "pattern_engine_version": "1.0",
                    "reason": "INSUFFICIENT_WEEKS",
                    "data_insufficient": True,
                    "weeks_available": 2,
                    "rolling_window_months": 6,
                    "patterns": [],
                    "pattern_count": 0,
                },
            }

            result = await handle(str(uuid4()), "test-123", {})

        assert "2 weeks" in result.structuredContent["assistant_guidance"]
        assert "4 completed weeks" in result.structuredContent["assistant_guidance"]

        # Test NO_PATTERNS
        with patch("mcp_server.priority_guardian.tools.get_patterns.backend_get") as mock_backend:
            mock_backend.return_value = {
                "success": True,
                "data": {
                    "pattern_engine_version": "1.0",
                    "reason": "NO_PATTERNS",
                    "data_insufficient": False,
                    "weeks_available": 6,
                    "rolling_window_months": 6,
                    "patterns": [],
                    "pattern_count": 0,
                },
            }

            result = await handle(str(uuid4()), "test-123", {})

        assert "No notable patterns" in result.structuredContent["assistant_guidance"]

    @pytest.mark.asyncio
    async def test_tool_returns_error_on_backend_failure(self):
        """Tool returns isError=True on backend error."""
        from mcp_server.priority_guardian.tools.get_patterns import handle

        with patch("mcp_server.priority_guardian.tools.get_patterns.backend_get") as mock_backend:
            mock_backend.return_value = {
                "success": False,
                "error": {
                    "code": "PATTERN_COMPUTE_ERROR",
                    "message": "Pattern computation failed.",
                },
            }

            result = await handle(str(uuid4()), "test-123", {})

        assert result.isError is True
        # Error message should be generic, not expose backend error codes
        assert "PATTERN_COMPUTE_ERROR" not in result.content[0].text

    @pytest.mark.asyncio
    async def test_tool_returns_error_on_http_exception(self):
        """Tool returns isError=True on HTTP exception."""
        from mcp_server.priority_guardian.tools.get_patterns import handle
        import httpx

        with patch("mcp_server.priority_guardian.tools.get_patterns.backend_get") as mock_backend:
            mock_backend.side_effect = httpx.HTTPStatusError(
                "Internal Server Error",
                request=MagicMock(),
                response=MagicMock(status_code=500),
            )

            result = await handle(str(uuid4()), "test-123", {})

        assert result.isError is True
        # Should have generic error message
        assert "Unable to analyze patterns" in result.content[0].text

    @pytest.mark.asyncio
    async def test_guidance_instructs_not_to_use_abandoned(self):
        """assistant_guidance instructs LLM not to use the word 'abandoned'."""
        from mcp_server.priority_guardian.tools.get_patterns import (
            GUIDANCE_PATTERNS_FOUND,
        )

        # The guidance should instruct the LLM not to use "abandoned"
        assert 'do not use the word "abandoned"' in GUIDANCE_PATTERNS_FOUND.lower()

    @pytest.mark.asyncio
    async def test_guidance_doesnt_contain_pattern_type_verbatim(self):
        """assistant_guidance does not contain pattern_type strings verbatim."""
        from mcp_server.priority_guardian.tools.get_patterns import (
            GUIDANCE_PATTERNS_FOUND,
        )

        # Check that internal pattern_type values are not in guidance
        assert "consistency_streak" not in GUIDANCE_PATTERNS_FOUND
        assert "abandoned_priority" not in GUIDANCE_PATTERNS_FOUND
        assert "priority_switching" not in GUIDANCE_PATTERNS_FOUND
        assert "priority_protection" not in GUIDANCE_PATTERNS_FOUND


# ============================================================================
# E2E Tests
# ============================================================================

class TestE2EFlows:
    """End-to-end tests for specific flows."""

    @pytest.mark.asyncio
    async def test_retired_keyword_resolution_e2e(self):
        """E2E: Retired priority keyword resolved from snapshot."""
        from backend.apps.priority_guardian.services.pattern_service import (
            compute_patterns,
            get_current_week_start_utc,
        )

        user_id = uuid4()
        priority_id = uuid4()

        # Create mock session
        session = AsyncMock()

        # Create retired priority with NULL keyword
        priority = MagicMock()
        priority.id = priority_id
        priority.name = "Retired Priority"
        priority.type = "flexible"
        priority.status = "retired"
        priority.calendar_keyword = None  # NULL after retirement
        priority.retired_at = datetime(2026, 2, 4, tzinfo=timezone.utc)
        priority.created_at = datetime(2025, 10, 1, tzinfo=timezone.utc)

        # Create snapshots with keyword preserved
        snapshots = []
        base_date = date(2026, 1, 5)
        for i in range(4):
            s = MagicMock()
            s.week_start = base_date + timedelta(weeks=i)
            s.priority_id = priority_id
            s.actual_hours = Decimal("10")
            s.total_tracked_hours = Decimal("40")
            s.streak_at_snapshot = i + 1
            s.calendar_keyword_at_snapshot = "P2"  # Preserved in snapshot
            snapshots.append(s)

        # Mock query results
        snap_result = MagicMock()
        snap_result.scalars.return_value.all.return_value = snapshots

        priority_result = MagicMock()
        priority_result.scalars.return_value.all.return_value = [priority]

        session.execute.side_effect = [snap_result, priority_result]

        with patch("backend.apps.priority_guardian.services.pattern_service.get_current_week_start_utc") as mock_week:
            mock_week.return_value = date(2026, 2, 9)

            result = await compute_patterns(user_id, session)

        # Verify patterns returned with resolved keyword
        assert result["success"] is True
        patterns = result["data"]["patterns"]
        # Should have consistency_streak pattern
        streak_pattern = next(
            (p for p in patterns if p["pattern_type"] == "consistency_streak"),
            None,
        )
        if streak_pattern:
            assert streak_pattern["calendar_keyword"] == "P2"
            assert streak_pattern["priority_status"] == "retired"
            assert "None" not in streak_pattern["detail"]

    @pytest.mark.asyncio
    async def test_decimal_serialization_e2e(self):
        """E2E: Decimal values are properly serialized to float."""
        from backend.apps.priority_guardian.services.pattern_service import (
            compute_patterns,
        )

        user_id = uuid4()
        priority_id = uuid4()

        session = AsyncMock()

        # Create priority
        priority = MagicMock()
        priority.id = priority_id
        priority.name = "Test"
        priority.type = "flexible"
        priority.status = "active"
        priority.calendar_keyword = "P1"
        priority.retired_at = None
        priority.created_at = datetime(2025, 10, 1, tzinfo=timezone.utc)

        # Create snapshots with low hours for abandoned pattern
        snapshots = []
        base_date = date(2026, 1, 5)
        for i in range(4):
            s = MagicMock()
            s.week_start = base_date + timedelta(weeks=i)
            s.priority_id = priority_id
            s.actual_hours = Decimal("0.5")
            s.total_tracked_hours = Decimal("40.0")
            s.streak_at_snapshot = 0
            s.calendar_keyword_at_snapshot = "P1"
            snapshots.append(s)

        snap_result = MagicMock()
        snap_result.scalars.return_value.all.return_value = snapshots

        priority_result = MagicMock()
        priority_result.scalars.return_value.all.return_value = [priority]

        session.execute.side_effect = [snap_result, priority_result]

        with patch("backend.apps.priority_guardian.services.pattern_service.get_current_week_start_utc") as mock_week:
            mock_week.return_value = date(2026, 2, 9)

            result = await compute_patterns(user_id, session)

        # Check that numeric values are floats, not Decimals
        patterns = result["data"]["patterns"]
        if patterns:
            abandoned = next(
                (p for p in patterns if p["pattern_type"] == "abandoned_priority"),
                None,
            )
            if abandoned:
                assert isinstance(abandoned["avg_hours_last_4_weeks"], float)

        # Verify JSON serialization doesn't fail
        import json
        json.dumps(result)  # Should not raise TypeError
