"""
Token Service - OAuth 2.1 token issuance and refresh.

The heart of the OAuth provider. Handles:
- Authorization code → token exchange
- Refresh token rotation
- Token storage and revocation
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.encryption import encrypt_token, decrypt_token, hash_refresh_token
from backend.core.logging import get_logger
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
    result = await db.execute(
        select(OAuthAuthorizationCode).where(
            OAuthAuthorizationCode.code == code
        )
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
        token_type="Bearer",
        expires_at=access_token_expires_at,
        refresh_token_enc=refresh_token_encrypted,
        refresh_token_hash=refresh_token_hashed,
        refresh_token_expires_at=refresh_token_expires_at,
        revoked=False,
        last_used_at=datetime.now(timezone.utc)
    )

    db.add(access_token_record)
    await db.commit()

    # Log success
    request_logger.info(
        "oauth.token.success",
        grant_type="authorization_code",
        jti=jti,
        user_id=str(auth_code.user_id),
        client_id=auth_code.client_id,
        scope=auth_code.scope
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token_plain,
        "token_type": "Bearer",
        "expires_in": settings.OAUTH_TOKEN_EXPIRY_SECONDS,
        "scope": auth_code.scope
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
    refresh_token_hashed = hash_refresh_token(refresh_token)
    result = await db.execute(
        select(OAuthAccessToken).where(
            OAuthAccessToken.refresh_token_hash == refresh_token_hashed
        )
    )
    matching_token = result.scalar_one_or_none()

    if not matching_token:
        return ("invalid_grant", "Invalid refresh token")

    # Validate not expired
    if not validate_token_not_expired(matching_token.refresh_token_expires_at):
        return ("invalid_grant", "Refresh token expired")

    # Validate not revoked
    if matching_token.revoked:
        return ("invalid_grant", "Refresh token revoked")

    # Validate client_id matches
    if not validate_client_id_match(matching_token.client_id, client_id):
        return ("invalid_grant", "client_id mismatch")

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
        token_type="Bearer",
        expires_at=new_access_token_expires_at,
        refresh_token_enc=new_refresh_token_encrypted,
        refresh_token_hash=new_refresh_token_hashed,
        refresh_token_expires_at=new_refresh_token_expires_at,
        revoked=False,
        last_used_at=datetime.now(timezone.utc)
    )

    db.add(new_access_token_record)
    await db.commit()

    # Log success
    request_logger.info(
        "oauth.token.success",
        grant_type="refresh_token",
        old_jti=matching_token.jti,
        new_jti=new_jti,
        user_id=str(matching_token.user_id),
        client_id=matching_token.client_id,
        scope=matching_token.scope
    )

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token_plain,
        "token_type": "Bearer",
        "expires_in": settings.OAUTH_TOKEN_EXPIRY_SECONDS,
        "scope": matching_token.scope
    }
