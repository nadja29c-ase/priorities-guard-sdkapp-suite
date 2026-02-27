"""
Unit tests for Priority Guardian MCP health endpoints.

Tests verify:
- GET / returns 200 with JSON body {"status": "ok", "service": "priority-guardian-mcp"}
- GET /health returns 200 with plain text "ok"
- POST /mcp does not return 404 (regression test)
"""

import pytest
import httpx
from unittest.mock import patch


@pytest.fixture
def pg_app():
    """Create Priority Guardian app for testing.

    Mocks external dependencies to avoid needing real config/database.
    """
    # Mock the config values that are required
    mock_config = {
        "MCP_SERVER_URL": "http://test-mcp.example.com",
        "OAUTH_ISSUER_URL": "http://test-oauth.example.com",
        "BACKEND_URL": "http://test-backend.example.com",
    }

    with patch.dict("os.environ", {"ENV": "dev"}, clear=False):
        with patch(
            "mcp_server.priority_guardian.config.MCP_SERVER_URL",
            mock_config["MCP_SERVER_URL"],
        ):
            with patch(
                "mcp_server.priority_guardian.config.OAUTH_ISSUER_URL",
                mock_config["OAUTH_ISSUER_URL"],
            ):
                with patch(
                    "mcp_server.priority_guardian.config.BACKEND_URL",
                    mock_config["BACKEND_URL"],
                ):
                    from mcp_server.priority_guardian.server import create_app

                    return create_app()


class TestPriorityGuardianHealthEndpoints:
    """Tests for Priority Guardian MCP health endpoints."""

    @pytest.mark.asyncio
    async def test_root_returns_200_json(self, pg_app):
        """GET / should return 200 with JSON health response."""
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        assert response.json() == {"status": "ok", "service": "priority-guardian-mcp"}

    @pytest.mark.asyncio
    async def test_health_returns_200_plain_text(self, pg_app):
        """GET /health should return 200 with plain text 'ok'."""
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        assert response.text == "ok"

    @pytest.mark.asyncio
    async def test_mcp_endpoint_not_404(self, pg_app):
        """POST /mcp should not return 404 (regression test).

        A 401 (auth required) or 200 are acceptable - the endpoint must exist.
        FastMCP returns 400 for malformed requests, which is also acceptable.

        Note: FastMCP may raise RuntimeError if session manager isn't initialized,
        but this still proves the route exists (404 would come from Starlette router).
        """
        transport = httpx.ASGITransport(app=pg_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            try:
                # Send minimal MCP initialize request
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
                    headers={"Content-Type": "application/json"},
                )
                # Must NOT be 404 - endpoint must exist
                assert response.status_code != 404, "POST /mcp returned 404 - endpoint missing"
            except RuntimeError as e:
                # RuntimeError from FastMCP session manager means the route exists
                # and reached the MCP handler - this is acceptable for this test
                if "Task group is not initialized" in str(e):
                    pass  # Route exists, MCP handler was reached
                else:
                    raise
