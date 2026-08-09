# (duplicate) — exists because it imports platform-specific config.#
# !! ITS CONTENTS ARE NOT A COPY. Verified 2026-08-09 by symbol-level sweep: this
# file has diverged STRUCTURALLY from the source named below, and not every
# divergence is documented. Do not assume a symbol here behaves as its namesake
# does there — and note that a symbol may be ABSENT here entirely. That is exactly
# how A22 happened: BearerAuthMiddleware dropped JWT validation, scope enforcement
# and the 413 guard while this header claimed a config-only difference.
# See doc/DUPL_DIVERGENCE_SWEEP_2026-08-09.md.
# Logic mirrors mcp_server/priority_guardian/http_client.py.
# Post-OpenAI-approval refactor: move shared logic to mcp_server/shared/
# with config injection and delete this file.

"""
HTTP client for Priority Guardian Claude MCP Server.

Provides helpers for calling the backend REST API with user identity headers.
"""

import httpx
import structlog

from mcp_server.priority_guardian_claude.config import BACKEND_URL, INTERNAL_API_SECRET

logger = structlog.get_logger(__name__)

# Shared HTTP client for calling backend API (lazily initialized)
http_client: httpx.AsyncClient | None = None


async def cleanup_http_client() -> None:
    """Close the HTTP client on shutdown to prevent connection leaks."""
    global http_client
    if http_client is not None:
        await http_client.aclose()
        http_client = None
        logger.info("mcp.http_client.closed")


async def backend_get(
    path: str,
    user_id: str,
    correlation_id: str
) -> dict:
    """
    Send a GET request to the backend API with user identity headers.

    Args:
        path: API path (e.g., "/api/priority-guardian/google/connection-status")
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID for tracing

    Returns:
        Response JSON from backend

    Raises:
        httpx.HTTPStatusError: If backend returns error status
    """
    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=30.0)

    url = f"{BACKEND_URL}{path}"

    headers = {
        "X-User-ID": user_id,
        "X-Correlation-ID": correlation_id,
    }
    if INTERNAL_API_SECRET:
        headers["X-Internal-Secret"] = INTERNAL_API_SECRET

    logger.info(
        "backend.api.get",
        correlation_id=correlation_id,
        url=path,
        user_id=user_id
    )

    resp = await http_client.get(url, headers=headers)

    # For 4xx errors, try to return structured error JSON so callers can
    # extract the user-friendly message. Only raise for 5xx or unparseable responses.
    if resp.status_code >= 400 and resp.status_code < 500:
        try:
            return resp.json()
        except Exception:
            resp.raise_for_status()

    resp.raise_for_status()
    return resp.json()


async def backend_post(
    path: str,
    json_data: dict,
    user_id: str,
    correlation_id: str
) -> dict:
    """
    Send a POST request to the backend API with user identity headers.

    Args:
        path: API path (e.g., "/api/priority-guardian/disconnect")
        json_data: Request payload
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID for tracing

    Returns:
        Response JSON from backend

    Raises:
        httpx.HTTPStatusError: If backend returns error status
    """
    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=30.0)

    url = f"{BACKEND_URL}{path}"

    # Add user identity headers
    headers = {
        "X-User-ID": user_id,
        "X-Correlation-ID": correlation_id,
    }
    if INTERNAL_API_SECRET:
        headers["X-Internal-Secret"] = INTERNAL_API_SECRET

    logger.info(
        "backend.api.post",
        correlation_id=correlation_id,
        url=path,
        user_id=user_id
    )

    resp = await http_client.post(url, json=json_data, headers=headers)

    # For 4xx errors, try to return structured error JSON so callers can
    # extract the user-friendly message. Only raise for 5xx or unparseable responses.
    if resp.status_code >= 400 and resp.status_code < 500:
        try:
            return resp.json()
        except Exception:
            resp.raise_for_status()

    resp.raise_for_status()
    return resp.json()


async def backend_put(
    path: str,
    json_data: dict,
    user_id: str,
    correlation_id: str
) -> dict:
    """
    Send a PUT request to the backend API with user identity headers.

    Args:
        path: API path (e.g., "/api/priority-guardian/priorities/{id}")
        json_data: Request payload
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID for tracing

    Returns:
        Response JSON from backend

    Raises:
        httpx.HTTPStatusError: If backend returns error status
    """
    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=30.0)

    url = f"{BACKEND_URL}{path}"

    headers = {
        "X-User-ID": user_id,
        "X-Correlation-ID": correlation_id,
    }
    if INTERNAL_API_SECRET:
        headers["X-Internal-Secret"] = INTERNAL_API_SECRET

    logger.info(
        "backend.api.put",
        correlation_id=correlation_id,
        url=path,
        user_id=user_id
    )

    resp = await http_client.put(url, json=json_data, headers=headers)

    # For 4xx errors, try to return structured error JSON so callers can
    # extract the user-friendly message. Only raise for 5xx or unparseable responses.
    if resp.status_code >= 400 and resp.status_code < 500:
        try:
            return resp.json()
        except Exception:
            resp.raise_for_status()

    resp.raise_for_status()
    return resp.json()


async def backend_delete(
    path: str,
    user_id: str,
    correlation_id: str
) -> dict:
    """
    Send a DELETE request to the backend API with user identity headers.

    Args:
        path: API path (e.g., "/api/priority-guardian/priorities/{id}")
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID for tracing

    Returns:
        Response JSON from backend

    Raises:
        httpx.HTTPStatusError: If backend returns error status
    """
    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=30.0)

    url = f"{BACKEND_URL}{path}"

    headers = {
        "X-User-ID": user_id,
        "X-Correlation-ID": correlation_id,
    }
    if INTERNAL_API_SECRET:
        headers["X-Internal-Secret"] = INTERNAL_API_SECRET

    logger.info(
        "backend.api.delete",
        correlation_id=correlation_id,
        url=path,
        user_id=user_id
    )

    resp = await http_client.delete(url, headers=headers)

    # For 4xx errors, try to return structured error JSON so callers can
    # extract the user-friendly message. Only raise for 5xx or unparseable responses.
    if resp.status_code >= 400 and resp.status_code < 500:
        try:
            return resp.json()
        except Exception:
            resp.raise_for_status()

    resp.raise_for_status()
    return resp.json()
