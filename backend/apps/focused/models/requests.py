"""
Pydantic request models for Focused app API endpoints.
"""

from pydantic import BaseModel, Field


class CheckCalendarRequest(BaseModel):
    """Request model for check_calendar endpoint."""

    time_start: str | None = Field(
        None, description="ISO8601 start time. None = now."
    )
    time_end: str | None = Field(
        None, description="ISO8601 end time. None = start + 7 days."
    )
    max_results: int = Field(
        20, ge=1, le=50, description="Max events to scan (1-50)"
    )


class WatchCalendarRequest(BaseModel):
    """Request model for watch_calendar endpoint."""

    user_id: str = Field(..., description="User ID for webhook registration")


class SyncCalendarRequest(BaseModel):
    """Request model for sync_calendar endpoint (Increment 6B)."""

    user_id: str = Field(..., description="User ID to sync calendar for")


class RunFocusModeRequest(BaseModel):
    """
    Request model for run_focus_mode endpoint (Increment 11).

    Activates or deactivates Apple Focus Mode via iOS Shortcuts URL scheme.
    """

    action: str = Field(
        ...,
        description="'on' to activate Focus Mode, 'off' to deactivate",
        pattern="^(on|off)$",
    )
    trigger_source: str = Field(
        ...,
        description="'calendar' (from detected event) or 'user' (manual)",
        pattern="^(calendar|user)$",
    )
    session_id: str | None = Field(
        None,
        description="Focus session UUID (required for calendar-triggered activation)",
    )
    session_title: str | None = Field(
        None,
        description="Session title (e.g., 'Work', 'Do Not Disturb'). Default: 'Work'",
        max_length=100,
    )
    duration_minutes: int | None = Field(
        None,
        ge=1,
        le=480,  # Max 8 hours
        description="Auto-deactivate after this many minutes (1-480)",
    )
    user_confirmation: bool | None = Field(
        None,
        description="User confirmed activation. Required when action='on'",
    )
