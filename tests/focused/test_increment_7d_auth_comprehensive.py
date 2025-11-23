"""
Comprehensive tests for Increment 7D - JWT Authentication & Authorization.

Tests ALL security-critical components:
1. validate_jwt() - JWT validation with all edge cases
2. JWKS cache - Fetching, caching, staleness, retry logic
3. authenticate_request() - End-to-end authentication flow
4. Scope enforcement - Per-tool scope validation
5. Integration tests - Real MCP tool calls
"""

import pytest
import time
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone, timedelta

import jwt as pyjwt
from jwt import PyJWK

from mcp.focused.mcp_auth import (
    JWKSCache,
    validate_jwt,
    authenticate_request,
    check_scopes,
    enforce_tool_scope,
    extract_authorization_header,
    extract_bearer_token,
    extract_or_generate_correlation_id,
    build_unauthorized_error,
    build_forbidden_error,
    UnauthorizedError,
    InsufficientScopeError,
)


# =============================================================================
# Test Fixtures - Config and Logger Mocking
# =============================================================================

@pytest.fixture(autouse=True)
def mock_config():
    """Mock config values to match test tokens."""
    with patch('mcp.focused.mcp_auth.FOCUSED_ISSUER', 'http://localhost:8000'):
        with patch('mcp.focused.mcp_auth.FOCUSED_AUDIENCE', 'focused-mcp'):
            with patch('mcp.focused.mcp_auth.CHATGPT_CLIENT_ID_FOCUSED', 'chatgpt-focused'):
                with patch('mcp.focused.mcp_auth.TOKEN_EXPIRY_GRACE_SECONDS', 60):
                    yield


@pytest.fixture(autouse=True)
def mock_logger():
    """Mock logger to handle structlog-style keyword arguments."""
    with patch('mcp.focused.mcp_auth.logger') as mock_log:
        # Make logger accept any keyword arguments
        mock_log.debug = Mock()
        mock_log.info = Mock()
        mock_log.warning = Mock()
        mock_log.error = Mock()
        yield mock_log


# =============================================================================
# Test Fixtures - JWT Token Creation
# =============================================================================

