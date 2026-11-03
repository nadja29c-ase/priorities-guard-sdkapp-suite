"""
Tests for rate-limit counter expiry (hotfix 2026-11-03).

Root cause: check_rate_limit incremented the env-prefixed key via redis_client.incr()
but set the expiry via redis_client._client.expire() on the UNPREFIXED key. The expiry
never applied, so every limit was a lifetime cap per key. Production (2026-11-03): all
5,753 rate-limit keys had no TTL; 134 /token keys were permanently over the limit.

These tests run the REAL RedisClient wrapper and check_rate_limit against fakeredis,
which implements the Redis protocol (MULTI/EXEC, EXPIRE NX) — not a hand-written mock,
because the hand-written FakeRedisClient in conftest.py prefixed keys inside expire()
and is exactly what let the bug through.

Each test documents "what bug would still pass this test?"
"""

import asyncio
from unittest.mock import MagicMock, patch

import fakeredis.aioredis
import pytest

from backend.core.rate_limit import RateLimitExceeded, check_rate_limit
from backend.core.redis_client import RedisClient

PREFIX = "test:"
KEY = "ratelimit:oauth:token:client-x:203.0.113.7"
PREFIXED = PREFIX + KEY


@pytest.fixture
def real_wrapper():
    """RedisClient (the production wrapper) backed by fakeredis."""
    client = RedisClient()
    client._env_prefix = PREFIX
    client._client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    with patch("backend.core.rate_limit.redis_client", client):
        yield client


class TestExpiryIsApplied:

    @pytest.mark.asyncio
    async def test_first_request_sets_ttl_on_prefixed_key(self, real_wrapper):
        """
        The test that would have caught the original bug: after the first request the
        PREFIXED key (the one actually counted) has a TTL in (0, window].

        Bug that would still pass: a TTL that is reset on every request (sliding window
        that never lets a busy key expire) — covered by test_existing_ttl_is_not_extended.
        """
        await check_rate_limit(KEY, limit=30, window=60)

        ttl = await real_wrapper._client.ttl(PREFIXED)
        assert 0 < ttl <= 60, f"prefixed key must expire within the window, ttl={ttl}"
        # The unprefixed key must not be created as a side effect
        assert await real_wrapper._client.exists(KEY) == 0

    @pytest.mark.asyncio
    async def test_existing_ttl_is_not_extended(self, real_wrapper):
        """
        Fixed-window semantics: later requests in the window keep the original expiry.

        Bug that would still pass: none of the expiry bugs; a limit that is off by one
        would still pass (covered by TestLimitBoundary).
        """
        await check_rate_limit(KEY, limit=30, window=60)
        await real_wrapper._client.expire(PREFIXED, 5)

        await check_rate_limit(KEY, limit=30, window=60)

        ttl = await real_wrapper._client.ttl(PREFIXED)
        assert 0 < ttl <= 5, f"EXPIRE NX must not overwrite an existing TTL, ttl={ttl}"

    @pytest.mark.asyncio
    async def test_counter_resets_after_window(self, real_wrapper):
        """
        A key that hit the limit is accepted again once the window has passed.

        Bug that would still pass: a window much longer than requested (e.g. seconds
        vs milliseconds confusion in the other direction) is not caught at window=1.
        """
        for _ in range(2):
            await check_rate_limit(KEY, limit=2, window=1)
        with pytest.raises(RateLimitExceeded):
            await check_rate_limit(KEY, limit=2, window=1)

        await asyncio.sleep(1.2)

        await check_rate_limit(KEY, limit=2, window=1)  # must not raise
        assert int(await real_wrapper._client.get(PREFIXED)) == 1


