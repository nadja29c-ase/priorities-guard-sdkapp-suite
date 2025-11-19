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
from .logic_sync import sync_calendar_events
from .logic_cleanup import cleanup_old_descriptions
from .models.requests import CheckCalendarRequest, WatchCalendarRequest, SyncCalendarRequest

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
# Sync Calendar Endpoint — Manual sync trigger 
# ---------------------------------------------------------------------
@router.post("/sync_calendar")
async def sync_calendar(
    payload: SyncCalendarRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """
    Manually trigger calendar sync for a user.

    Used for testing and manual sync operations.
    Syncs Google Calendar events into focused_focus_sessions table.

    Process:
        1. Check needs_sync flag in Redis
        2. Fetch events from Google Calendar (timeMin=-1d, timeMax=+30d)
        3. Upsert events in batches of 100
        4. Detect and soft-delete orphaned events
        5. Update last_synced_at timestamp
        6. Clear needs_sync flag

    Returns:
        {
            "success": True,
            "data": {
                "events_fetched": int,
                "events_inserted": int,
                "events_updated": int,
                "events_deleted": int
            }
        }
    """
    try:
        http_client = request.app.state.http_client

        result = await sync_calendar_events(
            user_id=payload.user_id,
            session=session,
            http_client=http_client,
        )

        # Check if logic returned an error
        if not result.get("success"):
            error_code = result.get("error", "SYNC_FAILED")

            # Map error codes to HTTP-friendly messages
            error_messages = {
                "USER_NOT_CONNECTED": "User has not connected their Google Calendar",
                "TOKEN_REFRESH_FAILED": "Failed to refresh access token",
                "REFRESH_TOKEN_INVALID": "Refresh token is invalid or revoked",
                "API_QUOTA_EXCEEDED": "Google API quota exceeded",
                "DATABASE_ERROR": "Database error occurred during sync",
                "GOOGLE_API_ERROR": "Error fetching events from Google Calendar",
                "EVENT_PROCESSING_ERROR": "Error processing calendar events",
            }

            return {
                "success": False,
                "error": {
                    "code": error_code,
                    "message": error_messages.get(error_code, result.get("error", "Sync failed")),
                },
            }

        # Success - return sync results
        return {
            "success": True,
            "data": {
                "events_fetched": result.get("events_fetched", 0),
                "events_inserted": result.get("events_inserted", 0),
                "events_updated": result.get("events_updated", 0),
                "events_deleted": result.get("events_deleted", 0),
                "message": result.get("message", "Sync completed successfully")
            },
        }

    except Exception as e:
        logger.error(f"Unexpected error in sync_calendar: {e}")
        return {
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred during sync",
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


# ---------------------------------------------------------------------
# Admin Endpoint — Cleanup Descriptions (Increment 6C)
# ---------------------------------------------------------------------
@router.post("/admin/cleanup_descriptions")
async def admin_cleanup_descriptions(
    session: AsyncSession = Depends(get_db),
):
    """
    Manually trigger description cleanup (dev/testing endpoint).

    Deletes event_description fields older than 72 hours to comply
    with GDPR data minimization principles.

    NOTE: This endpoint is for development and testing only.
    In production, cleanup runs automatically via Celery every 6 hours.

    Protection will be added later.

    Returns:
        {
            "success": True,
            "data": {
                "descriptions_deleted": int,
                "message": str
            }
        }
    """
    try:
        deleted_count = await cleanup_old_descriptions(session)

        return {
            "success": True,
            "data": {
                "descriptions_deleted": deleted_count,
                "message": f"Cleaned up {deleted_count} event descriptions older than 72 hours"
            }
        }

    except Exception as e:
        logger.error(f"Admin cleanup failed: {e}")
        return {
            "success": False,
            "error": {
                "code": "CLEANUP_FAILED",
                "message": "Failed to cleanup descriptions"
            }
        }
