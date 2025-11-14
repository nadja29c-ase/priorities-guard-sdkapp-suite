"""
Google OAuth endpoints for Focused app.

Handles OAuth flow initiation and callback processing.
"""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.encryption import encrypt_token
from backend.core.google_oauth import (
    cleanup_expired_states,
    exchange_code,
    generate_auth_url,
    store_state,
    verify_and_consume_state,
)
from backend.core.models import CoreConnection

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Google OAuth"])


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    """Consistent error payload for OAuth endpoints."""
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": {
                "code": code,
                "message": message,
            },
        },
    )


@router.get("/google/start")
async def start_google_oauth(
    request: Request,
    user_id: str = Query(..., description="Temporary user identifier"),
    session: AsyncSession = Depends(get_db),
):
    """
    Initiate Google OAuth flow.

    Cleans up expired states, generates authorization URL with user_id encoded in state,
    stores state, and redirects user to Google consent screen.

    Args:
        request: FastAPI request object (provides access to app state)
        user_id: Temporary user identifier (query parameter, encoded in state)
        session: Database session

    Returns:
        307 redirect to Google authorization URL
    """
    request_id = getattr(request.state, "request_id", "unknown")

    try:
        logger.info(
            f"Starting Google OAuth flow for user_id={user_id}",
            extra={"request_id": request_id},
        )

        # Cleanup expired states
        await cleanup_expired_states(session)

        # Generate authorization URL and state (user_id encoded in state)
        auth_url, state = generate_auth_url(user_id)

        # Store state in database
        await store_state(session, state)

        logger.info(
            f"Generated OAuth URL for user_id={user_id}",
            extra={"request_id": request_id},
        )

        # Redirect to Google
        return RedirectResponse(url=auth_url, status_code=307)

    except Exception as e:
        logger.error(
            f"Failed to start OAuth flow: {e}",
            extra={"request_id": request_id},
        )
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": {
                    "code": "OAUTH_START_FAILED",
                    "message": "Failed to initiate OAuth flow",
                },
            },
        )


@router.get("/google/callback")
async def google_oauth_callback(
    request: Request,
    code: str | None = Query(None, description="Authorization code from Google"),
    state: str | None = Query(None, description="OAuth state token for CSRF protection"),
    session: AsyncSession = Depends(get_db),
):
    """
    Handle Google OAuth callback.

    Verifies state (extracts user_id), exchanges code for tokens, encrypts tokens,
    and stores them in database.

    Args:
        request: FastAPI request object (provides access to app state)
        code: Authorization code from Google
        state: OAuth state token for CSRF protection (contains encoded user_id)
        session: Database session

    Returns:
        JSON response with connection status
    """
    request_id = getattr(request.state, "request_id", "unknown")

    try:
        if not code or not state:
            logger.warning(
                "Missing required parameters in OAuth callback",
                extra={"request_id": request_id},
            )
            return _error_response(
                status_code=400,
                code="MISSING_PARAMETERS",
                message="Query parameters 'code' and 'state' are required",
            )

        # Verify and consume state (CSRF check) and extract user_id
        user_id = await verify_and_consume_state(session, state)
        if not user_id:
            logger.warning(
                "Invalid or expired OAuth state",
                extra={"request_id": request_id},
            )
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": {
                        "code": "INVALID_STATE",
                        "message": "Invalid or expired OAuth state",
                    },
                },
            )

        logger.info(
            f"Processing OAuth callback for user_id={user_id}",
            extra={"request_id": request_id},
        )

        # Exchange code for tokens
        http_client = request.app.state.http_client
        token_data = await exchange_code(code, http_client)

        # Calculate token expiration
        token_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=token_data["expires_in"]
        )

        # Encrypt tokens
        encrypted_access = encrypt_token(token_data["access_token"])
        encrypted_refresh = (
            encrypt_token(token_data["refresh_token"])
            if token_data["refresh_token"]
            else None
        )

        # Upsert to core_connections (PostgreSQL upsert pattern)
        stmt = insert(CoreConnection).values(
            user_id=user_id,
            provider="google",
            encrypted_access_token=encrypted_access,
            encrypted_refresh_token=encrypted_refresh,
            token_expires_at=token_expires_at,
            scopes=token_data["scopes"],
        )

        stmt = stmt.on_conflict_do_update(
            constraint="uq_user_provider",
            set_={
                "encrypted_access_token": encrypted_access,
                "encrypted_refresh_token": encrypted_refresh,
                "token_expires_at": token_expires_at,
                "scopes": token_data["scopes"],
                "updated_at": datetime.now(timezone.utc),
            },
        )

        await session.execute(stmt)
        await session.commit()

        logger.info(
            f"Successfully stored Google tokens for user_id={user_id}",
            extra={"request_id": request_id},
        )

        # Return success response
        return {
            "success": True,
            "data": {
                "connected": True,
                "provider": "google",
                "scopes": token_data["scopes"],
            },
        }

    except ValueError as e:
        logger.error(
            f"OAuth error for user_id={user_id}: {e}",
            extra={"request_id": request_id},
        )
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": {"code": "OAUTH_ERROR", "message": str(e)},
            },
        )

    except Exception as e:
        logger.error(
            f"Database error for user_id={user_id}: {e}",
            extra={"request_id": request_id},
        )
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": {
                    "code": "DATABASE_ERROR",
                    "message": "Failed to store OAuth tokens",
                },
            },
        )
