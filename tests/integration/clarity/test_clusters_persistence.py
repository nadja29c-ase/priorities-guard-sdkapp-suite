"""
Integration tests for Clarity cluster persistence.

Tests the POST /api/clarity/clusters endpoint including:
- Successful cluster creation
- Missing/invalid X-User-ID handling
- Non-existent user handling
- Malformed cluster_data handling
- Database persistence verification

Tests the DELETE /api/clarity/data endpoint including:
- Successful deletion with confirmation
- Idempotent behavior (no_data on second delete)
- Rejection without confirmation
- Audit log persistence
"""

import pytest
from uuid import uuid4, UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.models import CoreUser, CoreToolAuditLog
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
        assert response.json()["detail"]["code"] == "UNAUTHORIZED"

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
    async def test_invalid_user_id_format_returns_401(self, client):
        """POST with invalid UUID format returns 401."""
        response = await client.post(
            "/api/clarity/clusters",
            headers={"X-User-ID": "not-a-uuid"},
            json={
                "cluster_data": {"clusters": []},
                "thoughts_exhausted": True,
            },
        )

        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "UNAUTHORIZED"

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
        # Verify created_at is timezone-aware (user-visible in API response)
        assert cluster.created_at.tzinfo is not None
        # Note: updated_at not asserted - internal implementation detail, not in API response

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
    async def test_post_upserts_snapshot(self, client, test_user):
        """POST upserts the user's snapshot (single-row model).

        Behavioral guarantee: Each POST replaces the previous snapshot.
        With UNIQUE(user_id), there's THE snapshot, not "latest".

        This test asserts behavior via API, not implementation via DB queries.
        """
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
        cluster_id_1 = response1.json()["cluster_id"]

        # Second POST (same user)
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

        # Behavioral guarantee: GET returns the current snapshot data
        # With upsert, cluster_id stays the same (same row updated).
        get_response = await client.get(
            "/api/clarity/clusters",
            headers={"X-User-ID": str(test_user.id)},
        )
        assert get_response.status_code == 200
        data = get_response.json()

        # Assert GET returns the SECOND POST's data, not the first
        assert data["cluster_data"]["clusters"][0]["cluster_name"] == "Second"
        assert data["thoughts_exhausted"] is False

    @pytest.mark.asyncio
    async def test_user_data_isolation(self, client, test_user, async_session):
        """One user's updates don't affect another user's data.

        Behavioral guarantee: User isolation - each user sees only their own data.
        Implementation detail (not tested): How data is stored or cleaned up.

        This test asserts behavior via API, not implementation via DB queries.
        """
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
        response_other = await client.post(
            "/api/clarity/clusters",
            headers={"X-User-ID": str(other_user.id)},
            json={
                "cluster_data": {
                    "clusters": [{"cluster_name": "User2", "thought_items": ["b"], "subclusters": [], "tags": []}]
                },
                "thoughts_exhausted": True,
            },
        )
        other_cluster_id = response_other.json()["cluster_id"]

        # Create second snapshot for test_user
        response_user1_v2 = await client.post(
            "/api/clarity/clusters",
            headers={"X-User-ID": str(test_user.id)},
            json={
                "cluster_data": {
                    "clusters": [{"cluster_name": "User1-v2", "thought_items": ["c"], "subclusters": [], "tags": []}]
                },
                "thoughts_exhausted": True,
            },
        )
        user1_v2_cluster_id = response_user1_v2.json()["cluster_id"]

        # Behavioral guarantee: Each user sees only their own snapshot
        get_user1 = await client.get(
            "/api/clarity/clusters",
            headers={"X-User-ID": str(test_user.id)},
        )
        assert get_user1.status_code == 200
        assert get_user1.json()["cluster_id"] == user1_v2_cluster_id
        assert get_user1.json()["cluster_data"]["clusters"][0]["cluster_name"] == "User1-v2"

        get_other = await client.get(
            "/api/clarity/clusters",
            headers={"X-User-ID": str(other_user.id)},
        )
        assert get_other.status_code == 200
        assert get_other.json()["cluster_id"] == other_cluster_id
        assert get_other.json()["cluster_data"]["clusters"][0]["cluster_name"] == "User2"


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
    async def test_get_clusters_success(self, client, test_user):
        """GET returns the user's cluster snapshot."""
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
        """GET returns 404 when user has no cluster snapshots.

        API CONTRACT - 404 Response Disambiguation:
            This endpoint returns 404 in two distinct cases:
            - "User not found" (detail message) - user_id doesn't exist
            - "No cluster snapshot found for user" (detail message) - user exists, no data

            Consumers MUST check the detail message to distinguish these cases.

            Alternative designs considered:
            - 200 {"cluster": null} - More RESTful, but changes response schema
            - 204 No Content - Ambiguous, no body for context

            Current design was chosen for simplicity. If consumers need programmatic
            distinction, add an error code field to the response body.
        """
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
        assert response.json()["detail"]["code"] == "UNAUTHORIZED"

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
    async def test_get_clusters_invalid_user_id_format_returns_401(self, client):
        """GET with invalid UUID format returns 401."""
        response = await client.get(
            "/api/clarity/clusters",
            headers={"X-User-ID": "not-a-uuid"},
        )

        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "UNAUTHORIZED"

    @pytest.mark.asyncio
    async def test_get_returns_updated_snapshot_after_upsert(self, client, test_user):
        """GET returns the updated snapshot after upsert."""
        # First POST (creates)
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

        # Second POST (upserts/updates)
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

        # GET returns the (single) snapshot
        get_response = await client.get(
            "/api/clarity/clusters",
            headers={"X-User-ID": str(test_user.id)},
        )

        assert get_response.status_code == 200
        data = get_response.json()

        assert data["cluster_id"] == new_cluster_id
        assert data["cluster_data"]["clusters"][0]["cluster_name"] == "New"
        assert data["thoughts_exhausted"] is True

    # NOTE: test_get_returns_snapshot_with_latest_created_at was removed.
    # With single-row model (UNIQUE user_id), there's no ordering concept.
    # Ordering tests are meaningless when there's at most one row per user.


