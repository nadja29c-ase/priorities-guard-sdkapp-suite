"""
Repository for Google OAuth connection persistence.

This layer handles only database operations. No business logic.
Receives pre-encrypted values from service layer.
"""

from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.models import CoreConnection


async def upsert_google_connection(
    user_id: str,
    encrypted_access_token: str,
    encrypted_refresh_token: str | None,
    token_expires_at: datetime,
    scopes: list[str],
    session: AsyncSession,
) -> None:
    """
    Upsert a Google OAuth connection for a user.

    Creates a new connection or updates an existing one.
    Clears revoked_at on reconnect to re-enable the connection.

    Args:
        user_id: The user's UUID (as string)
        encrypted_access_token: Pre-encrypted access token
        encrypted_refresh_token: Pre-encrypted refresh token (optional)
        token_expires_at: Token expiration timestamp
        scopes: List of authorized scopes
        session: Database session

    Returns:
        None
    """
    stmt = insert(CoreConnection).values(
        user_id=user_id,
        provider="google",
        connection_type="google",  # Required by CHECK constraint
        encrypted_access_token=encrypted_access_token,
        encrypted_refresh_token=encrypted_refresh_token,
        token_expires_at=token_expires_at,
        scopes=scopes,
        revoked_at=None,  # Explicitly not revoked on new connection
    )

    stmt = stmt.on_conflict_do_update(
        constraint="uq_user_provider",
        set_={
            "encrypted_access_token": encrypted_access_token,
            "encrypted_refresh_token": encrypted_refresh_token,
            "token_expires_at": token_expires_at,
            "scopes": scopes,
            "updated_at": datetime.now(timezone.utc),
            "revoked_at": None,  # Clear revocation on reconnect
            "connection_type": "google",  # Ensure correct type on update
        },
    )

    await session.execute(stmt)
    await session.commit()
