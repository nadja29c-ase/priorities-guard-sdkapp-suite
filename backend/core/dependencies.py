"""
Shared dependencies for all backend routers.

Contains FastAPI dependencies used across multiple apps (PG, Clarity, etc).
"""

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

    if not x_internal_secret or x_internal_secret != settings.INTERNAL_API_SECRET:
        # Generic error - never reveal expected vs actual secret
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )
