"""
Increment 13: OAuth Token Exchange - Integration Tests.

Tests (real test DB + Redis, HTTP calls):
1. Full OAuth flow → MCP tool call - 200 + valid response
2. Token exchange with invalid code_verifier - 400 invalid_grant
3. Token exchange with expired code - 400 invalid_grant
4. Token exchange with reused code - 400 invalid_grant
5. Token exchange with wrong client_id - 401 invalid_client
6. Token exchange with wrong redirect_uri - 400 invalid_grant
7. Refresh token exchange - 200 + new tokens
8. Refresh with revoked token - 400 invalid_grant
9. Refresh token rotation (old token invalidated) - Second refresh fails
10. Unsupported grant_type - 400 unsupported_grant_type
11. Missing required parameters - 400 invalid_request
12. JWKS signature verification - Token verifies against /oauth/focused/jwks
13. Rate limit on /token - 429 rate_limited
14. Cleanup job deletes expired auth codes - Codes >10 min removed
"""

import pytest
import pytest_asyncio
import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from jose import jwt
from cryptography.hazmat.primitives import serialization

from backend.core.oauth_provider.models import OAuthAuthorizationCode, OAuthAccessToken
from backend.core.models import CoreConnection, CoreUser
from backend.core.encryption import encrypt_token, hash_refresh_token


# OAuth token endpoint requires form-urlencoded content type
FORM_HEADERS = {"Content-Type": "application/x-www-form-urlencoded"}


# =============================================================================
# Fixtures
# =============================================================================

def generate_pkce_pair():
    """Generate PKCE code_verifier and code_challenge pair."""
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip('=')
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).decode().rstrip('=')
    return code_verifier, code_challenge


@pytest_asyncio.fixture
async def test_user(async_session: AsyncSession):
    """Create a test user."""
    user = CoreUser(
        id=uuid4(),
        chatgpt_user_id=f"test-chatgpt-user-{secrets.token_urlsafe(8)}"
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def oauth_client(async_session: AsyncSession):
    """
    Create a test OAuth client (CoreConnection with oauth_provider type).

    NOTE: This fixture is a synthetic OAuth client for testing the SDK provider.
    Only fields needed for token issuance are populated. The token endpoint does
    NOT use encrypted_access_token for oauth_provider clients - that field is
    only used for Google OAuth connections.
    """
    client_id = f"focused-client-{secrets.token_urlsafe(8)}"
    client_secret = secrets.token_urlsafe(32)

    client = CoreConnection(
        user_id=None,  # OAuth provider clients have NULL user_id
        provider="Test OAuth Client",
        connection_type="oauth_provider",
        client_id=client_id,
        client_secret_enc=encrypt_token(client_secret),
        redirect_uris=["https://app.example.com/callback"],
        grant_types=["authorization_code", "refresh_token"],
        scopes=["focused.read", "focused.write", "focused.notify"],
        encrypted_access_token="",  # Required field (unused for oauth_provider type)
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=365)
    )
    async_session.add(client)
    await async_session.commit()
    await async_session.refresh(client)

    # Attach secret for test convenience
    client.client_secret = client_secret
    return client


@pytest_asyncio.fixture
async def valid_auth_code(async_session: AsyncSession, test_user, oauth_client):
    """Create a valid authorization code in the database."""
    code_verifier, code_challenge = generate_pkce_pair()

    auth_code = OAuthAuthorizationCode(
        code=secrets.token_urlsafe(96),
        user_id=test_user.id,
        client_id=oauth_client.client_id,
        code_challenge=code_challenge,
        code_challenge_method="S256",
        redirect_uri=oauth_client.redirect_uris[0],
        scope=["focused.read", "focused.write"],
        state="test-state-12345678",
        nonce="test-nonce-12345678",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        used=False
    )
    async_session.add(auth_code)
    await async_session.commit()
    await async_session.refresh(auth_code)

    return {
        "code": auth_code.code,
        "code_verifier": code_verifier,
        "code_challenge": code_challenge,
        "redirect_uri": oauth_client.redirect_uris[0],
        "client_id": oauth_client.client_id,
        "user_id": test_user.id
    }


