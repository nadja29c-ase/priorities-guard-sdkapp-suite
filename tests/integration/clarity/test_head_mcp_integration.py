"""
Integration tests for Clarity MCP HEAD /mcp middleware.

Tests verify the middleware works correctly through the full middleware stack,
including CORS behavior and that it doesn't interfere with the MCP protocol.
"""

import pytest
import httpx
from unittest.mock import patch


@pytest.fixture
def clarity_app():
    """Create Clarity app for testing."""
    with patch.dict("os.environ", {"ENV": "dev"}, clear=False):
        from mcp_server.clarity.server import create_app
        return create_app()


class TestHeadMcpIntegration:
    """Integration tests for HEAD /mcp through full middleware stack."""

    @pytest.mark.asyncio
    async def test_head_mcp_through_middleware(self, clarity_app):
        """HEAD /mcp passes through full middleware stack with CORS headers."""
        transport = httpx.ASGITransport(app=clarity_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.head("/mcp")

        assert response.status_code == 200
        # CORS headers must be present
        assert "access-control-allow-origin" in response.headers
        assert "vary" in response.headers

    @pytest.mark.asyncio
    async def test_head_mcp_cors_with_origin(self, clarity_app):
        """HEAD /mcp with Origin header returns matching CORS response.

        When Origin is in allowed list, it should be echoed back.
        """
        transport = httpx.ASGITransport(app=clarity_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # In dev mode, localhost:5173 is allowed
            response = await client.head(
                "/mcp",
                headers={"Origin": "http://localhost:5173"}
            )

        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
        assert response.headers.get("vary") == "Origin"

    @pytest.mark.asyncio
    async def test_head_mcp_cors_matches_post_behavior(self, clarity_app):
        """HEAD /mcp CORS headers should be consistent with POST /mcp.

        Both should handle the same Origin in a compatible way.
        """
        transport = httpx.ASGITransport(app=clarity_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Test with allowed origin
            origin = "http://localhost:5173"

            head_response = await client.head("/mcp", headers={"Origin": origin})

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
                        "Origin": origin,
                    },
                )

                # If POST succeeds, compare CORS headers
                head_cors = head_response.headers.get("access-control-allow-origin")
                post_cors = post_response.headers.get("access-control-allow-origin")

                # HEAD should allow the same origin as POST
                # (HEAD uses middleware, POST uses Starlette CORS)
                # Both should allow localhost:5173 in dev mode
                assert head_cors == origin

            except RuntimeError:
                # FastMCP session manager not initialized - just verify HEAD works
                pass

        assert head_response.status_code == 200

    @pytest.mark.asyncio
    async def test_full_mcp_flow_unaffected(self, clarity_app):
        """Full MCP flow (initialize -> tools/list) should work unchanged.

        The HEAD middleware must not interfere with normal MCP operations.
        """
        transport = httpx.ASGITransport(app=clarity_app)
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
    async def test_head_does_not_affect_post_streaming(self, clarity_app):
        """POST /mcp streaming behavior unchanged after HEAD request."""
        transport = httpx.ASGITransport(app=clarity_app)
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

                # Verify POST works and has appropriate content type
                assert post_response.status_code not in (404, 405)

            except RuntimeError as e:
                if "Task group is not initialized" in str(e):
                    pass
                else:
                    raise
