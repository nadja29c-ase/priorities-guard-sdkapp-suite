"""
OAuth Discovery Endpoints for Clarity MCP Server.

Provides all required OAuth discovery endpoints:
- oauth-authorization-server (RFC 8414)
- oauth-protected-resource (RFC 9728)
- openid-configuration (OpenID Connect Discovery)
"""

from mcp_server.clarity.config import (
    CLARITY_ISSUER,
    MCP_SERVER_URL,
    OAUTH_ISSUER_URL,
    SCOPES_SUPPORTED,
)


async def openid_configuration():
    """OpenID Connect Discovery (RFC 8414)."""
    return {
        "issuer": CLARITY_ISSUER,
        "authorization_endpoint": f"{OAUTH_ISSUER_URL}/authorize",
        "token_endpoint": f"{OAUTH_ISSUER_URL}/token",
        "jwks_uri": f"{OAUTH_ISSUER_URL}/jwks",
        "registration_endpoint": f"{OAUTH_ISSUER_URL}/register",
        "scopes_supported": SCOPES_SUPPORTED,
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none"],
        "code_challenge_methods_supported": ["S256"],
    }


async def oauth_authorization_server():
    """OAuth 2.0 Authorization Server Metadata (RFC 8414)."""
    return {
        "issuer": CLARITY_ISSUER,
        "authorization_endpoint": f"{OAUTH_ISSUER_URL}/authorize",
        "token_endpoint": f"{OAUTH_ISSUER_URL}/token",
        "jwks_uri": f"{OAUTH_ISSUER_URL}/jwks",
        "registration_endpoint": f"{OAUTH_ISSUER_URL}/register",
        "scopes_supported": SCOPES_SUPPORTED,
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none"],
        "code_challenge_methods_supported": ["S256"],
    }


async def oauth_protected_resource():
    """OAuth 2.0 Protected Resource Metadata (RFC 9728)."""
    return {
        "resource": f"{MCP_SERVER_URL}/mcp",
        "authorization_servers": [CLARITY_ISSUER],
        "scopes_supported": SCOPES_SUPPORTED,
    }
