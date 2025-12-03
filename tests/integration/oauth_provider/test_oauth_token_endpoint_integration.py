"""
OAuth Token Endpoint Integration Tests (Increment 16).

Tests the token endpoint functionality:
2.1. Authorization Code → Token (Happy Path)
2.2. Refresh Token → New Access Token (Happy Path)
2.3. Refresh Token – expired
2.4. Refresh Token – replay use
2.5. Refresh Token – wrong client_id

Also covers:
- Token validation (3.1 - 3.4)
- Database state verification (9.2)

Test framework: pytest
Client: httpx.AsyncClient
Database: test DB with migrations applied
"""

import pytest
import pytest_asyncio
import base64
import hashlib
import jwt
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.models import CoreConnection, CoreUser
from backend.core.encryption import encrypt_token
from backend.core.oauth_provider.models import OAuthAuthorizationCode, OAuthAccessToken
from backend.core.oauth_provider.services.consent_service import create_authorization_code


# ============================================================================
# FIXTURES
# ============================================================================

def generate_pkce_pair(seed: str = "test-verifier") -> tuple[str, str]:
    """Generate a valid PKCE code_verifier and code_challenge pair."""
    code_verifier = base64.urlsafe_b64encode(
        hashlib.sha256(seed.encode()).digest()
    ).rstrip(b"=").decode("utf-8")

    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode("utf-8")

    return code_verifier, code_challenge


@pytest_asyncio.fixture
async def test_user(async_session: AsyncSession) -> CoreUser:
    """Create a test user for token tests."""
    user = CoreUser(
        chatgpt_user_id=f"test-chatgpt-user-token-{uuid4().hex[:8]}"
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def oauth_client(async_session: AsyncSession) -> dict:
    """Create a test OAuth client."""
    client_id = f"focused-client-token-{uuid4().hex[:8]}"
    client_secret = f"test-secret-{uuid4().hex[:16]}"
    redirect_uri = "https://chat.openai.com/aip/callback"

    client = CoreConnection(
        user_id=None,
        provider="Test OAuth Client",
        connection_type="oauth_provider",
        client_id=client_id,
        client_secret_enc=encrypt_token(client_secret),
        redirect_uris=[redirect_uri],
        grant_types=["authorization_code", "refresh_token"],
        encrypted_access_token="",
        scopes=["focused.read", "focused.write", "focused.notify"],
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        provider_metadata={"client_name": "Token Test Client"}
    )
    async_session.add(client)
    await async_session.commit()

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri
    }


@pytest_asyncio.fixture
async def oauth_client_b(async_session: AsyncSession) -> dict:
    """Create a second OAuth client for cross-client tests."""
    client_id = f"focused-client-other-{uuid4().hex[:8]}"
    client_secret = f"test-secret-other-{uuid4().hex[:16]}"
    redirect_uri = "https://other-app.example.com/callback"

    client = CoreConnection(
        user_id=None,
        provider="Other OAuth Client",
        connection_type="oauth_provider",
        client_id=client_id,
        client_secret_enc=encrypt_token(client_secret),
        redirect_uris=[redirect_uri],
        grant_types=["authorization_code", "refresh_token"],
        encrypted_access_token="",
        scopes=["focused.read", "focused.write"],
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        provider_metadata={"client_name": "Other Test Client"}
    )
    async_session.add(client)
    await async_session.commit()

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri
    }


@pytest_asyncio.fixture
async def token_response(
    client: AsyncClient,
    async_session: AsyncSession,
    test_user: CoreUser,
    oauth_client: dict
) -> dict:
    """
    Get a valid access token and refresh token for testing.

    Returns the full token response including access_token and refresh_token.
    """
    code_verifier, code_challenge = generate_pkce_pair("token-fixture-verifier")

    # Create authorization code
    code = await create_authorization_code(
        db=async_session,
        user_id=str(test_user.id),
        client_id=oauth_client["client_id"],
        code_challenge=code_challenge,
        code_challenge_method="S256",
        redirect_uri=oauth_client["redirect_uri"],
        scope="focused.read focused.write",
        correlation_id="token-fixture"
    )

    # Exchange for tokens
    response = await client.post(
        "/oauth/focused/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": code_verifier,
            "client_id": oauth_client["client_id"],
            "redirect_uri": oauth_client["redirect_uri"]
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )

    assert response.status_code == 200
    data = response.json()
    data["client_id"] = oauth_client["client_id"]
    data["user_id"] = str(test_user.id)
    return data


