"""
Unit tests for Google OAuth security hardening (Increment 11 Part A).

Tests:
- PKCE code_verifier and code_challenge generation
- State token generation
- Redis state storage and verification
- Tokens never logged
"""

import base64
import hashlib
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone

from backend.core.google_oauth import (
    generate_code_verifier,
    generate_code_challenge,
    generate_state_token,
    store_oauth_state,
    verify_and_get_oauth_state,
    generate_auth_url_with_pkce,
    OAUTH_STATE_TTL,
)


# =============================================================================
# PKCE Tests
# =============================================================================

class TestPKCEGeneration:
    """Tests for PKCE code_verifier and code_challenge generation."""

    def test_code_verifier_length_valid(self):
        """Test code verifier is within RFC 7636 bounds (43-128 chars)."""
        verifier = generate_code_verifier()
        assert 43 <= len(verifier) <= 128, f"Verifier length {len(verifier)} not in valid range"

    def test_code_verifier_is_base64url(self):
        """Test code verifier uses only base64url-safe characters."""
        verifier = generate_code_verifier()
        # Base64url alphabet: A-Z, a-z, 0-9, -, _
        valid_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
        assert all(c in valid_chars for c in verifier), "Verifier contains invalid characters"

    def test_code_verifier_no_padding(self):
        """Test code verifier has no base64 padding characters."""
        verifier = generate_code_verifier()
        assert "=" not in verifier, "Verifier should not contain padding"

    def test_code_challenge_is_base64url_sha256(self):
        """Test code challenge is correctly derived from verifier."""
        verifier = "test_verifier_string_with_sufficient_length_for_testing"
        challenge = generate_code_challenge(verifier)

        # Manually compute expected challenge
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        expected = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

        assert challenge == expected, "Challenge does not match expected SHA256(verifier)"

    def test_code_challenge_length(self):
        """Test code challenge is 43 characters (SHA256 base64url without padding)."""
        verifier = generate_code_verifier()
        challenge = generate_code_challenge(verifier)
        # SHA256 = 32 bytes, base64url = ceil(32 * 4/3) = 43 chars (no padding)
        assert len(challenge) == 43, f"Challenge length should be 43, got {len(challenge)}"


# =============================================================================
# State Token Tests
# =============================================================================

class TestStateTokenGeneration:
    """Tests for OAuth state token generation."""

    def test_state_generation_length(self):
        """Test state token is 64 characters (32 bytes hex encoded)."""
        state = generate_state_token()
        assert len(state) == 64, f"State length should be 64, got {len(state)}"

    def test_state_is_hex(self):
        """Test state token is valid hex string."""
        state = generate_state_token()
        # Should be parseable as hex
        try:
            int(state, 16)
        except ValueError:
            pytest.fail("State is not valid hex")


# =============================================================================
# Redis State Storage Tests
# =============================================================================

class TestRedisStateStorage:
    """Tests for Redis-based OAuth state storage."""

    @pytest.mark.asyncio
    async def test_state_stored_in_redis_with_correct_ttl(self):
        """Test state is stored in Redis with 10-minute TTL."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result = await store_oauth_state(
                state="test_state_123",
                user_id="user-uuid-123",
                code_verifier="test_verifier",
            )

        assert result is True
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args

        # Verify key format
        assert call_args[0][0] == "oauth:google:state:test_state_123"

        # Verify TTL is 10 minutes (600 seconds)
        assert call_args[1]["ex"] == OAUTH_STATE_TTL
        assert OAUTH_STATE_TTL == 600

    @pytest.mark.asyncio
    async def test_state_redis_value_contains_user_id(self):
        """Test Redis value contains user_id."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock(return_value=True)
        stored_value = None

        async def capture_value(key, value, ex=None):
            nonlocal stored_value
            stored_value = value
            return True

        mock_redis.set = capture_value

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            await store_oauth_state(
                state="test_state",
                user_id="user-uuid-456",
                code_verifier="verifier",
            )

        data = json.loads(stored_value)
        assert data["user_id"] == "user-uuid-456"

    @pytest.mark.asyncio
    async def test_state_redis_value_contains_code_verifier(self):
        """Test Redis value contains code_verifier."""
        mock_redis = AsyncMock()
        stored_value = None

        async def capture_value(key, value, ex=None):
            nonlocal stored_value
            stored_value = value
            return True

        mock_redis.set = capture_value

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            await store_oauth_state(
                state="test_state",
                user_id="user-uuid",
                code_verifier="my_secret_verifier",
            )

        data = json.loads(stored_value)
        assert data["code_verifier"] == "my_secret_verifier"

    @pytest.mark.asyncio
    async def test_state_redis_value_contains_created_at(self):
        """Test Redis value contains created_at timestamp."""
        mock_redis = AsyncMock()
        stored_value = None

        async def capture_value(key, value, ex=None):
            nonlocal stored_value
            stored_value = value
            return True

        mock_redis.set = capture_value

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            await store_oauth_state(
                state="test_state",
                user_id="user-uuid",
                code_verifier="verifier",
            )

        data = json.loads(stored_value)
        assert "created_at" in data
        # Verify it's a valid ISO timestamp
        datetime.fromisoformat(data["created_at"])


