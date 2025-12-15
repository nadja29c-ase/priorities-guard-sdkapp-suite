"""
Request context for passing HTTP headers to tool handlers.

FastMCP's @mcp.tool() decorator automatically injects HTTP headers into the
`meta` parameter. However, Clarity uses a custom registry pattern with direct
handler registration, which bypasses this injection.

This module provides contextvars to pass HTTP headers (especially Authorization)
from middleware to tool handlers.

Usage:
    # In middleware (before handling request):
    auth_header_var.set(auth_header_value)

    # In tool handler:
    auth_header = auth_header_var.get(None)
"""

from contextvars import ContextVar
from typing import Optional


# ContextVar for Authorization header
# Set by middleware, read by mcp_auth.authenticate_request
auth_header_var: ContextVar[Optional[str]] = ContextVar("auth_header", default=None)
