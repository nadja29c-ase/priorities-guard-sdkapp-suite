"""
Unit tests for onboarding_calendar_setup tool.

Tests phase-based onboarding flow for calendar setup and first snapshot.
"""

import pytest
from unittest.mock import AsyncMock, patch

from mcp_server.priority_guardian.tools.onboarding_calendar_setup import (
    ONBOARDING_CALENDAR_SETUP,
    handle,
    _handle_keyword_education,
    _handle_first_snapshot,
    _handle_reflection_setup,
)
from mcp_server.priority_guardian.tools.base import ToolUsageError


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_priorities_response():
    """Mock successful priorities response with connection."""
    return {
        "success": True,
        "data": {
            "priorities": [
                {
                    "id": "p1",
                    "name": "Ship PG V1.0",
                    "type": "deadline",
                    "calendar_keyword": "P1",
                    "status": "active",
                },
                {
                    "id": "p2",
                    "name": "Client outreach",
                    "type": "flexible",
                    "calendar_keyword": "P2",
                    "status": "active",
                },
            ],
            "google_connection": {"connected": True},
            "available_keywords": ["P3"],
        },
    }


@pytest.fixture
def mock_priorities_no_connection():
    """Mock priorities response without Google connection."""
    return {
        "success": True,
        "data": {
            "priorities": [
                {
                    "id": "p1",
                    "name": "Test Priority",
                    "type": "deadline",
                    "calendar_keyword": "P1",
                    "status": "active",
                },
            ],
            "google_connection": {"connected": False},
            "available_keywords": ["P2", "P3"],
        },
    }


@pytest.fixture
def mock_priorities_empty():
    """Mock priorities response with no priorities."""
    return {
        "success": True,
        "data": {
            "priorities": [],
            "google_connection": {"connected": True},
            "available_keywords": ["P1", "P2", "P3"],
        },
    }


