"""
Configuration for Sharpen MCP Server.

Stateless - no OAuth, no persistence.
"""

import os
from typing import Optional


# ============================================================================
# Environment Detection
# ============================================================================

ENV = os.getenv("ENV", "dev")


# ============================================================================
# Helper Functions
# ============================================================================

def get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get environment variable with optional default."""
    return os.getenv(key, default)


# ============================================================================
# Server Configuration
# ============================================================================

# Server port (8004 to avoid conflict with Clarity on 8002)
PORT = int(get_env("PORT", "8004"))

# Logging level
LOG_LEVEL = get_env("LOG_LEVEL", "INFO")


# ============================================================================
# CORS Configuration
# ============================================================================

# Environment detection for CORS
IS_DEV = ENV in ("dev", "development", "local")

# Default allowed origins (ChatGPT/OpenAI domains)
_DEFAULT_CORS_ORIGINS = [
    "https://web-sandbox.oaiusercontent.com",
    "https://chatgpt.com",
]

# CORS from environment
CORS_ALLOWED_ORIGINS_RAW = get_env("CORS_ALLOWED_ORIGINS")

if ENV in ("production", "staging") and not CORS_ALLOWED_ORIGINS_RAW:
    raise RuntimeError(
        "CORS_ALLOWED_ORIGINS must be explicitly set in production/staging."
    )

CORS_ALLOWED_ORIGINS: list[str] = (
    [origin.strip() for origin in CORS_ALLOWED_ORIGINS_RAW.split(",") if origin.strip()]
    if CORS_ALLOWED_ORIGINS_RAW
    else _DEFAULT_CORS_ORIGINS
)
