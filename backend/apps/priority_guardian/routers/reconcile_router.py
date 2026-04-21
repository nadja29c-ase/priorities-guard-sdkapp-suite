"""
Reconcile Router — Cross-device identity reconciliation endpoint for Priority Guardian.

Endpoints:
- POST /reconcile-user: Reconcile JWT user_id against openai/subject for cross-device continuity

Increment 78: Uses openai/subject as identity anchor to map users across devices.
The MCP server calls this endpoint after JWT validation to resolve the canonical user_id.

IMPORTANT: This endpoint is internal-only (requires X-Internal-Secret header).
It does NOT accept X-User-ID because its purpose is to produce one.
"""

from typing import Literal
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, update, exists
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.priority_guardian.dependencies import verify_internal_call
from backend.apps.priority_guardian.db_models import PgPriority
from backend.core.database import get_db
from backend.core.models import CoreUser, CoreConnection

logger = structlog.get_logger(__name__)

router = APIRouter(
    tags=["priority-guardian-reconcile"],
    dependencies=[Depends(verify_internal_call)],
)


# =============================================================================
# Request / Response Models
# =============================================================================

class ReconcileUserRequest(BaseModel):
    jwt_user_id: UUID
    openai_subject: str = Field(min_length=1, max_length=128)


class ReconcileUserResponse(BaseModel):
    user_id: UUID
    case: Literal["A", "B", "C1", "C2", "X"]


# =============================================================================
# Reconciliation Logic
# =============================================================================

async def _reconcile_user_by_subject(
    db: AsyncSession,
    jwt_user_id: UUID,
    openai_subject: str,
    correlation_id: str,
) -> tuple[UUID, Literal["A", "B", "C1", "C2", "X"]]:
    """
    Reconcile JWT-stamped user_id to the canonical CoreUser that owns the given
    openai/subject. See Inc 78 briefing for the algorithm spec.

    Fresh-shell invariant (see Inc 78 briefing, Case C anomaly guard):
    A CoreUser is a fresh shell ONLY when BOTH are true:
      - no active (non-revoked) CoreConnection with connection_type='google'
      - no PgPriority of any status
    When new PG-owned state tables are added, extend the check here.

    Uses the ORM against CoreUser, CoreConnection, and PgPriority models.
    See session_service.py for the canonical patterns.
    """
    log = logger.bind(correlation_id=correlation_id)

    # Step 1: Lookup by subject
    stmt = select(CoreUser.id).where(CoreUser.openai_subject == openai_subject)
    result = await db.execute(stmt)
    subject_user_id = result.scalar_one_or_none()

    # Step 2: Case A — no match (first-time bind)
    if subject_user_id is None:
        # Guarded update: only stamp if current openai_subject is NULL
        update_stmt = (
            update(CoreUser)
            .where(CoreUser.id == jwt_user_id, CoreUser.openai_subject.is_(None))
            .values(openai_subject=openai_subject)
        )
        update_result = await db.execute(update_stmt)
        await db.commit()

        if update_result.rowcount == 1:
            log.info(
                "reconcile.first_bind",
                jwt_user_id=str(jwt_user_id),
                subject=openai_subject,
            )
            return (jwt_user_id, "A")

        # Race lost: another request won. Re-lookup and fall through.
        log.info(
            "reconcile.race_lost",
            jwt_user_id=str(jwt_user_id),
            subject=openai_subject,
        )
        result = await db.execute(stmt)
        subject_user_id = result.scalar_one_or_none()

        # If still None after race, anomaly: race lost but no one owns the subject.
        # This shouldn't happen in normal operation. Possible causes:
        # - jwt_user_id already has a different subject (UPDATE WHERE openai_subject IS NULL fails)
        # - jwt_user_id was deleted between JWT issuance and this call
        # - Genuine concurrent race (extremely unlikely with guarded UPDATE)
        # Log error for alerting and return jwt_user_id with case "X" (anomaly).
        if subject_user_id is None:
            log.error(
                "reconcile.race_lost_no_winner",
                jwt_user_id=str(jwt_user_id),
                subject=openai_subject,
                msg="Race lost but re-lookup found no owner. Subject remains unbound.",
            )
            return (jwt_user_id, "X")

    # Step 3: Case B — match, same user (steady state)
    if subject_user_id == jwt_user_id:
        log.debug("reconcile.match", user_id=str(jwt_user_id))
        return (jwt_user_id, "B")

    # Step 4: Case C — match, different user (cross-device case)
    # Check if jwt_user_id is a fresh shell

    # Has active Google connection?
    has_google_stmt = select(
        exists().where(
            CoreConnection.user_id == jwt_user_id,
            CoreConnection.connection_type == "google",
            CoreConnection.revoked_at.is_(None),
        )
    )
    has_google_result = await db.execute(has_google_stmt)
    has_google_connection = has_google_result.scalar()

    # Has any priority?
    has_priorities_stmt = select(
        exists().where(PgPriority.user_id == jwt_user_id)
    )
    has_priorities_result = await db.execute(has_priorities_stmt)
    has_priorities = has_priorities_result.scalar()

    # Branch C1 or C2
    if not has_google_connection and not has_priorities:
        # C1: Fresh shell — return canonical user
        log.info(
            "reconcile.cross_device",
            jwt_user_id=str(jwt_user_id),
            canonical_user_id=str(subject_user_id),
            subject=openai_subject,
        )
        return (subject_user_id, "C1")
    else:
        # C2: Hydrated user — refuse swap
        log.error(
            "reconcile.ambiguous_collision",
            jwt_user_id=str(jwt_user_id),
            subject_user_id=str(subject_user_id),
            subject=openai_subject,
            has_google_connection=has_google_connection,
            has_priorities=has_priorities,
        )
        return (jwt_user_id, "C2")


# =============================================================================
# Endpoint
# =============================================================================

@router.post("/reconcile-user", response_model=ReconcileUserResponse)
async def reconcile_user(
    request: Request,
    req: ReconcileUserRequest,
    db: AsyncSession = Depends(get_db),
) -> ReconcileUserResponse:
    """
    Reconcile JWT user_id against openai/subject for cross-device identity continuity.

    Called by MCP server after JWT validation, before tool dispatch.
    Returns the canonical user_id to use for downstream operations.

    Cases:
    - A: First-time bind (subject not seen before)
    - B: Match, same user (steady state)
    - C1: Cross-device (fresh shell remapped to canonical)
    - C2: Ambiguous collision (hydrated user, no remap)
    - X: Anomaly (race lost but no owner found; ERROR logged, ops paged)

    Requires X-Internal-Secret header. Does NOT accept X-User-ID.
    """
    correlation_id = getattr(request.state, "correlation_id", "system")

    user_id, case = await _reconcile_user_by_subject(
        db=db,
        jwt_user_id=req.jwt_user_id,
        openai_subject=req.openai_subject,
        correlation_id=correlation_id,
    )

    return ReconcileUserResponse(user_id=user_id, case=case)
