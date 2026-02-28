"""
Google OAuth token management.

Provides reusable token refresh logic for Google OAuth tokens.
Shared between Focused and Priority Guardian apps.

Concurrency: Uses per-user asyncio.Lock to prevent redundant refresh
API calls when multiple coroutines detect an expired token simultaneously.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.encryption import decrypt_token, encrypt_token
from backend.core.google_calendar import refresh_access_token
from backend.core.models import CoreConnection

logger = logging.getLogger(__name__)

# Per-user locks for token refresh. Prevents concurrent refresh calls
# for the same user from making redundant Google API calls.
# NOTE: Only protects within a single process. If scaling to multiple
# workers/containers, upgrade to Redis distributed lock.
_user_refresh_locks: dict[str, asyncio.Lock] = {}


async def ensure_valid_access_token(
    connection: CoreConnection,
    session: AsyncSession,
    http_client: httpx.AsyncClient,
) -> dict[str, str]:
    """
    Ensure the user's access token is valid and fresh.

    Checks token expiration and auto-refreshes if needed.
    Updates the connection object and database in place.

    Concurrency: Uses per-user lock to prevent redundant refresh API calls.
    When multiple coroutines detect an expired token for the same user,
    only the first performs the refresh; others wait and reuse the result.

    Args:
        connection: User's Google connection from database
        session: Database session for committing updates
        http_client: HTTP client for API calls

    Returns:
        Success dict: {"access_token": "decrypted_token"}
        Error dict: {"error": "ERROR_CODE"}

    Error codes:
        - TOKEN_DECRYPTION_FAILED: Failed to decrypt refresh or access token
        - TOKEN_REFRESH_FAILED: Google token refresh API call failed
        - REFRESH_TOKEN_INVALID: Refresh token is invalid/revoked
        - API_QUOTA_EXCEEDED: Google API quota exceeded
    """
    # -----------------------------------------------------------
    # Get or create per-user lock
    # -----------------------------------------------------------
    user_key = str(connection.user_id)

    # Size-based eviction: clear all locks if dict grows too large
    # This is safe because recreating a lock just means one potential
    # redundant refresh - acceptable trade-off for simplicity
    if len(_user_refresh_locks) > 10000:
        _user_refresh_locks.clear()
        logger.debug("Cleared user refresh locks (size limit exceeded)")

    # Get-then-set pattern (NOT setdefault to avoid allocating throwaway Lock)
    lock = _user_refresh_locks.get(user_key)
    if lock is None:
        lock = asyncio.Lock()
        _user_refresh_locks[user_key] = lock

    # -----------------------------------------------------------
    # Acquire lock and check/refresh token
    # -----------------------------------------------------------
    async with lock:
        # Refresh connection from database to get latest state
        # (another coroutine may have already refreshed the token)
        await session.refresh(connection)

        now = datetime.now(timezone.utc)

        # -----------------------------------------------------------
        # Check if token needs refresh (re-check after acquiring lock)
        # -----------------------------------------------------------
        if not connection.token_expires_at or connection.token_expires_at <= now:
            logger.info(f"Access token expired for user {connection.user_id}, refreshing")

            # Decrypt refresh token
            try:
                refresh_token_decrypted = decrypt_token(connection.encrypted_refresh_token)
            except Exception as e:
                logger.error(f"Failed to decrypt refresh token for user {connection.user_id}: {e}")
                return {"error": "TOKEN_DECRYPTION_FAILED"}

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

            # Recompute now AFTER refresh (API call + retries can take several seconds)
            now = datetime.now(timezone.utc)

            # Update database
            connection.encrypted_access_token = encrypt_token(new_access_token)
            connection.token_expires_at = now + timedelta(seconds=expires_in)
            connection.updated_at = now
            await session.commit()

            logger.info(f"Access token refreshed for user {connection.user_id}")

            # Return decrypted token
            return {"access_token": new_access_token}

        # -----------------------------------------------------------
        # Token is still valid (possibly refreshed by another coroutine)
        # -----------------------------------------------------------
        try:
            access_token = decrypt_token(connection.encrypted_access_token)
            return {"access_token": access_token}
        except Exception as e:
            logger.error(f"Failed to decrypt access token for user {connection.user_id}: {e}")
            return {"error": "TOKEN_DECRYPTION_FAILED"}
