"""
Configuration for Priority Guardian MCP Server (Increment 01).

Centralizes all MCP-specific settings including JWT validation,
JWKS fetching, and OAuth client configuration.
"""

import os
from typing import Optional


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
    "PG_JWKS_URL",
    default="http://localhost:8000/oauth/pg/jwks"
)

# Expected JWT issuer (iss claim)
# Must match backend's settings.OAUTH_ISSUER
PG_ISSUER = get_env(
    "PG_ISSUER",
    default="https://www.priority-guard.com"
)

# Expected JWT audience (aud claim)
# Must match backend's settings.OAUTH_ISSUER (provider uses aud=iss)
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
if ENV in ("production", "prod", "staging") and not INTERNAL_API_SECRET:
    raise RuntimeError(
        "INTERNAL_API_SECRET is required in production. "
        "Set ENV=dev to disable this check for local development."
    )


# ============================================================================
# OAuth Discovery Configuration
# ============================================================================

# MCP Server public URL (used in discovery endpoint)
# Must match the actual public entrypoint for the MCP server
# Trailing slash stripped to prevent double-slash in discovery URLs
MCP_SERVER_URL = get_env(
    "PG_MCP_SERVER_URL",
    default="http://localhost:8003"
).rstrip("/")

# OAuth Authorization Server URL (must include /oauth/pg path)
# ChatGPT appends /.well-known/openid-configuration to this URL
OAUTH_ISSUER_URL = get_env(
    "PG_OAUTH_ISSUER_URL",
    default="http://localhost:8000/oauth/pg"
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

if ENV in ("production", "prod", "staging") and not CORS_ALLOWED_ORIGINS_RAW:
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
# Logging Configuration
# ============================================================================

# Log level
LOG_LEVEL = get_env("LOG_LEVEL", default="INFO")
