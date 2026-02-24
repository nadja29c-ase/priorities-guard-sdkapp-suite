"""
Unit tests for get_patterns assistant_guidance composition (Increment 25/26).

Tests per-pattern guidance composition for consistency_streak, abandoned_priority,
priority_switching, and priority_protection patterns.
"""

import pytest

from mcp_server.priority_guardian.tools.get_patterns import (
    _build_assistant_guidance,
    GUIDANCE_COMMON,
    GUIDANCE_CONSISTENCY_STREAK,
    GUIDANCE_ABANDONED_PRIORITY,
    GUIDANCE_PRIORITY_SWITCHING,
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
        assert "healthy pivoting" not in guidance  # switching
        assert "despite growing calendar pressure" not in guidance  # protection

    def test_all_four_patterns_present(self):
        """All 4 patterns present includes COMMON + all 4 per-pattern guidance blocks."""
        data = {
            "reason": "PATTERNS_FOUND",
            "patterns": [
                {"pattern_type": "consistency_streak", "priority_id": "p1"},
                {"pattern_type": "abandoned_priority", "priority_id": "p2"},
                {"pattern_type": "priority_switching"},
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
                {"pattern_type": "priority_switching"},
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
    """Tests for priority switching guidance (increment_28)."""

    def test_switching_guidance_contains_reflection_questions(self):
        """GUIDANCE_PRIORITY_SWITCHING contains the two reflection questions."""
        from mcp_server.priority_guardian.tools.get_patterns import (
            GUIDANCE_PRIORITY_SWITCHING,
        )

        # Check for the evidence vs gut call question
        assert "hard evidence that each pivot was more promising" in GUIDANCE_PRIORITY_SWITCHING
        assert "gut call" in GUIDANCE_PRIORITY_SWITCHING

        # Check for the frustration/energy question
        assert "frustration, low energy, or feeling stuck" in GUIDANCE_PRIORITY_SWITCHING

    def test_switching_guidance_inline_phrasing_in_canonical_order(self):
        """Switching guidance uses inline phrasing consistent with canonical order."""
        from mcp_server.priority_guardian.tools.get_patterns import (
            _build_assistant_guidance,
        )

        data = {
            "reason": "PATTERNS_FOUND",
            "patterns": [{"pattern_type": "priority_switching"}],
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
