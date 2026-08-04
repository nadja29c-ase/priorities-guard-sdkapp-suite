"""
Configuration for Clarity MCP Server (MindSort-OpenAI).

Centralizes all MCP-specific settings including JWT validation,
JWKS fetching, and OAuth client configuration.

PRODUCTION CONFIG (Render-confirmed 2026-07-02):
  CLARITY_OAUTH_ISSUER_URL = https://www.priority-guard.com/oauth/mindsort

The dev default below differs (/oauth/pg) for local testing against the
shared backend discovery. Changing the dev default to /oauth/mindsort
requires verifying the local backend mounts that path in dev mode —
flagged as follow-up, not changed in this increment.

See doc/ADR/ADR_005_platform_oauth_discovery_contracts.md for the three
intentional discovery shapes and why MindSort-OpenAI uses /oauth/mindsort.
"""

import os
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


# ============================================================================
# Environment Detection
# ============================================================================

ENV = os.getenv("ENV", "dev")

# Known ENV values — fail fast on unknown to prevent production guards being silently bypassed
# Production values trigger required-env guards; dev/test values use defaults.
# Pattern copied from mindsort_claude/config.py to ensure parity.
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
# NOTE: .strip() prevents trailing newline/whitespace from deploy tooling causing
# false-positive guard failures (inc_95 hardening per Codex review).
CLARITY_JWKS_URL = get_env(
    "CLARITY_JWKS_URL",
    default="http://localhost:8000/oauth/pg/jwks"
).strip()

# Clarity's expected production JWKS URL (ADR_005 Shape #2: /oauth/mindsort endpoints)
# This is app-specific — derived from mindsort_discovery.py (backend AS metadata).
# The JWKS URL is the JWT trust anchor — if it falls to dev default in production,
# auth fails closed (can't fetch keys from localhost) or validates against wrong keys.
_CLARITY_EXPECTED_JWKS_URL = "https://www.priority-guard.com/oauth/mindsort/jwks"

# Fail-fast: CLARITY_JWKS_URL must be the exact expected value in production/staging
# This guard is assert-known-good (exact match), not blocklist — catches ANY wrong value.
# Without this guard, a wrong JWKS URL silently breaks JWT validation:
# - localhost default in prod → can't fetch keys → auth fails closed (full outage)
# - wrong production JWKS → validates against wrong key set → potential security issue
if _is_production_env(ENV) and CLARITY_JWKS_URL != _CLARITY_EXPECTED_JWKS_URL:
    raise RuntimeError(
        f"CLARITY_JWKS_URL must be {_CLARITY_EXPECTED_JWKS_URL!r} in production/staging. "
        f"Got: {CLARITY_JWKS_URL!r}. "
        f"Known drift vectors: localhost defaults (http://localhost:8000/oauth/pg/jwks), "
        f"wrong path (/oauth/pg/jwks instead of /oauth/mindsort/jwks). "
        f"See doc/ADR/ADR_005_platform_oauth_discovery_contracts.md Shape #2. "
        f"ENV={ENV!r}."
    )

# Expected JWT issuer (iss claim)
# NOTE: Uses domain-only issuer to match existing Focused pattern.
# Path-qualified issuer (e.g., .../oauth/pg) is a future hardening task.
CLARITY_ISSUER = get_env(
    "CLARITY_ISSUER",
    default="https://www.priority-guard.com"
)

