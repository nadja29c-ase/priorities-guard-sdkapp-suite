"""
Google Connection Router - MCP-facing endpoints for Google Calendar connection.

Priority Guardian Increment 01: Provides MCP tools with connection status
and secure OAuth initiation.

Endpoints:
    GET /connection-status: Check if user has active Google connection
    POST /initiate-connection: Generate opaque token for secure OAuth initiation

These endpoints are called by the MCP server (not browsers).
They return JSON responses for MCP tool consumption.
"""

import structlog
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.models import CoreConnection
from backend.core.google_oauth import store_connection_token
from backend.core.config import settings

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Priority Guardian Google Connection"])


@router.get("/connection-status")
async def get_connection_status(
    x_user_id: str = Header(..., alias="X-User-ID"),
    session: AsyncSession = Depends(get_db),
):
    """
    Check if user has an active Google Calendar connection.

    Called by MCP server with X-User-ID header (from validated JWT).

    Args:
        x_user_id: User ID from JWT (set by MCP after token validation)
        session: Database session

    Returns:
        200: {
            "connected": true,
            "connected_at": "2025-01-15T10:30:00Z",
            "scopes": ["https://www.googleapis.com/auth/calendar.readonly"]
        }
        or
        200: {"connected": false}

    Note:
        Returns 200 even when not connected (not an error condition).
    """
    # Fail fast on malformed user_id (defensive)
    user_id = UUID(x_user_id)

    # Query for active Google connection (not revoked)
    result = await session.execute(
        select(CoreConnection).where(
            CoreConnection.user_id == user_id,
            CoreConnection.provider == "google",
            CoreConnection.connection_type == "google",
            CoreConnection.revoked_at.is_(None),  # Must not be revoked
        )
    )
    connection = result.scalar_one_or_none()

    if connection:
        return {
            "connected": True,
            "connected_at": connection.created_at.isoformat() if connection.created_at else None,
            "scopes": connection.scopes,
        }

    return {"connected": False}


@router.post("/initiate-connection")
async def initiate_connection(
    request: Request,
    x_user_id: str = Header(..., alias="X-User-ID"),
):
    """
    Generate a secure, single-use token for Google OAuth initiation.

    Returns an opaque token that can be used in a browser URL.
    The token expires in 10 minutes and can only be used once.

    Security:
        - Token is cryptographically random (secrets.token_urlsafe)
        - Token stored in Redis with 10-minute TTL
        - Token deleted after first use (single-use)
        - user_id never exposed in URL

    Args:
        request: FastAPI request object
        x_user_id: User ID from JWT (set by MCP after token validation)

    Returns:
        200: {
            "token": "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
            "connect_url": "https://api.priority-guard.com/auth/google/start?token=...",
            "expires_in": 600
        }
        500: If Redis is unavailable
    """
    # Get correlation_id from request state (set by middleware)
    correlation_id = getattr(request.state, "correlation_id", None)

    try:
        # Generate and store opaque connection token
        token = await store_connection_token(x_user_id, correlation_id=correlation_id)

        # Construct the connect URL using the public backend URL
        connect_url = f"{settings.BACKEND_PUBLIC_URL}/auth/google/start?token={token}"

        return {
            "token": token,
            "connect_url": connect_url,
            "expires_in": 600,
        }
    except Exception as e:
        logger.error(
            "connection_token_generation_failed",
            error=str(e),
            user_id=x_user_id,
            correlation_id=correlation_id,
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to generate connection token. Please try again.",
        )
