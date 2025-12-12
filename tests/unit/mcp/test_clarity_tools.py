"""
Clarity MCP tool unit tests.

Tests for cluster_raw_thoughts tool validation and formatting:
- Flat clusters (thought_items only)
- Nested clusters (subclusters only)
- Mixed clusters (both thought_items and subclusters)
- Empty validation (both empty = invalid)
- Confirmation field handling
- Behavioral tags validation and output
"""

import pytest
from pydantic import ValidationError

from mcp_server.clarity.tools import cluster_raw_thoughts
from mcp_server.clarity.server import (
    ClusterRequest,
    ClusterInput,
    SubclusterInput,
    ALLOWED_TAGS,
)


# =============================================================================
# Test: Pydantic Model Validation
# =============================================================================

class TestClusterInputValidation:
    """Test ClusterInput model validation."""

    def test_valid_flat_cluster(self):
        """Test valid flat cluster with thought_items."""
        cluster = ClusterInput(
            cluster_name="Marketing",
            thought_items=["task 1", "task 2"],
            subclusters=[]
        )
        assert cluster.cluster_name == "Marketing"
        assert len(cluster.thought_items) == 2
        assert len(cluster.subclusters) == 0

    def test_valid_nested_cluster(self):
        """Test valid nested cluster with subclusters."""
        cluster = ClusterInput(
            cluster_name="Engineering",
            thought_items=[],
            subclusters=[
                SubclusterInput(subcluster_name="Frontend", thought_items=["ui task"]),
                SubclusterInput(subcluster_name="Backend", thought_items=["api task"]),
            ]
        )
        assert cluster.cluster_name == "Engineering"
        assert len(cluster.thought_items) == 0
        assert len(cluster.subclusters) == 2

    def test_missing_cluster_name(self):
        """Test missing cluster_name raises ValidationError."""
        with pytest.raises(ValidationError):
            ClusterInput(thought_items=["task 1"])

    def test_default_empty_fields_requires_content(self):
        """Test that cluster with defaults (both empty) raises ValidationError."""
        with pytest.raises(ValidationError):
            ClusterInput(cluster_name="Test")
            # Validation requires at least one of thought_items or subclusters


