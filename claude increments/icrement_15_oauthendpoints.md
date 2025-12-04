Claude Code Briefing — Implement Missing OAuth Discovery Endpoints

Implement the following three discovery endpoints at the MCP server root and under the /mcp prefix:

Required endpoints:

/.well-known/openid-configuration

/.well-known/oauth-authorization-server

/.well-known/oauth-protected-resource (already implemented but only at root; must also be under /mcp)

ChatGPT expects ALL SIX paths to resolve:

root:
/.well-known/openid-configuration,
/.well-known/oauth-authorization-server,
/.well-known/oauth-protected-resource

prefixed:
/mcp/.well-known/openid-configuration,
/mcp/.well-known/oauth-authorization-server,
/mcp/.well-known/oauth-protected-resource

If any return 404 → OAuth flow aborts.

1. Create mcp_server/focused/discovery.py
from fastapi import APIRouter
from mcp_server.focused.config import OAUTH_ISSUER_URL, SCOPES_SUPPORTED, MCP_SERVER_URL

router = APIRouter()

@router.get("/.well-known/openid-configuration")
async def openid_config():
    return {
        "issuer": OAUTH_ISSUER_URL,
        "authorization_endpoint": f"{OAUTH_ISSUER_URL}/authorize",
        "token_endpoint": f"{OAUTH_ISSUER_URL}/token",
        "jwks_uri": f"{OAUTH_ISSUER_URL}/jwks",
        "registration_endpoint": f"{OAUTH_ISSUER_URL}/register",
        "scopes_supported": SCOPES_SUPPORTED
    }

@router.get("/.well-known/oauth-authorization-server")
async def oauth_authz_server():
    return {
        "issuer": OAUTH_ISSUER_URL,
        "authorization_endpoint": f"{OAUTH_ISSUER_URL}/authorize",
        "token_endpoint": f"{OAUTH_ISSUER_URL}/token",
        "jwks_uri": f"{OAUTH_ISSUER_URL}/jwks",
        "scopes_supported": SCOPES_SUPPORTED
    }

@router.get("/.well-known/oauth-protected-resource")
async def oauth_protected_resource():
    return {
        "resource": MCP_SERVER_URL,
        "authorization_servers": [OAUTH_ISSUER_URL],
        "scopes_supported": SCOPES_SUPPORTED
    }

2. Register the discovery router in your MCP server (server.py)

Inside create_app(), mount the router twice:

from mcp_server.focused.discovery import router as discovery_router

return Starlette(
    routes=[
        # required: discovery endpoints at root and /mcp
        Mount("/", app=discovery_router),
        Mount("/mcp", app=discovery_router),

        # existing fastmcp app
        Mount("/", app=fastmcp_asgi),
    ],
    lifespan=combined_lifespan
)

3. After deployment, verify these URLs return JSON (200 OK):

Root paths:

/.well-known/openid-configuration

/.well-known/oauth-authorization-server

/.well-known/oauth-protected-resource

Prefixed paths:

/mcp/.well-known/openid-configuration

/mcp/.well-known/oauth-authorization-server

/mcp/.well-known/oauth-protected-resource

All must work.

If any return 404 → ChatGPT rejects the connector.