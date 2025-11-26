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
) -> bool:
    """
    Store OAuth state in Redis with user_id and code_verifier.

    State is bound to user_id server-side to prevent tampering.
    TTL is 10 minutes.

    Args:
        state: The state token (used as key)
        user_id: User ID initiating the OAuth flow
        code_verifier: PKCE code verifier for this flow

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

    if result:
        logger.info(f"[oauth] Stored state for user_id={user_id}")
        return True
    else:
        logger.error(f"[oauth] Failed to store state for user_id={user_id}")
        return False


async def verify_and_get_oauth_state(state: str) -> dict[str, Any] | None:
    """
    Verify OAuth state exists in Redis and retrieve associated data.

    State is deleted after retrieval (single-use).

    Args:
        state: The state token to verify

    Returns:
        Dictionary with user_id and code_verifier if valid, None otherwise
    """
    key = f"oauth:google:state:{state}"

    # Get state data
    value = await redis_client.get(key)

    if value is None:
        logger.warning("[oauth] State verification failed: invalid or expired state")
        return None

    # Delete state (single-use)
    await redis_client.delete(key)

    try:
        data = json.loads(value)
        logger.info(f"[oauth] State verified for user_id={data.get('user_id')}")
        return {
            "user_id": data["user_id"],
            "code_verifier": data["code_verifier"],
        }
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"[oauth] Failed to parse state data: {e}")
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
                    f"Granted scopes: {scopes}"
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
                f"HTTP {e.response.status_code}"
            )
            if attempt == max_retries - 1:
                raise ValueError(f"Token exchange failed: {e.response.text}")

            # Exponential backoff with jitter
            delay = base_delay * (2**attempt) + random.uniform(0, 1)
            logger.info(f"Retrying in {delay:.2f} seconds...")
            await asyncio.sleep(delay)

        except Exception as e:
            logger.error(f"Token exchange failed unexpectedly: {e}")
            raise ValueError(f"Token exchange failed: {str(e)}")

    raise ValueError("Token exchange failed after maximum retries")


# ============================================================================
# Token Revocation (Increment 10)
# ============================================================================


async def revoke_google_token(
    refresh_token: str,
    http_client: httpx.AsyncClient,
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
            logger.info("Google OAuth token revoked successfully")
            return {"success": True, "error": None}

        # Token may already be revoked or invalid - still considered success
        if response.status_code == 400:
            error_data = response.json() if response.content else {}
            error_type = error_data.get("error", "unknown")

            # "invalid_token" means token was already revoked or expired
            if error_type == "invalid_token":
                logger.info("Google OAuth token already revoked or expired")
                return {"success": True, "error": None}

            logger.warning(f"Google token revocation failed: {error_type}")
            return {"success": False, "error": error_type}

        logger.warning(
            f"Google token revocation unexpected status: {response.status_code}"
        )
        return {"success": False, "error": f"HTTP {response.status_code}"}

    except Exception as e:
        logger.error(f"Google token revocation error: {e}")
        return {"success": False, "error": str(e)}
