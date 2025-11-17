"""
Focused business logic.

Fetches Google Calendar events and identifies focus blocks using:
- system default keywords
- user-defined custom keywords stored in DB

Keywords are NOT provided by the user in the tool call. The backend
determines the effective keyword list internally.
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.encryption import decrypt_token, encrypt_token
from backend.core.google_calendar import fetch_events, refresh_access_token, register_webhook, stop_webhook
from backend.core.models import CoreConnection
from backend.apps.focused.focused_config import get_default_keywords
from backend.apps.focused.db_models import FocusedUserKeyword  # <— custom user keywords table (optional MVP2)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Normalization helper
# ---------------------------------------------------------------------
def normalize(text: str) -> str:
    """
    Robust normalization for keyword matching:
    - lowercase
    - strip whitespace
    - collapse internal whitespace (spaces, tabs, newlines)
    """
    if not text:
        return ""
    text = text.lower().strip()
    return re.sub(r"\s+", " ", text)


# ---------------------------------------------------------------------
# Keyword matching — TITLE ONLY
# ---------------------------------------------------------------------
def matches_focus_keywords(event: dict, keywords: list[str]) -> str | None:
    """
    Match keywords ONLY against the event title (summary).
    """
    summary_norm = normalize(event.get("summary", ""))

    for keyword in keywords:
        keyword_norm = normalize(keyword)
        if keyword_norm in summary_norm:
            return keyword

    return None


# ---------------------------------------------------------------------
# Load user custom keywords from DB (safe for MVP1)
# ---------------------------------------------------------------------
async def load_user_custom_keywords(user_id: str, session: AsyncSession) -> list[str]:
    """
    Load custom user keywords from DB.

    For MVP1, this table may be empty or not built yet.
    Return empty list gracefully.
    """
    try:
        stmt = select(FocusedUserKeyword.keyword).where(
            FocusedUserKeyword.user_id == user_id
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return [row.strip() for row in rows if row and row.strip()]
    except Exception:
        # If table not created yet → MVP1 safe fallback
        # Rollback the session to clear the failed transaction state
        await session.rollback()
        return []


# ---------------------------------------------------------------------
# Main Business Logic
# ---------------------------------------------------------------------
async def check_calendar_impl(
    user_id: str,
    time_start: str | None,
    time_end: str | None,
    max_results: int,
    session: AsyncSession,
    http_client: httpx.AsyncClient,
) -> dict[str, Any]:
    """
    Core business logic for checking Google Calendar for focus blocks.
    Keywords are NOT passed by the user. They come from:
    - default system keywords
    - user's custom keywords stored in DB
    """

    # -----------------------------------------------------------
    # Effective Keywords = Defaults + User Custom
    # -----------------------------------------------------------
    system_defaults = get_default_keywords()  # ["focus", "deep work"]
    user_custom = await load_user_custom_keywords(user_id, session)

    combined = system_defaults + (user_custom or [])

    effective_keywords = list(
        {k.strip(): None for k in combined if isinstance(k, str) and k.strip()}.keys()
    )

    if not effective_keywords:
        raise ValueError("No valid focus keywords available.")

    logger.info(
        f"[check_calendar] user={user_id}, effective_keywords={effective_keywords}"
    )

    # -----------------------------------------------------------
    # Validate max_results
    # -----------------------------------------------------------
    if not (1 <= max_results <= 50):
        raise ValueError(f"max_results must be between 1 and 50, got {max_results}")

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
        logger.warning(f"[check_calendar] No Google connection for user {user_id}")
        raise ValueError("USER_NOT_CONNECTED")

    # -----------------------------------------------------------
    # Check token expiration and refresh if needed
    # -----------------------------------------------------------
    now = datetime.now(timezone.utc)
    if not connection.token_expires_at or connection.token_expires_at <= now:
        logger.info("Access token expired, refreshing")

        # Decrypt refresh token
        try:
            refresh_token_decrypted = decrypt_token(connection.encrypted_refresh_token)
        except Exception as e:
            logger.error(f"Failed to decrypt refresh token: {e}")
            return {"error": "TOKEN_REFRESH_FAILED"}

        # Refresh process
        try:
            result = await refresh_access_token(http_client, refresh_token_decrypted)
        except ValueError as e:
            if str(e) == "Refresh token invalid":
                return {"error": "REFRESH_TOKEN_INVALID"}
            if str(e) == "API quota exceeded":
                return {"error": "API_QUOTA_EXCEEDED"}
            return {"error": "TOKEN_REFRESH_FAILED"}
        except Exception:
            return {"error": "TOKEN_REFRESH_FAILED"}

        # Extract values
        new_access_token = result["access_token"]
        expires_in = result["expires_in"]

        # Update DB
        connection.encrypted_access_token = encrypt_token(new_access_token)
        connection.token_expires_at = now + timedelta(seconds=expires_in)
        connection.updated_at = now
        await session.commit()

    # -----------------------------------------------------------
    # Decrypt token
    # -----------------------------------------------------------
    try:
        access_token = decrypt_token(connection.encrypted_access_token)
    except Exception as e:
        logger.error(f"Failed to decrypt access token: {e}")
        raise ValueError("Failed to decrypt access token")

    # -----------------------------------------------------------
    # Determine time window
    # -----------------------------------------------------------
    now = datetime.now(timezone.utc)

    if time_start is None:
        time_start_dt = now
        time_start = time_start_dt.isoformat().replace("+00:00", "Z")
    else:
        try:
            time_start_dt = datetime.fromisoformat(time_start.replace("Z", "+00:00"))
        except Exception:
            raise ValueError(f"Invalid time_start format: {time_start}")

    if time_end is None:
        time_end_dt = time_start_dt + timedelta(days=7)
        time_end = time_end_dt.isoformat().replace("+00:00", "Z")
    else:
        try:
            time_end_dt = datetime.fromisoformat(time_end.replace("Z", "+00:00"))
        except Exception:
            raise ValueError(f"Invalid time_end format: {time_end}")

    if time_end_dt <= time_start_dt:
        raise ValueError("time_end must be after time_start")

    logger.info(f"[check_calendar] scanning {time_start} → {time_end}")

    # -----------------------------------------------------------
    # Fetch Google Calendar events
    # -----------------------------------------------------------
    try:
        calendar_response = await fetch_events(
            http_client=http_client,
            access_token=access_token,
            time_min=time_start,
            time_max=time_end,
            max_results=max_results,
        )
    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Calendar fetch failed: {e}")
        raise ValueError("Failed to fetch calendar events")

    events = calendar_response.get("items", [])
    total_events_scanned = len(events)

    logger.info(f"[check_calendar] Google returned {total_events_scanned} events")

    # -----------------------------------------------------------
    # Match focus blocks
    # -----------------------------------------------------------
    focus_blocks = []

    for event in events:
        matched_keyword = matches_focus_keywords(event, effective_keywords)

        if matched_keyword:
            start_obj = event.get("start", {})
            end_obj = event.get("end", {})

            start_time = start_obj.get("dateTime", start_obj.get("date", ""))
            end_time = end_obj.get("dateTime", end_obj.get("date", ""))

            focus_blocks.append(
                {
                    "id": event.get("id", ""),
                    "summary": event.get("summary", ""),
                    "start": start_time,
                    "end": end_time,
                    "matched_keyword": matched_keyword,
                }
            )

    focus_blocks_found = len(focus_blocks)

    logger.info(
        f"[check_calendar] Focus blocks: {focus_blocks_found}/{total_events_scanned}"
    )

    # -----------------------------------------------------------
    # Return results
    # conflicts + free_slots empty for MVP
    # -----------------------------------------------------------
    return {
        "focus_blocks": focus_blocks,
        "conflicts": [],
        "free_slots": [],
        "total_events_scanned": total_events_scanned,
        "focus_blocks_found": focus_blocks_found,
    }


# ---------------------------------------------------------------------
# Webhook Registration Logic
# ---------------------------------------------------------------------
async def watch_calendar_logic(
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
    # Check token expiration and refresh if needed
    # -----------------------------------------------------------
    now = datetime.now(timezone.utc)
    if not connection.token_expires_at or connection.token_expires_at <= now:
        logger.info("Access token expired, refreshing before webhook registration")

        # Decrypt refresh token
        try:
            refresh_token_decrypted = decrypt_token(connection.encrypted_refresh_token)
        except Exception as e:
            logger.error(f"Failed to decrypt refresh token: {e}")
            return {"error": "TOKEN_REFRESH_FAILED"}

        # Refresh process
        try:
            refresh_result = await refresh_access_token(http_client, refresh_token_decrypted)
        except ValueError as e:
            if str(e) == "Refresh token invalid":
                return {"error": "REFRESH_TOKEN_INVALID"}
            if str(e) == "API quota exceeded":
                return {"error": "API_QUOTA_EXCEEDED"}
            return {"error": "TOKEN_REFRESH_FAILED"}
        except Exception:
            return {"error": "TOKEN_REFRESH_FAILED"}

        # Extract values
        new_access_token = refresh_result["access_token"]
        expires_in = refresh_result["expires_in"]

        # Update DB
        connection.encrypted_access_token = encrypt_token(new_access_token)
        connection.token_expires_at = now + timedelta(seconds=expires_in)
        connection.updated_at = now
        await session.commit()

    # -----------------------------------------------------------
    # Decrypt access token
    # -----------------------------------------------------------
    try:
        access_token = decrypt_token(connection.encrypted_access_token)
    except Exception as e:
        logger.error(f"Failed to decrypt access token: {e}")
        return {"error": "TOKEN_DECRYPTION_FAILED"}

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
