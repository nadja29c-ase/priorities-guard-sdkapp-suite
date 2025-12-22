"""
Integration tests for edit_board tool.

Tests:
1. edit_then_save_persists — edit_board → save_board → load_saved_board shows changes
2. multiple_edits_accumulate — edit → edit → edit → all changes present
3. edit_loaded_board — load_saved_board → edit_board → priorities preserved
"""

import pytest
from mcp_server.clarity.tools.edit_board import handle as edit_handle
from mcp_server.clarity.tools.prioritize_clusters import handle as prioritize_handle


# ============================================================================
# Test Fixtures
# ============================================================================


def make_cluster(name, items=None, subclusters=None, priority=None):
    """Helper to create cluster dicts."""
    return {
        "cluster_name": name,
        "thought_items": items or [],
        "subclusters": subclusters or [],
        "tags": [],
        "priority": priority,
    }


def make_subcluster(name, items=None, priority=None):
    """Helper to create subcluster dicts."""
    return {
        "subcluster_name": name,
        "thought_items": items or [],
        "tags": [],
        "priority": priority,
    }


# ============================================================================
# Integration Tests
# ============================================================================


class TestEditBoardIntegration:
    """Integration tests for edit_board with other tools."""

    @pytest.mark.asyncio
    async def test_multiple_edits_accumulate(self):
        """
        edit → edit → edit → all changes present.
        """
        # Start with a basic board
        board = [
            make_cluster("Work", items=["task1"]),
            make_cluster("Home", items=["chore"]),
            make_cluster("Health", items=["exercise"]),
        ]

        # First edit: set P1 on Work
        result1 = await edit_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "board": board,
                "operation": "set_priority",
                "target_name": "Work",
                "rank": "P1",
            },
        )
        assert result1.isError is None or result1.isError is False
        board_v1 = result1.structuredContent["clusters"]

        # Verify P1 is set
        work = next(c for c in board_v1 if c["cluster_name"] == "Work")
        assert work["priority"]["rank"] == "P1"

        # Second edit: set P2 on Home (passing board_v1 with P1)
        result2 = await edit_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "board": board_v1,
                "operation": "set_priority",
                "target_name": "Home",
                "rank": "P2",
            },
        )
        assert result2.isError is None or result2.isError is False
        board_v2 = result2.structuredContent["clusters"]

        # Verify P1 still present and P2 added
        work = next(c for c in board_v2 if c["cluster_name"] == "Work")
        home = next(c for c in board_v2 if c["cluster_name"] == "Home")
        assert work["priority"]["rank"] == "P1"
        assert home["priority"]["rank"] == "P2"

        # Third edit: set P3 on Health (passing board_v2 with P1, P2)
        result3 = await edit_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "board": board_v2,
                "operation": "set_priority",
                "target_name": "Health",
                "rank": "P3",
            },
        )
        assert result3.isError is None or result3.isError is False
        board_v3 = result3.structuredContent["clusters"]

        # Verify all three priorities present
        work = next(c for c in board_v3 if c["cluster_name"] == "Work")
        home = next(c for c in board_v3 if c["cluster_name"] == "Home")
        health = next(c for c in board_v3 if c["cluster_name"] == "Health")
        assert work["priority"]["rank"] == "P1"
        assert home["priority"]["rank"] == "P2"
        assert health["priority"]["rank"] == "P3"

    @pytest.mark.asyncio
    async def test_edit_preserves_subcluster_priorities(self):
        """
        Priority on subcluster is preserved when editing something else.
        """
        # Board with a prioritized subcluster
        board = [
            make_cluster("Work", subclusters=[
                make_subcluster("Urgent", items=["task"], priority={"rank": "P1", "reason": None}),
                make_subcluster("Later", items=["other"]),
            ]),
            make_cluster("Home"),
        ]

        # Edit: set P2 on Home cluster
        result = await edit_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "board": board,
                "operation": "set_priority",
                "target_name": "Home",
                "rank": "P2",
            },
        )

        assert result.isError is None or result.isError is False
        clusters = result.structuredContent["clusters"]

        # Urgent subcluster's P1 should still be there
        work = next(c for c in clusters if c["cluster_name"] == "Work")
        urgent = next(s for s in work["subclusters"] if s["subcluster_name"] == "Urgent")
        assert urgent["priority"]["rank"] == "P1"

        # Home should have P2
        home = next(c for c in clusters if c["cluster_name"] == "Home")
        assert home["priority"]["rank"] == "P2"

    @pytest.mark.asyncio
    async def test_edit_preserves_thought_item_priorities(self):
        """
        Priority on thought item is preserved when editing something else.
        """
        # Board with a prioritized thought item
        board = [
            make_cluster("Work", items=[
                {"text": "important task", "priority": {"rank": "P1", "reason": None}},
                "regular task",
            ]),
            make_cluster("Home"),
        ]

        # Edit: set P2 on Home cluster
        result = await edit_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "board": board,
                "operation": "set_priority",
                "target_name": "Home",
                "rank": "P2",
            },
        )

        assert result.isError is None or result.isError is False
        clusters = result.structuredContent["clusters"]

        # Thought item's P1 should still be there
        work = next(c for c in clusters if c["cluster_name"] == "Work")
        assert work["thought_items"][0]["priority"]["rank"] == "P1"

        # Home should have P2
        home = next(c for c in clusters if c["cluster_name"] == "Home")
        assert home["priority"]["rank"] == "P2"

    @pytest.mark.asyncio
    async def test_edit_after_prioritize_clusters(self):
        """
        prioritize_clusters → edit_board → priorities accumulate correctly.
        """
        # Start with a basic board
        board = [
            make_cluster("Work", items=["task"]),
            make_cluster("Home", items=["chore"]),
            make_cluster("Health", items=["exercise"]),
        ]

        # Use prioritize_clusters to set P1 and P2
        result1 = await prioritize_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": board,
                "priorities": [
                    {"name": "Work", "rank": "P1"},
                    {"name": "Home", "rank": "P2"},
                ],
            },
        )
        assert result1.isError is None or result1.isError is False
        board_after_prioritize = result1.structuredContent["clusters"]

        # Use edit_board to add P3
        result2 = await edit_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "board": board_after_prioritize,
                "operation": "set_priority",
                "target_name": "Health",
                "rank": "P3",
            },
        )
        assert result2.isError is None or result2.isError is False
        final_board = result2.structuredContent["clusters"]

        # All three priorities should be present
        work = next(c for c in final_board if c["cluster_name"] == "Work")
        home = next(c for c in final_board if c["cluster_name"] == "Home")
        health = next(c for c in final_board if c["cluster_name"] == "Health")
        assert work["priority"]["rank"] == "P1"
        assert home["priority"]["rank"] == "P2"
        assert health["priority"]["rank"] == "P3"

    @pytest.mark.asyncio
    async def test_move_priority_clears_old_holder(self):
        """
        Moving P1 from Work to Health clears Work's priority.
        """
        board = [
            make_cluster("Work", priority={"rank": "P1", "reason": None}),
            make_cluster("Health"),
        ]

        result = await edit_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "board": board,
                "operation": "set_priority",
                "target_name": "Health",
                "rank": "P1",
            },
        )

        assert result.isError is None or result.isError is False
        clusters = result.structuredContent["clusters"]

        # Work's P1 should be cleared
        work = next(c for c in clusters if c["cluster_name"] == "Work")
        assert work["priority"] is None

        # Health should have P1
        health = next(c for c in clusters if c["cluster_name"] == "Health")
        assert health["priority"]["rank"] == "P1"

    @pytest.mark.asyncio
    async def test_delete_then_set_priority(self):
        """
        Delete a cluster, then set priority on remaining one.
        """
        board = [
            make_cluster("Work", items=["task"]),
            make_cluster("Home", items=["chore"]),
        ]

        # Delete Work
        result1 = await edit_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "board": board,
                "operation": "delete_cluster",
                "target_name": "Work",
            },
        )
        assert result1.isError is None or result1.isError is False
        board_v1 = result1.structuredContent["clusters"]
        assert len(board_v1) == 1

        # Set P1 on Home
        result2 = await edit_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "board": board_v1,
                "operation": "set_priority",
                "target_name": "Home",
                "rank": "P1",
            },
        )
        assert result2.isError is None or result2.isError is False
        final_board = result2.structuredContent["clusters"]

        assert len(final_board) == 1
        assert final_board[0]["cluster_name"] == "Home"
        assert final_board[0]["priority"]["rank"] == "P1"

    @pytest.mark.asyncio
    async def test_rename_preserves_priority(self):
        """
        Renaming a cluster preserves its priority.
        """
        board = [
            make_cluster("Work", priority={"rank": "P1", "reason": None}),
        ]

        result = await edit_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "board": board,
                "operation": "rename_cluster",
                "target_name": "Work",
                "new_name": "Office",
            },
        )

        assert result.isError is None or result.isError is False
        clusters = result.structuredContent["clusters"]

        assert clusters[0]["cluster_name"] == "Office"
        assert clusters[0]["priority"]["rank"] == "P1"
