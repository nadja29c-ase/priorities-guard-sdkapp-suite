"""
Priority Router - MCP-facing endpoints for priority operations.

Priority Guardian Increment 02+: Provides MCP tools with priority CRUD.

Endpoints:
    GET /priorities: List user's priorities with Google connection status
    POST /priorities: Create a new priority with auto-assigned calendar keyword

Trust Boundary (CRITICAL - see Trust Boundary section in Inc 02 briefing):
The backend trusts the X-User-ID header because:
- Only the PG MCP server calls backend tool endpoints
- The MCP server validates the JWT (signature, expiry, scope) and extracts user_id from sub claim
- Backend tool endpoints are not directly internet-accessible for tool operations
- The MCP server sets X-User-ID from the validated JWT — never from client input

If this assumption changes (e.g., backend becomes directly accessible, another service calls
the backend, or direct client → backend calls are added), add backend-side JWT validation.
"""

import structlog
from uuid import UUID
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.database import get_db
from backend.core.models import CoreConnection
from backend.apps.priority_guardian.db_models import PgPriority, PgDeliverable, PgGoal
from backend.apps.priority_guardian.dependencies import validate_user_id_header
from backend.apps.priority_guardian.models.requests import (
    CreatePriorityRequest,
    UpdatePriorityRequest,
    CreateDeliverableRequest,
    UpdateDeliverableRequest,
    CreateGoalRequest,
    UpdateGoalRequest,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Priority Guardian Priorities"])

# Ordered list of available keywords
AVAILABLE_KEYWORDS = ["P1", "P2", "P3"]
MAX_ACTIVE_PRIORITIES = 3


def compute_available_keywords(used_keywords: List[str]) -> List[str]:
    """
    Compute available keywords from the ordered list.

    Args:
        used_keywords: List of keywords already in use

    Returns:
        List of available keywords in order (P1, P2, P3)
    """
    return [kw for kw in AVAILABLE_KEYWORDS if kw not in used_keywords]


async def build_priorities_response(session: AsyncSession, user_id: UUID) -> dict:
    """
    Build the standard priorities response with Google connection status.

    This is the canonical response builder used by GET /priorities and all mutation
    endpoints. Every mutation returns the full priority list so the widget can
    replace its entire state without diffing.

    Args:
        session: Database session
        user_id: User ID (UUID)

    Returns:
        Response dict with shape:
        {
            "success": True,
            "data": {
                "priorities": [...],
                "google_connection": {...},
                "available_keywords": [...]
            }
        }
    """
    # Query priorities ordered by status (active first), then created_at
    # Use selectinload to eagerly load deliverables and goals (avoids N+1 queries)
    result = await session.execute(
        select(PgPriority)
        .where(PgPriority.user_id == user_id)
        .options(
            selectinload(PgPriority.deliverables),
            selectinload(PgPriority.goals),
        )
        .order_by(
            PgPriority.status.asc(),  # 'active' < 'retired' alphabetically → active first
            PgPriority.created_at.asc(),
        )
    )
    priorities = result.scalars().all()

    # Query Google connection status
    conn_result = await session.execute(
        select(CoreConnection).where(
            CoreConnection.user_id == user_id,
            CoreConnection.provider == "google",
            CoreConnection.connection_type == "google",
            CoreConnection.revoked_at.is_(None),
        )
    )
    connection = conn_result.scalar_one_or_none()

    # Build connection status
    if connection:
        google_connection = {
            "connected": True,
            "connected_at": connection.created_at.isoformat() if connection.created_at else None,
            "scopes": connection.scopes,
        }
    else:
        google_connection = {"connected": False}

    # Compute available keywords from active priorities
    active_keywords = [p.calendar_keyword for p in priorities if p.status == "active"]
    available_keywords = compute_available_keywords(active_keywords)

    # Build priority list with deliverables and goals
    priorities_data = []
    for p in priorities:
        deliverables_data = [
            {
                "id": str(d.id),
                "name": d.name,
                "done": d.done,
            }
            for d in p.deliverables
        ]

        goals_data = [
            {
                "id": str(g.id),
                "text": g.goal_text,
                "achieved": g.achieved,
            }
            for g in p.goals
        ]

        priority_data = {
            "id": str(p.id),
            "name": p.name,
            "type": p.type,
            "calendar_keyword": p.calendar_keyword,
            "status": p.status,
            "deadline": p.deadline.isoformat() if p.deadline else None,
            "weekly_hour_target": float(p.weekly_hour_target) if p.weekly_hour_target is not None else None,
            "checkpoint_date": p.checkpoint_date.isoformat() if p.checkpoint_date else None,
            "deliverables": deliverables_data,
            "goals": goals_data,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "updated_at": p.updated_at.isoformat() if p.updated_at else None,
        }

        # Include all aggregates for all priority types (Inc 08)
        priority_data["streak_count"] = p.streak_count
        priority_data["total_hours_invested"] = float(p.total_hours_invested) if p.total_hours_invested is not None else 0.0
        priority_data["avg_target_achievement"] = float(p.avg_target_achievement) if p.avg_target_achievement is not None else None

        priorities_data.append(priority_data)

    return {
        "success": True,
        "data": {
            "priorities": priorities_data,
            "google_connection": google_connection,
            "available_keywords": available_keywords,
        },
    }


@router.get("/priorities")
async def get_priorities(
    user_id: UUID = Depends(validate_user_id_header),
    session: AsyncSession = Depends(get_db),
):
    """
    Get user's priorities with Google connection status.

    Returns priorities (active first, then retired) along with Google Calendar
    connection status for the widget to display.

    Args:
        user_id: User ID from validated JWT (via X-User-ID header)
        session: Database session

    Returns:
        200: {
            "success": true,
            "data": {
                "priorities": [...],
                "google_connection": {
                    "connected": true,
                    "scopes": ["..."]
                },
                "available_keywords": ["P2", "P3"]
            }
        }
    """
    response = await build_priorities_response(session, user_id)

    logger.info(
        "priorities.get.success",
        user_id=str(user_id),
        priority_count=len(response["data"]["priorities"]),
        google_connected=response["data"]["google_connection"]["connected"],
    )

    return response


@router.post("/priorities", status_code=status.HTTP_201_CREATED)
async def create_priority(
    request: CreatePriorityRequest,
    user_id: UUID = Depends(validate_user_id_header),
    session: AsyncSession = Depends(get_db),
):
    """
    Create a new priority with optional keyword choice.

    If calendar_keyword is provided and available, uses it.
    If not provided, auto-assigns deterministically (P1 → P2 → P3).

    Transactional Safety:
    - Uses SELECT FOR UPDATE to lock user's active priorities
    - Counts active priorities and rejects if >= 3
    - Assigns first available keyword from [P1, P2, P3]
    - Catches IntegrityError from partial unique index as fallback

    Args:
        request: Validated priority creation request
        user_id: User ID from validated JWT (via X-User-ID header)
        session: Database session

    Returns:
        201 Created: Priority created successfully
        401 Unauthorized: Missing/invalid X-User-ID
        409 Conflict: MAX_PRIORITIES_REACHED or KEYWORD_CONFLICT
        422 Validation Error: Invalid request data

    Response format:
        {
            "success": true,
            "data": {
                "priority": { ... },
                "active_priority_count": 1,
                "available_keywords": ["P2", "P3"]
            }
        }
    """
    try:
        # =========================================================================
        # Transactional keyword assignment with row locking
        # =========================================================================

        # Step 1: SELECT FOR UPDATE on user's active priorities
        # Locks existing active rows. If user has zero active priorities, nothing is
        # locked — two concurrent requests could both see 0 and race. The partial
        # unique index + IntegrityError fallback below handles this case.
        result = await session.execute(
            select(PgPriority)
            .where(
                PgPriority.user_id == user_id,
                PgPriority.status == "active",
            )
            .with_for_update()
        )
        active_priorities = result.scalars().all()

        # Step 2: Count active priorities — if >= 3, return 409
        if len(active_priorities) >= MAX_ACTIVE_PRIORITIES:
            logger.info(
                "priority.create.max_reached",
                user_id=str(user_id),
                active_count=len(active_priorities),
            )
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "success": False,
                    "error": {
                        "code": "MAX_PRIORITIES_REACHED",
                        "message": "You already have 3 active priorities. Retire or delete one to add a new priority.",
                    },
                },
            )

        # Step 3: Compute next available keyword
        used_keywords = [p.calendar_keyword for p in active_priorities]
        available_keywords = compute_available_keywords(used_keywords)

        if not available_keywords:
            # Shouldn't happen if count < 3, but defensive
            logger.error(
                "priority.create.no_keywords_available",
                user_id=str(user_id),
                active_count=len(active_priorities),
                used_keywords=used_keywords,
            )
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "success": False,
                    "error": {
                        "code": "KEYWORD_CONFLICT",
                        "message": "No available keywords. This is unexpected — please retry.",
                    },
                },
            )

        # Step 4: Determine keyword (user choice or auto-assign)
        if request.calendar_keyword:
            # User requested a specific keyword
            if request.calendar_keyword not in available_keywords:
                logger.info(
                    "priority.create.keyword_unavailable",
                    user_id=str(user_id),
                    requested_keyword=request.calendar_keyword,
                    available_keywords=available_keywords,
                )
                return JSONResponse(
                    status_code=status.HTTP_409_CONFLICT,
                    content={
                        "success": False,
                        "error": {
                            "code": "KEYWORD_CONFLICT",
                            "message": f"Keyword {request.calendar_keyword} is already in use. Choose from: {', '.join(available_keywords)}",
                        },
                    },
                )
            assigned_keyword = request.calendar_keyword
        else:
            # Auto-assign first available
            assigned_keyword = available_keywords[0]

        # Step 4: Create the priority
        priority = PgPriority(
            user_id=user_id,
            name=request.name,
            type=request.type,
            calendar_keyword=assigned_keyword,
            deadline=request.deadline,
            weekly_hour_target=request.weekly_hour_target,
            checkpoint_date=request.checkpoint_date,
        )

        session.add(priority)

        # Flush to generate priority.id before creating related objects
        await session.flush()

        # Step 4b: For flexible priorities, create the initial goal
        if request.type == "flexible" and request.initial_goal_text:
            initial_goal = PgGoal(
                priority_id=priority.id,
                goal_text=request.initial_goal_text,
            )
            session.add(initial_goal)

        # Step 5: Commit (flush again to catch IntegrityError before commit)
        await session.flush()
        await session.commit()

        # Refresh to load relationships (goals) after commit
        await session.refresh(priority)

        # Step 6: Compute available_keywords post-commit from actual DB state
        # Re-query to get accurate post-commit state
        result = await session.execute(
            select(PgPriority.calendar_keyword).where(
                PgPriority.user_id == user_id,
                PgPriority.status == "active",
            )
        )
        post_commit_keywords = [row[0] for row in result.fetchall()]
        post_commit_available = compute_available_keywords(post_commit_keywords)

        logger.info(
            "priority.create.success",
            user_id=str(user_id),
            priority_id=str(priority.id),
            keyword=assigned_keyword,
            type=request.type,
        )

        # Build response
        # For goals, we need to query them since we just created them
        goals_data = [
            {
                "id": str(g.id),
                "text": g.goal_text,
                "achieved": g.achieved,
            }
            for g in priority.goals
        ]

        priority_data = {
            "id": str(priority.id),
            "name": priority.name,
            "type": priority.type,
            "calendar_keyword": priority.calendar_keyword,
            "status": priority.status,
            "deadline": priority.deadline.isoformat() if priority.deadline else None,
            "weekly_hour_target": float(priority.weekly_hour_target) if priority.weekly_hour_target is not None else None,
            "checkpoint_date": priority.checkpoint_date.isoformat() if priority.checkpoint_date else None,
            "deliverables": [],  # Always empty on creation
            "goals": goals_data,
            "created_at": priority.created_at.isoformat() if priority.created_at else None,
        }

        return {
            "success": True,
            "data": {
                "priority": priority_data,
                "active_priority_count": len(post_commit_keywords),
                "available_keywords": post_commit_available,
            },
        }

    except IntegrityError as e:
        await session.rollback()

        # Check if this is the expected partial unique index violation (race condition)
        # Only check constraint name, do NOT log exception message (contains raw SQL)
        error_str = str(e.orig) if e.orig else str(e)
        if "idx_pg_priorities_user_keyword_active" in error_str:
            # Race condition fallback: partial unique index violation
            logger.warning(
                "priority.create.keyword_race_condition",
                user_id=str(user_id),
                error_type=type(e.orig).__name__ if e.orig else type(e).__name__,
            )

            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "success": False,
                    "error": {
                        "code": "KEYWORD_CONFLICT",
                        "message": "A race condition occurred assigning the keyword. Please retry the request.",
                    },
                },
            )
        else:
            # Unexpected constraint violation — do NOT log str(e), contains raw SQL
            logger.error(
                "priority.create.unexpected_integrity_error",
                user_id=str(user_id),
                error_type=type(e.orig).__name__ if e.orig else type(e).__name__,
            )

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected database error occurred. Please try again.",
            )

    except ValidationError as e:
        # Pydantic validation error (shouldn't happen if FastAPI validates, but defensive)
        logger.warning(
            "priority.create.validation_error",
            user_id=str(user_id),
            errors=e.errors(),
        )

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "success": False,
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": str(e),
                },
            },
        )

    except Exception as e:
        # Unexpected error — do NOT log str(e), may contain sensitive data
        await session.rollback()

        logger.error(
            "priority.create.unexpected_error",
            user_id=str(user_id),
            error_type=type(e).__name__,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again.",
        )


