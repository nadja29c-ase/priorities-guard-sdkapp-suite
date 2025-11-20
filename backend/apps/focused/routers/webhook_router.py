"""
Webhook Router — Google Calendar push notifications.

Receives webhook events from Google Calendar.
ALWAYS returns 200 OK to prevent Google from shutting down the channel.
"""

import logging
from fastapi import APIRouter, Request, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.apps.focused.logic.webhook.webhook_processor import process_webhook_event

logger = logging.getLogger(__name__)

router = APIRouter(tags=["focused-webhooks"])


@router.post("/webhook/google_calendar/{user_id}")
async def receive_webhook(
    user_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """
    Receive Google Calendar push notification webhooks.

    Parses headers and delegates all logic to process_webhook_event().
    ALWAYS returns 200 OK to prevent Google from shutting down the channel.
    """
    # Extract Google webhook headers
    channel_id = request.headers.get("X-Goog-Channel-ID")
    resource_state = request.headers.get("X-Goog-Resource-State")
    resource_id = request.headers.get("X-Goog-Resource-ID")
    message_number = request.headers.get("X-Goog-Message-Number")

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
