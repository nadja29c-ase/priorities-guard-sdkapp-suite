"""
Module-level HTTP client for backend API calls.

Reused across requests for connection pooling.

TIMEOUT GUARANTEE:
    All requests via this client have a 10-second timeout.
    This prevents MCP from hanging indefinitely on network issues.
    Callers (persistence.py, etc.) rely on this guarantee.
"""

import httpx

# Default timeout for all backend API calls (seconds)
DEFAULT_TIMEOUT = 10.0

# Module-level HTTP client (reused across requests)
_http_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    """Get or create module-level HTTP client for backend calls.

    Returns:
        AsyncClient with DEFAULT_TIMEOUT configured.
        All requests will timeout after DEFAULT_TIMEOUT seconds.
    """
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=DEFAULT_TIMEOUT)
    return _http_client


async def cleanup_http_client():
    """Clean up HTTP client on shutdown."""
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None
