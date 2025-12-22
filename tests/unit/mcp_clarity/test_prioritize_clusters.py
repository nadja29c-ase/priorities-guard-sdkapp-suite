"""
Unit tests for prioritize_clusters tool.

Focus areas:
1. Validation rules (max 3, unique ranks, valid names, parent+child conflict)
2. Priority embedding in cluster/subcluster objects
3. Empty priorities (clearing)
4. Reason field handling
5. Error messages
"""

import pytest
from mcp_server.clarity.tools.prioritize_clusters import (
    handle,
    _find_all_names,
    _validate_priorities,
    _apply_priorities,
    _normalize_thought_item,
    _clear_all_thought_item_priorities,
    PriorityInput,
    MAX_PRIORITIES,
    ERROR_TOO_MANY_PRIORITIES,
    ERROR_DUPLICATE_RANK,
    ERROR_INVALID_CLUSTER,
    ERROR_NO_BOARD,
    ERROR_PARENT_AND_CHILD,
    ERROR_AMBIGUOUS_NAME,
    ERROR_INVALID_PARENT,
    ERROR_ITEM_INDEX_OUT_OF_BOUNDS,
)


# ============================================================================
# Test Fixtures
# ============================================================================


def make_cluster(name, items=None, subclusters=None, tags=None):
    """Helper to create cluster dicts."""
    return {
        "cluster_name": name,
        "thought_items": items or [],
        "subclusters": subclusters or [],
        "tags": tags or [],
    }


def make_subcluster(name, items=None, tags=None):
    """Helper to create subcluster dicts."""
    return {
        "subcluster_name": name,
        "thought_items": items or [],
        "tags": tags or [],
    }


def make_priority(name=None, rank="P1", reason=None, item_index=None, parent_name=None):
    """Helper to create PriorityInput objects."""
    return PriorityInput(
        name=name,
        rank=rank,
        reason=reason,
        item_index=item_index,
        parent_name=parent_name
    )


def make_item_priority(parent_name, item_index, rank, reason=None):
    """Helper to create PriorityInput for thought items."""
    return PriorityInput(
        item_index=item_index,
        parent_name=parent_name,
        rank=rank,
        reason=reason
    )


# ============================================================================
# Helper Function Tests
# ============================================================================


class TestFindAllNames:
    """Tests for _find_all_names helper."""

    def test_extracts_cluster_names(self):
        """Extracts cluster_name from all clusters."""
        clusters = [
            make_cluster("Work", items=["task1"]),
            make_cluster("Home", items=["chore"]),
        ]
        cluster_names, subcluster_names, _ = _find_all_names(clusters)
        assert cluster_names == {"Work", "Home"}
        assert subcluster_names == set()

    def test_extracts_subcluster_names(self):
        """Extracts subcluster_name from all subclusters."""
        clusters = [
            make_cluster("Work", subclusters=[
                make_subcluster("Urgent"),
                make_subcluster("Later"),
            ]),
        ]
        cluster_names, subcluster_names, _ = _find_all_names(clusters)
        assert cluster_names == {"Work"}
        assert subcluster_names == {"Urgent", "Later"}

    def test_builds_subcluster_to_parent_map(self):
        """Maps subcluster names to their parent cluster names."""
        clusters = [
            make_cluster("Work", subclusters=[
                make_subcluster("Urgent"),
            ]),
            make_cluster("Home", subclusters=[
                make_subcluster("Chores"),
            ]),
        ]
        _, _, subcluster_to_parent = _find_all_names(clusters)
        assert subcluster_to_parent == {"Urgent": "Work", "Chores": "Home"}

    def test_handles_empty_clusters(self):
        """Handles empty clusters list."""
        cluster_names, subcluster_names, subcluster_to_parent = _find_all_names([])
        assert cluster_names == set()
        assert subcluster_names == set()
        assert subcluster_to_parent == {}