# ============================================================================
# Priority Mutation Endpoints (Widget CRUD - Inc B)
# ============================================================================


@router.put("/priorities/{priority_id}")
async def update_priority(
    priority_id: str,
    request: UpdatePriorityRequest,
    user_id: UUID = Depends(validate_user_id_header),
    session: AsyncSession = Depends(get_db),
):
    """
    Update a priority's editable fields.

    Accepts partial updates - only fields present in body are updated.
    Type is immutable. calendar_keyword can be reassigned.

    For deadline priorities: name, deadline, calendar_keyword
    For flexible priorities: name, weekly_hour_target, checkpoint_date, calendar_keyword

    Keyword reassignment: If the requested keyword is held by another active priority,
    they automatically swap keywords using a 3-step atomic swap.

    Args:
        priority_id: Priority ID (UUID string)
        request: Partial update fields
        user_id: User ID from validated JWT
        session: Database session

    Returns:
        200: Full priorities response (same shape as GET /priorities)
        404: Priority not found or wrong user
        409: Keyword conflict during reassignment
        422: Validation error (cross-type field, etc.)
    """
    # Validate priority_id format
    try:
        pid = UUID(priority_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Priority not found"},
        )

    # Fetch priority (initial read, no lock yet)
    result = await session.execute(
        select(PgPriority).where(
            PgPriority.id == pid,
            PgPriority.user_id == user_id,
        )
    )
    priority = result.scalar_one_or_none()

    if not priority:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Priority not found"},
        )

    # Only active priorities can be updated
    if priority.status != "active":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Priority not found"},
        )

    # Check if any updates provided
    if not request.has_updates():
        # No-op, just return current state
        return await build_priorities_response(session, user_id)

    # Validate cross-type fields
    if priority.type == "deadline":
        if request.weekly_hour_target is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "VALIDATION_ERROR", "message": "weekly_hour_target is not valid for deadline priorities"},
            )
        if request.checkpoint_date is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "VALIDATION_ERROR", "message": "checkpoint_date is not valid for deadline priorities"},
            )
    elif priority.type == "flexible":
        if request.deadline is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"code": "VALIDATION_ERROR", "message": "deadline is not valid for flexible priorities"},
            )

    # Handle keyword reassignment separately (requires special logic)
    if request.calendar_keyword is not None:
        try:
            await _handle_keyword_reassignment(
                session=session,
                user_id=user_id,
                requesting_priority_id=pid,
                desired_keyword=request.calendar_keyword,
            )
        except IntegrityError as e:
            await session.rollback()
            logger.warning(
                "priority.reassign.integrity_error",
                user_id=str(user_id),
                priority_id=str(pid),
                error_type=type(e.orig).__name__ if e.orig else type(e).__name__,
            )
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "success": False,
                    "error": {
                        "code": "KEYWORD_CONFLICT",
                        "message": "Keyword conflict during reassignment. Please retry.",
                    },
                },
            )

    # Re-fetch priority after potential keyword swap (it may have been modified)
    result = await session.execute(
        select(PgPriority).where(PgPriority.id == pid)
    )
    priority = result.scalar_one()

    # Apply other updates
    if request.name is not None:
        priority.name = request.name
    if request.deadline is not None:
        priority.deadline = request.deadline
    if request.weekly_hour_target is not None:
        priority.weekly_hour_target = request.weekly_hour_target
    if request.checkpoint_date is not None:
        priority.checkpoint_date = request.checkpoint_date

    await session.commit()

    logger.info(
        "priority.update.success",
        user_id=str(user_id),
        priority_id=str(priority.id),
    )

    return await build_priorities_response(session, user_id)


