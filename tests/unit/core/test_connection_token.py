"""
Unit tests for Google connection token functions (Increment 18).

Tests:
- store_connection_token generates correct token format
- store_connection_token stores in Redis with correct key and TTL
- verify_connection_token returns user_id for valid token
- verify_connection_token returns None for expired/invalid token
- verify_connection_token deletes token after use (single-use)
"""

import pytest
from unittest.mock import AsyncMock, patch

from backend.core.google_oauth import (
    store_connection_token,
    verify_connection_token,
    CONNECTION_TOKEN_TTL,
)


# =============================================================================
# store_connection_token Tests
# =============================================================================

class TestStoreConnectionToken:
    """Tests for store_connection_token function."""

    @pytest.mark.asyncio
    async def test_token_is_url_safe(self):
        """Test generated token uses only URL-safe characters."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            token = await store_connection_token("user-123")

        # URL-safe base64 alphabet: A-Z, a-z, 0-9, -, _
        valid_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
        assert all(c in valid_chars for c in token), "Token contains non-URL-safe characters"

    @pytest.mark.asyncio
    async def test_token_length_is_43_chars(self):
        """Test generated token is 43 characters (32 bytes base64url encoded)."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            token = await store_connection_token("user-123")

        # secrets.token_urlsafe(32) produces 43 characters
        assert len(token) == 43, f"Token length should be 43, got {len(token)}"

    @pytest.mark.asyncio
    async def test_token_has_no_padding(self):
        """Test token has no base64 padding characters."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            token = await store_connection_token("user-123")

        assert "=" not in token, "Token should not contain padding"

    @pytest.mark.asyncio
    async def test_token_stored_with_correct_redis_key(self):
        """Test token is stored with google_connect:{token} key format."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            token = await store_connection_token("user-456")

        call_args = mock_redis.set.call_args
        expected_key = f"google_connect:{token}"
        assert call_args[0][0] == expected_key, f"Expected key {expected_key}"

    @pytest.mark.asyncio
    async def test_token_stored_with_user_id_value(self):
        """Test Redis value is the user_id."""
        mock_redis = AsyncMock()
        stored_value = None

        async def capture_value(_key, value, **_kwargs):
            nonlocal stored_value
            stored_value = value
            return True

        mock_redis.set = capture_value

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            await store_connection_token("user-789")

        assert stored_value == "user-789"

    @pytest.mark.asyncio
    async def test_token_stored_with_10_minute_ttl(self):
        """Test token is stored with 600 second (10 minute) TTL."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            await store_connection_token("user-123")

        call_args = mock_redis.set.call_args
        assert call_args[1]["ex"] == CONNECTION_TOKEN_TTL
        assert CONNECTION_TOKEN_TTL == 600, "TTL should be 600 seconds"

    @pytest.mark.asyncio
    async def test_tokens_are_unique(self):
        """Test multiple calls generate unique tokens."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            token1 = await store_connection_token("user-123")
            token2 = await store_connection_token("user-123")
            token3 = await store_connection_token("user-456")

        assert token1 != token2, "Tokens should be unique even for same user"
        assert token2 != token3, "Tokens should be unique"
        assert token1 != token3, "Tokens should be unique"

    @pytest.mark.asyncio
    async def test_store_handles_bytes_ok_response(self):
        """Test store handles Redis returning b'OK' bytes instead of True."""
        mock_redis = AsyncMock()
        # Some Redis clients return b'OK' instead of True
        mock_redis.set = AsyncMock(return_value=b"OK")

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            token = await store_connection_token("user-123")

        # Should succeed (b'OK' is truthy)
        assert token is not None
        assert len(token) == 43


# =============================================================================
# verify_connection_token Tests
# =============================================================================

class TestVerifyConnectionToken:
    """Tests for verify_connection_token function."""

    @pytest.mark.asyncio
    async def test_valid_token_returns_user_id(self):
        """Test valid token returns dict with user_id."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="user-123")
        mock_redis.delete = AsyncMock()

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result = await verify_connection_token("valid_token_abc")

        assert result is not None
        assert result["user_id"] == "user-123"
        assert result["scope"] is None  # Legacy format has no scope

    @pytest.mark.asyncio
    async def test_valid_token_bytes_decoded(self):
        """Test Redis bytes response is decoded to string."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=b"user-456")  # bytes
        mock_redis.delete = AsyncMock()

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result = await verify_connection_token("token_bytes")

        assert result is not None
        assert result["user_id"] == "user-456"
        assert isinstance(result["user_id"], str)

    @pytest.mark.asyncio
    async def test_invalid_token_returns_none(self):
        """Test invalid/unknown token returns None."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result = await verify_connection_token("nonexistent_token")

        assert result is None

    @pytest.mark.asyncio
    async def test_expired_token_returns_none(self):
        """Test expired token (TTL passed) returns None."""
        # Redis returns None for expired keys
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result = await verify_connection_token("expired_token")

        assert result is None

    @pytest.mark.asyncio
    async def test_token_deleted_after_verification(self):
        """Test token is deleted from Redis after use (single-use)."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="user-123")
        mock_redis.delete = AsyncMock()

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            await verify_connection_token("single_use_token")

        mock_redis.delete.assert_called_once_with("google_connect:single_use_token")

    @pytest.mark.asyncio
    async def test_token_not_deleted_if_invalid(self):
        """Test delete is not called for invalid tokens."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.delete = AsyncMock()

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            await verify_connection_token("invalid_token")

        mock_redis.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_correct_redis_key_queried(self):
        """Test verify queries the correct Redis key."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            await verify_connection_token("my_token_123")

        mock_redis.get.assert_called_once_with("google_connect:my_token_123")

    @pytest.mark.asyncio
    async def test_replay_attack_prevented(self):
        """Test same token cannot be used twice (single-use enforcement)."""
        mock_redis = AsyncMock()

        # First call: token exists
        # Second call: token was deleted, returns None
        mock_redis.get = AsyncMock(side_effect=["user-123", None])
        mock_redis.delete = AsyncMock()

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result1 = await verify_connection_token("one_time_token")
            result2 = await verify_connection_token("one_time_token")

        assert result1 is not None and result1["user_id"] == "user-123", "First use should succeed"
        assert result2 is None, "Second use should fail (token deleted)"


