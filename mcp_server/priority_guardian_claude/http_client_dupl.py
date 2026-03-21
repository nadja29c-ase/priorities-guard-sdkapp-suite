# (duplicate) — exists only because it imports platform-specific config.
# Logic lives in mcp_server/priority_guardian/http_client.py.
# Post-OpenAI-approval refactor: move shared logic to mcp_server/shared/
# with config injection and delete this file.

import mcp_server.priority_guardian.http_client as _shared

from mcp_server.priority_guardian_claude.config import (
    BACKEND_URL,
    INTERNAL_API_SECRET,
)

# Rebind config-dependent module globals to Claude platform values
_shared.BACKEND_URL = BACKEND_URL
_shared.INTERNAL_API_SECRET = INTERNAL_API_SECRET

# Re-export everything callers need
from mcp_server.priority_guardian.http_client import (  # noqa: E402, F401
    backend_get,
    backend_post,
    backend_put,
    backend_delete,
    cleanup_http_client,
)
