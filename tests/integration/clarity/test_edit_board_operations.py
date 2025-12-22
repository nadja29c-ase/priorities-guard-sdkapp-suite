"""
Integration tests for edit_board new operations.

Invariant under test: All edit_board operations are non-destructive
with respect to existing priorities.

Tests:
1. test_add_thought_item_preserves_priorities — add item to board with P1/P2, verify priorities unchanged
2. test_add_tag_preserves_priorities — add tag to board with priorities, verify priorities unchanged
3. test_remove_tag_preserves_priorities — remove tag from board with priorities, verify priorities unchanged
4. test_add_then_save_persists — add_thought_item → save_board → load_saved_board shows new item
"""

import pytest
from unittest.mock import AsyncMock, patch
from mcp_server.clarity.tools.edit_board import handle as edit_handle


# ============================================================================
# Test Fixtures
# ============================================================================


def make_cluster(name, items=None, subclusters=None, priority=None, tags=None):
    """Helper to create cluster dicts."""
    return {
        "cluster_name": name,
        "thought_items": items or [],
        "subclusters": subclusters or [],
        "tags": tags or [],
        "priority": priority,
    }


def make_subcluster(name, items=None, priority=None, tags=None):
    """Helper to create subcluster dicts."""
    return {
        "subcluster_name": name,
        "thought_items": items or [],
        "tags": tags or [],
        "priority": priority,
    }


# ============================================================================
# Priority Preservation Integration Tests
# ============================================================================


class TestNewOperationsPriorityPreservation:
    """
    Integration tests verifying that new edit_board operations
    do NOT modify existing priorities.
    """

    @pytest.mark.asyncio
    async def test_add_thought_item_preserves_priorities(self):
        """
        add_thought_item to board with P1/P2 → priorities unchanged.
        """
        board = [
            make_cluster("Work", items=["task1"], priority={"rank": "P1", "reason": None}),
            make_cluster("Home", items=["chore"], priority={"rank": "P2", "reason": None}),
            make_cluster("Health", items=["exercise"]),
        ]

        result = await edit_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "board": board,
                "operation": "add_thought_item",
                "parent_name": "Health",
                "text": "new thought item",
            },
        )

        assert result.isError is None or result.isError is False
        clusters = result.structuredContent["clusters"]

        # Verify P1/P2 are still intact
        work = next(c for c in clusters if c["cluster_name"] == "Work")
        home = next(c for c in clusters if c["cluster_name"] == "Home")
        health = next(c for c in clusters if c["cluster_name"] == "Health")

        assert work["priority"]["rank"] == "P1"
        assert home["priority"]["rank"] == "P2"
        assert health["priority"] is None

        # Verify new item was added
        assert "new thought item" in health["thought_items"]

    @pytest.mark.asyncio
    async def test_add_thought_item_preserves_thought_item_priorities(self):
        """
        add_thought_item when existing items have priorities → priorities unchanged.
        """
        board = [
            make_cluster("Work", items=[
                {"text": "important task", "priority": {"rank": "P1", "reason": None}},
                "regular task",
            ]),
        ]

        result = await edit_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "board": board,
                "operation": "add_thought_item",
                "parent_name": "Work",
                "text": "new task",
            },
        )

        assert result.isError is None or result.isError is False
        clusters = result.structuredContent["clusters"]

        # Verify thought item priority preserved
        work = clusters[0]
        assert work["thought_items"][0]["priority"]["rank"] == "P1"

        # Verify new item was added
        assert "new task" in work["thought_items"]

    @pytest.mark.asyncio
    async def test_add_tag_preserves_priorities(self):
        """
        add_tag to board with priorities → priorities unchanged.
        """
        board = [
            make_cluster("Work", items=["task"], priority={"rank": "P1", "reason": None}),
            make_cluster("Home", items=["chore"], priority={"rank": "P2", "reason": None}),
        ]

        result = await edit_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "board": board,
                "operation": "add_tag",
                "target_name": "Work",
                "tag": "research",
            },
        )

        assert result.isError is None or result.isError is False
        clusters = result.structuredContent["clusters"]

        # Verify priorities unchanged
        work = next(c for c in clusters if c["cluster_name"] == "Work")
        home = next(c for c in clusters if c["cluster_name"] == "Home")

        assert work["priority"]["rank"] == "P1"
        assert home["priority"]["rank"] == "P2"

        # Verify tag was added
        assert "research" in work["tags"]

    @pytest.mark.asyncio
    async def test_remove_tag_preserves_priorities(self):
        """
        remove_tag from board with priorities → priorities unchanged.
        """
        board = [
            make_cluster("Work", items=["task"], priority={"rank": "P1", "reason": None}, tags=["research"]),
            make_cluster("Home", items=["chore"], priority={"rank": "P2", "reason": None}),
        ]

        result = await edit_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "board": board,
                "operation": "remove_tag",
                "target_name": "Work",
                "tag": "research",
            },
        )

        assert result.isError is None or result.isError is False
        clusters = result.structuredContent["clusters"]

        # Verify priorities unchanged
        work = next(c for c in clusters if c["cluster_name"] == "Work")
        home = next(c for c in clusters if c["cluster_name"] == "Home")

        assert work["priority"]["rank"] == "P1"
        assert home["priority"]["rank"] == "P2"

        # Verify tag was removed
        assert "research" not in work["tags"]

    @pytest.mark.asyncio
    async def test_add_thought_item_preserves_subcluster_priorities(self):
        """
        add_thought_item when subclusters have priorities → priorities unchanged.
        """
        board = [
            make_cluster("Work", subclusters=[
                make_subcluster("Urgent", items=["task"], priority={"rank": "P1", "reason": None}),
                make_subcluster("Later", items=["other"]),
            ]),
        ]

        result = await edit_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "board": board,
                "operation": "add_thought_item",
                "parent_name": "Later",
                "text": "new thought",
            },
        )

        assert result.isError is None or result.isError is False
        clusters = result.structuredContent["clusters"]

        # Verify subcluster priority preserved
        work = clusters[0]
        urgent = next(s for s in work["subclusters"] if s["subcluster_name"] == "Urgent")
        later = next(s for s in work["subclusters"] if s["subcluster_name"] == "Later")

        assert urgent["priority"]["rank"] == "P1"

        # Verify new item was added
        assert "new thought" in later["thought_items"]


