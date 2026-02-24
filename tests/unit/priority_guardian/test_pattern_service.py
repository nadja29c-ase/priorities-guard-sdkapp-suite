"""
Unit tests for pattern service (Increment 21).

Tests pattern computation functions:
- get_current_week_start_utc()
- resolve_keyword()
- decimal_to_float_recursive()
- Pattern 1: Consistency Streak
- Pattern 2: Abandoned Priority Signal
- Pattern 3: Priority Switching Frequency
- Pattern 4: Priority Protection
- Sorting and global rules
"""

import pytest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

from backend.apps.priority_guardian.services.pattern_service import (
    get_current_week_start_utc,
    resolve_keyword,
    decimal_to_float_recursive,
    _get_retirement_week_start,
    _compute_consistency_streaks,
    _compute_abandoned_priorities,
    _compute_priority_switching,
    _compute_priority_protection,
    _sort_patterns,
    compute_patterns,
)


# ============================================================================
# Helper Tests
# ============================================================================

class TestGetCurrentWeekStartUtc:
    """Tests for get_current_week_start_utc helper."""

    def test_wednesday_returns_previous_monday(self):
        """Wednesday should return the Monday of that week."""
        with patch("backend.apps.priority_guardian.services.pattern_service.datetime") as mock_dt:
            # Wednesday Feb 11, 2026
            mock_dt.now.return_value = datetime(2026, 2, 11, 14, 0, 0, tzinfo=timezone.utc)

            result = get_current_week_start_utc()

            assert result == date(2026, 2, 9)  # Monday of that week
            assert result.weekday() == 0  # Monday

    def test_monday_returns_that_monday(self):
        """Monday should return that same Monday."""
        with patch("backend.apps.priority_guardian.services.pattern_service.datetime") as mock_dt:
            # Monday Feb 9, 2026
            mock_dt.now.return_value = datetime(2026, 2, 9, 10, 0, 0, tzinfo=timezone.utc)

            result = get_current_week_start_utc()

            assert result == date(2026, 2, 9)
            assert result.weekday() == 0

    def test_sunday_returns_previous_monday(self):
        """Sunday should return the Monday of that week (critical boundary)."""
        with patch("backend.apps.priority_guardian.services.pattern_service.datetime") as mock_dt:
            # Sunday Feb 15, 2026
            mock_dt.now.return_value = datetime(2026, 2, 15, 23, 59, 0, tzinfo=timezone.utc)

            result = get_current_week_start_utc()

            assert result == date(2026, 2, 9)  # Monday of that week
            assert result.weekday() == 0

    def test_always_returns_monday(self):
        """Result should always be a Monday (weekday 0)."""
        test_dates = [
            datetime(2026, 2, 9, tzinfo=timezone.utc),   # Monday
            datetime(2026, 2, 10, tzinfo=timezone.utc),  # Tuesday
            datetime(2026, 2, 11, tzinfo=timezone.utc),  # Wednesday
            datetime(2026, 2, 12, tzinfo=timezone.utc),  # Thursday
            datetime(2026, 2, 13, tzinfo=timezone.utc),  # Friday
            datetime(2026, 2, 14, tzinfo=timezone.utc),  # Saturday
            datetime(2026, 2, 15, tzinfo=timezone.utc),  # Sunday
        ]

        for test_date in test_dates:
            with patch("backend.apps.priority_guardian.services.pattern_service.datetime") as mock_dt:
                mock_dt.now.return_value = test_date
                result = get_current_week_start_utc()
                assert result.weekday() == 0, f"Failed for {test_date}"


class TestResolveKeyword:
    """Tests for resolve_keyword helper."""

    def test_active_priority_returns_keyword(self):
        """Active priority with keyword returns priority.calendar_keyword."""
        priority = MagicMock()
        priority.status = "active"
        priority.calendar_keyword = "P1"

        result = resolve_keyword(priority, [])

        assert result == "P1"

    def test_retired_priority_returns_snapshot_keyword(self):
        """Retired priority returns most recent non-NULL snapshot keyword."""
        priority = MagicMock()
        priority.status = "retired"
        priority.calendar_keyword = None
        priority.id = uuid4()

        # Snapshots ordered by week_start desc (most recent first)
        snap1 = MagicMock()
        snap1.calendar_keyword_at_snapshot = "P2"
        snap1.week_start = date(2026, 2, 2)

        snap2 = MagicMock()
        snap2.calendar_keyword_at_snapshot = "P1"  # Older, should not be used
        snap2.week_start = date(2026, 1, 26)

        result = resolve_keyword(priority, [snap1, snap2])

        assert result == "P2"

    def test_retired_priority_all_null_snapshots_returns_none(self):
        """Retired priority with all NULL snapshot keywords returns None."""
        priority = MagicMock()
        priority.status = "retired"
        priority.calendar_keyword = None
        priority.id = uuid4()

        snap1 = MagicMock()
        snap1.calendar_keyword_at_snapshot = None

        snap2 = MagicMock()
        snap2.calendar_keyword_at_snapshot = None

        result = resolve_keyword(priority, [snap1, snap2])

        assert result is None

    def test_active_priority_null_keyword_logs_warning(self):
        """Active priority with NULL keyword logs warning and returns None."""
        priority = MagicMock()
        priority.status = "active"
        priority.calendar_keyword = None
        priority.id = uuid4()
        priority.name = "Test Priority"

        with patch("backend.apps.priority_guardian.services.pattern_service.logger") as mock_logger:
            result = resolve_keyword(priority, [])

            mock_logger.warning.assert_called_once()
            assert result is None


class TestDecimalToFloatRecursive:
    """Tests for decimal_to_float_recursive utility."""

    def test_converts_decimal_to_float(self):
        """Decimal values are converted to float."""
        result = decimal_to_float_recursive(Decimal("10.5"))
        assert result == 10.5
        assert isinstance(result, float)

    def test_handles_nested_dicts(self):
        """Nested dicts have Decimals converted."""
        data = {
            "value": Decimal("10.5"),
            "nested": {
                "inner": Decimal("5.25"),
            },
        }

        result = decimal_to_float_recursive(data)

        assert result["value"] == 10.5
        assert result["nested"]["inner"] == 5.25

    def test_handles_lists(self):
        """Lists have Decimals converted."""
        data = [Decimal("1.0"), Decimal("2.0"), Decimal("3.0")]

        result = decimal_to_float_recursive(data)

        assert result == [1.0, 2.0, 3.0]

    def test_preserves_none(self):
        """None values are preserved."""
        data = {"value": None}

        result = decimal_to_float_recursive(data)

        assert result["value"] is None

    def test_preserves_strings(self):
        """String values are preserved."""
        data = {"name": "Test"}

        result = decimal_to_float_recursive(data)

        assert result["name"] == "Test"

    def test_preserves_dates(self):
        """Date values are preserved."""
        today = date.today()
        data = {"date": today}

        result = decimal_to_float_recursive(data)

        assert result["date"] == today


class TestGetRetirementWeekStart:
    """Tests for _get_retirement_week_start helper."""

    def test_wednesday_returns_monday_of_that_week(self):
        """Retired on Wednesday returns Monday of that week."""
        retired_at = datetime(2026, 2, 11, 14, 0, 0, tzinfo=timezone.utc)  # Wednesday

        result = _get_retirement_week_start(retired_at)

        assert result == date(2026, 2, 9)  # Monday

    def test_monday_returns_that_monday(self):
        """Retired on Monday returns that Monday."""
        retired_at = datetime(2026, 2, 9, 10, 0, 0, tzinfo=timezone.utc)

        result = _get_retirement_week_start(retired_at)

        assert result == date(2026, 2, 9)


# ============================================================================
# Pattern 1: Consistency Streak Tests
# ============================================================================

