"""
Module-level HTTP client for backend API calls.

Reused across requests for connection pooling.
"""

import httpx

# Module-level HTTP client (reused across requests)
_http_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    """Get or create module-level HTTP client for backend calls."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=10.0)
    return _http_client


async def cleanup_http_client():
    """Clean up HTTP client on shutdown."""
    global _http_client
    if _http_client:
        await _http_client.aclose()
        _http_client = None
