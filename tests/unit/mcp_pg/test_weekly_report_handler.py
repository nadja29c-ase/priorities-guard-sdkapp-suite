"""
Unit tests for get_weekly_report MCP handler (Increment 07).

Tests:
- Slice construction (priority + semantic)
- Validation (over-allocation, remainder handling)
- Two assistant_guidance modes (with/without semantic_groupings)
- Normalization functions
"""

import pytest

from mcp_server.priority_guardian.tools.get_weekly_report import (
    _build_assistant_guidance,
    _build_pie_slices,
    _normalize_priority_report,
    _normalize_time_allocation,
    _normalize_event,
    WIDGET_URI,
)


class TestBuildPieSlices:
    """Tests for _build_pie_slices() function."""

    def test_priority_slices_use_keyword_name_label(self):
        """Priority slices use '{keyword}: {name}' label format."""
        priorities = [
            {"name": "Build PG", "calendar_keyword": "P1"},
            {"name": "Client Work", "calendar_keyword": "P2"},
        ]
        time_allocation = {
            "keywords": {
                "P1": {"hours": 10.0, "event_count": 5},
                "P2": {"hours": 5.0, "event_count": 3},
            },
            "other_hours": 2.0,
        }

        slices, error = _build_pie_slices(priorities, time_allocation, None)

        assert error is None
        priority_slices = [s for s in slices if s["type"] == "priority"]
        assert len(priority_slices) == 2
        assert priority_slices[0]["label"] == "P1: Build PG"
        assert priority_slices[1]["label"] == "P2: Client Work"

    def test_zero_hour_priorities_excluded_from_slices(self):
        """Priorities with zero hours are excluded from slices."""
        priorities = [
            {"name": "Build PG", "calendar_keyword": "P1"},
            {"name": "Zero Hours", "calendar_keyword": "P3"},
        ]
        time_allocation = {
            "keywords": {
                "P1": {"hours": 10.0, "event_count": 5},
                "P3": {"hours": 0.0, "event_count": 0},  # Zero hours
            },
            "other_hours": 2.0,
        }

        slices, error = _build_pie_slices(priorities, time_allocation, None)

        assert error is None
        priority_slices = [s for s in slices if s["type"] == "priority"]
        assert len(priority_slices) == 1
        assert priority_slices[0]["keyword"] == "P1"

    def test_without_semantic_groupings_shows_other_slice(self):
        """Without semantic_groupings, shows single 'Other' slice."""
        priorities = [{"name": "Build PG", "calendar_keyword": "P1"}]
        time_allocation = {
            "keywords": {"P1": {"hours": 10.0, "event_count": 5}},
            "other_hours": 5.0,
        }

        slices, error = _build_pie_slices(priorities, time_allocation, None)

        assert error is None
        semantic_slices = [s for s in slices if s["type"] == "semantic"]
        assert len(semantic_slices) == 1
        assert semantic_slices[0]["label"] == "Other"
        assert semantic_slices[0]["hours"] == 5.0

    def test_zero_other_hours_no_other_slice(self):
        """Zero other_hours means no 'Other' slice."""
        priorities = [{"name": "Build PG", "calendar_keyword": "P1"}]
        time_allocation = {
            "keywords": {"P1": {"hours": 10.0, "event_count": 5}},
            "other_hours": 0.0,
        }

        slices, error = _build_pie_slices(priorities, time_allocation, None)

        assert error is None
        semantic_slices = [s for s in slices if s["type"] == "semantic"]
        assert len(semantic_slices) == 0

    def test_with_semantic_groupings_shows_category_slices(self):
        """With semantic_groupings, shows category slices instead of 'Other'."""
        priorities = [{"name": "Build PG", "calendar_keyword": "P1"}]
        time_allocation = {
            "keywords": {"P1": {"hours": 10.0, "event_count": 5}},
            "other_hours": 8.0,
        }
        semantic_groupings = [
            {"category": "Client calls", "hours": 5.0, "event_count": 3},
            {"category": "Admin", "hours": 3.0, "event_count": 2},
        ]

        slices, error = _build_pie_slices(priorities, time_allocation, semantic_groupings)

        assert error is None
        semantic_slices = [s for s in slices if s["type"] == "semantic"]
        assert len(semantic_slices) == 2
        assert semantic_slices[0]["label"] == "Client calls"
        assert semantic_slices[0]["hours"] == 5.0
        assert semantic_slices[1]["label"] == "Admin"
        assert semantic_slices[1]["hours"] == 3.0
        # No "Other" slice when semantic_groupings provided
        assert not any(s["label"] == "Other" for s in slices)

    def test_empty_semantic_groupings_treated_as_not_provided(self):
        """Empty semantic_groupings array treated same as not provided."""
        priorities = [{"name": "Build PG", "calendar_keyword": "P1"}]
        time_allocation = {
            "keywords": {"P1": {"hours": 10.0, "event_count": 5}},
            "other_hours": 5.0,
        }

        slices, error = _build_pie_slices(priorities, time_allocation, [])

        assert error is None
        semantic_slices = [s for s in slices if s["type"] == "semantic"]
        assert len(semantic_slices) == 1
        assert semantic_slices[0]["label"] == "Other"


