"""
Backend persistence for Clarity clusters.

Handles saving and retrieving cluster snapshots via the backend API.
Failures are logged but don't crash tool responses - user still sees their clusters.
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
) -> str | None:
    """
    Persist cluster snapshot to backend.

    Args:
        user_id: User ID from JWT
        cluster_data: Logical cluster data (no UI metadata)
        thoughts_exhausted: Whether user confirmed all thoughts captured
        correctly_clustered: User confirmation of cluster accuracy (null before confirmation)

    Returns:
        cluster_id on success, None on failure

    Note:
        Failure is logged but doesn't raise - caller can continue without persistence.
    """
    try:
        # Build headers with optional internal secret
        headers = {"X-User-ID": user_id}
        if INTERNAL_API_SECRET:
            headers["X-Internal-Secret"] = INTERNAL_API_SECRET

        client = get_http_client()
        response = await client.post(
            f"{BACKEND_URL}/api/clarity/clusters",
            headers=headers,
            json={
                "cluster_data": cluster_data,
                "thoughts_exhausted": thoughts_exhausted,
                "correctly_clustered": correctly_clustered,
            },
        )

        if response.status_code == 201:
            cluster_id = response.json().get("cluster_id")
            logger.info("clarity.persist.success",
                       cluster_id=cluster_id,
                       user_id=user_id)
            return cluster_id
        else:
            logger.warning("clarity.persist.failed",
                          status=response.status_code,
                          user_id=user_id,
                          response=response.text[:200])
            return None

    except Exception as e:
        logger.warning("clarity.persist.error",
                      error=str(e),
                      user_id=user_id)
        return None


async def get_cluster(user_id: str) -> dict | None:
    """
    Fetch user's latest cluster snapshot from backend.

    Args:
        user_id: User ID from JWT

    Returns:
        Full response dict on success (cluster_id, cluster_data, thoughts_exhausted,
        correctly_clustered, created_at), None if no snapshot exists or on error.

    Note:
        Failure is logged but doesn't raise - caller handles None gracefully.
    """
    try:
        # Build headers with optional internal secret
        headers = {"X-User-ID": user_id}
        if INTERNAL_API_SECRET:
            headers["X-Internal-Secret"] = INTERNAL_API_SECRET

        client = get_http_client()
        response = await client.get(
            f"{BACKEND_URL}/api/clarity/clusters",
            headers=headers,
        )

        if response.status_code == 200:
            data = response.json()
            logger.info("clarity.retrieve.success",
                       cluster_id=data.get("cluster_id"),
                       user_id=user_id)
            return data
        elif response.status_code == 404:
            logger.debug("clarity.retrieve.not_found",
                        user_id=user_id)
            return None
        else:
            logger.warning("clarity.retrieve.failed",
                          status=response.status_code,
                          user_id=user_id,
                          response=response.text[:200])
            return None

    except Exception as e:
        logger.warning("clarity.retrieve.error",
                      error=str(e),
                      user_id=user_id)
        return None
