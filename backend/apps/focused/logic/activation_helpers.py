"""
Helper functions for focus activation task.

These functions encapsulate database queries and can be easily mocked
in unit tests to test the task's business logic in isolation.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.focused.db_models import (
    FocusedConsentPreferences,
    FocusedFocusSession,
    FocusedScheduledJob,
)

logger = logging.getLogger(__name__)


async def fetch_focus_session(
    db: AsyncSession,
    session_id: UUID,
    user_id: UUID,
) -> FocusedFocusSession | None:
    """
    Fetch a focus session by ID and user ID.

    Args:
        db: Database session
        session_id: Focus session UUID
        user_id: User UUID

    Returns:
        FocusedFocusSession or None if not found
    """
    stmt = select(FocusedFocusSession).where(
        FocusedFocusSession.id == session_id,
        FocusedFocusSession.user_id == user_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def fetch_user_active_session(
    db: AsyncSession,
    user_id: UUID,
) -> FocusedFocusSession | None:
    """
    Check if user has an active focus session.

    An active session has actual_start set but no actual_end.

    Args:
        db: Database session
        user_id: User UUID

    Returns:
        FocusedFocusSession if active session exists, None otherwise
    """
    stmt = select(FocusedFocusSession).where(
        FocusedFocusSession.user_id == user_id,
        FocusedFocusSession.actual_start.isnot(None),
        FocusedFocusSession.actual_end.is_(None),
    ).limit(1)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def fetch_consent_preferences(
    db: AsyncSession,
    user_id: UUID,
) -> FocusedConsentPreferences | None:
    """
    Fetch user's consent preferences.

    Args:
        db: Database session
        user_id: User UUID

    Returns:
        FocusedConsentPreferences or None if not found
    """
    stmt = select(FocusedConsentPreferences).where(
        FocusedConsentPreferences.user_id == user_id
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def update_job_status(
    db: AsyncSession,
    job_id: UUID,
    status: str,
    error_reason: str | None = None,
    shortcut_url: str | None = None,
) -> None:
    """
    Update a scheduled job's status and optional fields.

    Args:
        db: Database session
        job_id: Job UUID
        status: New status value
        error_reason: Optional error reason (for failed/cancelled/skipped)
        shortcut_url: Optional shortcut URL (for successful activation prep)
    """
    values = {
        "status": status,
        "updated_at": datetime.now(timezone.utc),
    }
    if error_reason is not None:
        values["error_reason"] = error_reason
    if shortcut_url is not None:
        values["shortcut_url"] = shortcut_url

    stmt = (
        update(FocusedScheduledJob)
        .where(FocusedScheduledJob.id == job_id)
        .values(**values)
    )
    await db.execute(stmt)