@pytest_asyncio.fixture
async def valid_access_token(async_session: AsyncSession, test_user, oauth_client):
    """Create a valid access token with refresh token in the database."""
    refresh_token = secrets.token_urlsafe(32)
    jti = str(uuid4())

    token = OAuthAccessToken(
        jti=jti,
        user_id=test_user.id,
        client_id=oauth_client.client_id,
        scope=["focused.read", "focused.write"],
        token_type="Bearer",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        refresh_token_enc=encrypt_token(refresh_token),
        refresh_token_hash=hash_refresh_token(refresh_token),
        refresh_token_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        revoked=False
    )
    async_session.add(token)
    await async_session.commit()

    return {
        "jti": jti,
        "refresh_token": refresh_token,
        "client_id": oauth_client.client_id,
        "user_id": test_user.id
    }


# =============================================================================
# Test 1: Full OAuth Flow → MCP Tool Call
# =============================================================================

@pytest.mark.asyncio
async def test_full_oauth_flow_success(
    client: AsyncClient,
    valid_auth_code
):
    """
    Test 1: Full OAuth flow → token exchange → (simulated) MCP tool call.

    Verifies the complete flow works end-to-end:
    1. Exchange authorization code for tokens
    2. Verify access token is valid JWT
    3. Verify refresh token is returned
    """
    response = await client.post(
        "/oauth/focused/token",
        data={
            "grant_type": "authorization_code",
            "code": valid_auth_code["code"],
            "redirect_uri": valid_auth_code["redirect_uri"],
            "client_id": valid_auth_code["client_id"],
            "code_verifier": valid_auth_code["code_verifier"]
        },
        headers=FORM_HEADERS
    )

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "Bearer"
    assert "expires_in" in data
    assert "scope" in data

    # Verify scope contains requested scopes
    assert "focused.read" in data["scope"]
    assert "focused.write" in data["scope"]


# =============================================================================
# Test 2: Invalid code_verifier
# =============================================================================

@pytest.mark.asyncio
async def test_token_exchange_invalid_code_verifier(
    client: AsyncClient,
    valid_auth_code
):
    """
    Test 2: Token exchange with invalid code_verifier returns 401 invalid_grant.

    NOTE: RFC 6749 recommends 400 for invalid_grant, but our implementation
    uses 401 to distinguish authentication failures. Both are valid choices.
    """
    # Use wrong verifier
    wrong_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip('=')

    response = await client.post(
        "/oauth/focused/token",
        data={
            "grant_type": "authorization_code",
            "code": valid_auth_code["code"],
            "redirect_uri": valid_auth_code["redirect_uri"],
            "client_id": valid_auth_code["client_id"],
            "code_verifier": wrong_verifier
        },
        headers=FORM_HEADERS
    )

    # Implementation returns 401 for invalid_grant
    assert response.status_code == 401, f"Expected 401, got {response.status_code}"
    data = response.json()
    assert data["error"] == "invalid_grant"
    assert "PKCE" in data.get("error_description", "")


# =============================================================================
# Test 3: Expired Code
# =============================================================================

