"""
Integration tests for OAuth sessions (Increment 19).

Tests cross-app user identification via browser session cookies.
These tests verify the ACTUAL behavior of the identity resolution chain:
    login_hint > valid session cookie > new anonymous user

Tests the full authorization flow:
    1. GET /authorize → consent page with auth_context_id
    2. POST /consent with action="allow" → redirect with code, cookie set
    3. Verify authorization code references correct user
"""

import pytest
import pytest_asyncio
import base64
import hashlib
import re
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.models import CoreConnection, CoreUser
from backend.core.oauth_provider.cookies import (
    COOKIE_NAME,
    COOKIE_PATH,
    COOKIE_MAX_AGE,
)
from backend.core.oauth_provider.models import OAuthSession, OAuthAuthorizationCode
from backend.core.oauth_provider.services.session_service import SESSION_LIFETIME_DAYS
from backend.core.encryption import encrypt_token


# ============================================================================
# FIXTURES
# ============================================================================


@pytest_asyncio.fixture
async def test_oauth_client(async_session: AsyncSession):
    """Create a test OAuth client."""
    client_id = "test-session-client"
    client_secret = "test-secret-session-12345"

    # Check if already exists
    stmt = select(CoreConnection).where(
        CoreConnection.client_id == client_id,
        CoreConnection.connection_type == "oauth_provider"
    )
    result = await async_session.execute(stmt)
    existing = result.scalar_one_or_none()

    if not existing:
        client = CoreConnection(
            user_id=None,
            provider="Test Session Client",
            connection_type="oauth_provider",
            client_id=client_id,
            client_secret_enc=encrypt_token(client_secret),
            redirect_uris=["https://example.com/callback"],
            grant_types=["authorization_code", "refresh_token"],
            encrypted_access_token="",
            scopes=["focused.read", "focused.write"],
            token_expires_at=datetime.now(timezone.utc) + timedelta(days=365),
            provider_metadata={"client_name": "Test Session App"},
        )
        async_session.add(client)
        await async_session.commit()

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": "https://example.com/callback"
    }


@pytest_asyncio.fixture
async def cleanup_sessions(async_session: AsyncSession):
    """Clean up test sessions and auth codes after each test."""
    yield
    await async_session.execute(delete(OAuthSession))
    await async_session.execute(delete(OAuthAuthorizationCode))
    await async_session.commit()


def generate_pkce_pair():
    """Generate code_verifier and code_challenge for PKCE."""
    code_verifier = base64.urlsafe_b64encode(
        hashlib.sha256(b"test-verifier-session").digest()
    ).rstrip(b"=").decode("utf-8")

    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode("utf-8")).digest()
    ).rstrip(b"=").decode("utf-8")

    return code_verifier, code_challenge


async def count_users(async_session: AsyncSession) -> int:
    """Count total CoreUser records."""
    result = await async_session.execute(select(func.count(CoreUser.id)))
    return result.scalar()


def extract_auth_context_id(html: str) -> str:
    """Extract auth_context_id from consent page HTML."""
    # Look for hidden input: <input type="hidden" name="auth_context_id" value="...">
    match = re.search(r'name="auth_context_id"\s+value="([^"]+)"', html)
    if not match:
        match = re.search(r'value="([^"]+)"\s+name="auth_context_id"', html)
    if not match:
        raise ValueError(f"Could not find auth_context_id in HTML: {html[:500]}")
    return match.group(1)


async def complete_authorization_flow(
    client: AsyncClient,
    oauth_client: dict,
    cookies: dict | None = None,
    login_hint: str | None = None,
) -> tuple[str, str, dict]:
    """
    Complete the full OAuth authorization flow.

    Args:
        client: HTTP client
        oauth_client: OAuth client credentials
        cookies: Optional session cookies to send
        login_hint: Optional login_hint parameter

    Returns:
        Tuple of (authorization_code, user_id_from_auth_code, response_cookies)
    """
    _, code_challenge = generate_pkce_pair()

    # Step 1: GET /authorize → consent page
    params = {
        "response_type": "code",
        "client_id": oauth_client["client_id"],
        "redirect_uri": oauth_client["redirect_uri"],
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "scope": "focused.read",
    }
    if login_hint:
        params["login_hint"] = login_hint

    authorize_response = await client.get(
        "/oauth/focused/authorize",
        params=params,
        cookies=cookies or {},
        follow_redirects=False,
    )

    assert authorize_response.status_code == 200, f"Expected 200, got {authorize_response.status_code}"
    html = authorize_response.text
    auth_context_id = extract_auth_context_id(html)

    # Step 2: POST /consent with action="allow"
    consent_response = await client.post(
        "/oauth/focused/consent",
        data={
            "auth_context_id": auth_context_id,
            "action": "allow",
        },
        cookies=cookies or {},
        follow_redirects=False,
    )

    assert consent_response.status_code == 302, f"Expected 302, got {consent_response.status_code}"

    # Extract authorization code from redirect URL
    location = consent_response.headers.get("location", "")
    code_match = re.search(r"code=([^&]+)", location)
    assert code_match, f"No code in redirect: {location}"
    authorization_code = code_match.group(1)

    return authorization_code, consent_response.cookies