async def _handle_keyword_reassignment(
    session: AsyncSession,
    user_id: UUID,
    requesting_priority_id: UUID,
    desired_keyword: str,
) -> None:
    """
    Handle keyword reassignment with 3-step swap if needed.

    Case 0: Same keyword (no-op) - return immediately
    Case 1: Keyword is free - simple update
    Case 2: Keyword is held - 3-step swap with NULL intermediary

    Uses deterministic row locking (smallest UUID first) to prevent deadlocks.

    Args:
        session: Database session
        user_id: User ID
        requesting_priority_id: ID of priority requesting the keyword
        desired_keyword: The keyword to assign (P1, P2, or P3)

    Raises:
        IntegrityError: If a constraint violation occurs during swap
        HTTPException: For invariant violations (NULL persists after swap)
    """
    # Step 1: Initial read of requesting priority (no lock)
    result = await session.execute(
        select(PgPriority).where(PgPriority.id == requesting_priority_id)
    )
    requesting = result.scalar_one()

    # Case 0: Same keyword - no-op
    if requesting.calendar_keyword == desired_keyword:
        return

    freed_keyword = requesting.calendar_keyword

    # Step 2: Check if desired keyword is held by another active priority
    result = await session.execute(
        select(PgPriority).where(
            PgPriority.user_id == user_id,
            PgPriority.calendar_keyword == desired_keyword,
            PgPriority.status == "active",
            PgPriority.id != requesting_priority_id,
        )
    )
    displaced = result.scalar_one_or_none()

    if displaced is None:
        # Case 1: Keyword is free - simple update
        requesting.calendar_keyword = desired_keyword
        await session.flush()
        logger.info(
            "priority.reassign.free_keyword",
            user_id=str(user_id),
            priority_id=str(requesting_priority_id),
            new_keyword=desired_keyword,
        )
        return

    # Case 2: Keyword is held - need 3-step swap

    # Step 3: Lock both rows in deterministic order (smallest UUID first)
    ids_to_lock = sorted([requesting.id, displaced.id])
    result = await session.execute(
        select(PgPriority)
        .where(PgPriority.id.in_(ids_to_lock))
        .order_by(PgPriority.id)
        .with_for_update()
    )
    locked = {p.id: p for p in result.scalars().all()}
    requesting = locked[requesting_priority_id]
    displaced = locked[displaced.id]

    # Step 4: Re-validate after lock (TOCTOU defense)
    if displaced.calendar_keyword != desired_keyword:
        # State changed between read and lock - keyword may now be free
        requesting.calendar_keyword = desired_keyword
        await session.flush()
        logger.info(
            "priority.reassign.keyword_freed_during_lock",
            user_id=str(user_id),
            priority_id=str(requesting_priority_id),
            new_keyword=desired_keyword,
        )
        return

    # Step 5: Perform 3-step swap using NULL as intermediary

    # 5a: Clear displaced priority's keyword (NULL intermediary)
    displaced.calendar_keyword = None
    await session.flush()

    # 5b: Set requesting priority to desired keyword
    requesting.calendar_keyword = desired_keyword
    await session.flush()

    # 5c: Set displaced priority to freed keyword
    displaced.calendar_keyword = freed_keyword
    await session.flush()

    # Step 6: Invariant check (do NOT use assert — stripped by python -O)
    if requesting.calendar_keyword is None or displaced.calendar_keyword is None:
        await session.rollback()
        logger.error(
            "priority.reassign.invariant_violation",
            user_id=str(user_id),
            requesting_id=str(requesting.id),
            displaced_id=str(displaced.id),
            requesting_keyword=requesting.calendar_keyword,
            displaced_keyword=displaced.calendar_keyword,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "INVARIANT_VIOLATION", "message": "Keyword swap left NULL state. This is a bug."},
        )

    logger.info(
        "priority.reassign.swap_complete",
        user_id=str(user_id),
        requesting_id=str(requesting.id),
        displaced_id=str(displaced.id),
        requesting_keyword=desired_keyword,
        displaced_keyword=freed_keyword,
    )


