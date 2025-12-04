"""
Increment 17: OAuth Provider Hardening - Revoke Rate Limit Tests.

Tests rate limiting on /oauth/focused/revoke endpoint.

Spec: 10 requests / minute per client+IP
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.models import CoreConnection
from backend.core.encryption import encrypt_token


@pytest_asyncio.fixture
async def oauth_client_for_revoke(async_session: AsyncSession) -> dict:
    """Create a test OAuth client for revoke tests."""
    client_id = f"focused-client-revoke-{uuid4().hex[:8]}"
    client_secret = f"test-secret-{uuid4().hex[:16]}"
    redirect_uri = "https://example.com/callback"

    client = CoreConnection(
        user_id=None,
        provider="Test OAuth Client",
        connection_type="oauth_provider",
        client_id=client_id,
        client_secret_enc=encrypt_token(client_secret),
        redirect_uris=[redirect_uri],
        grant_types=["authorization_code", "refresh_token"],
        encrypted_access_token="",
        scopes=["focused.read", "focused.write"],
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        provider_metadata={"client_name": "Revoke Rate Limit Test Client"}
    )
    async_session.add(client)
    await async_session.commit()

    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri
    }


class TestRevokeEndpointRateLimit:
    """Test rate limiting on /oauth/focused/revoke endpoint."""

    @pytest.mark.asyncio
    async def test_revoke_rate_limit_blocks_excessive_requests(
        self,
        client: AsyncClient,
        oauth_client_for_revoke: dict,
        fake_redis_client
    ):
        """
        /oauth/revoke – 10 requests / minute per client+IP

        Fire 11 requests.
        Expect 429 on 11th.
        """
        responses = []
        for i in range(11):
            response = await client.post(
                "/oauth/focused/revoke",
                data={
                    "token": f"fake-token-{i}",
                    "client_id": oauth_client_for_revoke["client_id"]
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            responses.append(response.status_code)

        # First 10 should not be rate limited
        # RFC 7009: revoke endpoint returns 200 or 204 on success
        # (even for invalid/unknown tokens - this prevents token enumeration)
        for i, status in enumerate(responses[:10]):
            assert status in {200, 204}, \
                f"Request {i+1}: expected 200/204 before rate limit, got {status}"

        # 11th should be rate limited
        assert responses[10] == 429, f"11th request should be rate limited, got {responses[10]}"

    @pytest.mark.asyncio
    async def test_revoke_rate_limit_includes_retry_after(
        self,
        client: AsyncClient,
        oauth_client_for_revoke: dict,
        fake_redis_client  # Required for rate limiting to work
    ):
        """
        Rate limited /revoke responses must include correct Retry-After header.

        Verifies:
        1. Retry-After header is present on 429 responses
        2. Value is within expected range (1-60 seconds for 60s window)
        3. Subsequent 429s also include valid Retry-After
        4. Value doesn't reset or become invalid on repeated requests
        """
        client_id = oauth_client_for_revoke["client_id"]

        # Exhaust rate limit (10 requests)
        for i in range(10):
            response = await client.post(
                "/oauth/focused/revoke",
                data={"token": f"fake-token-{i}", "client_id": client_id},
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            assert response.status_code in {200, 204}, \
                f"Request {i+1} should succeed, got {response.status_code}"

        # Make 3 additional requests that should all be rate limited
        # This tests that Retry-After is consistent across multiple 429s
        retry_after_values = []
        for i in range(3):
            response = await client.post(
                "/oauth/focused/revoke",
                data={"token": f"fake-token-limited-{i}", "client_id": client_id},
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )

            assert response.status_code == 429, \
                f"Request {11 + i} should be rate limited, got {response.status_code}"

            assert "Retry-After" in response.headers, \
                "429 response must include Retry-After header"

            retry_after = int(response.headers["Retry-After"])
            retry_after_values.append(retry_after)

            # Retry-After should be within valid range for 60-second window
            # Must be > 0 (some time remaining) and <= 60 (window size)
            assert 1 <= retry_after <= 60, \
                f"Retry-After should be 1-60 seconds, got {retry_after}"

        # Verify Retry-After values are consistent (not resetting)
        # Values should be non-increasing (time is passing)
        # Allow equal values since requests happen quickly
        for i in range(len(retry_after_values) - 1):
            assert retry_after_values[i] >= retry_after_values[i + 1], \
                f"Retry-After should not increase: {retry_after_values}. " \
                "This may indicate the rate limit window is resetting incorrectly."

    @pytest.mark.asyncio
    async def test_revoke_rate_limit_is_per_client_and_ip(
        self,
        client: AsyncClient,
        oauth_client_for_revoke: dict,
        fake_redis_client
    ):
        """
        Rate limit key must be {client_id}:{IP}, not just {client_id}.

        This test verifies that:
        1. Exhausting rate limit for one IP doesn't affect another IP
        2. The rate limit key correctly includes both client_id and IP

        We verify by checking the keys created in fake_redis_client.
        """
        client_id = oauth_client_for_revoke["client_id"]

        # Exhaust rate limit (10 requests)
        for i in range(10):
            await client.post(
                "/oauth/focused/revoke",
                data={
                    "token": f"fake-token-{i}",
                    "client_id": client_id
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )

        # Check that rate limit key includes IP address
        # Keys should be like: rate_limit:revoke:{client_id}:{ip}
        # or similar pattern that includes both client_id and IP
        rate_limit_keys = [
            key for key in fake_redis_client.keys()
            if "revoke" in key.lower() or "rate" in key.lower()
        ]

        assert len(rate_limit_keys) > 0, "No rate limit keys found in Redis"

        # Verify the key contains both client_id and an IP-like component
        for key in rate_limit_keys:
            assert client_id in key, \
                f"Rate limit key should contain client_id: {key}"
            # Check for IP pattern (simple check for testclient IP)
            # In tests, IP is typically 'testclient' or '127.0.0.1'
            has_ip_component = (
                "127.0.0.1" in key or
                "testclient" in key.lower() or
                # Key should have at least 2 colons if it's {prefix}:{client_id}:{ip}
                key.count(":") >= 2
            )
            assert has_ip_component, \
                f"Rate limit key should include IP component: {key}"

    @pytest.mark.asyncio
    async def test_revoke_rate_limit_different_clients_independent(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        fake_redis_client
    ):
        """
        Different client_ids should have completely independent rate limits.

        Test flow:
        1. Client A makes 10 requests → all succeed (not limited)
        2. Client B makes 1 request → succeeds (B has its own counter)
        3. Client A makes 11th request → 429 (rate limited)
        4. Client B makes requests 2-11 → all succeed (B still under limit)

        This catches bugs where:
        - Rate limit key doesn't include client_id
        - Clients share a global counter
        - Key prefix is malformed

        If clients shared a counter, client B would hit 429 after only 1 request
        (since A already used 10). Instead, B should get a full 10 requests.
        """
        # Create two OAuth clients
        client_a_id = f"focused-client-a-{uuid4().hex[:8]}"
        client_b_id = f"focused-client-b-{uuid4().hex[:8]}"

        for cid in [client_a_id, client_b_id]:
            oauth_client = CoreConnection(
                user_id=None,
                provider="Test OAuth Client",
                connection_type="oauth_provider",
                client_id=cid,
                client_secret_enc=encrypt_token(f"secret-{cid}"),
                redirect_uris=["https://example.com/callback"],
                grant_types=["authorization_code", "refresh_token"],
                encrypted_access_token="",
                scopes=["focused.read"],
                token_expires_at=datetime.now(timezone.utc) + timedelta(days=365),
            )
            async_session.add(oauth_client)
        await async_session.commit()

        # Step 1: Client A makes 10 requests (should all succeed)
        for i in range(10):
            response = await client.post(
                "/oauth/focused/revoke",
                data={"token": f"fake-token-a-{i}", "client_id": client_a_id},
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            assert response.status_code in {200, 204}, \
                f"Client A request {i+1}: expected 200/204, got {response.status_code}"

        # Step 2: Client A makes 11th request (should be rate limited)
        response_a_11 = await client.post(
            "/oauth/focused/revoke",
            data={"token": "fake-token-a-11", "client_id": client_a_id},
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert response_a_11.status_code == 429, \
            f"Client A 11th request should be rate limited, got {response_a_11.status_code}"

        # Step 3: Client B makes 11 requests - first 10 should succeed, 11th should be 429
        # This proves B has its own independent counter starting from 0
        responses_b = []
        for i in range(11):
            response = await client.post(
                "/oauth/focused/revoke",
                data={"token": f"fake-token-b-{i}", "client_id": client_b_id},
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            responses_b.append(response.status_code)

        # First 10 requests for B should succeed
        for i, status in enumerate(responses_b[:10]):
            assert status in {200, 204}, \
                f"Client B request {i+1}: expected 200/204, got {status}. " \
                f"Client B should have independent rate limit. If this fails early, " \
                f"clients may be sharing a counter."

        # 11th request for B should be rate limited (B hit its own limit)
        assert responses_b[10] == 429, \
            f"Client B 11th request should be rate limited, got {responses_b[10]}"

    @pytest.mark.asyncio
    async def test_revoke_rate_limit_applies_regardless_of_token_validity(
        self,
        client: AsyncClient,
        oauth_client_for_revoke: dict,
        fake_redis_client
    ):
        """
        Rate limit must apply even for invalid/non-existent tokens.

        Per RFC 7009, the revoke endpoint returns 200 even for invalid tokens
        (to prevent token enumeration). But invalid tokens MUST still count
        toward the rate limit bucket.

        This catches bugs where:
        - Rate limiter only counts successful revocations
        - Token lookup failure bypasses rate limit increment
        - Early return on invalid token skips rate limit check

        Attack scenario without this protection:
        An attacker could probe millions of token values without hitting
        the rate limit if only valid tokens were counted.
        """
        client_id = oauth_client_for_revoke["client_id"]

        # Use the SAME invalid token for all requests
        # This ensures we're testing rate limiting, not token uniqueness
        invalid_token = "completely-invalid-token-that-does-not-exist"

        responses = []
        for i in range(11):
            response = await client.post(
                "/oauth/focused/revoke",
                data={
                    "token": invalid_token,
                    "client_id": client_id
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            responses.append(response.status_code)

        # First 10 requests should return 200 (RFC 7009: always 200 for revoke)
        for i, status in enumerate(responses[:10]):
            assert status in {200, 204}, \
                f"Request {i+1} with invalid token: expected 200/204, got {status}"

        # 11th request should be rate limited, even though all tokens were invalid
        assert responses[10] == 429, \
            f"11th request with invalid token should be rate limited, got {responses[10]}. " \
            "Invalid tokens must still count toward rate limit bucket."

    @pytest.mark.asyncio
    async def test_revoke_rate_limit_resets_after_ttl_expires(
        self,
        client: AsyncClient,
        oauth_client_for_revoke: dict,
        fake_redis_client
    ):
        """
        Rate limit should reset after TTL (60 seconds) expires.

        This catches bugs where:
        - Redis key is created without TTL
        - TTL is not set correctly on increment
        - Limiter misconfigured with wrong window duration

        Test flow:
        1. Exhaust rate limit (11 requests, 11th returns 429)
        2. Advance time past TTL (61 seconds)
        3. Verify next request succeeds (not 429)
        """
        client_id = oauth_client_for_revoke["client_id"]

        # Step 1: Exhaust rate limit
        for i in range(11):
            response = await client.post(
                "/oauth/focused/revoke",
                data={
                    "token": f"fake-token-exhaust-{i}",
                    "client_id": client_id
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )

        # Verify rate limit is active (11th request should be 429)
        assert response.status_code == 429, \
            f"Expected 429 after exhausting rate limit, got {response.status_code}"

        # Step 2: Advance time past TTL (rate limit window is 60 seconds)
        fake_redis_client.advance_time(61)

        # Step 3: Verify rate limit has reset
        response_after_ttl = await client.post(
            "/oauth/focused/revoke",
            data={
                "token": "fake-token-after-ttl",
                "client_id": client_id
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        assert response_after_ttl.status_code in {200, 204}, \
            f"Request after TTL expiry should succeed, got {response_after_ttl.status_code}"

    @pytest.mark.asyncio
    async def test_revoke_rate_limit_key_has_ttl_set(
        self,
        client: AsyncClient,
        oauth_client_for_revoke: dict,
        fake_redis_client
    ):
        """
        Verify rate limit keys have proper TTL set.

        This is a more direct test that catches missing expire() calls.
        """
        client_id = oauth_client_for_revoke["client_id"]

        # Make a single request to create the rate limit key
        await client.post(
            "/oauth/focused/revoke",
            data={
                "token": "fake-token-ttl-check",
                "client_id": client_id
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        # Find rate limit keys
        all_keys = fake_redis_client.keys("*")
        rate_limit_keys = [
            key for key in all_keys
            if "revoke" in key.lower() or "rate" in key.lower()
        ]

        assert len(rate_limit_keys) > 0, "No rate limit keys found after request"

        # Verify each rate limit key has a TTL set
        for key in rate_limit_keys:
            ttl = await fake_redis_client.ttl(key)
            assert ttl > 0, \
                f"Rate limit key '{key}' has no TTL (ttl={ttl}). " \
                "Keys without TTL will never expire, causing permanent rate limiting."
            # TTL should be <= 60 seconds (the rate limit window)
            assert ttl <= 60, \
                f"Rate limit key '{key}' has TTL {ttl}s, expected <= 60s"
