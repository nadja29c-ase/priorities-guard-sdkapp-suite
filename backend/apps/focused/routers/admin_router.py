"""
Admin Router — Internal admin endpoints for Focused app.

These endpoints are for development, testing, and admin operations.
In production, these should be protected with authentication/authorization.
"""

import logging
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.apps.focused.logic.sync.clean_eventdescr import cleanup_old_descriptions

logger = logging.getLogger(__name__)

router = APIRouter(tags=["focused-admin"])


@router.post("/admin/clean_eventdescr")
async def admin_clean_eventdescr(
    session: AsyncSession = Depends(get_db),
):
    """
    Manually trigger description cleanup (dev/testing endpoint).

    Deletes event_description fields older than 72 hours to comply
    with GDPR data minimization principles.

    NOTE: This endpoint is for development and testing only.
    In production, cleanup runs automatically via Celery every 6 hours.

    Protection will be added later.

    Returns:
        {
            "success": True,
            "data": {
                "descriptions_deleted": int,
                "message": str
            }
        }
    """
    try:
        deleted_count = await cleanup_old_descriptions(session)

        return {
            "success": True,
            "data": {
                "descriptions_deleted": deleted_count,
                "message": f"Cleaned up {deleted_count} event descriptions older than 72 hours"
            }
        }

    except Exception as e:
        logger.error(f"Admin cleanup failed: {e}")
        return {
            "success": False,
            "error": {
                "code": "CLEANUP_FAILED",
                "message": "Failed to cleanup descriptions"
            }
        }