class TestStuckKeyRepair:

    @pytest.mark.asyncio
    async def test_stuck_key_gets_expiry_on_access(self, real_wrapper):
        """
        R3a: a key left by the old build (no TTL, count > limit) is repaired on access.
        It is still rejected for the rest of the window, then expires.

        Bug that would still pass: a repair that sets the TTL but never lets the key
        recover in practice (e.g. very long window) — covered by the window=1 variant.
        """
        await real_wrapper._client.set(PREFIXED, "111")
        assert await real_wrapper._client.ttl(PREFIXED) == -1

        with pytest.raises(RateLimitExceeded):
            await check_rate_limit(KEY, limit=30, window=60)

        ttl = await real_wrapper._client.ttl(PREFIXED)
        assert 0 < ttl <= 60, f"stuck key must be given an expiry, ttl={ttl}"

    @pytest.mark.asyncio
    async def test_stuck_key_recovers_after_one_window(self, real_wrapper):
        """
        R3a end to end: a stuck key is usable again after one window.

        Bug that would still pass: none of the expiry bugs.
        """
        await real_wrapper._client.set(PREFIXED, "111")

        with pytest.raises(RateLimitExceeded):
            await check_rate_limit(KEY, limit=30, window=1)

        await asyncio.sleep(1.2)

        await check_rate_limit(KEY, limit=30, window=1)  # must not raise


class TestLimitBoundary:

    @pytest.mark.asyncio
    async def test_request_n_allowed_n_plus_1_rejected(self, real_wrapper):
        """
        Request N is allowed, N+1 is rejected, within one window.

        Bug that would still pass: none at the boundary; a wrong key (shared bucket)
        is covered by test_independent_buckets_per_client_ip in test_token_rate_limit.py.
        """
        for _ in range(30):
            await check_rate_limit(KEY, limit=30, window=60)
        with pytest.raises(RateLimitExceeded):
            await check_rate_limit(KEY, limit=30, window=60)


class TestAtomicity:

    @pytest.mark.asyncio
    async def test_incr_and_expire_run_in_one_transaction(self):
        """
        R1: increment and expiry are applied as ONE Redis transaction (MULTI/EXEC),
        both on the prefixed key, with EXPIRE NX.

        Bug that would still pass: a transaction whose EXEC result is ignored —
        covered by the fakeredis tests above, which read the real count back.
        """
        client = RedisClient()
        client._env_prefix = PREFIX

        pipe = MagicMock()
        pipe.__aenter__.return_value = pipe

        async def execute():
            return [1, True]

        pipe.execute = execute
        client._client = MagicMock()
        client._client.pipeline.return_value = pipe

        count = await client.incr_with_expiry(KEY, 60)

        assert count == 1
        client._client.pipeline.assert_called_once_with(transaction=True)
        pipe.incr.assert_called_once_with(PREFIXED)
        pipe.expire.assert_called_once_with(PREFIXED, 60, nx=True)


class TestFailOpen:

    @pytest.mark.asyncio
    async def test_redis_error_fails_open_and_logs(self, capsys, caplog):
        """
        R4 / ADR 004: a Redis error inside the counter call lets the request through
        and logs rate_limit.error.

        Bug that would still pass: an error path that fails open but logs nothing
        useful — the event name is asserted, the message content is not.
        """
        client = RedisClient()
        client._env_prefix = PREFIX
        client._client = MagicMock()
        client._client.pipeline.side_effect = ConnectionError("Redis connection lost")

        with patch("backend.core.rate_limit.redis_client", client):
            await check_rate_limit(KEY, limit=1, window=60)  # must not raise
            await check_rate_limit(KEY, limit=1, window=60)  # still must not raise

        # structlog writes to stdout or to stdlib logging depending on which test
        # configured logging first in the session, so check both
        logged = capsys.readouterr().out + caplog.text
        assert "rate_limit.error" in logged, f"Got: {logged}"

    @pytest.mark.asyncio
    async def test_redis_disconnected_bypasses(self, capsys, caplog):
        """
        Disconnected Redis keeps the existing bypass path and event name.

        Bug that would still pass: none relevant to this hotfix (unchanged code path).
        """
        client = RedisClient()  # _client is None -> not connected

        with patch("backend.core.rate_limit.redis_client", client):
            await check_rate_limit(KEY, limit=1, window=60)

        logged = capsys.readouterr().out + caplog.text
        assert "rate_limit.bypassed" in logged, f"Got: {logged}"