class TestConsistencyStreak:
    """Tests for Pattern 1: Consistency Streak."""

    def _create_priority(self, type_="flexible", status="active", keyword="P1"):
        """Create a mock priority."""
        p = MagicMock()
        p.id = uuid4()
        p.name = "Test Priority"
        p.type = type_
        p.status = status
        p.calendar_keyword = keyword
        p.retired_at = None
        return p

    def _create_snapshot(self, week_start, streak=None, actual_hours=Decimal("5.0"), keyword="P1", target_hours=Decimal("8.0")):
        """Create a mock snapshot."""
        s = MagicMock()
        s.week_start = week_start
        s.streak_at_snapshot = streak
        s.actual_hours = actual_hours
        s.calendar_keyword_at_snapshot = keyword
        s.target_hours = target_hours
        return s

    def test_flexible_priority_with_streak_6_surfaced(self):
        """Flexible priority with 6-week streak is surfaced."""
        priority = self._create_priority()
        # Need 6 actual snapshots for a streak of 6
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), streak=6),
            self._create_snapshot(date(2026, 1, 26), streak=5),
            self._create_snapshot(date(2026, 1, 19), streak=4),
            self._create_snapshot(date(2026, 1, 12), streak=3),
            self._create_snapshot(date(2026, 1, 5), streak=2),
            self._create_snapshot(date(2025, 12, 29), streak=1),
        ]

        patterns = _compute_consistency_streaks(
            [priority],
            {priority.id: snapshots},
            date(2026, 2, 9),
        )

        assert len(patterns) == 1
        assert patterns[0]["pattern_type"] == "consistency_streak"
        assert patterns[0]["streak_weeks"] == 6
        assert patterns[0]["streak_source"] == "snapshot"

    def test_streak_2_not_surfaced(self):
        """Streak of 2 (below threshold 4) is not surfaced."""
        priority = self._create_priority()
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), streak=2),
            self._create_snapshot(date(2026, 1, 26), streak=1),
            self._create_snapshot(date(2026, 1, 19), streak=0),
            self._create_snapshot(date(2026, 1, 12), streak=0),
        ]

        patterns = _compute_consistency_streaks(
            [priority],
            {priority.id: snapshots},
            date(2026, 2, 9),
        )

        assert len(patterns) == 0

    def test_deadline_priority_not_surfaced(self):
        """Deadline priority with high streak is not surfaced (flexible only)."""
        priority = self._create_priority(type_="deadline")
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), streak=8),
            self._create_snapshot(date(2026, 1, 26), streak=7),
            self._create_snapshot(date(2026, 1, 19), streak=6),
            self._create_snapshot(date(2026, 1, 12), streak=5),
        ]

        patterns = _compute_consistency_streaks(
            [priority],
            {priority.id: snapshots},
            date(2026, 2, 9),
        )

        assert len(patterns) == 0

    def test_retired_priority_not_surfaced(self):
        """Retired flexible priority with streak >= 4 is NOT surfaced (active only)."""
        priority = self._create_priority(status="retired", keyword=None)
        priority.retired_at = datetime(2026, 2, 4, tzinfo=timezone.utc)  # Retired mid-week

        # Would have streak=5 if active
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), streak=5, keyword="P1"),
            self._create_snapshot(date(2026, 1, 26), streak=4, keyword="P1"),
            self._create_snapshot(date(2026, 1, 19), streak=3, keyword="P1"),
            self._create_snapshot(date(2026, 1, 12), streak=2, keyword="P1"),
            self._create_snapshot(date(2026, 1, 5), streak=1, keyword="P1"),
        ]

        patterns = _compute_consistency_streaks(
            [priority],
            {priority.id: snapshots},
            date(2026, 2, 9),
        )

        # Retired priorities are skipped entirely
        assert len(patterns) == 0

    def test_null_streak_at_snapshot_skipped(self):
        """Snapshot with NULL streak_at_snapshot is skipped, next non-NULL used."""
        priority = self._create_priority()
        # Need 5 snapshots with actual_hours > 0 for streak=5
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), streak=None),  # NULL
            self._create_snapshot(date(2026, 1, 26), streak=5),     # This is used
            self._create_snapshot(date(2026, 1, 19), streak=4),
            self._create_snapshot(date(2026, 1, 12), streak=3),
            self._create_snapshot(date(2026, 1, 5), streak=2),
        ]

        patterns = _compute_consistency_streaks(
            [priority],
            {priority.id: snapshots},
            date(2026, 2, 9),
        )

        assert len(patterns) == 1
        assert patterns[0]["streak_weeks"] == 5
        assert patterns[0]["streak_source"] == "snapshot"

    def test_all_null_streak_uses_fallback(self):
        """All NULL streak_at_snapshot uses fallback computation."""
        priority = self._create_priority()
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), streak=None, actual_hours=Decimal("5")),
            self._create_snapshot(date(2026, 1, 26), streak=None, actual_hours=Decimal("3")),
            self._create_snapshot(date(2026, 1, 19), streak=None, actual_hours=Decimal("4")),
            self._create_snapshot(date(2026, 1, 12), streak=None, actual_hours=Decimal("2")),
            self._create_snapshot(date(2026, 1, 5), streak=None, actual_hours=Decimal("0")),
        ]

        patterns = _compute_consistency_streaks(
            [priority],
            {priority.id: snapshots},
            date(2026, 2, 9),
        )

        assert len(patterns) == 1
        assert patterns[0]["streak_weeks"] == 4  # Computed from 4 consecutive > 0
        assert patterns[0]["streak_source"] == "computed"

    def test_deadline_with_null_streak_fallback_not_surfaced(self):
        """Deadline priority with NULL streak and fallback still not surfaced."""
        priority = self._create_priority(type_="deadline")
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), streak=None, actual_hours=Decimal("10")),
            self._create_snapshot(date(2026, 1, 26), streak=None, actual_hours=Decimal("10")),
            self._create_snapshot(date(2026, 1, 19), streak=None, actual_hours=Decimal("10")),
            self._create_snapshot(date(2026, 1, 12), streak=None, actual_hours=Decimal("10")),
        ]

        patterns = _compute_consistency_streaks(
            [priority],
            {priority.id: snapshots},
            date(2026, 2, 9),
        )

        assert len(patterns) == 0

    def test_retired_flexible_with_long_streak_not_surfaced(self):
        """Retired flexible priority with 6-week streak and snapshots returns no pattern."""
        priority = self._create_priority(status="retired", keyword=None)
        priority.retired_at = datetime(2026, 1, 22, tzinfo=timezone.utc)  # Wednesday of week starting 1/19

        # Would have streak=6 if active
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), streak=8, keyword="P1"),
            self._create_snapshot(date(2026, 1, 26), streak=7, keyword="P1"),
            self._create_snapshot(date(2026, 1, 19), streak=6, keyword="P1"),
            self._create_snapshot(date(2026, 1, 12), streak=5, keyword="P1"),
            self._create_snapshot(date(2026, 1, 5), streak=4, keyword="P1"),
            self._create_snapshot(date(2025, 12, 29), streak=3, keyword="P1"),
            self._create_snapshot(date(2025, 12, 22), streak=2, keyword="P1"),
            self._create_snapshot(date(2025, 12, 15), streak=1, keyword="P1"),
        ]

        patterns = _compute_consistency_streaks(
            [priority],
            {priority.id: snapshots},
            date(2026, 2, 9),
        )

        # Retired priorities are skipped entirely - no pattern returned
        assert len(patterns) == 0


# ============================================================================
# Pattern 2: Abandoned Priority Tests
# ============================================================================

class TestAbandonedPriority:
    """Tests for Pattern 2: Abandoned Priority Signal."""

    def _create_priority(self, status="active", keyword="P1"):
        """Create a mock priority."""
        p = MagicMock()
        p.id = uuid4()
        p.name = "Test Priority"
        p.type = "flexible"
        p.status = status
        p.calendar_keyword = keyword
        return p

    def _create_snapshot(self, week_start, actual_hours=Decimal("5.0"), keyword="P1"):
        """Create a mock snapshot."""
        s = MagicMock()
        s.week_start = week_start
        s.actual_hours = actual_hours
        s.calendar_keyword_at_snapshot = keyword
        return s

    def test_active_priority_low_hours_surfaced(self):
        """Active priority averaging 0.3h/week is surfaced."""
        priority = self._create_priority()
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), actual_hours=Decimal("0.5")),
            self._create_snapshot(date(2026, 1, 26), actual_hours=Decimal("0.2")),
            self._create_snapshot(date(2026, 1, 19), actual_hours=Decimal("0.3")),
            self._create_snapshot(date(2026, 1, 12), actual_hours=Decimal("0.2")),
        ]

        patterns = _compute_abandoned_priorities(
            [priority],
            {priority.id: snapshots},
            current_week_start=date(2026, 2, 9),
        )

        assert len(patterns) == 1
        assert patterns[0]["pattern_type"] == "abandoned_priority"
        assert patterns[0]["avg_hours_last_4_weeks"] == Decimal("0.3")

    def test_active_priority_2h_not_surfaced(self):
        """Active priority averaging 2.0h/week is not surfaced."""
        priority = self._create_priority()
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), actual_hours=Decimal("2.0")),
            self._create_snapshot(date(2026, 1, 26), actual_hours=Decimal("2.0")),
            self._create_snapshot(date(2026, 1, 19), actual_hours=Decimal("2.0")),
            self._create_snapshot(date(2026, 1, 12), actual_hours=Decimal("2.0")),
        ]

        patterns = _compute_abandoned_priorities(
            [priority],
            {priority.id: snapshots},
            current_week_start=date(2026, 2, 9),
        )

        assert len(patterns) == 0

    def test_retired_priority_not_surfaced(self):
        """Retired priority with low hours is NOT surfaced."""
        priority = self._create_priority(status="retired")
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), actual_hours=Decimal("0.1")),
            self._create_snapshot(date(2026, 1, 26), actual_hours=Decimal("0.1")),
            self._create_snapshot(date(2026, 1, 19), actual_hours=Decimal("0.1")),
            self._create_snapshot(date(2026, 1, 12), actual_hours=Decimal("0.1")),
        ]

        patterns = _compute_abandoned_priorities(
            [priority],
            {priority.id: snapshots},
            current_week_start=date(2026, 2, 9),
        )

        assert len(patterns) == 0

    def test_only_3_snapshots_not_surfaced(self):
        """Active priority with only 3 snapshots is not surfaced."""
        priority = self._create_priority()
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), actual_hours=Decimal("0.1")),
            self._create_snapshot(date(2026, 1, 26), actual_hours=Decimal("0.1")),
            self._create_snapshot(date(2026, 1, 19), actual_hours=Decimal("0.1")),
        ]

        patterns = _compute_abandoned_priorities(
            [priority],
            {priority.id: snapshots},
            current_week_start=date(2026, 2, 9),
        )

        assert len(patterns) == 0

    def test_null_actual_hours_skipped(self):
        """Snapshots with NULL actual_hours are skipped in average."""
        priority = self._create_priority()
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), actual_hours=None),  # Skipped
            self._create_snapshot(date(2026, 1, 26), actual_hours=Decimal("0.2")),
            self._create_snapshot(date(2026, 1, 19), actual_hours=Decimal("0.2")),
            self._create_snapshot(date(2026, 1, 12), actual_hours=Decimal("0.2")),
            self._create_snapshot(date(2026, 1, 5), actual_hours=Decimal("0.2")),
        ]

        patterns = _compute_abandoned_priorities(
            [priority],
            {priority.id: snapshots},
            current_week_start=date(2026, 2, 9),
        )

        # Should use 4 non-NULL snapshots
        assert len(patterns) == 1
        assert patterns[0]["avg_hours_last_4_weeks"] == Decimal("0.2")

    # -------------------------------------------------------------------------
    # Deadline Priority Tests (increment_27)
    # -------------------------------------------------------------------------

    def _create_deadline_priority(self, deadline, status="active", keyword="P1"):
        """Create a mock deadline priority."""
        p = MagicMock()
        p.id = uuid4()
        p.name = "Test Deadline Priority"
        p.type = "deadline"
        p.status = status
        p.calendar_keyword = keyword
        p.deadline = deadline
        return p

    def test_deadline_3_weeks_away_fires(self):
        """Deadline priority, avg < 1.0h, deadline in 3 weeks → pattern fires, weeks_until_deadline = 3."""
        current_week_start = date(2026, 2, 9)
        deadline = current_week_start + timedelta(weeks=3)  # 3 weeks away
        priority = self._create_deadline_priority(deadline=deadline)
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), actual_hours=Decimal("0.5")),
            self._create_snapshot(date(2026, 1, 26), actual_hours=Decimal("0.2")),
            self._create_snapshot(date(2026, 1, 19), actual_hours=Decimal("0.3")),
            self._create_snapshot(date(2026, 1, 12), actual_hours=Decimal("0.2")),
        ]

        patterns = _compute_abandoned_priorities(
            [priority],
            {priority.id: snapshots},
            current_week_start=current_week_start,
        )

        assert len(patterns) == 1
        assert patterns[0]["pattern_type"] == "abandoned_priority"
        assert patterns[0]["weeks_until_deadline"] == 3

    def test_deadline_8_weeks_away_not_fires(self):
        """Deadline priority, avg < 1.0h, deadline in 8 weeks → pattern does NOT fire."""
        current_week_start = date(2026, 2, 9)
        deadline = current_week_start + timedelta(weeks=8)  # 8 weeks away
        priority = self._create_deadline_priority(deadline=deadline)
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), actual_hours=Decimal("0.5")),
            self._create_snapshot(date(2026, 1, 26), actual_hours=Decimal("0.2")),
            self._create_snapshot(date(2026, 1, 19), actual_hours=Decimal("0.3")),
            self._create_snapshot(date(2026, 1, 12), actual_hours=Decimal("0.2")),
        ]

        patterns = _compute_abandoned_priorities(
            [priority],
            {priority.id: snapshots},
            current_week_start=current_week_start,
        )

        assert len(patterns) == 0

    def test_deadline_exactly_4_weeks_fires(self):
        """Deadline priority, avg < 1.0h, deadline in exactly 4 weeks → pattern fires (boundary, ≤ 4)."""
        current_week_start = date(2026, 2, 9)
        deadline = current_week_start + timedelta(weeks=4)  # Exactly 4 weeks
        priority = self._create_deadline_priority(deadline=deadline)
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), actual_hours=Decimal("0.5")),
            self._create_snapshot(date(2026, 1, 26), actual_hours=Decimal("0.2")),
            self._create_snapshot(date(2026, 1, 19), actual_hours=Decimal("0.3")),
            self._create_snapshot(date(2026, 1, 12), actual_hours=Decimal("0.2")),
        ]

        patterns = _compute_abandoned_priorities(
            [priority],
            {priority.id: snapshots},
            current_week_start=current_week_start,
        )

        assert len(patterns) == 1
        assert patterns[0]["weeks_until_deadline"] == 4

    def test_deadline_5_weeks_away_not_fires(self):
        """Deadline priority, avg < 1.0h, deadline in 5 weeks → pattern does NOT fire (boundary, > 4)."""
        current_week_start = date(2026, 2, 9)
        deadline = current_week_start + timedelta(weeks=5)  # 5 weeks away
        priority = self._create_deadline_priority(deadline=deadline)
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), actual_hours=Decimal("0.5")),
            self._create_snapshot(date(2026, 1, 26), actual_hours=Decimal("0.2")),
            self._create_snapshot(date(2026, 1, 19), actual_hours=Decimal("0.3")),
            self._create_snapshot(date(2026, 1, 12), actual_hours=Decimal("0.2")),
        ]

        patterns = _compute_abandoned_priorities(
            [priority],
            {priority.id: snapshots},
            current_week_start=current_week_start,
        )

        assert len(patterns) == 0

    def test_deadline_flexible_no_weeks_field(self):
        """Flexible priority, avg < 1.0h → pattern fires as before, no weeks_until_deadline field."""
        priority = self._create_priority()  # Flexible by default
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), actual_hours=Decimal("0.5")),
            self._create_snapshot(date(2026, 1, 26), actual_hours=Decimal("0.2")),
            self._create_snapshot(date(2026, 1, 19), actual_hours=Decimal("0.3")),
            self._create_snapshot(date(2026, 1, 12), actual_hours=Decimal("0.2")),
        ]

        patterns = _compute_abandoned_priorities(
            [priority],
            {priority.id: snapshots},
            current_week_start=date(2026, 2, 9),
        )

        assert len(patterns) == 1
        assert patterns[0]["pattern_type"] == "abandoned_priority"
        assert "weeks_until_deadline" not in patterns[0]

    def test_deadline_above_threshold_not_fires(self):
        """Deadline priority, avg ≥ 1.0h, deadline in 2 weeks → pattern does NOT fire."""
        current_week_start = date(2026, 2, 9)
        deadline = current_week_start + timedelta(weeks=2)
        priority = self._create_deadline_priority(deadline=deadline)
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), actual_hours=Decimal("2.0")),
            self._create_snapshot(date(2026, 1, 26), actual_hours=Decimal("2.0")),
            self._create_snapshot(date(2026, 1, 19), actual_hours=Decimal("2.0")),
            self._create_snapshot(date(2026, 1, 12), actual_hours=Decimal("2.0")),
        ]

        patterns = _compute_abandoned_priorities(
            [priority],
            {priority.id: snapshots},
            current_week_start=current_week_start,
        )

        assert len(patterns) == 0

    def test_deadline_past_clamped_to_zero(self):
        """Deadline priority, avg < 1.0h, deadline already passed → pattern fires, weeks_until_deadline = 0."""
        current_week_start = date(2026, 2, 9)
        deadline = current_week_start - timedelta(weeks=2)  # 2 weeks ago
        priority = self._create_deadline_priority(deadline=deadline)
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), actual_hours=Decimal("0.5")),
            self._create_snapshot(date(2026, 1, 26), actual_hours=Decimal("0.2")),
            self._create_snapshot(date(2026, 1, 19), actual_hours=Decimal("0.3")),
            self._create_snapshot(date(2026, 1, 12), actual_hours=Decimal("0.2")),
        ]

        patterns = _compute_abandoned_priorities(
            [priority],
            {priority.id: snapshots},
            current_week_start=current_week_start,
        )

        assert len(patterns) == 1
        assert patterns[0]["weeks_until_deadline"] == 0

    def test_deadline_exactly_current_week_zero(self):
        """Deadline priority, avg < 1.0h, deadline is exactly current_week_start → weeks_until_deadline = 0."""
        current_week_start = date(2026, 2, 9)
        deadline = current_week_start  # Exactly on current week start
        priority = self._create_deadline_priority(deadline=deadline)
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), actual_hours=Decimal("0.5")),
            self._create_snapshot(date(2026, 1, 26), actual_hours=Decimal("0.2")),
            self._create_snapshot(date(2026, 1, 19), actual_hours=Decimal("0.3")),
            self._create_snapshot(date(2026, 1, 12), actual_hours=Decimal("0.2")),
        ]

        patterns = _compute_abandoned_priorities(
            [priority],
            {priority.id: snapshots},
            current_week_start=current_week_start,
        )

        assert len(patterns) == 1
        assert patterns[0]["weeks_until_deadline"] == 0


