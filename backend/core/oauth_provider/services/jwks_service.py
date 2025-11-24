"""
JWKS Service - JSON Web Key Set caching and retrieval.

Handles JWKS caching in Redis with 24h TTL.
"""

import json
from backend.core.crypto import get_current_jwks
from backend.core.logging import get_logger
from backend.core.redis_client import redis_client

logger = get_logger(__name__)

JWKS_CACHE_KEY = "oauth:jwks:current"
JWKS_CACHE_TTL = 86400  # 24 hours


async def get_jwks() -> dict:
    """
    Get JWKS with Redis caching.

    Returns:
        dict: JWKS document with public keys for JWT verification

    Cache Strategy:
        - Check Redis cache first
        - If miss, generate from crypto module
        - Cache result with 24h TTL
    """
    # Check Redis cache
    try:
        if redis_client.is_connected():
            cached_jwks = await redis_client.get(JWKS_CACHE_KEY)
            if cached_jwks:
                logger.debug("Returning cached JWKS")
                return json.loads(cached_jwks)
    except Exception as e:
        logger.warning(f"Redis cache miss for JWKS: {e}")

    # Generate JWKS from public key
    jwks = get_current_jwks()

    # Cache in Redis (24h TTL)
    try:
        if redis_client.is_connected():
            await redis_client.set(
                JWKS_CACHE_KEY,
                json.dumps(jwks),
                ex=JWKS_CACHE_TTL
            )
            logger.debug("Cached JWKS in Redis")
    except Exception as e:
        logger.warning(f"Failed to cache JWKS: {e}")

    return jwks
