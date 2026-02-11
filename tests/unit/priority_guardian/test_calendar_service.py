"""
Unit tests for calendar_service module.

Tests keyword matching, duration computation, event filtering,
bar_segments allocation, and week boundary computation.
"""

import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from backend.apps.priority_guardian.services.calendar_service import (
    match_keywords,
    is_all_day_event,
    is_declined_event,
    is_cancelled_event,
    compute_event_duration_hours,
    compute_week_boundaries,
    compute_allocation_from_events,
    compute_time_allocation,
    _empty_allocation,
)


# =============================================================================
# Keyword Matching Tests
# =============================================================================

class TestKeywordMatching:
    """Tests for match_keywords() function."""

    def test_matches_p1_at_start(self):
        """'P1 Marketing meeting' matches P1."""
        assert match_keywords("P1 Marketing meeting") == ["P1"]

    def test_matches_p2_in_middle(self):
        """'Weekly P2 review' matches P2."""
        assert match_keywords("Weekly P2 review") == ["P2"]

    def test_matches_p3(self):
        """'P3 exploration' matches P3."""
        assert match_keywords("P3 exploration") == ["P3"]

    def test_case_insensitive_lowercase(self):
        """'p1 standup' matches P1 (case-insensitive)."""
        result = match_keywords("p1 standup")
        assert "P1" in result

    def test_case_insensitive_mixed(self):
        """'P1 and p2 Sync' matches both."""
        result = match_keywords("P1 and p2 Sync")
        assert "P1" in result
        assert "P2" in result

    def test_brackets_dont_break_match(self):
        """'[P1] design sync' matches P1."""
        assert match_keywords("[P1] design sync") == ["P1"]

    def test_colon_after_keyword(self):
        """'P1: copywriting' matches P1."""
        assert match_keywords("P1: copywriting") == ["P1"]

    def test_no_match_returns_empty(self):
        """'Sprint planning' matches nothing."""
        assert match_keywords("Sprint planning") == []

    def test_multi_keyword_match(self):
        """'P1 and P2 sync' matches BOTH P1 and P2."""
        result = match_keywords("P1 and P2 sync")
        assert "P1" in result
        assert "P2" in result
        assert len(result) == 2

    def test_empty_title_no_match(self):
        """Empty title matches nothing."""
        assert match_keywords("") == []

    def test_none_title_no_match(self):
        """None title matches nothing."""
        assert match_keywords(None) == []

    # Word boundary rejection tests
    def test_rejects_ap1(self):
        """'AP1 budget' does NOT match P1."""
        assert match_keywords("AP1 budget") == []

    def test_rejects_p10(self):
        """'P10 rollout' does NOT match P1."""
        assert match_keywords("P10 rollout") == []

    def test_rejects_step_p1_x(self):
        """'StepP1X' does NOT match P1."""
        assert match_keywords("StepP1X") == []

    def test_rejects_p1_in_word(self):
        """'CompanyP1Name' does NOT match P1."""
        assert match_keywords("CompanyP1Name") == []

    # Word boundary acceptance tests
    def test_accepts_chapter_p1(self):
        """'Chapter P1' DOES match P1."""
        assert match_keywords("Chapter P1") == ["P1"]

    def test_accepts_p1_dash_at_end(self):
        """'P1-' at word boundary DOES match (dash is boundary)."""
        # Note: \b treats dash as word boundary
        result = match_keywords("P1- next steps")
        assert "P1" in result

    def test_all_three_keywords(self):
        """Event with P1, P2, P3 matches all three."""
        result = match_keywords("P1 P2 P3 big meeting")
        assert set(result) == {"P1", "P2", "P3"}


# =============================================================================
# Duration Computation Tests
# =============================================================================

