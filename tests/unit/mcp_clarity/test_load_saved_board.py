"""
Unit tests for load_saved_board tool.

Increment 10 Core Contract:
- When persistence returns None, tool returns safe empty structure
- Never crashes, never hallucinates data
- User sees actionable "no history" message
"""

import pytest
from unittest.mock import AsyncMock, patch

from mcp_server.clarity.tools.load_saved_board import handle


class TestLoadSavedBoardContract:
    """Increment 10 core promise: state recovery never crashes."""

    @pytest.mark.asyncio
    async def test_persistence_none_returns_safe_empty_structure(self):
        """CRITICAL: When get_cluster() returns None, tool returns user-safe structure.

        This is the core promise of Increment 10:
        - No crash on missing data
        - No hallucinated clusters
        - Explicit has_history=False flag for LLM
        - Empty clusters list (not None, not missing key)
        - Actionable user message

        If this test fails, Increment 10's state recovery is broken.
        """
        with patch("mcp_server.clarity.tools.load_saved_board.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None  # Simulates: new user, network error, or no history

            result = await handle(
                user_id="user-new",
                correlation_id="corr-123",
                arguments={},
            )

        # Core guarantees
        assert result.isError is not True, "Must not return error for missing data"
        assert result.structuredContent is not None, "Must return structured content"

        # Safe structure for LLM consumption
        assert result.structuredContent["has_history"] is False, "Must signal no history"
        assert result.structuredContent["clusters"] == [], "Must return empty list, not None"
        assert "clusters" in result.structuredContent, "clusters key must exist"

        # User-facing message exists (content is implementation detail)
        assert len(result.content) > 0, "Must have user message"
        assert isinstance(result.content[0].text, str), "Message must be string"

        # Persistence contract: exactly one call with correlation_id, no retries
        mock_get.assert_called_once_with(user_id="user-new", correlation_id="corr-123")

    @pytest.mark.asyncio
    async def test_persistence_error_does_not_crash_tool(self):
        """Persistence layer errors must not crash the MCP tool.

        get_cluster() returns None on network errors, timeouts, etc.
        Tool must handle this gracefully with empty structure.
        """
        with patch("mcp_server.clarity.tools.load_saved_board.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None  # Persistence returns None on any error

            # Must not raise
            result = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        assert result.isError is not True
        assert result.structuredContent["has_history"] is False
        # No retry on error - exactly one call with correlation_id
        mock_get.assert_called_once_with(user_id="user-456", correlation_id="corr-123")

    @pytest.mark.asyncio
    async def test_malformed_cluster_payload_missing_clusters_key(self):
        """Malformed backend data with missing clusters key is treated as empty snapshot.

        Backend might return data with missing 'clusters' key due to:
        - Schema changes
        - Migration bugs
        - Partial data corruption

        Increment 10 promise: never crash, never hallucinate.
        Semantic: snapshot exists (has_history=True), but empty (is_empty_snapshot=True).
        """
        malformed = {
            "cluster_id": "cluster-bad",
            "cluster_data": {},  # missing clusters key
            "created_at": "2025-01-15T10:00:00Z",
        }

        with patch("mcp_server.clarity.tools.load_saved_board.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = malformed

            result = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        assert result.isError is not True
        assert result.structuredContent["clusters"] == []
        # Snapshot exists but is malformed → treated as empty snapshot
        assert result.structuredContent["has_history"] is True
        assert result.structuredContent["is_empty_snapshot"] is True

    @pytest.mark.asyncio
    async def test_malformed_cluster_payload_clusters_is_none(self):
        """Backend returning clusters=None is treated as empty snapshot.

        Edge case where clusters key exists but value is None.
        Semantic: snapshot exists (has_history=True), but empty (is_empty_snapshot=True).
        """
        malformed = {
            "cluster_id": "cluster-bad",
            "cluster_data": {"clusters": None},
            "created_at": "2025-01-15T10:00:00Z",
        }

        with patch("mcp_server.clarity.tools.load_saved_board.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = malformed

            result = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        assert result.isError is not True
        assert result.structuredContent["clusters"] == []
        assert result.structuredContent["has_history"] is True
        assert result.structuredContent["is_empty_snapshot"] is True

    @pytest.mark.asyncio
    async def test_malformed_cluster_payload_missing_cluster_data(self):
        """Backend missing cluster_data entirely is treated as empty snapshot.

        Semantic: snapshot exists (has_history=True), but empty (is_empty_snapshot=True).
        """
        malformed = {
            "cluster_id": "cluster-bad",
            # cluster_data key missing entirely
            "created_at": "2025-01-15T10:00:00Z",
        }

        with patch("mcp_server.clarity.tools.load_saved_board.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = malformed

            result = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        assert result.isError is not True
        assert result.structuredContent["clusters"] == []
        assert result.structuredContent["has_history"] is True
        assert result.structuredContent["is_empty_snapshot"] is True

    @pytest.mark.asyncio
    async def test_partial_cluster_payload_passed_through(self):
        """Partial clusters are passed through unchanged (read-only passthrough).

        Tool is NOT a validator - it passes whatever backend returns.
        Clusters missing thought_items/tags/subclusters are still valid history.
        Validation is the responsibility of organize_thoughts (write path).

        This locks in the design decision: load_saved_board is pure read.
        """
        partial_cluster = {"cluster_name": "Work"}  # missing thought_items, tags, subclusters

        mock_cluster_data = {
            "cluster_id": "cluster-partial",
            "cluster_data": {"clusters": [partial_cluster]},
            "thoughts_exhausted": True,
            "correctly_clustered": True,
            "created_at": "2025-01-15T10:00:00Z",
        }

        with patch("mcp_server.clarity.tools.load_saved_board.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_cluster_data

            result = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        # Partial cluster passed through - has_history=True
        assert result.isError is not True
        assert result.structuredContent["has_history"] is True
        assert len(result.structuredContent["clusters"]) == 1
        assert result.structuredContent["clusters"][0] == partial_cluster

    @pytest.mark.asyncio
    async def test_mixed_valid_and_malformed_clusters_passed_through(self):
        """Mixed valid + malformed clusters are passed through unchanged.

        DESIGN DECISION:
        Tool is a read-only passthrough, NOT a validator. When backend returns
        a mix of valid and malformed clusters:
        - All clusters are passed through unchanged
        - has_history=True (non-empty list)
        - No filtering, no dropping, no validation

        Rationale:
        - Validation is the responsibility of organize_thoughts (write path)
        - Backend is source of truth; if it saved it, we return it
        - Filtering here could hide data corruption issues
        - ChatGPT can handle malformed clusters gracefully

        If stricter behavior is needed, add validation to persistence layer
        or backend, not here.
        """
        mixed_clusters = [
            # Valid cluster
            {"cluster_name": "Work", "thought_items": ["Task 1"], "tags": ["urgent"]},
            # Malformed: missing cluster_name
            {"thought_items": ["Orphan task"]},
            # Malformed: wrong types
            {"cluster_name": 123, "thought_items": "not a list"},
            # Valid cluster
            {"cluster_name": "Personal", "thought_items": ["Call mom"]},
            # Malformed: empty dict
            {},
        ]

        mock_cluster_data = {
            "cluster_id": "cluster-mixed",
            "cluster_data": {"clusters": mixed_clusters},
            "created_at": "2025-01-15T10:00:00Z",
        }

        with patch("mcp_server.clarity.tools.load_saved_board.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_cluster_data

            result = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        # All clusters passed through - no filtering
        assert result.isError is not True
        assert result.structuredContent["has_history"] is True
        assert result.structuredContent["clusters"] == mixed_clusters, \
            "All clusters must be passed through unchanged, including malformed ones"
        assert len(result.structuredContent["clusters"]) == 5

    @pytest.mark.asyncio
    async def test_cluster_order_preserved_from_backend(self):
        """Cluster order must be preserved from backend response.

        Ordering matters for:
        - Diff computation (what changed)
        - ChatGPT comparisons between sessions
        - User mental model (first cluster = most important)

        Backend controls order; tool is a passthrough.
        """
        ordered_clusters = [
            {"cluster_name": "First", "thought_items": ["A"]},
            {"cluster_name": "Second", "thought_items": ["B"]},
            {"cluster_name": "Third", "thought_items": ["C"]},
        ]

        mock_cluster_data = {
            "cluster_id": "cluster-ordered",
            "cluster_data": {"clusters": ordered_clusters},
            "created_at": "2025-01-15T10:00:00Z",
        }

        with patch("mcp_server.clarity.tools.load_saved_board.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_cluster_data

            result = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        # Order must be exactly preserved
        returned = result.structuredContent["clusters"]
        assert len(returned) == 3
        assert returned[0]["cluster_name"] == "First"
        assert returned[1]["cluster_name"] == "Second"
        assert returned[2]["cluster_name"] == "Third"

    @pytest.mark.asyncio
    async def test_tool_does_not_sort_or_reorder_clusters(self):
        """Tool must NOT sort, normalize, or reorder clusters.

        Guards against future "helpful" sorting like:
        - Alphabetical by cluster_name
        - By timestamp
        - By thought count
        - By tag priority

        MCP is a passthrough. Backend controls order. User expects
        clusters in the exact order they were saved.
        """
        # Deliberately "wrong" order: Z before A, no logical sorting
        unsorted_clusters = [
            {"cluster_name": "Zebra", "thought_items": ["Z1"]},
            {"cluster_name": "Apple", "thought_items": ["A1", "A2", "A3"]},
            {"cluster_name": "123-Numbers", "thought_items": ["N1"]},
            {"cluster_name": "middle", "thought_items": ["M1", "M2"]},
        ]

        mock_cluster_data = {
            "cluster_id": "cluster-unsorted",
            "cluster_data": {"clusters": unsorted_clusters},
            "created_at": "2025-01-15T10:00:00Z",
        }

        with patch("mcp_server.clarity.tools.load_saved_board.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_cluster_data

            result = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        # Exact order preserved - no sorting applied
        returned = result.structuredContent["clusters"]
        assert returned == unsorted_clusters, \
            "Tool must not sort or reorder clusters - exact passthrough required"

    @pytest.mark.asyncio
    async def test_large_cluster_payload_handled(self):
        """Large cluster payloads must be returned without truncation.

        Guards against accidental size-based logic (summarization, truncation).
        MCP should pass through all clusters regardless of count.
        """
        large_clusters = [
            {"cluster_name": f"Cluster-{i}", "thought_items": [f"Task-{i}"]}
            for i in range(50)
        ]

        mock_cluster_data = {
            "cluster_id": "cluster-large",
            "cluster_data": {"clusters": large_clusters},
            "created_at": "2025-01-15T10:00:00Z",
        }

        with patch("mcp_server.clarity.tools.load_saved_board.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_cluster_data

            result = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        assert result.isError is not True
        assert result.structuredContent["has_history"] is True
        assert len(result.structuredContent["clusters"]) == 50, "All clusters must be returned"

    @pytest.mark.asyncio
    async def test_extremely_large_cluster_payload_does_not_timeout(self):
        """Adversarial large payloads must pass through without truncation.

        This documents the upper bound: MCP is a passthrough, not an optimizer.
        Guards against:
        - Accidental summarization logic
        - Size-based truncation
        - Memory pressure causing timeouts

        ChatGPT can generate large outputs. Tool must handle them.
        """
        # 500 clusters with subclusters and thought items = realistic stress test
        large_clusters = [
            {
                "cluster_name": f"Cluster-{i}",
                "thought_items": [f"Thought-{i}-{j}" for j in range(5)],
                "subclusters": [
                    {
                        "subcluster_name": f"Sub-{i}-{k}",
                        "thought_items": [f"SubThought-{i}-{k}-{m}" for m in range(3)],
                        "tags": ["urgent"] if k % 2 == 0 else [],
                    }
                    for k in range(3)
                ],
                "tags": ["project"] if i % 5 == 0 else [],
            }
            for i in range(500)
        ]

        mock_cluster_data = {
            "cluster_id": "cluster-stress",
            "cluster_data": {"clusters": large_clusters},
            "created_at": "2025-01-15T10:00:00Z",
        }

        with patch("mcp_server.clarity.tools.load_saved_board.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_cluster_data

            result = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        # Core assertions
        assert result.isError is not True
        assert result.structuredContent["has_history"] is True
        assert len(result.structuredContent["clusters"]) == 500, \
            "All 500 clusters must be returned without truncation"

        # Spot check first and last clusters preserved correctly
        first = result.structuredContent["clusters"][0]
        last = result.structuredContent["clusters"][499]
        assert first["cluster_name"] == "Cluster-0"
        assert last["cluster_name"] == "Cluster-499"
        assert len(first["subclusters"]) == 3, "Subclusters must not be truncated"
        assert len(first["thought_items"]) == 5, "Thought items must not be truncated"

    @pytest.mark.asyncio
    async def test_get_cluster_exception_returns_safe_empty(self):
        """Exceptions from get_cluster must be swallowed, not propagated.

        Locks in resilience even if persistence layer changes.
        Tool must never crash on backend failures.
        """
        with patch("mcp_server.clarity.tools.load_saved_board.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = Exception("Network timeout")

            result = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        # Must return safe empty structure, not crash
        assert result.isError is not True
        assert result.structuredContent["has_history"] is False
        assert result.structuredContent["clusters"] == []
        # Critical: no retry on exception - exactly one call with correlation_id
        mock_get.assert_called_once_with(user_id="user-456", correlation_id="corr-123")

    @pytest.mark.asyncio
    async def test_output_schema_stable_when_no_history(self):
        """Schema must be stable when has_history=False.

        ChatGPT-side logic depends on exact keys. No drift allowed.
        """
        with patch("mcp_server.clarity.tools.load_saved_board.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            result = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        content = result.structuredContent

        # Required keys must exist
        assert "has_history" in content, "has_history key required"
        assert "clusters" in content, "clusters key required"

        # Types must be correct
        assert isinstance(content["has_history"], bool)
        assert isinstance(content["clusters"], list)

        # No unexpected keys (when no history, last_updated is optional/absent)
        allowed_keys = {"has_history", "clusters", "is_empty_snapshot", "last_updated", "saved_board_hash"}
        assert set(content.keys()) <= allowed_keys, \
            f"Unexpected keys: {set(content.keys()) - allowed_keys}"

    @pytest.mark.asyncio
    async def test_output_schema_stable_when_has_history(self):
        """Schema must be stable when has_history=True.

        ChatGPT-side logic depends on exact keys. No drift allowed.
        """
        mock_cluster_data = {
            "cluster_id": "cluster-abc",
            "cluster_data": {"clusters": [{"cluster_name": "Test"}]},
            "created_at": "2025-01-15T10:00:00Z",
        }

        with patch("mcp_server.clarity.tools.load_saved_board.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_cluster_data

            result = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        content = result.structuredContent

        # Required keys must exist
        assert "has_history" in content, "has_history key required"
        assert "clusters" in content, "clusters key required"
        assert "last_updated" in content, "last_updated key required when has_history=True"

        # Types must be correct
        assert isinstance(content["has_history"], bool)
        assert isinstance(content["clusters"], list)
        assert content["last_updated"] is None or isinstance(content["last_updated"], str)

        # No unexpected keys
        allowed_keys = {"has_history", "clusters", "is_empty_snapshot", "last_updated", "saved_board_hash"}
        assert set(content.keys()) == allowed_keys, \
            f"Schema mismatch. Expected {allowed_keys}, got {set(content.keys())}"

    @pytest.mark.asyncio
    async def test_list_from_persistence_treated_as_no_history(self):
        """If persistence returns a list (contract violation), treat as no history.

        Defense in depth: persistence layer rejects lists today, but if that
        changes, tool should not silently pick [0] or crash on .get() call.
        Safer to treat as corrupted state → empty history.
        """
        # Simulate persistence layer returning a list (future refactor risk)
        multiple_snapshots = [
            {"cluster_id": "snap-1", "cluster_data": {"clusters": [{"cluster_name": "A"}]}},
            {"cluster_id": "snap-2", "cluster_data": {"clusters": [{"cluster_name": "B"}]}},
        ]

        with patch("mcp_server.clarity.tools.load_saved_board.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = multiple_snapshots

            result = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        # Must fail safe, not crash or pick arbitrary snapshot
        assert result.isError is not True
        assert result.structuredContent["has_history"] is False
        assert result.structuredContent["clusters"] == []

    @pytest.mark.asyncio
    async def test_same_input_produces_same_output(self):
        """Tool must be deterministic for same backend payload.

        Guards against:
        - Future "helpful" enrichment adding timestamps, IDs, or metadata
        - Random ordering in JSON serialization
        - Any non-deterministic behavior

        Determinism is critical for:
        - Diffing between sessions
        - User trust (same input = same output)
        - Debugging and reproducibility
        """
        mock_cluster_data = {
            "cluster_id": "cluster-abc",
            "cluster_data": {
                "clusters": [
                    {"cluster_name": "Work", "thought_items": ["A", "B"], "tags": ["urgent"]},
                    {"cluster_name": "Personal", "thought_items": ["C"], "subclusters": []},
                ]
            },
            "created_at": "2025-01-15T10:00:00Z",
        }

        with patch("mcp_server.clarity.tools.load_saved_board.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_cluster_data

            # Call twice with identical inputs
            result1 = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )
            result2 = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        # Structured content must be identical (this is what ChatGPT consumes)
        assert result1.structuredContent == result2.structuredContent, \
            "Tool must be deterministic - same input must produce same output"

        # Note: We intentionally don't assert text content equality.
        # User-facing copy may change; structuredContent is the contract.

    @pytest.mark.asyncio
    async def test_tool_does_not_mutate_persistence_data(self):
        """Tool must not mutate any part of persistence data (deep check).

        Future enrichment logic might accidentally modify nested structures:
        - Cluster list itself
        - Individual cluster dicts
        - Nested subclusters, thought_items, tags

        Mutating persistence data creates subtle, hard-to-debug issues.
        """
        import copy

        mock_cluster_data = {
            "cluster_id": "cluster-xyz",
            "cluster_data": {
                "clusters": [
                    {
                        "cluster_name": "Work",
                        "thought_items": ["Task 1", "Task 2"],
                        "subclusters": [
                            {"subcluster_name": "Urgent", "thought_items": ["Sub 1"], "tags": ["urgent"]},
                        ],
                        "tags": ["project"],
                    },
                    {
                        "cluster_name": "Personal",
                        "thought_items": ["Task 3"],
                        "subclusters": [],
                        "tags": [],
                    },
                ]
            },
            "thoughts_exhausted": True,
            "correctly_clustered": True,
            "created_at": "2025-01-15T10:00:00Z",
        }

        # Deep freeze the original state
        original_state = copy.deepcopy(mock_cluster_data)

        with patch("mcp_server.clarity.tools.load_saved_board.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_cluster_data

            await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        # Deep compare: catches any nested mutation
        assert mock_cluster_data == original_state, \
            "Tool must not mutate persistence data at any level"

    @pytest.mark.asyncio
    async def test_handle_accepts_none_correlation_id(self):
        """Tool must not crash if correlation_id is None.

        correlation_id is used for tracing only - missing value must not break tool.
        """
        with patch("mcp_server.clarity.tools.load_saved_board.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            result = await handle(
                user_id="user-456",
                correlation_id=None,
                arguments={},
            )

        assert result.isError is not True

    @pytest.mark.asyncio
    async def test_none_user_id_treated_as_no_history(self):
        """None user_id must not crash - treated as no history.

        AUTH BOUNDARY DESIGN DECISION:
        - Auth validation happens at the MCP dispatcher level (before tool is called)
        - By the time handle() is called, user_id SHOULD be validated
        - But defense in depth: tool gracefully handles None → no history

        If you want fail-closed behavior, add validation at tool entry and update this test.
        Current behavior: None user_id flows to persistence → returns None → has_history=False
        """
        with patch("mcp_server.clarity.tools.load_saved_board.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None  # Persistence returns None for invalid user

            result = await handle(
                user_id=None,
                correlation_id="corr-123",
                arguments={},
            )

        # Current behavior: graceful degradation, not error
        assert result.isError is not True, "None user_id should not crash tool"
        assert result.structuredContent["has_history"] is False
        assert result.structuredContent["clusters"] == []

    @pytest.mark.asyncio
    async def test_empty_user_id_treated_as_no_history(self):
        """Empty string user_id must not crash - treated as no history.

        Same design as test_none_user_id_treated_as_no_history.
        Empty string flows to persistence → backend returns 401 → None → has_history=False
        """
        with patch("mcp_server.clarity.tools.load_saved_board.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None  # Persistence returns None for invalid user

            result = await handle(
                user_id="",
                correlation_id="corr-123",
                arguments={},
            )

        # Current behavior: graceful degradation, not error
        assert result.isError is not True, "Empty user_id should not crash tool"
        assert result.structuredContent["has_history"] is False
        assert result.structuredContent["clusters"] == []


class TestLoadSavedBoard:
    """Tests for the load_saved_board tool handler."""

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

        with patch("mcp_server.clarity.tools.load_saved_board.get_cluster", new_callable=AsyncMock) as mock_get:
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
        # User message exists (content is implementation detail)
        assert len(result.content) > 0
        assert isinstance(result.content[0].text, str)

    @pytest.mark.asyncio
    async def test_handle_returns_empty_when_no_history(self):
        """Should return empty clusters and has_history=False when user has no data."""
        with patch("mcp_server.clarity.tools.load_saved_board.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            result = await handle(
                user_id="user-new",
                correlation_id="corr-123",
                arguments={},
            )

        assert result.isError is not True
        assert result.structuredContent["has_history"] is False
        assert result.structuredContent["clusters"] == []
        # User message exists (content is implementation detail)
        assert len(result.content) > 0
        assert isinstance(result.content[0].text, str)

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

        with patch("mcp_server.clarity.tools.load_saved_board.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_cluster_data

            result = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={},
            )

        assert result.structuredContent["has_history"] is True
        assert len(result.structuredContent["clusters"]) == 3
        # User message exists (content is implementation detail)
        assert len(result.content) > 0
        assert isinstance(result.content[0].text, str)

    @pytest.mark.asyncio
    async def test_handle_calls_get_cluster_with_user_id(self):
        """Should call get_cluster with correct user_id and correlation_id."""
        with patch("mcp_server.clarity.tools.load_saved_board.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            await handle(
                user_id="specific-user-id",
                correlation_id="corr-123",
                arguments={},
            )

        mock_get.assert_called_once_with(user_id="specific-user-id", correlation_id="corr-123")

    @pytest.mark.asyncio
    async def test_handle_ignores_arguments(self):
        """Should work regardless of arguments passed (tool takes no input)."""
        with patch("mcp_server.clarity.tools.load_saved_board.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None

            # Even with extra arguments, it should work
            result = await handle(
                user_id="user-456",
                correlation_id="corr-123",
                arguments={"some_random_key": "value"},
            )

        assert result.isError is not True
        assert result.structuredContent["has_history"] is False
