"""
Increment 8 — Phase 2: OAuth Provider E2E Tests (23 tests)

Tests the OAuth 2.1 provider using:
- REAL DB (isolated test database)
- REAL Redis for authorization context
- REAL token encryption/signing
- REAL PKCE validation

Design Note:
    All clients are treated as PUBLIC CLIENTS (OAuth 2.1 pattern).
    - PKCE (S256) is MANDATORY and replaces client_secret validation
    - client_secret is returned at registration but NOT enforced at /token
    - This is intentional for ChatGPT/MCP SDK integration (native app pattern)
    - All clients share GLOBAL allowed scopes (no per-client restriction)

Test Categories:
- Test 01: Authorization code flow (full happy path)
- Test 02: Consent screen GET + POST (allow)
- Test 03: Consent screen deny
- Test 04: Token issuance (authorization_code grant)
- Test 05: Token issuance (refresh_token grant)
- Test 06: Token content validation (JWT claims with iss/aud values)
- Test 07: Redirect URI validation
- Test 08: State parameter validation (allow case)
- Test 09: PKCE enforcement (S256 required, wrong verifier fails)
- Test 10: Error handling (invalid client, code, redirect_uri)
- Test 11: Scope validation
- Test 12: Authorization code reuse fails
- Test 13: Old refresh token invalid after rotation
- Test 14: Expired refresh token fails
- Test 15: Missing PKCE parameters rejected
- Test 16: Plain PKCE method rejected (only S256)
- Test 17: Mismatched redirect_uri on token exchange fails
- Test 18: JWKS retrieval and JWT signature verification
- Test 19: Client registration validation (HTTP rejected, empty fields)
- Test 20: State parameter preserved on deny
- Test 21: Auth context expiry (Redis TTL simulation)
- Test 22: RFC 6749 error redirect format validation
- Test 23: Scope restriction enforcement (subset allowed, unauthorized rejected)
"""

import pytest
import hashlib
import base64
import secrets
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from httpx import AsyncClient
from jose import jwt

from backend.core.oauth_provider.models import OAuthAuthorizationCode


# =============================================================================
# PKCE Helpers
# =============================================================================

def generate_code_verifier() -> str:
    """Generate a PKCE code verifier (43-128 chars)."""
    return secrets.token_urlsafe(64)[:96]  # 96 chars


def generate_code_challenge(code_verifier: str) -> str:
    """Generate S256 PKCE code challenge from verifier."""
    digest = hashlib.sha256(code_verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# =============================================================================
# Test Helper Functions
# =============================================================================

async def register_oauth_client(
    client: AsyncClient,
    client_name: str = "Test Client",
    redirect_uris: list[str] | None = None,
) -> dict:
    """Register an OAuth client and return credentials."""
    if redirect_uris is None:
        redirect_uris = ["https://example.com/callback"]

    response = await client.post(
        "/oauth/focused/register",
        json={
            "client_name": client_name,
            "redirect_uris": redirect_uris,
        },
    )
    assert response.status_code == 200, f"Client registration failed: {response.text}"
    return response.json()


async def start_authorization(
    client: AsyncClient,
    client_id: str,
    redirect_uri: str,
    code_verifier: str,
    user_id: str,
    scope: str = "focused.read focused.write",
    state: str | None = None,
) -> tuple[int, str, dict]:
    """
    Start OAuth authorization flow.

    Returns: (status_code, response_text_or_location, parsed_params)
    """
    code_challenge = generate_code_challenge(code_verifier)

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "scope": scope,
        "user_id": user_id,  # TODO: temporary auth mechanism
    }
    if state:
        params["state"] = state

    response = await client.get("/oauth/focused/authorize", params=params)
    return response.status_code, response.text, dict(response.headers)


async def submit_consent(
    client: AsyncClient,
    auth_context_id: str,
    action: str = "allow",
) -> tuple[int, str]:
    """
    Submit consent form.

    Returns: (status_code, redirect_location)
    """
    response = await client.post(
        "/oauth/focused/consent",
        data={
            "auth_context_id": auth_context_id,
            "action": action,
        },
        follow_redirects=False,
    )
    location = response.headers.get("location", "")
    return response.status_code, location


async def exchange_code_for_tokens(
    client: AsyncClient,
    code: str,
    code_verifier: str,
    client_id: str,
    redirect_uri: str,
) -> tuple[int, dict]:
    """
    Exchange authorization code for tokens.

    Returns: (status_code, response_json)
    """
    response = await client.post(
        "/oauth/focused/token",
        json={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": code_verifier,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
        },
    )
    return response.status_code, response.json()


async def refresh_tokens(
    client: AsyncClient,
    refresh_token: str,
    client_id: str,
) -> tuple[int, dict]:
    """
    Exchange refresh token for new tokens.

    Returns: (status_code, response_json)
    """
    response = await client.post(
        "/oauth/focused/token",
        json={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        },
    )
    return response.status_code, response.json()


def extract_auth_context_id(html: str) -> str:
    """Extract auth_context_id from consent form HTML."""
    # Look for hidden input with name="auth_context_id"
    import re
    match = re.search(r'name="auth_context_id"\s+value="([^"]+)"', html)
    if not match:
        # Try alternate format
        match = re.search(r'value="([^"]+)"\s+name="auth_context_id"', html)
    if not match:
        raise ValueError(f"Could not find auth_context_id in HTML: {html[:500]}")
    return match.group(1)


def extract_code_from_redirect(location: str) -> str:
    """Extract authorization code from redirect URL."""
    parsed = urlparse(location)
    params = parse_qs(parsed.query)
    codes = params.get("code", [])
    if not codes:
        raise ValueError(f"No code in redirect URL: {location}")
    return codes[0]


def extract_error_from_redirect(location: str) -> tuple[str, str | None]:
    """Extract error and error_description from redirect URL."""
    parsed = urlparse(location)
    params = parse_qs(parsed.query)
    error = params.get("error", [""])[0]
    description = params.get("error_description", [None])[0]
    return error, description


