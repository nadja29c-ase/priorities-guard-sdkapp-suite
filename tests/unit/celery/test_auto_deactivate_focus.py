"""
Unit tests for auto_deactivate_focus Celery task (Increment 11).

Tests:
- Task closes open session (sets actual_end)
- Task is idempotent if session already closed
- Task handles session not found (may have been deleted)
- Job status set to completed/failed appropriately
- Invalid UUID handling

NOTE: The Celery tasks are synchronous functions that internally run async code
via asyncio.run_until_complete(). Tests call them directly as sync functions.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


class TestAutoDeactivateFocus:
    """Tests for auto_deactivate_focus Celery task."""

    @pytest.fixture
    def valid_user_id(self):
        return str(uuid4())

    @pytest.fixture
    def valid_session_id(self):
        return str(uuid4())

    @pytest.fixture
    def valid_job_id(self):
        return str(uuid4())

    @pytest.fixture
    def mock_focus_session(self):
        """Create a mock focus session that is active (not deactivated)."""
        session = MagicMock()
        session.id = uuid4()
        session.actual_start = datetime.now(timezone.utc) - timedelta(hours=1)
        session.actual_end = None  # Still active
        return session

    @pytest.fixture
    def mock_deactivated_session(self):
        """Create a mock focus session that is already deactivated."""
        session = MagicMock()
        session.id = uuid4()
        session.actual_start = datetime.now(timezone.utc) - timedelta(hours=2)
        session.actual_end = datetime.now(timezone.utc) - timedelta(hours=1)
        return session

    def test_task_closes_open_session(self, valid_user_id, valid_session_id, valid_job_id, mock_focus_session):
        """Test that task sets actual_end on an active session."""
        from backend.core.celery_app import auto_deactivate_focus

        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_focus_session)
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.commit = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            # Call the task directly - it's a sync function that runs async internally
            result = auto_deactivate_focus(valid_user_id, valid_session_id, valid_job_id)

        assert result["success"] is True
        assert result["status"] == "deactivated"
        assert mock_focus_session.actual_end is not None
        # Verify actual_end is timezone-aware UTC
        assert mock_focus_session.actual_end.tzinfo is not None
        assert mock_focus_session.actual_end.tzinfo.utcoffset(mock_focus_session.actual_end).total_seconds() == 0

    def test_task_idempotent_if_already_closed(self, valid_user_id, valid_session_id, valid_job_id, mock_deactivated_session):
        """Test that task is idempotent if session already has actual_end set."""
        from backend.core.celery_app import auto_deactivate_focus

        original_end_time = mock_deactivated_session.actual_end

        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_deactivated_session)
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.commit = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            result = auto_deactivate_focus(valid_user_id, valid_session_id, valid_job_id)

        assert result["success"] is True
        assert result["status"] == "already_deactivated"
        # actual_end should not have changed
        assert mock_deactivated_session.actual_end == original_end_time

    def test_task_handles_session_not_found(self, valid_user_id, valid_session_id, valid_job_id):
        """Test that task handles missing session gracefully (may have been deleted)."""
        from backend.core.celery_app import auto_deactivate_focus

        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)  # Session not found
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.commit = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            result = auto_deactivate_focus(valid_user_id, valid_session_id, valid_job_id)

        assert result["success"] is True
        assert result["status"] == "session_not_found"
        # Job should still be marked as completed
        mock_db_session.commit.assert_called()

    def test_task_handles_missing_scheduled_job(self, valid_user_id, valid_session_id, valid_job_id, mock_focus_session):
        """Test that task handles missing scheduled job gracefully.

        Scenario: User manually deactivated early, job was cancelled and deleted
        by cleanup, but Celery task fires later. Should not raise exception.
        """
        from backend.core.celery_app import auto_deactivate_focus

        execute_calls = []

        mock_db_session = AsyncMock()

        async def capture_execute(stmt):
            execute_calls.append(stmt)
            mock_result = MagicMock()
            # First call is SELECT for session - found
            if len(execute_calls) == 1:
                mock_result.scalar_one_or_none = MagicMock(return_value=mock_focus_session)
            # Second call is UPDATE for job - rowcount=0 means job not found
            else:
                mock_result.rowcount = 0
            return mock_result

        mock_db_session.execute = capture_execute
        mock_db_session.commit = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            result = auto_deactivate_focus(valid_user_id, valid_session_id, valid_job_id)

        # Should succeed even if job row doesn't exist
        assert result["success"] is True
        # Session was still deactivated
        assert mock_focus_session.actual_end is not None
        # Verify actual_end is timezone-aware UTC
        assert mock_focus_session.actual_end.tzinfo is not None
        assert mock_focus_session.actual_end.tzinfo.utcoffset(mock_focus_session.actual_end).total_seconds() == 0

    def test_task_marks_job_completed_on_success(self, valid_user_id, valid_session_id, valid_job_id, mock_focus_session):
        """Test that scheduled job status is set to 'completed' on success."""
        from backend.core.celery_app import auto_deactivate_focus

        execute_calls = []

        mock_db_session = AsyncMock()

        async def capture_execute(stmt):
            execute_calls.append(stmt)
            mock_result = MagicMock()
            # First call is SELECT, second is UPDATE
            if len(execute_calls) == 1:
                mock_result.scalar_one_or_none = MagicMock(return_value=mock_focus_session)
            return mock_result

        mock_db_session.execute = capture_execute
        mock_db_session.commit = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            result = auto_deactivate_focus(valid_user_id, valid_session_id, valid_job_id)

        assert result["success"] is True
        # Should have called execute twice: once for SELECT, once for UPDATE job status
        assert len(execute_calls) == 2
        # Verify the UPDATE sets status to 'completed'
        assert "completed" in str(execute_calls[1]).lower()

    def test_task_rejects_invalid_user_id_format(self, valid_session_id, valid_job_id):
        """Test that task handles invalid user_id UUID format."""
        from backend.core.celery_app import auto_deactivate_focus

        mock_db_session = AsyncMock()
        mock_db_session.commit = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            result = auto_deactivate_focus("not-a-valid-uuid", valid_session_id, valid_job_id)

        assert result["success"] is False
        assert result["error"] == "invalid_uuid"

    def test_task_rejects_invalid_session_id_format(self, valid_user_id, valid_job_id):
        """Test that task handles invalid session_id UUID format."""
        from backend.core.celery_app import auto_deactivate_focus

        mock_db_session = AsyncMock()
        mock_db_session.commit = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            result = auto_deactivate_focus(valid_user_id, "invalid-uuid", valid_job_id)

        assert result["success"] is False
        assert result["error"] == "invalid_uuid"

    def test_task_rejects_invalid_job_id_format(self, valid_user_id, valid_session_id):
        """Test that task handles invalid job_id UUID format."""
        from backend.core.celery_app import auto_deactivate_focus

        mock_db_session = AsyncMock()
        mock_db_session.commit = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            result = auto_deactivate_focus(valid_user_id, valid_session_id, "invalid-job-id")

        assert result["success"] is False
        assert result["error"] == "invalid_uuid"

    def test_task_retries_on_db_error(self, valid_user_id, valid_session_id, valid_job_id):
        """Test that task raises exception on DB error (triggering Celery retry)."""
        from backend.core.celery_app import auto_deactivate_focus

        mock_db_session = AsyncMock()
        mock_db_session.execute = AsyncMock(side_effect=Exception("DB connection lost"))
        mock_db_session.commit = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_db_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("backend.core.database.AsyncSessionLocal", return_value=mock_context):
            # Should raise (which triggers Celery retry mechanism)
            with pytest.raises(Exception, match="DB connection lost"):
                auto_deactivate_focus(valid_user_id, valid_session_id, valid_job_id)
