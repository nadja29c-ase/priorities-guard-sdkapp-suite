"""
Revoke Service - OAuth 2.1 token revocation logic.

Handles:
- Access token revocation (JWT)
- Refresh token revocation (opaque)
- Grant-scoped revocation per RFC 7009: an access token and its refresh token share one
  row, so revoking either kills that grant. This is NOT cascade revocation across a
  user's other authorization grants — those are independent rows and are untouched.
- NOTE: revocation is immediate at the Authorization Server and has NO effect at the
  resource servers, which validate statelessly via JWKS until exp + leeway.
  See doc/ADR/ADR_006_token_revocation_semantics.md.
- Always returns success (no token existence leaking)
"""

from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from jose import jwt, JWTError

from backend.core.oauth_provider.models import OAuthAccessToken
from backend.core.encryption import decrypt_token, hash_refresh_token
from backend.core.logging import get_logger, mask_client_id

logger = get_logger(__name__)


async def revoke_token(
    db: AsyncSession,
    token: str,
    client_id: str,
    correlation_id: str
) -> tuple[bool, str | None]:
    """
    Revoke a token (access token or refresh token).

    Args:
        db: Database session
        token: Token to revoke (JWT or opaque string)
        client_id: OAuth client ID
        correlation_id: Request correlation ID for logging

    Returns:
        Tuple of (success, token_type) where:
        - success: Always True (per RFC 7009)
        - token_type: "access_token", "refresh_token", or None if not found

    Notes:
        Per RFC 7009, always returns success even if token doesn't exist
        to avoid leaking token existence information.
    """
    request_logger = logger.bind(correlation_id=correlation_id)

    # Try to parse as JWT (access token)
    token_type = await _try_revoke_access_token(
        db, token, client_id, request_logger
    )
    if token_type:
        return True, token_type

    # Try as refresh token (opaque)
    token_type = await _try_revoke_refresh_token(
        db, token, client_id, request_logger
    )
    if token_type:
        return True, token_type

    # Token not found or invalid - still return success per RFC 7009
    request_logger.debug("oauth.revoke.not_found")
    return True, None


async def _try_revoke_access_token(
    db: AsyncSession,
    token: str,
    client_id: str,
    request_logger
) -> str | None:
    """
    Try to revoke token as access token (JWT).

    Returns:
        "access_token" if revoked, None otherwise
    """
    try:
        # Decode JWT without verification (we just need the jti)
        decoded = jwt.get_unverified_claims(token)
        jti = decoded.get("jti")

        if not jti:
            return None

        # Find access token by JTI
        result = await db.execute(
            select(OAuthAccessToken).where(OAuthAccessToken.jti == jti)
        )
        token_record = result.scalar_one_or_none()

        if not token_record:
            return None

        # Verify client_id matches
        if token_record.client_id != client_id:
            return None

        # Revoke access token
        token_record.revoked = True
        token_record.revoked_at = datetime.now(timezone.utc)
        await db.commit()

        request_logger.info(
            "oauth.revoke.success",
            token_type="access_token",
            jti=jti,
            client_id=mask_client_id(client_id)
        )

        return "access_token"

    except JWTError:
        # Not a JWT, might be refresh token
        return None
    except Exception as e:
        request_logger.error(
            "oauth.revoke.error",
            error=str(e),
            token_type="access_token"
        )
        return None


async def _try_revoke_refresh_token(
    db: AsyncSession,
    token: str,
    client_id: str,
    request_logger
) -> str | None:
    """
    Try to revoke token as refresh token (opaque).

    Returns:
        "refresh_token" if revoked, None otherwise
    """
    try:
        # Find token by refresh_token hash (O(1) indexed lookup!)
        refresh_token_hashed = hash_refresh_token(token)
        result = await db.execute(
            select(OAuthAccessToken).where(
                OAuthAccessToken.refresh_token_hash == refresh_token_hashed
            )
        )
        token_record = result.scalar_one_or_none()

        if not token_record:
            return None

        # Verify client_id matches
        if token_record.client_id != client_id:
            return None

        # Revoke this token
        token_record.revoked = True
        token_record.revoked_at = datetime.now(timezone.utc)
        await db.commit()

        request_logger.info(
            "oauth.revoke.success",
            token_type="refresh_token",
            jti=token_record.jti,
            client_id=mask_client_id(client_id)
        )

        return "refresh_token"

    except Exception as e:
        request_logger.error(
            "oauth.revoke.error",
            error=str(e),
            token_type="refresh_token"
        )
        return None
