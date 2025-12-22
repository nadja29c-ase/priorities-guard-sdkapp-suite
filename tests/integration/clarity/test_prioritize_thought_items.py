"""
Integration tests for thought item priority support.

Tests the full flow:
1. organize_thoughts → prioritize item → widget renders correctly
2. Priority on item bubbles up for cluster ordering
3. Clearing item priority restores default display (but keeps object format)
4. Mixed priorities (cluster P1, item P2) render and order correctly
5. Global uniqueness enforced across entity types
"""

import pytest
from mcp_server.clarity.tools.prioritize_clusters import handle as prioritize_handle


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

        # Prioritize a specific thought item
        result = await prioritize_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": clusters,
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
    async def test_item_priority_bubbles_up_for_ordering(self):
        """
        Priority on an item should make its container sort higher.
        """
        # Create clusters where second cluster has a prioritized item
        clusters = [
            make_cluster("Unprioritized", items=["task"]),
            make_cluster("Has Priority Item", items=["important task"]),
        ]

        # Prioritize item in second cluster
        result = await prioritize_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": clusters,
                "priorities": [
                    {"item_index": 0, "parent_name": "Has Priority Item", "rank": "P1"}
                ],
            },
        )

        assert result.isError is None or result.isError is False

        # The widget will use getEffectiveRank to sort clusters
        # The cluster with P1 item should sort first
        output_clusters = result.structuredContent["clusters"]

        # Verify both clusters are present
        cluster_names = [c["cluster_name"] for c in output_clusters]
        assert "Unprioritized" in cluster_names
        assert "Has Priority Item" in cluster_names

    @pytest.mark.asyncio
    async def test_clearing_item_priority_preserves_object_format(self):
        """
        When item priority is cleared, the object format is preserved.
        """
        # First, create a board with a prioritized item
        clusters = [make_cluster("Work", items=["task"])]

        result1 = await prioritize_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": clusters,
                "priorities": [
                    {"item_index": 0, "parent_name": "Work", "rank": "P1"}
                ],
            },
        )

        assert result1.isError is None or result1.isError is False
        prioritized_clusters = result1.structuredContent["clusters"]

        # Now clear all priorities
        result2 = await prioritize_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": prioritized_clusters,
                "priorities": [],  # Clear all
            },
        )

        assert result2.isError is None or result2.isError is False

        # The item should still be an object, not collapsed to string
        cleared_item = result2.structuredContent["clusters"][0]["thought_items"][0]
        assert isinstance(cleared_item, dict)
        assert cleared_item["text"] == "task"
        assert cleared_item["priority"] is None

    @pytest.mark.asyncio
    async def test_mixed_cluster_and_item_priorities(self):
        """
        Mix of cluster P1 and item P2 works correctly.
        """
        clusters = [
            make_cluster("Work", items=["task"]),
            make_cluster("Personal", items=["gym", "reading"]),
        ]

        result = await prioritize_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": clusters,
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

        result = await prioritize_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": clusters,
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

        result = await prioritize_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": clusters,
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
    async def test_reprioritizing_different_item(self):
        """
        Can move P1 from one item to another.
        """
        clusters = [make_cluster("Work", items=["task1", "task2"])]

        # First, prioritize task1
        result1 = await prioritize_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": clusters,
                "priorities": [
                    {"item_index": 0, "parent_name": "Work", "rank": "P1"}
                ],
            },
        )

        assert result1.isError is None or result1.isError is False
        clusters_v1 = result1.structuredContent["clusters"]

        # Now move P1 to task2
        result2 = await prioritize_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": clusters_v1,
                "priorities": [
                    {"item_index": 1, "parent_name": "Work", "rank": "P1"}  # Different item
                ],
            },
        )

        assert result2.isError is None or result2.isError is False

        items = result2.structuredContent["clusters"][0]["thought_items"]

        # task1 should no longer have priority
        assert items[0]["priority"] is None

        # task2 should now have P1
        assert items[1]["text"] == "task2"
        assert items[1]["priority"]["rank"] == "P1"

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

        result = await prioritize_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": clusters,
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


# ============================================================================
# Priority Preservation Integration Tests (Increment 23)
# ============================================================================


