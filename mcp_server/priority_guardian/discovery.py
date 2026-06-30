# mcp_server/priority_guardian/discovery.py
"""
OAuth Discovery Endpoints for Priority Guardian MCP Server.

Provides all required OAuth discovery endpoints:
- oauth-authorization-server (RFC 8414)
- oauth-protected-resource (RFC 9728)
- openid-configuration (OpenID Connect Discovery)

ChatGPT queries the MCP server directly for AS metadata and requires
issuer + all endpoints to share the same origin. The MCP server proxies
OAuth requests to the backend (www.priority-guard.com) transparently.

NOTE (production incident 2026-06-30): This file was reverted to its
pre-5854d50 shape. Commit 5854d50 ("Fix AS discovery: all endpoints point
to www") changed token/jwks/register endpoints and authorization_servers
from the MCP origin (pg) to the backend root (www) "for consistency." That
broke the same-origin token-exchange chain ChatGPT depends on: ChatGPT
discovers the AS via authorization_servers, then calls token/jwks/register
on that same origin. Pointing those at www (a different origin than the
advertised authorization_servers root) caused ChatGPT to complete OAuth but
silently abandon the connection before calling /mcp. MindSort (OpenAI) was
unaffected because it advertises an app-specific path issuer that resolves.
The working design is deliberately MIXED-origin (see field comments below);
do not "consolidate" these origins without reproducing a full ChatGPT
reconnect first.
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
        # authorization_endpoint points directly to backend — it's opened in a browser
        # popup and has no same-origin restriction. Proxying HTML through MCP server
        # causes encoding issues; backend serves it correctly.
        "authorization_endpoint": f"{OAUTH_ISSUER_BASE}/oauth/pg/authorize",
        "token_endpoint": f"{MCP_SERVER_URL}/oauth/token",
        "jwks_uri": f"{MCP_SERVER_URL}/oauth/jwks",
        "registration_endpoint": f"{MCP_SERVER_URL}/oauth/register",
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
        # authorization_endpoint points directly to backend — it's opened in a browser
        # popup and has no same-origin restriction. Proxying HTML through MCP server
        # causes encoding issues; backend serves it correctly.
        "authorization_endpoint": f"{OAUTH_ISSUER_BASE}/oauth/pg/authorize",
        "token_endpoint": f"{MCP_SERVER_URL}/oauth/token",
        "jwks_uri": f"{MCP_SERVER_URL}/oauth/jwks",
        "registration_endpoint": f"{MCP_SERVER_URL}/oauth/register",
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
        "authorization_servers": [MCP_SERVER_URL],
        "scopes_supported": SCOPES_SUPPORTED,
    }
