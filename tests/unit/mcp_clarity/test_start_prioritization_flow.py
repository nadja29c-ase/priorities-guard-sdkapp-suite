"""
Unit tests for start_prioritization_flow tool.

Focus areas:
1. Validation rules (max 3, unique ranks, valid names, parent+child conflict)
2. Priority embedding in cluster/subcluster objects
3. Empty priorities (clearing)
4. Reason field handling
5. Error messages
"""

from unittest.mock import AsyncMock, patch

import pytest
from mcp_server.clarity.tools.start_prioritization_flow import (
    handle,
    ALLOWED_TOP_LEVEL_KEYS,
    INPUT_SCHEMA,
    _find_all_names,
    _validate_priorities,
    ERROR_TOO_MANY_PRIORITIES,
    ERROR_DUPLICATE_RANK,
    ERROR_INVALID_CLUSTER,
    ERROR_NO_BOARD,
    ERROR_PARENT_AND_CHILD,
    ERROR_AMBIGUOUS_NAME,
    ERROR_INVALID_PARENT,
    ERROR_ITEM_INDEX_OUT_OF_BOUNDS,
)
from mcp_server.clarity.tools.board_utils import (
    PriorityInput,
    MAX_PRIORITIES,
    apply_priorities as _apply_priorities,
    normalize_thought_item as _normalize_thought_item,
    clear_all_thought_item_priorities as _clear_all_thought_item_priorities,
    clear_all_priorities as _clear_all_priorities,
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
        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            mock_get.return_value = {
                "cluster_data": {"clusters": []},
            }
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "Work is P1",
                    "priorities": [],
                },
            )
            assert result.isError is True
            assert ERROR_NO_BOARD in result.content[0].text

    @pytest.mark.asyncio
    async def test_rejects_too_many_priorities(self):
        """More than 3 priorities returns error."""
        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            mock_get.return_value = {
                "cluster_data": {
                    "clusters": [
                        {"cluster_name": "A", "thought_items": ["x"], "subclusters": []},
                        {"cluster_name": "B", "thought_items": ["x"], "subclusters": []},
                        {"cluster_name": "C", "thought_items": ["x"], "subclusters": []},
                        {"cluster_name": "D", "thought_items": ["x"], "subclusters": []},
                    ]
                },
            }
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "A is P1, B is P2, C is P3, D is P1",
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
        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            mock_get.return_value = {
                "cluster_data": {
                    "clusters": [
                        {"cluster_name": "Work", "thought_items": ["x"], "subclusters": []},
                        {"cluster_name": "Home", "thought_items": ["x"], "subclusters": []},
                    ]
                },
            }
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "Work and Home are both P1",
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
        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            mock_get.return_value = {
                "cluster_data": {
                    "clusters": [
                        {"cluster_name": "Work", "thought_items": ["x"], "subclusters": []},
                    ]
                },
            }
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "NonExistent is P1",
                    "priorities": [{"name": "NonExistent", "rank": "P1"}],
                },
            )
            assert result.isError is True
            assert ERROR_INVALID_CLUSTER in result.content[0].text

    @pytest.mark.asyncio
    async def test_rejects_parent_child_conflict(self):
        """Prioritizing parent and child returns error."""
        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            mock_get.return_value = {
                "cluster_data": {
                    "clusters": [
                        {
                            "cluster_name": "Work",
                            "thought_items": [],
                            "subclusters": [
                                {"subcluster_name": "Urgent", "thought_items": ["task"]}
                            ],
                        }
                    ]
                },
            }
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "Work is P1, Urgent is P2",
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
        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            mock_get.return_value = {
                "cluster_data": {
                    "clusters": [
                        {"cluster_name": "Work", "thought_items": ["x"], "subclusters": []},
                    ]
                },
            }
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "Work is P4",
                    "priorities": [{"name": "Work", "rank": "P4"}],  # Invalid
                },
            )
            assert result.isError is True