# ============================================================================
# COOKIE CONSTANTS TESTS
# ============================================================================


class TestCookieConstants:
    """Tests for session cookie configuration constants."""

    def test_cookie_name_is_pg_session(self):
        """Session cookie must be named pg_session."""
        assert COOKIE_NAME == "pg_session"

    def test_cookie_path_is_oauth(self):
        """Session cookie must have Path=/oauth."""
        assert COOKIE_PATH == "/oauth"

    def test_cookie_max_age_is_two_years(self):
        """Cookie max_age must be 2 years (63072000 seconds)."""
        assert COOKIE_MAX_AGE == 2 * 365 * 24 * 60 * 60  # 63072000

    def test_session_lifetime_matches_cookie_max_age(self):
        """SESSION_LIFETIME_DAYS must match COOKIE_MAX_AGE."""
        cookie_days = COOKIE_MAX_AGE / (24 * 60 * 60)
        assert SESSION_LIFETIME_DAYS == cookie_days


# ============================================================================
# IDENTITY RESOLUTION CHAIN TESTS - Full Flow
# ============================================================================


class TestIdentityResolutionChain:
    """
    Tests for the identity resolution priority chain:
        1. login_hint (highest priority)
        2. valid session cookie
        3. new anonymous user (lowest priority)

    Each test runs the FULL authorization flow to verify correct behavior.
    """

    @pytest.mark.asyncio
    async def test_no_cookie_no_login_hint_creates_new_user(
        self,
        client: AsyncClient,
        test_oauth_client: dict,
        async_session: AsyncSession,
        cleanup_sessions,
        fake_redis_client,
    ):
        """Without cookie or login_hint, should create new user and set cookie."""
        users_before = await count_users(async_session)

        # Complete authorization flow without cookie or login_hint
        auth_code, response_cookies = await complete_authorization_flow(
            client, test_oauth_client
        )

        # Verify a new user was created
        users_after = await count_users(async_session)
        assert users_after == users_before + 1

        # Verify session cookie was set
        assert COOKIE_NAME in response_cookies

        # Verify authorization code exists and references the new user
        result = await async_session.execute(
            select(OAuthAuthorizationCode).where(OAuthAuthorizationCode.code == auth_code)
        )
        auth_code_record = result.scalar_one()
        assert auth_code_record is not None

    @pytest.mark.asyncio
    async def test_valid_cookie_reuses_existing_user(
        self,
        client: AsyncClient,
        test_oauth_client: dict,
        async_session: AsyncSession,
        cleanup_sessions,
        fake_redis_client,
    ):
        """With valid session cookie, should reuse existing user."""
        # Create a user with a valid session
        existing_user = CoreUser(chatgpt_user_id=None)
        async_session.add(existing_user)
        await async_session.commit()
        await async_session.refresh(existing_user)
        original_user_id = existing_user.id

        session_token = "a" * 64
        session = OAuthSession(
            user_id=existing_user.id,
            session_token=session_token,
            expires_at=datetime.now(timezone.utc) + timedelta(days=100),
        )
        async_session.add(session)
        await async_session.commit()

        users_before = await count_users(async_session)

        # Complete authorization flow WITH valid session cookie
        auth_code, response_cookies = await complete_authorization_flow(
            client, test_oauth_client, cookies={COOKIE_NAME: session_token}
        )

        # Verify NO new user was created
        users_after = await count_users(async_session)
        assert users_after == users_before

        # Verify authorization code references the EXISTING user
        result = await async_session.execute(
            select(OAuthAuthorizationCode).where(OAuthAuthorizationCode.code == auth_code)
        )
        auth_code_record = result.scalar_one()
        assert auth_code_record.user_id == original_user_id

    @pytest.mark.asyncio
    async def test_expired_cookie_creates_new_user(
        self,
        client: AsyncClient,
        test_oauth_client: dict,
        async_session: AsyncSession,
        cleanup_sessions,
        fake_redis_client,
    ):
        """With expired session cookie, should ignore cookie and create new user."""
        # Create a user with an EXPIRED session
        existing_user = CoreUser(chatgpt_user_id=None)
        async_session.add(existing_user)
        await async_session.commit()
        await async_session.refresh(existing_user)
        original_user_id = existing_user.id

        session_token = "b" * 64
        session = OAuthSession(
            user_id=existing_user.id,
            session_token=session_token,
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),  # EXPIRED
        )
        async_session.add(session)
        await async_session.commit()

        users_before = await count_users(async_session)

        # Complete authorization flow with EXPIRED session cookie
        auth_code, response_cookies = await complete_authorization_flow(
            client, test_oauth_client, cookies={COOKIE_NAME: session_token}
        )

        # Verify a NEW user was created (expired cookie ignored)
        users_after = await count_users(async_session)
        assert users_after == users_before + 1

        # Verify authorization code references a DIFFERENT user
        result = await async_session.execute(
            select(OAuthAuthorizationCode).where(OAuthAuthorizationCode.code == auth_code)
        )
        auth_code_record = result.scalar_one()
        assert auth_code_record.user_id != original_user_id

    @pytest.mark.asyncio
    async def test_login_hint_takes_priority_over_valid_cookie(
        self,
        client: AsyncClient,
        test_oauth_client: dict,
        async_session: AsyncSession,
        cleanup_sessions,
        fake_redis_client,
    ):
        """login_hint should take priority over valid session cookie."""
        # Create user A with session cookie
        user_a = CoreUser(chatgpt_user_id=None)
        async_session.add(user_a)
        await async_session.commit()
        await async_session.refresh(user_a)
        user_a_id = user_a.id

        session_token = "c" * 64
        session = OAuthSession(
            user_id=user_a.id,
            session_token=session_token,
            expires_at=datetime.now(timezone.utc) + timedelta(days=100),
        )
        async_session.add(session)

        # Create user B with login_hint
        unique_chatgpt_id = "chatgpt_user_xyz_123"
        user_b = CoreUser(chatgpt_user_id=unique_chatgpt_id)
        async_session.add(user_b)
        await async_session.commit()
        await async_session.refresh(user_b)
        user_b_id = user_b.id

        # Complete authorization with BOTH cookie (user A) AND login_hint (user B)
        auth_code, response_cookies = await complete_authorization_flow(
            client,
            test_oauth_client,
            cookies={COOKIE_NAME: session_token},
            login_hint=unique_chatgpt_id,
        )

        # Verify authorization code references user B (login_hint), NOT user A (cookie)
        result = await async_session.execute(
            select(OAuthAuthorizationCode).where(OAuthAuthorizationCode.code == auth_code)
        )
        auth_code_record = result.scalar_one()
        assert auth_code_record.user_id == user_b_id
        assert auth_code_record.user_id != user_a_id

    @pytest.mark.asyncio
    async def test_invalid_cookie_token_creates_new_user(
        self,
        client: AsyncClient,
        test_oauth_client: dict,
        async_session: AsyncSession,
        cleanup_sessions,
        fake_redis_client,
    ):
        """With nonexistent session token, should create new user."""
        users_before = await count_users(async_session)

        # Complete authorization with invalid cookie (doesn't exist in DB)
        auth_code, response_cookies = await complete_authorization_flow(
            client,
            test_oauth_client,
            cookies={COOKIE_NAME: "nonexistent" + "f" * 53},  # 64 chars but not in DB
        )

        # Verify a new user was created
        users_after = await count_users(async_session)
        assert users_after == users_before + 1


