"""
Configuration for Unpack MCP Server.

Simplified configuration - no OAuth, no persistence.
"""

import os


# ============================================================================
# Environment Detection
# ============================================================================

ENV = os.getenv("ENV", "dev")


# ============================================================================
# Helper Functions
# ============================================================================

def get_env(key: str, default: str | None = None) -> str | None:
    """Get environment variable with optional default."""
    return os.getenv(key, default)


# ============================================================================
# Server Configuration
# ============================================================================

# Server port (default 8003 to avoid conflict with other MCP servers)
PORT = int(get_env("PORT", "8003"))

# Logging level
LOG_LEVEL = get_env("LOG_LEVEL", "INFO")


# ============================================================================
# CORS Configuration
# ============================================================================

# Environment detection for CORS
IS_DEV = ENV in ("dev", "development", "local")

# Default allowed origins (ChatGPT/OpenAI domains)
_DEFAULT_CORS_ORIGINS = [
    "https://web-sandbox.oaiusercontent.com",  # ChatGPT widget sandbox
    "https://chatgpt.com",
]

# CORS allowed origins from environment
CORS_ALLOWED_ORIGINS_RAW = get_env("CORS_ALLOWED_ORIGINS")

if ENV in ("production", "staging") and not CORS_ALLOWED_ORIGINS_RAW:
    raise RuntimeError(
        "CORS_ALLOWED_ORIGINS must be explicitly set in production/staging. "
        "Set to comma-separated list of allowed origins "
        "(e.g., 'https://web-sandbox.oaiusercontent.com,https://chatgpt.com')."
    )

# Parse origins from env var or use defaults (dev only)
CORS_ALLOWED_ORIGINS: list[str] = (
    [origin.strip() for origin in CORS_ALLOWED_ORIGINS_RAW.split(",") if origin.strip()]
    if CORS_ALLOWED_ORIGINS_RAW
    else _DEFAULT_CORS_ORIGINS
)
