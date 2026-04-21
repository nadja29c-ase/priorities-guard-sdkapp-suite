"""
Unit tests for client_service.create_oauth_client.

Tests the scopes validation fix (no global default scopes allowed)
and verifies the happy path still works with explicit scopes.
"""

import pytest

from backend.core.oauth_provider.services.client_service import create_oauth_client


@pytest.mark.asyncio
async def test_create_oauth_client_raises_when_scopes_none(async_session):
    """scopes=None must raise — no global default scopes allowed (cross-app privilege landmine)."""
    with pytest.raises(ValueError, match="scopes must be explicitly provided"):
        await create_oauth_client(
            db=async_session,
            client_name="test-client",
            redirect_uris=["https://example.com/callback"],
            grant_types=["authorization_code"],
            scopes=None,
        )


@pytest.mark.asyncio
async def test_create_oauth_client_succeeds_with_explicit_scopes(async_session):
    """Normal path still works when caller passes explicit scopes."""
    client_id, client_secret = await create_oauth_client(
        db=async_session,
        client_name="test-client",
        redirect_uris=["https://example.com/callback"],
        grant_types=["authorization_code", "refresh_token"],
        scopes=["pg.access"],
    )

    # The `pg-client-` prefix is a documented contract, not an implementation detail.
    # See client_service.py docstring ("Generates: Unique client_id (pg-client-{uuid})")
    # and register_client.py endpoint docstring (same contract). Keep the assertion.
    assert client_id.startswith("pg-client-")
    assert client_secret  # Plain-text secret returned exactly once
    assert len(client_secret) > 0
