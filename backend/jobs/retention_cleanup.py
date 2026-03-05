"""
GDPR Retention Cleanup tasks (Increment 39).

Periodic tasks enforcing privacy policy data retention promises:
- Audit logs deleted after 90 days
- Google OAuth connections soft-revoked after 6 months inactivity
- Inactive accounts hard-deleted after 6 months (no active connections or consents)
"""

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from backend.core.celery_app import celery_app
from backend.core.logging import get_logger

logger = get_logger(__name__)


@celery_app.task(
    name="backend.jobs.retention_cleanup.cleanup_expired_audit_logs",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def cleanup_expired_audit_logs(self):
    """
    Celery periodic task: Delete audit logs older than 90 days.

    Uses atomic CTE delete with RETURNING in a loop to handle large datasets
    without blocking. PostgreSQL does not support DELETE ... LIMIT directly.

    Task Configuration:
    - Max retries: 3
    - Retry backoff: Exponential (60s, 120s, 240s)
    - Schedule: Daily at 02:00 UTC
    """
    job_run_id = str(uuid4())
    task_logger = logger.bind(job_run_id=job_run_id)

    task_logger.info("retention.audit_logs.start")
    start_time = datetime.now(timezone.utc)

    try:
        from backend.core.database import AsyncSessionLocal
        from sqlalchemy import text

        async def run_cleanup():
            total_deleted = 0

            async with AsyncSessionLocal() as session:
                # Loop with atomic CTE delete until no more rows match
                while True:
                    # Atomic CTE: select + delete in single statement
                    # RETURNING drives loop termination (not rowcount)
                    stmt = text("""
                        WITH rows AS (
                            SELECT id FROM core_tool_audit_log
                            WHERE created_at < NOW() - INTERVAL '90 days'
                            ORDER BY created_at
                            LIMIT 500
                        )
                        DELETE FROM core_tool_audit_log
                        WHERE id IN (SELECT id FROM rows)
                        RETURNING id
                    """)

                    result = await session.execute(stmt)
                    deleted_ids = result.fetchall()
                    batch_count = len(deleted_ids)

                    if batch_count == 0:
                        # No more rows to delete
                        break

                    total_deleted += batch_count
                    await session.commit()

                return total_deleted

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

        duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
        task_logger.info(
            "retention.audit_logs.complete",
            deleted_count=deleted_count,
            duration_ms=duration_ms
        )
        return deleted_count

    except Exception as e:
        task_logger.error(
            "retention.audit_logs.error",
            error=str(e)
        )
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


@celery_app.task(
    name="backend.jobs.retention_cleanup.cleanup_idle_google_connections",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def cleanup_idle_google_connections(self):
    """
    Celery periodic task: Soft-revoke Google connections inactive for 6+ months.

    Target rows where:
    - connection_type = 'google'
    - revoked_at IS NULL
    - last_used_at < NOW() - 6 months OR (last_used_at IS NULL AND created_at < NOW() - 6 months)

    Action: Set revoked_at = now (soft revoke, mirrors disconnect pattern).
    Does NOT cascade-delete the user. Live calendar access is terminated; user data retained.

    Task Configuration:
    - Max retries: 3
    - Retry backoff: Exponential (60s, 120s, 240s)
    - Schedule: Monthly, 1st of each month at 03:00 UTC
    """
    job_run_id = str(uuid4())
    task_logger = logger.bind(job_run_id=job_run_id)

    task_logger.info("retention.idle_connections.start")
    start_time = datetime.now(timezone.utc)

    try:
        from backend.core.database import AsyncSessionLocal
        from sqlalchemy import text

        async def run_cleanup():
            async with AsyncSessionLocal() as session:
                now = datetime.now(timezone.utc)

                # Soft-revoke connections idle for 6+ months
                # IS NULL fallback handles pre-migration connections
                stmt = text("""
                    UPDATE core_connections
                    SET revoked_at = :now
                    WHERE connection_type = 'google'
                      AND revoked_at IS NULL
                      AND (
                          last_used_at < NOW() - INTERVAL '6 months'
                          OR (last_used_at IS NULL AND created_at < NOW() - INTERVAL '6 months')
                      )
                    RETURNING id
                """)

                result = await session.execute(stmt, {"now": now})
                revoked_count = len(result.fetchall())

                await session.commit()

                return revoked_count

        # Run async function in sync context
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        revoked_count = loop.run_until_complete(run_cleanup())

        duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
        task_logger.info(
            "retention.idle_connections.complete",
            revoked_count=revoked_count,
            duration_ms=duration_ms
        )
        return revoked_count

    except Exception as e:
        task_logger.error(
            "retention.idle_connections.error",
            error=str(e)
        )
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


@celery_app.task(
    name="backend.jobs.retention_cleanup.cleanup_inactive_accounts",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def cleanup_inactive_accounts(self):
    """
    Celery periodic task: Hard-delete fully inactive user accounts.

    A user qualifies for deletion when ALL of the following are true:
    - core_users.created_at < NOW() - 6 months
    - No active Google connection (no row where user_id = X AND revoked_at IS NULL)
    - No active consent (no row where user_id = X AND revoked_at IS NULL)

    Action: Hard delete core_users row. Existing ON DELETE CASCADE FKs propagate to:
    core_connections, core_consents, pg_priorities -> pg_deliverables, pg_goals,
    pg_weekly_snapshots, OAuth sessions and tokens.

    core_tool_audit_log rows are NOT deleted (intentionally no FK to core_users;
    audit logs expire independently via cleanup_expired_audit_logs).

    Task Configuration:
    - Max retries: 3
    - Retry backoff: Exponential (60s, 120s, 240s)
    - Schedule: Monthly, 1st of each month at 04:00 UTC (1 hour after Task 2)
    """
    job_run_id = str(uuid4())
    task_logger = logger.bind(job_run_id=job_run_id)

    task_logger.info("retention.inactive_accounts.start")
    start_time = datetime.now(timezone.utc)

    try:
        from backend.core.database import AsyncSessionLocal
        from sqlalchemy import text

        async def run_cleanup():
            async with AsyncSessionLocal() as session:
                # Delete users who:
                # 1. Were created more than 6 months ago
                # 2. Have no active connection (revoked_at IS NULL)
                # 3. Have no active consent (revoked_at IS NULL)
                #
                # The NOT EXISTS subqueries ensure we only delete truly inactive users.
                # CASCADE handles all dependent records except audit logs.
                stmt = text("""
                    DELETE FROM core_users
                    WHERE created_at < NOW() - INTERVAL '6 months'
                      AND NOT EXISTS (
                          SELECT 1 FROM core_connections
                          WHERE core_connections.user_id = core_users.id
                            AND core_connections.revoked_at IS NULL
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM core_consents
                          WHERE core_consents.user_id = core_users.id
                            AND core_consents.revoked_at IS NULL
                      )
                    RETURNING id
                """)

                result = await session.execute(stmt)
                deleted_count = len(result.fetchall())

                await session.commit()

                return deleted_count

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

        duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
        # Do not log individual user UUIDs — log count only (privacy)
        task_logger.info(
            "retention.inactive_accounts.complete",
            deleted_count=deleted_count,
            duration_ms=duration_ms
        )
        return deleted_count

    except Exception as e:
        task_logger.error(
            "retention.inactive_accounts.error",
            error=str(e)
        )
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
