"""
Unit tests for read_board_before_editing tool.

This tool returns data only - NO widget metadata.
Critical difference from load_saved_board: result.meta must always be None.
"""

import pytest
from unittest.mock import AsyncMock, patch

from mcp_server.clarity.tools.read_board_before_editing import handle


class TestReadSavedBoardNoWidget:
    """CRITICAL: read_board_before_editing must NEVER include widget metadata."""

    @pytest.mark.asyncio
    async def test_no_meta_when_clusters_found(self):
        """result.meta must be None when clusters are returned."""
        mock_cluster_data = {
            "cluster_id": "cluster-abc",
            "cluster_data": {
                "clusters": [{"cluster_name": "Work", "thought_items": ["Task 1"]}]
            },
            "created_at": "2025-01-15T10:00:00Z",
            "content_hash": "abc123",
        }

        with patch("mcp_server.clarity.tools.read_board_before_editing.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_cluster_data

            result = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        assert result.meta is None, "read_board_before_editing must NEVER return widget metadata"

    @pytest.mark.asyncio
    async def test_no_meta_when_no_history(self):
        """result.meta must be None when no saved board exists."""
        with patch("mcp_server.clarity.tools.read_board_before_editing.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            result = await handle(
                user_id="user-new",
                correlation_id="corr-123",
                arguments={},
            )

        assert result.meta is None, "read_board_before_editing must NEVER return widget metadata"

    @pytest.mark.asyncio
    async def test_no_meta_when_empty_snapshot(self):
        """result.meta must be None when snapshot exists but is empty."""
        mock_cluster_data = {
            "cluster_id": "cluster-empty",
            "cluster_data": {"clusters": []},
            "created_at": "2025-01-15T10:00:00Z",
            "content_hash": "empty123",
        }

        with patch("mcp_server.clarity.tools.read_board_before_editing.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_cluster_data

            result = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        assert result.meta is None, "read_board_before_editing must NEVER return widget metadata"

    @pytest.mark.asyncio
    async def test_no_meta_on_persistence_error(self):
        """result.meta must be None even when persistence fails."""
        with patch("mcp_server.clarity.tools.read_board_before_editing.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = Exception("Network error")

            result = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        assert result.meta is None, "read_board_before_editing must NEVER return widget metadata"


class TestReadSavedBoardReturnsData:
    """read_board_before_editing must return clusters and saved_board_hash."""

    @pytest.mark.asyncio
    async def test_returns_clusters_when_found(self):
        """Should return clusters in structuredContent."""
        mock_cluster_data = {
            "cluster_id": "cluster-abc",
            "cluster_data": {
                "clusters": [
                    {"cluster_name": "Work", "thought_items": ["Task 1", "Task 2"]},
                    {"cluster_name": "Personal", "thought_items": ["Task 3"]},
                ]
            },
            "created_at": "2025-01-15T10:00:00Z",
            "content_hash": "hash123",
        }

        with patch("mcp_server.clarity.tools.read_board_before_editing.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_cluster_data

            result = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        assert result.isError is not True
        assert len(result.structuredContent["clusters"]) == 2
        assert result.structuredContent["clusters"][0]["cluster_name"] == "Work"

    @pytest.mark.asyncio
    async def test_returns_saved_board_hash(self):
        """Should return saved_board_hash from persistence."""
        mock_cluster_data = {
            "cluster_id": "cluster-abc",
            "cluster_data": {"clusters": [{"cluster_name": "Test", "thought_items": ["A"]}]},
            "created_at": "2025-01-15T10:00:00Z",
            "content_hash": "expected_hash_value",
        }

        with patch("mcp_server.clarity.tools.read_board_before_editing.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_cluster_data

            result = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        assert result.structuredContent["saved_board_hash"] == "expected_hash_value"

    @pytest.mark.asyncio
    async def test_returns_null_hash_when_no_history(self):
        """Should return null saved_board_hash when no saved board."""
        with patch("mcp_server.clarity.tools.read_board_before_editing.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            result = await handle(
                user_id="user-new",
                correlation_id="corr-123",
                arguments={},
            )

        assert result.structuredContent["saved_board_hash"] is None


class TestReadSavedBoardEmptyState:
    """read_board_before_editing empty state handling."""

    @pytest.mark.asyncio
    async def test_empty_clusters_when_no_history(self):
        """Should return empty clusters list when no saved board."""
        with patch("mcp_server.clarity.tools.read_board_before_editing.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            result = await handle(
                user_id="user-new",
                correlation_id="corr-123",
                arguments={},
            )

        assert result.isError is not True
        assert result.structuredContent["clusters"] == []
        assert result.structuredContent["has_history"] is False

    @pytest.mark.asyncio
    async def test_empty_snapshot_has_history_true(self):
        """Empty snapshot should have has_history=True, is_empty_snapshot=True."""
        mock_cluster_data = {
            "cluster_id": "cluster-empty",
            "cluster_data": {"clusters": []},
            "created_at": "2025-01-15T10:00:00Z",
        }

        with patch("mcp_server.clarity.tools.read_board_before_editing.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_cluster_data

            result = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        assert result.structuredContent["has_history"] is True
        assert result.structuredContent["is_empty_snapshot"] is True
        assert result.structuredContent["clusters"] == []


class TestReadSavedBoardPersistenceError:
    """read_board_before_editing persistence error handling."""

    @pytest.mark.asyncio
    async def test_exception_returns_safe_empty(self):
        """Persistence exceptions should return safe empty structure."""
        with patch("mcp_server.clarity.tools.read_board_before_editing.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = Exception("Database connection failed")

            result = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        assert result.isError is not True
        assert result.structuredContent["clusters"] == []
        assert result.structuredContent["has_history"] is False

    @pytest.mark.asyncio
    async def test_no_retry_on_error(self):
        """Should not retry on persistence error."""
        with patch("mcp_server.clarity.tools.read_board_before_editing.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = Exception("Timeout")

            await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        mock_get.assert_called_once()


class TestReadSavedBoardSchemaStability:
    """read_board_before_editing schema stability tests."""

    @pytest.mark.asyncio
    async def test_schema_when_no_history(self):
        """Schema must be stable when has_history=False."""
        with patch("mcp_server.clarity.tools.read_board_before_editing.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            result = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        content = result.structuredContent
        assert "has_history" in content
        assert "clusters" in content
        assert "saved_board_hash" in content
        assert isinstance(content["clusters"], list)
        assert isinstance(content["has_history"], bool)

    @pytest.mark.asyncio
    async def test_schema_when_has_history(self):
        """Schema must be stable when has_history=True."""
        mock_cluster_data = {
            "cluster_id": "cluster-abc",
            "cluster_data": {"clusters": [{"cluster_name": "Test", "thought_items": ["A"]}]},
            "created_at": "2025-01-15T10:00:00Z",
            "content_hash": "hash123",
        }

        with patch("mcp_server.clarity.tools.read_board_before_editing.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_cluster_data

            result = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        content = result.structuredContent
        allowed_keys = {"has_history", "clusters", "is_empty_snapshot", "last_updated", "saved_board_hash"}
        assert set(content.keys()) == allowed_keys

    @pytest.mark.asyncio
    async def test_no_arguments_required(self):
        """Tool should work with empty arguments."""
        with patch("mcp_server.clarity.tools.read_board_before_editing.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            result = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        assert result.isError is not True
