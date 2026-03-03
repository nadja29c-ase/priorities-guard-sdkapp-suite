"""
OAuth Authorization Code Integration Tests (Increment 16).

Tests the authorization code lifecycle:
1.1. Generate authorization code (Happy Path)
1.2. Authorization Code – single use
1.3. Authorization Code – expired
1.4. Authorization Code – PKCE mismatch
1.5. Authorization Code – redirect_uri mismatch

Test framework: pytest
Client: httpx.AsyncClient
Database: test DB with migrations applied
"""

import pytest
import pytest_asyncio
import base64
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.models import CoreConnection, CoreUser
from backend.core.encryption import encrypt_token
from backend.core.oauth_provider.models import OAuthAuthorizationCode
from backend.core.oauth_provider.services.consent_service import create_authorization_code


# ============================================================================
# FIXTURES
# ============================================================================

def generate_pkce_pair(seed: str = "test-verifier") -> tuple[str, str]:
    """
    Generate a valid PKCE code_verifier and code_challenge pair.

    Args:
        seed: Seed for verifier generation

    Returns:
        Tuple of (code_verifier, code_challenge)
    """
    # Generate code_verifier (43-128 characters of URL-safe base64)
    code_verifier = base64.urlsafe_b64encode(
        hashlib.sha256(seed.encode()).digest()
    ).rstrip(b"=").decode("utf-8")

    # Generate code_challenge = base64url(sha256(code_verifier))
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode("utf-8")

    return code_verifier, code_challenge


@pytest_asyncio.fixture
async def test_user(async_session: AsyncSession) -> CoreUser:
    """Create a test user for authorization tests."""
    user = CoreUser(
        chatgpt_user_id=f"test-chatgpt-user-{uuid4().hex[:8]}"
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def oauth_client(async_session: AsyncSession) -> dict:
    """
    Create a test OAuth client (CoreConnection with connection_type=oauth_provider).

    Returns dict with client_id, client_secret, redirect_uri for test use.
    """
    client_id = f"focused-client-test-{uuid4().hex[:8]}"
    client_secret = f"test-secret-{uuid4().hex[:16]}"
    redirect_uri = "https://chat.openai.com/aip/callback"

    client = CoreConnection(
        user_id=None,  # OAuth provider clients have no user
        provider="Test OAuth Client",
        connection_type="oauth_provider",
        client_id=client_id,
        client_secret_enc=encrypt_token(client_secret),
        redirect_uris=[redirect_uri],
        grant_types=["authorization_code", "refresh_token"],
        encrypted_access_token="",  # Required field
        scopes=["focused.read", "focused.write", "focused.notify"],
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        provider_metadata={"client_name": "Test Client App"}
    )
    async_session.add(client)
    await async_session.commit()

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri
    }


@pytest_asyncio.fixture
async def authorization_code(
    async_session: AsyncSession,
    test_user: CoreUser,
    oauth_client: dict
) -> dict:
    """
    Create an authorization code for testing token exchange.

    Returns dict with code, code_verifier, and all params needed for exchange.
    """
    code_verifier, code_challenge = generate_pkce_pair("test-auth-code-verifier")
    scope = "focused.read focused.write"

    code = await create_authorization_code(
        db=async_session,
        user_id=str(test_user.id),
        client_id=oauth_client["client_id"],
        code_challenge=code_challenge,
        code_challenge_method="S256",
        redirect_uri=oauth_client["redirect_uri"],
        scope=scope,
        state="test-state-123",
        correlation_id="test-correlation"
    )

    return {
        "code": code,
        "code_verifier": code_verifier,
        "code_challenge": code_challenge,
        "client_id": oauth_client["client_id"],
        "redirect_uri": oauth_client["redirect_uri"],
        "scope": scope,
        "user_id": str(test_user.id)
    }


# ============================================================================
# TEST CLASS: AUTHORIZATION CODE GENERATION (1.1)
# ============================================================================

