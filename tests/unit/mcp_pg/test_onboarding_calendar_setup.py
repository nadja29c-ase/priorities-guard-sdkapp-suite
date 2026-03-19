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
    _handle_first_weekly_report,
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

def test_tool_metadata():
    """Assert all tool metadata is correctly set."""
    assert ONBOARDING_CALENDAR_SETUP.name == "onboarding_calendar_setup"
    assert ONBOARDING_CALENDAR_SETUP.read_only_hint is True
    assert ONBOARDING_CALENDAR_SETUP.widget_accessible is False
    assert ONBOARDING_CALENDAR_SETUP.open_world_hint is True
    assert ONBOARDING_CALENDAR_SETUP.required_scopes == ["pg.access"]
    assert ONBOARDING_CALENDAR_SETUP.widget_uri is None


def test_schema_rejects_invalid_phase():
    """Assert schema has proper enum validation."""
    schema = ONBOARDING_CALENDAR_SETUP.input_schema
    assert schema["properties"]["phase"]["enum"] == [
        "keyword_education",
        "first_weekly_report",
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
        assert guidance["next_phase"] == "first_weekly_report"

        # Check priorities in guidance
        priorities = guidance["priorities"]
        assert len(priorities) == 2
        assert priorities[0]["name"] == "Ship PG V1.0"
        assert priorities[0]["keyword"] == "P1"
        assert priorities[1]["name"] == "Client outreach"
        assert priorities[1]["keyword"] == "P2"

        # Verify no widget rendering from this phase
        assert "_meta" not in result.structuredContent


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
        assert "full dashboard" in result.content[0].text.lower()


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
        assert "at least one priority" in result.content[0].text.lower()


@pytest.mark.asyncio
async def test_keyword_education_possible_returning_user_logs_but_continues(
    mock_past_week_with_snapshot,
    mock_priorities_response,
):
    """Mock past weekly report returning snapshot_saved=True, AND mock /priorities returning valid data. Assert tool does NOT return isError=True. Assert response contains KEYWORD_EDUCATION guidance."""
    with patch(
        "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
        new_callable=AsyncMock,
    ) as mock_get:
        # First call: past week check (has snapshot), second call: priorities
        mock_get.side_effect = [mock_past_week_with_snapshot, mock_priorities_response]

        result = await handle("user-123", "corr-123", {"phase": "keyword_education"})

        # Should NOT be an error - logs warning but continues
        assert result.isError is not True
        assert result.structuredContent["success"] is True
        assert result.structuredContent["assistant_guidance"]["action"] == "KEYWORD_EDUCATION"

        # Check priorities still returned
        priorities = result.structuredContent["assistant_guidance"]["priorities"]
        assert len(priorities) == 2


# ============================================================================
# Test: first_weekly_report phase
# ============================================================================

@pytest.mark.asyncio
async def test_first_weekly_report_returns_weekly_data(
    mock_weekly_report_with_keywords,
    mock_past_week_no_snapshot,
):
    """Mock backend returning current week report with tagged hours. Assert response includes snapshot data and deliverable_education."""
    with patch(
        "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
        new_callable=AsyncMock,
    ) as mock_get:
        mock_get.side_effect = [mock_past_week_no_snapshot, mock_weekly_report_with_keywords]

        result = await handle("user-123", "corr-123", {"phase": "first_weekly_report"})

        assert result.isError is not True
        assert result.structuredContent["success"] is True

        data = result.structuredContent["data"]
        assert data["weekStart"] == "2026-02-17"
        assert data["weekEnd"] == "2026-02-23"
        assert data["isCurrentWeek"] is True
        assert data["timeAllocation"]["totalTrackedHours"] == 24.5

        # Assert no snake_case leakage in response
        assert "week_start" not in data
        assert "time_allocation" not in data
        assert "all_events" not in data
        assert "is_current_week" not in data

        guidance = result.structuredContent["assistant_guidance"]
        assert guidance["action"] == "FIRST_WEEKLY_REPORT"
        assert guidance["next_phase"] == "reflection_setup"
        assert "deliverable_education" in guidance
        assert "instruction" in guidance["deliverable_education"]

        # Verify no status fields in normalized priorities
        for priority in data["priorities"]:
            assert "flexStatus" not in priority
            assert "pacingStatus" not in priority

        # Verify widget_instruction structure
        assert "widget_instruction" in guidance
        assert guidance["widget_instruction"]["required"] is True
        assert guidance["widget_instruction"]["tool"] == "get_weekly_report"
        assert "week_start" in guidance["widget_instruction"]["arguments"]

        # Verify transition_prompt structure
        assert "transition_prompt" in guidance
        assert guidance["transition_prompt"]["required"] is True

        # Verify no widget rendering from this tool (no _meta)
        assert "_meta" not in result.structuredContent


@pytest.mark.asyncio
async def test_first_weekly_report_zero_keyword_hours_returns_retry_guidance(
    mock_weekly_report_zero_keywords,
    mock_past_week_no_snapshot,
):
    """Mock backend returning 0 priority hours, >0 other hours. Assert guidance tells user keywords aren't reflected yet."""
    with patch(
        "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
        new_callable=AsyncMock,
    ) as mock_get:
        mock_get.side_effect = [mock_past_week_no_snapshot, mock_weekly_report_zero_keywords]

        result = await handle("user-123", "corr-123", {"phase": "first_weekly_report"})

        assert result.isError is True
        assert "keywords aren't reflected yet" in result.content[0].text.lower()


@pytest.mark.asyncio
async def test_first_weekly_report_empty_week_returns_no_events(
    mock_past_week_no_snapshot,
):
    """Mock backend returning total_tracked_hours=0. Assert error about no events found."""
    mock_empty_week = {
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
                "total_tracked_hours": 0.0,
                "keywords": {
                    "P1": {"hours": 0.0, "event_count": 0},
                },
                "other_hours": 0.0,
            },
            "all_events": [],
        },
    }

    with patch(
        "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
        new_callable=AsyncMock,
    ) as mock_get:
        mock_get.side_effect = [mock_past_week_no_snapshot, mock_empty_week]

        result = await handle("user-123", "corr-123", {"phase": "first_weekly_report"})

        assert result.isError is True
        assert "no calendar events found" in result.content[0].text.lower()


