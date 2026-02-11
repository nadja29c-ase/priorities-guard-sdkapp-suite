"""
Shared dependencies for Priority Guardian routers.

Contains FastAPI dependencies used across multiple routers.
"""

from uuid import UUID

from fastapi import Header, HTTPException, status


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
