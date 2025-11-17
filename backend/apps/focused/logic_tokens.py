"""
Token management for Focused app.

Provides reusable token refresh logic for Google OAuth tokens.
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.encryption import decrypt_token, encrypt_token
from backend.core.google_calendar import refresh_access_token
from backend.core.models import CoreConnection

logger = logging.getLogger(__name__)


async def ensure_valid_access_token(
    connection: CoreConnection,
    session: AsyncSession,
    http_client: httpx.AsyncClient,
) -> dict[str, str]:
    """
    Ensure the user's access token is valid and fresh.

    Checks token expiration and auto-refreshes if needed.
    Updates the connection object and database in place.

    Args:
        connection: User's Google connection from database
        session: Database session for committing updates
        http_client: HTTP client for API calls

    Returns:
        Success dict: {"access_token": "decrypted_token"}
        Error dict: {"error": "ERROR_CODE"}

    Error codes:
        - TOKEN_REFRESH_FAILED: Generic refresh failure
        - REFRESH_TOKEN_INVALID: Refresh token is invalid/revoked
        - API_QUOTA_EXCEEDED: Google API quota exceeded
        - TOKEN_DECRYPTION_FAILED: Failed to decrypt token
    """
    now = datetime.now(timezone.utc)

    # -----------------------------------------------------------
    # Check if token needs refresh
    # -----------------------------------------------------------
    if not connection.token_expires_at or connection.token_expires_at <= now:
        logger.info(f"Access token expired for user {connection.user_id}, refreshing")

        # Decrypt refresh token
        try:
            refresh_token_decrypted = decrypt_token(connection.encrypted_refresh_token)
        except Exception as e:
            logger.error(f"Failed to decrypt refresh token: {e}")
            return {"error": "TOKEN_REFRESH_FAILED"}

        # Call Google refresh API
        try:
            result = await refresh_access_token(http_client, refresh_token_decrypted)
        except ValueError as e:
            if str(e) == "Refresh token invalid":
                return {"error": "REFRESH_TOKEN_INVALID"}
            if str(e) == "API quota exceeded":
                return {"error": "API_QUOTA_EXCEEDED"}
            return {"error": "TOKEN_REFRESH_FAILED"}
        except Exception:
            return {"error": "TOKEN_REFRESH_FAILED"}

        # Extract new token and expiration
        new_access_token = result["access_token"]
        expires_in = result["expires_in"]

        # Update database
        connection.encrypted_access_token = encrypt_token(new_access_token)
        connection.token_expires_at = now + timedelta(seconds=expires_in)
        connection.updated_at = now
        await session.commit()

        logger.info(f"Access token refreshed for user {connection.user_id}")

        # Return decrypted token
        return {"access_token": new_access_token}

    # -----------------------------------------------------------
    # Token is still valid, just decrypt it
    # -----------------------------------------------------------
    try:
        access_token = decrypt_token(connection.encrypted_access_token)
        return {"access_token": access_token}
    except Exception as e:
        logger.error(f"Failed to decrypt access token: {e}")
        return {"error": "TOKEN_DECRYPTION_FAILED"}