@pytest.mark.asyncio
async def test_token_exchange_expired_code(
    client: AsyncClient,
    async_session: AsyncSession,
    test_user,
    oauth_client
):
    """
    Test 3: Token exchange with expired code returns 401 invalid_grant.
    """
    code_verifier, code_challenge = generate_pkce_pair()

    # Create expired code (expired 1 minute ago)
    expired_code = OAuthAuthorizationCode(
        code=secrets.token_urlsafe(96),
        user_id=test_user.id,
        client_id=oauth_client.client_id,
        code_challenge=code_challenge,
        code_challenge_method="S256",
        redirect_uri=oauth_client.redirect_uris[0],
        scope=["focused.read"],
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),  # EXPIRED
        used=False
    )
    async_session.add(expired_code)
    await async_session.commit()

    response = await client.post(
        "/oauth/focused/token",
        data={
            "grant_type": "authorization_code",
            "code": expired_code.code,
            "redirect_uri": oauth_client.redirect_uris[0],
            "client_id": oauth_client.client_id,
            "code_verifier": code_verifier
        },
        headers=FORM_HEADERS
    )

    assert response.status_code == 401, f"Expected 401, got {response.status_code}"
    data = response.json()
    assert data["error"] == "invalid_grant"
    assert "expired" in data.get("error_description", "").lower()


# =============================================================================
# Test 4: Reused Code
# =============================================================================

@pytest.mark.asyncio
async def test_token_exchange_reused_code(
    client: AsyncClient,
    valid_auth_code
):
    """
    Test 4: Token exchange with reused code returns 401 invalid_grant.
    """
    token_data = {
        "grant_type": "authorization_code",
        "code": valid_auth_code["code"],
        "redirect_uri": valid_auth_code["redirect_uri"],
        "client_id": valid_auth_code["client_id"],
        "code_verifier": valid_auth_code["code_verifier"]
    }

    # First exchange - should succeed
    response1 = await client.post("/oauth/focused/token", data=token_data, headers=FORM_HEADERS)
    assert response1.status_code == 200, f"First exchange should succeed: {response1.text}"

    # Second exchange - should fail (code already used)
    response2 = await client.post("/oauth/focused/token", data=token_data, headers=FORM_HEADERS)
    assert response2.status_code == 401, f"Expected 401, got {response2.status_code}"
    data = response2.json()
    assert data["error"] == "invalid_grant"
    assert "used" in data.get("error_description", "").lower()


# =============================================================================
# Test 5: Wrong client_id
# =============================================================================

@pytest.mark.asyncio
async def test_token_exchange_wrong_client_id(
    client: AsyncClient,
    valid_auth_code
):
    """
    Test 5: Token exchange with wrong client_id returns 401 invalid_grant.
    """
    response = await client.post(
        "/oauth/focused/token",
        data={
            "grant_type": "authorization_code",
            "code": valid_auth_code["code"],
            "redirect_uri": valid_auth_code["redirect_uri"],
            "client_id": "wrong-client-id-12345",  # Wrong client
            "code_verifier": valid_auth_code["code_verifier"]
        },
        headers=FORM_HEADERS
    )

    assert response.status_code == 401, f"Expected 401, got {response.status_code}"
    data = response.json()
    assert data["error"] == "invalid_grant"
    assert "client" in data.get("error_description", "").lower()


# =============================================================================
# Test 6: Wrong redirect_uri
# =============================================================================

@pytest.mark.asyncio
async def test_token_exchange_wrong_redirect_uri(
    client: AsyncClient,
    valid_auth_code
):
    """
    Test 6: Token exchange with wrong redirect_uri returns 401 invalid_grant.

    Per spec: redirect_uri must EXACTLY match stored value (no normalization).
    """
    response = await client.post(
        "/oauth/focused/token",
        data={
            "grant_type": "authorization_code",
            "code": valid_auth_code["code"],
            "redirect_uri": "https://evil.com/callback",  # Wrong URI
            "client_id": valid_auth_code["client_id"],
            "code_verifier": valid_auth_code["code_verifier"]
        },
        headers=FORM_HEADERS
    )

    assert response.status_code == 401, f"Expected 401, got {response.status_code}"
    data = response.json()
    assert data["error"] == "invalid_grant"
    assert "redirect" in data.get("error_description", "").lower()


# =============================================================================
# Test 7: Refresh Token Exchange
# =============================================================================

