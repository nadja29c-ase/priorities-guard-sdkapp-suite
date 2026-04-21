"""
Integration tests for POST /api/priority-guardian/reconcile-user endpoint (Increment 78).

End-to-end HTTP tests verifying the reconciliation endpoint behavior.
"""

import pytest
from unittest.mock import patch
from uuid import uuid4
from datetime import date

from backend.apps.priority_guardian.db_models import PgPriority
from backend.core.models import CoreUser, CoreConnection

# Use a known test secret instead of relying on potentially-unset settings.INTERNAL_API_SECRET
TEST_INTERNAL_SECRET = "test-internal-secret-inc78"


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
async def user_a_hydrated(async_session):
    """Create a CoreUser with openai_subject and active Google connection."""
    from datetime import datetime, timezone

    user = CoreUser(id=uuid4(), openai_subject="v1/subject-hydrated")
    async_session.add(user)
    await async_session.flush()

    connection = CoreConnection(
        user_id=user.id,
        provider="google",
        connection_type="google",
        encrypted_access_token="enc-token",
        token_expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        scopes=["calendar.readonly"],
        revoked_at=None,
    )
    async_session.add(connection)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def user_b_fresh(async_session):
    """Create a fresh CoreUser with no subject, no connections, no priorities."""
    user = CoreUser(id=uuid4(), openai_subject=None)
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def user_with_priority(async_session):
    """Create a CoreUser with a PgPriority but no Google connection."""
    user = CoreUser(id=uuid4(), openai_subject=None)
    async_session.add(user)
    await async_session.flush()

    priority = PgPriority(
        user_id=user.id,
        name="Test Priority",
        type="deadline",
        calendar_keyword="P1",
        deadline=date(2099, 12, 31),
        status="active",
    )
    async_session.add(priority)
    await async_session.commit()
    await async_session.refresh(user)
    return user


# =============================================================================
# Security Tests
# =============================================================================

@pytest.mark.asyncio
async def test_endpoint_requires_internal_secret(client, user_b_fresh):
    """POST without X-Internal-Secret → 403."""
    # Patch to non-empty value so security check is enforced (empty = dev mode skips check)
    with patch("backend.core.config.settings.INTERNAL_API_SECRET", TEST_INTERNAL_SECRET):
        response = await client.post(
            "/api/priority-guardian/reconcile-user",
            json={
                "jwt_user_id": str(user_b_fresh.id),
                "openai_subject": "v1/test-subject",
            },
            # No X-Internal-Secret header
        )

        assert response.status_code == 403


@pytest.mark.asyncio
async def test_endpoint_rejects_malformed_body(client):
    """Missing fields or invalid UUID → 422."""
    with patch("backend.core.config.settings.INTERNAL_API_SECRET", TEST_INTERNAL_SECRET):
        headers = {"X-Internal-Secret": TEST_INTERNAL_SECRET}

        # Missing jwt_user_id
        response = await client.post(
            "/api/priority-guardian/reconcile-user",
            json={"openai_subject": "v1/test"},
            headers=headers,
        )
        assert response.status_code == 422

        # Invalid UUID
        response = await client.post(
            "/api/priority-guardian/reconcile-user",
            json={"jwt_user_id": "not-a-uuid", "openai_subject": "v1/test"},
            headers=headers,
        )
        assert response.status_code == 422

        # Empty subject
        response = await client.post(
            "/api/priority-guardian/reconcile-user",
            json={"jwt_user_id": str(uuid4()), "openai_subject": ""},
            headers=headers,
        )
        assert response.status_code == 422


# =============================================================================
# Full Flow Tests
# =============================================================================

@pytest.mark.asyncio
async def test_full_flow_case_a(client, async_session, user_b_fresh):
    """
    POST with subject no CoreUser has.
    Verify DB state after: target CoreUser has openai_subject stamped.
    Response {"user_id": X, "case": "A"}.
    """
    with patch("backend.core.config.settings.INTERNAL_API_SECRET", TEST_INTERNAL_SECRET):
        subject = "v1/brand-new-subject-integration"
        headers = {"X-Internal-Secret": TEST_INTERNAL_SECRET}

        response = await client.post(
            "/api/priority-guardian/reconcile-user",
            json={
                "jwt_user_id": str(user_b_fresh.id),
                "openai_subject": subject,
            },
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == str(user_b_fresh.id)
        assert data["case"] == "A"

        # Verify DB state
        await async_session.refresh(user_b_fresh)
        assert user_b_fresh.openai_subject == subject


@pytest.mark.asyncio
async def test_full_flow_case_c1_cross_device_fresh(client, async_session, user_a_hydrated, user_b_fresh):
    """
    Hydrated CoreUser_A with subject S and Google connection.
    Fresh CoreUser_B (no connection, no priorities).
    POST with jwt_user_id=B, subject=S.
    Response {"user_id": A, "case": "C1"}.
    B still in DB, unchanged.
    """
    with patch("backend.core.config.settings.INTERNAL_API_SECRET", TEST_INTERNAL_SECRET):
        headers = {"X-Internal-Secret": TEST_INTERNAL_SECRET}

        response = await client.post(
            "/api/priority-guardian/reconcile-user",
            json={
                "jwt_user_id": str(user_b_fresh.id),
                "openai_subject": user_a_hydrated.openai_subject,
            },
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == str(user_a_hydrated.id)
        assert data["case"] == "C1"

        # Verify B still exists and is unchanged
        await async_session.refresh(user_b_fresh)
        assert user_b_fresh.openai_subject is None  # B's subject not changed


@pytest.mark.asyncio
async def test_full_flow_case_c2_priorities_block_remap(client, async_session, user_a_hydrated, user_with_priority):
    """
    Hydrated CoreUser_A with subject S.
    CoreUser_B with no active Google connection BUT with one PgPriority row.
    POST with jwt_user_id=B, subject=S.
    Response {"user_id": B, "case": "C2"}.
    """
    with patch("backend.core.config.settings.INTERNAL_API_SECRET", TEST_INTERNAL_SECRET):
        headers = {"X-Internal-Secret": TEST_INTERNAL_SECRET}

        response = await client.post(
            "/api/priority-guardian/reconcile-user",
            json={
                "jwt_user_id": str(user_with_priority.id),
                "openai_subject": user_a_hydrated.openai_subject,
            },
            headers=headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == str(user_with_priority.id)
        assert data["case"] == "C2"


# =============================================================================
# DB Integrity Tests
# =============================================================================

@pytest.mark.asyncio
async def test_openai_subject_partial_unique_index(async_session):
    """
    Insert two CoreUsers with openai_subject=NULL (must succeed).
    Insert two CoreUsers with openai_subject="v1/abc" (second must fail with unique violation).

    The partial unique index is defined in CoreUser.__table_args__, so create_all()
    creates it. The migration also creates it for existing databases.
    """
    from sqlalchemy.exc import IntegrityError

    # Two NULL subjects should succeed
    user1 = CoreUser(id=uuid4(), openai_subject=None)
    user2 = CoreUser(id=uuid4(), openai_subject=None)
    async_session.add_all([user1, user2])
    await async_session.commit()

    # First non-NULL subject should succeed
    user3 = CoreUser(id=uuid4(), openai_subject="v1/unique-subject-integration")
    async_session.add(user3)
    await async_session.commit()

    # Second user with same non-NULL subject should fail
    user4 = CoreUser(id=uuid4(), openai_subject="v1/unique-subject-integration")
    async_session.add(user4)

    with pytest.raises(IntegrityError):
        await async_session.commit()
