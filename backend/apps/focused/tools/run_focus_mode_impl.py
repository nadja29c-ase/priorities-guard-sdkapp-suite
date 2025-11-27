"""
Run Focus Mode Tool Implementation (Increment 11).

Activates/deactivates Apple Focus Mode via iOS Shortcuts URL scheme.

Key behaviors:
- One active session per user (must deactivate before re-activating)
- Calendar-triggered: Uses existing session_id from sync engine
- Manual-triggered: Creates new session row with google_event_id=NULL
- Deactivation is idempotent (already-closed sessions return success)
- Optional auto-deactivation via duration_minutes parameter

The backend generates shortcut_url but does NOT invoke it.
ChatGPT client opens the URL on user's device.
"""

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import quote
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.focused.db_models import FocusedFocusSession, FocusedScheduledJob
from backend.core.celery_app import celery_app

logger = structlog.get_logger(__name__)

# Shortcut URL templates
ACTIVATE_SHORTCUT_URL = "shortcuts://run-shortcut?name=Activate%20Focus%20Mode&input=text&text={focus_name}"
DEACTIVATE_SHORTCUT_URL = "shortcuts://run-shortcut?name=Deactivate%20Focus%20Mode"

# Default focus mode name
DEFAULT_FOCUS_NAME = "Work"


async def run_focus_mode_impl(
    user_id: str,
    action: Literal["on", "off"],
    session: AsyncSession,
    trigger_source: Literal["calendar", "user"],
    session_id: str | None = None,
    focus_name: str | None = None,
    duration_minutes: int | None = None,
    user_confirmation: bool | None = None,
) -> dict:
    """
    Activate or deactivate Apple Focus Mode.

    Args:
        user_id: User identifier (from X-User-ID header)
        action: "on" to activate, "off" to deactivate
        session: Database session
        trigger_source: "calendar" (from detected event) or "user" (manual)
        session_id: Session UUID (required for calendar-triggered, ignored for user-triggered)
        focus_name: Focus mode name (default "Work")
        duration_minutes: Auto-deactivate after this many minutes (optional)
        user_confirmation: User confirmed activation (required for action="on")

    Returns:
        Dictionary with:
        - shortcut_status: "success" | "failed" | "not_installed" | "already_active" | "already_inactive"
        - shortcut_url: URL for ChatGPT client to open on device
        - focus_name: The focus mode name used
        - start_time: ISO 8601 timestamp
        - end_time: ISO 8601 timestamp | None
        - message: Human-readable status message
        - error_details: Error details if failed | None
    """
    log = logger.bind(user_id=user_id, action=action, trigger_source=trigger_source)
    log.info("run_focus_mode_called")

    try:
        user_uuid = UUID(user_id)
    except ValueError:
        log.warning("invalid_user_id_format")
        return _error_response("Invalid user ID format")

    # Validate action
    if action not in ("on", "off"):
        log.warning("invalid_action", action=action)
        return _error_response(f"Invalid action: '{action}'. Must be 'on' or 'off'.")

    # Validate trigger_source
    if trigger_source not in ("calendar", "user"):
        log.warning("invalid_trigger_source", trigger_source=trigger_source)
        return _error_response(f"Invalid trigger_source: '{trigger_source}'. Must be 'calendar' or 'user'.")

    # Normalize focus_name
    focus_name = focus_name or DEFAULT_FOCUS_NAME

    if action == "on":
        return await _activate_focus_mode(
            user_uuid=user_uuid,
            session=session,
            trigger_source=trigger_source,
            session_id=session_id,
            focus_name=focus_name,
            duration_minutes=duration_minutes,
            user_confirmation=user_confirmation,
            log=log,
        )
    else:
        return await _deactivate_focus_mode(
            user_uuid=user_uuid,
            session=session,
            trigger_source=trigger_source,
            session_id=session_id,
            log=log,
        )


