"""
Unit tests for ROUTE_SCOPE_REGISTRY in register_client.py (Increment 79).

Pure structure tests — no HTTP, no DB.
"""

from backend.core.oauth_provider.register_client import ROUTE_SCOPE_REGISTRY


def test_registry_contains_exactly_three_apps():
    """ROUTE_SCOPE_REGISTRY contains exactly focused, pg, mindsort."""
    assert set(ROUTE_SCOPE_REGISTRY.keys()) == {"focused", "pg", "mindsort"}