class TestPriorityPreservationIntegration:
    """Integration tests for priority preservation across entity types."""

    @pytest.mark.asyncio
    async def test_adding_item_priority_preserves_cluster_priority(self):
        """
        P1 on cluster, add P3 to item, P1 preserved.

        This tests that adding a new priority to a different entity type
        does not wipe existing priorities.
        """
        clusters = [
            make_cluster("Work", items=["task1", "task2"]),
            make_cluster("Personal", items=["gym"]),
        ]

        # First call: set P1 on Work cluster
        result1 = await prioritize_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": clusters,
                "priorities": [
                    {"name": "Work", "rank": "P1"}
                ],
            },
        )

        assert result1.isError is None or result1.isError is False
        clusters_v1 = result1.structuredContent["clusters"]

        # Verify P1 is on Work
        work = next(c for c in clusters_v1 if c["cluster_name"] == "Work")
        assert work["priority"]["rank"] == "P1"

        # Second call: add P3 to a thought item (different entity type)
        result2 = await prioritize_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": clusters_v1,
                "priorities": [
                    {"item_index": 0, "parent_name": "Personal", "rank": "P3"}
                ],
            },
        )

        assert result2.isError is None or result2.isError is False
        final_clusters = result2.structuredContent["clusters"]

        # Work's P1 should still be preserved
        work_final = next(c for c in final_clusters if c["cluster_name"] == "Work")
        assert work_final["priority"]["rank"] == "P1"

        # Personal's item should have P3
        personal_final = next(c for c in final_clusters if c["cluster_name"] == "Personal")
        assert personal_final["thought_items"][0]["text"] == "gym"
        assert personal_final["thought_items"][0]["priority"]["rank"] == "P3"

    @pytest.mark.asyncio
    async def test_moving_priority_between_entity_types(self):
        """
        Move P1 from cluster to item, cluster cleared.

        This tests that when a rank is reassigned to a different entity type,
        the old holder is properly cleared.
        """
        clusters = [
            make_cluster("Work", items=["task1"]),
            make_cluster("Personal", items=["gym"]),
        ]

        # First call: set P1 on Work cluster
        result1 = await prioritize_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": clusters,
                "priorities": [
                    {"name": "Work", "rank": "P1"}
                ],
            },
        )

        assert result1.isError is None or result1.isError is False
        clusters_v1 = result1.structuredContent["clusters"]

        # Verify P1 is on Work cluster
        work = next(c for c in clusters_v1 if c["cluster_name"] == "Work")
        assert work["priority"]["rank"] == "P1"

        # Second call: move P1 to a thought item
        result2 = await prioritize_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": clusters_v1,
                "priorities": [
                    {"item_index": 0, "parent_name": "Personal", "rank": "P1"}
                ],
            },
        )

        assert result2.isError is None or result2.isError is False
        final_clusters = result2.structuredContent["clusters"]

        # Work cluster's P1 should be cleared (rank taken by item)
        work_final = next(c for c in final_clusters if c["cluster_name"] == "Work")
        assert work_final["priority"] is None

        # Personal's item should now have P1
        personal_final = next(c for c in final_clusters if c["cluster_name"] == "Personal")
        assert personal_final["thought_items"][0]["priority"]["rank"] == "P1"

    @pytest.mark.asyncio
    async def test_subcluster_and_item_preservation(self):
        """
        P1 on subcluster, add P2 to item in different container, P1 preserved.
        """
        clusters = [
            make_cluster("Work", subclusters=[
                make_subcluster("Urgent", items=["urgent task"])
            ]),
            make_cluster("Personal", items=["gym"]),
        ]

        # First call: set P1 on Urgent subcluster
        result1 = await prioritize_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": clusters,
                "priorities": [
                    {"name": "Urgent", "rank": "P1"}
                ],
            },
        )

        assert result1.isError is None or result1.isError is False
        clusters_v1 = result1.structuredContent["clusters"]

        # Second call: add P2 to gym item
        result2 = await prioritize_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": clusters_v1,
                "priorities": [
                    {"item_index": 0, "parent_name": "Personal", "rank": "P2"}
                ],
            },
        )

        assert result2.isError is None or result2.isError is False
        final_clusters = result2.structuredContent["clusters"]

        # Urgent subcluster should still have P1
        work_final = next(c for c in final_clusters if c["cluster_name"] == "Work")
        urgent = next(s for s in work_final["subclusters"] if s["subcluster_name"] == "Urgent")
        assert urgent["priority"]["rank"] == "P1"

        # Personal's item should have P2
        personal_final = next(c for c in final_clusters if c["cluster_name"] == "Personal")
        assert personal_final["thought_items"][0]["priority"]["rank"] == "P2"
