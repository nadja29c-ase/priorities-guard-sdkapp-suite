"""
Unit tests for get_weekly_report MCP handler (Increment 06-S).

Tests the rewritten _build_assistant_guidance() function:
- Current week framing
- Past week framing
- Semantic grouping proposals (conversational only)
- No mention of saving/snapshots/persistence
"""

import pytest

from mcp_server.priority_guardian.tools.get_weekly_report import (
    _build_assistant_guidance,
    _normalize_priority_report,
    _normalize_time_allocation,
    _normalize_event,
)


class TestBuildAssistantGuidance:
    """Tests for _build_assistant_guidance() function."""

    def test_current_week_includes_progress_framing(self):
        """Current week guidance includes 'CURRENT WEEK in progress' framing."""
        data = {
            "is_current_week": True,
            "time_allocation": {"other_hours": 0},
        }

        guidance = _build_assistant_guidance(data, [], [])

        assert "CURRENT WEEK in progress" in guidance
        assert "progress check-in" in guidance.lower()

    def test_past_week_includes_completed_framing(self):
        """Past week guidance includes 'COMPLETED WEEK reflection' framing."""
        data = {
            "is_current_week": False,
            "time_allocation": {"other_hours": 0},
        }

        guidance = _build_assistant_guidance(data, [], [])

        assert "COMPLETED WEEK reflection" in guidance
        assert "look back" in guidance.lower()

    def test_proposes_semantic_categories_when_other_hours_exist(self):
        """Proposes semantic categories when non-priority time exists."""
        data = {
            "is_current_week": False,
            "time_allocation": {"other_hours": 5.5},
        }
        all_events = [
            {"title": "Team lunch", "matched_keywords": []},
            {"title": "Client call", "matched_keywords": []},
            {"title": "Admin tasks", "matched_keywords": []},
        ]

        guidance = _build_assistant_guidance(data, [], all_events)

        assert "5.5 hours of non-priority time" in guidance
        assert "semantic categories" in guidance.lower()
        assert "Team lunch" in guidance

    def test_never_asks_to_save_or_confirm(self):
        """Guidance never prompts user to save or confirm groupings."""
        data = {
            "is_current_week": False,
            "time_allocation": {"other_hours": 10.0},
        }
        all_events = [
            {"title": "Meeting 1", "matched_keywords": []},
            {"title": "Meeting 2", "matched_keywords": []},
        ]

        guidance = _build_assistant_guidance(data, [], all_events)

        guidance_lower = guidance.lower()
        # Should not PROMPT user to save groupings (saying "do NOT ask" is fine)
        assert "would you like to save" not in guidance_lower
        assert "save these categories" not in guidance_lower
        assert "shall i save" not in guidance_lower
        # Should explicitly say NOT to ask
        assert "do not ask them to save" in guidance_lower
        # No mention of snapshots as something to save
        assert "snapshot saved" not in guidance_lower

    def test_explicitly_says_not_to_ask_to_save(self):
        """Guidance explicitly instructs not to ask user to save."""
        data = {
            "is_current_week": False,
            "time_allocation": {"other_hours": 5.0},
        }
        all_events = [
            {"title": "Random meeting", "matched_keywords": []},
        ]

        guidance = _build_assistant_guidance(data, [], all_events)

        assert "Do NOT ask them to save" in guidance

    def test_no_semantic_proposal_when_no_other_hours(self):
        """No semantic grouping proposal when other_hours is 0."""
        data = {
            "is_current_week": False,
            "time_allocation": {"other_hours": 0.0},
        }

        guidance = _build_assistant_guidance(data, [], [])

        assert "semantic categories" not in guidance.lower()
        assert "non-priority time" not in guidance.lower()

    def test_asks_about_other_time_when_no_events_but_hours_exist(self):
        """When other_hours > 0 but no events, asks what time was spent on."""
        data = {
            "is_current_week": False,
            "time_allocation": {"other_hours": 3.0},
        }
        # No non-priority events (all matched keywords)
        all_events = [
            {"title": "P1 Work", "matched_keywords": ["P1"]},
        ]

        guidance = _build_assistant_guidance(data, [], all_events)

        assert "3.0 hours of non-priority time" in guidance
        assert "what this time was" in guidance.lower() or "spent on" in guidance.lower()

    def test_includes_priority_presentation_guidance(self):
        """Always includes guidance for presenting priority data."""
        data = {
            "is_current_week": True,
            "time_allocation": {"other_hours": 0},
        }

        guidance = _build_assistant_guidance(data, [], [])

        assert "ahead/on_track/behind" in guidance
        assert "pacing status" in guidance.lower()

    def test_includes_reflective_closing(self):
        """Always includes reflective closing guidance."""
        data = {
            "is_current_week": False,
            "time_allocation": {"other_hours": 0},
        }

        guidance = _build_assistant_guidance(data, [], [])

        assert "reflective" in guidance.lower()
        assert "coaching" in guidance.lower()


