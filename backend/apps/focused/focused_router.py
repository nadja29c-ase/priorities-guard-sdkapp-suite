"""
Focused Backend Router — HTTP endpoints for the Focused app.
MCP server calls these endpoints directly.

User keywords are NOT passed via API. The backend loads:
- system default keywords (config.py)
- user custom keywords (DB table)
"""

import logging
from fastapi import APIRouter, Request, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.core.database import get_db
from backend.core.models import CoreConnection

from .logic import check_calendar_impl, register_calendar_webhook
from .logic_webhook import process_webhook_event
from .models.requests import CheckCalendarRequest, WatchCalendarRequest

logger = logging.getLogger(__name__)

router = APIRouter(tags=["focused"])


# ---------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------
@router.get("/health")
async def health_check(request: Request):
    try:
        return {
            "success": True,
            "data": {
                "status": "ok",
                "service": "focused-backend",
                "version": "0.1.0",
            },
        }
    except Exception:
        return {
            "success": False,
            "error": {
                "code": "HEALTH_CHECK_FAILED",
                "message": "Health check endpoint encountered an error",
            },
        }


# ---------------------------------------------------------------------
# Main Endpoint — used by MCP tool
# ---------------------------------------------------------------------
@router.post("/check_calendar")
async def check_calendar(
    payload: CheckCalendarRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """
    MCP tool → backend endpoint.
    Loads:
        - system default keywords
        - user custom keywords
    Identifies focus blocks from Google Calendar.
    """
    try:
        # TEMP until OpenAI OAuth integration:
        # In Increment 3/4, replace with request.state.openai_user_id
        user_id = "test_user"

        http_client = request.app.state.http_client

        result = await check_calendar_impl(
            user_id=user_id,
            time_start=payload.time_start,
            time_end=payload.time_end,
            max_results=payload.max_results,
            session=session,
            http_client=http_client,
        )

        return {
            "success": True,
            "data": result,
        }

    except ValueError as e:
        # Known business/validation errors
        return {
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": str(e),
            },
        }

    except Exception as e:
        logger.error(f"Unexpected error in check_calendar: {e}")
        return {
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
            },
        }


# ---------------------------------------------------------------------
# Watch Calendar Endpoint — Register webhook - used by MCP tool
# ---------------------------------------------------------------------
@router.post("/watch_calendar")
async def watch_calendar(
    payload: WatchCalendarRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """
    Register Google Calendar push notification webhook.

    Registers a webhook channel with Google to receive real-time
    calendar event updates instead of polling.
    """
    try:
        http_client = request.app.state.http_client

        result = await register_calendar_webhook(
            user_id=payload.user_id,
            session=session,
            http_client=http_client,
        )

        # Check if logic returned an error
        if "error" in result:
            error_code = result["error"]

            # Map error codes to HTTP-friendly messages
            error_messages = {
                "USER_NOT_CONNECTED": "User has not connected their Google Calendar",
                "TOKEN_REFRESH_FAILED": "Failed to refresh access token",
                "REFRESH_TOKEN_INVALID": "Refresh token is invalid or revoked",
                "API_QUOTA_EXCEEDED": "Google API quota exceeded",
                "WEBHOOK_INVALID_REQUEST": "Invalid webhook request (400 - check configuration)",
                "WEBHOOK_RATE_LIMITED": "Webhook registration rate limited (429 - retry later)",
                "WEBHOOK_SERVER_ERROR": "Google server error (500/503 - temporary issue)",
                "WEBHOOK_NETWORK_ERROR": "Network error connecting to Google API",
                "WEBHOOK_REGISTRATION_FAILED": "Failed to register webhook with Google (unknown error)",
                "TOKEN_DECRYPTION_FAILED": "Failed to decrypt access token",
            }

            return {
                "success": False,
                "error": {
                    "code": error_code,
                    "message": error_messages.get(error_code, "An error occurred"),
                },
            }

        # Success - return structured response
        return {
            "success": True,
            "data": result,
        }

    except Exception as e:
        logger.error(f"Unexpected error in register_calendar_webhook: {e}")
        return {
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
            },
        }


# ---------------------------------------------------------------------
# Webhook Receiver — Google Calendar push notifications - used for Google Only
# ---------------------------------------------------------------------
@router.post("/webhook/focused/google_calendar/{user_id}")
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

    # Delegate ALL logic to logic_webhook.py
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