class TestHandlerSuccess:
    """Tests for successful prioritization."""

    @pytest.mark.asyncio
    async def test_single_priority_success(self):
        """Single priority is applied successfully."""
        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            mock_get.return_value = {
                "cluster_data": {
                    "clusters": [
                        {"cluster_name": "Work", "thought_items": ["task"], "subclusters": []},
                    ]
                },
            }
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "Work is my top priority",
                    "priorities": [{"name": "Work", "rank": "P1"}],
                },
            )

            assert result.isError is None or result.isError is False
            clusters = result.structuredContent["clusters"]
            assert clusters[0]["priority"]["rank"] == "P1"

    @pytest.mark.asyncio
    async def test_three_priorities_success(self):
        """Three priorities are applied successfully."""
        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            mock_get.return_value = {
                "cluster_data": {
                    "clusters": [
                        {"cluster_name": "Work", "thought_items": ["x"], "subclusters": []},
                        {"cluster_name": "Home", "thought_items": ["x"], "subclusters": []},
                        {"cluster_name": "Health", "thought_items": ["x"], "subclusters": []},
                    ]
                },
            }
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "Work P1, Home P2, Health P3",
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
        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            mock_get.return_value = {
                "cluster_data": {
                    "clusters": [
                        {"cluster_name": "Work", "thought_items": ["task"], "subclusters": [], "priority": {"rank": "P1", "reason": None}},
                    ]
                },
            }
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "clear all",
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
        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            mock_get.return_value = {
                "cluster_data": {
                    "clusters": [
                        {
                            "cluster_name": "Work",
                            "thought_items": [],
                            "subclusters": [
                                {"subcluster_name": "Urgent", "thought_items": ["task"]}
                            ],
                        }
                    ]
                },
            }
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "Urgent is P1",
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
        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            mock_get.return_value = {
                "cluster_data": {
                    "clusters": [
                        {"cluster_name": "Work", "thought_items": ["task"], "subclusters": []},
                    ]
                },
            }
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "unblock",
                    "user_priorities_verbatim": "Work is P1 because blocker",
                    "priorities": [{"name": "Work", "rank": "P1", "reason": "blocker"}],
                },
            )

            assert result.isError is None or result.isError is False
            clusters = result.structuredContent["clusters"]
            assert clusters[0]["priority"]["reason"] == "blocker"

    @pytest.mark.asyncio
    async def test_reason_null_when_absent(self):
        """Reason is null when not provided."""
        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            mock_get.return_value = {
                "cluster_data": {
                    "clusters": [
                        {"cluster_name": "Work", "thought_items": ["task"], "subclusters": []},
                    ]
                },
            }
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "Work is P1",
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
        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            mock_get.return_value = {
                "cluster_data": {
                    "clusters": [
                        {"cluster_name": "Third", "thought_items": ["x"], "subclusters": []},
                        {"cluster_name": "First", "thought_items": ["x"], "subclusters": []},
                        {"cluster_name": "Second", "thought_items": ["x"], "subclusters": []},
                    ]
                },
            }
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "First is P1, Second is P2",
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
        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            mock_get.return_value = {
                "cluster_data": {
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
                    ]
                },
            }
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "First is P1",
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
        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            mock_get.return_value = {
                "cluster_data": {
                    "clusters": [
                        {"cluster_name": "Work", "thought_items": ["task"], "subclusters": []},
                    ]
                },
            }
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "Work is P1",
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
        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            mock_get.return_value = {
                "cluster_data": {
                    "clusters": [
                        {
                            "cluster_name": "Work",
                            "thought_items": ["task1", "task2"],
                            "subclusters": [
                                {"subcluster_name": "Urgent", "thought_items": ["sub1", "sub2", "sub3"]}
                            ],
                        }
                    ]
                },
            }
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "Work is P1",
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
        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            mock_get.return_value = {
                "cluster_data": {
                    "clusters": [
                        {"cluster_name": "Work", "thought_items": ["x"], "subclusters": []},
                        {"cluster_name": "Home", "thought_items": ["x"], "subclusters": []},
                    ]
                },
            }
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "Work P2, Home P1",
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
        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            mock_get.return_value = {
                "cluster_data": {
                    "clusters": [
                        {"cluster_name": "Work", "thought_items": ["task1", "task2"], "subclusters": []}
                    ]
                },
            }
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "task1 is P1",
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
        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            mock_get.return_value = {
                "cluster_data": {
                    "clusters": [
                        {"cluster_name": "Work", "thought_items": ["only one"], "subclusters": []}
                    ]
                },
            }
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "item 5 is P1",
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
        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            mock_get.return_value = {
                "cluster_data": {
                    "clusters": [
                        {"cluster_name": "Work", "thought_items": ["task"], "subclusters": []}
                    ]
                },
            }
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "item 0 in NonExistent is P1",
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
        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            mock_get.return_value = {
                "cluster_data": {
                    "clusters": [
                        {
                            "cluster_name": "Same",
                            "thought_items": [],
                            "subclusters": [
                                {"subcluster_name": "Same", "thought_items": ["x"]}
                            ]
                        }
                    ]
                },
            }
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "Same is P1",
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
        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            mock_get.return_value = {
                "cluster_data": {
                    "clusters": [
                        {"cluster_name": "Work", "thought_items": ["task"], "subclusters": []},
                        {"cluster_name": "Home", "thought_items": ["chore"], "subclusters": []},
                    ]
                },
            }
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "Work P1, chore P2",
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
        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            # First prioritization returns clusters with P1
            mock_get.return_value = {
                "cluster_data": {
                    "clusters": [
                        {"cluster_name": "Work", "thought_items": [{"text": "task", "priority": {"rank": "P1", "reason": None}}], "subclusters": []}
                    ]
                },
            }

            # Second prioritization with different rank
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "task is now P2",
                    "priorities": [
                        {"item_index": 0, "parent_name": "Work", "rank": "P2"}
                    ],
                },
            )
            assert result.isError is None or result.isError is False
            item = result.structuredContent["clusters"][0]["thought_items"][0]
            assert item["priority"]["rank"] == "P2"

    @pytest.mark.asyncio
    async def test_clearing_item_preserves_object_structure(self):
        """Clearing item priority keeps object format."""
        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            mock_get.return_value = {
                "cluster_data": {
                    "clusters": [
                        {"cluster_name": "Work", "thought_items": [{"text": "task", "priority": {"rank": "P1", "reason": None}}], "subclusters": []}
                    ]
                },
            }

            # Clear all priorities
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "clear all",
                    "priorities": [],
                },
            )

            assert result.isError is None or result.isError is False
            item = result.structuredContent["clusters"][0]["thought_items"][0]
            # Should still be an object, not collapsed back to string
            assert isinstance(item, dict)
            assert item["text"] == "task"
            assert item["priority"] is None

    @pytest.mark.asyncio
    async def test_rejects_duplicate_rank_across_entity_types(self):
        """P1 on item blocks P1 on cluster (global uniqueness)."""
        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            mock_get.return_value = {
                "cluster_data": {
                    "clusters": [
                        {"cluster_name": "Work", "thought_items": ["task"], "subclusters": []},
                        {"cluster_name": "Home", "thought_items": ["chore"], "subclusters": []},
                    ]
                },
            }
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "task P1, Home P1",
                    "priorities": [
                        {"item_index": 0, "parent_name": "Work", "rank": "P1"},
                        {"name": "Home", "rank": "P1"},  # Duplicate P1
                    ],
                },
            )

            assert result.isError is True
            assert ERROR_DUPLICATE_RANK in result.content[0].text