class TestAddThenSavePersists:
    """
    Integration test: add_thought_item → save_board → load_saved_board
    shows new item.
    """

    @pytest.mark.asyncio
    async def test_add_then_save_persists(self):
        """
        add_thought_item → save_board → load_saved_board shows new item.
        """
        from mcp_server.clarity.tools.save_board import handle as save_handle
        from mcp_server.clarity.tools.load_saved_board import handle as load_handle

        # Start with a board
        board = [
            make_cluster("Work", items=["task1"]),
            make_cluster("Home", items=["chore"]),
        ]

        # Add a thought item
        result1 = await edit_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "board": board,
                "operation": "add_thought_item",
                "parent_name": "Work",
                "text": "new important task",
            },
        )

        assert result1.isError is None or result1.isError is False
        updated_board = result1.structuredContent["clusters"]

        # Verify new item was added
        work = next(c for c in updated_board if c["cluster_name"] == "Work")
        assert "new important task" in work["thought_items"]

        # Mock persistence and save
        mock_persist = AsyncMock(return_value=True)
        with patch("mcp_server.clarity.tools.save_board.persist_cluster", mock_persist):
            result2 = await save_handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "clusters": updated_board,
                    "thought_items": ["task1", "new important task", "chore"],
                },
            )

        assert result2.isError is None or result2.isError is False

        # Mock retrieval with updated board (simulating what was saved)
        with patch("mcp_server.clarity.tools.load_saved_board.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "cluster_id": "test-id",
                "cluster_data": {
                    "clusters": updated_board,
                    "sum_thought_items": 3,
                },
                "created_at": "2025-01-15T10:00:00Z",
            }
            result3 = await load_handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={},
            )

        assert result3.isError is None or result3.isError is False
        loaded_clusters = result3.structuredContent["clusters"]

        # Verify the new item is in the loaded board
        loaded_work = next(c for c in loaded_clusters if c["cluster_name"] == "Work")
        assert "new important task" in loaded_work["thought_items"]
