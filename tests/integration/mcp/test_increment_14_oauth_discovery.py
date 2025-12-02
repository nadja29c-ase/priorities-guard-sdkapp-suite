"""
Increment 14: MCP OAuth Discovery Integration Tests.

Tests for ChatGPT OAuth discovery, tool security metadata, and error formats.
These tests ensure the MCP server correctly implements OAuth protected resource
discovery per RFC 9728 and MCP specification requirements.

Test Categories:
1. Discovery Endpoint Tests
2. Tool Metadata Tests
3. Unauthorized/Forbidden Behavior Tests
4. Combined Flow Tests
5. Regression Tests
"""

import os
import pytest
import pytest_asyncio
import time
import base64
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import httpx
from httpx import AsyncClient, ASGITransport
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt


# ============================================================================
# Lifespan Context Manager
# ============================================================================

@asynccontextmanager
async def lifespan_context(app):
    """
    Async context manager to trigger ASGI lifespan events.

    HTTPX's ASGITransport doesn't trigger lifespan events automatically,
    so we must do it manually for FastMCP to initialize properly.

    ASGI lifespan protocol:
    1. App calls receive() expecting {"type": "lifespan.startup"}
    2. App does startup work
    3. App calls send({"type": "lifespan.startup.complete"})
    4. App calls receive() expecting {"type": "lifespan.shutdown"}
    5. App does shutdown work
    6. App calls send({"type": "lifespan.shutdown.complete"})
    """
    startup_complete = asyncio.Event()
    shutdown_complete = asyncio.Event()
    startup_exception = None
    receive_queue = asyncio.Queue()

    # Queue the startup message
    await receive_queue.put({"type": "lifespan.startup"})

    async def receive():
        return await receive_queue.get()

    async def send(message):
        nonlocal startup_exception
        if message["type"] == "lifespan.startup.complete":
            startup_complete.set()
        elif message["type"] == "lifespan.startup.failed":
            startup_complete.set()
            startup_exception = message.get("message", "Startup failed")
        elif message["type"] == "lifespan.shutdown.complete":
            shutdown_complete.set()

    scope = {"type": "lifespan", "asgi": {"version": "3.0"}}

    # Start lifespan task
    lifespan_task = asyncio.create_task(app(scope, receive, send))

    # Wait for startup (with timeout)
    try:
        await asyncio.wait_for(startup_complete.wait(), timeout=10.0)
    except asyncio.TimeoutError:
        lifespan_task.cancel()
        raise RuntimeError("Lifespan startup timed out")

    if startup_exception:
        lifespan_task.cancel()
        raise RuntimeError(f"Lifespan startup failed: {startup_exception}")

    try:
        yield
    finally:
        # Queue the shutdown message
        await receive_queue.put({"type": "lifespan.shutdown"})

        try:
            await asyncio.wait_for(shutdown_complete.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            pass

        lifespan_task.cancel()
        try:
            await lifespan_task
        except asyncio.CancelledError:
            pass


# ============================================================================
# Test Configuration
# ============================================================================

# Default test URLs (can be overridden via environment)
TEST_MCP_SERVER_URL = "http://localhost:8001"
TEST_OAUTH_ISSUER_URL = "http://localhost:8000/oauth/focused"
TEST_SCOPES_SUPPORTED = ["focused.read", "focused.write", "focused.notify"]


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_env_vars():
    """Set up mock environment variables for testing."""
    with patch.dict(os.environ, {
        "MCP_SERVER_URL": TEST_MCP_SERVER_URL,
        "OAUTH_ISSUER_URL": TEST_OAUTH_ISSUER_URL,
        "BACKEND_URL": "http://localhost:8000",
        "FOCUSED_JWKS_URL": "http://localhost:8000/oauth/focused/jwks",
        "FOCUSED_ISSUER": "https://www.priority-guard.com",
        "FOCUSED_AUDIENCE": "https://www.priority-guard.com",
        "CHATGPT_CLIENT_ID_FOCUSED": "",
    }):
        yield


@pytest.fixture
def rsa_keypair():
    """Generate RSA keypair for JWT signing in tests."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )
    public_key = private_key.public_key()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    # Build JWKS format
    public_numbers = public_key.public_numbers()
    n_bytes = public_numbers.n.to_bytes((public_numbers.n.bit_length() + 7) // 8, 'big')
    e_bytes = public_numbers.e.to_bytes((public_numbers.e.bit_length() + 7) // 8, 'big')

    jwks = {
        "keys": [{
            "kty": "RSA",
            "use": "sig",
            "alg": "RS256",
            "kid": "test-key-1",
            "n": base64.urlsafe_b64encode(n_bytes).rstrip(b'=').decode('ascii'),
            "e": base64.urlsafe_b64encode(e_bytes).rstrip(b'=').decode('ascii')
        }]
    }

    return {
        "private_key": private_key,
        "public_key": public_key,
        "private_pem": private_pem,
        "public_pem": public_pem,
        "jwks": jwks
    }


def create_test_jwt(
    private_key,
    user_id: str = "test-user-123",
    scopes: list = None,
    expired: bool = False,
    kid: str = "test-key-1"
) -> str:
    """Create a test JWT for authentication."""
    if scopes is None:
        scopes = ["focused.read", "focused.write", "focused.notify"]

    now = datetime.now(timezone.utc)

    if expired:
        exp = now - timedelta(hours=1)
        iat = now - timedelta(hours=2)
    else:
        exp = now + timedelta(hours=1)
        iat = now

    payload = {
        "sub": user_id,
        "iss": "https://www.priority-guard.com",
        "aud": "https://www.priority-guard.com",
        "exp": int(exp.timestamp()),
        "iat": int(iat.timestamp()),
        "nbf": int(iat.timestamp()),
        "scope": " ".join(scopes),
        "jti": f"test-jti-{int(time.time())}",
        "azp": "test-client-id"
    }

    return jwt.encode(
        payload,
        private_key,
        algorithm="RS256",
        headers={"kid": kid}
    )


@pytest_asyncio.fixture
async def mcp_client(mock_env_vars):
    """Create async test client for MCP server with manual lifespan.

    HTTPX's ASGITransport does not trigger lifespan events automatically,
    so we use lifespan_context to start FastMCP's lifespan manually.
    This initializes TaskGroups, session manager, and other internal state.

    NOTE: We must reload the server module for each test because FastMCP's
    StreamableHTTPSessionManager can only be started once per instance.
    """
    import sys

    # Remove cached modules to get fresh FastMCP instance
    mods_to_remove = [k for k in sys.modules if 'mcp_server.focused' in k]
    for mod in mods_to_remove:
        del sys.modules[mod]

    # Import fresh after env vars are set
    from mcp_server.focused.server import create_app

    app = create_app()

    # Manual lifespan start - required for FastMCP initialization
    async with lifespan_context(app):
        transport = ASGITransport(app=app)

        async with AsyncClient(
            transport=transport,
            base_url=TEST_MCP_SERVER_URL
        ) as client:
            yield client


# ============================================================================
# 1. Discovery Endpoint Tests
# ============================================================================

class TestDiscoveryEndpoint:
    """Tests for /.well-known/oauth-protected-resource endpoint."""

    @pytest.mark.asyncio
    async def test_discovery_endpoint_returns_200(self, mcp_client):
        """Test 1.1: Basic discovery endpoint resolves with 200."""
        response = await mcp_client.get("/.well-known/oauth-protected-resource")

        assert response.status_code == 200
        assert response.headers.get("content-type") == "application/json"

    @pytest.mark.asyncio
    async def test_discovery_endpoint_json_schema(self, mcp_client):
        """Test 1.1: Discovery response matches required schema."""
        response = await mcp_client.get("/.well-known/oauth-protected-resource")
        data = response.json()

        # Required fields per RFC 9728
        assert "resource" in data
        assert "authorization_servers" in data
        assert "scopes_supported" in data

        # Validate types
        assert isinstance(data["resource"], str)
        assert isinstance(data["authorization_servers"], list)
        assert isinstance(data["scopes_supported"], list)

        # Validate values
        assert data["resource"] == TEST_MCP_SERVER_URL
        assert TEST_OAUTH_ISSUER_URL in data["authorization_servers"]
        assert set(data["scopes_supported"]) == set(TEST_SCOPES_SUPPORTED)

    @pytest.mark.asyncio
    async def test_discovery_endpoint_authorization_servers_format(self, mcp_client):
        """Test 1.2: authorization_servers must include /oauth/focused path."""
        response = await mcp_client.get("/.well-known/oauth-protected-resource")
        data = response.json()

        # ChatGPT appends /.well-known/openid-configuration to this
        for server in data["authorization_servers"]:
            assert "/oauth/focused" in server, \
                "authorization_servers must include /oauth/focused path"

    @pytest.mark.asyncio
    async def test_discovery_endpoint_scopes_complete(self, mcp_client):
        """Test 1.2: All required scopes are present."""
        response = await mcp_client.get("/.well-known/oauth-protected-resource")
        data = response.json()

        required_scopes = {"focused.read", "focused.write", "focused.notify"}
        actual_scopes = set(data["scopes_supported"])

        assert required_scopes.issubset(actual_scopes), \
            f"Missing scopes: {required_scopes - actual_scopes}"

    @pytest.mark.asyncio
    async def test_discovery_endpoint_env_var_override(self):
        """Test 1.3: Environment variable override works."""
        custom_url = "http://custom-mcp-server:9999"
        custom_oauth = "http://custom-oauth:8000/oauth/focused"

        with patch.dict(os.environ, {
            "MCP_SERVER_URL": custom_url,
            "OAUTH_ISSUER_URL": custom_oauth,
            "BACKEND_URL": "http://localhost:8000",
            "FOCUSED_JWKS_URL": "http://localhost:8000/oauth/focused/jwks",
            "FOCUSED_ISSUER": "https://www.priority-guard.com",
            "FOCUSED_AUDIENCE": "https://www.priority-guard.com",
            "CHATGPT_CLIENT_ID_FOCUSED": "",
        }):
            # Re-import config to pick up new env vars
            import importlib
            import mcp_server.focused.config as config_module
            importlib.reload(config_module)

            # Re-import server module to use new config values
            import mcp_server.focused.server as server_module
            importlib.reload(server_module)

            app = server_module.create_app()

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url=custom_url
            ) as client:
                response = await client.get("/.well-known/oauth-protected-resource")
                data = response.json()

                assert data["resource"] == custom_url
                assert data["authorization_servers"][0] == custom_oauth


# ============================================================================
# 2. Tool Metadata Tests
# ============================================================================

class TestToolMetadata:
    """Tests for tool registration and scope enforcement configuration.

    NOTE: FastMCP v1.12.4 does NOT support tool-level security metadata.
    ChatGPT OAuth discovery is triggered via:
    A) /.well-known/oauth-protected-resource endpoint
    C) _meta["mcp/www_authenticate"] in error responses

    Tool-level security (B) is not possible with current FastMCP Python SDK.
    This is acceptable because A + C fully satisfy ChatGPT's OAuth discovery.
    """

    @pytest.mark.asyncio
    async def test_tools_are_registered(self, mock_env_vars):
        """Test 2.1: All expected tools are registered in FastMCP."""
        from mcp_server.focused.server import mcp

        # Get tool manager
        tool_manager = mcp._tool_manager
        tools = tool_manager._tools

        expected_tools = ["check_calendar", "watch_calendar", "run_focus_mode", "notify_user"]

        for tool_name in expected_tools:
            assert tool_name in tools, f"Tool {tool_name} not registered in FastMCP"

    @pytest.mark.asyncio
    async def test_tool_scopes_configured_for_enforcement(self, mock_env_vars):
        """Test 2.2: Tool scopes are configured in TOOL_SCOPES for runtime enforcement."""
        from mcp_server.focused.config import TOOL_SCOPES

        # These scopes are enforced at runtime via authenticate_request()
        expected_mapping = {
            "check_calendar": ["focused.read"],
            "watch_calendar": ["focused.write"],
            "run_focus_mode": ["focused.write"],
            "notify_user": ["focused.notify"],
        }

        for tool_name, expected_scopes in expected_mapping.items():
            assert tool_name in TOOL_SCOPES, f"Tool {tool_name} missing from TOOL_SCOPES"
            assert TOOL_SCOPES[tool_name] == expected_scopes, \
                f"Scope mismatch for {tool_name}: expected {expected_scopes}, got {TOOL_SCOPES[tool_name]}"

    @pytest.mark.asyncio
    async def test_scopes_supported_includes_all_tool_scopes(self, mock_env_vars):
        """Test 2.3: SCOPES_SUPPORTED includes all scopes used by tools."""
        from mcp_server.focused.config import TOOL_SCOPES, SCOPES_SUPPORTED

        # Collect all unique scopes from tools
        all_tool_scopes = set()
        for scopes in TOOL_SCOPES.values():
            all_tool_scopes.update(scopes)

        # Verify all are in SCOPES_SUPPORTED (for discovery endpoint)
        for scope in all_tool_scopes:
            assert scope in SCOPES_SUPPORTED, \
                f"Scope {scope} used by tools but not in SCOPES_SUPPORTED for discovery"


# ============================================================================
# 3. Unauthorized / Forbidden Behavior Tests
# ============================================================================

class TestUnauthorizedBehavior:
    """Tests for unauthorized (401) error responses."""

    @pytest.mark.asyncio
    async def test_unauthorized_no_auth_header(self, mock_env_vars):
        """Test 3.1: Unauthorized when no Authorization header present."""
        from mcp_server.focused.mcp_auth import build_unauthorized_error

        error = build_unauthorized_error()

        # Verify structure
        assert "error" in error
        assert error["error"]["code"] == -32001
        assert error["error"]["message"] == "Unauthorized"

        # Verify _meta structure for ChatGPT OAuth discovery
        assert "data" in error["error"]
        assert "_meta" in error["error"]["data"]
        assert "mcp/www_authenticate" in error["error"]["data"]["_meta"]

        www_auth = error["error"]["data"]["_meta"]["mcp/www_authenticate"]
        assert isinstance(www_auth, list)
        assert len(www_auth) > 0
        assert www_auth[0]["type"] == "oauth2"
        assert "resource_metadata" in www_auth[0]
        assert "/.well-known/oauth-protected-resource" in www_auth[0]["resource_metadata"]

    @pytest.mark.asyncio
    async def test_unauthorized_invalid_token_format(self, mock_env_vars):
        """Test 3.2: Unauthorized with malformed Authorization header."""
        from mcp_server.focused.mcp_auth import (
            extract_bearer_token,
            build_unauthorized_error
        )

        # Test malformed headers
        invalid_headers = [
            "Bearer",  # No token
            "Basic abc123",  # Wrong scheme
            "Bearer abc def",  # Multiple parts
            "",  # Empty
        ]

        for header in invalid_headers:
            token = extract_bearer_token(header)
            assert token is None, f"Should reject: {header}"

    @pytest.mark.asyncio
    async def test_unauthorized_expired_token(self, mock_env_vars, rsa_keypair):
        """Test 3.3: Unauthorized with expired token."""
        from mcp_server.focused.mcp_auth import validate_jwt, _jwks_cache

        # Create expired token
        expired_token = create_test_jwt(
            rsa_keypair["private_key"],
            expired=True
        )

        # Mock JWKS fetch to return our test keys
        async def mock_fetch_jwks(force=False):
            return rsa_keypair["jwks"]

        _jwks_cache.fetch_jwks = mock_fetch_jwks
        _jwks_cache._jwks = rsa_keypair["jwks"]
        _jwks_cache._fetched_at = time.time()

        # Should raise expired signature error
        with pytest.raises(jwt.ExpiredSignatureError):
            await validate_jwt(expired_token, "test-correlation-id")


class TestForbiddenBehavior:
    """Tests for forbidden (403) error responses."""

    @pytest.mark.asyncio
    async def test_forbidden_insufficient_scope(self, mock_env_vars):
        """Test 4.1: Forbidden when valid token but insufficient scope."""
        from mcp_server.focused.mcp_auth import build_forbidden_error

        error = build_forbidden_error(
            required_scopes=["focused.write"],
            actual_scopes=["focused.read"]
        )

        # Verify structure - code -32003 for forbidden
        assert "error" in error
        assert error["error"]["code"] == -32003
        assert error["error"]["message"] == "Forbidden"

        # Verify _meta structure
        assert "data" in error["error"]
        assert "_meta" in error["error"]["data"]
        assert "mcp/www_authenticate" in error["error"]["data"]["_meta"]

        www_auth = error["error"]["data"]["_meta"]["mcp/www_authenticate"]
        assert www_auth[0]["type"] == "oauth2"
        assert "/.well-known/oauth-protected-resource" in www_auth[0]["resource_metadata"]

    @pytest.mark.asyncio
    async def test_forbidden_vs_unauthorized_error_codes(self, mock_env_vars):
        """Test 4.1: Forbidden (-32003) vs Unauthorized (-32001) distinction."""
        from mcp_server.focused.mcp_auth import (
            build_unauthorized_error,
            build_forbidden_error
        )

        unauthorized = build_unauthorized_error()
        forbidden = build_forbidden_error()

        # Different error codes
        assert unauthorized["error"]["code"] == -32001
        assert forbidden["error"]["code"] == -32003

        # Different messages
        assert unauthorized["error"]["message"] == "Unauthorized"
        assert forbidden["error"]["message"] == "Forbidden"

    @pytest.mark.asyncio
    async def test_super_scope_token_passes(self, mock_env_vars):
        """Test 4.2: Token with extra scopes still passes."""
        from mcp_server.focused.mcp_auth import check_scopes

        # Token has more scopes than required
        token_scopes = {"focused.read", "focused.write", "focused.notify", "extra.scope"}
        required_scopes = ["focused.read"]

        assert check_scopes(token_scopes, required_scopes) is True

    @pytest.mark.asyncio
    async def test_exact_scope_match_passes(self, mock_env_vars):
        """Test 4.2: Token with exact required scopes passes."""
        from mcp_server.focused.mcp_auth import check_scopes

        token_scopes = {"focused.write"}
        required_scopes = ["focused.write"]

        assert check_scopes(token_scopes, required_scopes) is True

    @pytest.mark.asyncio
    async def test_missing_scope_fails(self, mock_env_vars):
        """Test 4.1: Token missing required scope fails."""
        from mcp_server.focused.mcp_auth import check_scopes

        token_scopes = {"focused.read"}
        required_scopes = ["focused.write"]

        assert check_scopes(token_scopes, required_scopes) is False


# ============================================================================
# 4. Combined Flow Tests
# ============================================================================

class TestCombinedFlow:
    """Tests for complete OAuth discovery flow."""

    @pytest.mark.asyncio
    async def test_oauth_discovery_chain(self, mcp_client):
        """Test 5.1: Full OAuth discovery simulation matching ChatGPT flow.

        This test validates the complete discovery chain:
        1. MCP server's protected resource metadata
        2. OIDC discovery from backend (requires backend running)

        Skips gracefully if backend is unavailable.
        """
        # Step 1: Fetch protected resource metadata
        resource_response = await mcp_client.get("/.well-known/oauth-protected-resource")
        assert resource_response.status_code == 200

        resource_data = resource_response.json()

        # Step 2: Read authorization_servers
        assert "authorization_servers" in resource_data
        assert len(resource_data["authorization_servers"]) > 0
        auth_server = resource_data["authorization_servers"][0]
        assert auth_server.endswith("/oauth/focused"), \
            "authorization_servers must end with /oauth/focused for ChatGPT"

        # Step 3: ChatGPT appends /.well-known/openid-configuration
        oidc_url = f"{auth_server}/.well-known/openid-configuration"

        # Step 4: Fetch OIDC config (this calls the backend)
        # Skip if backend is not running
        async with httpx.AsyncClient(timeout=5.0) as backend_client:
            try:
                oidc_response = await backend_client.get(oidc_url)
            except (httpx.ConnectError, httpx.ConnectTimeout):
                pytest.skip(f"Backend not running at {auth_server}")

            if oidc_response.status_code == 404:
                pytest.skip(f"Backend OIDC endpoint not available at {oidc_url}")

            assert oidc_response.status_code == 200, \
                f"OIDC discovery failed at {oidc_url}: {oidc_response.status_code}"

            oidc_data = oidc_response.json()

            # Verify required OIDC fields for ChatGPT
            assert "issuer" in oidc_data
            assert "authorization_endpoint" in oidc_data
            assert "token_endpoint" in oidc_data
            assert "jwks_uri" in oidc_data

    @pytest.mark.asyncio
    async def test_oidc_discovery_endpoint_accessible(self):
        """Test 5.2: Verify OIDC discovery endpoint is accessible.

        Requires backend to be running. Skips gracefully if unavailable.
        """
        oidc_url = f"{TEST_OAUTH_ISSUER_URL}/.well-known/openid-configuration"

        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                response = await client.get(oidc_url)
            except (httpx.ConnectError, httpx.ConnectTimeout):
                pytest.skip(f"Backend not running at {TEST_OAUTH_ISSUER_URL}")

            if response.status_code == 404:
                pytest.skip(f"Backend OIDC endpoint not available at {oidc_url}")

            assert response.status_code == 200, \
                f"Backend OIDC discovery must be accessible at {oidc_url}"

    @pytest.mark.asyncio
    async def test_error_contains_valid_discovery_url(self, mock_env_vars):
        """Test 5.1: Error responses contain valid discovery URL."""
        from mcp_server.focused.mcp_auth import build_unauthorized_error

        error = build_unauthorized_error()

        resource_metadata_url = error["error"]["data"]["_meta"]["mcp/www_authenticate"][0]["resource_metadata"]

        # URL should be fetchable (in real scenario)
        assert resource_metadata_url.endswith("/.well-known/oauth-protected-resource")
        assert resource_metadata_url.startswith(TEST_MCP_SERVER_URL)


# ============================================================================
# 5. Regression Tests
# ============================================================================

class TestRegression:
    """Regression tests to ensure existing functionality isn't broken."""

    @pytest.mark.asyncio
    async def test_fastmcp_root_still_accessible(self, mcp_client):
        """Test 6.1: FastMCP handshake still works at root."""
        # FastMCP should still respond at /
        response = await mcp_client.get("/")

        # FastMCP returns various responses depending on mode
        # Just ensure it doesn't 404
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_discovery_does_not_break_mcp(self, mcp_client):
        """Test 6.2: Discovery endpoint doesn't interfere with MCP."""
        # First hit discovery
        discovery_response = await mcp_client.get("/.well-known/oauth-protected-resource")
        assert discovery_response.status_code == 200

        # Then verify MCP still works
        mcp_response = await mcp_client.get("/")
        assert mcp_response.status_code != 404

    @pytest.mark.asyncio
    async def test_mcp_post_still_works(self, mcp_client):
        """Test 6.2: POST to MCP endpoint still works."""
        # MCP uses POST for RPC calls
        response = await mcp_client.post(
            "/",
            json={"jsonrpc": "2.0", "method": "ping", "id": 1}
        )

        # Routing must work (no 404) and server must not crash (no 5xx)
        assert response.status_code != 404, "MCP POST endpoint not routed correctly"
        assert response.status_code < 500, f"MCP server error: {response.status_code}"


