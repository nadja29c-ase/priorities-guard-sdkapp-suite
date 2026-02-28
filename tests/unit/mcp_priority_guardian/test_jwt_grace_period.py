"""
Unit tests for JWT grace period (leeway) behavior.

Tests verify that PyJWT leeway correctly handles:
- Tokens about to expire (should be accepted)
- Recently expired tokens within leeway (should be accepted)
- Tokens expired beyond leeway (should be rejected)

After removing the manual grace period check, leeway is the only
mechanism for clock skew tolerance.
"""

import base64
import time
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import jwt as pyjwt
from jwt import PyJWK


def _int_to_base64url(n: int, length: int) -> str:
    """Convert an integer to base64url-encoded string."""
    data = n.to_bytes(length, byteorder='big')
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


# Generate test RSA key pair at module level (reused across tests)
_private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
)
_public_key = _private_key.public_key()

# Convert to PEM for jwt encoding
_private_pem = _private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)

# Create JWK dict from public key
_public_numbers = _public_key.public_numbers()
_jwk_dict = {
    "kty": "RSA",
    "kid": "test-key-id",
    "use": "sig",
    "alg": "RS256",
    "n": _int_to_base64url(_public_numbers.n, 256),
    "e": _int_to_base64url(_public_numbers.e, 3),
}

# Create PyJWK from dict
_public_jwk = PyJWK.from_dict(_jwk_dict)


def _create_test_jwt(exp_offset_seconds: int) -> str:
    """Create a signed JWT with exp = now + exp_offset_seconds."""
    now = int(time.time())
    payload = {
        "iss": "https://www.priority-guard.com",
        "aud": "https://www.priority-guard.com",
        "sub": "test-user-123",
        "scope": "pg.access",
        "jti": "test-jti-456",
        "iat": now - 300,  # Issued 5 minutes ago
        "nbf": now - 300,  # Not before 5 minutes ago
        "exp": now + exp_offset_seconds,
    }
    return pyjwt.encode(
        payload,
        _private_pem,
        algorithm="RS256",
        headers={"kid": "test-key-id"},
    )


@pytest.fixture
def mock_jwks_cache():
    """Mock the JWKS cache to return our test public key."""
    with patch("mcp_server.priority_guardian.mcp_auth._jwks_cache") as mock_cache:
        # Mock fetch_jwks to do nothing (cache is "already populated")
        mock_cache.fetch_jwks = AsyncMock(return_value=None)
        # Mock get_signing_key to return our test public key
        mock_cache.get_signing_key = MagicMock(return_value=_public_jwk)
        yield mock_cache


class TestJWTGracePeriod:
    """Tests for JWT expiry handling with leeway."""

    @pytest.mark.asyncio
    async def test_token_25_seconds_from_expiry_accepted(self, mock_jwks_cache):
        """Token expiring in 25 seconds should be accepted."""
        from mcp_server.priority_guardian.mcp_auth import validate_jwt

        token = _create_test_jwt(exp_offset_seconds=25)

        # Should not raise - token is still valid
        result = await validate_jwt(token, correlation_id="test-corr")

        assert result["user_id"] == "test-user-123"
        assert "pg.access" in result["scopes"]

    @pytest.mark.asyncio
    async def test_token_expired_5_seconds_ago_accepted_via_leeway(self, mock_jwks_cache):
        """Token expired 5 seconds ago should be accepted via leeway."""
        from mcp_server.priority_guardian.mcp_auth import validate_jwt
        from mcp_server.priority_guardian.config import TOKEN_EXPIRY_GRACE_SECONDS

        # Verify our test assumption: leeway is at least 5 seconds
        assert TOKEN_EXPIRY_GRACE_SECONDS >= 5, "Test requires leeway >= 5 seconds"

        token = _create_test_jwt(exp_offset_seconds=-5)

        # Should not raise - within leeway window
        result = await validate_jwt(token, correlation_id="test-corr")

        assert result["user_id"] == "test-user-123"
        assert "pg.access" in result["scopes"]

    @pytest.mark.asyncio
    async def test_token_expired_beyond_leeway_rejected(self, mock_jwks_cache):
        """Token expired 60 seconds ago should be rejected (beyond 30s leeway)."""
        from mcp_server.priority_guardian.mcp_auth import validate_jwt
        import jwt

        token = _create_test_jwt(exp_offset_seconds=-60)

        # Should raise ExpiredSignatureError
        with pytest.raises(jwt.ExpiredSignatureError):
            await validate_jwt(token, correlation_id="test-corr")

    @pytest.mark.asyncio
    async def test_token_60_seconds_from_expiry_accepted(self, mock_jwks_cache):
        """Token expiring in 60 seconds should be accepted (baseline sanity check)."""
        from mcp_server.priority_guardian.mcp_auth import validate_jwt

        token = _create_test_jwt(exp_offset_seconds=60)

        # Should not raise - token is well within validity
        result = await validate_jwt(token, correlation_id="test-corr")

        assert result["user_id"] == "test-user-123"
        assert "pg.access" in result["scopes"]