# ============================================================================
# Priority Preservation Tests (Increment 23)
# ============================================================================


class TestClearAllPriorities:
    """Tests for _clear_all_priorities helper."""

    def test_clears_cluster_priorities(self):
        """Clears priority from all clusters."""
        clusters = [
            {"cluster_name": "Work", "thought_items": [], "subclusters": [], "priority": {"rank": "P1"}},
            {"cluster_name": "Home", "thought_items": [], "subclusters": [], "priority": {"rank": "P2"}},
        ]
        result = _clear_all_priorities(clusters)
        assert result[0]["priority"] is None
        assert result[1]["priority"] is None

    def test_clears_subcluster_priorities(self):
        """Clears priority from all subclusters."""
        clusters = [{
            "cluster_name": "Work",
            "thought_items": [],
            "subclusters": [
                {"subcluster_name": "Urgent", "thought_items": [], "priority": {"rank": "P1"}},
            ],
        }]
        result = _clear_all_priorities(clusters)
        assert result[0]["subclusters"][0]["priority"] is None

    def test_clears_thought_item_priorities(self):
        """Clears priority from all thought items."""
        clusters = [{
            "cluster_name": "Work",
            "thought_items": [
                {"text": "task1", "priority": {"rank": "P1"}},
                {"text": "task2", "priority": {"rank": "P2"}},
            ],
            "subclusters": [],
        }]
        result = _clear_all_priorities(clusters)
        assert result[0]["thought_items"][0]["priority"] is None
        assert result[0]["thought_items"][1]["priority"] is None

    def test_does_not_mutate_original(self):
        """Original clusters are not mutated."""
        clusters = [{"cluster_name": "Work", "thought_items": [], "subclusters": [], "priority": {"rank": "P1"}}]
        _clear_all_priorities(clusters)
        assert clusters[0]["priority"] == {"rank": "P1"}


