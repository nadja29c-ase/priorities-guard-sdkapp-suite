"""
Revoke Endpoint - OAuth 2.1 token revocation (RFC 7009).

HTTP layer only. Delegates all logic to service layer.

Note: OAuth 2.1 requires form-urlencoded POST data (RFC 7009 Section 2.1).
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.logging import get_logger
from backend.core.rate_limit import rate_limit_revoke
from backend.core.oauth_provider.services.revoke_service import revoke_token

logger = get_logger(__name__)

router = APIRouter(tags=["oauth-provider"])


@router.post("/oauth/focused/revoke")
async def revoke_endpoint(
    request: Request,
    token: str = Form(...),
    client_id: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """
    OAuth 2.1 token revocation endpoint (RFC 7009).

    Revokes access tokens or refresh tokens.
    Always returns 200 (even if token doesn't exist).

    Request Body:
        token: Access token (JWT) or refresh token (opaque)
        client_id: OAuth client ID

    Returns:
        200 OK (always, per RFC 7009)

    Security Notes:
        - Always returns 200 to avoid leaking token existence
        - Rate limited per client
        - Validates client_id matches token owner
        - Supports both access tokens (JWT) and refresh tokens (opaque)

    Example Request:
        {
            "token": "eyJhbGc...",
            "client_id": "client_abc123"
        }

    Example Response:
        {
            "success": true
        }
    """
    # Get correlation_id for logging
    correlation_id = request.state.correlation_id
    request_logger = logger.bind(correlation_id=correlation_id)

    request_logger.info(
        "oauth.revoke.request",
        client_id=client_id
    )

    # Rate limit check
    await rate_limit_revoke(request, client_id)

    # Revoke token (service layer handles all logic)
    success, token_type = await revoke_token(
        db=db,
        token=token,
        client_id=client_id,
        correlation_id=correlation_id
    )

    # Always return 200 per RFC 7009 (don't leak token existence)
    return JSONResponse({"success": True}, status_code=200)
