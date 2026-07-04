"""
Configuration for MindSort Claude MCP Server.

Centralizes all MCP-specific settings including JWT validation,
JWKS fetching, and OAuth client configuration.

Uses /oauth/pg/* endpoints (shared Priority Guardian OAuth provider).

# ============================================================================
# Required Render Environment Variables (for future deployment)
# ============================================================================
# CLARITY_CLAUDE_MCP_SERVER_URL   = <deployed Claude origin, NO /mcp>   e.g. https://mindsort-mcp.priority-guard.com
# CLARITY_CLAUDE_MCP_RESOURCE_URL = <origin>/mcp                        (derives automatically; only set if overriding)
# CLARITY_CLAUDE_OAUTH_ISSUER_URL = https://www.priority-guard.com/oauth/pg
# CLARITY_CLAUDE_BACKEND_URL      = https://www.priority-guard.com
# CLARITY_CLAUDE_INTERNAL_API_SECRET = <matches backend INTERNAL_API_SECRET>
# CLARITY_CLAUDE_JWKS_URL         = https://www.priority-guard.com/oauth/pg/jwks
# CLARITY_CLAUDE_ISSUER           = https://www.priority-guard.com
# CLARITY_CLAUDE_AUDIENCE         = https://mindsort-mcp.priority-guard.com/mcp  # resource-shaped, NOT issuer
# CLARITY_CLAUDE_CORS_ALLOWED_ORIGINS = <comma-separated list if needed>
# ENV = production
"""

import os
from typing import Optional
from urllib.parse import urlparse


# ============================================================================
# Environment Detection
# ============================================================================

ENV = os.getenv("ENV", "dev")

# Known ENV values — fail fast on unknown to prevent production guards being silently bypassed
# Production values trigger required-env guards; dev/test values use defaults.
_PRODUCTION_ENV_VALUES = {"production", "prod", "staging"}
_DEV_ENV_VALUES = {"dev", "development", "local", "test", "ci"}
_KNOWN_ENV_VALUES = _PRODUCTION_ENV_VALUES | _DEV_ENV_VALUES


def _is_production_env(env: str) -> bool:
    """Return True if env is a production-like environment.

    Canonical predicate — use this everywhere instead of inline tuples.
    Includes "prod" alias that PG uses, preventing ENV=prod from bypassing guards.
    """
    return env in _PRODUCTION_ENV_VALUES


# Fail-fast: raise on unknown ENV to prevent guards being bypassed
# Without this, a typo like ENV=produciton silently runs in non-production mode,
# letting localhost defaults leak into what the operator thinks is production.
# Note: Case and whitespace variants (ENV=Production, ENV=" production ") intentionally
# fail here rather than being normalized — maximally explicit, no silent coercion.
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
    """Get environment variable with optional default and requirement check.

    Args:
        key: Environment variable name
        default: Default value if not set (mutually exclusive with required=True)
        required: If True, raise in production/staging when not set

    Returns:
        Environment variable value, default, or None

    Raises:
        RuntimeError: If required=True and not set in production/staging
        AssertionError: If required=True and default is not None (config mistake)
    """
    # Catch config mistakes: required=True with a default makes no sense
    # (the default would always be used, so required check never triggers)
    assert not (required and default is not None), \
        f"get_env({key}): required=True is incompatible with default={default!r}"

    value = os.getenv(key, default)

    if required and value is None:
        if _is_production_env(ENV):
            raise RuntimeError(
                f"Required environment variable {key} not set. "
                f"This is required in {ENV} environment."
            )

    return value


# ============================================================================
# JWT Validation Settings
# ============================================================================

# JWKS URL - uses /oauth/pg/ (Priority Guardian shared OAuth)
CLARITY_JWKS_URL = get_env(
    "CLARITY_CLAUDE_JWKS_URL",
    default="http://localhost:8000/oauth/pg/jwks"
)

# Expected JWT issuer (iss claim)
# NOTE: Uses domain-only issuer to match existing Focused pattern.
# Path-qualified issuer (e.g., .../oauth/pg) is a future hardening task.
CLARITY_ISSUER = get_env(
    "CLARITY_CLAUDE_ISSUER",
    default="https://www.priority-guard.com"
)

# Expected JWT audience (aud claim)
# RATIONALE: The audience identifies the intended recipient of the token.
# This MUST match what the OAuth provider (/oauth/pg/token) issues in the 'aud' claim.
#
# PRODUCTION SHAPE (verified 2026-07-04): In production, CLARITY_CLAUDE_AUDIENCE is set
# to the resource URL (https://mindsort-mcp.priority-guard.com/mcp), NOT the issuer URL.
# The dev default below (issuer-shaped) differs from production. This is intentional:
# local testing uses shared backend discovery which may not match per-app resource URLs.
#
# The code default should NOT be changed — production env compensation is correct.
# Both Clarity and Focused MCP servers accept the same audience since they share
# a single OAuth provider - scope-based access control (clarity.write vs focused.write)
# determines which MCP server accepts which tokens.
CLARITY_AUDIENCE = get_env(
    "CLARITY_CLAUDE_AUDIENCE",
    default="https://www.priority-guard.com"
)

