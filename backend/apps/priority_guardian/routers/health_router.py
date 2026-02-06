"""
Health Router — Service health check endpoint for Priority Guardian.
"""

import logging
from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)

router = APIRouter(tags=["priority-guardian-health"])


@router.get("/health")
async def health_check(request: Request):
    """
    Health check endpoint for Priority Guardian backend service.
    """
    try:
        return {
            "success": True,
            "data": {
                "status": "ok",
                "service": "priority-guardian-backend",
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