class TestSliceValidation:
    """Tests for semantic_groupings validation in _build_pie_slices()."""

    def test_over_allocation_returns_error(self):
        """Grouped hours > other_hours + 0.5 returns validation error."""
        priorities = []
        time_allocation = {
            "keywords": {},
            "other_hours": 10.0,
        }
        # Total: 12.0h, exceeds 10.0 + 0.5 = 10.5h
        semantic_groupings = [
            {"category": "Client calls", "hours": 8.0, "event_count": 5},
            {"category": "Admin", "hours": 4.0, "event_count": 3},
        ]

        slices, error = _build_pie_slices(priorities, time_allocation, semantic_groupings)

        assert error is not None
        assert "exceed" in error.lower()
        assert "12.0" in error  # Grouped total
        assert "10.0" in error  # Other hours
        assert slices == []

    def test_within_tolerance_accepted(self):
        """Grouped hours <= other_hours + 0.5 is accepted."""
        priorities = []
        time_allocation = {
            "keywords": {},
            "other_hours": 10.0,
        }
        # Total: 10.4h, within 10.0 + 0.5 = 10.5h tolerance
        semantic_groupings = [
            {"category": "Client calls", "hours": 6.0, "event_count": 5},
            {"category": "Admin", "hours": 4.4, "event_count": 3},
        ]

        slices, error = _build_pie_slices(priorities, time_allocation, semantic_groupings)

        assert error is None
        assert len(slices) == 2

    def test_no_normalization_of_user_hours(self):
        """User-confirmed hours are never modified (no normalization)."""
        priorities = []
        time_allocation = {
            "keywords": {},
            "other_hours": 10.0,
        }
        semantic_groupings = [
            {"category": "Client calls", "hours": 5.5, "event_count": 5},
            {"category": "Admin", "hours": 3.3, "event_count": 3},
        ]

        slices, error = _build_pie_slices(priorities, time_allocation, semantic_groupings)

        assert error is None
        # Hours match exactly what user provided
        assert slices[0]["hours"] == 5.5
        assert slices[1]["hours"] == 3.3


