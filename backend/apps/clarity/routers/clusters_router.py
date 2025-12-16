"""
Clarity clusters persistence endpoint.

POST /api/clarity/clusters - Create new cluster snapshot
GET /api/clarity/clusters - Retrieve latest cluster snapshot

PERSISTENCE SEMANTICS:
    Single-row-per-user (replace-latest), NOT append-only.

    Each POST creates a new snapshot and deletes all previous snapshots
    for that user. GET returns the single most recent snapshot.

    This design was chosen because:
    - Clarity is stateless from ChatGPT's perspective
    - Only the current brain dump state matters
    - Historical snapshots have no use case
    - Simpler retention (no cleanup needed)

    If append-only history is needed later, change the DELETE in
    create_cluster() and update GET to handle multiple rows.
"""

from uuid import UUID

from fastapi import APIRouter, Request, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from backend.core.database import get_db
from backend.core.config import settings
from backend.core.models import CoreUser
from backend.apps.clarity.db_models import ClarityCluster
from backend.apps.clarity.models.requests import (
    CreateClusterRequest,
    CreateClusterResponse,
    GetClusterResponse,
)


logger = structlog.get_logger(__name__)

router = APIRouter(tags=["clarity"])


def _verify_internal_call(request: Request) -> None:
    """
    Verify request comes from trusted internal service (MCP server).

    Args:
        request: FastAPI request object

    Raises:
        HTTPException: 403 if X-Internal-Secret is missing or invalid

    Note:
        If INTERNAL_API_SECRET is empty, verification is skipped (dev mode).
        In production, set INTERNAL_API_SECRET to a strong random value.
    """
    if not settings.INTERNAL_API_SECRET:
        # Dev mode: skip verification
        return

    secret = request.headers.get("x-internal-secret")
    if not secret or secret != settings.INTERNAL_API_SECRET:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )


def _extract_user_id(request: Request) -> str:
    """
    Extract user_id from X-User-ID header.

    Args:
        request: FastAPI request object

    Returns:
        User ID string (UUID format)

    Raises:
        HTTPException: 401 if X-User-ID header is missing
    """
    user_id = request.headers.get("x-user-id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-ID header required",
        )
    return user_id


async def _verify_user_exists(user_id: str, session: AsyncSession) -> UUID:
    """
    Verify user exists in core_users table.

    Args:
        user_id: User ID string (should be UUID format)
        session: Database session

    Returns:
        User UUID

    Raises:
        HTTPException: 404 if user doesn't exist
        HTTPException: 400 if user_id is not valid UUID
    """
    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user_id format (expected UUID)",
        )

    result = await session.execute(
        select(CoreUser.id).where(CoreUser.id == user_uuid)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return user_uuid


@router.get(
    "/clusters",
    response_model=GetClusterResponse,
)
async def get_clusters(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> GetClusterResponse:
    """
    Retrieve user's latest cluster snapshot.

    Called by Clarity MCP server to fetch historical data for cross-session continuity.
    Returns the most recent cluster snapshot for the user.

    Headers:
        X-User-ID: User UUID (required)
        X-Internal-Secret: Internal API secret (required in production)

    Returns:
        200: Cluster snapshot data
        401: Missing X-User-ID header
        403: Invalid internal secret (production only)
        404: No cluster snapshot found for user

    Security:
        Validates X-Internal-Secret header to ensure request comes from
        trusted MCP server. In dev mode (INTERNAL_API_SECRET empty), this
        check is skipped.
    """
    # Verify internal call (403 if invalid secret in production)
    _verify_internal_call(request)

    # Extract and validate user_id
    user_id_str = _extract_user_id(request)
    user_uuid = await _verify_user_exists(user_id_str, session)

    # Query for latest cluster (ORDER BY created_at DESC LIMIT 1)
    result = await session.execute(
        select(ClarityCluster)
        .where(ClarityCluster.user_id == user_uuid)
        .order_by(ClarityCluster.created_at.desc())
        .limit(1)
    )
    cluster = result.scalar_one_or_none()

    if cluster is None:
        # 404 here means "user exists but has no snapshot"
        # (distinct from 404 "User not found" in _verify_user_exists)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No cluster snapshot found for user",
        )

    logger.info(
        "clarity.cluster.retrieved",
        cluster_id=str(cluster.id),
        user_id=str(user_uuid),
        cluster_count=cluster.cluster_count,
    )

    return GetClusterResponse(
        cluster_id=cluster.id,
        cluster_data=cluster.cluster_data,
        thoughts_exhausted=cluster.thoughts_exhausted,
        correctly_clustered=cluster.correctly_clustered,
        created_at=cluster.created_at,
    )


@router.post(
    "/clusters",
    response_model=CreateClusterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_cluster(
    payload: CreateClusterRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> CreateClusterResponse:
    """
    Create a new cluster snapshot, replacing any previous snapshot for this user.

    Called by Clarity MCP server after successful clustering.
    Keeps only the most recent snapshot per user (deletes old rows after insert).

    Headers:
        X-User-ID: User UUID (required)

    Body:
        cluster_data: {"clusters": [...]}
        thoughts_exhausted: bool
        correctly_clustered: bool | null

    Returns:
        201: {"cluster_id": "...", "created_at": "..."}
        400: Invalid cluster_data structure
        401: Missing X-User-ID header
        404: User not found

    Security:
        Validates X-Internal-Secret header to ensure request comes from
        trusted MCP server. In dev mode (INTERNAL_API_SECRET empty), this
        check is skipped.
    """
    # Verify internal call (403 if invalid secret in production)
    _verify_internal_call(request)

    # Extract and validate user_id
    user_id_str = _extract_user_id(request)
    user_uuid = await _verify_user_exists(user_id_str, session)

    # Create cluster record
    cluster = ClarityCluster(
        user_id=user_uuid,
        cluster_data=payload.cluster_data,
        thoughts_exhausted=payload.thoughts_exhausted,
        correctly_clustered=payload.correctly_clustered,
    )

    # Validate before insert
    try:
        cluster.validate()
    except ValueError as e:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # ATOMIC REPLACE: Delete old snapshots first, then insert new one.
    # This prevents race conditions where concurrent POSTs could:
    # - Delete each other's newly inserted rows
    # - Briefly have two active snapshots
    # Single commit ensures atomicity.
    delete_result = await session.execute(
        delete(ClarityCluster).where(ClarityCluster.user_id == user_uuid)
    )
    session.add(cluster)
    await session.commit()
    await session.refresh(cluster)

    # Observability: warn if multiple rows were deleted (invariant drift)
    # Should be 0 (first snapshot) or 1 (replacement). More indicates a bug.
    if delete_result.rowcount and delete_result.rowcount > 1:
        logger.warning(
            "clarity.cluster.multiple_old_rows_deleted",
            user_id=str(user_uuid),
            deleted_count=delete_result.rowcount,
            msg="Expected 0 or 1 old snapshots, found more. Check for race condition or bug.",
        )

    logger.info(
        "clarity.cluster.created",
        cluster_id=str(cluster.id),
        user_id=str(user_uuid),
        cluster_count=cluster.cluster_count,  # Computed property
        deleted_old_rows=delete_result.rowcount,
    )

    return CreateClusterResponse(
        cluster_id=cluster.id,
        created_at=cluster.created_at,
    )
