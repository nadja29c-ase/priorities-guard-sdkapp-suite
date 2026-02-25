"""
Shared dependencies for Priority Guardian routers.

Re-exports core dependencies for backward compatibility.
"""

# Re-export from core for backward compatibility
from backend.core.dependencies import verify_internal_call  # noqa: F401
from backend.core.dependencies import validate_user_id_header  # noqa: F401
