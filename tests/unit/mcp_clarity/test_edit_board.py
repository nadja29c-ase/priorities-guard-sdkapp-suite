"""
Unit tests for edit_board tool.

Tests:
1. set_priority operations
2. clear_priority operations
3. rename operations
4. delete operations
5. clear_all_priorities
6. add_thought_item operations
7. add_tag operations
8. remove_tag operations
9. Error handling
"""

import pytest
from mcp_server.clarity.tools.edit_board import (
    handle,
    _op_set_priority,
    _op_clear_priority,
    _op_rename_cluster,
    _op_rename_subcluster,
    _op_delete_cluster,
    _op_delete_subcluster,
    _op_delete_thought_item,
    _op_clear_all_priorities,
    _op_add_thought_item,
    _op_add_tag,
    _op_remove_tag,
    ERROR_NO_BOARD,
    ERROR_INVALID_OPERATION,
    ERROR_MISSING_TARGET,
    ERROR_CLUSTER_NOT_FOUND,
    ERROR_SUBCLUSTER_NOT_FOUND,
    ERROR_ITEM_NOT_FOUND,
    ERROR_MISSING_NEW_NAME,
    ERROR_MISSING_RANK,
    ERROR_MISSING_TEXT,
    ERROR_MISSING_TAG,
    ERROR_INVALID_TAG,
    ERROR_TAG_LIMIT,
    ERROR_TAG_NOT_FOUND,
    ERROR_AMBIGUOUS_NAME,
    ERROR_TEXT_TOO_LONG,
)


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
# Set Priority Tests
# ============================================================================


class TestSetPriority:
    """Tests for set_priority operation."""

    def test_set_priority_on_cluster(self):
        """Basic priority assignment on cluster."""
        clusters = [make_cluster("Work", items=["task"])]
        result, error = _op_set_priority(clusters, "Work", None, None, "P1")

        assert error is None
        assert result[0]["priority"]["rank"] == "P1"

    def test_set_priority_on_subcluster(self):
        """Priority assignment on subcluster."""
        clusters = [make_cluster("Work", subclusters=[
            make_subcluster("Urgent", items=["task"])
        ])]
        result, error = _op_set_priority(clusters, "Urgent", None, None, "P2")

        assert error is None
        assert result[0]["subclusters"][0]["priority"]["rank"] == "P2"

    def test_set_priority_on_thought_item(self):
        """Priority assignment on thought item."""
        clusters = [make_cluster("Work", items=["task1", "task2"])]
        result, error = _op_set_priority(clusters, None, "Work", 0, "P1")

        assert error is None
        assert result[0]["thought_items"][0]["priority"]["rank"] == "P1"

    def test_set_priority_preserves_existing(self):
        """Add P3, P1/P2 should remain intact."""
        clusters = [
            make_cluster("Work", priority={"rank": "P1", "reason": None}),
            make_cluster("Home", priority={"rank": "P2", "reason": None}),
            make_cluster("Health"),
        ]
        result, error = _op_set_priority(clusters, "Health", None, None, "P3")

        assert error is None
        assert result[0]["priority"]["rank"] == "P1"
        assert result[1]["priority"]["rank"] == "P2"
        assert result[2]["priority"]["rank"] == "P3"

    def test_set_priority_global_uniqueness(self):
        """Moving P1 clears old holder."""
        clusters = [
            make_cluster("Work", priority={"rank": "P1", "reason": None}),
            make_cluster("Home"),
        ]
        result, error = _op_set_priority(clusters, "Home", None, None, "P1")

        assert error is None
        # Work's P1 should be cleared
        assert result[0]["priority"] is None
        # Home gets P1
        assert result[1]["priority"]["rank"] == "P1"

    def test_set_priority_missing_rank(self):
        """Error when rank not provided."""
        clusters = [make_cluster("Work")]
        result, error = _op_set_priority(clusters, "Work", None, None, None)

        assert result is None
        assert ERROR_MISSING_RANK in error

    def test_set_priority_cluster_not_found(self):
        """Error when cluster not found."""
        clusters = [make_cluster("Work")]
        result, error = _op_set_priority(clusters, "NotExist", None, None, "P1")

        assert result is None
        assert "not found" in error.lower()

    def test_set_priority_item_out_of_bounds(self):
        """Error when item_index is out of bounds."""
        clusters = [make_cluster("Work", items=["task"])]
        result, error = _op_set_priority(clusters, None, "Work", 5, "P1")

        assert result is None
        assert "not found" in error.lower()


