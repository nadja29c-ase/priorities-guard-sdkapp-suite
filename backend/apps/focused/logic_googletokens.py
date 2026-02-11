"""
Token management for Focused app.

Re-exports ensure_valid_access_token from shared core module.
This file maintains backward compatibility for existing imports.
"""

# Re-export from shared core module for backward compatibility
from backend.core.google_token_management import ensure_valid_access_token

__all__ = ["ensure_valid_access_token"]
