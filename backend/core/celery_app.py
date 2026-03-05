"""
Celery application for background task processing.

Handles token renewal, webhook renewal, description cleanup, and other async jobs.

CRITICAL: Async tasks use get_event_loop().run_until_complete() instead of asyncio.run()
to avoid event loop conflicts and deadlocks in Celery worker threads.

=============================================================================
DEPLOYMENT ARCHITECTURE
=============================================================================

For MVP (Development/Testing):
------------------------------
Run Beat and Worker in the same process:
    celery -A backend.core.celery_app.celery_app worker --beat --loglevel=info -Q focused

This is acceptable for development but NOT recommended for production.

For Production (Recommended):
------------------------------
Run Beat and Worker as SEPARATE processes:

    # Terminal 1: Beat scheduler (schedules periodic tasks)
    celery -A backend.core.celery_app.celery_app beat --loglevel=info

    # Terminal 2: Worker (executes tasks)
    celery -A backend.core.celery_app.celery_app worker --loglevel=info -Q focused

Why separate processes?
- If worker crashes or is overloaded, Beat continues scheduling
- If Beat needs restart, workers keep processing queued tasks
- Better resource isolation and monitoring
- Easier to scale workers horizontally

Supervisor/Systemd Configuration:
----------------------------------
Create two service units:
1. celery-beat.service (single instance, schedules tasks)
2. celery-worker.service (can scale to N instances, executes tasks)
"""

import asyncio
import logging
from celery import Celery
from celery.schedules import crontab

from backend.core.config import settings

logger = logging.getLogger(__name__)

# Initialize Celery app
# NOTE: Requires Redis to be running at REDIS_URL
celery_app = Celery(
    "priority_guardian",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes max
    worker_prefetch_multiplier=1,
)

# ---------------------------------------------------------------------
# Periodic task schedule (Increment 6C + 7B)
# ---------------------------------------------------------------------
# IMPORTANT: In production, run Beat as a separate process from workers
# See deployment architecture in module docstring above
celery_app.conf.beat_schedule = {
    "cleanup-descriptions-every-6-hours": {
        "task": "backend.core.celery_app.cleanup_event_descriptions",
        "schedule": crontab(minute=0, hour="*/6"),  # Every 6 hours at :00
        "options": {
            "queue": "focused",
            "priority": 5,
            # CRITICAL: Expiry must be >= schedule interval to prevent gaps
            # Schedule runs every 6 hours. If expiry < 6h, tasks can expire before next run
            # This creates a gap where descriptions could exceed 72h + gap duration
            # Setting to 8h provides a 2h safety buffer for worker overload
            "expires": 28800,  # 8 hours - safe buffer above 6h schedule
            "max_retries": 3,  # Limit retry attempts to prevent infinite loops
            "retry_backoff": True,  # Exponential backoff on retries
            "retry_backoff_max": 600,  # Max 10 minutes between retries
        }
    },
    # OAuth cleanup tasks (Increment 7B)
    "cleanup-oauth-codes-every-15-minutes": {
        "task": "backend.jobs.oauth_cleanup.cleanup_expired_oauth_codes",
        "schedule": crontab(minute="*/15"),  # Every 15 minutes
        "options": {
            "queue": "focused",
            "priority": 7,
            "expires": 900,  # 15 minutes
            "max_retries": 3,
            "retry_backoff": True,
            "retry_backoff_max": 300,  # Max 5 minutes between retries
        }
    },
    "cleanup-oauth-tokens-every-hour": {
        "task": "backend.jobs.oauth_cleanup.cleanup_expired_oauth_tokens",
        "schedule": crontab(minute=0),  # Every hour at :00
        "options": {
            "queue": "focused",
            "priority": 6,
            "expires": 3600,  # 1 hour
            "max_retries": 3,
            "retry_backoff": True,
            "retry_backoff_max": 600,  # Max 10 minutes between retries
        }
    },
    # Scheduled jobs cleanup (Increment 11)
    "cleanup-scheduled-jobs-daily": {
        "task": "backend.core.celery_app.cleanup_scheduled_jobs",
        "schedule": crontab(minute=0, hour=3),  # Daily at 3:00 AM UTC
        "options": {
            "queue": "focused",
            "priority": 8,  # Lower priority than critical tasks
            "expires": 86400,  # 24 hours
            "max_retries": 3,
            "retry_backoff": True,
            "retry_backoff_max": 600,
        }
    },
    # =========================================================================
    # GDPR Retention Enforcement Tasks (Increment 39)
    # =========================================================================
    # OAuth sessions cleanup (existing task, now scheduled)
    "cleanup-oauth-sessions-weekly": {
        "task": "backend.jobs.oauth_cleanup.cleanup_expired_oauth_sessions",
        "schedule": crontab(minute=0, hour=1, day_of_week=0),  # Sunday 01:00 UTC
        "options": {
            "queue": "focused",
            "expires": 86400,  # 24 hours
        }
    },
    # Audit logs: 90-day retention
    "cleanup-audit-logs-daily": {
        "task": "backend.jobs.retention_cleanup.cleanup_expired_audit_logs",
        "schedule": crontab(minute=0, hour=2),  # Daily at 02:00 UTC
        "options": {
            "queue": "focused",
            "expires": 86400,  # 24 hours
        }
    },
    # Google connections: 6-month inactivity soft-revoke
    "cleanup-idle-google-connections-monthly": {
        "task": "backend.jobs.retention_cleanup.cleanup_idle_google_connections",
        "schedule": crontab(minute=0, hour=3, day_of_month=1),  # 1st of month, 03:00 UTC
        "options": {
            "queue": "focused",
            "expires": 604800,  # 7 days (survive worker downtime)
        }
    },
    # Inactive accounts: 6-month inactivity hard-delete
    "cleanup-inactive-accounts-monthly": {
        "task": "backend.jobs.retention_cleanup.cleanup_inactive_accounts",
        "schedule": crontab(minute=0, hour=4, day_of_month=1),  # 1st of month, 04:00 UTC
        "options": {
            "queue": "focused",
            "expires": 604800,  # 7 days (survive worker downtime)
        }
    },
}