async def _activate_focus_mode(
    user_uuid: UUID,
    session: AsyncSession,
    trigger_source: Literal["calendar", "user"],
    session_id: str | None,
    focus_name: str,
    duration_minutes: int | None,
    user_confirmation: bool | None,
    log,
) -> dict:
    """Handle focus mode activation."""
    now = datetime.now(timezone.utc)

    # Validate duration_minutes if provided (must be 1-480)
    if duration_minutes is not None:
        if duration_minutes < 1:
            log.warning("invalid_duration_too_low", duration_minutes=duration_minutes)
            return _error_response("duration_minutes must be >= 1")
        if duration_minutes > 480:
            log.warning("invalid_duration_too_high", duration_minutes=duration_minutes)
            return _error_response("duration_minutes must be <= 480")

    # Require user confirmation for activation
    if not user_confirmation:
        log.info("activation_declined_no_confirmation")
        return {
            "shortcut_status": "failed",
            "shortcut_url": None,
            "focus_name": focus_name,
            "start_time": now.isoformat(),
            "end_time": None,
            "message": "User confirmation required to activate Focus Mode.",
            "error_details": "user_confirmation must be true",
        }

    # Check for existing active session (one active session per user rule)
    existing_active = await _get_active_session(user_uuid, session)
    if existing_active:
        log.info("activation_blocked_already_active", existing_session_id=str(existing_active.id))
        return {
            "shortcut_status": "already_active",
            "shortcut_url": None,
            "focus_name": focus_name,
            "start_time": existing_active.actual_start.isoformat() if existing_active.actual_start else now.isoformat(),
            "end_time": None,
            "message": "Focus Mode is already active. Please deactivate first.",
            "error_details": None,
        }

    # Get or create the focus session
    if trigger_source == "calendar":
        # Calendar-triggered: session_id references existing row
        if not session_id:
            log.warning("calendar_trigger_missing_session_id")
            return _error_response("session_id is required for calendar-triggered activation")

        focus_session = await _get_session_by_id(user_uuid, session_id, session)
        if not focus_session:
            log.warning("session_not_found", session_id=session_id)
            return _not_found_response()

        # Calendar activation requires is_focus_block=True
        if not focus_session.is_focus_block:
            log.warning("calendar_session_not_focus_block", session_id=session_id)
            return _error_response("Session is not a focus block")

        # Update existing session
        focus_session.actual_start = now
        focus_session.trigger_source = "calendar"

    else:
        # Manual trigger: create new session row
        focus_session = await _create_manual_session(user_uuid, focus_name, now, session)

    # Calculate end time if duration provided
    end_time = None
    if duration_minutes:
        end_time = now + timedelta(minutes=duration_minutes)

        # Schedule auto-deactivation task
        await _schedule_auto_deactivate(
            user_uuid=user_uuid,
            session_id=focus_session.id,
            scheduled_at=end_time,
            session=session,
        )

    # Commit changes
    await session.commit()

    log.info(
        "focus_mode_activated",
        session_id=str(focus_session.id),
        duration_minutes=duration_minutes,
    )

    # Generate shortcut URL
    shortcut_url = ACTIVATE_SHORTCUT_URL.format(focus_name=quote(focus_name))

    return {
        "shortcut_status": "success",
        "shortcut_url": shortcut_url,
        "focus_name": focus_name,
        "start_time": now.isoformat(),
        "end_time": end_time.isoformat() if end_time else None,
        "message": f"Focus Mode '{focus_name}' activated successfully.",
        "error_details": None,
    }


async def _deactivate_focus_mode(
    user_uuid: UUID,
    session: AsyncSession,
    trigger_source: Literal["calendar", "user"],
    session_id: str | None,
    log,
) -> dict:
    """Handle focus mode deactivation."""
    now = datetime.now(timezone.utc)

    # Find the session to deactivate
    if trigger_source == "calendar":
        # Calendar-triggered: session_id is required
        if not session_id:
            log.warning("calendar_deactivation_missing_session_id")
            return _error_response("session_id is required for calendar-triggered deactivation")

        focus_session = await _get_session_by_id(user_uuid, session_id, session)
        if not focus_session:
            log.warning("session_not_found_for_deactivation", session_id=session_id)
            return _not_found_response()
    else:
        # Find active session for user
        focus_session = await _get_active_session(user_uuid, session)
        if not focus_session:
            log.info("no_active_session_for_deactivation")
            return {
                "shortcut_status": "already_inactive",
                "shortcut_url": DEACTIVATE_SHORTCUT_URL,
                "focus_name": DEFAULT_FOCUS_NAME,
                "start_time": now.isoformat(),
                "end_time": now.isoformat(),
                "message": "No active Focus Mode session to deactivate.",
                "error_details": None,
            }

    # Check if already deactivated (idempotent)
    if focus_session.actual_end is not None:
        log.info("session_already_inactive", session_id=str(focus_session.id))
        return {
            "shortcut_status": "already_inactive",
            "shortcut_url": DEACTIVATE_SHORTCUT_URL,
            "focus_name": focus_session.event_summary or DEFAULT_FOCUS_NAME,
            "start_time": focus_session.actual_start.isoformat() if focus_session.actual_start else now.isoformat(),
            "end_time": focus_session.actual_end.isoformat(),
            "message": "Focus Mode session was already deactivated.",
            "error_details": None,
        }

    # Deactivate the session
    focus_session.actual_end = now

    # Cancel any pending scheduled deactivation job for this session
    await _cancel_scheduled_job(focus_session.id, session, log)

    await session.commit()

    log.info("focus_mode_deactivated", session_id=str(focus_session.id))

    return {
        "shortcut_status": "success",
        "shortcut_url": DEACTIVATE_SHORTCUT_URL,
        "focus_name": focus_session.event_summary or DEFAULT_FOCUS_NAME,
        "start_time": focus_session.actual_start.isoformat() if focus_session.actual_start else now.isoformat(),
        "end_time": now.isoformat(),
        "message": "Focus Mode deactivated successfully.",
        "error_details": None,
    }


