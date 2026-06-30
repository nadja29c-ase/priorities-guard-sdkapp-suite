"""
Tests for /token endpoint rate limiting (inc_token_rate_limit_raise).

Verifies:
1. Limit raised from 5 to 30/min per client+IP
2. Independent buckets per client+IP
3. grant_type logged on exceed only (sanitized)
4. No grant_type log on success
5. Unknown grant_type sanitized to "unknown"

Each test documents "what bug would still pass this test?"
"""

import logging
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import Request

from backend.core.rate_limit import (
    rate_limit_token,
    RateLimitExceeded,
    VALID_GRANT_TYPES,
)


class TestTokenRateLimitValue:
    """Tests for the actual rate limit value (30/min)."""

    @pytest.mark.asyncio
    async def test_allows_30_requests_blocks_31st(self):
        """
        Test 1: rate_limit_token allows up to 30/min, blocks the 31st.

        Bug that would still pass: off-by-one error in the limit check.
        """
        # Track incr calls to simulate Redis counter
        call_count = 0

        async def mock_incr(key):
            nonlocal call_count
            call_count += 1
            return call_count

        mock_request = MagicMock(spec=Request)
        mock_request.state.correlation_id = "test-correlation-id"
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {}

        mock_redis = MagicMock()
        mock_redis.is_connected.return_value = True
        mock_redis.incr = mock_incr
        mock_redis._client = MagicMock()
        mock_redis._client.expire = AsyncMock()

        with patch("backend.core.rate_limit.redis_client", mock_redis):
            # First 30 requests should succeed
            for i in range(30):
                await rate_limit_token(mock_request, "test-client", grant_type="authorization_code")

            # 31st should raise RateLimitExceeded
            with pytest.raises(RateLimitExceeded):
                await rate_limit_token(mock_request, "test-client", grant_type="authorization_code")

        assert call_count == 31, f"Expected 31 calls (30 pass + 1 fail), got {call_count}"

    @pytest.mark.asyncio
    async def test_independent_buckets_per_client_ip(self):
        """
        Test 2: Two different client+IP combos have independent buckets.

        Client A at limit does not block client B.

        Bug that would still pass: key collapsing to global bucket (e.g., forgot {client_id}).
        """
        # Separate counters per key
        counters: dict[str, int] = {}

        async def mock_incr(key):
            counters[key] = counters.get(key, 0) + 1
            return counters[key]

        mock_request = MagicMock(spec=Request)
        mock_request.state.correlation_id = "test-correlation-id"
        mock_request.client = MagicMock()
        mock_request.client.host = "192.168.1.1"
        mock_request.headers = {}

        mock_redis = MagicMock()
        mock_redis.is_connected.return_value = True
        mock_redis.incr = mock_incr
        mock_redis._client = MagicMock()
        mock_redis._client.expire = AsyncMock()

        with patch("backend.core.rate_limit.redis_client", mock_redis):
            # Exhaust client A's bucket (30 requests)
            for _ in range(30):
                await rate_limit_token(mock_request, "client-A", grant_type="authorization_code")

            # Client A's 31st should fail
            with pytest.raises(RateLimitExceeded):
                await rate_limit_token(mock_request, "client-A", grant_type="authorization_code")

            # Client B should still succeed (independent bucket)
            await rate_limit_token(mock_request, "client-B", grant_type="authorization_code")

        # Verify separate keys were used
        assert "ratelimit:oauth:token:client-A:192.168.1.1" in counters
        assert "ratelimit:oauth:token:client-B:192.168.1.1" in counters
        assert counters["ratelimit:oauth:token:client-A:192.168.1.1"] == 31
        assert counters["ratelimit:oauth:token:client-B:192.168.1.1"] == 1


