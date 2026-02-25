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
from sqlalchemy import select, update, any_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.encryption import decrypt_token
from backend.core.google_oauth import revoke_google_token
from backend.core.models import CoreConnection, CoreUser
from backend.core.oauth_provider.models import OAuthAccessToken, OAuthAuthorizationCode

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
    3. Mark PG OAuth tokens as revoked

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
            "pg_tokens_revoked": 0,
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
            # Still mark tokens as revoked even if no connection
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
            # Revoke Google OAuth token (best-effort, before marking revoked in DB)
            if connection.encrypted_refresh_token:
                try:
                    refresh_token = decrypt_token(connection.encrypted_refresh_token)
                    http_client = request.app.state.http_client
                    revoke_result = await revoke_google_token(
                        refresh_token=refresh_token,
                        http_client=http_client,
                    )
                    details["google_token_revoked"] = revoke_result.get("success", False)
                    if not revoke_result["success"]:
                        logger.warning(
                            "pg_offboarding.google_revoke_failed",
                            user_id=str(user_id),
                            error=revoke_result.get("error"),
                        )
                except Exception as e:
                    logger.warning(
                        "pg_offboarding.google_revoke_error",
                        user_id=str(user_id),
                        error=str(e),
                    )
                    # Continue - non-blocking
            else:
                logger.info(
                    "pg_offboarding.no_refresh_token",
                    user_id=str(user_id),
                )

            # Mark connection as revoked
            connection.revoked_at = now
            details["google_connection_revoked"] = True
            await session.flush()

        # 2. Mark PG OAuth tokens as revoked (pg.* scoped tokens only)
        try:
            stmt = (
                update(OAuthAccessToken)
                .where(
                    OAuthAccessToken.user_id == user_id,
                    OAuthAccessToken.revoked == False,  # noqa: E712
                    "pg.access" == any_(OAuthAccessToken.scope),  # PG-scoped
                )
                .values(revoked=True, revoked_at=now)
            )
            result = await session.execute(stmt)
            details["pg_tokens_revoked"] = result.rowcount

        except Exception as e:
            logger.error(
                "pg_offboarding.token_revocation_error",
                user_id=str(user_id),
                error=str(e),
            )
            # Continue - non-blocking

        await session.commit()

        logger.info(
            "pg_offboarding.disconnect_completed",
            user_id=str(user_id),
            google_token_revoked=details["google_token_revoked"],
            google_connection_revoked=details["google_connection_revoked"],
            pg_tokens_revoked=details["pg_tokens_revoked"],
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