class TestSubclusterInputValidation:
    """Test SubclusterInput model validation."""

    def test_valid_subcluster(self):
        """Test valid subcluster."""
        subcluster = SubclusterInput(
            subcluster_name="Design",
            thought_items=["wireframe", "mockup"]
        )
        assert subcluster.subcluster_name == "Design"
        assert len(subcluster.thought_items) == 2

    def test_missing_subcluster_name(self):
        """Test missing subcluster_name raises ValidationError."""
        with pytest.raises(ValidationError):
            SubclusterInput(thought_items=["task"])

    def test_missing_thought_items(self):
        """Test missing thought_items raises ValidationError."""
        with pytest.raises(ValidationError):
            SubclusterInput(subcluster_name="Test")

    def test_empty_thought_items_raises_validation_error(self):
        """Test empty thought_items list raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            SubclusterInput(subcluster_name="Empty", thought_items=[])
        assert "no thought_items" in str(exc_info.value).lower()


class TestClusterRequestValidation:
    """Test ClusterRequest top-level validation."""

    def test_valid_request_first_call(self):
        """Test valid request on first call (correctly_clustered: null)."""
        request = ClusterRequest(
            thoughts_exhausted=True,
            correctly_clustered=None,
            clusters=[
                ClusterInput(cluster_name="Tasks", thought_items=["item 1"])
            ]
        )
        assert request.thoughts_exhausted is True
        assert request.correctly_clustered is None
        assert len(request.clusters) == 1

    def test_valid_request_recluster(self):
        """Test valid request on re-cluster (correctly_clustered: false)."""
        request = ClusterRequest(
            thoughts_exhausted=True,
            correctly_clustered=False,
            clusters=[
                ClusterInput(cluster_name="Revised", thought_items=["item"])
            ]
        )
        assert request.correctly_clustered is False

    def test_valid_request_confirmed(self):
        """Test valid request when user confirms clusters are correct."""
        request = ClusterRequest(
            thoughts_exhausted=True,
            correctly_clustered=True,
            clusters=[
                ClusterInput(cluster_name="Confirmed", thought_items=["item"])
            ]
        )
        assert request.correctly_clustered is True

    def test_missing_thoughts_exhausted(self):
        """Test missing thoughts_exhausted raises ValidationError."""
        with pytest.raises(ValidationError):
            ClusterRequest(
                correctly_clustered=None,
                clusters=[ClusterInput(cluster_name="Test", thought_items=["item"])]
            )

    def test_correctly_clustered_optional(self):
        """Test correctly_clustered defaults to None."""
        request = ClusterRequest(
            thoughts_exhausted=True,
            clusters=[ClusterInput(cluster_name="Test", thought_items=["item"])]
        )
        assert request.correctly_clustered is None


# =============================================================================
# Test: Cluster Content Validation (flat, nested, mixed, empty)
# =============================================================================

class TestClusterContentValidation:
    """Test cluster validation: flat, nested, mixed are valid; both empty is invalid."""

    def test_flat_cluster_valid(self):
        """Test flat cluster (thought_items only) is valid."""
        cluster = ClusterInput(
            cluster_name="Flat",
            thought_items=["a", "b", "c"],
            subclusters=[]
        )
        assert cluster.cluster_name == "Flat"
        assert len(cluster.thought_items) == 3
        assert len(cluster.subclusters) == 0

    def test_nested_cluster_valid(self):
        """Test nested cluster (subclusters only) is valid."""
        cluster = ClusterInput(
            cluster_name="Nested",
            thought_items=[],
            subclusters=[
                SubclusterInput(subcluster_name="Sub1", thought_items=["x"])
            ]
        )
        assert cluster.cluster_name == "Nested"
        assert len(cluster.thought_items) == 0
        assert len(cluster.subclusters) == 1

    def test_mixed_cluster_valid(self):
        """Test mixed cluster (both thought_items AND subclusters) is valid."""
        cluster = ClusterInput(
            cluster_name="Mixed",
            thought_items=["ungrouped1", "ungrouped2"],
            subclusters=[
                SubclusterInput(subcluster_name="Grouped", thought_items=["grouped1", "grouped2"])
            ]
        )
        assert cluster.cluster_name == "Mixed"
        assert len(cluster.thought_items) == 2
        assert len(cluster.subclusters) == 1

    def test_both_empty_raises_validation_error(self):
        """Test both thought_items AND subclusters empty raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ClusterInput(
                cluster_name="Empty",
                thought_items=[],
                subclusters=[]
            )
        assert "empty" in str(exc_info.value).lower()


# =============================================================================
# Test: cluster_raw_thoughts Tool Output
# =============================================================================

