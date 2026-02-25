"""
Calendar Router - Time allocation endpoint for Priority Guardian.

Priority Guardian Increment 05: Provides time allocation data from Google Calendar.

Endpoint:
    GET /calendar/time-allocation: Compute hours per keyword for current week

Trust Boundary: Same as priorities_router - X-User-ID header trusted from MCP server.
"""

import structlog
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.apps.priority_guardian.dependencies import validate_user_id_header, verify_internal_call
from backend.apps.priority_guardian.services.calendar_service import compute_time_allocation

logger = structlog.get_logger(__name__)

router = APIRouter(
    tags=["Priority Guardian Calendar"],
    dependencies=[Depends(verify_internal_call)],
)


@router.get("/calendar/time-allocation")
async def get_time_allocation(
    request: Request,
    user_id: UUID = Depends(validate_user_id_header),
    session: AsyncSession = Depends(get_db),
):
    """
    Get time allocation from Google Calendar for current week.

    Fetches calendar events, matches P1/P2/P3 keywords, and computes
    hours per keyword. Used by MCP get_priorities to enrich priority data.

    Returns:
        200: Time allocation data (always succeeds, zeros if no connection)
        401: Missing/invalid X-User-ID
        502: Google Calendar API failed after retries
        503: Token refresh failed (user may need to reconnect)

    Response shape:
        {
            "success": true,
            "data": {
                "week_start": "2026-02-09T00:00:00+01:00",
                "week_end": "2026-02-16T00:00:00+01:00",
                "timezone": "Europe/Berlin",
                "keywords": {
                    "P1": {"hours": 10.5, "event_count": 6},
                    "P2": {"hours": 3.0, "event_count": 2},
                    "P3": {"hours": 0.0, "event_count": 0}
                },
                "other_hours": 18.25,
                "total_tracked_hours": 31.75,
                "total_events_scanned": 42,
                "bar_segments": {"P1": 10.5, "P2": 3.0, "P3": 0.0, "other": 18.25}
            }
        }
    """
    # Extract correlation_id from request state (set by middleware)
    correlation_id = getattr(request.state, "correlation_id", None)

    # Get http_client from app state
    http_client = request.app.state.http_client

    try:
        allocation = await compute_time_allocation(
            user_id=user_id,
            session=session,
            http_client=http_client,
            correlation_id=correlation_id,
        )

        logger.info(
            "calendar.time_allocation.success",
            user_id=str(user_id),
            correlation_id=correlation_id,
            total_hours=allocation.get("total_tracked_hours", 0),
        )

        return {
            "success": True,
            "data": allocation,
        }

    except ValueError as e:
        # Token-related errors → 503 (temporary, user may need to reconnect)
        error_msg = str(e)
        logger.warning(
            "calendar.time_allocation.token_error",
            user_id=str(user_id),
            correlation_id=correlation_id,
            error=error_msg,
        )

        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "success": False,
                "error": {
                    "code": "TOKEN_ERROR",
                    "message": "Calendar data temporarily unavailable. Please try again or reconnect Google Calendar.",
                },
            },
        )

    except Exception as e:
        # Google API or other errors → 502 (upstream error)
        logger.error(
            "calendar.time_allocation.upstream_error",
            user_id=str(user_id),
            correlation_id=correlation_id,
            error=str(e),
            error_type=type(e).__name__,
        )

        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={
                "success": False,
                "error": {
                    "code": "UPSTREAM_ERROR",
                    "message": "Calendar data temporarily unavailable.",
                },
            },
        )
