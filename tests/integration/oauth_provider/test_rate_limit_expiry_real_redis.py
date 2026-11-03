"""
Integration tests for rate-limit counter expiry against a REAL Redis server (hotfix 2026-11-03).

Exercises the production code paths (rate_limit_token / rate_limit_register ->
check_rate_limit -> RedisClient.incr_with_expiry) and the one-time cleanup script
(ops/redis_ratelimit_ttl_cleanup.py) against real Redis, not a mock or fakeredis.

Uses an isolated database (default redis://localhost:6379/15, override with
TEST_REDIS_URL) and refuses to run if that database is not empty. Skipped if Redis is
unreachable. Production runs Redis 7.2.4; EXPIRE NX and MULTI/EXEC behave the same on
every Redis >= 7.0.
"""

import asyncio
import importlib.util
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
import redis
import redis.asyncio as aioredis
from fastapi import Request

from backend.core.rate_limit import RateLimitExceeded, rate_limit_register, rate_limit_token
from backend.core.redis_client import RedisClient

TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/15")
PREFIX = "itest:"

pytestmark = pytest.mark.integration


def _redis_available() -> bool:
    try:
        return redis.from_url(TEST_REDIS_URL, socket_connect_timeout=1).ping()
    except Exception:
        return False


if not _redis_available():
    pytest.skip(f"real Redis not reachable at {TEST_REDIS_URL}", allow_module_level=True)