class TestClusterRawThoughtsOutput:
    """Test cluster_raw_thoughts tool formatting."""

    def test_flat_cluster_output(self):
        """Test output for flat cluster."""
        clusters = [{
            "cluster_name": "Marketing",
            "thought_items": ["campaign", "budget", "timeline"],
            "subclusters": []
        }]

        result = cluster_raw_thoughts(clusters)

        assert "content" in result
        assert "structuredContent" in result
        assert len(result["structuredContent"]["clusters"]) == 1

        cluster = result["structuredContent"]["clusters"][0]
        assert cluster["cluster_name"] == "Marketing"
        assert cluster["sum_thought_items"] == 3
        assert len(cluster["thought_items"]) == 3
        assert len(cluster["subclusters"]) == 0

    def test_nested_cluster_output(self):
        """Test output for nested cluster with subclusters."""
        clusters = [{
            "cluster_name": "Engineering",
            "thought_items": [],
            "subclusters": [
                {"subcluster_name": "Frontend", "thought_items": ["react", "css"]},
                {"subcluster_name": "Backend", "thought_items": ["api", "db", "cache"]}
            ]
        }]

        result = cluster_raw_thoughts(clusters)

        cluster = result["structuredContent"]["clusters"][0]
        assert cluster["cluster_name"] == "Engineering"
        assert cluster["sum_thought_items"] == 5  # 2 + 3
        assert len(cluster["thought_items"]) == 0
        assert len(cluster["subclusters"]) == 2

        # Check subcluster counts
        assert cluster["subclusters"][0]["sum_thought_items"] == 2
        assert cluster["subclusters"][1]["sum_thought_items"] == 3

    def test_multiple_clusters_output(self):
        """Test output with multiple clusters (one flat, one nested)."""
        clusters = [
            {
                "cluster_name": "Simple",
                "thought_items": ["item1", "item2"],
                "subclusters": []
            },
            {
                "cluster_name": "Complex",
                "thought_items": [],
                "subclusters": [
                    {"subcluster_name": "Sub", "thought_items": ["a", "b"]}
                ]
            }
        ]

        result = cluster_raw_thoughts(clusters)

        assert len(result["structuredContent"]["clusters"]) == 2
        assert result["structuredContent"]["clusters"][0]["sum_thought_items"] == 2
        assert result["structuredContent"]["clusters"][1]["sum_thought_items"] == 2

    def test_mixed_cluster_output(self):
        """Test output for mixed cluster (both ungrouped items and subclusters)."""
        clusters = [{
            "cluster_name": "Marketing",
            "thought_items": ["Review Q1 budget", "Call agency"],
            "subclusters": [
                {"subcluster_name": "Social Media", "thought_items": ["Post schedule", "Analytics"]},
                {"subcluster_name": "Events", "thought_items": ["Conference booth"]}
            ]
        }]

        result = cluster_raw_thoughts(clusters)

        cluster = result["structuredContent"]["clusters"][0]
        assert cluster["cluster_name"] == "Marketing"
        # sum = 2 ungrouped + 2 + 1 = 5
        assert cluster["sum_thought_items"] == 5
        # Ungrouped items preserved
        assert len(cluster["thought_items"]) == 2
        assert cluster["thought_items"] == ["Review Q1 budget", "Call agency"]
        # Subclusters preserved
        assert len(cluster["subclusters"]) == 2
        assert cluster["subclusters"][0]["sum_thought_items"] == 2
        assert cluster["subclusters"][1]["sum_thought_items"] == 1

    def test_empty_clusters_list(self):
        """Test output with empty clusters list."""
        result = cluster_raw_thoughts([])

        assert result["structuredContent"]["clusters"] == []
        assert "content" in result

    def test_content_message(self):
        """Test content message is present."""
        clusters = [{"cluster_name": "Test", "thought_items": ["x"], "subclusters": []}]
        result = cluster_raw_thoughts(clusters)

        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        assert "organized" in result["content"][0]["text"].lower()


# =============================================================================
# Test: Behavioral Tags Validation
# =============================================================================

