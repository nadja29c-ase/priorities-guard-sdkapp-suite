"""
Google OAuth flow implementation.

Handles OAuth state management and token exchange using httpx.

This module does:
    - PKCE (Proof Key for Code Exchange) generation for enhanced security
    - OAuth state management via Redis (CSRF protection)
    - Token exchange with Google

This is your outbound Google OAuth client.

Security (Increment 11):
    - State stored in Redis with 10-minute TTL
    - State contains user_id and code_verifier (bound server-side)
    - PKCE S256 challenge sent to Google, verifier used in exchange
"""

import asyncio  # needed for retry sleeps
import base64
import hashlib
import json
import logging
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import httpx  # for async HTTP calls

from backend.core.config import settings  # my config, holds Google keys
from backend.core.redis_client import redis_client

logger = logging.getLogger(__name__)

# OAuth state TTL in seconds (10 minutes)
OAUTH_STATE_TTL = 600

# Connection token TTL in seconds (10 minutes) - Increment 18
CONNECTION_TOKEN_TTL = 600


# ============================================================================
# PKCE Functions (Increment 11)
# ============================================================================


def generate_code_verifier() -> str:
    """
    Generate a cryptographically secure code verifier for PKCE.

    Per RFC 7636:
    - Must be 43-128 characters
    - Must use unreserved characters: [A-Z], [a-z], [0-9], "-", ".", "_", "~"

    We use 64 bytes of random data, base64url encoded (86 chars).

    Returns:
        Code verifier string (86 characters)
    """
    # 64 bytes = 512 bits of entropy, base64url encoded = 86 chars
    random_bytes = os.urandom(64)
    verifier = base64.urlsafe_b64encode(random_bytes).decode("ascii").rstrip("=")
    return verifier


def generate_code_challenge(verifier: str) -> str:
    """
    Generate S256 code challenge from verifier.

    Per RFC 7636:
    code_challenge = BASE64URL(SHA256(code_verifier))

    Args:
        verifier: The code verifier string

    Returns:
        Base64url-encoded SHA256 hash (no padding)
    """
    # SHA256 hash of verifier bytes
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    # Base64url encode without padding
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return challenge


def generate_state_token() -> str:
    """
    Generate a cryptographically secure state token for CSRF protection.

    Returns:
        32-byte random string, hex encoded (64 characters)
    """
    return os.urandom(32).hex()


# ============================================================================
# Redis State Management (Increment 11)
# ============================================================================


async def store_oauth_state(
    state: str,
    user_id: str,
    code_verifier: str,
    correlation_id: str | None = None,
) -> bool:
    """
    Store OAuth state in Redis with user_id and code_verifier.

    State is bound to user_id server-side to prevent tampering.
    TTL is 10 minutes.

    Args:
        state: The state token (used as key)
        user_id: User ID initiating the OAuth flow
        code_verifier: PKCE code verifier for this flow
        correlation_id: Optional request correlation ID for tracing

    Returns:
        True if stored successfully, False otherwise
    """
    key = f"oauth:google:state:{state}"
    value = json.dumps({
        "user_id": user_id,
        "code_verifier": code_verifier,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    result = await redis_client.set(key, value, ex=OAUTH_STATE_TTL)

    log_extra = {"user_id": user_id}
    if correlation_id:
        log_extra["correlation_id"] = correlation_id

    if result:
        logger.info("[oauth] Stored state", extra=log_extra)
        return True
    else:
        logger.error("[oauth] Failed to store state", extra=log_extra)
        return False


async def verify_and_get_oauth_state(
    state: str,
    correlation_id: str | None = None,
) -> dict[str, Any] | None:
    """
    Verify OAuth state exists in Redis and retrieve associated data.

    State is deleted after retrieval (single-use).

    Args:
        state: The state token to verify
        correlation_id: Optional request correlation ID for tracing

    Returns:
        Dictionary with user_id and code_verifier if valid, None otherwise
    """
    key = f"oauth:google:state:{state}"

    # Get state data
    value = await redis_client.get(key)

    log_extra = {}
    if correlation_id:
        log_extra["correlation_id"] = correlation_id

    if value is None:
        logger.warning("[oauth] State verification failed: invalid or expired state", extra=log_extra)
        return None

    # Delete state (single-use)
    await redis_client.delete(key)

    try:
        data = json.loads(value)
        log_extra["user_id"] = data.get("user_id")
        logger.info("[oauth] State verified", extra=log_extra)
        return {
            "user_id": data["user_id"],
            "code_verifier": data["code_verifier"],
        }
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"[oauth] Failed to parse state data: {e}", extra=log_extra)
        return None


# ============================================================================
# OAuth Flow Functions (Increment 11 - with PKCE)
# ============================================================================


def generate_auth_url_with_pkce(code_challenge: str, state: str) -> str:
    """
    Generate Google OAuth authorization URL with PKCE.

    Builds the URL manually to include PKCE parameters.
    Does NOT use google_auth_oauthlib.flow.Flow (it doesn't support PKCE well).

    Args:
        code_challenge: The S256 code challenge
        state: The state token for CSRF protection

    Returns:
        Full authorization URL with all parameters
    """
    base_url = "https://accounts.google.com/o/oauth2/v2/auth"

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/calendar.readonly",
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }

    return f"{base_url}?{urlencode(params)}"