class TestPriorityPreservation:
    """Tests for priority preservation behavior (Increment 23 fix)."""

    def test_adding_priority_preserves_existing(self):
        """Add P3 to board with P1/P2, verify P1/P2 preserved."""
        clusters = [
            {"cluster_name": "Work", "thought_items": [], "subclusters": [], "priority": {"rank": "P1", "reason": None}},
            {"cluster_name": "Home", "thought_items": [], "subclusters": [], "priority": {"rank": "P2", "reason": None}},
            {"cluster_name": "Health", "thought_items": [], "subclusters": []},
        ]
        priorities = [make_priority(name="Health", rank="P3")]

        result = _apply_priorities(clusters, priorities)

        # P1 and P2 should be preserved
        assert result[0]["priority"]["rank"] == "P1"
        assert result[1]["priority"]["rank"] == "P2"
        # P3 should be added
        assert result[2]["priority"]["rank"] == "P3"

    def test_moving_rank_clears_old_holder(self):
        """Move P1 from Work to Health, verify Work cleared."""
        clusters = [
            {"cluster_name": "Work", "thought_items": [], "subclusters": [], "priority": {"rank": "P1", "reason": None}},
            {"cluster_name": "Home", "thought_items": [], "subclusters": [], "priority": {"rank": "P2", "reason": None}},
            {"cluster_name": "Health", "thought_items": [], "subclusters": []},
        ]
        priorities = [make_priority(name="Health", rank="P1")]

        result = _apply_priorities(clusters, priorities)

        # Work's P1 should be cleared (rank taken by Health)
        assert result[0]["priority"] is None
        # Home's P2 should be preserved
        assert result[1]["priority"]["rank"] == "P2"
        # Health gets P1
        assert result[2]["priority"]["rank"] == "P1"

    def test_empty_priorities_clears_all_explicit(self):
        """Empty array clears everything via explicit early return."""
        clusters = [
            {"cluster_name": "Work", "thought_items": [{"text": "task", "priority": {"rank": "P3"}}], "subclusters": [], "priority": {"rank": "P1", "reason": None}},
            {"cluster_name": "Home", "thought_items": [], "subclusters": [], "priority": {"rank": "P2", "reason": None}},
        ]
        priorities = []

        result = _apply_priorities(clusters, priorities)

        assert result[0]["priority"] is None
        assert result[1]["priority"] is None
        assert result[0]["thought_items"][0]["priority"] is None

    def test_replacing_rank_on_same_entity(self):
        """Change Home from P2 to P3, verify P1 preserved."""
        clusters = [
            {"cluster_name": "Work", "thought_items": [], "subclusters": [], "priority": {"rank": "P1", "reason": None}},
            {"cluster_name": "Home", "thought_items": [], "subclusters": [], "priority": {"rank": "P2", "reason": None}},
        ]
        priorities = [make_priority(name="Home", rank="P3")]

        result = _apply_priorities(clusters, priorities)

        # Work's P1 should be preserved
        assert result[0]["priority"]["rank"] == "P1"
        # Home gets P3 (P2 is gone)
        assert result[1]["priority"]["rank"] == "P3"

    def test_same_entity_same_rank_preserved(self):
        """Re-assign P1 to Work (already has P1), verify works."""
        clusters = [
            {"cluster_name": "Work", "thought_items": [], "subclusters": [], "priority": {"rank": "P1", "reason": None}},
            {"cluster_name": "Home", "thought_items": [], "subclusters": [], "priority": {"rank": "P2", "reason": None}},
        ]
        priorities = [make_priority(name="Work", rank="P1")]

        result = _apply_priorities(clusters, priorities)

        # Work keeps P1 (request wins, same value)
        assert result[0]["priority"]["rank"] == "P1"
        # Home's P2 should be preserved
        assert result[1]["priority"]["rank"] == "P2"

    def test_subcluster_priority_preserved(self):
        """Subcluster priorities are preserved when not reassigned."""
        clusters = [{
            "cluster_name": "Work",
            "thought_items": [],
            "subclusters": [
                {"subcluster_name": "Urgent", "thought_items": [], "priority": {"rank": "P1", "reason": None}},
                {"subcluster_name": "Later", "thought_items": [], "priority": {"rank": "P2", "reason": None}},
            ],
        }]
        priorities = [make_priority(name="Later", rank="P3")]

        result = _apply_priorities(clusters, priorities)

        # Urgent keeps P1
        assert result[0]["subclusters"][0]["priority"]["rank"] == "P1"
        # Later gets P3
        assert result[0]["subclusters"][1]["priority"]["rank"] == "P3"

    def test_thought_item_priority_preserved(self):
        """Thought item priorities are preserved when not reassigned."""
        clusters = [{
            "cluster_name": "Work",
            "thought_items": [
                {"text": "task1", "priority": {"rank": "P1", "reason": None}},
                {"text": "task2", "priority": {"rank": "P2", "reason": None}},
                "task3",  # string item, no priority
            ],
            "subclusters": [],
        }]
        priorities = [make_item_priority("Work", 2, "P3")]

        result = _apply_priorities(clusters, priorities)

        # task1 keeps P1
        assert result[0]["thought_items"][0]["priority"]["rank"] == "P1"
        # task2 keeps P2
        assert result[0]["thought_items"][1]["priority"]["rank"] == "P2"
        # task3 gets P3
        assert result[0]["thought_items"][2]["priority"]["rank"] == "P3"

    def test_moving_rank_from_item_to_cluster(self):
        """Moving P1 from thought item to cluster clears item."""
        clusters = [{
            "cluster_name": "Work",
            "thought_items": [
                {"text": "task1", "priority": {"rank": "P1", "reason": None}},
            ],
            "subclusters": [],
        }, {
            "cluster_name": "Home",
            "thought_items": [],
            "subclusters": [],
        }]
        priorities = [make_priority(name="Home", rank="P1")]

        result = _apply_priorities(clusters, priorities)

        # task1's P1 should be cleared (rank taken by Home)
        assert result[0]["thought_items"][0]["priority"] is None
        # Home gets P1
        assert result[1]["priority"]["rank"] == "P1"

    def test_moving_rank_from_cluster_to_item(self):
        """Moving P1 from cluster to thought item clears cluster."""
        clusters = [{
            "cluster_name": "Work",
            "thought_items": ["task1"],
            "subclusters": [],
            "priority": {"rank": "P1", "reason": None},
        }]
        priorities = [make_item_priority("Work", 0, "P1")]

        result = _apply_priorities(clusters, priorities)

        # Work cluster's P1 should be cleared (rank taken by item)
        assert result[0]["priority"] is None
        # task1 gets P1
        assert result[0]["thought_items"][0]["priority"]["rank"] == "P1"


