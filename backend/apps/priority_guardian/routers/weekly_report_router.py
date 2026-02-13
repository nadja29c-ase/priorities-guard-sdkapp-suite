"""
Weekly Report Router - MCP-facing endpoint for weekly report generation.

Priority Guardian: Provides weekly report with live computation from Google Calendar.

NOTE: Persistence (snapshots, backfill, semantic groupings) is deferred to a future increment.

Endpoints:
    GET /weekly-report: Generate weekly report for current or specified week
"""

import structlog
from datetime import date
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.apps.priority_guardian.dependencies import validate_user_id_header
from backend.apps.priority_guardian.services.weekly_report_service import (
    generate_weekly_report,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Priority Guardian Weekly Report"])


@router.get("/weekly-report")
async def get_weekly_report(
    request: Request,
    user_id: UUID = Depends(validate_user_id_header),
    session: AsyncSession = Depends(get_db),
    week_start: str | None = Query(
        None,
        description="Monday of the target week (ISO date: YYYY-MM-DD). "
        "Must be a Monday. If omitted, returns current week.",
        example="2026-02-10",
    ),
):
    """
    Generate a weekly report for the user.

    Computes live data from Google Calendar for both current and past weeks.
    No persistence in this version - snapshots and aggregates are deferred.

    Response includes:
    - Per-priority hours, event counts, status indicators
    - Time allocation breakdown
    - Filtered event list for LLM semantic grouping (conversational only)

    Args:
        request: FastAPI request (for correlation ID)
        user_id: User ID from validated JWT (via X-User-ID header)
        session: Database session
        week_start: Optional Monday date for specific week

    Returns:
        200: Weekly report data
        400: Invalid week_start (not Monday or invalid date format)
        401: Missing/invalid X-User-ID
        502: Google Calendar API error
        503: Token refresh failed
    """
    correlation_id = getattr(request.state, "correlation_id", None)
    log = {"user_id": str(user_id), "correlation_id": correlation_id}

    # Parse week_start if provided
    parsed_week_start: date | None = None
    if week_start:
        try:
            parsed_week_start = date.fromisoformat(week_start)
        except ValueError:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "error": {
                        "code": "INVALID_DATE_FORMAT",
                        "message": f"week_start must be ISO date format (YYYY-MM-DD), got: {week_start}",
                    },
                },
            )

        # Validate it's a Monday
        if parsed_week_start.weekday() != 0:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "error": {
                        "code": "NOT_A_MONDAY",
                        "message": f"week_start must be a Monday, got {week_start} "
                        f"(weekday={parsed_week_start.weekday()})",
                    },
                },
            )

    logger.info(
        "weekly_report.request",
        week_start=week_start,
        **log
    )

    # Get HTTP client from app state
    http_client: httpx.AsyncClient = request.app.state.http_client

    try:
        result = await generate_weekly_report(
            user_id=user_id,
            session=session,
            http_client=http_client,
            week_start=parsed_week_start,
            correlation_id=correlation_id,
        )

        logger.info(
            "weekly_report.success",
            is_current_week=result["data"]["is_current_week"],
            priority_count=len(result["data"]["priorities"]),
            **log
        )

        return result

    except ValueError as e:
        error_str = str(e)

        # Handle specific error cases
        if "Google Calendar not connected" in error_str:
            logger.info("weekly_report.no_google_connection", **log)
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "error": {
                        "code": "GOOGLE_NOT_CONNECTED",
                        "message": "Google Calendar is not connected. Please connect first.",
                    },
                },
            )

        if "Token error" in error_str:
            logger.warning("weekly_report.token_error", error=error_str, **log)
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "success": False,
                    "error": {
                        "code": "TOKEN_ERROR",
                        "message": "Unable to access Google Calendar. Please reconnect.",
                    },
                },
            )

        if "must be a Monday" in error_str:
            # Shouldn't happen since we validate above, but defensive
            logger.warning("weekly_report.not_monday", error=error_str, **log)
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "error": {
                        "code": "NOT_A_MONDAY",
                        "message": error_str,
                    },
                },
            )

        # Generic ValueError
        logger.error("weekly_report.value_error", error=error_str, **log)
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={
                "success": False,
                "error": {
                    "code": "CALENDAR_ERROR",
                    "message": "Failed to fetch calendar data. Please try again.",
                },
            },
        )

    except Exception as e:
        logger.error(
            "weekly_report.unexpected_error",
            error=str(e),
            error_type=type(e).__name__,
            **log
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again.",
        )
