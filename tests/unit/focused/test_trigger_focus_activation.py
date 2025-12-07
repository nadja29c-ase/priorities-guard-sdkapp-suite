"""
Unit tests for trigger_focus_activation Celery task (Increment 20).

Tests the task logic including:
- Status transitions (running -> pending_notification/pending_confirmation)
- Active session guard (skipped)
- Shortcut URL generation and storage
- Consent preference handling
- Error paths (session deleted, not focus block, URL generation failure)
- Cancellation when status != pending
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

# Patch paths for helper functions - these are imported inside the task
HELPERS_MODULE = "backend.apps.focused.logic.activation_helpers"
FETCH_FOCUS_SESSION_PATCH = f"{HELPERS_MODULE}.fetch_focus_session"
FETCH_USER_ACTIVE_SESSION_PATCH = f"{HELPERS_MODULE}.fetch_user_active_session"
FETCH_CONSENT_PREFERENCES_PATCH = f"{HELPERS_MODULE}.fetch_consent_preferences"
UPDATE_JOB_STATUS_PATCH = f"{HELPERS_MODULE}.update_job_status"

# Other patches
ASYNC_SESSION_PATCH = "backend.core.database.AsyncSessionLocal"
RUN_FOCUS_MODE_PATCH = "backend.apps.focused.tools.focus_activation_internal.run_focus_mode_internal"


def _create_mock_focus_session(
    user_id=None,
    session_id=None,
    is_focus_block=True,
    status="active",
    actual_start=None,
    actual_end=None,
    event_summary="Deep Work Session",
    end_time=None,
):
    """Create a mock FocusedFocusSession."""
    mock_session = MagicMock()
    mock_session.id = session_id or uuid4()
    mock_session.user_id = user_id or uuid4()
    mock_session.is_focus_block = is_focus_block
    mock_session.status = status
    mock_session.actual_start = actual_start
    mock_session.actual_end = actual_end
    mock_session.event_summary = event_summary
    mock_session.end_time = end_time or (datetime.now(timezone.utc) + timedelta(hours=1))
    return mock_session


def _create_mock_consent_prefs(auto_handle=False):
    """Create a mock FocusedConsentPreferences."""
    mock_prefs = MagicMock()
    mock_prefs.auto_handle_focus_blocks = auto_handle
    mock_prefs.always_confirm_duration = True
    return mock_prefs


class TestTriggerFocusActivationTask:
    """Unit tests for trigger_focus_activation Celery task."""

    # =========================================================================
    # Happy Path Tests
    # =========================================================================

    def test_sets_pending_notification_when_auto_handle_true(self):
        """Should set status to pending_notification when auto_handle_focus_blocks=True."""
        user_id = uuid4()
        session_id = uuid4()
        job_id = uuid4()

        mock_session = _create_mock_focus_session(
            user_id=user_id, session_id=session_id
        )
        mock_prefs = _create_mock_consent_prefs(auto_handle=True)

        with patch(ASYNC_SESSION_PATCH) as mock_session_local:
            mock_db = AsyncMock()
            mock_session_local.return_value.__aenter__.return_value = mock_db

            with patch(FETCH_FOCUS_SESSION_PATCH, new_callable=AsyncMock) as mock_fetch_session:
                mock_fetch_session.return_value = mock_session

                with patch(FETCH_USER_ACTIVE_SESSION_PATCH, new_callable=AsyncMock) as mock_fetch_active:
                    mock_fetch_active.return_value = None  # No active session

                    with patch(FETCH_CONSENT_PREFERENCES_PATCH, new_callable=AsyncMock) as mock_fetch_prefs:
                        mock_fetch_prefs.return_value = mock_prefs

                        with patch(UPDATE_JOB_STATUS_PATCH, new_callable=AsyncMock) as mock_update:
                            with patch(RUN_FOCUS_MODE_PATCH) as mock_run:
                                mock_run.return_value = {
                                    "shortcut_url": "shortcuts://test",
                                    "focus_name": "Deep Work Session",
                                    "end_time": "2025-01-01T12:00:00Z",
                                }

                                from backend.core.celery_app import trigger_focus_activation

                                result = trigger_focus_activation(
                                    str(user_id), str(session_id), str(job_id)
                                )

                                assert result["success"] is True
                                assert result["status"] == "pending_notification"
                                assert result["shortcut_url"] == "shortcuts://test"

                                # Verify update_job_status was called with correct final status
                                calls = mock_update.call_args_list
                                # First call: 'running', Final call: 'pending_notification'
                                assert calls[0][0][2] == "running"
                                final_call = calls[-1]
                                assert final_call[0][2] == "pending_notification"
                                assert final_call[1]["shortcut_url"] == "shortcuts://test"

    def test_sets_pending_confirmation_when_auto_handle_false(self):
        """Should set status to pending_confirmation when auto_handle_focus_blocks=False."""
        user_id = uuid4()
        session_id = uuid4()
        job_id = uuid4()

        mock_session = _create_mock_focus_session(
            user_id=user_id, session_id=session_id
        )
        mock_prefs = _create_mock_consent_prefs(auto_handle=False)

        with patch(ASYNC_SESSION_PATCH) as mock_session_local:
            mock_db = AsyncMock()
            mock_session_local.return_value.__aenter__.return_value = mock_db

            with patch(FETCH_FOCUS_SESSION_PATCH, new_callable=AsyncMock) as mock_fetch_session:
                mock_fetch_session.return_value = mock_session

                with patch(FETCH_USER_ACTIVE_SESSION_PATCH, new_callable=AsyncMock) as mock_fetch_active:
                    mock_fetch_active.return_value = None

                    with patch(FETCH_CONSENT_PREFERENCES_PATCH, new_callable=AsyncMock) as mock_fetch_prefs:
                        mock_fetch_prefs.return_value = mock_prefs

                        with patch(UPDATE_JOB_STATUS_PATCH, new_callable=AsyncMock) as mock_update:
                            with patch(RUN_FOCUS_MODE_PATCH) as mock_run:
                                mock_run.return_value = {
                                    "shortcut_url": "shortcuts://test",
                                    "focus_name": "Deep Work Session",
                                    "end_time": "2025-01-01T12:00:00Z",
                                }

                                from backend.core.celery_app import trigger_focus_activation

                                result = trigger_focus_activation(
                                    str(user_id), str(session_id), str(job_id)
                                )

                                assert result["success"] is True
                                assert result["status"] == "pending_confirmation"

    def test_defaults_to_pending_confirmation_when_no_preferences(self):
        """Should default to pending_confirmation when user has no consent preferences."""
        user_id = uuid4()
        session_id = uuid4()
        job_id = uuid4()

        mock_session = _create_mock_focus_session(
            user_id=user_id, session_id=session_id
        )

        with patch(ASYNC_SESSION_PATCH) as mock_session_local:
            mock_db = AsyncMock()
            mock_session_local.return_value.__aenter__.return_value = mock_db

            with patch(FETCH_FOCUS_SESSION_PATCH, new_callable=AsyncMock) as mock_fetch_session:
                mock_fetch_session.return_value = mock_session

                with patch(FETCH_USER_ACTIVE_SESSION_PATCH, new_callable=AsyncMock) as mock_fetch_active:
                    mock_fetch_active.return_value = None

                    with patch(FETCH_CONSENT_PREFERENCES_PATCH, new_callable=AsyncMock) as mock_fetch_prefs:
                        mock_fetch_prefs.return_value = None  # No preferences

                        with patch(UPDATE_JOB_STATUS_PATCH, new_callable=AsyncMock) as mock_update:
                            with patch(RUN_FOCUS_MODE_PATCH) as mock_run:
                                mock_run.return_value = {
                                    "shortcut_url": "shortcuts://test",
                                    "focus_name": "Test",
                                    "end_time": None,
                                }

                                from backend.core.celery_app import trigger_focus_activation

                                result = trigger_focus_activation(
                                    str(user_id), str(session_id), str(job_id)
                                )

                                assert result["success"] is True
                                assert result["status"] == "pending_confirmation"

    # =========================================================================
    # Active Session Guard Tests
    # =========================================================================

    def test_skips_when_user_has_active_focus_session(self):
        """Should set status to 'skipped' when user already has active focus."""
        user_id = uuid4()
        session_id = uuid4()
        job_id = uuid4()

        mock_session = _create_mock_focus_session(
            user_id=user_id, session_id=session_id
        )

        # Create an active session (different from the scheduled one)
        active_session = _create_mock_focus_session(
            user_id=user_id,
            session_id=uuid4(),  # Different session
            actual_start=datetime.now(timezone.utc) - timedelta(hours=1),
            actual_end=None,  # Still active
        )

        with patch(ASYNC_SESSION_PATCH) as mock_session_local:
            mock_db = AsyncMock()
            mock_session_local.return_value.__aenter__.return_value = mock_db

            with patch(FETCH_FOCUS_SESSION_PATCH, new_callable=AsyncMock) as mock_fetch_session:
                mock_fetch_session.return_value = mock_session

                with patch(FETCH_USER_ACTIVE_SESSION_PATCH, new_callable=AsyncMock) as mock_fetch_active:
                    mock_fetch_active.return_value = active_session  # User has active session!

                    with patch(UPDATE_JOB_STATUS_PATCH, new_callable=AsyncMock) as mock_update:
                        from backend.core.celery_app import trigger_focus_activation

                        result = trigger_focus_activation(
                            str(user_id), str(session_id), str(job_id)
                        )

                        assert result["success"] is False
                        assert result["status"] == "skipped"
                        assert "active_session_exists" in result.get("reason", "")

                        # Verify job status was updated to 'skipped'
                        calls = mock_update.call_args_list
                        assert any(c[0][2] == "skipped" for c in calls)

    # =========================================================================
    # Cancellation Tests
    # =========================================================================

    def test_cancels_when_session_deleted(self):
        """Should set status to 'cancelled' when focus session was soft-deleted."""
        user_id = uuid4()
        session_id = uuid4()
        job_id = uuid4()

        mock_session = _create_mock_focus_session(
            user_id=user_id,
            session_id=session_id,
            status="deleted",  # Soft-deleted
        )

        with patch(ASYNC_SESSION_PATCH) as mock_session_local:
            mock_db = AsyncMock()
            mock_session_local.return_value.__aenter__.return_value = mock_db

            with patch(FETCH_FOCUS_SESSION_PATCH, new_callable=AsyncMock) as mock_fetch_session:
                mock_fetch_session.return_value = mock_session  # Deleted session

                with patch(UPDATE_JOB_STATUS_PATCH, new_callable=AsyncMock) as mock_update:
                    from backend.core.celery_app import trigger_focus_activation

                    result = trigger_focus_activation(
                        str(user_id), str(session_id), str(job_id)
                    )

                    assert result["success"] is False
                    assert result["status"] == "session_deleted"

                    # Verify job was marked cancelled with correct error_reason
                    calls = mock_update.call_args_list
                    cancelled_call = next(c for c in calls if c[0][2] == "cancelled")
                    assert cancelled_call[1]["error_reason"] == "session_deleted"

    def test_cancels_when_not_focus_block(self):
        """Should set status to 'cancelled' when session is no longer a focus block."""
        user_id = uuid4()
        session_id = uuid4()
        job_id = uuid4()

        mock_session = _create_mock_focus_session(
            user_id=user_id,
            session_id=session_id,
            is_focus_block=False,  # No longer a focus block
        )

        with patch(ASYNC_SESSION_PATCH) as mock_session_local:
            mock_db = AsyncMock()
            mock_session_local.return_value.__aenter__.return_value = mock_db

            with patch(FETCH_FOCUS_SESSION_PATCH, new_callable=AsyncMock) as mock_fetch_session:
                mock_fetch_session.return_value = mock_session  # Not a focus block

                with patch(UPDATE_JOB_STATUS_PATCH, new_callable=AsyncMock) as mock_update:
                    from backend.core.celery_app import trigger_focus_activation

                    result = trigger_focus_activation(
                        str(user_id), str(session_id), str(job_id)
                    )

                    assert result["success"] is False
                    assert result["status"] == "not_focus_block"

                    # Verify job was marked cancelled with correct error_reason
                    calls = mock_update.call_args_list
                    cancelled_call = next(c for c in calls if c[0][2] == "cancelled")
                    assert cancelled_call[1]["error_reason"] == "not_focus_block"

    def test_cancels_when_session_not_found(self):
        """Should set status to 'cancelled' when focus session doesn't exist."""
        user_id = uuid4()
        session_id = uuid4()
        job_id = uuid4()

        with patch(ASYNC_SESSION_PATCH) as mock_session_local:
            mock_db = AsyncMock()
            mock_session_local.return_value.__aenter__.return_value = mock_db

            with patch(FETCH_FOCUS_SESSION_PATCH, new_callable=AsyncMock) as mock_fetch_session:
                mock_fetch_session.return_value = None  # Session not found

                with patch(UPDATE_JOB_STATUS_PATCH, new_callable=AsyncMock) as mock_update:
                    from backend.core.celery_app import trigger_focus_activation

                    result = trigger_focus_activation(
                        str(user_id), str(session_id), str(job_id)
                    )

                    assert result["success"] is False
                    assert result["status"] == "session_not_found"

                    # Verify job was marked cancelled with correct error_reason
                    calls = mock_update.call_args_list
                    cancelled_call = next(c for c in calls if c[0][2] == "cancelled")
                    assert cancelled_call[1]["error_reason"] == "session_not_found"

    # =========================================================================
    # Error Path Tests
    # =========================================================================

    def test_fails_when_url_generation_fails(self):
        """Should set status to 'failed' when shortcut URL generation fails."""
        user_id = uuid4()
        session_id = uuid4()
        job_id = uuid4()

        mock_session = _create_mock_focus_session(
            user_id=user_id, session_id=session_id
        )

        with patch(ASYNC_SESSION_PATCH) as mock_session_local:
            mock_db = AsyncMock()
            mock_session_local.return_value.__aenter__.return_value = mock_db

            with patch(FETCH_FOCUS_SESSION_PATCH, new_callable=AsyncMock) as mock_fetch_session:
                mock_fetch_session.return_value = mock_session

                with patch(FETCH_USER_ACTIVE_SESSION_PATCH, new_callable=AsyncMock) as mock_fetch_active:
                    mock_fetch_active.return_value = None

                    with patch(UPDATE_JOB_STATUS_PATCH, new_callable=AsyncMock) as mock_update:
                        with patch(RUN_FOCUS_MODE_PATCH) as mock_run:
                            mock_run.side_effect = Exception("URL generation error")

                            from backend.core.celery_app import trigger_focus_activation

                            result = trigger_focus_activation(
                                str(user_id), str(session_id), str(job_id)
                            )

                            assert result["success"] is False
                            assert result["status"] == "failed"
                            assert "URL generation error" in result.get("error", "")

                            # Verify job was marked failed
                            calls = mock_update.call_args_list
                            failed_call = next(c for c in calls if c[0][2] == "failed")
                            assert "url_generation_failed" in failed_call[1]["error_reason"]

    def test_fails_on_invalid_uuid(self):
        """Should return error for invalid UUID format."""
        with patch(ASYNC_SESSION_PATCH) as mock_session_local:
            mock_db = AsyncMock()
            mock_session_local.return_value.__aenter__.return_value = mock_db

            from backend.core.celery_app import trigger_focus_activation

            result = trigger_focus_activation(
                "not-a-uuid", str(uuid4()), str(uuid4())
            )

            assert result["success"] is False
            assert result["error"] == "invalid_uuid"

    # =========================================================================
    # Status Transition Tests
    # =========================================================================

    def test_shortcut_url_stored_in_job_and_returned(self):
        """Should store generated shortcut_url in the job record and return it."""
        user_id = uuid4()
        session_id = uuid4()
        job_id = uuid4()

        mock_session = _create_mock_focus_session(
            user_id=user_id, session_id=session_id
        )

        expected_url = "shortcuts://run-shortcut?name=Activate%20Focus%20Mode"

        with patch(ASYNC_SESSION_PATCH) as mock_session_local:
            mock_db = AsyncMock()
            mock_session_local.return_value.__aenter__.return_value = mock_db

            with patch(FETCH_FOCUS_SESSION_PATCH, new_callable=AsyncMock) as mock_fetch_session:
                mock_fetch_session.return_value = mock_session

                with patch(FETCH_USER_ACTIVE_SESSION_PATCH, new_callable=AsyncMock) as mock_fetch_active:
                    mock_fetch_active.return_value = None

                    with patch(FETCH_CONSENT_PREFERENCES_PATCH, new_callable=AsyncMock) as mock_fetch_prefs:
                        mock_fetch_prefs.return_value = None

                        with patch(UPDATE_JOB_STATUS_PATCH, new_callable=AsyncMock) as mock_update:
                            with patch(RUN_FOCUS_MODE_PATCH) as mock_run:
                                mock_run.return_value = {
                                    "shortcut_url": expected_url,
                                    "focus_name": "Deep Work",
                                    "end_time": None,
                                }

                                from backend.core.celery_app import trigger_focus_activation

                                result = trigger_focus_activation(
                                    str(user_id), str(session_id), str(job_id)
                                )

                                # Verify URL is in result
                                assert result["shortcut_url"] == expected_url
                                assert result["focus_name"] == "Deep Work"

                                # Verify update_job_status was called with shortcut_url
                                calls = mock_update.call_args_list
                                final_call = calls[-1]
                                assert final_call[1]["shortcut_url"] == expected_url

    def test_returns_end_time_from_activation_data(self):
        """Should return end_time from run_focus_mode_internal."""
        user_id = uuid4()
        session_id = uuid4()
        job_id = uuid4()

        mock_session = _create_mock_focus_session(
            user_id=user_id, session_id=session_id
        )

        expected_end_time = "2025-01-15T18:00:00Z"

        with patch(ASYNC_SESSION_PATCH) as mock_session_local:
            mock_db = AsyncMock()
            mock_session_local.return_value.__aenter__.return_value = mock_db

            with patch(FETCH_FOCUS_SESSION_PATCH, new_callable=AsyncMock) as mock_fetch_session:
                mock_fetch_session.return_value = mock_session

                with patch(FETCH_USER_ACTIVE_SESSION_PATCH, new_callable=AsyncMock) as mock_fetch_active:
                    mock_fetch_active.return_value = None

                    with patch(FETCH_CONSENT_PREFERENCES_PATCH, new_callable=AsyncMock) as mock_fetch_prefs:
                        mock_fetch_prefs.return_value = None

                        with patch(UPDATE_JOB_STATUS_PATCH, new_callable=AsyncMock) as mock_update:
                            with patch(RUN_FOCUS_MODE_PATCH) as mock_run:
                                mock_run.return_value = {
                                    "shortcut_url": "shortcuts://test",
                                    "focus_name": "Deep Work",
                                    "end_time": expected_end_time,
                                }

                                from backend.core.celery_app import trigger_focus_activation

                                result = trigger_focus_activation(
                                    str(user_id), str(session_id), str(job_id)
                                )

                                assert result["end_time"] == expected_end_time

    def test_first_status_update_is_running(self):
        """Should transition status to 'running' before any other processing."""
        user_id = uuid4()
        session_id = uuid4()
        job_id = uuid4()

        mock_session = _create_mock_focus_session(
            user_id=user_id, session_id=session_id
        )

        with patch(ASYNC_SESSION_PATCH) as mock_session_local:
            mock_db = AsyncMock()
            mock_session_local.return_value.__aenter__.return_value = mock_db

            with patch(FETCH_FOCUS_SESSION_PATCH, new_callable=AsyncMock) as mock_fetch_session:
                mock_fetch_session.return_value = mock_session

                with patch(FETCH_USER_ACTIVE_SESSION_PATCH, new_callable=AsyncMock) as mock_fetch_active:
                    mock_fetch_active.return_value = None

                    with patch(FETCH_CONSENT_PREFERENCES_PATCH, new_callable=AsyncMock) as mock_fetch_prefs:
                        mock_fetch_prefs.return_value = None

                        with patch(UPDATE_JOB_STATUS_PATCH, new_callable=AsyncMock) as mock_update:
                            with patch(RUN_FOCUS_MODE_PATCH) as mock_run:
                                mock_run.return_value = {
                                    "shortcut_url": "shortcuts://test",
                                    "focus_name": "Test",
                                    "end_time": None,
                                }

                                from backend.core.celery_app import trigger_focus_activation

                                trigger_focus_activation(
                                    str(user_id), str(session_id), str(job_id)
                                )

                                # First call should be to 'running'
                                first_call = mock_update.call_args_list[0]
                                assert first_call[0][2] == "running"