class TestDurationComputation:
    """Tests for compute_event_duration_hours()."""

    def test_two_hour_event(self):
        """2-hour event (10:00–12:00) → 2.0 hours."""
        event = {
            "start": {"dateTime": "2026-02-11T10:00:00+01:00"},
            "end": {"dateTime": "2026-02-11T12:00:00+01:00"},
        }
        assert compute_event_duration_hours(event) == 2.0

    def test_ninety_minute_event(self):
        """90-minute event → 1.5 hours."""
        event = {
            "start": {"dateTime": "2026-02-11T14:00:00+01:00"},
            "end": {"dateTime": "2026-02-11T15:30:00+01:00"},
        }
        assert compute_event_duration_hours(event) == 1.5

    def test_cross_midnight_event(self):
        """Cross-midnight event (23:00–01:00 next day) → 2.0 hours."""
        event = {
            "start": {"dateTime": "2026-02-11T23:00:00+01:00"},
            "end": {"dateTime": "2026-02-12T01:00:00+01:00"},
        }
        assert compute_event_duration_hours(event) == 2.0

    def test_zero_duration_event(self):
        """Zero-duration event (start == end) → 0.0 hours."""
        event = {
            "start": {"dateTime": "2026-02-11T10:00:00+01:00"},
            "end": {"dateTime": "2026-02-11T10:00:00+01:00"},
        }
        assert compute_event_duration_hours(event) == 0.0

    def test_missing_start_datetime(self):
        """Missing start dateTime → 0.0 hours."""
        event = {
            "start": {},
            "end": {"dateTime": "2026-02-11T12:00:00+01:00"},
        }
        assert compute_event_duration_hours(event) == 0.0

    def test_missing_end_datetime(self):
        """Missing end dateTime → 0.0 hours."""
        event = {
            "start": {"dateTime": "2026-02-11T10:00:00+01:00"},
            "end": {},
        }
        assert compute_event_duration_hours(event) == 0.0

    def test_rounds_to_two_decimals(self):
        """Duration rounded to 2 decimal places."""
        # 1 hour 20 minutes = 1.333... hours → 1.33
        event = {
            "start": {"dateTime": "2026-02-11T10:00:00+01:00"},
            "end": {"dateTime": "2026-02-11T11:20:00+01:00"},
        }
        assert compute_event_duration_hours(event) == 1.33


# =============================================================================
# Event Filtering Tests
# =============================================================================

class TestAllDayEventDetection:
    """Tests for is_all_day_event()."""

    def test_all_day_event_detected(self):
        """Event with start.date (no dateTime) is all-day."""
        event = {
            "start": {"date": "2026-02-11"},
            "end": {"date": "2026-02-12"},
        }
        assert is_all_day_event(event) is True

    def test_timed_event_not_all_day(self):
        """Event with start.dateTime is NOT all-day."""
        event = {
            "start": {"dateTime": "2026-02-11T10:00:00+01:00"},
            "end": {"dateTime": "2026-02-11T11:00:00+01:00"},
        }
        assert is_all_day_event(event) is False

    def test_event_with_both_uses_datetime(self):
        """Event with both date and dateTime uses dateTime (not all-day)."""
        event = {
            "start": {"date": "2026-02-11", "dateTime": "2026-02-11T10:00:00+01:00"},
            "end": {"dateTime": "2026-02-11T11:00:00+01:00"},
        }
        assert is_all_day_event(event) is False


class TestDeclinedEventDetection:
    """Tests for is_declined_event()."""

    def test_declined_event_detected(self):
        """Event with self=true and responseStatus=declined is declined."""
        event = {
            "attendees": [
                {"email": "other@example.com", "responseStatus": "accepted"},
                {"email": "me@example.com", "self": True, "responseStatus": "declined"},
            ]
        }
        assert is_declined_event(event) is True

    def test_accepted_event_not_declined(self):
        """Event with self=true and responseStatus=accepted is NOT declined."""
        event = {
            "attendees": [
                {"email": "me@example.com", "self": True, "responseStatus": "accepted"},
            ]
        }
        assert is_declined_event(event) is False

    def test_tentative_event_not_declined(self):
        """Event with responseStatus=tentative is NOT declined."""
        event = {
            "attendees": [
                {"email": "me@example.com", "self": True, "responseStatus": "tentative"},
            ]
        }
        assert is_declined_event(event) is False

    def test_no_attendees_not_declined(self):
        """Event with no attendees array is NOT declined (solo event)."""
        event = {"summary": "Solo work"}
        assert is_declined_event(event) is False

    def test_empty_attendees_not_declined(self):
        """Event with empty attendees array is NOT declined."""
        event = {"attendees": []}
        assert is_declined_event(event) is False


