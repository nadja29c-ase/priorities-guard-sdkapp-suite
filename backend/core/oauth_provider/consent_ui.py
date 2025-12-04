"""
Consent UI Endpoint - OAuth 2.1 user consent handling.

Processes user consent decisions (Allow/Deny) and generates authorization codes.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import urlencode

from backend.core.database import get_db
from backend.core.logging import get_logger
from backend.core.oauth_provider.services.authorization_service import get_authorization_context
from backend.core.oauth_provider.services.consent_service import create_authorization_code, record_consent

logger = get_logger(__name__)

router = APIRouter(tags=["oauth-provider"])


@router.post("/oauth/focused/consent")
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
    redirect_uri = auth_context["redirect_uri"]
    user_id = auth_context["user_id"]

    # Handle deny
    if action == "deny":
        request_logger.info(
            "oauth.consent.denied",
            user_id=user_id,
            client_id=client_id
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
        correlation_id=correlation_id
    )

    # Record consent for GDPR compliance (Increment 17)
    # Handle both string ("focused.read focused.write") and list formats
    scopes_list = scope.split() if isinstance(scope, str) else scope
    app_name = auth_context.get("app_name", "focused")  # Default to "focused" for backwards compatibility
    await record_consent(
        db=db,
        user_id=user_id,
        app_name=app_name,
        scopes=scopes_list,
        correlation_id=correlation_id
    )

    # Redirect to client with authorization code
    params = {"code": authorization_code}
    if state:
        params["state"] = state

    success_url = f"{redirect_uri}?{urlencode(params)}"
    return RedirectResponse(url=success_url, status_code=302)
