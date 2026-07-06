"""
Configuration for Priority Guardian MCP Server (Increment 01).

Centralizes all MCP-specific settings including JWT validation,
JWKS fetching, and OAuth client configuration.

inc_97: Added unknown-ENV fail-fast guard and startup logging of resolved config.
"""

import os
from typing import Optional
from urllib.parse import urlparse

import structlog

logger = structlog.get_logger(__name__)


# ============================================================================
# Environment Detection (evaluated once at module load)
# ============================================================================

ENV = os.getenv("ENV", "dev")

# Known ENV values — fail fast on unknown to prevent production guards being silently bypassed.
# Production values trigger required-env guards; dev/test values use defaults.
# Pattern copied from clarity/config.py (inc_94/95) to ensure parity across apps.
_PRODUCTION_ENV_VALUES = {"production", "prod", "staging"}
_DEV_ENV_VALUES = {"dev", "development", "local", "test", "ci"}
_KNOWN_ENV_VALUES = _PRODUCTION_ENV_VALUES | _DEV_ENV_VALUES


def _is_production_env(env: str) -> bool:
    """Return True if env is a production-like environment.

    Canonical predicate — use this everywhere instead of inline tuples.
    Includes "prod" alias that PG uses, preventing ENV=prod from bypassing guards.
    """
    return env in _PRODUCTION_ENV_VALUES


# Fail-fast: raise on unknown ENV to prevent guards being bypassed.
# Without this, a typo like ENV=produciton silently runs in non-production mode,
# disabling every production guard in this file (CORS, INTERNAL_API_SECRET,
# _prod_url_invariants, RFC 8414 origin check).
if ENV not in _KNOWN_ENV_VALUES:
    raise RuntimeError(
        f"Unknown ENV value {ENV!r}. "
        f"Known values: {sorted(_KNOWN_ENV_VALUES)}. "
        f"Refusing to start — this prevents production guards from being silently bypassed."
    )


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
        if _is_production_env(ENV):
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
    "PG_JWKS_URL",
    default="http://localhost:8000/oauth/pg/jwks"
)

# Expected JWT issuer (iss claim)
# Must match backend's settings.OAUTH_ISSUER
PG_ISSUER = get_env(
    "PG_ISSUER",
    default="https://www.priority-guard.com"
)

# Expected JWT audience (aud claim) — legacy fallback form.
#
# The PG MCP server's validate_jwt accepts THREE audience forms (see mcp_auth.py):
#   1. MCP_RESOURCE_URL  — e.g., https://pg.priority-guard.com/mcp (primary)
#   2. MCP_SERVER_URL    — e.g., https://pg.priority-guard.com (origin-only)
#   3. PG_AUDIENCE       — e.g., https://www.priority-guard.com (legacy: matches
#                          backend's OAUTH_ISSUER from pre-RFC-9728 behavior)
#
# Tokens minted today use form 1 or 2 depending on the `resource` parameter
# ChatGPT sends during authorize. Form 3 is kept for tokens issued before the
# RFC 9728 migration. Do not remove without verifying no active tokens use it.
PG_AUDIENCE = get_env(
    "PG_AUDIENCE",
    default="https://www.priority-guard.com"
)

# Token expiry clock skew tolerance (seconds).
# Passed as leeway to PyJWT to tolerate minor clock differences
# between backend and MCP server.
TOKEN_EXPIRY_GRACE_SECONDS = int(get_env(
    "TOKEN_EXPIRY_GRACE_SECONDS",
    default="30"
))

# JWKS cache TTL (seconds)
# How long to cache fetched JWKS before considering refresh
JWKS_CACHE_TTL_SECONDS = int(get_env(
    "JWKS_CACHE_TTL_SECONDS",
    default=str(24 * 3600)  # 24 hours
))

# JWKS maximum stale age (seconds)
# Maximum age before cached JWKS is considered too old to use
# If cache is older than this and refetch fails, reject tokens (fail closed)
JWKS_MAX_STALE_SECONDS = int(get_env(
    "JWKS_MAX_STALE_SECONDS",
    default=str(7 * 24 * 3600)  # 7 days
))

