"""
Check calendar tool implementation.

Fetches Google Calendar events and identifies focus blocks using:
- system default keywords
- user-defined custom keywords stored in DB

Keywords are NOT provided by the user in the tool call. The backend
determines the effective keyword list internally.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.google_calendar import fetch_events
from backend.core.models import CoreConnection
from backend.apps.focused.logic_googletokens import ensure_valid_access_token
from backend.apps.focused.tools.helpers.keyword_utils import (
    get_effective_keywords,
    matches_focus_keywords,
)

logger = logging.getLogger(__name__)


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
    effective_keywords = await get_effective_keywords(user_id, session)

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
    # Ensure valid access token (auto-refresh if needed)
    # -----------------------------------------------------------
    token_result = await ensure_valid_access_token(connection, session, http_client)

    if "error" in token_result:
        raise ValueError(token_result["error"])

    access_token = token_result["access_token"]

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
        matched_keyword = matches_focus_keywords(event.get("summary", ""), effective_keywords)

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