# ============================================================================
# Clear Priority Tests
# ============================================================================


class TestClearPriority:
    """Tests for clear_priority operation."""

    def test_clear_priority_from_cluster(self):
        """Removes priority from cluster."""
        clusters = [make_cluster("Work", priority={"rank": "P1", "reason": None})]
        result, error = _op_clear_priority(clusters, "Work", None, None)

        assert error is None
        assert result[0]["priority"] is None

    def test_clear_priority_from_subcluster(self):
        """Removes priority from subcluster."""
        clusters = [make_cluster("Work", subclusters=[
            make_subcluster("Urgent", priority={"rank": "P1", "reason": None})
        ])]
        result, error = _op_clear_priority(clusters, "Urgent", None, None)

        assert error is None
        assert result[0]["subclusters"][0]["priority"] is None

    def test_clear_priority_from_thought_item(self):
        """Removes priority from thought item."""
        clusters = [make_cluster("Work", items=[
            {"text": "task", "priority": {"rank": "P1", "reason": None}}
        ])]
        result, error = _op_clear_priority(clusters, None, "Work", 0)

        assert error is None
        assert result[0]["thought_items"][0]["priority"] is None

    def test_clear_priority_cluster_not_found(self):
        """Error when cluster not found."""
        clusters = [make_cluster("Work")]
        result, error = _op_clear_priority(clusters, "NotExist", None, None)

        assert result is None
        assert "not found" in error.lower()


# ============================================================================
# Rename Tests
# ============================================================================


class TestRenameCluster:
    """Tests for rename_cluster operation."""

    def test_rename_cluster(self):
        """Name changes, content intact."""
        clusters = [make_cluster("Work", items=["task1", "task2"])]
        result, error = _op_rename_cluster(clusters, "Work", "Office")

        assert error is None
        assert result[0]["cluster_name"] == "Office"
        assert result[0]["thought_items"] == ["task1", "task2"]

    def test_rename_cluster_not_found(self):
        """Error when cluster not found."""
        clusters = [make_cluster("Work")]
        result, error = _op_rename_cluster(clusters, "NotExist", "New")

        assert result is None
        assert "not found" in error.lower()

    def test_rename_cluster_missing_new_name(self):
        """Error when new_name not provided."""
        clusters = [make_cluster("Work")]
        result, error = _op_rename_cluster(clusters, "Work", None)

        assert result is None
        assert ERROR_MISSING_NEW_NAME in error


class TestRenameSubcluster:
    """Tests for rename_subcluster operation."""

    def test_rename_subcluster(self):
        """Name changes within parent."""
        clusters = [make_cluster("Work", subclusters=[
            make_subcluster("Urgent", items=["task"])
        ])]
        result, error = _op_rename_subcluster(clusters, "Urgent", "Work", "Critical")

        assert error is None
        assert result[0]["subclusters"][0]["subcluster_name"] == "Critical"
        assert result[0]["subclusters"][0]["thought_items"] == ["task"]

    def test_rename_subcluster_not_found(self):
        """Error when subcluster not found."""
        clusters = [make_cluster("Work", subclusters=[make_subcluster("Urgent")])]
        result, error = _op_rename_subcluster(clusters, "NotExist", "Work", "New")

        assert result is None
        assert "not found" in error.lower()


# ============================================================================
# Delete Tests
# ============================================================================


class TestDeleteCluster:
    """Tests for delete_cluster operation."""

    def test_delete_cluster(self):
        """Cluster removed from board."""
        clusters = [
            make_cluster("Work", items=["task"]),
            make_cluster("Home", items=["chore"]),
        ]
        result, error = _op_delete_cluster(clusters, "Work")

        assert error is None
        assert len(result) == 1
        assert result[0]["cluster_name"] == "Home"

    def test_delete_cluster_not_found(self):
        """Error when cluster not found."""
        clusters = [make_cluster("Work")]
        result, error = _op_delete_cluster(clusters, "NotExist")

        assert result is None
        assert "not found" in error.lower()


