"""
Webhook event processing logic for Focused app.

Handles Google Calendar push notification webhooks with:
- Idempotency checks (Redis)
- Validation
- Inline webhook renewal (with throttling)
- Event logging

No event processing yet - that comes in a future increment.
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.models import CoreConnection
from backend.core.redis_client import check_webhook_idempotency, check_renewal_throttle, set_needs_sync
from backend.apps.focused.logic_registerwebhook import register_calendar_webhook

logger = logging.getLogger(__name__)


def should_renew_webhook(expires_at: datetime | None, threshold_hours: int = 48) -> bool:
    """
    Check if webhook channel should be renewed.

    Args:
        expires_at: Webhook expiration timestamp
        threshold_hours: Renew if expiring within this many hours

    Returns:
        True if renewal is needed, False otherwise
    """
    if expires_at is None:
        return False

    now = datetime.now(timezone.utc)
    renewal_threshold = now + timedelta(hours=threshold_hours)

    return expires_at <= renewal_threshold


async def process_webhook_event(
    user_id: str,
    channel_id: str | None,
    resource_state: str | None,
    resource_id: str | None,
    message_number: str | None,
    session: AsyncSession,
    http_client: httpx.AsyncClient,
) -> None:
    """
    Process incoming Google Calendar webhook event.

    Flow:
    1. Check idempotency (Redis)
    2. Set needs_sync flag (marks calendar changed)
    3. Validate headers
    4. Load and validate user connection
    5. Check if renewal needed -> renew inline if yes (with throttling)
    6. Validate channel_id matches
    7. Log webhook event

    This function NEVER raises exceptions. All errors are logged and handled gracefully.
    Always completes successfully to ensure router returns 200 OK to Google. (Google requirements)

    Args:
        user_id: User ID from URL path
        channel_id: Google webhook channel ID
        resource_state: Google webhook resource state (sync/exists/not_exists)
        resource_id: Google webhook resource ID
        message_number: Google webhook message number (for idempotency)
        session: Database session
        http_client: HTTP client for Google API calls
    """
    try:
        # 1. Check idempotency FIRST (even with missing headers)
        if not message_number:
            logger.warning(f"[webhook] No message_number, skipping idempotency check: user={user_id}")
            # Continue processing (can't check idempotency without message_number)
        else:
            is_new = await check_webhook_idempotency(user_id, message_number, ttl_seconds=86400)
            if not is_new:
                logger.info(f"[webhook] Duplicate detected, already processed: user={user_id}, msg={message_number}")
                return  # Duplicate - stop here

        # 2. Set needs_sync flag (ALWAYS, even with missing headers). Something in the user’s calendar changed. We haven’t processed the changes yet.
        await set_needs_sync(user_id, ttl_seconds=300)
        logger.debug(f"[webhook] needs_sync flag set for user={user_id}")

        # 3. Log if headers are missing (but continue processing)
        # resource_state and resource_id are optional (SYNC/TEST messages may omit them)
        if not channel_id:
            logger.warning(f"[webhook] Missing channel_id header: user={user_id}")

        # 4. Load user connection
        stmt = select(CoreConnection).where(
            CoreConnection.user_id == user_id,
            CoreConnection.provider == "google",
        )
        result = await session.execute(stmt)
        connection = result.scalar_one_or_none()

        if connection is None:
            logger.warning(f"[webhook] No Google connection found for user {user_id}")
            # Don't return - continue gracefully and skip connection-dependent logic

        # 5. Check if renewal needed and renew inline (with throttling)
        # CRITICAL: This must run BEFORE channel_id validation to prevent race conditions
        # (Google may send webhooks with new channel_id before DB commit finishes)
        # Only attempt renewal if we have a valid connection
        if connection and should_renew_webhook(connection.google_channel_expires_at, threshold_hours=48):
            # Check throttle to prevent redundant renewal attempts
            renewal_allowed = await check_renewal_throttle(user_id, ttl_seconds=86400)

            if renewal_allowed:
                logger.info(f"[webhook] Channel expires soon, renewing inline: user={user_id}")

                try:
                    renewal_result = await register_calendar_webhook(
                        user_id=user_id,
                        session=session,
                        http_client=http_client,
                    )

                    if "error" in renewal_result:
                        logger.error(f"[webhook] Inline renewal failed: {renewal_result['error']}")
                    else:
                        logger.info(
                            f"[webhook] Inline renewal succeeded: expires={renewal_result['expires_at']}"
                        )
                except Exception as renewal_error:
                    # Catch any exceptions from renewal to prevent webhook handler crash
                    logger.error(f"[webhook] Inline renewal raised exception: user={user_id}, error={renewal_error}")
                    # Continue processing - don't let renewal failure break webhook handler
            else:
                logger.info(
                    f"[webhook] Renewal throttled (already renewed recently): user={user_id}"
                )

        # 6. Validate channel_id matches (after renewal, to handle race conditions)
        # Only validate if we have both channel_id and connection
        if connection and channel_id and connection.google_channel_id != channel_id:
            logger.warning(
                f"[webhook] Channel ID mismatch: user={user_id}, "
                f"expected={connection.google_channel_id}, received={channel_id}"
            )
            # Log mismatch but don't return - continue to log receipt

        # 7. Log webhook receipt
        logger.info(
            f"[webhook] Webhook received and handled: user={user_id}, "
            f"channel_id={channel_id or 'none'}, resource_state={resource_state or 'none'}, msg={message_number or 'none'}"
        )

    except Exception as e:
        logger.error(f"[webhook] Unhandled exception processing webhook for user {user_id}: {e}")
        # Always return gracefully - router must return 200 OK to Google