class TestValidatePriorities:
    """Tests for _validate_priorities helper."""

    def test_valid_single_priority(self):
        """Single valid priority passes validation."""
        clusters = [make_cluster("Work"), make_cluster("Home")]
        priorities = [make_priority(name="Work", rank="P1")]
        cluster_names = {"Work", "Home"}
        subcluster_names = set()
        subcluster_to_parent = {}

        error = _validate_priorities(
            priorities, clusters, cluster_names, subcluster_names, subcluster_to_parent
        )
        assert error is None

    def test_valid_three_priorities(self):
        """Three valid priorities passes validation."""
        clusters = [make_cluster("Work"), make_cluster("Home"), make_cluster("Health")]
        priorities = [
            make_priority(name="Work", rank="P1"),
            make_priority(name="Home", rank="P2"),
            make_priority(name="Health", rank="P3"),
        ]
        cluster_names = {"Work", "Home", "Health"}
        subcluster_names = set()
        subcluster_to_parent = {}

        error = _validate_priorities(
            priorities, clusters, cluster_names, subcluster_names, subcluster_to_parent
        )
        assert error is None

    def test_rejects_too_many_priorities(self):
        """More than 3 priorities is rejected."""
        clusters = [make_cluster("A"), make_cluster("B"), make_cluster("C"), make_cluster("D")]
        priorities = [
            make_priority(name="A", rank="P1"),
            make_priority(name="B", rank="P2"),
            make_priority(name="C", rank="P3"),
            make_priority(name="D", rank="P1"),  # 4th
        ]
        cluster_names = {"A", "B", "C", "D"}

        error = _validate_priorities(priorities, clusters, cluster_names, set(), {})
        assert error == ERROR_TOO_MANY_PRIORITIES

    def test_rejects_duplicate_ranks(self):
        """Duplicate ranks (two P1s) are rejected."""
        clusters = [make_cluster("Work"), make_cluster("Home")]
        priorities = [
            make_priority(name="Work", rank="P1"),
            make_priority(name="Home", rank="P1"),  # Duplicate P1
        ]
        cluster_names = {"Work", "Home"}

        error = _validate_priorities(priorities, clusters, cluster_names, set(), {})
        assert error == ERROR_DUPLICATE_RANK

    def test_rejects_invalid_cluster_name(self):
        """Invalid cluster name is rejected."""
        clusters = [make_cluster("Work"), make_cluster("Home")]
        priorities = [make_priority(name="NonExistent", rank="P1")]
        cluster_names = {"Work", "Home"}

        error = _validate_priorities(priorities, clusters, cluster_names, set(), {})
        assert error == ERROR_INVALID_CLUSTER

    def test_accepts_subcluster_name(self):
        """Valid subcluster name is accepted."""
        clusters = [make_cluster("Work", subclusters=[make_subcluster("Urgent")])]
        priorities = [make_priority(name="Urgent", rank="P1")]
        cluster_names = {"Work"}
        subcluster_names = {"Urgent"}
        subcluster_to_parent = {"Urgent": "Work"}

        error = _validate_priorities(
            priorities, clusters, cluster_names, subcluster_names, subcluster_to_parent
        )
        assert error is None

    def test_rejects_parent_and_child_conflict(self):
        """Cannot prioritize both cluster and its subcluster."""
        clusters = [make_cluster("Work", subclusters=[make_subcluster("Urgent")])]
        priorities = [
            make_priority(name="Work", rank="P1"),
            make_priority(name="Urgent", rank="P2"),  # Urgent is a subcluster of Work
        ]
        cluster_names = {"Work"}
        subcluster_names = {"Urgent"}
        subcluster_to_parent = {"Urgent": "Work"}

        error = _validate_priorities(
            priorities, clusters, cluster_names, subcluster_names, subcluster_to_parent
        )
        assert error == ERROR_PARENT_AND_CHILD

    def test_accepts_empty_priorities(self):
        """Empty priorities array is valid (clears priorities)."""
        clusters = [make_cluster("Work")]
        error = _validate_priorities([], clusters, {"Work"}, set(), {})
        assert error is None


class TestApplyPriorities:
    """Tests for _apply_priorities helper."""

    def test_applies_cluster_priority(self):
        """Priority is applied to cluster."""
        clusters = [make_cluster("Work", items=["task"])]
        priorities = [make_priority(name="Work", rank="P1", reason="blocker")]

        result = _apply_priorities(clusters, priorities)

        assert result[0]["priority"] == {"rank": "P1", "reason": "blocker"}

    def test_applies_subcluster_priority(self):
        """Priority is applied to subcluster."""
        clusters = [
            make_cluster("Work", subclusters=[
                make_subcluster("Urgent", items=["task"]),
            ])
        ]
        priorities = [make_priority(name="Urgent", rank="P2", reason="goal-aligned")]

        result = _apply_priorities(clusters, priorities)

        # Cluster has no priority
        assert result[0]["priority"] is None
        # Subcluster has priority
        assert result[0]["subclusters"][0]["priority"] == {"rank": "P2", "reason": "goal-aligned"}

    def test_clears_priorities_with_empty_array(self):
        """Empty priorities array clears all priorities."""
        clusters = [
            make_cluster("Work", items=["task"]),
            make_cluster("Home", items=["chore"]),
        ]
        priorities = []

        result = _apply_priorities(clusters, priorities)

        assert result[0]["priority"] is None
        assert result[1]["priority"] is None

    def test_does_not_mutate_original(self):
        """Original clusters list is not mutated."""
        clusters = [make_cluster("Work", items=["task"])]
        original_cluster = clusters[0]
        priorities = [make_priority(name="Work", rank="P1")]

        result = _apply_priorities(clusters, priorities)

        # Original unchanged
        assert "priority" not in original_cluster
        # Result has priority
        assert result[0]["priority"]["rank"] == "P1"

    def test_reason_none_when_not_provided(self):
        """Reason is None when not provided."""
        clusters = [make_cluster("Work", items=["task"])]
        priorities = [make_priority(name="Work", rank="P1")]

        result = _apply_priorities(clusters, priorities)

        assert result[0]["priority"]["reason"] is None