class TestRemainderHandling:
    """Tests for 'Uncategorized' remainder slice."""

    def test_remainder_above_threshold_adds_uncategorized(self):
        """Remainder >= 0.25h adds 'Uncategorized' slice."""
        priorities = []
        time_allocation = {
            "keywords": {},
            "other_hours": 10.0,
        }
        # Total: 9.5h, remainder: 0.5h >= 0.25h
        semantic_groupings = [
            {"category": "Client calls", "hours": 5.0, "event_count": 3},
            {"category": "Admin", "hours": 4.5, "event_count": 2},
        ]

        slices, error = _build_pie_slices(priorities, time_allocation, semantic_groupings)

        assert error is None
        assert len(slices) == 3
        uncategorized = [s for s in slices if s["label"] == "Uncategorized"]
        assert len(uncategorized) == 1
        assert uncategorized[0]["hours"] == 0.5
        assert uncategorized[0]["type"] == "semantic"

    def test_remainder_below_threshold_no_uncategorized(self):
        """Remainder < 0.25h is skipped (no 'Uncategorized' slice)."""
        priorities = []
        time_allocation = {
            "keywords": {},
            "other_hours": 10.0,
        }
        # Total: 9.8h, remainder: 0.2h < 0.25h
        semantic_groupings = [
            {"category": "Client calls", "hours": 5.0, "event_count": 3},
            {"category": "Admin", "hours": 4.8, "event_count": 2},
        ]

        slices, error = _build_pie_slices(priorities, time_allocation, semantic_groupings)

        assert error is None
        assert len(slices) == 2
        assert not any(s["label"] == "Uncategorized" for s in slices)

    def test_exact_match_no_uncategorized(self):
        """Exact match (remainder = 0) has no 'Uncategorized' slice."""
        priorities = []
        time_allocation = {
            "keywords": {},
            "other_hours": 10.0,
        }
        semantic_groupings = [
            {"category": "Client calls", "hours": 6.0, "event_count": 3},
            {"category": "Admin", "hours": 4.0, "event_count": 2},
        ]

        slices, error = _build_pie_slices(priorities, time_allocation, semantic_groupings)

        assert error is None
        assert len(slices) == 2
        assert not any(s["label"] == "Uncategorized" for s in slices)

    def test_slight_overshoot_within_tolerance_no_negative_remainder(self):
        """When sum slightly exceeds other_hours (within 0.5h tolerance), no negative Uncategorized."""
        priorities = []
        time_allocation = {
            "keywords": {},
            "other_hours": 12.0,
        }
        # Sum = 12.4h, exceeds 12.0 by 0.4h (within 0.5h tolerance)
        semantic_groupings = [
            {"category": "Client calls", "hours": 8.0, "event_count": 5},
            {"category": "Admin", "hours": 4.4, "event_count": 3},
        ]

        slices, error = _build_pie_slices(priorities, time_allocation, semantic_groupings)

        assert error is None
        assert len(slices) == 2
        # No Uncategorized slice with negative hours
        assert not any(s["label"] == "Uncategorized" for s in slices)
        # All slice hours are positive
        assert all(s["hours"] >= 0 for s in slices)


class TestBuildAssistantGuidanceMode1:
    """Tests for _build_assistant_guidance() without semantic_groupings (first call)."""

    def test_current_week_includes_progress_framing(self):
        """Current week guidance includes 'CURRENT WEEK in progress' framing."""
        data = {
            "is_current_week": True,
            "time_allocation": {"other_hours": 0},
        }

        guidance = _build_assistant_guidance(data, [], [], has_semantic_groupings=False)

        assert "CURRENT WEEK in progress" in guidance
        assert "progress check-in" in guidance.lower()

    def test_past_week_includes_completed_framing(self):
        """Past week guidance includes 'COMPLETED WEEK reflection' framing."""
        data = {
            "is_current_week": False,
            "time_allocation": {"other_hours": 0},
        }

        guidance = _build_assistant_guidance(data, [], [], has_semantic_groupings=False)

        assert "COMPLETED WEEK reflection" in guidance
        assert "look back" in guidance.lower()

    def test_proposes_semantic_groupings(self):
        """Mode 1 guidance proposes semantic groupings."""
        data = {
            "is_current_week": False,
            "time_allocation": {"other_hours": 5.5},
        }
        all_events = [
            {"title": "Team lunch", "matched_keywords": []},
            {"title": "Client call", "matched_keywords": []},
        ]

        guidance = _build_assistant_guidance(data, [], all_events, has_semantic_groupings=False)

        assert "5.5 hours of non-priority time" in guidance
        assert "semantic" in guidance.lower() or "categories" in guidance.lower()
        assert "call get_weekly_report again with the semantic_groupings" in guidance

    def test_instructs_to_narrate_all_priorities_including_zero(self):
        """Mode 1 guidance instructs to narrate ALL priorities including zero-hour ones."""
        data = {
            "is_current_week": False,
            "time_allocation": {"other_hours": 0},
        }

        guidance = _build_assistant_guidance(data, [], [], has_semantic_groupings=False)

        assert "ALL active priorities" in guidance or "zero hours" in guidance.lower()

    def test_does_not_contain_raw_event_titles_in_guidance(self):
        """Mode 1 guidance references allEvents abstractly, doesn't embed raw titles."""
        data = {
            "is_current_week": False,
            "time_allocation": {"other_hours": 5.0},
        }
        all_events = [
            {"title": "Specific Event Title ABC123", "matched_keywords": []},
        ]

        guidance = _build_assistant_guidance(data, [], all_events, has_semantic_groupings=False)

        # Should reference events abstractly
        assert "allEvents" in guidance or "event titles" in guidance.lower()
        # Should NOT embed the specific title directly
        assert "Specific Event Title ABC123" not in guidance

    def test_no_save_or_snapshot_language(self):
        """Mode 1 guidance doesn't prompt to save snapshots (but may instruct NOT to mention them)."""
        data = {
            "is_current_week": False,
            "time_allocation": {"other_hours": 5.0},
        }
        all_events = [{"title": "Meeting", "matched_keywords": []}]

        guidance = _build_assistant_guidance(data, [], all_events, has_semantic_groupings=False)

        guidance_lower = guidance.lower()
        # Should not prompt to SAVE snapshots (instructing NOT to mention is fine)
        assert "save snapshot" not in guidance_lower
        assert "snapshot saved" not in guidance_lower
        # Should instruct NOT to mention
        assert "do not mention" in guidance_lower or "not mention" in guidance_lower