class TestDeleteSubcluster:
    """Tests for delete_subcluster operation."""

    def test_delete_subcluster(self):
        """Subcluster removed, cluster intact."""
        clusters = [make_cluster("Work", subclusters=[
            make_subcluster("Urgent", items=["task1"]),
            make_subcluster("Later", items=["task2"]),
        ])]
        result, error = _op_delete_subcluster(clusters, "Urgent", "Work")

        assert error is None
        assert len(result[0]["subclusters"]) == 1
        assert result[0]["subclusters"][0]["subcluster_name"] == "Later"

    def test_delete_subcluster_not_found(self):
        """Error when subcluster not found."""
        clusters = [make_cluster("Work", subclusters=[make_subcluster("Urgent")])]
        result, error = _op_delete_subcluster(clusters, "NotExist", "Work")

        assert result is None
        assert "not found" in error.lower()


class TestDeleteThoughtItem:
    """Tests for delete_thought_item operation."""

    def test_delete_thought_item(self):
        """Item removed, others intact."""
        clusters = [make_cluster("Work", items=["task1", "task2", "task3"])]
        result, error = _op_delete_thought_item(clusters, "Work", 1)

        assert error is None
        assert len(result[0]["thought_items"]) == 2
        assert result[0]["thought_items"] == ["task1", "task3"]

    def test_delete_thought_item_out_of_bounds(self):
        """Error when item_index is out of bounds."""
        clusters = [make_cluster("Work", items=["task"])]
        result, error = _op_delete_thought_item(clusters, "Work", 5)

        assert result is None
        assert "not found" in error.lower()

    def test_delete_thought_item_parent_not_found(self):
        """Error when parent not found."""
        clusters = [make_cluster("Work", items=["task"])]
        result, error = _op_delete_thought_item(clusters, "NotExist", 0)

        assert result is None
        assert "not found" in error.lower()


# ============================================================================
# Clear All Priorities Tests
# ============================================================================


class TestClearAllPriorities:
    """Tests for clear_all_priorities operation."""

    def test_clear_all_priorities(self):
        """All priorities removed."""
        clusters = [
            make_cluster("Work", priority={"rank": "P1", "reason": None}, items=[
                {"text": "task", "priority": {"rank": "P3", "reason": None}}
            ]),
            make_cluster("Home", priority={"rank": "P2", "reason": None}),
        ]
        result, error = _op_clear_all_priorities(clusters)

        assert error is None
        assert result[0]["priority"] is None
        assert result[0]["thought_items"][0]["priority"] is None
        assert result[1]["priority"] is None


# ============================================================================
# Handler Tests
# ============================================================================


class TestHandler:
    """Tests for the main handler function."""

    @pytest.mark.asyncio
    async def test_set_priority_via_handler(self):
        """Handler correctly routes set_priority."""
        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "board": [
                    {"cluster_name": "Work", "thought_items": ["task"]}
                ],
                "operation": "set_priority",
                "target_name": "Work",
                "rank": "P1",
            },
        )

        assert result.isError is None or result.isError is False
        assert result.structuredContent["clusters"][0]["priority"]["rank"] == "P1"

    @pytest.mark.asyncio
    async def test_invalid_operation(self):
        """Returns error for invalid operation."""
        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "board": [{"cluster_name": "Work"}],
                "operation": "invalid_op",
            },
        )

        assert result.isError is True
        assert ERROR_INVALID_OPERATION in result.content[0].text

    @pytest.mark.asyncio
    async def test_no_board_provided(self):
        """Returns error when board is empty."""
        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "board": [],
                "operation": "set_priority",
                "target_name": "Work",
                "rank": "P1",
            },
        )

        assert result.isError is True
        assert ERROR_NO_BOARD in result.content[0].text

    @pytest.mark.asyncio
    async def test_cluster_not_found_via_handler(self):
        """Returns error when cluster not found."""
        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "board": [{"cluster_name": "Work"}],
                "operation": "set_priority",
                "target_name": "NotExist",
                "rank": "P1",
            },
        )

        assert result.isError is True
        assert "not found" in result.content[0].text.lower()

    @pytest.mark.asyncio
    async def test_delete_cluster_via_handler(self):
        """Handler correctly routes delete_cluster."""
        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "board": [
                    {"cluster_name": "Work", "thought_items": ["task"]},
                    {"cluster_name": "Home", "thought_items": ["chore"]},
                ],
                "operation": "delete_cluster",
                "target_name": "Work",
            },
        )

        assert result.isError is None or result.isError is False
        clusters = result.structuredContent["clusters"]
        assert len(clusters) == 1
        assert clusters[0]["cluster_name"] == "Home"

    @pytest.mark.asyncio
    async def test_clear_all_priorities_via_handler(self):
        """Handler correctly routes clear_all_priorities."""
        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "board": [
                    {"cluster_name": "Work", "priority": {"rank": "P1"}},
                    {"cluster_name": "Home", "priority": {"rank": "P2"}},
                ],
                "operation": "clear_all_priorities",
            },
        )

        assert result.isError is None or result.isError is False
        clusters = result.structuredContent["clusters"]
        assert clusters[0]["priority"] is None
        assert clusters[1]["priority"] is None

    @pytest.mark.asyncio
    async def test_preserves_existing_priorities(self):
        """Adding new priority preserves existing ones."""
        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "board": [
                    {"cluster_name": "Work", "priority": {"rank": "P1", "reason": None}},
                    {"cluster_name": "Home", "priority": {"rank": "P2", "reason": None}},
                    {"cluster_name": "Health"},
                ],
                "operation": "set_priority",
                "target_name": "Health",
                "rank": "P3",
            },
        )

        assert result.isError is None or result.isError is False
        clusters = result.structuredContent["clusters"]
        assert clusters[0]["priority"]["rank"] == "P1"
        assert clusters[1]["priority"]["rank"] == "P2"
        assert clusters[2]["priority"]["rank"] == "P3"


