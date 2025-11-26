"""
Google OAuth endpoints for Focused app.

This file handles:

/google/start → Begin OAuth flow (with PKCE + Redis state)

/google/callback → Handle Google's redirect

It covers everything outbound to Google.

Security (Increment 11):
    - PKCE S256 for enhanced security
    - State stored in Redis with 10-minute TTL
    - user_id bound server-side (retrieved from Redis, not accepted from callback)
    - HTML error pages for user-facing redirect flow
    - Tokens never logged

"""

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.encryption import encrypt_token
from backend.core.google_oauth import (
    exchange_code,
    generate_auth_url_with_pkce,
    generate_code_challenge,
    generate_code_verifier,
    generate_state_token,
    store_oauth_state,
    verify_and_get_oauth_state,
)
from backend.core.models import CoreConnection

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Google OAuth"])


def _html_error(title: str, message: str, status_code: int = 400) -> HTMLResponse:
    """
    Return HTML error page for user-facing OAuth errors.

    Simple HTML page that displays the error to the user.
    Per Increment 11: HTML errors for browser redirect flow.

    Args:
        title: Error title (e.g., "Authorization Failed")
        message: User-friendly error message
        status_code: HTTP status code (default 400)

    Returns:
        HTMLResponse with error page
    """
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>{title}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; padding: 40px; text-align: center; }}
        h1 {{ color: #dc3545; }}
        p {{ color: #666; max-width: 400px; margin: 20px auto; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <p>{message}</p>
    <p><small>You can close this window and try again.</small></p>
</body>
</html>"""
    return HTMLResponse(content=html_content, status_code=status_code)


def _html_success() -> HTMLResponse:
    """
    Return HTML success page after OAuth completes.

    Returns:
        HTMLResponse with success page
    """
    html_content = """<!DOCTYPE html>
<html>
<head>
    <title>Connected Successfully</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; padding: 40px; text-align: center; }
        h1 { color: #28a745; }
        p { color: #666; max-width: 400px; margin: 20px auto; }
    </style>
</head>
<body>
    <h1>Connected Successfully</h1>
    <p>Your Google Calendar has been connected. You can close this window.</p>
</body>
</html>"""
    return HTMLResponse(content=html_content, status_code=200)


@router.get("/start")
async def start_google_oauth(
    request: Request,
    user_id: str = Query(..., description="User identifier initiating OAuth"),
):
    """
    Initiate Google OAuth flow with PKCE.

    Security (Increment 11):
        - Generates cryptographically secure state token
        - Generates PKCE code_verifier and code_challenge (S256)
        - Stores state + user_id + code_verifier in Redis (10-min TTL)
        - Redirects user to Google consent screen

    Args:
        request: FastAPI request object
        user_id: User identifier (required query parameter)

    Returns:
        307 redirect to Google authorization URL
    """
    request_id = getattr(request.state, "request_id", "unknown")
    log = logger.bind(request_id=request_id, user_id=user_id)

    # Validate user_id format (should be valid UUID)
    try:
        UUID(user_id)
    except ValueError:
        log.warning("oauth_start_invalid_user_id", user_id=user_id)
        return _html_error(
            title="Invalid Request",
            message="Invalid user identifier format.",
            status_code=400,
        )

    log.info("oauth_start_initiated")

    try:
        # Generate PKCE values
        code_verifier = generate_code_verifier()
        code_challenge = generate_code_challenge(code_verifier)

        # Generate state token
        state = generate_state_token()

        # Store state in Redis with user_id and code_verifier
        stored = await store_oauth_state(
            state=state,
            user_id=user_id,
            code_verifier=code_verifier,
        )

        if not stored:
            log.error("oauth_start_state_storage_failed")
            return _html_error(
                title="Service Unavailable",
                message="Unable to initiate authorization. Please try again.",
                status_code=503,
            )

        # Generate authorization URL with PKCE
        auth_url = generate_auth_url_with_pkce(
            code_challenge=code_challenge,
            state=state,
        )

        log.info("oauth_start_redirecting_to_google")

        # Redirect to Google
        return RedirectResponse(url=auth_url, status_code=307)

    except Exception as e:
        log.exception("oauth_start_unexpected_error")
        return _html_error(
            title="Error",
            message="An unexpected error occurred. Please try again.",
            status_code=500,
        )


@router.get("/callback")
async def google_oauth_callback(
    request: Request,
    code: str | None = Query(None, description="Authorization code from Google"),
    state: str | None = Query(None, description="OAuth state token for CSRF protection"),
    error: str | None = Query(None, description="Error code from Google"),
    error_description: str | None = Query(None, description="Error description from Google"),
    session: AsyncSession = Depends(get_db),
):
    """
    Handle Google OAuth callback.

    Security (Increment 11):
        - Validates state exists in Redis (CSRF protection)
        - Retrieves user_id from Redis (not from query params)
        - Uses PKCE code_verifier from Redis in token exchange
        - State is single-use (deleted after verification)
        - Returns HTML error pages (user-facing redirect flow)
        - Never logs tokens

    Args:
        request: FastAPI request object (provides access to app state)
        code: Authorization code from Google
        state: OAuth state token for CSRF protection
        error: Error code if Google authorization failed
        error_description: Human-readable error description
        session: Database session

    Returns:
        HTML success page or HTML error page
    """
    request_id = getattr(request.state, "request_id", "unknown")
    log = logger.bind(request_id=request_id)

    # Handle Google-side errors (user denied, etc.)
    if error:
        log.warning(
            "oauth_callback_google_error",
            error=error,
            error_description=error_description,
        )
        if error == "access_denied":
            return _html_error(
                title="Access Denied",
                message="You denied access to your Google Calendar. Please try again if you'd like to connect.",
            )
        return _html_error(
            title="Authorization Failed",
            message=error_description or "Google authorization failed. Please try again.",
        )

    # Validate required parameters
    if not code:
        log.warning("oauth_callback_missing_code")
        return _html_error(
            title="Invalid Request",
            message="Missing authorization code from Google.",
        )

    if not state:
        log.warning("oauth_callback_missing_state")
        return _html_error(
            title="Invalid Request",
            message="Missing state parameter. Please start the authorization process again.",
        )

    # Verify state and retrieve user_id + code_verifier from Redis
    state_data = await verify_and_get_oauth_state(state)

    if state_data is None:
        log.warning("oauth_callback_invalid_state", state_prefix=state[:8] if state else "none")
        return _html_error(
            title="Session Expired",
            message="Your authorization session has expired or is invalid. Please try again.",
        )

    user_id = state_data["user_id"]
    code_verifier = state_data["code_verifier"]
    log = log.bind(user_id=user_id)

    log.info("oauth_callback_state_verified")

    try:
        # Exchange code for tokens (with PKCE verifier)
        http_client = request.app.state.http_client
        token_data = await exchange_code(
            code=code,
            http_client=http_client,
            code_verifier=code_verifier,
        )

        # Calculate token expiration
        token_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=token_data["expires_in"]
        )

        # Encrypt tokens before storage
        encrypted_access = encrypt_token(token_data["access_token"])
        encrypted_refresh = (
            encrypt_token(token_data["refresh_token"])
            if token_data["refresh_token"]
            else None
        )

        # Upsert to core_connections (PostgreSQL upsert pattern)
        stmt = insert(CoreConnection).values(
            user_id=user_id,
            provider="google",
            encrypted_access_token=encrypted_access,
            encrypted_refresh_token=encrypted_refresh,
            token_expires_at=token_expires_at,
            scopes=token_data["scopes"],
        )

        stmt = stmt.on_conflict_do_update(
            constraint="uq_user_provider",
            set_={
                "encrypted_access_token": encrypted_access,
                "encrypted_refresh_token": encrypted_refresh,
                "token_expires_at": token_expires_at,
                "scopes": token_data["scopes"],
                "updated_at": datetime.now(timezone.utc),
            },
        )

        await session.execute(stmt)
        await session.commit()

        log.info("oauth_callback_tokens_stored", scopes=token_data["scopes"])

        # Return success HTML page
        return _html_success()

    except ValueError as e:
        # Token exchange failed (scope missing, invalid code, etc.)
        log.error("oauth_callback_token_exchange_failed", error=str(e))
        return _html_error(
            title="Authorization Failed",
            message="Failed to complete authorization with Google. Please try again.",
        )

    except Exception as e:
        log.exception("oauth_callback_unexpected_error")
        return _html_error(
            title="Error",
            message="An unexpected error occurred. Please try again.",
            status_code=500,
        )
