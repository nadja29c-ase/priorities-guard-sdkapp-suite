# (duplicate) — exists because it imports platform-specific config.
#
# !! ITS CONTENTS ARE NOT A COPY. Verified 2026-08-09 by symbol-level sweep: this
# file has diverged STRUCTURALLY from the source named below, and not every
# divergence is documented. Do not assume a symbol here behaves as its namesake
# does there — and note that a symbol may be ABSENT here entirely. That is exactly
# how A22 happened: BearerAuthMiddleware dropped JWT validation, scope enforcement
# and the 413 guard while this header claimed a config-only difference.
# See doc/DUPL_DIVERGENCE_SWEEP_2026-08-09.md.
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
    OAUTH_ISSUER_BASE,
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


# FIX (inc_05): authorization_servers now advertises root issuer instead of
# path-qualified OAUTH_ISSUER_URL. This satisfies Claude's RFC 8414/9728 DCR
# discovery chain, which expects authorization_servers to match the AS's
# self-declared issuer (root).
#
# HARDENING (inc_05b): authorization_servers now sourced from dedicated
# OAUTH_ISSUER_BASE config value (not CLARITY_ISSUER). Both hold the same
# production value, but OAUTH_ISSUER_BASE is semantically correct for discovery
# while CLARITY_ISSUER is for JWT validation. The same-origin guard in config.py
# prevents future drift between OAUTH_ISSUER_BASE and OAUTH_ISSUER_URL.
#
# This does NOT violate Canonical Product Rule §0: this is the platform-coupled
# _dupl Claude file; the ChatGPT server (clarity/discovery.py) is untouched.
async def oauth_protected_resource():
    """OAuth 2.0 Protected Resource Metadata (RFC 9728)."""
    return {
        "resource": MCP_RESOURCE_URL,
        "authorization_servers": [OAUTH_ISSUER_BASE],
        "scopes_supported": SCOPES_SUPPORTED,
    }
