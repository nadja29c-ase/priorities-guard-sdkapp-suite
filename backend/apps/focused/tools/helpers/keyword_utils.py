"""
Keyword matching utilities for Focused app.

Functions for normalizing text and matching focus keywords.
"""

import re
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.focused.db_models import FocusedUserKeyword
from backend.apps.focused.focused_config import get_default_keywords

logger = logging.getLogger(__name__)


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


def matches_focus_keywords(summary: str, keywords: list[str]) -> str | None:
    """
    Match keywords ONLY against the event title (summary).

    Args:
        summary: Event summary/title string
        keywords: List of keywords to match against

    Returns:
        Matched keyword if found, None otherwise
    """
    summary_norm = normalize(summary or "")

    for keyword in keywords:
        keyword_norm = normalize(keyword)
        if keyword_norm in summary_norm:
            return keyword

    return None


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


async def get_effective_keywords(user_id: str, session: AsyncSession) -> list[str]:
    """
    Get effective keywords for a user (system defaults + user custom).

    Args:
        user_id: User ID
        session: Database session

    Returns:
        List of effective keywords (deduplicated)

    Raises:
        ValueError: If no valid keywords available
    """
    system_defaults = get_default_keywords()
    user_custom = await load_user_custom_keywords(user_id, session)

    combined = system_defaults + (user_custom or [])

    effective_keywords = list(
        {k.strip(): None for k in combined if isinstance(k, str) and k.strip()}.keys()
    )

    if not effective_keywords:
        raise ValueError("No valid focus keywords available.")

    return effective_keywords
