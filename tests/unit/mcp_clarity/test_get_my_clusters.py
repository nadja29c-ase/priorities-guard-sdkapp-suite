"""
Unit tests for get_my_clusters tool.
"""

import pytest
from unittest.mock import AsyncMock, patch

from mcp_server.clarity.tools.get_my_clusters import handle


class TestGetMyClusters:
    """Tests for the get_my_clusters tool handler."""

    @pytest.mark.asyncio
    async def test_handle_returns_clusters_when_found(self):
        """Should return clusters and has_history=True when user has data."""
        mock_cluster_data = {
            "cluster_id": "cluster-abc",
            "cluster_data": {
                "clusters": [
                    {
                        "cluster_name": "Work Tasks",
                        "thought_items": ["Review PR", "Update docs"],
                        "subclusters": [],
                        "tags": [],
                    }
                ]
            },
            "thoughts_exhausted": True,
            "correctly_clustered": True,
            "created_at": "2025-01-15T10:00:00Z",
        }

        with patch("mcp_server.clarity.tools.get_my_clusters.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_cluster_data

            result = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        assert result.isError is not True
        assert result.structuredContent["has_history"] is True
        assert len(result.structuredContent["clusters"]) == 1
        assert result.structuredContent["clusters"][0]["cluster_name"] == "Work Tasks"
        assert result.structuredContent["last_updated"] == "2025-01-15T10:00:00Z"
        assert "Retrieved 1 existing clusters" in result.content[0].text

    @pytest.mark.asyncio
    async def test_handle_returns_empty_when_no_history(self):
        """Should return empty clusters and has_history=False when user has no data."""
        with patch("mcp_server.clarity.tools.get_my_clusters.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            result = await handle(
                user_id="user-new",
                correlation_id="corr-123",
                arguments={},
            )

        assert result.isError is not True
        assert result.structuredContent["has_history"] is False
        assert result.structuredContent["clusters"] == []
        assert "No existing clusters found" in result.content[0].text

    @pytest.mark.asyncio
    async def test_handle_returns_multiple_clusters(self):
        """Should return all clusters when user has multiple."""
        mock_cluster_data = {
            "cluster_id": "cluster-xyz",
            "cluster_data": {
                "clusters": [
                    {"cluster_name": "Work", "thought_items": ["Task 1"], "subclusters": [], "tags": []},
                    {"cluster_name": "Personal", "thought_items": ["Task 2"], "subclusters": [], "tags": []},
                    {"cluster_name": "Learning", "thought_items": ["Task 3"], "subclusters": [], "tags": []},
                ]
            },
            "thoughts_exhausted": True,
            "correctly_clustered": None,
            "created_at": "2025-01-15T12:00:00Z",
        }

        with patch("mcp_server.clarity.tools.get_my_clusters.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_cluster_data

            result = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        assert result.structuredContent["has_history"] is True
        assert len(result.structuredContent["clusters"]) == 3
        assert "Retrieved 3 existing clusters" in result.content[0].text

    @pytest.mark.asyncio
    async def test_handle_calls_get_cluster_with_user_id(self):
        """Should call get_cluster with correct user_id."""
        with patch("mcp_server.clarity.tools.get_my_clusters.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            await handle(
                user_id="specific-user-id",
                correlation_id="corr-123",
                arguments={},
            )

        mock_get.assert_called_once_with("specific-user-id")

    @pytest.mark.asyncio
    async def test_handle_ignores_arguments(self):
        """Should work regardless of arguments passed (tool takes no input)."""
        with patch("mcp_server.clarity.tools.get_my_clusters.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            # Even with extra arguments, it should work
            result = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={"some_random_key": "value"},
            )

        assert result.isError is not True
        assert result.structuredContent["has_history"] is False