# ============================================================================
# Handler Tests
# ============================================================================


class TestHandlerValidation:
    """Tests for handle() validation."""

    @pytest.mark.asyncio
    async def test_rejects_empty_clusters(self):
        """Empty clusters returns error."""
        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": [],
                "priorities": [],
            },
        )
        assert result.isError is True
        assert ERROR_NO_BOARD in result.content[0].text

    @pytest.mark.asyncio
    async def test_rejects_too_many_priorities(self):
        """More than 3 priorities returns error."""
        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": [
                    {"cluster_name": "A", "thought_items": ["x"]},
                    {"cluster_name": "B", "thought_items": ["x"]},
                    {"cluster_name": "C", "thought_items": ["x"]},
                    {"cluster_name": "D", "thought_items": ["x"]},
                ],
                "priorities": [
                    {"name": "A", "rank": "P1"},
                    {"name": "B", "rank": "P2"},
                    {"name": "C", "rank": "P3"},
                    {"name": "D", "rank": "P1"},  # 4th priority
                ],
            },
        )
        assert result.isError is True
        assert ERROR_TOO_MANY_PRIORITIES in result.content[0].text

    @pytest.mark.asyncio
    async def test_rejects_duplicate_ranks(self):
        """Duplicate ranks returns error."""
        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": [
                    {"cluster_name": "Work", "thought_items": ["x"]},
                    {"cluster_name": "Home", "thought_items": ["x"]},
                ],
                "priorities": [
                    {"name": "Work", "rank": "P1"},
                    {"name": "Home", "rank": "P1"},  # Duplicate
                ],
            },
        )
        assert result.isError is True
        assert ERROR_DUPLICATE_RANK in result.content[0].text

    @pytest.mark.asyncio
    async def test_rejects_invalid_name(self):
        """Invalid cluster/subcluster name returns error."""
        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": [{"cluster_name": "Work", "thought_items": ["x"]}],
                "priorities": [{"name": "NonExistent", "rank": "P1"}],
            },
        )
        assert result.isError is True
        assert ERROR_INVALID_CLUSTER in result.content[0].text

    @pytest.mark.asyncio
    async def test_rejects_parent_child_conflict(self):
        """Prioritizing parent and child returns error."""
        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": [
                    {
                        "cluster_name": "Work",
                        "thought_items": [],
                        "subclusters": [
                            {"subcluster_name": "Urgent", "thought_items": ["task"]}
                        ],
                    }
                ],
                "priorities": [
                    {"name": "Work", "rank": "P1"},
                    {"name": "Urgent", "rank": "P2"},
                ],
            },
        )
        assert result.isError is True
        assert ERROR_PARENT_AND_CHILD in result.content[0].text

    @pytest.mark.asyncio
    async def test_rejects_invalid_rank(self):
        """Invalid rank value returns error."""
        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": [{"cluster_name": "Work", "thought_items": ["x"]}],
                "priorities": [{"name": "Work", "rank": "P4"}],  # Invalid
            },
        )
        assert result.isError is True