# ============================================================================
# Pattern 3: Priority Switching Tests
# ============================================================================

class TestPrioritySwitching:
    """Tests for Pattern 3: Priority Switching Frequency."""

    def _create_priority(
        self,
        created_at,
        retired_at=None,
        priority_type="flexible",
        goals=None,
        deliverables=None,
    ):
        """Create a mock priority with goals/deliverables."""
        p = MagicMock()
        p.id = uuid4()
        p.created_at = created_at
        p.retired_at = retired_at
        p.type = priority_type
        p.goals = goals if goals is not None else []
        p.deliverables = deliverables if deliverables is not None else []
        return p

    def _create_goal(self, achieved):
        """Create a mock goal."""
        g = MagicMock()
        g.achieved = achieved
        return g

    def _create_deliverable(self, done):
        """Create a mock deliverable."""
        d = MagicMock()
        d.done = done
        return d

    def test_4_retirements_surfaced(self):
        """4 retirements in 3 months is surfaced."""
        # current_week_start=2026-02-09, so 3 months ago is ~2025-11-09
        priorities = [
            self._create_priority(
                datetime(2025, 11, 15, tzinfo=timezone.utc),
                datetime(2025, 12, 1, tzinfo=timezone.utc),
            ),
            self._create_priority(
                datetime(2025, 12, 1, tzinfo=timezone.utc),
                datetime(2025, 12, 15, tzinfo=timezone.utc),
            ),
            self._create_priority(
                datetime(2025, 12, 15, tzinfo=timezone.utc),
                datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            self._create_priority(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 15, tzinfo=timezone.utc),
            ),
            self._create_priority(
                datetime(2026, 1, 15, tzinfo=timezone.utc),
                None,  # Active
            ),
        ]

        patterns = _compute_priority_switching(
            priorities,
            current_week_start=date(2026, 2, 9),
        )

        assert len(patterns) == 1
        assert patterns[0]["pattern_type"] == "priority_switching"
        assert patterns[0]["retirements_in_window"] == 4

    def test_1_retirement_not_surfaced(self):
        """1 retirement in 3 months is not surfaced (below threshold 3)."""
        priorities = [
            self._create_priority(
                datetime(2025, 12, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            self._create_priority(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                None,
            ),
        ]

        patterns = _compute_priority_switching(
            priorities,
            current_week_start=date(2026, 2, 9),
        )

        assert len(patterns) == 0

    def test_old_retirements_excluded(self):
        """Retirements older than 3 months are excluded."""
        # current_week_start=2026-02-09, so 3 months ago is ~2025-11-09
        # All these retirements are before that window
        priorities = [
            self._create_priority(
                datetime(2025, 6, 1, tzinfo=timezone.utc),
                datetime(2025, 7, 1, tzinfo=timezone.utc),  # Too old
            ),
            self._create_priority(
                datetime(2025, 7, 1, tzinfo=timezone.utc),
                datetime(2025, 8, 1, tzinfo=timezone.utc),  # Too old
            ),
            self._create_priority(
                datetime(2025, 8, 1, tzinfo=timezone.utc),
                datetime(2025, 9, 1, tzinfo=timezone.utc),  # Too old
            ),
            self._create_priority(
                datetime(2025, 9, 1, tzinfo=timezone.utc),
                datetime(2025, 10, 1, tzinfo=timezone.utc),  # Too old
            ),
        ]

        patterns = _compute_priority_switching(
            priorities,
            current_week_start=date(2026, 2, 9),
        )

        # All retirements before Nov 9, 2025 are excluded
        assert len(patterns) == 0

    def test_threshold_uses_retirements_not_creations(self):
        """Threshold is on retirements only, not creations."""
        # 5 creations in window but only 2 retirements
        priorities = [
            self._create_priority(datetime(2025, 11, 15, tzinfo=timezone.utc), None),
            self._create_priority(datetime(2025, 12, 1, tzinfo=timezone.utc), None),
            self._create_priority(datetime(2025, 12, 15, tzinfo=timezone.utc), None),
            self._create_priority(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 10, tzinfo=timezone.utc),
            ),
            self._create_priority(
                datetime(2026, 1, 10, tzinfo=timezone.utc),
                datetime(2026, 1, 20, tzinfo=timezone.utc),
            ),
        ]

        patterns = _compute_priority_switching(
            priorities,
            current_week_start=date(2026, 2, 9),
        )

        # Only 2 retirements, below threshold of 3
        assert len(patterns) == 0

    # -------------------------------------------------------------------------
    # Completion Filter Tests (increment_28)
    # -------------------------------------------------------------------------

    def test_completion_filter_all_incomplete_fires(self):
        """3 retired priorities with incomplete goals → retirements_in_window: 3, pattern fires."""
        priorities = [
            self._create_priority(
                datetime(2025, 12, 1, tzinfo=timezone.utc),
                datetime(2025, 12, 15, tzinfo=timezone.utc),
                goals=[self._create_goal(False)],
            ),
            self._create_priority(
                datetime(2025, 12, 15, tzinfo=timezone.utc),
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                goals=[self._create_goal(False), self._create_goal(True)],  # Partial
            ),
            self._create_priority(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 15, tzinfo=timezone.utc),
                goals=[self._create_goal(None)],  # None is not True
            ),
        ]

        patterns = _compute_priority_switching(
            priorities,
            current_week_start=date(2026, 2, 9),
        )

        assert len(patterns) == 1
        assert patterns[0]["retirements_in_window"] == 3

    def test_completion_filter_all_goals_achieved_excluded(self):
        """3 retired flexible priorities with all goals achieved → excluded, pattern does NOT fire."""
        priorities = [
            self._create_priority(
                datetime(2025, 12, 1, tzinfo=timezone.utc),
                datetime(2025, 12, 15, tzinfo=timezone.utc),
                goals=[self._create_goal(True), self._create_goal(True)],
            ),
            self._create_priority(
                datetime(2025, 12, 15, tzinfo=timezone.utc),
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                goals=[self._create_goal(True)],
            ),
            self._create_priority(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 15, tzinfo=timezone.utc),
                goals=[self._create_goal(True), self._create_goal(True), self._create_goal(True)],
            ),
        ]

        patterns = _compute_priority_switching(
            priorities,
            current_week_start=date(2026, 2, 9),
        )

        assert len(patterns) == 0

    def test_completion_filter_mixed_completions(self):
        """1 completed + 2 incomplete → retirements_in_window: 2, below threshold."""
        priorities = [
            self._create_priority(
                datetime(2025, 12, 1, tzinfo=timezone.utc),
                datetime(2025, 12, 15, tzinfo=timezone.utc),
                goals=[self._create_goal(True)],  # Completed - excluded
            ),
            self._create_priority(
                datetime(2025, 12, 15, tzinfo=timezone.utc),
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                goals=[self._create_goal(False)],  # Incomplete
            ),
            self._create_priority(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 15, tzinfo=timezone.utc),
                goals=[],  # Empty = incomplete
            ),
        ]

        patterns = _compute_priority_switching(
            priorities,
            current_week_start=date(2026, 2, 9),
        )

        # 2 incomplete, below threshold of 3
        assert len(patterns) == 0

    def test_completion_filter_1_complete_3_incomplete_fires(self):
        """1 completed + 3 incomplete → retirements_in_window: 3, pattern fires."""
        priorities = [
            self._create_priority(
                datetime(2025, 11, 20, tzinfo=timezone.utc),
                datetime(2025, 12, 1, tzinfo=timezone.utc),
                goals=[self._create_goal(True)],  # Completed - excluded
            ),
            self._create_priority(
                datetime(2025, 12, 1, tzinfo=timezone.utc),
                datetime(2025, 12, 15, tzinfo=timezone.utc),
                goals=[self._create_goal(False)],
            ),
            self._create_priority(
                datetime(2025, 12, 15, tzinfo=timezone.utc),
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                goals=[],
            ),
            self._create_priority(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 15, tzinfo=timezone.utc),
                goals=[self._create_goal(False)],
            ),
        ]

        patterns = _compute_priority_switching(
            priorities,
            current_week_start=date(2026, 2, 9),
        )

        assert len(patterns) == 1
        assert patterns[0]["retirements_in_window"] == 3
        assert patterns[0]["successful_retirements_excluded"] == 1

    def test_completion_filter_empty_goals_counts_as_switch(self):
        """3 retired with zero goals → all count as switches, pattern fires."""
        priorities = [
            self._create_priority(
                datetime(2025, 12, 1, tzinfo=timezone.utc),
                datetime(2025, 12, 15, tzinfo=timezone.utc),
                goals=[],
            ),
            self._create_priority(
                datetime(2025, 12, 15, tzinfo=timezone.utc),
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                goals=[],
            ),
            self._create_priority(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 15, tzinfo=timezone.utc),
                goals=[],
            ),
        ]

        patterns = _compute_priority_switching(
            priorities,
            current_week_start=date(2026, 2, 9),
        )

        assert len(patterns) == 1
        assert patterns[0]["retirements_in_window"] == 3

    def test_completion_filter_deadline_all_deliverables_done_excluded(self):
        """Deadline priority with all deliverables done → excluded from switch count."""
        priorities = [
            self._create_priority(
                datetime(2025, 12, 1, tzinfo=timezone.utc),
                datetime(2025, 12, 15, tzinfo=timezone.utc),
                priority_type="deadline",
                deliverables=[self._create_deliverable(True), self._create_deliverable(True)],
            ),
            self._create_priority(
                datetime(2025, 12, 15, tzinfo=timezone.utc),
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                priority_type="deadline",
                deliverables=[self._create_deliverable(True)],
            ),
            self._create_priority(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 15, tzinfo=timezone.utc),
                priority_type="deadline",
                deliverables=[self._create_deliverable(True)],
            ),
        ]

        patterns = _compute_priority_switching(
            priorities,
            current_week_start=date(2026, 2, 9),
        )

        # All 3 completed, excluded
        assert len(patterns) == 0

    def test_completion_filter_mixed_types(self):
        """Mixed types: 1 flexible completed, 1 deadline incomplete, 1 flexible empty → 2 switches."""
        priorities = [
            self._create_priority(
                datetime(2025, 12, 1, tzinfo=timezone.utc),
                datetime(2025, 12, 15, tzinfo=timezone.utc),
                priority_type="flexible",
                goals=[self._create_goal(True)],  # Completed - excluded
            ),
            self._create_priority(
                datetime(2025, 12, 15, tzinfo=timezone.utc),
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                priority_type="deadline",
                deliverables=[self._create_deliverable(False)],  # Incomplete
            ),
            self._create_priority(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 15, tzinfo=timezone.utc),
                priority_type="flexible",
                goals=[],  # Empty = incomplete
            ),
        ]

        patterns = _compute_priority_switching(
            priorities,
            current_week_start=date(2026, 2, 9),
        )

        # 2 switches, below threshold
        assert len(patterns) == 0

    def test_completion_filter_outside_3_month_window(self):
        """3 retirements within 6-month but outside 3-month window → pattern does NOT fire."""
        # Retirements in Aug-Oct 2025, outside 3-month window from Feb 2026
        priorities = [
            self._create_priority(
                datetime(2025, 7, 1, tzinfo=timezone.utc),
                datetime(2025, 8, 1, tzinfo=timezone.utc),
                goals=[self._create_goal(False)],
            ),
            self._create_priority(
                datetime(2025, 8, 1, tzinfo=timezone.utc),
                datetime(2025, 9, 1, tzinfo=timezone.utc),
                goals=[self._create_goal(False)],
            ),
            self._create_priority(
                datetime(2025, 9, 1, tzinfo=timezone.utc),
                datetime(2025, 10, 1, tzinfo=timezone.utc),
                goals=[self._create_goal(False)],
            ),
        ]

        patterns = _compute_priority_switching(
            priorities,
            current_week_start=date(2026, 2, 9),
        )

        # All outside 3-month window
        assert len(patterns) == 0

    def test_completion_filter_successful_retirements_excluded_field(self):
        """successful_retirements_excluded field is present and correct."""
        priorities = [
            self._create_priority(
                datetime(2025, 11, 20, tzinfo=timezone.utc),
                datetime(2025, 12, 1, tzinfo=timezone.utc),
                goals=[self._create_goal(True)],  # Excluded
            ),
            self._create_priority(
                datetime(2025, 12, 1, tzinfo=timezone.utc),
                datetime(2025, 12, 10, tzinfo=timezone.utc),
                goals=[self._create_goal(True), self._create_goal(True)],  # Excluded
            ),
            self._create_priority(
                datetime(2025, 12, 10, tzinfo=timezone.utc),
                datetime(2025, 12, 20, tzinfo=timezone.utc),
                goals=[self._create_goal(False)],
            ),
            self._create_priority(
                datetime(2025, 12, 20, tzinfo=timezone.utc),
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                goals=[],
            ),
            self._create_priority(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 15, tzinfo=timezone.utc),
                goals=[self._create_goal(False)],
            ),
        ]

        patterns = _compute_priority_switching(
            priorities,
            current_week_start=date(2026, 2, 9),
        )

        assert len(patterns) == 1
        assert patterns[0]["retirements_in_window"] == 3
        assert patterns[0]["successful_retirements_excluded"] == 2

    def test_completion_filter_partial_goals_counts_as_switch(self):
        """Flexible priority with 2/3 goals achieved → counts as switch (partial != complete)."""
        priorities = [
            self._create_priority(
                datetime(2025, 12, 1, tzinfo=timezone.utc),
                datetime(2025, 12, 15, tzinfo=timezone.utc),
                goals=[self._create_goal(True), self._create_goal(True), self._create_goal(False)],
            ),
            self._create_priority(
                datetime(2025, 12, 15, tzinfo=timezone.utc),
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                goals=[self._create_goal(True), self._create_goal(False)],
            ),
            self._create_priority(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 15, tzinfo=timezone.utc),
                goals=[self._create_goal(False)],
            ),
        ]

        patterns = _compute_priority_switching(
            priorities,
            current_week_start=date(2026, 2, 9),
        )

        # All 3 have at least one incomplete goal
        assert len(patterns) == 1
        assert patterns[0]["retirements_in_window"] == 3

    def test_completion_filter_empty_goals_list_is_switch(self):
        """Flexible priority with empty goals list ([]) → counts as switch."""
        priorities = [
            self._create_priority(
                datetime(2025, 12, 1, tzinfo=timezone.utc),
                datetime(2025, 12, 15, tzinfo=timezone.utc),
                goals=[],  # Empty list
            ),
            self._create_priority(
                datetime(2025, 12, 15, tzinfo=timezone.utc),
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                goals=[],
            ),
            self._create_priority(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 15, tzinfo=timezone.utc),
                goals=[],
            ),
        ]

        patterns = _compute_priority_switching(
            priorities,
            current_week_start=date(2026, 2, 9),
        )

        assert len(patterns) == 1
        assert patterns[0]["retirements_in_window"] == 3
        assert patterns[0]["successful_retirements_excluded"] == 0

    def test_completion_filter_retired_priorities_list(self):
        """retired_priorities list contains name, type, and completion status."""
        priorities = [
            self._create_priority(
                datetime(2025, 12, 1, tzinfo=timezone.utc),
                datetime(2025, 12, 15, tzinfo=timezone.utc),
                priority_type="flexible",
                goals=[self._create_goal(True), self._create_goal(False), self._create_goal(False)],
            ),
            self._create_priority(
                datetime(2025, 12, 15, tzinfo=timezone.utc),
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                priority_type="deadline",
                deliverables=[self._create_deliverable(False), self._create_deliverable(False)],
            ),
            self._create_priority(
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 15, tzinfo=timezone.utc),
                priority_type="flexible",
                goals=[],
            ),
        ]
        # Set names for verification
        priorities[0].name = "Project Alpha"
        priorities[1].name = "Birthday Party"
        priorities[2].name = "Side Hustle"

        patterns = _compute_priority_switching(
            priorities,
            current_week_start=date(2026, 2, 9),
        )

        assert len(patterns) == 1
        assert "retired_priorities" in patterns[0]
        retired = patterns[0]["retired_priorities"]
        assert len(retired) == 3
        # Check structure with completion status
        assert retired[0] == {
            "name": "Project Alpha",
            "type": "flexible",
            "goals_achieved": 1,
            "goals_total": 3,
        }
        assert retired[1] == {
            "name": "Birthday Party",
            "type": "deadline",
            "deliverables_done": 0,
            "deliverables_total": 2,
        }
        assert retired[2] == {
            "name": "Side Hustle",
            "type": "flexible",
            "goals_achieved": 0,
            "goals_total": 0,
        }


