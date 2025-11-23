"""
Focused MCP Tool Endpoints Router.

HTTP endpoints for MCP tools:
- check_calendar: Scan calendar for focus blocks
- watch_calendar: Register webhook for calendar changes
- sync_calendar: Manual sync trigger
"""

import logging
from fastapi import APIRouter, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.apps.focused.models.requests import (
    CheckCalendarRequest,
    WatchCalendarRequest,
    SyncCalendarRequest,
)
from backend.apps.focused.tools.check_calendar_impl import check_calendar_impl
from backend.apps.focused.tools.watch_calendar_impl import register_calendar_webhook
from backend.apps.focused.logic.sync.orchestrator import sync_calendar_events
from backend.apps.focused.utils.user_id_extraction import extract_user_id

logger = logging.getLogger(__name__)

router = APIRouter(tags=["focused-tools"])


# ---------------------------------------------------------------------
# Check Calendar — Main MCP tool endpoint
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

    Identity Source (Increment 7D):
        - Primary: X-User-ID header (from MCP after JWT validation)
        - Fallback: hardcoded test_user (for backward compatibility)
        - Logs warning if fallback is used
    """
    try:
        # Increment 7D: Extract user_id from X-User-ID header (with fallback)
        user_id = extract_user_id(request, None, "check_calendar")

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
# Watch Calendar — Register webhook (used by MCP tool)
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

    Identity Source (Increment 7D):
        - Primary: X-User-ID header (from MCP after JWT validation)
        - Fallback: payload.user_id (for backward compatibility)
        - Logs warning if fallback is used or mismatch detected
    """
    try:
        http_client = request.app.state.http_client

        # Increment 7D: Extract user_id from X-User-ID header (with fallback)
        user_id = extract_user_id(request, payload.user_id, "watch_calendar")

        result = await register_calendar_webhook(
            user_id=user_id,
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
# Sync Calendar — Manual sync trigger
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

    Identity Source (Increment 7D):
        - Primary: X-User-ID header (from MCP after JWT validation)
        - Fallback: payload.user_id (for backward compatibility)
        - Logs warning if fallback is used or mismatch detected

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

        # Increment 7D: Extract user_id from X-User-ID header (with fallback)
        user_id = extract_user_id(request, payload.user_id, "sync_calendar")

        result = await sync_calendar_events(
            user_id=user_id,
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
