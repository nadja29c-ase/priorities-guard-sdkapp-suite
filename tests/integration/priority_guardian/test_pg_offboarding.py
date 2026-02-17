"""
Integration tests for Priority Guardian offboarding endpoint (Increment 03).

Tests POST /api/priority-guardian/disconnect with real DB and mocked Google APIs.

Test coverage:
- disconnect calls revoke_google_token when connection has refresh token
- disconnect succeeds even when revoke_google_token fails (best-effort)
- disconnect skips revocation when no refresh token exists
- disconnect skips revocation when no connection exists
- full disconnect flow with mocked Google revoke returning 200
- full disconnect flow with mocked Google revoke returning 400 (already revoked)
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import patch, AsyncMock

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.models import CoreUser, CoreConnection
from backend.core.encryption import encrypt_token
from backend.core.oauth_provider.models import OAuthAccessToken


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest_asyncio.fixture
async def pg_user(async_session: AsyncSession):
    """Create a basic test user."""
    user = CoreUser(id=uuid4())
    async_session.add(user)
    await async_session.commit()
    return user


@pytest_asyncio.fixture
async def pg_user_with_connection(async_session: AsyncSession, pg_user: CoreUser):
    """Create a test user with Google connection (has refresh token)."""
    connection = CoreConnection(
        user_id=pg_user.id,
        provider="google",
        encrypted_access_token=encrypt_token("test_access_token"),
        encrypted_refresh_token=encrypt_token("test_refresh_token"),
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        scopes=["https://www.googleapis.com/auth/calendar.readonly"],
    )
    async_session.add(connection)
    await async_session.commit()

    return {"user": pg_user, "connection": connection}


@pytest_asyncio.fixture
async def pg_user_with_connection_no_refresh(async_session: AsyncSession, pg_user: CoreUser):
    """Create a test user with Google connection but NO refresh token."""
    connection = CoreConnection(
        user_id=pg_user.id,
        provider="google",
        encrypted_access_token=encrypt_token("test_access_token"),
        encrypted_refresh_token=None,  # No refresh token
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        scopes=["https://www.googleapis.com/auth/calendar.readonly"],
    )
    async_session.add(connection)
    await async_session.commit()

    return {"user": pg_user, "connection": connection}


@pytest_asyncio.fixture
async def pg_user_with_tokens(async_session: AsyncSession, pg_user_with_connection: dict):
    """Create a test user with connection and PG OAuth tokens."""
    user = pg_user_with_connection["user"]

    # Create PG-scoped OAuth tokens
    tokens = []
    for i in range(2):
        token = OAuthAccessToken(
            jti=f"pg-token-{uuid4()}",
            user_id=user.id,
            client_id="pg-test-client",
            scope=["pg.access"],
            token_type="Bearer",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            revoked=False,
        )
        async_session.add(token)
        tokens.append(token)

    await async_session.commit()

    return {
        **pg_user_with_connection,
        "tokens": tokens,
    }


# =============================================================================
# Unit-Style Tests (mocking revoke_google_token)
# =============================================================================

class TestDisconnectRevocationBehavior:
    """Tests for Google token revocation behavior during disconnect."""

    @pytest.mark.asyncio
    async def test_disconnect_calls_revoke_when_refresh_token_exists(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        pg_user_with_connection: dict,
    ):
        """Disconnect calls revoke_google_token when connection has refresh token."""
        user_id = str(pg_user_with_connection["user"].id)

        with patch(
            "backend.apps.priority_guardian.routers.offboarding_router.revoke_google_token",
            new_callable=AsyncMock,
            return_value={"success": True, "error": None},
        ) as mock_revoke:
            response = await client.post(
                "/api/priority-guardian/disconnect",
                headers={"X-User-ID": user_id},
            )

        assert response.status_code == 200
        mock_revoke.assert_called_once()

        # Verify the refresh token was decrypted and passed
        call_kwargs = mock_revoke.call_args.kwargs
        assert "refresh_token" in call_kwargs
        assert call_kwargs["refresh_token"] == "test_refresh_token"

        # Verify response indicates token was revoked
        data = response.json()
        assert data["details"]["google_token_revoked"] is True

    @pytest.mark.asyncio
    async def test_disconnect_succeeds_when_revoke_fails(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        pg_user_with_connection: dict,
    ):
        """Disconnect succeeds even when revoke_google_token fails (best-effort)."""
        user_id = str(pg_user_with_connection["user"].id)

        with patch(
            "backend.apps.priority_guardian.routers.offboarding_router.revoke_google_token",
            new_callable=AsyncMock,
            return_value={"success": False, "error": "Token already revoked"},
        ):
            response = await client.post(
                "/api/priority-guardian/disconnect",
                headers={"X-User-ID": user_id},
            )

        # Disconnect should still succeed
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "disconnected"
        assert data["details"]["google_token_revoked"] is False
        assert data["details"]["google_connection_revoked"] is True

    @pytest.mark.asyncio
    async def test_disconnect_succeeds_when_revoke_raises_exception(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        pg_user_with_connection: dict,
    ):
        """Disconnect succeeds even when revoke_google_token raises exception."""
        user_id = str(pg_user_with_connection["user"].id)

        with patch(
            "backend.apps.priority_guardian.routers.offboarding_router.revoke_google_token",
            new_callable=AsyncMock,
            side_effect=Exception("Network error"),
        ):
            response = await client.post(
                "/api/priority-guardian/disconnect",
                headers={"X-User-ID": user_id},
            )

        # Disconnect should still succeed despite exception
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "disconnected"
        assert data["details"]["google_token_revoked"] is False
        assert data["details"]["google_connection_revoked"] is True

    @pytest.mark.asyncio
    async def test_disconnect_skips_revocation_when_no_refresh_token(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        pg_user_with_connection_no_refresh: dict,
    ):
        """Disconnect skips revocation when no refresh token exists."""
        user_id = str(pg_user_with_connection_no_refresh["user"].id)

        with patch(
            "backend.apps.priority_guardian.routers.offboarding_router.revoke_google_token",
            new_callable=AsyncMock,
        ) as mock_revoke:
            response = await client.post(
                "/api/priority-guardian/disconnect",
                headers={"X-User-ID": user_id},
            )

        assert response.status_code == 200
        # revoke_google_token should NOT be called
        mock_revoke.assert_not_called()

        data = response.json()
        assert data["status"] == "disconnected"
        assert data["details"]["google_token_revoked"] is False
        assert data["details"]["google_connection_revoked"] is True

    @pytest.mark.asyncio
    async def test_disconnect_skips_revocation_when_no_connection(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        pg_user: CoreUser,
    ):
        """Disconnect skips revocation when no connection exists."""
        user_id = str(pg_user.id)

        with patch(
            "backend.apps.priority_guardian.routers.offboarding_router.revoke_google_token",
            new_callable=AsyncMock,
        ) as mock_revoke:
            response = await client.post(
                "/api/priority-guardian/disconnect",
                headers={"X-User-ID": user_id},
            )

        assert response.status_code == 200
        # revoke_google_token should NOT be called
        mock_revoke.assert_not_called()

        data = response.json()
        assert data["status"] == "disconnected"
        assert data["details"]["google_token_revoked"] is False
        assert data["details"]["google_connection_revoked"] is False


# =============================================================================
# Integration Tests (mocking Google API response)
# =============================================================================

class TestDisconnectIntegration:
    """Integration tests for full disconnect flow."""

    @pytest.mark.asyncio
    async def test_full_disconnect_with_google_revoke_success(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        pg_user_with_tokens: dict,
    ):
        """Full disconnect flow with mocked Google revoke endpoint returning 200."""
        user = pg_user_with_tokens["user"]
        connection = pg_user_with_tokens["connection"]
        user_id = str(user.id)

        with patch(
            "backend.apps.priority_guardian.routers.offboarding_router.revoke_google_token",
            new_callable=AsyncMock,
            return_value={"success": True, "error": None},
        ):
            response = await client.post(
                "/api/priority-guardian/disconnect",
                headers={"X-User-ID": user_id},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "disconnected"
        assert data["already_disconnected"] is False
        assert data["details"]["google_token_revoked"] is True
        assert data["details"]["google_connection_revoked"] is True
        assert data["details"]["pg_tokens_revoked"] == 2

        # Verify connection is marked as revoked in DB
        await async_session.refresh(connection)
        assert connection.revoked_at is not None

    @pytest.mark.asyncio
    async def test_full_disconnect_with_google_revoke_already_revoked(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        pg_user_with_tokens: dict,
    ):
        """Full disconnect flow with mocked Google revoke returning 400 (already revoked)."""
        user = pg_user_with_tokens["user"]
        connection = pg_user_with_tokens["connection"]
        user_id = str(user.id)

        # Google returns 400 when token is already revoked
        with patch(
            "backend.apps.priority_guardian.routers.offboarding_router.revoke_google_token",
            new_callable=AsyncMock,
            return_value={"success": False, "error": "invalid_token"},
        ):
            response = await client.post(
                "/api/priority-guardian/disconnect",
                headers={"X-User-ID": user_id},
            )

        # Disconnect should still succeed
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "disconnected"
        assert data["already_disconnected"] is False
        assert data["details"]["google_token_revoked"] is False
        assert data["details"]["google_connection_revoked"] is True
        assert data["details"]["pg_tokens_revoked"] == 2

        # Verify connection is marked as revoked in DB
        await async_session.refresh(connection)
        assert connection.revoked_at is not None

    @pytest.mark.asyncio
    async def test_disconnect_idempotent(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        pg_user_with_connection: dict,
    ):
        """Disconnect is idempotent - second call returns already_disconnected."""
        user_id = str(pg_user_with_connection["user"].id)

        # First disconnect
        with patch(
            "backend.apps.priority_guardian.routers.offboarding_router.revoke_google_token",
            new_callable=AsyncMock,
            return_value={"success": True, "error": None},
        ):
            response1 = await client.post(
                "/api/priority-guardian/disconnect",
                headers={"X-User-ID": user_id},
            )

        assert response1.status_code == 200
        assert response1.json()["already_disconnected"] is False

        # Second disconnect (should NOT call revoke_google_token)
        with patch(
            "backend.apps.priority_guardian.routers.offboarding_router.revoke_google_token",
            new_callable=AsyncMock,
        ) as mock_revoke:
            response2 = await client.post(
                "/api/priority-guardian/disconnect",
                headers={"X-User-ID": user_id},
            )

        assert response2.status_code == 200
        assert response2.json()["already_disconnected"] is True
        # Should not call revoke on already-disconnected user
        mock_revoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_disconnect_user_not_found(
        self,
        client: AsyncClient,
    ):
        """Disconnect returns 404 for non-existent user."""
        fake_user_id = str(uuid4())

        response = await client.post(
            "/api/priority-guardian/disconnect",
            headers={"X-User-ID": fake_user_id},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "User not found"

    @pytest.mark.asyncio
    async def test_disconnect_missing_header(
        self,
        client: AsyncClient,
    ):
        """Disconnect returns 422 when X-User-ID header is missing."""
        response = await client.post("/api/priority-guardian/disconnect")

        assert response.status_code == 422


# =============================================================================
# Decrypt Token Error Handling
# =============================================================================

class TestDisconnectDecryptionErrors:
    """Tests for handling decryption errors during disconnect."""

    @pytest.mark.asyncio
    async def test_disconnect_succeeds_when_decrypt_fails(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        pg_user_with_connection: dict,
    ):
        """Disconnect succeeds even when token decryption fails."""
        user_id = str(pg_user_with_connection["user"].id)
        connection = pg_user_with_connection["connection"]

        with patch(
            "backend.apps.priority_guardian.routers.offboarding_router.decrypt_token",
            side_effect=Exception("Decryption failed - corrupted data"),
        ):
            response = await client.post(
                "/api/priority-guardian/disconnect",
                headers={"X-User-ID": user_id},
            )

        # Disconnect should still succeed despite decryption failure
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "disconnected"
        assert data["details"]["google_token_revoked"] is False
        assert data["details"]["google_connection_revoked"] is True

        # Verify connection is still marked as revoked
        await async_session.refresh(connection)
        assert connection.revoked_at is not None


# =============================================================================
# DB State Verification Tests
# =============================================================================

class TestDisconnectDBStateVerification:
    """
    Tests verifying actual DB state after disconnect (not just API responses).

    These tests use raw SQL SELECTs to verify PostgreSQL state directly.
    """

    @pytest.mark.asyncio
    async def test_disconnect_sets_revoked_at_on_connection_in_db(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        pg_user_with_connection: dict,
    ):
        """5a. Disconnect sets revoked_at on connection (verified via raw SQL)."""
        from sqlalchemy import text

        user = pg_user_with_connection["user"]
        user_id = str(user.id)

        # Verify revoked_at is NULL before disconnect
        result = await async_session.execute(
            text("""
                SELECT revoked_at
                FROM core_connections
                WHERE user_id = :uid AND provider = 'google'
            """),
            {"uid": user.id},
        )
        row = result.fetchone()
        assert row is not None, "Connection should exist"
        assert row[0] is None, "revoked_at should be NULL before disconnect"

        with patch(
            "backend.apps.priority_guardian.routers.offboarding_router.revoke_google_token",
            new_callable=AsyncMock,
            return_value={"success": True, "error": None},
        ):
            response = await client.post(
                "/api/priority-guardian/disconnect",
                headers={"X-User-ID": user_id},
            )

        assert response.status_code == 200

        # Verify revoked_at is NOT NULL after disconnect (via raw SQL)
        result = await async_session.execute(
            text("""
                SELECT revoked_at
                FROM core_connections
                WHERE user_id = :uid AND provider = 'google'
            """),
            {"uid": user.id},
        )
        row = result.fetchone()
        assert row is not None, "Connection should still exist"
        assert row[0] is not None, "revoked_at should be set after disconnect"

    @pytest.mark.asyncio
    async def test_disconnect_revokes_pg_oauth_tokens_in_db(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        pg_user_with_tokens: dict,
    ):
        """5b. Disconnect revokes PG OAuth tokens (verified via raw SQL)."""
        from sqlalchemy import text

        user = pg_user_with_tokens["user"]
        user_id = str(user.id)

        # Verify tokens are NOT revoked before disconnect
        result = await async_session.execute(
            text("""
                SELECT COUNT(*)
                FROM oauth_access_tokens
                WHERE user_id = :uid AND 'pg.access' = ANY(scope) AND revoked = false
            """),
            {"uid": user.id},
        )
        unrevoked_count = result.scalar()
        assert unrevoked_count == 2, "Should have 2 unrevoked PG tokens before disconnect"

        with patch(
            "backend.apps.priority_guardian.routers.offboarding_router.revoke_google_token",
            new_callable=AsyncMock,
            return_value={"success": True, "error": None},
        ):
            response = await client.post(
                "/api/priority-guardian/disconnect",
                headers={"X-User-ID": user_id},
            )

        assert response.status_code == 200

        # Verify all PG tokens are revoked after disconnect
        result = await async_session.execute(
            text("""
                SELECT COUNT(*)
                FROM oauth_access_tokens
                WHERE user_id = :uid AND 'pg.access' = ANY(scope) AND revoked = false
            """),
            {"uid": user.id},
        )
        unrevoked_count = result.scalar()
        assert unrevoked_count == 0, "All PG tokens should be revoked after disconnect"

        # Verify tokens still exist (just marked as revoked, not deleted)
        result = await async_session.execute(
            text("""
                SELECT COUNT(*)
                FROM oauth_access_tokens
                WHERE user_id = :uid AND 'pg.access' = ANY(scope) AND revoked = true
            """),
            {"uid": user.id},
        )
        revoked_count = result.scalar()
        assert revoked_count == 2, "Tokens should be marked revoked, not deleted"

    @pytest.mark.asyncio
    async def test_disconnect_preserves_priority_data_in_db(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        pg_user_with_connection: dict,
    ):
        """5c. Disconnect preserves priority data (not deleted)."""
        from sqlalchemy import text
        from datetime import date, timedelta
        from decimal import Decimal
        from backend.apps.priority_guardian.db_models import PgPriority, PgDeliverable

        user = pg_user_with_connection["user"]
        user_id = str(user.id)

        # Create priorities and deliverables for this user
        priority = PgPriority(
            user_id=user.id,
            name="Test Priority",
            type="deadline",
            calendar_keyword="P1",
            status="active",
            deadline=date.today() + timedelta(days=30),
        )
        async_session.add(priority)
        await async_session.flush()

        deliverable = PgDeliverable(
            priority_id=priority.id,
            name="Test Deliverable",
            done=False,
        )
        async_session.add(deliverable)
        await async_session.commit()

        # Verify data exists before disconnect
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_priorities WHERE user_id = :uid"),
            {"uid": user.id},
        )
        assert result.scalar() == 1

        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_deliverables WHERE priority_id = :pid"),
            {"pid": priority.id},
        )
        assert result.scalar() == 1

        with patch(
            "backend.apps.priority_guardian.routers.offboarding_router.revoke_google_token",
            new_callable=AsyncMock,
            return_value={"success": True, "error": None},
        ):
            response = await client.post(
                "/api/priority-guardian/disconnect",
                headers={"X-User-ID": user_id},
            )

        assert response.status_code == 200

        # Verify priority data is PRESERVED after disconnect
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_priorities WHERE user_id = :uid"),
            {"uid": user.id},
        )
        assert result.scalar() == 1, "Priority should be preserved after disconnect"

        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_deliverables WHERE priority_id = :pid"),
            {"pid": priority.id},
        )
        assert result.scalar() == 1, "Deliverable should be preserved after disconnect"

    @pytest.mark.asyncio
    async def test_disconnect_preserves_snapshots_in_db(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        pg_user_with_connection: dict,
    ):
        """5d. Disconnect preserves snapshot data (not deleted)."""
        from sqlalchemy import text
        from datetime import date, datetime, timedelta
        from decimal import Decimal
        from backend.apps.priority_guardian.db_models import PgPriority

        user = pg_user_with_connection["user"]
        user_id = str(user.id)

        # Create priority
        priority = PgPriority(
            user_id=user.id,
            name="Test Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date.today() + timedelta(days=30),
            created_at=datetime(2026, 1, 1),  # Predate test weeks
        )
        async_session.add(priority)
        await async_session.flush()

        # Insert snapshot directly via SQL
        await async_session.execute(
            text("""
                INSERT INTO pg_weekly_snapshots
                (id, priority_id, user_id, week_start, week_end, actual_hours, target_hours, streak_at_snapshot)
                VALUES (gen_random_uuid(), :pid, :uid, '2026-01-19', '2026-01-25', 5.0, 10.0, 1)
            """),
            {"pid": priority.id, "uid": user.id},
        )
        await async_session.commit()

        # Verify snapshot exists before disconnect
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_weekly_snapshots WHERE user_id = :uid"),
            {"uid": user.id},
        )
        assert result.scalar() == 1

        with patch(
            "backend.apps.priority_guardian.routers.offboarding_router.revoke_google_token",
            new_callable=AsyncMock,
            return_value={"success": True, "error": None},
        ):
            response = await client.post(
                "/api/priority-guardian/disconnect",
                headers={"X-User-ID": user_id},
            )

        assert response.status_code == 200

        # Verify snapshot is PRESERVED after disconnect
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_weekly_snapshots WHERE user_id = :uid"),
            {"uid": user.id},
        )
        assert result.scalar() == 1, "Snapshot should be preserved after disconnect"

    @pytest.mark.asyncio
    async def test_double_disconnect_is_idempotent_in_db(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        pg_user_with_tokens: dict,
    ):
        """5e. Double disconnect is idempotent - DB state unchanged between calls."""
        from sqlalchemy import text

        user = pg_user_with_tokens["user"]
        user_id = str(user.id)

        # First disconnect
        with patch(
            "backend.apps.priority_guardian.routers.offboarding_router.revoke_google_token",
            new_callable=AsyncMock,
            return_value={"success": True, "error": None},
        ):
            response1 = await client.post(
                "/api/priority-guardian/disconnect",
                headers={"X-User-ID": user_id},
            )

        assert response1.status_code == 200
        assert response1.json()["already_disconnected"] is False

        # Capture DB state after first disconnect
        result = await async_session.execute(
            text("""
                SELECT revoked_at
                FROM core_connections
                WHERE user_id = :uid AND provider = 'google'
            """),
            {"uid": user.id},
        )
        revoked_at_after_first = result.fetchone()[0]

        result = await async_session.execute(
            text("""
                SELECT COUNT(*)
                FROM oauth_access_tokens
                WHERE user_id = :uid AND 'pg.access' = ANY(scope) AND revoked = true
            """),
            {"uid": user.id},
        )
        revoked_tokens_after_first = result.scalar()

        # Second disconnect
        with patch(
            "backend.apps.priority_guardian.routers.offboarding_router.revoke_google_token",
            new_callable=AsyncMock,
        ) as mock_revoke:
            response2 = await client.post(
                "/api/priority-guardian/disconnect",
                headers={"X-User-ID": user_id},
            )

        assert response2.status_code == 200
        assert response2.json()["already_disconnected"] is True
        mock_revoke.assert_not_called()  # Should not try to revoke again

        # Verify DB state is UNCHANGED after second disconnect
        result = await async_session.execute(
            text("""
                SELECT revoked_at
                FROM core_connections
                WHERE user_id = :uid AND provider = 'google'
            """),
            {"uid": user.id},
        )
        revoked_at_after_second = result.fetchone()[0]

        result = await async_session.execute(
            text("""
                SELECT COUNT(*)
                FROM oauth_access_tokens
                WHERE user_id = :uid AND 'pg.access' = ANY(scope) AND revoked = true
            """),
            {"uid": user.id},
        )
        revoked_tokens_after_second = result.scalar()

        # DB state should be identical
        assert revoked_at_after_first == revoked_at_after_second, \
            "revoked_at should not change on second disconnect"
        assert revoked_tokens_after_first == revoked_tokens_after_second, \
            "Token revocation count should not change on second disconnect"
