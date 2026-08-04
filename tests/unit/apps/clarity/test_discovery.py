"""
Unit tests for Clarity OAuth discovery endpoints.

Verifies all required fields are present and correctly derived from config.
"""

import pytest


class TestClarityDiscovery:
    """Tests for Clarity discovery endpoint structure and values."""

    @pytest.mark.asyncio
    async def test_openid_configuration_required_fields(self):
        """openid_configuration should return all required OAuth fields."""
        from mcp_server.clarity.discovery import openid_configuration
        from mcp_server.clarity.config import CLARITY_ISSUER, OAUTH_ISSUER_URL, SCOPES_SUPPORTED

        result = await openid_configuration()

        # Core fields - issuer must be domain-only
        assert result["issuer"] == CLARITY_ISSUER
        assert result["authorization_endpoint"] == f"{OAUTH_ISSUER_URL}/authorize"
        assert result["token_endpoint"] == f"{OAUTH_ISSUER_URL}/token"
        assert result["jwks_uri"] == f"{OAUTH_ISSUER_URL}/jwks"
        assert result["registration_endpoint"] == f"{OAUTH_ISSUER_URL}/register"
        assert result["scopes_supported"] == SCOPES_SUPPORTED

        # Required response/grant fields (RFC 8414 alignment with PG)
        assert result["response_types_supported"] == ["code"]
        assert result["grant_types_supported"] == ["authorization_code", "refresh_token"]
        assert result["token_endpoint_auth_methods_supported"] == ["none"]
        assert result["code_challenge_methods_supported"] == ["S256"]

    @pytest.mark.asyncio
    async def test_oauth_authorization_server_required_fields(self):
        """oauth_authorization_server should return all required OAuth fields."""
        from mcp_server.clarity.discovery import oauth_authorization_server
        from mcp_server.clarity.config import CLARITY_ISSUER, OAUTH_ISSUER_URL, SCOPES_SUPPORTED

        result = await oauth_authorization_server()

        # Core fields - issuer must be domain-only
        assert result["issuer"] == CLARITY_ISSUER
        assert result["authorization_endpoint"] == f"{OAUTH_ISSUER_URL}/authorize"
        assert result["token_endpoint"] == f"{OAUTH_ISSUER_URL}/token"
        assert result["jwks_uri"] == f"{OAUTH_ISSUER_URL}/jwks"
        assert result["registration_endpoint"] == f"{OAUTH_ISSUER_URL}/register"
        assert result["scopes_supported"] == SCOPES_SUPPORTED

        # Required response/grant fields (RFC 8414 alignment with PG)
        assert result["response_types_supported"] == ["code"]
        assert result["grant_types_supported"] == ["authorization_code", "refresh_token"]
        assert result["token_endpoint_auth_methods_supported"] == ["none"]
        assert result["code_challenge_methods_supported"] == ["S256"]

    @pytest.mark.asyncio
    async def test_oauth_protected_resource_includes_mcp_path(self):
        """oauth_protected_resource should return resource URL with /mcp path."""
        from mcp_server.clarity.discovery import oauth_protected_resource
        from mcp_server.clarity.config import MCP_SERVER_URL, OAUTH_ISSUER_URL, SCOPES_SUPPORTED

        result = await oauth_protected_resource()

        # resource must include /mcp path (RFC 9728 alignment with PG)
        assert result["resource"] == f"{MCP_SERVER_URL}/mcp"

        # authorization_servers must be path-qualified for Shape #2 (MindSort-OpenAI)
        # See doc/ADR/ADR_005_platform_oauth_discovery_contracts.md
        assert result["authorization_servers"] == [OAUTH_ISSUER_URL]
        assert result["scopes_supported"] == SCOPES_SUPPORTED

    @pytest.mark.asyncio
    async def test_discovery_scopes_consistency(self):
        """All discovery endpoints should return same scopes_supported."""
        from mcp_server.clarity.discovery import (
            openid_configuration,
            oauth_authorization_server,
            oauth_protected_resource,
        )
        from mcp_server.clarity.config import SCOPES_SUPPORTED

        oidc = await openid_configuration()
        oauth_as = await oauth_authorization_server()
        oauth_pr = await oauth_protected_resource()

        # All three should have scopes_supported matching config
        assert oidc["scopes_supported"] == SCOPES_SUPPORTED
        assert oauth_as["scopes_supported"] == SCOPES_SUPPORTED
        assert oauth_pr["scopes_supported"] == SCOPES_SUPPORTED