class TestHandlerSuccess:
    """Tests for successful prioritization."""

    @pytest.mark.asyncio
    async def test_single_priority_success(self):
        """Single priority is applied successfully."""
        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": [{"cluster_name": "Work", "thought_items": ["task"]}],
                "priorities": [{"name": "Work", "rank": "P1"}],
            },
        )

        assert result.isError is None or result.isError is False
        clusters = result.structuredContent["clusters"]
        assert clusters[0]["priority"]["rank"] == "P1"

    @pytest.mark.asyncio
    async def test_three_priorities_success(self):
        """Three priorities are applied successfully."""
        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": [
                    {"cluster_name": "Work", "thought_items": ["x"]},
                    {"cluster_name": "Home", "thought_items": ["x"]},
                    {"cluster_name": "Health", "thought_items": ["x"]},
                ],
                "priorities": [
                    {"name": "Work", "rank": "P1"},
                    {"name": "Home", "rank": "P2"},
                    {"name": "Health", "rank": "P3"},
                ],
            },
        )

        assert result.isError is None or result.isError is False
        clusters = result.structuredContent["clusters"]
        assert clusters[0]["priority"]["rank"] == "P1"
        assert clusters[1]["priority"]["rank"] == "P2"
        assert clusters[2]["priority"]["rank"] == "P3"

    @pytest.mark.asyncio
    async def test_empty_priorities_clears(self):
        """Empty priorities array clears all priorities."""
        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": [
                    {"cluster_name": "Work", "thought_items": ["task"]},
                ],
                "priorities": [],
            },
        )

        assert result.isError is None or result.isError is False
        clusters = result.structuredContent["clusters"]
        assert clusters[0]["priority"] is None
        assert "cleared" in result.content[0].text.lower()

    @pytest.mark.asyncio
    async def test_subcluster_priority_success(self):
        """Priority on subcluster is applied correctly."""
        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": [
                    {
                        "cluster_name": "Work",
                        "thought_items": [],
                        "subclusters": [
                            {"subcluster_name": "Urgent", "thought_items": ["task"]}
                        ],
                    }
                ],
                "priorities": [{"name": "Urgent", "rank": "P1"}],
            },
        )

        assert result.isError is None or result.isError is False
        clusters = result.structuredContent["clusters"]
        # Cluster has no direct priority
        assert clusters[0]["priority"] is None
        # Subcluster has priority
        assert clusters[0]["subclusters"][0]["priority"]["rank"] == "P1"

    @pytest.mark.asyncio
    async def test_reason_stored_when_provided(self):
        """Reason is stored in priority object."""
        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": [{"cluster_name": "Work", "thought_items": ["task"]}],
                "priorities": [{"name": "Work", "rank": "P1", "reason": "blocker"}],
            },
        )

        assert result.isError is None or result.isError is False
        clusters = result.structuredContent["clusters"]
        assert clusters[0]["priority"]["reason"] == "blocker"

    @pytest.mark.asyncio
    async def test_reason_null_when_absent(self):
        """Reason is null when not provided."""
        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": [{"cluster_name": "Work", "thought_items": ["task"]}],
                "priorities": [{"name": "Work", "rank": "P1"}],
            },
        )

        assert result.isError is None or result.isError is False
        clusters = result.structuredContent["clusters"]
        assert clusters[0]["priority"]["reason"] is None


class TestDataOrderPreservation:
    """Tests that data order is preserved (widget handles display order)."""

    @pytest.mark.asyncio
    async def test_cluster_order_unchanged(self):
        """Cluster order in output matches input (no reordering in tool)."""
        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": [
                    {"cluster_name": "Third", "thought_items": ["x"]},
                    {"cluster_name": "First", "thought_items": ["x"]},
                    {"cluster_name": "Second", "thought_items": ["x"]},
                ],
                "priorities": [
                    {"name": "First", "rank": "P1"},
                    {"name": "Second", "rank": "P2"},
                ],
            },
        )

        assert result.isError is None or result.isError is False
        clusters = result.structuredContent["clusters"]

        # Order unchanged from input
        assert clusters[0]["cluster_name"] == "Third"
        assert clusters[1]["cluster_name"] == "First"
        assert clusters[2]["cluster_name"] == "Second"

    @pytest.mark.asyncio
    async def test_subcluster_order_unchanged(self):
        """Subcluster order preserved (widget handles display order)."""
        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": [
                    {
                        "cluster_name": "Work",
                        "thought_items": [],
                        "subclusters": [
                            {"subcluster_name": "Third", "thought_items": ["x"]},
                            {"subcluster_name": "First", "thought_items": ["x"]},
                            {"subcluster_name": "Second", "thought_items": ["x"]},
                        ],
                    }
                ],
                "priorities": [{"name": "First", "rank": "P1"}],
            },
        )

        assert result.isError is None or result.isError is False
        subclusters = result.structuredContent["clusters"][0]["subclusters"]

        # Order unchanged
        assert subclusters[0]["subcluster_name"] == "Third"
        assert subclusters[1]["subcluster_name"] == "First"
        assert subclusters[2]["subcluster_name"] == "Second"


