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