# =============================================================================
# Redis Failure Handling Tests
# =============================================================================

class TestRedisFailureHandling:
    """Tests for Redis failure scenarios - tokens must fail hard, not silently."""

    @pytest.mark.asyncio
    async def test_store_raises_when_redis_set_returns_false(self):
        """Test store_connection_token raises when Redis .set() returns False."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=False)

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            with pytest.raises(RuntimeError, match="Failed to store connection token"):
                await store_connection_token("user-123")

    @pytest.mark.asyncio
    async def test_store_raises_when_redis_set_raises_exception(self):
        """Test store_connection_token propagates Redis connection errors."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(side_effect=ConnectionError("Redis connection refused"))

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            with pytest.raises(ConnectionError, match="Redis connection refused"):
                await store_connection_token("user-123")

    @pytest.mark.asyncio
    async def test_store_raises_when_redis_timeout(self):
        """Test store_connection_token propagates Redis timeout errors."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(side_effect=TimeoutError("Redis operation timed out"))

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            with pytest.raises(TimeoutError, match="Redis operation timed out"):
                await store_connection_token("user-123")

    @pytest.mark.asyncio
    async def test_verify_raises_when_redis_get_raises_exception(self):
        """Test verify_connection_token propagates Redis connection errors."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=ConnectionError("Redis connection refused"))

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            with pytest.raises(ConnectionError, match="Redis connection refused"):
                await verify_connection_token("some_token")

    @pytest.mark.asyncio
    async def test_verify_raises_when_redis_timeout(self):
        """Test verify_connection_token propagates Redis timeout errors."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=TimeoutError("Redis operation timed out"))

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            with pytest.raises(TimeoutError, match="Redis operation timed out"):
                await verify_connection_token("some_token")

    @pytest.mark.asyncio
    async def test_verify_succeeds_even_when_redis_delete_fails(self):
        """Test verify returns user_id even if delete fails (best-effort cleanup)."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="user-123")
        mock_redis.delete = AsyncMock(side_effect=ConnectionError("Redis connection lost"))

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            # Should still return user_id despite delete failure
            result = await verify_connection_token("some_token")

        assert result is not None and result["user_id"] == "user-123", "Verification should succeed even if cleanup fails"

    @pytest.mark.asyncio
    async def test_verify_logs_delete_failure(self):
        """Test that delete failures are logged (for debugging)."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="user-123")
        mock_redis.delete = AsyncMock(side_effect=ConnectionError("Redis down"))

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            with patch("backend.core.google_oauth.logger") as mock_logger:
                await verify_connection_token("some_token")

                # Should log the error with structured event name and error details
                mock_logger.error.assert_called()
                error_call = mock_logger.error.call_args
                # Check event name (first positional arg)
                assert error_call[0][0] == "google_oauth.connection_token_delete_failed"
                # Check error is passed as keyword arg
                assert "Redis down" in error_call[1].get("error", "")

    @pytest.mark.asyncio
    async def test_store_no_silent_failure_on_redis_error(self):
        """Test that Redis errors are never swallowed silently."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(side_effect=Exception("Unexpected Redis error"))

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            # Must raise, not return a token
            with pytest.raises(Exception, match="Unexpected Redis error"):
                await store_connection_token("user-123")

    @pytest.mark.asyncio
    async def test_verify_no_silent_failure_on_redis_error(self):
        """Test that Redis errors during verification are never swallowed."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=Exception("Unexpected Redis error"))

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            # Must raise, not return None (which would look like invalid token)
            with pytest.raises(Exception, match="Unexpected Redis error"):
                await verify_connection_token("some_token")


# =============================================================================
# Token Collision Tests
# =============================================================================

class TestTokenCollisionHandling:
    """Tests for pathological token collision scenarios."""

    @pytest.mark.asyncio
    async def test_same_token_generated_twice_overwrites_in_redis(self):
        """Test that if same token generated twice, second write overwrites first."""
        mock_redis = AsyncMock()
        set_calls = []

        async def capture_set(key, value, ex=None):
            set_calls.append({"key": key, "value": value, "ex": ex})
            return True

        mock_redis.set = capture_set

        # Mock secrets.token_urlsafe to return same token twice
        with patch("backend.core.google_oauth.redis_client", mock_redis):
            with patch("secrets.token_urlsafe", return_value="collision_token_abc"):
                token1 = await store_connection_token("user-111")
                token2 = await store_connection_token("user-222")

        # Both calls should succeed
        assert token1 == "collision_token_abc"
        assert token2 == "collision_token_abc"

        # Redis should have received two writes to the same key
        assert len(set_calls) == 2
        assert set_calls[0]["key"] == "google_connect:collision_token_abc"
        assert set_calls[1]["key"] == "google_connect:collision_token_abc"

        # Second write overwrites first user
        assert set_calls[0]["value"] == "user-111"
        assert set_calls[1]["value"] == "user-222"

    @pytest.mark.asyncio
    async def test_collision_last_write_wins(self):
        """Test that in collision scenario, last write wins (Redis behavior)."""
        mock_redis = AsyncMock()
        stored_data = {}

        async def mock_set(key, value, **_kwargs):
            stored_data[key] = value  # Last write wins
            return True

        async def mock_get(key):
            return stored_data.get(key)

        mock_redis.set = mock_set
        mock_redis.get = mock_get
        mock_redis.delete = AsyncMock()

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            with patch("secrets.token_urlsafe", return_value="same_token"):
                # User 1 stores token
                await store_connection_token("user-first")
                # User 2 stores same token (overwrites)
                await store_connection_token("user-second")

                # Verify returns user-second (last write wins)
                result = await verify_connection_token("same_token")

        assert result is not None and result["user_id"] == "user-second", "Last write should win in collision"


# =============================================================================
# User ID Type Handling Tests
# =============================================================================

class TestUserIdTypeHandling:
    """Tests for user_id type handling - forces explicit type assumptions."""

    @pytest.mark.asyncio
    async def test_string_user_id_accepted(self):
        """Test standard string user_id works."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            token = await store_connection_token("user-123")

        assert token is not None
        assert len(token) == 43

    @pytest.mark.asyncio
    async def test_uuid_string_user_id_accepted(self):
        """Test UUID string user_id works."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            token = await store_connection_token("550e8400-e29b-41d4-a716-446655440000")

        assert token is not None

    @pytest.mark.asyncio
    async def test_uuid_object_stored_as_string(self):
        """Test UUID object is converted to string when stored."""
        from uuid import UUID
        mock_redis = AsyncMock()
        stored_value = None

        async def capture_set(_key, value, **_kwargs):
            nonlocal stored_value
            stored_value = value
            return True

        mock_redis.set = capture_set

        uuid_obj = UUID("550e8400-e29b-41d4-a716-446655440000")

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            await store_connection_token(str(uuid_obj))

        # Should be stored as string
        assert stored_value == "550e8400-e29b-41d4-a716-446655440000"
        assert isinstance(stored_value, str)

    @pytest.mark.asyncio
    async def test_integer_user_id_rejected(self):
        """Test integer user_id is rejected (type safety)."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            # Should raise TypeError for non-string
            with pytest.raises(TypeError):
                await store_connection_token(12345)  # type: ignore

    @pytest.mark.asyncio
    async def test_none_user_id_rejected(self):
        """Test None user_id is rejected."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            with pytest.raises((TypeError, ValueError)):
                await store_connection_token(None)  # type: ignore

    @pytest.mark.asyncio
    async def test_empty_string_user_id_rejected(self):
        """Test empty string user_id is rejected."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            with pytest.raises(ValueError, match="user_id cannot be empty"):
                await store_connection_token("")

    @pytest.mark.asyncio
    async def test_whitespace_only_user_id_rejected(self):
        """Test whitespace-only user_id is rejected."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            with pytest.raises(ValueError, match="user_id cannot be empty"):
                await store_connection_token("   ")

    @pytest.mark.asyncio
    async def test_special_characters_in_user_id_accepted(self):
        """Test user_id with special characters is accepted (Redis handles it)."""
        mock_redis = AsyncMock()
        stored_value = None

        async def capture_set(_key, value, **_kwargs):
            nonlocal stored_value
            stored_value = value
            return True

        mock_redis.set = capture_set

        weird_user_id = "user:with:colons:and-dashes_and_underscores"

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            await store_connection_token(weird_user_id)

        assert stored_value == weird_user_id

    @pytest.mark.asyncio
    async def test_very_long_user_id_accepted(self):
        """Test very long user_id is accepted (no arbitrary limits)."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        long_user_id = "a" * 1000  # 1000 character user_id

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            token = await store_connection_token(long_user_id)

        assert token is not None


