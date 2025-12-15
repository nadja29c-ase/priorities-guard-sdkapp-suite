"""
Unit tests for clarity.write scope support in OAuth provider.

Tests that scope descriptions are properly defined in production code.
"""

from backend.core.oauth_provider.authorize import (
    SCOPE_DESCRIPTIONS_EN,
    SCOPE_DESCRIPTIONS_DE,
)
from backend.core.oauth_provider.discovery import SCOPES_SUPPORTED


class TestClarityScopeDescriptions:
    """Tests for clarity.write scope descriptions in authorize.py."""

    def test_scope_descriptions_include_clarity_write_en(self):
        """English scope descriptions must include clarity.write."""
        assert "clarity.write" in SCOPE_DESCRIPTIONS_EN
        # Check key terms rather than exact string (allows copy to evolve)
        desc = SCOPE_DESCRIPTIONS_EN["clarity.write"].lower()
        assert "cluster" in desc or "organize" in desc or "thought" in desc

    def test_scope_descriptions_include_clarity_write_de(self):
        """German scope descriptions must include clarity.write."""
        assert "clarity.write" in SCOPE_DESCRIPTIONS_DE
        assert len(SCOPE_DESCRIPTIONS_DE["clarity.write"]) > 0

    def test_clarity_scope_descriptions_not_empty(self):
        """clarity.write descriptions must be non-empty strings."""
        # EN description
        en_desc = SCOPE_DESCRIPTIONS_EN.get("clarity.write", "")
        assert isinstance(en_desc, str)
        assert len(en_desc) > 0
        assert en_desc.strip() == en_desc  # No leading/trailing whitespace

        # DE description
        de_desc = SCOPE_DESCRIPTIONS_DE.get("clarity.write", "")
        assert isinstance(de_desc, str)
        assert len(de_desc) > 0
        assert de_desc.strip() == de_desc

    def test_all_discovery_scopes_have_descriptions(self):
        """Every scope in discovery must have EN and DE descriptions."""
        for scope in SCOPES_SUPPORTED:
            assert scope in SCOPE_DESCRIPTIONS_EN, f"Missing EN description for {scope}"
            assert scope in SCOPE_DESCRIPTIONS_DE, f"Missing DE description for {scope}"

    def test_no_orphan_descriptions(self):
        """Every described scope must be in discovery scopes_supported."""
        for scope in SCOPE_DESCRIPTIONS_EN:
            assert scope in SCOPES_SUPPORTED, f"EN description for {scope} not in discovery"
        for scope in SCOPE_DESCRIPTIONS_DE:
            assert scope in SCOPES_SUPPORTED, f"DE description for {scope} not in discovery"


class TestDiscoveryScopesSupported:
    """Tests for clarity.write in discovery endpoint."""

    def test_scopes_supported_not_empty(self):
        """Discovery must advertise at least one scope."""
        assert SCOPES_SUPPORTED  # Non-empty

    def test_scopes_supported_includes_clarity_write(self):
        """Discovery endpoint must advertise clarity.write scope."""
        assert "clarity.write" in SCOPES_SUPPORTED

    def test_all_focused_scopes_present(self):
        """Discovery must include all Focused scopes for backwards compatibility."""
        assert "focused.read" in SCOPES_SUPPORTED
        assert "focused.write" in SCOPES_SUPPORTED
        assert "focused.notify" in SCOPES_SUPPORTED