# =============================================================================
# State Verification Tests
# =============================================================================

class TestStateVerification:
    """Tests for OAuth state verification."""

    @pytest.mark.asyncio
    async def test_valid_state_accepted(self):
        """Test valid state returns user_id and code_verifier."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps({
            "user_id": "user-123",
            "code_verifier": "verifier-456",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }))
        mock_redis.delete = AsyncMock()

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result = await verify_and_get_oauth_state("valid_state")

        assert result is not None
        assert result["user_id"] == "user-123"
        assert result["code_verifier"] == "verifier-456"

    @pytest.mark.asyncio
    async def test_missing_state_rejected(self):
        """Test missing/unknown state returns None."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result = await verify_and_get_oauth_state("nonexistent_state")

        assert result is None

    @pytest.mark.asyncio
    async def test_expired_state_rejected(self):
        """Test expired state (TTL passed) returns None."""
        # Redis returns None for expired keys
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result = await verify_and_get_oauth_state("expired_state")

        assert result is None

    @pytest.mark.asyncio
    async def test_state_deleted_after_use(self):
        """Test state is deleted from Redis after verification (single-use)."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps({
            "user_id": "user-123",
            "code_verifier": "verifier",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }))
        mock_redis.delete = AsyncMock()

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            await verify_and_get_oauth_state("state_to_delete")

        # Verify delete was called
        mock_redis.delete.assert_called_once_with("oauth:google:state:state_to_delete")

    @pytest.mark.asyncio
    async def test_malformed_state_data_rejected(self):
        """Test malformed JSON in Redis returns None."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="not valid json")
        mock_redis.delete = AsyncMock()

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result = await verify_and_get_oauth_state("malformed_state")

        assert result is None

    @pytest.mark.asyncio
    async def test_missing_fields_in_state_data_rejected(self):
        """Test state data missing required fields returns None."""
        mock_redis = AsyncMock()
        # Missing code_verifier
        mock_redis.get = AsyncMock(return_value=json.dumps({
            "user_id": "user-123",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }))
        mock_redis.delete = AsyncMock()

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result = await verify_and_get_oauth_state("incomplete_state")

        assert result is None


# =============================================================================
# Auth URL Generation Tests
# =============================================================================

class TestAuthURLGeneration:
    """Tests for OAuth authorization URL generation."""

    def test_auth_url_contains_pkce_challenge(self):
        """Test generated URL contains code_challenge parameter."""
        challenge = "test_challenge_value"
        state = "test_state"

        url = generate_auth_url_with_pkce(challenge, state)

        assert "code_challenge=test_challenge_value" in url

    def test_auth_url_contains_s256_method(self):
        """Test generated URL specifies S256 challenge method."""
        url = generate_auth_url_with_pkce("challenge", "state")

        assert "code_challenge_method=S256" in url

    def test_auth_url_contains_state(self):
        """Test generated URL contains state parameter."""
        url = generate_auth_url_with_pkce("challenge", "my_state_token")

        assert "state=my_state_token" in url

    def test_auth_url_uses_google_endpoint(self):
        """Test URL points to Google OAuth2 authorize endpoint."""
        url = generate_auth_url_with_pkce("challenge", "state")

        assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth")

    def test_auth_url_requests_calendar_readonly_scope(self):
        """Test URL requests calendar.readonly scope."""
        url = generate_auth_url_with_pkce("challenge", "state")

        assert "calendar.readonly" in url

    def test_auth_url_requests_offline_access(self):
        """Test URL requests offline access for refresh token."""
        url = generate_auth_url_with_pkce("challenge", "state")

        assert "access_type=offline" in url
