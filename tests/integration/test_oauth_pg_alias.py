"""
Test /oauth/pg/* alias routes work identically to /oauth/focused/*

These tests verify that the new /oauth/pg/* routes are properly registered
and return the same responses as the legacy /oauth/focused/* routes.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from backend.main import app


@pytest_asyncio.fixture
async def backend_client():
    """Create async test client for backend."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        yield client


class TestOAuthPgAlias:
    """Verify /oauth/pg/* routes work."""

    @pytest.mark.asyncio
    async def test_pg_jwks_endpoint(self, backend_client: AsyncClient):
        """GET /oauth/pg/jwks returns valid JWKS."""
        response = await backend_client.get("/oauth/pg/jwks")

        assert response.status_code == 200
        data = response.json()
        assert "keys" in data
        assert len(data["keys"]) > 0

    @pytest.mark.asyncio
    async def test_focused_jwks_endpoint(self, backend_client: AsyncClient):
        """GET /oauth/focused/jwks still works."""
        response = await backend_client.get("/oauth/focused/jwks")

        assert response.status_code == 200
        data = response.json()
        assert "keys" in data

    @pytest.mark.asyncio
    async def test_pg_and_focused_return_same_jwks(self, backend_client: AsyncClient):
        """Both /oauth/pg/jwks and /oauth/focused/jwks return identical keys."""
        pg_response = await backend_client.get("/oauth/pg/jwks")
        focused_response = await backend_client.get("/oauth/focused/jwks")

        assert pg_response.json() == focused_response.json()


class TestOpenIDConfiguration:
    """Test OpenID configuration endpoint."""

    @pytest.mark.asyncio
    async def test_openid_configuration_includes_clarity_scope(self, backend_client: AsyncClient):
        """GET /.well-known/openid-configuration includes clarity.write scope."""
        response = await backend_client.get("/.well-known/openid-configuration")

        assert response.status_code == 200
        data = response.json()
        assert "clarity.write" in data["scopes_supported"]
        assert "focused.read" in data["scopes_supported"]
        assert "focused.write" in data["scopes_supported"]

    @pytest.mark.asyncio
    async def test_openid_configuration_uses_pg_endpoints(self, backend_client: AsyncClient):
        """OpenID configuration points to /oauth/pg/* endpoints."""
        response = await backend_client.get("/.well-known/openid-configuration")

        data = response.json()

        # All endpoints must use /oauth/pg path (not /oauth/focused)
        assert "/oauth/pg/authorize" in data["authorization_endpoint"]
        assert "/oauth/pg/token" in data["token_endpoint"]
        assert "/oauth/pg/jwks" in data["jwks_uri"]
        assert "/oauth/pg/register" in data["registration_endpoint"]

        # Issuer consistency: all endpoints should be under the issuer
        issuer = data["issuer"]
        assert data["authorization_endpoint"].startswith(issuer)
        assert data["token_endpoint"].startswith(issuer)
        assert data["jwks_uri"].startswith(issuer)
        assert data["registration_endpoint"].startswith(issuer)

        # Guard against /oauth/focused appearing anywhere
        assert "/oauth/focused" not in data["authorization_endpoint"]
        assert "/oauth/focused" not in data["token_endpoint"]
        assert "/oauth/focused" not in data["jwks_uri"]
        assert "/oauth/focused" not in data["registration_endpoint"]


class TestOAuthProtectedResourceRemoved:
    """Test that backend no longer serves oauth-protected-resource."""

    @pytest.mark.asyncio
    async def test_oauth_protected_resource_not_served(self, backend_client: AsyncClient):
        """GET /.well-known/oauth-protected-resource returns 404."""
        response = await backend_client.get("/.well-known/oauth-protected-resource")

        # Should return 404 since we removed this endpoint from backend
        # Each MCP server now owns its own oauth-protected-resource
        assert response.status_code == 404