class TestCorruptedDataHandling:
    """Tests for graceful handling of corrupted/malformed DB data.

    STATE RECOVERY GUARANTEE (Increment 10):
        Even if DB data is corrupted, the API layer should not crash.
        The MCP layer has additional defenses, but API should be first line.
    """

    @pytest.fixture
    async def test_user(self, async_session: AsyncSession) -> CoreUser:
        """Create a test user for corrupted data tests."""
        user = CoreUser(
            id=uuid4(),
            chatgpt_user_id=f"test_corrupted_{uuid4().hex[:8]}",
        )
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)
        return user

    @pytest.mark.asyncio
    async def test_get_with_malformed_cluster_data_returns_data(
        self, client, test_user, async_session
    ):
        """GET returns data even if cluster_data structure is unexpected.

        API layer passes through whatever is in DB.
        MCP layer handles validation/fallback.

        This documents current behavior - API is a passthrough,
        corruption handling is at MCP layer.
        """
        # Directly insert corrupted data (missing 'clusters' key)
        corrupted_cluster = ClarityCluster(
            user_id=test_user.id,
            cluster_data={"wrong_key": "corrupted"},  # Missing 'clusters'
            thoughts_exhausted=True,
            correctly_clustered=None,
        )
        async_session.add(corrupted_cluster)
        await async_session.commit()
        await async_session.refresh(corrupted_cluster)

        # GET should still return the row (API is passthrough)
        response = await client.get(
            "/api/clarity/clusters",
            headers={"X-User-ID": str(test_user.id)},
        )

        # API returns 200 with whatever data exists
        # Corruption handling is MCP layer's responsibility
        assert response.status_code == 200
        data = response.json()
        assert data["cluster_id"] == str(corrupted_cluster.id)
        assert data["cluster_data"] == {"wrong_key": "corrupted"}
        # Envelope fields must still be valid despite corrupted payload
        assert "created_at" in data
        assert data["created_at"] is not None

    @pytest.mark.asyncio
    async def test_get_with_null_clusters_list_returns_data(
        self, client, test_user, async_session
    ):
        """GET returns data even if clusters list is null.

        Edge case: cluster_data has 'clusters' key but value is null.
        """
        corrupted_cluster = ClarityCluster(
            user_id=test_user.id,
            cluster_data={"clusters": None},  # null instead of list
            thoughts_exhausted=True,
            correctly_clustered=None,
        )
        async_session.add(corrupted_cluster)
        await async_session.commit()
        await async_session.refresh(corrupted_cluster)

        response = await client.get(
            "/api/clarity/clusters",
            headers={"X-User-ID": str(test_user.id)},
        )

        # API returns 200 - passthrough behavior
        assert response.status_code == 200
        data = response.json()
        assert data["cluster_data"]["clusters"] is None
        # Envelope fields must still be valid despite corrupted payload
        assert "created_at" in data
        assert data["created_at"] is not None