class TestCancelledEventDetection:
    """Tests for is_cancelled_event()."""

    def test_cancelled_event_detected(self):
        """Event with status=cancelled is cancelled."""
        event = {"status": "cancelled"}
        assert is_cancelled_event(event) is True

    def test_confirmed_event_not_cancelled(self):
        """Event with status=confirmed is NOT cancelled."""
        event = {"status": "confirmed"}
        assert is_cancelled_event(event) is False

    def test_no_status_not_cancelled(self):
        """Event with no status is NOT cancelled."""
        event = {"summary": "Meeting"}
        assert is_cancelled_event(event) is False


# =============================================================================
# Week Boundary Tests
# =============================================================================

class TestWeekBoundaries:
    """Tests for compute_week_boundaries()."""

    def test_europe_berlin_timezone(self):
        """Week boundaries for Europe/Berlin timezone."""
        with patch("backend.apps.priority_guardian.services.calendar_service.datetime") as mock_dt:
            # Wednesday Feb 11, 2026, 14:30 in Berlin
            mock_now = datetime(2026, 2, 11, 14, 30, tzinfo=ZoneInfo("Europe/Berlin"))
            mock_dt.now.return_value = mock_now

            start, end = compute_week_boundaries("Europe/Berlin")

            # Should be Monday Feb 9 00:00 to Monday Feb 16 00:00
            assert start.weekday() == 0  # Monday
            assert start.hour == 0
            assert start.minute == 0
            assert end.weekday() == 0  # Monday
            assert (end - start).days == 7

    def test_utc_fallback_for_invalid_timezone(self):
        """Invalid timezone falls back to UTC."""
        start, end = compute_week_boundaries("Invalid/Timezone")

        # Should still return valid week boundaries in UTC
        assert start.tzinfo is not None
        assert end.tzinfo is not None
        assert (end - start).days == 7

    def test_week_is_seven_days(self):
        """Week boundary is exactly 7 days."""
        start, end = compute_week_boundaries("UTC")
        assert (end - start).days == 7


# =============================================================================
# Allocation Computation Tests
# =============================================================================