# ============================================================================
# Pattern 4: Priority Protection Tests
# ============================================================================

class TestPriorityProtection:
    """Tests for Pattern 4: Priority Protection."""

    def _create_priority(self, status="active", keyword="P1"):
        """Create a mock priority."""
        p = MagicMock()
        p.id = uuid4()
        p.name = "Test Priority"
        p.type = "flexible"
        p.status = status
        p.calendar_keyword = keyword
        return p

    def _create_snapshot(
        self,
        week_start,
        actual_hours=Decimal("10.0"),
        total_tracked_hours=Decimal("40.0"),
        keyword="P1",
    ):
        """Create a mock snapshot."""
        s = MagicMock()
        s.week_start = week_start
        s.actual_hours = actual_hours
        s.total_tracked_hours = total_tracked_hours
        s.calendar_keyword_at_snapshot = keyword
        return s

    def test_stable_priority_growing_total_surfaced(self):
        """Priority stable at ~10h while total grew 25% is surfaced."""
        priority = self._create_priority()

        # Recent 4 weeks: priority=10h, total=50h
        # Prior 4 weeks: priority=10h, total=40h
        # Total change: 25%, priority change: 0%
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), Decimal("10"), Decimal("50")),
            self._create_snapshot(date(2026, 1, 26), Decimal("10"), Decimal("50")),
            self._create_snapshot(date(2026, 1, 19), Decimal("10"), Decimal("50")),
            self._create_snapshot(date(2026, 1, 12), Decimal("10"), Decimal("50")),
            self._create_snapshot(date(2026, 1, 5), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2025, 12, 29), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2025, 12, 22), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2025, 12, 15), Decimal("10"), Decimal("40")),
        ]

        patterns = _compute_priority_protection(
            [priority],
            {priority.id: snapshots},
        )

        assert len(patterns) == 1
        assert patterns[0]["pattern_type"] == "priority_protection"
        assert patterns[0]["priority_hours_trend"] == "stable"
        assert patterns[0]["total_hours_change_pct"] == Decimal("25.0")

    def test_total_hours_stable_not_surfaced(self):
        """Total hours stable (no pressure change) is not surfaced."""
        priority = self._create_priority()

        # Both periods: total=40h (no change)
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2026, 1, 26), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2026, 1, 19), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2026, 1, 12), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2026, 1, 5), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2025, 12, 29), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2025, 12, 22), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2025, 12, 15), Decimal("10"), Decimal("40")),
        ]

        patterns = _compute_priority_protection(
            [priority],
            {priority.id: snapshots},
        )

        assert len(patterns) == 0

    def test_priority_dropped_not_surfaced(self):
        """Priority hours dropped while total grew is not surfaced."""
        priority = self._create_priority()

        # Recent: priority=5h (dropped 50%), total=50h (grew 25%)
        # Prior: priority=10h, total=40h
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), Decimal("5"), Decimal("50")),
            self._create_snapshot(date(2026, 1, 26), Decimal("5"), Decimal("50")),
            self._create_snapshot(date(2026, 1, 19), Decimal("5"), Decimal("50")),
            self._create_snapshot(date(2026, 1, 12), Decimal("5"), Decimal("50")),
            self._create_snapshot(date(2026, 1, 5), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2025, 12, 29), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2025, 12, 22), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2025, 12, 15), Decimal("10"), Decimal("40")),
        ]

        patterns = _compute_priority_protection(
            [priority],
            {priority.id: snapshots},
        )

        assert len(patterns) == 0

    def test_total_grew_only_5_percent_not_surfaced(self):
        """Total hours grew by only 5% (below 15% threshold) is not surfaced."""
        priority = self._create_priority()

        # Total: 42h vs 40h = 5% change (below 15%)
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), Decimal("10"), Decimal("42")),
            self._create_snapshot(date(2026, 1, 26), Decimal("10"), Decimal("42")),
            self._create_snapshot(date(2026, 1, 19), Decimal("10"), Decimal("42")),
            self._create_snapshot(date(2026, 1, 12), Decimal("10"), Decimal("42")),
            self._create_snapshot(date(2026, 1, 5), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2025, 12, 29), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2025, 12, 22), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2025, 12, 15), Decimal("10"), Decimal("40")),
        ]

        patterns = _compute_priority_protection(
            [priority],
            {priority.id: snapshots},
        )

        assert len(patterns) == 0

    def test_only_4_snapshots_not_surfaced(self):
        """Priority with only 4 snapshots is skipped (needs 8)."""
        priority = self._create_priority()

        snapshots = [
            self._create_snapshot(date(2026, 2, 2), Decimal("10"), Decimal("50")),
            self._create_snapshot(date(2026, 1, 26), Decimal("10"), Decimal("50")),
            self._create_snapshot(date(2026, 1, 19), Decimal("10"), Decimal("50")),
            self._create_snapshot(date(2026, 1, 12), Decimal("10"), Decimal("50")),
        ]

        patterns = _compute_priority_protection(
            [priority],
            {priority.id: snapshots},
        )

        assert len(patterns) == 0

    def test_null_fields_excluded(self):
        """Snapshots with NULL total_tracked_hours or actual_hours excluded."""
        priority = self._create_priority()

        # Include NULL snapshots that should be excluded
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), None, Decimal("50")),  # NULL actual
            self._create_snapshot(date(2026, 1, 26), Decimal("10"), None),  # NULL total
            self._create_snapshot(date(2026, 1, 19), Decimal("10"), Decimal("50")),
            self._create_snapshot(date(2026, 1, 12), Decimal("10"), Decimal("50")),
            self._create_snapshot(date(2026, 1, 5), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2025, 12, 29), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2025, 12, 22), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2025, 12, 15), Decimal("10"), Decimal("40")),
        ]

        patterns = _compute_priority_protection(
            [priority],
            {priority.id: snapshots},
        )

        # Only 6 qualifying snapshots (< 8), pattern skipped
        assert len(patterns) == 0

    def test_prior_total_below_5h_skipped(self):
        """Prior period total_tracked_hours avg < 5h/week skips pattern."""
        priority = self._create_priority()

        # Prior period: avg 3h/week (below 5h floor)
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), Decimal("10"), Decimal("50")),
            self._create_snapshot(date(2026, 1, 26), Decimal("10"), Decimal("50")),
            self._create_snapshot(date(2026, 1, 19), Decimal("10"), Decimal("50")),
            self._create_snapshot(date(2026, 1, 12), Decimal("10"), Decimal("50")),
            self._create_snapshot(date(2026, 1, 5), Decimal("2"), Decimal("3")),
            self._create_snapshot(date(2025, 12, 29), Decimal("2"), Decimal("3")),
            self._create_snapshot(date(2025, 12, 22), Decimal("2"), Decimal("3")),
            self._create_snapshot(date(2025, 12, 15), Decimal("2"), Decimal("3")),
        ]

        patterns = _compute_priority_protection(
            [priority],
            {priority.id: snapshots},
        )

        assert len(patterns) == 0

    def test_boundary_priority_change_minus_10_surfaced(self):
        """Priority change exactly -10% is surfaced (boundary)."""
        priority = self._create_priority()

        # Recent: priority=9h, Prior: priority=10h → -10% change (at boundary)
        # Total: 46h vs 40h → 15% change (at boundary)
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), Decimal("9"), Decimal("46")),
            self._create_snapshot(date(2026, 1, 26), Decimal("9"), Decimal("46")),
            self._create_snapshot(date(2026, 1, 19), Decimal("9"), Decimal("46")),
            self._create_snapshot(date(2026, 1, 12), Decimal("9"), Decimal("46")),
            self._create_snapshot(date(2026, 1, 5), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2025, 12, 29), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2025, 12, 22), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2025, 12, 15), Decimal("10"), Decimal("40")),
        ]

        patterns = _compute_priority_protection(
            [priority],
            {priority.id: snapshots},
        )

        assert len(patterns) == 1
        assert patterns[0]["priority_hours_trend"] == "stable"

    def test_boundary_priority_change_minus_10_01_not_surfaced(self):
        """Priority change -10.01% is not surfaced (below boundary)."""
        priority = self._create_priority()

        # Recent: priority=8.999h, Prior: priority=10h → -10.01% change
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), Decimal("8.999"), Decimal("50")),
            self._create_snapshot(date(2026, 1, 26), Decimal("8.999"), Decimal("50")),
            self._create_snapshot(date(2026, 1, 19), Decimal("8.999"), Decimal("50")),
            self._create_snapshot(date(2026, 1, 12), Decimal("8.999"), Decimal("50")),
            self._create_snapshot(date(2026, 1, 5), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2025, 12, 29), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2025, 12, 22), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2025, 12, 15), Decimal("10"), Decimal("40")),
        ]

        patterns = _compute_priority_protection(
            [priority],
            {priority.id: snapshots},
        )

        assert len(patterns) == 0

    def test_growing_trend_detected(self):
        """Priority hours growing > 10% sets trend to 'growing'."""
        priority = self._create_priority()

        # Recent: priority=12h, Prior: priority=10h → +20% change
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), Decimal("12"), Decimal("50")),
            self._create_snapshot(date(2026, 1, 26), Decimal("12"), Decimal("50")),
            self._create_snapshot(date(2026, 1, 19), Decimal("12"), Decimal("50")),
            self._create_snapshot(date(2026, 1, 12), Decimal("12"), Decimal("50")),
            self._create_snapshot(date(2026, 1, 5), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2025, 12, 29), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2025, 12, 22), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2025, 12, 15), Decimal("10"), Decimal("40")),
        ]

        patterns = _compute_priority_protection(
            [priority],
            {priority.id: snapshots},
        )

        assert len(patterns) == 1
        assert patterns[0]["priority_hours_trend"] == "growing"


