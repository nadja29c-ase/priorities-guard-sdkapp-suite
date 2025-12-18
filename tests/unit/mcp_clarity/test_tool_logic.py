"""
Clarity MCP tool unit tests.

Tests for organize_thoughts tool validation and formatting:
- Flat clusters (thought_items only)
- Nested clusters (subclusters only)
- Mixed clusters (both thought_items and subclusters)
- Empty validation (both empty = invalid)
- Confirmation field handling
- Behavioral tags validation and output
- Tool boundary validation (raw dicts through call_tool_request)
"""

import pytest
from pydantic import ValidationError
from unittest.mock import MagicMock, patch
from mcp import types as mcp_types

from mcp_server.clarity.tool_logic import organize_thoughts
from mcp_server.clarity.tools.organize_thoughts import (
    ClusterRequest,
    ClusterInput,
    SubclusterInput,
    ALLOWED_TAGS,
)
from mcp_server.clarity.handlers.tools import call_tool_request


# =============================================================================
# Test Helpers
# =============================================================================

def _make_tool_request(arguments: dict, has_auth: bool = True) -> mcp_types.CallToolRequest:
    """Build a CallToolRequest with optional auth mock."""
    params = MagicMock()
    params.name = "organize_thoughts"
    params.arguments = arguments
    if has_auth:
        params._meta = {"headers": {"authorization": "Bearer mock-token"}}
    else:
        params._meta = None

    request = MagicMock(spec=mcp_types.CallToolRequest)
    request.params = params
    return request


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
        # Assert on error structure, not message wording (more robust)
        errors = exc_info.value.errors()
        assert len(errors) >= 1
        assert errors[0]["type"] == "value_error"  # Custom validator error


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

    def test_missing_thoughts_exhausted_defaults_to_false(self):
        """Test missing thoughts_exhausted defaults to False (LLM resilience)."""
        request = ClusterRequest(
            correctly_clustered=None,
            clusters=[ClusterInput(cluster_name="Test", thought_items=["item"])]
        )
        assert request.thoughts_exhausted is False  # Safe default: user may have more

    def test_correctly_clustered_optional(self):
        """Test correctly_clustered defaults to None."""
        request = ClusterRequest(
            thoughts_exhausted=True,
            clusters=[ClusterInput(cluster_name="Test", thought_items=["item"])]
        )
        assert request.correctly_clustered is None


# =============================================================================
# Test: Confirmation Field Handling (correctly_clustered)
# =============================================================================

