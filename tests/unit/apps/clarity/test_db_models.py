"""
Unit tests for Clarity database models.

Tests ClarityCluster model validation and constraints.
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone

from backend.apps.clarity.db_models import ClarityCluster


class TestClarityClusterValidation:
    """Test ClarityCluster.validate() method."""

    def _make_cluster(self, **overrides) -> ClarityCluster:
        """Create a valid ClarityCluster with optional overrides."""
        defaults = {
            "user_id": uuid4(),
            "cluster_data": {
                "clusters": [
                    {
                        "cluster_name": "Test Cluster",
                        "thought_items": ["item1", "item2"],
                        "subclusters": [],
                        "tags": [],
                    }
                ]
            },
        }
        defaults.update(overrides)
        return ClarityCluster(**defaults)

    def test_valid_cluster_passes_validation(self):
        """Valid cluster passes validation."""
        cluster = self._make_cluster()
        cluster.validate()  # Should not raise

    def test_user_id_required(self):
        """user_id cannot be None."""
        cluster = ClarityCluster(
            user_id=None,
            cluster_data={"clusters": []},
        )
        with pytest.raises(ValueError):
            cluster.validate()

    def test_cluster_data_must_be_dict(self):
        """cluster_data must be a dictionary."""
        cluster = self._make_cluster(cluster_data="not-a-dict")
        with pytest.raises(ValueError):
            cluster.validate()

    def test_cluster_data_cannot_be_none(self):
        """cluster_data cannot be None."""
        cluster = self._make_cluster(cluster_data=None)
        with pytest.raises(ValueError):
            cluster.validate()

    def test_cluster_data_must_have_clusters_key(self):
        """cluster_data must contain 'clusters' key."""
        cluster = self._make_cluster(cluster_data={"other": "data"})
        with pytest.raises(ValueError):
            cluster.validate()

    def test_clusters_must_be_list(self):
        """cluster_data['clusters'] must be a list."""
        cluster = self._make_cluster(cluster_data={"clusters": "not-a-list"})
        with pytest.raises(ValueError):
            cluster.validate()

    def test_empty_clusters_list_valid(self):
        """Empty clusters list is valid."""
        cluster = self._make_cluster(cluster_data={"clusters": []})
        cluster.validate()  # Should not raise

    def test_each_cluster_must_be_dict(self):
        """Each cluster in clusters array must be a dictionary."""
        cluster = self._make_cluster(
            cluster_data={"clusters": ["not-a-dict"]},
        )
        with pytest.raises(ValueError):
            cluster.validate()

    def test_each_cluster_must_have_cluster_name(self):
        """Each cluster must have 'cluster_name' field."""
        cluster = self._make_cluster(
            cluster_data={
                "clusters": [
                    {"thought_items": ["item1"]}  # Missing cluster_name
                ]
            },
        )
        with pytest.raises(ValueError):
            cluster.validate()


class TestClarityClusterCountProperty:
    """Test ClarityCluster.cluster_count computed property."""

    def test_cluster_count_empty(self):
        """cluster_count returns 0 for empty clusters."""
        cluster = ClarityCluster(
            user_id=uuid4(),
            cluster_data={"clusters": []},
        )
        assert cluster.cluster_count == 0

    def test_cluster_count_single(self):
        """cluster_count returns 1 for single cluster."""
        cluster = ClarityCluster(
            user_id=uuid4(),
            cluster_data={
                "clusters": [
                    {"cluster_name": "Test", "thought_items": ["a"]}
                ]
            },
        )
        assert cluster.cluster_count == 1

    def test_cluster_count_multiple(self):
        """cluster_count returns correct count for multiple clusters."""
        cluster = ClarityCluster(
            user_id=uuid4(),
            cluster_data={
                "clusters": [
                    {"cluster_name": "C1", "thought_items": ["a"]},
                    {"cluster_name": "C2", "thought_items": ["b"]},
                    {"cluster_name": "C3", "thought_items": ["c"]},
                ]
            },
        )
        assert cluster.cluster_count == 3

    def test_cluster_count_excludes_subclusters(self):
        """cluster_count only counts top-level clusters, not subclusters."""
        cluster = ClarityCluster(
            user_id=uuid4(),
            cluster_data={
                "clusters": [
                    {
                        "cluster_name": "Main",
                        "thought_items": [],
                        "subclusters": [
                            {"subcluster_name": "Sub1", "thought_items": ["a"]},
                            {"subcluster_name": "Sub2", "thought_items": ["b"]},
                        ],
                    }
                ]
            },
        )
        assert cluster.cluster_count == 1  # Only top-level


class TestClarityClusterRepr:
    """Test ClarityCluster.__repr__() method."""

    def test_repr_includes_key_fields(self):
        """__repr__ includes id, user_id, and clusters count."""
        user_id = uuid4()
        cluster = ClarityCluster(
            user_id=user_id,
            cluster_data={"clusters": []},
        )
        repr_str = repr(cluster)
        assert "ClarityCluster" in repr_str
        assert str(user_id) in repr_str
        assert "clusters=0" in repr_str


class TestClarityClusterComplexData:
    """Test ClarityCluster with complex cluster structures."""

    def test_cluster_with_subclusters(self):
        """Cluster with subclusters validates correctly."""
        cluster = ClarityCluster(
            user_id=uuid4(),
            cluster_data={
                "clusters": [
                    {
                        "cluster_name": "Main Cluster",
                        "thought_items": [],
                        "subclusters": [
                            {
                                "subcluster_name": "Sub 1",
                                "thought_items": ["a", "b"],
                                "tags": ["decide"],
                            },
                            {
                                "subcluster_name": "Sub 2",
                                "thought_items": ["c", "d"],
                                "tags": [],
                            },
                        ],
                        "tags": ["research"],
                    }
                ]
            },
        )
        cluster.validate()  # Should not raise

    def test_cluster_with_tags(self):
        """Cluster with tags validates correctly."""
        cluster = ClarityCluster(
            user_id=uuid4(),
            cluster_data={
                "clusters": [
                    {
                        "cluster_name": "Tagged Cluster",
                        "thought_items": ["item1"],
                        "subclusters": [],
                        "tags": ["decide", "delegate", "learn"],
                    }
                ]
            },
        )
        cluster.validate()  # Should not raise

    def test_multiple_clusters(self):
        """Multiple clusters validate correctly."""
        cluster = ClarityCluster(
            user_id=uuid4(),
            cluster_data={
                "clusters": [
                    {
                        "cluster_name": "Cluster 1",
                        "thought_items": ["a"],
                        "subclusters": [],
                        "tags": [],
                    },
                    {
                        "cluster_name": "Cluster 2",
                        "thought_items": ["b"],
                        "subclusters": [],
                        "tags": [],
                    },
                    {
                        "cluster_name": "Cluster 3",
                        "thought_items": ["c"],
                        "subclusters": [],
                        "tags": [],
                    },
                ]
            },
        )
        cluster.validate()  # Should not raise
