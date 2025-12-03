"""
OAuth Revocation Integration Tests (Increment 16).

Tests the revocation endpoint functionality:
5.1. /oauth/focused/revoke revokes access + refresh tokens
5.2. Revoked access token → protected endpoint fails
5.3. Revoked refresh token → cannot refresh

Also covers:
- Database state verification (9.3)

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
from backend.core.oauth_provider.models import OAuthAccessToken
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
    """Create a test user for revocation tests."""
    user = CoreUser(
        chatgpt_user_id=f"test-chatgpt-user-revoke-{uuid4().hex[:8]}"
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def oauth_client(async_session: AsyncSession) -> dict:
    """Create a test OAuth client."""
    client_id = f"focused-client-revoke-{uuid4().hex[:8]}"
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
        provider_metadata={"client_name": "Revoke Test Client"}
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
    Get a valid access token and refresh token for testing revocation.
    """
    code_verifier, code_challenge = generate_pkce_pair("revoke-fixture-verifier")

    code = await create_authorization_code(
        db=async_session,
        user_id=str(test_user.id),
        client_id=oauth_client["client_id"],
        code_challenge=code_challenge,
        code_challenge_method="S256",
        redirect_uri=oauth_client["redirect_uri"],
        scope="focused.read focused.write",
        correlation_id="revoke-fixture"
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
    data["client_id"] = oauth_client["client_id"]
    data["user_id"] = str(test_user.id)
    return data


# ============================================================================
# TEST CLASS: REVOCATION ENDPOINT (5.1 - 5.3)
# ============================================================================

class TestRevocationEndpoint:
    """Test token revocation functionality."""

    @pytest.mark.asyncio
    async def test_revoke_access_token_happy_path(
        self,
        client: AsyncClient,
        token_response: dict,
        oauth_client: dict
    ):
        """
        5.1. /oauth/focused/revoke revokes access token

        POST /oauth/focused/revoke with access token
        Expect: 200 OK + success=true
        """
        response = await client.post(
            "/oauth/focused/revoke",
            data={
                "token": token_response["access_token"],
                "client_id": oauth_client["client_id"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        # RFC 7009: Always return 200
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_revoke_refresh_token_happy_path(
        self,
        client: AsyncClient,
        token_response: dict,
        oauth_client: dict
    ):
        """
        5.1. /oauth/focused/revoke revokes refresh token

        POST /oauth/focused/revoke with refresh token
        Expect: 200 OK + success=true
        """
        response = await client.post(
            "/oauth/focused/revoke",
            data={
                "token": token_response["refresh_token"],
                "client_id": oauth_client["client_id"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_revoke_unknown_token_returns_200(
        self,
        client: AsyncClient,
        oauth_client: dict
    ):
        """
        RFC 7009: Revocation of unknown tokens should return 200.

        This prevents token enumeration attacks.
        """
        response = await client.post(
            "/oauth/focused/revoke",
            data={
                "token": "this-token-does-not-exist",
                "client_id": oauth_client["client_id"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        # Must return 200 per RFC 7009
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_revoke_missing_token_fails(
        self,
        client: AsyncClient,
        oauth_client: dict
    ):
        """
        Revocation without token must fail with 422.
        """
        response = await client.post(
            "/oauth/focused/revoke",
            data={
                "client_id": oauth_client["client_id"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert response.status_code == 422  # FastAPI validation error

    @pytest.mark.asyncio
    async def test_revoke_missing_client_id_fails(
        self,
        client: AsyncClient,
        token_response: dict
    ):
        """
        Revocation without client_id must fail with 422.
        """
        response = await client.post(
            "/oauth/focused/revoke",
            data={
                "token": token_response["access_token"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert response.status_code == 422  # FastAPI validation error


# ============================================================================
# TEST CLASS: REVOKED TOKEN BEHAVIOR (5.2 - 5.3)
# ============================================================================

class TestRevokedTokenBehavior:
    """Test behavior when using revoked tokens."""

    @pytest.mark.asyncio
    async def test_revoked_access_token_invalidates_refresh_token(
        self,
        client: AsyncClient,
        token_response: dict,
        oauth_client: dict
    ):
        """
        5.2. Revoked access token → refresh token must fail

        Revoking an access token marks the underlying DB token record as revoked.
        Since access + refresh tokens share the same DB row, refreshing must fail.
        """
        access_token = token_response["access_token"]
        refresh_token = token_response["refresh_token"]

        # Revoke the access token
        revoke_response = await client.post(
            "/oauth/focused/revoke",
            data={
                "token": access_token,
                "client_id": oauth_client["client_id"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert revoke_response.status_code == 200

        # The associated refresh token should now fail
        refresh_response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": oauth_client["client_id"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        # OAuth 2.1: invalid_grant returns 400 Bad Request
        assert refresh_response.status_code == 400
        data = refresh_response.json()
        assert data["error"] == "invalid_grant"

    @pytest.mark.asyncio
    async def test_revoked_refresh_token_cannot_refresh(
        self,
        client: AsyncClient,
        token_response: dict,
        oauth_client: dict
    ):
        """
        5.3. Revoked refresh token → cannot refresh

        After revocation, refresh token should fail with invalid_grant.
        """
        refresh_token = token_response["refresh_token"]

        # Revoke the token
        revoke_response = await client.post(
            "/oauth/focused/revoke",
            data={
                "token": refresh_token,
                "client_id": oauth_client["client_id"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert revoke_response.status_code == 200

        # Try to use revoked refresh token
        refresh_response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": oauth_client["client_id"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        # OAuth 2.1: invalid_grant returns 400 Bad Request
        assert refresh_response.status_code == 400
        data = refresh_response.json()
        assert data["error"] == "invalid_grant"


# ============================================================================
# TEST CLASS: DATABASE STATE VERIFICATION (9.3)
# ============================================================================

class TestRevocationDatabaseState:
    """Test that revocation updates database correctly."""

    @pytest.mark.asyncio
    async def test_revocation_sets_revoked_flag(
        self,
        client: AsyncClient,
        token_response: dict,
        async_session: AsyncSession,
        oauth_client: dict
    ):
        """
        9.3. Revocation flips revoked flag

        After /revoke:
        - oauth_access_tokens.revoked = TRUE
        - revoked_at timestamp set
        """
        # Get jti from access token
        payload = jwt.decode(
            token_response["access_token"],
            options={"verify_signature": False}
        )
        jti = payload["jti"]

        # Verify token is not revoked before
        await async_session.rollback()
        result = await async_session.execute(
            select(OAuthAccessToken).where(OAuthAccessToken.jti == jti)
        )
        token_before = result.scalar_one()
        assert token_before.revoked is False
        assert token_before.revoked_at is None

        # Revoke the access token
        revoke_response = await client.post(
            "/oauth/focused/revoke",
            data={
                "token": token_response["access_token"],
                "client_id": oauth_client["client_id"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert revoke_response.status_code == 200

        # Verify token is revoked after
        await async_session.rollback()
        result = await async_session.execute(
            select(OAuthAccessToken).where(OAuthAccessToken.jti == jti)
        )
        token_after = result.scalar_one()
        assert token_after.revoked is True
        assert token_after.revoked_at is not None

    @pytest.mark.asyncio
    async def test_revocation_by_refresh_token_revokes_record(
        self,
        client: AsyncClient,
        token_response: dict,
        async_session: AsyncSession,
        oauth_client: dict
    ):
        """
        Revoking by refresh token should also revoke the token record.
        """
        # Get jti from access token
        payload = jwt.decode(
            token_response["access_token"],
            options={"verify_signature": False}
        )
        jti = payload["jti"]

        # Revoke using refresh token
        revoke_response = await client.post(
            "/oauth/focused/revoke",
            data={
                "token": token_response["refresh_token"],
                "client_id": oauth_client["client_id"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert revoke_response.status_code == 200

        # Verify token record is revoked
        await async_session.rollback()
        result = await async_session.execute(
            select(OAuthAccessToken).where(OAuthAccessToken.jti == jti)
        )
        token_after = result.scalar_one()
        assert token_after.revoked is True


# ============================================================================
# TEST CLASS: MULTIPLE TOKENS REVOCATION
# ============================================================================

class TestMultipleTokensRevocation:
    """Test revocation behavior with multiple tokens."""

    @pytest.mark.asyncio
    async def test_revoke_does_not_affect_other_users_tokens(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        oauth_client: dict
    ):
        """
        Revoking one user's token should not affect another user's tokens.
        """
        # Create two users with tokens
        user1 = CoreUser(chatgpt_user_id=f"user1-{uuid4().hex[:8]}")
        user2 = CoreUser(chatgpt_user_id=f"user2-{uuid4().hex[:8]}")
        async_session.add_all([user1, user2])
        await async_session.commit()

        # Get tokens for both users
        tokens = []
        for user in [user1, user2]:
            code_verifier, code_challenge = generate_pkce_pair(f"multi-user-{user.id}")
            code = await create_authorization_code(
                db=async_session,
                user_id=str(user.id),
                client_id=oauth_client["client_id"],
                code_challenge=code_challenge,
                code_challenge_method="S256",
                redirect_uri=oauth_client["redirect_uri"],
                scope="focused.read",
                correlation_id=f"multi-user-{user.id}"
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
            tokens.append(response.json())

        user1_token = tokens[0]
        user2_token = tokens[1]

        # Revoke user1's token
        await client.post(
            "/oauth/focused/revoke",
            data={
                "token": user1_token["access_token"],
                "client_id": oauth_client["client_id"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        # User1's refresh token should now fail
        user1_refresh_response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": user1_token["refresh_token"],
                "client_id": oauth_client["client_id"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert user1_refresh_response.status_code == 400
        assert user1_refresh_response.json()["error"] == "invalid_grant"

        # User2's refresh token should still work
        user2_refresh_response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": user2_token["refresh_token"],
                "client_id": oauth_client["client_id"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert user2_refresh_response.status_code == 200
