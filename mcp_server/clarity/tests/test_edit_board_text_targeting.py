"""
Unit tests for text-based thought item targeting in edit_board.

Tests _find_thought_item_by_text helper and text targeting in
set_priority, clear_priority, delete_thought_item operations.
"""

import pytest
import copy

from mcp_server.clarity.tools.edit_board import (
    _find_thought_item_by_text,
    _op_set_priority,
    _op_clear_priority,
    _op_delete_thought_item,
    ERROR_ITEM_TEXT_NOT_FOUND,
    ERROR_ITEM_TEXT_AMBIGUOUS,
)


# ============================================================================
# Test fixtures
# ============================================================================

@pytest.fixture
def sample_clusters():
    """Board with clusters, subclusters, and thought items."""
    return [
        {
            "cluster_name": "Work Projects",
            "thought_items": [
                "Follow Up On Payments",
                "Review Q3 report",
                {"text": "Send invoice", "priority": None},
            ],
            "subclusters": [
                {
                    "subcluster_name": "Urgent Tasks",
                    "thought_items": [
                        "Call vendor",
                        "Submit timesheet",
                    ],
                }
            ],
        },
        {
            "cluster_name": "Personal",
            "thought_items": [
                "Book dentist",
                "Call vendor",  # Same text as in Urgent Tasks subcluster
            ],
            "subclusters": [],
        },
    ]


@pytest.fixture
def clusters_with_priority():
    """Board with a thought item that has a priority set."""
    return [
        {
            "cluster_name": "Work Projects",
            "thought_items": [
                {"text": "Follow up on payments", "priority": {"rank": "P1"}},
                "Review Q3 report",
            ],
            "subclusters": [],
        },
    ]


# ============================================================================
# _find_thought_item_by_text tests
# ============================================================================

def test_find_item_in_cluster(sample_clusters):
    """Item in cluster thought_items returns correct (index, cluster_name, None)."""
    index, parent, error = _find_thought_item_by_text(
        sample_clusters, "Review Q3 report"
    )
    assert error is None
    assert index == 1
    assert parent == "Work Projects"


def test_find_item_in_subcluster(sample_clusters):
    """Item in subcluster thought_items returns correct (index, subcluster_name, None)."""
    index, parent, error = _find_thought_item_by_text(
        sample_clusters, "Submit timesheet"
    )
    assert error is None
    assert index == 1
    assert parent == "Urgent Tasks"


def test_find_item_case_insensitive(sample_clusters):
    """Stored 'Follow Up On Payments' matches query 'follow up on payments'."""
    index, parent, error = _find_thought_item_by_text(
        sample_clusters, "follow up on payments"
    )
    assert error is None
    assert index == 0
    assert parent == "Work Projects"


def test_find_item_whitespace_tolerant(sample_clusters):
    """Whitespace is stripped before matching."""
    # Add item with extra whitespace
    sample_clusters[0]["thought_items"].append("  Whitespace item  ")

    index, parent, error = _find_thought_item_by_text(
        sample_clusters, "Whitespace item"
    )
    assert error is None
    assert index == 3
    assert parent == "Work Projects"


def test_find_item_object_format(sample_clusters):
    """Item stored as {"text": "Send invoice", ...} matches on text field."""
    index, parent, error = _find_thought_item_by_text(
        sample_clusters, "send invoice"
    )
    assert error is None
    assert index == 2
    assert parent == "Work Projects"


def test_find_item_not_found(sample_clusters):
    """Text not on board returns (None, None, error string containing the text)."""
    index, parent, error = _find_thought_item_by_text(
        sample_clusters, "nonexistent item"
    )
    assert index is None
    assert parent is None
    assert "nonexistent item" in error


def test_find_item_ambiguous_no_parent(sample_clusters):
    """Same text in two containers, no parent_name returns disambiguation error."""
    # "Call vendor" exists in both "Urgent Tasks" subcluster and "Personal" cluster
    index, parent, error = _find_thought_item_by_text(
        sample_clusters, "Call vendor"
    )
    assert index is None
    assert parent is None
    assert "Urgent Tasks" in error
    assert "Personal" in error


def test_find_item_ambiguous_with_parent(sample_clusters):
    """Same text in two containers, parent_name matches one returns correct result."""
    index, parent, error = _find_thought_item_by_text(
        sample_clusters, "Call vendor", parent_name="Urgent Tasks"
    )
    assert error is None
    assert index == 0
    assert parent == "Urgent Tasks"


def test_find_item_parent_not_found_falls_through(sample_clusters):
    """parent_name doesn't exist on board, falls through to board-wide search."""
    # "Review Q3 report" exists only in "Work Projects"
    # Provide non-existent parent_name - should fall through and find it
    index, parent, error = _find_thought_item_by_text(
        sample_clusters, "Review Q3 report", parent_name="Nonexistent Cluster"
    )
    assert error is None
    assert index == 1
    assert parent == "Work Projects"


# ============================================================================
# _op_set_priority with text targeting tests
# ============================================================================

def test_set_priority_by_text_success(sample_clusters):
    """text provided, no item_index resolves and sets priority correctly."""
    clusters = copy.deepcopy(sample_clusters)
    result, error = _op_set_priority(
        clusters,
        target_name=None,
        parent_name=None,
        item_index=None,
        rank="P2",
        text="Review Q3 report"
    )
    assert error is None
    assert result is not None
    # Check the item got priority set
    item = result[0]["thought_items"][1]
    assert isinstance(item, dict)
    assert item["priority"]["rank"] == "P2"