@router.delete("/priorities/{priority_id}")
async def delete_priority(
    priority_id: str,
    user_id: UUID = Depends(validate_user_id_header),
    session: AsyncSession = Depends(get_db),
):
    """
    Delete a priority and its associated deliverables.

    Cascade delete handles deliverables automatically via relationship config.
    After deletion, the freed keyword becomes available again.

    Args:
        priority_id: Priority ID (UUID string)
        user_id: User ID from validated JWT
        session: Database session

    Returns:
        200: Full priorities response (without deleted priority)
        404: Priority not found or wrong user
    """
    # Validate priority_id format
    try:
        pid = UUID(priority_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Priority not found"},
        )

    # Fetch priority
    result = await session.execute(
        select(PgPriority).where(
            PgPriority.id == pid,
            PgPriority.user_id == user_id,
        )
    )
    priority = result.scalar_one_or_none()

    if not priority:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Priority not found"},
        )

    keyword = priority.calendar_keyword

    # Delete (cascade handles deliverables)
    await session.delete(priority)
    await session.commit()

    logger.info(
        "priority.delete.success",
        user_id=str(user_id),
        priority_id=str(pid),
        freed_keyword=keyword,
    )

    return await build_priorities_response(session, user_id)


# ============================================================================
# Deliverable Endpoints (Widget CRUD - Inc B)
# ============================================================================


