"""
Focused Backend Router — HTTP endpoints for all Focused app backend operations.
Includes health, calendar checks, focus activation, patterns, and future endpoints.
"""

import logging
from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)

# NO prefix here - it's added in main.py
router = APIRouter(tags=["focused"])


@router.get("/health")
async def health_check(request: Request):
    """
    Health check endpoint for the focused backend.

    Returns:
        JSON response with service status and version
    """
    try:
        # Get request_id from middleware
        request_id = request.state.request_id

        # Log request received
        logger.info(
            "Health check request received",
            extra={"request_id": request_id}
        )

        # Prepare response
        response_data = {
            "success": True,
            "data": {
                "status": "ok",
                "service": "focused-backend",
                "version": "0.1.0"
            }
        }

        # Log request completed
        logger.info(
            "Health check request completed",
            extra={"request_id": request_id}
        )

        return response_data

    except Exception as e:
        # Log error
        logger.error(
            f"Health check failed: {str(e)}",
            extra={"request_id": getattr(request.state, "request_id", "unknown")}
        )

        # Return error format
        return {
            "success": False,
            "error": {
                "code": "HEALTH_CHECK_FAILED",
                "message": "Health check endpoint encountered an error"
            }
        }
