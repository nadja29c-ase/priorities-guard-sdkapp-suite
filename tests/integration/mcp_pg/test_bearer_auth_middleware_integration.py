"""
Integration tests for BearerAuthMiddleware (Increment B2-7).

Tests verify the middleware works correctly through the full middleware stack,
including 401/403/413 responses with proper WWW-Authenticate headers.

These tests spin up the real app via create_app() and hit it with an ASGI test
client. They verify middleware behavior in the real stack - they do not test
tool execution semantics.
"""

import base64
import json
import time
import pytest
import httpx
from unittest.mock import patch, MagicMock, AsyncMock
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import jwt as pyjwt
from jwt import PyJWK


# =============================================================================
# JWT Signing Helpers (same as unit tests)
# =============================================================================

def _int_to_base64url(n: int, length: int) -> str:
    """Convert an integer to base64url-encoded string."""
    data = n.to_bytes(length, byteorder='big')
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


# Generate test RSA key pair at module level
_private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
)
_public_key = _private_key.public_key()

_private_pem = _private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)

_public_numbers = _public_key.public_numbers()
_jwk_dict = {
    "kty": "RSA",
    "kid": "test-key-id",
    "use": "sig",
    "alg": "RS256",
    "n": _int_to_base64url(_public_numbers.n, 256),
    "e": _int_to_base64url(_public_numbers.e, 3),
}

_public_jwk = PyJWK.from_dict(_jwk_dict)


def _create_test_jwt(
    exp_offset_seconds: int = 300,
    scopes: str = "pg.access",
    iss: str = "https://www.priority-guard.com",
    aud: str = "https://www.priority-guard.com",
) -> str:
    """Create a signed JWT with configurable claims."""
    now = int(time.time())
    payload = {
        "iss": iss,
        "aud": aud,
        "sub": "test-user-123",
        "scope": scopes,
        "jti": "test-jti-456",
        "iat": now - 300,
        "nbf": now - 300,
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
        mock_cache.fetch_jwks = AsyncMock(return_value=None)
        mock_cache.get_signing_key = MagicMock(return_value=_public_jwk)
        yield mock_cache


@pytest.fixture
def pg_app(mock_jwks_cache):
    """Create Priority Guardian app for testing with mocked JWKS."""
    with patch.dict("os.environ", {"ENV": "dev"}, clear=False):
        from mcp_server.priority_guardian.server import create_app
        return create_app()


# =============================================================================
# Integration Tests: 401 Responses
# =============================================================================

class TestBearerAuthMiddleware401Integration:
    """Integration tests for HTTP 401 responses through full stack."""

    @pytest.mark.asyncio
    async def test_post_mcp_without_auth_returns_401(self, pg_app):
        """POST /mcp without Authorization → 401 with WWW-Authenticate."""
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/mcp",
                json={},
                headers={"Content-Type": "application/json"},
            )

        assert response.status_code == 401
        assert "www-authenticate" in response.headers
        assert 'error="invalid_token"' in response.headers["www-authenticate"]
        data = response.json()
        assert data["error"] == "unauthorized"

    @pytest.mark.asyncio
    async def test_post_mcp_with_invalid_token_returns_401(self, pg_app):
        """POST /mcp with Bearer invalid → 401."""
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/mcp",
                json={},
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer invalid-token",
                },
            )

        assert response.status_code == 401
        assert 'error="invalid_token"' in response.headers["www-authenticate"]

    @pytest.mark.asyncio
    async def test_post_mcp_with_expired_token_returns_401(self, pg_app):
        """POST /mcp with Bearer <expired> → 401."""
        token = _create_test_jwt(exp_offset_seconds=-60)  # Expired
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/mcp",
                json={},
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
            )

        assert response.status_code == 401
        assert "Token expired" in response.json()["error_description"]

    @pytest.mark.asyncio
    async def test_get_mcp_without_auth_returns_401(self, pg_app):
        """GET /mcp without Authorization → 401 (SSE stream initiation)."""
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/mcp")

        assert response.status_code == 401
        assert "www-authenticate" in response.headers

    @pytest.mark.asyncio
    async def test_delete_mcp_without_auth_returns_401(self, pg_app):
        """DELETE /mcp without Authorization → 401 (session close)."""
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete("/mcp")

        assert response.status_code == 401
        assert "www-authenticate" in response.headers

    @pytest.mark.asyncio
    async def test_head_mcp_without_auth_returns_200(self, pg_app):
        """HEAD /mcp without Authorization → 200 (HeadMcpMiddleware short-circuits)."""
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.head("/mcp")

        assert response.status_code == 200


# =============================================================================
# Integration Tests: 403 Responses
# =============================================================================

class TestBearerAuthMiddleware403Integration:
    """Integration tests for HTTP 403 responses through full stack."""

    @pytest.mark.asyncio
    async def test_valid_token_missing_scope_returns_403(self, pg_app):
        """POST /mcp tools/call with valid JWT but missing scope → 403."""
        token = _create_test_jwt(scopes="wrong.scope")
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "create_priority",
                        "arguments": {},
                    },
                },
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
            )

        assert response.status_code == 403
        assert 'error="insufficient_scope"' in response.headers["www-authenticate"]
        data = response.json()
        assert data["error"] == "insufficient_scope"
        assert "required_scopes" in data

    # NOTE: Pass-through tests (valid token with correct scope, initialize) are
    # covered by unit tests (test_bearer_auth_middleware.py cases 9, 12, 13).
    # Integration tests verify middleware ordering in the real stack via
    # 401/403/413 tests that complete cleanly without hitting FastMCP internals.


# =============================================================================
# Integration Tests: 413 Responses
# =============================================================================

class TestBearerAuthMiddleware413Integration:
    """Integration tests for HTTP 413 responses (body size limit)."""

    @pytest.mark.asyncio
    async def test_body_exceeds_limit_returns_413(self, pg_app):
        """POST /mcp with body > 1 MB → 413."""
        token = _create_test_jwt(scopes="pg.access")
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Create body larger than 1 MB
            large_body = "x" * (1024 * 1024 + 1)
            response = await client.post(
                "/mcp",
                content=large_body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {token}",
                },
            )

        assert response.status_code == 413
        data = response.json()
        assert data["error"] == "payload_too_large"


# =============================================================================
# Integration Tests: Discovery Endpoints Unaffected
# =============================================================================

class TestDiscoveryEndpointsUnaffected:
    """Tests verifying middleware doesn't interfere with discovery endpoints."""

    @pytest.mark.asyncio
    async def test_discovery_endpoint_accessible_without_auth(self, pg_app):
        """GET /.well-known/oauth-protected-resource → 200 (no auth required)."""
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/.well-known/oauth-protected-resource")

        assert response.status_code == 200
        # Verify it's a valid discovery response
        data = response.json()
        assert "resource" in data

    @pytest.mark.asyncio
    async def test_health_endpoint_accessible_without_auth(self, pg_app):
        """GET /health → 200 (no auth required)."""
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

        assert response.status_code == 200
        assert response.text == "ok"

    @pytest.mark.asyncio
    async def test_root_endpoint_accessible_without_auth(self, pg_app):
        """GET / → 200 (no auth required)."""
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "priority-guardian-mcp"
