"""
Client Registration Endpoint - OAuth 2.1 Dynamic Client Registration.

Implements RFC 7591 client registration for ChatGPT SDK integration.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.logging import get_logger
from backend.core.rate_limit import rate_limit_register
from backend.apps.focused.oauth.services.client_service import create_oauth_client
from backend.apps.focused.oauth.validators.client_metadata import (
    validate_client_name,
    validate_redirect_uris,
    validate_grant_types
)

logger = get_logger(__name__)

router = APIRouter(tags=["oauth-provider"])


class RegisterRequest(BaseModel):
    """OAuth client registration request."""
    client_name: str
    redirect_uris: list[str]
    grant_types: list[str] | None = None


@router.post("/oauth/focused/register")
async def register_endpoint(
    request: Request,
    register_request: RegisterRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    OAuth 2.1 dynamic client registration endpoint.

    Registers a new OAuth client and returns credentials.

    Request Body:
        client_name: Human-readable client name
        redirect_uris: Array of allowed redirect URIs (must use HTTPS)
        grant_types: Optional array of allowed grant types (default: authorization_code, refresh_token)

    Returns:
        client_id: Generated client identifier (focused-client-{uuid})
        client_secret: Generated client secret (32-byte URL-safe token)
        redirect_uris: Registered redirect URIs
        scope: Allowed scopes (focused.read focused.write focused.notify)

    Security Notes:
        - client_secret is only returned once (never stored in plain text)
        - Client must store client_secret securely
        - All redirect_uris must use HTTPS
        - Rate limited to prevent abuse

    Example Response:
        {
            "client_id": "focused-client-12345678-1234-1234-1234-123456789abc",
            "client_secret": "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
            "redirect_uris": ["https://chat.openai.com/aip/callback"],
            "scope": "focused.read focused.write focused.notify"
        }
    """
    # Get correlation_id for logging
    correlation_id = request.state.correlation_id
    request_logger = logger.bind(correlation_id=correlation_id)

    # Rate limit check
    await rate_limit_register(request)

    # Validate client_name
    valid, error = validate_client_name(register_request.client_name)
    if not valid:
        raise HTTPException(status_code=400, detail=error)

    # Validate redirect_uris
    valid, error = validate_redirect_uris(register_request.redirect_uris)
    if not valid:
        raise HTTPException(status_code=400, detail=error)

    # Validate grant_types
    valid, error = validate_grant_types(register_request.grant_types)
    if not valid:
        raise HTTPException(status_code=400, detail=error)

    # Set default grant types
    grant_types = register_request.grant_types or ["authorization_code", "refresh_token"]

    # Create OAuth client (handles encryption and DB persistence)
    client_id, client_secret = await create_oauth_client(
        db=db,
        client_name=register_request.client_name,
        redirect_uris=register_request.redirect_uris,
        grant_types=grant_types,
        correlation_id=correlation_id
    )

    # Return client credentials (client_secret only shown once)
    return JSONResponse({
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uris": register_request.redirect_uris,
        "scope": "focused.read focused.write focused.notify"
    })
