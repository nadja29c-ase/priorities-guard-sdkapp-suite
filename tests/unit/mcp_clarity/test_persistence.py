"""
Unit tests for Clarity persistence module.
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

        # Verify payload
        call_args = mock_client.post.call_args
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

        # Verify headers
        call_args = mock_client.get.call_args
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
    async def test_get_cluster_error_handling(self):
        """Should return None on network/server error."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Network error"))

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await get_cluster(user_id="user-456")

        assert result is None

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
