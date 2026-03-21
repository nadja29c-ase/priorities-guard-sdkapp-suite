# (duplicate) — exists only because it imports platform-specific config.
# Logic lives in mcp_server/priority_guardian/mcp_auth.py.
# Post-OpenAI-approval refactor: move shared logic to mcp_server/shared/
# with config injection and delete this file.

import mcp_server.priority_guardian.mcp_auth as _shared

from mcp_server.priority_guardian_claude.config import (
    PG_JWKS_URL,
    PG_ISSUER,
    PG_AUDIENCE,
    MCP_SERVER_URL,
    MCP_RESOURCE_URL,
    JWKS_CACHE_TTL_SECONDS,
    JWKS_MAX_STALE_SECONDS,
    JWKS_FETCH_TIMEOUT_SECONDS,
    TOKEN_EXPIRY_GRACE_SECONDS,
)

# Rebind config-dependent module globals to Claude platform values
_shared.PG_JWKS_URL = PG_JWKS_URL
_shared.PG_ISSUER = PG_ISSUER
_shared.PG_AUDIENCE = PG_AUDIENCE
_shared.MCP_SERVER_URL = MCP_SERVER_URL
_shared.MCP_RESOURCE_URL = MCP_RESOURCE_URL
_shared._MCP_ORIGIN = _shared._extract_origin(MCP_SERVER_URL)
_shared.JWKS_CACHE_TTL_SECONDS = JWKS_CACHE_TTL_SECONDS
_shared.JWKS_MAX_STALE_SECONDS = JWKS_MAX_STALE_SECONDS
_shared.JWKS_FETCH_TIMEOUT_SECONDS = JWKS_FETCH_TIMEOUT_SECONDS
_shared.TOKEN_EXPIRY_GRACE_SECONDS = TOKEN_EXPIRY_GRACE_SECONDS

# Re-export everything callers need
from mcp_server.priority_guardian.mcp_auth import (  # noqa: E402, F401
    authenticate_request,
    cleanup_jwks_cache,
    build_unauthorized_meta,
    build_forbidden_meta,
    UnauthorizedError,
    InsufficientScopeError,
    JWKSCache,
)
