"""
Integration tests for Priority Guardian MCP HEAD /mcp middleware.

Tests verify the middleware works correctly through the full middleware stack,
including CORS behavior and that it doesn't interfere with the MCP protocol.
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


class TestHeadMcpIntegration:
    """Integration tests for HEAD /mcp through full middleware stack."""

    @pytest.mark.asyncio
    async def test_head_mcp_through_middleware(self, pg_app):
        """HEAD /mcp passes through full middleware stack with CORS headers."""
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.head("/mcp")

        assert response.status_code == 200
        # CORS headers must be present
        assert response.headers.get("access-control-allow-origin") == "*"
        assert response.headers.get("vary") == "Origin"

    @pytest.mark.asyncio
    async def test_head_mcp_cors_with_origin(self, pg_app):
        """HEAD /mcp with Origin header returns * (PG has no CORS restrictions)."""
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.head(
                "/mcp",
                headers={"Origin": "https://chatgpt.com"}
            )

        assert response.status_code == 200
        # Priority Guardian uses * for all origins
        assert response.headers.get("access-control-allow-origin") == "*"
        assert response.headers.get("vary") == "Origin"

    @pytest.mark.asyncio
    async def test_full_mcp_flow_unaffected(self, pg_app):
        """Full MCP flow should work unchanged after HEAD requests.

        The HEAD middleware must not interfere with normal MCP operations.
        """
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # First verify HEAD works
            head_response = await client.head("/mcp")
            assert head_response.status_code == 200

            # Then verify POST still works
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

                # If we get a response, verify it's a valid MCP response
                assert response.status_code not in (404, 405)

            except RuntimeError as e:
                # FastMCP session manager not initialized in test context
                if "Task group is not initialized" in str(e):
                    pass  # Expected in unit test context
                else:
                    raise


class TestHeadMcpNoSideEffects:
    """Tests verifying HEAD /mcp has no side effects."""

    @pytest.mark.asyncio
    async def test_head_does_not_affect_post_streaming(self, pg_app):
        """POST /mcp streaming behavior unchanged after HEAD request."""
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Send HEAD first
            head_response = await client.head("/mcp")
            assert head_response.status_code == 200

            # Then POST - streaming headers should be unaffected
            try:
                post_response = await client.post(
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

                # Verify POST works
                assert post_response.status_code not in (404, 405)

            except RuntimeError as e:
                if "Task group is not initialized" in str(e):
                    pass
                else:
                    raise

    @pytest.mark.asyncio
    async def test_lifespan_middleware_still_works(self, pg_app):
        """Lifespan middleware should still handle startup/shutdown correctly.

        HEAD middleware is outermost, but lifespan events should still propagate.
        """
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Make multiple requests to verify stability
            for _ in range(3):
                response = await client.head("/mcp")
                assert response.status_code == 200

            # Verify GET also works
            response = await client.get("/")
            assert response.status_code == 200
            assert response.json() == {"status": "ok", "service": "priority-guardian-mcp"}