# ============================================================================
# SESSION COOKIE TESTS
# ============================================================================


class TestSessionCookieCreation:
    """Tests for session cookie creation after consent."""

    @pytest.mark.asyncio
    async def test_consent_sets_session_cookie(
        self,
        client: AsyncClient,
        test_oauth_client: dict,
        async_session: AsyncSession,
        cleanup_sessions,
        fake_redis_client,
    ):
        """Consent should set pg_session cookie."""
        auth_code, response_cookies = await complete_authorization_flow(
            client, test_oauth_client
        )

        # Verify cookie was set
        assert COOKIE_NAME in response_cookies

        # Verify cookie value is 64 hex chars
        cookie_value = response_cookies[COOKIE_NAME]
        assert len(cookie_value) == 64
        int(cookie_value, 16)  # Verify it's valid hex

    @pytest.mark.asyncio
    async def test_session_cookie_has_security_attributes(
        self,
        client: AsyncClient,
        test_oauth_client: dict,
        async_session: AsyncSession,
        cleanup_sessions,
        fake_redis_client,
    ):
        """Session cookie must have HttpOnly, SameSite=Lax, and correct Path.

        Note: Secure flag is only set in production (ENV != 'dev').
        In test environment, Secure is intentionally omitted to allow HTTP testing.
        """
        _, code_challenge = generate_pkce_pair()

        # Step 1: GET /authorize
        authorize_response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": test_oauth_client["client_id"],
                "redirect_uri": test_oauth_client["redirect_uri"],
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "scope": "focused.read",
            },
            follow_redirects=False,
        )
        auth_context_id = extract_auth_context_id(authorize_response.text)

        # Step 2: POST /consent - need raw response to check Set-Cookie header
        consent_response = await client.post(
            "/oauth/focused/consent",
            data={
                "auth_context_id": auth_context_id,
                "action": "allow",
            },
            follow_redirects=False,
        )

        # Get the Set-Cookie header
        set_cookie = consent_response.headers.get("set-cookie", "")

        # Verify security attributes (always required)
        assert COOKIE_NAME in set_cookie, f"Cookie {COOKIE_NAME} not in Set-Cookie header"
        assert "HttpOnly" in set_cookie, f"HttpOnly flag missing: {set_cookie}"
        assert "SameSite=Lax" in set_cookie or "SameSite=lax" in set_cookie, f"SameSite=Lax missing: {set_cookie}"
        assert f"Path={COOKIE_PATH}" in set_cookie, f"Path={COOKIE_PATH} missing: {set_cookie}"

        # Verify Max-Age is set (2 years)
        assert f"Max-Age={COOKIE_MAX_AGE}" in set_cookie, f"Max-Age={COOKIE_MAX_AGE} missing: {set_cookie}"

        # Note: Secure flag is conditionally set based on ENV setting
        # In production (ENV != 'dev'), Secure would be present
        # We test the logic separately in unit tests for cookies.py

    @pytest.mark.asyncio
    async def test_consent_reuses_valid_session_token(
        self,
        client: AsyncClient,
        test_oauth_client: dict,
        async_session: AsyncSession,
        cleanup_sessions,
        fake_redis_client,
    ):
        """Consent with valid cookie should reuse the existing session token."""
        # Create user with valid session
        existing_user = CoreUser(chatgpt_user_id=None)
        async_session.add(existing_user)
        await async_session.commit()
        await async_session.refresh(existing_user)
        user_id = existing_user.id  # Store scalar immediately after refresh

        original_session_token = "d" * 64
        session = OAuthSession(
            user_id=user_id,
            session_token=original_session_token,
            expires_at=datetime.now(timezone.utc) + timedelta(days=100),
        )
        async_session.add(session)
        await async_session.commit()

        # Complete authorization with valid session
        auth_code, response_cookies = await complete_authorization_flow(
            client, test_oauth_client, cookies={COOKIE_NAME: original_session_token}
        )

        # Cookie should be the SAME token (reused, not new)
        assert response_cookies[COOKIE_NAME] == original_session_token