# ============================================================================
# TEST CLASS: TOKEN ENDPOINT - AUTHORIZATION CODE GRANT (2.1)
# ============================================================================

class TestTokenEndpointAuthCodeGrant:
    """Test token endpoint with authorization_code grant."""

    @pytest.mark.asyncio
    async def test_token_exchange_happy_path(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user: CoreUser,
        oauth_client: dict
    ):
        """
        2.1. Authorization Code → Token (Happy Path)

        Expect:
        - access_token is returned (JWT, RS256 signed)
        - refresh_token returned (opaque random)
        - DB: row in oauth_access_tokens stored
        - Claims: sub=user_id, scope, exp=1h
        """
        code_verifier, code_challenge = generate_pkce_pair("happy-token-verifier")

        # Create authorization code
        code = await create_authorization_code(
            db=async_session,
            user_id=str(test_user.id),
            client_id=oauth_client["client_id"],
            code_challenge=code_challenge,
            code_challenge_method="S256",
            redirect_uri=oauth_client["redirect_uri"],
            scope="focused.read focused.write",
            correlation_id="happy-token-test"
        )

        # Exchange for tokens
        response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": code_verifier,
                "client_id": oauth_client["client_id"],
                "redirect_uri": oauth_client["redirect_uri"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "Bearer"
        assert "expires_in" in data
        assert "scope" in data

        # Verify JWT structure (header.payload.signature)
        access_token = data["access_token"]
        parts = access_token.split(".")
        assert len(parts) == 3, "Access token should be a JWT with 3 parts"

        # Decode JWT header to verify RS256
        header = jwt.get_unverified_header(access_token)
        assert header["alg"] == "RS256"
        assert "kid" in header

        # Decode JWT payload (unverified) to check claims
        payload = jwt.decode(access_token, options={"verify_signature": False})
        assert payload["sub"] == str(test_user.id)
        assert "scope" in payload
        assert "exp" in payload
        assert "iat" in payload
        assert "jti" in payload

    @pytest.mark.asyncio
    async def test_token_missing_grant_type(
        self,
        client: AsyncClient,
        oauth_client: dict
    ):
        """Token request without grant_type must fail with 422."""
        response = await client.post(
            "/oauth/focused/token",
            data={
                "code": "some-code",
                "client_id": oauth_client["client_id"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert response.status_code == 422  # FastAPI validation error

    @pytest.mark.asyncio
    async def test_token_unsupported_grant_type(
        self,
        client: AsyncClient,
        oauth_client: dict
    ):
        """Token request with unsupported grant_type must fail."""
        response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "client_credentials",
                "client_id": oauth_client["client_id"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "unsupported_grant_type"


# ============================================================================
# TEST CLASS: TOKEN ENDPOINT - REFRESH TOKEN GRANT (2.2 - 2.5)
# ============================================================================

class TestTokenEndpointRefreshGrant:
    """Test token endpoint with refresh_token grant."""

    @pytest.mark.asyncio
    async def test_refresh_token_happy_path(
        self,
        client: AsyncClient,
        token_response: dict,
        oauth_client: dict
    ):
        """
        2.2. Refresh Token → New Access Token (Happy Path)

        Expect:
        - New access token
        - New refresh token (rotation)
        - Old refresh token marked revoked
        """
        original_refresh_token = token_response["refresh_token"]
        original_access_token = token_response["access_token"]

        # Refresh the token
        response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": original_refresh_token,
                "client_id": oauth_client["client_id"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert response.status_code == 200
        data = response.json()

        # Verify new tokens are different
        assert data["access_token"] != original_access_token
        assert data["refresh_token"] != original_refresh_token

        # Verify response structure
        assert data["token_type"] == "Bearer"
        assert "expires_in" in data

    @pytest.mark.asyncio
    async def test_refresh_token_expired(
        self,
        client: AsyncClient,
        token_response: dict,
        async_session: AsyncSession,
        oauth_client: dict
    ):
        """
        2.3. Refresh Token – expired

        Set refresh_token_expires_at = now() - 1s
        Expect: 401 invalid_grant + "refresh_token_expired"
        """
        # Find the token record and expire it
        # First, we need to get the jti from the access token
        payload = jwt.decode(
            token_response["access_token"],
            options={"verify_signature": False}
        )
        jti = payload["jti"]

        # Expire the refresh token
        await async_session.execute(
            update(OAuthAccessToken)
            .where(OAuthAccessToken.jti == jti)
            .values(refresh_token_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
        await async_session.commit()

        # Try to refresh
        response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": token_response["refresh_token"],
                "client_id": oauth_client["client_id"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        # OAuth 2.1 spec: invalid_grant returns 400 Bad Request
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "invalid_grant"
        assert "expired" in data["error_description"].lower()

    @pytest.mark.asyncio
    async def test_refresh_token_replay_use(
        self,
        client: AsyncClient,
        token_response: dict,
        oauth_client: dict
    ):
        """
        2.4. Refresh Token – replay use

        Steps:
        - Exchange refresh_token → works
        - Exchange same token again → expect 400 invalid_grant + "revoked"
        """
        refresh_token = token_response["refresh_token"]

        # First refresh should succeed
        response1 = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": oauth_client["client_id"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert response1.status_code == 200

        # Second refresh with same token should fail (rotation)
        response2 = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": oauth_client["client_id"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        # OAuth 2.1 spec: invalid_grant returns 400 Bad Request
        assert response2.status_code == 400
        data = response2.json()
        assert data["error"] == "invalid_grant"
        assert "revoked" in data["error_description"].lower()

    @pytest.mark.asyncio
    async def test_refresh_token_wrong_client_id(
        self,
        client: AsyncClient,
        token_response: dict,
        oauth_client_b: dict
    ):
        """
        2.5. Refresh Token – wrong client_id

        Submit refresh_token with wrong client_id
        Expect 400 invalid_grant (client_id mismatch)
        """
        response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": token_response["refresh_token"],
                "client_id": oauth_client_b["client_id"]  # Wrong client
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        # OAuth 2.1 spec: invalid_grant returns 400 Bad Request
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "invalid_grant"

    @pytest.mark.asyncio
    async def test_refresh_token_invalid(
        self,
        client: AsyncClient,
        oauth_client: dict
    ):
        """Refresh with non-existent token fails."""
        response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": "this-refresh-token-does-not-exist",
                "client_id": oauth_client["client_id"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        # OAuth 2.1 spec: invalid_grant returns 400 Bad Request
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "invalid_grant"


# ============================================================================
# TEST CLASS: JWT TOKEN VALIDATION (3.1 - 3.4)
# ============================================================================

class TestJWTTokenValidation:
    """Test JWT access token structure and validation."""

    @pytest.mark.asyncio
    async def test_access_token_valid_structure(
        self,
        token_response: dict
    ):
        """
        3.1. Valid access token structure

        Verify JWT is properly formed with correct claims.
        """
        access_token = token_response["access_token"]

        # Verify JWT structure
        header = jwt.get_unverified_header(access_token)
        assert header["alg"] == "RS256"
        assert header["typ"] == "JWT"
        assert "kid" in header

        # Verify payload claims
        payload = jwt.decode(access_token, options={"verify_signature": False})
        assert "sub" in payload  # user_id
        assert "scope" in payload
        assert "exp" in payload
        assert "iat" in payload
        assert "jti" in payload
        assert "iss" in payload

    @pytest.mark.asyncio
    async def test_access_token_kid_in_jwks(
        self,
        client: AsyncClient,
        token_response: dict
    ):
        """
        Verify the token's kid is present in JWKS.
        """
        access_token = token_response["access_token"]
        header = jwt.get_unverified_header(access_token)
        token_kid = header["kid"]

        # Fetch JWKS
        response = await client.get("/oauth/focused/jwks")
        assert response.status_code == 200
        jwks = response.json()

        # Find matching kid
        kids = [key["kid"] for key in jwks["keys"]]
        assert token_kid in kids, f"Token kid {token_kid} not found in JWKS {kids}"

    @pytest.mark.asyncio
    async def test_access_token_expiry_approximately_one_hour(
        self,
        token_response: dict
    ):
        """
        Verify access token expires in approximately 1 hour.
        """
        access_token = token_response["access_token"]
        payload = jwt.decode(access_token, options={"verify_signature": False})

        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        iat = datetime.fromtimestamp(payload["iat"], tz=timezone.utc)

        token_lifetime = exp - iat
        # Should be approximately 1 hour (3600 seconds)
        assert timedelta(minutes=55) < token_lifetime < timedelta(minutes=65)


# ============================================================================
# TEST CLASS: DATABASE STATE VERIFICATION (9.2)
# ============================================================================

class TestTokenDatabaseState:
    """Test that tokens are stored correctly in database."""

    @pytest.mark.asyncio
    async def test_access_token_stored_correctly(
        self,
        async_session: AsyncSession,
        test_user: CoreUser,
        oauth_client: dict,
        client: AsyncClient
    ):
        """
        9.2. Access token inserts correct row

        Check:
        - encrypted refresh token stored
        - expires_at = now()+1h
        - jti unique
        """
        code_verifier, code_challenge = generate_pkce_pair("db-token-verifier")

        # Create and exchange authorization code
        code = await create_authorization_code(
            db=async_session,
            user_id=str(test_user.id),
            client_id=oauth_client["client_id"],
            code_challenge=code_challenge,
            code_challenge_method="S256",
            redirect_uri=oauth_client["redirect_uri"],
            scope="focused.read",
            correlation_id="db-token-test"
        )

        response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": code_verifier,
                "client_id": oauth_client["client_id"],
                "redirect_uri": oauth_client["redirect_uri"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert response.status_code == 200
        data = response.json()

        # Get jti from access token
        payload = jwt.decode(data["access_token"], options={"verify_signature": False})
        jti = payload["jti"]

        # Fetch token from database
        await async_session.rollback()  # Clear cache
        result = await async_session.execute(
            select(OAuthAccessToken).where(OAuthAccessToken.jti == jti)
        )
        token_record = result.scalar_one()

        # Verify stored data
        assert token_record.user_id == test_user.id
        assert token_record.client_id == oauth_client["client_id"]
        assert token_record.token_type == "Bearer"
        assert token_record.revoked is False

        # Refresh token should be stored (encrypted and hashed)
        assert token_record.refresh_token_enc is not None
        assert token_record.refresh_token_hash is not None

        # Verify expiration times
        now = datetime.now(timezone.utc)
        assert token_record.expires_at > now
        assert token_record.refresh_token_expires_at > now

        # Access token expires in ~1 hour
        access_token_lifetime = token_record.expires_at - now
        assert timedelta(minutes=55) < access_token_lifetime < timedelta(hours=2)

    @pytest.mark.asyncio
    async def test_refresh_rotation_creates_new_row(
        self,
        client: AsyncClient,
        token_response: dict,
        async_session: AsyncSession,
        oauth_client: dict
    ):
        """
        Refresh token rotation should create a new token row.
        """
        original_jti = jwt.decode(
            token_response["access_token"],
            options={"verify_signature": False}
        )["jti"]

        # Refresh the token
        response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": token_response["refresh_token"],
                "client_id": oauth_client["client_id"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert response.status_code == 200
        new_jti = jwt.decode(
            response.json()["access_token"],
            options={"verify_signature": False}
        )["jti"]

        # Verify both tokens exist in DB
        await async_session.rollback()

        result1 = await async_session.execute(
            select(OAuthAccessToken).where(OAuthAccessToken.jti == original_jti)
        )
        old_token = result1.scalar_one()

        result2 = await async_session.execute(
            select(OAuthAccessToken).where(OAuthAccessToken.jti == new_jti)
        )
        new_token = result2.scalar_one()

        # Old token should be revoked
        assert old_token.revoked is True
        assert old_token.revoked_at is not None

        # New token should be active
        assert new_token.revoked is False
        assert new_token.jti != original_jti
