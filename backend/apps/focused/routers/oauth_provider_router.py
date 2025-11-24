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
import secrets
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.database import get_db
from backend.core.jwt_utils import create_access_token
from backend.core.logging import get_logger

# Import extracted OAuth modules
from backend.apps.focused.oauth.authorize import router as authorize_router
from backend.apps.focused.oauth.consent_ui import router as consent_router
from backend.apps.focused.oauth.discovery import router as discovery_router
from backend.apps.focused.oauth.jwks import router as jwks_router
from backend.apps.focused.oauth.register_client import router as register_router
from backend.apps.focused.oauth.validators.pkce import verify_pkce, validate_code_challenge_method

logger = get_logger(__name__)

router = APIRouter(tags=["oauth-provider"])

# Include extracted routers
router.include_router(authorize_router)
router.include_router(consent_router)
router.include_router(discovery_router)
router.include_router(jwks_router)
router.include_router(register_router)


# =============================================================================
# Token Endpoint (Increment 7B)
# =============================================================================

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
    """
    from datetime import datetime, timezone
    from sqlalchemy import select
    from backend.core.oauth_models import OAuthAuthorizationCode, OAuthAccessToken
    from backend.core.encryption import encrypt_token, decrypt_token
    from backend.core.jwt_utils import create_refresh_token, calculate_refresh_token_expiry
    from backend.core.rate_limit import rate_limit_token

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

    if token_request.grant_type == "authorization_code":
        return await _handle_authorization_code_grant(token_request, db, request_logger)
    elif token_request.grant_type == "refresh_token":
        return await _handle_refresh_token_grant(token_request, db, request_logger)
    else:
        request_logger.error(
            "oauth.token.error",
            error="unsupported_grant_type",
            grant_type=token_request.grant_type
        )
        return JSONResponse(
            status_code=400,
            content={
                "error": "unsupported_grant_type",
                "error_description": "Only authorization_code and refresh_token are supported"
            }
        )


async def _handle_authorization_code_grant(
    token_request: TokenRequest,
    db: AsyncSession,
    request_logger
):
    """
    Handle authorization_code grant type.

    Validates code, PKCE, and issues new tokens.
    """
    from datetime import datetime, timezone
    from sqlalchemy import select
    from backend.core.oauth_models import OAuthAuthorizationCode, OAuthAccessToken
    from backend.core.encryption import encrypt_token
    from backend.core.jwt_utils import create_refresh_token, calculate_refresh_token_expiry

    # Validate required fields
    if not token_request.code:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_request",
                "error_description": "code is required"
            }
        )

    if not token_request.code_verifier:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_request",
                "error_description": "code_verifier is required (PKCE)"
            }
        )

    if not token_request.client_id:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_request",
                "error_description": "client_id is required"
            }
        )

    if not token_request.redirect_uri:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_request",
                "error_description": "redirect_uri is required"
            }
        )

    # Load authorization code from database
    result = await db.execute(
        select(OAuthAuthorizationCode).where(
            OAuthAuthorizationCode.code == token_request.code
        )
    )
    auth_code = result.scalar_one_or_none()

    if not auth_code:
        return JSONResponse(
            status_code=401,
            content={
                "error": "invalid_grant",
                "error_description": "Invalid authorization code"
            }
        )

    # Check code not expired
    if auth_code.expires_at < datetime.now(timezone.utc):
        return JSONResponse(
            status_code=401,
            content={
                "error": "invalid_grant",
                "error_description": "Authorization code expired"
            }
        )

    # Check code not already used
    if auth_code.used:
        return JSONResponse(
            status_code=401,
            content={
                "error": "invalid_grant",
                "error_description": "Authorization code already used"
            }
        )

    # Verify PKCE: SHA256(code_verifier) == code_challenge
    if not verify_pkce(token_request.code_verifier, auth_code.code_challenge):
        return JSONResponse(
            status_code=401,
            content={
                "error": "invalid_grant",
                "error_description": "PKCE verification failed"
            }
        )

    # Validate client_id matches
    if token_request.client_id != auth_code.client_id:
        return JSONResponse(
            status_code=401,
            content={
                "error": "invalid_grant",
                "error_description": "client_id mismatch"
            }
        )

    # Validate redirect_uri matches
    if token_request.redirect_uri != auth_code.redirect_uri:
        return JSONResponse(
            status_code=401,
            content={
                "error": "invalid_grant",
                "error_description": "redirect_uri mismatch"
            }
        )

    # Mark code as used
    auth_code.used = True
    await db.commit()

    # Create access token (JWT)
    access_token, jti = create_access_token(
        user_id=auth_code.user_id,
        client_id=auth_code.client_id,
        scope=auth_code.scope
    )

    # Create refresh token
    refresh_token_plain = create_refresh_token()
    refresh_token_encrypted = encrypt_token(refresh_token_plain)
    refresh_token_expires_at = calculate_refresh_token_expiry()

    # Calculate access token expiration
    from datetime import timedelta
    access_token_expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=settings.OAUTH_TOKEN_EXPIRY_SECONDS
    )

    # Store access token in database
    access_token_record = OAuthAccessToken(
        jti=jti,
        user_id=auth_code.user_id,
        client_id=auth_code.client_id,
        scope=auth_code.scope,
        token_type="Bearer",
        expires_at=access_token_expires_at,
        refresh_token_enc=refresh_token_encrypted,
        refresh_token_expires_at=refresh_token_expires_at,
        revoked=False,
        last_used_at=datetime.now(timezone.utc)
    )

    db.add(access_token_record)
    await db.commit()

    request_logger.info(
        "oauth.token.success",
        grant_type="authorization_code",
        jti=jti,
        user_id=str(auth_code.user_id),
        client_id=auth_code.client_id,
        scope=auth_code.scope
    )

    return JSONResponse({
        "access_token": access_token,
        "refresh_token": refresh_token_plain,
        "token_type": "Bearer",
        "expires_in": settings.OAUTH_TOKEN_EXPIRY_SECONDS,
        "scope": auth_code.scope
    })


async def _handle_refresh_token_grant(
    token_request: TokenRequest,
    db: AsyncSession,
    request_logger
):
    """
    Handle refresh_token grant type.

    Validates refresh token, revokes old tokens, and issues new ones.
    """
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select
    from backend.core.oauth_models import OAuthAccessToken
    from backend.core.encryption import encrypt_token, decrypt_token
    from backend.core.jwt_utils import create_refresh_token, calculate_refresh_token_expiry

    # Validate required fields
    if not token_request.refresh_token:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_request",
                "error_description": "refresh_token is required"
            }
        )

    if not token_request.client_id:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_request",
                "error_description": "client_id is required"
            }
        )

    # Find token by refresh_token (need to decrypt and match)
    result = await db.execute(
        select(OAuthAccessToken).where(
            OAuthAccessToken.refresh_token_enc.isnot(None)
        )
    )
    all_tokens = result.scalars().all()

    # Find matching refresh token
    matching_token = None
    for token in all_tokens:
        try:
            decrypted = decrypt_token(token.refresh_token_enc)
            if decrypted == token_request.refresh_token:
                matching_token = token
                break
        except Exception:
            continue

    if not matching_token:
        return JSONResponse(
            status_code=401,
            content={
                "error": "invalid_grant",
                "error_description": "Invalid refresh token"
            }
        )

    # Check not expired
    if matching_token.refresh_token_expires_at < datetime.now(timezone.utc):
        return JSONResponse(
            status_code=401,
            content={
                "error": "invalid_grant",
                "error_description": "Refresh token expired"
            }
        )

    # Check not revoked
    if matching_token.revoked:
        return JSONResponse(
            status_code=401,
            content={
                "error": "invalid_grant",
                "error_description": "Refresh token revoked"
            }
        )

    # Check client_id matches
    if token_request.client_id != matching_token.client_id:
        return JSONResponse(
            status_code=401,
            content={
                "error": "invalid_grant",
                "error_description": "client_id mismatch"
            }
        )

    # Revoke old token
    matching_token.revoked = True
    matching_token.revoked_at = datetime.now(timezone.utc)

    # Create new access token (same scope as old token)
    new_access_token, new_jti = create_access_token(
        user_id=matching_token.user_id,
        client_id=matching_token.client_id,
        scope=matching_token.scope
    )

    # Create new refresh token
    new_refresh_token_plain = create_refresh_token()
    new_refresh_token_encrypted = encrypt_token(new_refresh_token_plain)
    new_refresh_token_expires_at = calculate_refresh_token_expiry()

    # Calculate access token expiration
    new_access_token_expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=settings.OAUTH_TOKEN_EXPIRY_SECONDS
    )

    # Store new access token
    new_access_token_record = OAuthAccessToken(
        jti=new_jti,
        user_id=matching_token.user_id,
        client_id=matching_token.client_id,
        scope=matching_token.scope,
        token_type="Bearer",
        expires_at=new_access_token_expires_at,
        refresh_token_enc=new_refresh_token_encrypted,
        refresh_token_expires_at=new_refresh_token_expires_at,
        revoked=False,
        last_used_at=datetime.now(timezone.utc)
    )

    db.add(new_access_token_record)
    await db.commit()

    request_logger.info(
        "oauth.token.success",
        grant_type="refresh_token",
        old_jti=matching_token.jti,
        new_jti=new_jti,
        user_id=str(matching_token.user_id),
        client_id=matching_token.client_id,
        scope=matching_token.scope
    )

    return JSONResponse({
        "access_token": new_access_token,
        "refresh_token": new_refresh_token_plain,
        "token_type": "Bearer",
        "expires_in": settings.OAUTH_TOKEN_EXPIRY_SECONDS,
        "scope": matching_token.scope
    })


# =============================================================================
# Revocation Endpoint (Increment 7B)
# =============================================================================

class RevokeRequest(BaseModel):
    """OAuth token revocation request."""
    token: str
    client_id: str


@router.post("/oauth/focused/revoke")
async def revoke_endpoint(
    request: Request,
    revoke_request: RevokeRequest,
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
    """
    from datetime import datetime, timezone
    from sqlalchemy import select
    from jose import jwt, JWTError
    from backend.core.oauth_models import OAuthAccessToken
    from backend.core.encryption import decrypt_token
    from backend.core.rate_limit import rate_limit_revoke

    # Get correlation_id for logging
    correlation_id = request.state.correlation_id
    request_logger = logger.bind(correlation_id=correlation_id)

    request_logger.info(
        "oauth.revoke.request",
        client_id=revoke_request.client_id
    )

    # Rate limit check
    await rate_limit_revoke(request, revoke_request.client_id)

    # Try to parse as JWT (access token)
    try:
        # Decode JWT without verification (we just need the jti)
        decoded = jwt.get_unverified_claims(revoke_request.token)
        jti = decoded.get("jti")

        if jti:
            # Find access token by JTI
            result = await db.execute(
                select(OAuthAccessToken).where(OAuthAccessToken.jti == jti)
            )
            token_record = result.scalar_one_or_none()

            if token_record and token_record.client_id == revoke_request.client_id:
                # Revoke access token
                token_record.revoked = True
                token_record.revoked_at = datetime.now(timezone.utc)
                await db.commit()

                request_logger.info(
                    "oauth.revoke.success",
                    token_type="access_token",
                    jti=jti,
                    client_id=revoke_request.client_id
                )

            # Always return 200 (don't leak token existence)
            return JSONResponse({"success": True}, status_code=200)

    except JWTError:
        # Not a JWT, might be refresh token
        pass

    # Try to find as refresh token (opaque)
    result = await db.execute(
        select(OAuthAccessToken).where(
            OAuthAccessToken.refresh_token_enc.isnot(None)
        )
    )
    all_tokens = result.scalars().all()

    # Find matching refresh token
    for token_record in all_tokens:
        try:
            decrypted = decrypt_token(token_record.refresh_token_enc)
            if decrypted == revoke_request.token:
                # Verify client_id matches
                if token_record.client_id == revoke_request.client_id:
                    # Revoke this token
                    token_record.revoked = True
                    token_record.revoked_at = datetime.now(timezone.utc)
                    await db.commit()

                    request_logger.info(
                        "oauth.revoke.success",
                        token_type="refresh_token",
                        jti=token_record.jti,
                        client_id=revoke_request.client_id
                    )

                # Always return 200 (don't leak token existence)
                return JSONResponse({"success": True}, status_code=200)
        except Exception:
            continue

    # Token not found or invalid - still return 200 per RFC 7009
    logger.debug(f"Token revocation request completed (token not found)")
    return JSONResponse({"success": True}, status_code=200)


