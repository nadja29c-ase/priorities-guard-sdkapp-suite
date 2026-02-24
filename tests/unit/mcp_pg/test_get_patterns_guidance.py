"""
Unit tests for get_patterns assistant_guidance composition (Increment 25/26/28).

Tests per-pattern guidance composition for consistency_streak, abandoned_priority,
priority_switching, and priority_protection patterns.
"""

import pytest

from mcp_server.priority_guardian.tools.get_patterns import (
    _build_assistant_guidance,
    _get_switching_guidance,
    GUIDANCE_COMMON,
    GUIDANCE_CONSISTENCY_STREAK,
    GUIDANCE_ABANDONED_PRIORITY,
    GUIDANCE_PRIORITY_SWITCHING_NO_CRITERIA,
    GUIDANCE_PRIORITY_SWITCHING_INCOMPLETE,
    GUIDANCE_PRIORITY_PROTECTION,
    GUIDANCE_NO_PATTERNS,
    GUIDANCE_INSUFFICIENT_DATA_TEMPLATE,
)


class TestPerPatternGuidance:
    """Tests for per-pattern guidance composition."""

    def test_single_pattern_consistency_streak(self):
        """Single consistency_streak pattern includes COMMON + CONSISTENCY_STREAK only."""
        data = {
            "reason": "PATTERNS_FOUND",
            "patterns": [
                {"pattern_type": "consistency_streak", "priority_id": "p1"}
            ],
        }

        guidance = _build_assistant_guidance(data)

        # Should contain common guidance
        assert GUIDANCE_COMMON in guidance
        # Should contain consistency streak guidance with inline phrasing
        assert "When narrating consistency streak patterns:" in guidance
        assert "dashboard already shows the streak count" in guidance
        # Should NOT contain other pattern guidance
        assert "When narrating low-investment priority patterns:" not in guidance
        assert "When narrating priority switching patterns:" not in guidance
        assert "When narrating priority protection patterns:" not in guidance
        assert "Ask what the user wants to do about it" not in guidance  # abandoned
        assert "intentional pivoting" not in guidance  # switching
        assert "despite growing calendar pressure" not in guidance  # protection

    def test_all_four_patterns_present(self):
        """All 4 patterns present includes COMMON + all 4 per-pattern guidance blocks."""
        data = {
            "reason": "PATTERNS_FOUND",
            "patterns": [
                {"pattern_type": "consistency_streak", "priority_id": "p1"},
                {"pattern_type": "abandoned_priority", "priority_id": "p2"},
                {"pattern_type": "priority_switching", "retired_priorities": []},
                {"pattern_type": "priority_protection", "priority_id": "p3"},
            ],
        }

        guidance = _build_assistant_guidance(data)

        # Should contain common guidance
        assert GUIDANCE_COMMON in guidance
        # Should contain all 4 pattern guidance blocks with inline phrasing
        assert "When narrating consistency streak patterns:" in guidance
        assert "When narrating low-investment priority patterns:" in guidance
        assert "When narrating priority switching patterns:" in guidance
        assert "When narrating priority protection patterns:" in guidance
        # Verify actual guidance content is present
        assert "dashboard already shows the streak count" in guidance
        assert "Ask what the user wants to do about it" in guidance
        assert "intentional pivoting" in guidance
        assert "despite growing calendar pressure" in guidance

    def test_no_patterns_reason(self):
        """NO_PATTERNS reason returns GUIDANCE_NO_PATTERNS, no per-pattern guidance."""
        data = {
            "reason": "NO_PATTERNS",
            "patterns": [],
        }

        guidance = _build_assistant_guidance(data)

        assert guidance == GUIDANCE_NO_PATTERNS
        # Should NOT contain common or per-pattern guidance
        assert GUIDANCE_COMMON not in guidance
        assert "When narrating consistency streak patterns:" not in guidance
        assert "When narrating low-investment priority patterns:" not in guidance

    def test_insufficient_weeks_reason(self):
        """INSUFFICIENT_WEEKS reason returns templated guidance, no per-pattern guidance."""
        data = {
            "reason": "INSUFFICIENT_WEEKS",
            "weeks_available": 2,
            "patterns": [],
        }

        guidance = _build_assistant_guidance(data)

        assert "2 weeks of tracking data" in guidance
        assert "at least 4 completed weeks" in guidance
        # Should NOT contain common or per-pattern guidance
        assert GUIDANCE_COMMON not in guidance
        assert "When narrating consistency streak patterns:" not in guidance

    def test_unknown_pattern_type_skipped_gracefully(self):
        """Unknown pattern_type is skipped, other patterns still get guidance."""
        data = {
            "reason": "PATTERNS_FOUND",
            "patterns": [
                {"pattern_type": "future_pattern_v2", "priority_id": "p1"},  # unknown
                {"pattern_type": "consistency_streak", "priority_id": "p2"},  # known
            ],
        }

        guidance = _build_assistant_guidance(data)

        # Should contain common guidance
        assert GUIDANCE_COMMON in guidance
        # Should contain consistency streak guidance
        assert "When narrating consistency streak patterns:" in guidance
        assert "dashboard already shows the streak count" in guidance
        # Should NOT contain the unknown pattern type as a label
        assert "When narrating future_pattern_v2 patterns:" not in guidance
        assert "future_pattern_v2" not in guidance


