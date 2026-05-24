"""
Widget Diagnostic Router — Receives diagnostic events from widget for Better Stack ingestion.

Temporary diagnostic endpoint for Inc 89 (fullscreen flash-revert bug investigation).
Remove after bug is diagnosed.
"""

import json
import hashlib
import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from typing import Any, Optional

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["priority-guardian-diagnostic"])


class WidgetDiagnosticReport(BaseModel):
    """Client-side widget diagnostic event."""
    event: str = Field(..., min_length=1, max_length=100)
    data: Optional[dict[str, Any]] = None
    ts: Optional[int] = None
    ua: Optional[str] = Field(None, max_length=500)


# CORS headers for widget-diagnostic endpoint (WKWebView sends from ui:// or null origin)
WIDGET_DIAGNOSTIC_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


@router.options("/widget-diagnostic")
async def widget_diagnostic_preflight():
    """
    CORS preflight handler for widget-diagnostic endpoint.

    WKWebView may send OPTIONS before POST from non-standard origin.
    """
    return Response(status_code=204, headers=WIDGET_DIAGNOSTIC_CORS_HEADERS)


@router.post("/widget-diagnostic")
async def widget_diagnostic_report(request: Request, body: WidgetDiagnosticReport):
    """
    Receives client-side widget diagnostic events for debugging.

    No authentication required — widget may send diagnostics before auth state is available.
    Rate limiting not applied — diagnostic volume is inherently self-limiting (20/session cap in widget).
    CORS open (*) — widget origin is non-standard (ui:// or null).
    """
    # Enforce data field size limit (2048 bytes)
    if body.data is not None:
        serialized = json.dumps(body.data, separators=(",", ":"))
        if len(serialized.encode("utf-8")) > 2048:
            raise HTTPException(
                status_code=413,
                detail="diagnostic data field exceeds 2048 bytes",
            )

    correlation_id = getattr(request.state, "correlation_id", "widget")

    # Hash client IP for privacy (useful for grouping events from same client)
    client_ip = request.client.host if request.client else "unknown"
    ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()[:12]

    logger.info(
        "widget.diagnostic",
        correlation_id=correlation_id,
        service="priority-guardian",
        diagnostic_event=body.event,
        data=body.data or {},
        client_ts=body.ts,
        user_agent=body.ua or "(none)",
        ip_hash=ip_hash,
    )

    return Response(status_code=204, headers=WIDGET_DIAGNOSTIC_CORS_HEADERS)
