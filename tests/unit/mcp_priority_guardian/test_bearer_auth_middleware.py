"""
Unit tests for BearerAuthMiddleware (Increment B2-7).

Tests HTTP-layer auth compliance:
- HTTP 401 for missing, malformed, or invalid JWTs
- HTTP 403 for valid JWTs that lack required scopes
- HTTP 413 for oversized request bodies

Each test constructs a minimal ASGI scope dict and invokes the middleware
directly with a mocked inner app. For JWT cases, signs test tokens using
the same pattern as test_jwt_grace_period.py.
"""

import base64
import json
import time
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import jwt as pyjwt
from jwt import PyJWK


# =============================================================================
# JWT Signing Helpers (reused from test_jwt_grace_period.py)
# =============================================================================

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


# =============================================================================
# ASGI Test Helpers
# =============================================================================

def _make_scope(
    method: str = "POST",
    path: str = "/mcp",
    headers: list | None = None,
) -> dict:
    """Create a minimal ASGI HTTP scope."""
    return {
        "type": "http",
        "method": method,
        "path": path,
        "headers": headers or [],
    }


def _make_receive(body: bytes = b""):
    """Create a receive callable that returns a body."""
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {
                "type": "http.request",
                "body": body,
                "more_body": False,
            }
        return {"type": "http.disconnect"}

    return receive


class MockSend:
    """Mock ASGI send callable that captures responses."""

    def __init__(self):
        self.messages = []

    async def __call__(self, message):
        self.messages.append(message)

    @property
    def status(self) -> int:
        for msg in self.messages:
            if msg["type"] == "http.response.start":
                return msg.get("status", 0)
        return 0

    @property
    def headers(self) -> dict:
        for msg in self.messages:
            if msg["type"] == "http.response.start":
                return {
                    name.decode(): value.decode()
                    for name, value in msg.get("headers", [])
                }
        return {}

    @property
    def body(self) -> bytes:
        for msg in self.messages:
            if msg["type"] == "http.response.body":
                return msg.get("body", b"")
        return b""

    @property
    def body_json(self) -> dict:
        return json.loads(self.body) if self.body else {}


class MockInnerApp:
    """Mock inner ASGI app that tracks if it was called."""

    def __init__(self):
        self.called = False
        self.scope = None
        self.received_body = None
        self.received_more_body = None  # Track more_body flag

    async def __call__(self, scope, receive, send):
        self.called = True
        self.scope = scope
        # Read body to verify replay works
        msg = await receive()
        if msg["type"] == "http.request":
            self.received_body = msg.get("body", b"")
            self.received_more_body = msg.get("more_body", True)  # Default True if missing
        # Send a minimal response
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json")],
        })
        await send({
            "type": "http.response.body",
            "body": b'{"ok": true}',
        })


# =============================================================================
# Test: 401 Cases (cases 1-8)
# =============================================================================