# ============================================================================
# Add Thought Item Tests
# ============================================================================


class TestAddThoughtItem:
    """Tests for add_thought_item operation."""

    def test_add_thought_item_to_cluster(self):
        """Adds item to cluster's thought_items."""
        clusters = [make_cluster("Work", items=["task1"])]
        result, error = _op_add_thought_item(clusters, "Work", "new task")

        assert error is None
        assert len(result[0]["thought_items"]) == 2
        assert result[0]["thought_items"][1] == "new task"

    def test_add_thought_item_to_subcluster(self):
        """Adds item to subcluster's thought_items."""
        clusters = [make_cluster("Work", subclusters=[
            make_subcluster("Urgent", items=["task1"])
        ])]
        result, error = _op_add_thought_item(clusters, "Urgent", "new task")

        assert error is None
        assert len(result[0]["subclusters"][0]["thought_items"]) == 2
        assert result[0]["subclusters"][0]["thought_items"][1] == "new task"

    def test_add_thought_item_missing_parent(self):
        """Rejects missing parent_name."""
        clusters = [make_cluster("Work")]
        result, error = _op_add_thought_item(clusters, None, "new task")

        assert result is None
        assert "not found" in error.lower()

    def test_add_thought_item_missing_text(self):
        """Rejects missing text."""
        clusters = [make_cluster("Work")]
        result, error = _op_add_thought_item(clusters, "Work", None)

        assert result is None
        assert ERROR_MISSING_TEXT in error

    def test_add_thought_item_parent_not_found(self):
        """Rejects invalid parent_name."""
        clusters = [make_cluster("Work")]
        result, error = _op_add_thought_item(clusters, "NotExist", "new task")

        assert result is None
        assert "not found" in error.lower()

    def test_add_thought_item_text_too_long(self):
        """Rejects text > 500 chars."""
        clusters = [make_cluster("Work")]
        long_text = "x" * 501
        result, error = _op_add_thought_item(clusters, "Work", long_text)

        assert result is None
        assert "500" in error

    def test_add_thought_item_ambiguous_parent(self):
        """Rejects if parent name is both cluster and subcluster."""
        # Create a cluster with a subcluster that has the same name
        clusters = [
            make_cluster("Shared", items=["item1"]),
            make_cluster("Work", subclusters=[
                make_subcluster("Shared", items=["item2"])
            ])
        ]
        result, error = _op_add_thought_item(clusters, "Shared", "new task")

        assert result is None
        assert ERROR_AMBIGUOUS_NAME.format(name="Shared") == error


# ============================================================================
# Add Tag Tests
# ============================================================================