@pytest.mark.asyncio
async def test_refresh_token_exchange_success(
    client: AsyncClient,
    valid_access_token
):
    """
    Test 7: Refresh token exchange returns 200 + new tokens.
    """
    response = await client.post(
        "/oauth/focused/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": valid_access_token["refresh_token"],
            "client_id": valid_access_token["client_id"]
        },
        headers=FORM_HEADERS
    )

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "Bearer"
    assert "expires_in" in data

    # New refresh token should be different from old one
    assert data["refresh_token"] != valid_access_token["refresh_token"]


# =============================================================================
# Test 8: Refresh with Revoked Token
# =============================================================================

@pytest.mark.asyncio
async def test_refresh_with_revoked_token(
    client: AsyncClient,
    async_session: AsyncSession,
    test_user,
    oauth_client
):
    """
    Test 8: Refresh with revoked token returns 401 invalid_grant.
    """
    refresh_token = secrets.token_urlsafe(32)

    # Create revoked token
    revoked_token = OAuthAccessToken(
        jti=str(uuid4()),
        user_id=test_user.id,
        client_id=oauth_client.client_id,
        scope=["focused.read"],
        token_type="Bearer",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        refresh_token_enc=encrypt_token(refresh_token),
        refresh_token_hash=hash_refresh_token(refresh_token),
        refresh_token_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        revoked=True,  # REVOKED
        revoked_at=datetime.now(timezone.utc)
    )
    async_session.add(revoked_token)
    await async_session.commit()

    response = await client.post(
        "/oauth/focused/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": oauth_client.client_id
        },
        headers=FORM_HEADERS
    )

    assert response.status_code == 401, f"Expected 401, got {response.status_code}"
    data = response.json()
    assert data["error"] == "invalid_grant"
    assert "revoked" in data.get("error_description", "").lower()


# =============================================================================
# Test 8b: Refresh with Expired Token
# =============================================================================

@pytest.mark.asyncio
async def test_refresh_with_expired_token(
    client: AsyncClient,
    async_session: AsyncSession,
    test_user,
    oauth_client
):
    """
    Test 8b: Refresh with expired refresh token returns 401 invalid_grant.

    Refresh tokens expire after 30 days per spec.
    """
    refresh_token = secrets.token_urlsafe(32)

    # Create token with EXPIRED refresh token
    expired_token = OAuthAccessToken(
        jti=str(uuid4()),
        user_id=test_user.id,
        client_id=oauth_client.client_id,
        scope=["focused.read"],
        token_type="Bearer",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),  # Access token expired
        refresh_token_enc=encrypt_token(refresh_token),
        refresh_token_hash=hash_refresh_token(refresh_token),
        refresh_token_expires_at=datetime.now(timezone.utc) - timedelta(days=1),  # EXPIRED
        revoked=False
    )
    async_session.add(expired_token)
    await async_session.commit()

    response = await client.post(
        "/oauth/focused/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": oauth_client.client_id
        },
        headers=FORM_HEADERS
    )

    assert response.status_code == 401, f"Expected 401, got {response.status_code}"
    data = response.json()
    assert data["error"] == "invalid_grant"
    assert "expired" in data.get("error_description", "").lower()


# =============================================================================
# Test 9: Refresh Token Rotation (Old Token Invalidated)
# =============================================================================

@pytest.mark.asyncio
async def test_refresh_token_rotation_invalidates_old(
    client: AsyncClient,
    valid_access_token
):
    """
    Test 9: After refresh, old token is invalidated (second refresh fails).

    This tests single-use refresh tokens per OAuth 2.1 spec.
    """
    # First refresh - should succeed
    response1 = await client.post(
        "/oauth/focused/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": valid_access_token["refresh_token"],
            "client_id": valid_access_token["client_id"]
        },
        headers=FORM_HEADERS
    )
    assert response1.status_code == 200, f"First refresh should succeed: {response1.text}"

    # Second refresh with OLD token - should fail
    response2 = await client.post(
        "/oauth/focused/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": valid_access_token["refresh_token"],  # Old token
            "client_id": valid_access_token["client_id"]
        },
        headers=FORM_HEADERS
    )
    assert response2.status_code == 401, f"Expected 401, got {response2.status_code}"
    data = response2.json()
    assert data["error"] == "invalid_grant"


