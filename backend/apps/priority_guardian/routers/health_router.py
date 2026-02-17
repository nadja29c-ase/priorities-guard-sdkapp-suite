"""
Health Router — Service health check endpoint for Priority Guardian.

Verifies database connectivity so Render can detect unhealthy instances.
"""

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["priority-guardian-health"])


@router.get("/health")
async def health_check(session: AsyncSession = Depends(get_db)):
    """
    Health check endpoint for Priority Guardian backend service.

    Verifies database connectivity by executing a simple query.
    Returns 503 if DB is unreachable so Render can restart the instance.
    """
    try:
        # Verify DB connectivity
        await session.execute(text("SELECT 1"))

        return {
            "success": True,
            "data": {
                "status": "ok",
                "service": "priority-guardian-backend",
                "version": "0.1.0",
                "database": "connected",
            },
        }
    except Exception as e:
        logger.error(
            "health_check.db_error",
            error_type=type(e).__name__,
            error_message=str(e),
        )
        # Return 503 so load balancer/Render knows instance is unhealthy
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": {
                    "code": "HEALTH_CHECK_FAILED",
                    "message": "Database connection failed",
                },
            },
        )
