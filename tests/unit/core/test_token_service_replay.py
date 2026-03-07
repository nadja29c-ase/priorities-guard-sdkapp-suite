"""
Tests for Redis idempotent token replay (Increment 43).

Verifies that duplicate /oauth/token requests return cached responses
instead of invalid_grant errors.

Unit tests (8 required):
1. Redis hit + client_id match -> replayed token response
2. Redis hit + client_id mismatch -> invalid_grant
3. Redis unavailable at read time -> invalid_grant, no crash
4. Redis unavailable at write time -> first exchange completes, replay_write_failed logged
5. Redis TTL expired (key missing on second call) -> invalid_grant
6. oauth.token.idempotent_replay logged with correct fields
7. DB commit fails after Redis write -> Redis key deleted best-effort, exception propagated
8. Returned token_response never contains client_id or wrapper fields
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4

import pytest


class TestTokenReplayRedisHit:
    """Tests for successful Redis cache hits."""

    @pytest.mark.asyncio
    async def test_redis_hit_client_id_match_returns_cached_response(self):
        """
        Test 1: Redis hit + client_id match -> replayed token response.

        When auth_code.used=True and Redis has cached response with matching
        client_id, return the cached token response.
        """
        from backend.core.oauth_provider.services.token_service import exchange_authorization_code

        user_id = uuid4()
        client_id = "test-client-abc"
        cached_jti = str(uuid4())

        # Cached token response
        cached_token_response = {
            "access_token": "cached_access_token_xyz",
            "refresh_token": "cached_refresh_token_xyz",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "pg.access"
        }

        # Redis wrapper format
        cached_wrapper = {
            "client_id": client_id,
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "jti": cached_jti,
            "token_response": cached_token_response
        }

        # Mock auth code that is already used
        mock_code = MagicMock()
        mock_code.user_id = user_id
        mock_code.client_id = client_id
        mock_code.used = True  # Already used
        mock_code.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

        mock_db = AsyncMock()

        async def mock_execute(stmt):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_code
            return mock_result

        mock_db.execute = mock_execute

        # Mock Redis to return cached wrapper
        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_wrapper))

        with patch(
            "backend.core.oauth_provider.services.token_service.redis_client",
            mock_redis
        ):
            result = await exchange_authorization_code(
                db=mock_db,
                code="test_auth_code",
                code_verifier="test_verifier",
                client_id=client_id,
                redirect_uri="https://example.com/callback"
            )

        # Should return cached token response
        assert result == cached_token_response
        assert result["access_token"] == "cached_access_token_xyz"
        assert result["refresh_token"] == "cached_refresh_token_xyz"

        # Redis.get should have been called
        mock_redis.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_hit_client_id_mismatch_returns_invalid_grant(self):
        """
        Test 2: Redis hit + client_id mismatch -> invalid_grant.

        Security: prevent cross-client replay attacks.
        """
        from backend.core.oauth_provider.services.token_service import exchange_authorization_code

        user_id = uuid4()
        original_client_id = "original-client"
        attacker_client_id = "attacker-client"

        # Cached wrapper has original client_id
        cached_wrapper = {
            "client_id": original_client_id,
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "jti": str(uuid4()),
            "token_response": {"access_token": "token", "refresh_token": "refresh"}
        }

        # Mock auth code that is already used
        mock_code = MagicMock()
        mock_code.user_id = user_id
        mock_code.client_id = original_client_id
        mock_code.used = True
        mock_code.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

        mock_db = AsyncMock()

        async def mock_execute(stmt):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_code
            return mock_result

        mock_db.execute = mock_execute

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_wrapper))

        with patch(
            "backend.core.oauth_provider.services.token_service.redis_client",
            mock_redis
        ):
            result = await exchange_authorization_code(
                db=mock_db,
                code="test_auth_code",
                code_verifier="test_verifier",
                client_id=attacker_client_id,  # Different client_id
                redirect_uri="https://example.com/callback"
            )

        # Should return invalid_grant
        assert isinstance(result, tuple)
        assert result[0] == "invalid_grant"
        assert "already used" in result[1].lower()


class TestTokenReplayRedisUnavailable:
    """Tests for Redis unavailability scenarios."""

    @pytest.mark.asyncio
    async def test_redis_unavailable_at_read_returns_invalid_grant(self):
        """
        Test 3: Redis unavailable at read time -> invalid_grant, no crash.

        Fail-open: Redis errors should fall through to normal invalid_grant.
        """
        from backend.core.oauth_provider.services.token_service import exchange_authorization_code

        user_id = uuid4()
        client_id = "test-client"

        mock_code = MagicMock()
        mock_code.user_id = user_id
        mock_code.client_id = client_id
        mock_code.used = True
        mock_code.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

        mock_db = AsyncMock()

        async def mock_execute(stmt):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_code
            return mock_result

        mock_db.execute = mock_execute

        # Redis raises exception on get
        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(side_effect=ConnectionError("Redis unavailable"))

        with patch(
            "backend.core.oauth_provider.services.token_service.redis_client",
            mock_redis
        ):
            result = await exchange_authorization_code(
                db=mock_db,
                code="test_auth_code",
                code_verifier="test_verifier",
                client_id=client_id,
                redirect_uri="https://example.com/callback"
            )

        # Should return invalid_grant (not crash)
        assert isinstance(result, tuple)
        assert result[0] == "invalid_grant"
        assert "already used" in result[1].lower()

    @pytest.mark.asyncio
    async def test_redis_unavailable_at_write_completes_exchange(self):
        """
        Test 4: Redis unavailable at write time -> first exchange completes.

        Redis write failure should be swallowed; token issuance must succeed.
        """
        from backend.core.oauth_provider.services.token_service import exchange_authorization_code

        user_id = uuid4()
        client_id = "test-client"

        mock_code = MagicMock()
        mock_code.user_id = user_id
        mock_code.client_id = client_id
        mock_code.redirect_uri = "https://example.com/callback"
        mock_code.scope = ["pg.access"]
        mock_code.code_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        mock_code.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        mock_code.used = False
        mock_code.resource = None

        mock_db = AsyncMock()
        mock_db.add = MagicMock()

        async def mock_execute(stmt):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_code
            return mock_result

        mock_db.execute = mock_execute

        # Redis raises exception on set (write failure)
        mock_redis = MagicMock()
        mock_redis.set = AsyncMock(side_effect=ConnectionError("Redis write failed"))

        with patch(
            "backend.core.oauth_provider.services.token_service.redis_client",
            mock_redis
        ), patch(
            "backend.core.oauth_provider.services.token_service.verify_pkce",
            return_value=True
        ), patch(
            "backend.core.oauth_provider.services.token_service.create_access_token",
            return_value=("mock_access_token", str(uuid4()))
        ), patch(
            "backend.core.oauth_provider.services.token_service.create_refresh_token",
            return_value="mock_refresh_token"
        ), patch(
            "backend.core.oauth_provider.services.token_service.encrypt_token",
            return_value="encrypted"
        ):
            result = await exchange_authorization_code(
                db=mock_db,
                code="test_auth_code",
                code_verifier="test_verifier",
                client_id=client_id,
                redirect_uri="https://example.com/callback"
            )

        # Should succeed despite Redis failure
        assert isinstance(result, dict)
        assert "access_token" in result
        assert result["access_token"] == "mock_access_token"

        # db.commit should have been called
        assert mock_db.commit.call_count == 1


class TestTokenReplayTTLExpired:
    """Tests for Redis TTL expiration."""

    @pytest.mark.asyncio
    async def test_redis_key_missing_returns_invalid_grant(self):
        """
        Test 5: Redis TTL expired (key missing on second call) -> invalid_grant.

        After 30s TTL, the cached response is gone.
        """
        from backend.core.oauth_provider.services.token_service import exchange_authorization_code

        user_id = uuid4()
        client_id = "test-client"

        mock_code = MagicMock()
        mock_code.user_id = user_id
        mock_code.client_id = client_id
        mock_code.used = True
        mock_code.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

        mock_db = AsyncMock()

        async def mock_execute(stmt):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_code
            return mock_result

        mock_db.execute = mock_execute

        # Redis returns None (key expired/missing)
        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=None)

        with patch(
            "backend.core.oauth_provider.services.token_service.redis_client",
            mock_redis
        ):
            result = await exchange_authorization_code(
                db=mock_db,
                code="test_auth_code",
                code_verifier="test_verifier",
                client_id=client_id,
                redirect_uri="https://example.com/callback"
            )

        # Should return invalid_grant
        assert isinstance(result, tuple)
        assert result[0] == "invalid_grant"


class TestTokenReplayLogging:
    """Tests for logging behavior."""

    @pytest.mark.asyncio
    async def test_idempotent_replay_logged_with_correct_fields(self):
        """
        Test 6: oauth.token.idempotent_replay logged with correct fields.

        Log must include: masked client_id, jti, replay_age_seconds.
        """
        from backend.core.oauth_provider.services.token_service import exchange_authorization_code

        user_id = uuid4()
        client_id = "test-client-xyz123"
        cached_jti = str(uuid4())

        cached_wrapper = {
            "client_id": client_id,
            "cached_at": (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(),
            "jti": cached_jti,
            "token_response": {"access_token": "token", "refresh_token": "refresh"}
        }

        mock_code = MagicMock()
        mock_code.user_id = user_id
        mock_code.client_id = client_id
        mock_code.used = True
        mock_code.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

        mock_db = AsyncMock()

        async def mock_execute(stmt):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_code
            return mock_result

        mock_db.execute = mock_execute

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_wrapper))

        with patch(
            "backend.core.oauth_provider.services.token_service.redis_client",
            mock_redis
        ), patch(
            "backend.core.oauth_provider.services.token_service.logger"
        ) as mock_logger:
            # Mock the bind method to return a logger that we can inspect
            mock_bound_logger = MagicMock()
            mock_logger.bind.return_value = mock_bound_logger

            result = await exchange_authorization_code(
                db=mock_db,
                code="test_auth_code",
                code_verifier="test_verifier",
                client_id=client_id,
                redirect_uri="https://example.com/callback",
                correlation_id="test-correlation"
            )

        # Verify log was called with correct event
        mock_bound_logger.info.assert_called()
        log_calls = mock_bound_logger.info.call_args_list

        # Find the idempotent_replay log call
        replay_log = None
        for call_obj in log_calls:
            if call_obj[0][0] == "oauth.token.idempotent_replay":
                replay_log = call_obj
                break

        assert replay_log is not None, "oauth.token.idempotent_replay not logged"

        # Check kwargs contain required fields
        kwargs = replay_log[1]
        assert "client_id" in kwargs
        assert "jti" in kwargs
        assert kwargs["jti"] == cached_jti
        assert "replay_age_seconds" in kwargs


class TestTokenReplayDbCommitFailure:
    """Tests for DB commit failure handling."""

    @pytest.mark.asyncio
    async def test_db_commit_fails_redis_key_deleted(self):
        """
        Test 7: DB commit fails after Redis write -> Redis key deleted best-effort.

        Exception must be propagated after cleanup attempt.
        """
        from backend.core.oauth_provider.services.token_service import exchange_authorization_code

        user_id = uuid4()
        client_id = "test-client"

        mock_code = MagicMock()
        mock_code.user_id = user_id
        mock_code.client_id = client_id
        mock_code.redirect_uri = "https://example.com/callback"
        mock_code.scope = ["pg.access"]
        mock_code.code_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        mock_code.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        mock_code.used = False
        mock_code.resource = None

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock(side_effect=RuntimeError("DB commit failed"))

        async def mock_execute(stmt):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_code
            return mock_result

        mock_db.execute = mock_execute

        mock_redis = MagicMock()
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.delete = AsyncMock(return_value=1)

        with patch(
            "backend.core.oauth_provider.services.token_service.redis_client",
            mock_redis
        ), patch(
            "backend.core.oauth_provider.services.token_service.verify_pkce",
            return_value=True
        ), patch(
            "backend.core.oauth_provider.services.token_service.create_access_token",
            return_value=("mock_access_token", str(uuid4()))
        ), patch(
            "backend.core.oauth_provider.services.token_service.create_refresh_token",
            return_value="mock_refresh_token"
        ), patch(
            "backend.core.oauth_provider.services.token_service.encrypt_token",
            return_value="encrypted"
        ):
            with pytest.raises(RuntimeError, match="DB commit failed"):
                await exchange_authorization_code(
                    db=mock_db,
                    code="test_auth_code",
                    code_verifier="test_verifier",
                    client_id=client_id,
                    redirect_uri="https://example.com/callback"
                )

        # Redis.set should have been called (write before commit)
        mock_redis.set.assert_called_once()

        # Redis.delete should have been called (cleanup on commit failure)
        mock_redis.delete.assert_called_once()


class TestTokenReplayResponseFormat:
    """Tests for response format correctness."""

    @pytest.mark.asyncio
    async def test_returned_response_never_contains_wrapper_fields(self):
        """
        Test 8: Returned token_response never contains client_id or wrapper fields.

        Security: wrapper is internal; only token_response is returned to caller.
        """
        from backend.core.oauth_provider.services.token_service import exchange_authorization_code

        user_id = uuid4()
        client_id = "test-client"

        mock_code = MagicMock()
        mock_code.user_id = user_id
        mock_code.client_id = client_id
        mock_code.redirect_uri = "https://example.com/callback"
        mock_code.scope = ["pg.access"]
        mock_code.code_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        mock_code.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        mock_code.used = False
        mock_code.resource = None

        mock_db = AsyncMock()
        mock_db.add = MagicMock()

        async def mock_execute(stmt):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_code
            return mock_result

        mock_db.execute = mock_execute

        mock_redis = MagicMock()
        mock_redis.set = AsyncMock(return_value=True)

        with patch(
            "backend.core.oauth_provider.services.token_service.redis_client",
            mock_redis
        ), patch(
            "backend.core.oauth_provider.services.token_service.verify_pkce",
            return_value=True
        ), patch(
            "backend.core.oauth_provider.services.token_service.create_access_token",
            return_value=("mock_access_token", str(uuid4()))
        ), patch(
            "backend.core.oauth_provider.services.token_service.create_refresh_token",
            return_value="mock_refresh_token"
        ), patch(
            "backend.core.oauth_provider.services.token_service.encrypt_token",
            return_value="encrypted"
        ):
            result = await exchange_authorization_code(
                db=mock_db,
                code="test_auth_code",
                code_verifier="test_verifier",
                client_id=client_id,
                redirect_uri="https://example.com/callback"
            )

        # Should be a dict (success)
        assert isinstance(result, dict)

        # Should contain standard OAuth fields
        assert "access_token" in result
        assert "refresh_token" in result
        assert "token_type" in result
        assert "expires_in" in result
        assert "scope" in result

        # Should NOT contain wrapper fields
        assert "client_id" not in result, "client_id should not be in token_response"
        assert "cached_at" not in result, "cached_at should not be in token_response"
        assert "jti" not in result, "jti should not be in token_response"
        assert "token_response" not in result, "nested token_response should not exist"


# =============================================================================
# Increment 48 — Additional test coverage
# =============================================================================

class TestTokenReplayKeyFormat:
    """Tests for Redis key format correctness (Increment 48)."""

    @pytest.mark.asyncio
    async def test_redis_key_format_correct(self):
        """
        Test A: Redis key format is token_replay:{sha256_hex}.

        Key must start with 'token_replay:' and have 64-char sha256 hex suffix.
        """
        from backend.core.oauth_provider.services.token_service import exchange_authorization_code

        user_id = uuid4()
        client_id = "test-client"

        cached_wrapper = {
            "client_id": client_id,
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "jti": str(uuid4()),
            "token_response": {"access_token": "token", "refresh_token": "refresh"}
        }

        mock_code = MagicMock()
        mock_code.user_id = user_id
        mock_code.client_id = client_id
        mock_code.used = True
        mock_code.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

        mock_db = AsyncMock()

        async def mock_execute(stmt):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_code
            return mock_result

        mock_db.execute = mock_execute

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_wrapper))

        with patch(
            "backend.core.oauth_provider.services.token_service.redis_client",
            mock_redis
        ):
            await exchange_authorization_code(
                db=mock_db,
                code="test_auth_code",
                code_verifier="test_verifier",
                client_id=client_id,
                redirect_uri="https://example.com/callback"
            )

        # Extract the key used in Redis.get call
        mock_redis.get.assert_called_once()
        key = mock_redis.get.call_args[0][0]

        # Verify key format
        assert key.startswith("token_replay:"), f"Key should start with 'token_replay:', got: {key}"
        assert len(key) == len("token_replay:") + 64, (
            f"Key should be 'token_replay:' + 64 hex chars, got length {len(key)}"
        )

    def test_sha256_case_sensitivity(self):
        """
        Test B: sha256 hash is case-sensitive — no normalization applied.

        'ABCdef' and 'abcdef' must produce different keys.
        """
        from backend.core.oauth_provider.services.token_service import _token_replay_key

        key_upper = _token_replay_key("ABCdef")
        key_lower = _token_replay_key("abcdef")

        assert key_upper != key_lower, (
            "Different case codes should produce different keys (no normalization)"
        )
        # Both should still have correct format
        assert key_upper.startswith("token_replay:")
        assert key_lower.startswith("token_replay:")


class TestTokenReplayTTLWithFakeRedis:
    """Tests for TTL expiry using FakeRedisClient (Increment 48)."""

    @pytest.mark.asyncio
    async def test_ttl_expiry_with_fake_redis(self, fake_redis):
        """
        Test C: TTL expiry using FakeRedis advance_time.

        Write a cached wrapper with 30s TTL, advance time by 31s,
        then verify invalid_grant is returned (key expired).
        """
        from backend.core.oauth_provider.services.token_service import (
            exchange_authorization_code,
            _token_replay_key,
            TOKEN_REPLAY_TTL_SECONDS,
        )

        user_id = uuid4()
        client_id = "test-client"
        code = "test_auth_code_ttl"

        # Pre-populate fake_redis with a cached wrapper
        cached_wrapper = {
            "client_id": client_id,
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "jti": str(uuid4()),
            "token_response": {"access_token": "token", "refresh_token": "refresh"}
        }

        replay_key = _token_replay_key(code)
        # Write directly to fake_redis (simulating first successful exchange)
        await fake_redis.set(replay_key, json.dumps(cached_wrapper), ex=TOKEN_REPLAY_TTL_SECONDS)

        # Verify key exists
        assert await fake_redis.get(replay_key) is not None

        # Advance time past TTL
        fake_redis.advance_time(31)

        # Verify key is now expired
        assert await fake_redis.get(replay_key) is None

        # Now simulate a duplicate request with used=True auth code
        mock_code = MagicMock()
        mock_code.user_id = user_id
        mock_code.client_id = client_id
        mock_code.used = True
        mock_code.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

        mock_db = AsyncMock()

        async def mock_execute(stmt):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_code
            return mock_result

        mock_db.execute = mock_execute

        with patch(
            "backend.core.oauth_provider.services.token_service.redis_client",
            fake_redis
        ):
            result = await exchange_authorization_code(
                db=mock_db,
                code=code,
                code_verifier="test_verifier",
                client_id=client_id,
                redirect_uri="https://example.com/callback"
            )

        # Should return invalid_grant (TTL expired, key gone)
        assert isinstance(result, tuple)
        assert result[0] == "invalid_grant"


class TestTokenReplayConcurrency:
    """Tests for concurrent duplicate requests (Increment 48)."""

    @pytest.mark.asyncio
    async def test_concurrent_duplicates_no_crash(self, fake_redis):
        """
        Test D: Concurrent duplicate requests must not crash.

        Two concurrent requests with same code: one should succeed or return
        cached response, the other should return cached or invalid_grant.
        Neither should raise an exception.
        """
        import asyncio
        from backend.core.oauth_provider.services.token_service import exchange_authorization_code

        user_id = uuid4()
        client_id = "test-client"
        code = "test_concurrent_code"

        # Track whether code has been "used" - shared state across calls
        code_used = {"value": False}

        def create_mock_code():
            """Create a mock auth code with dynamic used status."""
            mock_code = MagicMock()
            mock_code.user_id = user_id
            mock_code.client_id = client_id
            mock_code.redirect_uri = "https://example.com/callback"
            mock_code.scope = ["pg.access"]
            mock_code.code_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
            mock_code.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
            mock_code.resource = None
            # Use current value at time of access
            mock_code.used = code_used["value"]
            return mock_code

        call_count = {"value": 0}

        async def mock_execute(stmt):
            call_count["value"] += 1
            mock_result = MagicMock()
            mock_code = create_mock_code()
            mock_result.scalar_one_or_none.return_value = mock_code
            return mock_result

        def make_mock_db():
            mock_db = AsyncMock()
            mock_db.execute = mock_execute
            mock_db.add = MagicMock()

            async def mock_commit():
                # First commit marks code as used
                code_used["value"] = True

            mock_db.commit = mock_commit
            return mock_db

        async def do_exchange():
            mock_db = make_mock_db()
            with patch(
                "backend.core.oauth_provider.services.token_service.redis_client",
                fake_redis
            ), patch(
                "backend.core.oauth_provider.services.token_service.verify_pkce",
                return_value=True
            ), patch(
                "backend.core.oauth_provider.services.token_service.create_access_token",
                return_value=("mock_access_token", str(uuid4()))
            ), patch(
                "backend.core.oauth_provider.services.token_service.create_refresh_token",
                return_value="mock_refresh_token"
            ), patch(
                "backend.core.oauth_provider.services.token_service.encrypt_token",
                return_value="encrypted"
            ):
                return await exchange_authorization_code(
                    db=mock_db,
                    code=code,
                    code_verifier="test_verifier",
                    client_id=client_id,
                    redirect_uri="https://example.com/callback"
                )

        # Run two concurrent exchanges
        results = await asyncio.gather(
            do_exchange(),
            do_exchange(),
            return_exceptions=True
        )

        # Neither should raise an exception
        for i, result in enumerate(results):
            assert not isinstance(result, Exception), (
                f"Exchange {i} raised exception: {result}"
            )

        # Categorize results
        successes = [r for r in results if isinstance(r, dict)]
        failures = [r for r in results if isinstance(r, tuple)]

        # At least one should succeed
        assert len(successes) >= 1, "At least one exchange should succeed"

        # Failures should be invalid_grant
        for failure in failures:
            assert failure[0] == "invalid_grant"


class TestTokenReplaySecurityBehavior:
    """Tests documenting security behavior on replay path (Increment 48)."""

    @pytest.mark.asyncio
    async def test_redirect_uri_mismatch_on_replay_returns_cached(self):
        """
        Test E: redirect_uri mismatch on replay still returns cached token.

        SECURITY NOTE: This is CORRECT behavior. redirect_uri is validated at
        authorization code creation time, not on replay. The replay path only
        verifies client_id matches the cached wrapper. A different redirect_uri
        in the replay request does not block replay because:
        1. The code is already used=True (validated on first exchange)
        2. The replay cache is keyed on code hash, gated on client_id only
        3. redirect_uri validation happened on first exchange

        This test documents and locks in this behavior.
        """
        from backend.core.oauth_provider.services.token_service import exchange_authorization_code

        user_id = uuid4()
        client_id = "test-client"
        original_redirect = "https://example.com/callback"
        different_redirect = "https://attacker.com/callback"

        cached_token_response = {
            "access_token": "cached_token",
            "refresh_token": "cached_refresh",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "pg.access"
        }

        cached_wrapper = {
            "client_id": client_id,
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "jti": str(uuid4()),
            "token_response": cached_token_response
        }

        mock_code = MagicMock()
        mock_code.user_id = user_id
        mock_code.client_id = client_id
        mock_code.redirect_uri = original_redirect  # Original redirect
        mock_code.used = True
        mock_code.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

        mock_db = AsyncMock()

        async def mock_execute(stmt):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_code
            return mock_result

        mock_db.execute = mock_execute

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_wrapper))

        with patch(
            "backend.core.oauth_provider.services.token_service.redis_client",
            mock_redis
        ):
            result = await exchange_authorization_code(
                db=mock_db,
                code="test_auth_code",
                code_verifier="test_verifier",
                client_id=client_id,
                redirect_uri=different_redirect,  # Different redirect_uri
            )

        # Should return cached token (redirect_uri not re-validated on replay)
        assert result == cached_token_response

    @pytest.mark.asyncio
    async def test_pkce_verifier_mismatch_on_replay_returns_cached(self):
        """
        Test F: PKCE verifier mismatch on replay still returns cached token.

        SECURITY NOTE: This is CORRECT behavior. PKCE is a one-time gate on
        first exchange only. On the replay path (used=True), PKCE is not
        re-verified because:
        1. The code is already used=True (PKCE was verified on first exchange)
        2. The replay cache is keyed on code hash, gated on client_id only
        3. A different code_verifier cannot "replay" to a different client
           because client_id is still checked against the wrapper

        This test documents and locks in this behavior.
        """
        from backend.core.oauth_provider.services.token_service import exchange_authorization_code

        user_id = uuid4()
        client_id = "test-client"

        cached_token_response = {
            "access_token": "cached_token",
            "refresh_token": "cached_refresh",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "pg.access"
        }

        cached_wrapper = {
            "client_id": client_id,
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "jti": str(uuid4()),
            "token_response": cached_token_response
        }

        mock_code = MagicMock()
        mock_code.user_id = user_id
        mock_code.client_id = client_id
        mock_code.used = True
        mock_code.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

        mock_db = AsyncMock()

        async def mock_execute(stmt):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_code
            return mock_result

        mock_db.execute = mock_execute

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_wrapper))

        with patch(
            "backend.core.oauth_provider.services.token_service.redis_client",
            mock_redis
        ):
            result = await exchange_authorization_code(
                db=mock_db,
                code="test_auth_code",
                code_verifier="WRONG_VERIFIER_completely_invalid",  # Wrong verifier
                client_id=client_id,
                redirect_uri="https://example.com/callback",
            )

        # Should return cached token (PKCE not re-verified on replay)
        assert result == cached_token_response
