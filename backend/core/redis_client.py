"""
Redis client for caching, idempotency, and throttling.

"Caching" here means:
- storing short-lived values
- making reads/writes extremely fast
- avoiding hitting the database for trivial checks

Idempotency:
Redis stores a key that marks a webhook message as "seen". This prevents double-processing.

Throttling = limiting how often a certain action can run, to prevent spam.

Environment Namespacing:
All Redis keys are automatically prefixed with the environment (dev/staging/prod).
This prevents key collisions when multiple environments share the same Redis instance.
Example: "focused:webhook:user123" becomes "dev:focused:webhook:user123"

Uses RDB persistence for data durability. Redis keeps all keys in memory.
Every X seconds or after Y writes, Redis dumps the entire dataset to disk as a .rdb file.
"""

import logging
from typing import Optional, Any
import redis.asyncio as redis

from backend.core.config import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Async Redis client for caching and queues."""

    def __init__(self):
        """Initialize Redis client (connection created on connect())."""
        self._client: Optional[redis.Redis] = None
        # Environment prefix for key namespacing (dev/staging/prod isolation)
        self._env_prefix = f"{settings.ENV}:"

    def _prefix_key(self, key: str) -> str:
        """
        Add environment prefix to key for namespace isolation.

        Args:
            key: Original key (e.g., "focused:webhook:user123")

        Returns:
            Prefixed key (e.g., "dev:focused:webhook:user123")

        This prevents key collisions when dev/staging/prod share the same Redis instance.
        """
        return f"{self._env_prefix}{key}"

    async def connect(self):
        """Initialize Redis connection pool.

        Raises RuntimeError on failure. Redis is load-bearing for OAuth security
        (rate limiting, authorization context, token replay prevention) — the app
        MUST NOT serve requests without it. Runtime callers that observe temporary
        Redis unavailability (via is_connected()) still degrade gracefully; this
        change only affects the startup path.
        """
        try:
            self._client = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            await self._client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            self._client = None
            logger.error(f"Redis connection failed at startup: {e}")
            raise RuntimeError(
                "Redis connection failed at startup. Redis is required for OAuth "
                "rate limiting, authorization context storage, and token replay "
                "prevention. Refusing to serve requests without it."
            ) from e

    async def close(self):
        """Close Redis connections."""
        if self._client:
            await self._client.aclose()
            self._client = None  # Explicitly set to None after closing
            logger.info("Redis connection closed")

    def is_connected(self) -> bool:
        """
        Check if Redis is connected and usable.

        Returns:
            True if connected, False otherwise
        """
        return self._client is not None

    async def get(self, key: str) -> Optional[str]:
        """
        Get value by key.

        Args:
            key: Cache key (will be automatically prefixed with environment)

        Returns:
            Cached value or None
        """
        if not self.is_connected():
            logger.warning("Redis not connected, get() returning None")
            return None

        try:
            prefixed_key = self._prefix_key(key)
            return await self._client.get(prefixed_key)
        except Exception as e:
            logger.error(f"Redis get() failed for key {key}: {e}")
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ex: Optional[int] = None,
        nx: bool = False
    ) -> Optional[bool]:
        """
        Set key-value pair with optional expiry.

        Args:
            key: Cache key (will be automatically prefixed with environment)
            value: Value to cache
            ex: Expiry in seconds
            nx: Only set if key does not exist (for idempotency)

        Returns:
            True: Key was set successfully.
            None: Key was NOT set. Two causes:
                  (a) nx=True and key already exists (idempotency block), or
                  (b) Redis error (connection lost, timeout, etc.).
                  Callers must treat None as "operation failed" regardless of cause.
            False: Reserved for future redis-py compatibility; not currently returned.
        """
        if not self.is_connected():
            logger.warning("Redis not connected, set() returning None")
            return None

        try:
            prefixed_key = self._prefix_key(key)
            result = await self._client.set(prefixed_key, value, ex=ex, nx=nx)
            # When nx=True:
            #   - result is True if key was set (new)
            #   - result is None if key already exists
            # When nx=False:
            #   - result is True if key was set
            return result
        except Exception as e:
            logger.error(f"Redis set() failed for key {key}: {e}")
            return None

    async def delete(self, key: str) -> int:
        """
        Delete key from cache.

        Args:
            key: Cache key (will be automatically prefixed with environment)

        Returns:
            Number of keys deleted
        """
        if not self.is_connected():
            logger.warning("Redis not connected, delete() returning 0")
            return 0

        try:
            prefixed_key = self._prefix_key(key)
            return await self._client.delete(prefixed_key)
        except Exception as e:
            logger.error(f"Redis delete() failed for key {key}: {e}")
            return 0

    async def incr(self, key: str, amount: int = 1) -> Optional[int]:
        """
        Increment counter (for rate limiting).

        Args:
            key: Counter key (will be automatically prefixed with environment)
            amount: Increment amount

        Returns:
            New counter value or None on error
        """
        if not self.is_connected():
            logger.warning("Redis not connected, incr() returning None")
            return None

        try:
            prefixed_key = self._prefix_key(key)
            return await self._client.incrby(prefixed_key, amount)
        except Exception as e:
            logger.error(f"Redis incr() failed for key {key}: {e}")
            return None

    async def exists(self, key: str) -> int:
        """
        Check if key exists in Redis.

        Args:
            key: Cache key (will be automatically prefixed with environment)

        Returns:
            1 if key exists, 0 if not, 0 on error
        """
        if not self.is_connected():
            logger.warning("Redis not connected, exists() returning 0")
            return 0

        try:
            prefixed_key = self._prefix_key(key)
            return await self._client.exists(prefixed_key)
        except Exception as e:
            logger.error(f"Redis exists() failed for key {key}: {e}")
            return 0

    async def ttl(self, key: str) -> int:
        """
        Get TTL (time-to-live) of a key in seconds.

        Args:
            key: Cache key (will be automatically prefixed with environment)

        Returns:
            TTL in seconds, -2 if key doesn't exist, -1 if no expiry, -3 on error
        """
        if not self.is_connected():
            logger.warning("Redis not connected, ttl() returning -3")
            return -3

        try:
            prefixed_key = self._prefix_key(key)
            return await self._client.ttl(prefixed_key)
        except Exception as e:
            logger.error(f"Redis ttl() failed for key {key}: {e}")
            return -3


# Global Redis client instance
redis_client = RedisClient()


# -------------------------------------------------------------
# Webhook Idempotency and Throttling (Increment 5)
# -------------------------------------------------------------

async def check_webhook_idempotency(
    user_id: str,
    message_number: str,
    ttl_seconds: int = 86400  # 24 hours
) -> bool:
    """
    Check if webhook was already processed.

    Uses Redis SET with NX (only if not exists) for atomic check-and-set.

    Args:
        user_id: User ID
        message_number: Google webhook message number
        ttl_seconds: TTL for idempotency key (default 24 hours)

    Returns:
        True if this is a new webhook (not processed before)
        False if this webhook was already processed (duplicate)
    """
    # Check Redis connection BEFORE attempting operation
    if not redis_client.is_connected():
        logger.warning(f"[idempotency] Redis unavailable, allowing webhook: user={user_id}, msg={message_number}")
        return True  # Allow webhook if Redis is down

    key = f"focused:webhook:{user_id}:{message_number}"

    # Try to set the key with NX (only if not exists)
    result = await redis_client.set(key, "1", ex=ttl_seconds, nx=True)

    if result is None:
        # Redis is connected, so None means key already exists (duplicate)
        logger.info(f"[idempotency] Duplicate webhook: user={user_id}, msg={message_number}")
        return False
    elif result is True:
        # Key was set successfully (new webhook)
        return True
    else:
        # Unexpected case (Redis error during set)
        logger.error(f"[idempotency] Unexpected Redis result, allowing webhook: user={user_id}")
        return True


async def check_renewal_throttle(
    user_id: str,
    ttl_seconds: int = 86400  # 24 hours
) -> bool:
    """
    Check if renewal is allowed (not throttled).

    Sets a throttle key if renewal is allowed.
    Prevents multiple renewal attempts within the TTL window.

    Args:
        user_id: User ID
        ttl_seconds: TTL for throttle key (default 24 hours)

    Returns:
        True if renewal is allowed (throttle key was set)
        False if renewal is throttled (key already exists)
    """
    # Check Redis connection BEFORE attempting operation
    if not redis_client.is_connected():
        logger.warning(f"[throttle] Redis unavailable, allowing renewal: user={user_id}")
        return True  # Allow renewal if Redis is down

    key = f"focused:webhook:renew_throttle:{user_id}"

    # Try to set the key with NX (only if not exists)
    result = await redis_client.set(key, "1", ex=ttl_seconds, nx=True)

    if result is None:
        # Redis is connected, so None means key already exists (throttled)
        logger.info(f"[throttle] Renewal throttled: user={user_id}")
        return False
    elif result is True:
        # Key was set successfully (renewal allowed)
        return True
    else:
        # Unexpected case (Redis error during set)
        logger.error(f"[throttle] Unexpected Redis result, allowing renewal: user={user_id}")
        return True


async def set_needs_sync(
    user_id: str,
    ttl_seconds: int = 300  # 5 minutes
) -> bool:
    """
    Set needs_sync flag for a user.

    Indicates that the user's calendar has changed and needs to be synced.
    Future increments will consume this flag to pull updated events.

    Args:
        user_id: User ID
        ttl_seconds: TTL for needs_sync flag (default 5 minutes)

    Returns:
        True if flag was set successfully
        False if Redis error occurred
    """
    # Check Redis connection BEFORE attempting operation
    if not redis_client.is_connected():
        logger.warning(f"[needs_sync] Redis unavailable, flag not stored: user={user_id}")
        return False

    key = f"focused:needs_sync:{user_id}"

    try:
        # Set the flag (overwrite if exists, we don't need NX here)
        result = await redis_client.set(key, "true", ex=ttl_seconds)

        if result is None:
            logger.error(f"[needs_sync] Failed to set flag (Redis error): user={user_id}")
            return False

        return True
    except Exception as e:
        logger.error(f"[needs_sync] Exception setting flag for user {user_id}: {e}")
        return False


async def get_needs_sync(user_id: str) -> bool:
    """
    Check if needs_sync flag exists for a user.

    Used by Increment 6B to determine if calendar sync is required.

    Args:
        user_id: User ID

    Returns:
        True if sync is needed (flag exists)
        False if sync not needed or Redis unavailable
    """
    # Check Redis connection BEFORE attempting operation
    if not redis_client.is_connected():
        logger.warning(f"[needs_sync] Redis unavailable, assuming no sync needed: user={user_id}")
        return False

    key = f"focused:needs_sync:{user_id}"

    try:
        value = await redis_client.get(key)
        exists = value is not None

        if exists:
            logger.info(f"[needs_sync] Flag exists for user {user_id}, sync required")
        else:
            logger.debug(f"[needs_sync] No flag for user {user_id}, no sync needed")

        return exists
    except Exception as e:
        logger.error(f"[needs_sync] Exception checking flag for user {user_id}: {e}")
        return False


async def delete_needs_sync(user_id: str) -> bool:
    """
    Delete needs_sync flag for a user.

    Called after successful calendar sync to clear the flag.
    CRITICAL: Only call this if sync was 100% successful.

    Args:
        user_id: User ID

    Returns:
        True if flag was deleted successfully (or didn't exist)
        False if Redis error occurred
    """
    # Check Redis connection BEFORE attempting operation
    if not redis_client.is_connected():
        logger.warning(f"[needs_sync] Redis unavailable, cannot delete flag: user={user_id}")
        return False

    key = f"focused:needs_sync:{user_id}"

    try:
        deleted_count = await redis_client.delete(key)

        if deleted_count > 0:
            logger.info(f"[needs_sync] Flag deleted for user {user_id}")
        else:
            logger.debug(f"[needs_sync] No flag to delete for user {user_id}")

        return True
    except Exception as e:
        logger.error(f"[needs_sync] Exception deleting flag for user {user_id}: {e}")
        return False