# ---------------------------------------------------------------------
# Periodic Task: Cleanup Event Descriptions (Increment 6C)
# ---------------------------------------------------------------------
@celery_app.task(
    name="backend.core.celery_app.cleanup_event_descriptions",
    bind=True,
    max_retries=3,
    default_retry_delay=60,  # 1 minute initial delay
)
def cleanup_event_descriptions(self):
    """
    Celery periodic task: Delete event descriptions older than 72 hours.

    Runs every 6 hours to comply with GDPR data minimization.

    This task wraps the async cleanup function and runs it in a sync context.

    Task Configuration:
    - Max retries: 3
    - Retry backoff: Exponential (60s, 120s, 240s)
    - Expires: 8 hours (2h buffer above 6h schedule for GDPR compliance)

    GDPR Timing:
    - Descriptions must be deleted at 72 hours
    - Cleanup runs every 6 hours (0:00, 6:00, 12:00, 18:00)
    - Worst case: Description stays for 72h + up to 6h = 78h (still compliant)
    - Expiry at 8h ensures no gaps in cleanup coverage
    """
    logger.info("[celery] Starting periodic description cleanup task")

    try:
        # Import inside task to avoid early DB initialization on Celery boot
        # This prevents circular imports and defers heavy imports until task execution
        from backend.apps.focused.logic.sync.clean_eventdescr import cleanup_old_descriptions
        from backend.core.database import AsyncSessionLocal

        async def run_cleanup():
            async with AsyncSessionLocal() as session:
                deleted_count = await cleanup_old_descriptions(session)
                # CRITICAL: Commit to persist changes to database
                await session.commit()
                return deleted_count

        # Run async function in sync context
        # CRITICAL: Use get_event_loop() instead of asyncio.run()
        # asyncio.run() creates a NEW loop which can deadlock in Celery workers
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                # If loop is closed, create a new one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            # No event loop exists, create one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        deleted_count = loop.run_until_complete(run_cleanup())

        logger.info(f"[celery] Description cleanup completed: {deleted_count} deleted")
        return deleted_count

    except Exception as e:
        logger.error(f"[celery] Description cleanup failed: {e}")
        # Retry with exponential backoff (max 3 attempts)
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


