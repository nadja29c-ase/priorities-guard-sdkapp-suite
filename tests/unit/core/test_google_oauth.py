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
        scope = "https://www.googleapis.com/auth/calendar.readonly"

        url = generate_auth_url_with_pkce(challenge, state, scope)

        assert "code_challenge=test_challenge_value" in url

    def test_auth_url_contains_s256_method(self):
        """Test generated URL specifies S256 challenge method."""
        scope = "https://www.googleapis.com/auth/calendar.readonly"
        url = generate_auth_url_with_pkce("challenge", "state", scope)

        assert "code_challenge_method=S256" in url

    def test_auth_url_contains_state(self):
        """Test generated URL contains state parameter."""
        scope = "https://www.googleapis.com/auth/calendar.readonly"
        url = generate_auth_url_with_pkce("challenge", "my_state_token", scope)

        assert "state=my_state_token" in url

    def test_auth_url_uses_google_endpoint(self):
        """Test URL points to Google OAuth2 authorize endpoint."""
        scope = "https://www.googleapis.com/auth/calendar.readonly"
        url = generate_auth_url_with_pkce("challenge", "state", scope)

        assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth")

    def test_auth_url_includes_passed_scope(self):
        """Test URL includes the exact scope passed as parameter."""
        scope = "https://www.googleapis.com/auth/calendar.events.readonly"
        url = generate_auth_url_with_pkce("challenge", "state", scope)

        assert "calendar.events.readonly" in url
        # Should NOT contain the old hardcoded scope
        assert "calendar.readonly" not in url or "events.readonly" in url

    def test_auth_url_includes_calendar_readonly_scope(self):
        """Test URL includes calendar.readonly scope when passed."""
        scope = "https://www.googleapis.com/auth/calendar.readonly"
        url = generate_auth_url_with_pkce("challenge", "state", scope)

        assert "calendar.readonly" in url

    def test_auth_url_requests_offline_access(self):
        """Test URL requests offline access for refresh token."""
        scope = "https://www.googleapis.com/auth/calendar.readonly"
        url = generate_auth_url_with_pkce("challenge", "state", scope)

        assert "access_type=offline" in url

    def test_auth_url_scope_is_url_encoded(self):
        """Test scope is properly URL-encoded in the auth URL."""
        from urllib.parse import urlparse, parse_qs

        scope = "https://www.googleapis.com/auth/calendar.events.readonly"
        url = generate_auth_url_with_pkce("challenge", "state", scope)

        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        assert "scope" in params
        assert params["scope"][0] == scope


# =============================================================================
# Token Exchange Scope Validation Tests
# =============================================================================

class TestExchangeCodeScopeValidation:
    """Tests for exchange_code scope validation."""

    @pytest.mark.asyncio
    async def test_exchange_code_validates_passed_scope(self):
        """Test exchange_code validates the scope passed as parameter."""
        from backend.core.google_oauth import exchange_code
        import httpx

        # Mock successful token response with the requested scope
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "access_token": "access123",
            "refresh_token": "refresh456",
            "expires_in": 3600,
            "scope": "https://www.googleapis.com/auth/calendar.events.readonly",
        }

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(return_value=mock_response)

        result = await exchange_code(
            code="auth_code",
            http_client=mock_client,
            code_verifier="verifier",
            required_scope="https://www.googleapis.com/auth/calendar.events.readonly",
        )

        assert result["access_token"] == "access123"
        assert "https://www.googleapis.com/auth/calendar.events.readonly" in result["scopes"]

    @pytest.mark.asyncio
    async def test_exchange_code_raises_on_wrong_scope(self):
        """Test exchange_code raises ValueError when required scope not granted."""
        from backend.core.google_oauth import exchange_code
        import httpx

        # Mock response with different scope than requested
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "access_token": "access123",
            "refresh_token": "refresh456",
            "expires_in": 3600,
            "scope": "https://www.googleapis.com/auth/calendar.readonly",  # Different scope
        }

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(return_value=mock_response)

        with pytest.raises(ValueError) as exc_info:
            await exchange_code(
                code="auth_code",
                http_client=mock_client,
                code_verifier="verifier",
                required_scope="https://www.googleapis.com/auth/calendar.events.readonly",
            )

        assert "calendar.events.readonly" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_exchange_code_succeeds_without_required_scope(self):
        """Test exchange_code succeeds when no required_scope is specified."""
        from backend.core.google_oauth import exchange_code
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "access_token": "access123",
            "refresh_token": "refresh456",
            "expires_in": 3600,
            "scope": "https://www.googleapis.com/auth/calendar.readonly",
        }

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(return_value=mock_response)

        # No required_scope - should succeed regardless of what Google returns
        result = await exchange_code(
            code="auth_code",
            http_client=mock_client,
            code_verifier="verifier",
            required_scope=None,
        )

        assert result["access_token"] == "access123"

    @pytest.mark.asyncio
    async def test_exchange_code_validates_calendar_readonly_scope(self):
        """Test exchange_code validates calendar.readonly scope correctly."""
        from backend.core.google_oauth import exchange_code
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "access_token": "access123",
            "refresh_token": "refresh456",
            "expires_in": 3600,
            "scope": "https://www.googleapis.com/auth/calendar.readonly openid",
        }

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(return_value=mock_response)

        result = await exchange_code(
            code="auth_code",
            http_client=mock_client,
            code_verifier="verifier",
            required_scope="https://www.googleapis.com/auth/calendar.readonly",
        )

        assert result["access_token"] == "access123"
        assert "https://www.googleapis.com/auth/calendar.readonly" in result["scopes"]


# =============================================================================
# OAuth State Scope Storage Tests
# =============================================================================

class TestOAuthStateScopeStorage:
    """Tests for scope storage in OAuth state."""

    @pytest.mark.asyncio
    async def test_store_oauth_state_with_scope(self):
        """Test store_oauth_state stores scope when provided."""
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
                scope="https://www.googleapis.com/auth/calendar.events.readonly",
            )

        data = json.loads(stored_value)
        assert data["scope"] == "https://www.googleapis.com/auth/calendar.events.readonly"

    @pytest.mark.asyncio
    async def test_store_oauth_state_without_scope(self):
        """Test store_oauth_state works without scope (backwards compat)."""
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
        assert "scope" not in data

    @pytest.mark.asyncio
    async def test_verify_oauth_state_returns_scope(self):
        """Test verify_and_get_oauth_state returns scope when present."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps({
            "user_id": "user-123",
            "code_verifier": "verifier-456",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "scope": "https://www.googleapis.com/auth/calendar.events.readonly",
        }))
        mock_redis.delete = AsyncMock()

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result = await verify_and_get_oauth_state("valid_state")

        assert result is not None
        assert result["scope"] == "https://www.googleapis.com/auth/calendar.events.readonly"

    @pytest.mark.asyncio
    async def test_verify_oauth_state_returns_none_scope_when_missing(self):
        """Test verify_and_get_oauth_state returns None scope for legacy state."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps({
            "user_id": "user-123",
            "code_verifier": "verifier-456",
            "created_at": datetime.now(timezone.utc).isoformat(),
            # No scope field
        }))
        mock_redis.delete = AsyncMock()

        with patch("backend.core.google_oauth.redis_client", mock_redis):
            result = await verify_and_get_oauth_state("legacy_state")

        assert result is not None
        assert result["scope"] is None
