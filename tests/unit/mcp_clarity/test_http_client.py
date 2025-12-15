"""
Unit tests for Clarity HTTP client module.

Tests the module-level HTTP client configuration including timeouts.
"""

import pytest
from unittest.mock import patch, MagicMock

from mcp_server.clarity.http_client import get_http_client, cleanup_http_client


class TestHttpClientConfiguration:
    """Tests for HTTP client configuration."""

    @pytest.fixture(autouse=True)
    def reset_client(self):
        """Reset the module-level client before each test."""
        import mcp_server.clarity.http_client as http_module
        http_module._http_client = None
        yield
        http_module._http_client = None

    def test_client_has_timeout_configured(self):
        """Client must be created with a timeout to prevent MCP hangs.

        This locks in the production guarantee that requests will not hang forever.
        """
        with patch("mcp_server.clarity.http_client.httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value = MagicMock()

            get_http_client()

            mock_client_class.assert_called_once()
            call_kwargs = mock_client_class.call_args.kwargs
            assert "timeout" in call_kwargs, "HTTP client must specify a timeout"
            assert call_kwargs["timeout"] > 0, "Timeout must be positive"

    def test_client_timeout_is_reasonable(self):
        """Timeout should be reasonable (not too short, not too long)."""
        with patch("mcp_server.clarity.http_client.httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value = MagicMock()

            get_http_client()

            timeout = mock_client_class.call_args.kwargs["timeout"]
            assert 5 <= timeout <= 30, f"Timeout {timeout}s should be between 5-30 seconds"

    def test_client_is_reused(self):
        """Client should be reused across calls (connection pooling)."""
        with patch("mcp_server.clarity.http_client.httpx.AsyncClient") as mock_client_class:
            mock_instance = MagicMock()
            mock_client_class.return_value = mock_instance

            client1 = get_http_client()
            client2 = get_http_client()

            assert client1 is client2, "Client should be reused"
            mock_client_class.assert_called_once()  # Only created once

    @pytest.mark.asyncio
    async def test_cleanup_closes_client(self):
        """Cleanup should close the HTTP client."""
        from unittest.mock import AsyncMock as AsyncMockClass

        with patch("mcp_server.clarity.http_client.httpx.AsyncClient") as mock_client_class:
            mock_instance = MagicMock()
            mock_instance.aclose = AsyncMockClass(return_value=None)
            mock_client_class.return_value = mock_instance

            get_http_client()  # Create client
            await cleanup_http_client()

            mock_instance.aclose.assert_called_once()
