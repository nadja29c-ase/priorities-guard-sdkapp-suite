"""
Integration tests for clarity scopes in OAuth provider.

Tests the full OAuth flow with clarity.read and clarity.write scopes:
- Discovery endpoint advertises clarity.read and clarity.write
- Client registration with clarity scopes
- Authorization accepts clarity scopes
- Token includes clarity scopes in scope claim
- Authorization rejects scope not registered to client
"""

import pytest
import pytest_asyncio
import base64
import hashlib
import jwt
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient  # Type hint only
from sqlalchemy.ext.asyncio import AsyncSession

from uuid import uuid4

from backend.core.models import CoreConnection
from backend.core.oauth_provider.models import OAuthAuthorizationCode


# ============================================================================
# FIXTURES
# ============================================================================

@pytest_asyncio.fixture
async def clarity_test_client(async_session: AsyncSession):
    """
    Create a test OAuth client with clarity.read and clarity.write scopes.

    Returns client info for testing clarity scope flows.
    Uses randomized client_id to avoid cross-test interference.
    """
    from backend.core.encryption import encrypt_token

    # Randomize to avoid CI flakiness and cross-test interference
    client_id = f"test-clarity-client-{uuid4()}"
    client_secret = f"test-clarity-secret-{uuid4()}"

    client = CoreConnection(
        user_id=None,  # OAuth provider clients have NULL user_id
        provider="Test Clarity Client",
        connection_type="oauth_provider",
        client_id=client_id,
        client_secret_enc=encrypt_token(client_secret),
        redirect_uris=["https://chat.openai.com/aip/callback"],
        grant_types=["authorization_code", "refresh_token"],
        encrypted_access_token="",
        scopes=["focused.read", "focused.write", "clarity.read", "clarity.write"],
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=365)
    )
    async_session.add(client)
    await async_session.commit()

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": "https://chat.openai.com/aip/callback"
    }


@pytest_asyncio.fixture
async def focused_only_client(async_session: AsyncSession):
    """
    Create a test OAuth client WITHOUT clarity.write scope.

    Used to test rejection of unauthorized scope requests.
    Uses randomized client_id to avoid cross-test interference.
    """
    from backend.core.encryption import encrypt_token

    # Randomize to avoid CI flakiness and cross-test interference
    client_id = f"test-focused-only-client-{uuid4()}"
    client_secret = f"test-focused-secret-{uuid4()}"

    client = CoreConnection(
        user_id=None,
        provider="Test Focused Only Client",
        connection_type="oauth_provider",
        client_id=client_id,
        client_secret_enc=encrypt_token(client_secret),
        redirect_uris=["https://chat.openai.com/aip/callback"],
        grant_types=["authorization_code", "refresh_token"],
        encrypted_access_token="",
        scopes=["focused.read", "focused.write"],  # NO clarity.write
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=365)
    )
    async_session.add(client)
    await async_session.commit()

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": "https://chat.openai.com/aip/callback"
    }


def generate_pkce_pair():
    """
    Generate code_verifier and code_challenge for PKCE (RFC 7636).

    code_verifier: High-entropy random string (43-128 chars)
    code_challenge: base64url(SHA256(code_verifier))
    """
    import os
    # Generate random verifier (32 bytes = 43 base64url chars after encoding)
    code_verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode()

    # Challenge = SHA256 hash of verifier
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()

    return code_verifier, code_challenge


# ============================================================================
# DISCOVERY TESTS
# ============================================================================