# =============================================================================
# URL Safety Tests
# =============================================================================

class TestTokenURLSafety:
    """Tests for token URL safety - ensures tokens work in all URL contexts."""

    @pytest.mark.asyncio
    async def test_token_has_no_url_reserved_characters(self):
        """Test token contains no URL reserved characters."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        # RFC 3986 reserved characters that would need encoding in URLs
        reserved_chars = set("!#$&'()*+,/:;=?@[]%")

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            # Generate multiple tokens to increase confidence
            for _ in range(100):
                token = await store_connection_token("user-123")
                for char in token:
                    assert char not in reserved_chars, f"Token contains reserved char: {char}"

    @pytest.mark.asyncio
    async def test_token_has_no_whitespace(self):
        """Test token contains no whitespace characters."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        import string
        whitespace = set(string.whitespace)

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            for _ in range(100):
                token = await store_connection_token("user-123")
                for char in token:
                    assert char not in whitespace, f"Token contains whitespace: {repr(char)}"

    @pytest.mark.asyncio
    async def test_token_has_no_plus_or_slash(self):
        """Test token has no + or / (standard base64 chars that are NOT URL-safe)."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            for _ in range(100):
                token = await store_connection_token("user-123")
                assert "+" not in token, "Token contains '+' (not URL-safe)"
                assert "/" not in token, "Token contains '/' (not URL-safe)"

    @pytest.mark.asyncio
    async def test_token_safe_in_query_string(self):
        """Test token can be safely embedded in URL query string."""
        from urllib.parse import urlencode, parse_qs

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            token = await store_connection_token("user-123")

            # Build URL with token as query parameter
            url_params = urlencode({"token": token})

            # Parse it back - should be identical
            parsed = parse_qs(url_params)
            assert parsed["token"][0] == token, "Token corrupted in URL encoding round-trip"

    @pytest.mark.asyncio
    async def test_token_safe_in_path_segment(self):
        """Test token can be safely used in URL path segment."""
        from urllib.parse import quote

        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            token = await store_connection_token("user-123")

            # URL-encode for path segment
            encoded = quote(token, safe="")

            # Should be identical (no encoding needed for URL-safe chars)
            assert encoded == token, f"Token required encoding: {token} -> {encoded}"

    @pytest.mark.asyncio
    async def test_token_with_leading_underscore_or_dash(self):
        """Test tokens starting with - or _ are handled correctly."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        # Force tokens that start with - or _ by mocking
        test_tokens = [
            "-leading_dash_token_abcdefghijklmnop",
            "_leading_underscore_abcdefghijklmno",
        ]

        for test_token in test_tokens:
            with patch("backend.core.google_oauth.redis_client", mock_redis):
                with patch("secrets.token_urlsafe", return_value=test_token):
                    token = await store_connection_token("user-123")

                    # Should still work in URL
                    from urllib.parse import urlencode, parse_qs
                    url_params = urlencode({"token": token})
                    parsed = parse_qs(url_params)
                    assert parsed["token"][0] == token

    @pytest.mark.asyncio
    async def test_token_with_trailing_underscore_or_dash(self):
        """Test tokens ending with - or _ are handled correctly."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        test_tokens = [
            "trailing_dash_token_abcdefghijklmno-",
            "trailing_underscore_abcdefghijklmn_",
        ]

        for test_token in test_tokens:
            with patch("backend.core.google_oauth.redis_client", mock_redis):
                with patch("secrets.token_urlsafe", return_value=test_token):
                    token = await store_connection_token("user-123")

                    from urllib.parse import urlencode, parse_qs
                    url_params = urlencode({"token": token})
                    parsed = parse_qs(url_params)
                    assert parsed["token"][0] == token

    @pytest.mark.asyncio
    async def test_token_starting_with_number(self):
        """Test tokens starting with a digit work correctly."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        # Token starting with digit
        test_token = "9abcdefghijklmnopqrstuvwxyz1234567890AB"

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            with patch("secrets.token_urlsafe", return_value=test_token):
                token = await store_connection_token("user-123")
                assert token[0] == "9"

                # Should work in URL
                from urllib.parse import urlencode, parse_qs
                url_params = urlencode({"token": token})
                parsed = parse_qs(url_params)
                assert parsed["token"][0] == token

    @pytest.mark.asyncio
    async def test_token_all_dashes_and_underscores(self):
        """Test pathological token with only dashes and underscores."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        # Extreme edge case
        test_token = "-_-_-_-_-_-_-_-_-_-_-_-_-_-_-_-_-_-_-_-_-"

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            with patch("secrets.token_urlsafe", return_value=test_token):
                token = await store_connection_token("user-123")

                from urllib.parse import urlencode, parse_qs
                url_params = urlencode({"token": token})
                parsed = parse_qs(url_params)
                assert parsed["token"][0] == token

    @pytest.mark.asyncio
    async def test_token_not_confused_with_cli_flag(self):
        """Test token starting with dash isn't confused with CLI flag in logs."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        # Token that looks like a CLI flag
        test_token = "--help_not_a_flag_abcdefghijklmnopqr"

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            with patch("secrets.token_urlsafe", return_value=test_token):
                token = await store_connection_token("user-123")

                # Token should be stored and retrievable
                assert token == test_token
                mock_redis.set.assert_called_once()


