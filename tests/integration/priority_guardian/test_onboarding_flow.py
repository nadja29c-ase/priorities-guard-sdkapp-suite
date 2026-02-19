"""
Integration tests for Priority Guardian onboarding flow.

Tests full dispatcher flow for onboarding_calendar_setup tool:
- CallToolRequest → dispatcher → handler → CallToolResult
- Verifies phase sequencing and response structure
"""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from mcp import types as mcp_types


class TestOnboardingCalendarSetup:
    """Full roundtrip tests for onboarding_calendar_setup tool."""

    @pytest.fixture
    def mock_auth_context(self):
        """Auth context returned by authenticate_request."""
        return {
            "user_id": str(uuid4()),
            "correlation_id": "test-correlation-id",
        }

    @pytest.fixture
    def mock_priorities_with_connection(self):
        """Mock priorities response with Google Calendar connected."""
        return {
            "success": True,
            "data": {
                "priorities": [
                    {
                        "id": str(uuid4()),
                        "name": "Ship PG V1.0",
                        "type": "deadline",
                        "calendar_keyword": "P1",
                        "status": "active",
                        "deadline": "2026-03-15",
                    },
                    {
                        "id": str(uuid4()),
                        "name": "Client outreach",
                        "type": "flexible",
                        "calendar_keyword": "P2",
                        "status": "active",
                        "weekly_hour_target": 10,
                        "checkpoint_date": "2026-03-01",
                    },
                ],
                "google_connection": {"connected": True, "connected_at": "2026-02-01T00:00:00Z"},
                "available_keywords": ["P3"],
            },
        }

    @pytest.fixture
    def mock_past_week_no_snapshot(self):
        """Mock past week report with no snapshot (new user)."""
        return {
            "success": True,
            "data": {
                "week_start": "2026-02-10",
                "week_end": "2026-02-16",
                "is_current_week": False,
                "snapshot_saved": False,
                "priorities": [],
                "time_allocation": {
                    "total_tracked_hours": 0,
                    "keywords": {},
                    "other_hours": 0,
                },
                "all_events": [],
            },
        }

    @pytest.fixture
    def mock_past_week_with_snapshot(self):
        """Mock past week report with snapshot (returning user)."""
        return {
            "success": True,
            "data": {
                "week_start": "2026-02-10",
                "week_end": "2026-02-16",
                "is_current_week": False,
                "snapshot_saved": True,
                "priorities": [],
                "time_allocation": {
                    "total_tracked_hours": 20,
                    "keywords": {"P1": {"hours": 10, "event_count": 5}},
                    "other_hours": 10,
                },
                "all_events": [],
            },
        }

    @pytest.fixture
    def mock_current_week_with_keywords(self):
        """Mock current week report with keyword-matched hours."""
        return {
            "success": True,
            "data": {
                "week_start": "2026-02-17",
                "week_end": "2026-02-23",
                "is_current_week": True,
                "snapshot_saved": False,
                "priorities": [
                    {
                        "id": str(uuid4()),
                        "name": "Ship PG V1.0",
                        "type": "deadline",
                        "calendar_keyword": "P1",
                        "actual_hours": 8.0,
                        "event_count": 5,
                        "deadline_date": "2026-03-15",
                        "days_remaining": 24,
                    },
                    {
                        "id": str(uuid4()),
                        "name": "Client outreach",
                        "type": "flexible",
                        "calendar_keyword": "P2",
                        "actual_hours": 4.0,
                        "event_count": 3,
                        "target_hours": 10.0,
                        "flex_status": "behind",
                    },
                ],
                "time_allocation": {
                    "total_tracked_hours": 24.5,
                    "keywords": {
                        "P1": {"hours": 8.0, "event_count": 5},
                        "P2": {"hours": 4.0, "event_count": 3},
                        "P3": {"hours": 0.0, "event_count": 0},
                    },
                    "other_hours": 12.5,
                },
                "all_events": [
                    {
                        "title": "P1: Design review",
                        "start": "2026-02-17T10:00:00",
                        "end": "2026-02-17T12:00:00",
                        "matched_keywords": ["P1"],
                    },
                    {
                        "title": "Team standup",
                        "start": "2026-02-17T09:00:00",
                        "end": "2026-02-17T09:30:00",
                        "matched_keywords": [],
                    },
                ],
            },
        }

    @pytest.mark.asyncio
    async def test_keyword_education_with_real_priorities(
        self,
        mock_auth_context,
        mock_priorities_with_connection,
        mock_past_week_no_snapshot,
    ):
        """Create user with 2 priorities, call keyword_education phase, assert response contains correct priority names and keywords."""
        from mcp_server.priority_guardian.handlers.tools import call_tool_request

        request = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(
                name="onboarding_calendar_setup",
                arguments={"phase": "keyword_education"},
            ),
        )

        with patch(
            "mcp_server.priority_guardian.handlers.tools.authenticate_request",
            new_callable=AsyncMock,
            return_value=mock_auth_context,
        ), patch(
            "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
            new_callable=AsyncMock,
            side_effect=[mock_past_week_no_snapshot, mock_priorities_with_connection],
        ):
            result = await call_tool_request(request)

        # Verify structure
        assert isinstance(result, mcp_types.CallToolResult)
        assert result.isError is not True

        # Verify structuredContent
        sc = result.structuredContent
        assert sc["success"] is True
        assert "data" in sc
        assert "priorities" in sc["data"]
        assert len(sc["data"]["priorities"]) == 2

        # Verify priority data
        p1 = sc["data"]["priorities"][0]
        assert p1["name"] == "Ship PG V1.0"
        assert p1["calendarKeyword"] == "P1"

        p2 = sc["data"]["priorities"][1]
        assert p2["name"] == "Client outreach"
        assert p2["calendarKeyword"] == "P2"

        # Verify assistant_guidance
        guidance = sc["assistant_guidance"]
        assert guidance["action"] == "KEYWORD_EDUCATION"
        assert guidance["next_phase"] == "first_snapshot"
        assert len(guidance["priorities"]) == 2
        assert guidance["priorities"][0]["name"] == "Ship PG V1.0"
        assert guidance["priorities"][0]["keyword"] == "P1"

        # Verify _meta
        assert sc["_meta"]["openai/outputTemplate"] == "ui://widget/pg-dashboard.html"

    @pytest.mark.asyncio
    async def test_first_snapshot_with_tagged_events(
        self,
        mock_auth_context,
        mock_past_week_no_snapshot,
        mock_current_week_with_keywords,
    ):
        """Create user with priorities and calendar connection, call first_snapshot, assert response includes weekly allocation data."""
        from mcp_server.priority_guardian.handlers.tools import call_tool_request

        request = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(
                name="onboarding_calendar_setup",
                arguments={"phase": "first_snapshot"},
            ),
        )

        with patch(
            "mcp_server.priority_guardian.handlers.tools.authenticate_request",
            new_callable=AsyncMock,
            return_value=mock_auth_context,
        ), patch(
            "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
            new_callable=AsyncMock,
            side_effect=[mock_past_week_no_snapshot, mock_current_week_with_keywords],
        ):
            result = await call_tool_request(request)

        # Verify structure
        assert isinstance(result, mcp_types.CallToolResult)
        assert result.isError is not True

        # Verify structuredContent
        sc = result.structuredContent
        assert sc["success"] is True

        # Verify weekly data
        data = sc["data"]
        assert data["weekStart"] == "2026-02-17"
        assert data["weekEnd"] == "2026-02-23"
        assert data["isCurrentWeek"] is True

        # Verify time allocation
        ta = data["timeAllocation"]
        assert ta["totalTrackedHours"] == 24.5
        assert ta["keywords"]["P1"]["hours"] == 8.0
        assert ta["keywords"]["P2"]["hours"] == 4.0
        assert ta["otherHours"] == 12.5

        # Verify priorities
        assert len(data["priorities"]) == 2
        assert data["priorities"][0]["actualHours"] == 8.0

        # Verify events
        assert len(data["allEvents"]) == 2

        # Verify guidance
        guidance = sc["assistant_guidance"]
        assert guidance["action"] == "FIRST_SNAPSHOT"
        assert guidance["next_phase"] == "reflection_setup"
        assert "deliverable_education" in guidance
        assert "instruction" in guidance["deliverable_education"]

        # Verify text content
        assert "24.5h" in result.content[0].text

    @pytest.mark.asyncio
    async def test_first_snapshot_already_onboarded_rejected(
        self,
        mock_auth_context,
        mock_past_week_with_snapshot,
    ):
        """Create user with past snapshots, call first_snapshot, assert error response."""
        from mcp_server.priority_guardian.handlers.tools import call_tool_request

        request = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(
                name="onboarding_calendar_setup",
                arguments={"phase": "first_snapshot"},
            ),
        )

        with patch(
            "mcp_server.priority_guardian.handlers.tools.authenticate_request",
            new_callable=AsyncMock,
            return_value=mock_auth_context,
        ), patch(
            "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
            new_callable=AsyncMock,
            return_value=mock_past_week_with_snapshot,
        ):
            result = await call_tool_request(request)

        # Verify error response
        assert isinstance(result, mcp_types.CallToolResult)
        assert result.isError is True

        # Verify error message
        error_text = result.content[0].text.lower()
        assert "already" in error_text
        assert "get_weekly_report" in result.content[0].text

    @pytest.mark.asyncio
    async def test_full_onboarding_sequence(
        self,
        mock_auth_context,
        mock_priorities_with_connection,
        mock_past_week_no_snapshot,
        mock_current_week_with_keywords,
    ):
        """Call all three phases in order, assert each returns expected guidance with correct next_phase / onboarding_complete."""
        from mcp_server.priority_guardian.handlers.tools import call_tool_request

        # Phase 1: keyword_education
        request1 = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(
                name="onboarding_calendar_setup",
                arguments={"phase": "keyword_education"},
            ),
        )

        with patch(
            "mcp_server.priority_guardian.handlers.tools.authenticate_request",
            new_callable=AsyncMock,
            return_value=mock_auth_context,
        ), patch(
            "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
            new_callable=AsyncMock,
            side_effect=[mock_past_week_no_snapshot, mock_priorities_with_connection],
        ):
            result1 = await call_tool_request(request1)

        assert result1.isError is not True
        assert result1.structuredContent["assistant_guidance"]["action"] == "KEYWORD_EDUCATION"
        assert result1.structuredContent["assistant_guidance"]["next_phase"] == "first_snapshot"

        # Phase 2: first_snapshot
        request2 = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(
                name="onboarding_calendar_setup",
                arguments={"phase": "first_snapshot"},
            ),
        )

        with patch(
            "mcp_server.priority_guardian.handlers.tools.authenticate_request",
            new_callable=AsyncMock,
            return_value=mock_auth_context,
        ), patch(
            "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
            new_callable=AsyncMock,
            side_effect=[mock_past_week_no_snapshot, mock_current_week_with_keywords],
        ):
            result2 = await call_tool_request(request2)

        assert result2.isError is not True
        assert result2.structuredContent["assistant_guidance"]["action"] == "FIRST_SNAPSHOT"
        assert result2.structuredContent["assistant_guidance"]["next_phase"] == "reflection_setup"
        assert "deliverable_education" in result2.structuredContent["assistant_guidance"]

        # Phase 3: reflection_setup
        request3 = mcp_types.CallToolRequest(
            method="tools/call",
            params=mcp_types.CallToolRequestParams(
                name="onboarding_calendar_setup",
                arguments={"phase": "reflection_setup"},
            ),
        )

        with patch(
            "mcp_server.priority_guardian.handlers.tools.authenticate_request",
            new_callable=AsyncMock,
            return_value=mock_auth_context,
        ):
            result3 = await call_tool_request(request3)

        assert result3.isError is not True
        assert result3.structuredContent["assistant_guidance"]["action"] == "REFLECTION_SETUP"
        assert result3.structuredContent["assistant_guidance"]["onboarding_complete"] is True
        assert "next_phase" not in result3.structuredContent["assistant_guidance"]