class TestConfirmationFieldHandling:
    """Test correctly_clustered field behavior.

    correctly_clustered is flow metadata for ChatGPT conversation:
    - null: first call, user hasn't reviewed yet
    - false: user said clusters are wrong, triggers re-cluster
    - true: user confirmed clusters are accurate

    This field is:
    - Validated at input (part of ClusterRequest)
    - Logged for observability
    - NOT included in output (it's input-only metadata)
    """

    @pytest.mark.asyncio
    async def test_correctly_clustered_null_accepted(self):
        """First call with correctly_clustered=null succeeds."""
        arguments = {
            "thoughts_exhausted": True,
            "correctly_clustered": None,
            "clusters": [{"cluster_name": "Test", "thought_items": ["item"]}]
        }

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.return_value = {
                "user_id": "user-123",
                "scopes": {"clarity.write"},
                "jti": "token-id",
                "azp": "client-id"
            }

            result = await call_tool_request(_make_tool_request(arguments))

        assert result.isError is not True
        assert result.structuredContent is not None

    @pytest.mark.asyncio
    async def test_correctly_clustered_false_accepted(self):
        """Re-cluster call with correctly_clustered=false succeeds."""
        arguments = {
            "thoughts_exhausted": True,
            "correctly_clustered": False,
            "clusters": [{"cluster_name": "Revised", "thought_items": ["new item"]}]
        }

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.return_value = {
                "user_id": "user-123",
                "scopes": {"clarity.write"},
                "jti": "token-id",
                "azp": "client-id"
            }

            result = await call_tool_request(_make_tool_request(arguments))

        assert result.isError is not True
        assert result.structuredContent is not None

    @pytest.mark.asyncio
    async def test_correctly_clustered_true_accepted(self):
        """Confirmation call with correctly_clustered=true succeeds."""
        arguments = {
            "thoughts_exhausted": True,
            "correctly_clustered": True,
            "clusters": [{"cluster_name": "Confirmed", "thought_items": ["item"]}]
        }

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.return_value = {
                "user_id": "user-123",
                "scopes": {"clarity.write"},
                "jti": "token-id",
                "azp": "client-id"
            }

            result = await call_tool_request(_make_tool_request(arguments))

        assert result.isError is not True
        assert result.structuredContent is not None

    @pytest.mark.asyncio
    async def test_correctly_clustered_not_in_output(self):
        """correctly_clustered is input-only, NOT included in tool output.

        This is intentional: it's flow metadata for ChatGPT, not widget data.
        """
        arguments = {
            "thoughts_exhausted": True,
            "correctly_clustered": True,
            "clusters": [{"cluster_name": "Test", "thought_items": ["item"]}]
        }

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.return_value = {
                "user_id": "user-123",
                "scopes": {"clarity.write"},
                "jti": "token-id",
                "azp": "client-id"
            }

            result = await call_tool_request(_make_tool_request(arguments))

        # correctly_clustered should NOT appear in output
        assert "correctly_clustered" not in result.structuredContent
        # Only clusters should be in output
        assert "clusters" in result.structuredContent

    @pytest.mark.asyncio
    async def test_thoughts_exhausted_not_in_output(self):
        """thoughts_exhausted is also input-only, NOT included in tool output."""
        arguments = {
            "thoughts_exhausted": True,
            "clusters": [{"cluster_name": "Test", "thought_items": ["item"]}]
        }

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.return_value = {
                "user_id": "user-123",
                "scopes": {"clarity.write"},
                "jti": "token-id",
                "azp": "client-id"
            }

            result = await call_tool_request(_make_tool_request(arguments))

        # thoughts_exhausted should NOT appear in output
        assert "thoughts_exhausted" not in result.structuredContent


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
        # Assert on error structure, not message wording
        errors = exc_info.value.errors()
        assert len(errors) >= 1
        assert errors[0]["type"] == "value_error"  # Custom validator error


# =============================================================================
# Test: organize_thoughts Tool Output
# =============================================================================

class TestOrganizeThoughtsOutput:
    """Test organize_thoughts tool formatting."""

    def test_flat_cluster_output(self):
        """Test output for flat cluster."""
        clusters = [{
            "cluster_name": "Marketing",
            "thought_items": ["campaign", "budget", "timeline"],
            "subclusters": []
        }]

        result = organize_thoughts(clusters)

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

        result = organize_thoughts(clusters)

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

        result = organize_thoughts(clusters)

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

        result = organize_thoughts(clusters)

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
        result = organize_thoughts([])

        assert result["structuredContent"]["clusters"] == []
        assert "content" in result

    def test_content_message(self):
        """Test content message is present and prompts for prioritization."""
        clusters = [{"cluster_name": "Test", "thought_items": ["x"], "subclusters": []}]
        result = organize_thoughts(clusters)

        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        assert "clarity board" in result["content"][0]["text"].lower()
        assert "prioritize" in result["content"][0]["text"].lower()


# =============================================================================
# Test: Output Schema Stability
# =============================================================================