class TestResponseStructure:
    """Tests for response structure."""

    @pytest.mark.asyncio
    async def test_includes_widget_meta(self):
        """Response includes widget metadata."""
        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": [{"cluster_name": "Work", "thought_items": ["task"]}],
                "priorities": [{"name": "Work", "rank": "P1"}],
            },
        )

        assert result.isError is None or result.isError is False
        # Widget meta is set
        assert result.meta is not None
        assert "openai/outputTemplate" in result.meta

    @pytest.mark.asyncio
    async def test_enriches_clusters(self):
        """Response clusters have sum_thought_items enrichment."""
        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": [
                    {
                        "cluster_name": "Work",
                        "thought_items": ["task1", "task2"],
                        "subclusters": [
                            {"subcluster_name": "Urgent", "thought_items": ["sub1", "sub2", "sub3"]}
                        ],
                    }
                ],
                "priorities": [{"name": "Work", "rank": "P1"}],
            },
        )

        assert result.isError is None or result.isError is False
        cluster = result.structuredContent["clusters"][0]
        # Should have sum_thought_items enrichment (2 direct + 3 subcluster = 5)
        assert cluster.get("sum_thought_items") == 5

    @pytest.mark.asyncio
    async def test_success_message_format(self):
        """Success message includes priority count and ranks."""
        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": [
                    {"cluster_name": "Work", "thought_items": ["x"]},
                    {"cluster_name": "Home", "thought_items": ["x"]},
                ],
                "priorities": [
                    {"name": "Work", "rank": "P2"},
                    {"name": "Home", "rank": "P1"},
                ],
            },
        )

        assert result.isError is None or result.isError is False
        text = result.content[0].text
        assert "2" in text  # Count
        assert "P1" in text
        assert "P2" in text


class TestMaxPrioritiesConstant:
    """Verify MAX_PRIORITIES constant."""

    def test_max_priorities_is_3(self):
        """MAX_PRIORITIES must be 3 per spec."""
        assert MAX_PRIORITIES == 3


# ============================================================================
# Integration Tests
# ============================================================================


class TestPriorityPersistenceRoundTrip:
    """Integration tests for priority persistence through save/load cycle."""

    @pytest.mark.asyncio
    async def test_priorities_persist_through_save_load_cycle(self):
        """
        prioritize_clusters → save_board → load_saved_board preserves priorities.

        This is the critical round-trip test from increment 13 spec.
        """
        from unittest.mock import AsyncMock, patch
        from mcp_server.clarity.tools.save_board import handle as save_handle
        from mcp_server.clarity.tools.load_saved_board import handle as load_handle

        # Step 1: Create board with priorities using prioritize_clusters
        # Note: Prioritize Work (cluster) and Home (different cluster), NOT parent+child
        prioritize_result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": [
                    {
                        "cluster_name": "Work",
                        "thought_items": ["task1", "task2"],
                        "subclusters": [
                            {"subcluster_name": "Urgent", "thought_items": ["urgent1"]}
                        ],
                    },
                    {
                        "cluster_name": "Home",
                        "thought_items": ["chore1"],
                        "subclusters": [],
                    },
                    {
                        "cluster_name": "Health",
                        "thought_items": ["exercise"],
                        "subclusters": [],
                    },
                ],
                "priorities": [
                    {"name": "Work", "rank": "P1", "reason": "blocker"},
                    {"name": "Home", "rank": "P2", "reason": "goal-aligned"},
                ],
            },
        )

        assert prioritize_result.isError is None or prioritize_result.isError is False
        prioritized_clusters = prioritize_result.structuredContent["clusters"]

        # Verify priorities are in the output
        work = next(c for c in prioritized_clusters if c["cluster_name"] == "Work")
        home = next(c for c in prioritized_clusters if c["cluster_name"] == "Home")
        assert work["priority"]["rank"] == "P1"
        assert home["priority"]["rank"] == "P2"

        # Step 2: Save the prioritized board (mock persistence)
        saved_data = None

        async def mock_persist(user_id, cluster_data, **kwargs):
            nonlocal saved_data
            saved_data = cluster_data

        with patch("mcp_server.clarity.tools.save_board.persist_cluster", mock_persist):
            save_result = await save_handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "clusters": prioritized_clusters,
                },
            )

        assert save_result.isError is None or save_result.isError is False
        assert saved_data is not None

        # Step 3: Load the saved board (mock get_cluster returns saved data)
        with patch("mcp_server.clarity.tools.load_saved_board.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "cluster_id": "test-id",
                "cluster_data": saved_data,
                "created_at": "2025-01-15T10:00:00Z",
            }

            load_result = await load_handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={},
            )

        assert load_result.isError is None or load_result.isError is False
        loaded_clusters = load_result.structuredContent["clusters"]

        # Step 4: Verify priorities survived the round-trip
        work_cluster = next(c for c in loaded_clusters if c["cluster_name"] == "Work")
        home_cluster = next(c for c in loaded_clusters if c["cluster_name"] == "Home")
        health_cluster = next(c for c in loaded_clusters if c["cluster_name"] == "Health")

        # Work cluster should have P1 priority
        assert work_cluster["priority"] is not None
        assert work_cluster["priority"]["rank"] == "P1"
        assert work_cluster["priority"]["reason"] == "blocker"

        # Home cluster should have P2 priority
        assert home_cluster["priority"] is not None
        assert home_cluster["priority"]["rank"] == "P2"
        assert home_cluster["priority"]["reason"] == "goal-aligned"

        # Health cluster should have no priority
        assert health_cluster["priority"] is None

    @pytest.mark.asyncio
    async def test_cleared_priorities_persist(self):
        """Empty priorities array clears priorities and persists correctly."""
        from unittest.mock import AsyncMock, patch
        from mcp_server.clarity.tools.save_board import handle as save_handle
        from mcp_server.clarity.tools.load_saved_board import handle as load_handle

        # Step 1: Clear priorities
        prioritize_result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": [
                    {"cluster_name": "Work", "thought_items": ["task"]},
                ],
                "priorities": [],  # Clear all priorities
            },
        )

        assert prioritize_result.isError is None or prioritize_result.isError is False
        cleared_clusters = prioritize_result.structuredContent["clusters"]
        assert cleared_clusters[0]["priority"] is None

        # Step 2: Save
        saved_data = None

        async def mock_persist(user_id, cluster_data, **kwargs):
            nonlocal saved_data
            saved_data = cluster_data

        with patch("mcp_server.clarity.tools.save_board.persist_cluster", mock_persist):
            await save_handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={"clusters": cleared_clusters},
            )

        # Step 3: Load and verify priorities are still cleared
        with patch("mcp_server.clarity.tools.load_saved_board.get_cluster", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "cluster_id": "test-id",
                "cluster_data": saved_data,
                "created_at": "2025-01-15T10:00:00Z",
            }

            load_result = await load_handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={},
            )

        loaded_clusters = load_result.structuredContent["clusters"]
        assert loaded_clusters[0]["priority"] is None


