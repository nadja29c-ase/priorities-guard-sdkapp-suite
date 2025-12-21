"""
Discovery Endpoints - OAuth 2.1 and OpenID Connect discovery.

Provides metadata endpoints for OAuth client discovery:
- OpenID Connect Discovery (/.well-known/openid-configuration)

NOTE: oauth-protected-resource is NOT served here. Each MCP server
publishes its own /.well-known/oauth-protected-resource with the
correct resource URL for that specific MCP server.

Supports scopes for all Priority Guardian apps:
- focused.* (Focused app)
- clarity.* (Clarity app)
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.core.config import settings

router = APIRouter(tags=["oauth-provider"])

# Supported scopes advertised in discovery (exported for testing)
# Sorted alphabetically for stable diffs and cleaner ordering
SCOPES_SUPPORTED = sorted([
    "clarity.write",
    "focused.notify",
    "focused.read",
    "focused.write",
])


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
    return JSONResponse({
        "issuer": settings.OAUTH_ISSUER,
        "authorization_endpoint": f"{settings.OAUTH_ISSUER}/oauth/pg/authorize",
        "token_endpoint": f"{settings.OAUTH_ISSUER}/oauth/pg/token",
        "jwks_uri": f"{settings.OAUTH_ISSUER}/oauth/pg/jwks",
        "registration_endpoint": f"{settings.OAUTH_ISSUER}/oauth/pg/register",
        "scopes_supported": SCOPES_SUPPORTED,
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"]
    })