@router.post("/priorities/{priority_id}/deliverables", status_code=status.HTTP_201_CREATED)
async def create_deliverable(
    priority_id: str,
    request: CreateDeliverableRequest,
    user_id: UUID = Depends(validate_user_id_header),
    session: AsyncSession = Depends(get_db),
):
    """
    Add a deliverable to a priority.

    Args:
        priority_id: Parent priority ID (UUID string)
        request: Deliverable creation request
        user_id: User ID from validated JWT
        session: Database session

    Returns:
        201: Full priorities response with new deliverable
        404: Parent priority not found or wrong user
        422: Validation error
    """
    # Validate priority_id format
    try:
        pid = UUID(priority_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Priority not found"},
        )

    # Fetch parent priority
    result = await session.execute(
        select(PgPriority).where(
            PgPriority.id == pid,
            PgPriority.user_id == user_id,
        )
    )
    priority = result.scalar_one_or_none()

    if not priority:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Priority not found"},
        )

    # Deliverables are only for deadline priorities
    if priority.type != "deadline":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "VALIDATION_ERROR", "message": "Deliverables are only valid for deadline priorities"},
        )

    # Create deliverable
    deliverable = PgDeliverable(
        priority_id=priority.id,
        name=request.name,
    )
    session.add(deliverable)
    await session.commit()

    logger.info(
        "deliverable.create.success",
        user_id=str(user_id),
        priority_id=str(priority.id),
        deliverable_id=str(deliverable.id),
    )

    # Expire cached objects so the next query gets fresh data with new deliverable
    session.expire_all()

    return await build_priorities_response(session, user_id)


