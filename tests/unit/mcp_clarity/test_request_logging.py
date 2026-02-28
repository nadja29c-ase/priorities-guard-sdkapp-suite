"""
Unit tests for Clarity MCP RequestLoggingMiddleware.

Tests verify:
- All HTTP requests are logged with structured fields
- Client IP extracted from X-Forwarded-For header
- User-Agent captured and truncated
- Response time measured
- Status code captured
- No sensitive data (Authorization) logged
- Lifespan events not logged
"""

import pytest
import httpx
import structlog
from structlog.testing import capture_logs
from unittest.mock import patch


@pytest.fixture
def clarity_app():
    """Create Clarity app for testing."""
    with patch.dict("os.environ", {"ENV": "dev"}, clear=False):
        from mcp_server.clarity.server import create_app
        return create_app()


class TestRequestLoggingMiddleware:
    """Tests for RequestLoggingMiddleware in Clarity."""

    @pytest.mark.asyncio
    async def test_logs_get_request(self, clarity_app):
        """GET / should produce log entry with method=GET, path=/, status=200."""
        with capture_logs() as cap_logs:
            transport = httpx.ASGITransport(app=clarity_app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/")

        assert response.status_code == 200

        # Find the http.request log entry
        http_logs = [log for log in cap_logs if log.get("event") == "http.request"]
        assert len(http_logs) >= 1

        log = http_logs[-1]  # Get the last one (the GET / request)
        assert log["method"] == "GET"
        assert log["path"] == "/"
        assert log["status_code"] == 200
        assert log["service"] == "clarity-mcp"

    @pytest.mark.asyncio
    async def test_logs_post_mcp(self, clarity_app):
        """POST /mcp should produce log entry with method=POST, path=/mcp."""
        with capture_logs() as cap_logs:
            transport = httpx.ASGITransport(app=clarity_app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                try:
                    await client.post(
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
                    # FastMCP may raise in test context
                    if "Task group is not initialized" not in str(e):
                        raise

        # Find the http.request log entry for POST /mcp
        http_logs = [log for log in cap_logs if log.get("event") == "http.request"]
        post_logs = [log for log in http_logs if log.get("method") == "POST" and log.get("path") == "/mcp"]
        assert len(post_logs) >= 1

        log = post_logs[-1]
        assert log["method"] == "POST"
        assert log["path"] == "/mcp"
        assert log["service"] == "clarity-mcp"

    @pytest.mark.asyncio
    async def test_logs_head_mcp(self, clarity_app):
        """HEAD /mcp should produce log entry with method=HEAD, path=/mcp, status=200."""
        with capture_logs() as cap_logs:
            transport = httpx.ASGITransport(app=clarity_app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.head("/mcp")

        assert response.status_code == 200

        # Find the http.request log entry
        http_logs = [log for log in cap_logs if log.get("event") == "http.request"]
        head_logs = [log for log in http_logs if log.get("method") == "HEAD" and log.get("path") == "/mcp"]
        assert len(head_logs) >= 1

        log = head_logs[-1]
        assert log["method"] == "HEAD"
        assert log["path"] == "/mcp"
        assert log["status_code"] == 200
        assert log["service"] == "clarity-mcp"

    @pytest.mark.asyncio
    async def test_logs_client_ip_from_xff(self, clarity_app):
        """Request with X-Forwarded-For header should use XFF IP in log."""
        with capture_logs() as cap_logs:
            transport = httpx.ASGITransport(app=clarity_app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(
                    "/",
                    headers={"X-Forwarded-For": "203.0.113.195, 70.41.3.18, 150.172.238.178"}
                )

        assert response.status_code == 200

        # Find the http.request log entry
        http_logs = [log for log in cap_logs if log.get("event") == "http.request"]
        assert len(http_logs) >= 1

        log = http_logs[-1]
        # Should use first IP from X-Forwarded-For
        assert log["client_ip"] == "203.0.113.195"

    @pytest.mark.asyncio
    async def test_logs_user_agent(self, clarity_app):
        """Request with User-Agent header should include user_agent in log."""
        test_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TestBrowser/1.0"
        with capture_logs() as cap_logs:
            transport = httpx.ASGITransport(app=clarity_app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(
                    "/",
                    headers={"User-Agent": test_ua}
                )

        assert response.status_code == 200

        # Find the http.request log entry
        http_logs = [log for log in cap_logs if log.get("event") == "http.request"]
        assert len(http_logs) >= 1

        log = http_logs[-1]
        assert log["user_agent"] == test_ua

    @pytest.mark.asyncio
    async def test_no_auth_header_logged(self, clarity_app):
        """Request with Authorization header should NOT log the auth token."""
        with capture_logs() as cap_logs:
            transport = httpx.ASGITransport(app=clarity_app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(
                    "/",
                    headers={"Authorization": "Bearer super-secret-token-12345"}
                )

        assert response.status_code == 200

        # Find the http.request log entry
        http_logs = [log for log in cap_logs if log.get("event") == "http.request"]
        assert len(http_logs) >= 1

        log = http_logs[-1]
        # Authorization should NOT be in the log
        assert "authorization" not in log
        assert "Authorization" not in log
        # Also verify the token value isn't anywhere in the log
        log_str = str(log)
        assert "super-secret-token-12345" not in log_str

    @pytest.mark.asyncio
    async def test_logs_response_time(self, clarity_app):
        """Any request should include response_time_ms > 0."""
        with capture_logs() as cap_logs:
            transport = httpx.ASGITransport(app=clarity_app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/")

        assert response.status_code == 200

        # Find the http.request log entry
        http_logs = [log for log in cap_logs if log.get("event") == "http.request"]
        assert len(http_logs) >= 1

        log = http_logs[-1]
        assert "response_time_ms" in log
        assert log["response_time_ms"] >= 0  # Could be 0 for very fast requests

    @pytest.mark.asyncio
    async def test_skips_lifespan(self, clarity_app):
        """Lifespan scope should not produce log entry.

        Note: This is tested implicitly - lifespan events happen during
        app startup/shutdown which we can't easily trigger in unit tests.
        We verify by checking that only HTTP requests produce logs.
        """
        with capture_logs() as cap_logs:
            transport = httpx.ASGITransport(app=clarity_app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                await client.get("/")

        # All http.request logs should have type=http (implicitly)
        http_logs = [log for log in cap_logs if log.get("event") == "http.request"]
        for log in http_logs:
            # Verify all logs are for HTTP requests (have method, path, status_code)
            assert "method" in log
            assert "path" in log
            assert "status_code" in log

    @pytest.mark.asyncio
    async def test_user_agent_truncated(self, clarity_app):
        """User-Agent longer than 200 chars should be truncated."""
        long_ua = "A" * 300  # 300 character User-Agent
        with capture_logs() as cap_logs:
            transport = httpx.ASGITransport(app=clarity_app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(
                    "/",
                    headers={"User-Agent": long_ua}
                )

        assert response.status_code == 200

        # Find the http.request log entry
        http_logs = [log for log in cap_logs if log.get("event") == "http.request"]
        assert len(http_logs) >= 1

        log = http_logs[-1]
        # Should be truncated to 200 chars
        assert len(log["user_agent"]) == 200
        assert log["user_agent"] == "A" * 200

    @pytest.mark.asyncio
    async def test_logs_origin_header(self, clarity_app):
        """Request with Origin header should include origin in log."""
        with capture_logs() as cap_logs:
            transport = httpx.ASGITransport(app=clarity_app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(
                    "/",
                    headers={"Origin": "https://chatgpt.com"}
                )

        assert response.status_code == 200

        # Find the http.request log entry
        http_logs = [log for log in cap_logs if log.get("event") == "http.request"]
        assert len(http_logs) >= 1

        log = http_logs[-1]
        assert log.get("origin") == "https://chatgpt.com"