# JWKS fetch timeout (seconds)
# Maximum time to wait for JWKS fetch request
JWKS_FETCH_TIMEOUT_SECONDS = int(get_env(
    "JWKS_FETCH_TIMEOUT_SECONDS",
    default="5"
))


# ============================================================================
# Backend Configuration
# ============================================================================

# Backend API base URL (trailing slash stripped to prevent URL-join bugs)
BACKEND_URL = get_env(
    "PG_BACKEND_URL",
    default="http://localhost:8000"
).rstrip("/")

# Internal API secret for backend authentication
# Must match backend's INTERNAL_API_SECRET setting.
# Empty = disabled (dev mode). In production, this MUST be set.
INTERNAL_API_SECRET = get_env(
    "INTERNAL_API_SECRET",
    default=""
)

# Fail-fast: INTERNAL_API_SECRET required in production
# Without this, every request would silently 403 - better to fail at startup
if _is_production_env(ENV) and not INTERNAL_API_SECRET:
    raise RuntimeError(
        "INTERNAL_API_SECRET is required in production. "
        "Set ENV=dev to disable this check for local development."
    )


# ============================================================================
# OAuth Discovery Configuration
# ============================================================================

# MCP Server origin URL (scheme + host only, no path)
# Used as the `issuer` in AS metadata — must match the host ChatGPT fetches discovery from.
# Per MCP spec: authorization base URL is derived by discarding path from MCP server URL.
# In production: https://pg.priority-guard.com (set via PG_MCP_SERVER_URL env var)
MCP_SERVER_URL = get_env(
    "PG_MCP_SERVER_URL",
    default="http://localhost:8003"
).rstrip("/")

# MCP Server resource URL (full URL including /mcp path)
# Used as the `resource` in protected resource metadata — must exactly match
# the URL ChatGPT uses to connect to the MCP server.
# In production: https://pg.priority-guard.com/mcp (set via PG_MCP_RESOURCE_URL env var)
# Falls back to MCP_SERVER_URL + /mcp if not explicitly set.
MCP_RESOURCE_URL = get_env(
    "PG_MCP_RESOURCE_URL",
    default=f"{MCP_SERVER_URL}/mcp"
).rstrip("/")

# OAuth Authorization Server URL (must include /oauth/pg path)
# ChatGPT appends /.well-known/openid-configuration to this URL
OAUTH_ISSUER_URL = get_env(
    "PG_OAUTH_ISSUER_URL",
    default="http://localhost:8000/oauth/pg"
)

# Authorization server base URL (issuer identifier and authorization_servers reference)
# Must match backend's OAUTH_ISSUER env var exactly.
# Used for: issuer claim, authorization_servers in protected resource metadata.
# Do NOT derive from OAUTH_ISSUER_URL — define explicitly to avoid path-change fragility.
OAUTH_ISSUER_BASE = get_env(
    "PG_OAUTH_ISSUER_BASE",
    default="http://localhost:8000"
)

# Fail-fast: OAUTH_ISSUER_URL must share the same origin as OAUTH_ISSUER_BASE (RFC 8414)
# Without this check, discovery could return issuer=www but token_endpoint=api,
# which causes silent OAuth failures in ChatGPT.
# Note: startswith() is insufficient — "https://www.example.com.evil.com" starts with
# "https://www.example.com" but has a completely different origin.
_base_parsed = urlparse(OAUTH_ISSUER_BASE)
_url_parsed = urlparse(OAUTH_ISSUER_URL)

if (_base_parsed.scheme, _base_parsed.netloc) != (_url_parsed.scheme, _url_parsed.netloc):
    raise RuntimeError(
        f"OAUTH_ISSUER_URL must share the same origin as OAUTH_ISSUER_BASE (RFC 8414). "
        f"Got OAUTH_ISSUER_BASE={OAUTH_ISSUER_BASE!r} (origin: {_base_parsed.scheme}://{_base_parsed.netloc}), "
        f"OAUTH_ISSUER_URL={OAUTH_ISSUER_URL!r} (origin: {_url_parsed.scheme}://{_url_parsed.netloc})."
    )