@router.put("/deliverables/{deliverable_id}")
async def update_deliverable(
    deliverable_id: str,
    request: UpdateDeliverableRequest,
    user_id: UUID = Depends(validate_user_id_header),
    session: AsyncSession = Depends(get_db),
):
    """
    Update a deliverable (toggle done or rename).

    Args:
        deliverable_id: Deliverable ID (UUID string)
        request: Partial update fields
        user_id: User ID from validated JWT
        session: Database session

    Returns:
        200: Full priorities response
        404: Deliverable not found or parent priority belongs to different user
    """
    # Validate deliverable_id format
    try:
        did = UUID(deliverable_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Deliverable not found"},
        )

    # Fetch deliverable with parent priority for user validation
    result = await session.execute(
        select(PgDeliverable)
        .join(PgPriority)
        .where(
            PgDeliverable.id == did,
            PgPriority.user_id == user_id,
        )
    )
    deliverable = result.scalar_one_or_none()

    if not deliverable:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Deliverable not found"},
        )

    # Check if any updates provided
    if not request.has_updates():
        return await build_priorities_response(session, user_id)

    # Apply updates
    if request.name is not None:
        deliverable.name = request.name
    if request.done is not None:
        deliverable.done = request.done

    await session.commit()

    logger.info(
        "deliverable.update.success",
        user_id=str(user_id),
        deliverable_id=str(deliverable.id),
        done=deliverable.done,
    )

    return await build_priorities_response(session, user_id)


