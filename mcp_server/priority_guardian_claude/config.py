"""
Configuration for Priority Guardian Claude MCP Server.

Centralizes all MCP-specific settings including JWT validation,
JWKS fetching, and OAuth client configuration.

Required Render env vars for production:
- PG_CLAUDE_MCP_SERVER_URL (e.g., https://pg-claude.priority-guard.com)
- PG_CLAUDE_MCP_RESOURCE_URL (e.g., https://pg-claude.priority-guard.com/mcp)
- PG_CLAUDE_OAUTH_ISSUER_URL (e.g., https://www.priority-guard.com/oauth/pg)
- PG_CLAUDE_OAUTH_ISSUER_BASE (e.g., https://www.priority-guard.com)
- PG_CLAUDE_BACKEND_URL (e.g., https://www.priority-guard.com)
- PG_CLAUDE_INTERNAL_API_SECRET (shared secret with backend)
- PG_CLAUDE_JWKS_URL (e.g., https://www.priority-guard.com/oauth/pg/jwks)
- PG_CLAUDE_ISSUER (e.g., https://www.priority-guard.com)
- PG_CLAUDE_AUDIENCE (e.g., https://www.priority-guard.com)
- PG_CLAUDE_CORS_ALLOWED_ORIGINS (e.g., https://claude.ai)

Optional Render env vars (have sensible defaults):
- PG_CLAUDE_TOKEN_EXPIRY_GRACE_SECONDS (default: 30)
- PG_CLAUDE_JWKS_CACHE_TTL_SECONDS (default: 86400 = 24h)
- PG_CLAUDE_JWKS_MAX_STALE_SECONDS (default: 604800 = 7d)
- PG_CLAUDE_JWKS_FETCH_TIMEOUT_SECONDS (default: 5)
"""

import os
from typing import Optional
from urllib.parse import urlparse


# ============================================================================
# Environment Detection (evaluated once at module load)
# ============================================================================

ENV = os.getenv("ENV", "dev")


# ============================================================================
# Helper Functions
# ============================================================================

