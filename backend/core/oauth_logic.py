"""
OAuth 2.1 token validation logic (Increment 7B).

Provides utilities for validating and verifying access tokens
used by MCP tools and API endpoints.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.oauth_models import OAuthAccessToken

logger = logging.getLogger(__name__)


class InvalidTokenError(HTTPException):
    """Raised when token validation fails."""

    def __init__(self, detail: str):
        super().__init__(status_code=401, detail=detail)


async def validate_access_token(jti: str, db: AsyncSession) -> OAuthAccessToken:
    """
    Validate access token by JTI.

    Checks:
    1. Token exists in database
    2. Token not expired
    3. Token not revoked

    Updates last_used_at timestamp on successful validation.

    Args:
        jti: JWT ID (unique token identifier)
        db: Database session

    Returns:
        OAuthAccessToken record if valid

    Raises:
        InvalidTokenError: If token is invalid, expired, or revoked
    """
    # Find token by JTI
    result = await db.execute(
        select(OAuthAccessToken).where(OAuthAccessToken.jti == jti)
    )
    token = result.scalar_one_or_none()

    if not token:
        logger.warning(f"Token validation failed: JTI not found (jti={jti})")
        raise InvalidTokenError("Token not found")

    # Check expiration
    if token.expires_at < datetime.now(timezone.utc):
        logger.warning(
            f"Token validation failed: Token expired "
            f"(jti={jti}, expires_at={token.expires_at})"
        )
        raise InvalidTokenError("Token expired")

    # Check revocation
    if token.revoked:
        logger.warning(
            f"Token validation failed: Token revoked "
            f"(jti={jti}, revoked_at={token.revoked_at})"
        )
        raise InvalidTokenError("Token revoked")

    # Update last_used_at timestamp
    token.last_used_at = datetime.now(timezone.utc)
    await db.commit()

    logger.debug(
        f"Token validated successfully: jti={jti}, "
        f"user_id={token.user_id}, client_id={token.client_id}"
    )

    return token


async def parse_and_validate_bearer_token(
    authorization: str,
    db: AsyncSession
) -> OAuthAccessToken:
    """
    Parse Bearer token from Authorization header and validate.

    Args:
        authorization: Authorization header value (e.g., "Bearer <token>")
        db: Database session

    Returns:
        OAuthAccessToken record if valid

    Raises:
        InvalidTokenError: If authorization header is invalid or token is invalid
    """
    from jose import jwt, JWTError

    # Parse Bearer token
    if not authorization.startswith("Bearer "):
        raise InvalidTokenError("Invalid Authorization header format")

    token = authorization.replace("Bearer ", "").strip()

    # Decode JWT (without signature verification, we just need JTI)
    try:
        decoded = jwt.get_unverified_claims(token)
        jti = decoded.get("jti")

        if not jti:
            raise InvalidTokenError("Token missing JTI claim")

    except JWTError as e:
        logger.warning(f"JWT decode failed: {e}")
        raise InvalidTokenError("Invalid JWT token")

    # Validate token in database
    return await validate_access_token(jti, db)


async def check_scope(token: OAuthAccessToken, required_scope: str) -> bool:
    """
    Check if token has required scope.

    Args:
        token: OAuth access token record
        required_scope: Required scope (e.g., "focused.write")

    Returns:
        True if token has required scope, False otherwise
    """
    token_scopes = set(token.scope.split())
    return required_scope in token_scopes
