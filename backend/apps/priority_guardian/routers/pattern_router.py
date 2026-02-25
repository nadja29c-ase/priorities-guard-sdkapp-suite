"""
Pattern Recognition router for Priority Guardian.

Exposes GET /patterns endpoint for computing behavioral patterns
from user's snapshot history. Called by MCP get_patterns tool.

Implements increment_21 specification.
"""

import structlog
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.apps.priority_guardian.dependencies import validate_user_id_header, verify_internal_call
from backend.apps.priority_guardian.services.pattern_service import compute_patterns

logger = structlog.get_logger(__name__)

router = APIRouter(
    tags=["Priority Guardian Patterns"],
    dependencies=[Depends(verify_internal_call)],
)


@router.get("/patterns")
async def get_patterns(
    request: Request,
    user_id: UUID = Depends(validate_user_id_header),
    session: AsyncSession = Depends(get_db),
):
    """
    Get behavioral patterns from user's tracking history.

    Returns patterns computed at read time from existing snapshot and priority data.
    No data is stored - patterns are computed fresh each call.

    Called by MCP get_patterns tool during weekly reflection or when user
    asks about trends/patterns.

    Args:
        request: FastAPI request (for correlation_id)
        user_id: Validated user ID from X-User-ID header
        session: SQLAlchemy async session

    Returns:
        JSON response with pattern data or error
    """
    correlation_id = getattr(request.state, "correlation_id", None)

    log = {"user_id": str(user_id), "correlation_id": correlation_id}

    # Call service
    result = await compute_patterns(
        user_id=user_id,
        session=session,
        correlation_id=correlation_id,
    )

    # Check for error response from service
    if not result.get("success"):
        error = result.get("error", {})
        logger.error(
            "patterns.endpoint.error",
            error_code=error.get("code"),
            **log,
        )
        return JSONResponse(
            status_code=500,
            content=result,
        )

    # Success response
    data = result.get("data", {})
    logger.info(
        "patterns.endpoint.complete",
        pattern_count=data.get("pattern_count", 0),
        weeks_available=data.get("weeks_available", 0),
        reason=data.get("reason"),
        **log,
    )

    return result