# ============================================================================
# Thought Item Priority Tests
# ============================================================================


class TestNormalizeThoughtItem:
    """Tests for _normalize_thought_item helper."""

    def test_converts_string_to_object(self):
        """String items become {text: ...} objects."""
        result = _normalize_thought_item("Test item")
        assert result == {"text": "Test item"}

    def test_preserves_object_format(self):
        """Object items are returned as-is."""
        item = {"text": "Already object", "priority": {"rank": "P1"}}
        result = _normalize_thought_item(item)
        assert result == item


class TestClearAllThoughtItemPriorities:
    """Tests for _clear_all_thought_item_priorities helper."""

    def test_clears_priority_from_objects(self):
        """Objects have priority set to None."""
        items = [
            {"text": "item1", "priority": {"rank": "P1"}},
            {"text": "item2", "priority": {"rank": "P2"}},
        ]
        result = _clear_all_thought_item_priorities(items)
        assert result[0]["priority"] is None
        assert result[1]["priority"] is None

    def test_preserves_strings(self):
        """String items are kept as strings."""
        items = ["string item", {"text": "object item", "priority": {"rank": "P1"}}]
        result = _clear_all_thought_item_priorities(items)
        assert result[0] == "string item"
        assert result[1]["text"] == "object item"
        assert result[1]["priority"] is None


