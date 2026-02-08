"""
Priority Creation Router - MCP-facing endpoint for creating priorities.

Priority Guardian Increment 02: Provides MCP tools with priority creation.

Endpoints:
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

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.apps.priority_guardian.db_models import PgPriority
from backend.apps.priority_guardian.models.requests import CreatePriorityRequest

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Priority Guardian Priorities"])

# Ordered list of available keywords
AVAILABLE_KEYWORDS = ["P1", "P2", "P3"]
MAX_ACTIVE_PRIORITIES = 3


def validate_user_id_header(
    x_user_id: str | None = Header(None, alias="X-User-ID")
) -> UUID:
    """
    Validate X-User-ID header as UUID.

    Trust Boundary: This header is trusted because it comes from the MCP server
    after JWT validation. The MCP server extracts user_id from the validated JWT's
    `sub` claim and sets this header. Never accept user_id from request body.

    Note: Header is declared optional (None default) so we can return 401 for missing
    headers. FastAPI's Header(...) would return 422, but the briefing requires 401
    for all auth-related failures.

    Args:
        x_user_id: User ID from MCP server (extracted from validated JWT)

    Returns:
        Validated UUID

    Raises:
        HTTPException 401: If header is missing or malformed (non-UUID)
    """
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Missing X-User-ID header"},
        )

    try:
        return UUID(x_user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Invalid X-User-ID header (must be UUID)"},
        )


def compute_available_keywords(used_keywords: List[str]) -> List[str]:
    """
    Compute available keywords from the ordered list.

    Args:
        used_keywords: List of keywords already in use

    Returns:
        List of available keywords in order (P1, P2, P3)
    """
    return [kw for kw in AVAILABLE_KEYWORDS if kw not in used_keywords]


@router.post("/priorities", status_code=status.HTTP_201_CREATED)
async def create_priority(
    request: CreatePriorityRequest,
    user_id: UUID = Depends(validate_user_id_header),
    session: AsyncSession = Depends(get_db),
):
    """
    Create a new priority with auto-assigned calendar keyword.

    The backend assigns calendar_keyword deterministically (P1 → P2 → P3).
    Users cannot choose or specify their keyword.

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

        assigned_keyword = available_keywords[0]  # First available in order

        # Step 4: Create the priority
        priority = PgPriority(
            user_id=user_id,
            name=request.name,
            type=request.type,
            calendar_keyword=assigned_keyword,
            deadline=request.deadline,
            weekly_hour_target=request.weekly_hour_target,
            checkpoint_date=request.checkpoint_date,
            desired_result=request.desired_result,
        )

        session.add(priority)

        # Step 5: Commit (flush first to catch IntegrityError before commit)
        await session.flush()
        await session.commit()

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
        priority_data = {
            "id": str(priority.id),
            "name": priority.name,
            "type": priority.type,
            "calendar_keyword": priority.calendar_keyword,
            "status": priority.status,
            "deadline": priority.deadline.isoformat() if priority.deadline else None,
            "weekly_hour_target": float(priority.weekly_hour_target) if priority.weekly_hour_target else None,
            "checkpoint_date": priority.checkpoint_date.isoformat() if priority.checkpoint_date else None,
            "desired_result": priority.desired_result,
            "deliverables": [],  # Always empty on creation
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
        error_str = str(e.orig) if e.orig else str(e)
        if "idx_pg_priorities_user_keyword_active" in error_str:
            # Race condition fallback: partial unique index violation
            logger.warning(
                "priority.create.keyword_race_condition",
                user_id=str(user_id),
                error=error_str,
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
            # Unexpected constraint violation — log full error and return 500
            logger.error(
                "priority.create.unexpected_integrity_error",
                user_id=str(user_id),
                error=error_str,
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
        # Unexpected error
        await session.rollback()

        logger.error(
            "priority.create.unexpected_error",
            user_id=str(user_id),
            error=str(e),
            error_type=type(e).__name__,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again.",
        )