# Token expiry grace period (seconds)
TOKEN_EXPIRY_GRACE_SECONDS = int(get_env(
    "TOKEN_EXPIRY_GRACE_SECONDS",
    default="30"
))

# JWKS cache settings
JWKS_CACHE_TTL_SECONDS = int(get_env(
    "JWKS_CACHE_TTL_SECONDS",
    default=str(24 * 3600)
))

JWKS_MAX_STALE_SECONDS = int(get_env(
    "JWKS_MAX_STALE_SECONDS",
    default=str(7 * 24 * 3600)
))

JWKS_FETCH_TIMEOUT_SECONDS = int(get_env(
    "JWKS_FETCH_TIMEOUT_SECONDS",
    default="5"
))


# ============================================================================
# Backend Configuration
# ============================================================================

BACKEND_URL = get_env(
    "CLARITY_CLAUDE_BACKEND_URL",
    default="http://localhost:8000"
).rstrip("/")

# Internal API secret for authenticated backend calls
# Must match INTERNAL_API_SECRET in backend config
# COUPLING: Empty string "" means "skip verification" in BOTH:
#   - MCP server (here): sends no X-Internal-API-Secret header
#   - Backend: accepts requests without the header when its secret is also ""
# This enables local dev without secrets. In prod, both must have matching values.
INTERNAL_API_SECRET = get_env(
    "CLARITY_CLAUDE_INTERNAL_API_SECRET",
    default=""  # Empty = dev mode (backend skips verification)
)


# ============================================================================
# OAuth Discovery Configuration
# ============================================================================

# MindSort Claude MCP Server public URL
# CRITICAL: This is an ORIGIN with NO /mcp path.
# discovery.py appends /mcp itself (resource = f"{MCP_SERVER_URL}/mcp"),
# and MCP_RESOURCE_URL derives as {MCP_SERVER_URL}/mcp.
# Putting /mcp in MCP_SERVER_URL produces https://domain/mcp/mcp and breaks
# the resource claim, the .well-known URLs, AND the ui.domain hash.
MCP_SERVER_URL = get_env(
    "CLARITY_CLAUDE_MCP_SERVER_URL",
    default="http://localhost:8003"
).rstrip("/")

# MCP Resource URL (the resource claim value)
# Defaults to {MCP_SERVER_URL}/mcp - only override if you need a different value
MCP_RESOURCE_URL = get_env(
    "CLARITY_CLAUDE_MCP_RESOURCE_URL",
    default=f"{MCP_SERVER_URL}/mcp"
)

# OAuth Authorization Server URL (uses /oauth/pg/)
# NOTE: This is the authorization server base URL for discovery, NOT the JWT 'iss' claim.
# - OAUTH_ISSUER_URL: http://localhost:8000/oauth/pg (authorization server endpoints)
# - CLARITY_ISSUER: https://www.priority-guard.com (JWT iss claim value)
# These differ because the OAuth provider uses a domain-only issuer in tokens.
OAUTH_ISSUER_URL = get_env(
    "CLARITY_CLAUDE_OAUTH_ISSUER_URL",
    default="http://localhost:8000/oauth/pg"
)

# Authorization server base URL (issuer identifier and authorization_servers reference)
# Must match backend's OAUTH_ISSUER env var exactly.
# Used for: issuer claim in AS metadata, authorization_servers in protected resource metadata.
# Do NOT derive from OAUTH_ISSUER_URL — define explicitly to avoid path-change fragility.
#
# NOTE: CLARITY_ISSUER (JWT iss validation) and OAUTH_ISSUER_BASE (discovery advertisement)
# hold the same production value (https://www.priority-guard.com) but serve different roles:
# - CLARITY_ISSUER: validates the 'iss' claim in incoming JWTs
# - OAUTH_ISSUER_BASE: advertised in oauth-protected-resource.authorization_servers
# Keep both explicit to prevent coupling bugs.
OAUTH_ISSUER_BASE = get_env(
    "CLARITY_CLAUDE_OAUTH_ISSUER_BASE",
    default="http://localhost:8000"
).rstrip("/")  # Normalize: remove trailing slash to ensure root comparison works

# Fail-fast: OAUTH_ISSUER_BASE must be a root issuer (no path, query, or fragment)
# A path like /oauth/pg would make authorization_servers non-root, breaking Claude discovery.
# The .rstrip("/") handles trailing slash; this rejects real paths.
_base_parsed = urlparse(OAUTH_ISSUER_BASE)
if _base_parsed.path not in ("", "/") or _base_parsed.query or _base_parsed.fragment:
    raise RuntimeError(
        f"CLARITY_CLAUDE_OAUTH_ISSUER_BASE must be a root issuer (no path, query, or fragment). "
        f"Got {OAUTH_ISSUER_BASE!r} with path={_base_parsed.path!r}, "
        f"query={_base_parsed.query!r}, fragment={_base_parsed.fragment!r}."
    )