class TestOutputSchemaStability:
    """Test output schema is stable and doesn't leak unexpected fields.

    These tests catch accidental additions of internal fields to output.
    If schema changes intentionally, update these tests.
    """

    def test_top_level_output_keys(self):
        """Top-level result has exactly expected keys."""
        clusters = [{"cluster_name": "Test", "thought_items": ["item"]}]
        result = organize_thoughts(clusters)

        assert set(result.keys()) == {"content", "structuredContent"}

    def test_structured_content_keys(self):
        """structuredContent has exactly expected keys."""
        clusters = [{"cluster_name": "Test", "thought_items": ["item"]}]
        result = organize_thoughts(clusters)

        assert set(result["structuredContent"].keys()) == {"clusters"}

    def test_cluster_output_keys_flat(self):
        """Flat cluster output has exactly expected keys."""
        clusters = [{"cluster_name": "Test", "thought_items": ["item"], "tags": ["decide"]}]
        result = organize_thoughts(clusters)

        cluster = result["structuredContent"]["clusters"][0]
        assert set(cluster.keys()) == {
            "cluster_name",
            "thought_items",
            "subclusters",
            "sum_thought_items",
            "tags",
            "priority",  # Added in increment 13
        }

    def test_cluster_output_keys_nested(self):
        """Nested cluster output has exactly expected keys."""
        clusters = [{
            "cluster_name": "Parent",
            "thought_items": [],
            "subclusters": [{"subcluster_name": "Child", "thought_items": ["item"]}],
            "tags": []
        }]
        result = organize_thoughts(clusters)

        cluster = result["structuredContent"]["clusters"][0]
        assert set(cluster.keys()) == {
            "cluster_name",
            "thought_items",
            "subclusters",
            "sum_thought_items",
            "tags",
            "priority",  # Added in increment 13
        }

    def test_subcluster_output_keys(self):
        """Subcluster output has exactly expected keys."""
        clusters = [{
            "cluster_name": "Parent",
            "thought_items": [],
            "subclusters": [{"subcluster_name": "Child", "thought_items": ["item"], "tags": ["research"]}]
        }]
        result = organize_thoughts(clusters)

        subcluster = result["structuredContent"]["clusters"][0]["subclusters"][0]
        assert set(subcluster.keys()) == {
            "subcluster_name",
            "thought_items",
            "sum_thought_items",
            "tags",
            "priority",  # Added in increment 13
        }

    def test_no_internal_fields_leak_to_cluster(self):
        """Internal fields like user_id, correlation_id don't leak to cluster output."""
        clusters = [{"cluster_name": "Test", "thought_items": ["item"]}]
        result = organize_thoughts(clusters)

        cluster = result["structuredContent"]["clusters"][0]
        forbidden_fields = {"user_id", "correlation_id", "azp", "jti", "scopes", "_meta"}
        assert forbidden_fields.isdisjoint(cluster.keys())

    def test_no_input_metadata_in_output(self):
        """Input metadata fields don't appear in output."""
        clusters = [{"cluster_name": "Test", "thought_items": ["item"]}]
        result = organize_thoughts(clusters)

        # These are input-only fields
        assert "thoughts_exhausted" not in result["structuredContent"]
        assert "correctly_clustered" not in result["structuredContent"]


# =============================================================================
# Test: Ordering Guarantees (contract tests)
# =============================================================================