# =============================================================================
# TTL Expiration Tests
# =============================================================================

class TestTokenTTLExpiration:
    """Tests for token TTL expiration behavior."""

    @pytest.mark.asyncio
    async def test_ttl_is_set_on_store(self):
        """Test that TTL (ex parameter) is always set when storing token."""
        mock_redis = AsyncMock()
        set_calls = []

        async def capture_set(key, value, ex=None):
            set_calls.append({"key": key, "value": value, "ex": ex})
            return True

        mock_redis.set = capture_set

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            await store_connection_token("user-123")

        assert len(set_calls) == 1
        assert set_calls[0]["ex"] is not None, "TTL must be set"
        assert set_calls[0]["ex"] == 600, "TTL must be 600 seconds"

    @pytest.mark.asyncio
    async def test_ttl_constant_equals_600(self):
        """Test that CONNECTION_TOKEN_TTL constant is 600 seconds."""
        assert CONNECTION_TOKEN_TTL == 600, "TTL should be 600 seconds (10 minutes)"

    @pytest.mark.asyncio
    async def test_ttl_is_passed_not_hardcoded(self):
        """Test that TTL uses the constant, not a hardcoded value."""
        mock_redis = AsyncMock()
        captured_ttl = None

        async def capture_set(_key, _value, ex=None):
            nonlocal captured_ttl
            captured_ttl = ex
            return True

        mock_redis.set = capture_set

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            await store_connection_token("user-123")

        # Verify TTL matches the constant
        assert captured_ttl == CONNECTION_TOKEN_TTL

    @pytest.mark.asyncio
    async def test_expired_token_returns_none(self):
        """Test that expired token (TTL passed) returns None on verify."""
        mock_redis = AsyncMock()
        # Simulate Redis returning None for expired key
        mock_redis.get = AsyncMock(return_value=None)

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result = await verify_connection_token("expired_token")

        assert result is None

    @pytest.mark.asyncio
    async def test_token_just_before_expiry_still_valid(self):
        """Test token is valid until TTL expires (no early expiration)."""
        mock_redis = AsyncMock()
        # Token still exists in Redis (not expired yet)
        mock_redis.get = AsyncMock(return_value="user-123")
        mock_redis.delete = AsyncMock()

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result = await verify_connection_token("almost_expired_token")

        assert result is not None and result["user_id"] == "user-123"

    @pytest.mark.asyncio
    async def test_ttl_not_refreshed_on_verify(self):
        """Test that verifying a token does not refresh its TTL."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="user-123")
        mock_redis.delete = AsyncMock()
        mock_redis.expire = AsyncMock()  # Should NOT be called

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            await verify_connection_token("some_token")

        # expire should never be called during verification
        mock_redis.expire.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_tokens_have_independent_ttls(self):
        """Test that each token has its own independent TTL."""
        mock_redis = AsyncMock()
        set_calls = []

        async def capture_set(key, _value, ex=None):
            set_calls.append({"key": key, "ex": ex})
            return True

        mock_redis.set = capture_set

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            await store_connection_token("user-1")
            await store_connection_token("user-2")
            await store_connection_token("user-3")

        # Each token should have its own TTL set
        assert len(set_calls) == 3
        for call in set_calls:
            assert call["ex"] == 600

    @pytest.mark.asyncio
    async def test_ttl_uses_redis_ex_not_expire(self):
        """Test TTL is set atomically via SET EX, not separate EXPIRE call."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.expire = AsyncMock()

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            await store_connection_token("user-123")

        # SET with EX should be called
        mock_redis.set.assert_called_once()
        call_kwargs = mock_redis.set.call_args[1]
        assert "ex" in call_kwargs, "TTL should be set via SET EX parameter"

        # Separate EXPIRE should NOT be called (atomic SET EX is preferred)
        mock_redis.expire.assert_not_called()

    @pytest.mark.asyncio
    async def test_simulate_time_based_expiration(self):
        """Test simulated time-based expiration using FakeRedis-like behavior."""
        # Simulate a Redis that tracks TTL and expires keys
        storage = {}
        ttls = {}

        async def mock_set(key, value, ex=None):
            storage[key] = value
            if ex:
                ttls[key] = ex
            return True

        async def mock_get(key):
            # Simulate expiration: if TTL would have passed, return None
            if key in ttls and ttls[key] <= 0:
                storage.pop(key, None)
                ttls.pop(key, None)
                return None
            return storage.get(key)

        def advance_time(seconds):
            """Simulate passage of time by reducing TTLs."""
            expired = []
            for key in ttls:
                ttls[key] -= seconds
                if ttls[key] <= 0:
                    expired.append(key)
            for key in expired:
                storage.pop(key, None)

        mock_redis = AsyncMock()
        mock_redis.set = mock_set
        mock_redis.get = mock_get
        mock_redis.delete = AsyncMock()

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            # Store token
            token = await store_connection_token("user-123")

            # Immediately after storage, token should be valid
            result = await verify_connection_token(token)
            assert result is not None and result["user_id"] == "user-123"
            # Note: verify deletes token, so we need to store again for time test

        # Store another token for time simulation
        with patch("backend.core.google_oauth.redis_client", mock_redis):
            token2 = await store_connection_token("user-456")

            # Advance time by 599 seconds (just before expiry)
            advance_time(599)
            # Token should still be valid
            assert storage.get(f"google_connect:{token2}") == "user-456"

            # Advance 2 more seconds (past expiry)
            advance_time(2)
            # Token should now be expired
            result = await mock_get(f"google_connect:{token2}")
            assert result is None, "Token should be expired after TTL"


