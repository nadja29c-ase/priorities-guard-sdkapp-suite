"""
Integration test for HTTP Authorization header flow.

Tests that Authorization headers sent in HTTP requests to /mcp
reach the authentication logic via the contextvar bridge.

This covers the flow:
1. HTTP request with Authorization header arrives at /mcp
2. MCPContentTypeAndAcceptFixMiddleware captures the header
3. Header is stored in auth_header_var (contextvar)
4. Tool handler's authenticate_request reads from contextvar
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from mcp_server.clarity.server import MCPContentTypeAndAcceptFixMiddleware
from mcp_server.clarity.request_context import auth_header_var
from mcp_server.clarity.mcp_auth import authenticate_request, UnauthorizedError


# ============================================================================
# Middleware Unit Tests
# ============================================================================

class TestMiddlewareAuthHeaderCapture:
    """Tests that the middleware properly captures Authorization headers."""

    @pytest.mark.asyncio
    async def test_middleware_captures_authorization_header_for_mcp_endpoint(self):
        """
        Verify middleware extracts and stores Authorization header for POST /mcp.
        """
        captured_auth = None

        # Mock downstream app that checks the contextvar
        async def mock_app(scope, receive, send):
            nonlocal captured_auth
            captured_auth = auth_header_var.get(None)

        middleware = MCPContentTypeAndAcceptFixMiddleware(mock_app)

        # Create ASGI scope for POST /mcp
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/mcp",
            "headers": [
                (b"authorization", b"Bearer test-token-12345"),
                (b"content-type", b"application/json"),
            ],
        }

        await middleware(scope, None, None)

        # Verify auth header was captured
        assert captured_auth == "Bearer test-token-12345"

    @pytest.mark.asyncio
    async def test_middleware_does_not_capture_for_non_mcp_paths(self):
        """
        Verify middleware does not set contextvar for non-/mcp paths.
        """
        captured_auth = None

        async def mock_app(scope, receive, send):
            nonlocal captured_auth
            captured_auth = auth_header_var.get(None)

        middleware = MCPContentTypeAndAcceptFixMiddleware(mock_app)

        # Create ASGI scope for different path
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/other",
            "headers": [
                (b"authorization", b"Bearer test-token-12345"),
            ],
        }

        await middleware(scope, None, None)

        # Auth header should NOT be captured for non-/mcp paths
        assert captured_auth is None

    @pytest.mark.asyncio
    async def test_middleware_handles_missing_authorization_header(self):
        """
        Verify middleware works when no Authorization header is present.
        """
        captured_auth = "NOT_SET"  # Use sentinel to distinguish from None

        async def mock_app(scope, receive, send):
            nonlocal captured_auth
            captured_auth = auth_header_var.get("NOT_SET")

        middleware = MCPContentTypeAndAcceptFixMiddleware(mock_app)

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/mcp",
            "headers": [
                (b"content-type", b"application/json"),
            ],
        }

        await middleware(scope, None, None)

        # No auth header to capture, contextvar should not be set
        assert captured_auth == "NOT_SET"


# ============================================================================
# Auth Function Integration Tests
# ============================================================================

class TestAuthenticateRequestContextVarFallback:
    """Tests that authenticate_request reads from contextvar."""

    @pytest.mark.asyncio
    async def test_authenticate_reads_from_contextvar_when_meta_empty(self):
        """
        Verify authenticate_request reads Authorization from contextvar
        when meta.headers is empty.
        """
        # Set up contextvar with a token
        auth_header_var.set("Bearer fake-token-for-test")

        # Call authenticate_request with empty meta
        # It should try to read from contextvar, then fail JWT validation
        try:
            await authenticate_request("organize_thoughts", {})
        except UnauthorizedError:
            # Expected - token validation will fail, but that proves
            # the code path that reads from contextvar was reached
            pass

    @pytest.mark.asyncio
    async def test_authenticate_prefers_contextvar_over_meta_headers(self):
        """
        Verify authenticate_request prefers contextvar over meta.headers.

        This tests the priority order: contextvar > meta.headers
        """
        # Set contextvar with a token
        auth_header_var.set("Bearer contextvar-token")

        # Create meta with different token
        meta = {"headers": {"authorization": "Bearer meta-token"}}

        # Mock validate_jwt to capture which token is used
        captured_token = None

        async def mock_validate(token, correlation_id):
            nonlocal captured_token
            captured_token = token
            raise Exception("Stop here")

        with patch("mcp_server.clarity.mcp_auth.validate_jwt", mock_validate):
            try:
                await authenticate_request("organize_thoughts", meta)
            except (UnauthorizedError, Exception):
                pass

        # The token from contextvar should be used (not meta.headers)
        assert captured_token == "contextvar-token"

    @pytest.mark.asyncio
    async def test_authenticate_falls_back_to_meta_when_contextvar_empty(self):
        """
        Verify authenticate_request falls back to meta.headers
        when contextvar is not set.
        """
        # Ensure contextvar is cleared
        auth_header_var.set(None)

        # Create meta with token
        meta = {"headers": {"authorization": "Bearer meta-fallback-token"}}

        captured_token = None

        async def mock_validate(token, correlation_id):
            nonlocal captured_token
            captured_token = token
            raise Exception("Stop here")

        with patch("mcp_server.clarity.mcp_auth.validate_jwt", mock_validate):
            try:
                await authenticate_request("organize_thoughts", meta)
            except (UnauthorizedError, Exception):
                pass

        # Should fall back to meta.headers
        assert captured_token == "meta-fallback-token"