async def exchange_code(
    code: str,
    http_client: httpx.AsyncClient,
    code_verifier: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """
    Exchange authorization code for access and refresh tokens.

    CRITICAL: Uses httpx ONLY, never Flow.fetch_token() (not async-safe).

    Implements exponential backoff:
    - Max retries: 3
    - Base delay: 1 second
    - Jitter: random.uniform(0, 1)

    Args:
        code: Authorization code from OAuth callback
        http_client: Shared httpx AsyncClient from app state
        code_verifier: PKCE code verifier (required for PKCE flows)
        correlation_id: Optional request correlation ID for tracing

    Returns:
        Dictionary containing:
        - access_token: str
        - refresh_token: str | None
        - expires_in: int
        - scopes: list[str]

    Raises:
        ValueError: If token exchange fails after retries
    """
    token_url = "https://oauth2.googleapis.com/token"
    payload = {
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    # Add PKCE verifier if provided
    if code_verifier:
        payload["code_verifier"] = code_verifier

    log_extra = {}
    if correlation_id:
        log_extra["correlation_id"] = correlation_id

    max_retries = 3
    base_delay = 1.0

    for attempt in range(max_retries):
        try:
            response = await http_client.post(token_url, data=payload)
            response.raise_for_status()

            token_data = response.json()

            # Parse scopes from space-separated string
            scope_string = token_data.get("scope", "")
            scopes = scope_string.split() if scope_string else []

            # Validate required scope was granted
            # Google can return fewer scopes than requested - this breaks the app silently
            required_scope = "https://www.googleapis.com/auth/calendar.readonly"
            if required_scope not in scopes:
                logger.error(
                    f"Missing required Google scope: {required_scope}. "
                    f"Granted scopes: {scopes}",
                    extra=log_extra
                )
                raise ValueError(
                    f"Missing required Google scope: calendar.readonly. "
                    f"User must grant calendar access to use this app."
                )

            return {
                "access_token": token_data["access_token"],
                "refresh_token": token_data.get("refresh_token"),
                "expires_in": token_data.get("expires_in", 3600),
                "scopes": scopes,
            }

        except httpx.HTTPStatusError as e:
            logger.warning(
                f"Token exchange failed (attempt {attempt + 1}/{max_retries}): "
                f"HTTP {e.response.status_code}",
                extra=log_extra
            )
            if attempt == max_retries - 1:
                raise ValueError(f"Token exchange failed: {e.response.text}")

            # Exponential backoff with jitter
            delay = base_delay * (2**attempt) + random.uniform(0, 1)
            logger.info(f"Retrying in {delay:.2f} seconds...", extra=log_extra)
            await asyncio.sleep(delay)

        except Exception as e:
            logger.error(f"Token exchange failed unexpectedly: {e}", extra=log_extra)
            raise ValueError(f"Token exchange failed: {str(e)}")

    raise ValueError("Token exchange failed after maximum retries")


# ============================================================================
# Connection Token Functions (Increment 18)
# ============================================================================


async def store_connection_token(
    user_id: str,
    correlation_id: str | None = None,
) -> str:
    """
    Generate and store an opaque token for Google OAuth initiation.

    The token maps to user_id in Redis and expires after 10 minutes.
    Used to securely initiate Google OAuth without exposing user_id in URL.

    Security:
        - Token is cryptographically random (secrets.token_urlsafe)
        - Token stored in Redis with 10-minute TTL
        - Token deleted after first use (single-use)
        - user_id never exposed in browser URL

    Args:
        user_id: The user's internal ID (UUID string)
        correlation_id: Optional request correlation ID for tracing

    Returns:
        Opaque token string (43 characters, URL-safe)
    """
    import secrets

    # Type validation
    if not isinstance(user_id, str):
        raise TypeError(f"user_id must be a string, got {type(user_id).__name__}")

    if not user_id.strip():
        raise ValueError("user_id cannot be empty")

    token = secrets.token_urlsafe(32)
    redis_key = f"google_connect:{token}"

    result = await redis_client.set(redis_key, user_id, ex=CONNECTION_TOKEN_TTL)

    log_extra = {"user_id": user_id}
    if correlation_id:
        log_extra["correlation_id"] = correlation_id

    if not result:
        logger.error("[oauth] Failed to store connection token in Redis", extra=log_extra)
        raise RuntimeError("Failed to store connection token in Redis")

    logger.info("[oauth] Stored connection token", extra=log_extra)

    return token


async def verify_connection_token(
    token: str,
    correlation_id: str | None = None,
) -> str | None:
    """
    Verify and consume a connection token.

    Retrieves the user_id associated with the token and deletes the token
    (single-use). Returns None if token is invalid or expired.

    Security:
        - Single-use: token is deleted after retrieval
        - Never logs the full token (only prefix for debugging)
        - Rejects malformed tokens before Redis lookup

    Args:
        token: The opaque token from the URL
        correlation_id: Optional request correlation ID for tracing

    Returns:
        user_id if valid, None if invalid/expired
    """
    log_extra = {}
    if correlation_id:
        log_extra["correlation_id"] = correlation_id

    # Validate token format before Redis lookup
    # Reject: None, non-string, empty, whitespace, or tokens with leading/trailing whitespace
    if not token or not isinstance(token, str) or token.strip() != token:
        logger.warning(
            "[oauth] Connection token verification failed: malformed token",
            extra=log_extra
        )
        return None

    # Reject tokens with embedded whitespace, null bytes, or control characters
    # Valid tokens from secrets.token_urlsafe only contain: A-Za-z0-9-_
    if any(c.isspace() or ord(c) < 32 for c in token):
        logger.warning(
            "[oauth] Connection token verification failed: invalid characters",
            extra=log_extra
        )
        return None

    redis_key = f"google_connect:{token}"

    # Get token data
    user_id = await redis_client.get(redis_key)

    if user_id is None:
        log_extra["token_prefix"] = token[:8] if token else "none"
        logger.warning(
            "[oauth] Connection token verification failed: invalid or expired",
            extra=log_extra
        )
        return None

    # Delete token (single-use) - best effort, don't fail verification if delete fails
    try:
        await redis_client.delete(redis_key)
    except Exception as e:
        # Log but don't fail - verification succeeded, cleanup is secondary
        # Token will expire via TTL anyway
        log_extra["token_prefix"] = token[:8]
        logger.error(
            f"[oauth] Failed to delete connection token after verification: {e}",
            extra=log_extra
        )

    # Redis returns bytes, decode if necessary
    if isinstance(user_id, bytes):
        user_id = user_id.decode("utf-8")

    log_extra["user_id"] = user_id
    logger.info("[oauth] Connection token verified", extra=log_extra)

    return user_id


# ============================================================================
# Token Revocation (Increment 10)
# ============================================================================


async def revoke_google_token(
    refresh_token: str,
    http_client: httpx.AsyncClient,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """
    Revoke a Google OAuth refresh token.

    MUST use refresh_token (not access_token) to invalidate both tokens.
    Google's revocation endpoint accepts either, but revoking the refresh token
    ensures both access and refresh tokens are invalidated.

    Per Google docs: https://developers.google.com/identity/protocols/oauth2/web-server#tokenrevoke

    Args:
        refresh_token: The user's refresh token to revoke
        http_client: Shared httpx AsyncClient
        correlation_id: Optional request correlation ID for tracing

    Returns:
        Dictionary with:
        - success: bool
        - error: str | None (if failed)

    Note:
        - Returns success=True even if token was already revoked
        - Logs warning on failure but does not raise (non-blocking)
    """
    revoke_url = "https://oauth2.googleapis.com/revoke"

    log_extra = {}
    if correlation_id:
        log_extra["correlation_id"] = correlation_id

    try:
        response = await http_client.post(
            revoke_url,
            params={"token": refresh_token},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code == 200:
            logger.info("Google OAuth token revoked successfully", extra=log_extra)
            return {"success": True, "error": None}

        # Token may already be revoked or invalid - still considered success
        if response.status_code == 400:
            error_data = response.json() if response.content else {}
            error_type = error_data.get("error", "unknown")

            # "invalid_token" means token was already revoked or expired
            if error_type == "invalid_token":
                logger.info("Google OAuth token already revoked or expired", extra=log_extra)
                return {"success": True, "error": None}

            logger.warning(f"Google token revocation failed: {error_type}", extra=log_extra)
            return {"success": False, "error": error_type}

        logger.warning(
            f"Google token revocation unexpected status: {response.status_code}",
            extra=log_extra
        )
        return {"success": False, "error": f"HTTP {response.status_code}"}

    except Exception as e:
        logger.error(f"Google token revocation error: {e}", extra=log_extra)
        return {"success": False, "error": str(e)}