@router.delete("/deliverables/{deliverable_id}")
async def delete_deliverable(
    deliverable_id: str,
    user_id: UUID = Depends(validate_user_id_header),
    session: AsyncSession = Depends(get_db),
):
    """
    Delete a deliverable.

    Args:
        deliverable_id: Deliverable ID (UUID string)
        user_id: User ID from validated JWT
        session: Database session

    Returns:
        200: Full priorities response (without deleted deliverable)
        404: Deliverable not found or parent priority belongs to different user
    """
    # Validate deliverable_id format
    try:
        did = UUID(deliverable_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Deliverable not found"},
        )

    # Fetch deliverable with parent priority for user validation
    result = await session.execute(
        select(PgDeliverable)
        .join(PgPriority)
        .where(
            PgDeliverable.id == did,
            PgPriority.user_id == user_id,
        )
    )
    deliverable = result.scalar_one_or_none()

    if not deliverable:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Deliverable not found"},
        )

    priority_id = deliverable.priority_id

    await session.delete(deliverable)
    await session.commit()

    logger.info(
        "deliverable.delete.success",
        user_id=str(user_id),
        deliverable_id=str(did),
        priority_id=str(priority_id),
    )

    return await build_priorities_response(session, user_id)


# ============================================================================
# Goal Endpoints (Widget CRUD - Inc D)
# ============================================================================

MAX_GOALS_PER_PRIORITY = 3


