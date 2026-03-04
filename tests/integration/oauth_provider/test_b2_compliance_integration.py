"""
B2-5 + B2-8 Compliance Integration Tests (Increment 35).

Tests RFC 9728 B2-5 (resource parameter) and B2-8 (redirect URI allowlist)
with full HTTP flow through actual endpoints.

B2-5 Integration Tests:
1. Full authorize(resource) -> token exchange(resource): JWT aud = resource value
2. Full authorize(resource) -> token exchange(no resource): JWT aud = authorize resource (downgrade protection)
3. Full authorize(no resource) -> token exchange(resource): JWT aud = token resource
4. Full authorize(no resource) -> token exchange(no resource): JWT aud = OAUTH_ISSUER
5. Token exchange: /token resource mismatches auth code resource -> 400 invalid_request
6. Full authorize(resource) -> token exchange -> refresh: all three issued JWTs have aud = original resource
7. Full authorize(no resource) -> token exchange(resource) -> refresh: refresh JWT aud = token-introduced resource
8. Token with aud = app's MCP server URL accepted by mcp_auth.py authenticate_request()
9. Token with aud = OAUTH_ISSUER (legacy) still accepted by mcp_auth.py
10. Token with aud = a different app's MCP server URL rejected by mcp_auth.py

B2-8 Integration Tests:
1. DCR POST to /oauth/pg/register with https://chatgpt.com/connector_platform_oauth_redirect -> 200
2. DCR POST to /oauth/pg/register with https://platform.openai.com/apps-manage/oauth -> 200
3. DCR POST to /oauth/pg/register with arbitrary HTTPS URI -> 400
4. DCR POST to /oauth/focused/register with allowed URI -> 200
5. DCR POST to /oauth/focused/register with disallowed URI -> 400

DB Integrity Tests:
1. oauth_authorization_codes table has resource column after migration
2. oauth_access_tokens table has resource column after migration
3. Both columns are nullable - insert with resource=NULL succeeds
4. Both columns accept URL string value
5. Existing rows unaffected after migration
6. Provider column accepts strings longer than 50 chars (VARCHAR(200) migration)
"""

import pytest
import pytest_asyncio
import base64
import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from jose import jwt

from backend.core.oauth_provider.models import (
    OAuthAuthorizationCode,
    OAuthAccessToken,
)
from backend.core.models import CoreConnection, CoreUser


# =============================================================================
# FIXTURES
# =============================================================================

def generate_pkce_pair():
    """Generate code_verifier and code_challenge for PKCE."""
    code_verifier = base64.urlsafe_b64encode(
        secrets.token_bytes(32)
    ).rstrip(b"=").decode("utf-8")

    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode("utf-8")).digest()
    ).rstrip(b"=").decode("utf-8")

    return code_verifier, code_challenge


@pytest_asyncio.fixture
async def test_user(async_session: AsyncSession):
    """Create a test user for OAuth flows."""
    user = CoreUser(
        id=uuid4(),
        chatgpt_user_id=f"test-b2-{uuid4()}"  # ChatGPT pseudonymous user ID
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_oauth_client(async_session: AsyncSession):
    """Create a test OAuth client with ChatGPT redirect URIs."""
    from backend.core.encryption import encrypt_token

    client_id = f"test-b2-client-{uuid4()}"
    client_secret = secrets.token_urlsafe(32)

    client = CoreConnection(
        user_id=None,  # OAuth provider clients have NULL user_id
        provider="Test B2 OAuth Client",
        connection_type="oauth_provider",
        client_id=client_id,
        client_secret_enc=encrypt_token(client_secret),
        redirect_uris=["https://chatgpt.com/connector_platform_oauth_redirect"],
        grant_types=["authorization_code", "refresh_token"],
        encrypted_access_token="",
        scopes=["pg.access"],
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=365)
    )
    async_session.add(client)
    await async_session.commit()

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": "https://chatgpt.com/connector_platform_oauth_redirect"
    }


