"""
Integration tests for ROUTE_SCOPE_REGISTRY default scope behavior (Increment 79).

Tests that each registration route defaults to the correct scopes when no scope
is provided in the request body.
"""

import pytest
from httpx import AsyncClient


# Allowed redirect URI for tests (from OAUTH_ALLOWED_REDIRECT_URIS)
ALLOWED_REDIRECT_URI = "https://chatgpt.com/connector_platform_oauth_redirect"


class TestRegistryDefaultScopes:
    """Tests verifying route-specific default scope behavior."""

    @pytest.mark.asyncio
    async def test_focused_registration_defaults_to_focused_scopes(
        self,
        client: AsyncClient,
        fake_redis_client
    ):
        """POST to /oauth/focused/register with no scope defaults to focused.* scopes."""
        response = await client.post(
            "/oauth/focused/register",
            json={
                "client_name": "Inc79-Test-Focused",
                "redirect_uris": [ALLOWED_REDIRECT_URI],
            }
        )

        if response.status_code == 429:
            pytest.skip("Rate limited")

        assert response.status_code == 200, f"Expected 200, got: {response.status_code}, body: {response.text}"
        data = response.json()

        # Use set comparison - don't pin sort order as API contract
        assert set(data["scope"].split()) == {"focused.read", "focused.write", "focused.notify"}

    @pytest.mark.asyncio
    async def test_pg_registration_defaults_to_pg_access(
        self,
        client: AsyncClient,
        fake_redis_client
    ):
        """POST to /oauth/pg/register with no scope defaults to pg.access."""
        response = await client.post(
            "/oauth/pg/register",
            json={
                "client_name": "Inc79-Test-PG",
                "redirect_uris": [ALLOWED_REDIRECT_URI],
            }
        )

        if response.status_code == 429:
            pytest.skip("Rate limited")

        assert response.status_code == 200, f"Expected 200, got: {response.status_code}, body: {response.text}"
        data = response.json()

        # Exact string comparison for single-scope route
        assert data["scope"] == "pg.access"

    @pytest.mark.asyncio
    async def test_mindsort_registration_defaults_to_clarity_write(
        self,
        client: AsyncClient,
        fake_redis_client
    ):
        """POST to /oauth/mindsort/register with no scope defaults to clarity.write."""
        response = await client.post(
            "/oauth/mindsort/register",
            json={
                "client_name": "Inc79-Test-MindSort",
                "redirect_uris": [ALLOWED_REDIRECT_URI],
            }
        )

        if response.status_code == 429:
            pytest.skip("Rate limited")

        assert response.status_code == 200, f"Expected 200, got: {response.status_code}, body: {response.text}"
        data = response.json()

        # Exact string comparison for single-scope route
        assert data["scope"] == "clarity.write"
