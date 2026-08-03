"""
Offboarding Router — User disconnect endpoint for Priority Guardian.

Endpoints:
- POST /disconnect: Revoke access without deleting data

Increment 01: Minimal disconnect only. No DELETE /delete-data yet (later increment).

Both endpoints require valid ChatGPT OAuth JWT for authentication.
User ID is extracted from the JWT sub claim via X-User-ID header.
"""

import structlog
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from backend.apps.priority_guardian.dependencies import verify_internal_call
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.priority_guardian.services.offboarding_service import (
    PgDeletionError,
    delete_user_data,
    revoke_google_access,
)
from backend.core.database import get_db
from backend.core.models import CoreConnection, CoreUser

logger = structlog.get_logger(__name__)

router = APIRouter(
    tags=["priority-guardian-offboarding"],
    dependencies=[Depends(verify_internal_call)],
)


@router.post("/disconnect")
async def disconnect(
    request: Request,
    x_user_id: str = Header(..., alias="X-User-ID"),
    session: AsyncSession = Depends(get_db),
):
    """
    Disconnect user from Priority Guardian app.

    PG disconnect is simpler than Focused's:
    - No webhook channel to stop (PG has no webhooks in Inc 01)
    - No focus sessions to clean up
    - No app-specific Redis cache to clear

    Just:
    1. Revoke Google OAuth token at Google (best-effort)
    2. Mark Google connection as revoked in core_connections

    Note: PG OAuth session tokens are NOT revoked here. Disconnect only revokes
    Google Calendar access. PG token revocation belongs in delete-account flows.

    Idempotent: calling twice returns 200 (already disconnected).

    Returns:
        200: {"status": "disconnected", "revoked_at": "<timestamp>"}
        422: Missing X-User-ID header (FastAPI validation)
        404: User not found
        500: Internal error
    """
    try:
        # X-User-ID extracted via Header() - FastAPI validates presence
        # Offboarding endpoints MUST be authenticated
        user_id = UUID(x_user_id)

        # Validate user exists in database
        user = await session.get(CoreUser, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        now = datetime.now(timezone.utc)
        details = {
            "google_token_revoked": False,
            "google_connection_revoked": False,
        }

        # 1. Load Google connection
        stmt = select(CoreConnection).where(
            CoreConnection.user_id == user_id,
            CoreConnection.provider == "google",
        )
        result = await session.execute(stmt)
        connection = result.scalar_one_or_none()

        if connection is None:
            logger.info("pg_offboarding.no_google_connection", user_id=str(user_id))
        elif connection.revoked_at is not None:
            logger.info(
                "pg_offboarding.already_disconnected",
                user_id=str(user_id),
                revoked_at=connection.revoked_at.isoformat(),
            )
            return {
                "status": "disconnected",
                "revoked_at": connection.revoked_at.isoformat(),
                "already_disconnected": True,
                "details": details,
            }
        else:
            # Revoke Google OAuth token (best-effort, before marking revoked in DB).
            # Extracted to services/offboarding_service.py so the delete-data path shares
            # one implementation rather than calling this route (which commits its own
            # transaction and returns early when already disconnected).
            # Behaviour here is unchanged: same order, same log events, same best-effort
            # semantics, same details key.
            revocation = await revoke_google_access(
                connection=connection,
                http_client=getattr(request.app.state, "http_client", None),
                user_id=user_id,
            )
            details["google_token_revoked"] = revocation["google_token_revoked"]

            # Mark connection as revoked
            connection.revoked_at = now
            details["google_connection_revoked"] = True
            await session.flush()

        await session.commit()

        logger.info(
            "pg_offboarding.disconnect_completed",
            user_id=str(user_id),
            google_token_revoked=details["google_token_revoked"],
            google_connection_revoked=details["google_connection_revoked"],
        )

        return {
            "status": "disconnected",
            "revoked_at": now.isoformat(),
            "already_disconnected": False,
            "details": details,
        }

    except ValueError as e:
        logger.error("pg_offboarding.invalid_user_id", error=str(e))
        raise HTTPException(status_code=400, detail=f"Invalid user ID: {e}")

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            "pg_offboarding.unexpected_error",
            error_type=type(e).__name__,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/delete-data")
async def delete_data(
    request: Request,
    x_user_id: str = Header(..., alias="X-User-ID"),
    session: AsyncSession = Depends(get_db),
):
    """
    Delete the user's Priority Guardian data. Operation A (ADR_008 §4).

    Deletes PG-owned tables and PG-scoped rows in shared tables. Does NOT delete the
    core_users row, the tool audit log, or the browser session — other Priority Guard Suite
    apps are unaffected. See services/offboarding_service.py for the verified inventory.

    NO COMMIT HERE. get_db commits when this returns and rolls back if it raises, so every
    local deletion plus the audit entry is one transaction.

    Idempotent: calling twice succeeds, the second call reporting zero rows.

    Returns:
        200: structured result — local deletion and Google revocation reported separately,
             never collapsed into a single success flag
        400: malformed X-User-ID
        404: user not found
        503: local deletion failed and was rolled back — explicitly retryable. If
             google_revocation_confirmed is true, Calendar access is already gone even
             though PG data remains, so this is never "nothing changed".
    """
    try:
        user_id = UUID(x_user_id)

        user = await session.get(CoreUser, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return await delete_user_data(
            user_id=user_id,
            session=session,
            http_client=getattr(request.app.state, "http_client", None),
        )

    except PgDeletionError as e:
        # The service already rolled back. Surfaced as 503 rather than 500 because the
        # condition is transient and the operation is safe to repeat.
        raise HTTPException(
            status_code=503,
            detail={
                "error": "deletion_failed",
                "message": e.message,
                "retryable": e.retryable,
                "google_revocation_confirmed": e.google_revoked,
            },
        )

    except ValueError as e:
        logger.error("pg_offboarding.invalid_user_id", error=str(e))
        raise HTTPException(status_code=400, detail=f"Invalid user ID: {e}")

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            "pg_offboarding.delete_data_unexpected_error",
            error_type=type(e).__name__,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail="Internal server error")
