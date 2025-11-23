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
from backend.apps.focused.oauth.discovery import router as discovery_router
from backend.apps.focused.oauth.jwks import router as jwks_router
from backend.apps.focused.oauth.register_client import router as register_router
from backend.apps.focused.oauth.validators.pkce import verify_pkce, validate_code_challenge_method

logger = get_logger(__name__)

router = APIRouter(tags=["oauth-provider"])

# Include extracted routers
router.include_router(discovery_router)
router.include_router(jwks_router)
router.include_router(register_router)


# =============================================================================
# Authorization Endpoint (Increment 7B)
# =============================================================================

@router.get("/oauth/focused/authorize", response_class=HTMLResponse)
async def authorize_endpoint(
    request: Request,
    response_type: str,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    code_challenge_method: str,
    scope: str,
    state: str | None = None,
    nonce: str | None = None,
    user_id: str | None = None,  # TODO (7C): Replace with real authentication
    db: AsyncSession = Depends(get_db)
):
    """
    OAuth 2.1 authorization endpoint with PKCE.

    Validates client, redirect URI, and scopes, then renders consent screen.

    Query Parameters:
        response_type: Must be "code"
        client_id: Registered OAuth client ID
        redirect_uri: Must match client's registered URIs
        code_challenge: PKCE code challenge (SHA256)
        code_challenge_method: Must be "S256"
        scope: Space-separated scopes (focused.read, focused.write, focused.notify)
        state: Optional CSRF token
        nonce: Optional OpenID Connect nonce
        user_id: TODO - temporary auth placeholder (will be replaced with session auth)

    Returns:
        HTML consent screen on success
        Error redirect on validation failure
    """
    from sqlalchemy import select
    from backend.core.oauth_models import OAuthClient
    from backend.core.rate_limit import rate_limit_authorize

    # Get correlation_id for logging
    correlation_id = request.state.correlation_id

    # Bind correlation_id to logger for this request
    request_logger = logger.bind(correlation_id=correlation_id)

    # Rate limit check
    await rate_limit_authorize(request)

    # Log authorization request
    request_logger.info(
        "oauth.authorize.request",
        client_id=client_id,
        response_type=response_type,
        scope=scope,
        redirect_uri=redirect_uri,
        code_challenge_method=code_challenge_method
    )

    # TODO (7C): Replace with real authentication middleware
    # For now, require user_id query param as temporary auth mechanism
    if not user_id:
        request_logger.warning(
            "oauth.authorize.error",
            error="missing_user_id",
            message="Authentication required"
        )
        raise HTTPException(
            status_code=401,
            detail="Authentication required. TODO: Implement session-based auth."
        )

    # Validate response_type
    if response_type != "code":
        return _error_redirect(
            redirect_uri,
            state,
            error="unsupported_response_type",
            description="Only response_type=code is supported"
        )

    # Validate code_challenge_method (must be S256)
    if not validate_code_challenge_method(code_challenge_method):
        return _error_redirect(
            redirect_uri,
            state,
            error="invalid_request",
            description="code_challenge_method must be S256"
        )

    # Validate client exists
    result = await db.execute(
        select(OAuthClient).where(OAuthClient.client_id == client_id)
    )
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(status_code=401, detail="Invalid client_id")

    # Validate redirect_uri is in client's registered URIs
    if redirect_uri not in client.redirect_uris:
        raise HTTPException(status_code=400, detail="Invalid redirect_uri")

    # Validate scopes
    allowed_scopes = {"focused.read", "focused.write", "focused.notify"}
    requested_scopes = set(scope.split())

    if not requested_scopes.issubset(allowed_scopes):
        return _error_redirect(
            redirect_uri,
            state,
            error="invalid_scope",
            description=f"Invalid scopes. Allowed: {', '.join(allowed_scopes)}"
        )

    # Generate auth context ID
    auth_context_id = str(uuid4())

    # Store authorization context in Redis (10 minute TTL)
    auth_context = {
        "client_id": client_id,
        "client_name": client.client_name,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "scope": scope,
        "state": state or "",
        "nonce": nonce or "",
        "redirect_uri": redirect_uri,
        "user_id": user_id,
        "expires_at": int(time.time()) + 600  # 10 minutes
    }

    redis_key = f"oauth:auth:{auth_context_id}"
    await redis_client.set(
        redis_key,
        json.dumps(auth_context),
        ex=600  # 10 minutes
    )

    logger.info(
        f"Authorization context created: auth_context_id={auth_context_id}, "
        f"client_id={client_id}, user_id={user_id}, scope={scope}"
    )

    # Render consent screen
    # TODO (7C): Detect user language preference for EN/DE template selection
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="backend/templates")

    return templates.TemplateResponse(
        "oauth_consent_en.html",
        {
            "request": request,
            "auth_context_id": auth_context_id,
            "client_name": client.client_name,
            "scopes": requested_scopes
        }
    )


