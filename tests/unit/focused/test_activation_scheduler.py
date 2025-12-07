"""
Unit tests for Focus Block Activation Scheduler (Increment 20).

Tests the scheduling, cancellation, and rescheduling of activation jobs.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from backend.apps.focused.logic.sync.activation_scheduler import (
    ACTIVATION_TASK_NAME,
    LEAD_TIME_MINUTES,
    schedule_focus_activation,
    cancel_scheduled_activation,
    reschedule_activation,
)


class TestScheduleFocusActivation:
    """Tests for schedule_focus_activation function."""

    @pytest.mark.asyncio
    async def test_schedules_job_for_future_event(self):
        """Should create job and schedule Celery task for future event."""
        user_id = uuid4()
        session_id = uuid4()
        event_start = datetime.now(timezone.utc) + timedelta(hours=2)

        mock_db = MagicMock()
        mock_db.add = MagicMock()  # Sync method
        mock_db.flush = AsyncMock()

        with patch("backend.apps.focused.logic.sync.activation_scheduler.celery_app") as mock_celery:
            mock_task = MagicMock()
            mock_task.id = "test-task-id"
            mock_celery.send_task.return_value = mock_task

            job = await schedule_focus_activation(
                user_id=user_id,
                session_id=session_id,
                event_start_time=event_start,
                db=mock_db,
            )

            # Verify job was created with correct fields
            assert job is not None
            assert job.user_id == user_id
            assert job.event_id == session_id
            assert job.job_type == "activation"
            assert job.status == "pending"
            assert job.celery_task_id == "test-task-id"

            # Verify critical timing fields (core to Increment 20)
            assert job.event_start_time == event_start
            expected_scheduled_at = event_start - timedelta(minutes=LEAD_TIME_MINUTES)
            assert job.scheduled_at == expected_scheduled_at

            # Verify initial field values per spec
            assert job.shortcut_url is None  # Generated later by task
            assert job.error_reason is None  # Only set on failure/cancellation
            assert job.retry_count == 0  # No retries yet

            # Verify Celery task was scheduled with correct args and ETA
            mock_celery.send_task.assert_called_once()
            call_args = mock_celery.send_task.call_args
            # Verify task name (uses constant to avoid coupling to exact path)
            assert call_args[0][0] == ACTIVATION_TASK_NAME
            # Verify args contain user_id, session_id, job_id
            task_args = call_args.kwargs["args"]
            assert task_args[0] == str(user_id)
            assert task_args[1] == str(session_id)
            assert task_args[2] == str(job.id)
            # Verify ETA
            assert call_args.kwargs["eta"] == expected_scheduled_at
            # Verify queue
            assert call_args.kwargs["queue"] == "focused"

            # Verify DB persistence: add() and flush() called
            mock_db.add.assert_called_once_with(job)
            mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_triggers_immediately_within_lead_time(self):
        """Should trigger immediately if event starts within LEAD_TIME_MINUTES."""
        user_id = uuid4()
        session_id = uuid4()
        # Event starts in 5 minutes (less than LEAD_TIME_MINUTES=10)
        event_start = datetime.now(timezone.utc) + timedelta(minutes=5)

        mock_db = MagicMock()
        mock_db.add = MagicMock()  # Sync method
        mock_db.flush = AsyncMock()

        with patch("backend.apps.focused.logic.sync.activation_scheduler.celery_app") as mock_celery:
            mock_task = MagicMock()
            mock_task.id = "test-task-id"
            mock_celery.send_task.return_value = mock_task

            job = await schedule_focus_activation(
                user_id=user_id,
                session_id=session_id,
                event_start_time=event_start,
                db=mock_db,
            )

            # Verify job was created with correct fields
            assert job is not None
            assert job.user_id == user_id
            assert job.event_id == session_id
            assert job.job_type == "activation"
            assert job.status == "pending"

            # Verify timing fields per spec:
            # - scheduled_at is ALWAYS event_start - lead_time (informational field)
            # - It does NOT get mutated even if in the past
            # - Celery immediate trigger is separate from DB record
            assert job.event_start_time == event_start
            expected_scheduled_at = event_start - timedelta(minutes=LEAD_TIME_MINUTES)
            assert job.scheduled_at == expected_scheduled_at  # Will be ~5 minutes in the past

            # Verify Celery task was scheduled immediately (no future ETA)
            mock_celery.send_task.assert_called_once()
            call_args = mock_celery.send_task.call_args
            # Verify task name (uses constant to avoid coupling to exact path)
            assert call_args[0][0] == ACTIVATION_TASK_NAME
            # Verify args contain user_id, session_id, job_id
            task_args = call_args.kwargs["args"]
            assert task_args[0] == str(user_id)
            assert task_args[1] == str(session_id)
            assert task_args[2] == str(job.id)
            # Verify NO ETA (immediate trigger) - either no eta key or eta is None
            assert call_args.kwargs.get("eta") is None
            # Verify queue
            assert call_args.kwargs["queue"] == "focused"

            # Verify DB persistence: add() and flush() called
            mock_db.add.assert_called_once_with(job)
            mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_boundary_exactly_at_lead_time(self):
        """Should trigger immediately when event_start == now + LEAD_TIME_MINUTES (boundary)."""
        user_id = uuid4()
        session_id = uuid4()
        # Event starts exactly at lead time boundary
        # scheduled_at would be exactly "now", which means delay_seconds <= 0
        event_start = datetime.now(timezone.utc) + timedelta(minutes=LEAD_TIME_MINUTES)

        mock_db = MagicMock()
        mock_db.add = MagicMock()  # Sync method
        mock_db.flush = AsyncMock()

        with patch("backend.apps.focused.logic.sync.activation_scheduler.celery_app") as mock_celery:
            mock_task = MagicMock()
            mock_task.id = "test-task-id"
            mock_celery.send_task.return_value = mock_task

            job = await schedule_focus_activation(
                user_id=user_id,
                session_id=session_id,
                event_start_time=event_start,
                db=mock_db,
            )

            # Verify job was created
            assert job is not None
            assert job.event_start_time == event_start
            expected_scheduled_at = event_start - timedelta(minutes=LEAD_TIME_MINUTES)
            assert job.scheduled_at == expected_scheduled_at  # Approximately "now"

            # Boundary case: scheduled_at is approximately now, so delay_seconds <= 0
            # This should trigger immediately (no ETA)
            mock_celery.send_task.assert_called_once()
            call_args = mock_celery.send_task.call_args

            # Verify task name (uses constant to avoid coupling to exact path)
            assert call_args[0][0] == ACTIVATION_TASK_NAME
            # Verify args contain user_id, session_id, job_id
            task_args = call_args.kwargs["args"]
            assert task_args[0] == str(user_id)
            assert task_args[1] == str(session_id)
            assert task_args[2] == str(job.id)
            # Verify NO ETA (immediate trigger)
            assert call_args.kwargs.get("eta") is None
            # Verify queue
            assert call_args.kwargs["queue"] == "focused"

    @pytest.mark.asyncio
    async def test_skips_past_events(self):
        """Should skip scheduling for events that already started."""
        user_id = uuid4()
        session_id = uuid4()
        # Event started 1 hour ago
        event_start = datetime.now(timezone.utc) - timedelta(hours=1)

        mock_db = AsyncMock()

        with patch("backend.apps.focused.logic.sync.activation_scheduler.celery_app") as mock_celery:
            job = await schedule_focus_activation(
                user_id=user_id,
                session_id=session_id,
                event_start_time=event_start,
                db=mock_db,
            )

            # Should return None (no job created)
            assert job is None

            # Celery should not be called
            mock_celery.send_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_idempotency_on_duplicate(self):
        """Should return None and NOT call Celery if job already exists (IntegrityError)."""
        from sqlalchemy.exc import IntegrityError

        user_id = uuid4()
        session_id = uuid4()
        event_start = datetime.now(timezone.utc) + timedelta(hours=2)

        mock_db = MagicMock()
        mock_db.add = MagicMock()  # Sync method
        mock_db.flush = AsyncMock(side_effect=IntegrityError("duplicate", None, None))
        mock_db.rollback = AsyncMock()

        with patch("backend.apps.focused.logic.sync.activation_scheduler.celery_app") as mock_celery:
            job = await schedule_focus_activation(
                user_id=user_id,
                session_id=session_id,
                event_start_time=event_start,
                db=mock_db,
            )

            # Should return None (idempotent skip)
            assert job is None

            # Verify DB operations: add() called, flush() raised IntegrityError, rollback() called
            mock_db.add.assert_called_once()
            mock_db.flush.assert_called_once()
            mock_db.rollback.assert_called_once()

            # CRITICAL: Celery must NOT be called when IntegrityError occurs
            # This verifies the implementation creates the DB row BEFORE scheduling Celery
            mock_celery.send_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_marks_job_failed_on_celery_send_failure(self):
        """Should mark job as failed if Celery send_task raises exception."""
        user_id = uuid4()
        session_id = uuid4()
        event_start = datetime.now(timezone.utc) + timedelta(hours=2)

        mock_db = MagicMock()
        mock_db.add = MagicMock()  # Sync method
        mock_db.flush = AsyncMock()

        with patch("backend.apps.focused.logic.sync.activation_scheduler.celery_app") as mock_celery:
            mock_celery.send_task.side_effect = Exception("Celery broker unavailable")

            job = await schedule_focus_activation(
                user_id=user_id,
                session_id=session_id,
                event_start_time=event_start,
                db=mock_db,
            )

            # Job should be returned but marked as failed
            assert job is not None
            assert job.status == "failed"
            assert "Celery broker unavailable" in job.error_reason

            # DB operations should still have been called (at least once for initial persist)
            mock_db.add.assert_called_once()
            assert mock_db.flush.call_count >= 1

    @pytest.mark.asyncio
    async def test_celery_task_id_saved_after_flush(self):
        """Should save celery_task_id only after flush() provides job.id."""
        user_id = uuid4()
        session_id = uuid4()
        event_start = datetime.now(timezone.utc) + timedelta(hours=2)

        mock_db = AsyncMock()

        # Track call order
        call_order = []

        async def mock_flush():
            call_order.append("flush")

        mock_db.flush = mock_flush

        def mock_add(obj):
            call_order.append("add")

        mock_db.add = mock_add

        with patch("backend.apps.focused.logic.sync.activation_scheduler.celery_app") as mock_celery:
            def mock_send_task(*args, **kwargs):
                call_order.append("send_task")
                mock_task = MagicMock()
                mock_task.id = "test-task-id"
                return mock_task

            mock_celery.send_task = mock_send_task

            job = await schedule_focus_activation(
                user_id=user_id,
                session_id=session_id,
                event_start_time=event_start,
                db=mock_db,
            )

            # Verify correct order: add -> flush -> send_task
            # flush() must happen before send_task so job.id is available
            assert call_order == ["add", "flush", "send_task"]

            # Verify celery_task_id was saved
            assert job.celery_task_id == "test-task-id"


class TestCancelScheduledActivation:
    """Tests for cancel_scheduled_activation function."""

    @pytest.mark.asyncio
    async def test_cancels_pending_job(self):
        """Should cancel pending job and revoke Celery task."""
        user_id = uuid4()
        session_id = uuid4()

        # Create a mock job
        mock_job = MagicMock()
        mock_job.id = uuid4()
        mock_job.celery_task_id = "test-task-id"
        mock_job.status = "pending"

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job
        mock_db.execute.return_value = mock_result

        with patch("backend.apps.focused.logic.sync.activation_scheduler.celery_app") as mock_celery:
            result = await cancel_scheduled_activation(
                user_id=user_id,
                session_id=session_id,
                db=mock_db,
                reason="event_deleted",
            )

            # Should return True (job was cancelled)
            assert result is True

            # Verify Celery task was revoked
            mock_celery.control.revoke.assert_called_once_with(
                "test-task-id", terminate=False
            )

            # Verify job status was updated
            assert mock_job.status == "cancelled"
            assert mock_job.error_reason == "event_deleted"

    @pytest.mark.asyncio
    async def test_returns_false_when_no_pending_job(self):
        """Should return False if no pending job exists."""
        user_id = uuid4()
        session_id = uuid4()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with patch("backend.apps.focused.logic.sync.activation_scheduler.celery_app") as mock_celery:
            result = await cancel_scheduled_activation(
                user_id=user_id,
                session_id=session_id,
                db=mock_db,
            )

            # Should return False (no job to cancel)
            assert result is False

            # Celery should not be called
            mock_celery.control.revoke.assert_not_called()

    @pytest.mark.asyncio
    async def test_only_queries_for_pending_jobs(self):
        """Should only look for jobs with status='pending'.

        This verifies the query filter includes status='pending', ensuring
        completed/failed/cancelled jobs are not accidentally cancelled.
        """
        user_id = uuid4()
        session_id = uuid4()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with patch("backend.apps.focused.logic.sync.activation_scheduler.celery_app"):
            await cancel_scheduled_activation(
                user_id=user_id,
                session_id=session_id,
                db=mock_db,
            )

            # Verify the query was executed
            mock_db.execute.assert_called_once()

            # Extract the query and verify it filters for pending status
            call_args = mock_db.execute.call_args
            query = call_args[0][0]
            query_str = str(query.compile(compile_kwargs={"literal_binds": True}))

            # Verify key filters are present in the query
            assert "status" in query_str.lower()
            assert "pending" in query_str.lower()

    @pytest.mark.asyncio
    async def test_handles_revoke_failure_gracefully(self):
        """Should continue even if Celery revoke fails - job still marked cancelled with reason."""
        user_id = uuid4()
        session_id = uuid4()

        mock_job = MagicMock()
        mock_job.id = uuid4()
        mock_job.celery_task_id = "test-task-id"
        mock_job.status = "pending"
        mock_job.error_reason = None

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_job
        mock_db.execute.return_value = mock_result

        with patch("backend.apps.focused.logic.sync.activation_scheduler.celery_app") as mock_celery:
            mock_celery.control.revoke.side_effect = Exception("Celery error")

            result = await cancel_scheduled_activation(
                user_id=user_id,
                session_id=session_id,
                db=mock_db,
                reason="event_deleted",
            )

            # Should still return True (job was cancelled in DB despite revoke failure)
            assert result is True
            assert mock_job.status == "cancelled"
            assert mock_job.error_reason == "event_deleted"

            # Verify revoke was attempted
            mock_celery.control.revoke.assert_called_once_with("test-task-id", terminate=False)


class TestRescheduleActivation:
    """Tests for reschedule_activation function."""

    @pytest.mark.asyncio
    async def test_cancels_old_and_schedules_new(self):
        """Should cancel existing job and schedule new one."""
        user_id = uuid4()
        session_id = uuid4()
        new_start = datetime.now(timezone.utc) + timedelta(hours=3)

        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()

        # Mock cancel returns True (old job existed)
        with patch(
            "backend.apps.focused.logic.sync.activation_scheduler.cancel_scheduled_activation"
        ) as mock_cancel:
            mock_cancel.return_value = True

            with patch(
                "backend.apps.focused.logic.sync.activation_scheduler.schedule_focus_activation"
            ) as mock_schedule:
                mock_job = MagicMock()
                mock_job.job_type = "activation"
                mock_schedule.return_value = mock_job

                result = await reschedule_activation(
                    user_id=user_id,
                    session_id=session_id,
                    new_event_start_time=new_start,
                    db=mock_db,
                )

                # Verify cancel was called with job_type implied as 'activation'
                mock_cancel.assert_called_once_with(
                    user_id=user_id,
                    session_id=session_id,
                    db=mock_db,
                    reason="event_time_changed",
                )

                # Verify schedule was called with new time
                mock_schedule.assert_called_once_with(
                    user_id=user_id,
                    session_id=session_id,
                    event_start_time=new_start,
                    db=mock_db,
                )

                assert result == mock_job
                assert result.job_type == "activation"

    @pytest.mark.asyncio
    async def test_schedules_new_even_when_no_existing_job(self):
        """Should schedule new job even if no existing job to cancel."""
        user_id = uuid4()
        session_id = uuid4()
        new_start = datetime.now(timezone.utc) + timedelta(hours=3)

        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()

        # Mock cancel returns False (no existing job)
        with patch(
            "backend.apps.focused.logic.sync.activation_scheduler.cancel_scheduled_activation"
        ) as mock_cancel:
            mock_cancel.return_value = False

            with patch(
                "backend.apps.focused.logic.sync.activation_scheduler.schedule_focus_activation"
            ) as mock_schedule:
                mock_job = MagicMock()
                mock_job.job_type = "activation"
                mock_schedule.return_value = mock_job

                result = await reschedule_activation(
                    user_id=user_id,
                    session_id=session_id,
                    new_event_start_time=new_start,
                    db=mock_db,
                )

                # Cancel should still be called (even if nothing to cancel)
                mock_cancel.assert_called_once()

                # Schedule should still be called regardless of cancel result
                mock_schedule.assert_called_once_with(
                    user_id=user_id,
                    session_id=session_id,
                    event_start_time=new_start,
                    db=mock_db,
                )

                # New job should be returned with correct job_type
                assert result == mock_job
                assert result.job_type == "activation"


class TestLeadTimeConfiguration:
    """Tests for lead time configuration."""

    def test_lead_time_is_10_minutes(self):
        """LEAD_TIME_MINUTES should be 10 as per spec."""
        assert LEAD_TIME_MINUTES == 10