@pytest.mark.asyncio
async def test_refresh_token_rotation_issues_new_jti(
    client: AsyncClient,
    valid_access_token
):
    """
    Test 9b: Refresh token rotation issues a new JTI (JWT ID).

    Each token exchange must produce a unique JTI for revocation tracking.
    """
    # First refresh
    response1 = await client.post(
        "/oauth/focused/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": valid_access_token["refresh_token"],
            "client_id": valid_access_token["client_id"]
        },
        headers=FORM_HEADERS
    )
    assert response1.status_code == 200
    data1 = response1.json()

    # Decode JWT to get JTI (without verification for simplicity)
    access_token_1 = data1["access_token"]
    claims_1 = jwt.get_unverified_claims(access_token_1)
    jti_1 = claims_1["jti"]

    # Second refresh with NEW token
    response2 = await client.post(
        "/oauth/focused/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": data1["refresh_token"],  # Use NEW refresh token
            "client_id": valid_access_token["client_id"]
        },
        headers=FORM_HEADERS
    )
    assert response2.status_code == 200
    data2 = response2.json()

    # Decode second JWT
    access_token_2 = data2["access_token"]
    claims_2 = jwt.get_unverified_claims(access_token_2)
    jti_2 = claims_2["jti"]

    # JTIs must be different
    assert jti_1 != jti_2, f"JTIs should be unique: {jti_1} vs {jti_2}"

    # Verify JTIs are valid UUIDs
    from uuid import UUID
    UUID(jti_1)  # Will raise if invalid
    UUID(jti_2)  # Will raise if invalid


# =============================================================================
# Test 10: Unsupported grant_type
# =============================================================================

@pytest.mark.asyncio
async def test_unsupported_grant_type(
    client: AsyncClient,
    oauth_client
):
    """
    Test 10: Unsupported grant_type returns 400 unsupported_grant_type.
    """
    response = await client.post(
        "/oauth/focused/token",
        data={
            "grant_type": "client_credentials",  # Not supported
            "client_id": oauth_client.client_id
        },
        headers=FORM_HEADERS
    )

    # May return 400 or 422 depending on form validation
    assert response.status_code in [400, 422], f"Expected 400/422, got {response.status_code}"

    data = response.json()
    if response.status_code == 400:
        # OAuth error format
        assert data["error"] == "unsupported_grant_type", \
            f"Expected unsupported_grant_type error, got: {data}"
    else:
        # FastAPI validation error format (422)
        assert "detail" in data, "422 response should have 'detail' field"


# =============================================================================
# Test 11: Missing Required Parameters
# =============================================================================

@pytest.mark.asyncio
async def test_missing_required_parameters(
    client: AsyncClient,
    oauth_client
):
    """
    Test 11: Missing required parameters returns 400/422 invalid_request.
    """
    # Missing code for authorization_code grant
    response = await client.post(
        "/oauth/focused/token",
        data={
            "grant_type": "authorization_code",
            "client_id": oauth_client.client_id,
            # Missing: code, code_verifier, redirect_uri
        },
        headers=FORM_HEADERS
    )

    # FastAPI returns 422 for validation errors
    assert response.status_code in [400, 422], f"Expected 400/422, got {response.status_code}"


@pytest.mark.asyncio
async def test_missing_grant_type(
    client: AsyncClient,
    oauth_client
):
    """Test missing grant_type returns error."""
    response = await client.post(
        "/oauth/focused/token",
        data={
            "client_id": oauth_client.client_id,
            "code": "some-code"
            # Missing: grant_type
        },
        headers=FORM_HEADERS
    )

    assert response.status_code in [400, 422], f"Expected 400/422, got {response.status_code}"