class TestValidatePrioritiesWithThoughtItems:
    """Tests for _validate_priorities with thought item targeting."""

    def test_valid_item_priority(self):
        """Valid thought item priority passes validation."""
        clusters = [make_cluster("Work", items=["task1", "task2"])]
        cluster_names, subcluster_names, subcluster_to_parent = _find_all_names(clusters)
        priorities = [make_item_priority("Work", 0, "P1")]

        error = _validate_priorities(
            priorities, clusters, cluster_names, subcluster_names, subcluster_to_parent
        )
        assert error is None

    def test_rejects_invalid_parent_name(self):
        """Invalid parent_name is rejected."""
        clusters = [make_cluster("Work", items=["task"])]
        cluster_names, subcluster_names, subcluster_to_parent = _find_all_names(clusters)
        priorities = [make_item_priority("NonExistent", 0, "P1")]

        error = _validate_priorities(
            priorities, clusters, cluster_names, subcluster_names, subcluster_to_parent
        )
        assert "NonExistent" in error

    def test_rejects_item_index_out_of_bounds(self):
        """Out of bounds item_index is rejected."""
        clusters = [make_cluster("Work", items=["task"])]  # Only 1 item
        cluster_names, subcluster_names, subcluster_to_parent = _find_all_names(clusters)
        priorities = [make_item_priority("Work", 5, "P1")]  # Index 5 doesn't exist

        error = _validate_priorities(
            priorities, clusters, cluster_names, subcluster_names, subcluster_to_parent
        )
        assert "out of bounds" in error

    def test_rejects_negative_item_index(self):
        """Negative item_index is rejected."""
        clusters = [make_cluster("Work", items=["task"])]
        cluster_names, subcluster_names, subcluster_to_parent = _find_all_names(clusters)
        priorities = [make_item_priority("Work", -1, "P1")]

        error = _validate_priorities(
            priorities, clusters, cluster_names, subcluster_names, subcluster_to_parent
        )
        assert "out of bounds" in error

    def test_rejects_ambiguous_name(self):
        """Ambiguous name (both cluster and subcluster) is rejected."""
        clusters = [
            make_cluster("Shared", items=["task"], subclusters=[
                make_subcluster("Shared", items=["sub task"])  # Same name as parent
            ])
        ]
        cluster_names, subcluster_names, subcluster_to_parent = _find_all_names(clusters)
        priorities = [make_priority(name="Shared", rank="P1")]

        error = _validate_priorities(
            priorities, clusters, cluster_names, subcluster_names, subcluster_to_parent
        )
        assert "both a cluster and subcluster" in error

    def test_mixed_container_and_item_priorities(self):
        """Can mix cluster priority and item priority."""
        clusters = [
            make_cluster("Work", items=["task1"]),
            make_cluster("Home", items=["chore"]),
        ]
        cluster_names, subcluster_names, subcluster_to_parent = _find_all_names(clusters)
        priorities = [
            make_priority(name="Work", rank="P1"),
            make_item_priority("Home", 0, "P2"),
        ]

        error = _validate_priorities(
            priorities, clusters, cluster_names, subcluster_names, subcluster_to_parent
        )
        assert error is None


class TestApplyPrioritiesWithThoughtItems:
    """Tests for _apply_priorities with thought item targeting."""

    def test_applies_item_priority(self):
        """Priority is applied to thought item."""
        clusters = [make_cluster("Work", items=["task1", "task2"])]
        priorities = [make_item_priority("Work", 0, "P1", "blocker")]

        result = _apply_priorities(clusters, priorities)

        items = result[0]["thought_items"]
        assert items[0]["text"] == "task1"
        assert items[0]["priority"] == {"rank": "P1", "reason": "blocker"}
        # Second item should not have priority (still a string since never prioritized)
        assert items[1] == "task2"

    def test_converts_string_to_object_when_prioritized(self):
        """String thought items become objects when prioritized."""
        clusters = [make_cluster("Work", items=["plain string"])]
        priorities = [make_item_priority("Work", 0, "P1")]

        result = _apply_priorities(clusters, priorities)

        item = result[0]["thought_items"][0]
        assert isinstance(item, dict)
        assert item["text"] == "plain string"
        assert item["priority"]["rank"] == "P1"

    def test_clears_existing_item_priorities(self):
        """Existing item priorities are cleared when not in priorities list."""
        clusters = [{
            "cluster_name": "Work",
            "thought_items": [
                {"text": "has priority", "priority": {"rank": "P1"}},
            ],
            "subclusters": [],
            "tags": [],
        }]
        priorities = []  # Empty = clear all

        result = _apply_priorities(clusters, priorities)

        item = result[0]["thought_items"][0]
        assert item["text"] == "has priority"
        assert item["priority"] is None

    def test_applies_subcluster_item_priority(self):
        """Priority is applied to thought item in subcluster."""
        clusters = [
            make_cluster("Work", subclusters=[
                make_subcluster("Urgent", items=["urgent task"])
            ])
        ]
        priorities = [make_item_priority("Urgent", 0, "P1")]

        result = _apply_priorities(clusters, priorities)

        sub_item = result[0]["subclusters"][0]["thought_items"][0]
        assert sub_item["text"] == "urgent task"
        assert sub_item["priority"]["rank"] == "P1"

    def test_preserves_object_structure_after_clearing(self):
        """Object items keep object format even after priority is cleared."""
        clusters = [{
            "cluster_name": "Work",
            "thought_items": [
                {"text": "was prioritized", "priority": {"rank": "P1"}},
            ],
            "subclusters": [],
            "tags": [],
        }]
        priorities = []

        result = _apply_priorities(clusters, priorities)

        item = result[0]["thought_items"][0]
        assert isinstance(item, dict)
        assert item["text"] == "was prioritized"
        assert item["priority"] is None