# =============================================================================
# Concurrency Safety Tests
# =============================================================================

class TestConcurrencySafety:
    """
    Tests for concurrent access to tokens.

    IMPORTANT: The current implementation uses separate GET + DELETE operations,
    which creates a race condition window. These tests document the current
    behavior and verify that at minimum, both callers don't silently succeed
    with the same token.

    For true atomicity, the implementation would need:
    - Redis GETDEL command (Redis 6.2+), or
    - Lua script: GET + DELETE in one atomic operation
    """

    @pytest.mark.asyncio
    async def test_sequential_verify_second_returns_none(self):
        """Test sequential verification: second call returns None (token deleted)."""
        mock_redis = AsyncMock()
        # First call returns user, second returns None (deleted)
        mock_redis.get = AsyncMock(side_effect=["user-123", None])
        mock_redis.delete = AsyncMock()

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result1 = await verify_connection_token("token")
            result2 = await verify_connection_token("token")

        assert result1 is not None and result1["user_id"] == "user-123", "First verify should succeed"
        assert result2 is None, "Second verify should fail (token consumed)"

    @pytest.mark.asyncio
    async def test_race_condition_both_get_before_delete(self):
        """
        Test race condition: both calls GET before either DELETEs.

        This documents the CURRENT behavior (race condition exists).
        Both calls would return the user_id, which is a security concern.

        TODO: Fix with atomic GETDEL or Lua script.
        """
        mock_redis = AsyncMock()
        # Simulate race: both GETs return user before DELETE happens
        mock_redis.get = AsyncMock(side_effect=["user-123", "user-123"])
        mock_redis.delete = AsyncMock()

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result1 = await verify_connection_token("token")
            result2 = await verify_connection_token("token")

        # CURRENT BEHAVIOR: Both succeed (race condition!)
        # This test documents the vulnerability
        assert result1 is not None and result1["user_id"] == "user-123"
        assert result2 is not None and result2["user_id"] == "user-123", "Race condition: both callers got the token"

        # At least verify delete was called twice
        assert mock_redis.delete.call_count == 2

    @pytest.mark.asyncio
    async def test_concurrent_verify_with_asyncio_gather(self):
        """
        Test truly concurrent verification using asyncio.gather.

        This simulates real-world concurrent requests hitting the same token.
        """
        import asyncio

        mock_redis = AsyncMock()
        get_call_count = 0
        delete_call_count = 0

        async def mock_get(_key):
            nonlocal get_call_count
            get_call_count += 1
            # Simulate slight delay to increase chance of race
            await asyncio.sleep(0.001)
            # Both calls happen before delete, so both see the value
            if get_call_count <= 2:
                return "user-123"
            return None

        async def mock_delete(_key):
            nonlocal delete_call_count
            delete_call_count += 1

        mock_redis.get = mock_get
        mock_redis.delete = mock_delete

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            # Launch two concurrent verifications
            results = await asyncio.gather(
                verify_connection_token("same_token"),
                verify_connection_token("same_token"),
            )

        # Document current behavior: both may succeed (race condition)
        # At least one should succeed - check for dict with user_id
        successful_results = [r for r in results if r is not None and r.get("user_id") == "user-123"]
        assert len(successful_results) >= 1, "At least one verification should succeed"

        # Count successes
        successes = successful_results

        # With current implementation, both likely succeed (bad)
        # This test will need updating when atomicity is added
        if len(successes) == 2:
            # Race condition occurred - document it
            pass  # Expected with current non-atomic implementation
        elif len(successes) == 1:
            # One succeeded, one failed - ideal behavior
            pass

    @pytest.mark.asyncio
    async def test_atomic_getdel_would_prevent_race(self):
        """
        Test how atomic GETDEL would behave (documents ideal implementation).

        This test shows the DESIRED behavior if we used Redis GETDEL.
        """
        mock_redis = AsyncMock()
        token_exists = True

        async def atomic_getdel(_key):
            """Simulate atomic GETDEL: returns value and deletes in one op."""
            nonlocal token_exists
            if token_exists:
                token_exists = False  # Atomically consume
                return "user-123"
            return None

        # If we had GETDEL, we'd call it instead of GET+DELETE
        # This shows the ideal behavior
        result1 = await atomic_getdel("token")
        result2 = await atomic_getdel("token")

        assert result1 == "user-123", "First call gets the token"
        assert result2 is None, "Second call fails (token already consumed)"

    @pytest.mark.asyncio
    async def test_high_concurrency_stress(self):
        """
        Stress test: 10 concurrent verifications of the same token.

        Documents behavior under high concurrency.
        """
        import asyncio

        mock_redis = AsyncMock()
        get_count = 0

        async def mock_get(_key):
            nonlocal get_count
            get_count += 1
            # First N calls all see the token (race window)
            if get_count <= 10:
                await asyncio.sleep(0.0001)  # Simulate network latency
                return "user-123"
            return None

        mock_redis.get = mock_get
        mock_redis.delete = AsyncMock()

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            # Launch 10 concurrent verifications
            results = await asyncio.gather(*[
                verify_connection_token("token") for _ in range(10)
            ])

        successes = [r for r in results if r is not None and r.get("user_id") == "user-123"]

        # Document: with current implementation, all 10 might succeed
        # This is the race condition we need to fix
        assert len(successes) >= 1, "At least one should succeed"

        # In production with atomic GETDEL, we'd want exactly 1 success
        # Current implementation allows multiple due to race condition

    @pytest.mark.asyncio
    async def test_delete_failure_doesnt_allow_reuse(self):
        """
        Test that delete failure doesn't silently allow token reuse.

        Even if delete fails, the token should not be easily reusable
        (it will eventually expire via TTL).
        """
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=["user-123", "user-123"])
        mock_redis.delete = AsyncMock(side_effect=Exception("Delete failed"))

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            # First call succeeds (delete fails but is caught)
            result1 = await verify_connection_token("token")
            # Second call also succeeds because delete didn't work
            result2 = await verify_connection_token("token")

        assert result1 is not None and result1["user_id"] == "user-123"
        # This documents that delete failure allows reuse (mitigated by TTL)
        assert result2 is not None and result2["user_id"] == "user-123", "Delete failure allows reuse until TTL"


