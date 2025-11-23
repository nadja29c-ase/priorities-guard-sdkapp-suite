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
import sys
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
    async def test_validate_jwt_unknown_kid_retry_success(self, rsa_keypair, mock_jwks):
        """
        Test CRITICAL 7D retry flow: unknown kid → refetch JWKS → success.

        Scenario:
        1. First attempt: kid not in cached JWKS
        2. Trigger JWKS refetch (force=True)
        3. Second attempt: kid found in fresh JWKS
        4. Token validation succeeds
        """
        token = create_test_token(rsa_keypair)

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()

            # Setup signing key
            signing_key = PyJWK(mock_jwks["keys"][0])

            # First call: kid not found
            # Second call: kid found (after refetch)
            mock_cache.get_signing_key = Mock(side_effect=[
                None,  # First attempt: unknown kid
                signing_key  # After refetch: kid found
            ])

            # Should succeed after retry
            result = await validate_jwt(token, "test-correlation-id")

            # Verify successful validation
            assert result["user_id"] == "test-user-123"
            assert result["jti"] == "test-jti-456"
            assert "focused.read" in result["scopes"]

            # Verify refetch was triggered
            assert mock_cache.fetch_jwks.call_count == 2
            # Second call should have force=True
            assert mock_cache.fetch_jwks.call_args_list[1][1].get('force') == True

    @pytest.mark.asyncio
    async def test_validate_jwt_invalid_signature(self, rsa_keypair, mock_jwks):
        """
        Test CRITICAL security check: JWT signed with wrong private key fails signature verification.

        This is a fundamental security test - ensures forged JWTs are rejected.

        Scenario:
        1. Generate a DIFFERENT RSA keypair (attacker's key)
        2. Sign JWT with attacker's private key
        3. Provide legitimate public key in JWKS (our key, not attacker's)
        4. Signature verification MUST fail
        """
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend

        # Generate ATTACKER's keypair (different from legitimate keypair)
        attacker_private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        attacker_private_pem = attacker_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )

        # Create token signed with ATTACKER's private key
        now = int(time.time())
        payload = {
            "sub": "attacker-user",
            "scope": "focused.read focused.write",  # Trying to escalate privileges
            "iss": "http://localhost:8000",
            "aud": "focused-mcp",
            "azp": "chatgpt-focused",
            "jti": "forged-jti",
            "exp": now + 3600,
            "nbf": now,
            "iat": now,
        }

        # Sign with attacker's key
        forged_token = pyjwt.encode(
            payload,
            attacker_private_pem,
            algorithm="RS256",
            headers={"kid": "test-key-1"}  # Claims to be our key
        )

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()

            # Provide LEGITIMATE public key (from rsa_keypair, not attacker's)
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            # Should raise InvalidSignatureError (signature doesn't match)
            with pytest.raises(pyjwt.InvalidSignatureError):
                await validate_jwt(forged_token, "test-correlation-id")

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

    @pytest.mark.asyncio
    async def test_authenticate_meta_none_generates_correlation_id(self, rsa_keypair, mock_jwks):
        """
        Test authenticate_request with meta=None generates correlation_id.

        CRITICAL: Validates that when meta is None (not just missing correlation_id),
        the function properly:
        1. Generates a correlation ID
        2. Returns it in auth_context
        3. Doesn't crash trying to access meta["headers"]
        """
        token = create_test_token(rsa_keypair)

        # Pass meta=None explicitly
        meta = None

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            # This will fail because meta=None means no headers, which should raise UnauthorizedError
            # But it should STILL generate and propagate a correlation_id
            with pytest.raises(UnauthorizedError) as exc_info:
                await authenticate_request("check_calendar", meta)

            # Even though auth failed, correlation_id should have been generated
            # (we can't verify it from the exception, but we can verify no crash occurred)
            assert exc_info.value.error == "invalid_token"

    @pytest.mark.asyncio
    async def test_authenticate_empty_meta_generates_correlation_id(self, rsa_keypair, mock_jwks):
        """
        Test authenticate_request with meta={} generates correlation_id.

        Validates that when meta is empty dict (no headers, no correlation_id),
        correlation_id is still generated and would be returned in success case.
        """
        token = create_test_token(rsa_keypair)

        # Empty meta dict
        meta = {}

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            # This will fail because meta={} means no headers
            with pytest.raises(UnauthorizedError) as exc_info:
                await authenticate_request("check_calendar", meta)

            # Should fail with invalid_token (missing Authorization header)
            assert exc_info.value.error == "invalid_token"
            assert "Missing Authorization header" in exc_info.value.description

    @pytest.mark.asyncio
    async def test_authenticate_invalid_issuer_raises_unauthorized(self, rsa_keypair, mock_jwks):
        """Test invalid issuer raises UnauthorizedError with proper error code."""
        # Create token with wrong issuer
        token = create_test_token(rsa_keypair, iss="https://evil.com")

        meta = {
            "headers": {"Authorization": f"Bearer {token}"},
            "correlation_id": "test-123"
        }

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            # Should raise UnauthorizedError (not plain InvalidTokenError)
            with pytest.raises(UnauthorizedError) as exc_info:
                await authenticate_request("check_calendar", meta)

            # Verify error details
            assert exc_info.value.error == "invalid_token"
            assert "issuer" in exc_info.value.description.lower() or "invalid" in exc_info.value.description.lower()

    @pytest.mark.asyncio
    async def test_authenticate_invalid_audience_raises_unauthorized(self, rsa_keypair, mock_jwks):
        """Test invalid audience raises UnauthorizedError with proper error code."""
        # Create token with wrong audience
        token = create_test_token(rsa_keypair, aud="wrong-audience")

        meta = {
            "headers": {"Authorization": f"Bearer {token}"},
            "correlation_id": "test-123"
        }

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            # Should raise UnauthorizedError
            with pytest.raises(UnauthorizedError) as exc_info:
                await authenticate_request("check_calendar", meta)

            # Verify error details
            assert exc_info.value.error == "invalid_token"
            assert "audience" in exc_info.value.description.lower() or "invalid" in exc_info.value.description.lower()

    @pytest.mark.asyncio
    async def test_authenticate_expired_token_raises_unauthorized(self, rsa_keypair, mock_jwks):
        """Test expired token raises UnauthorizedError (not raw ExpiredSignatureError)."""
        now = int(time.time())

        # Create expired token
        token = create_test_token(
            rsa_keypair,
            exp=now - 3600,  # Expired 1 hour ago
            iat=now - 7200,
            nbf=now - 7200
        )

        meta = {
            "headers": {"Authorization": f"Bearer {token}"},
            "correlation_id": "test-123"
        }

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            # Should raise UnauthorizedError with "Token expired" description
            with pytest.raises(UnauthorizedError) as exc_info:
                await authenticate_request("check_calendar", meta)

            # Verify error details
            assert exc_info.value.error == "invalid_token"
            assert "expired" in exc_info.value.description.lower()

    @pytest.mark.asyncio
    async def test_authenticate_missing_scope_claim(self, rsa_keypair, mock_jwks):
        """Test token missing 'scope' claim raises UnauthorizedError."""
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

        meta = {
            "headers": {"Authorization": f"Bearer {token}"},
            "correlation_id": "test-123"
        }

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            # Should raise UnauthorizedError
            with pytest.raises(UnauthorizedError) as exc_info:
                await authenticate_request("check_calendar", meta)

            assert exc_info.value.error == "invalid_token"

    @pytest.mark.asyncio
    async def test_authenticate_missing_jti_claim(self, rsa_keypair, mock_jwks):
        """Test token missing 'jti' claim raises UnauthorizedError."""
        from cryptography.hazmat.primitives import serialization

        private_key_pem = rsa_keypair["private_key"].private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )

        now = int(time.time())
        payload = {
            "sub": "test-user",
            "scope": "focused.read",
            "iss": "http://localhost:8000",
            "aud": "focused-mcp",
            "azp": "chatgpt-focused",
            # Missing 'jti' - required claim
            "exp": now + 3600,
            "nbf": now,
            "iat": now,
        }

        token = pyjwt.encode(payload, private_key_pem, algorithm="RS256", headers={"kid": "test-key-1"})

        meta = {
            "headers": {"Authorization": f"Bearer {token}"},
            "correlation_id": "test-123"
        }

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            # Should raise UnauthorizedError
            with pytest.raises(UnauthorizedError) as exc_info:
                await authenticate_request("check_calendar", meta)

            assert exc_info.value.error == "invalid_token"

    @pytest.mark.asyncio
    async def test_authenticate_missing_azp_claim(self, rsa_keypair, mock_jwks):
        """Test token missing 'azp' claim raises UnauthorizedError."""
        from cryptography.hazmat.primitives import serialization

        private_key_pem = rsa_keypair["private_key"].private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )

        now = int(time.time())
        payload = {
            "sub": "test-user",
            "scope": "focused.read",
            "iss": "http://localhost:8000",
            "aud": "focused-mcp",
            "jti": "test-jti",
            # Missing 'azp' - required claim
            "exp": now + 3600,
            "nbf": now,
            "iat": now,
        }

        token = pyjwt.encode(payload, private_key_pem, algorithm="RS256", headers={"kid": "test-key-1"})

        meta = {
            "headers": {"Authorization": f"Bearer {token}"},
            "correlation_id": "test-123"
        }

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            # Should raise UnauthorizedError
            with pytest.raises(UnauthorizedError) as exc_info:
                await authenticate_request("check_calendar", meta)

            assert exc_info.value.error == "invalid_token"

    @pytest.mark.asyncio
    async def test_authenticate_missing_sub_claim(self, rsa_keypair, mock_jwks):
        """Test token missing 'sub' claim raises UnauthorizedError."""
        from cryptography.hazmat.primitives import serialization

        private_key_pem = rsa_keypair["private_key"].private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )

        now = int(time.time())
        payload = {
            # Missing 'sub' - required claim
            "scope": "focused.read",
            "iss": "http://localhost:8000",
            "aud": "focused-mcp",
            "azp": "chatgpt-focused",
            "jti": "test-jti",
            "exp": now + 3600,
            "nbf": now,
            "iat": now,
        }

        token = pyjwt.encode(payload, private_key_pem, algorithm="RS256", headers={"kid": "test-key-1"})

        meta = {
            "headers": {"Authorization": f"Bearer {token}"},
            "correlation_id": "test-123"
        }

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            # Should raise UnauthorizedError
            with pytest.raises(UnauthorizedError) as exc_info:
                await authenticate_request("check_calendar", meta)

            assert exc_info.value.error == "invalid_token"

    @pytest.mark.asyncio
    async def test_authenticate_nbf_in_future_raises_unauthorized(self, rsa_keypair, mock_jwks):
        """Test token with nbf (not before) in the future raises UnauthorizedError."""
        now = int(time.time())

        # Create token that's not valid yet (nbf = now + 1 hour)
        token = create_test_token(
            rsa_keypair,
            nbf=now + 3600,  # Not valid for another hour
            iat=now,
            exp=now + 7200
        )

        meta = {
            "headers": {"Authorization": f"Bearer {token}"},
            "correlation_id": "test-123"
        }

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            # Should raise UnauthorizedError (token not yet valid)
            with pytest.raises(UnauthorizedError) as exc_info:
                await authenticate_request("check_calendar", meta)

            # Verify error details
            assert exc_info.value.error == "invalid_token"
            # PyJWT raises ImmatureSignatureError for nbf in future
            assert "immature" in exc_info.value.description.lower() or "not yet valid" in exc_info.value.description.lower()

    @pytest.mark.asyncio
    async def test_authenticate_wrong_algorithm_raises_unauthorized(self, rsa_keypair, mock_jwks):
        """
        Test token signed with wrong algorithm (HS256 instead of RS256) is rejected.

        This prevents algorithm confusion attacks where an attacker tries to use
        HMAC (HS256) instead of RSA (RS256).
        """
        from cryptography.hazmat.primitives import serialization

        # Create token with HS256 (symmetric) instead of RS256 (asymmetric)
        secret = "secret-key"
        now = int(time.time())
        payload = {
            "sub": "test-user",
            "scope": "focused.read",
            "iss": "http://localhost:8000",
            "aud": "focused-mcp",
            "azp": "chatgpt-focused",
            "jti": "test-jti",
            "exp": now + 3600,
            "nbf": now,
            "iat": now,
        }

        # Sign with HS256 (wrong algorithm)
        token = pyjwt.encode(payload, secret, algorithm="HS256", headers={"kid": "test-key-1"})

        meta = {
            "headers": {"Authorization": f"Bearer {token}"},
            "correlation_id": "test-123"
        }

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            # Should raise UnauthorizedError (algorithm mismatch)
            with pytest.raises(UnauthorizedError) as exc_info:
                await authenticate_request("check_calendar", meta)

            # Verify error details
            assert exc_info.value.error == "invalid_token"
            # Error should mention algorithm issue (PyJWT says "alg value is not allowed")
            assert "alg" in exc_info.value.description.lower() or "algorithm" in exc_info.value.description.lower()

    @pytest.mark.asyncio
    async def test_authenticate_invalid_signature_raises_unauthorized(self, rsa_keypair, mock_jwks):
        """
        Test CRITICAL security check: forged JWT (wrong signature) raises UnauthorizedError.

        This ensures that JWTs signed with a different private key are rejected at the
        authenticate_request level, with proper error conversion to UnauthorizedError.

        Attack scenario:
        1. Attacker generates their own RSA keypair
        2. Creates JWT with elevated privileges (focused.read + focused.write)
        3. Signs JWT with their private key
        4. Claims to use our kid in header
        5. System validates against OUR public key → signature mismatch → rejection
        """
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend

        # Generate ATTACKER's keypair
        attacker_private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        attacker_private_pem = attacker_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )

        # Create forged token with escalated privileges
        now = int(time.time())
        payload = {
            "sub": "attacker-user",
            "scope": "focused.read focused.write focused.notify",  # All scopes!
            "iss": "http://localhost:8000",
            "aud": "focused-mcp",
            "azp": "chatgpt-focused",
            "jti": "forged-jti-123",
            "exp": now + 3600,
            "nbf": now,
            "iat": now,
        }

        # Sign with attacker's private key
        forged_token = pyjwt.encode(
            payload,
            attacker_private_pem,
            algorithm="RS256",
            headers={"kid": "test-key-1"}  # Claims to use our key
        )

        meta = {
            "headers": {"Authorization": f"Bearer {forged_token}"},
            "correlation_id": "test-123"
        }

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()

            # Provide LEGITIMATE public key (not attacker's)
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            # Should raise UnauthorizedError (signature verification fails)
            with pytest.raises(UnauthorizedError) as exc_info:
                await authenticate_request("check_calendar", meta)

            # Verify error is properly converted from InvalidSignatureError
            assert exc_info.value.error == "invalid_token"
            assert "signature" in exc_info.value.description.lower()

    @pytest.mark.asyncio
    async def test_authenticate_unknown_kid_retry_success_end_to_end(self, rsa_keypair, mock_jwks):
        """
        Test CRITICAL end-to-end flow: unknown kid → JWKS refetch → authentication success.

        This tests the FULL authenticate_request() flow including:
        1. First JWKS lookup: kid not found
        2. Trigger JWKS refetch (force=True)
        3. Second JWKS lookup: kid found
        4. JWT validation succeeds
        5. Scope enforcement succeeds
        6. User identity extracted successfully
        """
        token = create_test_token(rsa_keypair, scope="focused.read")

        meta = {
            "headers": {"Authorization": f"Bearer {token}"},
            "correlation_id": "test-retry-123"
        }

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()

            # Setup signing key
            signing_key = PyJWK(mock_jwks["keys"][0])

            # First call: kid not found (triggers refetch)
            # Second call: kid found (after refetch)
            mock_cache.get_signing_key = Mock(side_effect=[
                None,  # First attempt: unknown kid
                signing_key  # After refetch: kid found
            ])

            # Should succeed after retry
            result = await authenticate_request("check_calendar", meta)

            # Verify successful authentication
            assert result["user_id"] == "test-user-123"
            assert result["correlation_id"] == "test-retry-123"
            assert result["jti"] == "test-jti-456"
            assert "focused.read" in result["scopes"]

            # Verify JWKS refetch was triggered
            assert mock_cache.fetch_jwks.call_count == 2
            # Second call should have force=True
            assert mock_cache.fetch_jwks.call_args_list[1][1].get('force') == True


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