def get_env(key: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    """
    Get environment variable with optional default and requirement check.

    Args:
        key: Environment variable name
        default: Default value if not set
        required: If True, raise error if not set and no default

    Returns:
        Environment variable value

    Raises:
        RuntimeError: If required=True and variable not set
    """
    value = os.getenv(key, default)

    if required and value is None:
        # In production, critical configs must be set
        if ENV in ("production", "prod", "staging"):
            raise RuntimeError(
                f"Required environment variable {key} not set. "
                f"This is required in {ENV} environment."
            )

    return value


# ============================================================================
# JWT Validation Settings
# ============================================================================


# JWKS URL for fetching public keys
# Dev default: local backend, Prod: production domain
PG_JWKS_URL = get_env(
    "PG_CLAUDE_JWKS_URL",
    default="http://localhost:8000/oauth/pg/jwks"
)

# Expected JWT issuer (iss claim)
# Must match backend's settings.OAUTH_ISSUER
PG_ISSUER = get_env(
    "PG_CLAUDE_ISSUER",
    default="https://www.priority-guard.com"
)

# Expected JWT audience (aud claim)
# Must match backend's settings.OAUTH_ISSUER (provider uses aud=iss)
PG_AUDIENCE = get_env(
    "PG_CLAUDE_AUDIENCE",
    default="https://www.priority-guard.com"
)

# Token expiry clock skew tolerance (seconds).
# Passed as leeway to PyJWT to tolerate minor clock differences
# between backend and MCP server.
TOKEN_EXPIRY_GRACE_SECONDS = int(get_env(
    "PG_CLAUDE_TOKEN_EXPIRY_GRACE_SECONDS",
    default="30"
))

# JWKS cache TTL (seconds)
# How long to cache fetched JWKS before considering refresh
JWKS_CACHE_TTL_SECONDS = int(get_env(
    "PG_CLAUDE_JWKS_CACHE_TTL_SECONDS",
    default=str(24 * 3600)  # 24 hours
))

# JWKS maximum stale age (seconds)
# Maximum age before cached JWKS is considered too old to use
# If cache is older than this and refetch fails, reject tokens (fail closed)
JWKS_MAX_STALE_SECONDS = int(get_env(
    "PG_CLAUDE_JWKS_MAX_STALE_SECONDS",
    default=str(7 * 24 * 3600)  # 7 days
))

# JWKS fetch timeout (seconds)
# Maximum time to wait for JWKS fetch request
JWKS_FETCH_TIMEOUT_SECONDS = int(get_env(
    "PG_CLAUDE_JWKS_FETCH_TIMEOUT_SECONDS",
    default="5"
))


# ============================================================================
# Backend Configuration
# ============================================================================

# Backend API base URL (trailing slash stripped to prevent URL-join bugs)
BACKEND_URL = get_env(
    "PG_CLAUDE_BACKEND_URL",
    default="http://localhost:8000"
).rstrip("/")

# Internal API secret for backend authentication
# Must match backend's INTERNAL_API_SECRET setting.
# Empty = disabled (dev mode). In production, this MUST be set.
INTERNAL_API_SECRET = get_env(
    "PG_CLAUDE_INTERNAL_API_SECRET",
    default=""
)

# Fail-fast: INTERNAL_API_SECRET required in production
# Without this, every request would silently 403 - better to fail at startup
if ENV in ("production", "prod", "staging") and not INTERNAL_API_SECRET:
    raise RuntimeError(
        "PG_CLAUDE_INTERNAL_API_SECRET is required in production. "
        "Set ENV=dev to disable this check for local development."
    )


# ============================================================================
# OAuth Discovery Configuration
# ============================================================================

# MCP Server origin URL (scheme + host only, no path)
# Used as the `issuer` in AS metadata — must match the host Claude fetches discovery from.
# Per MCP spec: authorization base URL is derived by discarding path from MCP server URL.
# In production: https://pg-claude.priority-guard.com (set via PG_CLAUDE_MCP_SERVER_URL env var)
MCP_SERVER_URL = get_env(
    "PG_CLAUDE_MCP_SERVER_URL",
    default="http://localhost:8004"
).rstrip("/")

# MCP Server resource URL (full URL including /mcp path)
# Used as the `resource` in protected resource metadata — must exactly match
# the URL Claude uses to connect to the MCP server.
# In production: https://pg-claude.priority-guard.com/mcp (set via PG_CLAUDE_MCP_RESOURCE_URL env var)
# Falls back to MCP_SERVER_URL + /mcp if not explicitly set.
MCP_RESOURCE_URL = get_env(
    "PG_CLAUDE_MCP_RESOURCE_URL",
    default=f"{MCP_SERVER_URL}/mcp"
).rstrip("/")

# OAuth Authorization Server URL (must include /oauth/pg path)
# Claude appends /.well-known/openid-configuration to this URL
OAUTH_ISSUER_URL = get_env(
    "PG_CLAUDE_OAUTH_ISSUER_URL",
    default="http://localhost:8000/oauth/pg"
)

# Authorization server base URL (issuer identifier and authorization_servers reference)
# Must match backend's OAUTH_ISSUER env var exactly.
# Used for: issuer claim, authorization_servers in protected resource metadata.
# Do NOT derive from OAUTH_ISSUER_URL — define explicitly to avoid path-change fragility.
OAUTH_ISSUER_BASE = get_env(
    "PG_CLAUDE_OAUTH_ISSUER_BASE",
    default="http://localhost:8000"
)

# Fail-fast: OAUTH_ISSUER_URL must share the same origin as OAUTH_ISSUER_BASE (RFC 8414)
# Without this check, discovery could return issuer=www but token_endpoint=api,
# which causes silent OAuth failures in Claude.
# Note: startswith() is insufficient — "https://www.example.com.evil.com" starts with
# "https://www.example.com" but has a completely different origin.
_base_parsed = urlparse(OAUTH_ISSUER_BASE)
_url_parsed = urlparse(OAUTH_ISSUER_URL)

if (_base_parsed.scheme, _base_parsed.netloc) != (_url_parsed.scheme, _url_parsed.netloc):
    raise RuntimeError(
        f"PG_CLAUDE_OAUTH_ISSUER_URL must share the same origin as PG_CLAUDE_OAUTH_ISSUER_BASE (RFC 8414). "
        f"Got PG_CLAUDE_OAUTH_ISSUER_BASE={OAUTH_ISSUER_BASE!r} (origin: {_base_parsed.scheme}://{_base_parsed.netloc}), "
        f"PG_CLAUDE_OAUTH_ISSUER_URL={OAUTH_ISSUER_URL!r} (origin: {_url_parsed.scheme}://{_url_parsed.netloc})."
    )

# Fail-fast: warn if OAUTH_ISSUER_BASE contains localhost in production
if ENV in ("production", "prod", "staging") and "localhost" in OAUTH_ISSUER_BASE:
    raise RuntimeError(
        "PG_CLAUDE_OAUTH_ISSUER_BASE contains 'localhost' in production. "
        "Set to production URL (e.g., https://www.priority-guard.com)."
    )

# Supported OAuth scopes for discovery endpoint
SCOPES_SUPPORTED = ["pg.access"]


# ============================================================================
# CORS Configuration
# ============================================================================

# CORS allowed origins for cross-origin requests
# In production, this must be explicitly set to known Claude/Anthropic domains.
# In dev, empty string allows all origins.
CORS_ALLOWED_ORIGINS_RAW = get_env("PG_CLAUDE_CORS_ALLOWED_ORIGINS")

if ENV in ("production", "prod", "staging") and not CORS_ALLOWED_ORIGINS_RAW:
    raise RuntimeError(
        "PG_CLAUDE_CORS_ALLOWED_ORIGINS must be explicitly set in production/staging. "
        "Example: 'https://claude.ai'"
    )

CORS_ALLOWED_ORIGINS: list[str] = (
    [origin.strip() for origin in CORS_ALLOWED_ORIGINS_RAW.split(",") if origin.strip()]
    if CORS_ALLOWED_ORIGINS_RAW
    else []  # Empty list in dev = allow all (middleware uses *)
)

# Development mode flag
IS_DEV = ENV == "dev"


# ============================================================================
# Logging Configuration
# ============================================================================

# Log level
LOG_LEVEL = get_env("LOG_LEVEL", default="INFO")
