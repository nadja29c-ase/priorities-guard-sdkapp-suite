"""
Focused Backend Router — HTTP endpoints for the Focused app.
MCP server calls these endpoints directly.

User keywords are NOT passed via API. The backend loads:
- system default keywords (config.py)
- user custom keywords (DB table)
"""

import logging
from fastapi import APIRouter, Request, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.apps.focused.logic import check_calendar_impl

logger = logging.getLogger(__name__)

router = APIRouter(tags=["focused"])


# ---------------------------------------------------------------------
# Request Model (no keywords, no user_id)
# ---------------------------------------------------------------------
class CheckCalendarRequest(BaseModel):
    time_start: str | None = Field(
        None, description="ISO8601 start time. None = now."
    )
    time_end: str | None = Field(
        None, description="ISO8601 end time. None = start + 7 days."
    )
    max_results: int = Field(
        20, ge=1, le=50, description="Max events to scan (1-50)"
    )


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
