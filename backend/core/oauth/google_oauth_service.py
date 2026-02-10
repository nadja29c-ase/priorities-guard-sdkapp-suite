"""
Google OAuth service layer.

Orchestrates the OAuth flow by coordinating utilities, encryption, and repository.
Service raises typed exceptions; router catches and renders HTML.
"""

from datetime import datetime, timedelta, timezone

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.encryption import encrypt_token
from backend.core.google_oauth import (
    exchange_code,
    generate_auth_url_with_pkce,
    generate_code_challenge,
    generate_code_verifier,
    generate_state_token,
    store_oauth_state,
    verify_and_get_oauth_state,
    verify_connection_token,
)
from backend.core.oauth.exceptions import (
    ConnectionTokenExpiredError,
    GoogleOAuthError,
    StateInvalidError,
    StateStorageError,
    TokenExchangeError,
)
from backend.core.repositories.google_connection_repo import upsert_google_connection

logger = structlog.get_logger(__name__)

# Default scope for backwards compatibility (Focused uses this)
DEFAULT_GOOGLE_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"


async def initiate_oauth_flow(
    token: str,
    correlation_id: str,
) -> str:
    """
    Initiate Google OAuth flow with PKCE.

    Validates and consumes the opaque connection token, generates PKCE values,
    stores state in Redis, and returns the Google authorization URL.

    Args:
        token: Opaque connection token from /api/focused/google/initiate-connection
        correlation_id: Request correlation ID for tracing

    Returns:
        Google OAuth redirect URL

    Raises:
        ConnectionTokenExpiredError: If token is invalid or expired
        GoogleOAuthError: If state storage fails or other unexpected error
    """
    log = logger.bind(correlation_id=correlation_id)

    try:
        # Validate and consume connection token
        token_data = await verify_connection_token(token, correlation_id=correlation_id)

        if token_data is None:
            log.warning(
                "oauth_start_invalid_token",
                token_prefix=token[:8] if token else "none"
            )
            raise ConnectionTokenExpiredError("Connection token invalid or expired")

        user_id = token_data["user_id"]
        # Use scope from token if provided, otherwise default (backwards compat for Focused)
        scope = token_data.get("scope") or DEFAULT_GOOGLE_SCOPE

        log = log.bind(user_id=user_id)
        log.info("oauth_start_initiated")

        # Generate PKCE values
        code_verifier = generate_code_verifier()
        code_challenge = generate_code_challenge(code_verifier)

        # Generate state token
        state = generate_state_token()

        # Store state in Redis with user_id, code_verifier, and scope
        stored = await store_oauth_state(
            state=state,
            user_id=user_id,
            code_verifier=code_verifier,
            correlation_id=correlation_id,
            scope=scope,
        )

        if not stored:
            log.error("oauth_start_state_storage_failed")
            raise StateStorageError("Failed to store OAuth state")

        # Generate authorization URL with PKCE and scope
        auth_url = generate_auth_url_with_pkce(
            code_challenge=code_challenge,
            state=state,
            scope=scope,
        )

        log.info("oauth_start_redirecting_to_google")

        return auth_url

    except ConnectionTokenExpiredError:
        raise
    except StateStorageError:
        raise
    except GoogleOAuthError:
        raise
    except Exception as e:
        log.exception("oauth_start_unexpected_error")
        raise GoogleOAuthError(f"Unexpected error during OAuth initiation: {e}") from e


async def complete_oauth_flow(
    code: str,
    state: str,
    session: AsyncSession,
    http_client: httpx.AsyncClient,
    correlation_id: str,
) -> None:
    """
    Complete Google OAuth flow.

    Validates state, exchanges authorization code for tokens, encrypts tokens,
    and persists to database via repository.

    Args:
        code: Authorization code from Google
        state: OAuth state token for CSRF protection
        session: Database session
        http_client: HTTP client for Google API calls
        correlation_id: Request correlation ID for tracing

    Returns:
        None on success

    Raises:
        StateInvalidError: If state is invalid or expired
        TokenExchangeError: If token exchange with Google fails
        GoogleOAuthError: If unexpected error occurs
    """
    log = logger.bind(correlation_id=correlation_id)

    try:
        # Verify state and retrieve user_id + code_verifier + scope from Redis
        state_data = await verify_and_get_oauth_state(state, correlation_id=correlation_id)

        if state_data is None:
            log.warning("oauth_callback_invalid_state", state_prefix=state[:8] if state else "none")
            raise StateInvalidError("OAuth state invalid or expired")

        user_id = state_data["user_id"]
        code_verifier = state_data["code_verifier"]
        # Use scope from state if provided, otherwise default (backwards compat)
        scope = state_data.get("scope") or DEFAULT_GOOGLE_SCOPE
        log = log.bind(user_id=user_id)

        log.info("oauth_callback_state_verified")

        # Exchange code for tokens (with PKCE verifier and scope validation)
        token_data = await exchange_code(
            code=code,
            http_client=http_client,
            code_verifier=code_verifier,
            correlation_id=correlation_id,
            required_scope=scope,
        )

        # Calculate token expiration
        token_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=token_data["expires_in"]
        )

        # Encrypt tokens before storage (service responsibility)
        encrypted_access = encrypt_token(token_data["access_token"])
        encrypted_refresh = (
            encrypt_token(token_data["refresh_token"])
            if token_data["refresh_token"]
            else None
        )

        # Persist to database via repository
        await upsert_google_connection(
            user_id=user_id,
            encrypted_access_token=encrypted_access,
            encrypted_refresh_token=encrypted_refresh,
            token_expires_at=token_expires_at,
            scopes=token_data["scopes"],
            session=session,
        )

        log.info("oauth_callback_tokens_stored", scopes=token_data["scopes"])

    except ValueError as e:
        # Token exchange failed (scope missing, invalid code, etc.)
        log.error("oauth_callback_token_exchange_failed", error=str(e))
        raise TokenExchangeError(f"Token exchange failed: {e}") from e
    except (StateInvalidError, TokenExchangeError, GoogleOAuthError):
        raise
    except Exception as e:
        log.exception("oauth_callback_unexpected_error")
        raise GoogleOAuthError(f"Unexpected error during OAuth completion: {e}") from e