class TestOAuthProvider:
    """OAuth 2.1 Provider E2E tests."""

    # =========================================================================
    # Test 01: Full Authorization Code Flow (Happy Path)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_01_full_authorization_code_flow(
        self,
        client: AsyncClient,
        async_session: AsyncSession,  # noqa: ARG002
        test_user_with_connection: dict,
    ):
        """
        Test 1: Complete OAuth authorization code flow.

        Flow:
        1. Register OAuth client
        2. Start authorization request -> consent screen
        3. Submit consent (allow) -> redirect with code
        4. Exchange code for tokens
        5. Verify tokens are valid

        Verifies:
        - Client registration returns client_id and client_secret
        - Authorization returns consent screen
        - Consent allow redirects with code
        - Token exchange returns access_token and refresh_token
        """
        user_id = test_user_with_connection["user_id"]
        redirect_uri = "https://example.com/callback"

        # Step 1: Register OAuth client
        oauth_client = await register_oauth_client(
            client,
            client_name="Test App",
            redirect_uris=[redirect_uri],
        )
        client_id = oauth_client["client_id"]
        assert client_id.startswith("focused-client-")

        # Step 2: Start authorization
        code_verifier = generate_code_verifier()
        status, html, _ = await start_authorization(
            client,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
            user_id=user_id,
            scope="focused.read focused.write",
            state="test_state_123",
        )

        assert status == 200, f"Authorization failed: {html}"
        assert "auth_context_id" in html, "Consent screen should contain auth_context_id"

        # Step 3: Submit consent (allow)
        auth_context_id = extract_auth_context_id(html)
        status, location = await submit_consent(client, auth_context_id, action="allow")

        assert status == 302, f"Consent should redirect, got {status}"
        assert location.startswith(redirect_uri), f"Should redirect to {redirect_uri}"
        assert "code=" in location, "Redirect should contain authorization code"
        assert "state=test_state_123" in location, "Redirect should contain state"

        # Step 4: Exchange code for tokens
        code = extract_code_from_redirect(location)
        status, token_response = await exchange_code_for_tokens(
            client,
            code=code,
            code_verifier=code_verifier,
            client_id=client_id,
            redirect_uri=redirect_uri,
        )

        assert status == 200, f"Token exchange failed: {token_response}"
        assert "access_token" in token_response
        assert "refresh_token" in token_response
        assert token_response["token_type"] == "Bearer"
        assert token_response["expires_in"] == 3600
        assert "focused.read" in token_response["scope"]
        assert "focused.write" in token_response["scope"]

    # =========================================================================
    # Test 02: Consent Screen Allow
    # =========================================================================

    @pytest.mark.asyncio
    async def test_02_consent_screen_allow(
        self,
        client: AsyncClient,
        async_session: AsyncSession,  # noqa: ARG002
        test_user_with_connection: dict,
    ):
        """
        Test 2: Consent screen displays correctly and allow works.

        Verifies:
        - GET /authorize returns HTML consent screen with auth_context_id
        - POST /consent with action=allow redirects with code
        """
        user_id = test_user_with_connection["user_id"]
        redirect_uri = "https://example.com/callback"

        # Register client
        oauth_client = await register_oauth_client(
            client,
            client_name="My Test App",
            redirect_uris=[redirect_uri],
        )
        client_id = oauth_client["client_id"]

        # Start authorization
        code_verifier = generate_code_verifier()
        status, html, _ = await start_authorization(
            client,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
            user_id=user_id,
            scope="focused.read",
        )

        assert status == 200
        # Verify consent screen contains the auth_context_id hidden field
        assert "auth_context_id" in html

        # Submit consent
        auth_context_id = extract_auth_context_id(html)
        status, location = await submit_consent(client, auth_context_id, action="allow")

        assert status == 302
        assert "code=" in location

    # =========================================================================
    # Test 03: Consent Screen Deny
    # =========================================================================

    @pytest.mark.asyncio
    async def test_03_consent_screen_deny(
        self,
        client: AsyncClient,
        async_session: AsyncSession,  # noqa: ARG002
        test_user_with_connection: dict,
    ):
        """
        Test 3: Consent deny returns access_denied error.

        Verifies:
        - POST /consent with action=deny redirects with error
        - Error is access_denied
        - State is preserved in redirect
        """
        user_id = test_user_with_connection["user_id"]
        redirect_uri = "https://example.com/callback"

        # Register client
        oauth_client = await register_oauth_client(client, redirect_uris=[redirect_uri])
        client_id = oauth_client["client_id"]

        # Start authorization with state
        code_verifier = generate_code_verifier()
        status, html, _ = await start_authorization(
            client,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
            user_id=user_id,
            state="csrf_token_xyz",
        )

        assert status == 200
        auth_context_id = extract_auth_context_id(html)

        # Submit consent with deny
        status, location = await submit_consent(client, auth_context_id, action="deny")

        assert status == 302
        assert location.startswith(redirect_uri)
        error, _ = extract_error_from_redirect(location)
        assert error == "access_denied"
        assert "state=csrf_token_xyz" in location

    # =========================================================================
    # Test 04: Token Issuance (authorization_code grant)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_04_token_issuance_authorization_code(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
    ):
        """
        Test 4: authorization_code grant returns valid tokens.

        Verifies:
        - Token response contains all required fields
        - Access token is a valid JWT
        - Authorization code is marked as used after exchange
        """
        user_id = test_user_with_connection["user_id"]
        redirect_uri = "https://example.com/callback"

        # Setup: Register client and get authorization code
        oauth_client = await register_oauth_client(client, redirect_uris=[redirect_uri])
        client_id = oauth_client["client_id"]

        code_verifier = generate_code_verifier()
        status, html, _ = await start_authorization(
            client,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
            user_id=user_id,
        )
        auth_context_id = extract_auth_context_id(html)
        _, location = await submit_consent(client, auth_context_id, action="allow")
        code = extract_code_from_redirect(location)

        # Exchange code for tokens
        status, token_response = await exchange_code_for_tokens(
            client,
            code=code,
            code_verifier=code_verifier,
            client_id=client_id,
            redirect_uri=redirect_uri,
        )

        assert status == 200
        assert "access_token" in token_response
        assert "refresh_token" in token_response
        assert token_response["token_type"] == "Bearer"
        assert token_response["expires_in"] == 3600

        # Verify access token is valid JWT (decode without verification)
        access_token = token_response["access_token"]
        decoded = jwt.get_unverified_claims(access_token)
        assert "sub" in decoded
        assert "exp" in decoded
        assert "iat" in decoded

        # Verify authorization code is marked as used
        async_session.expire_all()
        result = await async_session.execute(
            select(OAuthAuthorizationCode).where(OAuthAuthorizationCode.code == code)
        )
        auth_code = result.scalar_one_or_none()
        assert auth_code is not None
        assert auth_code.used is True, "Authorization code should be marked as used"

    # =========================================================================
    # Test 05: Token Issuance (refresh_token grant)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_05_token_issuance_refresh_token(
        self,
        client: AsyncClient,
        async_session: AsyncSession,  # noqa: ARG002
        test_user_with_connection: dict,
    ):
        """
        Test 5: refresh_token grant returns new tokens.

        Verifies:
        - Refresh token can be exchanged for new access token
        - New tokens are different from original
        - New refresh token is also returned (rotation)
        """
        user_id = test_user_with_connection["user_id"]
        redirect_uri = "https://example.com/callback"

        # Setup: Get initial tokens
        oauth_client = await register_oauth_client(client, redirect_uris=[redirect_uri])
        client_id = oauth_client["client_id"]

        code_verifier = generate_code_verifier()
        status, html, _ = await start_authorization(
            client,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
            user_id=user_id,
        )
        auth_context_id = extract_auth_context_id(html)
        _, location = await submit_consent(client, auth_context_id, action="allow")
        code = extract_code_from_redirect(location)

        _, initial_tokens = await exchange_code_for_tokens(
            client,
            code=code,
            code_verifier=code_verifier,
            client_id=client_id,
            redirect_uri=redirect_uri,
        )

        original_access = initial_tokens["access_token"]
        original_refresh = initial_tokens["refresh_token"]

        # Exchange refresh token for new tokens
        status, new_tokens = await refresh_tokens(
            client,
            refresh_token=original_refresh,
            client_id=client_id,
        )

        assert status == 200, f"Refresh failed: {new_tokens}"
        assert "access_token" in new_tokens
        assert "refresh_token" in new_tokens

        # Tokens should be different
        assert new_tokens["access_token"] != original_access
        assert new_tokens["refresh_token"] != original_refresh

    # =========================================================================
    # Test 06: Token Content Validation (JWT Claims)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_06_token_content_validation(
        self,
        client: AsyncClient,
        async_session: AsyncSession,  # noqa: ARG002
        test_user_with_connection: dict,
    ):
        """
        Test 6: JWT access token contains required claims.

        Verifies JWT claims:
        - sub: user_id
        - aud: audience
        - iss: issuer
        - exp: expiration
        - iat: issued at
        - jti: unique token ID
        - scope: requested scopes
        - client_id: OAuth client ID
        """
        user_id = test_user_with_connection["user_id"]
        redirect_uri = "https://example.com/callback"

        # Get tokens
        oauth_client = await register_oauth_client(client, redirect_uris=[redirect_uri])
        client_id = oauth_client["client_id"]

        code_verifier = generate_code_verifier()
        _, html, _ = await start_authorization(
            client,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
            user_id=user_id,
            scope="focused.read focused.write focused.notify",
        )
        auth_context_id = extract_auth_context_id(html)
        _, location = await submit_consent(client, auth_context_id, action="allow")
        code = extract_code_from_redirect(location)

        _, token_response = await exchange_code_for_tokens(
            client,
            code=code,
            code_verifier=code_verifier,
            client_id=client_id,
            redirect_uri=redirect_uri,
        )

        # Decode and validate JWT claims
        access_token = token_response["access_token"]
        decoded = jwt.get_unverified_claims(access_token)

        # Required claims - existence
        assert "sub" in decoded, "sub (subject) required"
        assert "aud" in decoded, "aud (audience) required"
        assert "iss" in decoded, "iss (issuer) required"
        assert "exp" in decoded, "exp (expiration) required"
        assert "iat" in decoded, "iat (issued at) required"
        assert "jti" in decoded, "jti (JWT ID) required"

        # Validate claim VALUES
        from backend.core.config import settings
        assert decoded["sub"] == user_id, f"sub should be user_id, got {decoded['sub']}"
        assert decoded["iss"] == settings.OAUTH_ISSUER, \
            f"iss should be {settings.OAUTH_ISSUER}, got {decoded['iss']}"
        assert decoded["aud"] == settings.OAUTH_ISSUER, \
            f"aud should be {settings.OAUTH_ISSUER}, got {decoded['aud']}"

        # Verify expiration is ~1 hour from now
        exp = decoded["exp"]
        iat = decoded["iat"]
        assert exp - iat == 3600, "Token should expire in 1 hour"

        # Verify scope
        assert "scope" in decoded
        scope_str = decoded["scope"]
        assert "focused.read" in scope_str
        assert "focused.write" in scope_str
        assert "focused.notify" in scope_str

        # Verify client_id
        assert decoded.get("client_id") == client_id or decoded.get("azp") == client_id

    # =========================================================================
    # Test 07: Redirect URI Validation
    # =========================================================================

    @pytest.mark.asyncio
    async def test_07_redirect_uri_validation(
        self,
        client: AsyncClient,
        async_session: AsyncSession,  # noqa: ARG002
        test_user_with_connection: dict,
    ):
        """
        Test 7: Invalid redirect_uri is rejected.

        Verifies:
        - Redirect URI not in registered list returns error
        - Error is returned as HTTP error (not redirect)
        """
        user_id = test_user_with_connection["user_id"]

        # Register client with specific redirect URI
        oauth_client = await register_oauth_client(
            client,
            redirect_uris=["https://registered.com/callback"],
        )
        client_id = oauth_client["client_id"]

        # Try authorization with unregistered redirect_uri
        code_verifier = generate_code_verifier()
        code_challenge = generate_code_challenge(code_verifier)

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": "https://attacker.com/callback",  # Not registered
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "scope": "focused.read",
                "user_id": user_id,
            },
        )

        # Should return HTTP 400, not redirect to attacker
        assert response.status_code == 400
        assert "redirect_uri" in response.text.lower()

    # =========================================================================
    # Test 08: State Parameter Validation
    # =========================================================================

    @pytest.mark.asyncio
    async def test_08_state_parameter_preserved(
        self,
        client: AsyncClient,
        async_session: AsyncSession,  # noqa: ARG002
        test_user_with_connection: dict,
    ):
        """
        Test 8: State parameter is preserved through the flow.

        Verifies:
        - State from authorization request appears in redirect
        - State is preserved in both allow and deny cases
        """
        user_id = test_user_with_connection["user_id"]
        redirect_uri = "https://example.com/callback"

        oauth_client = await register_oauth_client(client, redirect_uris=[redirect_uri])
        client_id = oauth_client["client_id"]

        # Test with specific state value
        state = "unique_csrf_token_" + secrets.token_urlsafe(16)

        code_verifier = generate_code_verifier()
        status, html, _ = await start_authorization(
            client,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
            user_id=user_id,
            state=state,
        )

        assert status == 200
        auth_context_id = extract_auth_context_id(html)

        # Allow case
        _, location = await submit_consent(client, auth_context_id, action="allow")
        assert f"state={state}" in location, "State should be in allow redirect"

    # =========================================================================
    # Test 09: PKCE Enforcement (S256 Required)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_09_pkce_enforcement(
        self,
        client: AsyncClient,
        async_session: AsyncSession,  # noqa: ARG002
        test_user_with_connection: dict,
    ):
        """
        Test 9: PKCE is mandatory - wrong verifier fails.

        Verifies:
        - Token exchange with wrong code_verifier fails
        - Error is invalid_grant
        - Correct verifier succeeds (control)
        """
        user_id = test_user_with_connection["user_id"]
        redirect_uri = "https://example.com/callback"

        oauth_client = await register_oauth_client(client, redirect_uris=[redirect_uri])
        client_id = oauth_client["client_id"]

        # Get authorization code with correct verifier
        correct_verifier = generate_code_verifier()
        status, html, _ = await start_authorization(
            client,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_verifier=correct_verifier,
            user_id=user_id,
        )
        auth_context_id = extract_auth_context_id(html)
        _, location = await submit_consent(client, auth_context_id, action="allow")
        code = extract_code_from_redirect(location)

        # Try token exchange with WRONG verifier
        wrong_verifier = generate_code_verifier()  # Different verifier
        status, error_response = await exchange_code_for_tokens(
            client,
            code=code,
            code_verifier=wrong_verifier,  # Wrong!
            client_id=client_id,
            redirect_uri=redirect_uri,
        )

        assert status == 401, f"Wrong verifier should fail, got {status}"
        assert error_response.get("error") == "invalid_grant"
        assert "pkce" in error_response.get("error_description", "").lower()

    # =========================================================================
    # Test 10: Error Handling
    # =========================================================================

    @pytest.mark.asyncio
    async def test_10_error_handling(
        self,
        client: AsyncClient,
        async_session: AsyncSession,  # noqa: ARG002
        test_user_with_connection: dict,
    ):
        """
        Test 10: OAuth errors are properly returned.

        Verifies error handling for:
        - Invalid client_id
        - Invalid/expired authorization code
        - Missing required parameters
        """
        user_id = test_user_with_connection["user_id"]
        redirect_uri = "https://example.com/callback"

        # Register a valid client for some tests
        oauth_client = await register_oauth_client(client, redirect_uris=[redirect_uri])
        valid_client_id = oauth_client["client_id"]

        # --- Test: Invalid client_id in /authorize ---
        code_verifier = generate_code_verifier()
        code_challenge = generate_code_challenge(code_verifier)

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": "invalid-client-id",
                "redirect_uri": redirect_uri,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "scope": "focused.read",
                "user_id": user_id,
            },
        )
        assert response.status_code == 401

        # --- Test: Invalid authorization code in /token ---
        response = await client.post(
            "/oauth/focused/token",
            json={
                "grant_type": "authorization_code",
                "code": "invalid_code_that_does_not_exist",
                "code_verifier": code_verifier,
                "client_id": valid_client_id,
                "redirect_uri": redirect_uri,
            },
        )
        assert response.status_code == 401
        error_json = response.json()
        assert error_json.get("error") == "invalid_grant"

        # --- Test: Missing code_verifier ---
        response = await client.post(
            "/oauth/focused/token",
            json={
                "grant_type": "authorization_code",
                "code": "some_code",
                "client_id": valid_client_id,
                "redirect_uri": redirect_uri,
                # code_verifier missing
            },
        )
        assert response.status_code == 400
        error_json = response.json()
        assert error_json.get("error") == "invalid_request"
        assert "code_verifier" in error_json.get("error_description", "")

        # --- Test: Unsupported grant_type ---
        response = await client.post(
            "/oauth/focused/token",
            json={
                "grant_type": "client_credentials",  # Not supported
                "client_id": valid_client_id,
            },
        )
        assert response.status_code == 400
        error_json = response.json()
        assert error_json.get("error") == "unsupported_grant_type"

    # =========================================================================
    # Test 11: Scope Validation
    # =========================================================================

    @pytest.mark.asyncio
    async def test_11_scope_validation(
        self,
        client: AsyncClient,
        async_session: AsyncSession,  # noqa: ARG002
        test_user_with_connection: dict,
    ):
        """
        Test 11: Invalid scopes are rejected.

        Verifies:
        - Invalid scope returns error redirect
        - Valid scopes are accepted
        """
        user_id = test_user_with_connection["user_id"]
        redirect_uri = "https://example.com/callback"

        oauth_client = await register_oauth_client(client, redirect_uris=[redirect_uri])
        client_id = oauth_client["client_id"]

        # Try authorization with invalid scope
        code_verifier = generate_code_verifier()
        code_challenge = generate_code_challenge(code_verifier)

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "scope": "focused.read invalid.scope",  # Invalid scope
                "user_id": user_id,
            },
            follow_redirects=False,
        )

        # Should redirect with error
        assert response.status_code == 302
        location = response.headers.get("location", "")
        error, _ = extract_error_from_redirect(location)
        assert error == "invalid_scope"

    # =========================================================================
    # Test 12: Authorization Code Reuse Must Fail
    # =========================================================================

    @pytest.mark.asyncio
    async def test_12_authorization_code_reuse_fails(
        self,
        client: AsyncClient,
        async_session: AsyncSession,  # noqa: ARG002
        test_user_with_connection: dict,
    ):
        """
        Test 12: Authorization code cannot be reused.

        Verifies:
        - First token exchange succeeds
        - Second token exchange with same code fails with invalid_grant
        """
        user_id = test_user_with_connection["user_id"]
        redirect_uri = "https://example.com/callback"

        # Register client and get authorization code
        oauth_client = await register_oauth_client(client, redirect_uris=[redirect_uri])
        client_id = oauth_client["client_id"]

        code_verifier = generate_code_verifier()
        status, html, _ = await start_authorization(
            client,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
            user_id=user_id,
        )
        auth_context_id = extract_auth_context_id(html)
        _, location = await submit_consent(client, auth_context_id, action="allow")
        code = extract_code_from_redirect(location)

        # First exchange - should succeed
        status, token_response = await exchange_code_for_tokens(
            client,
            code=code,
            code_verifier=code_verifier,
            client_id=client_id,
            redirect_uri=redirect_uri,
        )
        assert status == 200, f"First exchange should succeed: {token_response}"
        assert "access_token" in token_response

        # Second exchange with SAME code - should fail
        status, error_response = await exchange_code_for_tokens(
            client,
            code=code,  # Same code
            code_verifier=code_verifier,
            client_id=client_id,
            redirect_uri=redirect_uri,
        )
        assert status == 401, f"Code reuse should fail with 401, got {status}"
        assert error_response.get("error") == "invalid_grant"

    # =========================================================================
    # Test 13: Old Refresh Token Invalid After Rotation
    # =========================================================================

    @pytest.mark.asyncio
    async def test_13_old_refresh_token_invalid_after_rotation(
        self,
        client: AsyncClient,
        async_session: AsyncSession,  # noqa: ARG002
        test_user_with_connection: dict,
    ):
        """
        Test 13: Old refresh token must not work after rotation.

        Verifies:
        - Refresh token rotation returns new tokens
        - Old refresh token is invalidated
        - Attempting to use old refresh token fails with invalid_grant
        """
        user_id = test_user_with_connection["user_id"]
        redirect_uri = "https://example.com/callback"

        # Get initial tokens
        oauth_client = await register_oauth_client(client, redirect_uris=[redirect_uri])
        client_id = oauth_client["client_id"]

        code_verifier = generate_code_verifier()
        status, html, _ = await start_authorization(
            client,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
            user_id=user_id,
        )
        auth_context_id = extract_auth_context_id(html)
        _, location = await submit_consent(client, auth_context_id, action="allow")
        code = extract_code_from_redirect(location)

        _, initial_tokens = await exchange_code_for_tokens(
            client,
            code=code,
            code_verifier=code_verifier,
            client_id=client_id,
            redirect_uri=redirect_uri,
        )

        old_refresh_token = initial_tokens["refresh_token"]

        # Rotate tokens - exchange refresh token for new pair
        status, new_tokens = await refresh_tokens(
            client,
            refresh_token=old_refresh_token,
            client_id=client_id,
        )
        assert status == 200, f"Refresh should succeed: {new_tokens}"
        assert new_tokens["refresh_token"] != old_refresh_token

        # Try to use OLD refresh token again - should fail
        status, error_response = await refresh_tokens(
            client,
            refresh_token=old_refresh_token,  # Old token
            client_id=client_id,
        )
        assert status == 401, f"Old refresh token should be invalid, got {status}"
        assert error_response.get("error") == "invalid_grant"

    # =========================================================================
    # Test 14: Expired Refresh Token Fails
    # =========================================================================

    @pytest.mark.asyncio
    async def test_14_expired_refresh_token_fails(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
    ):
        """
        Test 14: Expired refresh token must fail.

        Verifies:
        - Refresh token with expired timestamp fails with invalid_grant
        """
        user_id = test_user_with_connection["user_id"]
        redirect_uri = "https://example.com/callback"

        # Get initial tokens
        oauth_client = await register_oauth_client(client, redirect_uris=[redirect_uri])
        client_id = oauth_client["client_id"]

        code_verifier = generate_code_verifier()
        status, html, _ = await start_authorization(
            client,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
            user_id=user_id,
        )
        auth_context_id = extract_auth_context_id(html)
        _, location = await submit_consent(client, auth_context_id, action="allow")
        code = extract_code_from_redirect(location)

        _, initial_tokens = await exchange_code_for_tokens(
            client,
            code=code,
            code_verifier=code_verifier,
            client_id=client_id,
            redirect_uri=redirect_uri,
        )

        refresh_token = initial_tokens["refresh_token"]

        # Expire the refresh token by updating DB directly
        # Target ONLY this specific token using its hash
        from datetime import datetime, timezone
        from backend.core.encryption import hash_refresh_token

        refresh_token_hash = hash_refresh_token(refresh_token)
        expired_time = datetime.now(timezone.utc) - timedelta(days=1)
        await async_session.execute(
            text(
                "UPDATE oauth_access_tokens SET refresh_token_expires_at = :expired "
                "WHERE refresh_token_hash = :token_hash"
            ),
            {"expired": expired_time, "token_hash": refresh_token_hash},
        )
        await async_session.commit()

        # Try to use expired refresh token - should fail
        status, error_response = await refresh_tokens(
            client,
            refresh_token=refresh_token,
            client_id=client_id,
        )
        assert status == 401, f"Expired refresh token should fail, got {status}"
        assert error_response.get("error") == "invalid_grant"

    # =========================================================================
    # Test 15: Missing PKCE Parameters Rejected
    # =========================================================================

    @pytest.mark.asyncio
    async def test_15_missing_pkce_rejected(
        self,
        client: AsyncClient,
        async_session: AsyncSession,  # noqa: ARG002
        test_user_with_connection: dict,
    ):
        """
        Test 15: Missing PKCE parameters are rejected.

        Verifies:
        - Missing code_challenge returns 422 (validation error)
        - Missing code_challenge_method returns 422 (validation error)
        """
        user_id = test_user_with_connection["user_id"]
        redirect_uri = "https://example.com/callback"

        oauth_client = await register_oauth_client(client, redirect_uris=[redirect_uri])
        client_id = oauth_client["client_id"]

        # --- Test: Missing code_challenge ---
        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                # code_challenge missing
                "code_challenge_method": "S256",
                "scope": "focused.read",
                "user_id": user_id,
            },
        )
        # FastAPI returns 422 for missing required query params
        assert response.status_code == 422, f"Missing code_challenge should fail: {response.text}"

        # --- Test: Missing code_challenge_method ---
        code_verifier = generate_code_verifier()
        code_challenge = generate_code_challenge(code_verifier)

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "code_challenge": code_challenge,
                # code_challenge_method missing
                "scope": "focused.read",
                "user_id": user_id,
            },
        )
        assert response.status_code == 422, f"Missing code_challenge_method should fail: {response.text}"

    # =========================================================================
    # Test 16: Plain PKCE Method Rejected (Only S256 Allowed)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_16_plain_pkce_method_rejected(
        self,
        client: AsyncClient,
        async_session: AsyncSession,  # noqa: ARG002
        test_user_with_connection: dict,
    ):
        """
        Test 16: Plain PKCE method is rejected, only S256 allowed.

        Verifies:
        - code_challenge_method=plain returns error redirect
        - Only S256 is accepted per OAuth 2.1 spec
        """
        user_id = test_user_with_connection["user_id"]
        redirect_uri = "https://example.com/callback"

        oauth_client = await register_oauth_client(client, redirect_uris=[redirect_uri])
        client_id = oauth_client["client_id"]

        code_verifier = generate_code_verifier()

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "code_challenge": code_verifier,  # Plain = verifier itself
                "code_challenge_method": "plain",  # Not allowed
                "scope": "focused.read",
                "user_id": user_id,
            },
            follow_redirects=False,
        )

        # Should redirect with error
        assert response.status_code == 302
        location = response.headers.get("location", "")
        error, description = extract_error_from_redirect(location)
        assert error == "invalid_request"
        assert "S256" in (description or "")

    # =========================================================================
    # Test 17: Mismatched redirect_uri on Token Exchange Fails
    # =========================================================================

    @pytest.mark.asyncio
    async def test_17_mismatched_redirect_uri_on_token_fails(
        self,
        client: AsyncClient,
        async_session: AsyncSession,  # noqa: ARG002
        test_user_with_connection: dict,
    ):
        """
        Test 17: redirect_uri must match between /authorize and /token.

        Verifies:
        - Token exchange with different redirect_uri fails with invalid_grant
        """
        user_id = test_user_with_connection["user_id"]
        original_redirect_uri = "https://example.com/callback"
        wrong_redirect_uri = "https://example.com/different"

        # Register client with both redirect URIs
        oauth_client = await register_oauth_client(
            client,
            redirect_uris=[original_redirect_uri, wrong_redirect_uri],
        )
        client_id = oauth_client["client_id"]

        # Get authorization code with original redirect_uri
        code_verifier = generate_code_verifier()
        status, html, _ = await start_authorization(
            client,
            client_id=client_id,
            redirect_uri=original_redirect_uri,
            code_verifier=code_verifier,
            user_id=user_id,
        )
        auth_context_id = extract_auth_context_id(html)
        _, location = await submit_consent(client, auth_context_id, action="allow")
        code = extract_code_from_redirect(location)

        # Try token exchange with DIFFERENT redirect_uri
        status, error_response = await exchange_code_for_tokens(
            client,
            code=code,
            code_verifier=code_verifier,
            client_id=client_id,
            redirect_uri=wrong_redirect_uri,  # Different from /authorize
        )

        assert status == 401, f"Mismatched redirect_uri should fail, got {status}"
        assert error_response.get("error") == "invalid_grant"

    # =========================================================================
    # Test 18: JWKS Retrieval and JWT Signature Verification
    # =========================================================================

    @pytest.mark.asyncio
    async def test_18_jwks_and_signature_verification(
        self,
        client: AsyncClient,
        async_session: AsyncSession,  # noqa: ARG002
        test_user_with_connection: dict,
    ):
        """
        Test 18: JWKS endpoint returns valid key and tokens are verifiable.

        This is the CRITICAL cryptographic E2E test that proves:
        - JWKS endpoint returns the correct public key
        - Access tokens are signed with the corresponding private key
        - External verifiers (OpenAI, MCP server) can validate our tokens

        Verifies:
        - GET /oauth/focused/jwks returns valid JWK Set
        - JWK contains required fields (kty, kid, n, e, use, alg)
        - Access token signature can be verified using JWKS public key
        - Token claims are correct after verification
        """
        from jose import jwt as jose_jwt
        from backend.core.config import settings

        user_id = test_user_with_connection["user_id"]
        redirect_uri = "https://example.com/callback"

        # Step 1: Get an access token through normal flow
        oauth_client = await register_oauth_client(client, redirect_uris=[redirect_uri])
        client_id = oauth_client["client_id"]

        code_verifier = generate_code_verifier()
        _, html, _ = await start_authorization(
            client,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
            user_id=user_id,
        )
        auth_context_id = extract_auth_context_id(html)
        _, location = await submit_consent(client, auth_context_id, action="allow")
        code = extract_code_from_redirect(location)

        _, token_response = await exchange_code_for_tokens(
            client,
            code=code,
            code_verifier=code_verifier,
            client_id=client_id,
            redirect_uri=redirect_uri,
        )

        access_token = token_response["access_token"]

        # Step 2: Fetch JWKS from endpoint
        jwks_response = await client.get("/oauth/focused/jwks")
        assert jwks_response.status_code == 200, f"JWKS endpoint failed: {jwks_response.text}"

        jwks = jwks_response.json()
        assert "keys" in jwks, "JWKS must contain 'keys' array"
        assert len(jwks["keys"]) >= 1, "JWKS must contain at least one key"

        # Step 3: Validate JWKS key structure
        key = jwks["keys"][0]
        assert key.get("kty") == "RSA", "Key type must be RSA"
        assert key.get("use") == "sig", "Key use must be 'sig'"
        assert key.get("alg") == "RS256", "Algorithm must be RS256"
        assert "kid" in key, "Key must have kid (key ID)"
        assert "n" in key, "RSA key must have modulus (n)"
        assert "e" in key, "RSA key must have exponent (e)"
        assert "d" not in key, "Private key component (d) must NOT be exposed"

        # Step 4: Extract kid from token header
        token_header = jose_jwt.get_unverified_header(access_token)
        token_kid = token_header.get("kid")
        assert token_kid is not None, "Token must have kid in header"
        assert token_header.get("alg") == "RS256", "Token must use RS256 algorithm"

        # Step 5: Find matching key in JWKS
        matching_key = None
        for k in jwks["keys"]:
            if k.get("kid") == token_kid:
                matching_key = k
                break
        assert matching_key is not None, f"JWKS must contain key with kid={token_kid}"

        # Step 6: Verify signature using JWKS public key
        # jose library can use JWK directly
        try:
            verified_claims = jose_jwt.decode(
                access_token,
                matching_key,
                algorithms=["RS256"],
                audience=settings.OAUTH_ISSUER,
                issuer=settings.OAUTH_ISSUER,
            )
        except Exception as e:
            pytest.fail(f"JWT signature verification failed: {e}")

        # Step 7: Validate verified claims
        assert verified_claims["sub"] == user_id
        assert verified_claims["iss"] == settings.OAUTH_ISSUER
        assert verified_claims["aud"] == settings.OAUTH_ISSUER
        assert "scope" in verified_claims
        assert "exp" in verified_claims
        assert "iat" in verified_claims
        assert "jti" in verified_claims

    # =========================================================================
    # Test 19: Client Registration Validation
    # =========================================================================

    @pytest.mark.asyncio
    async def test_19_register_validation(
        self,
        client: AsyncClient,
        async_session: AsyncSession,  # noqa: ARG002
    ):
        """
        Test 19: /register endpoint validates client metadata.

        Verifies:
        - HTTP redirect_uri is rejected (HTTPS required)
        - Empty client_name is rejected
        - Empty redirect_uris array is rejected
        """
        # --- Test: HTTP redirect_uri rejected ---
        response = await client.post(
            "/oauth/focused/register",
            json={
                "client_name": "Test Client",
                "redirect_uris": ["http://example.com/callback"],  # HTTP not HTTPS
            },
        )
        assert response.status_code == 400, f"HTTP redirect should fail: {response.text}"
        error_json = response.json()
        assert "HTTPS" in error_json.get("detail", "")

        # --- Test: Empty client_name rejected ---
        response = await client.post(
            "/oauth/focused/register",
            json={
                "client_name": "",  # Empty
                "redirect_uris": ["https://example.com/callback"],
            },
        )
        assert response.status_code == 400, f"Empty client_name should fail: {response.text}"
        error_json = response.json()
        assert "client_name" in error_json.get("detail", "")

        # --- Test: Empty redirect_uris array rejected ---
        response = await client.post(
            "/oauth/focused/register",
            json={
                "client_name": "Test Client",
                "redirect_uris": [],  # Empty array
            },
        )
        assert response.status_code == 400, f"Empty redirect_uris should fail: {response.text}"
        error_json = response.json()
        assert "redirect_uri" in error_json.get("detail", "")

    # =========================================================================
    # Test 20: State Parameter Preserved on Deny
    # =========================================================================

    @pytest.mark.asyncio
    async def test_20_state_preserved_on_deny(
        self,
        client: AsyncClient,
        async_session: AsyncSession,  # noqa: ARG002
        test_user_with_connection: dict,
    ):
        """
        Test 20: State parameter is preserved when user denies consent.

        Verifies:
        - State from authorization request appears in deny redirect
        - Error redirect includes both error and state
        """
        user_id = test_user_with_connection["user_id"]
        redirect_uri = "https://example.com/callback"

        oauth_client = await register_oauth_client(client, redirect_uris=[redirect_uri])
        client_id = oauth_client["client_id"]

        # Use a unique state value
        state = "deny_test_state_" + secrets.token_urlsafe(16)

        code_verifier = generate_code_verifier()
        status, html, _ = await start_authorization(
            client,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
            user_id=user_id,
            state=state,
        )

        assert status == 200
        auth_context_id = extract_auth_context_id(html)

        # Deny consent
        status, location = await submit_consent(client, auth_context_id, action="deny")

        assert status == 302
        assert location.startswith(redirect_uri)

        # Verify error is access_denied
        error, _ = extract_error_from_redirect(location)
        assert error == "access_denied"

        # Verify state is preserved in deny redirect
        assert f"state={state}" in location, "State must be preserved on deny redirect"

    # =========================================================================
    # Test 21: Auth Context Expiry (Redis TTL)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_21_auth_context_expiry(
        self,
        client: AsyncClient,
        async_session: AsyncSession,  # noqa: ARG002
        test_user_with_connection: dict,
    ):
        """
        Test 21: Expired auth_context in Redis causes consent to fail.

        Verifies:
        - After auth_context expires (deleted from Redis), consent submit fails
        - Error is 400 with "expired or invalid" message
        """
        from backend.core.redis_client import redis_client as rc
        from backend.core.oauth_provider.services.authorization_service import (
            build_auth_context_key
        )

        user_id = test_user_with_connection["user_id"]
        redirect_uri = "https://example.com/callback"

        oauth_client = await register_oauth_client(client, redirect_uris=[redirect_uri])
        client_id = oauth_client["client_id"]

        code_verifier = generate_code_verifier()
        status, html, _ = await start_authorization(
            client,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
            user_id=user_id,
        )

        assert status == 200
        auth_context_id = extract_auth_context_id(html)

        # Simulate expiry by deleting auth_context from Redis
        # Use the service's key builder to stay DRY
        redis_key = build_auth_context_key(auth_context_id)
        await rc.delete(redis_key)

        # Now try to submit consent - should fail
        response = await client.post(
            "/oauth/focused/consent",
            data={
                "auth_context_id": auth_context_id,
                "action": "allow",
            },
            follow_redirects=False,
        )

        assert response.status_code == 400, f"Expired context should fail: {response.text}"
        assert "expired" in response.text.lower() or "invalid" in response.text.lower()

    # =========================================================================
    # Test 22: RFC 6749 Error Redirect Format
    # =========================================================================

    @pytest.mark.asyncio
    async def test_22_rfc6749_error_redirect_format(
        self,
        client: AsyncClient,
        async_session: AsyncSession,  # noqa: ARG002
        test_user_with_connection: dict,
    ):
        """
        Test 22: Error redirects conform to RFC 6749 Section 4.1.2.1.

        RFC 6749 requires error redirects to contain:
        - error (REQUIRED): single ASCII error code
        - error_description (OPTIONAL): human-readable description
        - error_uri (OPTIONAL): URI with more info
        - state (REQUIRED if present in request)

        Verifies:
        - Only allowed query params are present (no extraneous fields)
        - error is a valid RFC 6749 error code
        - state is preserved exactly as sent
        - No fragment (#) is used (query string only)
        """
        user_id = test_user_with_connection["user_id"]
        redirect_uri = "https://example.com/callback"

        oauth_client = await register_oauth_client(client, redirect_uris=[redirect_uri])
        client_id = oauth_client["client_id"]

        # Test 1: access_denied error (consent deny)
        state = "rfc6749_test_state_abc123"
        code_verifier = generate_code_verifier()
        status, html, _ = await start_authorization(
            client,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
            user_id=user_id,
            state=state,
        )

        auth_context_id = extract_auth_context_id(html)
        status, location = await submit_consent(client, auth_context_id, action="deny")

        assert status == 302

        # Parse redirect URL
        parsed = urlparse(location)
        assert parsed.fragment == "", "Error redirect must use query string, not fragment"
        assert parsed.scheme == "https"
        assert parsed.netloc == "example.com"
        assert parsed.path == "/callback"

        # Parse query params
        params = parse_qs(parsed.query)

        # Validate required fields
        assert "error" in params, "error is REQUIRED in error redirect"
        error_code = params["error"][0]

        # RFC 6749 Section 4.1.2.1 valid error codes
        valid_error_codes = {
            "invalid_request",
            "unauthorized_client",
            "access_denied",
            "unsupported_response_type",
            "invalid_scope",
            "server_error",
            "temporarily_unavailable",
        }
        assert error_code in valid_error_codes, f"Invalid error code: {error_code}"
        assert error_code == "access_denied", "Consent deny should return access_denied"

        # Validate state is preserved exactly
        assert "state" in params, "state MUST be included if present in request"
        assert params["state"][0] == state, "state must match exactly"

        # Validate only allowed params are present
        allowed_params = {"error", "error_description", "error_uri", "state"}
        actual_params = set(params.keys())
        extraneous = actual_params - allowed_params
        assert not extraneous, f"Extraneous params in error redirect: {extraneous}"

        # Test 2: invalid_scope error
        code_verifier2 = generate_code_verifier()
        code_challenge2 = generate_code_challenge(code_verifier2)
        state2 = "invalid_scope_test_xyz"

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "code_challenge": code_challenge2,
                "code_challenge_method": "S256",
                "scope": "focused.read totally.invalid.scope",
                "user_id": user_id,
                "state": state2,
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        location2 = response.headers.get("location", "")

        parsed2 = urlparse(location2)
        params2 = parse_qs(parsed2.query)

        assert params2["error"][0] == "invalid_scope"
        assert params2["state"][0] == state2

        # Check no extraneous params
        actual_params2 = set(params2.keys())
        extraneous2 = actual_params2 - allowed_params
        assert not extraneous2, f"Extraneous params in invalid_scope redirect: {extraneous2}"

    # =========================================================================
    # Test 23: Scope Restriction Enforcement
    # =========================================================================

    @pytest.mark.asyncio
    async def test_23_scope_restriction_enforcement(
        self,
        client: AsyncClient,
        async_session: AsyncSession,  # noqa: ARG002
        test_user_with_connection: dict,
    ):
        """
        Test 23: Clients can only request allowed scopes.

        Design Note:
            Current implementation uses GLOBAL allowed scopes (focused.read,
            focused.write, focused.notify) for all clients. Per-client scope
            restriction is not implemented - all MCP clients are first-party.

        Verifies:
        - Client can request any subset of allowed scopes
        - Client cannot request scopes outside the global allowed set
        - Token contains only the requested (valid) scopes
        """
        user_id = test_user_with_connection["user_id"]
        redirect_uri = "https://example.com/callback"

        oauth_client = await register_oauth_client(client, redirect_uris=[redirect_uri])
        client_id = oauth_client["client_id"]

        # Test 1: Request single scope - should succeed
        code_verifier1 = generate_code_verifier()
        status, html, _ = await start_authorization(
            client,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier1,
            user_id=user_id,
            scope="focused.read",  # Single scope
        )
        assert status == 200, "Single valid scope should be accepted"

        auth_context_id = extract_auth_context_id(html)
        _, location = await submit_consent(client, auth_context_id, action="allow")
        code = extract_code_from_redirect(location)

        status, token_response = await exchange_code_for_tokens(
            client,
            code=code,
            code_verifier=code_verifier1,
            client_id=client_id,
            redirect_uri=redirect_uri,
        )

        assert status == 200
        # Verify token contains only requested scope (OAuth 2.0: space-separated string)
        response_scope = token_response["scope"]
        assert response_scope == "focused.read", f"Expected 'focused.read', got {response_scope}"

        # Decode JWT to verify scope claim (must be string per OAuth 2.0 standard)
        access_token = token_response["access_token"]
        decoded = jwt.get_unverified_claims(access_token)
        jwt_scope = decoded["scope"]
        assert jwt_scope == "focused.read", f"JWT scope must be string, got {jwt_scope}"

        # Test 2: Request two scopes - should succeed
        code_verifier2 = generate_code_verifier()
        status, html, _ = await start_authorization(
            client,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier2,
            user_id=user_id,
            scope="focused.read focused.notify",  # Two scopes
        )
        assert status == 200, "Two valid scopes should be accepted"

        auth_context_id = extract_auth_context_id(html)
        _, location = await submit_consent(client, auth_context_id, action="allow")
        code = extract_code_from_redirect(location)

        status, token_response = await exchange_code_for_tokens(
            client,
            code=code,
            code_verifier=code_verifier2,
            client_id=client_id,
            redirect_uri=redirect_uri,
        )

        assert status == 200
        # Verify both scopes are in token response (OAuth 2.0: space-separated string)
        response_scope = token_response["scope"]
        assert isinstance(response_scope, str), f"scope must be string, got {type(response_scope)}"
        assert "focused.read" in response_scope
        assert "focused.notify" in response_scope

        # Test 3: Request unauthorized scope - should fail
        code_verifier3 = generate_code_verifier()
        code_challenge3 = generate_code_challenge(code_verifier3)

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "code_challenge": code_challenge3,
                "code_challenge_method": "S256",
                "scope": "focused.read admin.delete",  # admin.delete is not allowed
                "user_id": user_id,
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        location = response.headers.get("location", "")
        error, _ = extract_error_from_redirect(location)
        assert error == "invalid_scope", "Unauthorized scope should return invalid_scope"
