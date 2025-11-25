"""
Webhook Router — Google Calendar push notifications.

Receives webhook events from Google Calendar.
ALWAYS returns 200 OK to prevent Google from shutting down the channel.

User identification:
- Google sends X-Goog-Channel-ID header
- We look up user_id from channel_id in core_connections table
- No user_id in URL path (Google doesn't know our user IDs)
"""

import logging
from fastapi import APIRouter, Request, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.models import CoreConnection
from backend.apps.focused.logic.webhook.webhook_processor import process_webhook_event

logger = logging.getLogger(__name__)

router = APIRouter(tags=["focused-webhooks"])


@router.post("/google_calendar")
async def receive_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """
    Receive Google Calendar push notification webhooks.

    User is identified via X-Goog-Channel-ID header -> DB lookup.
    Parses headers and delegates all logic to process_webhook_event().
    ALWAYS returns 200 OK to prevent Google from shutting down the channel.
    """
    # Extract Google webhook headers
    channel_id = request.headers.get("X-Goog-Channel-ID")
    resource_state = request.headers.get("X-Goog-Resource-State")
    resource_id = request.headers.get("X-Goog-Resource-ID")
    message_number = request.headers.get("X-Goog-Message-Number")

    # Look up user_id from channel_id
    user_id = None
    if channel_id:
        result = await session.execute(
            select(CoreConnection.user_id).where(
                CoreConnection.google_channel_id == channel_id
            )
        )
        row = result.scalar_one_or_none()
        if row:
            user_id = row

    if not user_id:
        # Can't identify user - log and return 200 (Google requirement)
        logger.warning(f"[webhook] Unknown channel_id, cannot identify user: channel={channel_id}")
        return Response(status_code=200)

    http_client = request.app.state.http_client

    # Delegate ALL logic to webhook_processor.py
    await process_webhook_event(
        user_id=user_id,
        channel_id=channel_id,
        resource_state=resource_state,
        resource_id=resource_id,
        message_number=message_number,
        session=session,
        http_client=http_client,
    )

    # Always return 200 OK (no body needed - Google only checks status code)
    return Response(status_code=200)
