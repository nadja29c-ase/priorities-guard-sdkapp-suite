"""
Google Calendar webhook registration logic for Focused app.

Handles registering push notification channels with Google Calendar API.
"""

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.google_calendar import register_webhook, stop_webhook
from backend.core.models import CoreConnection

from .logic_tokens import ensure_valid_access_token

logger = logging.getLogger(__name__)


async def register_calendar_webhook(
    user_id: str,
    session: AsyncSession,
    http_client: httpx.AsyncClient,
) -> dict[str, Any]:
    """
    Register Google Calendar push notification webhook.

    Flow:
    1. Load user's Google connection
    2. Check token expiration and auto-refresh if needed
    3. Stop existing webhook channel if present (log warning if fails, continue anyway)
    4. Generate new channel ID
    5. Register new webhook with Google
    6. Store channel metadata in DB
    7. Return success response

    Args:
        user_id: User ID
        session: Database session
        http_client: HTTP client for Google API calls

    Returns:
        Success dict with channel_id and expires_at, or error dict
    """
    # -----------------------------------------------------------
    # Load Google connection
    # -----------------------------------------------------------
    stmt = select(CoreConnection).where(
        CoreConnection.user_id == user_id,
        CoreConnection.provider == "google",
    )
    result = await session.execute(stmt)
    connection = result.scalar_one_or_none()

    if connection is None:
        logger.warning(f"[watch_calendar] No Google connection for user {user_id}")
        return {"error": "USER_NOT_CONNECTED"}

    # -----------------------------------------------------------
    # Ensure valid access token (auto-refresh if needed)
    # -----------------------------------------------------------
    token_result = await ensure_valid_access_token(connection, session, http_client)

    if "error" in token_result:
        return token_result

    access_token = token_result["access_token"]

    # -----------------------------------------------------------
    # Stop existing webhook channel if present
    # -----------------------------------------------------------
    if connection.google_channel_id and connection.google_resource_id:
        logger.info(f"Stopping existing webhook channel: {connection.google_channel_id}")
        stop_success = await stop_webhook(
            http_client=http_client,
            access_token=access_token,
            channel_id=connection.google_channel_id,
            resource_id=connection.google_resource_id,
        )
        if not stop_success:
            logger.warning(
                f"Failed to stop existing channel {connection.google_channel_id}, continuing with new registration"
            )
        # Continue regardless of stop result

    # -----------------------------------------------------------
    # Generate new channel ID and register webhook
    # -----------------------------------------------------------
    new_channel_id = uuid4().hex

    try:
        webhook_response = await register_webhook(
            http_client=http_client,
            access_token=access_token,
            channel_id=new_channel_id,
            user_id=user_id,
        )
    except ValueError as e:
        if str(e) == "API quota exceeded":
            return {"error": "API_QUOTA_EXCEEDED"}
        # All other ValueErrors (invalid request, server errors after retries, etc.)
        return {"error": "WEBHOOK_REGISTRATION_FAILED"}
    except Exception as e:
        logger.error(f"Webhook registration failed: {type(e).__name__}")
        return {"error": "WEBHOOK_REGISTRATION_FAILED"}

    # -----------------------------------------------------------
    # Extract response fields
    # -----------------------------------------------------------
    try:
        returned_channel_id = webhook_response.get("id")
        resource_id = webhook_response.get("resourceId")
        expiration_ms = webhook_response.get("expiration")

        if not returned_channel_id or not resource_id or not expiration_ms:
            logger.error("Google webhook response missing required fields")
            return {"error": "WEBHOOK_REGISTRATION_FAILED"}

        # Convert expiration from milliseconds to UTC datetime
        expires_at = datetime.fromtimestamp(int(expiration_ms) / 1000, tz=timezone.utc)

    except (ValueError, TypeError) as e:
        logger.error(f"Failed to parse webhook response: {e}")
        return {"error": "WEBHOOK_REGISTRATION_FAILED"}

    # -----------------------------------------------------------
    # Update DB with webhook metadata
    # -----------------------------------------------------------
    connection.google_channel_id = returned_channel_id
    connection.google_resource_id = resource_id
    connection.google_channel_expires_at = expires_at
    connection.updated_at = datetime.now(timezone.utc)
    await session.commit()

    logger.info(
        f"[watch_calendar] Webhook registered: channel_id={returned_channel_id}, expires={expires_at.isoformat()}"
    )

    # -----------------------------------------------------------
    # Return success response
    # -----------------------------------------------------------
    return {
        "channel_id": returned_channel_id,
        "expires_at": expires_at.isoformat(),
    }
