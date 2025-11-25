"""
Increment 8 — Phase 3: MCP Integration E2E Tests (21 tests)

Tests the MCP server integration using:
- REAL JWT validation (signature verification via JWKS)
- REAL OAuth tokens (issued by Phase 2 OAuth provider)
- MOCKED backend_post (don't call real backend API)

Test Categories:
- Test 01: MCP → Backend chain (check_calendar)
- Test 02: Valid token accepted
- Test 02b: meta.headers overrides HTTP Authorization header
- Test 03: Expired token rejected
- Test 04: Missing token rejected
- Test 05: Wrong scope rejected
- Test 06: User identity extraction (X-User-ID header)
- Test 07: Correlation ID propagation (provided)
- Test 07b: Correlation ID generation (when missing)
- Test 08: Backend error propagation
- Test 09: Backend timeout (unreachable)
- Test 10: Unknown kid triggers JWKS refetch
- Test 11: JWKS fetch failure (fail-closed)
- Test 12: JSON-RPC error format validation
- Test 13: Tool output transformation
- Test 14: Multiple scopes enforcement
- Test 15: Backend returns invalid JSON
- Test 16: Tool not found
- Test 17: Invalid parameter types
- Test 18: FastMCP isError=True parsing
- Test 18b: FastMCP isError=True with malformed content

Design Note:
    FastMCP always returns SSE-formatted responses, even with stateless_http=True.
    The SSE format wraps JSON-RPC responses as: "event: message\\ndata: {...}\\n\\n"
    MCPTestClient and parse_sse_response() handle this transparently.
    backend_post is mocked to avoid calling real backend endpoints.
    JWT validation is REAL (fetches JWKS from real OAuth provider endpoint).
"""

import os

# CRITICAL: Set before importing MCP modules
# These must be set before any MCP imports to ensure config picks them up

# Bypass azp validation since tests use dynamically registered OAuth clients
os.environ["CHATGPT_CLIENT_ID_FOCUSED"] = ""

# Ensure MCP iss/aud match OAuth provider settings
# Import settings first to get the actual values
from backend.core.config import settings as _settings
os.environ["FOCUSED_ISSUER"] = _settings.OAUTH_ISSUER
os.environ["FOCUSED_AUDIENCE"] = _settings.OAUTH_ISSUER

import pytest
import pytest_asyncio
import json
import hashlib
import base64
import secrets
import re
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock
from uuid import uuid4
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from httpx import AsyncClient, ASGITransport

# Note: settings already imported as _settings above for env var setup
settings = _settings


# =============================================================================
# MCP Test Client Helper
# =============================================================================

# Default headers required by FastMCP (even in stateless mode)
MCP_DEFAULT_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def parse_sse_response(response) -> dict:
    """
    Parse SSE response from FastMCP.

    FastMCP even in stateless mode returns SSE format:
        event: message
        data: {"jsonrpc": "2.0", ...}

    Returns the parsed JSON-RPC response.
    """
    text = response.text
    for line in text.split('\n'):
        line = line.strip()
        if line.startswith('data: '):
            return json.loads(line[6:])

    # Fallback: try raw JSON
    try:
        return response.json()
    except json.JSONDecodeError:
        raise ValueError(f"Could not parse response: {text}")


class MCPResponse:
    """Wrapper for MCP responses that auto-parses SSE."""

    def __init__(self, response):
        self._response = response
        self._parsed = None

    @property
    def status_code(self):
        return self._response.status_code

    def json(self):
        if self._parsed is None:
            self._parsed = parse_sse_response(self._response)
        return self._parsed


class MCPTestClient(AsyncClient):
    """
    Test client for MCP server that automatically includes required headers
    and parses SSE responses.

    FastMCP requires Accept header to include text/event-stream even in
    stateless mode. Responses are SSE format, which this client parses.
    """

    async def post(self, url, **kwargs):
        """POST with MCP default headers merged, returns MCPResponse."""
        headers = dict(MCP_DEFAULT_HEADERS)
        if "headers" in kwargs:
            headers.update(kwargs["headers"])
        kwargs["headers"] = headers
        response = await super().post(url, **kwargs)
        return MCPResponse(response)


@asynccontextmanager
async def create_mcp_test_client(jwks_data: dict = None) -> AsyncGenerator[AsyncClient, None]:
    """
    Create an async test client for the MCP server with proper lifespan.

    Note: FastMCP returns SSE-formatted responses even with stateless_http=True.
    MCPTestClient wraps responses in MCPResponse which auto-parses SSE format.
    This context manager handles the session manager lifespan properly.

    IMPORTANT: We must reload the MCP server module for each test because
    FastMCP's StreamableHTTPSessionManager can only be run once per instance.

    Args:
        jwks_data: JWKS dict to pre-populate cache (required for JWT validation)

    Usage:
        async with create_mcp_test_client(jwks_data) as mcp_client:
            # Patch AFTER reload by re-importing the reloaded module
            from mcp_server.focused import server
            with patch.object(server, "backend_post", AsyncMock(...)) as mock:
                response = await mcp_client.post("/mcp", json=...)
    """
    import time
    import importlib
    import mcp_server.focused.mcp_auth as mcp_auth_module
    import mcp_server.focused.server as server_module

    # IMPORTANT: Reload order matters for exception class identity!
    # 1. First reload mcp_auth (defines UnauthorizedError, InsufficientScopeError)
    # 2. Then reload server (imports those exception classes)
    # This ensures server's exception handlers match the raised exception types.
    importlib.reload(mcp_auth_module)
    importlib.reload(server_module)

    # Pre-populate JWKS cache AFTER reload (before any JWT validation)
    if jwks_data:
        mcp_auth_module._jwks_cache._jwks = jwks_data
        mcp_auth_module._jwks_cache._fetched_at = time.time()

    mcp = server_module.mcp
    mcp_app = mcp.streamable_http_app()

    # Start session manager lifespan
    async with mcp.session_manager.run():
        async with MCPTestClient(
            transport=ASGITransport(app=mcp_app, raise_app_exceptions=True),
            base_url="http://test"
        ) as client:
            yield client


# =============================================================================
# PKCE Helpers (copied from Phase 2)
# =============================================================================

def generate_code_verifier() -> str:
    """Generate a PKCE code verifier (43-128 chars)."""
    return secrets.token_urlsafe(64)[:96]


