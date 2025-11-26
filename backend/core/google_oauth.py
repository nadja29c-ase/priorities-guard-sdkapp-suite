"""
Google OAuth flow implementation.

Handles OAuth state management and token exchange using httpx.

This module does two things:
    - Manages OAuth state tokens (CSRF protection)
    - Exchanges Googles authorization code for access/refresh tokens

This is your outbound Google OAuth client.
"""

import asyncio #needed for retry sleeps
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx #for async HTTP calls
from google_auth_oauthlib.flow import Flow #ONLY used to generate the Google OAuth URL
from sqlalchemy import delete, select #SQLAlchemy query builders
from sqlalchemy.ext.asyncio import AsyncSession #DB session type

from backend.core.config import settings #my config, holds Google keys
from backend.core.oauth_provider.models import OAuthState  # OAuth provider subsystem

logger = logging.getLogger(__name__)


# ============================================================================
# State Management Functions
# ============================================================================


async def cleanup_expired_states(session: AsyncSession) -> None:
    """
    Purpose:
    Deletes old state tokens older than 10 minutes.

    Why:
    OAuth state table must stay small & clean.
    You call it in your /start endpoint.    

    Args:
        session: Database session
    """
    now = datetime.now(timezone.utc)
    stmt = delete(OAuthState).where(OAuthState.expires_at < now)
    result = await session.execute(stmt)
    await session.commit()

    if result.rowcount > 0:
        logger.info(f"Cleaned up {result.rowcount} expired OAuth states")


async def store_state(session: AsyncSession, state: str) -> None:
    """
    Store OAuth state token in database with 10-minute expiration.

    Args:
        session: Database session
        state: OAuth state token to store

    Raises:
        Exception: If database operation fails
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=10)

    oauth_state = OAuthState(
        state=state,
        expires_at=expires_at,
    )

    session.add(oauth_state)
    await session.commit()


async def verify_and_consume_state(session: AsyncSession, state: str) -> bool:
    """
    Verify OAuth state exists and not expired, then delete it (single-use).

    Args:
        session: Database session
        state: OAuth state token to verify

    Returns:
        True if state is valid and not expired, False otherwise
    """
    now = datetime.now(timezone.utc)

    # Check if state exists and not expired
    stmt = select(OAuthState).where(
        OAuthState.state == state, OAuthState.expires_at >= now
    )
    result = await session.execute(stmt)
    oauth_state = result.scalar_one_or_none()

    if oauth_state is None:
        logger.warning("OAuth state verification failed: invalid or expired state")
        return False

    # Delete state (single-use)
    await session.delete(oauth_state)
    await session.commit()

    return True


# ============================================================================
# OAuth Flow Functions
# ============================================================================


async def generate_auth_url() -> tuple[str, str]:
    """
    Generate Google OAuth authorization URL, that the user must click.

    Uses google_auth_oauthlib.flow.Flow ONLY for URL generation (no network calls).

    Returns:
        Tuple of (authorization_url, state)
    """
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
            }
        },
        scopes=["https://www.googleapis.com/auth/calendar.readonly"],
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
    )

    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )

    return auth_url, state


async def exchange_code(code: str, http_client: httpx.AsyncClient) -> dict[str, Any]:
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
