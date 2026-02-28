"""
Unit tests for MCP discovery endpoint URL consistency.

Tests verify that discovery endpoints return URLs derived from
configured values, catching drift when config changes.
"""

import pytest


class TestDiscoveryConsistency:
    """Tests for discovery endpoint URL and scope consistency."""

    @pytest.mark.asyncio
    async def test_openid_configuration_urls_derive_from_oauth_issuer_url(self):
        """openid_configuration URLs should derive from OAUTH_ISSUER_URL."""
        from mcp_server.priority_guardian.discovery import openid_configuration
        from mcp_server.priority_guardian.config import OAUTH_ISSUER_URL

        result = await openid_configuration()

        # All these URLs should start with OAUTH_ISSUER_URL
        assert result["authorization_endpoint"].startswith(OAUTH_ISSUER_URL)
        assert result["token_endpoint"].startswith(OAUTH_ISSUER_URL)
        assert result["jwks_uri"].startswith(OAUTH_ISSUER_URL)
        assert result["registration_endpoint"].startswith(OAUTH_ISSUER_URL)

        # issuer should exactly match
        assert result["issuer"] == OAUTH_ISSUER_URL

    @pytest.mark.asyncio
    async def test_oauth_authorization_server_urls_derive_from_oauth_issuer_url(self):
        """oauth_authorization_server URLs should derive from OAUTH_ISSUER_URL."""
        from mcp_server.priority_guardian.discovery import oauth_authorization_server
        from mcp_server.priority_guardian.config import OAUTH_ISSUER_URL

        result = await oauth_authorization_server()

        # All these URLs should start with OAUTH_ISSUER_URL
        assert result["authorization_endpoint"].startswith(OAUTH_ISSUER_URL)
        assert result["token_endpoint"].startswith(OAUTH_ISSUER_URL)
        assert result["jwks_uri"].startswith(OAUTH_ISSUER_URL)

        # issuer should exactly match
        assert result["issuer"] == OAUTH_ISSUER_URL

    @pytest.mark.asyncio
    async def test_oauth_protected_resource_uses_mcp_server_url(self):
        """oauth_protected_resource should use MCP_SERVER_URL and OAUTH_ISSUER_URL."""
        from mcp_server.priority_guardian.discovery import oauth_protected_resource
        from mcp_server.priority_guardian.config import MCP_SERVER_URL, OAUTH_ISSUER_URL

        result = await oauth_protected_resource()

        # resource should exactly match MCP_SERVER_URL
        assert result["resource"] == MCP_SERVER_URL

        # authorization_servers should contain OAUTH_ISSUER_URL
        assert OAUTH_ISSUER_URL in result["authorization_servers"]

    @pytest.mark.asyncio
    async def test_discovery_scopes_match_config(self):
        """All discovery endpoints should return scopes_supported matching config."""
        from mcp_server.priority_guardian.discovery import (
            openid_configuration,
            oauth_authorization_server,
            oauth_protected_resource,
        )
        from mcp_server.priority_guardian.config import SCOPES_SUPPORTED

        oidc = await openid_configuration()
        oauth_as = await oauth_authorization_server()
        oauth_pr = await oauth_protected_resource()

        # All three should have scopes_supported matching config
        assert oidc["scopes_supported"] == SCOPES_SUPPORTED
        assert oauth_as["scopes_supported"] == SCOPES_SUPPORTED
        assert oauth_pr["scopes_supported"] == SCOPES_SUPPORTED

    @pytest.mark.asyncio
    async def test_code_challenge_methods_include_s256(self):
        """openid_configuration and oauth_authorization_server should include S256."""
        from mcp_server.priority_guardian.discovery import (
            openid_configuration,
            oauth_authorization_server,
        )

        oidc = await openid_configuration()
        oauth_as = await oauth_authorization_server()

        # Both should have code_challenge_methods_supported with S256
        assert "code_challenge_methods_supported" in oidc
        assert "S256" in oidc["code_challenge_methods_supported"]

        assert "code_challenge_methods_supported" in oauth_as
        assert "S256" in oauth_as["code_challenge_methods_supported"]
