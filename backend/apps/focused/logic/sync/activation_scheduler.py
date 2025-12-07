"""
Focus Block Activation Scheduler (Increment 20).

Handles scheduling and cancellation of Celery tasks for automatic
focus mode activation when focus blocks are detected during sync.

Key behaviors:
- Schedule activation task for (start_time - LEAD_TIME_MINUTES)
- Idempotency via DB unique constraint (no duplicate jobs)
- Cancellation when event is deleted or time changes
- Immediate trigger if event starts within LEAD_TIME_MINUTES
"""

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.focused.db_models import FocusedScheduledJob
from backend.core.celery_app import celery_app

logger = logging.getLogger(__name__)

# Configuration
LEAD_TIME_MINUTES = 10  # Schedule activation this many minutes before event start

# Task name constant - single source of truth for Celery task path
# If the task moves, update this constant (tests import it too)
ACTIVATION_TASK_NAME = "backend.core.celery_app.trigger_focus_activation"


async def schedule_focus_activation(
    user_id: UUID,
    session_id: UUID,
    event_start_time: datetime,
    db: AsyncSession,
) -> FocusedScheduledJob | None:
    """
    Schedule a focus activation task for the given focus session.

    Creates a job record in focused_scheduled_jobs and schedules a Celery task
    to fire at (event_start_time - LEAD_TIME_MINUTES).

    Args:
        user_id: User's UUID
        session_id: Focus session UUID (from focused_focus_sessions.id)
        event_start_time: When the calendar event starts (UTC)
        db: Database session

    Returns:
        The created FocusedScheduledJob, or None if already scheduled (idempotent)

    Note:
        Uses DB unique constraint for idempotency. If a job already exists for
        this (user_id, event_id, job_type, event_start_time), returns None.
    """
    now = datetime.now(timezone.utc)

    # Skip if event already started
    if event_start_time <= now:
        logger.debug(
            "focused.scheduler.skip_past_event",
            extra={
                "user_id": str(user_id),
                "session_id": str(session_id),
                "event_start_time": event_start_time.isoformat(),
                "reason": "event_already_started",
            }
        )
        return None

    # Calculate scheduled_at (informational - when task was meant to fire)
    # This is always event_start - lead_time, even if in the past
    scheduled_at = event_start_time - timedelta(minutes=LEAD_TIME_MINUTES)

    # Create job record (idempotency via unique constraint)
    # Note: Explicitly set all fields to avoid relying on DB defaults for in-memory access
    job = FocusedScheduledJob(
        user_id=user_id,
        job_type="activation",
        event_id=session_id,
        event_start_time=event_start_time,
        scheduled_at=scheduled_at,
        status="pending",
        shortcut_url=None,  # Generated later by task
        error_reason=None,  # Only set on failure/cancellation
        retry_count=0,  # No retries yet
    )

    try:
        db.add(job)
        await db.flush()  # Get the generated ID and check constraint
    except IntegrityError:
        # Job already exists for this event/time - idempotent skip
        await db.rollback()
        logger.debug(
            "focused.scheduler.already_scheduled",
            extra={
                "user_id": str(user_id),
                "session_id": str(session_id),
                "event_start_time": event_start_time.isoformat(),
            }
        )
        return None

    # Schedule Celery task
    delay_seconds = (scheduled_at - now).total_seconds()

    try:
        if delay_seconds <= 0:
            # Trigger immediately
            task = celery_app.send_task(
                ACTIVATION_TASK_NAME,
                args=[str(user_id), str(session_id), str(job.id)],
                queue="focused",
            )
        else:
            # Schedule with ETA
            task = celery_app.send_task(
                ACTIVATION_TASK_NAME,
                args=[str(user_id), str(session_id), str(job.id)],
                eta=scheduled_at,
                queue="focused",
            )

        # Store Celery task ID
        job.celery_task_id = task.id
    except Exception as e:
        # Celery send failed - mark job as failed
        logger.error(
            "focused.scheduler.celery_send_failed",
            extra={
                "user_id": str(user_id),
                "session_id": str(session_id),
                "job_id": str(job.id),
                "error": str(e),
            }
        )
        job.status = "failed"
        job.error_reason = f"celery_send_failed: {str(e)[:200]}"
        return job

    logger.info(
        "focused.scheduler.job_created",
        extra={
            "user_id": str(user_id),
            "session_id": str(session_id),
            "job_id": str(job.id),
            "celery_task_id": task.id,
            "scheduled_at": scheduled_at.isoformat(),
            "event_start_time": event_start_time.isoformat(),
            "immediate": delay_seconds <= 0,
        }
    )

    return job


async def cancel_scheduled_activation(
    user_id: UUID,
    session_id: UUID,
    db: AsyncSession,
    reason: str = "event_changed",
) -> bool:
    """
    Cancel any pending activation job for the given focus session.

    Used when:
    - Event is deleted
    - Event time changes (old job cancelled, new one scheduled)
    - Event keywords removed (no longer a focus block)

    Args:
        user_id: User's UUID
        session_id: Focus session UUID
        db: Database session
        reason: Why the job is being cancelled

    Returns:
        True if a job was cancelled, False if no pending job found
    """
    # Find pending activation job for this session
    stmt = select(FocusedScheduledJob).where(
        FocusedScheduledJob.user_id == user_id,
        FocusedScheduledJob.event_id == session_id,
        FocusedScheduledJob.job_type == "activation",
        FocusedScheduledJob.status == "pending",
    )
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()

    if not job:
        logger.debug(
            "focused.scheduler.no_pending_job",
            extra={
                "user_id": str(user_id),
                "session_id": str(session_id),
            }
        )
        return False

    # Revoke the Celery task (if it has a task ID)
    if job.celery_task_id:
        try:
            celery_app.control.revoke(job.celery_task_id, terminate=False)
            logger.info(
                "focused.scheduler.celery_revoked",
                extra={
                    "job_id": str(job.id),
                    "celery_task_id": job.celery_task_id,
                }
            )
        except Exception as e:
            # Log but don't fail - the job status update is more important
            logger.warning(
                "focused.scheduler.revoke_failed",
                extra={
                    "job_id": str(job.id),
                    "celery_task_id": job.celery_task_id,
                    "error": str(e),
                }
            )

    # Mark job as cancelled
    job.status = "cancelled"
    job.error_reason = reason

    logger.info(
        "focused.scheduler.job_cancelled",
        extra={
            "user_id": str(user_id),
            "session_id": str(session_id),
            "job_id": str(job.id),
            "reason": reason,
        }
    )

    return True


async def reschedule_activation(
    user_id: UUID,
    session_id: UUID,
    new_event_start_time: datetime,
    db: AsyncSession,
) -> FocusedScheduledJob | None:
    """
    Reschedule activation job when event time changes.

    Cancels any existing pending job and schedules a new one.

    Args:
        user_id: User's UUID
        session_id: Focus session UUID
        new_event_start_time: New event start time (UTC)
        db: Database session

    Returns:
        The new FocusedScheduledJob, or None if scheduling failed
    """
    # Cancel existing job (if any)
    await cancel_scheduled_activation(
        user_id=user_id,
        session_id=session_id,
        db=db,
        reason="event_time_changed",
    )

    # Schedule new job
    return await schedule_focus_activation(
        user_id=user_id,
        session_id=session_id,
        event_start_time=new_event_start_time,
        db=db,
    )
