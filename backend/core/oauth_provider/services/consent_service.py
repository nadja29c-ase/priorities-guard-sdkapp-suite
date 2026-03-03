"""
Consent Service - OAuth 2.1 user consent handling.

Handles authorization code generation, consent persistence, and storage.
"""

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from backend.core.logging import get_logger, mask_client_id
from backend.core.models import CoreConsent
from backend.core.oauth_provider.models import OAuthAuthorizationCode

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

    Important:
        Caller MUST delete the Redis authorization context after calling this function.
        The context is single-use and must not be replayable.

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
    # NOTE: nonce parameter accepted for backward compatibility but not stored
    # (OpenID Connect is not implemented; column was dropped for data minimization)
    auth_code_record = OAuthAuthorizationCode(
        code=authorization_code,
        user_id=UUID(user_id),
        client_id=client_id,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        redirect_uri=redirect_uri,
        scope=scope.split(),  # Convert space-separated string to array
        state=state,
        expires_at=expires_at,
        used=False
    )

    try:
        db.add(auth_code_record)
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    # Log code creation (no secrets logged)
    request_logger = logger.bind(correlation_id=correlation_id) if correlation_id else logger
    request_logger.info(
        "oauth.consent.allowed",
        user_id=user_id,
        client_id=mask_client_id(client_id),
        scope=scope
    )

    return authorization_code


async def record_consent(
    db: AsyncSession,
    user_id: str,
    app_name: str,
    scopes: list[str],
    correlation_id: str | None = None
) -> None:
    """
    Record user consent for scopes (GDPR compliance).

    Creates or updates consent records for each scope.
    Uses upsert to handle re-consent after revocation:
    - If consent exists and is active: no-op (idempotent)
    - If consent exists but was revoked: clears revoked_at, updates granted_at
    - If consent doesn't exist: creates new record

    Args:
        db: Database session
        user_id: User UUID as string
        app_name: SDK app name (e.g., "focused")
        scopes: List of scopes consented to
        correlation_id: For logging

    Example:
        >>> await record_consent(
        ...     db=db,
        ...     user_id="550e8400-e29b-41d4-a716-446655440000",
        ...     app_name="focused",
        ...     scopes=["focused.read", "focused.write"]
        ... )
    """
    request_logger = logger.bind(correlation_id=correlation_id) if correlation_id else logger
    user_uuid = UUID(user_id)
    now = datetime.now(timezone.utc)

    for scope in scopes:
        # PostgreSQL upsert: INSERT ... ON CONFLICT DO UPDATE
        stmt = insert(CoreConsent).values(
            user_id=user_uuid,
            app_name=app_name,
            scope=scope,
            granted_at=now,
            revoked_at=None
        ).on_conflict_do_update(
            constraint="uq_user_app_scope",
            set_={
                "granted_at": now,
                "revoked_at": None
            }
        )

        await db.execute(stmt)

    await db.commit()

    request_logger.info(
        "oauth.consent.recorded",
        user_id=user_id,
        app_name=app_name,
        scopes=scopes
    )
