"""
OAuth Discovery Endpoint for Clarity MCP Server.

Only provides oauth-protected-resource metadata.
OpenID/authorization server discovery belongs to the backend OAuth provider,
not the MCP resource server.
"""

from mcp_server.clarity.config import (
    MCP_SERVER_URL,
    OAUTH_ISSUER_URL,
    SCOPES_SUPPORTED,
)


async def oauth_protected_resource():
    """OAuth 2.0 Protected Resource Metadata (RFC 9728)."""
    return {
        "resource": MCP_SERVER_URL,
        "authorization_servers": [OAUTH_ISSUER_URL],
        "scopes_supported": SCOPES_SUPPORTED,
    }
