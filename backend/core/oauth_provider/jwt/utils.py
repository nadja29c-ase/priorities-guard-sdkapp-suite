"""
JWT token creation helpers for OAuth provider (Increment 7A).

Provides utilities for:
- Creating access tokens (signed JWTs)
- Creating refresh tokens (opaque random strings)
- Token expiration calculation
"""

import secrets
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from backend.core.config import settings
from backend.core.crypto import sign_jwt


def create_access_token(
    user_id: UUID,
    client_id: str,
    scope: str,
    expires_delta: timedelta | None = None
) -> tuple[str, str]:
    """
    Create a signed JWT access token.

    Args:
        user_id: User UUID
        client_id: OAuth client identifier
        scope: Space-separated scopes (e.g., "focused.read focused.write")
        expires_delta: Token expiration delta (default: 1 hour from config)

    Returns:
        Tuple of (access_token, jti)
        - access_token: Signed RS256 JWT
        - jti: JWT ID (for revocation tracking)

    JWT Claims:
        - sub: User ID (UUID as string)
        - aud: OAuth issuer (audience)
        - iss: OAuth issuer
        - exp: Expiration timestamp (Unix epoch)
        - iat: Issued-at timestamp (Unix epoch)
        - jti: JWT ID (unique identifier)
        - scope: Space-separated scopes
        - client_id: OAuth client identifier
    """
    # Calculate expiration
    if expires_delta is None:
        expires_delta = timedelta(seconds=settings.OAUTH_TOKEN_EXPIRY_SECONDS)

    now = datetime.now(timezone.utc)
    expires_at = now + expires_delta

    # Generate unique JTI
    jti = str(uuid4())

    # Build JWT payload
    payload = {
        "sub": str(user_id),
        "aud": settings.OAUTH_ISSUER,
        "iss": settings.OAUTH_ISSUER,
        "exp": int(expires_at.timestamp()),
        "iat": int(now.timestamp()),
        "jti": jti,
        "scope": scope,
        "client_id": client_id,
    }

    # Sign JWT with RS256
    access_token = sign_jwt(payload, kid=settings.OAUTH_JWT_KID)

    return (access_token, jti)


def create_refresh_token() -> str:
    """
    Generate cryptographically random refresh token.

    Returns:
        URL-safe base64-encoded random string (43 characters)

    Note:
        Refresh token is opaque (not a JWT).
        Must be stored encrypted in database.
        Used for token rotation (7B).
    """
    # Generate 32 random bytes as URL-safe base64 (no padding)
    refresh_token = secrets.token_urlsafe(32)

    return refresh_token


def calculate_refresh_token_expiry() -> datetime:
    """
    Calculate refresh token expiration timestamp.

    Returns:
        Expiration datetime (30 days from now, UTC)
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=settings.OAUTH_REFRESH_TOKEN_EXPIRY_DAYS)
    return expires_at