def _error_redirect(redirect_uri: str, state: str | None, error: str, description: str):
    """
    Redirect to client with OAuth error.

    Args:
        redirect_uri: Client's redirect URI
        state: CSRF state token
        error: OAuth error code
        description: Human-readable error description

    Returns:
        Redirect response with error parameters
    """
    from fastapi.responses import RedirectResponse
    from urllib.parse import urlencode

    params = {
        "error": error,
        "error_description": description
    }

    if state:
        params["state"] = state

    error_url = f"{redirect_uri}?{urlencode(params)}"
    return RedirectResponse(url=error_url, status_code=302)


# =============================================================================
# Consent POST Endpoint (Increment 7B)
# =============================================================================

@router.post("/oauth/focused/consent")
async def consent_endpoint(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle user consent decision (Allow/Deny).

    Form Data:
        auth_context_id: Authorization context ID from Redis
        action: "allow" or "deny"

    Returns:
        Redirect to client's redirect_uri with:
        - code and state (if allowed)
        - error=access_denied and state (if denied)
    """
    from fastapi.responses import RedirectResponse
    from urllib.parse import urlencode
    from datetime import datetime, timedelta, timezone
    from uuid import UUID
    from backend.core.oauth_models import OAuthAuthorizationCode

    # Get correlation_id for logging
    correlation_id = request.state.correlation_id
    request_logger = logger.bind(correlation_id=correlation_id)

    # Parse form data
    form_data = await request.form()
    auth_context_id = form_data.get("auth_context_id")
    action = form_data.get("action")

    request_logger.info(
        "oauth.consent.request",
        action=action,
        auth_context_id=auth_context_id
    )

    if not auth_context_id:
        raise HTTPException(status_code=400, detail="Missing auth_context_id")

    if action not in ("allow", "deny"):
        raise HTTPException(status_code=400, detail="Invalid action")

    # Load authorization context from Redis
    redis_key = f"oauth:auth:{auth_context_id}"
    auth_context_json = await redis_client.get(redis_key)

    if not auth_context_json:
        raise HTTPException(
            status_code=400,
            detail="Authorization context expired or invalid"
        )

    auth_context = json.loads(auth_context_json)

    # Extract context data
    client_id = auth_context["client_id"]
    code_challenge = auth_context["code_challenge"]
    code_challenge_method = auth_context["code_challenge_method"]
    scope = auth_context["scope"]
    state = auth_context.get("state") or None
    nonce = auth_context.get("nonce") or None
    redirect_uri = auth_context["redirect_uri"]
    user_id = auth_context["user_id"]

    # Delete authorization context from Redis (single-use)
    await redis_client.delete(redis_key)

    # Handle deny
    if action == "deny":
        request_logger.info(
            "oauth.consent.denied",
            user_id=user_id,
            client_id=client_id
        )

        params = {"error": "access_denied"}
        if state:
            params["state"] = state

        deny_url = f"{redirect_uri}?{urlencode(params)}"
        return RedirectResponse(url=deny_url, status_code=302)

    # Handle allow
    # Generate authorization code (128 characters, cryptographically random)
    authorization_code = secrets.token_urlsafe(96)  # 96 bytes -> 128 chars base64url

    # Calculate expiration (10 minutes)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    # Store authorization code in database
    auth_code_record = OAuthAuthorizationCode(
        code=authorization_code,
        user_id=UUID(user_id),
        client_id=client_id,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        redirect_uri=redirect_uri,
        scope=scope,
        state=state,
        nonce=nonce,
        expires_at=expires_at,
        used=False
    )

    db.add(auth_code_record)
    await db.commit()

    request_logger.info(
        "oauth.consent.allowed",
        user_id=user_id,
        client_id=client_id,
        scope=scope
    )

    # Redirect to client with authorization code
    params = {"code": authorization_code}
    if state:
        params["state"] = state

    success_url = f"{redirect_uri}?{urlencode(params)}"
    return RedirectResponse(url=success_url, status_code=302)


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


