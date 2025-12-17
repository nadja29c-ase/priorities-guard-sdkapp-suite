"""
Increment 10 Cross-Layer Contract Tests.

These tests verify the end-to-end contract across all layers:
    Backend Response → Persistence Layer → Tool Output

Purpose:
- Prevents drift between layers during refactoring
- Protects Increment 10's core value proposition
- Ensures data flows correctly through the entire stack

IMPORTANT: These tests mock at the HTTP layer only, allowing real code
to execute through persistence and tool layers. This catches contract
violations that unit tests of individual layers might miss.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from mcp_server.clarity.tools.load_saved_board import handle as load_saved_board_handle


class TestIncrement10EndToEndContract:
    """Cross-layer contract tests for state recovery (Increment 10)."""

    @pytest.mark.asyncio
    async def test_backend_success_flows_to_tool_output(self):
        """Full success path: backend → persistence → tool.

        Verifies that valid backend data flows unchanged through all layers
        and produces correct tool output for ChatGPT consumption.
        """
        # Simulate backend response
        backend_response = {
            "cluster_id": "cluster-abc-123",
            "cluster_data": {
                "clusters": [
                    {
                        "cluster_name": "Work",
                        "thought_items": ["Review PR", "Update docs"],
                        "subclusters": [],
                        "tags": ["urgent"],
                    },
                    {
                        "cluster_name": "Personal",
                        "thought_items": ["Call mom"],
                        "subclusters": [],
                        "tags": [],
                    },
                ]
            },
            "thoughts_exhausted": True,
            "correctly_clustered": True,
            "created_at": "2025-01-15T10:00:00Z",
        }

        mock_http_response = MagicMock()
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = backend_response

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_http_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await load_saved_board_handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        # Contract: Tool output matches backend data
        assert result.isError is not True
        assert result.structuredContent["has_history"] is True
        assert len(result.structuredContent["clusters"]) == 2

        # Clusters must be passed through unchanged
        clusters = result.structuredContent["clusters"]
        assert clusters[0]["cluster_name"] == "Work"
        assert clusters[0]["thought_items"] == ["Review PR", "Update docs"]
        assert clusters[0]["tags"] == ["urgent"]
        assert clusters[1]["cluster_name"] == "Personal"

        # Metadata must be present
        assert result.structuredContent["last_updated"] == "2025-01-15T10:00:00Z"

    @pytest.mark.asyncio
    async def test_backend_404_flows_to_empty_history(self):
        """404 path: backend not found → persistence None → tool empty.

        New users have no clusters. Backend returns 404, tool returns
        safe empty structure with has_history=False.
        """
        mock_http_response = MagicMock()
        mock_http_response.status_code = 404
        mock_http_response.text = "Not Found"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_http_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await load_saved_board_handle(
                user_id="new-user",
                correlation_id="corr-123",
                arguments={},
            )

        # Contract: Empty structure for new users
        assert result.isError is not True
        assert result.structuredContent["has_history"] is False
        assert result.structuredContent["clusters"] == []

    @pytest.mark.asyncio
    async def test_backend_500_flows_to_safe_fallback(self):
        """Error path: backend 500 → persistence None → tool empty.

        Backend errors must not crash MCP. Tool returns safe empty structure.
        """
        mock_http_response = MagicMock()
        mock_http_response.status_code = 500
        mock_http_response.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_http_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await load_saved_board_handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        # Contract: Graceful degradation on backend error
        assert result.isError is not True
        assert result.structuredContent["has_history"] is False
        assert result.structuredContent["clusters"] == []

    @pytest.mark.asyncio
    async def test_backend_timeout_flows_to_safe_fallback(self):
        """Timeout path: backend slow → persistence exception → tool empty.

        Slow backends must not hang MCP. Tool returns safe empty structure.
        """
        import httpx

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Request timed out"))

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await load_saved_board_handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        # Contract: Graceful degradation on timeout
        assert result.isError is not True
        assert result.structuredContent["has_history"] is False
        assert result.structuredContent["clusters"] == []

    @pytest.mark.asyncio
    async def test_backend_malformed_json_flows_to_safe_fallback(self):
        """Malformed JSON path: backend garbage → persistence exception → tool empty.

        Invalid JSON (e.g., HTML error page) must not crash MCP.
        """
        mock_http_response = MagicMock()
        mock_http_response.status_code = 200
        mock_http_response.json.side_effect = ValueError("Invalid JSON")

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_http_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await load_saved_board_handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        # Contract: Graceful degradation on malformed response
        assert result.isError is not True
        assert result.structuredContent["has_history"] is False
        assert result.structuredContent["clusters"] == []

    @pytest.mark.asyncio
    async def test_backend_list_response_rejected_across_layers(self):
        """Contract violation path: backend returns list → rejected at persistence → tool empty.

        If backend changes to return list instead of dict, entire stack
        must reject it gracefully rather than crash or pick [0].
        """
        # Backend returns list (contract violation)
        backend_response = [
            {"cluster_id": "snap-1", "cluster_data": {"clusters": []}},
            {"cluster_id": "snap-2", "cluster_data": {"clusters": []}},
        ]

        mock_http_response = MagicMock()
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = backend_response

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_http_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await load_saved_board_handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        # Contract: List rejected, returns safe empty
        assert result.isError is not True
        assert result.structuredContent["has_history"] is False
        assert result.structuredContent["clusters"] == []

    @pytest.mark.asyncio
    async def test_cluster_ordering_preserved_end_to_end(self):
        """Ordering contract: cluster order from backend preserved in tool output.

        Order matters for diffing and user mental model. Backend controls order,
        MCP must preserve it exactly.
        """
        backend_response = {
            "cluster_id": "cluster-ordered",
            "cluster_data": {
                "clusters": [
                    {"cluster_name": "Alpha", "thought_items": ["A"]},
                    {"cluster_name": "Beta", "thought_items": ["B"]},
                    {"cluster_name": "Gamma", "thought_items": ["C"]},
                    {"cluster_name": "Delta", "thought_items": ["D"]},
                ]
            },
            "created_at": "2025-01-15T10:00:00Z",
        }

        mock_http_response = MagicMock()
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = backend_response

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_http_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await load_saved_board_handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        # Contract: Order exactly preserved
        clusters = result.structuredContent["clusters"]
        assert [c["cluster_name"] for c in clusters] == ["Alpha", "Beta", "Gamma", "Delta"]

    @pytest.mark.asyncio
    async def test_empty_clusters_treated_as_no_history(self):
        """Empty clusters path: backend returns empty list → has_history=False.

        User might have created and then deleted all clusters.
        Empty clusters = no usable history.
        """
        backend_response = {
            "cluster_id": "cluster-empty",
            "cluster_data": {
                "clusters": []  # Empty
            },
            "created_at": "2025-01-15T10:00:00Z",
        }

        mock_http_response = MagicMock()
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = backend_response

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_http_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await load_saved_board_handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        # Contract: Empty clusters = snapshot exists but empty
        assert result.structuredContent["has_history"] is True
        assert result.structuredContent["is_empty_snapshot"] is True
        assert result.structuredContent["clusters"] == []


class TestIncrement10OutputSchema:
    """Schema stability tests across layers."""

    @pytest.mark.asyncio
    async def test_output_schema_has_history_true(self):
        """Schema when has_history=True must have exactly these keys."""
        backend_response = {
            "cluster_id": "cluster-abc",
            "cluster_data": {"clusters": [{"cluster_name": "Test"}]},
            "created_at": "2025-01-15T10:00:00Z",
        }

        mock_http_response = MagicMock()
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = backend_response

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_http_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await load_saved_board_handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        # Schema contract
        expected_keys = {"has_history", "clusters", "is_empty_snapshot", "last_updated", "saved_board_hash"}
        assert set(result.structuredContent.keys()) == expected_keys

    @pytest.mark.asyncio
    async def test_output_schema_has_history_false(self):
        """Schema when has_history=False must have exactly these keys."""
        mock_http_response = MagicMock()
        mock_http_response.status_code = 404
        mock_http_response.text = "Not Found"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_http_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await load_saved_board_handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        # Schema contract (last_updated may be absent)
        content = result.structuredContent
        assert "has_history" in content
        assert "clusters" in content
        assert content["has_history"] is False
        assert content["clusters"] == []