class TestNormalizePriorityReport:
    """Tests for _normalize_priority_report() function."""

    def test_normalizes_flexible_priority_fields(self):
        """Flexible priority fields are normalized to camelCase."""
        priority = {
            "id": "test-id",
            "name": "Test Priority",
            "type": "flexible",
            "calendar_keyword": "P1",
            "actual_hours": 5.5,
            "event_count": 3,
            "target_hours": 10.0,
            "flex_status": "on_track",
            "streak_count": 0,
            "avg_hours_week": None,
            "total_hours_invested": 0.0,
        }

        result = _normalize_priority_report(priority)

        assert result["calendarKeyword"] == "P1"
        assert result["actualHours"] == 5.5
        assert result["eventCount"] == 3
        assert result["targetHours"] == 10.0
        assert result["flexStatus"] == "on_track"
        assert result["streakCount"] == 0
        assert result["previousWeek"] is None  # Always null in simplified

    def test_normalizes_deadline_priority_fields(self):
        """Deadline priority fields are normalized to camelCase."""
        priority = {
            "id": "test-id",
            "name": "Test Deadline",
            "type": "deadline",
            "calendar_keyword": "P2",
            "actual_hours": 8.0,
            "event_count": 5,
            "deadline_date": "2026-03-01",
            "days_remaining": 15,
            "deliverables_completed": 2,
            "deliverables_total": 5,
            "pacing_status": "ahead",
        }

        result = _normalize_priority_report(priority)

        assert result["calendarKeyword"] == "P2"
        assert result["deadlineDate"] == "2026-03-01"
        assert result["daysRemaining"] == 15
        assert result["deliverablesCompleted"] == 2
        assert result["deliverablesTotal"] == 5
        assert result["pacingStatus"] == "ahead"
        assert result["previousWeek"] is None  # Always null in simplified

    def test_previous_week_always_null(self):
        """previousWeek is always null in simplified version."""
        # Even if backend somehow returns previous_week, normalize to null
        priority = {
            "id": "test-id",
            "name": "Test",
            "type": "flexible",
            "calendar_keyword": "P1",
            "previous_week": {"actual_hours": 5.0},  # Should be ignored
        }

        result = _normalize_priority_report(priority)

        assert result["previousWeek"] is None


class TestNormalizeTimeAllocation:
    """Tests for _normalize_time_allocation() function."""

    def test_normalizes_field_names(self):
        """Time allocation fields are normalized to camelCase."""
        allocation = {
            "total_tracked_hours": 25.5,
            "keywords": {
                "P1": {"hours": 10.0, "event_count": 5},
                "P2": {"hours": 8.0, "event_count": 3},
                "P3": {"hours": 2.5, "event_count": 2},
            },
            "other_hours": 5.0,
        }

        result = _normalize_time_allocation(allocation)

        assert result["totalTrackedHours"] == 25.5
        assert result["otherHours"] == 5.0
        assert result["keywords"]["P1"]["hours"] == 10.0
        assert result["keywords"]["P1"]["eventCount"] == 5

    def test_handles_missing_keywords(self):
        """Handles missing keywords gracefully with defaults."""
        allocation = {
            "total_tracked_hours": 0,
            "keywords": {},
            "other_hours": 0,
        }

        result = _normalize_time_allocation(allocation)

        assert result["keywords"]["P1"]["hours"] == 0.0
        assert result["keywords"]["P1"]["eventCount"] == 0


class TestNormalizeEvent:
    """Tests for _normalize_event() function."""

    def test_normalizes_event_fields(self):
        """Event fields are normalized to camelCase."""
        event = {
            "title": "Team Meeting",
            "description": "Weekly sync",
            "start": "2026-02-10T10:00:00Z",
            "end": "2026-02-10T11:00:00Z",
            "matched_keywords": ["P1"],
        }

        result = _normalize_event(event)

        assert result["title"] == "Team Meeting"
        assert result["description"] == "Weekly sync"
        assert result["matchedKeywords"] == ["P1"]

    def test_handles_missing_fields(self):
        """Handles missing fields with defaults."""
        event = {}

        result = _normalize_event(event)

        assert result["title"] == ""
        assert result["description"] == ""
        assert result["matchedKeywords"] == []
