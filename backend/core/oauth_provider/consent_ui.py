"""
Consent UI Endpoint - OAuth 2.1 user consent handling.

Processes user consent decisions (Allow/Deny) and generates authorization codes.
Sets session cookie for cross-app user identification (Increment 19).
"""

import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import urlencode, urlparse

from backend.core.database import get_db
from backend.core.logging import get_logger, mask_client_id
from backend.core.oauth_provider.cookies import get_session_cookie, set_session_cookie
from backend.core.oauth_provider.services.authorization_service import get_authorization_context
from backend.core.oauth_provider.services.consent_service import create_authorization_code, record_consent
from backend.core.oauth_provider.services.session_service import create_session, get_session_user
from backend.core.rate_limit import check_rate_limit, get_client_ip

logger = get_logger(__name__)

router = APIRouter(tags=["oauth-provider"])


def _derive_app_name_from_scopes(scopes: list[str]) -> str:
    """
    Derive app name from OAuth scopes for GDPR audit trail.

    Scope prefixes:
    - pg.* -> "priority_guardian"
    - clarity.* -> "clarity"
    - focused.* -> "focused" (default)

    Args:
        scopes: List of OAuth scopes

    Returns:
        App name string for consent records
    """
    for scope in scopes:
        if scope.startswith("pg."):
            return "priority_guardian"
        if scope.startswith("clarity."):
            return "clarity"
    return "focused"


@router.post("/oauth/focused/consent")
@router.post("/oauth/pg/consent")
async def consent_endpoint(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle user consent decision (Allow/Deny).

    Form Data:
        auth_context_id: Authorization context ID from Redis
        action: "allow" or "deny"

    Returns:
        Redirect to client's redirect_uri with:
        - code and state (if allowed)
        - error=access_denied and state (if denied)

    Flow:
        1. Parse form data (auth_context_id, action)
        2. Retrieve authorization context from Redis
        3. Delete context (single-use)
        4. If denied: redirect with error=access_denied
        5. If allowed: generate authorization code, store in DB, redirect with code

    Security Notes:
        - Authorization context is single-use (deleted after retrieval)
        - Authorization code is single-use (128 characters, cryptographically random)
        - Code expires after 10 minutes
        - PKCE challenge stored for later verification

    Example Redirect (Allow):
        https://example.com/callback?code=abc...&state=xyz

    Example Redirect (Deny):
        https://example.com/callback?error=access_denied&state=xyz
    """
    # Get correlation_id for logging
    correlation_id = request.state.correlation_id
    request_logger = logger.bind(correlation_id=correlation_id)

    # Rate limit by IP (Increment 20 - security hardening)
    # Limit raised to 100/min (matching /authorize). Rationale: consent is
    # user-initiated and a single OAuth flow can generate multiple hits from
    # the same IP, especially during testing and review.
    ip = get_client_ip(request)
    await check_rate_limit(
        key=f"ratelimit:oauth:consent:ip:{ip}",
        limit=100,
        window=60,
        request=request
    )

    # Parse form data
    form_data = await request.form()
    auth_context_id = form_data.get("auth_context_id")
    action = form_data.get("action")

    request_logger.info(
        "oauth.consent.request",
        action=action,
        auth_context_id=auth_context_id
    )

    # Validate form data
    if not auth_context_id:
        raise HTTPException(status_code=400, detail="Missing auth_context_id")

    if action not in ("allow", "deny"):
        raise HTTPException(status_code=400, detail="Invalid action")

    # Retrieve authorization context from Redis (single-use, deletes after read)
    auth_context = await get_authorization_context(
        auth_context_id,
        delete_after_read=True
    )

    if not auth_context:
        raise HTTPException(
            status_code=400,
            detail="Authorization context expired or invalid"
        )

    # Validate required fields in context
    required_fields = ["client_id", "code_challenge", "code_challenge_method", "scope", "redirect_uri", "user_id"]
    missing_fields = [f for f in required_fields if f not in auth_context or not auth_context[f]]
    if missing_fields:
        raise HTTPException(
            status_code=400,
            detail=f"Authorization context missing required fields: {', '.join(missing_fields)}"
        )

    # Extract context data
    client_id = auth_context["client_id"]
    code_challenge = auth_context["code_challenge"]
    code_challenge_method = auth_context["code_challenge_method"]
    scope = auth_context["scope"]
    state = auth_context.get("state") or None
    nonce = auth_context.get("nonce") or None
    resource = auth_context.get("resource") or None  # RFC 9728 B2-5
    redirect_uri = auth_context["redirect_uri"]
    user_id = auth_context["user_id"]

    # Handle deny
    if action == "deny":
        request_logger.info(
            "oauth.consent.denied",
            user_id=user_id,
            client_id=mask_client_id(client_id)
        )

        params = {"error": "access_denied"}
        if state:
            params["state"] = state

        deny_url = f"{redirect_uri}?{urlencode(params)}"
        return RedirectResponse(url=deny_url, status_code=302)

    # Handle allow - generate authorization code
    authorization_code = await create_authorization_code(
        db=db,
        user_id=user_id,
        client_id=client_id,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        redirect_uri=redirect_uri,
        scope=scope,
        state=state,
        nonce=nonce,
        resource=resource,  # RFC 9728 B2-5
        correlation_id=correlation_id
    )

    # Record consent for GDPR compliance (Increment 17)
    # Handle both string ("focused.read focused.write") and list formats
    scopes_list = scope.split() if isinstance(scope, str) else scope
    app_name = _derive_app_name_from_scopes(scopes_list)
    await record_consent(
        db=db,
        user_id=user_id,
        app_name=app_name,
        scopes=scopes_list,
        correlation_id=correlation_id
    )

    # =========================================================================
    # Set session cookie for cross-app user identification (Increment 19)
    # =========================================================================
    # Read existing session cookie
    existing_session_token = get_session_cookie(request)
    session_token = None

    # Prevalidate token format (64-char lowercase hex from secrets.token_hex(32))
    if existing_session_token and re.fullmatch(r"[0-9a-f]{64}", existing_session_token):
        # Validate existing session (this also extends expiry via sliding window)
        session_user_id = await get_session_user(existing_session_token, db, correlation_id)
        if session_user_id and str(session_user_id) == str(user_id):
            # Existing session is valid AND belongs to same user - reuse
            session_token = existing_session_token
            request_logger.debug(
                "oauth.consent.session_reused",
                user_id=user_id,
                session_user_id=str(session_user_id),
            )

    if not session_token:
        # No valid session - create a new one
        session_token = await create_session(user_id, db, correlation_id)
        request_logger.info(
            "oauth.consent.session_created",
            user_id=user_id,
        )

    # Redirect to client with authorization code
    params = {"code": authorization_code}
    if state:
        params["state"] = state

    success_url = f"{redirect_uri}?{urlencode(params)}"
    request_logger.info(
        "oauth.consent.redirect_prepared",
        user_id=user_id,
        auth_context_id=auth_context_id,
        redirect_host=urlparse(redirect_uri).netloc,
        redirect_path=urlparse(redirect_uri).path,
        state_present=state is not None,
        code_prefix=authorization_code[:8],
    )
    response = RedirectResponse(url=success_url, status_code=302)

    # Set session cookie on response
    set_session_cookie(response, session_token)

    return response
