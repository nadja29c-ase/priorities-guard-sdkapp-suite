"""
Snapshot Router - Exposes snapshot persistence to MCP handler.

Priority Guardian Increment 08: Opportunistic snapshot creation.

Endpoints:
    POST /snapshots/ensure: Ensure weekly snapshots are up to date

Called by get_priorities MCP handler on every dashboard load.
Creates missing snapshots for completed weeks, updates aggregates.
"""

import structlog
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.apps.priority_guardian.dependencies import validate_user_id_header
from backend.apps.priority_guardian.services.snapshot_service import (
    ensure_snapshots_up_to_date,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Priority Guardian Snapshots"])


@router.post("/snapshots/ensure")
async def ensure_snapshots(
    user_id: UUID = Depends(validate_user_id_header),
    session: AsyncSession = Depends(get_db),
):
    """
    Ensure weekly snapshots are up to date.

    Called by get_priorities MCP handler on every dashboard load.
    Creates missing snapshots for up to 3 completed weeks.
    Updates running aggregates (streak_count, avg_hours_week, total_hours_invested).

    This endpoint:
    - Is idempotent (safe to call repeatedly)
    - Never fails with error status (returns 200 with partial results)
    - Runs in parallel with other dashboard data fetches

    Args:
        user_id: User ID from validated JWT (via X-User-ID header)
        session: Database session

    Returns:
        200: {
            "success": true,
            "data": {
                "checked": 3,    # Weeks checked
                "created": 1,    # Weeks with new snapshots
                "errors": 0      # Weeks that failed
            }
        }
    """
    # Create HTTP client for Google API calls
    async with httpx.AsyncClient(timeout=30.0) as http_client:
        result = await ensure_snapshots_up_to_date(
            user_id=user_id,
            session=session,
            http_client=http_client,
            correlation_id=None,  # Could extract from header if needed
        )

    logger.info(
        "snapshot.ensure.complete",
        user_id=str(user_id),
        checked=result["checked"],
        created=result["created"],
        errors=result["errors"],
    )

    return {
        "success": True,
        "data": result,
    }