# Expected JWT audience (aud claim)
# RATIONALE: The audience identifies the intended recipient of the token.
# This MUST match what the OAuth provider (/oauth/pg/token) issues in the 'aud' claim.
#
# PRODUCTION SHAPE (verified 2026-07-04): In production, CLARITY_AUDIENCE is set to
# the resource URL (https://mindsort.priority-guard.com/mcp), NOT the issuer URL.
# The dev default below (issuer-shaped) differs from production. This is intentional:
# local testing uses shared backend discovery which may not match per-app resource URLs.
#
# The code default should NOT be changed — production env compensation is correct.
# Both Clarity and Focused MCP servers accept the same audience since they share
# a single OAuth provider - scope-based access control (clarity.write vs focused.write)
# determines which MCP server accepts which tokens.
CLARITY_AUDIENCE = get_env(
    "CLARITY_AUDIENCE",
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

# BACKEND_URL: used by persistence.py for persist/retrieve API calls.
#
# INCIDENT GUARD (2026-07-05): This guard was added after a silent data loss incident.
# MindSort-Claude deployed with CLARITY_CLAUDE_BACKEND_URL (correct value, read by nothing)
# while persistence.py imports CLARITY_BACKEND_URL from this file. The missing env var
# silently fell to localhost:8000, causing every persist operation to fail for days.
# "Latent defense-in-depth" became "actual data loss" — never deploy without this guard.
#
# NOTE TO MINDSORT-CLAUDE DEPLOYERS: This module is shared. MindSort-Claude MUST set
# CLARITY_BACKEND_URL (not CLARITY_CLAUDE_BACKEND_URL) for persistence to work.
# The shim (mcp_auth_dupl.py) rebinds auth globals only — BACKEND_URL is NOT rebound.
BACKEND_URL = get_env(
    "CLARITY_BACKEND_URL",
    default="http://localhost:8000"
).strip().rstrip("/")

# Fail-fast: BACKEND_URL must not contain localhost in production
# Without this guard, persistence silently fails (connects to nothing) and
# organize_thoughts falsely logs "auto_persisted" while data is lost.
if _is_production_env(ENV) and "localhost" in BACKEND_URL:
    raise RuntimeError(
        "CLARITY_BACKEND_URL contains 'localhost' in production. "
        "Set to production URL (e.g., https://www.priority-guard.com). "
        "Incident: 2026-07-05 silent persistence failure on MindSort-Claude."
    )

# Internal API secret for authenticated backend calls
# Must match INTERNAL_API_SECRET in backend config
# COUPLING: Empty string "" means "skip verification" in BOTH:
#   - MCP server (here): sends no X-Internal-API-Secret header
#   - Backend: accepts requests without the header when its secret is also ""
# This enables local dev without secrets. In prod, both must have matching values.
INTERNAL_API_SECRET = get_env(
    "INTERNAL_API_SECRET",
    default=""  # Empty = dev mode (backend skips verification)
)


# ============================================================================
# OAuth Discovery Configuration
# ============================================================================

# Clarity MCP Server public URL
MCP_SERVER_URL = get_env(
    "CLARITY_MCP_SERVER_URL",
    default="http://localhost:8002"
).strip().rstrip("/")

# MCP Resource URL (the resource claim value)
# Defaults to {MCP_SERVER_URL}/mcp — only override if you need a different value
MCP_RESOURCE_URL = get_env(
    "CLARITY_MCP_RESOURCE_URL",
    default=f"{MCP_SERVER_URL}/mcp"
).strip()

# OAuth Authorization Server URL
# NOTE: This is the authorization server base URL for discovery, NOT the JWT 'iss' claim.
#
# PRODUCTION (Render-confirmed 2026-07-02):
#   CLARITY_OAUTH_ISSUER_URL = https://www.priority-guard.com/oauth/mindsort
#
# DEV DEFAULT: http://localhost:8000/oauth/pg
#   The dev default points to /oauth/pg (shared backend discovery) rather than
#   /oauth/mindsort because the local backend may not mount /oauth/mindsort in
#   dev mode. Production MUST use /oauth/mindsort per ADR_005 (Shape #2).
#   Changing this dev default requires verifying the local backend mounts
#   /oauth/mindsort — flagged as follow-up.
#
# - OAUTH_ISSUER_URL: authorization server endpoints (path-qualified)
# - CLARITY_ISSUER: JWT iss claim value (root domain only)
# These differ because the OAuth provider uses a domain-only issuer in tokens.
OAUTH_ISSUER_URL = get_env(
    "CLARITY_OAUTH_ISSUER_URL",
    default="http://localhost:8000/oauth/pg"
).strip()

# Clarity's expected production OAuth issuer (ADR_005 Shape #2: path-qualified)
# This is app-specific — other apps have different expected values per ADR_005.
_CLARITY_EXPECTED_OAUTH_ISSUER = "https://www.priority-guard.com/oauth/mindsort"

# Fail-fast: OAUTH_ISSUER_URL must be the exact expected value in production/staging
# This guard is assert-known-good (exact match), not blocklist — catches ANY wrong value.
# Without this guard, a wrong OAUTH_ISSUER_URL silently breaks the OAuth discovery chain:
# ChatGPT follows authorization_servers to the wrong AS metadata, gets wrong endpoints,
# and OAuth fails or uses the wrong consent screen.
if _is_production_env(ENV) and OAUTH_ISSUER_URL != _CLARITY_EXPECTED_OAUTH_ISSUER:
    raise RuntimeError(
        f"CLARITY_OAUTH_ISSUER_URL must be {_CLARITY_EXPECTED_OAUTH_ISSUER!r} in production/staging. "
        f"Got: {OAUTH_ISSUER_URL!r}. "
        f"Known drift vectors: localhost defaults, http://localhost:8000/oauth/pg, "
        f"bare https://www.priority-guard.com, https://www.priority-guard.com/oauth/pg. "
        f"See doc/ADR/ADR_005_platform_oauth_discovery_contracts.md Shape #2."
    )

# Supported OAuth scopes for Clarity MCP server
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
    # inc_91 diagnostic tool - no scopes required, but must be registered
    # to pass enforce_tool_scope()'s fail-closed check on unknown tools
    "_diagnostic_tiny_widget": [],
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

# Default allowed origins (ChatGPT/OpenAI domains)
# Used in dev mode only - production requires explicit configuration
_DEFAULT_CORS_ORIGINS = [
    "https://web-sandbox.oaiusercontent.com",  # ChatGPT widget sandbox
    "https://chatgpt.com",
    "https://chat.openai.com",
]

# CORS allowed origins from environment
# SECURITY: Required in production to prevent silent breakage when OpenAI adds domains
CORS_ALLOWED_ORIGINS_RAW = get_env("CORS_ALLOWED_ORIGINS")

if _is_production_env(ENV) and not CORS_ALLOWED_ORIGINS_RAW:
    raise RuntimeError(
        "CORS_ALLOWED_ORIGINS must be explicitly set in production/staging. "
        "OpenAI may add subdomains without notice. "
        "Set to comma-separated list of allowed origins "
        "(e.g., 'https://web-sandbox.oaiusercontent.com,https://chatgpt.com')."
    )

# Parse origins from env var or use defaults (dev only)
CORS_ALLOWED_ORIGINS: list[str] = (
    [origin.strip() for origin in CORS_ALLOWED_ORIGINS_RAW.split(",") if origin.strip()]
    if CORS_ALLOWED_ORIGINS_RAW
    else _DEFAULT_CORS_ORIGINS
)


# ============================================================================
# Startup Logging — Resolved OAuth Config
# ============================================================================
# Log resolved OAuth config at import time to eliminate dashboard-vs-runtime ambiguity.
# These URLs are non-secret (public discovery endpoints) — safe to log.
# inc_94: Added after a production discovery drift that resolved before runtime
# value was captured, making diagnosis a guessing game.

logger.info(
    "clarity.config.oauth_resolved",
    oauth_issuer_url=OAUTH_ISSUER_URL,
    jwks_url=CLARITY_JWKS_URL,
    mcp_server_url=MCP_SERVER_URL,
    mcp_resource_url=MCP_RESOURCE_URL,
    env=ENV,
)