class TestAuthorizationCodeGeneration:
    """Test authorization code generation via /authorize endpoint."""

    @pytest.mark.asyncio
    async def test_authorize_generates_code_happy_path(
        self,
        client: AsyncClient,
        oauth_client: dict
    ):
        """
        1.1. Generate authorization code (Happy Path)

        Given: valid GET /oauth/focused/authorize with all required params
        Expect: HTML consent screen rendered with auth_context_id
        """
        code_verifier, code_challenge = generate_pkce_pair("happy-path-verifier")

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": oauth_client["client_id"],
                "redirect_uri": oauth_client["redirect_uri"],
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "scope": "focused.read focused.write",
                "state": "test-state-happy",
                "login_hint": "test-user-happy-path"
            }
        )

        # Should return HTML consent page
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

        # Consent page should contain auth_context_id hidden field
        assert "auth_context_id" in response.text
        assert "focused.read" in response.text or "Permissions" in response.text

    @pytest.mark.asyncio
    async def test_authorize_creates_user_from_login_hint(
        self,
        client: AsyncClient,
        oauth_client: dict,
        async_session: AsyncSession
    ):
        """
        Authorize endpoint should create user if login_hint user doesn't exist.
        """
        unique_login_hint = f"new-user-{uuid4().hex[:8]}"
        code_verifier, code_challenge = generate_pkce_pair("new-user-verifier")

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": oauth_client["client_id"],
                "redirect_uri": oauth_client["redirect_uri"],
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "scope": "focused.read",
                "login_hint": unique_login_hint
            }
        )

        assert response.status_code == 200

        # Verify user was created
        result = await async_session.execute(
            select(CoreUser).where(CoreUser.chatgpt_user_id == unique_login_hint)
        )
        user = result.scalar_one_or_none()
        assert user is not None
        assert user.chatgpt_user_id == unique_login_hint


# ============================================================================
# TEST CLASS: AUTHORIZATION CODE EXCHANGE (1.2 - 1.5)
# ============================================================================

