"""
Integration tests for thought item priority support.

Tests the full flow:
1. organize_thoughts → prioritize item → widget renders correctly
2. Priority on item bubbles up for cluster ordering
3. Clearing item priority restores default display (but keeps object format)
4. Mixed priorities (cluster P1, item P2) render and order correctly
5. Global uniqueness enforced across entity types
"""

from unittest.mock import AsyncMock, patch

import pytest
from mcp_server.clarity.tools.start_prioritization_flow import handle as prioritize_handle


# ============================================================================
# Test Fixtures
# ============================================================================


def make_cluster(name, items=None, subclusters=None):
    """Helper to create cluster dicts."""
    return {
        "cluster_name": name,
        "thought_items": items or [],
        "subclusters": subclusters or [],
        "tags": [],
    }


def make_subcluster(name, items=None):
    """Helper to create subcluster dicts."""
    return {
        "subcluster_name": name,
        "thought_items": items or [],
        "tags": [],
    }


# ============================================================================
# Integration Tests
# ============================================================================


class TestThoughtItemPriorityFlow:
    """Full flow integration tests for thought item priorities."""

    @pytest.mark.asyncio
    async def test_prioritize_item_produces_correct_output(self):
        """
        Full flow: create board → prioritize item → verify output structure.
        """
        # Create a board with thought items
        clusters = [
            make_cluster("Work", items=["Email boss", "Review code", "Team meeting"]),
            make_cluster("Personal", items=["Gym", "Call mom"]),
        ]

        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            mock_get.return_value = {"cluster_data": {"clusters": clusters}}

            # Prioritize a specific thought item
            result = await prioritize_handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "Email boss is P1",
                    "priorities": [
                        {"item_index": 0, "parent_name": "Work", "rank": "P1"}
                    ],
                },
            )

            assert result.isError is None or result.isError is False

            # Verify the item has priority
            output_clusters = result.structuredContent["clusters"]
            work_cluster = next(c for c in output_clusters if c["cluster_name"] == "Work")
            first_item = work_cluster["thought_items"][0]

            assert first_item["text"] == "Email boss"
            assert first_item["priority"]["rank"] == "P1"

            # Other items should not have priority (still strings since never prioritized)
            second_item = work_cluster["thought_items"][1]
            assert second_item == "Review code"

    @pytest.mark.asyncio
    async def test_mixed_cluster_and_item_priorities(self):
        """
        Mix of cluster P1 and item P2 works correctly.
        """
        clusters = [
            make_cluster("Work", items=["task"]),
            make_cluster("Personal", items=["gym", "reading"]),
        ]

        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            mock_get.return_value = {"cluster_data": {"clusters": clusters}}

            result = await prioritize_handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "Work P1, gym P2",
                    "priorities": [
                        {"name": "Work", "rank": "P1"},  # Cluster priority
                        {"item_index": 0, "parent_name": "Personal", "rank": "P2"},  # Item priority
                    ],
                },
            )

            assert result.isError is None or result.isError is False

            output = result.structuredContent["clusters"]

            # Work cluster has direct priority
            work = next(c for c in output if c["cluster_name"] == "Work")
            assert work["priority"]["rank"] == "P1"

            # Personal cluster has no direct priority
            personal = next(c for c in output if c["cluster_name"] == "Personal")
            assert personal["priority"] is None

            # But Personal's first item has P2
            gym_item = personal["thought_items"][0]
            assert gym_item["text"] == "gym"
            assert gym_item["priority"]["rank"] == "P2"

    @pytest.mark.asyncio
    async def test_global_uniqueness_across_entity_types(self):
        """
        Cannot have P1 on a cluster AND P1 on an item.
        """
        clusters = [
            make_cluster("Work", items=["task"]),
            make_cluster("Personal", items=["gym"]),
        ]

        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            mock_get.return_value = {"cluster_data": {"clusters": clusters}}

            result = await prioritize_handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "Work P1, gym P1",
                    "priorities": [
                        {"name": "Work", "rank": "P1"},  # Cluster P1
                        {"item_index": 0, "parent_name": "Personal", "rank": "P1"},  # Item P1 - duplicate!
                    ],
                },
            )

            assert result.isError is True
            # Should reject duplicate rank
            assert "P1" in result.content[0].text or "rank" in result.content[0].text.lower()

    @pytest.mark.asyncio
    async def test_subcluster_item_priority(self):
        """
        Priority can be assigned to items within subclusters.
        """
        clusters = [
            make_cluster("Work", subclusters=[
                make_subcluster("Urgent", items=["urgent task 1", "urgent task 2"]),
                make_subcluster("Later", items=["can wait"]),
            ])
        ]

        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            mock_get.return_value = {"cluster_data": {"clusters": clusters}}

            result = await prioritize_handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "urgent task 1 is P1",
                    "priorities": [
                        {"item_index": 0, "parent_name": "Urgent", "rank": "P1"}
                    ],
                },
            )

            assert result.isError is None or result.isError is False

            work = result.structuredContent["clusters"][0]
            urgent = next(s for s in work["subclusters"] if s["subcluster_name"] == "Urgent")

            first_item = urgent["thought_items"][0]
            assert first_item["text"] == "urgent task 1"
            assert first_item["priority"]["rank"] == "P1"

    @pytest.mark.asyncio
    async def test_three_priorities_across_all_types(self):
        """
        Can have P1 on cluster, P2 on subcluster, P3 on item.
        """
        clusters = [
            make_cluster("Work", items=["direct work item"]),
            make_cluster("Personal", subclusters=[
                make_subcluster("Health", items=["exercise"])
            ]),
            make_cluster("Admin", items=["paperwork"]),
        ]

        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            mock_get.return_value = {"cluster_data": {"clusters": clusters}}

            result = await prioritize_handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "Work P1, Health P2, paperwork P3",
                    "priorities": [
                        {"name": "Work", "rank": "P1"},  # Cluster
                        {"name": "Health", "rank": "P2"},  # Subcluster
                        {"item_index": 0, "parent_name": "Admin", "rank": "P3"},  # Item
                    ],
                },
            )

            assert result.isError is None or result.isError is False

            output = result.structuredContent["clusters"]

            # Work has P1
            work = next(c for c in output if c["cluster_name"] == "Work")
            assert work["priority"]["rank"] == "P1"

            # Health subcluster has P2
            personal = next(c for c in output if c["cluster_name"] == "Personal")
            health = next(s for s in personal["subclusters"] if s["subcluster_name"] == "Health")
            assert health["priority"]["rank"] == "P2"

            # Admin's item has P3
            admin = next(c for c in output if c["cluster_name"] == "Admin")
            assert admin["thought_items"][0]["priority"]["rank"] == "P3"