def _load_cleanup_module():
    path = Path(__file__).resolve().parents[3] / "ops" / "redis_ratelimit_ttl_cleanup.py"
    spec = importlib.util.spec_from_file_location("redis_ratelimit_ttl_cleanup", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest_asyncio.fixture
async def real_redis():
    """Production RedisClient wrapper on an isolated, empty real Redis database."""
    raw = aioredis.from_url(TEST_REDIS_URL, decode_responses=True)
    if await raw.dbsize() != 0:
        await raw.aclose()
        pytest.skip(f"{TEST_REDIS_URL} is not empty; refusing to run against it")

    client = RedisClient()
    client._env_prefix = PREFIX
    client._client = raw
    with patch("backend.core.rate_limit.redis_client", client):
        yield client

    await raw.flushdb()
    await raw.aclose()


def _request(ip: str) -> MagicMock:
    req = MagicMock(spec=Request)
    req.state.correlation_id = "itest"
    req.client = MagicMock()
    req.client.host = ip
    req.headers = {}
    return req


async def _end_window(raw, key: str) -> None:
    """Simulate the 60s window ending without waiting 60s: shorten the real TTL."""
    assert await raw.ttl(key) > 0, "key must already carry an expiry"
    await raw.pexpire(key, 50)
    await asyncio.sleep(0.2)
    assert await raw.exists(key) == 0


class TestTokenEndpointRealRedis:

    @pytest.mark.asyncio
    async def test_token_limit_then_accepted_after_window(self, real_redis):
        """
        /token, same client_id + IP: request 31 rejected, real TTL in (0, 60],
        accepted again once the window has passed.

        Bug that would still pass: a window shorter than 60s (the end of the window
        is simulated, not waited for) — the TTL bound assertion limits it to <= 60.
        """
        req = _request("198.51.100.10")
        key = f"{PREFIX}ratelimit:oauth:token:pg-client-test:198.51.100.10"

        for _ in range(30):
            await rate_limit_token(req, "pg-client-test", grant_type="refresh_token")
        with pytest.raises(RateLimitExceeded):
            await rate_limit_token(req, "pg-client-test", grant_type="refresh_token")

        ttl = await real_redis._client.ttl(key)
        assert 0 < ttl <= 60, f"ttl={ttl}"

        await _end_window(real_redis._client, key)
        await rate_limit_token(req, "pg-client-test", grant_type="refresh_token")  # must not raise


class TestRegisterEndpointRealRedis:

    @pytest.mark.asyncio
    async def test_register_limit_then_accepted_after_window(self, real_redis):
        """
        /register, same IP: request 31 rejected, real TTL in (0, 60], accepted again
        after the window. This is the PG-Claude dynamic client registration path.

        Bug that would still pass: same as the /token test.
        """
        req = _request("198.51.100.20")
        key = f"{PREFIX}ratelimit:oauth:register:198.51.100.20"

        for _ in range(30):
            await rate_limit_register(req)
        with pytest.raises(RateLimitExceeded):
            await rate_limit_register(req)

        ttl = await real_redis._client.ttl(key)
        assert 0 < ttl <= 60, f"ttl={ttl}"

        await _end_window(real_redis._client, key)
        await rate_limit_register(req)  # must not raise


class TestStuckKeyRealRedis:

    @pytest.mark.asyncio
    async def test_seeded_stuck_key_recovers(self, real_redis):
        """
        R3a on real Redis: a key in the production failure state (no TTL, count 111)
        gets an expiry on the next request and is usable after the window.

        Bug that would still pass: none of the expiry bugs.
        """
        req = _request("198.51.100.30")
        key = f"{PREFIX}ratelimit:oauth:token:pg-client-test:198.51.100.30"
        await real_redis._client.set(key, "111")
        assert await real_redis._client.ttl(key) == -1

        with pytest.raises(RateLimitExceeded):
            await rate_limit_token(req, "pg-client-test", grant_type="refresh_token")
        assert 0 < await real_redis._client.ttl(key) <= 60

        await _end_window(real_redis._client, key)
        await rate_limit_token(req, "pg-client-test", grant_type="refresh_token")  # must not raise


class TestCleanupScriptRealRedis:

    @pytest.mark.asyncio
    async def test_cleanup_touches_only_no_ttl_ratelimit_string_keys(self, real_redis):
        """
        R3b: dry run changes nothing; apply sets an expiry ONLY on rate-limit string
        keys without a TTL. Non-rate-limit keys, keys with a TTL, keys where
        "ratelimit" is not the second segment, and non-string keys are untouched.
        Nothing is deleted.

        Bug that would still pass: a cleanup that is correct but too slow for the
        production key count (~5,750 keys) — not measured here.
        """
        raw = real_redis._client
        stuck = f"{PREFIX}ratelimit:oauth:token:c:198.51.100.40"
        with_ttl = f"{PREFIX}ratelimit:oauth:register:198.51.100.41"
        other_no_ttl = f"{PREFIX}oauth:auth:abc"
        lookalike = f"{PREFIX}focused:ratelimit:x"
        hash_key = f"{PREFIX}ratelimit:oauth:weird"
        await raw.set(stuck, "111")
        await raw.set(with_ttl, "3", ex=40)
        await raw.set(other_no_ttl, "v")
        await raw.set(lookalike, "5")
        await raw.hset(hash_key, mapping={"a": "1"})

        cleanup = _load_cleanup_module()
        sync = redis.from_url(TEST_REDIS_URL, decode_responses=True)
        try:
            dry = cleanup.run(sync, apply=False, window=60)
            assert await raw.ttl(stuck) == -1, "dry run must not change anything"
            assert dry[f"{PREFIX}ratelimit:oauth:token"]["no_ttl"] == 1

            applied = cleanup.run(sync, apply=True, window=60)
            assert applied[f"{PREFIX}ratelimit:oauth:token"]["expiry_set"] == 1
            assert applied[f"{PREFIX}ratelimit:oauth:weird"]["skipped_not_string"] == 1

            verify = cleanup.run(sync, apply=False, window=60)
            assert all(c.get("no_ttl", 0) == 0 for c in verify.values()), verify
        finally:
            sync.close()

        assert 0 < await raw.ttl(stuck) <= 60
        assert await raw.get(stuck) == "111", "cleanup must not change or delete values"
        assert 0 < await raw.ttl(with_ttl) <= 40, "existing TTL must not be overwritten"
        assert await raw.ttl(other_no_ttl) == -1, "non-rate-limit key must be untouched"
        assert await raw.ttl(lookalike) == -1, "'ratelimit' as a later segment must not match"
        assert await raw.ttl(hash_key) == -1, "non-string key must be untouched"