@pytest.mark.asyncio
async def test_first_weekly_report_google_not_connected(
    mock_past_week_no_snapshot,
):
    """Mock backend returning GOOGLE_NOT_CONNECTED error. Assert error with full dashboard guidance."""
    mock_not_connected = {
        "success": False,
        "error": {
            "code": "GOOGLE_NOT_CONNECTED",
            "message": "Google Calendar not connected",
        },
    }

    with patch(
        "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
        new_callable=AsyncMock,
    ) as mock_get:
        mock_get.side_effect = [mock_past_week_no_snapshot, mock_not_connected]

        result = await handle("user-123", "corr-123", {"phase": "first_weekly_report"})

        assert result.isError is True
        assert "full dashboard" in result.content[0].text.lower()


@pytest.mark.asyncio
async def test_first_weekly_report_without_keyword_phase_still_works(
    mock_past_week_no_snapshot,
):
    """Call first_weekly_report directly without prior keyword_education. Confirms stateless design."""
    mock_valid_report = {
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
                    "actual_hours": 4.0,
                    "event_count": 3,
                },
            ],
            "time_allocation": {
                "total_tracked_hours": 12.0,
                "keywords": {"P1": {"hours": 4.0, "event_count": 3}},
                "other_hours": 8.0,
            },
            "all_events": [],
        },
    }

    with patch(
        "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
        new_callable=AsyncMock,
    ) as mock_get:
        mock_get.side_effect = [mock_past_week_no_snapshot, mock_valid_report]

        # Call first_weekly_report directly — no prior keyword_education call
        result = await handle("user-123", "corr-123", {"phase": "first_weekly_report"})

        assert result.isError is not True
        assert result.structuredContent["assistant_guidance"]["action"] == "FIRST_WEEKLY_REPORT"


@pytest.mark.asyncio
async def test_first_weekly_report_unknown_backend_error(
    mock_past_week_no_snapshot,
):
    """Mock backend returning unexpected error code. Assert ToolUsageError raised."""
    mock_error_response = {
        "success": False,
        "error": {
            "code": "SOMETHING_UNEXPECTED",
            "message": "Unexpected failure",
        },
    }

    with patch(
        "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
        new_callable=AsyncMock,
    ) as mock_get:
        mock_get.side_effect = [mock_past_week_no_snapshot, mock_error_response]

        with pytest.raises(ToolUsageError, match="Unexpected failure"):
            await handle("user-123", "corr-123", {"phase": "first_weekly_report"})