# Fail-fast: warn if OAUTH_ISSUER_BASE contains localhost in production
if _is_production_env(ENV) and "localhost" in OAUTH_ISSUER_BASE:
    raise RuntimeError(
        "PG_OAUTH_ISSUER_BASE contains 'localhost' in production. "
        "Set to production URL (e.g., https://www.priority-guard.com)."
    )

# Fail-fast: all URL env vars must be real production URLs in prod/staging.
# Default values in this module are localhost-based for dev convenience, but
# silently accepting them in production causes subtle failures (JWKS unreachable,
# discovery publishes wrong URL, reconcile calls hit localhost). Fail loudly at
# startup instead of serving a broken stack.
if _is_production_env(ENV):
    _prod_url_invariants = {
        "PG_JWKS_URL": PG_JWKS_URL,
        "PG_MCP_SERVER_URL (MCP_SERVER_URL)": MCP_SERVER_URL,
        "PG_MCP_RESOURCE_URL (MCP_RESOURCE_URL)": MCP_RESOURCE_URL,
        "PG_OAUTH_ISSUER_URL (OAUTH_ISSUER_URL)": OAUTH_ISSUER_URL,
        "PG_BACKEND_URL (BACKEND_URL)": BACKEND_URL,
        "PG_ISSUER": PG_ISSUER,
        "PG_AUDIENCE": PG_AUDIENCE,
    }
    _invalid_urls = {
        name: value
        for name, value in _prod_url_invariants.items()
        if "localhost" in value or value.startswith("http://")
    }
    if _invalid_urls:
        raise RuntimeError(
            f"Production URL validation failed. These env vars must be set to "
            f"HTTPS production URLs (not localhost, not http://): {_invalid_urls}"
        )

# Supported OAuth scopes for discovery endpoint
SCOPES_SUPPORTED = ["pg.access"]


# ============================================================================
# CORS Configuration
# ============================================================================

# CORS allowed origins for cross-origin requests
# In production, this must be explicitly set to known ChatGPT/OpenAI domains.
# In dev, empty string allows all origins.
CORS_ALLOWED_ORIGINS_RAW = get_env("CORS_ALLOWED_ORIGINS")

if _is_production_env(ENV) and not CORS_ALLOWED_ORIGINS_RAW:
    raise RuntimeError(
        "CORS_ALLOWED_ORIGINS must be explicitly set in production/staging. "
        "Example: 'https://chatgpt.com,https://chat.openai.com'"
    )

CORS_ALLOWED_ORIGINS: list[str] = (
    [origin.strip() for origin in CORS_ALLOWED_ORIGINS_RAW.split(",") if origin.strip()]
    if CORS_ALLOWED_ORIGINS_RAW
    else []  # Empty list in dev = allow all (middleware uses *)
)

# Development mode flag
IS_DEV = ENV == "dev"


# ============================================================================
# Request Size Limits
# ============================================================================

# Maximum request body size for MCP endpoints (bytes)
# Prevents DoS via oversized payloads. Default 1 MB is generous for JSON-RPC.
MAX_MCP_BODY_SIZE_BYTES = int(get_env(
    "MAX_MCP_BODY_SIZE_BYTES",
    default=str(1024 * 1024)  # 1 MB
))


# ============================================================================
# Logging Configuration
# ============================================================================

# Log level
LOG_LEVEL = get_env("LOG_LEVEL", default="INFO")


# ============================================================================
# Startup Logging — Resolved OAuth Config
# ============================================================================
# Log resolved OAuth config at import time to eliminate dashboard-vs-runtime ambiguity.
# These URLs are non-secret (public discovery endpoints) — safe to log.
# inc_97: Added after MindSort discovery drift diagnosis showed the value of
# capturing resolved config at startup rather than inferring from dashboard.

logger.info(
    "pg.config.oauth_resolved",
    pg_jwks_url=PG_JWKS_URL,
    mcp_server_url=MCP_SERVER_URL,
    mcp_resource_url=MCP_RESOURCE_URL,
    oauth_issuer_url=OAUTH_ISSUER_URL,
    oauth_issuer_base=OAUTH_ISSUER_BASE,
    env=ENV,
)
