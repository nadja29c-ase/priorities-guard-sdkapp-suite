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
    PriorityInput,
    MAX_PRIORITIES,
    ERROR_TOO_MANY_PRIORITIES,
    ERROR_DUPLICATE_RANK,
    ERROR_INVALID_CLUSTER,
    ERROR_NO_BOARD,
    ERROR_PARENT_AND_CHILD,
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


def make_priority(name, rank, reason=None):
    """Helper to create PriorityInput objects."""
    return PriorityInput(name=name, rank=rank, reason=reason)


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
        priorities = [make_priority("Work", "P1")]
        cluster_names = {"Work", "Home"}
        subcluster_names = set()
        subcluster_to_parent = {}

        error = _validate_priorities(
            priorities, cluster_names, subcluster_names, subcluster_to_parent
        )
        assert error is None

    def test_valid_three_priorities(self):
        """Three valid priorities passes validation."""
        priorities = [
            make_priority("Work", "P1"),
            make_priority("Home", "P2"),
            make_priority("Health", "P3"),
        ]
        cluster_names = {"Work", "Home", "Health"}
        subcluster_names = set()
        subcluster_to_parent = {}

        error = _validate_priorities(
            priorities, cluster_names, subcluster_names, subcluster_to_parent
        )
        assert error is None

    def test_rejects_too_many_priorities(self):
        """More than 3 priorities is rejected."""
        priorities = [
            make_priority("A", "P1"),
            make_priority("B", "P2"),
            make_priority("C", "P3"),
            make_priority("D", "P1"),  # 4th
        ]
        cluster_names = {"A", "B", "C", "D"}

        error = _validate_priorities(priorities, cluster_names, set(), {})
        assert error == ERROR_TOO_MANY_PRIORITIES

    def test_rejects_duplicate_ranks(self):
        """Duplicate ranks (two P1s) are rejected."""
        priorities = [
            make_priority("Work", "P1"),
            make_priority("Home", "P1"),  # Duplicate P1
        ]
        cluster_names = {"Work", "Home"}

        error = _validate_priorities(priorities, cluster_names, set(), {})
        assert error == ERROR_DUPLICATE_RANK

    def test_rejects_invalid_cluster_name(self):
        """Invalid cluster name is rejected."""
        priorities = [make_priority("NonExistent", "P1")]
        cluster_names = {"Work", "Home"}

        error = _validate_priorities(priorities, cluster_names, set(), {})
        assert error == ERROR_INVALID_CLUSTER

    def test_accepts_subcluster_name(self):
        """Valid subcluster name is accepted."""
        priorities = [make_priority("Urgent", "P1")]
        cluster_names = {"Work"}
        subcluster_names = {"Urgent"}
        subcluster_to_parent = {"Urgent": "Work"}

        error = _validate_priorities(
            priorities, cluster_names, subcluster_names, subcluster_to_parent
        )
        assert error is None

    def test_rejects_parent_and_child_conflict(self):
        """Cannot prioritize both cluster and its subcluster."""
        priorities = [
            make_priority("Work", "P1"),
            make_priority("Urgent", "P2"),  # Urgent is a subcluster of Work
        ]
        cluster_names = {"Work"}
        subcluster_names = {"Urgent"}
        subcluster_to_parent = {"Urgent": "Work"}

        error = _validate_priorities(
            priorities, cluster_names, subcluster_names, subcluster_to_parent
        )
        assert error == ERROR_PARENT_AND_CHILD

    def test_accepts_empty_priorities(self):
        """Empty priorities array is valid (clears priorities)."""
        error = _validate_priorities([], {"Work"}, set(), {})
        assert error is None


class TestApplyPriorities:
    """Tests for _apply_priorities helper."""

    def test_applies_cluster_priority(self):
        """Priority is applied to cluster."""
        clusters = [make_cluster("Work", items=["task"])]
        priorities = [make_priority("Work", "P1", "blocker")]

        result = _apply_priorities(clusters, priorities)

        assert result[0]["priority"] == {"rank": "P1", "reason": "blocker"}

    def test_applies_subcluster_priority(self):
        """Priority is applied to subcluster."""
        clusters = [
            make_cluster("Work", subclusters=[
                make_subcluster("Urgent", items=["task"]),
            ])
        ]
        priorities = [make_priority("Urgent", "P2", "goal-aligned")]

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
        priorities = [make_priority("Work", "P1")]

        result = _apply_priorities(clusters, priorities)

        # Original unchanged
        assert "priority" not in original_cluster
        # Result has priority
        assert result[0]["priority"]["rank"] == "P1"

    def test_reason_none_when_not_provided(self):
        """Reason is None when not provided."""
        clusters = [make_cluster("Work", items=["task"])]
        priorities = [make_priority("Work", "P1")]

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
