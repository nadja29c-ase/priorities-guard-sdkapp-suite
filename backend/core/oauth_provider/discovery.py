"""
Discovery Endpoints - OAuth 2.1 and OpenID Connect discovery.

Provides metadata endpoints for OAuth client discovery:
- OpenID Connect Discovery (/.well-known/openid-configuration)
- OAuth Authorization Server Metadata (/.well-known/oauth-authorization-server)

NOTE: oauth-protected-resource is NOT served here. Each MCP server
publishes its own /.well-known/oauth-protected-resource with the
correct resource URL for that specific MCP server.

Supports scopes for Priority Guardian (pg.access).
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.core.config import settings

router = APIRouter(tags=["oauth-provider"])

# Supported scopes advertised in discovery (exported for testing)
# Only Priority Guardian scope - Focused deprecated, Clarity rejected
SCOPES_SUPPORTED = ["pg.access"]


def _authorization_server_metadata() -> dict:
    """
    Build OAuth authorization server metadata dict.

    Shared by both openid-configuration and oauth-authorization-server
    endpoints to guarantee they never drift.
    """
    return {
        "issuer": settings.OAUTH_ISSUER,
        "authorization_endpoint": f"{settings.OAUTH_ISSUER}/oauth/pg/authorize",
        "token_endpoint": f"{settings.OAUTH_ISSUER}/oauth/pg/token",
        "jwks_uri": f"{settings.OAUTH_ISSUER}/oauth/pg/jwks",
        "registration_endpoint": f"{settings.OAUTH_ISSUER}/oauth/pg/register",
        "scopes_supported": SCOPES_SUPPORTED,
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
    }


@router.get("/.well-known/openid-configuration")
async def openid_configuration():
    """
    OpenID Connect Discovery endpoint.

    Returns OAuth provider configuration for ChatGPT discovery.

    Returns:
        JSONResponse: OpenID Connect discovery document

    Example Response:
        {
            "issuer": "https://api.example.com",
            "authorization_endpoint": "https://api.example.com/oauth/pg/authorize",
            "token_endpoint": "https://api.example.com/oauth/pg/token",
            "jwks_uri": "https://api.example.com/oauth/pg/jwks",
            ...
        }
    """
    return JSONResponse(_authorization_server_metadata())


@router.get("/.well-known/oauth-authorization-server")
async def oauth_authorization_server():
    """
    OAuth 2.0 Authorization Server Metadata endpoint (RFC 8414).

    Returns the same metadata as openid-configuration. Both endpoints
    use the shared _authorization_server_metadata() helper to guarantee
    they never drift.

    Returns:
        JSONResponse: OAuth authorization server metadata document
    """
    return JSONResponse(_authorization_server_metadata())