class TestBuildAssistantGuidanceMode2:
    """Tests for _build_assistant_guidance() with semantic_groupings (second call)."""

    def test_says_not_to_list_categories(self):
        """Mode 2 guidance says NOT to repeat/list categories."""
        data = {
            "is_current_week": False,
            "time_allocation": {"other_hours": 5.0},
        }

        guidance = _build_assistant_guidance(data, [], [], has_semantic_groupings=True)

        assert "NOT repeat" in guidance or "NOT list" in guidance
        assert "chart displays them" in guidance.lower()

    def test_makes_brief_observation(self):
        """Mode 2 guidance instructs brief coaching observation."""
        data = {
            "is_current_week": False,
            "time_allocation": {"other_hours": 5.0},
        }

        guidance = _build_assistant_guidance(data, [], [], has_semantic_groupings=True)

        assert "brief" in guidance.lower()
        assert "observation" in guidance.lower() or "coaching" in guidance.lower()

    def test_asks_what_stands_out(self):
        """Mode 2 guidance asks what stands out."""
        data = {
            "is_current_week": False,
            "time_allocation": {"other_hours": 5.0},
        }

        guidance = _build_assistant_guidance(data, [], [], has_semantic_groupings=True)

        assert "stands out" in guidance.lower()

    def test_keeps_it_short(self):
        """Mode 2 guidance says to keep it short."""
        data = {
            "is_current_week": False,
            "time_allocation": {"other_hours": 5.0},
        }

        guidance = _build_assistant_guidance(data, [], [], has_semantic_groupings=True)

        assert "short" in guidance.lower() or "heavy lifting" in guidance.lower()

    def test_no_save_or_snapshot_language(self):
        """Mode 2 guidance doesn't mention save or snapshot."""
        data = {
            "is_current_week": False,
            "time_allocation": {"other_hours": 5.0},
        }

        guidance = _build_assistant_guidance(data, [], [], has_semantic_groupings=True)

        guidance_lower = guidance.lower()
        assert "snapshot" not in guidance_lower
        assert "save" not in guidance_lower
        assert "persistence" not in guidance_lower


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
        assert result["previousWeek"] is None

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
        assert result["previousWeek"] is None

    def test_previous_week_always_null(self):
        """previousWeek is always null."""
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


class TestWidgetUri:
    """Tests for WIDGET_URI constant."""

    def test_widget_uri_is_pg_dashboard(self):
        """WIDGET_URI points to pg-dashboard widget."""
        assert WIDGET_URI == "ui://widget/pg-dashboard.html"