class TestBearerAuthMiddleware401:
    """Tests for HTTP 401 responses (missing, malformed, or invalid JWTs)."""

    @pytest.mark.asyncio
    async def test_no_authorization_header_returns_401(self, mock_jwks_cache, capsys):
        """Case 1: No Authorization header → 401, reason=missing_header."""
        from mcp_server.priority_guardian.server import BearerAuthMiddleware

        middleware = BearerAuthMiddleware(MockInnerApp(), "https://pg.test.com")
        scope = _make_scope(headers=[])
        send = MockSend()

        await middleware(scope, _make_receive(), send)

        assert send.status == 401
        assert "www-authenticate" in send.headers
        assert 'error="invalid_token"' in send.headers["www-authenticate"]
        assert send.body_json["error"] == "unauthorized"
        assert send.body_json["error_description"] == "Authentication required"

        # Verify structured log event was emitted (structlog writes to stdout)
        captured = capsys.readouterr()
        assert "auth.middleware.rejected" in captured.out
        assert "missing_header" in captured.out

    @pytest.mark.asyncio
    async def test_header_not_bearer_returns_401(self, mock_jwks_cache):
        """Case 2: Authorization header not Bearer ... → 401, reason=invalid_format."""
        from mcp_server.priority_guardian.server import BearerAuthMiddleware

        middleware = BearerAuthMiddleware(MockInnerApp(), "https://pg.test.com")
        scope = _make_scope(headers=[
            (b"authorization", b"Basic dXNlcjpwYXNz"),
        ])
        send = MockSend()

        await middleware(scope, _make_receive(), send)

        assert send.status == 401
        assert 'error="invalid_token"' in send.headers["www-authenticate"]
        assert "Invalid Authorization header format" in send.body_json["error_description"]

    @pytest.mark.asyncio
    async def test_malformed_bearer_token_returns_401(self, mock_jwks_cache):
        """Case 3: Bearer <malformed> → 401, reason=invalid_token."""
        from mcp_server.priority_guardian.server import BearerAuthMiddleware

        middleware = BearerAuthMiddleware(MockInnerApp(), "https://pg.test.com")
        scope = _make_scope(headers=[
            (b"authorization", b"Bearer not-a-jwt"),
        ])
        send = MockSend()

        await middleware(scope, _make_receive(), send)

        assert send.status == 401
        assert 'error="invalid_token"' in send.headers["www-authenticate"]

    @pytest.mark.asyncio
    async def test_expired_token_returns_401(self, mock_jwks_cache, capsys):
        """Case 4: Bearer <valid-but-expired> → 401, reason=token_expired."""
        from mcp_server.priority_guardian.server import BearerAuthMiddleware

        token = _create_test_jwt(exp_offset_seconds=-60)  # Expired 60s ago
        middleware = BearerAuthMiddleware(MockInnerApp(), "https://pg.test.com")
        scope = _make_scope(headers=[
            (b"authorization", f"Bearer {token}".encode()),
        ])
        send = MockSend()

        await middleware(scope, _make_receive(), send)

        assert send.status == 401
        assert "Token expired" in send.body_json["error_description"]

        # Verify structured log event was emitted (structlog writes to stdout)
        captured = capsys.readouterr()
        assert "auth.middleware.rejected" in captured.out
        assert "token_expired" in captured.out

    @pytest.mark.asyncio
    async def test_wrong_issuer_returns_401(self, mock_jwks_cache):
        """Case 5: Bearer <valid-but-wrong-iss> → 401, reason=invalid_token."""
        from mcp_server.priority_guardian.server import BearerAuthMiddleware

        token = _create_test_jwt(iss="https://wrong-issuer.com")
        middleware = BearerAuthMiddleware(MockInnerApp(), "https://pg.test.com")
        scope = _make_scope(headers=[
            (b"authorization", f"Bearer {token}".encode()),
        ])
        send = MockSend()

        await middleware(scope, _make_receive(), send)

        assert send.status == 401
        assert 'error="invalid_token"' in send.headers["www-authenticate"]

    @pytest.mark.asyncio
    async def test_wrong_audience_returns_401(self, mock_jwks_cache):
        """Case 6: Bearer <valid-but-wrong-aud> → 401, reason=invalid_token."""
        from mcp_server.priority_guardian.server import BearerAuthMiddleware

        token = _create_test_jwt(aud="https://wrong-audience.com")
        middleware = BearerAuthMiddleware(MockInnerApp(), "https://pg.test.com")
        scope = _make_scope(headers=[
            (b"authorization", f"Bearer {token}".encode()),
        ])
        send = MockSend()

        await middleware(scope, _make_receive(), send)

        assert send.status == 401
        assert 'error="invalid_token"' in send.headers["www-authenticate"]

    @pytest.mark.asyncio
    async def test_discovery_endpoint_passes_through(self, mock_jwks_cache):
        """Case 7: Path /.well-known/oauth-protected-resource → passes through."""
        from mcp_server.priority_guardian.server import BearerAuthMiddleware

        inner_app = MockInnerApp()
        middleware = BearerAuthMiddleware(inner_app, "https://pg.test.com")
        scope = _make_scope(
            method="GET",
            path="/.well-known/oauth-protected-resource",
            headers=[],  # No auth header
        )
        send = MockSend()

        await middleware(scope, _make_receive(), send)

        assert inner_app.called
        # Verify scope was passed through unchanged
        assert inner_app.scope is scope

    @pytest.mark.asyncio
    async def test_health_endpoint_passes_through(self, mock_jwks_cache):
        """Case 8: Path /health → passes through."""
        from mcp_server.priority_guardian.server import BearerAuthMiddleware

        inner_app = MockInnerApp()
        middleware = BearerAuthMiddleware(inner_app, "https://pg.test.com")
        scope = _make_scope(
            method="GET",
            path="/health",
            headers=[],  # No auth header
        )
        send = MockSend()

        await middleware(scope, _make_receive(), send)

        assert inner_app.called
        # Verify scope was passed through unchanged
        assert inner_app.scope is scope