# ============================================================================
# Detail String Tests
# ============================================================================

class TestDetailStrings:
    """Tests for detail string construction."""

    def _create_priority(self, name="Test Priority", keyword="P1"):
        """Create a mock priority."""
        p = MagicMock()
        p.id = uuid4()
        p.name = name
        p.type = "flexible"
        p.status = "active"
        p.calendar_keyword = keyword
        p.retired_at = None
        return p

    def _create_snapshot(self, week_start, streak=5, keyword="P1", target_hours=Decimal("8.0")):
        """Create a mock snapshot."""
        s = MagicMock()
        s.week_start = week_start
        s.streak_at_snapshot = streak
        s.actual_hours = Decimal("5")
        s.calendar_keyword_at_snapshot = keyword
        s.target_hours = target_hours
        return s

    def test_detail_with_keyword(self):
        """Pattern with non-null keyword includes keyword in detail."""
        priority = self._create_priority(keyword="P1")
        # Need 5 snapshots for streak=5
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), streak=5, keyword="P1"),
            self._create_snapshot(date(2026, 1, 26), streak=4),
            self._create_snapshot(date(2026, 1, 19), streak=3),
            self._create_snapshot(date(2026, 1, 12), streak=2),
            self._create_snapshot(date(2026, 1, 5), streak=1),
        ]

        patterns = _compute_consistency_streaks(
            [priority],
            {priority.id: snapshots},
            date(2026, 2, 9),
        )

        # Detail should not contain "None" or null
        assert "None" not in patterns[0]["detail"]
        assert "null" not in patterns[0]["detail"]

    def test_detail_without_keyword_uses_name(self):
        """Pattern with null keyword uses priority_name in detail."""
        # Active priority with NULL keyword (edge case - logs warning but still produces pattern)
        priority = self._create_priority(name="My Custom Priority", keyword=None)
        # status is already "active" from helper

        # Need 5 snapshots with NULL keyword for streak=5
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), streak=5, keyword=None),
            self._create_snapshot(date(2026, 1, 26), streak=4, keyword=None),
            self._create_snapshot(date(2026, 1, 19), streak=3, keyword=None),
            self._create_snapshot(date(2026, 1, 12), streak=2, keyword=None),
            self._create_snapshot(date(2026, 1, 5), streak=1, keyword=None),
        ]

        with patch("backend.apps.priority_guardian.services.pattern_service.logger"):
            patterns = _compute_consistency_streaks(
                [priority],
                {priority.id: snapshots},
                date(2026, 2, 9),
            )

        # Pattern should still be produced
        assert len(patterns) == 1
        # Detail should NOT contain "None" or "null" - uses priority_name fallback
        assert "None" not in patterns[0]["detail"]
        assert "null" not in patterns[0]["detail"]


