"""
Unit tests for HeadMcpMiddleware CORS origin matching edge cases.

Tests verify CORS header behavior for matching origins, non-matching origins,
missing Origin header, and empty allowed_origins list.

Gap #9: HEAD /mcp CORS Origin Matching Edge Cases
"""

import pytest
from unittest.mock import AsyncMock


class TestHeadMcpCorsEdgeCases:
    """Tests for HeadMcpMiddleware CORS origin handling."""

    @pytest.fixture
    def mock_inner_app(self):
        """Create a mock inner app that should NOT be called."""
        return AsyncMock()

    def _build_scope(self, origin: str | None = None) -> dict:
        """Build ASGI scope for HEAD /mcp request."""
        headers = []
        if origin is not None:
            headers.append((b"origin", origin.encode("utf-8")))

        return {
            "type": "http",
            "method": "HEAD",
            "path": "/mcp",
            "headers": headers,
        }

    async def _get_response_headers(self, middleware, scope) -> dict:
        """Execute middleware and capture response headers."""
        captured_headers = {}

        async def mock_receive():
            return {"type": "http.request", "body": b""}

        async def mock_send(message):
            if message["type"] == "http.response.start":
                for name, value in message.get("headers", []):
                    captured_headers[name.decode("utf-8")] = value.decode("utf-8")

        await middleware(scope, mock_receive, mock_send)
        return captured_headers

    @pytest.mark.asyncio
    async def test_matching_origin_returns_origin(self, mock_inner_app):
        """Matching origin in allowed_origins returns that origin."""
        from mcp_server.priority_guardian.server import HeadMcpMiddleware

        middleware = HeadMcpMiddleware(
            mock_inner_app,
            allowed_origins=["https://chatgpt.com"]
        )

        scope = self._build_scope(origin="https://chatgpt.com")
        headers = await self._get_response_headers(middleware, scope)

        # Should return the matching origin
        assert headers.get("access-control-allow-origin") == "https://chatgpt.com"
        assert headers.get("vary") == "Origin"

        # Verify non-CORS headers (only need to check once)
        assert headers.get("content-type").startswith("application/json")
        assert headers.get("cache-control") == "no-store"

        # Inner app should NOT be called (middleware short-circuits)
        mock_inner_app.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_matching_origin_returns_wildcard(self, mock_inner_app):
        """Non-matching origin returns wildcard."""
        from mcp_server.priority_guardian.server import HeadMcpMiddleware

        middleware = HeadMcpMiddleware(
            mock_inner_app,
            allowed_origins=["https://chatgpt.com"]
        )

        scope = self._build_scope(origin="https://evil.com")
        headers = await self._get_response_headers(middleware, scope)

        # Should return wildcard for non-matching origin
        assert headers.get("access-control-allow-origin") == "*"
        assert headers.get("vary") == "Origin"

        # Inner app should NOT be called
        mock_inner_app.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_origin_header_returns_wildcard(self, mock_inner_app):
        """Missing Origin header returns wildcard."""
        from mcp_server.priority_guardian.server import HeadMcpMiddleware

        middleware = HeadMcpMiddleware(
            mock_inner_app,
            allowed_origins=["https://chatgpt.com"]
        )

        scope = self._build_scope(origin=None)  # No Origin header
        headers = await self._get_response_headers(middleware, scope)

        # Should return wildcard when no Origin header
        assert headers.get("access-control-allow-origin") == "*"
        assert headers.get("vary") == "Origin"

        # Inner app should NOT be called
        mock_inner_app.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_allowed_origins_returns_wildcard(self, mock_inner_app):
        """Empty allowed_origins list returns wildcard."""
        from mcp_server.priority_guardian.server import HeadMcpMiddleware

        # Test with empty list
        middleware = HeadMcpMiddleware(
            mock_inner_app,
            allowed_origins=[]
        )

        scope = self._build_scope(origin="https://chatgpt.com")
        headers = await self._get_response_headers(middleware, scope)

        # Should return wildcard when allowed_origins is empty
        assert headers.get("access-control-allow-origin") == "*"

        # Inner app should NOT be called
        mock_inner_app.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_allowed_origins_returns_wildcard(self, mock_inner_app):
        """None allowed_origins returns wildcard."""
        from mcp_server.priority_guardian.server import HeadMcpMiddleware

        # Test with None
        middleware = HeadMcpMiddleware(
            mock_inner_app,
            allowed_origins=None
        )

        scope = self._build_scope(origin="https://chatgpt.com")
        headers = await self._get_response_headers(middleware, scope)

        # Should return wildcard when allowed_origins is None
        assert headers.get("access-control-allow-origin") == "*"

        # Inner app should NOT be called
        mock_inner_app.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_mcp_passes_through_to_inner_app(self, mock_inner_app):
        """GET /mcp passes through to inner app (middleware only intercepts HEAD)."""
        from mcp_server.priority_guardian.server import HeadMcpMiddleware

        middleware = HeadMcpMiddleware(
            mock_inner_app,
            allowed_origins=["https://chatgpt.com"]
        )

        # Build scope for GET /mcp (not HEAD)
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/mcp",
            "headers": [(b"origin", b"https://chatgpt.com")],
        }

        async def mock_receive():
            return {"type": "http.request", "body": b""}

        async def mock_send(message):
            pass

        await middleware(scope, mock_receive, mock_send)

        # Inner app SHOULD be called (GET is not intercepted)
        mock_inner_app.assert_called_once()
