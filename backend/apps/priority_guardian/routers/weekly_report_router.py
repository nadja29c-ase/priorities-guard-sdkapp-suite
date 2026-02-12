"""
Weekly Report Router - MCP-facing endpoint for weekly report generation.

Priority Guardian Increment 06: Provides weekly report with snapshot persistence
and aggregate tracking.

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
from pydantic import BaseModel, Field
from backend.apps.priority_guardian.services.weekly_report_service import (
    generate_weekly_report,
    save_semantic_grouping,
    SemanticGroupingError,
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

    For the current (incomplete) week: returns live calendar data, no persistence.
    For completed past weeks: persists snapshots and updates priority aggregates.

    The endpoint handles backfill automatically: if snapshots are missing for
    weeks between the last saved week and the requested week, it fetches calendar
    data for each missing week and creates snapshots (up to 12 weeks max).

    Response includes:
    - Per-priority hours, event counts, status indicators
    - Week-over-week comparison (if previous week snapshot exists)
    - Aggregate stats (streak_count, avg_hours_week, total_hours_invested)
    - Time allocation breakdown and filtered event list for LLM processing

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
            snapshot_saved=result["data"]["snapshot_saved"],
            weeks_backfilled=result["data"]["weeks_backfilled"],
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


# ============================================================================
# Semantic Grouping Endpoint (Increment 07)
# ============================================================================


class SemanticCategory(BaseModel):
    """A single semantic category for non-priority time."""

    category: str = Field(..., min_length=1, max_length=100, description="Category name")
    hours: float = Field(..., ge=0, description="Hours in this category")
    event_count: int = Field(..., ge=0, description="Number of events in this category")


class SemanticGroupingRequest(BaseModel):
    """Request body for saving semantic groupings."""

    week_start: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Monday of the week (ISO date: YYYY-MM-DD)",
    )
    groupings: list[SemanticCategory] = Field(
        ...,
        min_length=1,
        description="Semantic categories for non-priority time",
    )


@router.post("/weekly-report/semantic-grouping")
async def post_semantic_grouping(
    request: Request,
    body: SemanticGroupingRequest,
    user_id: UUID = Depends(validate_user_id_header),
    session: AsyncSession = Depends(get_db),
):
    """
    Save semantic groupings for a weekly report.

    Attaches user-confirmed categories for non-priority time to the
    weekly snapshot. Returns pie chart data with priority + semantic slices.

    Args:
        request: FastAPI request (for correlation ID and HTTP client)
        body: Semantic grouping request
        user_id: User ID from validated JWT
        session: Database session

    Returns:
        200: Pie chart slices data
        400: Invalid request (not a Monday, empty groupings, validation errors)
        404: No snapshot for this week
        503: Google Calendar access error
    """
    correlation_id = getattr(request.state, "correlation_id", None)
    log = {"user_id": str(user_id), "correlation_id": correlation_id}

    # Parse week_start
    try:
        parsed_week_start = date.fromisoformat(body.week_start)
    except ValueError:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "error": {
                    "code": "INVALID_DATE_FORMAT",
                    "message": f"week_start must be ISO date format (YYYY-MM-DD), got: {body.week_start}",
                },
            },
        )

    logger.info(
        "semantic_grouping.request",
        week_start=body.week_start,
        category_count=len(body.groupings),
        **log
    )

    # Get HTTP client from app state
    http_client: httpx.AsyncClient = request.app.state.http_client

    # Convert Pydantic models to dicts
    groupings = [g.model_dump() for g in body.groupings]

    try:
        result = await save_semantic_grouping(
            user_id=user_id,
            session=session,
            http_client=http_client,
            week_start=parsed_week_start,
            groupings=groupings,
            correlation_id=correlation_id,
        )

        logger.info(
            "semantic_grouping.success",
            slice_count=len(result["data"]["slices"]),
            total_hours=result["data"]["total_hours"],
            **log
        )

        return result

    except SemanticGroupingError as e:
        logger.warning(
            "semantic_grouping.error",
            error_code=e.code,
            error_message=e.message,
            **log
        )

        # Map error codes to HTTP status codes
        status_map = {
            "NOT_A_MONDAY": status.HTTP_400_BAD_REQUEST,
            "EMPTY_GROUPINGS": status.HTTP_400_BAD_REQUEST,
            "INVALID_CATEGORY": status.HTTP_400_BAD_REQUEST,
            "DUPLICATE_CATEGORY": status.HTTP_400_BAD_REQUEST,
            "INVALID_HOURS": status.HTTP_400_BAD_REQUEST,
            "INVALID_EVENT_COUNT": status.HTTP_400_BAD_REQUEST,
            "NO_SNAPSHOT": status.HTTP_404_NOT_FOUND,
            "GOOGLE_NOT_CONNECTED": status.HTTP_400_BAD_REQUEST,
            "TOKEN_ERROR": status.HTTP_503_SERVICE_UNAVAILABLE,
            "NO_OTHER_HOURS": status.HTTP_400_BAD_REQUEST,
            "EXCEEDS_OTHER_HOURS": status.HTTP_400_BAD_REQUEST,
        }

        http_status = status_map.get(e.code, status.HTTP_400_BAD_REQUEST)

        return JSONResponse(
            status_code=http_status,
            content={
                "success": False,
                "error": {
                    "code": e.code,
                    "message": e.message,
                },
            },
        )

    except Exception as e:
        logger.error(
            "semantic_grouping.unexpected_error",
            error=str(e),
            error_type=type(e).__name__,
            **log
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again.",
        )