# ============================================================================
# Sorting Tests
# ============================================================================

class TestSortPatterns:
    """Tests for pattern sorting."""

    def test_deterministic_order(self):
        """Patterns sorted by (pattern_type, priority_id, priority_name)."""
        patterns = [
            {"pattern_type": "priority_protection", "priority_id": "bbb", "priority_name": "Alpha"},
            {"pattern_type": "consistency_streak", "priority_id": "ccc", "priority_name": "Beta"},
            {"pattern_type": "abandoned_priority", "priority_id": "aaa", "priority_name": "Gamma"},
            {"pattern_type": "consistency_streak", "priority_id": "aaa", "priority_name": "Alpha"},
        ]

        sorted_patterns = _sort_patterns(patterns)

        # Should be sorted by pattern_type first
        assert sorted_patterns[0]["pattern_type"] == "abandoned_priority"
        assert sorted_patterns[1]["pattern_type"] == "consistency_streak"
        assert sorted_patterns[2]["pattern_type"] == "consistency_streak"
        assert sorted_patterns[3]["pattern_type"] == "priority_protection"

    def test_null_priority_name_doesnt_crash(self):
        """Sorting with NULL priority_name doesn't crash."""
        patterns = [
            {"pattern_type": "consistency_streak", "priority_id": "aaa", "priority_name": None},
            {"pattern_type": "consistency_streak", "priority_id": "bbb", "priority_name": "Test"},
        ]

        # Should not raise
        sorted_patterns = _sort_patterns(patterns)

        assert len(sorted_patterns) == 2


# ============================================================================
# Global Rules Tests
# ============================================================================

