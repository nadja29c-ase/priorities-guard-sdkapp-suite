"""
OAuth claim validation tests using test keys.

Tests JWT validation logic with locally-issued tokens signed with test keys.
Verifies that incorrect claims fail appropriately.
"""

import time
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import jwt

from mcp_server.clarity.mcp_auth import (
    authenticate_request,
    UnauthorizedError,
    InsufficientScopeError,
)


# ============================================================================
# Test Key Generation
# ============================================================================

def generate_test_rsa_keypair():
    """Generate RSA key pair for testing."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    public_key = private_key.public_key()
    return private_key, public_key


def get_private_key_pem(private_key):
    """Get PEM-encoded private key."""
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )


def get_public_key_jwk(public_key, kid: str):
    """Convert public key to JWK format for JWKS."""
    public_numbers = public_key.public_numbers()

    # Convert integers to base64url-encoded bytes
    import base64

    def int_to_base64url(n, length):
        data = n.to_bytes(length, byteorder='big')
        return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')

    return {
        "kty": "RSA",
        "kid": kid,
        "use": "sig",
        "alg": "RS256",
        "n": int_to_base64url(public_numbers.n, 256),
        "e": int_to_base64url(public_numbers.e, 3),
    }


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def test_keys():
    """Generate test RSA key pair."""
    private_key, public_key = generate_test_rsa_keypair()
    kid = "test-key-001"
    return {
        "private_key": private_key,
        "public_key": public_key,
        "private_key_pem": get_private_key_pem(private_key),
        "jwk": get_public_key_jwk(public_key, kid),
        "kid": kid,
    }


@pytest.fixture
def valid_claims():
    """Standard valid claims for testing."""
    now = int(time.time())
    return {
        "sub": "user-123",
        "iss": "https://www.priority-guard.com",
        "aud": "https://www.priority-guard.com",
        "azp": "test-client-id",
        "scope": "clarity.write",
        "exp": now + 3600,
        "iat": now,
        "nbf": now - 10,
        "jti": "test-token-id",
    }


def create_signed_jwt(claims: dict, private_key_pem: bytes, kid: str) -> str:
    """Create a signed JWT with the given claims."""
    return jwt.encode(
        claims,
        private_key_pem,
        algorithm="RS256",
        headers={"kid": kid}
    )


def _create_mock_jwks_cache(jwk: dict):
    """Create a mock JWKS cache that returns the test key."""
    mock_cache = MagicMock()

    # Mock fetch_jwks as async
    mock_cache.fetch_jwks = AsyncMock()

    # Mock get_signing_key to return a key-like object
    mock_signing_key = MagicMock()
    # PyJWT expects the key in .key attribute
    from jwt import PyJWK
    mock_signing_key.key = PyJWK.from_dict(jwk).key

    mock_cache.get_signing_key = MagicMock(return_value=mock_signing_key)

    return mock_cache


@pytest.fixture
def mock_auth_context(test_keys):
    """Fixture that patches JWKS cache and client ID for auth tests."""
    mock_cache = _create_mock_jwks_cache(test_keys["jwk"])

    with patch("mcp_server.clarity.mcp_auth._jwks_cache", mock_cache):
        with patch("mcp_server.clarity.mcp_auth.CHATGPT_CLIENT_ID_CLARITY", "test-client-id"):
            yield


def make_auth_meta(token: str) -> dict:
    """Create meta dict with Authorization header for authenticate_request."""
    return {"headers": {"authorization": f"Bearer {token}"}}


# ============================================================================
# Tests: Valid Token
# ============================================================================

class TestValidToken:
    """Tests that valid tokens are accepted."""

    @pytest.mark.asyncio
    async def test_valid_token_passes_validation(self, test_keys, valid_claims, mock_auth_context):
        """A properly signed token with correct claims should validate."""
        token = create_signed_jwt(
            valid_claims,
            test_keys["private_key_pem"],
            test_keys["kid"]
        )

        result = await authenticate_request("organize_thoughts", make_auth_meta(token))

        assert result["user_id"] == "user-123"
        assert "clarity.write" in result["scopes"]


# ============================================================================
# Tests: Invalid Claims
# ============================================================================

class TestInvalidIssuer:
    """Tests that wrong issuer is rejected."""

    @pytest.mark.asyncio
    async def test_wrong_issuer_fails(self, test_keys, valid_claims, mock_auth_context):
        """Token with wrong issuer should fail validation."""
        claims = {**valid_claims, "iss": "https://evil.com"}
        token = create_signed_jwt(claims, test_keys["private_key_pem"], test_keys["kid"])

        with pytest.raises(UnauthorizedError):
            await authenticate_request("organize_thoughts", make_auth_meta(token))


class TestInvalidAudience:
    """Tests that wrong audience is rejected."""

    @pytest.mark.asyncio
    async def test_wrong_audience_fails(self, test_keys, valid_claims, mock_auth_context):
        """Token with wrong audience should fail validation."""
        claims = {**valid_claims, "aud": "https://wrong-audience.com"}
        token = create_signed_jwt(claims, test_keys["private_key_pem"], test_keys["kid"])

        with pytest.raises(UnauthorizedError):
            await authenticate_request("organize_thoughts", make_auth_meta(token))


class TestInvalidAzp:
    """Tests that wrong authorized party (azp) is rejected."""

    @pytest.mark.asyncio
    async def test_wrong_azp_fails(self, test_keys, valid_claims, mock_auth_context):
        """Token with wrong azp should fail validation."""
        claims = {**valid_claims, "azp": "wrong-client-id"}
        token = create_signed_jwt(claims, test_keys["private_key_pem"], test_keys["kid"])

        with pytest.raises(UnauthorizedError):
            await authenticate_request("organize_thoughts", make_auth_meta(token))


class TestMissingScope:
    """Tests that missing clarity.write scope is rejected."""

    @pytest.mark.asyncio
    async def test_missing_clarity_write_scope_fails(self, test_keys, valid_claims, mock_auth_context):
        """Token without clarity.write scope should be rejected at auth level."""
        claims = {**valid_claims, "scope": "focused.write"}  # Wrong scope
        token = create_signed_jwt(claims, test_keys["private_key_pem"], test_keys["kid"])

        with pytest.raises(InsufficientScopeError) as exc_info:
            await authenticate_request("organize_thoughts", make_auth_meta(token))

        assert "clarity.write" in exc_info.value.required_scopes


class TestExpiredToken:
    """Tests that expired tokens are rejected."""

    @pytest.mark.asyncio
    async def test_expired_token_fails(self, test_keys, valid_claims, mock_auth_context):
        """Expired token should fail validation."""
        claims = {**valid_claims, "exp": int(time.time()) - 3600}  # Expired 1 hour ago
        token = create_signed_jwt(claims, test_keys["private_key_pem"], test_keys["kid"])

        with pytest.raises(UnauthorizedError):
            await authenticate_request("organize_thoughts", make_auth_meta(token))


class TestInvalidSignature:
    """Tests that tokens with invalid signatures are rejected."""

    @pytest.mark.asyncio
    async def test_wrong_key_fails(self, test_keys, valid_claims, mock_auth_context):
        """Token signed with different key should fail."""
        # Generate a different key pair
        other_private, _ = generate_test_rsa_keypair()
        other_pem = get_private_key_pem(other_private)

        # Sign with different key but use original key's kid
        token = create_signed_jwt(valid_claims, other_pem, test_keys["kid"])

        with pytest.raises(UnauthorizedError):
            await authenticate_request("organize_thoughts", make_auth_meta(token))


class TestMissingKid:
    """Tests that tokens without kid in header are rejected."""

    @pytest.mark.asyncio
    async def test_missing_kid_fails(self, test_keys, valid_claims, mock_auth_context):
        """Token without kid in header should fail validation."""
        # Create token without kid in header
        token = jwt.encode(
            valid_claims,
            test_keys["private_key_pem"],
            algorithm="RS256",
            headers={}  # no kid
        )

        with pytest.raises(UnauthorizedError):
            await authenticate_request("organize_thoughts", make_auth_meta(token))
