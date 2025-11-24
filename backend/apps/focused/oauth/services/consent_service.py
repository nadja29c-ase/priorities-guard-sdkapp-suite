"""
Consent Service - OAuth 2.1 user consent handling.

Handles authorization code generation and storage after user consent.
"""

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.logging import get_logger
from backend.core.oauth_models import OAuthAuthorizationCode

logger = get_logger(__name__)

AUTH_CODE_TTL_MINUTES = 10


async def create_authorization_code(
    db: AsyncSession,
    user_id: str,
    client_id: str,
    code_challenge: str,
    code_challenge_method: str,
    redirect_uri: str,
    scope: str,
    state: str | None = None,
    nonce: str | None = None,
    correlation_id: str | None = None
) -> str:
    """
    Generate and store authorization code in database.

    Creates a cryptographically secure authorization code that the client
    will exchange for access tokens. Code expires after 10 minutes.

    Args:
        db: Database session
        user_id: User who granted consent
        client_id: OAuth client identifier
        code_challenge: PKCE code challenge
        code_challenge_method: PKCE method (S256)
        redirect_uri: Client's redirect URI
        scope: Space-separated scopes
        state: Optional CSRF token
        nonce: Optional OpenID Connect nonce
        correlation_id: Optional correlation ID for logging

    Returns:
        str: Authorization code (128 characters, URL-safe base64)

    Security Notes:
        - Code is single-use only (marked as 'used' after token exchange)
        - Expires after 10 minutes
        - PKCE challenge stored for verification during token exchange
        - Code replay attacks prevented by 'used' flag

    Example:
        >>> code = await create_authorization_code(
        ...     db, "user-123", "focused-client-456", "abc...", "S256",
        ...     "https://example.com/callback", "focused.read focused.write"
        ... )
        >>> print(code)
        dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk...
    """
    # Generate cryptographically secure authorization code
    # 96 bytes -> 128 characters (base64url)
    authorization_code = secrets.token_urlsafe(96)

    # Calculate expiration (10 minutes from now)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=AUTH_CODE_TTL_MINUTES)

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

    # Log code creation (no secrets logged)
    request_logger = logger.bind(correlation_id=correlation_id) if correlation_id else logger
    request_logger.info(
        "oauth.consent.allowed",
        user_id=user_id,
        client_id=client_id,
        scope=scope
    )

    return authorization_code
