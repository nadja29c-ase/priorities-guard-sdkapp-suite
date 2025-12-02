# mcp_server/focused/discovery.py

from fastapi import APIRouter
from mcp_server.focused.config import (
    OAUTH_ISSUER_URL,
    SCOPES_SUPPORTED,
)

router = APIRouter()

@router.get("/.well-known/openid-configuration")
async def openid_configuration():
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
    return {
        "issuer": OAUTH_ISSUER_URL,
        "authorization_endpoint": f"{OAUTH_ISSUER_URL}/authorize",
        "token_endpoint": f"{OAUTH_ISSUER_URL}/token",
        "jwks_uri": f"{OAUTH_ISSUER_URL}/jwks",
        "scopes_supported": SCOPES_SUPPORTED,
    }