class TestAuthorizationCodeExchange:
    """Test authorization code exchange at /token endpoint."""

    @pytest.mark.asyncio
    async def test_exchange_code_happy_path(
        self,
        client: AsyncClient,
        authorization_code: dict
    ):
        """
        Token exchange with valid authorization code succeeds.

        Expect:
        - access_token is returned (JWT)
        - refresh_token is returned (opaque)
        - token_type is Bearer
        - scope matches requested
        """
        response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "authorization_code",
                "code": authorization_code["code"],
                "code_verifier": authorization_code["code_verifier"],
                "client_id": authorization_code["client_id"],
                "redirect_uri": authorization_code["redirect_uri"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert response.status_code == 200
        data = response.json()

        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "Bearer"
        assert "expires_in" in data
        assert data["expires_in"] > 0

        # Verify scope matches requested (RFC 6749 requirement)
        assert "scope" in data
        assert data["scope"] == authorization_code["scope"]

        # Verify JWT structure (header.payload.signature)
        access_token = data["access_token"]
        assert access_token.count(".") == 2

    @pytest.mark.asyncio
    async def test_exchange_code_single_use(
        self,
        client: AsyncClient,
        authorization_code: dict
    ):
        """
        1.2. Authorization Code – single use

        Steps:
        - Exchange code once → expect 200
        - Exchange same code second time → expect 400 invalid_grant
        """
        # First exchange should succeed
        response1 = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "authorization_code",
                "code": authorization_code["code"],
                "code_verifier": authorization_code["code_verifier"],
                "client_id": authorization_code["client_id"],
                "redirect_uri": authorization_code["redirect_uri"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert response1.status_code == 200

        # Second exchange with same code should fail
        response2 = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "authorization_code",
                "code": authorization_code["code"],
                "code_verifier": authorization_code["code_verifier"],
                "client_id": authorization_code["client_id"],
                "redirect_uri": authorization_code["redirect_uri"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        # OAuth 2.1 spec: invalid_grant returns 400 Bad Request
        assert response2.status_code == 400
        data = response2.json()
        assert data["error"] == "invalid_grant"
        assert "used" in data["error_description"].lower()

    @pytest.mark.asyncio
    async def test_exchange_code_expired(
        self,
        client: AsyncClient,
        authorization_code: dict,
        async_session: AsyncSession
    ):
        """
        1.3. Authorization Code – expired

        Set expires_at = now() - 1s
        Exchange → expect 400 invalid_grant + "expired"
        """
        # Manually expire the code
        await async_session.execute(
            update(OAuthAuthorizationCode)
            .where(OAuthAuthorizationCode.code == authorization_code["code"])
            .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        )
        await async_session.commit()

        response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "authorization_code",
                "code": authorization_code["code"],
                "code_verifier": authorization_code["code_verifier"],
                "client_id": authorization_code["client_id"],
                "redirect_uri": authorization_code["redirect_uri"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        # OAuth 2.1 spec: invalid_grant returns 400 Bad Request
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "invalid_grant"
        assert "expired" in data["error_description"].lower()

    @pytest.mark.asyncio
    async def test_exchange_code_pkce_mismatch(
        self,
        client: AsyncClient,
        authorization_code: dict
    ):
        """
        1.4. Authorization Code – PKCE mismatch

        Send wrong code_verifier
        Expect: 400 invalid_grant + PKCE verification failed
        """
        # Use a different verifier that doesn't match the challenge
        wrong_verifier = "this-is-a-wrong-verifier-that-wont-match"

        response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "authorization_code",
                "code": authorization_code["code"],
                "code_verifier": wrong_verifier,
                "client_id": authorization_code["client_id"],
                "redirect_uri": authorization_code["redirect_uri"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        # OAuth 2.1 spec: invalid_grant returns 400 Bad Request
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "invalid_grant"
        assert "pkce" in data["error_description"].lower()

    @pytest.mark.asyncio
    async def test_exchange_code_redirect_uri_mismatch(
        self,
        client: AsyncClient,
        authorization_code: dict
    ):
        """
        1.5. Authorization Code – redirect_uri mismatch

        Create auth code with redirect_uri=A
        Exchange with redirect_uri=B
        Expect: 400 invalid_grant + redirect_uri mismatch
        """
        # Use a different redirect_uri than what was registered
        wrong_redirect_uri = "https://evil.example.com/callback"

        response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "authorization_code",
                "code": authorization_code["code"],
                "code_verifier": authorization_code["code_verifier"],
                "client_id": authorization_code["client_id"],
                "redirect_uri": wrong_redirect_uri
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        # OAuth 2.1 spec: invalid_grant returns 400 Bad Request
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "invalid_grant"
        assert "redirect_uri" in data["error_description"].lower()

    @pytest.mark.asyncio
    async def test_exchange_code_invalid_code(
        self,
        client: AsyncClient,
        oauth_client: dict
    ):
        """
        Exchange with non-existent code fails with invalid_grant.
        """
        code_verifier, _ = generate_pkce_pair("invalid-code-test")

        response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "authorization_code",
                "code": "this-code-does-not-exist",
                "code_verifier": code_verifier,
                "client_id": oauth_client["client_id"],
                "redirect_uri": oauth_client["redirect_uri"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        # OAuth 2.1 spec: invalid_grant returns 400 Bad Request
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "invalid_grant"


# ============================================================================
# TEST CLASS: DATABASE STATE VERIFICATION
# ============================================================================

class TestAuthorizationCodeDatabaseState:
    """Test that authorization codes are stored correctly in database."""

    @pytest.mark.asyncio
    async def test_authorization_code_stored_correctly(
        self,
        async_session: AsyncSession,
        test_user: CoreUser,
        oauth_client: dict
    ):
        """
        9.1. Authorization code inserts correct row

        Check:
        - user_id
        - client_id
        - scope
        - expires_at
        - redirect_uri
        - code_challenge
        - used = FALSE
        """
        code_verifier, code_challenge = generate_pkce_pair("db-state-verifier")
        scope = "focused.read focused.write"

        code = await create_authorization_code(
            db=async_session,
            user_id=str(test_user.id),
            client_id=oauth_client["client_id"],
            code_challenge=code_challenge,
            code_challenge_method="S256",
            redirect_uri=oauth_client["redirect_uri"],
            scope=scope,
            state="test-state-db",
            correlation_id="test-db-correlation"
        )

        # Fetch the stored code
        result = await async_session.execute(
            select(OAuthAuthorizationCode).where(
                OAuthAuthorizationCode.code == code
            )
        )
        stored_code = result.scalar_one()

        # Verify all fields
        assert stored_code.user_id == test_user.id
        assert stored_code.client_id == oauth_client["client_id"]
        assert stored_code.scope == ["focused.read", "focused.write"]
        assert stored_code.redirect_uri == oauth_client["redirect_uri"]
        assert stored_code.code_challenge == code_challenge
        assert stored_code.code_challenge_method == "S256"
        assert stored_code.state == "test-state-db"
        # nonce column was dropped (OpenID Connect not implemented)
        assert stored_code.used is False

        # Expires_at should be ~10 minutes from now
        time_until_expiry = stored_code.expires_at - datetime.now(timezone.utc)
        assert timedelta(minutes=9) < time_until_expiry < timedelta(minutes=11)

    @pytest.mark.asyncio
    async def test_authorization_code_marked_used_after_exchange(
        self,
        client: AsyncClient,
        authorization_code: dict,
        async_session: AsyncSession
    ):
        """
        After successful token exchange, code should be marked as used.
        """
        # Exchange the code
        response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "authorization_code",
                "code": authorization_code["code"],
                "code_verifier": authorization_code["code_verifier"],
                "client_id": authorization_code["client_id"],
                "redirect_uri": authorization_code["redirect_uri"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert response.status_code == 200

        # Verify code is marked as used in DB
        # Need to refresh the session to see changes from different session
        await async_session.rollback()  # Clear any cached state
        result = await async_session.execute(
            select(OAuthAuthorizationCode).where(
                OAuthAuthorizationCode.code == authorization_code["code"]
            )
        )
        stored_code = result.scalar_one()
        assert stored_code.used is True


# ============================================================================
# TEST CLASS: FULL E2E AUTHORIZATION FLOW (1.1 Complete)
# ============================================================================

class TestFullAuthorizationFlow:
    """
    Test the complete E2E flow: GET /authorize → POST /consent → 302 redirect.

    This tests the full HTTP layer integration, not just service-level code.
    Requires fake_redis_client fixture for authorization context storage.
    """

    @pytest.mark.asyncio
    async def test_full_authorize_consent_flow_creates_code_and_redirects(
        self,
        client: AsyncClient,
        oauth_client: dict,
        async_session: AsyncSession,
        fake_redis_client
    ):
        """
        1.1. Generate authorization code (Happy Path) - Full E2E Flow

        Steps:
        1. GET /oauth/focused/authorize with valid params
        2. Extract auth_context_id from HTML response
        3. POST /oauth/focused/consent with action=allow
        4. Assert 302 redirect with code and state in query params
        5. Verify code exists in database with correct fields
        """
        import re
        from urllib.parse import urlparse, parse_qs

        # Setup (fake_redis_client fixture patches Redis for auth context storage)
        _ = fake_redis_client  # Used implicitly by authorize/consent endpoints
        _code_verifier, code_challenge = generate_pkce_pair("e2e-flow-verifier")
        test_state = "test-state-e2e-full-flow"
        login_hint = f"e2e-user-{uuid4().hex[:8]}"

        # Step 1: GET /authorize
        authorize_response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": oauth_client["client_id"],
                "redirect_uri": oauth_client["redirect_uri"],
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "scope": "focused.read focused.write",
                "state": test_state,
                "login_hint": login_hint
            }
        )

        assert authorize_response.status_code == 200
        assert "text/html" in authorize_response.headers.get("content-type", "")

        # Step 2: Extract auth_context_id from HTML
        html = authorize_response.text
        match = re.search(r'name="auth_context_id"\s+value="([^"]+)"', html)
        assert match is not None, "auth_context_id not found in consent form"
        auth_context_id = match.group(1)

        # Step 3: POST /consent with Allow
        consent_response = await client.post(
            "/oauth/focused/consent",
            data={
                "auth_context_id": auth_context_id,
                "action": "allow"
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False
        )

        # Step 4: Assert 302 redirect with code and state
        assert consent_response.status_code == 302
        location = consent_response.headers.get("location", "")

        # Verify redirect URL
        assert location.startswith(oauth_client["redirect_uri"])

        # Parse query params
        parsed = urlparse(location)
        query_params = parse_qs(parsed.query)

        # Verify code is present and non-empty
        assert "code" in query_params
        auth_code = query_params["code"][0]
        assert len(auth_code) > 0

        # Verify state is preserved
        assert "state" in query_params
        assert query_params["state"][0] == test_state

        # Step 5: Verify code exists in database with correct fields
        await async_session.rollback()  # Clear any cached state
        result = await async_session.execute(
            select(OAuthAuthorizationCode).where(
                OAuthAuthorizationCode.code == auth_code
            )
        )
        stored_code = result.scalar_one()

        # Verify stored code fields
        assert stored_code.client_id == oauth_client["client_id"]
        assert stored_code.redirect_uri == oauth_client["redirect_uri"]
        assert stored_code.code_challenge == code_challenge
        assert stored_code.code_challenge_method == "S256"
        assert stored_code.state == test_state
        assert stored_code.scope == ["focused.read", "focused.write"]
        assert stored_code.used is False

        # Verify expires_at is ~10 minutes in the future
        time_until_expiry = stored_code.expires_at - datetime.now(timezone.utc)
        assert timedelta(minutes=9) < time_until_expiry < timedelta(minutes=11)

        # Verify user was created from login_hint
        user_result = await async_session.execute(
            select(CoreUser).where(CoreUser.id == stored_code.user_id)
        )
        user = user_result.scalar_one()
        assert user.chatgpt_user_id == login_hint

    @pytest.mark.asyncio
    async def test_consent_deny_redirects_with_error(
        self,
        client: AsyncClient,
        oauth_client: dict,
        fake_redis_client
    ):
        """
        Test that denying consent redirects with error=access_denied.
        """
        import re
        from urllib.parse import urlparse, parse_qs

        # fake_redis_client fixture patches Redis for auth context storage
        _ = fake_redis_client
        _code_verifier, code_challenge = generate_pkce_pair("deny-flow-verifier")
        test_state = "test-state-deny-flow"

        # GET /authorize
        authorize_response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": oauth_client["client_id"],
                "redirect_uri": oauth_client["redirect_uri"],
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "scope": "focused.read",
                "state": test_state,
                "login_hint": f"deny-user-{uuid4().hex[:8]}"
            }
        )

        assert authorize_response.status_code == 200

        # Extract auth_context_id
        match = re.search(r'name="auth_context_id"\s+value="([^"]+)"', authorize_response.text)
        assert match is not None
        auth_context_id = match.group(1)

        # POST /consent with Deny
        consent_response = await client.post(
            "/oauth/focused/consent",
            data={
                "auth_context_id": auth_context_id,
                "action": "deny"
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False
        )

        # Should redirect with error=access_denied
        assert consent_response.status_code == 302
        location = consent_response.headers.get("location", "")
        assert location.startswith(oauth_client["redirect_uri"])

        parsed = urlparse(location)
        query_params = parse_qs(parsed.query)

        assert "error" in query_params
        assert query_params["error"][0] == "access_denied"
        assert "state" in query_params
        assert query_params["state"][0] == test_state
        # Should NOT have code param
        assert "code" not in query_params