class TestDiscoveryIncludesClarityScope:
    """Tests that discovery endpoint advertises clarity scopes."""

    @pytest.mark.asyncio
    async def test_discovery_includes_clarity_write(self, client):
        """
        GET /.well-known/openid-configuration must include clarity.write
        in scopes_supported array.
        """
        response = await client.get("/.well-known/openid-configuration")

        assert response.status_code == 200
        data = response.json()

        assert "scopes_supported" in data
        assert isinstance(data["scopes_supported"], list)
        assert "clarity.write" in data["scopes_supported"]

    @pytest.mark.asyncio
    async def test_discovery_includes_clarity_read(self, client):
        """
        GET /.well-known/openid-configuration must include clarity.read
        in scopes_supported array.
        """
        response = await client.get("/.well-known/openid-configuration")

        assert response.status_code == 200
        data = response.json()

        assert "scopes_supported" in data
        assert isinstance(data["scopes_supported"], list)
        assert "clarity.read" in data["scopes_supported"]

    @pytest.mark.asyncio
    async def test_discovery_includes_all_focused_scopes(self, client):
        """
        Discovery must still include all Focused scopes for backwards compatibility.
        """
        response = await client.get("/.well-known/openid-configuration")

        assert response.status_code == 200
        data = response.json()

        scopes = data["scopes_supported"]
        assert "focused.read" in scopes
        assert "focused.write" in scopes
        assert "focused.notify" in scopes


# ============================================================================
# CLIENT REGISTRATION TESTS
# ============================================================================

class TestClientRegistrationWithClarityScope:
    """Tests that clients can register with clarity scopes."""

    @pytest.mark.asyncio
    async def test_register_client_with_clarity_write_scope(self, client, async_session: AsyncSession):
        """
        POST /oauth/pg/register with scope including clarity.write
        should succeed and create client with that scope.
        """
        import secrets
        from sqlalchemy import select

        registration_data = {
            "client_name": f"Test Clarity Registration {secrets.token_hex(4)}",
            "redirect_uris": ["https://example.com/callback"],
            "grant_types": ["authorization_code", "refresh_token"],
            "scope": "focused.read clarity.write"
        }

        response = await client.post(
            "/oauth/pg/register",
            json=registration_data
        )

        # API returns 200 or 201 on successful registration
        assert response.status_code in (200, 201)
        data = response.json()

        # Verify response includes clarity.write scope
        assert "client_id" in data
        assert "scope" in data
        assert "clarity.write" in data["scope"]

        # Verify client was actually persisted with clarity.write scope in DB
        stmt = select(CoreConnection).where(CoreConnection.client_id == data["client_id"])
        result = await async_session.execute(stmt)
        persisted_client = result.scalar_one_or_none()

        assert persisted_client is not None, "Client not found in database"
        assert "clarity.write" in persisted_client.scopes, "clarity.write not persisted in DB"

    @pytest.mark.asyncio
    async def test_register_client_with_clarity_read_scope(self, client, async_session: AsyncSession):
        """
        POST /oauth/pg/register with scope including clarity.read
        should succeed and create client with that scope.
        """
        import secrets
        from sqlalchemy import select

        registration_data = {
            "client_name": f"Test Clarity Read Registration {secrets.token_hex(4)}",
            "redirect_uris": ["https://example.com/callback"],
            "grant_types": ["authorization_code", "refresh_token"],
            "scope": "clarity.read"
        }

        response = await client.post(
            "/oauth/pg/register",
            json=registration_data
        )

        # API returns 200 or 201 on successful registration
        assert response.status_code in (200, 201)
        data = response.json()

        # Verify response includes clarity.read scope
        assert "client_id" in data
        assert "scope" in data
        assert "clarity.read" in data["scope"]

        # Verify client was actually persisted with clarity.read scope in DB
        stmt = select(CoreConnection).where(CoreConnection.client_id == data["client_id"])
        result = await async_session.execute(stmt)
        persisted_client = result.scalar_one_or_none()

        assert persisted_client is not None, "Client not found in database"
        assert "clarity.read" in persisted_client.scopes, "clarity.read not persisted in DB"


# ============================================================================
# AUTHORIZATION TESTS
# ============================================================================

