"""
Unit tests for AS/RS boundary enforcement in backend config.

The backend AS must never reference MCP server (RS) URLs. This file
guards against reintroduction of PG_MCP_SERVER_URL or similar fields.
"""

import pytest


class TestASRSBoundary:
    """Tests that backend config enforces AS/RS separation."""

    def test_settings_has_no_mcp_server_url_fields(self):
        """
        Settings class must not have any *_MCP_SERVER_URL fields.

        The AS does not know about RS URLs. If you're adding an MCP server URL
        to backend config, you're violating the AS/RS boundary.
        """
        from backend.core.config import Settings

        field_names = set(Settings.model_fields.keys())

        # These should never exist in backend config
        forbidden_patterns = ["MCP_SERVER_URL", "mcp_server_url"]

        violations = [
            name for name in field_names
            for pattern in forbidden_patterns
            if pattern.lower() in name.lower()
        ]

        assert not violations, (
            f"Found RS URL field(s) in backend config: {violations}. "
            "The AS must not reference MCP server URLs. See ADR_MCP Server "
            "Implementation Standard.md → Backend Config Boundary."
        )

    def test_backend_does_not_export_www_authenticate_value(self):
        """
        backend.core.config must not export WWW_AUTHENTICATE_VALUE.

        The AS cannot emit resource_metadata headers because it doesn't know
        which RS the client will use. Token endpoint uses 'Bearer realm="oauth"'.
        """
        from backend.core import config

        assert not hasattr(config, "WWW_AUTHENTICATE_VALUE"), (
            "config.WWW_AUTHENTICATE_VALUE should not exist. "
            "The AS emits 'Bearer realm=\"oauth\"', not resource_metadata. "
            "See ADR_MCP Server Implementation Standard.md → Backend Config Boundary."
        )

        assert not hasattr(config, "RESOURCE_METADATA_URL"), (
            "config.RESOURCE_METADATA_URL should not exist. "
            "RS metadata URLs belong in MCP server config, not backend. "
            "See ADR_MCP Server Implementation Standard.md → Backend Config Boundary."
        )
