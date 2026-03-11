"""
Health Router — Service health check endpoint for Priority Guardian.

Verifies database connectivity so Render can detect unhealthy instances.
"""

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from backend.core.database import get_db

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["priority-guardian-health"])


class WidgetErrorReport(BaseModel):
    """Client-side widget error report from iOS WKWebView."""
    name: Optional[str] = None
    message: Optional[str] = None
    stack: Optional[str] = None
    componentStack: Optional[str] = None
    ua: Optional[str] = None


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


# CORS headers for widget-error endpoint (WKWebView sends from ui:// or null origin)
WIDGET_ERROR_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


@router.options("/widget-error")
async def widget_error_preflight():
    """
    CORS preflight handler for widget-error endpoint.

    WKWebView may send OPTIONS before POST from non-standard origin.
    """
    return Response(status_code=204, headers=WIDGET_ERROR_CORS_HEADERS)


@router.post("/widget-error")
async def widget_error_report(request: Request, body: WidgetErrorReport):
    """
    Receives client-side widget crash reports from inside WKWebView/ChatGPT sandbox.

    No authentication required — widget may crash before auth state is available.
    Rate limiting not applied — crash volume is inherently self-limiting.
    CORS open (*) — widget origin is non-standard (ui:// or null).
    """
    correlation_id = getattr(request.state, "correlation_id", "widget")

    logger.error(
        "widget.client_error",
        correlation_id=correlation_id,
        error_name=body.name or "(none)",
        error_message=body.message or "(none)",
        stack=body.stack or "(none)",
        component_stack=body.componentStack or "(none)",
        user_agent=body.ua or "(none)",
    )

    return JSONResponse(
        content={"success": True},
        headers=WIDGET_ERROR_CORS_HEADERS,
    )
