"""
Google OAuth token management.

Provides reusable token refresh logic for Google OAuth tokens.
Shared between Focused and Priority Guardian apps.

Concurrency: Uses per-user asyncio.Lock to prevent redundant refresh
API calls when multiple coroutines detect an expired token simultaneously.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.encryption import decrypt_token, encrypt_token
from backend.core.google_calendar import refresh_access_token
from backend.core.models import CoreConnection

logger = logging.getLogger(__name__)

# =============================================================================
# Lock eviction constants (see ADR-002)
# =============================================================================
LOCK_TTL_SECONDS = 1800  # 30 minutes - stale if unused longer than this
MAX_LOCK_ENTRIES = 10000  # Hard cap on lock dict size
EVICTION_TARGET_RATIO = 0.8  # Evict down to 80% of max on hard cap

# Type alias for lock entry: (lock, last_used_monotonic_timestamp)
LockEntry = tuple[asyncio.Lock, float]

# Per-user locks for token refresh. Prevents concurrent refresh calls
# for the same user from making redundant Google API calls.
# NOTE: Only protects within a single process. If scaling to multiple
# workers/containers, upgrade to Redis distributed lock.
_user_refresh_locks: dict[str, LockEntry] = {}


def _evict_stale_locks() -> None:
    """
    Evict stale lock entries to keep dict bounded.

    Called only when inserting a new key at or above MAX_LOCK_ENTRIES.
    Must be synchronous (no await) to prevent task-switching mid-mutation.

    Eviction strategy:
    1. TTL pass: Remove entries older than LOCK_TTL_SECONDS with unheld locks
    2. Hard cap pass: If still at capacity, evict oldest unheld entries
       down to EVICTION_TARGET_RATIO of max
    """
    now = time.monotonic()

    # -------------------------------------------------------------------------
    # Pass 1: TTL-based eviction (remove stale unheld locks)
    # -------------------------------------------------------------------------
    # Snapshot keys to avoid mutating dict during iteration
    stale_keys = []
    for user_key, (lock, last_used) in list(_user_refresh_locks.items()):
        age = now - last_used
        if age > LOCK_TTL_SECONDS and not lock.locked():
            stale_keys.append(user_key)

    for key in stale_keys:
        del _user_refresh_locks[key]

    if stale_keys:
        logger.debug(f"Evicted {len(stale_keys)} stale lock entries (TTL pass)")

    # -------------------------------------------------------------------------
    # Pass 2: Hard cap eviction (if still at capacity)
    # -------------------------------------------------------------------------
    if len(_user_refresh_locks) < MAX_LOCK_ENTRIES:
        return  # TTL pass was sufficient

    # Build list of unheld entries sorted by last_used (oldest first)
    evictable = [
        (user_key, last_used)
        for user_key, (lock, last_used) in _user_refresh_locks.items()
        if not lock.locked()
    ]
    evictable.sort(key=lambda x: x[1])  # Sort by last_used ascending

    # Evict until we reach target ratio or run out of evictable entries
    target_size = int(MAX_LOCK_ENTRIES * EVICTION_TARGET_RATIO)
    evicted_count = 0

    for user_key, _ in evictable:
        if len(_user_refresh_locks) <= target_size:
            break
        # Re-check lock is still unheld (defensive)
        entry = _user_refresh_locks.get(user_key)
        if entry and not entry[0].locked():
            del _user_refresh_locks[user_key]
            evicted_count += 1

    if evicted_count:
        logger.debug(f"Evicted {evicted_count} lock entries (hard cap pass)")


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
    # Get or create per-user lock (with TTL-based eviction)
    # -----------------------------------------------------------
    user_key = str(connection.user_id)
    now = time.monotonic()

    entry = _user_refresh_locks.get(user_key)
    if entry is not None:
        # Existing entry: update timestamp, reuse lock
        lock, _ = entry
        _user_refresh_locks[user_key] = (lock, now)
    else:
        # New entry: run eviction if at capacity, then insert
        if len(_user_refresh_locks) >= MAX_LOCK_ENTRIES:
            _evict_stale_locks()

        if len(_user_refresh_locks) >= MAX_LOCK_ENTRIES:
            # Eviction couldn't free space - use local lock (not stored)
            # User loses cross-coroutine dedup for this call only
            lock = asyncio.Lock()
            logger.debug(f"Lock dict at capacity, using local lock for user {user_key}")
        else:
            lock = asyncio.Lock()
            _user_refresh_locks[user_key] = (lock, now)

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
