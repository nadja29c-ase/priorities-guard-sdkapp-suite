"""
OAuth Provider cleanup tasks (Increment 7B + 7C + 19).

Periodic tasks for cleaning up expired OAuth data with structured logging:
- Authorization codes (expired after 10 minutes)
- Access tokens (expired after 1 hour)
- Refresh tokens (expired after 30 days)
- OAuth sessions (expired after 2 years of inactivity) - Increment 19
"""

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from backend.core.celery_app import celery_app
from backend.core.logging import get_logger

logger = get_logger(__name__)


@celery_app.task(
    name="backend.jobs.oauth_cleanup.cleanup_expired_oauth_codes",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def cleanup_expired_oauth_codes(self):
    """
    Celery periodic task: Delete expired OAuth authorization codes.

    Runs every 15 minutes to remove authorization codes that have expired
    (10 minute lifetime).

    This prevents the oauth_authorization_codes table from growing indefinitely.

    Task Configuration:
    - Max retries: 3
    - Retry backoff: Exponential (60s, 120s, 240s)
    - Schedule: Every 15 minutes
    """
    # Generate correlation_id for background job
    correlation_id = str(uuid4())
    task_logger = logger.bind(correlation_id=correlation_id)

    task_logger.info("oauth.cleanup.codes.start")

    try:
        # Import inside task to avoid early DB initialization
        from backend.core.database import AsyncSessionLocal
        from backend.core.oauth_provider.models import OAuthAuthorizationCode
        from sqlalchemy import select, delete

        async def run_cleanup():
            async with AsyncSessionLocal() as session:
                # Find expired codes
                now = datetime.now(timezone.utc)

                # Delete expired authorization codes
                stmt = delete(OAuthAuthorizationCode).where(
                    OAuthAuthorizationCode.expires_at < now
                )

                result = await session.execute(stmt)
                deleted_count = result.rowcount

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

        task_logger.info(
            "oauth.cleanup.codes.complete",
            deleted_count=deleted_count
        )
        return deleted_count

    except Exception as e:
        task_logger.error(
            "oauth.cleanup.codes.error",
            error=str(e)
        )
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


@celery_app.task(
    name="backend.jobs.oauth_cleanup.cleanup_expired_oauth_tokens",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def cleanup_expired_oauth_tokens(self):
    """
    Celery periodic task: Delete expired OAuth access tokens.

    Runs every hour to remove access tokens that have expired
    (1 hour lifetime for access tokens, 30 days for refresh tokens).

    Deletes tokens where both access token AND refresh token have expired.

    Task Configuration:
    - Max retries: 3
    - Retry backoff: Exponential (60s, 120s, 240s)
    - Schedule: Every hour
    """
    # Generate correlation_id for background job
    correlation_id = str(uuid4())
    task_logger = logger.bind(correlation_id=correlation_id)

    task_logger.info("oauth.cleanup.tokens.start")

    try:
        # Import inside task to avoid early DB initialization
        from backend.core.database import AsyncSessionLocal
        from backend.core.oauth_provider.models import OAuthAccessToken
        from sqlalchemy import select, delete, or_

        async def run_cleanup():
            async with AsyncSessionLocal() as session:
                now = datetime.now(timezone.utc)

                # Delete tokens where BOTH access token and refresh token expired
                # (Keep tokens if refresh token is still valid)
                stmt = delete(OAuthAccessToken).where(
                    OAuthAccessToken.expires_at < now,
                    or_(
                        OAuthAccessToken.refresh_token_expires_at < now,
                        OAuthAccessToken.refresh_token_expires_at.is_(None)
                    )
                )

                result = await session.execute(stmt)
                deleted_count = result.rowcount

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

        task_logger.info(
            "oauth.cleanup.tokens.complete",
            deleted_count=deleted_count
        )
        return deleted_count

    except Exception as e:
        task_logger.error(
            "oauth.cleanup.tokens.error",
            error=str(e)
        )
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


@celery_app.task(
    name="backend.jobs.oauth_cleanup.cleanup_expired_oauth_sessions",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def cleanup_expired_oauth_sessions(self):
    """
    Celery task: Delete expired OAuth browser sessions (Increment 19).

    Sessions expire after 2 years of inactivity (sliding window).
    This task should be scheduled weekly.

    Task Configuration:
    - Max retries: 3
    - Retry backoff: Exponential (60s, 120s, 240s)
    - Schedule: Weekly (not configured here, add to beat schedule)
    """
    # Generate correlation_id for background job
    correlation_id = str(uuid4())
    task_logger = logger.bind(correlation_id=correlation_id)

    task_logger.info("oauth.cleanup.sessions.start")

    try:
        # Import inside task to avoid early DB initialization
        from backend.core.database import AsyncSessionLocal
        from backend.core.oauth_provider.models import OAuthSession
        from sqlalchemy import delete

        async def run_cleanup():
            async with AsyncSessionLocal() as session:
                now = datetime.now(timezone.utc)

                # Delete expired sessions
                stmt = delete(OAuthSession).where(
                    OAuthSession.expires_at < now
                )

                result = await session.execute(stmt)
                deleted_count = result.rowcount

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

        task_logger.info(
            "oauth.cleanup.sessions.complete",
            deleted_count=deleted_count
        )
        return deleted_count

    except Exception as e:
        task_logger.error(
            "oauth.cleanup.sessions.error",
            error=str(e)
        )
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
