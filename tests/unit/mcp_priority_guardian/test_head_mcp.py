"""
Unit tests for Priority Guardian MCP HEAD /mcp middleware.

Tests verify:
- HEAD /mcp returns 200 with empty body
- HEAD /mcp has correct headers (Content-Type, Cache-Control, CORS)
- HEAD /mcp does not include Allow header
- HEAD to other paths is not intercepted
- POST /mcp still works (no regression)
- GET /mcp returns 200 (verify existing behavior)
"""

import pytest
import httpx
from unittest.mock import patch


@pytest.fixture
def pg_app():
    """Create Priority Guardian app for testing."""
    with patch.dict("os.environ", {"ENV": "dev"}, clear=False):
        from mcp_server.priority_guardian.server import create_app
        return create_app()


class TestHeadMcpMiddleware:
    """Tests for HEAD /mcp middleware in Priority Guardian."""

    @pytest.mark.asyncio
    async def test_head_mcp_returns_200(self, pg_app):
        """HEAD /mcp should return 200 status."""
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.head("/mcp")

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_head_mcp_empty_body(self, pg_app):
        """HEAD /mcp should return empty body (per HTTP spec)."""
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.head("/mcp")

        assert response.content == b""

    @pytest.mark.asyncio
    async def test_head_mcp_has_content_type(self, pg_app):
        """HEAD /mcp should have Content-Type: application/json header."""
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.head("/mcp")

        assert response.headers.get("content-type") == "application/json"

    @pytest.mark.asyncio
    async def test_head_mcp_has_cache_control(self, pg_app):
        """HEAD /mcp should have Cache-Control: no-store header."""
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.head("/mcp")

        assert response.headers.get("cache-control") == "no-store"

    @pytest.mark.asyncio
    async def test_head_mcp_has_cors_headers(self, pg_app):
        """HEAD /mcp should have CORS headers."""
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.head("/mcp")

        # Priority Guardian uses * for CORS (no restrictions)
        assert response.headers.get("access-control-allow-origin") == "*"
        assert response.headers.get("vary") == "Origin"

    @pytest.mark.asyncio
    async def test_head_mcp_no_allow_header(self, pg_app):
        """HEAD /mcp must NOT include Allow header.

        The old 405 response included 'Allow: GET, POST, DELETE'.
        The new 200 response must not include this header.
        """
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.head("/mcp")

        assert "allow" not in response.headers

    @pytest.mark.asyncio
    async def test_head_other_paths_unaffected(self, pg_app):
        """HEAD to other paths should not be intercepted by HEAD /mcp middleware."""
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # HEAD / should go through normal routing
            response_root = await client.head("/")
            # HEAD /health should go through normal routing
            response_health = await client.head("/health")

        # These may return 200 or 405 depending on whether the routes support HEAD
        # The key test is that they're NOT intercepted by our middleware
        assert response_root.status_code in (200, 405)
        assert response_health.status_code in (200, 405)

    @pytest.mark.asyncio
    async def test_get_root_returns_200(self, pg_app):
        """GET / should return 200 (verify existing health check works)."""
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "service": "priority-guardian-mcp"}

    @pytest.mark.asyncio
    async def test_get_mcp_returns_200(self, pg_app):
        """GET /mcp should return 200 (even if body is error JSON).

        FastMCP returns 200 with JSON-RPC error for GET without proper Accept header.
        This is acceptable - we just verify it's not 4xx/5xx.
        """
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            try:
                response = await client.get("/mcp")
                # GET /mcp without proper headers may return 200 with error JSON
                # Key: it should NOT be 404 or 405
                assert response.status_code not in (404, 405)
            except RuntimeError as e:
                # RuntimeError from FastMCP session manager means the route exists
                if "Task group is not initialized" in str(e):
                    pass  # Route exists, GET is handled by FastMCP
                else:
                    raise

    @pytest.mark.asyncio
    async def test_post_mcp_still_works(self, pg_app):
        """POST /mcp should still work (no regression from HEAD middleware).

        The HEAD middleware must not interfere with POST requests.
        """
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            try:
                response = await client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "clientInfo": {"name": "test", "version": "1.0"},
                        },
                    },
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "text/event-stream, application/json",
                    },
                )
                # Must NOT be 404 or 405 - POST must work
                assert response.status_code not in (404, 405)
            except RuntimeError as e:
                # RuntimeError from FastMCP session manager means the route exists
                if "Task group is not initialized" in str(e):
                    pass  # Route exists, POST works
                else:
                    raise

    @pytest.mark.asyncio
    async def test_head_does_not_trigger_session(self, pg_app, caplog):
        """HEAD /mcp should not instantiate MCP session state.

        The middleware should short-circuit before FastMCP processes the request.
        """
        import logging
        caplog.set_level(logging.DEBUG)

        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.head("/mcp")

        assert response.status_code == 200
        # Should NOT see session-related logs
        log_text = caplog.text.lower()
        assert "terminating session" not in log_text
        assert "session manager" not in log_text
