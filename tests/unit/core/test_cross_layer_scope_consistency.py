"""
Unit tests for cross-layer scope consistency between backend and MCP server.

Tests verify that scopes declared in MCP server config are supported by the
backend's OAuth provider discovery. This catches drift when config changes.

Gap #7: Cross-Layer Scope Consistency (Backend ↔ MCP Server)
"""

import pytest


class TestCrossLayerScopeConsistency:
    """Tests for backend ↔ MCP server scope alignment."""

    def test_backend_scopes_include_all_mcp_pg_scopes(self):
        """Every scope in MCP PG config must exist in backend discovery."""
        from backend.core.oauth_provider.discovery import SCOPES_SUPPORTED as backend_scopes
        from mcp_server.priority_guardian.config import SCOPES_SUPPORTED as mcp_scopes

        # Every MCP scope must be in backend's supported scopes
        for scope in mcp_scopes:
            assert scope in backend_scopes, (
                f"MCP server requests scope '{scope}' but backend "
                f"doesn't advertise it in SCOPES_SUPPORTED. "
                f"Backend scopes: {backend_scopes}"
            )

    def test_consent_scope_descriptions_cover_all_mcp_pg_scopes(self):
        """Every PG scope must have descriptions in both EN and DE."""
        from backend.core.oauth_provider.authorize import (
            SCOPE_DESCRIPTIONS_EN,
            SCOPE_DESCRIPTIONS_DE,
        )
        from mcp_server.priority_guardian.config import SCOPES_SUPPORTED as mcp_scopes

        for scope in mcp_scopes:
            # Check English description exists
            assert scope in SCOPE_DESCRIPTIONS_EN, (
                f"Scope '{scope}' missing English description in "
                f"SCOPE_DESCRIPTIONS_EN. Add it to authorize.py."
            )
            assert SCOPE_DESCRIPTIONS_EN[scope], (
                f"Scope '{scope}' has empty English description"
            )

            # Check German description exists
            assert scope in SCOPE_DESCRIPTIONS_DE, (
                f"Scope '{scope}' missing German description in "
                f"SCOPE_DESCRIPTIONS_DE. Add it to authorize.py."
            )
            assert SCOPE_DESCRIPTIONS_DE[scope], (
                f"Scope '{scope}' has empty German description"
            )
