"""
Integration tests for Priority Guardian MCP discovery endpoints.

Tests verify that discovery endpoints mounted at both root and /mcp suffix
return valid JSON with required fields. ChatGPT specifically hits the /mcp
suffixed paths.

Gap #5: oauth_protected_resource/mcp Not Tested at MCP Server Level
"""

import pytest
import httpx
from unittest.mock import patch


@pytest.fixture
def pg_app():
    """Create Priority Guardian app for testing."""
    with patch.dict("os.environ", {"ENV": "dev"}, clear=False):
        from mcp_server.priority_guardian.server import create_app
        return create_app()


class TestDiscoveryEndpointsMcpSuffix:
    """Integration tests for /mcp suffixed discovery endpoints."""

    @pytest.mark.asyncio
    async def test_oauth_protected_resource_mcp_returns_valid_json(self, pg_app):
        """GET /.well-known/oauth-protected-resource/mcp returns valid JSON."""
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/.well-known/oauth-protected-resource/mcp")

        assert response.status_code == 200

        # Verify content-type
        content_type = response.headers.get("content-type", "")
        assert content_type.startswith("application/json")

        # Verify required fields
        data = response.json()
        assert "resource" in data
        assert isinstance(data["resource"], str)

        assert "authorization_servers" in data
        assert isinstance(data["authorization_servers"], list)
        assert len(data["authorization_servers"]) > 0

        assert "scopes_supported" in data
        assert isinstance(data["scopes_supported"], list)

    @pytest.mark.asyncio
    async def test_openid_configuration_mcp_returns_valid_json(self, pg_app):
        """GET /.well-known/openid-configuration/mcp returns valid JSON."""
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/.well-known/openid-configuration/mcp")

        assert response.status_code == 200

        # Verify content-type
        content_type = response.headers.get("content-type", "")
        assert content_type.startswith("application/json")

        # Verify required fields
        data = response.json()
        assert "issuer" in data
        assert isinstance(data["issuer"], str)

        assert "authorization_endpoint" in data
        assert isinstance(data["authorization_endpoint"], str)

        assert "token_endpoint" in data
        assert isinstance(data["token_endpoint"], str)

        assert "jwks_uri" in data
        assert isinstance(data["jwks_uri"], str)

        assert "code_challenge_methods_supported" in data
        assert isinstance(data["code_challenge_methods_supported"], list)
        assert "S256" in data["code_challenge_methods_supported"]

    @pytest.mark.asyncio
    async def test_oauth_authorization_server_mcp_returns_valid_json(self, pg_app):
        """GET /.well-known/oauth-authorization-server/mcp returns valid JSON."""
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/.well-known/oauth-authorization-server/mcp")

        assert response.status_code == 200

        # Verify content-type
        content_type = response.headers.get("content-type", "")
        assert content_type.startswith("application/json")

        # Verify required fields
        data = response.json()
        assert "issuer" in data
        assert isinstance(data["issuer"], str)

        assert "authorization_endpoint" in data
        assert isinstance(data["authorization_endpoint"], str)

        assert "token_endpoint" in data
        assert isinstance(data["token_endpoint"], str)

        assert "jwks_uri" in data
        assert isinstance(data["jwks_uri"], str)

    @pytest.mark.asyncio
    async def test_mcp_suffix_matches_root(self, pg_app):
        """Root and /mcp suffixed endpoints return identical JSON.

        This catches router mis-mount regressions where the /mcp variant
        accidentally points to a different handler.
        """
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # oauth-protected-resource
            root_opr = await client.get("/.well-known/oauth-protected-resource")
            mcp_opr = await client.get("/.well-known/oauth-protected-resource/mcp")
            assert root_opr.json() == mcp_opr.json(), "oauth-protected-resource mismatch"

            # openid-configuration
            root_oidc = await client.get("/.well-known/openid-configuration")
            mcp_oidc = await client.get("/.well-known/openid-configuration/mcp")
            assert root_oidc.json() == mcp_oidc.json(), "openid-configuration mismatch"

            # oauth-authorization-server
            root_oas = await client.get("/.well-known/oauth-authorization-server")
            mcp_oas = await client.get("/.well-known/oauth-authorization-server/mcp")
            assert root_oas.json() == mcp_oas.json(), "oauth-authorization-server mismatch"