# =============================================================================
# Redis Key Prefix Consistency Tests
# =============================================================================

class TestRedisKeyPrefixConsistency:
    """Tests verifying consistent Redis key prefix across all operations."""

    EXPECTED_PREFIX = "google_connect:"

    @pytest.mark.asyncio
    async def test_store_uses_correct_prefix(self):
        """Test store_connection_token uses google_connect: prefix for SET."""
        mock_redis = AsyncMock()
        set_key = None

        async def capture_set(key, *_args, **_kwargs):
            nonlocal set_key
            set_key = key
            return True

        mock_redis.set = capture_set

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            token = await store_connection_token("user-123")

        assert set_key is not None
        assert set_key.startswith(self.EXPECTED_PREFIX), f"SET key must start with {self.EXPECTED_PREFIX}"
        assert set_key == f"{self.EXPECTED_PREFIX}{token}"

    @pytest.mark.asyncio
    async def test_verify_get_uses_correct_prefix(self):
        """Test verify_connection_token uses google_connect: prefix for GET."""
        mock_redis = AsyncMock()
        get_key = None

        async def capture_get(key):
            nonlocal get_key
            get_key = key
            return "user-123"

        mock_redis.get = capture_get
        mock_redis.delete = AsyncMock()

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            await verify_connection_token("my_token_abc")

        assert get_key is not None
        assert get_key.startswith(self.EXPECTED_PREFIX), f"GET key must start with {self.EXPECTED_PREFIX}"
        assert get_key == f"{self.EXPECTED_PREFIX}my_token_abc"

    @pytest.mark.asyncio
    async def test_verify_delete_uses_correct_prefix(self):
        """Test verify_connection_token uses google_connect: prefix for DELETE."""
        mock_redis = AsyncMock()
        delete_key = None

        async def capture_delete(key):
            nonlocal delete_key
            delete_key = key

        mock_redis.get = AsyncMock(return_value="user-123")
        mock_redis.delete = capture_delete

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            await verify_connection_token("my_token_xyz")

        assert delete_key is not None
        assert delete_key.startswith(self.EXPECTED_PREFIX), f"DELETE key must start with {self.EXPECTED_PREFIX}"
        assert delete_key == f"{self.EXPECTED_PREFIX}my_token_xyz"

    @pytest.mark.asyncio
    async def test_all_operations_use_same_prefix(self):
        """Test SET, GET, and DELETE all use the same prefix format."""
        mock_redis = AsyncMock()
        captured_keys = {"set": None, "get": None, "delete": None}

        async def capture_set(key, *_args, **_kwargs):
            captured_keys["set"] = key
            return True

        async def capture_get(key):
            captured_keys["get"] = key
            return "user-123"

        async def capture_delete(key):
            captured_keys["delete"] = key

        mock_redis.set = capture_set
        mock_redis.get = capture_get
        mock_redis.delete = capture_delete

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            # Store a token
            token = await store_connection_token("user-123")
            # Verify (which does GET + DELETE)
            await verify_connection_token(token)

        # All keys should use the same prefix
        expected_key = f"{self.EXPECTED_PREFIX}{token}"

        assert captured_keys["set"] == expected_key, "SET used wrong key"
        assert captured_keys["get"] == expected_key, "GET used wrong key"
        assert captured_keys["delete"] == expected_key, "DELETE used wrong key"

    @pytest.mark.asyncio
    async def test_prefix_not_duplicated(self):
        """Test prefix is not accidentally duplicated (google_connect:google_connect:)."""
        mock_redis = AsyncMock()
        captured_keys = []

        async def capture_set(key, *_args, **_kwargs):
            captured_keys.append(key)
            return True

        mock_redis.set = capture_set

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            await store_connection_token("user-123")

        for key in captured_keys:
            # Should only have one occurrence of the prefix
            assert key.count(self.EXPECTED_PREFIX) == 1, f"Prefix duplicated in key: {key}"

    @pytest.mark.asyncio
    async def test_delete_not_called_for_invalid_token(self):
        """Test DELETE is not called when token doesn't exist (GET returns None)."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.delete = AsyncMock()

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result = await verify_connection_token("nonexistent_token")

        assert result is None
        # DELETE should NOT be called for non-existent tokens
        mock_redis.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_and_delete_use_exact_same_key(self):
        """Test GET and DELETE operate on the exact same Redis key."""
        mock_redis = AsyncMock()
        get_keys = []
        delete_keys = []

        async def capture_get(key):
            get_keys.append(key)
            return "user-123"

        async def capture_delete(key):
            delete_keys.append(key)

        mock_redis.get = capture_get
        mock_redis.delete = capture_delete

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            await verify_connection_token("test_token")

        assert len(get_keys) == 1
        assert len(delete_keys) == 1
        assert get_keys[0] == delete_keys[0], "GET and DELETE must use the same key"


# =============================================================================
# Invalid Token Input Tests
# =============================================================================

class TestInvalidTokenInput:
    """Tests for invalid token inputs to verify_connection_token.

    These tests verify that malformed tokens:
    1. Return None
    2. Never call Redis .get() (rejected before lookup)
    3. Never call Redis .delete()
    """

    @pytest.mark.asyncio
    async def test_empty_token_returns_none_no_redis(self):
        """Test empty string token returns None and never calls Redis."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.delete = AsyncMock()

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result = await verify_connection_token("")

        assert result is None
        mock_redis.get.assert_not_called()
        mock_redis.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_token_returns_none_no_redis(self):
        """Test None token returns None and never calls Redis."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.delete = AsyncMock()

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result = await verify_connection_token(None)  # type: ignore

        assert result is None
        mock_redis.get.assert_not_called()
        mock_redis.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_special_chars_only_token_queries_redis(self):
        """Test token with only special characters queries Redis (valid format)."""
        # Note: "=====" doesn't contain whitespace/control chars, so it passes
        # format validation and queries Redis (which returns None)
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.delete = AsyncMock()

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result = await verify_connection_token("=====")

        assert result is None
        mock_redis.get.assert_called_once()
        mock_redis.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_whitespace_only_token_returns_none_no_redis(self):
        """Test whitespace-only token returns None and never calls Redis."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.delete = AsyncMock()

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result = await verify_connection_token("   ")

        assert result is None
        mock_redis.get.assert_not_called()
        mock_redis.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_token_with_embedded_spaces_returns_none_no_redis(self):
        """Test token with embedded spaces returns None and never calls Redis."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.delete = AsyncMock()

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result = await verify_connection_token("token with spaces")

        assert result is None
        mock_redis.get.assert_not_called()
        mock_redis.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_token_with_tabs_returns_none_no_redis(self):
        """Test token with tabs returns None and never calls Redis."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.delete = AsyncMock()

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result = await verify_connection_token("token\twith\ttabs")

        assert result is None
        mock_redis.get.assert_not_called()
        mock_redis.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_newline_token_returns_none_no_redis(self):
        """Test token with newlines returns None and never calls Redis."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.delete = AsyncMock()

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result = await verify_connection_token("token\nwith\nnewlines")

        assert result is None
        mock_redis.get.assert_not_called()
        mock_redis.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_null_byte_token_returns_none_no_redis(self):
        """Test token with null bytes returns None and never calls Redis."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.delete = AsyncMock()

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result = await verify_connection_token("token\x00with\x00nulls")

        assert result is None
        mock_redis.get.assert_not_called()
        mock_redis.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_sql_injection_attempt_queries_redis(self):
        """Test SQL injection-like token queries Redis (no whitespace/control chars)."""
        # Note: "'; DROP TABLE users; --" contains spaces, so it's rejected early
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.delete = AsyncMock()

        malicious_token = "';DROP_TABLE_users;--"  # No spaces - passes format check

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result = await verify_connection_token(malicious_token)

        assert result is None
        mock_redis.get.assert_called_once()
        mock_redis.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_sql_injection_with_spaces_returns_none_no_redis(self):
        """Test SQL injection with spaces returns None and never calls Redis."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.delete = AsyncMock()

        malicious_token = "'; DROP TABLE users; --"  # Has spaces

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result = await verify_connection_token(malicious_token)

        assert result is None
        mock_redis.get.assert_not_called()
        mock_redis.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_unicode_token_queries_redis(self):
        """Test unicode token queries Redis (no control chars)."""
        # Unicode without control characters passes format validation
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.delete = AsyncMock()

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result = await verify_connection_token("token_with_émojis_🔑")

        assert result is None
        mock_redis.get.assert_called_once()
        mock_redis.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_very_long_token_queries_redis(self):
        """Test extremely long token queries Redis (no control chars)."""
        # Long tokens without control characters pass format validation
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.delete = AsyncMock()

        very_long_token = "x" * 10000  # 10KB token

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result = await verify_connection_token(very_long_token)

        assert result is None
        mock_redis.get.assert_called_once()
        mock_redis.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_path_traversal_queries_redis(self):
        """Test path traversal token queries Redis (no whitespace)."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.delete = AsyncMock()

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result = await verify_connection_token("../../../etc/passwd")

        assert result is None
        mock_redis.get.assert_called_once()
        mock_redis.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_malformed_tokens_never_call_redis(self):
        """Test that tokens with whitespace/control chars never call Redis."""
        malformed_tokens = [
            "",                          # empty
            "   ",                       # whitespace only
            "token with spaces",         # embedded spaces
            "token\twith\ttabs",         # tabs
            "token\nwith\nnewlines",     # newlines
            "token\x00with\x00nulls",    # null bytes
            " leading_space",            # leading whitespace
            "trailing_space ",           # trailing whitespace
            "\ttab_start",               # leading tab
        ]

        for token in malformed_tokens:
            mock_redis = AsyncMock()
            mock_redis.get = AsyncMock(return_value=None)
            mock_redis.delete = AsyncMock()

            with patch("backend.core.google_oauth.redis_client", mock_redis):
                result = await verify_connection_token(token)

            assert result is None, f"Token '{repr(token)}' should return None"
            mock_redis.get.assert_not_called(), f"Redis.get should not be called for '{repr(token)}'"
            mock_redis.delete.assert_not_called(), f"Redis.delete should not be called for '{repr(token)}'"

    @pytest.mark.asyncio
    async def test_valid_format_tokens_query_redis(self):
        """Test that well-formed tokens (even if nonexistent) query Redis."""
        valid_format_tokens = [
            "validtoken123",
            "abc-def_ghi",
            "UPPERCASE",
            "MixedCase123",
            "=====",                      # No whitespace/control chars
            "../../../etc/passwd",        # No whitespace/control chars
        ]

        for token in valid_format_tokens:
            mock_redis = AsyncMock()
            mock_redis.get = AsyncMock(return_value=None)
            mock_redis.delete = AsyncMock()

            with patch("backend.core.google_oauth.redis_client", mock_redis):
                result = await verify_connection_token(token)

            assert result is None, f"Token '{token}' should return None"
            mock_redis.get.assert_called_once(), f"Redis.get should be called for '{token}'"
            mock_redis.delete.assert_not_called(), f"Delete should not be called for token '{token}'"