class TestAuthorizationAcceptsClarityScope:
    """Tests that /authorize endpoint accepts clarity scopes."""

    @pytest.mark.asyncio
    async def test_authorize_accepts_clarity_write_scope(
        self,
        client,
        clarity_test_client: dict
    ):
        """
        GET /oauth/pg/authorize with scope=clarity.write should render
        consent page (200 OK) for clients registered with that scope.
        """
        _, code_challenge = generate_pkce_pair()  # verifier not needed for this test

        response = await client.get(
            "/oauth/pg/authorize",
            params={
                "response_type": "code",
                "client_id": clarity_test_client["client_id"],
                "redirect_uri": clarity_test_client["redirect_uri"],
                "scope": "clarity.write",
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "state": "test-state"
            },
            follow_redirects=False
        )

        # Should render consent page, not redirect with error
        assert response.status_code == 200
        # Should contain scope description for clarity.write
        assert b"clarity" in response.content.lower() or b"cluster" in response.content.lower()

    @pytest.mark.asyncio
    async def test_authorize_accepts_clarity_read_scope(
        self,
        client,
        clarity_test_client: dict
    ):
        """
        GET /oauth/pg/authorize with scope=clarity.read should render
        consent page (200 OK) for clients registered with that scope.
        """
        _, code_challenge = generate_pkce_pair()  # verifier not needed for this test

        response = await client.get(
            "/oauth/pg/authorize",
            params={
                "response_type": "code",
                "client_id": clarity_test_client["client_id"],
                "redirect_uri": clarity_test_client["redirect_uri"],
                "scope": "clarity.read",
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "state": "test-state"
            },
            follow_redirects=False
        )

        # Should render consent page, not redirect with error
        assert response.status_code == 200
        # Should contain scope description for clarity.read
        assert b"clarity" in response.content.lower() or b"cluster" in response.content.lower() or b"view" in response.content.lower()

    @pytest.mark.asyncio
    async def test_authorize_rejects_unregistered_scope(
        self,
        client,
        focused_only_client: dict
    ):
        """
        GET /oauth/pg/authorize with scope=clarity.write should fail
        for clients NOT registered with clarity.write scope.
        """
        _, code_challenge = generate_pkce_pair()  # verifier not needed for this test

        response = await client.get(
            "/oauth/pg/authorize",
            params={
                "response_type": "code",
                "client_id": focused_only_client["client_id"],
                "redirect_uri": focused_only_client["redirect_uri"],
                "scope": "clarity.write",
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "state": "test-state"
            },
            follow_redirects=False
        )

        # Should redirect with invalid_scope error
        assert response.status_code == 302
        location = response.headers.get("location", "")
        assert "error=invalid_scope" in location


# ============================================================================
# TOKEN ISSUANCE TESTS
# ============================================================================

class TestTokenExchangeWithClarityScope:
    """Tests token exchange includes clarity.write in issued JWT."""

    @pytest.mark.asyncio
    async def test_token_exchange_includes_clarity_scope(
        self,
        client,
        async_session: AsyncSession,
        clarity_test_client: dict
    ):
        """
        Token exchange with clarity.write scope should result in
        JWT with clarity.write in the scope claim.

        NOTE: This test inserts an auth code directly to test token issuance
        in isolation. The authorize endpoint acceptance is tested separately
        in TestAuthorizationAcceptsClarityScope.
        """
        from backend.core.models import CoreUser

        code_verifier, code_challenge = generate_pkce_pair()

        # Create test user
        user = CoreUser(chatgpt_user_id="test-clarity-user")
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)

        # Create authorization code directly (simulating consent approval)
        auth_code = OAuthAuthorizationCode(
            code="test-clarity-auth-code",
            client_id=clarity_test_client["client_id"],
            redirect_uri=clarity_test_client["redirect_uri"],
            scope=["clarity.write"],  # Request clarity.write scope
            code_challenge=code_challenge,
            code_challenge_method="S256",
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            used=False
        )
        async_session.add(auth_code)
        await async_session.commit()

        # Exchange code for token
        response = await client.post(
            "/oauth/pg/token",
            data={
                "grant_type": "authorization_code",
                "code": "test-clarity-auth-code",
                "redirect_uri": clarity_test_client["redirect_uri"],
                "client_id": clarity_test_client["client_id"],
                "code_verifier": code_verifier
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Verify scope in response
        assert "scope" in data
        assert "clarity.write" in data["scope"]

        # Decode JWT and verify scope claim
        # NOTE: Signature and claim validation (iss, aud, azp) are covered by
        # OAuth system tests; this test only checks scope propagation.
        access_token = data["access_token"]
        decoded = jwt.decode(access_token, options={"verify_signature": False})

        assert "scope" in decoded
        assert "clarity.write" in decoded["scope"]
