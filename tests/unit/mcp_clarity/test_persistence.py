"""
Unit tests for Clarity persistence module.

Note on patching INTERNAL_API_SECRET:
  We patch at 'mcp_server.clarity.persistence.INTERNAL_API_SECRET' because
  persistence.py imports it directly: `from .config import INTERNAL_API_SECRET`.
  If that import style changes, these patches will need updating.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from mcp_server.clarity.persistence import persist_cluster, get_cluster


class TestPersistCluster:
    """Tests for the persist_cluster function."""

    @pytest.mark.asyncio
    async def test_persist_cluster_success(self):
        """Should return cluster_id on successful persistence."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"cluster_id": "test-cluster-123"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await persist_cluster(
                user_id="user-456",
                cluster_data={"clusters": [{"cluster_name": "Test"}]},
                thoughts_exhausted=True,
                correctly_clustered=None,
            )

        assert result == "test-cluster-123"
        mock_client.post.assert_called_once()

        # Verify URL and payload
        call_args = mock_client.post.call_args
        assert call_args.args[0].endswith("/api/clarity/clusters")
        assert "X-User-ID" in call_args.kwargs["headers"]
        assert call_args.kwargs["json"]["thoughts_exhausted"] is True

    @pytest.mark.asyncio
    async def test_persist_cluster_failure_returns_none(self):
        """Should return None on non-201 response."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await persist_cluster(
                user_id="user-456",
                cluster_data={"clusters": []},
                thoughts_exhausted=True,
                correctly_clustered=None,
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_persist_cluster_exception_returns_none(self):
        """Should return None on network/exception error."""
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("Network error"))

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await persist_cluster(
                user_id="user-456",
                cluster_data={"clusters": []},
                thoughts_exhausted=True,
                correctly_clustered=None,
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_persist_cluster_uses_post_not_get(self):
        """Should use POST method, never GET (defensive method check)."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"cluster_id": "test-123"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.get = AsyncMock()

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            await persist_cluster(
                user_id="user-456",
                cluster_data={"clusters": []},
                thoughts_exhausted=True,
                correctly_clustered=None,
            )

        mock_client.post.assert_called_once()
        mock_client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_persist_cluster_uses_shared_http_client(self):
        """Should use get_http_client() which has timeout configured.

        IMPORTANT: The timeout guarantee comes from the shared HTTP client
        (see http_client.py: httpx.AsyncClient(timeout=10.0)).

        This test ensures we always use get_http_client() and don't bypass it
        with a custom client that might lack timeout configuration.
        If this test fails, MCP could hang on slow/unresponsive backends.
        """
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"cluster_id": "test-123"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client") as mock_get_client:
            mock_get_client.return_value = mock_client

            await persist_cluster(
                user_id="user-456",
                cluster_data={"clusters": []},
                thoughts_exhausted=True,
                correctly_clustered=None,
            )

            # Verify get_http_client() was called (not bypassed)
            mock_get_client.assert_called_once()

    @pytest.mark.asyncio
    async def test_persist_cluster_includes_internal_secret(self):
        """Should include X-Internal-Secret header when configured."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"cluster_id": "test-123"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            with patch("mcp_server.clarity.persistence.INTERNAL_API_SECRET", "secret-key"):
                await persist_cluster(
                    user_id="user-456",
                    cluster_data={"clusters": []},
                    thoughts_exhausted=True,
                    correctly_clustered=None,
                )

        call_args = mock_client.post.call_args
        assert call_args.kwargs["headers"]["X-Internal-Secret"] == "secret-key"


class TestGetCluster:
    """Tests for the get_cluster function."""

    @pytest.mark.asyncio
    async def test_get_cluster_success(self):
        """Should return cluster_data when 200 response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "cluster_id": "cluster-abc",
            "cluster_data": {"clusters": [{"cluster_name": "Test Cluster"}]},
            "thoughts_exhausted": True,
            "correctly_clustered": None,
            "created_at": "2025-01-15T10:00:00Z",
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await get_cluster(user_id="user-456")

        assert result is not None
        assert result["cluster_id"] == "cluster-abc"
        assert result["cluster_data"]["clusters"][0]["cluster_name"] == "Test Cluster"
        mock_client.get.assert_called_once()

        # Verify URL and headers
        call_args = mock_client.get.call_args
        assert call_args.args[0].endswith("/api/clarity/clusters")
        assert call_args.kwargs["headers"]["X-User-ID"] == "user-456"

    @pytest.mark.asyncio
    async def test_get_cluster_not_found(self):
        """Should return None when 404 response."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await get_cluster(user_id="user-no-clusters")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_cluster_network_error_returns_none(self):
        """Should return None on network exception (connection refused, timeout, etc)."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Network error"))

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await get_cluster(user_id="user-456")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_cluster_uses_get_not_post(self):
        """Should use GET method, never POST (defensive method check)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"cluster_id": "test-123", "cluster_data": {}}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.post = AsyncMock()

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            await get_cluster(user_id="user-456")

        mock_client.get.assert_called_once()
        mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_cluster_uses_shared_http_client(self):
        """Should use get_http_client() which has timeout configured.

        IMPORTANT: The timeout guarantee comes from the shared HTTP client
        (see http_client.py: httpx.AsyncClient(timeout=10.0)).

        This test ensures we always use get_http_client() and don't bypass it
        with a custom client that might lack timeout configuration.
        If this test fails, MCP could hang on slow/unresponsive backends.
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"cluster_id": "test-123", "cluster_data": {}}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client") as mock_get_client:
            mock_get_client.return_value = mock_client

            await get_cluster(user_id="user-456")

            # Verify get_http_client() was called (not bypassed)
            mock_get_client.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_cluster_includes_internal_secret(self):
        """Should include X-Internal-Secret header when configured."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "cluster_id": "cluster-abc",
            "cluster_data": {"clusters": []},
            "thoughts_exhausted": True,
            "correctly_clustered": None,
            "created_at": "2025-01-15T10:00:00Z",
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            with patch("mcp_server.clarity.persistence.INTERNAL_API_SECRET", "secret-key"):
                await get_cluster(user_id="user-456")

        call_args = mock_client.get.call_args
        assert call_args.kwargs["headers"]["X-Internal-Secret"] == "secret-key"

    @pytest.mark.asyncio
    async def test_get_cluster_server_error_returns_none(self):
        """Should return None on 500 server error."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await get_cluster(user_id="user-456")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_cluster_unexpected_payload_passes_through(self):
        """Should pass through unexpected JSON shapes (caller handles gracefully).

        Note: This documents current behavior. The MCP layer trusts the backend
        but consumers (get_my_clusters tool) handle missing keys with .get() defaults.
        If stricter validation is needed, add it to persistence.py and update this test.
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"unexpected": "shape"}  # Missing expected keys

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await get_cluster(user_id="user-456")

        # Currently passes through as-is (no validation at persistence layer)
        assert result == {"unexpected": "shape"}
        # Consumer must handle missing keys gracefully

    @pytest.mark.asyncio
    async def test_get_cluster_invalid_json_returns_none(self):
        """Should return None when backend returns invalid JSON (e.g., HTML error page).

        This locks in the 'never crash MCP on backend weirdness' guarantee.
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await get_cluster(user_id="user-456")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_cluster_none_user_id_returns_none(self):
        """Should return None when user_id is None (defensive boundary test).

        Documents behavior: sends X-User-ID: None header, backend returns 401,
        function returns None without crashing. Type hint says str but we handle
        None gracefully at the boundary.
        """
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await get_cluster(user_id=None)

        assert result is None
