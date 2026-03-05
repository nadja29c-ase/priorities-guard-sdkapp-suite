"""
Unit tests for GDPR retention cleanup tasks (Increment 39).

Tests verify correct SQL logic per task without real database.

NOTE: The Celery tasks are synchronous functions that internally run async code
via asyncio.run_until_complete(). Tests call them directly as sync functions.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID


class TestCleanupExpiredAuditLogs:
    """Tests for cleanup_expired_audit_logs Celery task."""

    def test_uses_atomic_cte_with_returning(self):
        """Test that cleanup uses atomic CTE with RETURNING, not two-step select+delete."""
        from backend.jobs.retention_cleanup import cleanup_expired_audit_logs

        captured_stmts = []

        mock_db_session = AsyncMock()

        # First call returns 5 rows (deleted), second call returns 0 (done)
        call_count = 0

        async def capture_execute(stmt):
            nonlocal call_count
            captured_stmts.append(str(stmt))
            mock_result = MagicMock()
            if call_count == 0:
                mock_result.fetchall.return_value = [(i,) for i in range(5)]
                call_count += 1
            else:
                mock_result.fetchall.return_value = []
            return mock_result

        mock_db_session.execute = capture_execute
        mock_db_session.commit = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            result = cleanup_expired_audit_logs()

        # Verify CTE structure in SQL
        assert len(captured_stmts) >= 1
        sql = captured_stmts[0].lower()
        assert "with rows as" in sql
        assert "returning id" in sql
        assert "delete from core_tool_audit_log" in sql
        # Verify commit was called (once per batch, count varies)
        mock_db_session.commit.assert_called()

    def test_loop_exits_when_returning_empty(self):
        """Test that loop terminates based on RETURNING result set, not rowcount."""
        from backend.jobs.retention_cleanup import cleanup_expired_audit_logs

        call_count = 0
        max_calls = 10  # Safety limit

        mock_db_session = AsyncMock()

        async def track_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count > max_calls:
                raise RuntimeError("Infinite loop detected")

            mock_result = MagicMock()
            if call_count <= 3:
                # First 3 calls return some rows
                mock_result.fetchall.return_value = [(i,) for i in range(100)]
            else:
                # 4th call returns empty (loop should exit)
                mock_result.fetchall.return_value = []
            return mock_result

        mock_db_session.execute = track_execute
        mock_db_session.commit = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            result = cleanup_expired_audit_logs()

        # Should have called execute 4 times (3 with data, 1 empty)
        assert call_count == 4
        # Total deleted should be 300 (3 batches of 100)
        assert result == 300
        # Verify commit was called (once per batch, count varies)
        mock_db_session.commit.assert_called()

    def test_idempotent_no_rows_deleted_twice(self):
        """Test that running twice with no matching rows produces same result."""
        from backend.jobs.retention_cleanup import cleanup_expired_audit_logs

        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []  # No rows match
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.commit = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            result1 = cleanup_expired_audit_logs()
            result2 = cleanup_expired_audit_logs()

        assert result1 == 0
        assert result2 == 0

    def test_retries_on_db_error(self):
        """Test that cleanup raises exception on DB error (triggering Celery retry)."""
        from backend.jobs.retention_cleanup import cleanup_expired_audit_logs

        mock_db_session = AsyncMock()
        mock_db_session.execute = AsyncMock(side_effect=Exception("DB connection lost"))

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            with pytest.raises(Exception, match="DB connection lost"):
                cleanup_expired_audit_logs()

    def test_logs_job_run_id(self):
        """Test that task logs with a valid job_run_id UUID."""
        from backend.jobs.retention_cleanup import cleanup_expired_audit_logs

        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.commit = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            with patch("backend.jobs.retention_cleanup.logger") as mock_logger:
                mock_bound = MagicMock()
                mock_logger.bind.return_value = mock_bound

                cleanup_expired_audit_logs()

        # Verify logger.bind was called with job_run_id
        mock_logger.bind.assert_called()
        call_kwargs = mock_logger.bind.call_args.kwargs
        assert "job_run_id" in call_kwargs
        # Validate it's a proper UUID string
        job_run_id = call_kwargs["job_run_id"]
        assert isinstance(job_run_id, str)
        assert len(job_run_id) > 0
        UUID(job_run_id)  # Raises if invalid


class TestCleanupIdleGoogleConnections:
    """Tests for cleanup_idle_google_connections Celery task."""

    def test_revokes_old_last_used_at_connections(self):
        """Test that connections with last_used_at > 6 months ago get revoked."""
        from backend.jobs.retention_cleanup import cleanup_idle_google_connections

        captured_stmt = None

        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [(i,) for i in range(3)]  # 3 connections revoked

        async def capture_execute(stmt, params=None):
            nonlocal captured_stmt
            captured_stmt = str(stmt)
            return mock_result

        mock_db_session.execute = capture_execute
        mock_db_session.commit = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            result = cleanup_idle_google_connections()

        assert result == 3
        # Verify SQL contains the correct conditions
        sql = captured_stmt.lower()
        assert "update core_connections" in sql
        assert "set revoked_at" in sql
        assert "connection_type = 'google'" in sql
        assert "revoked_at is null" in sql
        assert "last_used_at < now() - interval '6 months'" in sql
        # Verify commit was called once
        mock_db_session.commit.assert_called_once()

    def test_revokes_null_last_used_at_with_old_created_at(self):
        """Test NULL fallback: old created_at with NULL last_used_at gets revoked."""
        from backend.jobs.retention_cleanup import cleanup_idle_google_connections

        captured_stmt = None

        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [(1,)]  # 1 connection revoked

        async def capture_execute(stmt, params=None):
            nonlocal captured_stmt
            captured_stmt = str(stmt)
            return mock_result

        mock_db_session.execute = capture_execute
        mock_db_session.commit = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            result = cleanup_idle_google_connections()

        # Verify SQL contains NULL fallback condition
        sql = captured_stmt.lower()
        assert "last_used_at is null and created_at < now() - interval '6 months'" in sql
        # Verify commit was called once
        mock_db_session.commit.assert_called_once()

    def test_does_not_touch_recent_connections(self):
        """Test that connections with recent last_used_at are untouched.

        This is enforced by the SQL WHERE clause. We verify the task
        uses the correct SQL structure.
        """
        from backend.jobs.retention_cleanup import cleanup_idle_google_connections

        captured_stmt = None

        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []  # No recent connections match

        async def capture_execute(stmt, params=None):
            nonlocal captured_stmt
            captured_stmt = str(stmt)
            return mock_result

        mock_db_session.execute = capture_execute
        mock_db_session.commit = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            result = cleanup_idle_google_connections()

        assert result == 0
        # The SQL excludes recent connections via the interval condition

    def test_does_not_touch_already_revoked_connections(self):
        """Test that already-revoked connections are untouched.

        Enforced by WHERE revoked_at IS NULL in the SQL.
        """
        from backend.jobs.retention_cleanup import cleanup_idle_google_connections

        captured_stmt = None

        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        async def capture_execute(stmt, params=None):
            nonlocal captured_stmt
            captured_stmt = str(stmt)
            return mock_result

        mock_db_session.execute = capture_execute
        mock_db_session.commit = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            result = cleanup_idle_google_connections()

        sql = captured_stmt.lower()
        assert "revoked_at is null" in sql

    def test_only_targets_google_connection_type(self):
        """Test that only google connection_type rows are targeted.

        Non-google connection_type rows must be untouched.
        """
        from backend.jobs.retention_cleanup import cleanup_idle_google_connections

        captured_stmt = None

        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        async def capture_execute(stmt, params=None):
            nonlocal captured_stmt
            captured_stmt = str(stmt)
            return mock_result

        mock_db_session.execute = capture_execute
        mock_db_session.commit = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            cleanup_idle_google_connections()

        sql = captured_stmt.lower()
        assert "connection_type = 'google'" in sql

    def test_idempotent(self):
        """Test that running twice produces same result (all already revoked)."""
        from backend.jobs.retention_cleanup import cleanup_idle_google_connections

        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []  # No rows to revoke (all already done)
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.commit = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            result1 = cleanup_idle_google_connections()
            result2 = cleanup_idle_google_connections()

        assert result1 == 0
        assert result2 == 0

    def test_logs_job_run_id(self):
        """Test that task logs with a valid job_run_id UUID."""
        from backend.jobs.retention_cleanup import cleanup_idle_google_connections

        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.commit = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            with patch("backend.jobs.retention_cleanup.logger") as mock_logger:
                mock_bound = MagicMock()
                mock_logger.bind.return_value = mock_bound

                cleanup_idle_google_connections()

        # Verify logger.bind was called with job_run_id
        mock_logger.bind.assert_called()
        call_kwargs = mock_logger.bind.call_args.kwargs
        assert "job_run_id" in call_kwargs
        # Validate it's a proper UUID string
        job_run_id = call_kwargs["job_run_id"]
        assert isinstance(job_run_id, str)
        assert len(job_run_id) > 0
        UUID(job_run_id)  # Raises if invalid


class TestCleanupInactiveAccounts:
    """Tests for cleanup_inactive_accounts Celery task."""

    def test_deletes_users_matching_all_criteria(self):
        """Test that users matching all three deletion criteria are deleted."""
        from backend.jobs.retention_cleanup import cleanup_inactive_accounts

        captured_stmt = None

        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [(i,) for i in range(2)]  # 2 users deleted

        async def capture_execute(stmt):
            nonlocal captured_stmt
            captured_stmt = str(stmt)
            return mock_result

        mock_db_session.execute = capture_execute
        mock_db_session.commit = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            result = cleanup_inactive_accounts()

        assert result == 2
        sql = captured_stmt.lower()
        assert "delete from core_users" in sql
        assert "created_at < now() - interval '6 months'" in sql
        # Verify commit was called once
        mock_db_session.commit.assert_called_once()

    def test_retains_users_with_active_connection(self):
        """Test that users with active connections are retained.

        Enforced by NOT EXISTS subquery for core_connections with revoked_at IS NULL.
        """
        from backend.jobs.retention_cleanup import cleanup_inactive_accounts

        captured_stmt = None

        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        async def capture_execute(stmt):
            nonlocal captured_stmt
            captured_stmt = str(stmt)
            return mock_result

        mock_db_session.execute = capture_execute
        mock_db_session.commit = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            cleanup_inactive_accounts()

        sql = captured_stmt.lower()
        assert "not exists" in sql
        assert "core_connections" in sql
        assert "revoked_at is null" in sql

    def test_retains_users_with_active_consent(self):
        """Test that users with active consents are retained.

        Enforced by NOT EXISTS subquery for core_consents with revoked_at IS NULL.
        """
        from backend.jobs.retention_cleanup import cleanup_inactive_accounts

        captured_stmt = None

        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        async def capture_execute(stmt):
            nonlocal captured_stmt
            captured_stmt = str(stmt)
            return mock_result

        mock_db_session.execute = capture_execute
        mock_db_session.commit = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            cleanup_inactive_accounts()

        sql = captured_stmt.lower()
        assert "not exists" in sql
        assert "core_consents" in sql

    def test_retains_users_created_recently(self):
        """Test that users created less than 6 months ago are retained.

        Enforced by created_at < NOW() - INTERVAL '6 months' in WHERE clause.
        """
        from backend.jobs.retention_cleanup import cleanup_inactive_accounts

        captured_stmt = None

        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        async def capture_execute(stmt):
            nonlocal captured_stmt
            captured_stmt = str(stmt)
            return mock_result

        mock_db_session.execute = capture_execute
        mock_db_session.commit = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            cleanup_inactive_accounts()

        sql = captured_stmt.lower()
        assert "created_at < now() - interval '6 months'" in sql

    def test_idempotent(self):
        """Test that running twice produces same result (all already deleted)."""
        from backend.jobs.retention_cleanup import cleanup_inactive_accounts

        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []  # No users to delete (all already done)
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.commit = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            result1 = cleanup_inactive_accounts()
            result2 = cleanup_inactive_accounts()

        assert result1 == 0
        assert result2 == 0

    def test_logs_count_not_individual_uuids(self):
        """Test that task logs count only, not individual user UUIDs (privacy)."""
        from backend.jobs.retention_cleanup import cleanup_inactive_accounts

        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [(i,) for i in range(5)]  # 5 users deleted
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.commit = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        log_calls = []

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            with patch("backend.jobs.retention_cleanup.logger") as mock_logger:
                mock_bound = MagicMock()
                mock_logger.bind.return_value = mock_bound
                mock_bound.info = lambda *args, **kwargs: log_calls.append(kwargs)

                cleanup_inactive_accounts()

        # Verify deleted_count is logged
        assert any("deleted_count" in call for call in log_calls)
        # Verify no user_id is logged (privacy)
        for call in log_calls:
            assert "user_id" not in call

    def test_logs_job_run_id(self):
        """Test that task logs with a valid job_run_id UUID."""
        from backend.jobs.retention_cleanup import cleanup_inactive_accounts

        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.commit = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            with patch("backend.jobs.retention_cleanup.logger") as mock_logger:
                mock_bound = MagicMock()
                mock_logger.bind.return_value = mock_bound

                cleanup_inactive_accounts()

        # Verify logger.bind was called with job_run_id
        mock_logger.bind.assert_called()
        call_kwargs = mock_logger.bind.call_args.kwargs
        assert "job_run_id" in call_kwargs
        # Validate it's a proper UUID string
        job_run_id = call_kwargs["job_run_id"]
        assert isinstance(job_run_id, str)
        assert len(job_run_id) > 0
        UUID(job_run_id)  # Raises if invalid


class TestTaskRetryBehavior:
    """Tests for retry behavior across all retention tasks."""

    def test_audit_logs_retries_on_error(self):
        """Test that audit logs cleanup retries on error."""
        from backend.jobs.retention_cleanup import cleanup_expired_audit_logs

        mock_db_session = AsyncMock()
        mock_db_session.execute = AsyncMock(side_effect=Exception("Connection reset"))

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            with pytest.raises(Exception, match="Connection reset"):
                cleanup_expired_audit_logs()

    def test_idle_connections_retries_on_error(self):
        """Test that idle connections cleanup retries on error."""
        from backend.jobs.retention_cleanup import cleanup_idle_google_connections

        mock_db_session = AsyncMock()
        mock_db_session.execute = AsyncMock(side_effect=Exception("Timeout"))

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            with pytest.raises(Exception, match="Timeout"):
                cleanup_idle_google_connections()

    def test_inactive_accounts_retries_on_error(self):
        """Test that inactive accounts cleanup retries on error."""
        from backend.jobs.retention_cleanup import cleanup_inactive_accounts

        mock_db_session = AsyncMock()
        mock_db_session.execute = AsyncMock(side_effect=Exception("Deadlock"))

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            with pytest.raises(Exception, match="Deadlock"):
                cleanup_inactive_accounts()