class TestGuidanceSeparation:
    """Tests for proper separation between guidance blocks."""

    def test_guidance_blocks_separated_by_double_newline(self):
        """Guidance blocks are joined with double newline separators."""
        data = {
            "reason": "PATTERNS_FOUND",
            "patterns": [
                {"pattern_type": "consistency_streak", "priority_id": "p1"},
                {"pattern_type": "priority_protection", "priority_id": "p2"},
            ],
        }

        guidance = _build_assistant_guidance(data)

        # Should have double newline between blocks
        assert "\n\nWhen narrating consistency streak patterns:" in guidance
        assert "\n\nWhen narrating priority protection patterns:" in guidance

    def test_empty_patterns_list_returns_common_only(self):
        """PATTERNS_FOUND with empty patterns list returns only GUIDANCE_COMMON."""
        data = {
            "reason": "PATTERNS_FOUND",
            "patterns": [],
        }

        guidance = _build_assistant_guidance(data)

        # Should just be common guidance with no pattern blocks
        assert guidance == GUIDANCE_COMMON


class TestCanonicalOrder:
    """Tests for canonical order iteration (increment_26)."""

    def test_all_patterns_in_canonical_order(self):
        """All 4 patterns appear in canonical order regardless of input order."""
        # Input in reverse order
        data = {
            "reason": "PATTERNS_FOUND",
            "patterns": [
                {"pattern_type": "priority_protection", "priority_id": "p4"},
                {"pattern_type": "priority_switching", "retired_priorities": []},
                {"pattern_type": "abandoned_priority", "priority_id": "p2"},
                {"pattern_type": "consistency_streak", "priority_id": "p1"},
            ],
        }

        guidance = _build_assistant_guidance(data)

        # Find positions of each pattern guidance in the output
        streak_pos = guidance.find("When narrating consistency streak patterns:")
        abandoned_pos = guidance.find("When narrating low-investment priority patterns:")
        switching_pos = guidance.find("When narrating priority switching patterns:")
        protection_pos = guidance.find("When narrating priority protection patterns:")

        # All should be present
        assert streak_pos > 0
        assert abandoned_pos > 0
        assert switching_pos > 0
        assert protection_pos > 0

        # Verify canonical order: streak < abandoned < switching < protection
        assert streak_pos < abandoned_pos < switching_pos < protection_pos


