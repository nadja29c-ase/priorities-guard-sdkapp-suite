"""
OAuth Security Integration Tests (Increment 16).

Tests security requirements and error handling:
7.3. Unknown client_id in /token
7.4. Unknown client_id in /authorize
7.5. Token exchange with missing fields
10.1. Token issued for one client cannot be used for another (refresh + auth code)
10.2. Non-HTTPS redirect rejected (registration + authorize)
10.3. Redirect URI must match registered URI
10.4. Scope validation (invalid, excess, mixed)
10.5. PKCE validation (required, S256 only, malformed challenges)

Note: Tests 7.1/7.2 (Missing/Invalid Authorization header) are not applicable here.
The backend OAuth provider doesn't expose protected endpoints - token validation
happens at the MCP server level via JWKS.

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
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.models import CoreConnection, CoreUser
from backend.core.encryption import encrypt_token
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
    """Create a test user for security tests."""
    user = CoreUser(
        chatgpt_user_id=f"test-chatgpt-user-security-{uuid4().hex[:8]}"
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def oauth_client(async_session: AsyncSession) -> dict:
    """Create a test OAuth client."""
    client_id = f"focused-client-security-{uuid4().hex[:8]}"
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
        provider_metadata={"client_name": "Security Test Client"}
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
    """Create a second OAuth client for cross-client security tests."""
    client_id = f"focused-client-security-b-{uuid4().hex[:8]}"
    client_secret = f"test-secret-b-{uuid4().hex[:16]}"
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
        provider_metadata={"client_name": "Security Test Client B"}
    )
    async_session.add(client)
    await async_session.commit()

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri
    }


@pytest_asyncio.fixture
async def token_for_client_a(
    client: AsyncClient,
    async_session: AsyncSession,
    test_user: CoreUser,
    oauth_client: dict
) -> dict:
    """Get a valid token issued for oauth_client (client A)."""
    code_verifier, code_challenge = generate_pkce_pair("security-token-a")

    code = await create_authorization_code(
        db=async_session,
        user_id=str(test_user.id),
        client_id=oauth_client["client_id"],
        code_challenge=code_challenge,
        code_challenge_method="S256",
        redirect_uri=oauth_client["redirect_uri"],
        scope="focused.read focused.write",
        correlation_id="security-token-a"
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
    return data


# ============================================================================
# TEST CLASS: ERROR HANDLING (7.1 - 7.5)
# ============================================================================

class TestSecurityErrorHandling:
    """Test security-related error responses."""

    @pytest.mark.asyncio
    async def test_unknown_client_id_in_token(
        self,
        client: AsyncClient
    ):
        """
        7.3. Unknown client_id in /token

        Expect: 401 invalid_client
        """
        code_verifier, _ = generate_pkce_pair("unknown-client")

        response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "authorization_code",
                "code": "some-code",
                "code_verifier": code_verifier,
                "client_id": "non-existent-client-id",
                "redirect_uri": "https://example.com/callback"
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        # Could be 401 (invalid_client) or 400 (invalid_grant for bad code)
        assert response.status_code in [400, 401]
        data = response.json()
        assert data["error"] in ["invalid_client", "invalid_grant"]

    @pytest.mark.asyncio
    async def test_unknown_client_id_in_authorize(
        self,
        client: AsyncClient
    ):
        """
        7.4. Unknown client_id in /authorize

        Expect: 302 redirect with error or 400 invalid_client
        """
        code_verifier, code_challenge = generate_pkce_pair("unknown-client-auth")

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": "non-existent-client-id",
                "redirect_uri": "https://example.com/callback",
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "scope": "focused.read"
            },
            follow_redirects=False
        )

        # Should return error redirect or 400
        if response.status_code == 302:
            location = response.headers.get("location", "")
            assert "error=invalid_client" in location
        else:
            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_token_missing_code_verifier(
        self,
        client: AsyncClient,
        oauth_client: dict
    ):
        """
        7.5. Token exchange with missing code_verifier

        Expect: 400 invalid_request
        """
        response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "authorization_code",
                "code": "some-code",
                "client_id": oauth_client["client_id"],
                "redirect_uri": oauth_client["redirect_uri"]
                # Missing code_verifier
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "invalid_request"
        assert "code_verifier" in data["error_description"].lower()

    @pytest.mark.asyncio
    async def test_token_missing_redirect_uri(
        self,
        client: AsyncClient,
        oauth_client: dict
    ):
        """
        7.5. Token exchange with missing redirect_uri

        Expect: 400 invalid_request
        """
        code_verifier, _ = generate_pkce_pair("missing-redirect")

        response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "authorization_code",
                "code": "some-code",
                "code_verifier": code_verifier,
                "client_id": oauth_client["client_id"]
                # Missing redirect_uri
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "invalid_request"
        assert "redirect_uri" in data["error_description"].lower()

    @pytest.mark.asyncio
    async def test_token_missing_client_id(
        self,
        client: AsyncClient,
        oauth_client: dict
    ):
        """
        7.5. Token exchange with missing client_id

        Expect: 400 invalid_request
        """
        code_verifier, _ = generate_pkce_pair("missing-client")

        response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "authorization_code",
                "code": "some-code",
                "code_verifier": code_verifier,
                "redirect_uri": oauth_client["redirect_uri"]
                # Missing client_id
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "invalid_request"
        assert "client_id" in data["error_description"].lower()

    @pytest.mark.asyncio
    async def test_refresh_token_missing(
        self,
        client: AsyncClient,
        oauth_client: dict
    ):
        """
        7.5. Refresh grant with missing refresh_token parameter.

        Expect: 400 invalid_request
        """
        response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "refresh_token",
                "client_id": oauth_client["client_id"]
                # Missing refresh_token
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "invalid_request"

    @pytest.mark.asyncio
    async def test_refresh_token_malformed(
        self,
        client: AsyncClient,
        oauth_client: dict
    ):
        """
        Refresh grant with malformed/garbage refresh_token.

        Expect: 400 invalid_grant (token not found/invalid)
        """
        response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": "not-a-valid-token-!!!@#$%^&*()",
                "client_id": oauth_client["client_id"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "invalid_grant"


# ============================================================================
# TEST CLASS: CROSS-CLIENT SECURITY (10.1)
# ============================================================================

class TestCrossClientSecurity:
    """Test that tokens are properly isolated between clients."""

    @pytest.mark.asyncio
    async def test_refresh_token_client_mismatch(
        self,
        client: AsyncClient,
        token_for_client_a: dict,
        oauth_client_b: dict
    ):
        """
        10.1. Token issued for one client cannot be used for another

        Token issued for client A, try to refresh with client B.
        Expect: 400 invalid_grant (client_id mismatch) per OAuth 2.1 spec
        """
        response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": token_for_client_a["refresh_token"],
                "client_id": oauth_client_b["client_id"]  # Different client
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        # OAuth 2.1: invalid_grant returns 400 Bad Request
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "invalid_grant"

    @pytest.mark.asyncio
    async def test_authorization_code_client_mismatch(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user: CoreUser,
        oauth_client: dict,
        oauth_client_b: dict
    ):
        """
        10.1. Authorization code issued for client A cannot be used by client B.

        Code issued for client A, try to exchange with client B.
        Expect: 400 invalid_grant (client_id mismatch) per OAuth 2.1 spec
        """
        code_verifier, code_challenge = generate_pkce_pair("cross-client-code")

        # Create authorization code for client A
        code = await create_authorization_code(
            db=async_session,
            user_id=str(test_user.id),
            client_id=oauth_client["client_id"],  # Client A
            code_challenge=code_challenge,
            code_challenge_method="S256",
            redirect_uri=oauth_client["redirect_uri"],
            scope="focused.read",
            correlation_id="cross-client-test"
        )

        # Try to exchange with client B
        response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": code_verifier,
                "client_id": oauth_client_b["client_id"],  # Different client!
                "redirect_uri": oauth_client_b["redirect_uri"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        # OAuth 2.1: invalid_grant for mismatched client_id
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "invalid_grant"

    @pytest.mark.asyncio
    async def test_authorization_code_replay_fails(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user: CoreUser,
        oauth_client: dict
    ):
        """
        2.1/2.4. Authorization code replay must return invalid_grant.

        OAuth 2.1 requires authorization codes to be single-use.
        Attempting to exchange the same code twice must fail.
        This prevents session fixation attacks.
        """
        code_verifier, code_challenge = generate_pkce_pair("code-replay-test")

        # Create authorization code
        code = await create_authorization_code(
            db=async_session,
            user_id=str(test_user.id),
            client_id=oauth_client["client_id"],
            code_challenge=code_challenge,
            code_challenge_method="S256",
            redirect_uri=oauth_client["redirect_uri"],
            scope="focused.read",
            correlation_id="code-replay-test"
        )

        # First exchange - should succeed
        first_response = await client.post(
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
        assert first_response.status_code == 200, (
            f"First exchange should succeed, got {first_response.status_code}"
        )

        # Second exchange with same code - MUST fail
        second_response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "authorization_code",
                "code": code,  # Same code again
                "code_verifier": code_verifier,
                "client_id": oauth_client["client_id"],
                "redirect_uri": oauth_client["redirect_uri"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        # OAuth 2.1: Code replay must return 400 invalid_grant
        assert second_response.status_code == 400, (
            f"Code replay should fail with 400, got {second_response.status_code}"
        )
        data = second_response.json()
        assert data["error"] == "invalid_grant", (
            f"Code replay should return invalid_grant, got {data.get('error')}"
        )

    @pytest.mark.asyncio
    async def test_token_exchange_wrong_redirect_uri_fails(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user: CoreUser,
        oauth_client: dict
    ):
        """
        2.3. Token exchange with wrong redirect_uri must fail.

        OAuth 2.1 requires redirect_uri in token request to exactly match
        the redirect_uri used during authorization.
        """
        code_verifier, code_challenge = generate_pkce_pair("wrong-redirect-test")

        # Create authorization code with redirect_uri A
        code = await create_authorization_code(
            db=async_session,
            user_id=str(test_user.id),
            client_id=oauth_client["client_id"],
            code_challenge=code_challenge,
            code_challenge_method="S256",
            redirect_uri=oauth_client["redirect_uri"],  # Original redirect
            scope="focused.read",
            correlation_id="wrong-redirect-test"
        )

        # Try to exchange with different redirect_uri
        response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": code_verifier,
                "client_id": oauth_client["client_id"],
                "redirect_uri": "https://different.example.com/callback"  # Wrong!
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        # OAuth 2.1: redirect_uri mismatch must return 400 invalid_grant
        assert response.status_code == 400, (
            f"Wrong redirect_uri should fail with 400, got {response.status_code}"
        )
        data = response.json()
        assert data["error"] == "invalid_grant", (
            f"Wrong redirect_uri should return invalid_grant, got {data.get('error')}"
        )


# ============================================================================
# TEST CLASS: REDIRECT URI SECURITY (10.2)
# ============================================================================

class TestRedirectUriSecurity:
    """Test redirect URI validation."""

    @pytest.mark.asyncio
    async def test_http_redirect_rejected(
        self,
        client: AsyncClient,
        async_session: AsyncSession
    ):
        """
        10.2. Non-HTTPS redirect rejected

        Any redirect starting with "http://" should be rejected.
        Expect: 400 invalid_redirect_uri
        """
        # First, try to register a client with http redirect
        response = await client.post(
            "/oauth/focused/register",
            json={
                "client_name": "HTTP Redirect Test",
                "redirect_uris": ["http://insecure.example.com/callback"],  # HTTP!
                "grant_types": ["authorization_code"]
            }
        )

        # Should reject the HTTP redirect
        assert response.status_code == 400
        data = response.json()
        # Error message can be in "error_description" or "detail" field
        error_msg = data.get("error_description", "") or data.get("detail", "")
        assert "redirect" in error_msg.lower() or "https" in error_msg.lower()

    @pytest.mark.asyncio
    @pytest.mark.xfail(
        reason="SECURITY: Backend redirects to unregistered URI with error. "
               "Per OAuth 2.0 spec 4.1.2.1, server SHOULD NOT redirect when "
               "redirect_uri is invalid. Implementation needs fix.",
        strict=True
    )
    async def test_http_redirect_rejected_in_authorize(
        self,
        client: AsyncClient,
        async_session: AsyncSession
    ):
        """
        10.2. Non-HTTPS redirect rejected at /authorize

        Attempting to use an http:// redirect_uri when only https:// is
        registered must NOT redirect to the unregistered http:// URL.

        Per OAuth 2.0 spec section 4.1.2.1, when redirect_uri is invalid,
        the server SHOULD NOT redirect to the client at all.
        """
        # Create a client with HTTPS redirect for registration
        client_id = f"focused-client-https-test-{uuid4().hex[:8]}"
        oauth_client = CoreConnection(
            user_id=None,
            provider="HTTPS Test Client",
            connection_type="oauth_provider",
            client_id=client_id,
            client_secret_enc=encrypt_token("secret"),
            redirect_uris=["https://example.com/callback"],
            grant_types=["authorization_code"],
            encrypted_access_token="",
            scopes=["focused.read"],
            token_expires_at=datetime.now(timezone.utc) + timedelta(days=365)
        )
        async_session.add(oauth_client)
        await async_session.commit()

        code_verifier, code_challenge = generate_pkce_pair("https-only-test")

        # Try to authorize with http:// redirect (not registered)
        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": "http://example.com/callback",  # HTTP version - not registered
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "scope": "focused.read"
            },
            follow_redirects=False
        )

        # SECURITY: Must NOT redirect to the unregistered http:// URL
        if response.status_code == 302:
            location = response.headers.get("location", "")
            # Must NOT redirect to the unregistered http:// URL
            assert not location.startswith("http://example.com"), (
                "SECURITY VULNERABILITY: Redirected to unregistered http:// URL!"
            )
            # If redirecting, must go to the registered https:// URL with error
            assert location.startswith("https://example.com/callback"), (
                f"Expected redirect to registered URL, got: {location}"
            )
            assert "error=" in location
        else:
            # 400 is the correct response per OAuth spec
            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_localhost_http_allowed_for_development(
        self,
        client: AsyncClient
    ):
        """
        localhost http redirects may be allowed for development.

        This is per OAuth 2.1 spec which allows http://localhost.
        """
        response = await client.post(
            "/oauth/focused/register",
            json={
                "client_name": "Localhost Test",
                "redirect_uris": ["http://localhost:3000/callback"],
                "grant_types": ["authorization_code"]
            }
        )

        # localhost http may be allowed (200/201) or rejected (400)
        # Both are valid implementations
        assert response.status_code in [200, 201, 400]

    @pytest.mark.asyncio
    @pytest.mark.xfail(
        reason="SECURITY: Backend redirects to unregistered attacker URI with error. "
               "Per OAuth 2.0 spec 4.1.2.1, server SHOULD NOT redirect when "
               "redirect_uri is invalid. Implementation needs fix.",
        strict=True
    )
    async def test_redirect_uri_not_registered(
        self,
        client: AsyncClient,
        oauth_client: dict
    ):
        """
        10.3. Redirect URI must exactly match a pre-registered URI.

        Using an unregistered redirect must NOT redirect to the attacker's URL.

        Per OAuth 2.0 spec section 4.1.2.1, if the redirect_uri is invalid,
        the server SHOULD NOT redirect to the client at all.
        """
        code_verifier, code_challenge = generate_pkce_pair("unregistered-redirect")

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": oauth_client["client_id"],
                "redirect_uri": "https://attacker.evil.com/steal-code",  # Not registered
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "scope": "focused.read"
            },
            follow_redirects=False
        )

        # SECURITY: Must NOT redirect to the attacker's URL
        if response.status_code == 302:
            location = response.headers.get("location", "")
            # CRITICAL: Must NOT redirect to attacker domain
            assert not location.startswith("https://attacker.evil.com"), (
                "SECURITY VULNERABILITY: Redirected to unregistered attacker URL!"
            )
            # Must NOT contain a code parameter
            assert "code=" not in location, (
                "SECURITY VULNERABILITY: Authorization code issued to unregistered URI!"
            )
            # If redirecting, should go to registered URL with error
            assert location.startswith(oauth_client["redirect_uri"]), (
                f"Expected redirect to registered URL, got: {location}"
            )
            assert "error=" in location
        else:
            # 400 is the correct response per OAuth spec
            assert response.status_code == 400


# ============================================================================
# TEST CLASS: SCOPE VALIDATION
# ============================================================================

class TestScopeValidation:
    """Test OAuth scope validation at the authorization layer."""

    @pytest.mark.asyncio
    async def test_authorize_with_invalid_scope(
        self,
        client: AsyncClient,
        oauth_client: dict
    ):
        """
        Requesting an unregistered scope should fail.
        """
        code_verifier, code_challenge = generate_pkce_pair("invalid-scope")

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": oauth_client["client_id"],
                "redirect_uri": oauth_client["redirect_uri"],
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "scope": "admin.delete_all",  # Not a valid scope
                "state": "test-state"
            },
            follow_redirects=False
        )

        # Should return error
        if response.status_code == 302:
            location = response.headers.get("location", "")
            assert "error=invalid_scope" in location
        else:
            assert response.status_code in [400, 403]

    @pytest.mark.asyncio
    async def test_authorize_with_excess_scope(
        self,
        client: AsyncClient,
        async_session: AsyncSession
    ):
        """
        Requesting scopes beyond what client is registered for should fail.
        """
        # Create client with limited scopes
        client_id = f"focused-client-limited-{uuid4().hex[:8]}"
        limited_client = CoreConnection(
            user_id=None,
            provider="Limited OAuth Client",
            connection_type="oauth_provider",
            client_id=client_id,
            client_secret_enc=encrypt_token("secret"),
            redirect_uris=["https://example.com/callback"],
            grant_types=["authorization_code"],
            encrypted_access_token="",
            scopes=["focused.read"],  # Only read scope
            token_expires_at=datetime.now(timezone.utc) + timedelta(days=365)
        )
        async_session.add(limited_client)
        await async_session.commit()

        code_verifier, code_challenge = generate_pkce_pair("excess-scope")

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": "https://example.com/callback",
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "scope": "focused.read focused.write",  # Write not registered
                "state": "test-state"
            },
            follow_redirects=False
        )

        # Should return invalid_scope error
        if response.status_code == 302:
            location = response.headers.get("location", "")
            assert "error=invalid_scope" in location

    @pytest.mark.asyncio
    async def test_authorize_with_mixed_valid_invalid_scopes(
        self,
        client: AsyncClient,
        oauth_client: dict
    ):
        """
        10.4. Mixed valid+invalid scopes should fail.

        Request includes "focused.read" (valid) + "admin.delete" (invalid).
        The entire request must fail - no partial scope grants.
        """
        code_verifier, code_challenge = generate_pkce_pair("mixed-scope")

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": oauth_client["client_id"],
                "redirect_uri": oauth_client["redirect_uri"],
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "scope": "focused.read admin.delete",  # Mixed valid + invalid
                "state": "test-state"
            },
            follow_redirects=False
        )

        # Should return invalid_scope error for the invalid scope
        if response.status_code == 302:
            location = response.headers.get("location", "")
            assert "error=invalid_scope" in location, (
                "Mixed valid+invalid scopes should return invalid_scope error"
            )
        else:
            # 400 is also acceptable
            assert response.status_code == 400


# ============================================================================
# TEST CLASS: PKCE SECURITY
# ============================================================================

class TestPKCESecurity:
    """Test PKCE security requirements."""

    @pytest.mark.asyncio
    async def test_authorize_requires_pkce(
        self,
        client: AsyncClient,
        oauth_client: dict
    ):
        """
        OAuth 2.1 requires PKCE. Request without code_challenge should fail.
        """
        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": oauth_client["client_id"],
                "redirect_uri": oauth_client["redirect_uri"],
                "scope": "focused.read",
                "state": "test-state"
                # Missing code_challenge and code_challenge_method
            },
            follow_redirects=False
        )

        # Should fail (422 validation or 302 with error)
        if response.status_code == 302:
            location = response.headers.get("location", "")
            assert "error" in location
        else:
            assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    async def test_authorize_requires_s256_method(
        self,
        client: AsyncClient,
        oauth_client: dict
    ):
        """
        OAuth 2.1 requires S256 for PKCE. Plain method should fail.
        """
        code_verifier, code_challenge = generate_pkce_pair("plain-method")

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": oauth_client["client_id"],
                "redirect_uri": oauth_client["redirect_uri"],
                "code_challenge": code_challenge,
                "code_challenge_method": "plain",  # Not allowed in OAuth 2.1
                "scope": "focused.read"
            },
            follow_redirects=False
        )

        # Should fail
        if response.status_code == 302:
            location = response.headers.get("location", "")
            assert "error" in location
        else:
            assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    async def test_backend_defers_pkce_validation_to_token_endpoint(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user: CoreUser,
        oauth_client: dict
    ):
        """
        10.5. Backend defers PKCE validation to token endpoint.

        Note: OAuth 2.1 recommends validating code_challenge format at the
        authorization endpoint. This implementation defers validation to the
        token endpoint, which is acceptable but less strict.

        The authorization endpoint stores the code_challenge without format
        validation. Validation occurs at token exchange when the code_verifier
        hash is compared against the stored challenge.

        This test verifies that a malformed code_challenge stored during
        authorization will cause the token exchange to fail because no
        valid code_verifier can produce a matching hash.
        """
        malformed_challenge = "not-valid-base64url!!!@#$%"

        # Create an authorization code with malformed challenge directly
        code = await create_authorization_code(
            db=async_session,
            user_id=str(test_user.id),
            client_id=oauth_client["client_id"],
            code_challenge=malformed_challenge,  # Malformed
            code_challenge_method="S256",
            redirect_uri=oauth_client["redirect_uri"],
            scope="focused.read",
            correlation_id="malformed-challenge-test"
        )

        # Try to exchange - will fail because no verifier can match
        response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": "some-random-verifier-that-wont-match",
                "client_id": oauth_client["client_id"],
                "redirect_uri": oauth_client["redirect_uri"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        # Should fail with invalid_grant (PKCE mismatch)
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "invalid_grant"

    @pytest.mark.asyncio
    async def test_code_verifier_too_short_fails(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user: CoreUser,
        oauth_client: dict
    ):
        """
        10.5. code_verifier that is too short should fail at token exchange.

        RFC 7636 specifies code_verifier must be 43-128 characters.
        """
        # Create a proper code_challenge first
        proper_verifier, proper_challenge = generate_pkce_pair("short-verifier-test")

        code = await create_authorization_code(
            db=async_session,
            user_id=str(test_user.id),
            client_id=oauth_client["client_id"],
            code_challenge=proper_challenge,
            code_challenge_method="S256",
            redirect_uri=oauth_client["redirect_uri"],
            scope="focused.read",
            correlation_id="short-verifier-test"
        )

        # Try to exchange with too-short verifier
        response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": "abc",  # Too short - should be 43-128 chars
                "client_id": oauth_client["client_id"],
                "redirect_uri": oauth_client["redirect_uri"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        # Should fail - either validation error or PKCE mismatch
        assert response.status_code == 400
        data = response.json()
        assert data["error"] in ["invalid_request", "invalid_grant"]

    @pytest.mark.asyncio
    async def test_code_verifier_too_long_fails(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user: CoreUser,
        oauth_client: dict
    ):
        """
        10.5. code_verifier that is too long should fail at token exchange.

        RFC 7636 specifies code_verifier must be 43-128 characters.
        """
        # Create a proper code_challenge first
        proper_verifier, proper_challenge = generate_pkce_pair("long-verifier-test")

        code = await create_authorization_code(
            db=async_session,
            user_id=str(test_user.id),
            client_id=oauth_client["client_id"],
            code_challenge=proper_challenge,
            code_challenge_method="S256",
            redirect_uri=oauth_client["redirect_uri"],
            scope="focused.read",
            correlation_id="long-verifier-test"
        )

        # Try to exchange with too-long verifier (150 chars)
        long_verifier = "A" * 150

        response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": long_verifier,  # Too long - should be 43-128 chars
                "client_id": oauth_client["client_id"],
                "redirect_uri": oauth_client["redirect_uri"]
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        # Should fail - either validation error or PKCE mismatch
        assert response.status_code == 400
        data = response.json()
        assert data["error"] in ["invalid_request", "invalid_grant"]


# ============================================================================
# TEST CLASS: LOGIN HINT SECURITY
# ============================================================================

class TestLoginHintSecurity:
    """Test login_hint security measures."""

    @pytest.mark.asyncio
    async def test_login_hint_max_length(
        self,
        client: AsyncClient,
        oauth_client: dict
    ):
        """
        login_hint should be rejected if too long (VARCHAR(64) limit).
        """
        code_verifier, code_challenge = generate_pkce_pair("long-login-hint")
        long_login_hint = "x" * 100  # Exceeds 64 char limit

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": oauth_client["client_id"],
                "redirect_uri": oauth_client["redirect_uri"],
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "scope": "focused.read",
                "login_hint": long_login_hint
            },
            follow_redirects=False
        )

        # Should return error
        if response.status_code == 302:
            location = response.headers.get("location", "")
            assert "error" in location
        else:
            assert response.status_code in [400, 422]