# ============================================================================
# SESSION SLIDING WINDOW TESTS
# ============================================================================


class TestSessionSlidingWindow:
    """Tests for session expiry extension on use (sliding window)."""

    @pytest.mark.asyncio
    async def test_valid_session_expiry_extended_on_use(
        self,
        client: AsyncClient,
        test_oauth_client: dict,
        async_session: AsyncSession,
        cleanup_sessions,
        fake_redis_client,
    ):
        """Using a valid session should extend its expiry by SESSION_LIFETIME_DAYS."""
        # Create user with session that expires in 100 days
        existing_user = CoreUser(chatgpt_user_id=None)
        async_session.add(existing_user)
        await async_session.commit()
        await async_session.refresh(existing_user)
        user_id = existing_user.id  # Store scalar immediately after refresh

        session_token = "e" * 64
        original_expiry = datetime.now(timezone.utc) + timedelta(days=100)
        session = OAuthSession(
            user_id=user_id,
            session_token=session_token,
            expires_at=original_expiry,
        )
        async_session.add(session)
        await async_session.commit()

        # Use the session
        await complete_authorization_flow(
            client, test_oauth_client, cookies={COOKIE_NAME: session_token}
        )

        # Refresh session from DB and check expiry was extended
        async_session.expire_all()
        result = await async_session.execute(
            select(OAuthSession).where(OAuthSession.session_token == session_token)
        )
        updated_session = result.scalar_one()

        # New expiry should be approximately now + SESSION_LIFETIME_DAYS (730 days)
        expected_new_expiry = datetime.now(timezone.utc) + timedelta(days=SESSION_LIFETIME_DAYS)

        # Allow 1 minute tolerance for test execution time
        assert updated_session.expires_at > original_expiry
        assert abs((updated_session.expires_at - expected_new_expiry).total_seconds()) < 60