class TestSwitchingPatternGuidance:
    """Tests for priority switching guidance variants (increment_28)."""

    def test_both_variants_contain_reflection_questions(self):
        """Both switching guidance variants contain the reflection questions."""
        # Check NO_CRITERIA variant
        assert "hard evidence that each pivot was more promising" in GUIDANCE_PRIORITY_SWITCHING_NO_CRITERIA
        assert "gut call" in GUIDANCE_PRIORITY_SWITCHING_NO_CRITERIA
        assert "frustration, low energy, or feeling stuck" in GUIDANCE_PRIORITY_SWITCHING_NO_CRITERIA

        # Check INCOMPLETE variant
        assert "hard evidence that each pivot was more promising" in GUIDANCE_PRIORITY_SWITCHING_INCOMPLETE
        assert "gut call" in GUIDANCE_PRIORITY_SWITCHING_INCOMPLETE
        assert "frustration, low energy, or feeling stuck" in GUIDANCE_PRIORITY_SWITCHING_INCOMPLETE

    def test_no_criteria_variant_mentions_no_goals_defined(self):
        """NO_CRITERIA variant mentions goals/deliverables not defined."""
        assert "without any goals or deliverables defined" in GUIDANCE_PRIORITY_SWITCHING_NO_CRITERIA
        assert "no clear success criteria" in GUIDANCE_PRIORITY_SWITCHING_NO_CRITERIA

    def test_incomplete_variant_mentions_incomplete_outcomes(self):
        """INCOMPLETE variant mentions incomplete goals/deliverables."""
        assert "goals or deliverables still incomplete" in GUIDANCE_PRIORITY_SWITCHING_INCOMPLETE
        assert "specific incomplete goals or deliverables by name" in GUIDANCE_PRIORITY_SWITCHING_INCOMPLETE

    def test_switching_guidance_inline_phrasing_in_canonical_order(self):
        """Switching guidance uses inline phrasing consistent with canonical order."""
        data = {
            "reason": "PATTERNS_FOUND",
            "patterns": [{"pattern_type": "priority_switching", "retired_priorities": []}],
        }

        guidance = _build_assistant_guidance(data)

        # Should use inline phrasing "When narrating priority switching patterns:"
        assert "When narrating priority switching patterns:" in guidance

    def test_description_uses_recent_months_not_hardcoded(self):
        """DESCRIPTION uses 'recent months' not a hardcoded month count for switching."""
        from mcp_server.priority_guardian.tools.get_patterns import DESCRIPTION

        # Should NOT contain hardcoded month counts for switching
        # The description mentions "priority switching frequency" without a specific window
        assert "priority switching frequency" in DESCRIPTION
        # Should not hardcode "3 months" or "6 months" for the switching pattern
        # (Note: "4 weeks" is for data requirements, not switching window)
        assert "3 months" not in DESCRIPTION.lower()
        assert "6 months" not in DESCRIPTION.lower()