# =============================================================================
# Test: 403 Cases (cases 9-14)
# =============================================================================

class TestBearerAuthMiddleware403:
    """Tests for HTTP 403 responses (valid JWT but insufficient scopes)."""

    @pytest.mark.asyncio
    async def test_valid_token_with_required_scope_passes_through(self, mock_jwks_cache):
        """Case 9: Valid token with required scopes → inner app called."""
        from mcp_server.priority_guardian.server import BearerAuthMiddleware

        token = _create_test_jwt(scopes="pg.access")
        inner_app = MockInnerApp()
        middleware = BearerAuthMiddleware(inner_app, "https://pg.test.com")

        body = json.dumps({
            "method": "tools/call",
            "params": {"name": "create_priority", "arguments": {}},
        }).encode()

        scope = _make_scope(headers=[
            (b"authorization", f"Bearer {token}".encode()),
        ])
        send = MockSend()

        # Mock get_tool to return a tool that requires pg.access
        with patch("mcp_server.priority_guardian.tools.get_tool") as mock_get_tool:
            mock_tool = MagicMock()
            mock_tool.required_scopes = ["pg.access"]
            mock_get_tool.return_value = mock_tool

            await middleware(scope, _make_receive(body), send)

        assert inner_app.called
        # Verify scope was passed through unchanged
        assert inner_app.scope is scope

    @pytest.mark.asyncio
    async def test_valid_token_missing_required_scope_returns_403(self, mock_jwks_cache, capsys):
        """Case 10: Valid token missing required scope → 403, reason=insufficient_scope."""
        from mcp_server.priority_guardian.server import BearerAuthMiddleware

        token = _create_test_jwt(scopes="other.scope")  # Wrong scope
        inner_app = MockInnerApp()
        middleware = BearerAuthMiddleware(inner_app, "https://pg.test.com")

        body = json.dumps({
            "method": "tools/call",
            "params": {"name": "create_priority", "arguments": {}},
        }).encode()

        scope = _make_scope(headers=[
            (b"authorization", f"Bearer {token}".encode()),
        ])
        send = MockSend()

        # Mock get_tool to return a tool that requires pg.access
        with patch("mcp_server.priority_guardian.tools.get_tool") as mock_get_tool:
            mock_tool = MagicMock()
            mock_tool.required_scopes = ["pg.access"]
            mock_get_tool.return_value = mock_tool

            await middleware(scope, _make_receive(body), send)

        assert not inner_app.called
        assert send.status == 403
        assert 'error="insufficient_scope"' in send.headers["www-authenticate"]
        assert 'scope="pg.access"' in send.headers["www-authenticate"]
        assert send.body_json["error"] == "insufficient_scope"
        assert "create_priority" in send.body_json["error_description"]
        assert send.body_json["required_scopes"] == ["pg.access"]

        # Verify structured log event with tool_name and scopes (structlog writes to stdout)
        captured = capsys.readouterr()
        assert "auth.middleware.rejected" in captured.out
        assert "insufficient_scope" in captured.out
        assert "create_priority" in captured.out

    @pytest.mark.asyncio
    async def test_unknown_tool_passes_through(self, mock_jwks_cache):
        """Case 11: Unknown tool → inner app called (FastMCP handles it)."""
        from mcp_server.priority_guardian.server import BearerAuthMiddleware

        token = _create_test_jwt(scopes="pg.access")
        inner_app = MockInnerApp()
        middleware = BearerAuthMiddleware(inner_app, "https://pg.test.com")

        body = json.dumps({
            "method": "tools/call",
            "params": {"name": "nonexistent_tool", "arguments": {}},
        }).encode()

        scope = _make_scope(headers=[
            (b"authorization", f"Bearer {token}".encode()),
        ])
        send = MockSend()

        # Mock get_tool to return None (unknown tool)
        with patch("mcp_server.priority_guardian.tools.get_tool") as mock_get_tool:
            mock_get_tool.return_value = None

            await middleware(scope, _make_receive(body), send)

        assert inner_app.called
        # Verify scope was passed through unchanged
        assert inner_app.scope is scope

    @pytest.mark.asyncio
    async def test_initialize_method_passes_through(self, mock_jwks_cache):
        """Case 12: method=initialize → inner app called, no scope check."""
        from mcp_server.priority_guardian.server import BearerAuthMiddleware

        token = _create_test_jwt(scopes="")  # No scopes
        inner_app = MockInnerApp()
        middleware = BearerAuthMiddleware(inner_app, "https://pg.test.com")

        body = json.dumps({"method": "initialize"}).encode()

        scope = _make_scope(headers=[
            (b"authorization", f"Bearer {token}".encode()),
        ])
        send = MockSend()

        await middleware(scope, _make_receive(body), send)

        assert inner_app.called
        # Verify scope was passed through unchanged
        assert inner_app.scope is scope

    @pytest.mark.asyncio
    async def test_tools_list_method_passes_through(self, mock_jwks_cache):
        """Case 13: method=tools/list → inner app called, no scope check."""
        from mcp_server.priority_guardian.server import BearerAuthMiddleware

        token = _create_test_jwt(scopes="")  # No scopes
        inner_app = MockInnerApp()
        middleware = BearerAuthMiddleware(inner_app, "https://pg.test.com")

        body = json.dumps({"method": "tools/list"}).encode()

        scope = _make_scope(headers=[
            (b"authorization", f"Bearer {token}".encode()),
        ])
        send = MockSend()

        await middleware(scope, _make_receive(body), send)

        assert inner_app.called
        # Verify scope was passed through unchanged
        assert inner_app.scope is scope

    @pytest.mark.asyncio
    async def test_malformed_json_passes_through(self, mock_jwks_cache):
        """Case 14: Malformed JSON body → inner app called (FastMCP handles it)."""
        from mcp_server.priority_guardian.server import BearerAuthMiddleware

        token = _create_test_jwt(scopes="pg.access")
        inner_app = MockInnerApp()
        middleware = BearerAuthMiddleware(inner_app, "https://pg.test.com")

        body = b"not valid json {"

        scope = _make_scope(headers=[
            (b"authorization", f"Bearer {token}".encode()),
        ])
        send = MockSend()

        await middleware(scope, _make_receive(body), send)

        assert inner_app.called
        # Verify scope was passed through unchanged
        assert inner_app.scope is scope