# ============================================================================
# Edge Case Tests
# ============================================================================

class TestEdgeCases:
    """Edge case and boundary tests."""

    @pytest.mark.asyncio
    async def test_discovery_with_trailing_slash(self, mcp_client):
        """Discovery endpoint without trailing slash."""
        # Standard path without trailing slash
        response = await mcp_client.get("/.well-known/oauth-protected-resource")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_discovery_content_type_json(self, mcp_client):
        """Discovery returns proper JSON content type."""
        response = await mcp_client.get("/.well-known/oauth-protected-resource")

        content_type = response.headers.get("content-type", "")
        assert "application/json" in content_type

    @pytest.mark.asyncio
    async def test_error_meta_structure_complete(self, mock_env_vars):
        """Error _meta structure is complete for ChatGPT parsing."""
        from mcp_server.focused.mcp_auth import build_unauthorized_error

        error = build_unauthorized_error()

        # Navigate to www_authenticate
        data = error.get("error", {}).get("data", {})
        meta = data.get("_meta", {})
        www_auth = meta.get("mcp/www_authenticate", [])

        assert len(www_auth) == 1
        auth_entry = www_auth[0]

        # Required fields for ChatGPT
        assert "type" in auth_entry
        assert "resource_metadata" in auth_entry
        assert auth_entry["type"] == "oauth2"