class TestOrderingGuarantees:
    """Test that ordering is preserved in output.

    CONTRACT: Input order is preserved in output.
    - Clusters appear in the same order as input
    - Subclusters appear in the same order as input
    - Thought items appear in the same order as input

    This is important for the widget: users expect clusters to render
    in the order ChatGPT organized them.
    """

    def test_cluster_order_preserved(self):
        """Clusters appear in output in same order as input."""
        clusters = [
            {"cluster_name": "First", "thought_items": ["a"]},
            {"cluster_name": "Second", "thought_items": ["b"]},
            {"cluster_name": "Third", "thought_items": ["c"]},
        ]
        result = organize_thoughts(clusters)

        output_names = [c["cluster_name"] for c in result["structuredContent"]["clusters"]]
        assert output_names == ["First", "Second", "Third"]

    def test_subcluster_order_preserved(self):
        """Subclusters appear in output in same order as input."""
        clusters = [{
            "cluster_name": "Parent",
            "thought_items": [],
            "subclusters": [
                {"subcluster_name": "Alpha", "thought_items": ["1"]},
                {"subcluster_name": "Beta", "thought_items": ["2"]},
                {"subcluster_name": "Gamma", "thought_items": ["3"]},
            ]
        }]
        result = organize_thoughts(clusters)

        output_names = [sc["subcluster_name"] for sc in result["structuredContent"]["clusters"][0]["subclusters"]]
        assert output_names == ["Alpha", "Beta", "Gamma"]

    def test_thought_items_order_preserved_in_cluster(self):
        """Thought items in cluster appear in same order as input."""
        clusters = [{
            "cluster_name": "Tasks",
            "thought_items": ["first task", "second task", "third task"],
            "subclusters": []
        }]
        result = organize_thoughts(clusters)

        output_items = result["structuredContent"]["clusters"][0]["thought_items"]
        assert output_items == ["first task", "second task", "third task"]

    def test_thought_items_order_preserved_in_subcluster(self):
        """Thought items in subcluster appear in same order as input."""
        clusters = [{
            "cluster_name": "Parent",
            "thought_items": [],
            "subclusters": [{
                "subcluster_name": "Child",
                "thought_items": ["item A", "item B", "item C"]
            }]
        }]
        result = organize_thoughts(clusters)

        output_items = result["structuredContent"]["clusters"][0]["subclusters"][0]["thought_items"]
        assert output_items == ["item A", "item B", "item C"]

    def test_tags_order_preserved(self):
        """Tags appear in same order as input."""
        clusters = [{
            "cluster_name": "Tagged",
            "thought_items": ["item"],
            "tags": ["decide", "research", "delegate"]
        }]
        result = organize_thoughts(clusters)

        output_tags = result["structuredContent"]["clusters"][0]["tags"]
        assert output_tags == ["decide", "research", "delegate"]


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
        # Assert on error structure, not message wording
        errors = exc_info.value.errors()
        assert len(errors) >= 1
        assert errors[0]["type"] == "value_error"  # Custom validator error

    def test_invalid_tag_raises_validation_error(self):
        """Test cluster with invalid tag raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ClusterInput(
                cluster_name="Invalid",
                thought_items=["item"],
                tags=["urgent"]
            )
        # Assert on error structure, not message wording
        errors = exc_info.value.errors()
        assert len(errors) >= 1
        assert errors[0]["type"] == "value_error"  # Custom validator error

    def test_subcluster_tags_valid(self):
        """Test subcluster with valid tags is valid."""
        subcluster = SubclusterInput(
            subcluster_name="Tagged",
            thought_items=["item"],
            tags=["delegate", "test"]
        )
        assert subcluster.tags == ["delegate", "test"]

    def test_subcluster_too_many_tags_raises_validation_error(self):
        """Test subcluster with >3 tags raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            SubclusterInput(
                subcluster_name="TooMany",
                thought_items=["item"],
                tags=["decide", "learn", "align", "research"]
            )
        # Assert on error structure, not message wording
        errors = exc_info.value.errors()
        assert len(errors) >= 1
        assert errors[0]["type"] == "value_error"  # Custom validator error

    def test_subcluster_invalid_tag_raises_validation_error(self):
        """Test subcluster with invalid tag raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            SubclusterInput(
                subcluster_name="Invalid",
                thought_items=["item"],
                tags=["priority"]
            )
        # Assert on error structure, not message wording
        errors = exc_info.value.errors()
        assert len(errors) >= 1
        assert errors[0]["type"] == "value_error"  # Custom validator error

    def test_allowed_tags_constant(self):
        """Test ALLOWED_TAGS contains expected values."""
        assert "decide" in ALLOWED_TAGS
        assert "research" in ALLOWED_TAGS
        assert "test" in ALLOWED_TAGS
        assert "delegate" in ALLOWED_TAGS
        assert "automate" in ALLOWED_TAGS
        assert "learn" in ALLOWED_TAGS
        assert "align" in ALLOWED_TAGS
        assert len(ALLOWED_TAGS) == 7


# =============================================================================
# Test: Tags in Tool Output
# =============================================================================

class TestTagsOutput:
    """Test tags are passed through in organize_thoughts output."""

    def test_cluster_tags_in_output(self):
        """Test cluster tags appear in output."""
        clusters = [{
            "cluster_name": "Tagged",
            "thought_items": ["item"],
            "subclusters": [],
            "tags": ["decide", "delegate"]
        }]

        result = organize_thoughts(clusters)
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

        result = organize_thoughts(clusters)
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

        result = organize_thoughts(clusters)
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

        result = organize_thoughts(clusters)
        cluster = result["structuredContent"]["clusters"][0]

        assert "tags" in cluster
        assert cluster["tags"] == []


# =============================================================================
# Test: Tool Boundary Validation (raw dicts through call_tool_request)
# =============================================================================

class TestToolBoundaryValidation:
    """Test validation happens at the tool boundary, not just in Pydantic models.

    Critical: These tests ensure malformed tool calls can't bypass validation.
    A refactor that skips validation should fail these tests.
    """

    @pytest.mark.asyncio
    async def test_tool_rejects_empty_cluster(self):
        """Empty cluster (no thought_items, no subclusters) is rejected at tool boundary."""
        arguments = {
            "thoughts_exhausted": True,
            "clusters": [{
                "cluster_name": "Empty",
                "thought_items": [],
                "subclusters": []
            }]
        }

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.return_value = {
                "user_id": "user-123",
                "scopes": {"clarity.write"},
                "jti": "token-id",
                "azp": "client-id"
            }

            result = await call_tool_request(_make_tool_request(arguments))

        # Should return structured error (validation fails, repair fails for empty cluster)
        assert result.isError is True
        assert len(result.content) > 0
        # Check for JSON-RPC -32602 Invalid Params error
        import json
        error_response = json.loads(result.content[0].text)
        assert error_response["error"]["code"] == -32602
        assert "invalid" in error_response["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_tool_rejects_missing_cluster_name(self):
        """Cluster without cluster_name is rejected at tool boundary."""
        arguments = {
            "thoughts_exhausted": True,
            "clusters": [{
                # Missing cluster_name
                "thought_items": ["item1", "item2"],
                "subclusters": []
            }]
        }

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.return_value = {
                "user_id": "user-123",
                "scopes": {"clarity.write"},
                "jti": "token-id",
                "azp": "client-id"
            }

            result = await call_tool_request(_make_tool_request(arguments))

        # Should return error
        assert result.isError is True

    @pytest.mark.asyncio
    async def test_tool_rejects_empty_subcluster(self):
        """Subcluster with empty thought_items is rejected at tool boundary."""
        arguments = {
            "thoughts_exhausted": True,
            "clusters": [{
                "cluster_name": "HasEmptySubcluster",
                "thought_items": [],
                "subclusters": [{
                    "subcluster_name": "Empty",
                    "thought_items": []  # Empty - invalid
                }]
            }]
        }

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.return_value = {
                "user_id": "user-123",
                "scopes": {"clarity.write"},
                "jti": "token-id",
                "azp": "client-id"
            }

            result = await call_tool_request(_make_tool_request(arguments))

        # Should return error
        assert result.isError is True

    @pytest.mark.asyncio
    async def test_tool_rejects_subcluster_missing_thought_items(self):
        """Subcluster missing thought_items field entirely is rejected at tool boundary.

        This is realistic: LLM/user might send {"subcluster_name": "X"} without thought_items.
        """
        arguments = {
            "thoughts_exhausted": True,
            "clusters": [{
                "cluster_name": "Parent",
                "thought_items": [],
                "subclusters": [{
                    "subcluster_name": "Broken"
                    # Missing thought_items field entirely
                }]
            }]
        }

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.return_value = {
                "user_id": "user-123",
                "scopes": {"clarity.write"},
                "jti": "token-id",
                "azp": "client-id"
            }

            result = await call_tool_request(_make_tool_request(arguments))

        # Should return error
        assert result.isError is True

    @pytest.mark.asyncio
    async def test_tool_strips_invalid_tag(self):
        """Cluster with invalid tag has the tag stripped (resilient to cached schemas)."""
        arguments = {
            "thoughts_exhausted": True,
            "clusters": [{
                "cluster_name": "BadTag",
                "thought_items": ["item"],
                "subclusters": [],
                "tags": ["urgent"]  # Invalid tag - will be stripped
            }]
        }

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.return_value = {
                "user_id": "user-123",
                "scopes": {"clarity.write"},
                "jti": "token-id",
                "azp": "client-id"
            }

            result = await call_tool_request(_make_tool_request(arguments))

        # Should succeed with invalid tag stripped
        assert result.isError is False
        # Verify the invalid tag was removed
        assert result.structuredContent["clusters"][0]["tags"] == []

    @pytest.mark.asyncio
    async def test_tool_rejects_too_many_tags(self):
        """Cluster with >3 tags is rejected at tool boundary."""
        arguments = {
            "thoughts_exhausted": True,
            "clusters": [{
                "cluster_name": "TooManyTags",
                "thought_items": ["item"],
                "subclusters": [],
                "tags": ["decide", "research", "test", "delegate"]  # 4 tags - max is 3
            }]
        }

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.return_value = {
                "user_id": "user-123",
                "scopes": {"clarity.write"},
                "jti": "token-id",
                "azp": "client-id"
            }

            result = await call_tool_request(_make_tool_request(arguments))

        # Should return error
        assert result.isError is True

    @pytest.mark.asyncio
    async def test_tool_accepts_valid_raw_dict(self):
        """Valid raw dict passes validation at tool boundary."""
        arguments = {
            "thoughts_exhausted": True,
            "clusters": [{
                "cluster_name": "Valid",
                "thought_items": ["task 1", "task 2"],
                "subclusters": []
            }]
        }

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.return_value = {
                "user_id": "user-123",
                "scopes": {"clarity.write"},
                "jti": "token-id",
                "azp": "client-id"
            }

            result = await call_tool_request(_make_tool_request(arguments))

        # Should succeed
        assert result.isError is not True
        assert result.structuredContent is not None
        assert "clusters" in result.structuredContent

    @pytest.mark.asyncio
    async def test_tool_repairs_raw_string_list(self):
        """Raw string list in clusters field gets repaired to valid cluster."""
        arguments = {
            "thoughts_exhausted": True,
            "clusters": ["task 1", "task 2", "task 3"]  # Malformed - strings instead of dicts
        }

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.return_value = {
                "user_id": "user-123",
                "scopes": {"clarity.write"},
                "jti": "token-id",
                "azp": "client-id"
            }

            result = await call_tool_request(_make_tool_request(arguments))

        # Should succeed via repair logic
        assert result.isError is not True
        assert result.structuredContent is not None
        assert len(result.structuredContent["clusters"]) == 1
        assert result.structuredContent["clusters"][0]["cluster_name"] == "Tasks"

    @pytest.mark.asyncio
    async def test_validation_runs_before_tool_logic(self):
        """Verify validation happens before tool logic executes.

        This test ensures a refactor can't accidentally skip validation.
        We pass invalid data and check it never reaches organize_thoughts().
        """
        arguments = {
            "thoughts_exhausted": True,
            "clusters": [{
                "cluster_name": "Empty",
                "thought_items": [],
                "subclusters": []
            }]
        }

        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.return_value = {
                "user_id": "user-123",
                "scopes": {"clarity.write"},
                "jti": "token-id",
                "azp": "client-id"
            }

            with patch("mcp_server.clarity.tools.organize_thoughts.format_clusters") as mock_tool:
                result = await call_tool_request(_make_tool_request(arguments))

                # format_clusters should NOT be called for invalid input
                mock_tool.assert_not_called()

        assert result.isError is True