class TestSwitchingGuidanceSelection:
    """Tests for dynamic switching guidance selection based on retired_priorities data."""

    def test_all_no_criteria_selects_no_criteria_variant(self):
        """All retired priorities with goals_total=0 selects NO_CRITERIA variant."""
        patterns = [
            {
                "pattern_type": "priority_switching",
                "retired_priorities": [
                    {"name": "Priority A", "type": "flexible", "goals_achieved": 0, "goals_total": 0},
                    {"name": "Priority B", "type": "flexible", "goals_achieved": 0, "goals_total": 0},
                    {"name": "Priority C", "type": "deadline", "deliverables_done": 0, "deliverables_total": 0},
                ],
            }
        ]

        guidance = _get_switching_guidance(patterns)

        assert guidance == GUIDANCE_PRIORITY_SWITCHING_NO_CRITERIA

    def test_some_with_criteria_selects_incomplete_variant(self):
        """Mixed priorities (some with criteria) selects INCOMPLETE variant."""
        patterns = [
            {
                "pattern_type": "priority_switching",
                "retired_priorities": [
                    {"name": "Priority A", "type": "flexible", "goals_achieved": 1, "goals_total": 3},  # Has criteria
                    {"name": "Priority B", "type": "flexible", "goals_achieved": 0, "goals_total": 0},  # No criteria
                ],
            }
        ]

        guidance = _get_switching_guidance(patterns)

        assert guidance == GUIDANCE_PRIORITY_SWITCHING_INCOMPLETE

    def test_all_with_criteria_selects_incomplete_variant(self):
        """All retired priorities with criteria selects INCOMPLETE variant."""
        patterns = [
            {
                "pattern_type": "priority_switching",
                "retired_priorities": [
                    {"name": "Priority A", "type": "flexible", "goals_achieved": 1, "goals_total": 3},
                    {"name": "Priority B", "type": "deadline", "deliverables_done": 2, "deliverables_total": 5},
                ],
            }
        ]

        guidance = _get_switching_guidance(patterns)

        assert guidance == GUIDANCE_PRIORITY_SWITCHING_INCOMPLETE

    def test_empty_retired_priorities_selects_no_criteria_variant(self):
        """Empty retired_priorities list selects NO_CRITERIA variant."""
        patterns = [
            {
                "pattern_type": "priority_switching",
                "retired_priorities": [],
            }
        ]

        guidance = _get_switching_guidance(patterns)

        assert guidance == GUIDANCE_PRIORITY_SWITCHING_NO_CRITERIA

    def test_missing_retired_priorities_selects_no_criteria_variant(self):
        """Missing retired_priorities key selects NO_CRITERIA variant."""
        patterns = [
            {
                "pattern_type": "priority_switching",
            }
        ]

        guidance = _get_switching_guidance(patterns)

        assert guidance == GUIDANCE_PRIORITY_SWITCHING_NO_CRITERIA

    def test_no_switching_pattern_returns_incomplete_fallback(self):
        """No switching pattern in list returns INCOMPLETE as fallback."""
        patterns = [
            {"pattern_type": "consistency_streak", "priority_id": "p1"},
        ]

        guidance = _get_switching_guidance(patterns)

        assert guidance == GUIDANCE_PRIORITY_SWITCHING_INCOMPLETE

    def test_deadline_priority_with_deliverables_selects_incomplete(self):
        """Deadline priority with deliverables_total > 0 selects INCOMPLETE variant."""
        patterns = [
            {
                "pattern_type": "priority_switching",
                "retired_priorities": [
                    {"name": "Launch Event", "type": "deadline", "deliverables_done": 1, "deliverables_total": 4},
                ],
            }
        ]

        guidance = _get_switching_guidance(patterns)

        assert guidance == GUIDANCE_PRIORITY_SWITCHING_INCOMPLETE

    def test_build_guidance_uses_correct_variant_for_no_criteria(self):
        """_build_assistant_guidance uses NO_CRITERIA variant when appropriate."""
        data = {
            "reason": "PATTERNS_FOUND",
            "patterns": [
                {
                    "pattern_type": "priority_switching",
                    "retired_priorities": [
                        {"name": "Priority A", "type": "flexible", "goals_achieved": 0, "goals_total": 0},
                    ],
                }
            ],
        }

        guidance = _build_assistant_guidance(data)

        assert "without any goals or deliverables defined" in guidance
        assert "goals or deliverables still incomplete" not in guidance

    def test_build_guidance_uses_correct_variant_for_incomplete(self):
        """_build_assistant_guidance uses INCOMPLETE variant when appropriate."""
        data = {
            "reason": "PATTERNS_FOUND",
            "patterns": [
                {
                    "pattern_type": "priority_switching",
                    "retired_priorities": [
                        {"name": "Priority A", "type": "flexible", "goals_achieved": 1, "goals_total": 3},
                    ],
                }
            ],
        }

        guidance = _build_assistant_guidance(data)

        assert "goals or deliverables still incomplete" in guidance
        assert "without any goals or deliverables defined" not in guidance
