"""
OAuth Provider Router — OAuth 2.1 provider for ChatGPT SDK integration (Increment 7A).

Implements:
- Discovery endpoints (.well-known/openid-configuration, oauth-protected-resource)
- JWKS endpoint (JSON Web Key Set for JWT verification)
- Placeholder /authorize, /token, /register endpoints

Status: Increment 7A COMPLETE (Skeleton implementation)
Real authorization logic will be added in Increment 7B.
"""

import json
import logging
import secrets
import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from backend.core.config import settings
from backend.core.crypto import get_current_jwks
from backend.core.jwt_utils import create_access_token
from backend.core.redis_client import redis_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["oauth-provider"])


# =============================================================================
# Discovery Endpoints
# =============================================================================

@router.get("/.well-known/openid-configuration")
async def openid_configuration():
    """
    OpenID Connect Discovery endpoint.

    Returns OAuth provider configuration for ChatGPT discovery.
    """
    return JSONResponse({
        "issuer": settings.OAUTH_ISSUER,
        "authorization_endpoint": f"{settings.OAUTH_ISSUER}/oauth/focused/authorize",
        "token_endpoint": f"{settings.OAUTH_ISSUER}/oauth/focused/token",
        "jwks_uri": f"{settings.OAUTH_ISSUER}/oauth/focused/jwks",
        "registration_endpoint": f"{settings.OAUTH_ISSUER}/oauth/focused/register",
        "scopes_supported": ["focused.read", "focused.write", "focused.notify"],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"]
    })


@router.get("/.well-known/oauth-protected-resource")
async def oauth_protected_resource():
    """
    OAuth Protected Resource Metadata endpoint.

    Describes the MCP server resource and scopes.
    """
    return JSONResponse({
        "resource": f"{settings.OAUTH_ISSUER}/mcp/focused",
        "authorization_servers": [settings.OAUTH_ISSUER],
        "scopes": {
            "focused.read": "Read calendar sync status and focus analytics",
            "focused.write": "Activate Focus Mode and modify settings",
            "focused.notify": "Send push notifications"
        }
    })


# =============================================================================
# JWKS Endpoint
# =============================================================================

@router.get("/oauth/focused/jwks")
async def jwks_endpoint():
    """
    JSON Web Key Set (JWKS) endpoint.

    Returns public keys for JWT signature verification.
    Cached in Redis with 24h TTL.
    """
    # Check Redis cache
    try:
        if redis_client.is_connected():
            cached_jwks = await redis_client.get("oauth:jwks:current")
            if cached_jwks:
                logger.debug("Returning cached JWKS")
                return JSONResponse(json.loads(cached_jwks))
    except Exception as e:
        logger.warning(f"Redis cache miss for JWKS: {e}")

    # Generate JWKS from public key
    jwks = get_current_jwks()

    # Cache in Redis (24h TTL)
    try:
        if redis_client.is_connected():
            await redis_client.set(
                "oauth:jwks:current",
                json.dumps(jwks),
                ex=86400  # 24 hours
            )
            logger.debug("Cached JWKS in Redis")
    except Exception as e:
        logger.warning(f"Failed to cache JWKS: {e}")

    return JSONResponse(jwks)


# =============================================================================
# Placeholder: Authorization Endpoint
# =============================================================================

@router.get("/oauth/focused/authorize", response_class=HTMLResponse)
async def authorize_endpoint(request: Request):
    """
    OAuth authorization endpoint (placeholder for 7A).

    Real implementation in 7B:
    - PKCE validation
    - User consent screen
    - Authorization code generation
    """
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Focused - Authorize</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                max-width: 600px;
                margin: 100px auto;
                padding: 20px;
                text-align: center;
            }
            h1 {
                color: #333;
            }
            p {
                color: #666;
                font-size: 14px;
            }
        </style>
    </head>
    <body>
        <h1>OAuth Authorization</h1>
        <p>Placeholder - implementation in Increment 7B</p>
        <p style="margin-top: 40px; color: #999;">
            This is the OAuth provider skeleton (7A).<br>
            Authorization logic will be added in 7B.
        </p>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content, status_code=200)


# =============================================================================
# Placeholder: Token Endpoint
# =============================================================================

class TokenRequest(BaseModel):
    """OAuth token request (standard fields)."""
    grant_type: str
    code: str | None = None
    redirect_uri: str | None = None
    code_verifier: str | None = None
    refresh_token: str | None = None


@router.post("/oauth/focused/token")
async def token_endpoint(token_request: TokenRequest):
    """
    OAuth token endpoint (placeholder for 7A).

    Returns dummy JWT for testing.

    Real implementation in 7B:
    - Validate authorization code
    - Verify PKCE code_verifier
    - Issue real access token
    - Handle refresh tokens
    """
    # 7A: Basic validation (check grant_type exists)
    if not token_request.grant_type:
        raise HTTPException(status_code=400, detail="grant_type required")

    # 7A: Return dummy JWT (no validation)
    dummy_user_id = uuid4()
    dummy_client_id = "focused-client-001"
    dummy_scope = "focused.read focused.write"

    access_token, jti = create_access_token(
        user_id=dummy_user_id,
        client_id=dummy_client_id,
        scope=dummy_scope
    )

    logger.info(
        f"Issued dummy access token (7A): jti={jti}, "
        f"user_id={dummy_user_id}, grant_type={token_request.grant_type}"
    )

    return JSONResponse({
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": settings.OAUTH_TOKEN_EXPIRY_SECONDS,
        "scope": dummy_scope
    })


# =============================================================================
# Placeholder: Client Registration Endpoint
# =============================================================================

class RegisterRequest(BaseModel):
    """OAuth client registration request (minimal)."""
    client_name: str | None = None
    redirect_uris: list[str] | None = None


@router.post("/oauth/focused/register")
async def register_endpoint(register_request: RegisterRequest):
    """
    OAuth client registration endpoint (placeholder for 7A).

    Returns static client credentials.

    Real implementation in 7B:
    - Store client in database (core_connections with connection_type='oauth_provider')
    - Generate real client_id and client_secret
    - Validate redirect_uris
    """
    # 7A: Return static placeholder
    client_id = f"focused-client-{secrets.token_hex(8)}"
    client_secret = secrets.token_urlsafe(32)

    logger.info(
        f"Registered dummy OAuth client (7A): client_id={client_id}, "
        f"client_name={register_request.client_name}"
    )

    return JSONResponse({
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "focused.read focused.write focused.notify"
    })
