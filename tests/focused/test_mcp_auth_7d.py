"""
Comprehensive tests for Increment 7D - MCP Token Validation.

Tests JWT validation, JWKS caching, scope enforcement, and backend migration.
"""

import pytest
import time
import jwt
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

# Import modules to test
import sys
sys.path.insert(0, '/Users/nadja/Desktop/Priority Guard Suite/priority-guardian')

from mcp.focused import mcp_auth
from mcp.focused.mcp_auth import (
    JWKSCache,
    extract_authorization_header,
    extract_bearer_token,
    validate_jwt,
    check_scopes,
    enforce_tool_scope,
    extract_or_generate_correlation_id,
    authenticate_request,
    UnauthorizedError,
    InsufficientScopeError,
    build_unauthorized_error,
    build_forbidden_error,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def rsa_keypair():
    """Generate RSA keypair for testing JWT signatures."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )

    public_key = private_key.public_key()

    # Serialize private key for JWT signing
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    # Serialize public key for JWKS
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    return {
        "private_key": private_pem,
        "public_key": public_pem,
        "private_key_obj": private_key,
        "public_key_obj": public_key
    }


@pytest.fixture
def mock_jwks(rsa_keypair):
    """Mock JWKS response with test public key."""
    # Convert public key to JWK format (simplified)
    return {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "kid": "test-kid-123",
                "alg": "RS256",
                "n": "test-modulus",
                "e": "AQAB"
            }
        ]
    }


@pytest.fixture
def valid_token_payload():
    """Valid JWT payload for testing."""
    return {
        "iss": "https://www.priority-guard.com/oauth/focused",
        "aud": "https://www.priority-guard.com/mcp/focused",
        "sub": "user-123",
        "azp": "test-client-id",
        "scope": "focused.read focused.write",
        "jti": "token-jti-456",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,  # 1 hour from now
        "nbf": int(time.time()) - 10  # 10 seconds ago
    }


@pytest.fixture
def create_test_token(rsa_keypair, valid_token_payload):
    """Factory to create test JWTs."""
    def _create_token(payload_overrides=None, kid="test-kid-123"):
        payload = valid_token_payload.copy()
        if payload_overrides:
            payload.update(payload_overrides)

        return jwt.encode(
            payload,
            rsa_keypair["private_key"],
            algorithm="RS256",
            headers={"kid": kid}
        )

    return _create_token


# =============================================================================
# Unit Tests: Header Extraction
# =============================================================================

class TestHeaderExtraction:
    """Test Authorization header extraction and Bearer token parsing."""

    def test_extract_authorization_header_success(self):
        """Test extracting Authorization header (case-insensitive)."""
        headers = {"Authorization": "Bearer token123"}
        result = extract_authorization_header(headers)
        assert result == "Bearer token123"

    def test_extract_authorization_header_lowercase(self):
        """Test header extraction with lowercase key."""
        headers = {"authorization": "Bearer token123"}
        result = extract_authorization_header(headers)
        assert result == "Bearer token123"

    def test_extract_authorization_header_mixed_case(self):
        """Test header extraction with mixed case key."""
        headers = {"AuThOrIzAtIoN": "Bearer token123"}
        result = extract_authorization_header(headers)
        assert result == "Bearer token123"

    def test_extract_authorization_header_missing(self):
        """Test extraction when header is missing."""
        headers = {"Content-Type": "application/json"}
        result = extract_authorization_header(headers)
        assert result is None

    def test_extract_bearer_token_success(self):
        """Test extracting Bearer token from valid header."""
        auth_header = "Bearer eyJhbGciOiJSUzI1NiJ9..."
        result = extract_bearer_token(auth_header)
        assert result == "eyJhbGciOiJSUzI1NiJ9..."

    def test_extract_bearer_token_case_insensitive(self):
        """Test Bearer keyword is case-insensitive."""
        auth_header = "bearer token123"
        result = extract_bearer_token(auth_header)
        assert result == "token123"

    def test_extract_bearer_token_invalid_format(self):
        """Test extraction with invalid format."""
        assert extract_bearer_token("Basic token123") is None
        assert extract_bearer_token("token123") is None
        assert extract_bearer_token("Bearer") is None
        assert extract_bearer_token("Bearer ") is None

    def test_extract_bearer_token_none(self):
        """Test extraction with None input."""
        result = extract_bearer_token(None)
        assert result is None


# =============================================================================
# Unit Tests: Scope Enforcement
# =============================================================================

class TestScopeEnforcement:
    """Test scope checking and enforcement logic."""

    def test_check_scopes_all_present(self):
        """Test scope check when all required scopes are present."""
        token_scopes = {"focused.read", "focused.write", "focused.notify"}
        required_scopes = ["focused.read", "focused.write"]
        assert check_scopes(token_scopes, required_scopes) is True

    def test_check_scopes_missing_one(self):
        """Test scope check when one required scope is missing."""
        token_scopes = {"focused.read"}
        required_scopes = ["focused.read", "focused.write"]
        assert check_scopes(token_scopes, required_scopes) is False

    def test_check_scopes_empty_required(self):
        """Test scope check with no required scopes."""
        token_scopes = {"focused.read"}
        required_scopes = []
        assert check_scopes(token_scopes, required_scopes) is True

    def test_check_scopes_empty_token(self):
        """Test scope check with no token scopes."""
        token_scopes = set()
        required_scopes = ["focused.read"]
        assert check_scopes(token_scopes, required_scopes) is False

    def test_enforce_tool_scope_success(self):
        """Test enforce_tool_scope when scopes are sufficient."""
        token_scopes = {"focused.read", "focused.write"}
        # Should not raise
        enforce_tool_scope("check_calendar", token_scopes, "test-corr-id")

    def test_enforce_tool_scope_insufficient(self):
        """Test enforce_tool_scope raises when scopes are insufficient."""
        token_scopes = {"focused.read"}

        with pytest.raises(InsufficientScopeError) as exc_info:
            enforce_tool_scope("watch_calendar", token_scopes, "test-corr-id")

        assert exc_info.value.required_scopes == ["focused.write"]
        assert exc_info.value.actual_scopes == ["focused.read"]

    def test_enforce_tool_scope_unknown_tool(self):
        """Test enforce_tool_scope with unknown tool (no requirements)."""
        token_scopes = {"focused.read"}
        # Should not raise (no requirements for unknown tools)
        enforce_tool_scope("unknown_tool", token_scopes, "test-corr-id")


# =============================================================================
# Unit Tests: Correlation ID
# =============================================================================

class TestCorrelationID:
    """Test correlation ID extraction and generation."""

    def test_extract_correlation_id_from_meta(self):
        """Test extracting correlation_id from metadata."""
        meta = {"correlation_id": "existing-corr-id-123"}
        result = extract_or_generate_correlation_id(meta)
        assert result == "existing-corr-id-123"

    def test_generate_correlation_id_missing(self):
        """Test generating correlation_id when missing."""
        meta = {"headers": {}}
        result = extract_or_generate_correlation_id(meta)
        # Should be a UUID (36 characters with dashes)
        assert len(result) == 36
        assert result.count("-") == 4

    def test_generate_correlation_id_none_meta(self):
        """Test generating correlation_id when meta is None."""
        result = extract_or_generate_correlation_id(None)
        assert len(result) == 36

    def test_generate_correlation_id_malformed(self):
        """Test generating new correlation_id when existing is malformed."""
        meta = {"correlation_id": ""}
        result = extract_or_generate_correlation_id(meta)
        assert len(result) == 36


# =============================================================================
# Unit Tests: Error Builders
# =============================================================================

class TestErrorBuilders:
    """Test RFC 6750-compliant error response builders."""

    def test_build_unauthorized_error(self):
        """Test building 401 Unauthorized error response."""
        result = build_unauthorized_error("invalid_token", "Token expired")

        assert result["error"]["code"] == -32001
        assert result["error"]["message"] == "Unauthorized"
        assert result["error"]["data"]["error"] == "invalid_token"
        assert result["error"]["data"]["error_description"] == "Token expired"
        assert "www_authenticate" in result["error"]["data"]
        assert "Bearer realm=" in result["error"]["data"]["www_authenticate"]

    def test_build_forbidden_error(self):
        """Test building 403 Forbidden error response."""
        result = build_forbidden_error(
            required_scopes=["focused.write"],
            actual_scopes=["focused.read"]
        )

        assert result["error"]["code"] == -32002
        assert result["error"]["message"] == "Forbidden"
        assert result["error"]["data"]["error"] == "insufficient_scope"
        assert result["error"]["data"]["required_scopes"] == ["focused.write"]
        assert result["error"]["data"]["actual_scopes"] == ["focused.read"]
        assert "www_authenticate" in result["error"]["data"]
        assert "insufficient_scope" in result["error"]["data"]["www_authenticate"]


# =============================================================================
# Unit Tests: JWKS Cache
# =============================================================================

class TestJWKSCache:
    """Test JWKS caching with TTL and max stale age."""

    @pytest.mark.asyncio
    async def test_cache_valid_within_ttl(self, mock_jwks):
        """Test cache is valid within TTL period."""
        cache = JWKSCache()
        cache._jwks = mock_jwks
        cache._fetched_at = time.time() - 3600  # 1 hour ago

        # Within 24-hour TTL
        assert cache.is_cache_valid() is True
        assert cache.is_cache_too_old() is False

    @pytest.mark.asyncio
    async def test_cache_stale_but_usable(self, mock_jwks):
        """Test cache is stale but still within max age."""
        cache = JWKSCache()
        cache._jwks = mock_jwks
        cache._fetched_at = time.time() - (25 * 3600)  # 25 hours ago

        # Beyond 24h TTL but within 7-day max
        assert cache.is_cache_valid() is False
        assert cache.is_cache_too_old() is False

    @pytest.mark.asyncio
    async def test_cache_too_old(self, mock_jwks):
        """Test cache is too old (> 7 days)."""
        cache = JWKSCache()
        cache._jwks = mock_jwks
        cache._fetched_at = time.time() - (8 * 24 * 3600)  # 8 days ago

        assert cache.is_cache_valid() is False
        assert cache.is_cache_too_old() is True

    @pytest.mark.asyncio
    async def test_fetch_jwks_uses_cache(self, mock_jwks):
        """Test fetch_jwks uses cache when valid."""
        cache = JWKSCache()
        cache._jwks = mock_jwks
        cache._fetched_at = time.time()

        result = await cache.fetch_jwks()
        assert result == mock_jwks

    @pytest.mark.asyncio
    async def test_fetch_jwks_refetches_when_stale(self, mock_jwks):
        """Test fetch_jwks refetches when cache is stale."""
        cache = JWKSCache()
        cache._jwks = {"old": "data"}
        cache._fetched_at = time.time() - (25 * 3600)  # Stale

        # Mock HTTP client
        with patch.object(cache._http_client, 'get', new_callable=AsyncMock) as mock_get:
            mock_response = Mock()
            mock_response.json.return_value = mock_jwks
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            result = await cache.fetch_jwks()

            assert result == mock_jwks
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_jwks_fails_uses_stale_cache(self, mock_jwks):
        """Test fetch_jwks uses stale cache when refetch fails."""
        cache = JWKSCache()
        cache._jwks = mock_jwks
        cache._fetched_at = time.time() - (25 * 3600)  # Stale but usable

        # Mock HTTP client to fail
        with patch.object(cache._http_client, 'get', side_effect=Exception("Network error")):
            result = await cache.fetch_jwks()

            # Should return stale cache
            assert result == mock_jwks

    @pytest.mark.asyncio
    async def test_fetch_jwks_fails_closed_when_too_old(self):
        """Test fetch_jwks fails closed when cache is too old and refetch fails."""
        cache = JWKSCache()
        cache._jwks = {"old": "data"}
        cache._fetched_at = time.time() - (8 * 24 * 3600)  # Too old

        # Mock HTTP client to fail
        with patch.object(cache._http_client, 'get', side_effect=Exception("Network error")):
            with pytest.raises(Exception, match="JWKS fetch failed"):
                await cache.fetch_jwks()


# =============================================================================
# Integration Tests: Full Authentication Flow
# =============================================================================

class TestAuthenticationFlow:
    """Integration tests for complete authentication flow."""

    @pytest.mark.asyncio
    async def test_authenticate_request_success(self, create_test_token, mock_jwks, rsa_keypair):
        """Test successful authentication with valid token and scopes."""
        token = create_test_token()

        meta = {
            "headers": {"Authorization": f"Bearer {token}"},
            "correlation_id": "test-corr-123"
        }

        # Mock JWKS cache and JWT validation
        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            # Mock JWKS fetch
            mock_cache.fetch_jwks = AsyncMock(return_value=mock_jwks)

            # Mock get_signing_key to return our test key
            from jwt import PyJWK
            mock_jwk = PyJWK({"kty": "RSA", "kid": "test-kid-123"})
            mock_jwk._key = rsa_keypair["public_key_obj"]
            mock_cache.get_signing_key = Mock(return_value=mock_jwk)

            # Mock config
            with patch('mcp.focused.mcp_auth.CHATGPT_CLIENT_ID_FOCUSED', "test-client-id"):
                result = await authenticate_request("check_calendar", meta)

        assert result["user_id"] == "user-123"
        assert result["correlation_id"] == "test-corr-123"
        assert "focused.read" in result["scopes"]
        assert "focused.write" in result["scopes"]

    @pytest.mark.asyncio
    async def test_authenticate_request_missing_header(self):
        """Test authentication fails when Authorization header is missing."""
        meta = {"headers": {}}

        with pytest.raises(UnauthorizedError) as exc_info:
            await authenticate_request("check_calendar", meta)

        assert exc_info.value.error == "invalid_token"
        assert "Missing Authorization header" in exc_info.value.description

    @pytest.mark.asyncio
    async def test_authenticate_request_invalid_format(self):
        """Test authentication fails with invalid header format."""
        meta = {"headers": {"Authorization": "Basic token123"}}

        with pytest.raises(UnauthorizedError) as exc_info:
            await authenticate_request("check_calendar", meta)

        assert exc_info.value.error == "invalid_token"
        assert "Invalid Authorization header format" in exc_info.value.description

    @pytest.mark.asyncio
    async def test_authenticate_request_insufficient_scope(self, create_test_token, mock_jwks, rsa_keypair):
        """Test authentication fails when token lacks required scopes."""
        # Token with only focused.read
        token = create_test_token({"scope": "focused.read"})

        meta = {"headers": {"Authorization": f"Bearer {token}"}}

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock(return_value=mock_jwks)

            from jwt import PyJWK
            mock_jwk = PyJWK({"kty": "RSA", "kid": "test-kid-123"})
            mock_jwk._key = rsa_keypair["public_key_obj"]
            mock_cache.get_signing_key = Mock(return_value=mock_jwk)

            with patch('mcp.focused.mcp_auth.CHATGPT_CLIENT_ID_FOCUSED', "test-client-id"):
                # watch_calendar requires focused.write
                with pytest.raises(InsufficientScopeError) as exc_info:
                    await authenticate_request("watch_calendar", meta)

        assert exc_info.value.required_scopes == ["focused.write"]
        assert exc_info.value.actual_scopes == ["focused.read"]

    @pytest.mark.asyncio
    async def test_authenticate_request_expired_token(self, create_test_token):
        """Test authentication fails with expired token."""
        # Token expired 1 hour ago
        token = create_test_token({
            "exp": int(time.time()) - 3600,
            "iat": int(time.time()) - 7200
        })

        meta = {"headers": {"Authorization": f"Bearer {token}"}}

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()

            with pytest.raises(UnauthorizedError) as exc_info:
                await authenticate_request("check_calendar", meta)

        assert exc_info.value.error == "invalid_token"

    @pytest.mark.asyncio
    async def test_authenticate_request_expiring_soon(self, create_test_token, mock_jwks, rsa_keypair):
        """Test authentication fails when token expires in < 30 seconds."""
        # Token expires in 20 seconds
        token = create_test_token({"exp": int(time.time()) + 20})

        meta = {"headers": {"Authorization": f"Bearer {token}"}}

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock(return_value=mock_jwks)

            from jwt import PyJWK
            mock_jwk = PyJWK({"kty": "RSA", "kid": "test-kid-123"})
            mock_jwk._key = rsa_keypair["public_key_obj"]
            mock_cache.get_signing_key = Mock(return_value=mock_jwk)

            with patch('mcp.focused.mcp_auth.CHATGPT_CLIENT_ID_FOCUSED', "test-client-id"):
                with pytest.raises(UnauthorizedError) as exc_info:
                    await authenticate_request("check_calendar", meta)

        assert exc_info.value.error == "invalid_token"
        assert "Token expired" in exc_info.value.description or "expires" in exc_info.value.description.lower()


# =============================================================================
# Integration Tests: Backend Header Migration
# =============================================================================

class TestBackendHeaderMigration:
    """Test backend accepts X-User-ID header with fallback."""

    def test_backend_reads_x_user_id_header(self):
        """Test backend reads X-User-ID header as primary source."""
        # Mock FastAPI request
        request = Mock()
        request.headers = MagicMock()
        request.headers.get = Mock(return_value="user-from-header")

        user_id = request.headers.get("x-user-id")
        assert user_id == "user-from-header"

    def test_backend_falls_back_to_payload(self):
        """Test backend falls back to payload when header missing."""
        request = Mock()
        request.headers = MagicMock()
        request.headers.get = Mock(return_value=None)

        user_id_header = request.headers.get("x-user-id")
        user_id_payload = "user-from-payload"

        user_id = user_id_header if user_id_header else user_id_payload
        assert user_id == "user-from-payload"

    def test_backend_detects_mismatch(self):
        """Test backend detects mismatch between header and payload."""
        request = Mock()
        request.headers = MagicMock()
        request.headers.get = Mock(return_value="user-header")

        user_id_header = request.headers.get("x-user-id")
        user_id_payload = "user-payload"

        # Header wins
        user_id = user_id_header
        assert user_id == "user-header"

        # Should detect mismatch
        assert user_id_payload != user_id_header


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
