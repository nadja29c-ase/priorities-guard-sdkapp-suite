# (duplicate) — exists only because it imports platform-specific config.
# Mirrors mcp_server/clarity/discovery.py. Maintain alongside; consolidate only on demonstrated churn.

"""
OAuth Discovery Endpoints for MindSort Claude MCP Server.

Provides all required OAuth discovery endpoints:
- oauth-authorization-server (RFC 8414)
- oauth-protected-resource (RFC 9728)
- openid-configuration (OpenID Connect Discovery)
"""

from mcp_server.mindsort_claude.config import (
    CLARITY_ISSUER,
    MCP_RESOURCE_URL,
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


# FIX (inc_05): authorization_servers now advertises CLARITY_ISSUER (root issuer,
# https://www.priority-guard.com) instead of OAUTH_ISSUER_URL (path-qualified,
# .../oauth/pg). This satisfies Claude's RFC 8414/9728 DCR discovery chain, which
# expects authorization_servers to match the AS's self-declared issuer (root).
#
# This does NOT violate Canonical Product Rule §0: this is the platform-coupled
# _dupl Claude file; the ChatGPT server (clarity/discovery.py) is untouched and
# retains its behavior. Structural hardening (dedicated OAUTH_ISSUER_BASE +
# same-origin guard, mirroring PG) is tracked as inc_05b, to run after the
# connection is confirmed.
async def oauth_protected_resource():
    """OAuth 2.0 Protected Resource Metadata (RFC 9728)."""
    return {
        "resource": MCP_RESOURCE_URL,
        "authorization_servers": [CLARITY_ISSUER],
        "scopes_supported": SCOPES_SUPPORTED,
    }