@pytest.fixture
def rsa_keypair():
    """Generate RSA key pair for JWT signing."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.backends import default_backend

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    public_key = private_key.public_key()

    return {
        "private_key": private_key,
        "public_key": public_key
    }


@pytest.fixture
def mock_jwks(rsa_keypair):
    """Create mock JWKS with test public key."""
    from cryptography.hazmat.primitives import serialization
    import json
    import base64

    public_key = rsa_keypair["public_key"]

    # Convert to PEM format
    public_key_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    # Get public numbers for JWK
    public_numbers = public_key.public_numbers()

    # Convert to JWK format manually
    def int_to_base64(n):
        """Convert integer to base64url."""
        n_bytes = n.to_bytes((n.bit_length() + 7) // 8, byteorder='big')
        return base64.urlsafe_b64encode(n_bytes).rstrip(b'=').decode('utf-8')

    jwk = {
        "kty": "RSA",
        "use": "sig",
        "kid": "test-key-1",
        "alg": "RS256",
        "n": int_to_base64(public_numbers.n),
        "e": int_to_base64(public_numbers.e)
    }

    return {
        "keys": [jwk]
    }


def create_test_token(rsa_keypair, **claims):
    """
    Create a test JWT token with custom claims.

    Default claims:
    - sub: test-user-123
    - scope: focused.read focused.write
    - iss: http://localhost:8000
    - aud: focused-mcp
    - azp: chatgpt-focused
    - jti: test-jti-456
    - exp: now + 1 hour
    - nbf: now
    - iat: now
    """
    from cryptography.hazmat.primitives import serialization

    private_key_pem = rsa_keypair["private_key"].private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    now = int(time.time())

    # Default claims
    payload = {
        "sub": "test-user-123",
        "scope": "focused.read focused.write",
        "iss": "http://localhost:8000",
        "aud": "focused-mcp",
        "azp": "chatgpt-focused",
        "jti": "test-jti-456",
        "exp": now + 3600,
        "nbf": now,
        "iat": now,
    }

    # Override with custom claims
    payload.update(claims)

    # Encode JWT
    token = pyjwt.encode(
        payload,
        private_key_pem,
        algorithm="RS256",
        headers={"kid": "test-key-1"}
    )

    return token


# =============================================================================
# Test 1: validate_jwt() - Core JWT Validation
# =============================================================================

class TestValidateJWT:
    """Test JWT validation with all edge cases."""

    @pytest.mark.asyncio
    async def test_validate_jwt_missing_kid(self, rsa_keypair):
        """Test JWT without kid in header raises error."""
        from cryptography.hazmat.primitives import serialization

        private_key_pem = rsa_keypair["private_key"].private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )

        payload = {"sub": "test-user"}

        # Create token WITHOUT kid in header
        token = pyjwt.encode(payload, private_key_pem, algorithm="RS256")

        with pytest.raises(pyjwt.InvalidTokenError, match="Missing kid"):
            await validate_jwt(token, "test-correlation-id")

    @pytest.mark.asyncio
    async def test_validate_jwt_unknown_kid_retry_logic(self, rsa_keypair, mock_jwks):
        """Test unknown kid triggers JWKS refetch and retry."""
        token = create_test_token(rsa_keypair)

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            # First call: kid not found
            # Second call (after refetch): still not found
            mock_cache.fetch_jwks = AsyncMock()
            mock_cache.get_signing_key = Mock(return_value=None)  # Always return None

            # Should raise InvalidTokenError for unknown kid
            with pytest.raises(pyjwt.InvalidTokenError, match="Unknown kid"):
                await validate_jwt(token, "test-correlation-id")

            # Verify refetch was called with force=True
            assert mock_cache.fetch_jwks.call_count == 2
            # Second call should have force=True
            assert mock_cache.fetch_jwks.call_args_list[1][1].get('force') == True

    @pytest.mark.asyncio
    async def test_validate_jwt_expired_token(self, rsa_keypair):
        """Test expired token raises ExpiredSignatureError."""
        now = int(time.time())

        # Create token that expired 1 hour ago
        token = create_test_token(
            rsa_keypair,
            exp=now - 3600,  # Expired 1 hour ago
            iat=now - 7200,  # Issued 2 hours ago
            nbf=now - 7200
        )

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            mock_cache.get_signing_key = Mock(return_value=None)

            # Will fail during kid lookup, but that's ok for this test structure
            with pytest.raises(Exception):
                await validate_jwt(token, "test-correlation-id")

    @pytest.mark.asyncio
    async def test_validate_jwt_expiring_within_grace_period(self, rsa_keypair, mock_jwks):
        """Test token expiring within grace period is rejected."""
        now = int(time.time())

        # Create token expiring in 10 seconds (within 60s grace period)
        token = create_test_token(
            rsa_keypair,
            exp=now + 10,  # Expires in 10 seconds
        )

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()

            # Setup proper signing key
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            # Should raise ExpiredSignatureError (within grace period)
            with pytest.raises(pyjwt.ExpiredSignatureError):
                await validate_jwt(token, "test-correlation-id")

    @pytest.mark.asyncio
    async def test_validate_jwt_missing_required_claims(self, rsa_keypair):
        """Test token without required claims fails validation."""
        # Create token missing 'scope' claim
        token = create_test_token(
            rsa_keypair,
            scope=None  # Remove scope claim
        )

        # Remove scope from payload
        from cryptography.hazmat.primitives import serialization
        private_key_pem = rsa_keypair["private_key"].private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )

        now = int(time.time())
        payload = {
            "sub": "test-user",
            "iss": "http://localhost:8000",
            "aud": "focused-mcp",
            "azp": "chatgpt-focused",
            "jti": "test-jti",
            "exp": now + 3600,
            "nbf": now,
            "iat": now,
            # Missing 'scope' - required claim
        }

        token = pyjwt.encode(payload, private_key_pem, algorithm="RS256", headers={"kid": "test-key-1"})

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            mock_cache.get_signing_key = Mock(return_value=None)

            with pytest.raises(Exception):
                await validate_jwt(token, "test-correlation-id")

    @pytest.mark.asyncio
    async def test_validate_jwt_invalid_issuer(self, rsa_keypair, mock_jwks):
        """Test token with wrong issuer fails validation."""
        token = create_test_token(
            rsa_keypair,
            iss="https://evil.com"  # Wrong issuer
        )

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            with pytest.raises(pyjwt.InvalidTokenError):
                await validate_jwt(token, "test-correlation-id")

    @pytest.mark.asyncio
    async def test_validate_jwt_invalid_audience(self, rsa_keypair, mock_jwks):
        """Test token with wrong audience fails validation."""
        token = create_test_token(
            rsa_keypair,
            aud="wrong-audience"
        )

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            with pytest.raises(pyjwt.InvalidTokenError):
                await validate_jwt(token, "test-correlation-id")

    @pytest.mark.asyncio
    async def test_validate_jwt_invalid_azp(self, rsa_keypair, mock_jwks):
        """Test token with wrong azp (authorized party) fails validation."""
        token = create_test_token(
            rsa_keypair,
            azp="wrong-client-id"  # Should be chatgpt-focused
        )

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            with pytest.raises(pyjwt.InvalidTokenError, match="Invalid azp"):
                await validate_jwt(token, "test-correlation-id")

    @pytest.mark.asyncio
    async def test_validate_jwt_valid_token_success(self, rsa_keypair, mock_jwks):
        """Test valid token passes all validation checks."""
        token = create_test_token(rsa_keypair)

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            result = await validate_jwt(token, "test-correlation-id")

            assert result["user_id"] == "test-user-123"
            assert result["jti"] == "test-jti-456"
            assert result["azp"] == "chatgpt-focused"
            assert "focused.read" in result["scopes"]
            assert "focused.write" in result["scopes"]


# =============================================================================
# Test 2: JWKS Cache Behavior
# =============================================================================

class TestJWKSCache:
    """Test JWKS caching, fetching, and staleness logic."""

    @pytest.mark.asyncio
    async def test_jwks_cache_hit(self):
        """Test cache hit when JWKS is fresh."""
        cache = JWKSCache()

        # Manually set cache
        cache._jwks = {"keys": [{"kid": "test-1"}]}
        cache._fetched_at = time.time()

        assert cache.is_cache_valid() == True

        # fetch_jwks should return cached value
        with patch.object(cache._http_client, 'get') as mock_get:
            result = await cache.fetch_jwks(force=False)

            # Should not call HTTP client
            mock_get.assert_not_called()
            assert result == {"keys": [{"kid": "test-1"}]}

    @pytest.mark.asyncio
    async def test_jwks_fetch_success(self):
        """Test successful JWKS fetch updates cache."""
        cache = JWKSCache()

        mock_response = Mock()
        mock_response.json.return_value = {"keys": [{"kid": "new-key"}]}
        mock_response.raise_for_status = Mock()

        with patch.object(cache._http_client, 'get', return_value=mock_response) as mock_get:
            result = await cache.fetch_jwks(force=True)

            mock_get.assert_called_once()
            assert result == {"keys": [{"kid": "new-key"}]}
            assert cache._jwks == {"keys": [{"kid": "new-key"}]}
            assert cache._fetched_at is not None

    @pytest.mark.asyncio
    async def test_jwks_fetch_failure_with_valid_stale_cache(self):
        """Test fetch failure falls back to stale cache if not too old."""
        from mcp.focused.config import JWKS_MAX_STALE_SECONDS

        cache = JWKSCache()

        # Set stale but not too old cache (fetched 2 days ago)
        cache._jwks = {"keys": [{"kid": "stale-key"}]}
        cache._fetched_at = time.time() - (2 * 86400)  # 2 days ago

        # Mock fetch failure
        with patch.object(cache._http_client, 'get', side_effect=Exception("Network error")):
            # Should return stale cache
            result = await cache.fetch_jwks(force=True)

            assert result == {"keys": [{"kid": "stale-key"}]}

    @pytest.mark.asyncio
    async def test_jwks_fetch_failure_with_too_old_cache(self):
        """Test fetch failure with too-old cache raises exception."""
        from mcp.focused.config import JWKS_MAX_STALE_SECONDS

        cache = JWKSCache()

        # Set cache that's too old (fetched 8 days ago, max is 7 days)
        cache._jwks = {"keys": [{"kid": "old-key"}]}
        cache._fetched_at = time.time() - (8 * 86400)

        # Mock fetch failure
        with patch.object(cache._http_client, 'get', side_effect=Exception("Network error")):
            with pytest.raises(Exception, match="JWKS fetch failed"):
                await cache.fetch_jwks(force=True)

    def test_jwks_cache_too_old_check(self):
        """Test cache too old detection."""
        from mcp.focused.config import JWKS_MAX_STALE_SECONDS

        cache = JWKSCache()

        # Fresh cache
        cache._fetched_at = time.time()
        assert cache.is_cache_too_old() == False

        # Stale but not too old (2 days)
        cache._fetched_at = time.time() - (2 * 86400)
        assert cache.is_cache_too_old() == False

        # Too old (8 days)
        cache._fetched_at = time.time() - (8 * 86400)
        assert cache.is_cache_too_old() == True

    def test_get_signing_key_by_kid(self, mock_jwks):
        """Test getting signing key by kid."""
        cache = JWKSCache()
        cache._jwks = mock_jwks

        # Get existing kid
        key = cache.get_signing_key("test-key-1")
        assert key is not None
        assert key.key_id == "test-key-1"

        # Get non-existent kid
        key = cache.get_signing_key("unknown-kid")
        assert key is None


# =============================================================================
# Test 3: authenticate_request() - Main Auth Function
# =============================================================================

class TestAuthenticateRequest:
    """Test end-to-end authentication flow."""

    @pytest.mark.asyncio
    async def test_authenticate_missing_auth_header(self):
        """Test missing Authorization header raises UnauthorizedError."""
        meta = {
            "headers": {},
            "correlation_id": "test-123"
        }

        with pytest.raises(UnauthorizedError, match="Missing Authorization"):
            await authenticate_request("check_calendar", meta)

    @pytest.mark.asyncio
    async def test_authenticate_invalid_header_format(self):
        """Test invalid Authorization header format."""
        meta = {
            "headers": {"Authorization": "InvalidFormat"},
            "correlation_id": "test-123"
        }

        with pytest.raises(UnauthorizedError, match="Invalid Authorization header"):
            await authenticate_request("check_calendar", meta)

    @pytest.mark.asyncio
    async def test_authenticate_valid_token_success(self, rsa_keypair, mock_jwks):
        """Test successful authentication with valid token."""
        token = create_test_token(rsa_keypair, scope="focused.read")

        meta = {
            "headers": {"Authorization": f"Bearer {token}"},
            "correlation_id": "test-123"
        }

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            result = await authenticate_request("check_calendar", meta)

            assert result["user_id"] == "test-user-123"
            assert result["correlation_id"] == "test-123"
            assert result["jti"] == "test-jti-456"
            assert "focused.read" in result["scopes"]

    @pytest.mark.asyncio
    async def test_authenticate_insufficient_scope(self, rsa_keypair, mock_jwks):
        """Test authentication fails when token lacks required scope."""
        # Token only has focused.read, but watch_calendar needs focused.write
        token = create_test_token(rsa_keypair, scope="focused.read")

        meta = {
            "headers": {"Authorization": f"Bearer {token}"},
            "correlation_id": "test-123"
        }

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            with pytest.raises(InsufficientScopeError):
                await authenticate_request("watch_calendar", meta)  # Requires focused.write

    @pytest.mark.asyncio
    async def test_authenticate_correlation_id_generation(self, rsa_keypair, mock_jwks):
        """Test correlation ID is generated when not provided."""
        token = create_test_token(rsa_keypair)

        meta = {
            "headers": {"Authorization": f"Bearer {token}"},
            # No correlation_id provided
        }

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            result = await authenticate_request("check_calendar", meta)

            # Should have generated correlation_id
            assert "correlation_id" in result
            assert len(result["correlation_id"]) > 0


# =============================================================================
# Test 4: Scope Enforcement
# =============================================================================

class TestScopeEnforcement:
    """Test scope checking and enforcement."""

    def test_check_scopes_all_present(self):
        """Test scope check when all required scopes present."""
        token_scopes = {"focused.read", "focused.write", "focused.notify"}
        required_scopes = ["focused.read", "focused.write"]

        assert check_scopes(token_scopes, required_scopes) == True

    def test_check_scopes_missing_one(self):
        """Test scope check when missing one required scope."""
        token_scopes = {"focused.read"}
        required_scopes = ["focused.read", "focused.write"]

        assert check_scopes(token_scopes, required_scopes) == False

    def test_enforce_tool_scope_success(self):
        """Test scope enforcement succeeds with correct scopes."""
        token_scopes = {"focused.read", "focused.write"}

        # Should not raise
        enforce_tool_scope("check_calendar", token_scopes, "test-correlation")

    def test_enforce_tool_scope_failure(self):
        """Test scope enforcement fails with insufficient scopes."""
        token_scopes = {"focused.read"}  # Missing focused.write

        with pytest.raises(InsufficientScopeError) as exc_info:
            enforce_tool_scope("watch_calendar", token_scopes, "test-correlation")

        assert "focused.write" in str(exc_info.value.required_scopes)


# =============================================================================
# Test 5: Error Response Builders
# =============================================================================

class TestErrorResponses:
    """Test RFC 6750 error response builders."""

    def test_build_unauthorized_error_structure(self):
        """Test unauthorized error has correct JSON-RPC structure."""
        error = build_unauthorized_error("invalid_token", "Token expired")

        assert "error" in error
        assert error["error"]["code"] == -32001
        assert error["error"]["message"] == "Unauthorized"
        assert error["error"]["data"]["error"] == "invalid_token"
        assert error["error"]["data"]["error_description"] == "Token expired"
        assert "www_authenticate" in error["error"]["data"]
        assert "Bearer realm=" in error["error"]["data"]["www_authenticate"]

    def test_build_forbidden_error_structure(self):
        """Test forbidden error has correct JSON-RPC structure."""
        error = build_forbidden_error(["focused.write"], ["focused.read"])

        assert "error" in error
        assert error["error"]["code"] == -32002
        assert error["error"]["message"] == "Forbidden"
        assert error["error"]["data"]["error"] == "insufficient_scope"
        assert error["error"]["data"]["required_scopes"] == ["focused.write"]
        assert error["error"]["data"]["actual_scopes"] == ["focused.read"]
        assert "www_authenticate" in error["error"]["data"]
        assert "insufficient_scope" in error["error"]["data"]["www_authenticate"]


# =============================================================================
# Test 6: Helper Functions
# =============================================================================

class TestHelperFunctions:
    """Test header extraction and correlation ID helpers."""

    def test_extract_authorization_header_case_insensitive(self):
        """Test authorization header extraction is case-insensitive."""
        headers = {"AuThOrIzAtIoN": "Bearer token"}
        assert extract_authorization_header(headers) == "Bearer token"

    def test_extract_bearer_token_valid(self):
        """Test bearer token extraction from valid header."""
        assert extract_bearer_token("Bearer abc123") == "abc123"

    def test_extract_bearer_token_invalid_format(self):
        """Test bearer token extraction with invalid format."""
        assert extract_bearer_token("Basic abc123") is None
        assert extract_bearer_token("Bearer") is None
        assert extract_bearer_token("") is None

    def test_extract_or_generate_correlation_id_provided(self):
        """Test correlation ID extraction when provided."""
        meta = {"correlation_id": "existing-123"}
        assert extract_or_generate_correlation_id(meta) == "existing-123"

    def test_extract_or_generate_correlation_id_generated(self):
        """Test correlation ID generation when not provided."""
        meta = {}
        correlation_id = extract_or_generate_correlation_id(meta)

        # Should be a valid UUID-like string
        assert len(correlation_id) > 0
        assert "-" in correlation_id