# ---------------------------------------------------------------------
# Auto-Deactivate Focus Mode Task (Increment 11)
# ---------------------------------------------------------------------
@celery_app.task(
    name="backend.core.celery_app.auto_deactivate_focus",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def auto_deactivate_focus(self, user_id: str, session_id: str, job_id: str):
    """
    Celery task: Auto-deactivate focus mode after duration expires.

    Called when a user activates focus mode with duration_minutes.
    The task:
    1. Loads the focus session by (user_id, session_id)
    2. If actual_end IS NULL: sets actual_end = now (closes the session)
    3. If actual_end already set: no-op (idempotent)
    4. Updates the scheduled job status to 'completed'

    NOTE: This task only updates DB state. It does NOT generate or deliver
    shortcut_url - that requires notify_user() which is Increment 12+.

    Args:
        user_id: User UUID string
        session_id: Focus session UUID string
        job_id: Scheduled job UUID string

    Returns:
        Dictionary with result status
    """
    logger.info(
        f"[celery] Auto-deactivate focus task started: "
        f"user_id={user_id}, session_id={session_id}, job_id={job_id}"
    )

    try:
        from datetime import datetime, timezone
        from uuid import UUID

        from sqlalchemy import select, update

        from backend.apps.focused.db_models import FocusedFocusSession, FocusedScheduledJob
        from backend.core.database import AsyncSessionLocal

        async def run_deactivation():
            async with AsyncSessionLocal() as session:
                # Parse UUIDs
                try:
                    user_uuid = UUID(user_id)
                    session_uuid = UUID(session_id)
                    job_uuid = UUID(job_id)
                except ValueError as e:
                    logger.error(f"[celery] Invalid UUID format: {e}")
                    return {"success": False, "error": "invalid_uuid"}

                # Load focus session
                stmt = select(FocusedFocusSession).where(
                    FocusedFocusSession.id == session_uuid,
                    FocusedFocusSession.user_id == user_uuid,
                )
                result = await session.execute(stmt)
                focus_session = result.scalar_one_or_none()

                if not focus_session:
                    logger.warning(
                        f"[celery] Focus session not found: session_id={session_id}"
                    )
                    # Still mark job as completed (session may have been deleted)
                    await _mark_job_status(session, job_uuid, "completed")
                    await session.commit()
                    return {"success": True, "status": "session_not_found"}

                # Check if already deactivated (idempotent)
                if focus_session.actual_end is not None:
                    logger.info(
                        f"[celery] Focus session already deactivated: session_id={session_id}"
                    )
                    await _mark_job_status(session, job_uuid, "completed")
                    await session.commit()
                    return {"success": True, "status": "already_deactivated"}

                # Deactivate the session
                now = datetime.now(timezone.utc)
                focus_session.actual_end = now

                # Mark job as completed
                await _mark_job_status(session, job_uuid, "completed")

                await session.commit()

                logger.info(
                    f"[celery] Focus session deactivated: session_id={session_id}"
                )
                return {"success": True, "status": "deactivated"}

        async def _mark_job_status(session, job_uuid, status):
            """Update scheduled job status."""
            stmt = (
                update(FocusedScheduledJob)
                .where(FocusedScheduledJob.id == job_uuid)
                .values(status=status, updated_at=datetime.now(timezone.utc))
            )
            await session.execute(stmt)

        # Run async function in sync context
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        result = loop.run_until_complete(run_deactivation())

        logger.info(f"[celery] Auto-deactivate task completed: {result}")
        return result

    except Exception as e:
        logger.error(f"[celery] Auto-deactivate focus failed: {e}")

        # Try to mark job as failed
        try:
            from uuid import UUID
            from sqlalchemy import update
            from backend.apps.focused.db_models import FocusedScheduledJob
            from backend.core.database import AsyncSessionLocal

            async def mark_failed():
                async with AsyncSessionLocal() as session:
                    stmt = (
                        update(FocusedScheduledJob)
                        .where(FocusedScheduledJob.id == UUID(job_id))
                        .values(
                            status="failed",
                            retry_count=FocusedScheduledJob.retry_count + 1,
                            updated_at=datetime.now(timezone.utc),
                        )
                    )
                    await session.execute(stmt)
                    await session.commit()

            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            loop.run_until_complete(mark_failed())
        except Exception as inner_e:
            logger.error(f"[celery] Failed to mark job as failed: {inner_e}")

        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=30 * (2 ** self.request.retries))


