"""
Backend persistence for Clarity clusters.

Handles saving and retrieving cluster snapshots via the backend API.
Failures are logged but don't crash tool responses - user still sees their clusters.

IMPORTANT:
    This module intentionally does NOT normalize or merge cluster state.
    It is a pure read/write layer. Reconciliation logic (if ever needed) lives
    in the load_saved_board tool, not here.

TIMEOUT GUARANTEE:
    All HTTP calls use get_http_client() which has a 10-second timeout.
    See http_client.py for the guarantee. This prevents hanging on network issues.
"""

import structlog

from .http_client import get_http_client
from .config import BACKEND_URL, INTERNAL_API_SECRET

logger = structlog.get_logger(__name__)


async def persist_cluster(
    user_id: str,
    cluster_data: dict,
    thoughts_exhausted: bool,
    correctly_clustered: bool | None,
    correlation_id: str | None = None,
    content_hash: str | None = None,
) -> str | None:
    """
    Persist cluster snapshot to backend.

    Args:
        user_id: User ID from JWT
        cluster_data: Logical cluster data (no UI metadata)
        thoughts_exhausted: DEPRECATED - always pass False
        correctly_clustered: DEPRECATED - always pass None
        correlation_id: Optional correlation ID for distributed tracing
        content_hash: SHA256 hash of board content for saved state detection

    Returns:
        cluster_id on success, None on failure

    Note:
        Failure is logged but doesn't raise - caller can continue without persistence.
    """
    # Bind correlation_id to logger for consistent tracing
    log = logger.bind(correlation_id=correlation_id) if correlation_id else logger

    try:
        # Build headers
        headers = {"X-User-ID": user_id}
        if INTERNAL_API_SECRET:
            headers["X-Internal-Secret"] = INTERNAL_API_SECRET
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id

        # Build payload
        payload = {
            "cluster_data": cluster_data,
            "thoughts_exhausted": thoughts_exhausted,
            "correctly_clustered": correctly_clustered,
        }
        if content_hash is not None:
            payload["content_hash"] = content_hash

        client = get_http_client()
        response = await client.post(
            f"{BACKEND_URL}/api/clarity/clusters",
            headers=headers,
            json=payload,
        )

        if response.status_code == 201:
            cluster_id = response.json().get("cluster_id")
            if not cluster_id:
                # Backend returned 201 but missing cluster_id - contract violation
                log.warning("clarity.persist.malformed_response",
                           user_id=user_id,
                           response=response.text[:200])
                return None
            log.info("clarity.persist.success",
                    cluster_id=cluster_id,
                    user_id=user_id)
            return cluster_id

        # Granular error handling for better observability
        if response.status_code in (401, 403):
            # Auth issues: likely internal secret mismatch or missing user
            log.error("clarity.persist.auth_failed",
                     status=response.status_code,
                     user_id=user_id,
                     response=response.text[:200])
        elif response.status_code == 422:
            # Validation failed: likely schema drift between MCP and backend
            log.error("clarity.persist.validation_failed",
                     status=response.status_code,
                     user_id=user_id,
                     response=response.text[:200])
        else:
            # Other errors (404, 500, etc.)
            log.warning("clarity.persist.failed",
                       status=response.status_code,
                       user_id=user_id,
                       response=response.text[:200])
        return None

    except Exception as e:
        log.warning("clarity.persist.error",
                   error=str(e),
                   user_id=user_id)
        return None


async def get_cluster(user_id: str, correlation_id: str | None = None) -> dict | None:
    """
    Fetch user's cluster snapshot from backend.

    Args:
        user_id: User ID from JWT
        correlation_id: Optional correlation ID for distributed tracing

    Returns:
        Full response dict on success (cluster_id, cluster_data, thoughts_exhausted,
        correctly_clustered, created_at), None if no snapshot exists or on error.

    Note:
        Failure is logged but doesn't raise - caller handles None gracefully.
    """
    # Bind correlation_id to logger for consistent tracing
    log = logger.bind(correlation_id=correlation_id) if correlation_id else logger

    try:
        # Build headers
        headers = {"X-User-ID": user_id}
        if INTERNAL_API_SECRET:
            headers["X-Internal-Secret"] = INTERNAL_API_SECRET
        if correlation_id:
            headers["X-Correlation-ID"] = correlation_id

        client = get_http_client()
        response = await client.get(
            f"{BACKEND_URL}/api/clarity/clusters",
            headers=headers,
        )

        if response.status_code == 200:
            data = response.json()
            # Contract: backend returns single dict, not list
            if isinstance(data, list):
                log.warning("clarity.retrieve.contract_violation",
                           user_id=user_id,
                           error="Backend returned list, expected dict")
                return None
            log.info("clarity.retrieve.success",
                    cluster_id=data.get("cluster_id"),
                    user_id=user_id)
            return data

        if response.status_code == 404:
            # Expected: user has no snapshot yet
            log.debug("clarity.retrieve.not_found",
                     user_id=user_id)
            return None

        # Granular error handling for better observability
        if response.status_code in (401, 403):
            # Auth issues: likely internal secret mismatch or missing user
            log.error("clarity.retrieve.auth_failed",
                     status=response.status_code,
                     user_id=user_id,
                     response=response.text[:200])
        else:
            # Other errors (500, etc.)
            log.warning("clarity.retrieve.failed",
                       status=response.status_code,
                       user_id=user_id,
                       response=response.text[:200])
        return None

    except Exception as e:
        log.warning("clarity.retrieve.error",
                   error=str(e),
                   user_id=user_id)
        return None