class TestPriorityPreservationHandler:
    """Handler-level tests for priority preservation."""

    @pytest.mark.asyncio
    async def test_adding_p3_preserves_p1_p2(self):
        """Integration: Add P3 to board with P1/P2, verify preserved."""
        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            # Board already has P1 and P2
            mock_get.return_value = {
                "cluster_data": {
                    "clusters": [
                        {"cluster_name": "Work", "thought_items": ["task"], "subclusters": [], "priority": {"rank": "P1", "reason": None}},
                        {"cluster_name": "Home", "thought_items": ["chore"], "subclusters": [], "priority": {"rank": "P2", "reason": None}},
                        {"cluster_name": "Health", "thought_items": ["exercise"], "subclusters": []},
                    ]
                },
            }

            # Add P3 only
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "Health is P3",
                    "priorities": [
                        {"name": "Health", "rank": "P3"},
                    ],
                },
            )
            assert result.isError is None or result.isError is False
            final_clusters = result.structuredContent["clusters"]

            # Verify all priorities
            work = next(c for c in final_clusters if c["cluster_name"] == "Work")
            home = next(c for c in final_clusters if c["cluster_name"] == "Home")
            health = next(c for c in final_clusters if c["cluster_name"] == "Health")

            assert work["priority"]["rank"] == "P1"
            assert home["priority"]["rank"] == "P2"
            assert health["priority"]["rank"] == "P3"

    @pytest.mark.asyncio
    async def test_moving_rank_clears_old_holder_handler(self):
        """Integration: Move P1 from Work to Health."""
        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock):
            # Board has P1 on Work
            mock_get.return_value = {
                "cluster_data": {
                    "clusters": [
                        {"cluster_name": "Work", "thought_items": ["task"], "subclusters": [], "priority": {"rank": "P1", "reason": None}},
                        {"cluster_name": "Health", "thought_items": ["exercise"], "subclusters": []},
                    ]
                },
            }

            # Move P1 to Health
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "Health is now P1",
                    "priorities": [
                        {"name": "Health", "rank": "P1"},
                    ],
                },
            )
            final_clusters = result.structuredContent["clusters"]

            work = next(c for c in final_clusters if c["cluster_name"] == "Work")
            health = next(c for c in final_clusters if c["cluster_name"] == "Health")

            # Work's P1 should be cleared
            assert work["priority"] is None
            # Health gets P1
            assert health["priority"]["rank"] == "P1"