async def _get_active_session(user_uuid: UUID, session: AsyncSession) -> FocusedFocusSession | None:
    """Get the currently active focus session for a user."""
    stmt = (
        select(FocusedFocusSession)
        .where(
            FocusedFocusSession.user_id == user_uuid,
            FocusedFocusSession.actual_start.isnot(None),
            FocusedFocusSession.actual_end.is_(None),
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _get_session_by_id(
    user_uuid: UUID,
    session_id: str,
    session: AsyncSession,
) -> FocusedFocusSession | None:
    """
    Get a focus session by ID, verifying ownership.

    Returns None if:
    - Session doesn't exist
    - Session belongs to different user (do not leak existence)
    """
    try:
        session_uuid = UUID(session_id)
    except ValueError:
        return None

    stmt = select(FocusedFocusSession).where(
        FocusedFocusSession.id == session_uuid,
        FocusedFocusSession.user_id == user_uuid,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _create_manual_session(
    user_uuid: UUID,
    focus_name: str,
    now: datetime,
    session: AsyncSession,
) -> FocusedFocusSession:
    """Create a new manual focus session."""
    # Manual sessions have a default duration of 2 hours if not specified
    end_time = now + timedelta(hours=2)

    # Generate a hash for the manual session
    content = f"manual:{user_uuid}:{now.isoformat()}"
    content_hash = hashlib.sha256(content.encode()).hexdigest()

    focus_session = FocusedFocusSession(
        user_id=user_uuid,
        google_event_id=None,  # Manual session
        google_calendar_id="primary",
        google_ical_uid=None,  # Manual session
        google_updated_at=None,  # Manual session
        event_summary=focus_name,
        start_time=now,
        end_time=end_time,
        is_focus_block=True,
        sha256_content_hash=content_hash,
        trigger_source="user",
        actual_start=now,
    )

    session.add(focus_session)
    await session.flush()  # Get the generated ID

    return focus_session


async def _schedule_auto_deactivate(
    user_uuid: UUID,
    session_id: UUID,
    scheduled_at: datetime,
    session: AsyncSession,
) -> FocusedScheduledJob:
    """
    Schedule an auto-deactivation Celery task.

    Creates a job record in focused_scheduled_jobs and schedules
    the Celery task to execute at the specified time.
    """
    # Create job record
    job = FocusedScheduledJob(
        user_id=user_uuid,
        job_type="focus_deactivate",
        scheduled_at=scheduled_at,
        payload={"session_id": str(session_id)},
    )
    session.add(job)
    await session.flush()  # Get the generated ID

    # Schedule Celery task
    # Calculate delay in seconds
    delay_seconds = (scheduled_at - datetime.now(timezone.utc)).total_seconds()
    if delay_seconds < 0:
        delay_seconds = 0

    # Schedule Celery task using module-level celery_app import
    task = celery_app.send_task(
        "backend.core.celery_app.auto_deactivate_focus",
        args=[str(user_uuid), str(session_id), str(job.id)],
        countdown=delay_seconds,
    )

    # Store Celery task ID
    job.celery_task_id = task.id

    return job


async def _cancel_scheduled_job(
    session_id: UUID,
    db_session: AsyncSession,
    log,
) -> None:
    """
    Cancel any pending scheduled deactivation job for the given session.

    - Finds pending job with session_id in payload
    - Revokes the Celery task
    - Marks job status as 'cancelled'
    """
    # Find pending job for this session
    stmt = select(FocusedScheduledJob).where(
        FocusedScheduledJob.payload["session_id"].astext == str(session_id),
        FocusedScheduledJob.status == "pending",
        FocusedScheduledJob.job_type == "focus_deactivate",
    )
    result = await db_session.execute(stmt)
    job = result.scalar_one_or_none()

    # Verify it's actually a FocusedScheduledJob (not a FocusedFocusSession mistakenly returned)
    # Check that celery_task_id is a string (FocusedFocusSession doesn't have this attribute)
    if job and isinstance(getattr(job, "celery_task_id", None), str) and job.celery_task_id:
        log.info("cancelling_scheduled_job", job_id=str(job.id), celery_task_id=job.celery_task_id)

        # Revoke the Celery task
        celery_app.control.revoke(job.celery_task_id, terminate=True)

        # Mark job as cancelled
        job.status = "cancelled"


def _error_response(message: str) -> dict:
    """Generate a standard error response."""
    return {
        "shortcut_status": "failed",
        "shortcut_url": None,
        "focus_name": DEFAULT_FOCUS_NAME,
        "start_time": datetime.now(timezone.utc).isoformat(),
        "end_time": None,
        "message": message,
        "error_details": message,
    }


def _not_found_response() -> dict:
    """Generate a 404-style response for session not found."""
    return {
        "shortcut_status": "failed",
        "shortcut_url": None,
        "focus_name": DEFAULT_FOCUS_NAME,
        "start_time": datetime.now(timezone.utc).isoformat(),
        "end_time": None,
        "message": "Session not found.",
        "error_details": "session_not_found",
    }
