"""
Offboarding Router — User disconnect and data deletion endpoints.

Endpoints:
- POST /disconnect: Revoke access without deleting data
- DELETE /delete-data: Full data deletion (GDPR Art. 17)

Both endpoints require valid ChatGPT OAuth JWT for authentication.
User ID is extracted from the JWT sub claim via X-User-ID header.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.redis_client import redis_client
from backend.core.models import CoreUser
from backend.apps.focused.logic.offboarding import disconnect_user, delete_user_data

logger = logging.getLogger(__name__)

router = APIRouter(tags=["focused-offboarding"])


@router.post("/disconnect")
async def disconnect(
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """
    Disconnect user from Focused app.

    Revokes Google OAuth, stops webhook channel, marks ChatGPT tokens revoked,
    and clears Redis cache. Does NOT delete user data.

    Idempotent: calling twice returns 200 (already disconnected).

    Returns:
        200: {"status": "disconnected", "revoked_at": "<timestamp>"}
        401: Missing authentication (X-User-ID header required)
        404: User not found
        500: Internal error
    """
    try:
        # Extract user_id from X-User-ID header (set by MCP after JWT validation)
        # Offboarding endpoints MUST be authenticated - no fallback allowed
        user_id_header = request.headers.get("x-user-id")
        if not user_id_header:
            raise HTTPException(
                status_code=401,
                detail="Authentication required. X-User-ID header missing."
            )
        user_id = UUID(user_id_header)

        # Validate user exists in database
        user = await session.get(CoreUser, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        http_client = request.app.state.http_client

        result = await disconnect_user(
            user_id=user_id,
            session=session,
            http_client=http_client,
            redis_client=redis_client,
        )

        if result["success"]:
            return {
                "status": "disconnected",
                "revoked_at": result["revoked_at"],
                "already_disconnected": result.get("already_disconnected", False),
                "details": result.get("details", {}),
            }
        else:
            raise HTTPException(status_code=500, detail="Disconnect failed")

    except ValueError as e:
        logger.error(f"[offboarding] Invalid user_id: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid user ID: {e}")

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"[offboarding] Disconnect error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/delete-data")
async def delete_data(
    request: Request,
    session: AsyncSession = Depends(get_db),
):
    """
    Delete all Focused app data for user (GDPR Art. 17).

    Sequence:
    1. Calls disconnect logic first
    2. Deletes focused_focus_sessions
    3. Deletes focused_user_keywords
    4. Deletes already-revoked Focused OAuth tokens
    5. Writes audit log

    Does NOT delete core_users row (shared across SDK apps).

    Idempotent: calling twice returns 200 (no data to delete).

    Returns:
        200: {"status": "deleted", "tables_affected": N}
        401: Missing authentication (X-User-ID header required)
        404: User not found
        500: Internal error
    """
    try:
        # Extract user_id from X-User-ID header (set by MCP after JWT validation)
        # Offboarding endpoints MUST be authenticated - no fallback allowed
        user_id_header = request.headers.get("x-user-id")
        if not user_id_header:
            raise HTTPException(
                status_code=401,
                detail="Authentication required. X-User-ID header missing."
            )
        user_id = UUID(user_id_header)

        # Validate user exists in database
        user = await session.get(CoreUser, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        http_client = request.app.state.http_client

        result = await delete_user_data(
            user_id=user_id,
            session=session,
            http_client=http_client,
            redis_client=redis_client,
        )

        if result["success"]:
            return {
                "status": "deleted",
                "tables_affected": result["tables_affected"],
                "rows_deleted": result["rows_deleted"],
                "audit_log_id": result["audit_log_id"],
            }
        else:
            raise HTTPException(status_code=500, detail="Delete failed")

    except ValueError as e:
        logger.error(f"[offboarding] Invalid user_id: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid user ID: {e}")

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"[offboarding] Delete-data error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
