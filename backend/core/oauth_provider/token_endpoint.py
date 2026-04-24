"""
Token Endpoint - OAuth 2.1 token issuance.

HTTP layer only. Delegates all logic to service layer.

Note: OAuth 2.1 requires form-urlencoded POST data (RFC 6749 Section 4.1.3).
Supports client credentials via both form body and HTTP Basic Auth header.
"""

import base64
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.logging import get_logger, mask_client_id
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


def _extract_basic_auth(request: Request) -> tuple[str | None, str | None]:
    """
    Extract client_id and client_secret from HTTP Basic Auth header.

    Per RFC 6749 Section 2.3.1, clients may authenticate via Basic Auth.

    Returns:
        Tuple of (client_id, client_secret) or (None, None) if not present
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.lower().startswith("basic "):
        return None, None

    try:
        encoded = auth_header[6:]  # Remove "Basic " prefix
        decoded = base64.b64decode(encoded).decode("utf-8")
        if ":" not in decoded:
            return None, None
        client_id, client_secret = decoded.split(":", 1)
        return client_id, client_secret
    except Exception:
        return None, None


@router.post("/oauth/focused/token")
@router.post("/oauth/pg/token")
@router.post("/oauth/mindsort/token")
async def token_endpoint(
    request: Request,
    grant_type: str = Form(...),
    code: str | None = Form(None),
    redirect_uri: str | None = Form(None),
    code_verifier: str | None = Form(None),
    refresh_token: str | None = Form(None),
    client_id: str | None = Form(None),
    resource: str | None = Form(None),
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
            resource: Optional MCP server URL (RFC 9728 B2-5)

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

    # Extract client credentials from Basic Auth header if not in form body
    # Per RFC 6749 Section 2.3.1, clients may use HTTP Basic Auth
    # NOTE: Do not log client_id from Basic Auth - the header contains secrets
    client_from_header = False
    if not client_id:
        header_client_id, _header_client_secret = _extract_basic_auth(request)
        if header_client_id:
            client_id = header_client_id
            client_from_header = True

    # Log token request
    # Don't log client_id if it came from Basic Auth (header contains secrets)
    request_logger.info(
        "oauth.token.request",
        grant_type=grant_type,
        client_id="[from_header]" if client_from_header else mask_client_id(client_id)
    )

    # Require client_id (from form body or Basic Auth).
    # RFC 6749 §5.2: invalid_client → 401 with WWW-Authenticate challenge.
    # Use 'Bearer realm="oauth"' — AS-level challenge, no RS-specific metadata
    # (per ADR MCP Server Implementation Standard → Backend Config Boundary).
    if client_id is None:
        request_logger.warning(
            "oauth.token.error",
            error="invalid_client",
            error_description="client_id is required",
            grant_type=grant_type,
        )
        return JSONResponse(
            status_code=401,
            content={
                "error": "invalid_client",
                "error_description": "client_id is required"
            },
            headers={"WWW-Authenticate": 'Bearer realm="oauth"'}
        )

    # Rate limit check
    await rate_limit_token(request, client_id)

    # Validate grant_type
    valid, error = validate_grant_type(grant_type)
    if not valid:
        request_logger.error(
            "oauth.token.error",
            error=error,
            grant_type=grant_type
        )
        return JSONResponse(
            status_code=400,
            content={
                "error": error,
                "error_description": "Only authorization_code and refresh_token are supported"
            }
        )

    # Handle authorization_code grant
    if grant_type == "authorization_code":
        # Validate required fields
        valid, missing_field = validate_authorization_code_request(
            code,
            code_verifier,
            client_id,
            redirect_uri
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
            code=code,
            code_verifier=code_verifier,
            client_id=client_id,
            redirect_uri=redirect_uri,
            resource=resource,  # RFC 9728 B2-5
            correlation_id=correlation_id
        )

        # Check if error
        if isinstance(result, tuple):
            error_code, error_description = result
            request_logger.warning(
                "oauth.token.error",
                grant_type="authorization_code",
                error=error_code,
                error_description=error_description,
                client_id=mask_client_id(client_id)
            )
            # OAuth 2.1: invalid_client → 401, invalid_grant → 400
            status_code = 401 if error_code == "invalid_client" else 400
            # RFC 6750: Add WWW-Authenticate header for 401 responses
            # Use 'Bearer realm="oauth"' — AS-level challenge, no RS-specific metadata
            headers = {"WWW-Authenticate": 'Bearer realm="oauth"'} if status_code == 401 else None
            return JSONResponse(
                status_code=status_code,
                content={
                    "error": error_code,
                    "error_description": error_description
                },
                headers=headers
            )

        return JSONResponse(result)

    # Handle refresh_token grant
    elif grant_type == "refresh_token":
        # Validate required fields
        valid, missing_field = validate_refresh_token_request(
            refresh_token,
            client_id
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
            refresh_token=refresh_token,
            client_id=client_id,
            correlation_id=correlation_id
        )

        # Check if error
        if isinstance(result, tuple):
            error_code, error_description = result
            request_logger.warning(
                "oauth.token.error",
                grant_type="refresh_token",
                error=error_code,
                error_description=error_description,
                client_id=mask_client_id(client_id)
            )
            # OAuth 2.1: invalid_client → 401, invalid_grant → 400
            status_code = 401 if error_code == "invalid_client" else 400
            # RFC 6750: Add WWW-Authenticate header for 401 responses
            # Use 'Bearer realm="oauth"' — AS-level challenge, no RS-specific metadata
            headers = {"WWW-Authenticate": 'Bearer realm="oauth"'} if status_code == 401 else None
            return JSONResponse(
                status_code=status_code,
                content={
                    "error": error_code,
                    "error_description": error_description
                },
                headers=headers
            )

        return JSONResponse(result)