class TestAddTag:
    """Tests for add_tag operation."""

    def test_add_tag_to_cluster(self):
        """Adds valid tag to cluster."""
        clusters = [make_cluster("Work")]
        result, error = _op_add_tag(clusters, "Work", "research")

        assert error is None
        assert "research" in result[0]["tags"]

    def test_add_tag_to_subcluster(self):
        """Adds valid tag to subcluster."""
        clusters = [make_cluster("Work", subclusters=[make_subcluster("Urgent")])]
        result, error = _op_add_tag(clusters, "Urgent", "decide")

        assert error is None
        assert "decide" in result[0]["subclusters"][0]["tags"]

    def test_add_tag_invalid_value(self):
        """Rejects invalid tag value."""
        clusters = [make_cluster("Work")]
        result, error = _op_add_tag(clusters, "Work", "invalid_tag")

        assert result is None
        assert ERROR_INVALID_TAG in error

    def test_add_tag_at_limit(self):
        """Rejects when already at 3 tags."""
        clusters = [{
            "cluster_name": "Work",
            "thought_items": [],
            "subclusters": [],
            "tags": ["decide", "research", "test"],
            "priority": None,
        }]
        result, error = _op_add_tag(clusters, "Work", "delegate")

        assert result is None
        assert "3 tags" in error

    def test_add_tag_duplicate_silent(self):
        """Succeeds silently if tag already present."""
        clusters = [{
            "cluster_name": "Work",
            "thought_items": [],
            "subclusters": [],
            "tags": ["research"],
            "priority": None,
        }]
        result, error = _op_add_tag(clusters, "Work", "research")

        assert error is None
        assert result[0]["tags"] == ["research"]  # No duplicate added

    def test_add_tag_ambiguous_target(self):
        """Rejects if target name is both cluster and subcluster."""
        clusters = [
            make_cluster("Shared"),
            make_cluster("Work", subclusters=[make_subcluster("Shared")])
        ]
        result, error = _op_add_tag(clusters, "Shared", "research")

        assert result is None
        assert ERROR_AMBIGUOUS_NAME.format(name="Shared") == error


# ============================================================================
# Remove Tag Tests
# ============================================================================


class TestRemoveTag:
    """Tests for remove_tag operation."""

    def test_remove_tag_from_cluster(self):
        """Removes existing tag from cluster."""
        clusters = [{
            "cluster_name": "Work",
            "thought_items": [],
            "subclusters": [],
            "tags": ["research", "decide"],
            "priority": None,
        }]
        result, error = _op_remove_tag(clusters, "Work", "research")

        assert error is None
        assert "research" not in result[0]["tags"]
        assert "decide" in result[0]["tags"]

    def test_remove_tag_from_subcluster(self):
        """Removes existing tag from subcluster."""
        clusters = [{
            "cluster_name": "Work",
            "thought_items": [],
            "subclusters": [{
                "subcluster_name": "Urgent",
                "thought_items": [],
                "tags": ["research", "decide"],
                "priority": None,
            }],
            "tags": [],
            "priority": None,
        }]
        result, error = _op_remove_tag(clusters, "Urgent", "research")

        assert error is None
        assert "research" not in result[0]["subclusters"][0]["tags"]
        assert "decide" in result[0]["subclusters"][0]["tags"]

    def test_remove_tag_not_found(self):
        """Rejects if tag not present."""
        clusters = [{
            "cluster_name": "Work",
            "thought_items": [],
            "subclusters": [],
            "tags": ["research"],
            "priority": None,
        }]
        result, error = _op_remove_tag(clusters, "Work", "decide")

        assert result is None
        assert ERROR_TAG_NOT_FOUND.format(tag="decide", name="Work") == error

    def test_remove_tag_ambiguous_target(self):
        """Rejects if target name is both cluster and subcluster."""
        clusters = [
            {
                "cluster_name": "Shared",
                "thought_items": [],
                "subclusters": [],
                "tags": ["research"],
                "priority": None,
            },
            {
                "cluster_name": "Work",
                "thought_items": [],
                "subclusters": [{
                    "subcluster_name": "Shared",
                    "thought_items": [],
                    "tags": ["decide"],
                    "priority": None,
                }],
                "tags": [],
                "priority": None,
            }
        ]
        result, error = _op_remove_tag(clusters, "Shared", "research")

        assert result is None
        assert ERROR_AMBIGUOUS_NAME.format(name="Shared") == error