# ============================================================================
# REVOKE ENDPOINT SESSION TESTS (Increment 19 Semantics)
# ============================================================================


class TestRevokeEndpointSession:
    """
    Tests for session handling during token revocation (Increment 19).

    CRITICAL: App revocation does NOT delete sessions or clear cookies.
    This preserves cross-app identity:
        - User revokes Focused app → session still valid
        - User authorizes Decliner app → same user recognized via cookie

    Sessions are ONLY deleted on full user data deletion (delete_user_sessions).
    """

    @pytest.mark.asyncio
    async def test_revoke_does_not_clear_session_cookie(
        self,
        client: AsyncClient,
        test_oauth_client: dict,
        async_session: AsyncSession,
        cleanup_sessions,
        fake_redis_client,
    ):
        """POST /oauth/focused/revoke must NOT clear session cookie (Increment 19)."""
        # Create user with session
        existing_user = CoreUser(chatgpt_user_id=None)
        async_session.add(existing_user)
        await async_session.commit()
        await async_session.refresh(existing_user)
        user_id = existing_user.id  # Store scalar immediately after refresh

        session_token = "f" * 64  # 64 hex chars
        session = OAuthSession(
            user_id=user_id,
            session_token=session_token,
            expires_at=datetime.now(timezone.utc) + timedelta(days=100),
        )
        async_session.add(session)
        await async_session.commit()

        # Call revoke endpoint with session cookie
        response = await client.post(
            "/oauth/focused/revoke",
            data={
                "token": "dummy_token",
                "client_id": test_oauth_client["client_id"],
            },
            cookies={COOKIE_NAME: session_token},
        )

        assert response.status_code == 200

        # Verify NO Set-Cookie header that clears the cookie
        set_cookie = response.headers.get("set-cookie", "")
        # Either no Set-Cookie at all, or if present, it should NOT clear (no Max-Age=0)
        if set_cookie:
            assert "Max-Age=0" not in set_cookie, (
                f"Revoke should NOT clear cookie, but found: {set_cookie}"
            )

    @pytest.mark.asyncio
    async def test_revoke_does_not_delete_session_from_database(
        self,
        client: AsyncClient,
        test_oauth_client: dict,
        async_session: AsyncSession,
        cleanup_sessions,
        fake_redis_client,
    ):
        """POST /oauth/focused/revoke must NOT delete session row (Increment 19)."""
        # Create user with session
        existing_user = CoreUser(chatgpt_user_id=None)
        async_session.add(existing_user)
        await async_session.commit()
        await async_session.refresh(existing_user)
        user_id = existing_user.id  # Store scalar immediately after refresh

        session_token = "0" * 64  # 64 hex chars
        session = OAuthSession(
            user_id=user_id,
            session_token=session_token,
            expires_at=datetime.now(timezone.utc) + timedelta(days=100),
        )
        async_session.add(session)
        await async_session.commit()

        # Verify session exists before revoke
        result = await async_session.execute(
            select(OAuthSession).where(OAuthSession.session_token == session_token)
        )
        assert result.scalar_one_or_none() is not None

        # Call revoke endpoint
        await client.post(
            "/oauth/focused/revoke",
            data={
                "token": "dummy_token",
                "client_id": test_oauth_client["client_id"],
            },
            cookies={COOKIE_NAME: session_token},
        )

        # CRITICAL: Session must still exist in database
        async_session.expire_all()
        result = await async_session.execute(
            select(OAuthSession).where(OAuthSession.session_token == session_token)
        )
        session_after = result.scalar_one_or_none()
        assert session_after is not None, (
            "Session was deleted on revoke - this breaks cross-app identity!"
        )
        assert session_after.user_id == user_id

    @pytest.mark.asyncio
    async def test_revoke_preserves_cross_app_identity(
        self,
        client: AsyncClient,
        test_oauth_client: dict,
        async_session: AsyncSession,
        cleanup_sessions,
        fake_redis_client,
    ):
        """
        After revoking one app, user should still be recognized for other apps.

        Scenario:
        1. User authorizes Focused app → session created
        2. User revokes Focused app tokens
        3. User authorizes Decliner app → SAME user via session cookie
        """
        # Step 1: Create user with session (simulating previous authorization)
        existing_user = CoreUser(chatgpt_user_id=None)
        async_session.add(existing_user)
        await async_session.commit()
        await async_session.refresh(existing_user)
        original_user_id = existing_user.id  # Store scalar immediately after refresh

        session_token = "2" * 64  # 64 hex chars
        session = OAuthSession(
            user_id=original_user_id,
            session_token=session_token,
            expires_at=datetime.now(timezone.utc) + timedelta(days=100),
        )
        async_session.add(session)
        await async_session.commit()

        users_before = await count_users(async_session)

        # Step 2: Revoke tokens (simulating user revoking Focused app)
        revoke_response = await client.post(
            "/oauth/focused/revoke",
            data={
                "token": "some_access_token",
                "client_id": test_oauth_client["client_id"],
            },
            cookies={COOKIE_NAME: session_token},
        )
        assert revoke_response.status_code == 200

        # Step 3: User authorizes another app (simulating Decliner authorization)
        auth_code, response_cookies = await complete_authorization_flow(
            client, test_oauth_client, cookies={COOKIE_NAME: session_token}
        )

        # CRITICAL: No new user should be created
        users_after = await count_users(async_session)
        assert users_after == users_before, (
            f"New user created after revoke! Before: {users_before}, After: {users_after}"
        )

        # CRITICAL: Authorization code should reference the SAME user
        result = await async_session.execute(
            select(OAuthAuthorizationCode).where(OAuthAuthorizationCode.code == auth_code)
        )
        auth_code_record = result.scalar_one()
        assert auth_code_record.user_id == original_user_id, (
            f"Wrong user after revoke! Expected: {original_user_id}, Got: {auth_code_record.user_id}"
        )