@pytest.mark.asyncio
async def test_first_weekly_report_only_priority_hours_no_other(
    mock_past_week_no_snapshot,
):
    """Mock report with priority hours but zero other_hours. Assert success."""
    mock_priority_only = {
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
                    "actual_hours": 6.0,
                    "event_count": 4,
                },
                {
                    "id": "p2",
                    "name": "Client outreach",
                    "type": "flexible",
                    "calendar_keyword": "P2",
                    "actual_hours": 2.0,
                    "event_count": 2,
                },
            ],
            "time_allocation": {
                "total_tracked_hours": 8.0,
                "keywords": {
                    "P1": {"hours": 6.0, "event_count": 4},
                    "P2": {"hours": 2.0, "event_count": 2},
                    "P3": {"hours": 0.0, "event_count": 0},
                },
                "other_hours": 0.0,
            },
            "all_events": [],
        },
    }

    with patch(
        "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
        new_callable=AsyncMock,
    ) as mock_get:
        mock_get.side_effect = [mock_past_week_no_snapshot, mock_priority_only]

        result = await handle("user-123", "corr-123", {"phase": "first_weekly_report"})

        assert result.isError is not True
        assert result.structuredContent["data"]["timeAllocation"]["otherHours"] == 0


@pytest.mark.asyncio
async def test_first_weekly_report_past_snapshots_logs_warning_but_continues(
    mock_past_week_with_snapshot,
    mock_weekly_report_with_keywords,
):
    """Mock backend indicating past snapshots exist. Assert tool logs warning but continues (no isError)."""
    with patch(
        "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
        new_callable=AsyncMock,
    ) as mock_get:
        # First call: past week check (has snapshot), second call: current week
        mock_get.side_effect = [mock_past_week_with_snapshot, mock_weekly_report_with_keywords]

        result = await handle("user-123", "corr-123", {"phase": "first_weekly_report"})

        # Should NOT be an error - logs warning but continues
        assert result.isError is not True
        assert result.structuredContent["success"] is True
        assert result.structuredContent["assistant_guidance"]["action"] == "FIRST_WEEKLY_REPORT"


# ============================================================================
# Test: reflection_setup phase
# ============================================================================

@pytest.mark.asyncio
async def test_reflection_setup_returns_guidance_only():
    """Call with phase reflection_setup. Assert guidance includes onboarding_complete: true."""
    # No mock needed — reflection_setup makes no backend calls
    result = await handle("user-123", "corr-123", {"phase": "reflection_setup"})

    assert result.isError is not True
    assert result.structuredContent["success"] is True

    guidance = result.structuredContent["assistant_guidance"]
    assert guidance["action"] == "REFLECTION_SETUP"
    assert guidance["onboarding_complete"] is True

    # Verify no widget rendering from this phase
    assert "_meta" not in result.structuredContent


@pytest.mark.asyncio
async def test_reflection_setup_no_backend_call():
    """Assert reflection_setup does NOT call backend_get (purely guidance)."""
    with patch(
        "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
        new_callable=AsyncMock,
    ) as mock_get:
        result = await handle("user-123", "corr-123", {"phase": "reflection_setup"})

        # Verify no backend calls were made
        mock_get.assert_not_called()

        # Still returns success
        assert result.isError is not True
        assert result.structuredContent["success"] is True


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


# ============================================================================
# Test: Status fields and terminology
# ============================================================================

@pytest.mark.asyncio
async def test_first_weekly_report_no_status_fields_in_response(
    mock_weekly_report_with_keywords,
    mock_past_week_no_snapshot,
):
    """Verify flexStatus and pacingStatus are absent from normalized priorities even when backend includes them."""
    with patch(
        "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
        new_callable=AsyncMock,
    ) as mock_get:
        mock_get.side_effect = [mock_past_week_no_snapshot, mock_weekly_report_with_keywords]

        result = await handle("user-123", "corr-123", {"phase": "first_weekly_report"})

        assert result.isError is not True
        data = result.structuredContent["data"]

        # Backend mock includes flex_status but normalized response should not
        for priority in data["priorities"]:
            assert "flexStatus" not in priority
            assert "pacingStatus" not in priority


