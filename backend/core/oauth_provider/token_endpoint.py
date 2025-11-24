"""
Token Endpoint - OAuth 2.1 token issuance.

HTTP layer only. Delegates all logic to service layer.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.logging import get_logger
from backend.core.rate_limit import rate_limit_token
from backend.core.oauth_provider.services.token_service import (
    exchange_authorization_code,
    exchange_refresh_token
)
from backend.core.oauth_provider.validators.token_validators import (
    validate_grant_type,
    validate_authorization_code_request,
    validate_refresh_token_request
)

logger = get_logger(__name__)

router = APIRouter(tags=["oauth-provider"])


class TokenRequest(BaseModel):
    """OAuth token request (standard fields)."""
    grant_type: str
    code: str | None = None
    redirect_uri: str | None = None
    code_verifier: str | None = None
    refresh_token: str | None = None
    client_id: str | None = None


@router.post("/oauth/focused/token")
async def token_endpoint(
    request: Request,
    token_request: TokenRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    OAuth 2.1 token endpoint.

    Supports two grant types:
    1. authorization_code: Exchange code for access + refresh tokens
    2. refresh_token: Rotate tokens

    Request Body:
        grant_type: "authorization_code" or "refresh_token"

        For authorization_code:
            code: Authorization code from /authorize
            code_verifier: PKCE code verifier
            client_id: OAuth client ID
            redirect_uri: Must match original request

        For refresh_token:
            refresh_token: Refresh token from previous /token response
            client_id: OAuth client ID

    Returns:
        access_token: JWT signed with RS256
        refresh_token: Opaque token (only for authorization_code grant)
        token_type: "Bearer"
        expires_in: Expiration in seconds
        scope: Space-separated scopes

    Security Notes:
        - PKCE required for authorization_code grant
        - Refresh token rotation (old token revoked)
        - Rate limited per client
        - All tokens stored encrypted in database

    Example Response:
        {
            "access_token": "eyJhbGc...",
            "refresh_token": "abc123...",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "focused.read focused.write"
        }

    Example Error:
        {
            "error": "invalid_grant",
            "error_description": "Authorization code expired"
        }
    """
    # Get correlation_id for logging
    correlation_id = request.state.correlation_id
    request_logger = logger.bind(correlation_id=correlation_id)

    # Log token request
    request_logger.info(
        "oauth.token.request",
        grant_type=token_request.grant_type,
        client_id=token_request.client_id
    )

    # Rate limit check (requires client_id)
    if token_request.client_id:
        await rate_limit_token(request, token_request.client_id)

    # Validate grant_type
    valid, error = validate_grant_type(token_request.grant_type)
    if not valid:
        request_logger.error(
            "oauth.token.error",
            error=error,
            grant_type=token_request.grant_type
        )
        return JSONResponse(
            status_code=400,
            content={
                "error": error,
                "error_description": "Only authorization_code and refresh_token are supported"
            }
        )

    # Handle authorization_code grant
    if token_request.grant_type == "authorization_code":
        # Validate required fields
        valid, missing_field = validate_authorization_code_request(
            token_request.code,
            token_request.code_verifier,
            token_request.client_id,
            token_request.redirect_uri
        )
        if not valid:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "invalid_request",
                    "error_description": f"{missing_field} is required" + (" (PKCE)" if missing_field == "code_verifier" else "")
                }
            )

        # Exchange code for tokens
        result = await exchange_authorization_code(
            db=db,
            code=token_request.code,
            code_verifier=token_request.code_verifier,
            client_id=token_request.client_id,
            redirect_uri=token_request.redirect_uri,
            correlation_id=correlation_id
        )

        # Check if error
        if isinstance(result, tuple):
            error_code, error_description = result
            return JSONResponse(
                status_code=401,
                content={
                    "error": error_code,
                    "error_description": error_description
                }
            )

        return JSONResponse(result)

    # Handle refresh_token grant
    elif token_request.grant_type == "refresh_token":
        # Validate required fields
        valid, missing_field = validate_refresh_token_request(
            token_request.refresh_token,
            token_request.client_id
        )
        if not valid:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "invalid_request",
                    "error_description": f"{missing_field} is required"
                }
            )

        # Exchange refresh token for new tokens
        result = await exchange_refresh_token(
            db=db,
            refresh_token=token_request.refresh_token,
            client_id=token_request.client_id,
            correlation_id=correlation_id
        )

        # Check if error
        if isinstance(result, tuple):
            error_code, error_description = result
            return JSONResponse(
                status_code=401,
                content={
                    "error": error_code,
                    "error_description": error_description
                }
            )

        return JSONResponse(result)