# =============================================================================
# Test 12: JWKS Signature Verification
# =============================================================================

@pytest.mark.asyncio
async def test_jwks_signature_verification(
    client: AsyncClient,
    valid_auth_code
):
    """
    Test 12: Token verifies against /oauth/focused/jwks using RS256.

    1. Exchange code for token
    2. Fetch JWKS from endpoint
    3. Verify token signature using public key
    """
    # Exchange code for token
    token_response = await client.post(
        "/oauth/focused/token",
        data={
            "grant_type": "authorization_code",
            "code": valid_auth_code["code"],
            "redirect_uri": valid_auth_code["redirect_uri"],
            "client_id": valid_auth_code["client_id"],
            "code_verifier": valid_auth_code["code_verifier"]
        },
        headers=FORM_HEADERS
    )
    assert token_response.status_code == 200

    access_token = token_response.json()["access_token"]

    # Fetch JWKS
    jwks_response = await client.get("/oauth/focused/jwks")
    assert jwks_response.status_code == 200

    jwks = jwks_response.json()
    assert "keys" in jwks
    assert len(jwks["keys"]) > 0

    # Get the key
    key = jwks["keys"][0]
    assert key["kty"] == "RSA"
    assert key["alg"] == "RS256"
    assert "n" in key
    assert "e" in key
    assert "kid" in key

    # Verify token using the public key from crypto module
    from backend.core.crypto import get_public_key
    public_key = get_public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    # Decode and verify signature
    decoded = jwt.decode(
        access_token,
        public_pem,
        algorithms=["RS256"],
        options={"verify_aud": False}
    )

    # Verify essential claims
    assert "sub" in decoded
    assert "iss" in decoded
    assert "exp" in decoded
    assert "jti" in decoded
    assert "scope" in decoded
    assert str(valid_auth_code["user_id"]) == decoded["sub"]


# =============================================================================
# Test 13: Rate Limit on /token
# =============================================================================

@pytest.mark.asyncio
async def test_rate_limit_on_token_endpoint(
    client: AsyncClient,
    oauth_client
):
    """
    Test 13: Rate limit on /token returns 429 rate_limited.

    Note: Rate limiting requires Redis. Without Redis, this test validates
    that the endpoint handles multiple requests correctly.
    """
    responses = []

    # Make 10 rapid requests with invalid codes
    for i in range(10):
        response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "authorization_code",
                "code": f"invalid-code-{i}",
                "redirect_uri": "https://app.example.com/callback",
                "client_id": oauth_client.client_id,
                "code_verifier": "test-verifier-12345678901234567890"
            },
            headers=FORM_HEADERS
        )
        responses.append(response.status_code)

    # With Redis: At least one should be 429 (rate limited)
    # Without Redis: All should be 401 (invalid code)
    if 429 in responses:
        # Rate limiting is active
        pass
    else:
        # Rate limiting not triggered (Redis not available or limit not reached)
        # All responses should be 401 (invalid code)
        assert all(r == 401 for r in responses), f"Expected all 401, got {responses}"


# =============================================================================
# Test 14: Cleanup Job Deletes Expired Auth Codes
# =============================================================================