# =============================================================================
# Test: Body Handling Cases (cases 15-17)
# =============================================================================

class TestBearerAuthMiddlewareBodyHandling:
    """Tests for body size limits and replay."""

    @pytest.mark.asyncio
    async def test_body_exceeds_size_limit_returns_413(self, mock_jwks_cache, capsys):
        """Case 15: Body > 1 MB → HTTP 413, inner app not called."""
        from mcp_server.priority_guardian.server import BearerAuthMiddleware

        token = _create_test_jwt(scopes="pg.access")
        inner_app = MockInnerApp()
        middleware = BearerAuthMiddleware(inner_app, "https://pg.test.com")

        # Create body larger than 1 MB
        body = b"x" * (1024 * 1024 + 1)

        scope = _make_scope(headers=[
            (b"authorization", f"Bearer {token}".encode()),
        ])
        send = MockSend()

        await middleware(scope, _make_receive(body), send)

        assert not inner_app.called
        assert send.status == 413
        assert send.body_json["error"] == "payload_too_large"

        # Verify structured log event with size_bytes (structlog writes to stdout)
        captured = capsys.readouterr()
        assert "auth.middleware.rejected" in captured.out
        assert "body_too_large" in captured.out
        assert "size_bytes" in captured.out

    @pytest.mark.asyncio
    async def test_content_length_header_exceeds_limit_returns_413(self, mock_jwks_cache):
        """Pre-flight check: Content-Length > 1 MB with valid JWT → 413 without reading body."""
        from mcp_server.priority_guardian.server import BearerAuthMiddleware

        token = _create_test_jwt(scopes="pg.access")
        inner_app = MockInnerApp()
        middleware = BearerAuthMiddleware(inner_app, "https://pg.test.com")

        # Set Content-Length header to exceed limit (body itself is small)
        scope = _make_scope(headers=[
            (b"authorization", f"Bearer {token}".encode()),
            (b"content-length", b"2000000"),  # 2 MB declared
        ])
        send = MockSend()

        # Body is small - but Content-Length says it's big
        await middleware(scope, _make_receive(b"small body"), send)

        assert not inner_app.called
        assert send.status == 413
        assert send.body_json["error"] == "payload_too_large"

    @pytest.mark.asyncio
    async def test_content_length_exceeds_limit_without_auth_returns_401(self, mock_jwks_cache):
        """Content-Length > 1 MB but no auth → 401 (auth check before size check)."""
        from mcp_server.priority_guardian.server import BearerAuthMiddleware

        inner_app = MockInnerApp()
        middleware = BearerAuthMiddleware(inner_app, "https://pg.test.com")

        # Large Content-Length but no auth header
        scope = _make_scope(headers=[
            (b"content-length", b"2000000"),  # 2 MB declared, no auth
        ])
        send = MockSend()

        await middleware(scope, _make_receive(b"small body"), send)

        assert not inner_app.called
        # Auth check comes first: should be 401, not 413
        assert send.status == 401
        assert send.body_json["error"] == "unauthorized"

    @pytest.mark.asyncio
    async def test_valid_body_replayed_correctly(self, mock_jwks_cache):
        """Case 16: Valid body → body correctly replayed to inner app with more_body=False."""
        from mcp_server.priority_guardian.server import BearerAuthMiddleware

        token = _create_test_jwt(scopes="pg.access")
        inner_app = MockInnerApp()
        middleware = BearerAuthMiddleware(inner_app, "https://pg.test.com")

        body = json.dumps({"method": "initialize"}).encode()

        scope = _make_scope(headers=[
            (b"authorization", f"Bearer {token}".encode()),
        ])
        send = MockSend()

        await middleware(scope, _make_receive(body), send)

        assert inner_app.called
        assert inner_app.received_body == body
        # Verify more_body: False on replayed chunk (briefing acceptance criterion)
        assert inner_app.received_more_body is False
        # Verify scope was passed through unchanged
        assert inner_app.scope is scope

    @pytest.mark.asyncio
    async def test_empty_body_replayed_correctly(self, mock_jwks_cache):
        """Case 17: Empty body → inner app called, replayed body is empty with more_body=False."""
        from mcp_server.priority_guardian.server import BearerAuthMiddleware

        token = _create_test_jwt(scopes="pg.access")
        inner_app = MockInnerApp()
        middleware = BearerAuthMiddleware(inner_app, "https://pg.test.com")

        scope = _make_scope(headers=[
            (b"authorization", f"Bearer {token}".encode()),
        ])
        send = MockSend()

        await middleware(scope, _make_receive(b""), send)

        assert inner_app.called
        assert inner_app.received_body == b""
        # Verify more_body: False on replayed chunk
        assert inner_app.received_more_body is False
        # Verify scope was passed through unchanged
        assert inner_app.scope is scope

    @pytest.mark.asyncio
    async def test_get_request_no_body_parsing(self, mock_jwks_cache):
        """GET /mcp with valid token passes through without body parsing."""
        from mcp_server.priority_guardian.server import BearerAuthMiddleware

        token = _create_test_jwt(scopes="pg.access")
        inner_app = MockInnerApp()
        middleware = BearerAuthMiddleware(inner_app, "https://pg.test.com")

        scope = _make_scope(
            method="GET",
            headers=[(b"authorization", f"Bearer {token}".encode())],
        )
        send = MockSend()

        await middleware(scope, _make_receive(), send)

        assert inner_app.called
        assert send.status == 200

    @pytest.mark.asyncio
    async def test_delete_request_no_body_parsing(self, mock_jwks_cache):
        """DELETE /mcp with valid token passes through without body parsing."""
        from mcp_server.priority_guardian.server import BearerAuthMiddleware

        token = _create_test_jwt(scopes="pg.access")
        inner_app = MockInnerApp()
        middleware = BearerAuthMiddleware(inner_app, "https://pg.test.com")

        scope = _make_scope(
            method="DELETE",
            headers=[(b"authorization", f"Bearer {token}".encode())],
        )
        send = MockSend()

        await middleware(scope, _make_receive(), send)

        assert inner_app.called
        assert send.status == 200