class TestAllocationComputation:
    """Tests for compute_allocation_from_events()."""

    def test_single_p1_event(self):
        """Single P1 event counted correctly."""
        events = [
            {
                "id": "event-1",
                "summary": "P1 work session",
                "start": {"dateTime": "2026-02-11T10:00:00+01:00"},
                "end": {"dateTime": "2026-02-11T12:00:00+01:00"},
            }
        ]

        result = compute_allocation_from_events(events)

        assert result["keywords"]["P1"]["hours"] == 2.0
        assert result["keywords"]["P1"]["event_count"] == 1
        assert result["keywords"]["P2"]["hours"] == 0.0
        assert result["keywords"]["P3"]["hours"] == 0.0
        assert result["other_hours"] == 0.0
        assert result["total_tracked_hours"] == 2.0

    def test_multiple_events_aggregation(self):
        """Multiple P1 events aggregated correctly."""
        events = [
            {
                "id": "event-1",
                "summary": "P1 morning",
                "start": {"dateTime": "2026-02-11T09:00:00+01:00"},
                "end": {"dateTime": "2026-02-11T11:00:00+01:00"},
            },
            {
                "id": "event-2",
                "summary": "P1 afternoon",
                "start": {"dateTime": "2026-02-11T14:00:00+01:00"},
                "end": {"dateTime": "2026-02-11T17:00:00+01:00"},
            },
        ]

        result = compute_allocation_from_events(events)

        assert result["keywords"]["P1"]["hours"] == 5.0  # 2 + 3
        assert result["keywords"]["P1"]["event_count"] == 2
        assert result["total_tracked_hours"] == 5.0

    def test_other_hours_for_non_keyword_events(self):
        """Non-keyword events counted as 'other'."""
        events = [
            {
                "id": "event-1",
                "summary": "Team lunch",
                "start": {"dateTime": "2026-02-11T12:00:00+01:00"},
                "end": {"dateTime": "2026-02-11T13:00:00+01:00"},
            }
        ]

        result = compute_allocation_from_events(events)

        assert result["keywords"]["P1"]["hours"] == 0.0
        assert result["other_hours"] == 1.0
        assert result["total_tracked_hours"] == 1.0

    def test_multi_keyword_event_counts_for_each(self):
        """Event 'P1 P2 sync' counts for BOTH keywords."""
        events = [
            {
                "id": "event-1",
                "summary": "P1 P2 sync",
                "start": {"dateTime": "2026-02-11T10:00:00+01:00"},
                "end": {"dateTime": "2026-02-11T12:00:00+01:00"},
            }
        ]

        result = compute_allocation_from_events(events)

        # Duration counted for EACH keyword
        assert result["keywords"]["P1"]["hours"] == 2.0
        assert result["keywords"]["P2"]["hours"] == 2.0
        # But totalTrackedHours is deduplicated
        assert result["total_tracked_hours"] == 2.0

    def test_bar_segments_exclusive_allocation(self):
        """bar_segments assigns multi-match to highest priority (P1 > P2 > P3)."""
        events = [
            {
                "id": "event-1",
                "summary": "P1 P2 sync",  # Multi-match: P1 wins
                "start": {"dateTime": "2026-02-11T10:00:00+01:00"},
                "end": {"dateTime": "2026-02-11T12:00:00+01:00"},
            }
        ]

        result = compute_allocation_from_events(events)

        # P1 gets the bar segment (highest priority)
        assert result["bar_segments"]["P1"] == 2.0
        assert result["bar_segments"]["P2"] == 0.0
        # bar_segments sum equals total_tracked_hours
        total_segments = sum(result["bar_segments"].values())
        assert total_segments == result["total_tracked_hours"]

    def test_complex_multi_match_scenario(self):
        """Complex scenario: P1-only, P1+P2, P2-only, other events."""
        events = [
            {
                "id": "event-1",
                "summary": "P1 work",
                "start": {"dateTime": "2026-02-11T09:00:00+01:00"},
                "end": {"dateTime": "2026-02-11T12:00:00+01:00"},
            },  # 3h P1
            {
                "id": "event-2",
                "summary": "P1 P2 sync",
                "start": {"dateTime": "2026-02-11T13:00:00+01:00"},
                "end": {"dateTime": "2026-02-11T15:00:00+01:00"},
            },  # 2h P1+P2
            {
                "id": "event-3",
                "summary": "P2 review",
                "start": {"dateTime": "2026-02-11T15:00:00+01:00"},
                "end": {"dateTime": "2026-02-11T16:00:00+01:00"},
            },  # 1h P2
            {
                "id": "event-4",
                "summary": "Lunch",
                "start": {"dateTime": "2026-02-11T12:00:00+01:00"},
                "end": {"dateTime": "2026-02-11T13:00:00+01:00"},
            },  # 1h other
        ]

        result = compute_allocation_from_events(events)

        # Keywords (overlapping)
        assert result["keywords"]["P1"]["hours"] == 5.0  # 3 + 2
        assert result["keywords"]["P2"]["hours"] == 3.0  # 2 + 1
        assert result["keywords"]["P3"]["hours"] == 0.0
        assert result["other_hours"] == 1.0

        # Total (deduplicated)
        assert result["total_tracked_hours"] == 7.0  # 3 + 2 + 1 + 1

        # bar_segments (exclusive)
        assert result["bar_segments"]["P1"] == 5.0  # 3h + 2h (P1+P2 goes to P1)
        assert result["bar_segments"]["P2"] == 1.0  # Only P2-exclusive
        assert result["bar_segments"]["other"] == 1.0
        assert sum(result["bar_segments"].values()) == 7.0

    def test_excludes_all_day_events(self):
        """All-day events excluded from all calculations."""
        events = [
            {
                "id": "event-1",
                "summary": "P1 all day",
                "start": {"date": "2026-02-11"},
                "end": {"date": "2026-02-12"},
            }
        ]

        result = compute_allocation_from_events(events)

        assert result["keywords"]["P1"]["hours"] == 0.0
        assert result["total_tracked_hours"] == 0.0

    def test_excludes_declined_events(self):
        """Declined events excluded from all calculations."""
        events = [
            {
                "id": "event-1",
                "summary": "P1 meeting",
                "start": {"dateTime": "2026-02-11T10:00:00+01:00"},
                "end": {"dateTime": "2026-02-11T12:00:00+01:00"},
                "attendees": [
                    {"email": "me@example.com", "self": True, "responseStatus": "declined"}
                ],
            }
        ]

        result = compute_allocation_from_events(events)

        assert result["keywords"]["P1"]["hours"] == 0.0
        assert result["total_tracked_hours"] == 0.0

    def test_excludes_cancelled_events(self):
        """Cancelled events excluded from all calculations."""
        events = [
            {
                "id": "event-1",
                "summary": "P1 meeting",
                "start": {"dateTime": "2026-02-11T10:00:00+01:00"},
                "end": {"dateTime": "2026-02-11T12:00:00+01:00"},
                "status": "cancelled",
            }
        ]

        result = compute_allocation_from_events(events)

        assert result["keywords"]["P1"]["hours"] == 0.0
        assert result["total_tracked_hours"] == 0.0

    def test_excludes_zero_duration_events(self):
        """Zero-duration events excluded from calculations."""
        events = [
            {
                "id": "event-1",
                "summary": "P1 marker",
                "start": {"dateTime": "2026-02-11T10:00:00+01:00"},
                "end": {"dateTime": "2026-02-11T10:00:00+01:00"},
            }
        ]

        result = compute_allocation_from_events(events)

        assert result["keywords"]["P1"]["hours"] == 0.0
        assert result["total_tracked_hours"] == 0.0

    def test_empty_events_returns_zeros(self):
        """No events returns all zeros."""
        result = compute_allocation_from_events([])

        assert result["keywords"]["P1"]["hours"] == 0.0
        assert result["keywords"]["P2"]["hours"] == 0.0
        assert result["keywords"]["P3"]["hours"] == 0.0
        assert result["other_hours"] == 0.0
        assert result["total_tracked_hours"] == 0.0
        assert result["total_events_scanned"] == 0


# =============================================================================
# Empty Allocation Helper Test
# =============================================================================

class TestEmptyAllocation:
    """Tests for _empty_allocation() helper."""

    def test_returns_all_zeros(self):
        """Empty allocation returns all zeros."""
        result = _empty_allocation()

        assert result["keywords"]["P1"]["hours"] == 0.0
        assert result["keywords"]["P2"]["hours"] == 0.0
        assert result["keywords"]["P3"]["hours"] == 0.0
        assert result["other_hours"] == 0.0
        assert result["total_tracked_hours"] == 0.0
        assert result["total_events_scanned"] == 0
        assert result["bar_segments"]["P1"] == 0.0
        assert result["bar_segments"]["P2"] == 0.0
        assert result["bar_segments"]["P3"] == 0.0
        assert result["bar_segments"]["other"] == 0.0
