"""
Client Registration Endpoint - OAuth 2.1 Dynamic Client Registration.

Implements RFC 7591 client registration for ChatGPT SDK integration.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.database import get_db
from backend.core.logging import get_logger
from backend.core.rate_limit import rate_limit_register
from backend.core.oauth_provider.discovery import SCOPES_SUPPORTED
from backend.core.oauth_provider.services.client_service import create_oauth_client
from backend.core.oauth_provider.validators.client_metadata import (
    validate_client_name,
    validate_redirect_uris,
    validate_grant_types
)

logger = get_logger(__name__)

router = APIRouter(tags=["oauth-provider"])


class RegisterRequest(BaseModel):
    """OAuth client registration request."""
    client_name: str
    redirect_uris: list[str]
    grant_types: list[str] | None = None
    scope: str | None = None  # Space-separated list of requested scopes


# Supported scopes derived from discovery (single source of truth)
# Prevents drift between what's advertised and what's accepted
SUPPORTED_SCOPES = set(SCOPES_SUPPORTED)

# Route-specific defaults (least privilege principle)
# - /oauth/focused/register: Focused app scopes only (backward compatibility)
# - /oauth/pg/register: PG suite scopes (each MCP server advertises only its own scopes)
DEFAULT_SCOPES_FOCUSED = ["focused.read", "focused.write", "focused.notify"]
DEFAULT_SCOPES_PG = ["pg.access"]  # Default for Priority Guardian suite


@router.post("/oauth/focused/register")
@router.post("/oauth/pg/register")
async def register_endpoint(
    request: Request,
    register_request: RegisterRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    OAuth 2.1 dynamic client registration endpoint.

    Registers a new OAuth client and returns credentials.

    Routes:
        /oauth/focused/register: Focused app clients (defaults to focused.* scopes)
        /oauth/pg/register: Priority Guardian clients (defaults to pg.access)

    Request Body:
        client_name: Human-readable client name
        redirect_uris: Array of allowed redirect URIs (must use HTTPS)
        grant_types: Optional array of allowed grant types (default: authorization_code, refresh_token)
        scope: Optional space-separated scopes (defaults per route if omitted)

    Returns:
        client_id: Generated client identifier (pg-client-{uuid})
        client_secret: Generated client secret (32-byte URL-safe token)
        redirect_uris: Registered redirect URIs
        scope: Allowed scopes

    Security Notes:
        - client_secret is only returned once (never stored in plain text)
        - Client must store client_secret securely
        - redirect_uris must be in allowlist (RFC 9728 B2-8):
          - https://chatgpt.com/connector_platform_oauth_redirect
          - https://platform.openai.com/apps-manage/oauth
          - (localhost URIs allowed in dev mode only)
        - Rate limited to prevent abuse
        - Least privilege: each route has minimal default scopes

    Example Response:
        {
            "client_id": "pg-client-12345678-1234-1234-1234-123456789abc",
            "client_secret": "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
            "redirect_uris": ["https://chat.openai.com/aip/callback"],
            "scope": "pg.access"
        }
    """
    # Get correlation_id for logging
    correlation_id = request.state.correlation_id
    request_logger = logger.bind(correlation_id=correlation_id)

    # Rate limit check
    await rate_limit_register(request)

    # Validate client_name
    valid, error = validate_client_name(register_request.client_name)
    if not valid:
        raise HTTPException(status_code=400, detail=error)

    # Validate redirect_uris against allowlist (RFC 9728 B2-8)
    valid, error = validate_redirect_uris(
        register_request.redirect_uris,
        allowed_uris=settings.OAUTH_ALLOWED_REDIRECT_URIS
    )
    if not valid:
        raise HTTPException(status_code=400, detail=error)

    # Validate grant_types
    valid, error = validate_grant_types(register_request.grant_types)
    if not valid:
        raise HTTPException(status_code=400, detail=error)

    # Set default grant types
    grant_types = register_request.grant_types or ["authorization_code", "refresh_token"]

    # Determine route-specific default scopes (least privilege)
    route_path = request.url.path
    if route_path == "/oauth/focused/register":
        default_scopes = DEFAULT_SCOPES_FOCUSED
    else:
        # /oauth/pg/register: PG suite defaults (ChatGPT doesn't send scope param)
        default_scopes = DEFAULT_SCOPES_PG

    # Parse and validate requested scopes
    # Normalize: treat whitespace-only as "no scope provided"
    scope_str = (register_request.scope or "").strip()
    if scope_str:
        requested_scopes = scope_str.split()
        invalid_scopes = set(requested_scopes) - SUPPORTED_SCOPES
        if invalid_scopes:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported scopes: {', '.join(sorted(invalid_scopes))}"
            )
        scopes = list(set(requested_scopes))  # Remove duplicates
        request_logger.info(
            "oauth.register.scopes_requested",
            requested_scope=scope_str[:200],  # Truncate to prevent log spam
            parsed_scopes=sorted(scopes)  # Log in sorted order for readability
        )
    else:
        # No scope provided - use route-specific defaults
        scopes = default_scopes.copy()
        request_logger.info(
            "oauth.register.scopes_default",
            route=route_path,
            default_scopes=scopes
        )

    # Sort scopes once for deterministic storage and response
    scopes = sorted(scopes)

    # Create OAuth client (handles encryption and DB persistence)
    client_id, client_secret = await create_oauth_client(
        db=db,
        client_name=register_request.client_name,
        redirect_uris=register_request.redirect_uris,
        grant_types=grant_types,
        scopes=scopes,
        correlation_id=correlation_id
    )

    # Return client credentials (client_secret only shown once)
    return JSONResponse({
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uris": register_request.redirect_uris,
        "scope": " ".join(scopes)  # Already sorted above
    })
