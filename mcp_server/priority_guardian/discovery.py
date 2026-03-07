# mcp_server/priority_guardian/discovery.py
"""
OAuth Discovery Endpoints for Priority Guardian MCP Server.

Provides all required OAuth discovery endpoints:
- oauth-authorization-server (RFC 8414)
- oauth-protected-resource (RFC 9728)
- openid-configuration (OpenID Connect Discovery)

www.priority-guard.com is the Authorization Server (AS).
pg.priority-guard.com is the Resource Server (RS).
All AS metadata endpoints point to www for consistency.
"""

from mcp_server.priority_guardian.config import (
    MCP_SERVER_URL,
    MCP_RESOURCE_URL,
    OAUTH_ISSUER_BASE,
    SCOPES_SUPPORTED,
)


async def openid_configuration():
    """OpenID Connect Discovery (RFC 8414)."""
    return {
        "issuer": OAUTH_ISSUER_BASE,
        "authorization_endpoint": f"{OAUTH_ISSUER_BASE}/oauth/pg/authorize",
        "token_endpoint": f"{OAUTH_ISSUER_BASE}/oauth/pg/token",
        "jwks_uri": f"{OAUTH_ISSUER_BASE}/oauth/pg/jwks",
        "registration_endpoint": f"{OAUTH_ISSUER_BASE}/oauth/pg/register",
        "scopes_supported": SCOPES_SUPPORTED,
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
    }


async def oauth_authorization_server():
    """OAuth 2.0 Authorization Server Metadata (RFC 8414)."""
    return {
        "issuer": OAUTH_ISSUER_BASE,
        "authorization_endpoint": f"{OAUTH_ISSUER_BASE}/oauth/pg/authorize",
        "token_endpoint": f"{OAUTH_ISSUER_BASE}/oauth/pg/token",
        "jwks_uri": f"{OAUTH_ISSUER_BASE}/oauth/pg/jwks",
        "registration_endpoint": f"{OAUTH_ISSUER_BASE}/oauth/pg/register",
        "scopes_supported": SCOPES_SUPPORTED,
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
    }


async def oauth_protected_resource():
    """OAuth 2.0 Protected Resource Metadata (RFC 9728)."""
    return {
        "resource": MCP_RESOURCE_URL,
        "authorization_servers": [OAUTH_ISSUER_BASE],
        "scopes_supported": SCOPES_SUPPORTED,
    }
