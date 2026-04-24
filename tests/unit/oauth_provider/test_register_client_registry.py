"""
Unit tests for ROUTE_SCOPE_REGISTRY in register_client.py (Increment 79).

Pure structure tests — no HTTP, no DB.
"""

from backend.core.oauth_provider.register_client import (
    ROUTE_SCOPE_REGISTRY,
    SUPPORTED_SCOPES,
)


def test_registry_contains_exactly_three_apps():
    """ROUTE_SCOPE_REGISTRY contains exactly focused, pg, mindsort."""
    assert set(ROUTE_SCOPE_REGISTRY.keys()) == {"focused", "pg", "mindsort"}


def test_supported_scopes_includes_all_registry_scopes():
    """SUPPORTED_SCOPES contains every scope from every app in the registry."""
    expected = {scope for scopes in ROUTE_SCOPE_REGISTRY.values() for scope in scopes}
    assert SUPPORTED_SCOPES == expected


def test_supported_scopes_includes_focused_scopes():
    """Regression: Focused scopes must be in SUPPORTED_SCOPES.

    Previously SUPPORTED_SCOPES was derived from discovery.SCOPES_SUPPORTED
    which excluded focused.*, causing explicit DCR requests for focused scopes
    to fail validation even though the /oauth/focused/register route accepts them.
    """
    assert "focused.read" in SUPPORTED_SCOPES
    assert "focused.write" in SUPPORTED_SCOPES
    assert "focused.notify" in SUPPORTED_SCOPES
