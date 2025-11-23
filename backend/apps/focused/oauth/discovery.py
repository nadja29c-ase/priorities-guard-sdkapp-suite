"""
Discovery Endpoints - OAuth 2.1 and OpenID Connect discovery.

Provides metadata endpoints for OAuth client discovery:
- OpenID Connect Discovery (/.well-known/openid-configuration)
- OAuth Protected Resource Metadata (/.well-known/oauth-protected-resource)
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.core.config import settings

router = APIRouter(tags=["oauth-provider"])


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
            "authorization_endpoint": "https://api.example.com/oauth/focused/authorize",
            "token_endpoint": "https://api.example.com/oauth/focused/token",
            "jwks_uri": "https://api.example.com/oauth/focused/jwks",
            ...
        }
    """
    return JSONResponse({
        "issuer": settings.OAUTH_ISSUER,
        "authorization_endpoint": f"{settings.OAUTH_ISSUER}/oauth/focused/authorize",
        "token_endpoint": f"{settings.OAUTH_ISSUER}/oauth/focused/token",
        "jwks_uri": f"{settings.OAUTH_ISSUER}/oauth/focused/jwks",
        "registration_endpoint": f"{settings.OAUTH_ISSUER}/oauth/focused/register",
        "scopes_supported": ["focused.read", "focused.write", "focused.notify"],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"]
    })


@router.get("/.well-known/oauth-protected-resource")
async def oauth_protected_resource():
    """
    OAuth Protected Resource Metadata endpoint.

    Describes the MCP server resource and scopes.

    Returns:
        JSONResponse: Protected resource metadata

    Example Response:
        {
            "resource": "https://api.example.com/mcp/focused",
            "authorization_servers": ["https://api.example.com"],
            "scopes": {
                "focused.read": "Read calendar sync status and focus analytics",
                ...
            }
        }
    """
    return JSONResponse({
        "resource": f"{settings.OAUTH_ISSUER}/mcp/focused",
        "authorization_servers": [settings.OAUTH_ISSUER],
        "scopes": {
            "focused.read": "Read calendar sync status and focus analytics",
            "focused.write": "Activate Focus Mode and modify settings",
            "focused.notify": "Send push notifications"
        }
    })