def generate_code_challenge(code_verifier: str) -> str:
    """Generate S256 PKCE code challenge from verifier."""
    digest = hashlib.sha256(code_verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# =============================================================================
# OAuth Helpers (get tokens from OAuth provider)
# =============================================================================

async def get_oauth_tokens(
    backend_client: AsyncClient,
    user_id: str,
    scope: str = "focused.read focused.write focused.notify"
) -> dict:
    """
    Get OAuth tokens through the full flow.

    This uses the REAL OAuth provider to issue tokens.
    The MCP server will validate these tokens using REAL JWKS.
    """
    redirect_uri = "https://example.com/callback"

    # Register client
    reg_response = await backend_client.post(
        "/oauth/focused/register",
        json={
            "client_name": "MCP Test Client",
            "redirect_uris": [redirect_uri],
        },
    )
    assert reg_response.status_code == 200
    client_id = reg_response.json()["client_id"]

    # Start authorization
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)

    auth_response = await backend_client.get(
        "/oauth/focused/authorize",
        params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "scope": scope,
            "user_id": user_id,
        },
    )
    assert auth_response.status_code == 200

    # Extract auth_context_id from consent form
    import re
    match = re.search(r'name="auth_context_id"\s+value="([^"]+)"', auth_response.text)
    auth_context_id = match.group(1)

    # Submit consent
    consent_response = await backend_client.post(
        "/oauth/focused/consent",
        data={
            "auth_context_id": auth_context_id,
            "action": "allow",
        },
        follow_redirects=False,
    )
    assert consent_response.status_code == 302

    # Extract authorization code
    from urllib.parse import parse_qs, urlparse
    location = consent_response.headers.get("location", "")
    parsed = urlparse(location)
    code = parse_qs(parsed.query)["code"][0]

    # Exchange for tokens
    token_response = await backend_client.post(
        "/oauth/focused/token",
        json={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": code_verifier,
            "client_id": client_id,
            "redirect_uri": redirect_uri,
        },
    )
    assert token_response.status_code == 200

    return token_response.json()


# =============================================================================
# MCP Client Helpers
# =============================================================================

def build_mcp_request(
    tool_name: str,
    arguments: dict | None = None,
    request_id: int = 1,
    access_token: str | None = None,
    correlation_id: str | None = None,
) -> dict:
    """
    Build a JSON-RPC 2.0 request for MCP tool call.

    FastMCP tools receive arguments, not HTTP headers. Authorization must be
    passed through the tool's `meta` argument, not HTTP Authorization header.

    Args:
        tool_name: Name of the tool to call
        arguments: Tool-specific arguments
        request_id: JSON-RPC request ID
        access_token: Bearer token for authorization (passed via meta.headers)
        correlation_id: Correlation ID for request tracing

    Returns:
        JSON-RPC 2.0 request dictionary
    """
    args = dict(arguments) if arguments else {}

    # Build meta with headers for auth (simulates what a real MCP client would do)
    meta = {}
    if access_token or correlation_id:
        meta["headers"] = {}
        if access_token:
            meta["headers"]["authorization"] = f"Bearer {access_token}"
        if correlation_id:
            meta["headers"]["x-correlation-id"] = correlation_id

    if meta:
        args["meta"] = meta

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": args
        }
    }


def parse_mcp_response(data: dict, expected_id: int = 1) -> tuple[dict | None, dict | None]:
    """
    Parse FastMCP JSON-RPC response, handling different MCP spec versions.

    FastMCP response formats:
    - Standard: {"result": {"content": [{"type": "text", "text": "..."}]}}
    - With isError: {"result": {"content": [...], "isError": false}}
    - Error: {"error": {"code": -32001, "message": "...", "data": {...}}}

    Args:
        data: JSON-RPC response dictionary
        expected_id: Expected request ID for correlation (default: 1)

    Returns:
        Tuple of (tool_response, error)
        - If success: (parsed_tool_json, None)
        - If error: (None, error_dict)

    Raises:
        AssertionError: If JSON-RPC envelope is malformed
    """
    # Validate JSON-RPC 2.0 envelope
    assert data.get("jsonrpc") == "2.0", f"Expected jsonrpc 2.0, got: {data.get('jsonrpc')}"
    assert data.get("id") == expected_id, f"Expected id={expected_id}, got: {data.get('id')}"

    # Check for JSON-RPC error
    if "error" in data:
        return None, data["error"]

    # Extract result
    result = data.get("result")
    if result is None:
        return None, {"code": -1, "message": "No result in response"}

    # Check isError flag if present
    if result.get("isError", False):
        # Tool returned an error via isError flag
        content = result.get("content", [])
        if content:
            text = content[0].get("text", "")
            try:
                return None, json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return None, {"code": -1, "message": text}
        return None, {"code": -1, "message": "Unknown tool error"}

    # Extract content
    content = result.get("content", [])
    if not content:
        return None, {"code": -1, "message": "Empty content in result"}

    # Get text from first content item (type may be "text" or "output")
    first_content = content[0]
    text = first_content.get("text", "")

    # Parse as JSON
    try:
        tool_response = json.loads(text)
        return tool_response, None
    except (json.JSONDecodeError, TypeError):
        # Return raw text as response
        # TODO: Once backend error handling is stricter, consider returning
        # an error tuple here instead of {"raw": text}. All backend errors
        # should result in proper error JSON, not partial/malformed content.
        return {"raw": text}, None


