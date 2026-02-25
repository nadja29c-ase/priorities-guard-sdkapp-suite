"""
Unit tests for Priority Guardian HTTP client.

Tests http_client.py:
- backend_get adds correct headers
- backend_post adds correct headers
- backend_put adds correct headers
- backend_delete adds correct headers
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
        mock_response.status_code = 200
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
    async def test_backend_get_returns_json_on_4xx_error(self):
        """backend_get returns JSON body on 4xx errors (for structured error messages)."""
        import mcp_server.priority_guardian.http_client as http_client_module
        http_client_module.http_client = None

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {
            "success": False,
            "error": {"code": "NOT_FOUND", "message": "Resource not found"}
        }
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            from mcp_server.priority_guardian.http_client import backend_get

            result = await backend_get(
                "/api/test",
                user_id="user-123",
                correlation_id="corr-456",
            )

        assert result["success"] is False
        assert result["error"]["code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_backend_get_raises_on_5xx_error(self):
        """backend_get raises HTTPStatusError on 5xx errors."""
        import httpx
        import mcp_server.priority_guardian.http_client as http_client_module
        http_client_module.http_client = None

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500 Internal Server Error",
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
        mock_response.status_code = 200
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
        mock_response.status_code = 200
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


class TestBackendPut:
    """Tests for backend_put function."""

    @pytest.mark.asyncio
    async def test_backend_put_adds_headers(self):
        """backend_put adds X-User-ID and X-Correlation-ID headers."""
        import mcp_server.priority_guardian.http_client as http_client_module
        http_client_module.http_client = None

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "test"}
        mock_response.raise_for_status = MagicMock()
        mock_client.put.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            from mcp_server.priority_guardian.http_client import backend_put

            await backend_put(
                "/api/test/123",
                {"name": "Updated"},
                user_id="user-123",
                correlation_id="corr-456",
            )

        # Verify headers were passed
        call_kwargs = mock_client.put.call_args
        headers = call_kwargs.kwargs.get("headers", {})
        assert headers["X-User-ID"] == "user-123"
        assert headers["X-Correlation-ID"] == "corr-456"

    @pytest.mark.asyncio
    async def test_backend_put_sends_json_body(self):
        """backend_put sends JSON body."""
        import mcp_server.priority_guardian.http_client as http_client_module
        http_client_module.http_client = None

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "test"}
        mock_response.raise_for_status = MagicMock()
        mock_client.put.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            from mcp_server.priority_guardian.http_client import backend_put

            await backend_put(
                "/api/priorities/123",
                {"name": "Updated Name", "deadline": "2026-04-01"},
                user_id="user-123",
                correlation_id="corr-456",
            )

        # Verify JSON body was passed
        call_kwargs = mock_client.put.call_args
        json_body = call_kwargs.kwargs.get("json", {})
        assert json_body["name"] == "Updated Name"
        assert json_body["deadline"] == "2026-04-01"

    @pytest.mark.asyncio
    async def test_backend_put_returns_json_on_4xx_error(self):
        """backend_put returns JSON body on 4xx errors (for structured error messages)."""
        import mcp_server.priority_guardian.http_client as http_client_module
        http_client_module.http_client = None

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {
            "success": False,
            "error": {"code": "NOT_FOUND", "message": "Priority not found"}
        }
        mock_client.put.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            from mcp_server.priority_guardian.http_client import backend_put

            result = await backend_put(
                "/api/priorities/nonexistent",
                {"name": "Updated"},
                user_id="user-123",
                correlation_id="corr-456",
            )

        assert result["success"] is False
        assert result["error"]["code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_backend_put_raises_on_5xx_error(self):
        """backend_put raises HTTPStatusError on 5xx errors."""
        import httpx
        import mcp_server.priority_guardian.http_client as http_client_module
        http_client_module.http_client = None

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=MagicMock(),
            response=mock_response,
        )
        mock_client.put.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            from mcp_server.priority_guardian.http_client import backend_put

            with pytest.raises(httpx.HTTPStatusError):
                await backend_put(
                    "/api/priorities/123",
                    {"name": "Updated"},
                    user_id="user-123",
                    correlation_id="corr-456",
                )


class TestBackendDelete:
    """Tests for backend_delete function."""

    @pytest.mark.asyncio
    async def test_backend_delete_adds_headers(self):
        """backend_delete adds X-User-ID and X-Correlation-ID headers."""
        import mcp_server.priority_guardian.http_client as http_client_module
        http_client_module.http_client = None

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status = MagicMock()
        mock_client.delete.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            from mcp_server.priority_guardian.http_client import backend_delete

            await backend_delete(
                "/api/test/123",
                user_id="user-123",
                correlation_id="corr-456",
            )

        # Verify headers were passed
        call_kwargs = mock_client.delete.call_args
        headers = call_kwargs.kwargs.get("headers", {})
        assert headers["X-User-ID"] == "user-123"
        assert headers["X-Correlation-ID"] == "corr-456"

    @pytest.mark.asyncio
    async def test_backend_delete_returns_json_on_4xx_error(self):
        """backend_delete returns JSON body on 4xx errors (for structured error messages)."""
        import mcp_server.priority_guardian.http_client as http_client_module
        http_client_module.http_client = None

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {
            "success": False,
            "error": {"code": "NOT_FOUND", "message": "Priority not found"}
        }
        mock_client.delete.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            from mcp_server.priority_guardian.http_client import backend_delete

            result = await backend_delete(
                "/api/priorities/nonexistent",
                user_id="user-123",
                correlation_id="corr-456",
            )

        assert result["success"] is False
        assert result["error"]["code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_backend_delete_raises_on_5xx_error(self):
        """backend_delete raises HTTPStatusError on 5xx errors."""
        import httpx
        import mcp_server.priority_guardian.http_client as http_client_module
        http_client_module.http_client = None

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=MagicMock(),
            response=mock_response,
        )
        mock_client.delete.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            from mcp_server.priority_guardian.http_client import backend_delete

            with pytest.raises(httpx.HTTPStatusError):
                await backend_delete(
                    "/api/priorities/123",
                    user_id="user-123",
                    correlation_id="corr-456",
                )

    @pytest.mark.asyncio
    async def test_backend_delete_returns_json_response(self):
        """backend_delete returns JSON response from backend."""
        import mcp_server.priority_guardian.http_client as http_client_module
        http_client_module.http_client = None

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True, "data": {"deleted": True}}
        mock_response.raise_for_status = MagicMock()
        mock_client.delete.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            from mcp_server.priority_guardian.http_client import backend_delete

            result = await backend_delete(
                "/api/priorities/123",
                user_id="user-123",
                correlation_id="corr-456",
            )

        assert result["success"] is True
        assert result["data"]["deleted"] is True


class TestInternalSecretHeader:
    """Tests for X-Internal-Secret header inclusion."""

    @pytest.mark.asyncio
    async def test_backend_get_includes_internal_secret_when_configured(self):
        """backend_get includes X-Internal-Secret header when INTERNAL_API_SECRET is set."""
        import mcp_server.priority_guardian.http_client as http_client_module
        http_client_module.http_client = None

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "test"}
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("mcp_server.priority_guardian.http_client.INTERNAL_API_SECRET", "test-secret"):
                from mcp_server.priority_guardian.http_client import backend_get

                await backend_get(
                    "/api/test",
                    user_id="user-123",
                    correlation_id="corr-456",
                )

        call_kwargs = mock_client.get.call_args
        headers = call_kwargs.kwargs.get("headers", {})
        assert headers["X-Internal-Secret"] == "test-secret"

    @pytest.mark.asyncio
    async def test_backend_get_omits_internal_secret_when_empty(self):
        """backend_get omits X-Internal-Secret header when INTERNAL_API_SECRET is empty."""
        import mcp_server.priority_guardian.http_client as http_client_module
        http_client_module.http_client = None

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "test"}
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("mcp_server.priority_guardian.http_client.INTERNAL_API_SECRET", ""):
                from mcp_server.priority_guardian.http_client import backend_get

                await backend_get(
                    "/api/test",
                    user_id="user-123",
                    correlation_id="corr-456",
                )

        call_kwargs = mock_client.get.call_args
        headers = call_kwargs.kwargs.get("headers", {})
        assert "X-Internal-Secret" not in headers

    @pytest.mark.asyncio
    async def test_backend_post_includes_internal_secret_when_configured(self):
        """backend_post includes X-Internal-Secret header when INTERNAL_API_SECRET is set."""
        import mcp_server.priority_guardian.http_client as http_client_module
        http_client_module.http_client = None

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "test"}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("mcp_server.priority_guardian.http_client.INTERNAL_API_SECRET", "test-secret"):
                from mcp_server.priority_guardian.http_client import backend_post

                await backend_post(
                    "/api/test",
                    {"key": "value"},
                    user_id="user-123",
                    correlation_id="corr-456",
                )

        call_kwargs = mock_client.post.call_args
        headers = call_kwargs.kwargs.get("headers", {})
        assert headers["X-Internal-Secret"] == "test-secret"

    @pytest.mark.asyncio
    async def test_backend_put_includes_internal_secret_when_configured(self):
        """backend_put includes X-Internal-Secret header when INTERNAL_API_SECRET is set."""
        import mcp_server.priority_guardian.http_client as http_client_module
        http_client_module.http_client = None

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "test"}
        mock_response.raise_for_status = MagicMock()
        mock_client.put.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("mcp_server.priority_guardian.http_client.INTERNAL_API_SECRET", "test-secret"):
                from mcp_server.priority_guardian.http_client import backend_put

                await backend_put(
                    "/api/test/123",
                    {"name": "Updated"},
                    user_id="user-123",
                    correlation_id="corr-456",
                )

        call_kwargs = mock_client.put.call_args
        headers = call_kwargs.kwargs.get("headers", {})
        assert headers["X-Internal-Secret"] == "test-secret"

    @pytest.mark.asyncio
    async def test_backend_delete_includes_internal_secret_when_configured(self):
        """backend_delete includes X-Internal-Secret header when INTERNAL_API_SECRET is set."""
        import mcp_server.priority_guardian.http_client as http_client_module
        http_client_module.http_client = None

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"success": True}
        mock_response.raise_for_status = MagicMock()
        mock_client.delete.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("mcp_server.priority_guardian.http_client.INTERNAL_API_SECRET", "test-secret"):
                from mcp_server.priority_guardian.http_client import backend_delete

                await backend_delete(
                    "/api/test/123",
                    user_id="user-123",
                    correlation_id="corr-456",
                )

        call_kwargs = mock_client.delete.call_args
        headers = call_kwargs.kwargs.get("headers", {})
        assert headers["X-Internal-Secret"] == "test-secret"


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
