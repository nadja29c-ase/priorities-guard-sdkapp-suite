"""
Shared dependencies for all backend routers.

Contains FastAPI dependencies used across multiple apps (PG, Clarity, etc).
"""

import secrets
from uuid import UUID

from fastapi import Header, HTTPException, status

from backend.core.config import settings


def verify_internal_call(
    x_internal_secret: str | None = Header(None, alias="X-Internal-Secret"),
) -> None:
    """
    Verify request comes from trusted internal service (MCP server).

    Use as a router-level dependency to protect all endpoints in a router.
    Automatically applied via dependencies=[Depends(verify_internal_call)] on APIRouter.

    Security Model:
        - In dev mode (INTERNAL_API_SECRET empty): verification skipped
        - In production (INTERNAL_API_SECRET set): requires matching header
        - NEVER reveals expected or attempted secret in error responses

    Args:
        x_internal_secret: X-Internal-Secret header value from request

    Raises:
        HTTPException 403: If header is missing or invalid in production mode
    """
    if not settings.INTERNAL_API_SECRET:
        # Dev mode: skip verification
        return

    if not x_internal_secret or not secrets.compare_digest(x_internal_secret, settings.INTERNAL_API_SECRET):
        # Generic error - never reveal expected vs actual secret
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )


def validate_user_id_header(
    x_user_id: str | None = Header(None, alias="X-User-ID")
) -> UUID:
    """
    Validate X-User-ID header as UUID.

    Trust Boundary: This header is trusted because it comes from the MCP server
    after JWT validation. The MCP server extracts user_id from the validated JWT's
    `sub` claim and sets this header. Never accept user_id from request body.

    Note: Header is declared optional (None default) so we can return 401 for missing
    headers. FastAPI's Header(...) would return 422, but we require 401
    for all auth-related failures.

    Args:
        x_user_id: User ID from MCP server (extracted from validated JWT)

    Returns:
        Validated UUID

    Raises:
        HTTPException 401: If header is missing or malformed (non-UUID)
    """
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Missing X-User-ID header"},
        )

    try:
        return UUID(x_user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Invalid X-User-ID header (must be UUID)"},
        )