@pytest.mark.asyncio
async def test_keyword_education_instruction_contains_weekly_report_terminology(
    mock_priorities_response,
    mock_past_week_no_snapshot,
):
    """Assert instruction uses 'weekly report' and not 'snapshot' or 'allocation'."""
    with patch(
        "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
        new_callable=AsyncMock,
    ) as mock_get:
        mock_get.side_effect = [mock_past_week_no_snapshot, mock_priorities_response]

        result = await handle("user-123", "corr-123", {"phase": "keyword_education"})

        instruction = result.structuredContent["assistant_guidance"]["instruction"]
        assert "weekly report" in instruction.lower()
        assert "snapshot" not in instruction.lower()
        assert "allocation" not in instruction.lower()


@pytest.mark.asyncio
async def test_first_weekly_report_instruction_contains_weekly_report_terminology(
    mock_weekly_report_with_keywords,
    mock_past_week_no_snapshot,
):
    """Assert instruction uses 'weekly report' terminology consistently."""
    with patch(
        "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
        new_callable=AsyncMock,
    ) as mock_get:
        mock_get.side_effect = [mock_past_week_no_snapshot, mock_weekly_report_with_keywords]

        result = await handle("user-123", "corr-123", {"phase": "first_weekly_report"})

        guidance = result.structuredContent["assistant_guidance"]
        transition_message = guidance["transition_prompt"]["message"]
        assert "weekly report" in transition_message.lower()
        assert "snapshot" not in transition_message.lower()


@pytest.mark.asyncio
async def test_reflection_setup_instruction_no_motivational_filler():
    """Assert instruction does not contain motivational filler phrases."""
    result = await handle("user-123", "corr-123", {"phase": "reflection_setup"})

    instruction = result.structuredContent["assistant_guidance"]["instruction"]
    instruction_lower = instruction.lower()

    assert "big leverage" not in instruction_lower
    assert "real insight" not in instruction_lower
    assert "game changer" not in instruction_lower


# ============================================================================
# Increment 75: Data Minimization Tests
# ============================================================================


@pytest.mark.asyncio
async def test_onboarding_returns_all_events(mock_priorities_response):
    """first_weekly_report phase returns all events in allEvents (no filtering)."""
    mock_weekly_report = {
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
                },
            ],
            "time_allocation": {
                "total_tracked_hours": 24.5,
                "keywords": {
                    "P1": {"hours": 8.0, "event_count": 5},
                },
                "other_hours": 12.5,
            },
            "all_events": [
                {"title": "P1: Design review", "start": "2026-02-17T10:00:00", "end": "2026-02-17T12:00:00", "matched_keywords": ["P1"]},
                {"title": "P1: Sprint planning", "start": "2026-02-17T14:00:00", "end": "2026-02-17T15:00:00", "matched_keywords": ["P1"]},
                {"title": "Team standup", "start": "2026-02-17T09:00:00", "end": "2026-02-17T09:30:00", "matched_keywords": []},
                {"title": "Client call", "start": "2026-02-17T16:00:00", "end": "2026-02-17T17:00:00", "matched_keywords": []},
            ],
        },
    }

    # Mock past week as already snapshotted so it uses this week's data
    mock_past_week = {
        "success": True,
        "data": {
            "week_start": "2026-02-10",
            "week_end": "2026-02-16",
            "is_current_week": False,
            "snapshot_saved": True,  # Already snapshotted
            "priorities": [],
            "time_allocation": {},
            "all_events": [],
        },
    }

    with patch(
        "mcp_server.priority_guardian.tools.onboarding_calendar_setup.backend_get",
        new_callable=AsyncMock,
    ) as mock_get:
        # First call gets past week (snapshotted), second call gets current week
        mock_get.side_effect = [mock_past_week, mock_weekly_report]

        result = await handle("user-123", "corr-123", {"phase": "first_weekly_report"})

    data = result.structuredContent["data"]
    all_events = data["allEvents"]

    # All events should be included (no filtering during onboarding)
    assert len(all_events) == 4

    # Verify all events are present
    titles = [e["title"] for e in all_events]
    assert "Team standup" in titles
    assert "Client call" in titles
    assert "P1: Design review" in titles
    assert "P1: Sprint planning" in titles

    # Verify priority events have matchedKeywords preserved
    p1_events = [e for e in all_events if e.get("matchedKeywords")]
    assert len(p1_events) == 2
    assert all("P1" in e["matchedKeywords"] for e in p1_events)