# ---------------------------------------------------------------------
# Cleanup Scheduled Jobs Task (Increment 11)
# ---------------------------------------------------------------------
@celery_app.task(
    name="backend.core.celery_app.cleanup_scheduled_jobs",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def cleanup_scheduled_jobs(self):
    """
    Celery periodic task: Delete old scheduled jobs.

    Retention policy (per Increment 11 spec):
    - Jobs with status IN ('completed', 'failed', 'cancelled')
    - Where updated_at < NOW() - INTERVAL '7 days'

    Runs daily at 3:00 AM UTC.
    """
    logger.info("[celery] Starting scheduled jobs cleanup task")

    try:
        from datetime import datetime, timedelta, timezone

        from sqlalchemy import delete, select

        from backend.apps.focused.db_models import FocusedScheduledJob
        from backend.core.database import AsyncSessionLocal

        async def run_cleanup():
            async with AsyncSessionLocal() as session:
                cutoff = datetime.now(timezone.utc) - timedelta(days=7)

                # First, query jobs to be deleted for logging
                select_stmt = select(
                    FocusedScheduledJob.id,
                    FocusedScheduledJob.status,
                    FocusedScheduledJob.payload,
                ).where(
                    FocusedScheduledJob.status.in_(["completed", "failed", "cancelled"]),
                    FocusedScheduledJob.updated_at < cutoff,
                )
                result = await session.execute(select_stmt)
                jobs_to_delete = result.fetchall()

                # Log each job being deleted (for debugging/audit)
                for job_id, status, payload in jobs_to_delete:
                    session_id = payload.get("session_id") if payload else None
                    logger.debug(
                        "[celery] Deleting scheduled job",
                        extra={
                            "job_id": str(job_id),
                            "status": status,
                            "session_id": session_id,
                        },
                    )

                # Now delete the jobs
                delete_stmt = delete(FocusedScheduledJob).where(
                    FocusedScheduledJob.status.in_(["completed", "failed", "cancelled"]),
                    FocusedScheduledJob.updated_at < cutoff,
                )
                await session.execute(delete_stmt)
                await session.commit()

                return len(jobs_to_delete)

        # Run async function in sync context
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        deleted_count = loop.run_until_complete(run_cleanup())

        logger.info(
            "[celery] Scheduled jobs cleanup completed",
            extra={
                "deleted_count": deleted_count,
                "retention_days": 7,
                "statuses_cleaned": ["completed", "failed", "cancelled"],
            },
        )
        return deleted_count

    except Exception as e:
        logger.error(
            "[celery] Scheduled jobs cleanup failed",
            extra={"error": str(e), "retry_count": self.request.retries},
        )
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


# ---------------------------------------------------------------------
# Trigger Focus Activation Task (Increment 20)
# ---------------------------------------------------------------------
@celery_app.task(
    name="backend.core.celery_app.trigger_focus_activation",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def trigger_focus_activation(self, user_id: str, session_id: str, job_id: str):
    """
    Celery task: Trigger focus mode activation at scheduled time.

    Called by the sync pipeline when a focus block is detected.
    Scheduled for (event_start_time - LEAD_TIME_MINUTES).

    Flow:
    1. Update job status to 'running'
    2. Re-fetch session from DB (verify still valid)
    3. Check user has no active focus session
    4. Generate shortcut URL via run_focus_mode_internal()
    5. Load consent preference
    6. Set final status: 'pending_notification' or 'pending_confirmation'

    Note: This task does NOT activate Focus Mode directly (iOS prevents that).
    It prepares the shortcut URL for notification delivery (Increment 21).

    Args:
        user_id: User UUID string
        session_id: Focus session UUID string
        job_id: Scheduled job UUID string

    Returns:
        Dictionary with result status and shortcut_url
    """
    logger.info(
        f"[celery] Trigger focus activation task started: "
        f"user_id={user_id}, session_id={session_id}, job_id={job_id}"
    )

    try:
        from uuid import UUID

        from backend.apps.focused.logic.activation_helpers import (
            fetch_focus_session,
            fetch_user_active_session,
            fetch_consent_preferences,
            update_job_status,
        )
        from backend.apps.focused.tools.focus_activation_internal import (
            run_focus_mode_internal,
        )
        from backend.core.database import AsyncSessionLocal

        async def run_activation():
            async with AsyncSessionLocal() as db:
                # Parse UUIDs
                try:
                    user_uuid = UUID(user_id)
                    session_uuid = UUID(session_id)
                    job_uuid = UUID(job_id)
                except ValueError as e:
                    logger.error(f"[celery] Invalid UUID format: {e}")
                    return {"success": False, "error": "invalid_uuid"}

                # 1. Update job status to 'running'
                await update_job_status(db, job_uuid, "running")

                # 2. Re-fetch focus session from DB
                focus_session = await fetch_focus_session(db, session_uuid, user_uuid)

                if not focus_session:
                    logger.warning(
                        f"[celery] Focus session not found: session_id={session_id}"
                    )
                    await update_job_status(
                        db, job_uuid, "cancelled",
                        error_reason="session_not_found"
                    )
                    await db.commit()
                    return {"success": False, "status": "session_not_found"}

                # Check if session is still a focus block
                if not focus_session.is_focus_block:
                    logger.info(
                        f"[celery] Session no longer a focus block: session_id={session_id}"
                    )
                    await update_job_status(
                        db, job_uuid, "cancelled",
                        error_reason="not_focus_block"
                    )
                    await db.commit()
                    return {"success": False, "status": "not_focus_block"}

                # Check if session was soft-deleted
                if focus_session.status == "deleted":
                    logger.info(
                        f"[celery] Focus session was deleted: session_id={session_id}"
                    )
                    await update_job_status(
                        db, job_uuid, "cancelled",
                        error_reason="session_deleted"
                    )
                    await db.commit()
                    return {"success": False, "status": "session_deleted"}

                # 3. Check user has no active focus session
                active_session = await fetch_user_active_session(db, user_uuid)

                if active_session:
                    logger.info(
                        f"[celery] User already has active focus session: "
                        f"active_session_id={active_session.id}"
                    )
                    await update_job_status(
                        db, job_uuid, "skipped",
                        error_reason="active_session_exists"
                    )
                    await db.commit()
                    return {"success": False, "status": "skipped", "reason": "active_session_exists"}

                # 4. Generate shortcut URL
                # NOTE: run_focus_mode_internal() is pure CPU-bound (string ops only).
                # No timeout required unless future versions introduce I/O.
                try:
                    activation_data = run_focus_mode_internal(focus_session)
                    shortcut_url = activation_data.get("shortcut_url")
                    focus_name = activation_data.get("focus_name")
                    end_time = activation_data.get("end_time")

                    # Validate required fields
                    if not shortcut_url:
                        raise ValueError("run_focus_mode_internal returned no shortcut_url")
                    if not focus_name:
                        raise ValueError("run_focus_mode_internal returned no focus_name")
                except Exception as e:
                    logger.error(f"[celery] Failed to generate shortcut URL: {e}")
                    await update_job_status(
                        db, job_uuid, "failed",
                        error_reason=f"url_generation_failed: {str(e)[:200]}"
                    )
                    await db.commit()
                    return {"success": False, "status": "failed", "error": str(e)}

                # 5. Load consent preferences
                preferences = await fetch_consent_preferences(db, user_uuid)

                # Default: auto_handle_focus_blocks = False
                auto_handle = preferences.auto_handle_focus_blocks if preferences else False

                # 6. Set final status based on preference
                if auto_handle:
                    # User wants automatic notifications
                    final_status = "pending_notification"
                    logger.info(
                        f"[celery] Activation ready for notification: "
                        f"session_id={session_id}, focus_name={focus_name}"
                    )
                else:
                    # User must initiate via ChatGPT
                    final_status = "pending_confirmation"
                    logger.info(
                        f"[celery] Activation awaiting user confirmation: "
                        f"session_id={session_id}, focus_name={focus_name}"
                    )

                # Update job with shortcut_url and final status
                await update_job_status(
                    db, job_uuid, final_status,
                    shortcut_url=shortcut_url
                )
                await db.commit()

                return {
                    "success": True,
                    "status": final_status,
                    "shortcut_url": shortcut_url,
                    "focus_name": focus_name,
                    "end_time": end_time,  # May be None if session has no end_time
                }

        # Run async function in sync context
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        result = loop.run_until_complete(run_activation())

        logger.info(f"[celery] Trigger focus activation completed: {result}")
        return result

    except Exception as e:
        logger.error(f"[celery] Trigger focus activation failed: {e}")

        # Try to mark job as failed
        try:
            from datetime import datetime, timezone
            from uuid import UUID

            from backend.apps.focused.logic.activation_helpers import update_job_status
            from backend.core.database import AsyncSessionLocal

            async def mark_failed():
                async with AsyncSessionLocal() as db:
                    await update_job_status(
                        db, UUID(job_id), "failed",
                        error_reason=f"task_exception: {str(e)[:200]}"
                    )
                    await db.commit()

            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            loop.run_until_complete(mark_failed())
        except Exception as inner_e:
            logger.error(f"[celery] Failed to mark job as failed: {inner_e}")

        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=30 * (2 ** self.request.retries))


# ---------------------------------------------------------------------
# TODO: Token and Webhook Renewal Tasks
# ---------------------------------------------------------------------
def renew_google_token(user_id: str) -> dict:
    """
    Background task to renew Google access token.

    Args:
        user_id: User identifier

    Returns:
        Result status
    """
    # TODO: Implement token renewal
    pass


def renew_webhook(user_id: str, resource_id: str) -> dict:
    """
    Background task to renew Google Calendar webhook.

    Args:
        user_id: User identifier
        resource_id: Webhook resource ID

    Returns:
        Result status
    """
    # TODO: Implement webhook renewal
    pass
