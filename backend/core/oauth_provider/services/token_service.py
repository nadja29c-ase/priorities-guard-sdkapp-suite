"""
Token Service - OAuth 2.1 token issuance and refresh.

The heart of the OAuth provider. Handles:
- Authorization code → token exchange
- Refresh token rotation
- Token storage and revocation
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.encryption import encrypt_token, hash_refresh_token
from backend.core.logging import get_logger, mask_client_id
from backend.core.oauth_provider.jwt.utils import create_refresh_token, calculate_refresh_token_expiry
from backend.core.oauth_provider.models import OAuthAuthorizationCode, OAuthAccessToken
from backend.core.oauth_provider.jwt.jwt_signer import create_access_token
from backend.core.oauth_provider.validators.pkce import verify_pkce
from backend.core.oauth_provider.validators.token_validators import (
    validate_token_not_expired,
    validate_client_id_match,
    validate_redirect_uri_match
)

logger = get_logger(__name__)


async def exchange_authorization_code(
    db: AsyncSession,
    code: str,
    code_verifier: str,
    client_id: str,
    redirect_uri: str,
    resource: str | None = None,
    correlation_id: str | None = None
) -> dict | tuple[str, str]:
    """
    Exchange authorization code for access + refresh tokens.

    Validates:
    - Code exists and not expired
    - Code not already used
    - PKCE verification
    - client_id matches
    - redirect_uri matches

    Then:
    - Marks code as used
    - Generates access token (JWT)
    - Generates refresh token (opaque)
    - Stores tokens in database

    Args:
        db: Database session
        code: Authorization code
        code_verifier: PKCE code verifier
        client_id: Client identifier
        redirect_uri: Redirect URI
        resource: Optional resource parameter (RFC 9728 B2-5)
        correlation_id: Optional correlation ID for logging

    Returns:
        dict: Token response or tuple of (error_code, error_description)

    Example Success:
        {
            "access_token": "eyJhbGc...",
            "refresh_token": "abc123...",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "focused.read focused.write"
        }

    Example Error:
        ("invalid_grant", "Authorization code expired")
    """
    request_logger = logger.bind(correlation_id=correlation_id) if correlation_id else logger

    # Load authorization code from database
    # Use FOR UPDATE to acquire row-level lock and prevent concurrent exchange
    result = await db.execute(
        select(OAuthAuthorizationCode)
        .where(OAuthAuthorizationCode.code == code)
        .with_for_update()
    )
    auth_code = result.scalar_one_or_none()

    if not auth_code:
        return ("invalid_grant", "Invalid authorization code")

    # Validate not expired
    if not validate_token_not_expired(auth_code.expires_at):
        return ("invalid_grant", "Authorization code expired")

    # Validate not already used
    if auth_code.used:
        return ("invalid_grant", "Authorization code already used")

    # Verify PKCE
    if not verify_pkce(code_verifier, auth_code.code_challenge):
        return ("invalid_grant", "PKCE verification failed")

    # Validate client_id matches
    if not validate_client_id_match(auth_code.client_id, client_id):
        return ("invalid_grant", "client_id mismatch")

    # Validate redirect_uri matches
    if not validate_redirect_uri_match(auth_code.redirect_uri, redirect_uri):
        return ("invalid_grant", "redirect_uri mismatch")

    # =========================================================================
    # RFC 9728 B2-5: Resource resolution rules
    # Determines final_resource for JWT aud claim and OAuthAccessToken storage
    # =========================================================================
    if auth_code.resource:
        # Auth code has resource set
        if resource is None:
            # Rule 1: /token omits resource → use auth_code.resource (downgrade protection)
            final_resource = auth_code.resource
        elif resource == auth_code.resource:
            # Rule 2: /token sends matching resource → use auth_code.resource
            final_resource = auth_code.resource
        else:
            # Rule 3: /token sends different resource → error (cannot change)
            return ("invalid_request", "resource mismatch")
    else:
        # Auth code has no resource
        if resource:
            # Rule 4: /token sends resource → accept it
            final_resource = resource
        else:
            # Rule 5: Neither has resource → fall back to OAUTH_ISSUER
            final_resource = None  # create_access_token will use OAUTH_ISSUER

    # Mark code as used
    auth_code.used = True

    # Create access token (JWT)
    # Convert scope list to space-separated string (OAuth 2.0 standard)
    scope_str = " ".join(auth_code.scope) if isinstance(auth_code.scope, list) else auth_code.scope
    access_token, jti = create_access_token(
        user_id=auth_code.user_id,
        client_id=auth_code.client_id,
        scope=scope_str,
        resource=final_resource  # RFC 9728 B2-5
    )

    # Create refresh token
    refresh_token_plain = create_refresh_token()
    refresh_token_encrypted = encrypt_token(refresh_token_plain)
    refresh_token_hashed = hash_refresh_token(refresh_token_plain)
    refresh_token_expires_at = calculate_refresh_token_expiry()

    # Calculate access token expiration
    access_token_expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=settings.OAUTH_TOKEN_EXPIRY_SECONDS
    )

    # Store access token in database
    access_token_record = OAuthAccessToken(
        jti=jti,
        user_id=auth_code.user_id,
        client_id=auth_code.client_id,
        scope=auth_code.scope,
        resource=final_resource,  # RFC 9728 B2-5: stored for refresh grant
        token_type="Bearer",
        expires_at=access_token_expires_at,
        refresh_token_enc=refresh_token_encrypted,
        refresh_token_hash=refresh_token_hashed,
        refresh_token_expires_at=refresh_token_expires_at,
        revoked=False,
    )

    db.add(access_token_record)
    await db.commit()

    # Log success (mask client_id for privacy)
    request_logger.info(
        "oauth.token.success",
        grant_type="authorization_code",
        jti=jti,
        user_id=str(auth_code.user_id),
        client_id=mask_client_id(auth_code.client_id),
        scope=auth_code.scope
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token_plain,
        "token_type": "Bearer",
        "expires_in": settings.OAUTH_TOKEN_EXPIRY_SECONDS,
        "scope": scope_str  # Return as space-separated string (OAuth 2.0 standard)
    }


async def exchange_refresh_token(
    db: AsyncSession,
    refresh_token: str,
    client_id: str,
    correlation_id: str | None = None
) -> dict | tuple[str, str]:
    """
    Exchange refresh token for new access + refresh tokens.

    Validates:
    - Refresh token exists (decrypts all stored tokens to find match)
    - Token not expired
    - Token not revoked
    - client_id matches

    Then:
    - Revokes old token
    - Generates new access token (JWT)
    - Generates new refresh token (opaque)
    - Stores new tokens in database

    Args:
        db: Database session
        refresh_token: Refresh token (plain text)
        client_id: Client identifier
        correlation_id: Optional correlation ID for logging

    Returns:
        dict: Token response or tuple of (error_code, error_description)

    Example Success:
        {
            "access_token": "eyJhbGc...",
            "refresh_token": "xyz789...",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "focused.read focused.write"
        }

    Example Error:
        ("invalid_grant", "Refresh token expired")
    """
    request_logger = logger.bind(correlation_id=correlation_id) if correlation_id else logger

    # Find token by refresh_token hash (O(1) indexed lookup!)
    # Use FOR UPDATE to acquire row-level lock and prevent concurrent exchange
    # Filter revoked == False in WHERE clause so second concurrent caller sees zero rows
    refresh_token_hashed = hash_refresh_token(refresh_token)
    result = await db.execute(
        select(OAuthAccessToken)
        .where(
            OAuthAccessToken.refresh_token_hash == refresh_token_hashed,
            OAuthAccessToken.revoked == False,  # noqa: E712
        )
        .with_for_update()
    )
    matching_token = result.scalar_one_or_none()

    if not matching_token:
        return ("invalid_grant", "Invalid refresh token")

    # Validate not expired
    if not validate_token_not_expired(matching_token.refresh_token_expires_at):
        return ("invalid_grant", "Refresh token expired")

    # Validate client_id matches
    if not validate_client_id_match(matching_token.client_id, client_id):
        return ("invalid_grant", "client_id mismatch")

    # Revoke old token
    matching_token.revoked = True
    matching_token.revoked_at = datetime.now(timezone.utc)

    # Create new access token (same scope and resource as old token)
    # Convert scope list to space-separated string (OAuth 2.0 standard)
    scope_str = " ".join(matching_token.scope) if isinstance(matching_token.scope, list) else matching_token.scope
    new_access_token, new_jti = create_access_token(
        user_id=matching_token.user_id,
        client_id=matching_token.client_id,
        scope=scope_str,
        resource=matching_token.resource  # RFC 9728 B2-5: preserve resource from original token
    )

    # Create new refresh token
    new_refresh_token_plain = create_refresh_token()
    new_refresh_token_encrypted = encrypt_token(new_refresh_token_plain)
    new_refresh_token_hashed = hash_refresh_token(new_refresh_token_plain)
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
        resource=matching_token.resource,  # RFC 9728 B2-5: carry forward
        token_type="Bearer",
        expires_at=new_access_token_expires_at,
        refresh_token_enc=new_refresh_token_encrypted,
        refresh_token_hash=new_refresh_token_hashed,
        refresh_token_expires_at=new_refresh_token_expires_at,
        revoked=False,
    )

    db.add(new_access_token_record)
    await db.commit()

    # Log success (mask client_id for privacy)
    request_logger.info(
        "oauth.token.success",
        grant_type="refresh_token",
        old_jti=matching_token.jti,
        new_jti=new_jti,
        user_id=str(matching_token.user_id),
        client_id=mask_client_id(matching_token.client_id),
        scope=matching_token.scope
    )

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token_plain,
        "token_type": "Bearer",
        "expires_in": settings.OAUTH_TOKEN_EXPIRY_SECONDS,
        "scope": scope_str  # Return as space-separated string (OAuth 2.0 standard)
    }