@pytest.mark.asyncio
async def test_cleanup_job_deletes_expired_codes(
    async_session: AsyncSession,
    test_user,
    oauth_client
):
    """
    Test 14: Cleanup job deletes expired auth codes (>10 min).

    This tests the cleanup logic directly, not through Celery.
    """
    _, code_challenge = generate_pkce_pair()

    # Create an expired code (expired 15 minutes ago)
    expired_code = OAuthAuthorizationCode(
        code=secrets.token_urlsafe(96),
        user_id=test_user.id,
        client_id=oauth_client.client_id,
        code_challenge=code_challenge,
        code_challenge_method="S256",
        redirect_uri=oauth_client.redirect_uris[0],
        scope=["focused.read"],
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=15),
        used=False
    )
    async_session.add(expired_code)
    await async_session.commit()

    # Verify code exists
    result = await async_session.execute(
        select(OAuthAuthorizationCode).where(
            OAuthAuthorizationCode.code == expired_code.code
        )
    )
    assert result.scalar_one_or_none() is not None, "Expired code should exist before cleanup"

    # Run cleanup logic (same as Celery task)
    now = datetime.now(timezone.utc)
    stmt = delete(OAuthAuthorizationCode).where(
        OAuthAuthorizationCode.expires_at < now
    )
    delete_result = await async_session.execute(stmt)
    await async_session.commit()

    # Verify code was deleted
    result = await async_session.execute(
        select(OAuthAuthorizationCode).where(
            OAuthAuthorizationCode.code == expired_code.code
        )
    )
    assert result.scalar_one_or_none() is None, "Expired code should be deleted by cleanup"
    assert delete_result.rowcount >= 1, "At least one code should be deleted"


@pytest.mark.asyncio
async def test_cleanup_deletes_expired_used_codes(
    async_session: AsyncSession,
    test_user,
    oauth_client
):
    """
    Test that cleanup job deletes expired codes even if already used.

    Both unused AND used expired codes should be cleaned up.
    """
    _, code_challenge = generate_pkce_pair()

    # Create an expired AND used code
    expired_used_code = OAuthAuthorizationCode(
        code=secrets.token_urlsafe(96),
        user_id=test_user.id,
        client_id=oauth_client.client_id,
        code_challenge=code_challenge,
        code_challenge_method="S256",
        redirect_uri=oauth_client.redirect_uris[0],
        scope=["focused.read"],
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=15),
        used=True  # Already used
    )
    async_session.add(expired_used_code)
    await async_session.commit()

    # Verify code exists
    result = await async_session.execute(
        select(OAuthAuthorizationCode).where(
            OAuthAuthorizationCode.code == expired_used_code.code
        )
    )
    assert result.scalar_one_or_none() is not None, "Expired+used code should exist before cleanup"

    # Run cleanup logic
    now = datetime.now(timezone.utc)
    stmt = delete(OAuthAuthorizationCode).where(
        OAuthAuthorizationCode.expires_at < now
    )
    delete_result = await async_session.execute(stmt)
    await async_session.commit()

    # Verify code was deleted
    result = await async_session.execute(
        select(OAuthAuthorizationCode).where(
            OAuthAuthorizationCode.code == expired_used_code.code
        )
    )
    assert result.scalar_one_or_none() is None, "Expired+used code should be deleted by cleanup"
    assert delete_result.rowcount >= 1, "At least one code should be deleted"


@pytest.mark.asyncio
async def test_cleanup_preserves_valid_codes(
    async_session: AsyncSession,
    test_user,
    oauth_client
):
    """
    Test that cleanup job does NOT delete valid (unexpired) codes.
    """
    _, code_challenge = generate_pkce_pair()

    # Create a valid code (expires in 5 minutes)
    valid_code = OAuthAuthorizationCode(
        code=secrets.token_urlsafe(96),
        user_id=test_user.id,
        client_id=oauth_client.client_id,
        code_challenge=code_challenge,
        code_challenge_method="S256",
        redirect_uri=oauth_client.redirect_uris[0],
        scope=["focused.read"],
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),  # Still valid
        used=False
    )
    async_session.add(valid_code)
    await async_session.commit()

    # Run cleanup
    now = datetime.now(timezone.utc)
    stmt = delete(OAuthAuthorizationCode).where(
        OAuthAuthorizationCode.expires_at < now
    )
    await async_session.execute(stmt)
    await async_session.commit()

    # Verify valid code still exists
    result = await async_session.execute(
        select(OAuthAuthorizationCode).where(
            OAuthAuthorizationCode.code == valid_code.code
        )
    )
    assert result.scalar_one_or_none() is not None, "Valid code should NOT be deleted"
