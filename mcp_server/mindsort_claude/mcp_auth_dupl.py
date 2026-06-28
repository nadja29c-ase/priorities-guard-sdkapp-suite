# (duplicate) — exists only because it imports platform-specific config.
# Mirrors mcp_server/clarity/mcp_auth.py. Maintain alongside; consolidate only on demonstrated churn.

import mcp_server.clarity.mcp_auth as _shared

from mcp_server.mindsort_claude.config import (
    CLARITY_JWKS_URL,
    CLARITY_ISSUER,
    CLARITY_AUDIENCE,
    MCP_SERVER_URL,
    TOOL_SCOPES,
    TOKEN_EXPIRY_GRACE_SECONDS,
    JWKS_CACHE_TTL_SECONDS,
    JWKS_MAX_STALE_SECONDS,
    JWKS_FETCH_TIMEOUT_SECONDS,
)

# Rebind config-dependent module globals to Claude platform values
_shared.CLARITY_JWKS_URL = CLARITY_JWKS_URL
_shared.CLARITY_ISSUER = CLARITY_ISSUER
_shared.CLARITY_AUDIENCE = CLARITY_AUDIENCE
_shared.MCP_SERVER_URL = MCP_SERVER_URL
_shared.TOOL_SCOPES = TOOL_SCOPES
_shared.TOKEN_EXPIRY_GRACE_SECONDS = TOKEN_EXPIRY_GRACE_SECONDS
_shared.JWKS_CACHE_TTL_SECONDS = JWKS_CACHE_TTL_SECONDS
_shared.JWKS_MAX_STALE_SECONDS = JWKS_MAX_STALE_SECONDS
_shared.JWKS_FETCH_TIMEOUT_SECONDS = JWKS_FETCH_TIMEOUT_SECONDS

# Re-export everything callers need
from mcp_server.clarity.mcp_auth import (  # noqa: E402, F401
    authenticate_request,
    cleanup_jwks_cache,
    build_unauthorized_meta,
    build_forbidden_meta,
    UnauthorizedError,
    InsufficientScopeError,
    JWKSCache,
)
