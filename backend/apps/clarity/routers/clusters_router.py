"""
Clarity clusters persistence endpoint.

POST /api/clarity/clusters - Upsert cluster snapshot
GET /api/clarity/clusters - Retrieve cluster snapshot

PERSISTENCE SEMANTICS:
    Single-row-per-user (replace-latest), NOT append-only.

    Each POST upserts the user's snapshot (INSERT or UPDATE if exists).
    GET returns the single snapshot for the user.

    Enforced at DB level via UNIQUE constraint on user_id.

    This design was chosen because:
    - Clarity is stateless from ChatGPT's perspective
    - Only the current brain dump state matters
    - Historical snapshots have no use case
    - Simpler retention (no cleanup needed)

    If append-only history is needed later, remove the UNIQUE constraint,
    change upsert to INSERT, and update GET to handle multiple rows.

CONCURRENCY MODEL:
    Last-write-wins. Concurrent POSTs for the same user may overwrite each
    other; this is acceptable because Clarity snapshots represent full state
    (not incremental deltas).
"""

from uuid import UUID

from fastapi import APIRouter, Request, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func
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
    Retrieve user's cluster snapshot.

    Called by Clarity MCP server to fetch persisted data for cross-session continuity.
    Single-row model: each user has at most one snapshot (enforced by UNIQUE constraint).

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

    # NOTE: _verify_user_exists adds an extra DB round-trip but provides clearer
    # error semantics: "User not found" (404) vs "No snapshot for user" (404).
    # This helps debug MCP server issues (stale user IDs vs missing data).
    # Trade-off accepted: ~1ms indexed PK lookup for better observability.
    user_uuid = await _verify_user_exists(user_id_str, session)

    # Single-row model: UNIQUE(user_id) guarantees at most one row per user.
    # No ORDER BY or LIMIT needed - there's THE snapshot, not "latest".
    result = await session.execute(
        select(ClarityCluster).where(ClarityCluster.user_id == user_uuid)
    )
    cluster = result.scalar_one_or_none()

    if cluster is None:
        # 404 here means "user exists but has no snapshot"
        # (distinct from 404 "User not found" in _verify_user_exists)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No cluster snapshot found for user",
        )

    correlation_id = getattr(request.state, "correlation_id", "system")
    logger.info(
        "clarity.cluster.retrieved",
        correlation_id=correlation_id,
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
        content_hash=cluster.content_hash,
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
    Upsert the user's cluster snapshot.

    Called by Clarity MCP server after successful clustering.
    Single-row model: INSERT if no snapshot exists, UPDATE if one does.

    Headers:
        X-User-ID: User UUID (required)
        X-Internal-Secret: Internal API secret (required in production)

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

    # Validation is handled by Pydantic (CreateClusterRequest.validate_cluster_data)
    # which enforces minimal structural viability before we reach here.

    # UPSERT: Insert new row or update existing row for this user.
    # The UNIQUE constraint on user_id (uq_clarity_clusters_user_id) enforces
    # single-row-per-user at the database level, preventing race conditions
    # where concurrent POSTs could create duplicate rows.
    #
    # On conflict: we update all data fields AND reset created_at to preserve
    # "replace-latest" semantics where each POST represents a fresh snapshot.
    stmt = (
        insert(ClarityCluster)
        .values(
            user_id=user_uuid,
            cluster_data=payload.cluster_data,
            thoughts_exhausted=payload.thoughts_exhausted,
            correctly_clustered=payload.correctly_clustered,
            content_hash=payload.content_hash,
        )
        .on_conflict_do_update(
            index_elements=["user_id"],  # Safer than hardcoding constraint name
            set_={
                "cluster_data": payload.cluster_data,
                "thoughts_exhausted": payload.thoughts_exhausted,
                "correctly_clustered": payload.correctly_clustered,
                "content_hash": payload.content_hash,
                "created_at": func.now(),  # Reset timestamp on replace
                "updated_at": func.now(),
            },
        )
        .returning(ClarityCluster.id, ClarityCluster.created_at)
    )

    result = await session.execute(stmt)
    row = result.one()
    cluster_id, created_at = row
    await session.commit()  # Explicit commit ensures data is persisted before response

    # Compute cluster count from payload (already validated by Pydantic)
    cluster_count = len(payload.cluster_data["clusters"])  # No .get() - fail loud if invariant broken

    correlation_id = getattr(request.state, "correlation_id", "system")
    logger.info(
        "clarity.cluster.upserted",
        correlation_id=correlation_id,
        cluster_id=str(cluster_id),
        user_id=str(user_uuid),
        cluster_count=cluster_count,
    )

    return CreateClusterResponse(
        cluster_id=cluster_id,
        created_at=created_at,
    )