# ============================================================================
# Malformed-Input Guards (A -> B -> C)
# ============================================================================


BOARD_WITH_P1 = {
    "cluster_data": {
        "clusters": [
            {"cluster_name": "Work", "thought_items": ["task"], "subclusters": [],
             "priority": {"rank": "P1", "reason": "blocker"}},
            {"cluster_name": "Home", "thought_items": ["chore"], "subclusters": []},
        ]
    },
}


class TestMalformedInputGuards:
    """
    Malformed input must FAIL CLOSED before any fetch/mutate/persist.

    Pre-fix, each of these silently resolved `priorities` to [], took the
    clear-all branch, and PERSISTED the erasure.
    """

    @staticmethod
    def _patched():
        """Patch the three side-effecting calls so non-invocation is assertable."""
        return (
            patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster",
                  new_callable=AsyncMock),
            patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster",
                  new_callable=AsyncMock),
            patch("mcp_server.clarity.tools.start_prioritization_flow._apply_priorities"),
        )

    @pytest.mark.asyncio
    async def test_missing_priorities_key_fails_closed(self):
        """Guard B: `priorities` absent -> structured error, nothing touched."""
        get_p, persist_p, apply_p = self._patched()
        with get_p as mock_get, persist_p as mock_persist, apply_p as mock_apply:
            mock_get.return_value = BOARD_WITH_P1
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "Work is my P1",
                },
            )

            assert result.isError is True
            sc = result.structuredContent
            assert sc["success"] is False
            assert sc["error"] == "missing_priorities"
            assert sc["state_modified"] is False
            assert sc["invalid_fields"] == ["priorities"]
            assert sc["assistant_guidance"]["action"] == "retry_with_canonical_priorities"
            assert result.content[0].text == "Malformed input: missing_priorities"

            mock_get.assert_not_called()
            mock_apply.assert_not_called()
            mock_persist.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_top_level_key_with_valid_priorities_fails_closed(self):
        """
        Guard A in isolation: an unknown key cannot be silently ignored even when
        `priorities` is present and valid.
        """
        get_p, persist_p, apply_p = self._patched()
        with get_p as mock_get, persist_p as mock_persist, apply_p as mock_apply:
            mock_get.return_value = BOARD_WITH_P1
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "Home is my P2",
                    "priorities": [{"name": "Home", "rank": "P2", "reason": "relief"}],
                    "priority_2": "Home",
                },
            )

            assert result.isError is True
            sc = result.structuredContent
            assert sc["error"] == "unknown_top_level_fields"
            assert sc["state_modified"] is False
            assert sc["invalid_fields"] == ["priority_2"]
            assert result.content[0].text == "Malformed input: unknown_top_level_fields"

            mock_get.assert_not_called()
            mock_apply.assert_not_called()
            mock_persist.assert_not_called()

    @pytest.mark.asyncio
    async def test_production_multi_fault_shape_guard_a_wins(self):
        """
        The EXACT production shape trips both A and B. Asserts the A->B
        precedence: it must report the unknown fields, not the missing key.
        """
        get_p, persist_p, apply_p = self._patched()
        with get_p as mock_get, persist_p as mock_persist, apply_p as mock_apply:
            mock_get.return_value = BOARD_WITH_P1
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "Home is my P1",
                    "priority_1": "Home",
                    "priority_1_parent_cluster": "Work",
                },
            )

            assert result.isError is True
            sc = result.structuredContent
            assert sc["error"] == "unknown_top_level_fields"
            assert sc["state_modified"] is False
            assert sc["invalid_fields"] == ["priority_1", "priority_1_parent_cluster"]

            mock_get.assert_not_called()
            mock_apply.assert_not_called()
            mock_persist.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad_value", ["Work Projects", {"name": "Work", "rank": "P1"}])
    async def test_non_list_priorities_fails_closed(self, bad_value):
        """
        Guard C: `priorities` present but not a list. Pre-fix this was coerced to
        [] and cleared the board — the third path to the same destructive bug.
        """
        get_p, persist_p, apply_p = self._patched()
        with get_p as mock_get, persist_p as mock_persist, apply_p as mock_apply:
            mock_get.return_value = BOARD_WITH_P1
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "Work is my P1",
                    "priorities": bad_value,
                },
            )

            assert result.isError is True
            sc = result.structuredContent
            assert sc["error"] == "invalid_priorities_type"
            assert sc["state_modified"] is False
            assert sc["invalid_fields"] == ["priorities"]
            assert result.content[0].text == "Malformed input: invalid_priorities_type"

            mock_get.assert_not_called()
            mock_apply.assert_not_called()
            mock_persist.assert_not_called()

    @pytest.mark.asyncio
    async def test_guidance_instruction_states_cumulative_replacement(self):
        """
        The corrective instruction must say the array REPLACES (so the model
        resends the full cumulative set) and that nothing was modified —
        otherwise a fixed destructive-clear becomes a destructive-overwrite.
        """
        get_p, persist_p, _ = self._patched()
        with get_p, persist_p:
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "Work is my P1",
                },
            )
        instruction = result.structuredContent["assistant_guidance"]["instruction"]
        assert "CUMULATIVE" in instruction
        assert "REPLACES" in instruction
        assert "NO existing priorities were modified" in instruction

    @pytest.mark.asyncio
    async def test_provenance_gates_still_win_over_malformed_guards(self):
        """
        Ordering: a call missing BOTH a verbatim field and `priorities` must get
        the EXISTING provenance instruction, unchanged by this increment.
        """
        get_p, persist_p, _ = self._patched()
        with get_p, persist_p:
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "",
                    "priority_1": "Work",
                },
            )
        assert result.isError is True
        assert result.structuredContent["error"] == "empty_priorities_verbatim"
        assert result.structuredContent["assistant_guidance"]["action"] == "ASK_CLARIFYING"

    @pytest.mark.asyncio
    async def test_allowed_keys_derived_from_schema(self):
        """The allow-list must track the published schema, not a hand-written copy."""
        assert ALLOWED_TOP_LEVEL_KEYS == set(INPUT_SCHEMA["properties"])
        assert ALLOWED_TOP_LEVEL_KEYS == {
            "user_prioritization_criterion_verbatim",
            "user_priorities_verbatim",
            "priorities",
        }

    @pytest.mark.asyncio
    async def test_explicit_empty_list_passes_all_three_guards(self):
        """
        Over-reach guard: `[]` is present AND is a list, so A/B/C must NOT fire.
        It reaches the existing clear-all path and persists, exactly as today.
        """
        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock) as mock_persist:
            mock_get.return_value = BOARD_WITH_P1
            mock_persist.return_value = "cluster-123"
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "clear them all",
                    "priorities": [],
                },
            )

            assert result.isError is None or result.isError is False
            assert "error" not in (result.structuredContent or {})
            clusters = result.structuredContent["clusters"]
            assert clusters[0]["priority"] is None
            mock_get.assert_called_once()
            mock_persist.assert_called_once()


