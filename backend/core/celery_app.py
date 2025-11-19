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
# Periodic task schedule (Increment 6C)
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
        from backend.apps.focused.logic_cleanup import cleanup_old_descriptions
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
