"""
Unit tests for auto_deactivate_focus Celery task (Increment 11).

Tests:
- Task closes open session (sets actual_end)
- Task is idempotent if session already closed
- Task handles session not found (may have been deleted)
- Job status set to completed/failed appropriately
- Invalid UUID handling
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

        with patch("backend.core.celery_app.AsyncSessionLocal") as mock_session_local:
            mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
            mock_session_local.return_value.__aexit__ = AsyncMock(return_value=None)

            result = auto_deactivate_focus(valid_user_id, valid_session_id, valid_job_id)

        assert result["success"] is True
        assert result["status"] == "deactivated"
        assert mock_focus_session.actual_end is not None

    def test_task_idempotent_if_already_closed(self, valid_user_id, valid_session_id, valid_job_id, mock_deactivated_session):
        """Test that task is idempotent if session already has actual_end set."""
        from backend.core.celery_app import auto_deactivate_focus

        original_end_time = mock_deactivated_session.actual_end

        mock_db_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_deactivated_session)
        mock_db_session.execute = AsyncMock(return_value=mock_result)
        mock_db_session.commit = AsyncMock()

        with patch("backend.core.celery_app.AsyncSessionLocal") as mock_session_local:
            mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
            mock_session_local.return_value.__aexit__ = AsyncMock(return_value=None)

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

        with patch("backend.core.celery_app.AsyncSessionLocal") as mock_session_local:
            mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
            mock_session_local.return_value.__aexit__ = AsyncMock(return_value=None)

            result = auto_deactivate_focus(valid_user_id, valid_session_id, valid_job_id)

        assert result["success"] is True
        assert result["status"] == "session_not_found"
        # Job should still be marked as completed
        mock_db_session.commit.assert_called()

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

        with patch("backend.core.celery_app.AsyncSessionLocal") as mock_session_local:
            mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
            mock_session_local.return_value.__aexit__ = AsyncMock(return_value=None)

            result = auto_deactivate_focus(valid_user_id, valid_session_id, valid_job_id)

        assert result["success"] is True
        # Should have called execute twice: once for SELECT, once for UPDATE job status
        assert len(execute_calls) == 2

    def test_task_rejects_invalid_user_id_format(self, valid_session_id, valid_job_id):
        """Test that task handles invalid user_id UUID format."""
        from backend.core.celery_app import auto_deactivate_focus

        mock_db_session = AsyncMock()
        mock_db_session.commit = AsyncMock()

        with patch("backend.core.celery_app.AsyncSessionLocal") as mock_session_local:
            mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
            mock_session_local.return_value.__aexit__ = AsyncMock(return_value=None)

            result = auto_deactivate_focus("not-a-valid-uuid", valid_session_id, valid_job_id)

        assert result["success"] is False
        assert result["error"] == "invalid_uuid"

    def test_task_rejects_invalid_session_id_format(self, valid_user_id, valid_job_id):
        """Test that task handles invalid session_id UUID format."""
        from backend.core.celery_app import auto_deactivate_focus

        mock_db_session = AsyncMock()
        mock_db_session.commit = AsyncMock()

        with patch("backend.core.celery_app.AsyncSessionLocal") as mock_session_local:
            mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
            mock_session_local.return_value.__aexit__ = AsyncMock(return_value=None)

            result = auto_deactivate_focus(valid_user_id, "invalid-uuid", valid_job_id)

        assert result["success"] is False
        assert result["error"] == "invalid_uuid"

    def test_task_rejects_invalid_job_id_format(self, valid_user_id, valid_session_id):
        """Test that task handles invalid job_id UUID format."""
        from backend.core.celery_app import auto_deactivate_focus

        mock_db_session = AsyncMock()
        mock_db_session.commit = AsyncMock()

        with patch("backend.core.celery_app.AsyncSessionLocal") as mock_session_local:
            mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_db_session)
            mock_session_local.return_value.__aexit__ = AsyncMock(return_value=None)

            result = auto_deactivate_focus(valid_user_id, valid_session_id, "invalid-job-id")

        assert result["success"] is False
        assert result["error"] == "invalid_uuid"

    def test_task_marks_job_failed_on_db_error(self, valid_user_id, valid_session_id, valid_job_id):
        """Test that job is marked as failed when DB error occurs."""
        from backend.core.celery_app import auto_deactivate_focus

        # Simulate DB error on execute
        mock_db_session = AsyncMock()
        mock_db_session.execute = AsyncMock(side_effect=Exception("DB connection lost"))
        mock_db_session.commit = AsyncMock()

        # Mock for the failure marking session
        mock_failure_session = AsyncMock()
        mock_failure_session.execute = AsyncMock()
        mock_failure_session.commit = AsyncMock()

        call_count = 0

        def session_factory():
            nonlocal call_count
            call_count += 1
            mock = MagicMock()
            if call_count == 1:
                # First session (main operation) - will fail
                mock.__aenter__ = AsyncMock(return_value=mock_db_session)
            else:
                # Second session (failure marking)
                mock.__aenter__ = AsyncMock(return_value=mock_failure_session)
            mock.__aexit__ = AsyncMock(return_value=None)
            return mock

        with patch("backend.core.celery_app.AsyncSessionLocal", side_effect=session_factory):
            # Should raise and retry
            with pytest.raises(Exception):
                auto_deactivate_focus(valid_user_id, valid_session_id, valid_job_id)