# =============================================================================
# Test: Additional edge cases
# =============================================================================

class TestBearerAuthMiddlewareEdgeCases:
    """Additional edge cases for completeness."""

    @pytest.mark.asyncio
    async def test_tool_with_empty_required_scopes_passes_through(self, mock_jwks_cache):
        """Tool with empty required_scopes should pass through."""
        from mcp_server.priority_guardian.server import BearerAuthMiddleware

        token = _create_test_jwt(scopes="")  # No scopes
        inner_app = MockInnerApp()
        middleware = BearerAuthMiddleware(inner_app, "https://pg.test.com")

        body = json.dumps({
            "method": "tools/call",
            "params": {"name": "no_scope_tool", "arguments": {}},
        }).encode()

        scope = _make_scope(headers=[
            (b"authorization", f"Bearer {token}".encode()),
        ])
        send = MockSend()

        # Mock get_tool to return a tool with no required scopes
        with patch("mcp_server.priority_guardian.tools.get_tool") as mock_get_tool:
            mock_tool = MagicMock()
            mock_tool.required_scopes = []  # Empty
            mock_get_tool.return_value = mock_tool

            await middleware(scope, _make_receive(body), send)

        assert inner_app.called
        assert send.status == 200

    @pytest.mark.asyncio
    async def test_www_authenticate_contains_resource_metadata(self, mock_jwks_cache):
        """WWW-Authenticate header contains correct resource_metadata URL."""
        from mcp_server.priority_guardian.server import BearerAuthMiddleware

        middleware = BearerAuthMiddleware(MockInnerApp(), "https://pg.test.com")
        scope = _make_scope(headers=[])
        send = MockSend()

        await middleware(scope, _make_receive(), send)

        assert send.status == 401
        www_auth = send.headers["www-authenticate"]
        assert 'resource_metadata="https://pg.test.com/.well-known/oauth-protected-resource"' in www_auth

    @pytest.mark.asyncio
    async def test_get_mcp_without_auth_returns_401(self, mock_jwks_cache):
        """GET /mcp without Authorization → 401."""
        from mcp_server.priority_guardian.server import BearerAuthMiddleware

        middleware = BearerAuthMiddleware(MockInnerApp(), "https://pg.test.com")
        scope = _make_scope(method="GET", headers=[])
        send = MockSend()

        await middleware(scope, _make_receive(), send)

        assert send.status == 401

    @pytest.mark.asyncio
    async def test_delete_mcp_without_auth_returns_401(self, mock_jwks_cache):
        """DELETE /mcp without Authorization → 401."""
        from mcp_server.priority_guardian.server import BearerAuthMiddleware

        middleware = BearerAuthMiddleware(MockInnerApp(), "https://pg.test.com")
        scope = _make_scope(method="DELETE", headers=[])
        send = MockSend()

        await middleware(scope, _make_receive(), send)

        assert send.status == 401

    @pytest.mark.asyncio
    async def test_multi_scope_403_formats_correctly(self, mock_jwks_cache):
        """Tool requiring multiple scopes → 403 with space-separated scope list."""
        from mcp_server.priority_guardian.server import BearerAuthMiddleware

        token = _create_test_jwt(scopes="single.scope")  # Only one scope
        inner_app = MockInnerApp()
        middleware = BearerAuthMiddleware(inner_app, "https://pg.test.com")

        body = json.dumps({
            "method": "tools/call",
            "params": {"name": "multi_scope_tool", "arguments": {}},
        }).encode()

        scope = _make_scope(headers=[
            (b"authorization", f"Bearer {token}".encode()),
        ])
        send = MockSend()

        # Mock get_tool to return a tool that requires multiple scopes
        with patch("mcp_server.priority_guardian.tools.get_tool") as mock_get_tool:
            mock_tool = MagicMock()
            mock_tool.required_scopes = ["pg.access", "pg.admin"]  # Two scopes
            mock_get_tool.return_value = mock_tool

            await middleware(scope, _make_receive(body), send)

        assert not inner_app.called
        assert send.status == 403
        # Verify multi-scope formatting: scope="pg.access pg.admin"
        www_auth = send.headers["www-authenticate"]
        assert 'scope="pg.access pg.admin"' in www_auth
        assert send.body_json["required_scopes"] == ["pg.access", "pg.admin"]

    @pytest.mark.asyncio
    async def test_replay_receive_forwards_to_original_after_body(self, mock_jwks_cache):
        """After body is consumed, replay_receive forwards to original receive (Bug 2 regression guard)."""
        from mcp_server.priority_guardian.server import BearerAuthMiddleware

        token = _create_test_jwt(scopes="pg.access")
        middleware = BearerAuthMiddleware(MockInnerApp(), "https://pg.test.com")

        body = b'{"method": "initialize"}'

        # Track receive calls
        receive_calls = []
        original_receive = _make_receive(body)

        async def tracking_receive():
            result = await original_receive()
            receive_calls.append(result)
            return result

        # Create an inner app that calls receive() twice
        class DoubleReceiveApp:
            def __init__(self):
                self.called = False
                self.first_msg = None
                self.second_msg = None

            async def __call__(self, scope, receive, send):
                self.called = True
                self.first_msg = await receive()
                self.second_msg = await receive()
                await send({
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                })
                await send({
                    "type": "http.response.body",
                    "body": b"ok",
                })

        inner_app = DoubleReceiveApp()
        middleware = BearerAuthMiddleware(inner_app, "https://pg.test.com")

        scope = _make_scope(headers=[
            (b"authorization", f"Bearer {token}".encode()),
        ])
        send = MockSend()

        await middleware(scope, tracking_receive, send)

        assert inner_app.called
        # First receive() should return the replayed body
        assert inner_app.first_msg["type"] == "http.request"
        assert inner_app.first_msg["body"] == body
        # Second receive() should forward to original (returns http.disconnect)
        assert inner_app.second_msg["type"] == "http.disconnect"

    @pytest.mark.asyncio
    async def test_auth_header_var_untouched_on_rejection(self, mock_jwks_cache):
        """Verify auth_header_var is NOT set by BearerAuthMiddleware on rejection (Hygiene 7)."""
        from mcp_server.priority_guardian.server import BearerAuthMiddleware
        from mcp_server.priority_guardian.request_context import auth_header_var

        middleware = BearerAuthMiddleware(MockInnerApp(), "https://pg.test.com")
        scope = _make_scope(headers=[])  # No auth header → 401
        send = MockSend()

        # Verify auth_header_var is at default before call
        assert auth_header_var.get() is None

        await middleware(scope, _make_receive(), send)

        assert send.status == 401
        # Verify auth_header_var is still at default after rejection
        # (BearerAuthMiddleware does NOT set it - that's MCPContentTypeAndAcceptFixMiddleware's job)
        assert auth_header_var.get() is None
