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
from sqlalchemy import select, delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func
import structlog

from backend.core.database import get_db
from backend.core.dependencies import verify_internal_call, validate_user_id_header
from backend.core.models import CoreUser, CoreToolAuditLog
from backend.apps.clarity.db_models import ClarityCluster
from backend.apps.clarity.models.requests import (
    CreateClusterRequest,
    CreateClusterResponse,
    GetClusterResponse,
    DeleteDataRequest,
    DeleteDataResponse,
)


logger = structlog.get_logger(__name__)

router = APIRouter(
    tags=["clarity"],
    dependencies=[Depends(verify_internal_call)],
)


async def _verify_user_exists(user_id: UUID, session: AsyncSession) -> None:
    """
    Verify user exists in core_users table.

    Args:
        user_id: User UUID (already validated by validate_user_id_header)
        session: Database session

    Raises:
        HTTPException: 404 if user doesn't exist
    """
    result = await session.execute(
        select(CoreUser.id).where(CoreUser.id == user_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )


@router.get(
    "/clusters",
    response_model=GetClusterResponse,
)
async def get_clusters(
    request: Request,
    user_id: UUID = Depends(validate_user_id_header),
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
        401: Missing or malformed X-User-ID header
        403: Invalid internal secret (production only)
        404: No cluster snapshot found for user

    Security:
        Validates X-Internal-Secret header to ensure request comes from
        trusted MCP server. In dev mode (INTERNAL_API_SECRET empty), this
        check is skipped.
    """
    # NOTE: _verify_user_exists adds an extra DB round-trip but provides clearer
    # error semantics: "User not found" (404) vs "No snapshot for user" (404).
    # This helps debug MCP server issues (stale user IDs vs missing data).
    # Trade-off accepted: ~1ms indexed PK lookup for better observability.
    await _verify_user_exists(user_id, session)

    # Single-row model: UNIQUE(user_id) guarantees at most one row per user.
    # No ORDER BY or LIMIT needed - there's THE snapshot, not "latest".
    result = await session.execute(
        select(ClarityCluster).where(ClarityCluster.user_id == user_id)
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
        user_id=str(user_id),
        cluster_count=cluster.cluster_count,
    )

    return GetClusterResponse(
        cluster_id=cluster.id,
        cluster_data=cluster.cluster_data,
        created_at=cluster.created_at,
        content_hash=cluster.content_hash,
        # DEPRECATED fields - return fixed values for backward compatibility
        thoughts_exhausted=False,
        correctly_clustered=None,
    )


@router.post(
    "/clusters",
    response_model=CreateClusterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_cluster(
    payload: CreateClusterRequest,
    request: Request,
    user_id: UUID = Depends(validate_user_id_header),
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
        401: Missing or malformed X-User-ID header
        404: User not found

    Security:
        Validates X-Internal-Secret header to ensure request comes from
        trusted MCP server. In dev mode (INTERNAL_API_SECRET empty), this
        check is skipped.
    """
    await _verify_user_exists(user_id, session)

    # Validation is handled by Pydantic (CreateClusterRequest.validate_cluster_data)
    # which enforces minimal structural viability before we reach here.

    # UPSERT: Insert new row or update existing row for this user.
    # The UNIQUE constraint on user_id (uq_clarity_clusters_user_id) enforces
    # single-row-per-user at the database level, preventing race conditions
    # where concurrent POSTs could create duplicate rows.
    #
    # On conflict: we update all data fields AND reset created_at to preserve
    # "replace-latest" semantics where each POST represents a fresh snapshot.
    #
    # NOTE: thoughts_exhausted and correctly_clustered were dropped from the
    # database (data minimization). The request schema still accepts them for
    # backward compatibility but they are not persisted.
    stmt = (
        insert(ClarityCluster)
        .values(
            user_id=user_id,
            cluster_data=payload.cluster_data,
            content_hash=payload.content_hash,
        )
        .on_conflict_do_update(
            index_elements=["user_id"],  # Safer than hardcoding constraint name
            set_={
                "cluster_data": payload.cluster_data,
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
        user_id=str(user_id),
        cluster_count=cluster_count,
    )

    return CreateClusterResponse(
        cluster_id=cluster_id,
        created_at=created_at,
    )


@router.delete(
    "/data",
    response_model=DeleteDataResponse,
)
async def delete_data(
    payload: DeleteDataRequest,
    request: Request,
    user_id: UUID = Depends(validate_user_id_header),
    session: AsyncSession = Depends(get_db),
) -> DeleteDataResponse:
    """
    Delete user's Clarity data (GDPR/compliance endpoint).

    Permanently deletes the user's saved board. This cannot be undone.
    Requires confirm=true in request body to execute.

    Headers:
        X-User-ID: User UUID (required)
        X-Internal-Secret: Internal API secret (required in production)

    Body:
        confirm: bool (must be true to execute deletion)

    Returns:
        200: {"status": "deleted", "message": "...", "deleted": {"clarity_clusters": N}}
        200: {"status": "no_data", "message": "..."}  (idempotent - no data to delete)
        400: Missing or false confirm parameter
        401: Missing or malformed X-User-ID header
        403: Invalid internal secret (production only)
        404: User not found

    Transaction Safety:
        Delete and audit log write happen in the SAME database transaction.
        If either fails, the entire transaction rolls back.
    """
    # Check confirmation BEFORE any database operations
    if not payload.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deletion requires explicit confirmation. Call with confirm=true.",
        )

    await _verify_user_exists(user_id, session)

    correlation_id = getattr(request.state, "correlation_id", "system")

    # TRANSACTION: Delete data AND write audit log atomically
    # Using session.begin() ensures both operations succeed or both roll back
    async with session.begin_nested():
        # 1. Delete user's clarity clusters
        delete_stmt = (
            delete(ClarityCluster)
            .where(ClarityCluster.user_id == user_id)
            .returning(ClarityCluster.id)
        )
        result = await session.execute(delete_stmt)
        deleted_ids = result.scalars().all()
        deleted_count = len(deleted_ids)

        # 2. Write audit log (same transaction)
        audit_entry = CoreToolAuditLog(
            user_id=user_id,
            app_name="clarity",
            action="delete_my_data",
            result_status="success" if deleted_count > 0 else "no_data",
            details={
                "scope": "clarity_data",
                "rows_deleted": {"clarity_clusters": deleted_count},
                "confirm_provided": True,
                "trigger": "user_request",
            },
        )
        session.add(audit_entry)

    # Commit transaction
    await session.commit()

    # Build response
    if deleted_count > 0:
        logger.info(
            "clarity.data.deleted",
            correlation_id=correlation_id,
            user_id=str(user_id),
            deleted_count=deleted_count,
        )
        return DeleteDataResponse(
            status="deleted",
            message="Your saved Clarity board has been permanently deleted.",
            deleted={"boards": deleted_count},
        )
    else:
        logger.info(
            "clarity.data.no_data",
            correlation_id=correlation_id,
            user_id=str(user_id),
        )
        return DeleteDataResponse(
            status="no_data",
            message="No saved board found. Nothing to delete.",
            deleted=None,
        )
