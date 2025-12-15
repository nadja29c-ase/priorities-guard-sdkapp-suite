"""
Integration tests for Clarity cluster persistence.

Tests the POST /api/clarity/clusters endpoint including:
- Successful cluster creation
- Missing/invalid X-User-ID handling
- Non-existent user handling
- Malformed cluster_data handling
- Database persistence verification
"""

import pytest
import pytest_asyncio
from uuid import uuid4, UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.models import CoreUser
from backend.apps.clarity.db_models import ClarityCluster


class TestClustersPersistence:
    """Test POST /api/clarity/clusters endpoint."""

    @pytest.fixture
    async def test_user(self, async_session: AsyncSession) -> CoreUser:
        """Create a test user for cluster persistence tests."""
        user = CoreUser(
            id=uuid4(),
            chatgpt_user_id=f"test_chatgpt_{uuid4().hex[:8]}",
        )
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)
        return user

    @pytest.mark.asyncio
    async def test_create_cluster_success(self, client, test_user):
        """POST with valid data returns 201 + cluster_id."""
        response = await client.post(
            "/api/clarity/clusters",
            headers={"X-User-ID": str(test_user.id)},
            json={
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
                "thoughts_exhausted": True,
                "correctly_clustered": None,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert "cluster_id" in data
        assert "created_at" in data

        # Verify it's a valid UUID
        cluster_uuid = UUID(data["cluster_id"])
        assert cluster_uuid is not None

    @pytest.mark.asyncio
    async def test_missing_user_id_header_returns_401(self, client):
        """POST without X-User-ID returns 401."""
        response = await client.post(
            "/api/clarity/clusters",
            json={
                "cluster_data": {"clusters": []},
                "thoughts_exhausted": True,
            },
        )

        assert response.status_code == 401
        assert "X-User-ID" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_nonexistent_user_returns_404(self, client):
        """POST with unknown user_id returns 404."""
        fake_user_id = str(uuid4())

        response = await client.post(
            "/api/clarity/clusters",
            headers={"X-User-ID": fake_user_id},
            json={
                "cluster_data": {"clusters": []},
                "thoughts_exhausted": True,
            },
        )

        assert response.status_code == 404
        assert "User not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_invalid_user_id_format_returns_400(self, client):
        """POST with invalid UUID format returns 400."""
        response = await client.post(
            "/api/clarity/clusters",
            headers={"X-User-ID": "not-a-uuid"},
            json={
                "cluster_data": {"clusters": []},
                "thoughts_exhausted": True,
            },
        )

        assert response.status_code == 400
        assert "Invalid user_id format" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_malformed_cluster_data_missing_clusters_key(self, client, test_user):
        """POST with cluster_data missing 'clusters' key returns 422."""
        response = await client.post(
            "/api/clarity/clusters",
            headers={"X-User-ID": str(test_user.id)},
            json={
                "cluster_data": {"other": "data"},  # Missing 'clusters' key
                "thoughts_exhausted": True,
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_malformed_cluster_data_clusters_not_list(self, client, test_user):
        """POST with cluster_data['clusters'] not a list returns 422."""
        response = await client.post(
            "/api/clarity/clusters",
            headers={"X-User-ID": str(test_user.id)},
            json={
                "cluster_data": {"clusters": "not-a-list"},
                "thoughts_exhausted": True,
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_thoughts_exhausted_returns_422(self, client, test_user):
        """POST without thoughts_exhausted returns 422 (required field)."""
        response = await client.post(
            "/api/clarity/clusters",
            headers={"X-User-ID": str(test_user.id)},
            json={
                "cluster_data": {"clusters": []},
                # thoughts_exhausted omitted
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_cluster_persisted_to_db(self, client, test_user, async_session):
        """Verify cluster retrievable from DB after POST."""
        cluster_data = {
            "clusters": [
                {
                    "cluster_name": "Persisted Cluster",
                    "thought_items": ["task1", "task2", "task3"],
                    "subclusters": [
                        {
                            "subcluster_name": "Sub 1",
                            "thought_items": ["sub_item"],
                            "tags": ["decide"],
                        }
                    ],
                    "tags": ["research", "delegate"],
                }
            ]
        }

        response = await client.post(
            "/api/clarity/clusters",
            headers={"X-User-ID": str(test_user.id)},
            json={
                "cluster_data": cluster_data,
                "thoughts_exhausted": True,
                "correctly_clustered": True,
            },
        )

        assert response.status_code == 201
        cluster_id = UUID(response.json()["cluster_id"])

        # Verify in database
        result = await async_session.execute(
            select(ClarityCluster).where(ClarityCluster.id == cluster_id)
        )
        cluster = result.scalar_one_or_none()

        assert cluster is not None
        assert cluster.user_id == test_user.id
        assert cluster.cluster_count == 1
        assert cluster.thoughts_exhausted is True
        assert cluster.correctly_clustered is True
        assert cluster.cluster_data["clusters"][0]["cluster_name"] == "Persisted Cluster"
        assert len(cluster.cluster_data["clusters"][0]["thought_items"]) == 3
        assert len(cluster.cluster_data["clusters"][0]["subclusters"]) == 1
        # Verify timestamps are timezone-aware
        assert cluster.created_at.tzinfo is not None
        assert cluster.updated_at.tzinfo is not None

    @pytest.mark.asyncio
    async def test_empty_clusters_list_valid(self, client, test_user):
        """POST with empty clusters list is valid."""
        response = await client.post(
            "/api/clarity/clusters",
            headers={"X-User-ID": str(test_user.id)},
            json={
                "cluster_data": {"clusters": []},
                "thoughts_exhausted": False,
                "correctly_clustered": None,
            },
        )

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_correctly_clustered_null_valid(self, client, test_user):
        """POST with correctly_clustered=null is valid."""
        response = await client.post(
            "/api/clarity/clusters",
            headers={"X-User-ID": str(test_user.id)},
            json={
                "cluster_data": {
                    "clusters": [
                        {
                            "cluster_name": "Test",
                            "thought_items": ["item"],
                            "subclusters": [],
                            "tags": [],
                        }
                    ]
                },
                "thoughts_exhausted": True,
                # correctly_clustered omitted (defaults to None)
            },
        )

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_multiple_clusters_count_correct(self, client, test_user, async_session):
        """Verify cluster_count is derived correctly for multiple clusters."""
        cluster_data = {
            "clusters": [
                {"cluster_name": "C1", "thought_items": ["a"], "subclusters": [], "tags": []},
                {"cluster_name": "C2", "thought_items": ["b"], "subclusters": [], "tags": []},
                {"cluster_name": "C3", "thought_items": ["c"], "subclusters": [], "tags": []},
            ]
        }

        response = await client.post(
            "/api/clarity/clusters",
            headers={"X-User-ID": str(test_user.id)},
            json={
                "cluster_data": cluster_data,
                "thoughts_exhausted": True,
            },
        )

        assert response.status_code == 201
        cluster_id = UUID(response.json()["cluster_id"])

        # Verify cluster_count in database
        result = await async_session.execute(
            select(ClarityCluster).where(ClarityCluster.id == cluster_id)
        )
        cluster = result.scalar_one()

        assert cluster.cluster_count == 3  # Top-level clusters only

    @pytest.mark.asyncio
    async def test_cluster_missing_cluster_name_returns_422(self, client, test_user):
        """POST with cluster missing cluster_name returns 422."""
        response = await client.post(
            "/api/clarity/clusters",
            headers={"X-User-ID": str(test_user.id)},
            json={
                "cluster_data": {
                    "clusters": [
                        {"thought_items": ["item"]}  # Missing cluster_name
                    ]
                },
                "thoughts_exhausted": True,
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_new_post_replaces_old_snapshot(self, client, test_user, async_session):
        """Second POST replaces first (only one row per user)."""
        # First POST
        response1 = await client.post(
            "/api/clarity/clusters",
            headers={"X-User-ID": str(test_user.id)},
            json={
                "cluster_data": {
                    "clusters": [
                        {"cluster_name": "First", "thought_items": ["a"], "subclusters": [], "tags": []}
                    ]
                },
                "thoughts_exhausted": True,
            },
        )
        assert response1.status_code == 201
        cluster_id_1 = UUID(response1.json()["cluster_id"])

        # Second POST (same user) - replaces first
        response2 = await client.post(
            "/api/clarity/clusters",
            headers={"X-User-ID": str(test_user.id)},
            json={
                "cluster_data": {
                    "clusters": [
                        {"cluster_name": "Second", "thought_items": ["b"], "subclusters": [], "tags": []}
                    ]
                },
                "thoughts_exhausted": False,
            },
        )
        assert response2.status_code == 201
        cluster_id_2 = UUID(response2.json()["cluster_id"])

        # Verify only one row exists (the second one)
        assert cluster_id_1 != cluster_id_2

        result = await async_session.execute(
            select(ClarityCluster).where(ClarityCluster.user_id == test_user.id)
        )
        clusters = result.scalars().all()

        assert len(clusters) == 1
        assert clusters[0].id == cluster_id_2
        assert clusters[0].cluster_data["clusters"][0]["cluster_name"] == "Second"

    @pytest.mark.asyncio
    async def test_deletion_scoped_to_user(self, client, test_user, async_session):
        """Deleting old snapshots doesn't affect other users."""
        # Create another user
        other_user = CoreUser(id=uuid4(), chatgpt_user_id=f"other_{uuid4().hex[:8]}")
        async_session.add(other_user)
        await async_session.commit()

        # Create snapshot for test_user
        await client.post(
            "/api/clarity/clusters",
            headers={"X-User-ID": str(test_user.id)},
            json={
                "cluster_data": {
                    "clusters": [{"cluster_name": "User1", "thought_items": ["a"], "subclusters": [], "tags": []}]
                },
                "thoughts_exhausted": True,
            },
        )

        # Create snapshot for other_user
        await client.post(
            "/api/clarity/clusters",
            headers={"X-User-ID": str(other_user.id)},
            json={
                "cluster_data": {
                    "clusters": [{"cluster_name": "User2", "thought_items": ["b"], "subclusters": [], "tags": []}]
                },
                "thoughts_exhausted": True,
            },
        )

        # Create second snapshot for test_user (should delete first)
        await client.post(
            "/api/clarity/clusters",
            headers={"X-User-ID": str(test_user.id)},
            json={
                "cluster_data": {
                    "clusters": [{"cluster_name": "User1-v2", "thought_items": ["c"], "subclusters": [], "tags": []}]
                },
                "thoughts_exhausted": True,
            },
        )

        # Verify: 1 row for test_user, 1 row for other_user
        result = await async_session.execute(select(ClarityCluster))
        all_clusters = result.scalars().all()

        assert len(all_clusters) == 2
        user_ids = {c.user_id for c in all_clusters}
        assert user_ids == {test_user.id, other_user.id}


class TestGetClusters:
    """Test GET /api/clarity/clusters endpoint."""

    @pytest.fixture
    async def test_user(self, async_session: AsyncSession) -> CoreUser:
        """Create a test user for cluster retrieval tests."""
        user = CoreUser(
            id=uuid4(),
            chatgpt_user_id=f"test_get_chatgpt_{uuid4().hex[:8]}",
        )
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)
        return user

    @pytest.mark.asyncio
    async def test_get_clusters_returns_latest(self, client, test_user):
        """GET returns the most recent cluster snapshot."""
        # First, create a snapshot via POST
        cluster_data = {
            "clusters": [
                {
                    "cluster_name": "Work Tasks",
                    "thought_items": ["Review PR", "Update docs"],
                    "subclusters": [],
                    "tags": ["delegate"],
                }
            ]
        }

        post_response = await client.post(
            "/api/clarity/clusters",
            headers={"X-User-ID": str(test_user.id)},
            json={
                "cluster_data": cluster_data,
                "thoughts_exhausted": True,
                "correctly_clustered": True,
            },
        )
        assert post_response.status_code == 201
        created_cluster_id = post_response.json()["cluster_id"]

        # Now retrieve via GET
        get_response = await client.get(
            "/api/clarity/clusters",
            headers={"X-User-ID": str(test_user.id)},
        )

        assert get_response.status_code == 200
        data = get_response.json()

        assert data["cluster_id"] == created_cluster_id
        assert data["thoughts_exhausted"] is True
        assert data["correctly_clustered"] is True
        assert "created_at" in data
        assert data["cluster_data"]["clusters"][0]["cluster_name"] == "Work Tasks"
        assert len(data["cluster_data"]["clusters"][0]["thought_items"]) == 2

    @pytest.mark.asyncio
    async def test_get_clusters_404_when_none(self, client, test_user):
        """GET returns 404 when user has no cluster snapshots."""
        response = await client.get(
            "/api/clarity/clusters",
            headers={"X-User-ID": str(test_user.id)},
        )

        assert response.status_code == 404
        assert "No cluster snapshot found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_clusters_missing_user_id_returns_401(self, client):
        """GET without X-User-ID returns 401."""
        response = await client.get("/api/clarity/clusters")

        assert response.status_code == 401
        assert "X-User-ID" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_clusters_nonexistent_user_returns_404(self, client):
        """GET with unknown user_id returns 404."""
        fake_user_id = str(uuid4())

        response = await client.get(
            "/api/clarity/clusters",
            headers={"X-User-ID": fake_user_id},
        )

        assert response.status_code == 404
        assert "User not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_clusters_invalid_user_id_format_returns_400(self, client):
        """GET with invalid UUID format returns 400."""
        response = await client.get(
            "/api/clarity/clusters",
            headers={"X-User-ID": "not-a-uuid"},
        )

        assert response.status_code == 400
        assert "Invalid user_id format" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_clusters_returns_most_recent_after_update(self, client, test_user):
        """GET returns the most recent snapshot after multiple POSTs."""
        # First POST
        await client.post(
            "/api/clarity/clusters",
            headers={"X-User-ID": str(test_user.id)},
            json={
                "cluster_data": {
                    "clusters": [
                        {"cluster_name": "Old", "thought_items": ["old item"], "subclusters": [], "tags": []}
                    ]
                },
                "thoughts_exhausted": False,
            },
        )

        # Second POST (replaces first)
        post_response = await client.post(
            "/api/clarity/clusters",
            headers={"X-User-ID": str(test_user.id)},
            json={
                "cluster_data": {
                    "clusters": [
                        {"cluster_name": "New", "thought_items": ["new item"], "subclusters": [], "tags": []}
                    ]
                },
                "thoughts_exhausted": True,
            },
        )
        new_cluster_id = post_response.json()["cluster_id"]

        # GET should return the latest
        get_response = await client.get(
            "/api/clarity/clusters",
            headers={"X-User-ID": str(test_user.id)},
        )

        assert get_response.status_code == 200
        data = get_response.json()

        assert data["cluster_id"] == new_cluster_id
        assert data["cluster_data"]["clusters"][0]["cluster_name"] == "New"
        assert data["thoughts_exhausted"] is True
