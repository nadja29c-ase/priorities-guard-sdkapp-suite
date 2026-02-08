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

def get_env(key: str, default: Optional[str] = None, required: bool = False) -> str:
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
        if ENV in ("production", "staging"):
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

# Expected ChatGPT client ID for azp claim validation
# Required in production, optional in dev (for testing)
CHATGPT_CLIENT_ID_PG = get_env(
    "CHATGPT_CLIENT_ID_PG",
    required=True  # Will fail in prod/staging if not set
)

# Token expiry grace period (seconds)
# Reject tokens expiring within this window to prevent race conditions
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
# Scope Definitions
# ============================================================================

# Tool → Required scopes mapping
TOOL_SCOPES = {
    "connect_google_calendar": ["pg.access"],
    "disconnect_google_calendar": ["pg.access"],
    "create_priority": ["pg.access"],
}


# ============================================================================
# Logging Configuration
# ============================================================================

# Log level
LOG_LEVEL = get_env("LOG_LEVEL", default="INFO")