@pytest.fixture
def mock_weekly_report_with_keywords():
    """Mock weekly report with keyword-matched hours."""
    return {
        "success": True,
        "data": {
            "week_start": "2026-02-17",
            "week_end": "2026-02-23",
            "is_current_week": True,
            "snapshot_saved": False,
            "priorities": [
                {
                    "id": "p1",
                    "name": "Ship PG V1.0",
                    "type": "deadline",
                    "calendar_keyword": "P1",
                    "actual_hours": 8.0,
                    "event_count": 5,
                    "deadline_date": "2026-03-15",
                    "days_remaining": 24,
                },
                {
                    "id": "p2",
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
                {"title": "P1: Design review", "start": "2026-02-17T10:00:00", "end": "2026-02-17T12:00:00", "matched_keywords": ["P1"]},
                {"title": "Team standup", "start": "2026-02-17T09:00:00", "end": "2026-02-17T09:30:00", "matched_keywords": []},
            ],
        },
    }


@pytest.fixture
def mock_weekly_report_zero_keywords():
    """Mock weekly report with events but no keyword matches."""
    return {
        "success": True,
        "data": {
            "week_start": "2026-02-17",
            "week_end": "2026-02-23",
            "is_current_week": True,
            "snapshot_saved": False,
            "priorities": [
                {
                    "id": "p1",
                    "name": "Ship PG V1.0",
                    "type": "deadline",
                    "calendar_keyword": "P1",
                    "actual_hours": 0.0,
                    "event_count": 0,
                },
            ],
            "time_allocation": {
                "total_tracked_hours": 15.0,
                "keywords": {
                    "P1": {"hours": 0.0, "event_count": 0},
                    "P2": {"hours": 0.0, "event_count": 0},
                    "P3": {"hours": 0.0, "event_count": 0},
                },
                "other_hours": 15.0,
            },
            "all_events": [],
        },
    }


@pytest.fixture
def mock_past_week_with_snapshot():
    """Mock past week report with snapshot_saved=True."""
    return {
        "success": True,
        "data": {
            "week_start": "2026-02-10",
            "week_end": "2026-02-16",
            "is_current_week": False,
            "snapshot_saved": True,
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
def mock_past_week_no_snapshot():
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


# ============================================================================
# Test: Tool Definition
# ============================================================================

def test_tool_is_read_only():
    """Assert read_only_hint=True on tool definition."""
    assert ONBOARDING_CALENDAR_SETUP.read_only_hint is True


def test_tool_not_widget_accessible():
    """Assert tool is not widget-callable."""
    assert ONBOARDING_CALENDAR_SETUP.widget_accessible is False


def test_schema_rejects_invalid_phase():
    """Assert schema has proper enum validation."""
    schema = ONBOARDING_CALENDAR_SETUP.input_schema
    assert schema["properties"]["phase"]["enum"] == [
        "keyword_education",
        "first_snapshot",
        "reflection_setup",
    ]
    assert schema["additionalProperties"] is False


# ============================================================================
# Test: keyword_education phase
# ============================================================================

@pytest.mark.asyncio
async def test_keyword_education_returns_priorities_with_keywords(
    mock_priorities_response,
    mock_past_week_no_snapshot,
):
    """Mock backend returning 2 active priorities. Assert guidance includes priority names and keywords."""
    with patch(
        "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
        new_callable=AsyncMock,
    ) as mock_get:
        # First call: past week check (no snapshot)
        # Second call: priorities
        mock_get.side_effect = [mock_past_week_no_snapshot, mock_priorities_response]

        result = await handle("user-123", "corr-123", {"phase": "keyword_education"})

        assert result.isError is not True
        assert result.structuredContent["success"] is True

        guidance = result.structuredContent["assistant_guidance"]
        assert guidance["action"] == "KEYWORD_EDUCATION"
        assert guidance["next_phase"] == "first_snapshot"

        # Check priorities in guidance
        priorities = guidance["priorities"]
        assert len(priorities) == 2
        assert priorities[0]["name"] == "Ship PG V1.0"
        assert priorities[0]["keyword"] == "P1"
        assert priorities[1]["name"] == "Client outreach"
        assert priorities[1]["keyword"] == "P2"


@pytest.mark.asyncio
async def test_keyword_education_no_connection_returns_error(
    mock_priorities_no_connection,
    mock_past_week_no_snapshot,
):
    """Mock backend returning no connection. Assert isError=True with guidance to connect via dashboard."""
    with patch(
        "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
        new_callable=AsyncMock,
    ) as mock_get:
        mock_get.side_effect = [mock_past_week_no_snapshot, mock_priorities_no_connection]

        result = await handle("user-123", "corr-123", {"phase": "keyword_education"})

        assert result.isError is True
        assert "isn't connected" in result.content[0].text.lower()
        assert "dashboard" in result.content[0].text.lower()


@pytest.mark.asyncio
async def test_keyword_education_no_priorities_returns_error(
    mock_priorities_empty,
    mock_past_week_no_snapshot,
):
    """Mock backend returning 0 priorities. Assert error guidance."""
    with patch(
        "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
        new_callable=AsyncMock,
    ) as mock_get:
        mock_get.side_effect = [mock_past_week_no_snapshot, mock_priorities_empty]

        result = await handle("user-123", "corr-123", {"phase": "keyword_education"})

        assert result.isError is True
        assert "priority" in result.content[0].text.lower()


# ============================================================================
# Test: first_snapshot phase
# ============================================================================

@pytest.mark.asyncio
async def test_first_snapshot_returns_weekly_data(
    mock_weekly_report_with_keywords,
    mock_past_week_no_snapshot,
):
    """Mock backend returning current week report with tagged hours. Assert response includes snapshot data and deliverable_education."""
    with patch(
        "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
        new_callable=AsyncMock,
    ) as mock_get:
        mock_get.side_effect = [mock_past_week_no_snapshot, mock_weekly_report_with_keywords]

        result = await handle("user-123", "corr-123", {"phase": "first_snapshot"})

        assert result.isError is not True
        assert result.structuredContent["success"] is True

        data = result.structuredContent["data"]
        assert data["weekStart"] == "2026-02-17"
        assert data["weekEnd"] == "2026-02-23"
        assert data["isCurrentWeek"] is True
        assert data["timeAllocation"]["totalTrackedHours"] == 24.5

        guidance = result.structuredContent["assistant_guidance"]
        assert guidance["action"] == "FIRST_SNAPSHOT"
        assert guidance["next_phase"] == "reflection_setup"
        assert "deliverable_education" in guidance
        assert "instruction" in guidance["deliverable_education"]


@pytest.mark.asyncio
async def test_first_snapshot_zero_keyword_hours_returns_retry_guidance(
    mock_weekly_report_zero_keywords,
    mock_past_week_no_snapshot,
):
    """Mock backend returning 0 priority hours, >0 other hours. Assert guidance tells user keywords aren't reflected yet."""
    with patch(
        "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
        new_callable=AsyncMock,
    ) as mock_get:
        mock_get.side_effect = [mock_past_week_no_snapshot, mock_weekly_report_zero_keywords]

        result = await handle("user-123", "corr-123", {"phase": "first_snapshot"})

        assert result.isError is True
        text = result.content[0].text.lower()
        assert "keyword" in text
        assert "try again" in text or "sync" in text


@pytest.mark.asyncio
async def test_first_snapshot_already_onboarded_returns_error(
    mock_past_week_with_snapshot,
):
    """Mock backend indicating past snapshots exist. Assert error guidance saying user appears to have been using PG."""
    with patch(
        "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
        new_callable=AsyncMock,
    ) as mock_get:
        mock_get.return_value = mock_past_week_with_snapshot

        result = await handle("user-123", "corr-123", {"phase": "first_snapshot"})

        assert result.isError is True
        text = result.content[0].text.lower()
        assert "appear" in text or "already" in text
        assert "get_weekly_report" in result.content[0].text


# ============================================================================
# Test: reflection_setup phase
# ============================================================================

@pytest.mark.asyncio
async def test_reflection_setup_returns_guidance_only(mock_past_week_no_snapshot):
    """Call with phase reflection_setup. Assert guidance includes onboarding_complete: true."""
    with patch(
        "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
        new_callable=AsyncMock,
        return_value=mock_past_week_no_snapshot,
    ):
        result = await handle("user-123", "corr-123", {"phase": "reflection_setup"})

        assert result.isError is not True
        assert result.structuredContent["success"] is True

        guidance = result.structuredContent["assistant_guidance"]
        assert guidance["action"] == "REFLECTION_SETUP"
        assert guidance["onboarding_complete"] is True


@pytest.mark.asyncio
async def test_reflection_setup_already_onboarded_returns_error(mock_past_week_with_snapshot):
    """reflection_setup with past snapshots returns error."""
    with patch(
        "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
        new_callable=AsyncMock,
        return_value=mock_past_week_with_snapshot,
    ):
        result = await handle("user-123", "corr-123", {"phase": "reflection_setup"})

        assert result.isError is True
        text = result.content[0].text.lower()
        assert "already" in text or "appear" in text
        assert "get_weekly_report" in result.content[0].text


# ============================================================================
# Test: Input validation
# ============================================================================

@pytest.mark.asyncio
async def test_missing_phase_raises_error():
    """Assert missing phase raises ToolUsageError."""
    with pytest.raises(ToolUsageError, match="phase is required"):
        await handle("user-123", "corr-123", {})


@pytest.mark.asyncio
async def test_invalid_phase_raises_error():
    """Assert invalid phase raises ToolUsageError."""
    with pytest.raises(ToolUsageError, match="Invalid phase"):
        await handle("user-123", "corr-123", {"phase": "invalid_phase"})