class TestDeleteData:
    """Test DELETE /api/clarity/data endpoint (GDPR compliance)."""

    @pytest.fixture
    async def test_user(self, async_session: AsyncSession) -> CoreUser:
        """Create a test user for delete tests."""
        user = CoreUser(
            id=uuid4(),
            chatgpt_user_id=f"test_delete_{uuid4().hex[:8]}",
        )
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)
        return user

    @pytest.fixture
    async def user_with_cluster(self, client, test_user) -> CoreUser:
        """Create a user with a cluster snapshot."""
        await client.post(
            "/api/clarity/clusters",
            headers={"X-User-ID": str(test_user.id)},
            json={
                "cluster_data": {
                    "clusters": [
                        {"cluster_name": "Test", "thought_items": ["item"], "subclusters": [], "tags": []}
                    ]
                },
                "thoughts_exhausted": True,
            },
        )
        return test_user

    @pytest.mark.asyncio
    async def test_delete_success(self, client, user_with_cluster, async_session):
        """DELETE with confirm=true returns 200 + deleted count."""
        response = await client.request(
            "DELETE",
            "/api/clarity/data",
            headers={"X-User-ID": str(user_with_cluster.id)},
            json={"confirm": True},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"
        assert data["deleted"]["boards"] == 1
        assert "permanently deleted" in data["message"]

        # Verify actually deleted from DB
        result = await async_session.execute(
            select(ClarityCluster).where(ClarityCluster.user_id == user_with_cluster.id)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_no_data_idempotent(self, client, test_user):
        """DELETE when no data exists returns 200 + no_data (idempotent)."""
        response = await client.request(
            "DELETE",
            "/api/clarity/data",
            headers={"X-User-ID": str(test_user.id)},
            json={"confirm": True},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "no_data"
        assert data["deleted"] is None

    @pytest.mark.asyncio
    async def test_delete_without_confirm_returns_400(self, client, user_with_cluster):
        """DELETE without confirm parameter returns 400."""
        response = await client.request(
            "DELETE",
            "/api/clarity/data",
            headers={"X-User-ID": str(user_with_cluster.id)},
            json={},  # No confirm
        )

        assert response.status_code == 400
        assert "confirm" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_delete_with_confirm_false_returns_400(self, client, user_with_cluster):
        """DELETE with confirm=false returns 400."""
        response = await client.request(
            "DELETE",
            "/api/clarity/data",
            headers={"X-User-ID": str(user_with_cluster.id)},
            json={"confirm": False},
        )

        assert response.status_code == 400
        assert "confirm" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_delete_missing_user_id_returns_401(self, client):
        """DELETE without X-User-ID returns 401."""
        response = await client.request(
            "DELETE",
            "/api/clarity/data",
            json={"confirm": True},
        )

        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "UNAUTHORIZED"

    @pytest.mark.asyncio
    async def test_delete_nonexistent_user_returns_404(self, client):
        """DELETE with unknown user_id returns 404."""
        fake_user_id = str(uuid4())

        response = await client.request(
            "DELETE",
            "/api/clarity/data",
            headers={"X-User-ID": fake_user_id},
            json={"confirm": True},
        )

        assert response.status_code == 404
        assert "User not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_delete_invalid_user_id_format_returns_401(self, client):
        """DELETE with invalid UUID format returns 401."""
        response = await client.request(
            "DELETE",
            "/api/clarity/data",
            headers={"X-User-ID": "not-a-uuid"},
            json={"confirm": True},
        )

        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "UNAUTHORIZED"

    @pytest.mark.asyncio
    async def test_delete_writes_audit_log(self, client, user_with_cluster, async_session):
        """DELETE writes audit log entry in same transaction."""
        response = await client.request(
            "DELETE",
            "/api/clarity/data",
            headers={"X-User-ID": str(user_with_cluster.id)},
            json={"confirm": True},
        )

        assert response.status_code == 200

        # Verify audit log was written
        result = await async_session.execute(
            select(CoreToolAuditLog).where(
                CoreToolAuditLog.user_id == user_with_cluster.id,
                CoreToolAuditLog.action == "delete_my_data",
            )
        )
        audit_entry = result.scalar_one_or_none()

        assert audit_entry is not None
        assert audit_entry.app_name == "clarity"
        assert audit_entry.result_status == "success"
        assert audit_entry.details["rows_deleted"]["clarity_clusters"] == 1
        assert audit_entry.details["confirm_provided"] is True

    @pytest.mark.asyncio
    async def test_delete_no_data_writes_audit_log(self, client, test_user, async_session):
        """DELETE with no data still writes audit log (for compliance tracking)."""
        response = await client.request(
            "DELETE",
            "/api/clarity/data",
            headers={"X-User-ID": str(test_user.id)},
            json={"confirm": True},
        )

        assert response.status_code == 200

        # Verify audit log was written even for no_data
        result = await async_session.execute(
            select(CoreToolAuditLog).where(
                CoreToolAuditLog.user_id == test_user.id,
                CoreToolAuditLog.action == "delete_my_data",
            )
        )
        audit_entry = result.scalar_one_or_none()

        assert audit_entry is not None
        assert audit_entry.result_status == "no_data"
        assert audit_entry.details["rows_deleted"]["clarity_clusters"] == 0

    @pytest.mark.asyncio
    async def test_double_delete_is_idempotent(self, client, user_with_cluster):
        """Calling DELETE twice returns deleted then no_data (idempotent)."""
        # First delete
        response1 = await client.request(
            "DELETE",
            "/api/clarity/data",
            headers={"X-User-ID": str(user_with_cluster.id)},
            json={"confirm": True},
        )
        assert response1.status_code == 200
        assert response1.json()["status"] == "deleted"

        # Second delete (same user)
        response2 = await client.request(
            "DELETE",
            "/api/clarity/data",
            headers={"X-User-ID": str(user_with_cluster.id)},
            json={"confirm": True},
        )
        assert response2.status_code == 200
        assert response2.json()["status"] == "no_data"