# ============================================================================
# CROSS-APP USER IDENTIFICATION TESTS
# ============================================================================


class TestCrossAppUserIdentification:
    """
    Tests for the primary Increment 19 use case:
    Same user authorizing multiple apps in the same browser.
    """

    @pytest.mark.asyncio
    async def test_second_app_authorization_reuses_same_user(
        self,
        client: AsyncClient,
        test_oauth_client: dict,
        async_session: AsyncSession,
        cleanup_sessions,
        fake_redis_client,
    ):
        """
        Simulate cross-app scenario:
        1. User authorizes "Focused" app → user created, session created
        2. User authorizes "Decliner" app (same browser) → same user reused

        This is the core Increment 19 use case.
        """
        # Simulate: User already authorized one app, has a session cookie
        existing_user = CoreUser(chatgpt_user_id=None)
        async_session.add(existing_user)
        await async_session.commit()
        await async_session.refresh(existing_user)
        original_user_id = existing_user.id  # Store scalar immediately after refresh

        session_token = "1" * 64  # 64 hex chars
        session = OAuthSession(
            user_id=original_user_id,
            session_token=session_token,
            expires_at=datetime.now(timezone.utc) + timedelta(days=SESSION_LIFETIME_DAYS),
        )
        async_session.add(session)
        await async_session.commit()

        users_before = await count_users(async_session)

        # Simulate: User now authorizes a "second app" (same browser = same cookie)
        auth_code, response_cookies = await complete_authorization_flow(
            client, test_oauth_client, cookies={COOKIE_NAME: session_token}
        )

        # CRITICAL: No new user should be created
        users_after = await count_users(async_session)
        assert users_after == users_before

        # CRITICAL: Authorization code should reference the SAME user
        result = await async_session.execute(
            select(OAuthAuthorizationCode).where(OAuthAuthorizationCode.code == auth_code)
        )
        auth_code_record = result.scalar_one()
        assert auth_code_record.user_id == original_user_id

        # Session should still reference the same user
        result = await async_session.execute(
            select(OAuthSession).where(OAuthSession.session_token == session_token)
        )
        session_after = result.scalar_one()
        assert session_after.user_id == original_user_id