@router.post("/priorities/{priority_id}/goals", status_code=status.HTTP_201_CREATED)
async def create_goal(
    priority_id: str,
    request: CreateGoalRequest,
    user_id: UUID = Depends(validate_user_id_header),
    session: AsyncSession = Depends(get_db),
):
    """
    Add a goal to a flexible priority.

    Maximum 3 goals per priority. Only valid for flexible priorities.

    Args:
        priority_id: Parent priority ID (UUID string)
        request: Goal creation request
        user_id: User ID from validated JWT
        session: Database session

    Returns:
        201: Full priorities response with new goal
        404: Parent priority not found or wrong user
        409: Max goals reached (3)
        422: Priority is not flexible type
    """
    # Validate priority_id format
    try:
        pid = UUID(priority_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Priority not found"},
        )

    # Fetch parent priority with goals
    result = await session.execute(
        select(PgPriority)
        .where(
            PgPriority.id == pid,
            PgPriority.user_id == user_id,
        )
        .options(selectinload(PgPriority.goals))
    )
    priority = result.scalar_one_or_none()

    if not priority:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Priority not found"},
        )

    # Goals are only for flexible priorities
    if priority.type != "flexible":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "VALIDATION_ERROR", "message": "Goals are only valid for flexible priorities"},
        )

    # Check max goals limit
    if len(priority.goals) >= MAX_GOALS_PER_PRIORITY:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "success": False,
                "error": {
                    "code": "MAX_GOALS_REACHED",
                    "message": f"Maximum {MAX_GOALS_PER_PRIORITY} goals per priority. Delete a goal to add a new one.",
                },
            },
        )

    # Create goal
    goal = PgGoal(
        priority_id=priority.id,
        goal_text=request.text,
    )
    session.add(goal)
    await session.commit()

    logger.info(
        "goal.create.success",
        user_id=str(user_id),
        priority_id=str(priority.id),
        goal_id=str(goal.id),
    )

    # Expire cached objects so the next query gets fresh data with new goal
    session.expire_all()

    return await build_priorities_response(session, user_id)


@router.put("/goals/{goal_id}")
async def update_goal(
    goal_id: str,
    request: UpdateGoalRequest,
    user_id: UUID = Depends(validate_user_id_header),
    session: AsyncSession = Depends(get_db),
):
    """
    Update a goal (toggle achieved or rename).

    Args:
        goal_id: Goal ID (UUID string)
        request: Partial update fields
        user_id: User ID from validated JWT
        session: Database session

    Returns:
        200: Full priorities response
        404: Goal not found or parent priority belongs to different user
    """
    # Validate goal_id format
    try:
        gid = UUID(goal_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Goal not found"},
        )

    # Fetch goal with parent priority for user validation
    result = await session.execute(
        select(PgGoal)
        .join(PgPriority)
        .where(
            PgGoal.id == gid,
            PgPriority.user_id == user_id,
        )
    )
    goal = result.scalar_one_or_none()

    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Goal not found"},
        )

    # Check if any updates provided
    if not request.has_updates():
        return await build_priorities_response(session, user_id)

    # Apply updates
    if request.text is not None:
        goal.goal_text = request.text
    if request.achieved is not None:
        goal.achieved = request.achieved

    await session.commit()

    logger.info(
        "goal.update.success",
        user_id=str(user_id),
        goal_id=str(goal.id),
        achieved=goal.achieved,
    )

    return await build_priorities_response(session, user_id)


@router.delete("/goals/{goal_id}")
async def delete_goal(
    goal_id: str,
    user_id: UUID = Depends(validate_user_id_header),
    session: AsyncSession = Depends(get_db),
):
    """
    Delete a goal.

    Args:
        goal_id: Goal ID (UUID string)
        user_id: User ID from validated JWT
        session: Database session

    Returns:
        200: Full priorities response (without deleted goal)
        404: Goal not found or parent priority belongs to different user
    """
    # Validate goal_id format
    try:
        gid = UUID(goal_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Goal not found"},
        )

    # Fetch goal with parent priority for user validation
    result = await session.execute(
        select(PgGoal)
        .join(PgPriority)
        .where(
            PgGoal.id == gid,
            PgPriority.user_id == user_id,
        )
    )
    goal = result.scalar_one_or_none()

    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Goal not found"},
        )

    priority_id = goal.priority_id

    await session.delete(goal)
    await session.commit()

    logger.info(
        "goal.delete.success",
        user_id=str(user_id),
        goal_id=str(gid),
        priority_id=str(priority_id),
    )

    return await build_priorities_response(session, user_id)
