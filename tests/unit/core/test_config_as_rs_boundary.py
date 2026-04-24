"""
Unit tests for AS/RS boundary enforcement in backend config.

The backend AS must never reference MCP server (RS) URLs. This file
guards against reintroduction of PG_MCP_SERVER_URL or similar fields.
"""


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

        # These substrings should never appear in any backend Settings field name.
        # Why each one is forbidden:
        # - MCP_SERVER_URL    — RS server URL (PG_MCP_SERVER_URL pattern)
        # - MCP_RESOURCE_URL  — RS resource URL per RFC 9728
        # - RESOURCE_METADATA — derived constant pointing to RS metadata
        # All belong in the MCP server's own config, never in the AS.
        forbidden_patterns = ["MCP_SERVER_URL", "MCP_RESOURCE_URL", "RESOURCE_METADATA"]

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

        assert not hasattr(config, "_MCP_ORIGIN"), (
            "config._MCP_ORIGIN should not exist. "
            "MCP origin derivation belongs in MCP server config, not backend. "
            "Underscore prefix doesn't exempt it from the AS/RS boundary — "
            "this constant was the building block for resource_metadata URLs. "
            "See ADR_MCP Server Implementation Standard.md → Backend Config Boundary."
        )