# Fail-fast: OAUTH_ISSUER_URL must share the same origin as OAUTH_ISSUER_BASE (RFC 8414)
# Without this check, discovery could return issuer=www but token_endpoint=api,
# which causes silent OAuth failures in Claude.
# Note: startswith() is insufficient — "https://www.example.com.evil.com" starts with
# "https://www.example.com" but has a completely different origin.
# _base_parsed already defined above (shape guard); only need _url_parsed here.
_url_parsed = urlparse(OAUTH_ISSUER_URL)

if (_base_parsed.scheme, _base_parsed.netloc) != (_url_parsed.scheme, _url_parsed.netloc):
    raise RuntimeError(
        f"CLARITY_CLAUDE_OAUTH_ISSUER_URL must share the same origin as CLARITY_CLAUDE_OAUTH_ISSUER_BASE (RFC 8414). "
        f"Got CLARITY_CLAUDE_OAUTH_ISSUER_BASE={OAUTH_ISSUER_BASE!r} (origin: {_base_parsed.scheme}://{_base_parsed.netloc}), "
        f"CLARITY_CLAUDE_OAUTH_ISSUER_URL={OAUTH_ISSUER_URL!r} (origin: {_url_parsed.scheme}://{_url_parsed.netloc})."
    )

# Fail-fast: OAUTH_ISSUER_BASE must not contain localhost in production
# Uses canonical _is_production_env() predicate (includes "prod" alias)
if _is_production_env(ENV) and "localhost" in OAUTH_ISSUER_BASE:
    raise RuntimeError(
        "CLARITY_CLAUDE_OAUTH_ISSUER_BASE contains 'localhost' in production. "
        "Set to production URL (e.g., https://www.priority-guard.com)."
    )

# Supported OAuth scopes for MindSort Claude MCP server
# NOTE: This must mirror the clarity.* scopes in backend discovery
# (backend/core/oauth_provider/discovery.py → SCOPES_SUPPORTED).
# Unit tests in test_clarity_scope.py verify this invariant.
SCOPES_SUPPORTED = ["clarity.write"]


# ============================================================================
# Scope Definitions
# ============================================================================

TOOL_SCOPES = {
    "organize_thoughts": ["clarity.write"],
    "load_saved_board": ["clarity.write"],
    "read_board_before_editing": ["clarity.write"],
    "save_board": ["clarity.write"],
    "start_prioritization_flow": ["clarity.write"],
    "edit_board": ["clarity.write"],
    "delete_my_data": ["clarity.write"],
}


# ============================================================================
# Logging Configuration
# ============================================================================

# NOTE: Currently unused - logging is configured via structlog defaults.
# Reserved for future use if explicit log level control is needed.
# To use: import LOG_LEVEL in server.py and pass to structlog.configure().
LOG_LEVEL = get_env("LOG_LEVEL", default="INFO")


# ============================================================================
# CORS Configuration
# ============================================================================

# Environment detection for CORS
# Uses the inverse of canonical _is_production_env() for consistency.
# Note: staging is deliberately treated as production (IS_DEV=False) — it gets the same
# strict origin validation as production to catch CORS issues before they hit prod.
IS_DEV = not _is_production_env(ENV)

# Default allowed origins for Claude
# NOTE: Claude proxies widget calls, so direct browser access may not be needed.
# This is kept for dev mode and potential future use.
# UNVERIFIED-FOR-CLAUDE: Whether Claude's browser client hits this server directly
# is unconfirmed. Keep CORS for now; may be removable once behavior is confirmed.
_DEFAULT_CORS_ORIGINS = [
    "https://claude.ai",
]

# CORS allowed origins from environment
# SECURITY: Required in production to prevent silent breakage
CORS_ALLOWED_ORIGINS_RAW = get_env("CLARITY_CLAUDE_CORS_ALLOWED_ORIGINS")

if _is_production_env(ENV) and not CORS_ALLOWED_ORIGINS_RAW:
    raise RuntimeError(
        "CLARITY_CLAUDE_CORS_ALLOWED_ORIGINS must be explicitly set in production/staging. "
        "Set to comma-separated list of allowed origins "
        "(e.g., 'https://claude.ai')."
    )

# Parse origins from env var or use defaults (dev only)
CORS_ALLOWED_ORIGINS: list[str] = (
    [origin.strip() for origin in CORS_ALLOWED_ORIGINS_RAW.split(",") if origin.strip()]
    if CORS_ALLOWED_ORIGINS_RAW
    else _DEFAULT_CORS_ORIGINS
)