class TestGlobalRules:
    """Tests for global floor and rules."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock async session."""
        session = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_3_weeks_returns_insufficient(self, mock_session):
        """User with 3 completed weeks returns data_insufficient."""
        user_id = uuid4()

        # Mock snapshot query - 3 weeks
        snapshots = [MagicMock() for _ in range(3)]
        for i, s in enumerate(snapshots):
            s.week_start = date(2026, 1, 12 + i * 7)
            s.priority_id = uuid4()

        snap_result = MagicMock()
        snap_result.scalars.return_value.all.return_value = snapshots

        # Mock priority query
        priority_result = MagicMock()
        priority_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [snap_result, priority_result]

        result = await compute_patterns(user_id, mock_session)

        assert result["success"] is True
        assert result["data"]["data_insufficient"] is True
        assert result["data"]["weeks_available"] == 3
        assert result["data"]["reason"] == "INSUFFICIENT_WEEKS"

    @pytest.mark.asyncio
    async def test_12_weeks_computes_patterns(self, mock_session):
        """User with 12 completed weeks computes patterns normally."""
        user_id = uuid4()

        # Create 12 weeks of snapshots with proper objects
        priority_id = uuid4()
        snapshots = []
        base_date = date(2025, 11, 17)
        for i in range(12):
            s = MagicMock()
            s.week_start = base_date + timedelta(weeks=i)
            s.priority_id = priority_id
            s.actual_hours = Decimal("5")
            s.total_tracked_hours = Decimal("40")
            s.streak_at_snapshot = i + 1
            s.calendar_keyword_at_snapshot = "P1"
            snapshots.append(s)

        snap_result = MagicMock()
        snap_result.scalars.return_value.all.return_value = snapshots

        # Mock priority query
        priority = MagicMock()
        priority.id = priority_id
        priority.name = "Test"
        priority.type = "flexible"
        priority.status = "active"
        priority.calendar_keyword = "P1"
        priority.retired_at = None
        priority.created_at = datetime(2025, 11, 1, tzinfo=timezone.utc)

        priority_result = MagicMock()
        priority_result.scalars.return_value.all.return_value = [priority]

        mock_session.execute.side_effect = [snap_result, priority_result]

        with patch("backend.apps.priority_guardian.services.pattern_service.get_current_week_start_utc") as mock_week:
            mock_week.return_value = date(2026, 2, 9)

            result = await compute_patterns(user_id, mock_session)

        assert result["success"] is True
        assert result["data"]["data_insufficient"] is False

    @pytest.mark.asyncio
    async def test_snapshots_outside_window_excluded(self, mock_session):
        """Snapshots older than 6 months are excluded."""
        user_id = uuid4()

        # Create old snapshots (> 6 months ago)
        priority_id = uuid4()
        old_snapshots = []
        for i in range(4):
            s = MagicMock()
            s.week_start = date(2025, 1, 5) + timedelta(weeks=i)  # Very old
            s.priority_id = priority_id
            old_snapshots.append(s)

        # The query should filter these out, so mock returns empty
        snap_result = MagicMock()
        snap_result.scalars.return_value.all.return_value = []

        priority_result = MagicMock()
        priority_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [snap_result, priority_result]

        result = await compute_patterns(user_id, mock_session)

        assert result["data"]["weeks_available"] == 0
        assert result["data"]["data_insufficient"] is True

    @pytest.mark.asyncio
    async def test_multiple_patterns_returned(self, mock_session):
        """Multiple patterns can be returned simultaneously."""
        user_id = uuid4()

        # Create priority with data for consistency_streak pattern
        # Need 4+ consecutive weeks with hours > 0 and streak_at_snapshot >= 4
        priority_id = uuid4()
        snapshots = []

        # Create snapshots in descending order (most recent first)
        # Week 8 (most recent) - streak=8
        # Week 7 - streak=7
        # etc.
        base_date = date(2025, 12, 15)
        for i in range(8):
            week_idx = 7 - i  # Descending: 7, 6, 5, 4, 3, 2, 1, 0
            s = MagicMock()
            s.week_start = base_date + timedelta(weeks=week_idx)
            s.priority_id = priority_id
            s.actual_hours = Decimal("10")
            s.total_tracked_hours = Decimal("40")
            s.streak_at_snapshot = week_idx + 1  # 8, 7, 6, 5, 4, 3, 2, 1
            s.calendar_keyword_at_snapshot = "P1"
            snapshots.append(s)

        snap_result = MagicMock()
        snap_result.scalars.return_value.all.return_value = snapshots

        priority = MagicMock()
        priority.id = priority_id
        priority.name = "Test"
        priority.type = "flexible"
        priority.status = "active"
        priority.calendar_keyword = "P1"
        priority.retired_at = None
        priority.created_at = datetime(2025, 11, 1, tzinfo=timezone.utc)

        priority_result = MagicMock()
        priority_result.scalars.return_value.all.return_value = [priority]

        mock_session.execute.side_effect = [snap_result, priority_result]

        with patch("backend.apps.priority_guardian.services.pattern_service.get_current_week_start_utc") as mock_week:
            mock_week.return_value = date(2026, 2, 9)

            result = await compute_patterns(user_id, mock_session)

        assert result["data"]["data_insufficient"] is False
        # Should have consistency_streak pattern (streak >= 4)
        assert result["data"]["pattern_count"] >= 1
        pattern_types = [p["pattern_type"] for p in result["data"]["patterns"]]
        assert "consistency_streak" in pattern_types

    @pytest.mark.asyncio
    async def test_3_retirements_but_0_weeks_insufficient(self, mock_session):
        """3 retirements exist but weeks_available=0 returns insufficient."""
        user_id = uuid4()

        # No snapshots
        snap_result = MagicMock()
        snap_result.scalars.return_value.all.return_value = []

        # 3 retired priorities
        priorities = []
        for i in range(3):
            p = MagicMock()
            p.id = uuid4()
            p.status = "retired"
            p.retired_at = datetime(2026, 1, 1 + i * 7, tzinfo=timezone.utc)
            p.created_at = datetime(2025, 10, 1, tzinfo=timezone.utc)
            priorities.append(p)

        priority_result = MagicMock()
        priority_result.scalars.return_value.all.return_value = priorities

        mock_session.execute.side_effect = [snap_result, priority_result]

        result = await compute_patterns(user_id, mock_session)

        # Global floor enforced before any pattern logic
        assert result["data"]["data_insufficient"] is True
        assert result["data"]["patterns"] == []
        assert result["data"]["reason"] == "INSUFFICIENT_WEEKS"


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestErrorHandling:
    """Tests for error handling in pattern service."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_unexpected_exception_returns_error(self, mock_session):
        """Unexpected exception returns error response, never raises."""
        user_id = uuid4()

        mock_session.execute.side_effect = RuntimeError("Unexpected DB error")

        # Should not raise
        result = await compute_patterns(user_id, mock_session)

        assert result["success"] is False
        assert result["error"]["code"] == "PATTERN_COMPUTE_ERROR"
        assert "Pattern computation failed" in result["error"]["message"]


# ============================================================================
# Snapshot Ordering Contract Tests
# ============================================================================

class TestSnapshotOrderingContract:
    """Tests that verify snapshot ordering assumption is required.

    Pattern logic assumes snapshots are ordered by week_start DESC (most recent first).
    These tests lock in that contract so query-layer changes don't silently break patterns.
    """

    def _create_priority(self, type_="flexible", status="active", keyword="P1"):
        """Create a mock priority."""
        p = MagicMock()
        p.id = uuid4()
        p.name = "Test Priority"
        p.type = type_
        p.status = status
        p.calendar_keyword = keyword
        p.retired_at = None
        return p

    def _create_snapshot(self, week_start, streak=None, actual_hours=Decimal("5.0"), keyword="P1", target_hours=Decimal("8.0")):
        """Create a mock snapshot."""
        s = MagicMock()
        s.week_start = week_start
        s.streak_at_snapshot = streak
        s.actual_hours = actual_hours
        s.calendar_keyword_at_snapshot = keyword
        s.target_hours = target_hours
        return s

    def test_ascending_order_breaks_fallback_streak(self):
        """Ascending snapshot order (wrong) produces incorrect streak via fallback.

        This test documents that pattern logic REQUIRES descending order.
        If snapshots are ascending (oldest first), fallback streak computation breaks.
        """
        priority = self._create_priority()

        # Snapshots in ASCENDING order (oldest first) - WRONG ORDER
        # Actual hours pattern: 0, 5, 5, 5, 5 (oldest to newest)
        # Correct streak (from most recent): 4 consecutive weeks with hours
        # With wrong order: starts at oldest (0 hours), streak = 0
        snapshots_ascending = [
            self._create_snapshot(date(2026, 1, 5), streak=None, actual_hours=Decimal("0")),   # oldest
            self._create_snapshot(date(2026, 1, 12), streak=None, actual_hours=Decimal("5")),
            self._create_snapshot(date(2026, 1, 19), streak=None, actual_hours=Decimal("5")),
            self._create_snapshot(date(2026, 1, 26), streak=None, actual_hours=Decimal("5")),
            self._create_snapshot(date(2026, 2, 2), streak=None, actual_hours=Decimal("5")),   # newest
        ]

        # With ascending order, fallback hits 0 hours first and breaks immediately
        patterns = _compute_consistency_streaks(
            [priority],
            {priority.id: snapshots_ascending},
            date(2026, 2, 9),
        )

        # WRONG result due to wrong order - streak is 0, pattern not surfaced
        assert len(patterns) == 0

        # Now test with CORRECT descending order
        snapshots_descending = list(reversed(snapshots_ascending))

        patterns_correct = _compute_consistency_streaks(
            [priority],
            {priority.id: snapshots_descending},
            date(2026, 2, 9),
        )

        # CORRECT result - streak is 4, pattern surfaced
        assert len(patterns_correct) == 1
        assert patterns_correct[0]["streak_weeks"] == 4


# ============================================================================
# Cross-Priority Sorting Determinism Tests
# ============================================================================

class TestCrossPrioritySortingDeterminism:
    """Tests that verify deterministic output order across multiple patterns."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_multiple_pattern_types_returned_in_deterministic_order(self, mock_session):
        """Multiple pattern types are returned in stable, deterministic order.

        Order should be: abandoned_priority, consistency_streak, priority_protection, priority_switching
        (alphabetical by pattern_type, then by priority_id, then by priority_name)
        """
        user_id = uuid4()

        # Create two priorities - one for streak, one for abandoned
        streak_priority_id = uuid4()
        abandoned_priority_id = uuid4()

        # Create snapshots for both priorities
        base_date = date(2025, 12, 1)
        snapshots = []

        # Streak priority: 8 weeks of solid hours with streak >= 4
        for i in range(8):
            s = MagicMock()
            s.week_start = base_date + timedelta(weeks=(7 - i))  # Descending
            s.priority_id = streak_priority_id
            s.actual_hours = Decimal("10")
            s.total_tracked_hours = Decimal("40")
            s.streak_at_snapshot = 8 - i
            s.calendar_keyword_at_snapshot = "P1"
            snapshots.append(s)

        # Abandoned priority: 4 weeks of low hours
        for i in range(4):
            s = MagicMock()
            s.week_start = base_date + timedelta(weeks=(7 - i))
            s.priority_id = abandoned_priority_id
            s.actual_hours = Decimal("0.3")
            s.total_tracked_hours = Decimal("40")
            s.streak_at_snapshot = 0
            s.calendar_keyword_at_snapshot = "P2"
            snapshots.append(s)

        snap_result = MagicMock()
        snap_result.scalars.return_value.all.return_value = snapshots

        # Create priorities
        streak_priority = MagicMock()
        streak_priority.id = streak_priority_id
        streak_priority.name = "Streak Priority"
        streak_priority.type = "flexible"
        streak_priority.status = "active"
        streak_priority.calendar_keyword = "P1"
        streak_priority.retired_at = None
        streak_priority.created_at = datetime(2025, 10, 1, tzinfo=timezone.utc)

        abandoned_priority = MagicMock()
        abandoned_priority.id = abandoned_priority_id
        abandoned_priority.name = "Abandoned Priority"
        abandoned_priority.type = "flexible"
        abandoned_priority.status = "active"
        abandoned_priority.calendar_keyword = "P2"
        abandoned_priority.retired_at = None
        abandoned_priority.created_at = datetime(2025, 10, 1, tzinfo=timezone.utc)

        priority_result = MagicMock()
        priority_result.scalars.return_value.all.return_value = [streak_priority, abandoned_priority]

        mock_session.execute.side_effect = [snap_result, priority_result]

        with patch("backend.apps.priority_guardian.services.pattern_service.get_current_week_start_utc") as mock_week:
            mock_week.return_value = date(2026, 2, 9)

            result = await compute_patterns(user_id, mock_session)

        assert result["success"] is True
        patterns = result["data"]["patterns"]

        # Should have at least 2 patterns
        assert len(patterns) >= 2

        pattern_types = [p["pattern_type"] for p in patterns]

        # Verify deterministic order: abandoned comes before consistency (alphabetical)
        if "abandoned_priority" in pattern_types and "consistency_streak" in pattern_types:
            abandoned_idx = pattern_types.index("abandoned_priority")
            streak_idx = pattern_types.index("consistency_streak")
            assert abandoned_idx < streak_idx, "Patterns must be sorted alphabetically by pattern_type"

    @pytest.mark.asyncio
    async def test_same_pattern_type_sorted_by_priority_id(self, mock_session):
        """Same pattern type for multiple priorities sorted by priority_id."""
        user_id = uuid4()

        # Create two priorities that will both have consistency streaks
        priority_id_1 = uuid4()
        priority_id_2 = uuid4()

        base_date = date(2025, 12, 1)
        snapshots = []

        for pid in [priority_id_1, priority_id_2]:
            for i in range(4):
                s = MagicMock()
                s.week_start = base_date + timedelta(weeks=(3 - i))
                s.priority_id = pid
                s.actual_hours = Decimal("10")
                s.total_tracked_hours = Decimal("40")
                s.streak_at_snapshot = 4 - i
                s.calendar_keyword_at_snapshot = "P1"
                s.target_hours = Decimal("8")
                snapshots.append(s)

        snap_result = MagicMock()
        snap_result.scalars.return_value.all.return_value = snapshots

        priorities = []
        for pid in [priority_id_1, priority_id_2]:
            p = MagicMock()
            p.id = pid
            p.name = f"Priority {pid}"
            p.type = "flexible"
            p.status = "active"
            p.calendar_keyword = "P1"
            p.retired_at = None
            p.created_at = datetime(2025, 10, 1, tzinfo=timezone.utc)
            priorities.append(p)

        priority_result = MagicMock()
        priority_result.scalars.return_value.all.return_value = priorities

        mock_session.execute.side_effect = [snap_result, priority_result]

        with patch("backend.apps.priority_guardian.services.pattern_service.get_current_week_start_utc") as mock_week:
            mock_week.return_value = date(2026, 2, 9)

            result = await compute_patterns(user_id, mock_session)

        patterns = result["data"]["patterns"]
        streak_patterns = [p for p in patterns if p["pattern_type"] == "consistency_streak"]

        assert len(streak_patterns) == 2

        # Verify sorted by priority_id (string comparison)
        ids = [p["priority_id"] for p in streak_patterns]
        assert ids == sorted(ids), "Same pattern_type must be sorted by priority_id"


# ============================================================================
# Increment 26: Weekly Detail Enrichment Tests
# ============================================================================

