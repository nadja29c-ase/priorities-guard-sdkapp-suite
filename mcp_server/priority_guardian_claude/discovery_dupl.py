# (duplicate) — exists because it imports platform-specific config.
#
# !! ITS CONTENTS ARE NOT A COPY. Verified 2026-08-09 by symbol-level sweep: this
# file has diverged STRUCTURALLY from the source named below, and not every
# divergence is documented. Do not assume a symbol here behaves as its namesake
# does there — and note that a symbol may be ABSENT here entirely. That is exactly
# how A22 happened: BearerAuthMiddleware dropped JWT validation, scope enforcement
# and the 413 guard while this header claimed a config-only difference.
# See doc/DUPL_DIVERGENCE_SWEEP_2026-08-09.md.
# Logic lives in mcp_server/priority_guardian/discovery.py.
# Post-OpenAI-approval refactor: move shared logic to mcp_server/shared/
# with config injection and delete this file.

# mcp_server/priority_guardian_claude/discovery_dupl.py
"""
OAuth Discovery Endpoints for Priority Guardian Claude MCP Server.

Provides all required OAuth discovery endpoints:
- oauth-authorization-server (RFC 8414)
- oauth-protected-resource (RFC 9728)
- openid-configuration (OpenID Connect Discovery)

www.priority-guard.com is the Authorization Server (AS).
mcp.priority-guard.com is the Resource Server (RS).

PLATFORM-SPECIFIC SHAPE (Claude — Shape #3 per ADR_005):
All AS metadata endpoints point to www (root issuer) because Claude's
RFC 8414/9728-literal discovery chain requires authorization_servers to
match the AS's self-declared issuer (root). This is CORRECT for Claude,
but would be FATAL for ChatGPT — never port this shape to the OpenAI twin
(mcp_server/priority_guardian/discovery.py uses a different mixed-origin
shape required by ChatGPT's same-origin discovery→token chain).

See:
- doc/ADR/ADR_005_platform_oauth_discovery_contracts.md
- claude increments/SHARED ARCHITECTURE/hotfix_pg_openai_discovery_restore.md
"""

from mcp_server.priority_guardian_claude.config import (
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
