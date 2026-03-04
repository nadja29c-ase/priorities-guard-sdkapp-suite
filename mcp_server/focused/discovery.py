# mcp_server/focused/discovery.py
"""
OAuth Discovery Endpoints (Increment 15).

Single source of truth for all OAuth/.well-known discovery responses.
Starlette wrappers in server.py call these functions.
"""

from fastapi import APIRouter
from mcp_server.focused.config import (
    MCP_SERVER_URL,
    OAUTH_ISSUER_URL,
    SCOPES_SUPPORTED,
)

router = APIRouter()


@router.get("/.well-known/openid-configuration")
async def openid_configuration():
    """OpenID Connect Discovery (RFC 8414)."""
    return {
        "issuer": OAUTH_ISSUER_URL,
        "authorization_endpoint": f"{OAUTH_ISSUER_URL}/authorize",
        "token_endpoint": f"{OAUTH_ISSUER_URL}/token",
        "jwks_uri": f"{OAUTH_ISSUER_URL}/jwks",
        "registration_endpoint": f"{OAUTH_ISSUER_URL}/register",
        "scopes_supported": SCOPES_SUPPORTED,
    }


@router.get("/.well-known/oauth-authorization-server")
async def oauth_authorization_server():
    """OAuth 2.0 Authorization Server Metadata (RFC 8414)."""
    return {
        "issuer": OAUTH_ISSUER_URL,
        "authorization_endpoint": f"{OAUTH_ISSUER_URL}/authorize",
        "token_endpoint": f"{OAUTH_ISSUER_URL}/token",
        "jwks_uri": f"{OAUTH_ISSUER_URL}/jwks",
        "registration_endpoint": f"{OAUTH_ISSUER_URL}/register",
        "scopes_supported": SCOPES_SUPPORTED,
    }


@router.get("/.well-known/oauth-protected-resource")
async def oauth_protected_resource():
    """OAuth 2.0 Protected Resource Metadata (RFC 9728)."""
    return {
        "resource": MCP_SERVER_URL,
        "authorization_servers": [OAUTH_ISSUER_URL],
        "scopes_supported": SCOPES_SUPPORTED,
    }