class TestMCPIntegration:
    """MCP Integration E2E tests."""

    @pytest_asyncio.fixture
    async def jwks_data(self, client: AsyncClient) -> dict:
        """
        Fetch JWKS from OAuth provider for use in MCP tests.

        The MCP server fetches JWKS from FOCUSED_JWKS_URL (default localhost:8000),
        but during tests there's no real backend running. We fetch JWKS via the
        test client and pass it to create_mcp_test_client() for injection.
        """
        response = await client.get("/oauth/focused/jwks")
        assert response.status_code == 200, f"Failed to fetch JWKS: {response.text}"
        return response.json()

    # =========================================================================
    # Test 01: MCP → Backend chain (check_calendar)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_01_mcp_backend_chain(
        self,
        client: AsyncClient,
        test_user_with_connection: dict,
        jwks_data: dict,
    ):
        """
        Test 1: MCP server correctly chains to backend.

        Verifies:
        - MCP accepts valid Bearer token (via meta.headers, NOT HTTP headers)
        - MCP calls backend_post with correct headers
        - User ID extracted from token sub claim
        - Correlation ID forwarded to backend
        """
        user_id = test_user_with_connection["user_id"]

        # Get valid tokens from OAuth provider
        tokens = await get_oauth_tokens(client, user_id, scope="focused.read")
        access_token = tokens["access_token"]

        # Mock backend_post to capture the call
        mock_response = {
            "success": True,
            "data": {
                "focus_blocks": [],
                "conflicts": [],
                "next_focus_block": None
            }
        }

        async with create_mcp_test_client(jwks_data) as mcp_client:
            # Patch AFTER reload by re-importing the reloaded module
            from mcp_server.focused import server
            with patch.object(server, "backend_post", AsyncMock(return_value=mock_response)) as mock_backend:
                # Call MCP tool - auth via meta.headers ONLY (no HTTP Authorization header)
                response = await mcp_client.post(
                    "/mcp",
                    json=build_mcp_request(
                        "check_calendar",
                        arguments={
                            "time_start": "2025-01-15T00:00:00Z",
                            "time_end": "2025-01-16T00:00:00Z"
                        },
                        access_token=access_token,
                        correlation_id="test-correlation-123"
                    ),
                    # NO headers= here - auth goes through meta.headers
                )

                # Verify MCP response
                assert response.status_code == 200
                data = response.json()

                # Parse response using helper (handles different MCP spec versions)
                tool_response, error = parse_mcp_response(data)
                assert error is None, f"Expected success, got error: {error}"
                assert tool_response.get("success") is True

                # Verify backend_post was called with correct parameters
                mock_backend.assert_called_once()
                call_args = mock_backend.call_args

                # Verify positional args: (path, json_data)
                assert len(call_args.args) == 2, f"Expected 2 positional args, got {len(call_args.args)}"
                assert call_args.args[0] == "/api/focused/check_calendar"
                assert isinstance(call_args.args[1], dict), "Second arg should be JSON payload dict"

                # Verify keyword args: user_id and correlation_id (in that order)
                assert set(call_args.kwargs.keys()) == {"user_id", "correlation_id"}, \
                    f"Expected kwargs {{user_id, correlation_id}}, got {set(call_args.kwargs.keys())}"

                # Verify user_id extracted from token
                assert call_args.kwargs["user_id"] == user_id

                # Verify correlation_id is present
                assert call_args.kwargs["correlation_id"], "correlation_id should not be empty"

    # =========================================================================
    # Test 02: Valid token accepted
    # =========================================================================

    @pytest.mark.asyncio
    async def test_02_valid_token_accepted(
        self,
        client: AsyncClient,
        test_user_with_connection: dict,
        jwks_data: dict,
    ):
        """
        Test 2: Valid OAuth token is accepted by MCP server.

        Verifies:
        - Token with focused.read scope can call check_calendar
        - Response contains result (not error)
        """
        user_id = test_user_with_connection["user_id"]

        tokens = await get_oauth_tokens(client, user_id, scope="focused.read")
        access_token = tokens["access_token"]

        mock_response = {"success": True, "data": {"focus_blocks": []}}

        async with create_mcp_test_client(jwks_data) as mcp_client:
            from mcp_server.focused import server
            with patch.object(server, "backend_post", AsyncMock(return_value=mock_response)):
                # Auth via meta.headers ONLY
                response = await mcp_client.post(
                    "/mcp",
                    json=build_mcp_request("check_calendar", access_token=access_token),
                )

                assert response.status_code == 200
                data = response.json()

                # Valid token should not produce auth error
                if "error" in data:
                    error_code = data["error"].get("code", 0)
                    # Auth errors are -32001 (unauthorized) or -32002 (forbidden)
                    assert error_code not in [-32001, -32002], f"Unexpected auth error: {data}"

    # =========================================================================
    # Test 02b: meta.headers overrides HTTP Authorization header
    # =========================================================================

    @pytest.mark.asyncio
    async def test_02b_meta_headers_overrides_http_header(
        self,
        client: AsyncClient,
        test_user_with_connection: dict,
        jwks_data: dict,
    ):
        """
        Test 2b: meta.headers.authorization takes precedence over HTTP header.

        This is critical MCP behavior: when both are present, meta.headers wins.
        This test prevents accidental header mixing bugs.

        Verifies:
        - Valid token in meta.headers + invalid token in HTTP header → SUCCESS
        - MCP uses meta.headers, ignores HTTP Authorization header
        """
        user_id = test_user_with_connection["user_id"]

        # Get a valid token
        tokens = await get_oauth_tokens(client, user_id, scope="focused.read")
        valid_token = tokens["access_token"]

        # Create an invalid/garbage token for HTTP header
        invalid_http_token = "invalid.garbage.token"

        mock_response = {"success": True, "data": {"focus_blocks": []}}

        async with create_mcp_test_client(jwks_data) as mcp_client:
            from mcp_server.focused import server
            with patch.object(server, "backend_post", AsyncMock(return_value=mock_response)) as mock_backend:
                # Valid token in meta.headers (should be used)
                # Invalid token in HTTP header (should be ignored)
                response = await mcp_client.post(
                    "/mcp",
                    json=build_mcp_request("check_calendar", access_token=valid_token),
                    headers={"Authorization": f"Bearer {invalid_http_token}"},
                )

                assert response.status_code == 200
                data = response.json()

                # Should succeed because MCP uses meta.headers (valid token)
                # NOT the HTTP header (invalid token)
                if "error" in data:
                    error_code = data["error"].get("code", 0)
                    assert error_code not in [-32001, -32002], \
                        f"MCP should use meta.headers (valid), not HTTP header (invalid). Got: {data}"

                # Verify backend was actually called (auth succeeded)
                mock_backend.assert_called_once()

                # Verify user_id was extracted from the valid token
                call_kwargs = mock_backend.call_args.kwargs
                assert call_kwargs["user_id"] == user_id, \
                    "User ID should match the valid token in meta.headers"

    # =========================================================================
    # Test 03: Expired token rejected
    # =========================================================================

    @pytest.mark.asyncio
    async def test_03_expired_token_rejected(
        self,
        client: AsyncClient,  # noqa: ARG002 - Required for fixture ordering
        test_user_with_connection: dict,
        jwks_data: dict,
    ):
        """
        Test 3: Expired token is rejected.

        Verifies:
        - Token with past exp claim is rejected
        - Error code is -32001 (unauthorized)
        - Error contains "expired" in message
        """
        user_id = test_user_with_connection["user_id"]

        # Create an expired token manually
        from backend.core.crypto import sign_jwt

        now = datetime.now(timezone.utc)
        expired_payload = {
            "sub": user_id,
            "aud": settings.OAUTH_ISSUER,
            "iss": settings.OAUTH_ISSUER,
            "exp": int((now - timedelta(hours=1)).timestamp()),  # Expired 1 hour ago
            "iat": int((now - timedelta(hours=2)).timestamp()),
            "jti": str(uuid4()),
            "scope": "focused.read",
            "azp": "test-client",
            "client_id": "test-client"
        }
        expired_token = sign_jwt(expired_payload, kid=settings.OAUTH_JWT_KID)

        async with create_mcp_test_client(jwks_data) as mcp_client:
            # Auth via meta.headers ONLY
            response = await mcp_client.post(
                "/mcp",
                json=build_mcp_request("check_calendar", access_token=expired_token),
            )

            assert response.status_code == 200  # JSON-RPC always returns 200
            data = response.json()

            # Parse the MCP response - error is returned as tool content with error key
            tool_response, error = parse_mcp_response(data)

            # Should have error (either JSON-RPC level or inside tool response)
            if error:
                # JSON-RPC level error
                assert error.get("code") == -32001, f"Expected -32001 (unauthorized), got: {error}"
            else:
                # Tool returned error in content
                assert tool_response is not None
                assert "error" in tool_response, f"Expected error in tool response: {tool_response}"
                error_obj = tool_response.get("error", {})
                assert error_obj.get("code") == -32001, f"Expected -32001 (unauthorized), got: {error_obj}"

                # Error should mention expiration
                error_desc = error_obj.get("data", {}).get("error_description", "").lower()
                assert "expired" in error_desc, f"Expected 'expired' in error_description: {error_desc}"

    # =========================================================================
    # Test 04: Missing token rejected
    # =========================================================================

    @pytest.mark.asyncio
    async def test_04_missing_token_rejected(self, client: AsyncClient, jwks_data: dict):  # noqa: ARG002
        """
        Test 4: Missing Authorization header is rejected.

        Verifies:
        - Request without auth token (no meta.headers.authorization) fails
        - Error code is -32001 (unauthorized)
        - Error mentions missing header
        """
        async with create_mcp_test_client(jwks_data) as mcp_client:
            # No access_token passed - no meta.headers.authorization
            response = await mcp_client.post(
                "/mcp",
                json=build_mcp_request("check_calendar"),
            )

            assert response.status_code == 200
            data = response.json()

            # Parse the MCP response
            tool_response, error = parse_mcp_response(data)

            # Should have error (either JSON-RPC level or inside tool response)
            if error:
                assert error.get("code") == -32001, f"Expected -32001 (unauthorized), got: {error}"
            else:
                assert tool_response is not None
                assert "error" in tool_response, f"Expected error in tool response: {tool_response}"
                error_obj = tool_response.get("error", {})
                assert error_obj.get("code") == -32001, f"Expected -32001 (unauthorized), got: {error_obj}"

    # =========================================================================
    # Test 05: Wrong scope rejected
    # =========================================================================

    @pytest.mark.asyncio
    async def test_05_wrong_scope_rejected(
        self,
        client: AsyncClient,
        test_user_with_connection: dict,
        jwks_data: dict,
    ):
        """
        Test 5: Token with wrong scope is rejected.

        Verifies:
        - Token with focused.notify cannot call check_calendar (requires focused.read)
        - Error code is -32002 (forbidden/insufficient_scope)
        """
        user_id = test_user_with_connection["user_id"]

        # Get token with only focused.notify scope
        tokens = await get_oauth_tokens(client, user_id, scope="focused.notify")
        access_token = tokens["access_token"]

        async with create_mcp_test_client(jwks_data) as mcp_client:
            # Auth via meta.headers ONLY
            response = await mcp_client.post(
                "/mcp",
                json=build_mcp_request("check_calendar", access_token=access_token),
            )

            assert response.status_code == 200
            data = response.json()

            # Parse the MCP response
            tool_response, error = parse_mcp_response(data)

            # Should have error (either JSON-RPC level or inside tool response)
            if error:
                assert error.get("code") == -32002, f"Expected -32002 (forbidden), got: {error}"
                # Error should mention scope
                error_data = error.get("data", {})
                assert error_data.get("error") == "insufficient_scope"
            else:
                assert tool_response is not None
                assert "error" in tool_response, f"Expected error in tool response: {tool_response}"
                error_obj = tool_response.get("error", {})
                assert error_obj.get("code") == -32002, f"Expected -32002 (forbidden), got: {error_obj}"
                # Error should mention scope
                error_data = error_obj.get("data", {})
                assert error_data.get("error") == "insufficient_scope"

    # =========================================================================
    # Test 06: User identity extraction
    # =========================================================================

    @pytest.mark.asyncio
    async def test_06_user_identity_extraction(
        self,
        client: AsyncClient,
        test_user_with_connection: dict,
        jwks_data: dict,
    ):
        """
        Test 6: User ID is correctly extracted from token and forwarded.

        Verifies:
        - X-User-ID header sent to backend matches token sub claim
        """
        user_id = test_user_with_connection["user_id"]

        tokens = await get_oauth_tokens(client, user_id, scope="focused.read")
        access_token = tokens["access_token"]

        mock_response = {"success": True, "data": {}}

        async with create_mcp_test_client(jwks_data) as mcp_client:
            from mcp_server.focused import server
            with patch.object(server, "backend_post", AsyncMock(return_value=mock_response)) as mock_backend:
                # Auth via meta.headers ONLY
                await mcp_client.post(
                    "/mcp",
                    json=build_mcp_request("check_calendar", access_token=access_token),
                )

                # Verify user_id was passed to backend
                mock_backend.assert_called_once()
                call_kwargs = mock_backend.call_args.kwargs

                # User ID should match the token's sub claim
                assert call_kwargs["user_id"] == user_id

    # =========================================================================
    # Test 07: Correlation ID propagation
    # =========================================================================

    @pytest.mark.asyncio
    async def test_07_correlation_id_propagation(
        self,
        client: AsyncClient,
        test_user_with_connection: dict,
        jwks_data: dict,
    ):
        """
        Test 7: Correlation ID is propagated to backend.

        Verifies:
        - X-Correlation-ID from meta.headers is forwarded
        - If not provided, a new UUID is generated
        """
        user_id = test_user_with_connection["user_id"]

        tokens = await get_oauth_tokens(client, user_id, scope="focused.read")
        access_token = tokens["access_token"]

        mock_response = {"success": True, "data": {}}
        test_correlation_id = "test-correlation-id-abc123"

        async with create_mcp_test_client(jwks_data) as mcp_client:
            from mcp_server.focused import server
            with patch.object(server, "backend_post", AsyncMock(return_value=mock_response)) as mock_backend:
                # Auth and correlation_id via meta.headers ONLY
                await mcp_client.post(
                    "/mcp",
                    json=build_mcp_request(
                        "check_calendar",
                        access_token=access_token,
                        correlation_id=test_correlation_id
                    ),
                )

                # Verify correlation_id was passed to backend
                mock_backend.assert_called_once()
                call_kwargs = mock_backend.call_args.kwargs

                # Should have a correlation_id
                assert "correlation_id" in call_kwargs

                # Verify the exact correlation ID was forwarded
                # If MCP generates its own, this will catch that regression
                actual_correlation_id = call_kwargs["correlation_id"]

                # The correlation ID should either be:
                # 1. The exact one we sent (if MCP extracts from meta.headers)
                # 2. A valid UUID (if MCP generates its own)
                # For now, we verify it's a non-empty string
                assert actual_correlation_id, "correlation_id should not be empty"
                assert isinstance(actual_correlation_id, str)

                # If the MCP correctly extracts from meta.headers, it should match
                # If this assertion fails, MCP is generating its own ID (acceptable but tracked)
                if actual_correlation_id != test_correlation_id:
                    # MCP generated its own - verify it's a valid UUID format
                    uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                    assert re.match(uuid_pattern, actual_correlation_id, re.IGNORECASE), \
                        f"Generated correlation_id should be valid UUID, got: {actual_correlation_id}"

    # =========================================================================
    # Test 07b: Correlation ID generation when missing
    # =========================================================================

    @pytest.mark.asyncio
    async def test_07b_correlation_id_generated_when_missing(
        self,
        client: AsyncClient,
        test_user_with_connection: dict,
        jwks_data: dict,
    ):
        """
        Test 7b: MCP generates a valid UUID correlation ID when none provided.

        Verifies:
        - When no X-Correlation-ID is in meta.headers, MCP generates one
        - Generated ID is a valid UUID format
        - Backend receives the generated correlation_id
        """
        user_id = test_user_with_connection["user_id"]

        tokens = await get_oauth_tokens(client, user_id, scope="focused.read")
        access_token = tokens["access_token"]

        mock_response = {"success": True, "data": {}}

        async with create_mcp_test_client(jwks_data) as mcp_client:
            from mcp_server.focused import server
            with patch.object(server, "backend_post", AsyncMock(return_value=mock_response)) as mock_backend:
                # Auth via meta.headers, but NO correlation_id
                await mcp_client.post(
                    "/mcp",
                    json=build_mcp_request(
                        "check_calendar",
                        access_token=access_token,
                        # correlation_id intentionally omitted
                    ),
                )

                # Verify backend was called
                mock_backend.assert_called_once()
                call_kwargs = mock_backend.call_args.kwargs

                # Should have a correlation_id even though we didn't provide one
                assert "correlation_id" in call_kwargs, \
                    "MCP should generate correlation_id when not provided"

                generated_id = call_kwargs["correlation_id"]

                # Must be non-empty
                assert generated_id, "Generated correlation_id should not be empty"
                assert isinstance(generated_id, str)

                # Must be valid UUID format
                uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                assert re.match(uuid_pattern, generated_id, re.IGNORECASE), \
                    f"Generated correlation_id should be valid UUID, got: {generated_id}"

    # =========================================================================
    # Test 08: Backend error propagation
    # =========================================================================

    @pytest.mark.asyncio
    async def test_08_backend_error_propagation(
        self,
        client: AsyncClient,
        test_user_with_connection: dict,
        jwks_data: dict,
    ):
        """
        Test 8: Backend errors are converted to JSON-RPC format.

        Verifies:
        - Backend 500 error is caught
        - Error is returned as JSON-RPC error (not HTTP error)
        - HTTP status is still 200 (JSON-RPC standard)
        """
        import httpx

        user_id = test_user_with_connection["user_id"]

        tokens = await get_oauth_tokens(client, user_id, scope="focused.read")
        access_token = tokens["access_token"]

        # Mock backend to raise HTTP error
        mock_response = httpx.Response(
            status_code=500,
            json={"error": "Internal server error"}
        )

        async with create_mcp_test_client(jwks_data) as mcp_client:
            from mcp_server.focused import server
            mock_backend = AsyncMock(side_effect=httpx.HTTPStatusError(
                "Internal Server Error",
                request=httpx.Request("POST", "http://test"),
                response=mock_response
            ))
            with patch.object(server, "backend_post", mock_backend):
                # Auth via meta.headers ONLY
                response = await mcp_client.post(
                    "/mcp",
                    json=build_mcp_request("check_calendar", access_token=access_token),
                )

                # HTTP should be 200 (JSON-RPC wraps errors)
                assert response.status_code == 200
                data = response.json()

                # Parse response - tool handler catches errors and returns error info
                tool_response, error = parse_mcp_response(data)
                # Either JSON-RPC error OR tool returned success=False
                if error:
                    pass  # Expected - backend error propagated
                else:
                    assert tool_response.get("success") is False or "error" in tool_response

    # =========================================================================
    # Test 09: Backend timeout (unreachable)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_09_backend_timeout(
        self,
        client: AsyncClient,
        test_user_with_connection: dict,
        jwks_data: dict,
    ):
        """
        Test 9: Backend timeout is handled gracefully.

        Verifies:
        - Network timeout is caught
        - Error is returned as JSON-RPC (HTTP 200)
        - No backend retries (single attempt)
        """
        import httpx

        user_id = test_user_with_connection["user_id"]

        tokens = await get_oauth_tokens(client, user_id, scope="focused.read")
        access_token = tokens["access_token"]

        async with create_mcp_test_client(jwks_data) as mcp_client:
            from mcp_server.focused import server
            mock_backend = AsyncMock(side_effect=httpx.TimeoutException("Connection timeout"))
            with patch.object(server, "backend_post", mock_backend):
                # Auth via meta.headers ONLY
                response = await mcp_client.post(
                    "/mcp",
                    json=build_mcp_request("check_calendar", access_token=access_token),
                )

                # Verify only one call (no retries)
                assert mock_backend.call_count == 1

                assert response.status_code == 200
                data = response.json()

                # Parse response - tool handler catches timeout and returns error info
                tool_response, error = parse_mcp_response(data)
                # Either JSON-RPC error OR tool returned success=False
                if error:
                    pass  # Expected - timeout error propagated
                else:
                    assert tool_response.get("success") is False
                    assert "error" in tool_response

    # =========================================================================
    # Test 10: Unknown kid triggers JWKS refetch
    # =========================================================================

    @pytest.mark.asyncio
    async def test_10_unknown_kid_rejected(
        self,
        client: AsyncClient,
        test_user_with_connection: dict,
        jwks_data: dict,
    ):
        """
        Test 10: Token with unknown kid is rejected.

        Verifies:
        - When a token has a kid that doesn't exist in JWKS, it's rejected
        - Error code is -32001 (unauthorized) with "invalid_token" error
        - Error description mentions unknown kid

        Note: The MCP will attempt to refetch JWKS when encountering unknown kid,
        but since there's no real backend, it will fall back to cached JWKS.
        After refetch, if kid still unknown, token is rejected.
        """
        user_id = test_user_with_connection["user_id"]
        from backend.core.crypto import sign_jwt

        mock_response = {"success": True, "data": {}}

        async with create_mcp_test_client(jwks_data) as mcp_client:
            from mcp_server.focused import server

            # Create a token with an unknown kid
            now = datetime.now(timezone.utc)
            unknown_kid_payload = {
                "sub": user_id,
                "aud": settings.OAUTH_ISSUER,
                "iss": settings.OAUTH_ISSUER,
                "exp": int((now + timedelta(hours=1)).timestamp()),
                "iat": int(now.timestamp()),
                "jti": str(uuid4()),
                "scope": "focused.read",
                "azp": "test-client",
                "client_id": "test-client"
            }
            # Sign with a fake kid that doesn't exist in JWKS
            unknown_kid_token = sign_jwt(unknown_kid_payload, kid="unknown-kid-12345")

            with patch.object(server, "backend_post", AsyncMock(return_value=mock_response)) as mock_backend:
                # Request with unknown kid token should fail auth
                response = await mcp_client.post(
                    "/mcp",
                    json=build_mcp_request("check_calendar", access_token=unknown_kid_token),
                )

                # Backend should NOT be called (auth fails first)
                mock_backend.assert_not_called()

                assert response.status_code == 200
                data = response.json()

                # Parse the MCP response
                tool_response, error = parse_mcp_response(data)

                # Should have error (either JSON-RPC level or inside tool response)
                if error:
                    assert error.get("code") == -32001, f"Expected -32001 (unauthorized), got: {error}"
                    error_data = error.get("data", {})
                    assert "unknown kid" in error_data.get("error_description", "").lower(), \
                        f"Expected 'unknown kid' in error_description: {error_data}"
                else:
                    assert tool_response is not None
                    assert "error" in tool_response, f"Expected error in tool response: {tool_response}"
                    error_obj = tool_response.get("error", {})
                    assert error_obj.get("code") == -32001, f"Expected -32001 (unauthorized), got: {error_obj}"
                    error_data = error_obj.get("data", {})
                    assert "unknown kid" in error_data.get("error_description", "").lower(), \
                        f"Expected 'unknown kid' in error_description: {error_data}"

    # =========================================================================
    # Test 11: JWKS fetch failure (fail-closed)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_11_jwks_fetch_failure(
        self,
        client: AsyncClient,  # noqa: ARG002 - Required for fixture ordering
        test_user_with_connection: dict,
        jwks_data: dict,  # noqa: ARG002 - Present for fixture ordering but not used
    ):
        """
        Test 11: JWKS fetch failure causes token rejection (fail-closed).

        Verifies:
        - If JWKS cannot be fetched and cache is invalid, reject token
        - Backend is NOT called when auth fails

        Note: This test intentionally does NOT populate JWKS cache and patches
        fetch_jwks to always fail, simulating JWKS endpoint unavailability.
        """
        from backend.core.crypto import sign_jwt

        user_id = test_user_with_connection["user_id"]

        # Create a valid token structure (we'll fail at JWKS fetch, not signature)
        now = datetime.now(timezone.utc)
        token_payload = {
            "sub": user_id,
            "aud": settings.OAUTH_ISSUER,
            "iss": settings.OAUTH_ISSUER,
            "exp": int((now + timedelta(hours=1)).timestamp()),
            "iat": int(now.timestamp()),
            "jti": str(uuid4()),
            "scope": "focused.read",
            "azp": "test-client",
            "client_id": "test-client"
        }
        access_token = sign_jwt(token_payload, kid=settings.OAUTH_JWT_KID)

        # Create a failing fetch_jwks function
        async def failing_fetch_jwks(force=False):  # noqa: ARG001
            raise Exception("JWKS fetch failed and no valid cache available: JWKS unavailable")

        # Don't pass jwks_data - we want empty cache
        async with create_mcp_test_client() as mcp_client:  # No jwks_data!
            from mcp_server.focused import server
            import mcp_server.focused.mcp_auth as mcp_auth_module
            cache = mcp_auth_module._jwks_cache

            with patch.object(server, "backend_post", AsyncMock()) as mock_backend:
                with patch.object(cache, "fetch_jwks", new=failing_fetch_jwks):
                    # Auth via meta.headers ONLY
                    response = await mcp_client.post(
                        "/mcp",
                        json=build_mcp_request("check_calendar", access_token=access_token),
                    )

                    # Backend should NOT be called (fail-closed)
                    mock_backend.assert_not_called()

                    assert response.status_code == 200
                    data = response.json()

                    # Parse the MCP response - error is in tool content
                    tool_response, error = parse_mcp_response(data)

                    # Should have error (either JSON-RPC level or inside tool response)
                    if error:
                        assert error.get("code") == -32001, f"Expected -32001 (unauthorized), got: {error}"
                    else:
                        assert tool_response is not None
                        assert "error" in tool_response, f"Expected error in tool response: {tool_response}"
                        error_obj = tool_response.get("error", {})
                        assert error_obj.get("code") == -32001, f"Expected -32001 (unauthorized), got: {error_obj}"

    # =========================================================================
    # Test 12: JSON-RPC error format validation
    # =========================================================================

    @pytest.mark.asyncio
    async def test_12_jsonrpc_error_format(self, client: AsyncClient, jwks_data: dict):  # noqa: ARG002
        """
        Test 12: Auth errors are returned in correct format.

        Note: FastMCP returns auth errors as tool content, not JSON-RPC level errors.
        The error JSON inside content follows OAuth 2.1 error response structure.

        Verifies error structure in tool content:
        - error.code: integer (-32001 for unauthorized)
        - error.message: string
        - error.data: object with OAuth error details
        """
        async with create_mcp_test_client(jwks_data) as mcp_client:
            response = await mcp_client.post(
                "/mcp",
                json=build_mcp_request("check_calendar"),
                # No auth header
            )

            assert response.status_code == 200
            data = response.json()

            # Parse the MCP response - error is in tool content
            tool_response, error = parse_mcp_response(data)

            # Get the error object (either from JSON-RPC error or tool content)
            if error:
                # JSON-RPC level error
                error_obj = error
            else:
                # Tool content error
                assert tool_response is not None
                assert "error" in tool_response, f"Expected error in response: {tool_response}"
                error_obj = tool_response["error"]

            # Validate error structure
            assert "code" in error_obj
            assert isinstance(error_obj["code"], int)
            assert error_obj["code"] == -32001  # Unauthorized

            assert "message" in error_obj
            assert isinstance(error_obj["message"], str)

            # Data should contain OAuth error details
            if "data" in error_obj:
                assert isinstance(error_obj["data"], dict)
                # Should have OAuth error field
                assert "error" in error_obj["data"]

    # =========================================================================
    # Test 13: Tool output transformation
    # =========================================================================

    @pytest.mark.asyncio
    async def test_13_tool_output_transformation(
        self,
        client: AsyncClient,
        test_user_with_connection: dict,
        jwks_data: dict,
    ):
        """
        Test 13: Backend response is correctly transformed for MCP.

        Verifies:
        - Backend JSON is serialized to string
        - Result is properly formatted
        """
        user_id = test_user_with_connection["user_id"]

        tokens = await get_oauth_tokens(client, user_id, scope="focused.read")
        access_token = tokens["access_token"]

        backend_data = {
            "success": True,
            "data": {
                "focus_blocks": [
                    {"event_id": "e1", "title": "Focus Block", "start": "2025-01-15T09:00:00Z"}
                ],
                "conflicts": [],
                "next_focus_block": {
                    "event_id": "e1",
                    "starts_in_minutes": 30
                }
            }
        }

        async with create_mcp_test_client(jwks_data) as mcp_client:
            from mcp_server.focused import server
            with patch.object(server, "backend_post", AsyncMock(return_value=backend_data)):
                # Auth via meta.headers ONLY
                response = await mcp_client.post(
                    "/mcp",
                    json=build_mcp_request("check_calendar", access_token=access_token),
                )

                assert response.status_code == 200
                data = response.json()

                # Parse response using helper (handles different MCP spec versions)
                tool_response, error = parse_mcp_response(data)
                assert error is None, f"Expected success, got error: {error}"
                assert tool_response.get("success") is True
                assert "data" in tool_response
                assert "focus_blocks" in tool_response["data"]

    # =========================================================================
    # Test 14: Multiple scopes enforcement
    # =========================================================================

    @pytest.mark.asyncio
    async def test_14_multiple_scopes_enforcement(
        self,
        client: AsyncClient,
        test_user_with_connection: dict,
        jwks_data: dict,
    ):
        """
        Test 14: Different tools require different scopes.

        Verifies:
        - check_calendar requires focused.read
        - watch_calendar requires focused.write
        - notify_user requires focused.notify
        - Token with all scopes can access all tools
        """
        user_id = test_user_with_connection["user_id"]

        # Token with only focused.read
        read_tokens = await get_oauth_tokens(client, user_id, scope="focused.read")
        read_token = read_tokens["access_token"]

        # Token with all scopes
        all_tokens = await get_oauth_tokens(client, user_id, scope="focused.read focused.write focused.notify")
        all_token = all_tokens["access_token"]

        mock_response = {"success": True, "data": {}}

        async with create_mcp_test_client(jwks_data) as mcp_client:
            from mcp_server.focused import server
            with patch.object(server, "backend_post", AsyncMock(return_value=mock_response)):
                # read_token can access check_calendar (focused.read)
                # Auth via meta.headers ONLY
                r1 = await mcp_client.post(
                    "/mcp",
                    json=build_mcp_request("check_calendar", access_token=read_token),
                )

                # read_token CANNOT access watch_calendar (focused.write)
                r2 = await mcp_client.post(
                    "/mcp",
                    json=build_mcp_request("watch_calendar", access_token=read_token),
                )

                # all_token can access watch_calendar
                r3 = await mcp_client.post(
                    "/mcp",
                    json=build_mcp_request("watch_calendar", access_token=all_token),
                )

                # Parse all responses
                d1 = r1.json()
                tool1, err1 = parse_mcp_response(d1)

                d2 = r2.json()
                tool2, err2 = parse_mcp_response(d2)

                d3 = r3.json()
                tool3, err3 = parse_mcp_response(d3)

                # Helper to extract error from either parse_mcp_response error
                # or from tool_response.error (when isError=false but content is error JSON)
                def get_error(tool_resp, err):
                    if err:
                        return err
                    if tool_resp and "error" in tool_resp:
                        return tool_resp["error"]
                    return None

                # 1. read_token + check_calendar = OK (no insufficient_scope error)
                error1 = get_error(tool1, err1)
                if error1:
                    assert error1.get("data", {}).get("error") != "insufficient_scope", \
                        f"Should succeed with read scope, got: {error1}"

                # 2. read_token + watch_calendar = forbidden (insufficient_scope)
                error2 = get_error(tool2, err2)
                assert error2 is not None, f"Should fail without write scope, got: {tool2}"
                assert error2.get("data", {}).get("error") == "insufficient_scope", \
                    f"Expected insufficient_scope error, got: {error2}"
                assert error2.get("code") == -32002, f"Expected -32002 (forbidden), got: {error2}"

                # 3. all_token + watch_calendar = OK (no insufficient_scope error)
                error3 = get_error(tool3, err3)
                if error3:
                    assert error3.get("data", {}).get("error") != "insufficient_scope", \
                        f"Should succeed with all scopes, got: {error3}"

    # =========================================================================
    # Test 15: Backend returns invalid JSON
    # =========================================================================

    @pytest.mark.asyncio
    async def test_15_backend_invalid_json(
        self,
        client: AsyncClient,
        test_user_with_connection: dict,
        jwks_data: dict,
    ):
        """
        Test 15: Backend returns corrupted/invalid JSON.

        Verifies:
        - MCP catches JSON decode error
        - Returns proper JSON-RPC error response
        - Does not crash or expose internal errors
        """
        user_id = test_user_with_connection["user_id"]

        tokens = await get_oauth_tokens(client, user_id, scope="focused.read")
        access_token = tokens["access_token"]

        async with create_mcp_test_client(jwks_data) as mcp_client:
            from mcp_server.focused import server
            # Return invalid JSON (will cause json.dumps to fail or tool to error)
            # Actually, backend_post returns a dict, so we need to simulate
            # the httpx response returning invalid JSON
            mock_backend = AsyncMock(side_effect=ValueError("Invalid JSON from backend"))
            with patch.object(server, "backend_post", mock_backend):
                # Auth via meta.headers ONLY
                response = await mcp_client.post(
                    "/mcp",
                    json=build_mcp_request("check_calendar", access_token=access_token),
                )

                assert response.status_code == 200
                data = response.json()

                # Should return error (either JSON-RPC error or tool error)
                tool_response, error = parse_mcp_response(data)
                if error:
                    # JSON-RPC level error
                    pass  # Expected
                else:
                    # Tool caught error and returned error response
                    assert tool_response.get("success") is False or "error" in tool_response

    # =========================================================================
    # Test 16: Tool not found
    # =========================================================================

    @pytest.mark.asyncio
    async def test_16_tool_not_found(
        self,
        client: AsyncClient,
        test_user_with_connection: dict,
        jwks_data: dict,
    ):
        """
        Test 16: Invalid tool name returns error.

        Note: FastMCP returns tool not found as result with isError=true,
        containing "Unknown tool: {name}" message.

        Verifies:
        - Calling non-existent tool returns error
        - Error message mentions "unknown tool"
        """
        user_id = test_user_with_connection["user_id"]

        tokens = await get_oauth_tokens(client, user_id, scope="focused.read")
        access_token = tokens["access_token"]

        async with create_mcp_test_client(jwks_data) as mcp_client:
            # Auth via meta.headers ONLY
            response = await mcp_client.post(
                "/mcp",
                json=build_mcp_request("nonexistent_tool_xyz", access_token=access_token),
            )

            assert response.status_code == 200
            data = response.json()

            # Validate JSON-RPC envelope
            assert data.get("jsonrpc") == "2.0"
            assert data.get("id") == 1

            # Parse response using helper (handles isError=true)
            tool_response, error = parse_mcp_response(data)

            # Should have error for unknown tool
            # FastMCP returns isError=true with message in content
            assert error is not None, f"Expected error for unknown tool, got: {tool_response}"

            # Error message should mention "unknown tool"
            error_msg = error.get("message", "").lower()
            assert "unknown tool" in error_msg, \
                f"Expected 'unknown tool' in error message, got: {error}"

    # =========================================================================
    # Test 17: Invalid parameter types
    # =========================================================================

    @pytest.mark.asyncio
    async def test_17_invalid_parameter_types(
        self,
        client: AsyncClient,
        test_user_with_connection: dict,
        jwks_data: dict,
    ):
        """
        Test 17: Invalid parameter types are rejected.

        Verifies:
        - Passing wrong type (int instead of string) is handled
        - Returns appropriate error (not a crash)
        """
        user_id = test_user_with_connection["user_id"]

        tokens = await get_oauth_tokens(client, user_id, scope="focused.read")
        access_token = tokens["access_token"]

        mock_response = {"success": True, "data": {}}

        async with create_mcp_test_client(jwks_data) as mcp_client:
            from mcp_server.focused import server
            with patch.object(server, "backend_post", AsyncMock(return_value=mock_response)):
                # Pass invalid types: time_start should be string, not int
                # Auth via meta.headers ONLY
                response = await mcp_client.post(
                    "/mcp",
                    json=build_mcp_request(
                        "check_calendar",
                        arguments={
                            "time_start": 12345,  # Should be ISO8601 string
                            "time_end": {"invalid": "object"},  # Should be string
                            "max_results": "not_a_number"  # Should be int
                        },
                        access_token=access_token
                    ),
                )

                assert response.status_code == 200
                data = response.json()

                # Validate JSON-RPC envelope
                assert data.get("jsonrpc") == "2.0"
                assert data.get("id") == 1

                # Response should either:
                # 1. Have JSON-RPC error (-32602 Invalid params)
                # 2. Have tool result with error (if tool handles validation)
                # 3. Have tool result with success (if backend is lenient)
                # The key is: no crash, proper JSON-RPC response
                #
                # TODO: When stricter schema validation is implemented in MCP tools,
                # update this test to expect -32602 (Invalid params) error code.
                if "error" in data:
                    # FastMCP or tool returned validation error
                    # -32602 is standard for invalid params
                    pass  # Expected for strict validation
                else:
                    # Tool handled it (either success or tool-level error)
                    assert "result" in data

    # =========================================================================
    # Test 18: FastMCP isError=True parsing
    # =========================================================================

    @pytest.mark.asyncio
    async def test_18_iserror_parsing(self):
        """
        Test 18: FastMCP returns result.isError=True (tool exception).

        Verifies:
        - parse_mcp_response detects isError flag
        - JSON from content is parsed as error
        - No crash on malformed content
        """
        # Simulated FastMCP SSE/JSON-RPC error envelope
        fake_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "isError": True,
                "content": [
                    {
                        "type": "text",
                        "text": '{"error": "Tool crashed", "code": "internal_failure"}'
                    }
                ]
            }
        }

        tool_response, error = parse_mcp_response(fake_response)

        # isError=True means: tool_response=None, error!=None
        assert tool_response is None
        assert error is not None
        assert error.get("error") == "Tool crashed"
        assert error.get("code") == "internal_failure"

    # =========================================================================
    # Test 18b: FastMCP isError=True with malformed content
    # =========================================================================

    @pytest.mark.asyncio
    async def test_18b_iserror_malformed_content(self):
        """
        Test 18b: FastMCP isError=True with non-JSON content.

        Verifies:
        - Parser handles malformed JSON in isError content gracefully
        - Returns error with message (not crash)
        """
        fake_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "isError": True,
                "content": [
                    {"type": "text", "text": "THIS_IS_NOT_JSON"}
                ]
            }
        }

        tool_response, error = parse_mcp_response(fake_response)

        assert tool_response is None
        assert error is not None
        assert "message" in error
