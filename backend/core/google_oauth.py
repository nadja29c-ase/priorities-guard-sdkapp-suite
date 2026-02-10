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
import os
import random
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx  # for async HTTP calls

from backend.core.config import settings  # my config, holds Google keys
from backend.core.logging import get_logger
from backend.core.redis_client import redis_client

logger = get_logger(__name__)

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
    scope: str | None = None,
) -> bool:
    """
    Store OAuth state in Redis with user_id, code_verifier, and scope.

    State is bound to user_id server-side to prevent tampering.
    TTL is 10 minutes.

    Args:
        state: The state token (used as key)
        user_id: User ID initiating the OAuth flow
        code_verifier: PKCE code verifier for this flow
        correlation_id: Optional request correlation ID for tracing
        scope: Optional Google OAuth scope (for validation in callback)

    Returns:
        True if stored successfully, False otherwise
    """
    key = f"oauth:google:state:{state}"
    state_data = {
        "user_id": user_id,
        "code_verifier": code_verifier,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if scope:
        state_data["scope"] = scope
    value = json.dumps(state_data)

    result = await redis_client.set(key, value, ex=OAUTH_STATE_TTL)

    if result:
        logger.info("google_oauth.state_stored", user_id=user_id, correlation_id=correlation_id)
        return True
    else:
        logger.error("google_oauth.state_storage_failed", user_id=user_id, correlation_id=correlation_id)
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
        Dictionary with user_id, code_verifier, and scope if valid, None otherwise
    """
    key = f"oauth:google:state:{state}"

    # Get state data
    value = await redis_client.get(key)

    if value is None:
        logger.warning(
            "google_oauth.state_verification_failed",
            reason="invalid_or_expired",
            correlation_id=correlation_id
        )
        return None

    # Delete state (single-use)
    await redis_client.delete(key)

    try:
        data = json.loads(value)
        user_id = data["user_id"]
        logger.info("google_oauth.state_verified", user_id=user_id, correlation_id=correlation_id)
        return {
            "user_id": user_id,
            "code_verifier": data["code_verifier"],
            "scope": data.get("scope"),
        }
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(
            "google_oauth.state_parse_failed",
            error=str(e),
            correlation_id=correlation_id
        )
        return None


# ============================================================================
# OAuth Flow Functions (Increment 11 - with PKCE)
# ============================================================================


def generate_auth_url_with_pkce(code_challenge: str, state: str, scope: str) -> str:
    """
    Generate Google OAuth authorization URL with PKCE.

    Builds the URL manually to include PKCE parameters.
    Does NOT use google_auth_oauthlib.flow.Flow (it doesn't support PKCE well).

    Args:
        code_challenge: The S256 code challenge
        state: The state token for CSRF protection
        scope: The Google OAuth scope to request (e.g., calendar.readonly)

    Returns:
        Full authorization URL with all parameters
    """
    base_url = "https://accounts.google.com/o/oauth2/v2/auth"

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": scope,
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
    required_scope: str | None = None,
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
        required_scope: The scope that must be granted (app-specific)

    Returns:
        Dictionary containing:
        - access_token: str
        - refresh_token: str | None
        - expires_in: int
        - scopes: list[str]

    Raises:
        ValueError: If token exchange fails after retries or required scope not granted
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
            if required_scope and required_scope not in scopes:
                logger.error(
                    "google_oauth.token_exchange_missing_scope",
                    required_scope=required_scope,
                    granted_scopes=scopes,
                    correlation_id=correlation_id
                )
                # Extract short scope name for user-friendly message
                scope_short = required_scope.split("/")[-1] if "/" in required_scope else required_scope
                raise ValueError(
                    f"Missing required Google scope: {scope_short}. "
                    f"User must grant calendar access to use this app."
                )

            logger.info(
                "google_oauth.token_exchange_success",
                scopes=scopes,
                correlation_id=correlation_id
            )

            return {
                "access_token": token_data["access_token"],
                "refresh_token": token_data.get("refresh_token"),
                "expires_in": token_data.get("expires_in", 3600),
                "scopes": scopes,
            }

        except httpx.HTTPStatusError as e:
            # Parse Google's error response for better diagnostics
            error_type = "unknown"
            error_desc = ""
            try:
                error_data = e.response.json()
                error_type = error_data.get("error", "unknown")
                error_desc = error_data.get("error_description", "")
            except Exception:
                pass

            # Provide actionable guidance for common errors
            if error_type == "invalid_client":
                logger.error(
                    "google_oauth.token_exchange_failed",
                    google_error=error_type,
                    google_error_description=error_desc,
                    http_status=e.response.status_code,
                    attempt=attempt + 1,
                    max_attempts=max_retries,
                    action="Check GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables",
                    correlation_id=correlation_id
                )
            elif error_type == "invalid_grant":
                logger.warning(
                    "google_oauth.token_exchange_failed",
                    google_error=error_type,
                    google_error_description=error_desc,
                    http_status=e.response.status_code,
                    attempt=attempt + 1,
                    max_attempts=max_retries,
                    action="Authorization code expired or already used",
                    correlation_id=correlation_id
                )
            elif error_type == "redirect_uri_mismatch":
                logger.error(
                    "google_oauth.token_exchange_failed",
                    google_error=error_type,
                    google_error_description=error_desc,
                    http_status=e.response.status_code,
                    attempt=attempt + 1,
                    max_attempts=max_retries,
                    action="Check GOOGLE_REDIRECT_URI matches Google Cloud Console exactly",
                    correlation_id=correlation_id
                )
            else:
                logger.warning(
                    "google_oauth.token_exchange_failed",
                    google_error=error_type,
                    google_error_description=error_desc,
                    http_status=e.response.status_code,
                    attempt=attempt + 1,
                    max_attempts=max_retries,
                    correlation_id=correlation_id
                )

            if attempt == max_retries - 1:
                raise ValueError(
                    f"Token exchange failed: {error_type} - {error_desc}"
                )

            # Exponential backoff with jitter
            delay = base_delay * (2**attempt) + random.uniform(0, 1)
            logger.info(
                "google_oauth.token_exchange_retry",
                delay_seconds=round(delay, 2),
                attempt=attempt + 1,
                correlation_id=correlation_id
            )
            await asyncio.sleep(delay)

        except ValueError:
            # Re-raise ValueError (e.g., missing required scope) without wrapping
            raise

        except Exception as e:
            logger.error(
                "google_oauth.token_exchange_unexpected_error",
                error=str(e),
                correlation_id=correlation_id
            )
            raise ValueError(f"Token exchange failed: {str(e)}")

    raise ValueError("Token exchange failed after maximum retries")


# ============================================================================
# Connection Token Functions (Increment 18)
# ============================================================================


async def store_connection_token(
    user_id: str,
    correlation_id: str | None = None,
    scope: str | None = None,
) -> str:
    """
    Generate and store an opaque token for Google OAuth initiation.

    The token maps to user_id (and optionally scope) in Redis and expires
    after 10 minutes. Used to securely initiate Google OAuth without
    exposing user_id in URL.

    Security:
        - Token is cryptographically random (secrets.token_urlsafe)
        - Token stored in Redis with 10-minute TTL
        - Token deleted after first use (single-use)
        - user_id never exposed in browser URL

    Args:
        user_id: The user's internal ID (UUID string)
        correlation_id: Optional request correlation ID for tracing
        scope: Optional Google OAuth scope to request (app-specific)

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

    # Store user_id and scope as JSON if scope provided, otherwise just user_id
    # for backwards compatibility
    if scope:
        value = json.dumps({"user_id": user_id, "scope": scope})
    else:
        value = user_id

    result = await redis_client.set(redis_key, value, ex=CONNECTION_TOKEN_TTL)

    if not result:
        logger.error(
            "google_oauth.connection_token_storage_failed",
            user_id=user_id,
            correlation_id=correlation_id
        )
        raise RuntimeError("Failed to store connection token in Redis")

    logger.info(
        "google_oauth.connection_token_stored",
        user_id=user_id,
        has_scope=scope is not None,
        correlation_id=correlation_id
    )

    return token


async def verify_connection_token(
    token: str,
    correlation_id: str | None = None,
) -> dict[str, Any] | None:
    """
    Verify and consume a connection token.

    Retrieves the user_id and scope associated with the token and deletes
    the token (single-use). Returns None if token is invalid or expired.

    Security:
        - Single-use: token is deleted after retrieval
        - Never logs the full token (only prefix for debugging)
        - Rejects malformed tokens before Redis lookup

    Args:
        token: The opaque token from the URL
        correlation_id: Optional request correlation ID for tracing

    Returns:
        Dictionary with user_id and scope if valid, None if invalid/expired
    """
    # Validate token format before Redis lookup
    # Reject: None, non-string, empty, whitespace, or tokens with leading/trailing whitespace
    if not token or not isinstance(token, str) or token.strip() != token:
        logger.warning(
            "google_oauth.connection_token_verification_failed",
            reason="malformed_token",
            correlation_id=correlation_id
        )
        return None

    # Reject tokens with embedded whitespace, null bytes, or control characters
    # Valid tokens from secrets.token_urlsafe only contain: A-Za-z0-9-_
    if any(c.isspace() or ord(c) < 32 for c in token):
        logger.warning(
            "google_oauth.connection_token_verification_failed",
            reason="invalid_characters",
            correlation_id=correlation_id
        )
        return None

    redis_key = f"google_connect:{token}"

    # Get token data
    value = await redis_client.get(redis_key)

    if value is None:
        token_prefix = token[:8] if token else "none"
        logger.warning(
            "google_oauth.connection_token_verification_failed",
            reason="invalid_or_expired",
            token_prefix=token_prefix,
            correlation_id=correlation_id
        )
        return None

    # Delete token (single-use) - best effort, don't fail verification if delete fails
    try:
        await redis_client.delete(redis_key)
    except Exception as e:
        # Log but don't fail - verification succeeded, cleanup is secondary
        # Token will expire via TTL anyway
        logger.error(
            "google_oauth.connection_token_delete_failed",
            error=str(e),
            token_prefix=token[:8],
            correlation_id=correlation_id
        )

    # Redis returns bytes, decode if necessary
    if isinstance(value, bytes):
        value = value.decode("utf-8")

    # Parse value - could be plain user_id (legacy) or JSON with user_id and scope
    try:
        data = json.loads(value)
        user_id = data["user_id"]
        scope = data.get("scope")
    except (json.JSONDecodeError, KeyError, TypeError):
        # Legacy format: value is just user_id string
        user_id = value
        scope = None

    logger.info(
        "google_oauth.connection_token_verified",
        user_id=user_id,
        has_scope=scope is not None,
        correlation_id=correlation_id
    )

    return {"user_id": user_id, "scope": scope}


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

    try:
        response = await http_client.post(
            revoke_url,
            params={"token": refresh_token},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code == 200:
            logger.info("google_oauth.token_revoked", correlation_id=correlation_id)
            return {"success": True, "error": None}

        # Token may already be revoked or invalid - still considered success
        if response.status_code == 400:
            error_data = response.json() if response.content else {}
            error_type = error_data.get("error", "unknown")

            # "invalid_token" means token was already revoked or expired
            if error_type == "invalid_token":
                logger.info(
                    "google_oauth.token_already_revoked",
                    correlation_id=correlation_id
                )
                return {"success": True, "error": None}

            logger.warning(
                "google_oauth.token_revocation_failed",
                google_error=error_type,
                http_status=response.status_code,
                correlation_id=correlation_id
            )
            return {"success": False, "error": error_type}

        logger.warning(
            "google_oauth.token_revocation_failed",
            http_status=response.status_code,
            correlation_id=correlation_id
        )
        return {"success": False, "error": f"HTTP {response.status_code}"}

    except Exception as e:
        logger.error(
            "google_oauth.token_revocation_error",
            error=str(e),
            correlation_id=correlation_id
        )
        return {"success": False, "error": str(e)}
