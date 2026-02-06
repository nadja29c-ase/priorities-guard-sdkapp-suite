"""
Priority Guardian integration tests.

Tests:
- Health endpoint returns correct structure
- pg.access scope is advertised in OAuth discovery
- Google connection status endpoint
"""

import pytest
from uuid import uuid4
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.oauth_provider.discovery import SCOPES_SUPPORTED


class TestHealthEndpoint:
    """Test Priority Guardian health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client: AsyncClient):
        """Test health endpoint returns success response."""
        response = await client.get("/api/priority-guardian/health")

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert data["data"]["status"] == "ok"
        assert data["data"]["service"] == "priority-guardian-backend"
        assert "version" in data["data"]

    @pytest.mark.asyncio
    async def test_health_response_structure(self, client: AsyncClient):
        """Test health response follows standard structure."""
        response = await client.get("/api/priority-guardian/health")

        data = response.json()

        # Must have success key
        assert "success" in data

        # When success, must have data key
        assert "data" in data

        # data must have required fields
        assert "status" in data["data"]
        assert "service" in data["data"]


class TestPGScopeAdvertised:
    """Test pg.access scope is properly advertised."""

    def test_pg_access_in_supported_scopes(self):
        """Test pg.access is in SCOPES_SUPPORTED list."""
        assert "pg.access" in SCOPES_SUPPORTED

    def test_scopes_sorted_alphabetically(self):
        """Test scopes are sorted alphabetically."""
        assert SCOPES_SUPPORTED == sorted(SCOPES_SUPPORTED)


class TestPGScopeDescriptions:
    """Test pg.access scope descriptions are defined."""

    def test_pg_access_description_en(self):
        """Test English scope description exists."""
        from backend.core.oauth_provider.authorize import SCOPE_DESCRIPTIONS_EN

        assert "pg.access" in SCOPE_DESCRIPTIONS_EN
        # Description should mention Priority Guardian and calendar
        desc = SCOPE_DESCRIPTIONS_EN["pg.access"]
        assert "Priority Guardian" in desc or "calendar" in desc.lower()

    def test_pg_access_description_de(self):
        """Test German scope description exists."""
        from backend.core.oauth_provider.authorize import SCOPE_DESCRIPTIONS_DE

        assert "pg.access" in SCOPE_DESCRIPTIONS_DE
        # Description should mention Priority Guardian or calendar
        desc = SCOPE_DESCRIPTIONS_DE["pg.access"]
        assert "Priority Guardian" in desc or "kalender" in desc.lower()


class TestGoogleConnectionStatus:
    """Test Google connection status endpoint."""

    @pytest.fixture
    async def test_user(self, async_session: AsyncSession):
        """Create a test user for connection status tests."""
        user_id = str(uuid4())
        await async_session.execute(
            text("INSERT INTO core_users (id) VALUES (:id)"),
            {"id": user_id},
        )
        await async_session.commit()
        return user_id

    @pytest.mark.asyncio
    async def test_connection_status_not_connected(self, client: AsyncClient, test_user: str):
        """Test connection-status returns false when user has no Google connection."""
        response = await client.get(
            "/api/priority-guardian/google/connection-status",
            headers={"X-User-ID": test_user}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["connected"] is False

    @pytest.mark.asyncio
    async def test_connection_status_requires_user_id(self, client: AsyncClient):
        """Test connection-status returns 422 without X-User-ID header."""
        response = await client.get("/api/priority-guardian/google/connection-status")

        # FastAPI returns 422 for missing required header
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_connection_status_connected(
        self,
        client: AsyncClient,
        test_user: str,
        async_session: AsyncSession
    ):
        """Test connection-status returns true when user has active Google connection."""
        # Insert a Google connection for the user
        await async_session.execute(
            text("""
                INSERT INTO core_connections (
                    user_id, provider, connection_type,
                    encrypted_access_token, token_expires_at, scopes
                ) VALUES (
                    :user_id, 'google', 'google',
                    'encrypted_token_placeholder',
                    now() + interval '1 hour',
                    ARRAY['https://www.googleapis.com/auth/calendar.readonly']::text[]
                )
            """),
            {"user_id": test_user},
        )
        await async_session.commit()

        response = await client.get(
            "/api/priority-guardian/google/connection-status",
            headers={"X-User-ID": test_user}
        )

        assert response.status_code == 200
        data = response.json()

        assert data["connected"] is True
        assert "connected_at" in data
        assert "scopes" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