class TestCancelScheduledActivationStatusGuards:
    """Tests for cancellation behavior based on job status."""

    @pytest.mark.asyncio
    async def test_only_cancels_pending_jobs(self):
        """Should only cancel jobs with status='pending'."""
        from backend.apps.focused.logic.sync.activation_scheduler import (
            cancel_scheduled_activation,
        )

        user_id = uuid4()
        session_id = uuid4()

        # Job with status='running' - should NOT be cancelled
        # The query filters by status='pending', so running jobs won't match
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # Query filters by status='pending'
        mock_db.execute.return_value = mock_result

        with patch(
            "backend.apps.focused.logic.sync.activation_scheduler.celery_app"
        ) as mock_celery:
            result = await cancel_scheduled_activation(
                user_id=user_id,
                session_id=session_id,
                db=mock_db,
            )

            # Should return False because no 'pending' job was found
            assert result is False
            mock_celery.control.revoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_revoke_running_jobs(self):
        """Should NOT revoke Celery task if job status is 'running' (spec requirement).

        The cancel_scheduled_activation query filters by status='pending',
        so running jobs are never selected for cancellation.
        """
        from backend.apps.focused.logic.sync.activation_scheduler import (
            cancel_scheduled_activation,
        )

        user_id = uuid4()
        session_id = uuid4()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with patch(
            "backend.apps.focused.logic.sync.activation_scheduler.celery_app"
        ) as mock_celery:
            await cancel_scheduled_activation(
                user_id=user_id,
                session_id=session_id,
                db=mock_db,
            )

            # Verify revoke wasn't called when no pending result is returned
            mock_celery.control.revoke.assert_not_called()