class TestTagValidation:
    """Test behavioral tags validation on clusters and subclusters."""

    def test_no_tags_valid(self):
        """Test cluster with no tags is valid."""
        cluster = ClusterInput(
            cluster_name="NoTags",
            thought_items=["item"],
            tags=[]
        )
        assert cluster.tags == []

    def test_single_tag_valid(self):
        """Test cluster with single valid tag is valid."""
        cluster = ClusterInput(
            cluster_name="SingleTag",
            thought_items=["item"],
            tags=["decide"]
        )
        assert cluster.tags == ["decide"]

    def test_max_tags_valid(self):
        """Test cluster with max 3 tags is valid."""
        cluster = ClusterInput(
            cluster_name="MaxTags",
            thought_items=["item"],
            tags=["decide", "learn", "align"]
        )
        assert len(cluster.tags) == 3

    def test_too_many_tags_raises_validation_error(self):
        """Test cluster with >3 tags raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ClusterInput(
                cluster_name="TooMany",
                thought_items=["item"],
                tags=["decide", "learn", "align", "research"]
            )
        assert "maximum is 3" in str(exc_info.value).lower()

    def test_invalid_tag_raises_validation_error(self):
        """Test cluster with invalid tag raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ClusterInput(
                cluster_name="Invalid",
                thought_items=["item"],
                tags=["urgent"]
            )
        assert "invalid tag" in str(exc_info.value).lower()

    def test_subcluster_tags_valid(self):
        """Test subcluster with valid tags is valid."""
        subcluster = SubclusterInput(
            subcluster_name="Tagged",
            thought_items=["item"],
            tags=["delegate", "unblock"]
        )
        assert subcluster.tags == ["delegate", "unblock"]

    def test_subcluster_too_many_tags_raises_validation_error(self):
        """Test subcluster with >3 tags raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            SubclusterInput(
                subcluster_name="TooMany",
                thought_items=["item"],
                tags=["decide", "learn", "align", "research"]
            )
        assert "maximum is 3" in str(exc_info.value).lower()

    def test_subcluster_invalid_tag_raises_validation_error(self):
        """Test subcluster with invalid tag raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            SubclusterInput(
                subcluster_name="Invalid",
                thought_items=["item"],
                tags=["priority"]
            )
        assert "invalid tag" in str(exc_info.value).lower()

    def test_allowed_tags_constant(self):
        """Test ALLOWED_TAGS contains expected values."""
        assert "decide" in ALLOWED_TAGS
        assert "experiment" in ALLOWED_TAGS
        assert "research" in ALLOWED_TAGS
        assert "validate" in ALLOWED_TAGS
        assert "unblock" in ALLOWED_TAGS
        assert "delegate" in ALLOWED_TAGS
        assert "automate" in ALLOWED_TAGS
        assert "learn" in ALLOWED_TAGS
        assert "align" in ALLOWED_TAGS
        assert len(ALLOWED_TAGS) == 9


# =============================================================================
# Test: Tags in Tool Output
# =============================================================================

class TestTagsOutput:
    """Test tags are passed through in cluster_raw_thoughts output."""

    def test_cluster_tags_in_output(self):
        """Test cluster tags appear in output."""
        clusters = [{
            "cluster_name": "Tagged",
            "thought_items": ["item"],
            "subclusters": [],
            "tags": ["decide", "delegate"]
        }]

        result = cluster_raw_thoughts(clusters)
        cluster = result["structuredContent"]["clusters"][0]

        assert "tags" in cluster
        assert cluster["tags"] == ["decide", "delegate"]

    def test_subcluster_tags_in_output(self):
        """Test subcluster tags appear in output."""
        clusters = [{
            "cluster_name": "Parent",
            "thought_items": [],
            "subclusters": [
                {
                    "subcluster_name": "Child",
                    "thought_items": ["item"],
                    "tags": ["research", "learn"]
                }
            ],
            "tags": []
        }]

        result = cluster_raw_thoughts(clusters)
        subcluster = result["structuredContent"]["clusters"][0]["subclusters"][0]

        assert "tags" in subcluster
        assert subcluster["tags"] == ["research", "learn"]

    def test_empty_tags_in_output(self):
        """Test empty tags array appears in output."""
        clusters = [{
            "cluster_name": "NoTags",
            "thought_items": ["item"],
            "subclusters": [],
            "tags": []
        }]

        result = cluster_raw_thoughts(clusters)
        cluster = result["structuredContent"]["clusters"][0]

        assert "tags" in cluster
        assert cluster["tags"] == []

    def test_missing_tags_defaults_to_empty(self):
        """Test missing tags field defaults to empty array."""
        clusters = [{
            "cluster_name": "NoTagsField",
            "thought_items": ["item"],
            "subclusters": []
            # No tags field
        }]

        result = cluster_raw_thoughts(clusters)
        cluster = result["structuredContent"]["clusters"][0]

        assert "tags" in cluster
        assert cluster["tags"] == []
