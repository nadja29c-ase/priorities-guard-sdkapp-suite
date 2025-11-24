"""
Authorization Endpoint - OAuth 2.1 authorization request handling.

Handles authorization requests, validates parameters, and renders consent screen.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import urlencode

from backend.core.database import get_db
from backend.core.logging import get_logger
from backend.core.oauth_models import OAuthClient
from backend.core.rate_limit import rate_limit_authorize
from backend.apps.focused.oauth.services.authorization_service import create_authorization_context
from backend.apps.focused.oauth.validators.pkce import validate_code_challenge_method

logger = get_logger(__name__)

router = APIRouter(tags=["oauth-provider"])


def _error_redirect(redirect_uri: str, state: str | None, error: str, description: str):
    """
    Redirect to client with OAuth error.

    Args:
        redirect_uri: Client's redirect URI
        state: CSRF state token
        error: OAuth error code
        description: Human-readable error description

    Returns:
        Redirect response with error parameters
    """
    params = {
        "error": error,
        "error_description": description
    }

    if state:
        params["state"] = state

    error_url = f"{redirect_uri}?{urlencode(params)}"
    return RedirectResponse(url=error_url, status_code=302)


@router.get("/oauth/focused/authorize", response_class=HTMLResponse)
async def authorize_endpoint(
    request: Request,
    response_type: str,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    code_challenge_method: str,
    scope: str,
    state: str | None = None,
    nonce: str | None = None,
    user_id: str | None = None,  # TODO (7C): Replace with real authentication
    db: AsyncSession = Depends(get_db)
):
    """
    OAuth 2.1 authorization endpoint with PKCE.

    Validates client, redirect URI, and scopes, then renders consent screen.

    Query Parameters:
        response_type: Must be "code"
        client_id: Registered OAuth client ID
        redirect_uri: Must match client's registered URIs
        code_challenge: PKCE code challenge (SHA256)
        code_challenge_method: Must be "S256"
        scope: Space-separated scopes (focused.read, focused.write, focused.notify)
        state: Optional CSRF token
        nonce: Optional OpenID Connect nonce
        user_id: TODO - temporary auth placeholder (will be replaced with session auth)

    Returns:
        HTML consent screen on success
        Error redirect on validation failure

    Security Notes:
        - PKCE required (S256 challenge method)
        - redirect_uri must be pre-registered
        - Scopes validated against allowed list
        - Rate limited to prevent abuse
        - Authorization context stored in Redis (10 min TTL)

    Example:
        GET /oauth/focused/authorize?
            response_type=code&
            client_id=focused-client-123&
            redirect_uri=https://example.com/callback&
            code_challenge=abc...&
            code_challenge_method=S256&
            scope=focused.read+focused.write&
            state=xyz&
            user_id=user-456
    """
    # Get correlation_id for logging
    correlation_id = request.state.correlation_id
    request_logger = logger.bind(correlation_id=correlation_id)

    # Rate limit check
    await rate_limit_authorize(request)

    # Log authorization request
    request_logger.info(
        "oauth.authorize.request",
        client_id=client_id,
        response_type=response_type,
        scope=scope,
        redirect_uri=redirect_uri,
        code_challenge_method=code_challenge_method
    )

    # TODO (7C): Replace with real authentication middleware
    # For now, require user_id query param as temporary auth mechanism
    if not user_id:
        request_logger.warning(
            "oauth.authorize.error",
            error="missing_user_id",
            message="Authentication required"
        )
        raise HTTPException(
            status_code=401,
            detail="Authentication required. TODO: Implement session-based auth."
        )

    # Validate response_type
    if response_type != "code":
        return _error_redirect(
            redirect_uri,
            state,
            error="unsupported_response_type",
            description="Only response_type=code is supported"
        )

    # Validate code_challenge_method (must be S256)
    if not validate_code_challenge_method(code_challenge_method):
        return _error_redirect(
            redirect_uri,
            state,
            error="invalid_request",
            description="code_challenge_method must be S256"
        )

    # Validate client exists
    result = await db.execute(
        select(OAuthClient).where(OAuthClient.client_id == client_id)
    )
    client = result.scalar_one_or_none()

    if not client:
        raise HTTPException(status_code=401, detail="Invalid client_id")

    # Validate redirect_uri is in client's registered URIs
    if redirect_uri not in client.redirect_uris:
        raise HTTPException(status_code=400, detail="Invalid redirect_uri")

    # Validate scopes
    allowed_scopes = {"focused.read", "focused.write", "focused.notify"}
    requested_scopes = set(scope.split())

    if not requested_scopes.issubset(allowed_scopes):
        return _error_redirect(
            redirect_uri,
            state,
            error="invalid_scope",
            description=f"Invalid scopes. Allowed: {', '.join(allowed_scopes)}"
        )

    # Create authorization context in Redis (10 minute TTL)
    auth_context_id = await create_authorization_context(
        client_id=client_id,
        client_name=client.client_name,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        scope=scope,
        redirect_uri=redirect_uri,
        user_id=user_id,
        state=state,
        nonce=nonce,
        correlation_id=correlation_id
    )

    # Render consent screen
    # TODO (7C): Detect user language preference for EN/DE template selection
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="backend/templates")

    return templates.TemplateResponse(
        "oauth_consent_en.html",
        {
            "request": request,
            "auth_context_id": auth_context_id,
            "client_name": client.client_name,
            "scopes": requested_scopes
        }
    )