class TestMalformedGuardsDoNotBlockValidCalls:
    """The guards must be invisible to every well-formed invocation."""

    @pytest.mark.asyncio
    async def test_single_priority_still_applies_and_persists(self):
        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock) as mock_persist:
            mock_get.return_value = {
                "cluster_data": {
                    "clusters": [
                        {"cluster_name": "Work", "thought_items": ["task"], "subclusters": []},
                        {"cluster_name": "Home", "thought_items": ["chore"], "subclusters": []},
                    ]
                },
            }
            mock_persist.return_value = "cluster-123"
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "Work is my P1",
                    "priorities": [{"name": "Work", "rank": "P1", "reason": "relief"}],
                },
            )
            assert result.isError is None or result.isError is False
            clusters = result.structuredContent["clusters"]
            assert clusters[0]["priority"]["rank"] == "P1"
            mock_persist.assert_called_once()

    @pytest.mark.asyncio
    async def test_cumulative_two_priorities_still_applies_and_persists(self):
        with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new_callable=AsyncMock) as mock_get, \
             patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new_callable=AsyncMock) as mock_persist:
            mock_get.return_value = {
                "cluster_data": {
                    "clusters": [
                        {"cluster_name": "Work", "thought_items": ["task"], "subclusters": []},
                        {"cluster_name": "Home", "thought_items": ["chore"], "subclusters": []},
                    ]
                },
            }
            mock_persist.return_value = "cluster-123"
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_prioritization_criterion_verbatim": "relief",
                    "user_priorities_verbatim": "Work P1, Home P2",
                    "priorities": [
                        {"name": "Work", "rank": "P1", "reason": "relief"},
                        {"name": "Home", "rank": "P2", "reason": "relief"},
                    ],
                },
            )
            assert result.isError is None or result.isError is False
            clusters = result.structuredContent["clusters"]
            assert clusters[0]["priority"]["rank"] == "P1"
            assert clusters[1]["priority"]["rank"] == "P2"
            mock_persist.assert_called_once()
