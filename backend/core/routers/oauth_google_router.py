"""
Google OAuth endpoints (shared across all SDK apps).

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

Architecture (Increment 18B):
    - Router handles HTTP concerns only (request/response)
    - Service layer handles OAuth orchestration
    - Repository layer handles database persistence
    - HTML rendering in dedicated module

Location (Increment 18C):
    - Moved from backend/apps/focused/routers/ to backend/core/routers/
    - Shared entrypoint for all SDK apps
"""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.html.oauth_pages import render_error, render_success
from backend.core.oauth.exceptions import (
    ConnectionTokenExpiredError,
    GoogleOAuthError,
    StateInvalidError,
    StateStorageError,
    TokenExchangeError,
)
from backend.core.oauth.google_oauth_service import (
    complete_oauth_flow,
    initiate_oauth_flow,
)

router = APIRouter(tags=["Google OAuth"])


@router.get("/start")
async def start_google_oauth(
    request: Request,
    token: str = Query(..., description="Opaque connection token from /api/focused/google/initiate-connection"),
):
    """
    Initiate Google OAuth flow with PKCE.

    Security (Increment 11 + 18):
        - Accepts opaque token instead of user_id (user_id never in URL)
        - Token is single-use (deleted after validation)
        - Token expires after 10 minutes
        - Generates PKCE code_verifier and code_challenge (S256)
        - Stores state + user_id + code_verifier in Redis (10-min TTL)
        - Redirects user to Google consent screen

    Args:
        request: FastAPI request object
        token: Opaque connection token (required query parameter)

    Returns:
        307 redirect to Google authorization URL, or HTML error page
    """
    correlation_id = getattr(request.state, "correlation_id", "unknown")

    try:
        redirect_url = await initiate_oauth_flow(token, correlation_id)
        return RedirectResponse(url=redirect_url, status_code=307)
    except ConnectionTokenExpiredError:
        return render_error(
            title="Link Expired",
            message="This connection link has expired or has already been used. Please return to ChatGPT and request a new link.",
            status_code=400,
        )
    except StateStorageError:
        return render_error(
            title="Service Unavailable",
            message="Unable to initiate authorization. Please try again.",
            status_code=503,
        )
    except GoogleOAuthError:
        return render_error(
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
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    http_client = request.app.state.http_client

    # Handle Google-side errors (user denied, etc.)
    if error:
        if error == "access_denied":
            return render_error(
                title="Access Denied",
                message="You denied access to your Google Calendar. Please try again if you'd like to connect.",
            )
        return render_error(
            title="Authorization Failed",
            message=error_description or "Google authorization failed. Please try again.",
        )

    # Validate required parameters (router responsibility)
    if not code:
        return render_error(
            title="Invalid Request",
            message="Missing authorization code from Google.",
        )

    if not state:
        return render_error(
            title="Invalid Request",
            message="Missing state parameter. Please start the authorization process again.",
        )

    try:
        await complete_oauth_flow(code, state, session, http_client, correlation_id)
        return render_success()
    except StateInvalidError:
        return render_error(
            title="Session Expired",
            message="Your authorization session has expired or is invalid. Please try again.",
        )
    except TokenExchangeError:
        return render_error(
            title="Authorization Failed",
            message="Failed to complete authorization with Google. Please try again.",
        )
    except GoogleOAuthError:
        return render_error(
            title="Error",
            message="An unexpected error occurred. Please try again.",
            status_code=500,
        )