class TestTokenRateLimitLogging:
    """Tests for grant_type logging on rate limit exceed."""

    @pytest.mark.asyncio
    async def test_grant_type_logged_on_exceed(self, capsys):
        """
        Test 3: grant_type appears in the token rate-limit log ON EXCEED.

        Bug that would still pass: guardrail 1 silently not wired (follow-up
        bucket-split decision would be blind to which grant_type is being 429'd).
        """
        # Simulate already at limit (counter returns 31)
        async def mock_incr(key):
            return 31

        mock_request = MagicMock(spec=Request)
        mock_request.state.correlation_id = "test-correlation-id"
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {}

        mock_redis = MagicMock()
        mock_redis.is_connected.return_value = True
        mock_redis.incr = mock_incr
        mock_redis._client = MagicMock()
        mock_redis._client.expire = AsyncMock()

        with patch("backend.core.rate_limit.redis_client", mock_redis):
            with pytest.raises(RateLimitExceeded):
                await rate_limit_token(mock_request, "test-client", grant_type="refresh_token")

        # structlog writes to stdout, not Python's logging
        captured = capsys.readouterr()
        assert "oauth.token.rate_limited" in captured.out, (
            f"Expected oauth.token.rate_limited warning. Got: {captured.out}"
        )
        assert "refresh_token" in captured.out, (
            f"Expected grant_type=refresh_token in log. Got: {captured.out}"
        )

    @pytest.mark.asyncio
    async def test_no_grant_type_log_on_success(self, capsys):
        """
        Test 3a: No grant_type log on a SUCCESSFUL token request.

        A token request under the limit must NOT emit oauth.token.rate_limited.

        Bug that would still pass: logging on every request (noise + corrupted
        telemetry that bucket-split decision relies on).
        """
        # Simulate under limit (counter returns 1)
        async def mock_incr(key):
            return 1

        mock_request = MagicMock(spec=Request)
        mock_request.state.correlation_id = "test-correlation-id"
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {}

        mock_redis = MagicMock()
        mock_redis.is_connected.return_value = True
        mock_redis.incr = mock_incr
        mock_redis._client = MagicMock()
        mock_redis._client.expire = AsyncMock()

        with patch("backend.core.rate_limit.redis_client", mock_redis):
            # Should succeed without raising
            await rate_limit_token(mock_request, "test-client", grant_type="authorization_code")

        # Verify NO rate_limited warning was logged
        captured = capsys.readouterr()
        assert "oauth.token.rate_limited" not in captured.out, (
            f"Expected NO oauth.token.rate_limited on success. Got: {captured.out}"
        )

    @pytest.mark.asyncio
    async def test_unknown_grant_type_sanitized(self, capsys):
        """
        Test 3b: Unknown/garbage grant_type is sanitized to "unknown" in the log.

        Attacker-controlled Form(...) input must not be logged raw (log injection).

        Bug that would still pass: raw grant_type logged, allowing telemetry
        poisoning from malicious client.
        """
        # Simulate at limit
        async def mock_incr(key):
            return 31

        mock_request = MagicMock(spec=Request)
        mock_request.state.correlation_id = "test-correlation-id"
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {}

        mock_redis = MagicMock()
        mock_redis.is_connected.return_value = True
        mock_redis.incr = mock_incr
        mock_redis._client = MagicMock()
        mock_redis._client.expire = AsyncMock()

        with patch("backend.core.rate_limit.redis_client", mock_redis):
            # Try with garbage grant_type
            with pytest.raises(RateLimitExceeded):
                await rate_limit_token(mock_request, "test-client", grant_type="<script>alert('xss')</script>")

        # structlog writes to stdout
        captured = capsys.readouterr()

        # Verify "unknown" appears, NOT the raw garbage
        assert "unknown" in captured.out, (
            f"Expected sanitized grant_type='unknown'. Got: {captured.out}"
        )
        assert "<script>" not in captured.out, (
            f"Raw garbage grant_type should NOT appear in logs. Got: {captured.out}"
        )

    @pytest.mark.asyncio
    async def test_empty_grant_type_sanitized(self, capsys):
        """
        Test 3b variant: Empty/None grant_type is sanitized to "unknown".

        Bug that would still pass: crash on None grant_type.
        """
        async def mock_incr(key):
            return 31

        mock_request = MagicMock(spec=Request)
        mock_request.state.correlation_id = "test-correlation-id"
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {}

        mock_redis = MagicMock()
        mock_redis.is_connected.return_value = True
        mock_redis.incr = mock_incr
        mock_redis._client = MagicMock()
        mock_redis._client.expire = AsyncMock()

        with patch("backend.core.rate_limit.redis_client", mock_redis):
            # Try with None grant_type
            with pytest.raises(RateLimitExceeded):
                await rate_limit_token(mock_request, "test-client", grant_type=None)

        captured = capsys.readouterr()
        assert "unknown" in captured.out


class TestTokenRateLimitKeyShape:
    """Tests for rate limit key shape (client_id extraction)."""

    @pytest.mark.asyncio
    async def test_key_uses_real_client_id_not_placeholder(self):
        """
        Test 4: Key uses real client_id, not literal "[from_header]".

        ChatGPT sends credentials via Basic Auth. The key must use the
        extracted client_id, not a log placeholder.

        Bug that would still pass: all ChatGPT clients sharing one bucket
        because key used "[from_header]" literal string.
        """
        captured_keys: list[str] = []

        async def mock_incr(key):
            captured_keys.append(key)
            return 1

        mock_request = MagicMock(spec=Request)
        mock_request.state.correlation_id = "test-correlation-id"
        mock_request.client = MagicMock()
        mock_request.client.host = "10.0.0.1"
        mock_request.headers = {}

        mock_redis = MagicMock()
        mock_redis.is_connected.return_value = True
        mock_redis.incr = mock_incr
        mock_redis._client = MagicMock()
        mock_redis._client.expire = AsyncMock()

        with patch("backend.core.rate_limit.redis_client", mock_redis):
            await rate_limit_token(
                mock_request,
                "real-chatgpt-client-id-12345",
                grant_type="authorization_code"
            )

        assert len(captured_keys) == 1
        key = captured_keys[0]

        # Key must contain the real client_id
        assert "real-chatgpt-client-id-12345" in key, (
            f"Key should contain real client_id, got: {key}"
        )
        # Key must NOT contain placeholder strings
        assert "[from_header]" not in key, (
            f"Key should NOT contain [from_header] placeholder, got: {key}"
        )
        assert "from_header" not in key.lower(), (
            f"Key should NOT contain any 'from_header' variant, got: {key}"
        )


class TestValidGrantTypes:
    """Tests for the VALID_GRANT_TYPES constant."""

    def test_valid_grant_types_contains_expected_values(self):
        """Verify VALID_GRANT_TYPES contains exactly the expected OAuth grant types."""
        assert VALID_GRANT_TYPES == {"authorization_code", "refresh_token"}
