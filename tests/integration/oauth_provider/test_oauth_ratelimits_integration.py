"""
OAuth Rate Limiting Integration Tests (Increment 16).

Tests the rate limiting functionality:
6.1. /oauth/token – 5 requests / minute per client+IP
6.2. /oauth/register – 10 requests / minute per IP
6.3. /oauth/authorize – 20/min per IP

Uses fakeredis fixture for isolated rate limit testing.

Test framework: pytest
Client: httpx.AsyncClient
Redis: fakeredis (in-memory mock)
"""

import pytest
import pytest_asyncio
import base64
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import patch
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
    """Create a test user for rate limit tests."""
    user = CoreUser(
        chatgpt_user_id=f"test-chatgpt-user-ratelimit-{uuid4().hex[:8]}"
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def oauth_client(async_session: AsyncSession) -> dict:
    """Create a test OAuth client."""
    client_id = f"focused-client-ratelimit-{uuid4().hex[:8]}"
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
        provider_metadata={"client_name": "Rate Limit Test Client"}
    )
    async_session.add(client)
    await async_session.commit()

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri
    }


# ============================================================================
# TEST CLASS: TOKEN ENDPOINT RATE LIMITING (6.1)
# ============================================================================

class TestTokenEndpointRateLimit:
    """Test rate limiting on /oauth/focused/token endpoint."""

    @pytest.mark.asyncio
    async def test_token_rate_limit_allows_normal_usage(
        self,
        client: AsyncClient,
        oauth_client: dict,
        fake_redis_client
    ):
        """
        Normal usage within rate limit should succeed.

        5 requests / minute per client+IP should all pass.
        """
        code_verifier, _ = generate_pkce_pair("rate-limit-normal")

        # Make 5 requests (at limit)
        for i in range(5):
            response = await client.post(
                "/oauth/focused/token",
                data={
                    "grant_type": "authorization_code",
                    "code": f"test-code-{i}",
                    "code_verifier": code_verifier,
                    "client_id": oauth_client["client_id"],
                    "redirect_uri": oauth_client["redirect_uri"]
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            # Will fail with 401 (invalid code) but NOT 429 (rate limit)
            assert response.status_code != 429, f"Request {i+1} was rate limited unexpectedly"

    @pytest.mark.asyncio
    async def test_token_rate_limit_blocks_excessive_requests(
        self,
        client: AsyncClient,
        oauth_client: dict,
        fake_redis_client
    ):
        """
        6.1. /oauth/token – 5 requests / minute per client+IP

        Make 6 quick requests.
        Expect 429 Too Many Requests for the 6th.
        """
        code_verifier, _ = generate_pkce_pair("rate-limit-excessive")

        responses = []
        for i in range(6):
            response = await client.post(
                "/oauth/focused/token",
                data={
                    "grant_type": "authorization_code",
                    "code": f"rate-limit-code-{i}",
                    "code_verifier": code_verifier,
                    "client_id": oauth_client["client_id"],
                    "redirect_uri": oauth_client["redirect_uri"]
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            responses.append(response.status_code)

        # First 5 should not be rate limited (will be 401 invalid_grant)
        for i, status in enumerate(responses[:5]):
            assert status != 429, f"Request {i+1} was rate limited unexpectedly"

        # 6th should be rate limited
        assert responses[5] == 429, f"6th request should be rate limited, got {responses[5]}"


# ============================================================================
# TEST CLASS: REGISTER ENDPOINT RATE LIMITING (6.2)
# ============================================================================

class TestRegisterEndpointRateLimit:
    """Test rate limiting on /oauth/focused/register endpoint."""

    @pytest.mark.asyncio
    async def test_register_rate_limit_blocks_excessive_requests(
        self,
        client: AsyncClient,
        fake_redis_client
    ):
        """
        6.2. /oauth/register – 10 requests / minute per IP

        Fire 11 requests.
        Expect 429 on 11th.
        """
        responses = []
        for i in range(11):
            response = await client.post(
                "/oauth/focused/register",
                json={
                    "client_name": f"Rate Limit Test Client {i}",
                    "redirect_uris": ["https://example.com/callback"],
                    "grant_types": ["authorization_code", "refresh_token"],
                    "response_types": ["code"],
                    "token_endpoint_auth_method": "client_secret_post"
                }
            )
            responses.append(response.status_code)

        # First 10 should not be rate limited (may succeed or fail for other reasons)
        for i, status in enumerate(responses[:10]):
            assert status != 429, f"Request {i+1} was rate limited unexpectedly"

        # 11th should be rate limited
        assert responses[10] == 429, f"11th request should be rate limited, got {responses[10]}"

    @pytest.mark.asyncio
    async def test_register_rate_limit_includes_retry_after_header(
        self,
        client: AsyncClient,
        fake_redis_client
    ):
        """
        Rate limited responses should include Retry-After header.
        """
        # Exhaust rate limit
        for i in range(11):
            response = await client.post(
                "/oauth/focused/register",
                json={
                    "client_name": f"Rate Limit Header Test {i}",
                    "redirect_uris": ["https://example.com/callback"],
                    "grant_types": ["authorization_code"]
                }
            )
            if response.status_code == 429:
                assert "Retry-After" in response.headers
                retry_after = int(response.headers["Retry-After"])
                assert retry_after > 0
                break


# ============================================================================
# TEST CLASS: AUTHORIZE ENDPOINT RATE LIMITING (6.3)
# ============================================================================

class TestAuthorizeEndpointRateLimit:
    """Test rate limiting on /oauth/focused/authorize endpoint."""

    @pytest.mark.asyncio
    async def test_authorize_rate_limit_by_ip(
        self,
        client: AsyncClient,
        oauth_client: dict,
        fake_redis_client
    ):
        """
        6.3. /oauth/authorize – 20/min per IP

        Simulate 21 calls from same IP.
        Expect 429 on 21st.
        """
        code_verifier, code_challenge = generate_pkce_pair("authorize-rate-limit")

        responses = []
        for i in range(21):
            response = await client.get(
                "/oauth/focused/authorize",
                params={
                    "response_type": "code",
                    "client_id": oauth_client["client_id"],
                    "redirect_uri": oauth_client["redirect_uri"],
                    "code_challenge": code_challenge,
                    "code_challenge_method": "S256",
                    "scope": "focused.read",
                    "state": f"state-{i}"
                }
            )
            responses.append(response.status_code)

        # First 20 should not be rate limited
        for i, status in enumerate(responses[:20]):
            assert status != 429, f"Request {i+1} was rate limited unexpectedly"

        # 21st should be rate limited
        assert responses[20] == 429, f"21st request should be rate limited, got {responses[20]}"

# ============================================================================
# TEST CLASS: RATE LIMIT ISOLATION
# ============================================================================

class TestRateLimitIsolation:
    """Test that rate limits are properly isolated by key."""

    @pytest.mark.asyncio
    async def test_different_clients_have_separate_rate_limits(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        fake_redis_client
    ):
        """
        Rate limits for /token are per client+IP, not global.

        Two different clients should each get their own limit.
        """
        # Create two clients
        clients = []
        for i in range(2):
            client_id = f"focused-client-isolation-{i}-{uuid4().hex[:8]}"
            oauth_client = CoreConnection(
                user_id=None,
                provider=f"Test OAuth Client {i}",
                connection_type="oauth_provider",
                client_id=client_id,
                client_secret_enc=encrypt_token("secret"),
                redirect_uris=["https://example.com/callback"],
                grant_types=["authorization_code", "refresh_token"],
                encrypted_access_token="",
                scopes=["focused.read"],
                token_expires_at=datetime.now(timezone.utc) + timedelta(days=365)
            )
            async_session.add(oauth_client)
            clients.append(client_id)
        await async_session.commit()

        code_verifier, _ = generate_pkce_pair("isolation-test")

        # Exhaust rate limit for client 0 (limit is 5/min, so 6th should be 429)
        responses_client0 = []
        for i in range(6):
            response = await client.post(
                "/oauth/focused/token",
                data={
                    "grant_type": "authorization_code",
                    "code": f"code-{i}",
                    "code_verifier": code_verifier,
                    "client_id": clients[0],
                    "redirect_uri": "https://example.com/callback"
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            responses_client0.append(response.status_code)

        # First 5 should not be rate limited (may return 400 for invalid code, but not 429)
        for i, status in enumerate(responses_client0[:5]):
            assert status != 429, f"Request {i+1} for client 0 was rate limited unexpectedly"

        # 6th request for client 0 MUST be rate limited - proves rate limiting works
        assert responses_client0[5] == 429, (
            f"6th request for client 0 should be rate limited, got {responses_client0[5]}. "
            "Rate limiting may be broken."
        )

        # Client 1 should still be able to make requests (different rate limit key)
        response = await client.post(
            "/oauth/focused/token",
            data={
                "grant_type": "authorization_code",
                "code": "code-new",
                "code_verifier": code_verifier,
                "client_id": clients[1],
                "redirect_uri": "https://example.com/callback"
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        # Should not be rate limited (client 1 has fresh limit)
        assert response.status_code != 429, (
            "Client 1 should not be rate limited - rate limits should be per-client"
        )


# ============================================================================
# TEST CLASS: RATE LIMIT GRACEFUL DEGRADATION
# ============================================================================

class TestRateLimitGracefulDegradation:
    """Test behavior when Redis is unavailable."""

    @pytest.mark.asyncio
    async def test_requests_allowed_when_redis_disconnected(
        self,
        client: AsyncClient,
        oauth_client: dict
    ):
        """
        When Redis is disconnected, rate limiting should be bypassed.

        This tests graceful degradation - don't block users when
        rate limiting infrastructure is down.
        """
        from unittest.mock import MagicMock

        # Create a mock that reports disconnected
        mock_redis = MagicMock()
        mock_redis.is_connected.return_value = False

        code_verifier, _ = generate_pkce_pair("redis-disconnected")

        with patch("backend.core.rate_limit.redis_client", mock_redis):
            # Make more requests than the limit (limit is 5/min for token)
            for i in range(10):
                response = await client.post(
                    "/oauth/focused/token",
                    data={
                        "grant_type": "authorization_code",
                        "code": f"code-{i}",
                        "code_verifier": code_verifier,
                        "client_id": oauth_client["client_id"],
                        "redirect_uri": oauth_client["redirect_uri"]
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                # None should be 429 when Redis is disconnected
                assert response.status_code != 429, f"Request {i+1} was rate limited with Redis disconnected"

    @pytest.mark.asyncio
    async def test_requests_allowed_when_redis_raises_error(
        self,
        client: AsyncClient,
        oauth_client: dict
    ):
        """
        When Redis raises connection errors, rate limiting should be bypassed.

        This tests that the rate limiter catches exceptions and allows
        requests through rather than blocking users.
        """
        from unittest.mock import MagicMock, AsyncMock

        # Create a mock that raises ConnectionError on incr
        mock_redis = MagicMock()
        mock_redis.is_connected.return_value = True
        mock_redis.incr = AsyncMock(side_effect=ConnectionError("Redis connection failed"))

        code_verifier, _ = generate_pkce_pair("redis-error")

        with patch("backend.core.rate_limit.redis_client", mock_redis):
            # Make more requests than the limit
            for i in range(10):
                response = await client.post(
                    "/oauth/focused/token",
                    data={
                        "grant_type": "authorization_code",
                        "code": f"code-{i}",
                        "code_verifier": code_verifier,
                        "client_id": oauth_client["client_id"],
                        "redirect_uri": oauth_client["redirect_uri"]
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                # None should be 429 when Redis raises errors
                assert response.status_code != 429, f"Request {i+1} was rate limited despite Redis error"
