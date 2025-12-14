"""
Authorization Endpoint - OAuth 2.1 authorization request handling.

Handles authorization requests, validates parameters, resolves user identity
via login_hint or session cookie, and renders consent screen with language detection.

Increment 12: OAuth Consent UI Implementation.
Increment 19: Cross-app user identification via session cookies.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import urlencode, urlparse, urlunparse

from backend.core.database import get_db
from backend.core.logging import get_logger, mask_client_id
from backend.core.models import CoreConnection, CoreUser
from backend.core.rate_limit import check_rate_limit, get_client_ip
from backend.core.oauth_provider.cookies import get_session_cookie
from backend.core.oauth_provider.services.authorization_service import create_authorization_context
from backend.core.oauth_provider.services.session_service import get_session_user
from backend.core.oauth_provider.validators.pkce import validate_code_challenge_method

logger = get_logger(__name__)

router = APIRouter(tags=["oauth-provider"])

# Initialize Jinja2 templates
templates = Jinja2Templates(directory="backend/templates")


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


def _detect_language(request: Request) -> str:
    """
    Detect user language from Accept-Language header.

    Args:
        request: FastAPI request object

    Returns:
        Language code: "de" for German, "en" for everything else
    """
    accept_language = request.headers.get("Accept-Language", "")
    # Simple detection: if starts with "de", use German
    if accept_language.lower().startswith("de"):
        return "de"
    return "en"


def _normalize(s: str | None) -> str | None:
    """
    Normalize string parameter: strip whitespace, convert empty to None.

    This is critical for OAuth 2.1 security - empty/whitespace strings
    must be treated as missing parameters.

    Args:
        s: Input string (may be None)

    Returns:
        Stripped string if non-empty, None otherwise
    """
    if s is None:
        return None
    s = s.strip()
    return s if s else None


def _normalize_redirect_uri(uri: str) -> str | None:
    """
    Normalize redirect_uri per RFC 3986 rules:
    - scheme: lowercased
    - host: lowercased
    - path: preserved case-sensitive
    - query: must be empty
    - fragment: must be empty

    Returns:
        Normalized URI string, or None if invalid.
    """
    if not uri:
        return None

    try:
        parsed = urlparse(uri)
    except Exception:
        return None

    # Reject relative URIs (must have scheme and host)
    if not parsed.scheme or not parsed.netloc:
        return None

    # Reject any query or fragment (OAuth 2.1 strict)
    if parsed.query or parsed.fragment:
        return None

    # Normalize scheme and host to lowercase
    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        # Keep path exact
    )

    return urlunparse(normalized)


async def _resolve_user_identity(
    request: Request,
    db: AsyncSession,
    chatgpt_user_id: str | None,
    correlation_id: str
) -> CoreUser:
    """
    Resolve user identity via identity resolution chain (Increment 19).

    Priority order:
    1. login_hint provided → find or create by chatgpt_user_id
    2. Valid session cookie → get existing user from session
    3. Neither → create new anonymous user

    This ensures:
    - Forward compatibility with OpenAI's potential login_hint support
    - Cross-app user linking via browser session cookie
    - Graceful fallback to anonymous users

    Args:
        request: FastAPI request object (for reading session cookie)
        db: Database session
        chatgpt_user_id: ChatGPT user ID from login_hint parameter (may be None)
        correlation_id: Request correlation ID for logging

    Returns:
        CoreUser: Existing or newly created user

    TODO (Future Increment - Orphan User Cleanup):
        Users who start OAuth but abandon before completion, or let tokens expire
        and re-authorize (creating new user), leave orphan core_users rows.
        Per architecture: "Accounts with no active OAuth connections or consents
        for >= 6 months are automatically anonymized or deleted."

        Implementation:
        - Celery task that runs weekly
        - Finds core_users with no oauth_access_tokens AND no core_consents for 6+ months
        - Either deletes or anonymizes these rows
    """
    request_logger = logger.bind(correlation_id=correlation_id)

    # =========================================================================
    # Priority 1: login_hint provided → find or create by chatgpt_user_id
    # =========================================================================
    if chatgpt_user_id:
        result = await db.execute(
            select(CoreUser).where(CoreUser.chatgpt_user_id == chatgpt_user_id)
        )
        user = result.scalar_one_or_none()

        if user:
            request_logger.info(
                "oauth.authorize.user_found",
                user_id=str(user.id),
                identity_source="login_hint",
            )
            return user

        # Create new user with chatgpt_user_id
        user = CoreUser(chatgpt_user_id=chatgpt_user_id)
        db.add(user)
        await db.commit()
        await db.refresh(user)

        request_logger.info(
            "oauth.authorize.user_created",
            user_id=str(user.id),
            identity_source="login_hint",
        )
        return user

    # =========================================================================
    # Priority 2: Valid session cookie → get existing user from session
    # =========================================================================
    session_token = get_session_cookie(request)
    # Prevalidate token format (64-char hex from secrets.token_hex(32))
    if session_token and len(session_token) == 64:
        session_user_id = await get_session_user(session_token, db, correlation_id)
        if session_user_id:
            # Look up the user to return the full CoreUser object
            result = await db.execute(
                select(CoreUser).where(CoreUser.id == session_user_id)
            )
            user = result.scalar_one_or_none()

            if user:
                request_logger.info(
                    "oauth.authorize.user_found",
                    user_id=str(user.id),
                    identity_source="session_cookie",
                )
                return user

            # Session references non-existent user (shouldn't happen, but handle gracefully)
            request_logger.warning(
                "oauth.authorize.session_user_not_found",
                session_user_id=str(session_user_id),
            )

    # =========================================================================
    # Priority 3: Neither → create new anonymous user
    # =========================================================================
    user = CoreUser(chatgpt_user_id=None)
    db.add(user)
    await db.commit()
    await db.refresh(user)

    request_logger.info(
        "oauth.authorize.user_created",
        user_id=str(user.id),
        identity_source="new_anonymous",
    )
    return user


@router.get("/oauth/focused/authorize", response_class=HTMLResponse)
@router.get("/oauth/pg/authorize", response_class=HTMLResponse)
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
    login_hint: str | None = None,
    db: AsyncSession = Depends(get_db)
):
    """
    OAuth 2.1 authorization endpoint with PKCE.

    Validates client, redirect URI, and scopes. Resolves user identity via
    login_hint parameter, then renders consent screen in user's language.

    Query Parameters:
        response_type: Must be "code"
        client_id: Registered OAuth client ID
        redirect_uri: Must match client's registered URIs
        code_challenge: PKCE code challenge (SHA256)
        code_challenge_method: Must be "S256"
        scope: Space-separated scopes (focused.read, focused.write, focused.notify)
        state: Optional CSRF token
        nonce: Optional OpenID Connect nonce
        login_hint: Optional - ChatGPT user ID for user identification

    Returns:
        HTML consent screen on success
        Error redirect on validation failure

    Security Notes:
        - login_hint is optional; if missing, an anonymous user is created
        - User identity resolved via login_hint → core_users.chatgpt_user_id
        - Never accept raw user_id from query params (prevents impersonation)
        - PKCE required (S256 challenge method)
        - redirect_uri must be pre-registered
        - Rate limited: by IP always, by login_hint if provided
        - Authorization context stores internal user_id (UUID), NOT chatgpt_user_id

    Example:
        GET /oauth/focused/authorize?
            response_type=code&
            client_id=focused-client-123&
            redirect_uri=https://example.com/callback&
            code_challenge=abc...&
            code_challenge_method=S256&
            scope=focused.read+focused.write&
            state=xyz&
            login_hint=chatgpt_user_123
    """
    # Get correlation_id for logging
    correlation_id = request.state.correlation_id
    request_logger = logger.bind(correlation_id=correlation_id)

    # =========================================================================
    # NORMALIZE ALL PARAMETERS (OAuth 2.1 security requirement)
    # Empty strings and whitespace-only must be treated as missing
    # =========================================================================
    client_id = _normalize(client_id)
    redirect_uri = _normalize(redirect_uri)
    scope = _normalize(scope)
    login_hint = _normalize(login_hint)
    code_challenge = _normalize(code_challenge)
    code_challenge_method = _normalize(code_challenge_method)
    state = _normalize(state)
    nonce = _normalize(nonce)

    # =========================================================================
    # VALIDATE REQUIRED PARAMETERS BEFORE ANY REDIRECTS
    # These are checked before we can safely redirect to client
    # =========================================================================

    # client_id is required
    if not client_id:
        request_logger.warning(
            "oauth.authorize.error",
            error="invalid_request",
            message="client_id is required"
        )
        # Cannot redirect - no valid redirect_uri without client validation
        raise HTTPException(status_code=400, detail="client_id is required")

    # redirect_uri is required
    if not redirect_uri:
        request_logger.warning(
            "oauth.authorize.error",
            error="invalid_request",
            message="redirect_uri is required"
        )
        # Cannot redirect - no valid redirect_uri
        raise HTTPException(status_code=400, detail="redirect_uri is required")

    # Phase 1: Rate limit by IP (before login_hint validation)
    ip = get_client_ip(request)
    await check_rate_limit(
        key=f"ratelimit:oauth:authorize:ip:{ip}",
        limit=20,
        window=60,
        request=request
    )

    # Log authorization request (don't log login_hint for privacy)
    request_logger.info(
        "oauth.authorize.request",
        client_id=mask_client_id(client_id),
        response_type=response_type,
        scope=scope,
        redirect_uri=redirect_uri,
        code_challenge_method=code_challenge_method,
        has_login_hint=login_hint is not None
    )

    # =========================================================================
    # VALIDATE PKCE PARAMETERS (OAuth 2.1 REQUIRED)
    # =========================================================================
    if not code_challenge:
        request_logger.warning(
            "oauth.authorize.error",
            error="invalid_request",
            message="code_challenge is required"
        )
        return _error_redirect(
            redirect_uri,
            state,
            error="invalid_request",
            description="code_challenge is required"
        )

    if not code_challenge_method:
        request_logger.warning(
            "oauth.authorize.error",
            error="invalid_request",
            message="code_challenge_method is required"
        )
        return _error_redirect(
            redirect_uri,
            state,
            error="invalid_request",
            description="code_challenge_method is required"
        )

    # =========================================================================
    # VALIDATE SCOPE (OAuth 2.1 REQUIRED)
    # =========================================================================
    if not scope:
        request_logger.warning(
            "oauth.authorize.error",
            error="invalid_scope",
            message="scope is required"
        )
        return _error_redirect(
            redirect_uri,
            state,
            error="invalid_scope",
            description="scope is required"
        )

    # =========================================================================
    # VALIDATE LOGIN_HINT (Optional - if provided, validate length)
    # When missing, an anonymous user will be created
    # =========================================================================
    # Validate login_hint length if provided (chatgpt_user_id is VARCHAR(64))
    if login_hint and len(login_hint) > 64:
        request_logger.warning(
            "oauth.authorize.error",
            error="invalid_request",
            message="login_hint exceeds maximum length"
        )
        return _error_redirect(
            redirect_uri,
            state,
            error="invalid_request",
            description="login_hint exceeds maximum length"
        )

    # Phase 2: Rate limit by login_hint (only if provided)
    if login_hint:
        await check_rate_limit(
            key=f"ratelimit:oauth:authorize:login_hint:{login_hint}",
            limit=20,
            window=60,
            request=request
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

    # Validate client exists (OAuth provider connection)
    result = await db.execute(
        select(CoreConnection).where(
            CoreConnection.client_id == client_id,
            CoreConnection.connection_type == "oauth_provider"
        )
    )
    client = result.scalar_one_or_none()

    if not client:
        request_logger.warning(
            "oauth.authorize.error",
            error="invalid_client",
            client_id=mask_client_id(client_id)
        )
        return _error_redirect(
            redirect_uri,
            state,
            error="invalid_client",
            description="Unknown client_id"
        )

    # Validate redirect_uri per RFC 3986 (case-insensitive scheme/host, case-sensitive path)
    # Normalize the incoming redirect URI
    normalized_redirect = _normalize_redirect_uri(redirect_uri)
    if not normalized_redirect:
        request_logger.warning(
            "oauth.authorize.error",
            error="invalid_redirect_uri",
            client_id=mask_client_id(client_id),
            message="Invalid redirect_uri format (query/fragment not allowed)"
        )
        return _error_redirect(
            redirect_uri,
            state,
            error="invalid_request",
            description="Invalid redirect_uri"
        )

    # Normalize all registered URIs and compare
    normalized_registered = {
        _normalize_redirect_uri(uri) for uri in client.redirect_uris
    }

    if normalized_redirect not in normalized_registered:
        request_logger.warning(
            "oauth.authorize.error",
            error="invalid_redirect_uri",
            client_id=mask_client_id(client_id)
        )
        return _error_redirect(
            redirect_uri,
            state,
            error="invalid_request",
            description="redirect_uri not registered for this client"
        )

    # Validate scopes against client's registered scopes (NOT hardcoded)
    # Security: Each client can only request scopes it was registered with
    allowed_scopes = set(client.scopes)
    requested_scopes = set(scope.split())

    if not requested_scopes.issubset(allowed_scopes):
        request_logger.warning(
            "oauth.authorize.error",
            error="invalid_scope",
            client_id=mask_client_id(client_id),
            requested=list(requested_scopes),
            allowed=list(allowed_scopes)
        )
        return _error_redirect(
            redirect_uri,
            state,
            error="invalid_scope",
            description="Requested scopes exceed client's registered scopes"
        )

    # Resolve user identity via identity resolution chain (Increment 19)
    # Priority: 1. login_hint, 2. session cookie, 3. new anonymous user
    user = await _resolve_user_identity(request, db, login_hint, correlation_id)

    # Extract client_name from provider_metadata (human-readable app name for consent UI)
    # NOTE: client.provider is the connection_type ("oauth_provider"), NOT the app name
    client_name = client.provider_metadata.get("client_name", client_id)

    # Create authorization context in Redis (10 minute TTL)
    # IMPORTANT: Store internal user_id (UUID), NOT chatgpt_user_id
    auth_context_id = await create_authorization_context(
        client_id=client_id,
        client_name=client_name,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        scope=scope,
        redirect_uri=redirect_uri,
        user_id=str(user.id),  # Internal UUID, not chatgpt_user_id
        state=state,
        nonce=nonce,
        correlation_id=correlation_id
    )

    # Detect user language preference
    language = _detect_language(request)
    template_name = f"oauth_consent_{language}.html"

    # Scope descriptions for consent UI (localized)
    # TODO: Move to i18n system for proper localization
    scope_descriptions_en = {
        "focused.read": "Read your calendar events to detect focus sessions and provide insights.",
        "focused.write": "Toggle Apple Focus (the built-in Do Not Disturb mode) on your iPhone during your focus sessions.",
        "focused.notify": "Send notifications related to your focus schedule.",
    }
    scope_descriptions_de = {
        "focused.read": "Deine Kalendertermine lesen, um Fokus-Zeiten zu erkennen und dir hilfreiche Einblicke zu geben.",
        "focused.write": "Apple Fokus (den integrierten „Nicht stören“-Modus) auf deinem iPhone während deiner Fokus-Zeiten ein- und ausschalten.",
        "focused.notify": "Relevante Benachrichtigungen senden",
    }
    scope_descriptions = scope_descriptions_de if language == "de" else scope_descriptions_en

    request_logger.info(
        "oauth.authorize.consent_rendered",
        user_id=str(user.id),
        client_id=mask_client_id(client_id),
        client_name=client_name,
        language=language
    )

    return templates.TemplateResponse(
        template_name,
        {
            "request": request,
            "auth_context_id": auth_context_id,
            "client_name": client_name,
            "scopes": requested_scopes,
            "scope_descriptions": scope_descriptions,
        }
    )