class TestHandlerWithThoughtItems:
    """Handler tests for thought item priorities."""

    @pytest.mark.asyncio
    async def test_prioritize_thought_item_success(self):
        """Prioritizing a thought item works correctly."""
        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": [
                    {"cluster_name": "Work", "thought_items": ["task1", "task2"]}
                ],
                "priorities": [
                    {"item_index": 0, "parent_name": "Work", "rank": "P1"}
                ],
            },
        )

        assert result.isError is None or result.isError is False
        clusters = result.structuredContent["clusters"]
        item = clusters[0]["thought_items"][0]
        assert item["text"] == "task1"
        assert item["priority"]["rank"] == "P1"

    @pytest.mark.asyncio
    async def test_rejects_out_of_bounds_index(self):
        """Out of bounds item_index returns error."""
        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": [
                    {"cluster_name": "Work", "thought_items": ["only one"]}
                ],
                "priorities": [
                    {"item_index": 5, "parent_name": "Work", "rank": "P1"}
                ],
            },
        )

        assert result.isError is True
        assert "out of bounds" in result.content[0].text

    @pytest.mark.asyncio
    async def test_rejects_invalid_parent(self):
        """Invalid parent_name returns error."""
        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": [
                    {"cluster_name": "Work", "thought_items": ["task"]}
                ],
                "priorities": [
                    {"item_index": 0, "parent_name": "NonExistent", "rank": "P1"}
                ],
            },
        )

        assert result.isError is True
        assert "NonExistent" in result.content[0].text

    @pytest.mark.asyncio
    async def test_rejects_ambiguous_name(self):
        """Ambiguous name returns error."""
        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": [
                    {
                        "cluster_name": "Same",
                        "thought_items": [],
                        "subclusters": [
                            {"subcluster_name": "Same", "thought_items": ["x"]}
                        ]
                    }
                ],
                "priorities": [
                    {"name": "Same", "rank": "P1"}
                ],
            },
        )

        assert result.isError is True
        assert "both a cluster and subcluster" in result.content[0].text

    @pytest.mark.asyncio
    async def test_mixed_priorities_success(self):
        """Mix of cluster and item priorities works."""
        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": [
                    {"cluster_name": "Work", "thought_items": ["task"]},
                    {"cluster_name": "Home", "thought_items": ["chore"]},
                ],
                "priorities": [
                    {"name": "Work", "rank": "P1"},
                    {"item_index": 0, "parent_name": "Home", "rank": "P2"},
                ],
            },
        )

        assert result.isError is None or result.isError is False
        clusters = result.structuredContent["clusters"]

        # Cluster has direct priority
        assert clusters[0]["priority"]["rank"] == "P1"

        # Item has priority
        item = clusters[1]["thought_items"][0]
        assert item["text"] == "chore"
        assert item["priority"]["rank"] == "P2"

    @pytest.mark.asyncio
    async def test_reprioritize_same_item_different_rank(self):
        """Re-prioritizing an item with a different rank succeeds."""
        # First prioritization
        result1 = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": [
                    {"cluster_name": "Work", "thought_items": ["task"]}
                ],
                "priorities": [
                    {"item_index": 0, "parent_name": "Work", "rank": "P1"}
                ],
            },
        )
        assert result1.isError is None or result1.isError is False
        clusters = result1.structuredContent["clusters"]

        # Second prioritization with different rank
        result2 = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": clusters,
                "priorities": [
                    {"item_index": 0, "parent_name": "Work", "rank": "P2"}
                ],
            },
        )
        assert result2.isError is None or result2.isError is False
        item = result2.structuredContent["clusters"][0]["thought_items"][0]
        assert item["priority"]["rank"] == "P2"

    @pytest.mark.asyncio
    async def test_clearing_item_preserves_object_structure(self):
        """Clearing item priority keeps object format."""
        # First add priority
        result1 = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": [
                    {"cluster_name": "Work", "thought_items": ["task"]}
                ],
                "priorities": [
                    {"item_index": 0, "parent_name": "Work", "rank": "P1"}
                ],
            },
        )
        clusters = result1.structuredContent["clusters"]

        # Then clear all priorities
        result2 = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": clusters,
                "priorities": [],
            },
        )

        assert result2.isError is None or result2.isError is False
        item = result2.structuredContent["clusters"][0]["thought_items"][0]
        # Should still be an object, not collapsed back to string
        assert isinstance(item, dict)
        assert item["text"] == "task"
        assert item["priority"] is None

    @pytest.mark.asyncio
    async def test_rejects_duplicate_rank_across_entity_types(self):
        """P1 on item blocks P1 on cluster (global uniqueness)."""
        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "clusters": [
                    {"cluster_name": "Work", "thought_items": ["task"]},
                    {"cluster_name": "Home", "thought_items": ["chore"]},
                ],
                "priorities": [
                    {"item_index": 0, "parent_name": "Work", "rank": "P1"},
                    {"name": "Home", "rank": "P1"},  # Duplicate P1
                ],
            },
        )

        assert result.isError is True
        assert ERROR_DUPLICATE_RANK in result.content[0].text