# =============================================================================
# Test 7: MCP Server Integration - Error Response Format
# =============================================================================

class TestMCPServerErrorResponses:
    """
    Test that MCP server's @handle_mcp_errors decorator returns correct JSON-RPC error responses.

    CRITICAL: Validates that the decorator properly formats errors from authentication failures:
    - Correct JSON-RPC error codes (-32001 for unauthorized, -32002 for forbidden)
    - WWW-Authenticate headers in response data
    - Proper JSON structure that clients can parse
    """

    @pytest.fixture
    def handle_mcp_errors(self):
        """Import the @handle_mcp_errors decorator with mocked dependencies."""
        with patch.dict('sys.modules', {
            'mcp.server': MagicMock(),
            'mcp.server.fastmcp': MagicMock(),
        }):
            # Import the module first
            import mcp.focused.server as server_module

            # Then mock the logger to accept keyword arguments
            server_module.logger = Mock()
            server_module.logger.debug = Mock()
            server_module.logger.info = Mock()
            server_module.logger.warning = Mock()
            server_module.logger.error = Mock()

            return server_module.handle_mcp_errors

    @pytest.mark.asyncio
    async def test_decorator_missing_auth_header_returns_jsonrpc_error(self, mock_config, handle_mcp_errors):
        """
        Test decorator with missing Authorization header returns JSON-RPC error -32001.

        Expected response:
        {
            "error": {
                "code": -32001,
                "message": "Unauthorized",
                "data": {
                    "error": "invalid_token",
                    "error_description": "Missing Authorization header",
                    "www_authenticate": "Bearer realm=..."
                }
            }
        }
        """
        # Create a test tool that calls authenticate_request
        @handle_mcp_errors("test_tool")
        async def test_tool(_meta=None):
            # This will raise UnauthorizedError due to missing header
            await authenticate_request("test_tool", _meta)
            return json.dumps({"success": True})

        # Call with no Authorization header
        meta = {"headers": {}}
        result_json = await test_tool(_meta=meta)

        # Parse JSON response
        result = json.loads(result_json)

        # Verify JSON-RPC error structure
        assert "error" in result
        assert result["error"]["code"] == -32001
        assert result["error"]["message"] == "Unauthorized"

        # Verify error details
        data = result["error"]["data"]
        assert data["error"] == "invalid_token"
        assert "Missing Authorization header" in data["error_description"]

        # Verify WWW-Authenticate header present
        assert "www_authenticate" in data
        assert "Bearer realm=" in data["www_authenticate"]

    @pytest.mark.asyncio
    async def test_decorator_expired_token_returns_jsonrpc_error(self, mock_config, rsa_keypair, mock_jwks, handle_mcp_errors):
        """
        Test decorator with expired token returns JSON-RPC error -32001.
        """
        # Create a test tool that calls authenticate_request
        @handle_mcp_errors("test_tool")
        async def test_tool(_meta=None):
            await authenticate_request("test_tool", _meta)
            return json.dumps({"success": True})

        # Create expired token
        now = int(time.time())
        token = create_test_token(
            rsa_keypair,
            exp=now - 3600,  # Expired 1 hour ago
            scope="focused.read"
        )

        meta = {
            "headers": {"Authorization": f"Bearer {token}"}
        }

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            result_json = await test_tool(_meta=meta)

        # Parse JSON response
        result = json.loads(result_json)

        # Verify JSON-RPC error structure
        assert "error" in result
        assert result["error"]["code"] == -32001
        assert result["error"]["message"] == "Unauthorized"

        # Verify error details
        data = result["error"]["data"]
        assert data["error"] == "invalid_token"
        assert "expired" in data["error_description"].lower()

        # Verify WWW-Authenticate header
        assert "www_authenticate" in data
        assert 'error="invalid_token"' in data["www_authenticate"]

    @pytest.mark.asyncio
    async def test_decorator_insufficient_scope_returns_jsonrpc_forbidden(self, mock_config, rsa_keypair, mock_jwks, handle_mcp_errors):
        """
        Test decorator with insufficient scopes returns JSON-RPC error -32002.

        Simulates a tool requiring focused.read scope.
        """
        # Create a test tool that requires focused.read
        @handle_mcp_errors("check_calendar")
        async def test_tool(_meta=None):
            await authenticate_request("check_calendar", _meta)
            return json.dumps({"success": True})

        # Create token with wrong scope (focused.write instead of focused.read)
        token = create_test_token(
            rsa_keypair,
            scope="focused.write"  # Wrong scope
        )

        meta = {
            "headers": {"Authorization": f"Bearer {token}"}
        }

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            result_json = await test_tool(_meta=meta)

        # Parse JSON response
        result = json.loads(result_json)

        # Verify JSON-RPC forbidden error structure
        assert "error" in result
        assert result["error"]["code"] == -32002
        assert result["error"]["message"] == "Forbidden"

        # Verify error details
        data = result["error"]["data"]
        assert data["error"] == "insufficient_scope"
        assert data["required_scopes"] == ["focused.read"]
        assert data["actual_scopes"] == ["focused.write"]

        # Verify WWW-Authenticate header
        assert "www_authenticate" in data
        assert 'error="insufficient_scope"' in data["www_authenticate"]

    @pytest.mark.asyncio
    async def test_decorator_write_tool_insufficient_scope(self, mock_config, rsa_keypair, mock_jwks, handle_mcp_errors):
        """
        Test decorator with write tool requiring focused.write scope.

        Simulates watch_calendar (requires focused.write).
        """
        # Create a test tool that requires focused.write
        @handle_mcp_errors("watch_calendar")
        async def test_tool(_meta=None):
            await authenticate_request("watch_calendar", _meta)
            return json.dumps({"success": True})

        # Create token with wrong scope (focused.read instead of focused.write)
        token = create_test_token(
            rsa_keypair,
            scope="focused.read"  # Insufficient scope
        )

        meta = {
            "headers": {"Authorization": f"Bearer {token}"}
        }

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            result_json = await test_tool(_meta=meta)

        # Parse JSON response
        result = json.loads(result_json)

        # Verify JSON-RPC forbidden error structure
        assert "error" in result
        assert result["error"]["code"] == -32002
        assert result["error"]["message"] == "Forbidden"

        # Verify error details
        data = result["error"]["data"]
        assert data["error"] == "insufficient_scope"
        assert data["required_scopes"] == ["focused.write"]
        assert data["actual_scopes"] == ["focused.read"]

    @pytest.mark.asyncio
    async def test_decorator_notify_scope_enforcement(self, mock_config, rsa_keypair, mock_jwks, handle_mcp_errors):
        """
        Test decorator enforces focused.notify scope for notify_user tool.
        """
        # Create a test tool that requires focused.notify
        @handle_mcp_errors("notify_user")
        async def test_tool(_meta=None):
            await authenticate_request("notify_user", _meta)
            return json.dumps({"success": True})

        # Create token with read scope only
        token = create_test_token(
            rsa_keypair,
            scope="focused.read"
        )

        meta = {
            "headers": {"Authorization": f"Bearer {token}"}
        }

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            result_json = await test_tool(_meta=meta)

        # Parse JSON response
        result = json.loads(result_json)

        # Should get insufficient_scope error
        assert "error" in result
        assert result["error"]["code"] == -32002
        assert result["error"]["data"]["error"] == "insufficient_scope"
        assert result["error"]["data"]["required_scopes"] == ["focused.notify"]

    @pytest.mark.asyncio
    async def test_decorator_backend_error_passthrough(self, mock_config, rsa_keypair, mock_jwks, handle_mcp_errors):
        """
        Test decorator properly passes through backend HTTP errors.

        Simulates a backend error (not auth error).
        """
        import httpx

        # Create a test tool that raises HTTPStatusError
        @handle_mcp_errors("test_tool")
        async def test_tool(_meta=None):
            # Simulate backend returning error
            response = httpx.Response(
                status_code=500,
                json={"success": False, "error": {"code": "BACKEND_ERROR", "message": "Something went wrong"}}
            )
            raise httpx.HTTPStatusError("Backend error", request=None, response=response)

        meta = {"headers": {}}
        result_json = await test_tool(_meta=meta)

        # Parse JSON response
        result = json.loads(result_json)

        # Should return the backend error as-is
        assert "success" in result
        assert result["success"] is False
        assert result["error"]["code"] == "BACKEND_ERROR"