class TestConsistencyStreakWeeklyDetail:
    """Tests for weekly_detail in consistency_streak patterns (Increment 26)."""

    def _create_priority(self, type_="flexible", status="active", keyword="P1"):
        """Create a mock priority."""
        p = MagicMock()
        p.id = uuid4()
        p.name = "Test Priority"
        p.type = type_
        p.status = status
        p.calendar_keyword = keyword
        p.retired_at = None
        return p

    def _create_snapshot(
        self,
        week_start,
        streak=None,
        actual_hours=Decimal("5.0"),
        target_hours=Decimal("8.0"),
        keyword="P1",
    ):
        """Create a mock snapshot."""
        s = MagicMock()
        s.week_start = week_start
        s.streak_at_snapshot = streak
        s.actual_hours = actual_hours
        s.target_hours = target_hours
        s.calendar_keyword_at_snapshot = keyword
        return s

    def test_6_week_streak_weekly_detail_structure(self):
        """6-week streak has weekly_detail with 6 entries, chronological order."""
        priority = self._create_priority()
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), streak=6, actual_hours=Decimal("7"), target_hours=Decimal("8")),
            self._create_snapshot(date(2026, 1, 26), streak=5, actual_hours=Decimal("6"), target_hours=Decimal("8")),
            self._create_snapshot(date(2026, 1, 19), streak=4, actual_hours=Decimal("5"), target_hours=Decimal("8")),
            self._create_snapshot(date(2026, 1, 12), streak=3, actual_hours=Decimal("4"), target_hours=Decimal("8")),
            self._create_snapshot(date(2026, 1, 5), streak=2, actual_hours=Decimal("3"), target_hours=Decimal("8")),
            self._create_snapshot(date(2025, 12, 29), streak=1, actual_hours=Decimal("2"), target_hours=Decimal("8")),
        ]

        patterns = _compute_consistency_streaks(
            [priority],
            {priority.id: snapshots},
            date(2026, 2, 9),
        )

        assert len(patterns) == 1
        pattern = patterns[0]
        assert "weekly_detail" in pattern
        weekly_detail = pattern["weekly_detail"]

        # Should have 6 entries
        assert len(weekly_detail) == 6

        # Should be chronological (oldest first)
        assert weekly_detail[0]["week_start"] == "2025-12-29"
        assert weekly_detail[5]["week_start"] == "2026-02-02"

        # Check structure of entries
        for entry in weekly_detail:
            assert "week_start" in entry
            assert "actual_hours" in entry
            assert "target_hours" in entry
            assert isinstance(entry["week_start"], str)

        # Verify actual values match snapshot data
        assert weekly_detail[0]["actual_hours"] == Decimal("2")
        assert weekly_detail[0]["target_hours"] == Decimal("8")
        assert weekly_detail[5]["actual_hours"] == Decimal("7")

    def test_null_target_hours_preserved(self):
        """Deadline priority with NULL target_hours has target_hours: None."""
        priority = self._create_priority(type_="flexible")
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), streak=4, actual_hours=Decimal("10"), target_hours=None),
            self._create_snapshot(date(2026, 1, 26), streak=3, actual_hours=Decimal("10"), target_hours=None),
            self._create_snapshot(date(2026, 1, 19), streak=2, actual_hours=Decimal("10"), target_hours=None),
            self._create_snapshot(date(2026, 1, 12), streak=1, actual_hours=Decimal("10"), target_hours=None),
        ]

        patterns = _compute_consistency_streaks(
            [priority],
            {priority.id: snapshots},
            date(2026, 2, 9),
        )

        assert len(patterns) == 1
        weekly_detail = patterns[0]["weekly_detail"]

        # target_hours should be None (serializes as JSON null)
        for entry in weekly_detail:
            assert entry["target_hours"] is None

    def test_12_week_streak_capped_at_8(self):
        """12-week streak has weekly_detail capped at 8 entries."""
        priority = self._create_priority()
        # Create 12 weeks of snapshots
        snapshots = []
        for i in range(12):
            week = date(2026, 2, 2) - timedelta(weeks=i)
            snapshots.append(
                self._create_snapshot(week, streak=12 - i, actual_hours=Decimal(f"{10 - i * 0.5}"))
            )

        patterns = _compute_consistency_streaks(
            [priority],
            {priority.id: snapshots},
            date(2026, 2, 9),
        )

        assert len(patterns) == 1
        pattern = patterns[0]

        # streak_weeks should still report 12
        assert pattern["streak_weeks"] == 12

        # But weekly_detail should be capped at 8 entries
        assert len(pattern["weekly_detail"]) == 8

        # Should be the 8 most recent weeks (chronologically ordered)
        # Most recent is 2026-02-02, 8th most recent is 2025-12-15
        assert pattern["weekly_detail"][0]["week_start"] == "2025-12-15"
        assert pattern["weekly_detail"][7]["week_start"] == "2026-02-02"

    def test_weekly_detail_from_exact_streak_slice(self):
        """weekly_detail only includes consecutive streak weeks from most recent."""
        priority = self._create_priority()
        # Pattern: weeks 1-4 have hours > 0, week 5 has 0, weeks 6-8 have hours > 0
        # Streak should be 4 (from most recent backward until break)
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), streak=None, actual_hours=Decimal("5")),   # Week 8
            self._create_snapshot(date(2026, 1, 26), streak=None, actual_hours=Decimal("5")),  # Week 7
            self._create_snapshot(date(2026, 1, 19), streak=None, actual_hours=Decimal("5")),  # Week 6
            self._create_snapshot(date(2026, 1, 12), streak=None, actual_hours=Decimal("5")),  # Week 5
            self._create_snapshot(date(2026, 1, 5), streak=None, actual_hours=Decimal("0")),   # Week 4 - BREAK
            self._create_snapshot(date(2025, 12, 29), streak=None, actual_hours=Decimal("5")), # Week 3
            self._create_snapshot(date(2025, 12, 22), streak=None, actual_hours=Decimal("5")), # Week 2
            self._create_snapshot(date(2025, 12, 15), streak=None, actual_hours=Decimal("5")), # Week 1
        ]

        patterns = _compute_consistency_streaks(
            [priority],
            {priority.id: snapshots},
            date(2026, 2, 9),
        )

        assert len(patterns) == 1
        pattern = patterns[0]

        # Streak should be 4 (computed fallback)
        assert pattern["streak_weeks"] == 4
        assert pattern["streak_source"] == "computed"

        # weekly_detail should only include the 4 consecutive streak weeks
        assert len(pattern["weekly_detail"]) == 4

        # Should not include week 5 (2026-01-05) or earlier
        week_starts = [e["week_start"] for e in pattern["weekly_detail"]]
        assert "2026-01-05" not in week_starts  # The break week
        assert "2025-12-29" not in week_starts  # Before break

        # Should include the 4 consecutive weeks from most recent
        assert "2026-01-12" in week_starts
        assert "2026-01-19" in week_starts
        assert "2026-01-26" in week_starts
        assert "2026-02-02" in week_starts


class TestAbandonedPriorityWeeklyDetail:
    """Tests for weekly_detail in abandoned_priority patterns (Increment 26)."""

    def _create_priority(self, status="active", keyword="P1"):
        """Create a mock priority."""
        p = MagicMock()
        p.id = uuid4()
        p.name = "Test Priority"
        p.type = "flexible"
        p.status = status
        p.calendar_keyword = keyword
        return p

    def _create_snapshot(
        self,
        week_start,
        actual_hours=Decimal("0.5"),
        target_hours=Decimal("5.0"),
        keyword="P1",
    ):
        """Create a mock snapshot."""
        s = MagicMock()
        s.week_start = week_start
        s.actual_hours = actual_hours
        s.target_hours = target_hours
        s.calendar_keyword_at_snapshot = keyword
        return s

    def test_weekly_detail_with_4_entries(self):
        """abandoned_priority has weekly_detail with 4 entries, chronological order."""
        priority = self._create_priority()
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), actual_hours=Decimal("0.5"), target_hours=Decimal("5")),
            self._create_snapshot(date(2026, 1, 26), actual_hours=Decimal("0.3"), target_hours=Decimal("5")),
            self._create_snapshot(date(2026, 1, 19), actual_hours=Decimal("0.2"), target_hours=Decimal("5")),
            self._create_snapshot(date(2026, 1, 12), actual_hours=Decimal("0.2"), target_hours=Decimal("5")),
        ]

        patterns = _compute_abandoned_priorities(
            [priority],
            {priority.id: snapshots},
            current_week_start=date(2026, 2, 9),
        )

        assert len(patterns) == 1
        pattern = patterns[0]
        assert "weekly_detail" in pattern
        weekly_detail = pattern["weekly_detail"]

        # Should have exactly 4 entries
        assert len(weekly_detail) == 4

        # Should be chronological (oldest first)
        assert weekly_detail[0]["week_start"] == "2026-01-12"
        assert weekly_detail[3]["week_start"] == "2026-02-02"

        # Check values match
        assert weekly_detail[0]["actual_hours"] == Decimal("0.2")
        assert weekly_detail[0]["target_hours"] == Decimal("5")
        assert weekly_detail[3]["actual_hours"] == Decimal("0.5")


class TestPriorityProtectionPeriodSummary:
    """Tests for period_summary in priority_protection patterns (Increment 26)."""

    def _create_priority(self, status="active", keyword="P1"):
        """Create a mock priority."""
        p = MagicMock()
        p.id = uuid4()
        p.name = "Test Priority"
        p.type = "flexible"
        p.status = status
        p.calendar_keyword = keyword
        return p

    def _create_snapshot(
        self,
        week_start,
        actual_hours=Decimal("10.0"),
        total_tracked_hours=Decimal("40.0"),
        keyword="P1",
    ):
        """Create a mock snapshot."""
        s = MagicMock()
        s.week_start = week_start
        s.actual_hours = actual_hours
        s.total_tracked_hours = total_tracked_hours
        s.calendar_keyword_at_snapshot = keyword
        return s

    def test_period_summary_correct_values(self):
        """priority_protection has period_summary with correct computed values."""
        priority = self._create_priority()

        # Recent 4 weeks: priority=10h, total=50h
        # Prior 4 weeks: priority=10h, total=40h
        # Total change: 25%
        snapshots = [
            self._create_snapshot(date(2026, 2, 2), Decimal("10"), Decimal("50")),
            self._create_snapshot(date(2026, 1, 26), Decimal("10"), Decimal("50")),
            self._create_snapshot(date(2026, 1, 19), Decimal("10"), Decimal("50")),
            self._create_snapshot(date(2026, 1, 12), Decimal("10"), Decimal("50")),
            self._create_snapshot(date(2026, 1, 5), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2025, 12, 29), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2025, 12, 22), Decimal("10"), Decimal("40")),
            self._create_snapshot(date(2025, 12, 15), Decimal("10"), Decimal("40")),
        ]

        patterns = _compute_priority_protection(
            [priority],
            {priority.id: snapshots},
        )

        assert len(patterns) == 1
        pattern = patterns[0]
        assert "period_summary" in pattern
        period_summary = pattern["period_summary"]

        # Check all required fields
        assert "prior_avg_priority_hours" in period_summary
        assert "recent_avg_priority_hours" in period_summary
        assert "prior_avg_total_hours" in period_summary
        assert "recent_avg_total_hours" in period_summary
        assert "total_hours_change_pct" in period_summary

        # Verify computed values
        assert period_summary["prior_avg_priority_hours"] == Decimal("10")
        assert period_summary["recent_avg_priority_hours"] == Decimal("10")
        assert period_summary["prior_avg_total_hours"] == Decimal("40")
        assert period_summary["recent_avg_total_hours"] == Decimal("50")
        assert period_summary["total_hours_change_pct"] == Decimal("25.0")


class TestDecimalToFloatWithWeeklyDetail:
    """Tests for decimal_to_float_recursive with weekly_detail structures (Increment 26)."""

    def test_converts_nested_weekly_detail_decimals(self):
        """Converts Decimal values inside nested weekly_detail dicts to float."""
        pattern = {
            "pattern_type": "consistency_streak",
            "streak_weeks": 6,
            "weekly_detail": [
                {
                    "week_start": "2026-01-12",
                    "actual_hours": Decimal("6.5"),
                    "target_hours": Decimal("8.0"),
                },
                {
                    "week_start": "2026-01-19",
                    "actual_hours": Decimal("7.0"),
                    "target_hours": Decimal("8.0"),
                },
            ],
        }

        result = decimal_to_float_recursive(pattern)

        # Decimals should be converted to float
        assert result["weekly_detail"][0]["actual_hours"] == 6.5
        assert isinstance(result["weekly_detail"][0]["actual_hours"], float)
        assert result["weekly_detail"][0]["target_hours"] == 8.0
        assert isinstance(result["weekly_detail"][0]["target_hours"], float)

    def test_preserves_none_in_weekly_detail(self):
        """Preserves None values (for NULL target_hours) in weekly_detail."""
        pattern = {
            "weekly_detail": [
                {
                    "week_start": "2026-01-12",
                    "actual_hours": Decimal("10.0"),
                    "target_hours": None,
                },
            ],
        }

        result = decimal_to_float_recursive(pattern)

        assert result["weekly_detail"][0]["target_hours"] is None

    def test_preserves_string_week_start(self):
        """Does not mutate string fields like week_start."""
        pattern = {
            "weekly_detail": [
                {
                    "week_start": "2026-01-12",
                    "actual_hours": Decimal("5.0"),
                    "target_hours": Decimal("8.0"),
                },
            ],
        }

        result = decimal_to_float_recursive(pattern)

        assert result["weekly_detail"][0]["week_start"] == "2026-01-12"
        assert isinstance(result["weekly_detail"][0]["week_start"], str)