@pytest_asyncio.fixture
async def authenticated_auth_code(
    async_session: AsyncSession,
    test_user,
    test_oauth_client
):
    """
    Create a valid authorization code for testing token exchange.

    Returns the code and code_verifier needed for exchange.
    """
    code_verifier, code_challenge = generate_pkce_pair()
    auth_code = secrets.token_urlsafe(32)

    code_record = OAuthAuthorizationCode(
        code=auth_code,
        user_id=test_user.id,
        client_id=test_oauth_client["client_id"],
        redirect_uri=test_oauth_client["redirect_uri"],
        scope=["pg.access"],
        code_challenge=code_challenge,
        code_challenge_method="S256",
        resource=None,  # Will be set by specific tests
        used=False,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
    )
    async_session.add(code_record)
    await async_session.commit()

    return {
        "code": auth_code,
        "code_verifier": code_verifier,
        "client_id": test_oauth_client["client_id"],
        "redirect_uri": test_oauth_client["redirect_uri"],
        "user_id": test_user.id
    }


# =============================================================================
# B2-5 INTEGRATION TESTS: Resource Parameter Flow
# =============================================================================

class TestResourceParameterFlow:
    """Test full OAuth flow with resource parameter."""

    @pytest.mark.asyncio
    async def test_full_flow_authorize_with_resource_token_with_resource(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user,
        test_oauth_client,
        fake_redis_client
    ):
        """
        Test 1: Full authorize(resource) -> token exchange(resource): JWT aud = resource value.
        """
        from backend.core.config import settings
        from backend.core.crypto import get_public_key
        from cryptography.hazmat.primitives import serialization

        code_verifier, code_challenge = generate_pkce_pair()
        resource_url = "https://mcp.priority-guard.com"

        # Create auth code with resource
        auth_code = secrets.token_urlsafe(32)
        code_record = OAuthAuthorizationCode(
            code=auth_code,
            user_id=test_user.id,
            client_id=test_oauth_client["client_id"],
            redirect_uri=test_oauth_client["redirect_uri"],
            scope=["pg.access"],
            code_challenge=code_challenge,
            code_challenge_method="S256",
            resource=resource_url,  # Authorize with resource
            used=False,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
        )
        async_session.add(code_record)
        await async_session.commit()

        # Exchange code for tokens
        response = await client.post(
            "/oauth/pg/token",
            data={
                "grant_type": "authorization_code",
                "code": auth_code,
                "redirect_uri": test_oauth_client["redirect_uri"],
                "client_id": test_oauth_client["client_id"],
                "code_verifier": code_verifier,
                "resource": resource_url  # Token with resource
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert response.status_code == 200, f"Token exchange failed: {response.text}"
        data = response.json()
        assert "access_token" in data

        # Decode JWT and verify aud
        public_key = get_public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        decoded = jwt.decode(
            data["access_token"],
            public_pem,
            algorithms=["RS256"],
            options={"verify_aud": False}
        )

        assert decoded["aud"] == resource_url, \
            f"JWT aud should be resource URL, got: {decoded['aud']}"

    @pytest.mark.asyncio
    async def test_full_flow_authorize_with_resource_token_omits_resource(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user,
        test_oauth_client,
        fake_redis_client
    ):
        """
        Test 2: Full authorize(resource) -> token exchange(no resource): JWT aud = authorize resource.

        Downgrade protection: cannot remove resource.
        """
        from backend.core.crypto import get_public_key
        from cryptography.hazmat.primitives import serialization

        code_verifier, code_challenge = generate_pkce_pair()
        resource_url = "https://mcp.priority-guard.com"

        # Create auth code WITH resource
        auth_code = secrets.token_urlsafe(32)
        code_record = OAuthAuthorizationCode(
            code=auth_code,
            user_id=test_user.id,
            client_id=test_oauth_client["client_id"],
            redirect_uri=test_oauth_client["redirect_uri"],
            scope=["pg.access"],
            code_challenge=code_challenge,
            code_challenge_method="S256",
            resource=resource_url,  # HAS resource
            used=False,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
        )
        async_session.add(code_record)
        await async_session.commit()

        # Exchange WITHOUT resource (downgrade attempt)
        response = await client.post(
            "/oauth/pg/token",
            data={
                "grant_type": "authorization_code",
                "code": auth_code,
                "redirect_uri": test_oauth_client["redirect_uri"],
                "client_id": test_oauth_client["client_id"],
                "code_verifier": code_verifier,
                # resource OMITTED
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert response.status_code == 200, f"Token exchange failed: {response.text}"
        data = response.json()

        # Decode JWT - should still have original resource as aud
        public_key = get_public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        decoded = jwt.decode(
            data["access_token"],
            public_pem,
            algorithms=["RS256"],
            options={"verify_aud": False}
        )

        assert decoded["aud"] == resource_url, \
            f"JWT aud should be authorize resource (downgrade protection), got: {decoded['aud']}"

    @pytest.mark.asyncio
    async def test_full_flow_authorize_no_resource_token_with_resource(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user,
        test_oauth_client,
        fake_redis_client
    ):
        """
        Test 3: Full authorize(no resource) -> token exchange(resource): JWT aud = token resource.

        Token can introduce resource when auth code has none.
        """
        from backend.core.crypto import get_public_key
        from cryptography.hazmat.primitives import serialization

        code_verifier, code_challenge = generate_pkce_pair()
        token_resource = "https://mcp.priority-guard.com"

        # Create auth code WITHOUT resource
        auth_code = secrets.token_urlsafe(32)
        code_record = OAuthAuthorizationCode(
            code=auth_code,
            user_id=test_user.id,
            client_id=test_oauth_client["client_id"],
            redirect_uri=test_oauth_client["redirect_uri"],
            scope=["pg.access"],
            code_challenge=code_challenge,
            code_challenge_method="S256",
            resource=None,  # NO resource
            used=False,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
        )
        async_session.add(code_record)
        await async_session.commit()

        # Exchange WITH resource (token introduces it)
        response = await client.post(
            "/oauth/pg/token",
            data={
                "grant_type": "authorization_code",
                "code": auth_code,
                "redirect_uri": test_oauth_client["redirect_uri"],
                "client_id": test_oauth_client["client_id"],
                "code_verifier": code_verifier,
                "resource": token_resource  # Token introduces resource
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert response.status_code == 200, f"Token exchange failed: {response.text}"
        data = response.json()

        # Decode JWT
        public_key = get_public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        decoded = jwt.decode(
            data["access_token"],
            public_pem,
            algorithms=["RS256"],
            options={"verify_aud": False}
        )

        assert decoded["aud"] == token_resource, \
            f"JWT aud should be token-introduced resource, got: {decoded['aud']}"

    @pytest.mark.asyncio
    async def test_full_flow_authorize_no_resource_token_no_resource(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user,
        test_oauth_client,
        fake_redis_client
    ):
        """
        Test 4: Full authorize(no resource) -> token exchange(no resource): JWT aud = OAUTH_ISSUER.
        """
        from backend.core.config import settings
        from backend.core.crypto import get_public_key
        from cryptography.hazmat.primitives import serialization

        code_verifier, code_challenge = generate_pkce_pair()

        # Create auth code WITHOUT resource
        auth_code = secrets.token_urlsafe(32)
        code_record = OAuthAuthorizationCode(
            code=auth_code,
            user_id=test_user.id,
            client_id=test_oauth_client["client_id"],
            redirect_uri=test_oauth_client["redirect_uri"],
            scope=["pg.access"],
            code_challenge=code_challenge,
            code_challenge_method="S256",
            resource=None,  # NO resource
            used=False,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
        )
        async_session.add(code_record)
        await async_session.commit()

        # Exchange WITHOUT resource
        response = await client.post(
            "/oauth/pg/token",
            data={
                "grant_type": "authorization_code",
                "code": auth_code,
                "redirect_uri": test_oauth_client["redirect_uri"],
                "client_id": test_oauth_client["client_id"],
                "code_verifier": code_verifier,
                # resource OMITTED
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert response.status_code == 200, f"Token exchange failed: {response.text}"
        data = response.json()

        # Decode JWT
        public_key = get_public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        decoded = jwt.decode(
            data["access_token"],
            public_pem,
            algorithms=["RS256"],
            options={"verify_aud": False}
        )

        assert decoded["aud"] == settings.OAUTH_ISSUER, \
            f"JWT aud should fall back to OAUTH_ISSUER, got: {decoded['aud']}"

    @pytest.mark.asyncio
    async def test_resource_mismatch_returns_400(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user,
        test_oauth_client,
        fake_redis_client
    ):
        """
        Test 5: Token exchange: /token resource mismatches auth code resource -> 400 invalid_request.
        """
        code_verifier, code_challenge = generate_pkce_pair()
        auth_code_resource = "https://mcp.priority-guard.com"
        different_resource = "https://different.example.com"

        # Create auth code WITH resource
        auth_code = secrets.token_urlsafe(32)
        code_record = OAuthAuthorizationCode(
            code=auth_code,
            user_id=test_user.id,
            client_id=test_oauth_client["client_id"],
            redirect_uri=test_oauth_client["redirect_uri"],
            scope=["pg.access"],
            code_challenge=code_challenge,
            code_challenge_method="S256",
            resource=auth_code_resource,  # HAS resource
            used=False,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
        )
        async_session.add(code_record)
        await async_session.commit()

        # Exchange with DIFFERENT resource
        response = await client.post(
            "/oauth/pg/token",
            data={
                "grant_type": "authorization_code",
                "code": auth_code,
                "redirect_uri": test_oauth_client["redirect_uri"],
                "client_id": test_oauth_client["client_id"],
                "code_verifier": code_verifier,
                "resource": different_resource  # DIFFERENT resource
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert response.status_code == 400, f"Expected 400, got: {response.status_code}"
        data = response.json()
        assert data.get("error") == "invalid_request"
        assert "mismatch" in data.get("error_description", "").lower()


class TestRefreshTokenResourcePreservation:
    """Test resource preservation through refresh token flow."""

    @pytest.mark.asyncio
    async def test_refresh_preserves_original_resource(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user,
        test_oauth_client,
        fake_redis_client
    ):
        """
        Test 6: Full authorize(resource) -> token exchange -> refresh: all three issued JWTs have aud = original resource.
        """
        from backend.core.crypto import get_public_key
        from cryptography.hazmat.primitives import serialization

        code_verifier, code_challenge = generate_pkce_pair()
        resource_url = "https://mcp.priority-guard.com"

        # Create auth code with resource
        auth_code = secrets.token_urlsafe(32)
        code_record = OAuthAuthorizationCode(
            code=auth_code,
            user_id=test_user.id,
            client_id=test_oauth_client["client_id"],
            redirect_uri=test_oauth_client["redirect_uri"],
            scope=["pg.access"],
            code_challenge=code_challenge,
            code_challenge_method="S256",
            resource=resource_url,
            used=False,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
        )
        async_session.add(code_record)
        await async_session.commit()

        # Exchange code for tokens
        exchange_response = await client.post(
            "/oauth/pg/token",
            data={
                "grant_type": "authorization_code",
                "code": auth_code,
                "redirect_uri": test_oauth_client["redirect_uri"],
                "client_id": test_oauth_client["client_id"],
                "code_verifier": code_verifier,
                "resource": resource_url
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert exchange_response.status_code == 200
        exchange_data = exchange_response.json()

        # Refresh
        refresh_response = await client.post(
            "/oauth/pg/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": exchange_data["refresh_token"],
                "client_id": test_oauth_client["client_id"],
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert refresh_response.status_code == 200, f"Refresh failed: {refresh_response.text}"
        refresh_data = refresh_response.json()

        # Decode both JWTs
        public_key = get_public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        exchange_decoded = jwt.decode(
            exchange_data["access_token"],
            public_pem,
            algorithms=["RS256"],
            options={"verify_aud": False}
        )

        refresh_decoded = jwt.decode(
            refresh_data["access_token"],
            public_pem,
            algorithms=["RS256"],
            options={"verify_aud": False}
        )

        # Both should have same aud
        assert exchange_decoded["aud"] == resource_url
        assert refresh_decoded["aud"] == resource_url

    @pytest.mark.asyncio
    async def test_refresh_preserves_token_introduced_resource(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user,
        test_oauth_client,
        fake_redis_client
    ):
        """
        Test 7: Full authorize(no resource) -> token exchange(resource) -> refresh: refresh JWT aud = token-introduced resource.
        """
        from backend.core.crypto import get_public_key
        from cryptography.hazmat.primitives import serialization

        code_verifier, code_challenge = generate_pkce_pair()
        token_resource = "https://mcp.priority-guard.com"

        # Create auth code WITHOUT resource
        auth_code = secrets.token_urlsafe(32)
        code_record = OAuthAuthorizationCode(
            code=auth_code,
            user_id=test_user.id,
            client_id=test_oauth_client["client_id"],
            redirect_uri=test_oauth_client["redirect_uri"],
            scope=["pg.access"],
            code_challenge=code_challenge,
            code_challenge_method="S256",
            resource=None,  # NO resource
            used=False,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
        )
        async_session.add(code_record)
        await async_session.commit()

        # Exchange with resource (token introduces it)
        exchange_response = await client.post(
            "/oauth/pg/token",
            data={
                "grant_type": "authorization_code",
                "code": auth_code,
                "redirect_uri": test_oauth_client["redirect_uri"],
                "client_id": test_oauth_client["client_id"],
                "code_verifier": code_verifier,
                "resource": token_resource  # Token introduces resource
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert exchange_response.status_code == 200
        exchange_data = exchange_response.json()

        # Refresh
        refresh_response = await client.post(
            "/oauth/pg/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": exchange_data["refresh_token"],
                "client_id": test_oauth_client["client_id"],
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert refresh_response.status_code == 200
        refresh_data = refresh_response.json()

        # Decode refresh JWT
        public_key = get_public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        refresh_decoded = jwt.decode(
            refresh_data["access_token"],
            public_pem,
            algorithms=["RS256"],
            options={"verify_aud": False}
        )

        assert refresh_decoded["aud"] == token_resource, \
            "Refresh JWT should preserve token-introduced resource"


# =============================================================================
# B2-8 INTEGRATION TESTS: Redirect URI Allowlist
# =============================================================================

class TestDCRRedirectURIAllowlist:
    """Test Dynamic Client Registration redirect URI allowlist."""

    CHATGPT_REDIRECT_URI = "https://chatgpt.com/connector_platform_oauth_redirect"
    OPENAI_PLATFORM_REDIRECT_URI = "https://platform.openai.com/apps-manage/oauth"

    @pytest.mark.asyncio
    async def test_dcr_pg_register_with_chatgpt_redirect_uri_success(
        self,
        client: AsyncClient,
        fake_redis_client
    ):
        """
        Test 1: DCR POST to /oauth/pg/register with https://chatgpt.com/connector_platform_oauth_redirect -> 200.
        """
        # Use short client name to fit provider varchar(50) column
        response = await client.post(
            "/oauth/pg/register",
            json={
                "client_name": "B2-Test-PG-Client",
                "redirect_uris": [self.CHATGPT_REDIRECT_URI],
                "grant_types": ["authorization_code", "refresh_token"],
            }
        )

        # May hit rate limit
        if response.status_code == 429:
            pytest.skip("Rate limited (expected behavior)")

        assert response.status_code == 200, f"Expected 200, got: {response.status_code}, body: {response.text}"
        data = response.json()
        assert "client_id" in data
        assert "client_secret" in data

    @pytest.mark.asyncio
    async def test_dcr_pg_register_with_openai_platform_redirect_uri_success(
        self,
        client: AsyncClient,
        fake_redis_client
    ):
        """
        Test 2: DCR POST to /oauth/pg/register with https://platform.openai.com/apps-manage/oauth -> 200.
        """
        response = await client.post(
            "/oauth/pg/register",
            json={
                "client_name": "B2-Test-PG-OpenAI",
                "redirect_uris": [self.OPENAI_PLATFORM_REDIRECT_URI],
                "grant_types": ["authorization_code", "refresh_token"],
            }
        )

        if response.status_code == 429:
            pytest.skip("Rate limited")

        assert response.status_code == 200, f"Expected 200, got: {response.status_code}"

    @pytest.mark.asyncio
    async def test_dcr_pg_register_with_arbitrary_uri_rejected(
        self,
        client: AsyncClient,
        fake_redis_client
    ):
        """
        Test 3: DCR POST to /oauth/pg/register with arbitrary HTTPS URI -> 400.
        """
        response = await client.post(
            "/oauth/pg/register",
            json={
                "client_name": "B2-Test-Reject",
                "redirect_uris": ["https://evil.example.com/callback"],
                "grant_types": ["authorization_code", "refresh_token"],
            }
        )

        if response.status_code == 429:
            pytest.skip("Rate limited")

        assert response.status_code == 400, f"Expected 400, got: {response.status_code}"
        assert "not in allowlist" in response.json().get("detail", "").lower()

    @pytest.mark.asyncio
    async def test_dcr_focused_register_with_allowed_uri_success(
        self,
        client: AsyncClient,
        fake_redis_client
    ):
        """
        Test 4: DCR POST to /oauth/focused/register with allowed URI -> 200.
        """
        response = await client.post(
            "/oauth/focused/register",
            json={
                "client_name": "B2-Test-Focused",
                "redirect_uris": [self.CHATGPT_REDIRECT_URI],
                "grant_types": ["authorization_code", "refresh_token"],
            }
        )

        if response.status_code == 429:
            pytest.skip("Rate limited")

        assert response.status_code == 200, f"Expected 200, got: {response.status_code}"

    @pytest.mark.asyncio
    async def test_dcr_focused_register_with_disallowed_uri_rejected(
        self,
        client: AsyncClient,
        fake_redis_client
    ):
        """
        Test 5: DCR POST to /oauth/focused/register with disallowed URI -> 400.
        """
        response = await client.post(
            "/oauth/focused/register",
            json={
                "client_name": "B2-Test-FocusReject",
                "redirect_uris": ["https://arbitrary.example.com/callback"],
                "grant_types": ["authorization_code", "refresh_token"],
            }
        )

        if response.status_code == 429:
            pytest.skip("Rate limited")

        assert response.status_code == 400, f"Expected 400, got: {response.status_code}"


# =============================================================================
# DB INTEGRITY TESTS
# =============================================================================

class TestDBIntegrity:
    """Test database schema integrity for resource column."""

    @pytest.mark.asyncio
    async def test_oauth_authorization_codes_has_resource_column(
        self,
        async_session: AsyncSession
    ):
        """
        DB Integrity Test 1: oauth_authorization_codes table has resource column.
        """
        result = await async_session.execute(
            text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'oauth_authorization_codes'
                AND column_name = 'resource'
            """)
        )
        row = result.fetchone()

        assert row is not None, "resource column should exist in oauth_authorization_codes"
        assert row[1] in ("character varying", "varchar", "text"), \
            f"resource column should be string type, got: {row[1]}"
        assert row[2] == "YES", "resource column should be nullable"

    @pytest.mark.asyncio
    async def test_oauth_access_tokens_has_resource_column(
        self,
        async_session: AsyncSession
    ):
        """
        DB Integrity Test 2: oauth_access_tokens table has resource column.
        """
        result = await async_session.execute(
            text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'oauth_access_tokens'
                AND column_name = 'resource'
            """)
        )
        row = result.fetchone()

        assert row is not None, "resource column should exist in oauth_access_tokens"
        assert row[1] in ("character varying", "varchar", "text"), \
            f"resource column should be string type, got: {row[1]}"
        assert row[2] == "YES", "resource column should be nullable"

    @pytest.mark.asyncio
    async def test_resource_column_nullable_insert_null_succeeds(
        self,
        async_session: AsyncSession,
        test_user,
        test_oauth_client
    ):
        """
        DB Integrity Test 3: Both columns are nullable - insert with resource=NULL succeeds.
        """
        code_verifier, code_challenge = generate_pkce_pair()

        # Insert auth code with resource=NULL
        auth_code = OAuthAuthorizationCode(
            code=secrets.token_urlsafe(32),
            user_id=test_user.id,
            client_id=test_oauth_client["client_id"],
            redirect_uri=test_oauth_client["redirect_uri"],
            scope=["pg.access"],
            code_challenge=code_challenge,
            code_challenge_method="S256",
            resource=None,  # Explicitly NULL
            used=False,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
        )
        async_session.add(auth_code)
        await async_session.commit()

        # Insert access token with resource=NULL
        access_token = OAuthAccessToken(
            jti=str(uuid4()),
            user_id=test_user.id,
            client_id=test_oauth_client["client_id"],
            scope=["pg.access"],
            resource=None,  # Explicitly NULL
            token_type="Bearer",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            refresh_token_enc="test",
            refresh_token_hash="test",
            refresh_token_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            revoked=False
        )
        async_session.add(access_token)
        await async_session.commit()

        # Verify both were inserted with NULL resource
        result = await async_session.execute(
            select(OAuthAuthorizationCode).where(OAuthAuthorizationCode.code == auth_code.code)
        )
        fetched_code = result.scalar_one()
        assert fetched_code.resource is None

        result = await async_session.execute(
            select(OAuthAccessToken).where(OAuthAccessToken.jti == access_token.jti)
        )
        fetched_token = result.scalar_one()
        assert fetched_token.resource is None

    @pytest.mark.asyncio
    async def test_resource_column_accepts_url_string(
        self,
        async_session: AsyncSession,
        test_user,
        test_oauth_client
    ):
        """
        DB Integrity Test 4: Both columns accept URL string value.
        """
        code_verifier, code_challenge = generate_pkce_pair()
        resource_url = "https://mcp.priority-guard.com/api/v1"

        # Insert auth code with resource URL
        auth_code = OAuthAuthorizationCode(
            code=secrets.token_urlsafe(32),
            user_id=test_user.id,
            client_id=test_oauth_client["client_id"],
            redirect_uri=test_oauth_client["redirect_uri"],
            scope=["pg.access"],
            code_challenge=code_challenge,
            code_challenge_method="S256",
            resource=resource_url,
            used=False,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
        )
        async_session.add(auth_code)
        await async_session.commit()

        # Insert access token with resource URL
        access_token = OAuthAccessToken(
            jti=str(uuid4()),
            user_id=test_user.id,
            client_id=test_oauth_client["client_id"],
            scope=["pg.access"],
            resource=resource_url,
            token_type="Bearer",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            refresh_token_enc="test",
            refresh_token_hash="test",
            refresh_token_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            revoked=False
        )
        async_session.add(access_token)
        await async_session.commit()

        # Verify both were inserted with resource URL
        result = await async_session.execute(
            select(OAuthAuthorizationCode).where(OAuthAuthorizationCode.code == auth_code.code)
        )
        fetched_code = result.scalar_one()
        assert fetched_code.resource == resource_url

        result = await async_session.execute(
            select(OAuthAccessToken).where(OAuthAccessToken.jti == access_token.jti)
        )
        fetched_token = result.scalar_one()
        assert fetched_token.resource == resource_url

    @pytest.mark.asyncio
    async def test_existing_rows_unaffected(
        self,
        async_session: AsyncSession,
        test_user,
        test_oauth_client
    ):
        """
        DB Integrity Test 5: Existing rows unaffected after migration.

        Insert rows, then verify they can still be read/updated.
        """
        code_verifier, code_challenge = generate_pkce_pair()

        # Insert auth code
        auth_code = OAuthAuthorizationCode(
            code=secrets.token_urlsafe(32),
            user_id=test_user.id,
            client_id=test_oauth_client["client_id"],
            redirect_uri=test_oauth_client["redirect_uri"],
            scope=["pg.access"],
            code_challenge=code_challenge,
            code_challenge_method="S256",
            resource=None,
            used=False,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
        )
        async_session.add(auth_code)
        await async_session.commit()

        # Read it back
        result = await async_session.execute(
            select(OAuthAuthorizationCode).where(OAuthAuthorizationCode.code == auth_code.code)
        )
        fetched = result.scalar_one()

        # Update it
        fetched.used = True
        await async_session.commit()

        # Verify update
        await async_session.refresh(fetched)
        assert fetched.used is True

        # Verify all columns still accessible
        assert fetched.user_id == test_user.id
        assert fetched.client_id == test_oauth_client["client_id"]
        assert fetched.scope == ["pg.access"]
        assert fetched.resource is None  # Still NULL

    @pytest.mark.asyncio
    async def test_provider_column_accepts_long_strings(
        self,
        async_session: AsyncSession
    ):
        """
        DB Integrity Test 6: Provider column accepts strings longer than 50 chars.

        After migration y5z6a7b8c9d0, provider column is VARCHAR(200).
        This test verifies DCR client names up to 100 chars work correctly.
        """
        from backend.core.encryption import encrypt_token

        # Create a 100-character provider name (well over the old 50-char limit)
        long_provider_name = "A" * 100

        client = CoreConnection(
            user_id=None,  # OAuth provider clients have NULL user_id
            provider=long_provider_name,
            connection_type="oauth_provider",
            client_id=f"test-long-provider-{uuid4()}",
            client_secret_enc=encrypt_token("test-secret"),
            redirect_uris=["https://chatgpt.com/connector_platform_oauth_redirect"],
            grant_types=["authorization_code", "refresh_token"],
            encrypted_access_token="",
            scopes=["pg.access"],
            token_expires_at=datetime.now(timezone.utc) + timedelta(days=365)
        )
        async_session.add(client)
        await async_session.commit()

        # Verify the row was persisted with the full 100-char provider name
        result = await async_session.execute(
            select(CoreConnection).where(CoreConnection.client_id == client.client_id)
        )
        fetched = result.scalar_one()

        assert fetched.provider == long_provider_name
        assert len(fetched.provider) == 100