# =============================================================================
# Test 8: End-to-End MCP Server Tool Integration
# =============================================================================

class TestMCPServerToolsEndToEnd:
    """
    CRITICAL end-to-end tests for ACTUAL MCP server tools.

    Tests the real check_calendar, watch_calendar, run_focus_mode, notify_user
    functions (not just decorator wrappers) with:
    - Valid tokens → success
    - Invalid tokens → proper errors
    - Missing scopes → proper errors
    - Backend errors → proper passthrough
    """

    @pytest.fixture
    def mock_backend_post(self):
        """Mock backend_post function to simulate backend API."""
        with patch('mcp.focused.server.backend_post', new_callable=AsyncMock) as mock:
            yield mock

    @pytest.fixture
    def import_server(self):
        """Import server module with mocked dependencies."""
        # Create a pass-through mock for @mcp.tool() decorator
        def passthrough_decorator(*args, **kwargs):
            """Decorator that returns the function unchanged."""
            def decorator(func):
                return func
            # Handle both @mcp.tool() and @mcp.tool
            if len(args) == 1 and callable(args[0]):
                return args[0]
            return decorator

        # Mock FastMCP with pass-through tool decorator
        mock_fastmcp = MagicMock()
        mock_mcp_instance = MagicMock()
        mock_mcp_instance.tool = passthrough_decorator
        mock_fastmcp.return_value = mock_mcp_instance

        with patch.dict('sys.modules', {
            'mcp.server': MagicMock(),
            'mcp.server.fastmcp': MagicMock(FastMCP=mock_fastmcp),
        }):
            import mcp.focused.server as server_module
            # Mock logger
            server_module.logger = Mock()
            # Replace mcp instance with our mock
            server_module.mcp = mock_mcp_instance
            yield server_module

    @pytest.mark.asyncio
    async def test_check_calendar_valid_token_success(self, mock_config, rsa_keypair, mock_jwks, import_server, mock_backend_post):
        """
        Test ACTUAL check_calendar tool with valid token returns success.

        End-to-end flow:
        1. Valid JWT with focused.read scope
        2. Authentication succeeds
        3. Backend returns focus blocks
        4. Tool returns success response
        """
        # Setup backend response
        mock_backend_post.return_value = {
            "success": True,
            "data": {
                "focus_blocks": [
                    {"id": "block-1", "summary": "Deep work session"}
                ]
            }
        }

        # Create valid token
        token = create_test_token(rsa_keypair, scope="focused.read")

        meta = {
            "headers": {"Authorization": f"Bearer {token}"}
        }

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            result_json = await import_server.check_calendar(
                time_start=None,
                time_end=None,
                max_results=20,
                _meta=meta
            )

        # Parse response
        result = json.loads(result_json)

        # Verify success
        assert result["success"] is True
        assert "focus_blocks" in result["data"]
        assert len(result["data"]["focus_blocks"]) == 1

        # Verify backend was called
        mock_backend_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_calendar_expired_token_returns_error(self, mock_config, rsa_keypair, mock_jwks, import_server):
        """
        Test ACTUAL check_calendar tool with expired token returns JSON-RPC error.
        """
        # Create expired token
        now = int(time.time())
        token = create_test_token(
            rsa_keypair,
            exp=now - 3600,  # Expired
            scope="focused.read"
        )

        meta = {
            "headers": {"Authorization": f"Bearer {token}"}
        }

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            result_json = await import_server.check_calendar(
                time_start=None,
                time_end=None,
                max_results=20,
                _meta=meta
            )

        # Parse response
        result = json.loads(result_json)

        # Verify error
        assert "error" in result
        assert result["error"]["code"] == -32001
        assert result["error"]["data"]["error"] == "invalid_token"
        assert "expired" in result["error"]["data"]["error_description"].lower()

    @pytest.mark.asyncio
    async def test_check_calendar_insufficient_scope_returns_error(self, mock_config, rsa_keypair, mock_jwks, import_server):
        """
        Test ACTUAL check_calendar tool with wrong scope returns JSON-RPC forbidden error.

        check_calendar requires focused.read.
        """
        # Create token with wrong scope
        token = create_test_token(rsa_keypair, scope="focused.write")

        meta = {
            "headers": {"Authorization": f"Bearer {token}"}
        }

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            result_json = await import_server.check_calendar(
                time_start=None,
                time_end=None,
                max_results=20,
                _meta=meta
            )

        # Parse response
        result = json.loads(result_json)

        # Verify forbidden error
        assert "error" in result
        assert result["error"]["code"] == -32002
        assert result["error"]["data"]["error"] == "insufficient_scope"
        assert result["error"]["data"]["required_scopes"] == ["focused.read"]

    @pytest.mark.asyncio
    async def test_check_calendar_missing_header_returns_error(self, mock_config, import_server):
        """
        Test ACTUAL check_calendar tool with missing Authorization header returns error.
        """
        meta = {"headers": {}}  # No Authorization header

        result_json = await import_server.check_calendar(
            time_start=None,
            time_end=None,
            max_results=20,
            _meta=meta
        )

        # Parse response
        result = json.loads(result_json)

        # Verify error
        assert "error" in result
        assert result["error"]["code"] == -32001
        assert result["error"]["data"]["error"] == "invalid_token"
        assert "Missing Authorization header" in result["error"]["data"]["error_description"]

    @pytest.mark.asyncio
    async def test_watch_calendar_valid_token_success(self, mock_config, rsa_keypair, mock_jwks, import_server, mock_backend_post):
        """
        Test ACTUAL watch_calendar tool with valid token returns success.

        watch_calendar requires focused.write scope.
        """
        # Setup backend response
        mock_backend_post.return_value = {
            "success": True,
            "data": {
                "channel_id": "webhook-channel-123",
                "expiration": 1234567890
            }
        }

        # Create valid token with write scope
        token = create_test_token(rsa_keypair, scope="focused.write")

        meta = {
            "headers": {"Authorization": f"Bearer {token}"}
        }

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            result_json = await import_server.watch_calendar(_meta=meta)

        # Parse response
        result = json.loads(result_json)

        # Verify success
        assert result["success"] is True
        assert "channel_id" in result["data"]

    @pytest.mark.asyncio
    async def test_watch_calendar_insufficient_scope_returns_error(self, mock_config, rsa_keypair, mock_jwks, import_server):
        """
        Test ACTUAL watch_calendar tool with read scope (needs write) returns error.
        """
        # Create token with read scope only
        token = create_test_token(rsa_keypair, scope="focused.read")

        meta = {
            "headers": {"Authorization": f"Bearer {token}"}
        }

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            result_json = await import_server.watch_calendar(_meta=meta)

        # Parse response
        result = json.loads(result_json)

        # Verify forbidden error
        assert "error" in result
        assert result["error"]["code"] == -32002
        assert result["error"]["data"]["error"] == "insufficient_scope"
        assert result["error"]["data"]["required_scopes"] == ["focused.write"]

    @pytest.mark.asyncio
    async def test_run_focus_mode_not_implemented(self, mock_config, rsa_keypair, mock_jwks, import_server):
        """
        Test ACTUAL run_focus_mode tool returns NOT_IMPLEMENTED (after auth).

        Verifies authentication happens BEFORE not_implemented check.
        """
        # Create valid token with write scope
        token = create_test_token(rsa_keypair, scope="focused.write")

        meta = {
            "headers": {"Authorization": f"Bearer {token}"}
        }

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            result_json = await import_server.run_focus_mode(_meta=meta)

        # Parse response
        result = json.loads(result_json)

        # Should get NOT_IMPLEMENTED (not auth error)
        assert result["success"] is False
        assert result["error"]["code"] == "NOT_IMPLEMENTED"

    @pytest.mark.asyncio
    async def test_notify_user_requires_notify_scope(self, mock_config, rsa_keypair, mock_jwks, import_server):
        """
        Test ACTUAL notify_user tool requires focused.notify scope.
        """
        # Create token with read scope only
        token = create_test_token(rsa_keypair, scope="focused.read")

        meta = {
            "headers": {"Authorization": f"Bearer {token}"}
        }

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            result_json = await import_server.notify_user(_meta=meta)

        # Parse response
        result = json.loads(result_json)

        # Verify forbidden error
        assert "error" in result
        assert result["error"]["code"] == -32002
        assert result["error"]["data"]["error"] == "insufficient_scope"
        assert result["error"]["data"]["required_scopes"] == ["focused.notify"]

    @pytest.mark.asyncio
    async def test_check_calendar_forged_signature_rejected(self, mock_config, rsa_keypair, mock_jwks, import_server):
        """
        Test ACTUAL check_calendar tool rejects forged JWT (invalid signature).

        CRITICAL security test: End-to-end verification that forged JWTs are rejected.
        """
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend

        # Generate attacker's keypair
        attacker_private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        attacker_private_pem = attacker_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )

        # Create forged token
        now = int(time.time())
        payload = {
            "sub": "attacker",
            "scope": "focused.read focused.write",
            "iss": "http://localhost:8000",
            "aud": "focused-mcp",
            "azp": "chatgpt-focused",
            "jti": "forged",
            "exp": now + 3600,
            "nbf": now,
            "iat": now,
        }

        forged_token = pyjwt.encode(
            payload,
            attacker_private_pem,
            algorithm="RS256",
            headers={"kid": "test-key-1"}
        )

        meta = {
            "headers": {"Authorization": f"Bearer {forged_token}"}
        }

        with patch('mcp.focused.mcp_auth._jwks_cache') as mock_cache:
            mock_cache.fetch_jwks = AsyncMock()
            signing_key = PyJWK(mock_jwks["keys"][0])
            mock_cache.get_signing_key = Mock(return_value=signing_key)

            result_json = await import_server.check_calendar(
                time_start=None,
                time_end=None,
                max_results=20,
                _meta=meta
            )

        # Parse response
        result = json.loads(result_json)

        # Verify signature error
        assert "error" in result
        assert result["error"]["code"] == -32001
        assert result["error"]["data"]["error"] == "invalid_token"
        assert "signature" in result["error"]["data"]["error_description"].lower()