def test_set_priority_item_index_wins(sample_clusters):
    """Both text and item_index provided, item_index is used."""
    clusters = copy.deepcopy(sample_clusters)
    # item_index=0 targets "Follow Up On Payments", text would target something else
    result, error = _op_set_priority(
        clusters,
        target_name=None,
        parent_name="Work Projects",
        item_index=0,
        rank="P1",
        text="Review Q3 report"  # This should be ignored
    )
    assert error is None
    # Item at index 0 should have priority, not "Review Q3 report"
    item = result[0]["thought_items"][0]
    assert isinstance(item, dict)
    assert item["priority"]["rank"] == "P1"


def test_set_priority_cluster_target_unchanged(sample_clusters):
    """target_name provided (cluster), existing path works, text ignored."""
    clusters = copy.deepcopy(sample_clusters)
    result, error = _op_set_priority(
        clusters,
        target_name="Work Projects",
        parent_name=None,
        item_index=None,
        rank="P1",
        text="Review Q3 report"  # Should be ignored when target_name is set
    )
    assert error is None
    # Cluster should have priority set (not the thought item from text)
    cluster = result[0]
    assert cluster.get("priority") is not None
    assert cluster["priority"]["rank"] == "P1"
    # Verify "Review Q3 report" item was NOT targeted (text was ignored)
    item = result[0]["thought_items"][1]
    if isinstance(item, dict):
        assert item.get("priority") is None or item["priority"].get("rank") != "P1"
    # If item is still a string, it wasn't targeted (correct behavior)


def test_set_priority_text_not_found(sample_clusters):
    """text not on board returns error, board unchanged."""
    clusters = copy.deepcopy(sample_clusters)
    result, error = _op_set_priority(
        clusters,
        target_name=None,
        parent_name=None,
        item_index=None,
        rank="P2",
        text="nonexistent item"
    )
    assert result is None
    assert "nonexistent item" in error


# ============================================================================
# _op_clear_priority with text targeting tests
# ============================================================================

def test_clear_priority_by_text_success(clusters_with_priority):
    """text provided resolves and clears priority correctly."""
    clusters = copy.deepcopy(clusters_with_priority)
    result, error = _op_clear_priority(
        clusters,
        target_name=None,
        parent_name=None,
        item_index=None,
        text="follow up on payments"
    )
    assert error is None
    item = result[0]["thought_items"][0]
    assert item["priority"] is None


def test_clear_priority_item_index_wins(clusters_with_priority):
    """Both text and item_index provided, item_index is used."""
    clusters = copy.deepcopy(clusters_with_priority)
    result, error = _op_clear_priority(
        clusters,
        target_name=None,
        parent_name="Work Projects",
        item_index=0,
        text="Review Q3 report"  # Should be ignored
    )
    assert error is None
    # Item at index 0 should have priority cleared
    item = result[0]["thought_items"][0]
    assert item["priority"] is None


# ============================================================================
# _op_delete_thought_item with text targeting tests
# ============================================================================

def test_delete_thought_item_by_text_success(sample_clusters):
    """text provided, item found and deleted."""
    clusters = copy.deepcopy(sample_clusters)
    original_count = len(clusters[0]["thought_items"])

    result, error = _op_delete_thought_item(
        clusters,
        parent_name=None,
        item_index=None,
        text="Review Q3 report"
    )
    assert error is None
    assert len(result[0]["thought_items"]) == original_count - 1
    # Verify the item is gone
    texts = [
        item if isinstance(item, str) else item.get("text", "")
        for item in result[0]["thought_items"]
    ]
    assert "Review Q3 report" not in texts


def test_delete_thought_item_text_not_found(sample_clusters):
    """text not on board returns error, board unchanged."""
    clusters = copy.deepcopy(sample_clusters)
    result, error = _op_delete_thought_item(
        clusters,
        parent_name=None,
        item_index=None,
        text="nonexistent item"
    )
    assert result is None
    assert "nonexistent item" in error


def test_delete_thought_item_item_index_wins(sample_clusters):
    """Both text and item_index provided, item_index is used."""
    clusters = copy.deepcopy(sample_clusters)

    # Delete item at index 0 ("Follow Up On Payments")
    # text points to a different item
    result, error = _op_delete_thought_item(
        clusters,
        parent_name="Work Projects",
        item_index=0,
        text="Review Q3 report"  # Should be ignored
    )
    assert error is None
    # "Follow Up On Payments" (index 0) should be deleted, not "Review Q3 report"
    texts = [
        item if isinstance(item, str) else item.get("text", "")
        for item in result[0]["thought_items"]
    ]
    assert "Follow Up On Payments" not in texts
    assert "Review Q3 report" in texts


# ============================================================================
# Integration test (requires DB) - placeholder
# ============================================================================

@pytest.mark.skip(reason="Requires DB setup - run separately in integration tests")
async def test_edit_board_set_priority_by_text_e2e():
    """
    Integration test:
    1. Seed DB with a board containing a known thought item
    2. Call handle() with set_priority + text="<known item text>" + rank="P2"
    3. Assert response is not isError
    4. Assert persisted board has priority set on the correct item
    5. Assert other items unchanged
    """
    pass
