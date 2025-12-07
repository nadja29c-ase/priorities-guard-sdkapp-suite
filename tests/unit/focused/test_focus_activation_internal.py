"""
Unit tests for Focus Activation Internal utilities (Increment 20).

Tests the minimal utility functions for generating shortcut URLs.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from backend.apps.focused.tools.focus_activation_internal import (
    DEFAULT_FOCUS_NAME,
    extract_focus_name,
    generate_shortcut_url,
    run_focus_mode_internal,
)


class TestExtractFocusName:
    """Tests for extract_focus_name function."""

    def test_extracts_name_from_summary(self):
        """Should extract focus name from event summary."""
        result = extract_focus_name("Deep Work Session")
        assert result == "Deep Work Session"

    def test_returns_default_for_none(self):
        """Should return default name when summary is None."""
        result = extract_focus_name(None)
        assert result == DEFAULT_FOCUS_NAME

    def test_returns_default_for_empty_string(self):
        """Should return default name when summary is empty."""
        result = extract_focus_name("")
        assert result == DEFAULT_FOCUS_NAME

    def test_returns_default_for_whitespace(self):
        """Should return default name when summary is only whitespace."""
        result = extract_focus_name("   ")
        assert result == DEFAULT_FOCUS_NAME

    def test_strips_whitespace(self):
        """Should strip leading/trailing whitespace from summary."""
        result = extract_focus_name("  Focus Time  ")
        assert result == "Focus Time"

    def test_truncates_long_summaries(self):
        """Should truncate summaries longer than 100 characters."""
        long_name = "A" * 150
        result = extract_focus_name(long_name)
        assert len(result) == 100
        assert result == "A" * 100


class TestGenerateShortcutUrl:
    """Tests for generate_shortcut_url function."""

    def test_generates_valid_url(self):
        """Should generate valid shortcuts:// URL."""
        result = generate_shortcut_url("Deep Work")
        assert result.startswith("shortcuts://run-shortcut")
        assert "Activate%20Focus%20Mode" in result
        assert "Deep%20Work" in result

    def test_url_encodes_special_characters(self):
        """Should URL-encode special characters in focus name."""
        result = generate_shortcut_url("Focus & Code")
        assert "Focus%20%26%20Code" in result

    def test_handles_unicode_characters(self):
        """Should handle unicode characters in focus name."""
        result = generate_shortcut_url("Focus 🎯")
        assert "shortcuts://run-shortcut" in result


class TestRunFocusModeInternal:
    """Tests for run_focus_mode_internal function."""

    def test_returns_shortcut_url(self):
        """Should return dictionary with shortcut_url."""
        mock_session = MagicMock()
        mock_session.event_summary = "Deep Work"
        mock_session.end_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        result = run_focus_mode_internal(mock_session)

        assert "shortcut_url" in result
        assert result["shortcut_url"].startswith("shortcuts://")

    def test_returns_focus_name(self):
        """Should return extracted focus name."""
        mock_session = MagicMock()
        mock_session.event_summary = "Deep Work Session"
        mock_session.end_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        result = run_focus_mode_internal(mock_session)

        assert result["focus_name"] == "Deep Work Session"

    def test_returns_end_time_iso_format(self):
        """Should return end_time as ISO 8601 string."""
        mock_session = MagicMock()
        mock_session.event_summary = "Focus"
        mock_session.end_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        result = run_focus_mode_internal(mock_session)

        assert result["end_time"] == "2025-01-01T12:00:00+00:00"

    def test_returns_none_end_time_when_missing(self):
        """Should return None for end_time when session has no end_time."""
        mock_session = MagicMock()
        mock_session.event_summary = "Focus"
        mock_session.end_time = None

        result = run_focus_mode_internal(mock_session)

        assert result["end_time"] is None

    def test_uses_default_name_for_empty_summary(self):
        """Should use default focus name when summary is empty."""
        mock_session = MagicMock()
        mock_session.event_summary = None
        mock_session.end_time = None

        result = run_focus_mode_internal(mock_session)

        assert result["focus_name"] == DEFAULT_FOCUS_NAME
