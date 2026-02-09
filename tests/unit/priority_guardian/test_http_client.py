"""
Unit tests for Priority Guardian HTTP client.

Tests http_client.py:
- backend_get adds correct headers
- backend_post adds correct headers
- cleanup_http_client closes the client
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestBackendGet:
    """Tests for backend_get function."""

    @pytest.mark.asyncio
    async def test_backend_get_adds_user_id_header(self):
        """backend_get adds X-User-ID header from user_id parameter."""
        # Reset the global http_client
        import mcp_server.priority_guardian.http_client as http_client_module
        http_client_module.http_client = None

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": "test"}
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            from mcp_server.priority_guardian.http_client import backend_get

            await backend_get(
                "/api/test",
                user_id="user-123",
                correlation_id="corr-456",
            )

        # Verify headers were passed
        call_kwargs = mock_client.get.call_args
        headers = call_kwargs.kwargs.get("headers", {})
        assert headers["X-User-ID"] == "user-123"
        assert headers["X-Correlation-ID"] == "corr-456"

    @pytest.mark.asyncio
    async def test_backend_get_raises_on_error_status(self):
        """backend_get raises HTTPStatusError on error status."""
        import httpx
        import mcp_server.priority_guardian.http_client as http_client_module
        http_client_module.http_client = None

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404 Not Found",
            request=MagicMock(),
            response=mock_response,
        )
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            from mcp_server.priority_guardian.http_client import backend_get

            with pytest.raises(httpx.HTTPStatusError):
                await backend_get(
                    "/api/test",
                    user_id="user-123",
                    correlation_id="corr-456",
                )


class TestBackendPost:
    """Tests for backend_post function."""

    @pytest.mark.asyncio
    async def test_backend_post_adds_headers(self):
        """backend_post adds X-User-ID and X-Correlation-ID headers."""
        import mcp_server.priority_guardian.http_client as http_client_module
        http_client_module.http_client = None

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": "test"}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            from mcp_server.priority_guardian.http_client import backend_post

            await backend_post(
                "/api/test",
                {"key": "value"},
                user_id="user-123",
                correlation_id="corr-456",
            )

        # Verify headers were passed
        call_kwargs = mock_client.post.call_args
        headers = call_kwargs.kwargs.get("headers", {})
        assert headers["X-User-ID"] == "user-123"
        assert headers["X-Correlation-ID"] == "corr-456"

    @pytest.mark.asyncio
    async def test_backend_post_sends_json_body(self):
        """backend_post sends JSON body."""
        import mcp_server.priority_guardian.http_client as http_client_module
        http_client_module.http_client = None

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": "test"}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            from mcp_server.priority_guardian.http_client import backend_post

            await backend_post(
                "/api/test",
                {"name": "Test Priority", "type": "deadline"},
                user_id="user-123",
                correlation_id="corr-456",
            )

        # Verify JSON body was passed
        call_kwargs = mock_client.post.call_args
        json_body = call_kwargs.kwargs.get("json", {})
        assert json_body["name"] == "Test Priority"
        assert json_body["type"] == "deadline"


class TestCleanupHttpClient:
    """Tests for cleanup_http_client function."""

    @pytest.mark.asyncio
    async def test_cleanup_closes_client(self):
        """cleanup_http_client closes the HTTP client."""
        import mcp_server.priority_guardian.http_client as http_client_module

        mock_client = AsyncMock()
        http_client_module.http_client = mock_client

        from mcp_server.priority_guardian.http_client import cleanup_http_client

        await cleanup_http_client()

        mock_client.aclose.assert_called_once()
        assert http_client_module.http_client is None

    @pytest.mark.asyncio
    async def test_cleanup_handles_none_client(self):
        """cleanup_http_client handles None client gracefully."""
        import mcp_server.priority_guardian.http_client as http_client_module
        http_client_module.http_client = None

        from mcp_server.priority_guardian.http_client import cleanup_http_client

        # Should not raise
        await cleanup_http_client()
