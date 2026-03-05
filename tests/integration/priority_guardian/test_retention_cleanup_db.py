"""
DB-level integration tests for GDPR retention cleanup tasks (Increment 39).

These tests verify actual PostgreSQL behavior against a real test database:
- Migration creates last_used_at column and indexes
- Cleanup tasks operate correctly on real data
- CASCADE DELETE propagates correctly
- Audit log independence from user deletion

All tests use real test PostgreSQL - no DB mocking.
"""

import pytest
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.models import CoreUser, CoreConnection, CoreConsent, CoreToolAuditLog
from backend.apps.priority_guardian.db_models import PgPriority, PgGoal, PgWeeklySnapshot


# =============================================================================
# Section 1: Migration Integrity Tests
# =============================================================================


class TestMigrationIntegrity:
    """Verify migration creates correct schema."""

    @pytest.mark.asyncio
    async def test_last_used_at_column_exists(self, async_session: AsyncSession):
        """After upgrade: last_used_at column exists on core_connections, is nullable."""
        result = await async_session.execute(
            text("""
                SELECT column_name, is_nullable, data_type
                FROM information_schema.columns
                WHERE table_name = 'core_connections'
                AND column_name = 'last_used_at'
            """)
        )
        row = result.fetchone()
        assert row is not None, "last_used_at column should exist"
        assert row[1] == "YES", "last_used_at should be nullable"
        assert "timestamp" in row[2].lower(), "last_used_at should be timestamp type"

    @pytest.mark.asyncio
    async def test_last_used_at_simple_index_exists(self, async_session: AsyncSession):
        """After upgrade: ix_core_connections_last_used_at index exists."""
        result = await async_session.execute(
            text("""
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'core_connections'
                AND indexname = 'ix_core_connections_last_used_at'
            """)
        )
        row = result.fetchone()
        assert row is not None, "Simple index ix_core_connections_last_used_at should exist"

    @pytest.mark.asyncio
    async def test_partial_index_for_google_active_exists(self, async_session: AsyncSession):
        """After upgrade: ix_core_connections_google_active partial index exists."""
        # Partial indexes are not returned by inspector.get_indexes in all cases
        # Use raw SQL to check
        result = await async_session.execute(
            text("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = 'core_connections'
                AND indexname = 'ix_core_connections_google_active'
            """)
        )
        row = result.fetchone()
        assert row is not None, "Partial index ix_core_connections_google_active should exist"
        # Verify it's a partial index with the correct WHERE clause
        indexdef = row[1].lower()
        assert "where" in indexdef, "Should be a partial index"
        assert "connection_type" in indexdef, "Should filter by connection_type"
        assert "revoked_at is null" in indexdef, "Should filter by revoked_at IS NULL"

    @pytest.mark.asyncio
    async def test_last_used_at_has_no_server_default(self, async_session: AsyncSession):
        """After upgrade: last_used_at has no server default (no backfill)."""
        result = await async_session.execute(
            text("""
                SELECT column_default
                FROM information_schema.columns
                WHERE table_name = 'core_connections'
                AND column_name = 'last_used_at'
            """)
        )
        row = result.fetchone()
        assert row[0] is None, "last_used_at should have no server default"

    @pytest.mark.asyncio
    async def test_pre_existing_connections_have_null_last_used_at(
        self, async_session: AsyncSession
    ):
        """All pre-existing rows have last_used_at = NULL after migration (no backfill)."""
        # Create a user
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Create a connection without setting last_used_at
        await async_session.execute(
            text("""
                INSERT INTO core_connections
                (id, user_id, provider, connection_type, encrypted_access_token,
                 token_expires_at, scopes, provider_metadata)
                VALUES
                (:id, :user_id, 'google', 'google', 'encrypted_token',
                 :expires, ARRAY['calendar.readonly'], '{}')
            """),
            {
                "id": uuid4(),
                "user_id": user.id,
                "expires": datetime.now(timezone.utc) + timedelta(hours=1),
            },
        )
        await async_session.commit()

        # Verify last_used_at is NULL
        result = await async_session.execute(
            text("SELECT last_used_at FROM core_connections WHERE user_id = :uid"),
            {"uid": user.id},
        )
        row = result.fetchone()
        assert row[0] is None, "Pre-existing connection should have NULL last_used_at"


# =============================================================================
# Section 2: Audit Log Cleanup Tests
# =============================================================================


class TestCleanupExpiredAuditLogs:
    """Test cleanup_expired_audit_logs against real database."""

    @pytest.mark.asyncio
    async def test_deletes_old_rows_preserves_recent(self, async_session: AsyncSession):
        """Seed 5 old rows (91 days) and 3 recent rows (30 days), verify correct deletion."""
        # Insert old audit logs (91 days ago)
        old_time = datetime.now(timezone.utc) - timedelta(days=91)
        for i in range(5):
            await async_session.execute(
                text("""
                    INSERT INTO core_tool_audit_log
                    (id, user_id, app_name, action, result_status, created_at)
                    VALUES (:id, :uid, 'test', 'test_action', 'success', :created)
                """),
                {"id": uuid4(), "uid": uuid4(), "created": old_time},
            )

        # Insert recent audit logs (30 days ago)
        recent_time = datetime.now(timezone.utc) - timedelta(days=30)
        for i in range(3):
            await async_session.execute(
                text("""
                    INSERT INTO core_tool_audit_log
                    (id, user_id, app_name, action, result_status, created_at)
                    VALUES (:id, :uid, 'test', 'test_action', 'success', :created)
                """),
                {"id": uuid4(), "uid": uuid4(), "created": recent_time},
            )
        await async_session.commit()

        # Verify initial count
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM core_tool_audit_log")
        )
        assert result.scalar() == 8

        # Run cleanup task
        from backend.jobs.retention_cleanup import cleanup_expired_audit_logs
        deleted = cleanup_expired_audit_logs()

        # Verify correct deletion
        assert deleted == 5, "Should delete 5 old rows"

        result = await async_session.execute(
            text("SELECT COUNT(*) FROM core_tool_audit_log")
        )
        assert result.scalar() == 3, "3 recent rows should remain"

    @pytest.mark.asyncio
    async def test_loop_terminates_on_empty_result(self, async_session: AsyncSession):
        """Verify loop terminates correctly when no rows match (no infinite loop)."""
        # Insert only recent audit logs
        recent_time = datetime.now(timezone.utc) - timedelta(days=30)
        for i in range(3):
            await async_session.execute(
                text("""
                    INSERT INTO core_tool_audit_log
                    (id, user_id, app_name, action, result_status, created_at)
                    VALUES (:id, :uid, 'test', 'test_action', 'success', :created)
                """),
                {"id": uuid4(), "uid": uuid4(), "created": recent_time},
            )
        await async_session.commit()

        # Run cleanup - should complete without hanging
        from backend.jobs.retention_cleanup import cleanup_expired_audit_logs
        deleted = cleanup_expired_audit_logs()

        assert deleted == 0, "Should delete 0 rows when none match"

        # Verify all rows still exist
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM core_tool_audit_log")
        )
        assert result.scalar() == 3


# =============================================================================
# Section 3: Idle Google Connections Cleanup Tests
# =============================================================================


class TestCleanupIdleGoogleConnections:
    """Test cleanup_idle_google_connections against real database."""

    @pytest.mark.asyncio
    async def test_revokes_old_last_used_at_connections(self, async_session: AsyncSession):
        """Connection with last_used_at > 6 months ago gets revoked_at set."""
        # Create user
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Connection with old last_used_at (7 months ago)
        old_time = datetime.now(timezone.utc) - timedelta(days=210)  # ~7 months
        conn_id = uuid4()
        await async_session.execute(
            text("""
                INSERT INTO core_connections
                (id, user_id, provider, connection_type, encrypted_access_token,
                 token_expires_at, scopes, provider_metadata, last_used_at)
                VALUES
                (:id, :user_id, 'google', 'google', 'encrypted_token',
                 :expires, ARRAY['calendar.readonly'], '{}', :last_used)
            """),
            {
                "id": conn_id,
                "user_id": user.id,
                "expires": datetime.now(timezone.utc) + timedelta(hours=1),
                "last_used": old_time,
            },
        )
        await async_session.commit()

        # Run cleanup
        from backend.jobs.retention_cleanup import cleanup_idle_google_connections
        revoked = cleanup_idle_google_connections()

        assert revoked == 1, "Should revoke 1 connection"

        # Verify revoked_at is set
        result = await async_session.execute(
            text("SELECT revoked_at FROM core_connections WHERE id = :id"),
            {"id": conn_id},
        )
        row = result.fetchone()
        assert row[0] is not None, "revoked_at should be set"

    @pytest.mark.asyncio
    async def test_revokes_null_last_used_at_with_old_created_at(
        self, async_session: AsyncSession
    ):
        """Connection with NULL last_used_at and old created_at gets revoked."""
        # Create user
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Connection with NULL last_used_at and old created_at (7 months ago)
        old_time = datetime.now(timezone.utc) - timedelta(days=210)
        conn_id = uuid4()
        await async_session.execute(
            text("""
                INSERT INTO core_connections
                (id, user_id, provider, connection_type, encrypted_access_token,
                 token_expires_at, scopes, provider_metadata, created_at, last_used_at)
                VALUES
                (:id, :user_id, 'google', 'google', 'encrypted_token',
                 :expires, ARRAY['calendar.readonly'], '{}', :created, NULL)
            """),
            {
                "id": conn_id,
                "user_id": user.id,
                "expires": datetime.now(timezone.utc) + timedelta(hours=1),
                "created": old_time,
            },
        )
        await async_session.commit()

        # Run cleanup
        from backend.jobs.retention_cleanup import cleanup_idle_google_connections
        revoked = cleanup_idle_google_connections()

        assert revoked == 1, "Should revoke 1 connection with NULL fallback"

    @pytest.mark.asyncio
    async def test_does_not_touch_recent_connections(self, async_session: AsyncSession):
        """Connection with recent last_used_at is untouched."""
        # Create user
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Connection with recent last_used_at (1 week ago)
        recent_time = datetime.now(timezone.utc) - timedelta(days=7)
        conn_id = uuid4()
        await async_session.execute(
            text("""
                INSERT INTO core_connections
                (id, user_id, provider, connection_type, encrypted_access_token,
                 token_expires_at, scopes, provider_metadata, last_used_at)
                VALUES
                (:id, :user_id, 'google', 'google', 'encrypted_token',
                 :expires, ARRAY['calendar.readonly'], '{}', :last_used)
            """),
            {
                "id": conn_id,
                "user_id": user.id,
                "expires": datetime.now(timezone.utc) + timedelta(hours=1),
                "last_used": recent_time,
            },
        )
        await async_session.commit()

        # Run cleanup
        from backend.jobs.retention_cleanup import cleanup_idle_google_connections
        revoked = cleanup_idle_google_connections()

        assert revoked == 0, "Should not revoke recent connection"

        # Verify revoked_at is still NULL
        result = await async_session.execute(
            text("SELECT revoked_at FROM core_connections WHERE id = :id"),
            {"id": conn_id},
        )
        row = result.fetchone()
        assert row[0] is None, "revoked_at should still be NULL"

    @pytest.mark.asyncio
    async def test_does_not_touch_already_revoked_connections(
        self, async_session: AsyncSession
    ):
        """Already-revoked connections are untouched."""
        # Create user
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Already revoked connection (old last_used_at but already revoked)
        old_time = datetime.now(timezone.utc) - timedelta(days=210)
        revoke_time = datetime.now(timezone.utc) - timedelta(days=30)
        conn_id = uuid4()
        await async_session.execute(
            text("""
                INSERT INTO core_connections
                (id, user_id, provider, connection_type, encrypted_access_token,
                 token_expires_at, scopes, provider_metadata, last_used_at, revoked_at)
                VALUES
                (:id, :user_id, 'google', 'google', 'encrypted_token',
                 :expires, ARRAY['calendar.readonly'], '{}', :last_used, :revoked)
            """),
            {
                "id": conn_id,
                "user_id": user.id,
                "expires": datetime.now(timezone.utc) + timedelta(hours=1),
                "last_used": old_time,
                "revoked": revoke_time,
            },
        )
        await async_session.commit()

        # Run cleanup
        from backend.jobs.retention_cleanup import cleanup_idle_google_connections
        revoked = cleanup_idle_google_connections()

        assert revoked == 0, "Should not touch already-revoked connection"


# =============================================================================
# Section 4: Inactive Accounts Cleanup Tests
# =============================================================================


class TestCleanupInactiveAccounts:
    """Test cleanup_inactive_accounts against real database."""

    @pytest.mark.asyncio
    async def test_deletes_fully_inactive_user_with_cascade(
        self, async_session: AsyncSession
    ):
        """
        Fully inactive user (created 7 months ago, no active connection/consent)
        is deleted with all dependent data.
        """
        # Create inactive user (7 months old)
        user_id = uuid4()
        old_time = datetime.now(timezone.utc) - timedelta(days=210)
        await async_session.execute(
            text("INSERT INTO core_users (id, created_at) VALUES (:id, :created)"),
            {"id": user_id, "created": old_time},
        )

        # Add revoked connection (not active)
        conn_id = uuid4()
        await async_session.execute(
            text("""
                INSERT INTO core_connections
                (id, user_id, provider, connection_type, encrypted_access_token,
                 token_expires_at, scopes, provider_metadata, revoked_at)
                VALUES
                (:id, :user_id, 'google', 'google', 'encrypted_token',
                 :expires, ARRAY['calendar.readonly'], '{}', :revoked)
            """),
            {
                "id": conn_id,
                "user_id": user_id,
                "expires": datetime.now(timezone.utc) + timedelta(hours=1),
                "revoked": datetime.now(timezone.utc) - timedelta(days=30),
            },
        )

        # Add revoked consent (not active)
        await async_session.execute(
            text("""
                INSERT INTO core_consents
                (id, user_id, app_name, scope, revoked_at)
                VALUES (:id, :user_id, 'priority_guardian', 'pg.read', :revoked)
            """),
            {
                "id": uuid4(),
                "user_id": user_id,
                "revoked": datetime.now(timezone.utc) - timedelta(days=30),
            },
        )

        # Add priority and goal for cascade test
        priority_id = uuid4()
        await async_session.execute(
            text("""
                INSERT INTO pg_priorities
                (id, user_id, name, type, calendar_keyword, status,
                 weekly_hour_target, checkpoint_date)
                VALUES
                (:id, :user_id, 'Test', 'flexible', 'P1', 'active',
                 10.0, :checkpoint)
            """),
            {
                "id": priority_id,
                "user_id": user_id,
                "checkpoint": date.today() + timedelta(days=30),
            },
        )

        goal_id = uuid4()
        await async_session.execute(
            text("""
                INSERT INTO pg_goals
                (id, priority_id, goal_text, achieved)
                VALUES (:id, :pid, 'Test goal', false)
            """),
            {"id": goal_id, "pid": priority_id},
        )

        # Add audit log for independence test
        audit_log_id = uuid4()
        await async_session.execute(
            text("""
                INSERT INTO core_tool_audit_log
                (id, user_id, app_name, action, result_status)
                VALUES (:id, :uid, 'test', 'test_action', 'success')
            """),
            {"id": audit_log_id, "uid": user_id},
        )

        await async_session.commit()

        # Run cleanup
        from backend.jobs.retention_cleanup import cleanup_inactive_accounts
        deleted = cleanup_inactive_accounts()

        assert deleted == 1, "Should delete 1 inactive user"

        # Verify user is deleted
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM core_users WHERE id = :id"),
            {"id": user_id},
        )
        assert result.scalar() == 0, "User should be deleted"

        # Verify cascade: priority deleted
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_priorities WHERE id = :id"),
            {"id": priority_id},
        )
        assert result.scalar() == 0, "Priority should be cascade deleted"

        # Verify cascade: goal deleted
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_goals WHERE id = :id"),
            {"id": goal_id},
        )
        assert result.scalar() == 0, "Goal should be cascade deleted"

        # Verify audit log STILL EXISTS (independence)
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM core_tool_audit_log WHERE id = :id"),
            {"id": audit_log_id},
        )
        assert result.scalar() == 1, "Audit log should still exist (no FK)"

    @pytest.mark.asyncio
    async def test_retains_user_with_active_connection(self, async_session: AsyncSession):
        """User with active connection (revoked_at IS NULL) is retained."""
        # Create old user (7 months)
        user_id = uuid4()
        old_time = datetime.now(timezone.utc) - timedelta(days=210)
        await async_session.execute(
            text("INSERT INTO core_users (id, created_at) VALUES (:id, :created)"),
            {"id": user_id, "created": old_time},
        )

        # Add ACTIVE connection (revoked_at IS NULL)
        await async_session.execute(
            text("""
                INSERT INTO core_connections
                (id, user_id, provider, connection_type, encrypted_access_token,
                 token_expires_at, scopes, provider_metadata)
                VALUES
                (:id, :user_id, 'google', 'google', 'encrypted_token',
                 :expires, ARRAY['calendar.readonly'], '{}')
            """),
            {
                "id": uuid4(),
                "user_id": user_id,
                "expires": datetime.now(timezone.utc) + timedelta(hours=1),
            },
        )
        await async_session.commit()

        # Run cleanup
        from backend.jobs.retention_cleanup import cleanup_inactive_accounts
        deleted = cleanup_inactive_accounts()

        assert deleted == 0, "Should not delete user with active connection"

        # Verify user still exists
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM core_users WHERE id = :id"),
            {"id": user_id},
        )
        assert result.scalar() == 1, "User should still exist"

    @pytest.mark.asyncio
    async def test_retains_user_with_active_consent(self, async_session: AsyncSession):
        """User with active consent (revoked_at IS NULL) is retained."""
        # Create old user (7 months)
        user_id = uuid4()
        old_time = datetime.now(timezone.utc) - timedelta(days=210)
        await async_session.execute(
            text("INSERT INTO core_users (id, created_at) VALUES (:id, :created)"),
            {"id": user_id, "created": old_time},
        )

        # Add ACTIVE consent (revoked_at IS NULL)
        await async_session.execute(
            text("""
                INSERT INTO core_consents
                (id, user_id, app_name, scope)
                VALUES (:id, :user_id, 'priority_guardian', 'pg.read')
            """),
            {"id": uuid4(), "user_id": user_id},
        )
        await async_session.commit()

        # Run cleanup
        from backend.jobs.retention_cleanup import cleanup_inactive_accounts
        deleted = cleanup_inactive_accounts()

        assert deleted == 0, "Should not delete user with active consent"

    @pytest.mark.asyncio
    async def test_retains_user_created_recently(self, async_session: AsyncSession):
        """User created less than 6 months ago is retained."""
        # Create recent user (1 month ago)
        user_id = uuid4()
        recent_time = datetime.now(timezone.utc) - timedelta(days=30)
        await async_session.execute(
            text("INSERT INTO core_users (id, created_at) VALUES (:id, :created)"),
            {"id": user_id, "created": recent_time},
        )
        await async_session.commit()

        # Run cleanup
        from backend.jobs.retention_cleanup import cleanup_inactive_accounts
        deleted = cleanup_inactive_accounts()

        assert deleted == 0, "Should not delete recently created user"

    @pytest.mark.asyncio
    async def test_task_2_then_task_3_sequence(self, async_session: AsyncSession):
        """
        Run Task 2 (idle connections) then Task 3 (inactive accounts) in sequence.
        Verifies that Task 2 soft-revokes connections before Task 3 checks for deletion.
        """
        # Create old user (7 months)
        user_id = uuid4()
        old_time = datetime.now(timezone.utc) - timedelta(days=210)
        await async_session.execute(
            text("INSERT INTO core_users (id, created_at) VALUES (:id, :created)"),
            {"id": user_id, "created": old_time},
        )

        # Add old Google connection (will be soft-revoked by Task 2)
        conn_id = uuid4()
        await async_session.execute(
            text("""
                INSERT INTO core_connections
                (id, user_id, provider, connection_type, encrypted_access_token,
                 token_expires_at, scopes, provider_metadata, last_used_at)
                VALUES
                (:id, :user_id, 'google', 'google', 'encrypted_token',
                 :expires, ARRAY['calendar.readonly'], '{}', :last_used)
            """),
            {
                "id": conn_id,
                "user_id": user_id,
                "expires": datetime.now(timezone.utc) + timedelta(hours=1),
                "last_used": old_time,
            },
        )
        await async_session.commit()

        # Before Task 2: user has active connection
        result = await async_session.execute(
            text("""
                SELECT COUNT(*) FROM core_connections
                WHERE user_id = :uid AND revoked_at IS NULL
            """),
            {"uid": user_id},
        )
        assert result.scalar() == 1, "Should have 1 active connection before Task 2"

        # Run Task 2: soft-revoke idle connections
        from backend.jobs.retention_cleanup import cleanup_idle_google_connections
        revoked = cleanup_idle_google_connections()
        assert revoked == 1, "Task 2 should revoke 1 connection"

        # After Task 2: no active connections
        result = await async_session.execute(
            text("""
                SELECT COUNT(*) FROM core_connections
                WHERE user_id = :uid AND revoked_at IS NULL
            """),
            {"uid": user_id},
        )
        assert result.scalar() == 0, "Should have 0 active connections after Task 2"

        # Run Task 3: delete inactive accounts
        from backend.jobs.retention_cleanup import cleanup_inactive_accounts
        deleted = cleanup_inactive_accounts()
        assert deleted == 1, "Task 3 should delete 1 user"

        # Verify user is deleted
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM core_users WHERE id = :id"),
            {"id": user_id},
        )
        assert result.scalar() == 0, "User should be deleted after Task 2 + Task 3 sequence"
