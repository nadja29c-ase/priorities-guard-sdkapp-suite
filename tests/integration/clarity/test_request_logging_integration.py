"""
Integration tests for Clarity MCP RequestLoggingMiddleware.

Tests verify:
- Full request lifecycle produces correct log entries
- Multiple sequential requests all logged correctly
- 4xx responses logged as warning
"""

import pytest
import httpx
from structlog.testing import capture_logs
from unittest.mock import patch


@pytest.fixture
def clarity_app():
    """Create Clarity app for testing."""
    with patch.dict("os.environ", {"ENV": "dev"}, clear=False):
        from mcp_server.clarity.server import create_app
        return create_app()


class TestRequestLoggingIntegration:
    """Integration tests for RequestLoggingMiddleware in Clarity."""

    @pytest.mark.asyncio
    async def test_full_request_lifecycle_logged(self, clarity_app):
        """GET / -> HEAD /mcp -> POST /mcp initialize produces three log entries."""
        with capture_logs() as cap_logs:
            transport = httpx.ASGITransport(app=clarity_app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                # 1. GET /
                response1 = await client.get("/")
                assert response1.status_code == 200

                # 2. HEAD /mcp
                response2 = await client.head("/mcp")
                assert response2.status_code == 200

                # 3. POST /mcp (may raise due to FastMCP test limitations)
                try:
                    response3 = await client.post(
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
                except RuntimeError as e:
                    if "Task group is not initialized" not in str(e):
                        raise

        # Find all http.request log entries
        http_logs = [log for log in cap_logs if log.get("event") == "http.request"]

        # Should have at least 3 entries (GET /, HEAD /mcp, POST /mcp)
        assert len(http_logs) >= 3

        # Find specific log entries
        get_root_logs = [l for l in http_logs if l.get("method") == "GET" and l.get("path") == "/"]
        head_mcp_logs = [l for l in http_logs if l.get("method") == "HEAD" and l.get("path") == "/mcp"]
        post_mcp_logs = [l for l in http_logs if l.get("method") == "POST" and l.get("path") == "/mcp"]

        assert len(get_root_logs) >= 1
        assert len(head_mcp_logs) >= 1
        assert len(post_mcp_logs) >= 1

        # Verify status codes
        assert get_root_logs[-1]["status_code"] == 200
        assert head_mcp_logs[-1]["status_code"] == 200

        # All should have service field
        for log in [get_root_logs[-1], head_mcp_logs[-1], post_mcp_logs[-1]]:
            assert log["service"] == "clarity-mcp"

    @pytest.mark.asyncio
    async def test_4xx_logged_as_warning(self, clarity_app):
        """Request to nonexistent path should produce warning log with 404 status."""
        with capture_logs() as cap_logs:
            transport = httpx.ASGITransport(app=clarity_app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/nonexistent-path-12345")

        assert response.status_code == 404

        # Find the http.request log entry for the 404
        http_logs = [log for log in cap_logs if log.get("event") == "http.request"]
        not_found_logs = [l for l in http_logs if l.get("path") == "/nonexistent-path-12345"]

        assert len(not_found_logs) >= 1
        log = not_found_logs[-1]

        assert log["status_code"] == 404
        # Warning level is indicated by log_level field in structlog
        assert log.get("log_level") == "warning"

    @pytest.mark.asyncio
    async def test_discovery_endpoints_logged(self, clarity_app):
        """OAuth discovery endpoint requests should be logged."""
        with capture_logs() as cap_logs:
            transport = httpx.ASGITransport(app=clarity_app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/.well-known/oauth-protected-resource")

        assert response.status_code == 200

        # Find the http.request log entry
        http_logs = [log for log in cap_logs if log.get("event") == "http.request"]
        discovery_logs = [l for l in http_logs if "oauth-protected-resource" in l.get("path", "")]

        assert len(discovery_logs) >= 1
        log = discovery_logs[-1]
        assert log["status_code"] == 200
        assert log["method"] == "GET"
