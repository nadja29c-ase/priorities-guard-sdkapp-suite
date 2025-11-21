"""
Rate limiting for OAuth endpoints using Redis (Increment 7B + 7C).

Implements sliding window rate limiting to prevent abuse with structured logging.
"""

from typing import Optional

from fastapi import HTTPException, Request
from backend.core.logging import get_logger
from backend.core.redis_client import redis_client

logger = get_logger(__name__)


class RateLimitExceeded(HTTPException):
    """Raised when rate limit is exceeded."""

    def __init__(self, retry_after: int):
        super().__init__(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)}
        )


async def check_rate_limit(
    key: str,
    limit: int,
    window: int = 60,
    request: Request = None
) -> None:
    """
    Check rate limit using Redis counter with structured logging.

    Implements a sliding window rate limiter:
    - Increments counter for the key
    - Sets TTL on first request
    - Raises RateLimitExceeded if limit exceeded
    - Logs violations with correlation ID

    Args:
        key: Redis key for rate limiting (e.g., "ratelimit:oauth:token:client-123:192.168.1.1")
        limit: Maximum number of requests allowed in window
        window: Time window in seconds (default: 60)
        request: FastAPI request (for correlation_id extraction)

    Raises:
        RateLimitExceeded: If rate limit is exceeded
    """
    # Extract correlation_id if request provided
    correlation_id = getattr(request.state, 'correlation_id', 'system') if request else 'system'
    request_logger = logger.bind(correlation_id=correlation_id)

    # Check if Redis is available
    if not redis_client.is_connected():
        request_logger.warning(
            "rate_limit.bypassed",
            reason="redis_unavailable",
            key_pattern=key.split(":")[0]
        )
        return

    try:
        # Increment counter
        count = await redis_client.incr(key)

        # Set TTL on first request
        if count == 1:
            await redis_client._client.expire(key, window)

        # Check if limit exceeded
        if count > limit:
            # Extract key pattern (don't log full key with IP)
            key_parts = key.split(":")
            key_pattern = ":".join(key_parts[:3]) if len(key_parts) >= 3 else key_parts[0]

            request_logger.warning(
                "rate_limit.exceeded",
                key_pattern=key_pattern,
                count=count,
                limit=limit,
                window=window
            )
            raise RateLimitExceeded(retry_after=window)

    except RateLimitExceeded:
        raise
    except Exception as e:
        # Log error but don't block request if Redis fails
        request_logger.error(
            "rate_limit.error",
            error=str(e)
        )


def get_client_ip(request: Request) -> str:
    """
    Extract client IP address from request.

    Handles X-Forwarded-For header for proxied requests.

    Args:
        request: FastAPI request object

    Returns:
        Client IP address
    """
    # Check X-Forwarded-For header (for proxied requests)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take first IP in chain
        return forwarded_for.split(",")[0].strip()

    # Fallback to direct client IP
    return request.client.host if request.client else "unknown"


async def rate_limit_authorize(request: Request) -> None:
    """
    Rate limit /authorize endpoint: 20 requests per minute per IP.

    Args:
        request: FastAPI request object

    Raises:
        RateLimitExceeded: If rate limit exceeded
    """
    ip = get_client_ip(request)
    key = f"ratelimit:oauth:authorize:{ip}"
    await check_rate_limit(key, limit=20, window=60, request=request)


async def rate_limit_token(request: Request, client_id: str) -> None:
    """
    Rate limit /token endpoint: 5 requests per minute per client+IP.

    Args:
        request: FastAPI request object
        client_id: OAuth client ID

    Raises:
        RateLimitExceeded: If rate limit exceeded
    """
    ip = get_client_ip(request)
    key = f"ratelimit:oauth:token:{client_id}:{ip}"
    await check_rate_limit(key, limit=5, window=60, request=request)


async def rate_limit_revoke(request: Request, client_id: str) -> None:
    """
    Rate limit /revoke endpoint: 10 requests per minute per client+IP.

    Args:
        request: FastAPI request object
        client_id: OAuth client ID

    Raises:
        RateLimitExceeded: If rate limit exceeded
    """
    ip = get_client_ip(request)
    key = f"ratelimit:oauth:revoke:{client_id}:{ip}"
    await check_rate_limit(key, limit=10, window=60, request=request)


async def rate_limit_register(request: Request) -> None:
    """
    Rate limit /register endpoint: 10 requests per minute per IP.

    Args:
        request: FastAPI request object

    Raises:
        RateLimitExceeded: If rate limit exceeded
    """
    ip = get_client_ip(request)
    key = f"ratelimit:oauth:register:{ip}"
    await check_rate_limit(key, limit=10, window=60, request=request)
