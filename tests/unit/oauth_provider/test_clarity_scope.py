"""
Unit tests for clarity scope support in OAuth provider.

Tests that scope descriptions are properly defined in production code.
Covers both clarity.read (read-only tools) and clarity.write (mutation tools).
"""

from backend.core.oauth_provider.authorize import (
    SCOPE_DESCRIPTIONS_EN,
    SCOPE_DESCRIPTIONS_DE,
)
from backend.core.oauth_provider.discovery import SCOPES_SUPPORTED


class TestClarityScopeDescriptions:
    """Tests for clarity scope descriptions in authorize.py."""

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

    def test_scope_descriptions_include_clarity_read_en(self):
        """English scope descriptions must include clarity.read."""
        assert "clarity.read" in SCOPE_DESCRIPTIONS_EN
        # Check key terms rather than exact string (allows copy to evolve)
        desc = SCOPE_DESCRIPTIONS_EN["clarity.read"].lower()
        assert "view" in desc or "cluster" in desc or "history" in desc

    def test_scope_descriptions_include_clarity_read_de(self):
        """German scope descriptions must include clarity.read."""
        assert "clarity.read" in SCOPE_DESCRIPTIONS_DE
        assert len(SCOPE_DESCRIPTIONS_DE["clarity.read"]) > 0

    def test_clarity_scope_descriptions_not_empty(self):
        """Clarity scope descriptions must be non-empty strings."""
        for scope in ["clarity.read", "clarity.write"]:
            # EN description
            en_desc = SCOPE_DESCRIPTIONS_EN.get(scope, "")
            assert isinstance(en_desc, str), f"{scope} EN description not a string"
            assert len(en_desc) > 0, f"{scope} EN description empty"
            assert en_desc.strip() == en_desc, f"{scope} EN has whitespace"

            # DE description
            de_desc = SCOPE_DESCRIPTIONS_DE.get(scope, "")
            assert isinstance(de_desc, str), f"{scope} DE description not a string"
            assert len(de_desc) > 0, f"{scope} DE description empty"
            assert de_desc.strip() == de_desc, f"{scope} DE has whitespace"

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

    def test_en_and_de_scope_sets_match(self):
        """EN and DE must describe exactly the same scopes (no missing translations)."""
        en_scopes = set(SCOPE_DESCRIPTIONS_EN.keys())
        de_scopes = set(SCOPE_DESCRIPTIONS_DE.keys())
        assert en_scopes == de_scopes, (
            f"EN-only: {en_scopes - de_scopes}, DE-only: {de_scopes - en_scopes}"
        )


class TestDiscoveryScopesSupported:
    """Tests for clarity scopes in discovery endpoint."""

    def test_scopes_supported_not_empty(self):
        """Discovery must advertise at least one scope."""
        assert SCOPES_SUPPORTED  # Non-empty

    def test_scopes_supported_includes_clarity_write(self):
        """Discovery endpoint must advertise clarity.write scope."""
        assert "clarity.write" in SCOPES_SUPPORTED

    def test_scopes_supported_includes_clarity_read(self):
        """Discovery endpoint must advertise clarity.read scope."""
        assert "clarity.read" in SCOPES_SUPPORTED

    def test_all_focused_scopes_present(self):
        """Discovery must include all Focused scopes for backwards compatibility."""
        assert "focused.read" in SCOPES_SUPPORTED
        assert "focused.write" in SCOPES_SUPPORTED
        assert "focused.notify" in SCOPES_SUPPORTED

    def test_all_clarity_scopes_present(self):
        """Discovery must include all Clarity scopes."""
        assert "clarity.read" in SCOPES_SUPPORTED
        assert "clarity.write" in SCOPES_SUPPORTED

    def test_discovery_scopes_minimum_required_set(self):
        """Discovery must include all required scopes (guards against accidental removal)."""
        required_scopes = {
            "focused.read",
            "focused.write",
            "focused.notify",
            "clarity.read",
            "clarity.write",
        }
        assert required_scopes.issubset(set(SCOPES_SUPPORTED)), (
            f"Missing required scopes: {required_scopes - set(SCOPES_SUPPORTED)}"
        )
