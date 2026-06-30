"""
Authorization Service - OAuth 2.1 authorization context management.

Handles authorization context storage and retrieval in Redis.
"""

import json
import time
from uuid import uuid4

from backend.core.logging import get_logger, mask_client_id
from backend.core.redis_client import redis_client

logger = get_logger(__name__)

AUTH_CONTEXT_TTL = 600  # 10 minutes
AUTH_CONTEXT_KEY_PREFIX = "oauth:auth:"
AUTH_CONTEXT_SCHEMA_VERSION = 1  # Increment when context structure changes


def build_auth_context_key(auth_context_id: str) -> str:
    """Build Redis key for authorization context."""
    return f"{AUTH_CONTEXT_KEY_PREFIX}{auth_context_id}"


async def create_authorization_context(
    client_id: str,
    client_name: str,
    code_challenge: str,
    code_challenge_method: str,
    scope: str,
    redirect_uri: str,
    user_id: str,
    state: str | None = None,
    nonce: str | None = None,
    resource: str | None = None,
    app_name: str | None = None,  # v2: threaded for consent_ui.py to reuse
    correlation_id: str | None = None
) -> str:
    """
    Create authorization context in Redis.

    Stores temporary authorization state while user reviews consent screen.
    Context expires after 10 minutes.

    Args:
        client_id: OAuth client identifier
        client_name: Human-readable client name
        code_challenge: PKCE code challenge
        code_challenge_method: PKCE method (always S256)
        scope: Space-separated scopes
        redirect_uri: Client's redirect URI
        user_id: Authenticated user ID
        state: Optional CSRF token
        nonce: Optional OpenID Connect nonce
        resource: Optional resource parameter (RFC 9728 B2-5)
        app_name: Optional resolved app name (v2: threaded to consent_ui.py)
        correlation_id: Optional correlation ID for logging

    Returns:
        str: Authorization context ID (UUID)

    Note:
        The app_name field is additive (v2 inc_consent_template_fallthrough_guard).
        Schema version is NOT bumped because:
        - Old contexts (no app_name) are handled by consent_ui.py fallback
        - New contexts (with app_name) are ignored by old consent_ui.py code
        Both rolling-deploy directions are safe.

    Example:
        >>> auth_context_id = await create_authorization_context(
        ...     "focused-client-123", "My App", "abc123...", "S256",
        ...     "focused.read focused.write", "https://example.com/callback",
        ...     "user-456", state="xyz", correlation_id="req-789"
        ... )
        >>> print(auth_context_id)
        12345678-1234-1234-1234-123456789abc
    """
    # Generate unique context ID
    auth_context_id = str(uuid4())

    # Build authorization context
    auth_context = {
        "v": AUTH_CONTEXT_SCHEMA_VERSION,  # Schema version for future migrations (NOT bumped for app_name - additive)
        "client_id": client_id,
        "client_name": client_name,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "scope": scope,
        "state": state,
        "nonce": nonce,
        "resource": resource,  # RFC 9728 B2-5
        "redirect_uri": redirect_uri,
        "user_id": user_id,
        "app_name": app_name,  # v2: may be None for old deploys, consent_ui.py falls back
        "expires_at": int(time.time()) + AUTH_CONTEXT_TTL
    }

    # Store in Redis with 10-minute TTL
    redis_key = build_auth_context_key(auth_context_id)
    await redis_client.set(
        redis_key,
        json.dumps(auth_context),
        ex=AUTH_CONTEXT_TTL
    )

    # Log context creation
    request_logger = logger.bind(correlation_id=correlation_id) if correlation_id else logger
    request_logger.info(
        "oauth.auth.context_created",
        auth_context_id=auth_context_id,
        client_id=mask_client_id(client_id),
        user_id=user_id,
        scope=scope
    )

    return auth_context_id


async def get_authorization_context(
    auth_context_id: str,
    delete_after_read: bool = True
) -> dict | None:
    """
    Retrieve authorization context from Redis.

    Args:
        auth_context_id: Authorization context ID
        delete_after_read: If True, delete context after reading (single-use)

    Returns:
        dict: Authorization context or None if not found/expired

    Example:
        >>> context = await get_authorization_context("12345678-...")
        >>> print(context["client_id"])
        focused-client-123
    """
    redis_key = build_auth_context_key(auth_context_id)
    auth_context_json = await redis_client.get(redis_key)

    if not auth_context_json:
        return None

    # Delete context after reading (single-use)
    if delete_after_read:
        await redis_client.delete(redis_key)

    return json.loads(auth_context_json)
