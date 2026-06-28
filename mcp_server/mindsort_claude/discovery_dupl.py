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


# DEFERRED (MindSort-wide, post-OpenAI-review): authorization_servers advertises
# OAUTH_ISSUER_URL (path-qualified, .../oauth/pg) while the backend AS declares
# issuer = https://www.priority-guard.com (root, no path). RFC 8414/9728 expect the
# authorization_servers entry to match the AS's self-declared issuer. The in-review
# ChatGPT server (clarity/discovery.py) has the IDENTICAL behavior, so this is shared
# MindSort behavior, not a Claude-port defect. Fixing it Claude-only would diverge from
# ChatGPT MindSort (violates Canonical Product Rule §0) and is an unverified change to
# the OAuth surface. Evaluate for BOTH platforms together after OpenAI review clears,
# with a real OAuth client test. Do not fix in isolation.
async def oauth_protected_resource():
    """OAuth 2.0 Protected Resource Metadata (RFC 9728)."""
    return {
        "resource": MCP_RESOURCE_URL,
        "authorization_servers": [OAUTH_ISSUER_URL],
        "scopes_supported": SCOPES_SUPPORTED,
    }
