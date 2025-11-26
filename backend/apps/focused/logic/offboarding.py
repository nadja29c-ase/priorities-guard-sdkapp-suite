"""
Offboarding logic for Focused SDK app (Increment 10).

Handles user disconnect and data deletion for GDPR compliance.

Disconnect sequence (order matters):
1. Stop Google webhook channel
2. Revoke Google OAuth token
3. Mark ChatGPT OAuth tokens as revoked
4. Update core_connections (mark revoked, clear webhook fields)
5. Clear Redis cache

Delete-data sequence:
1. Call disconnect logic first (if not already disconnected)
2. Delete from focused_focus_sessions
3. Delete from focused_user_keywords
4. Delete already-revoked Focused OAuth tokens
5. Write audit log
"""

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.models import CoreConnection, CoreToolAuditLog
from backend.core.encryption import decrypt_token
from backend.core.google_oauth import revoke_google_token
from backend.core.google_calendar import stop_webhook_channel
from backend.core.oauth_provider.models import OAuthAccessToken, OAuthAuthorizationCode
from backend.apps.focused.db_models import FocusedFocusSession, FocusedUserKeyword

logger = logging.getLogger(__name__)


async def disconnect_user(
    user_id: UUID,
    session: AsyncSession,
    http_client: httpx.AsyncClient,
    redis_client: Any,
) -> dict[str, Any]:
    """
    Disconnect user from Focused app.

    Revokes Google OAuth, stops webhook channel, marks ChatGPT tokens revoked,
    and clears Redis cache. Does NOT delete user data.

    Args:
        user_id: User UUID to disconnect
        session: Database session
        http_client: HTTP client for Google API calls
        redis_client: Redis client for cache clearing

    Returns:
        Dictionary with:
        - success: bool
        - already_disconnected: bool (True if user was already disconnected)
        - revoked_at: str (ISO timestamp)
        - details: dict (what was done)
    """
    logger.info(f"[offboarding] Starting disconnect for user {user_id}")

    details = {
        "google_token_revoked": False,
        "webhook_stopped": False,
        "chatgpt_tokens_revoked": 0,
        "redis_keys_deleted": 0,
    }

    # 1. Load Google connection
    stmt = select(CoreConnection).where(
        CoreConnection.user_id == user_id,
        CoreConnection.provider == "google",
    )
    result = await session.execute(stmt)
    connection = result.scalar_one_or_none()

    if connection is None:
        logger.info(f"[offboarding] No Google connection found for user {user_id}")
        return {
            "success": True,
            "already_disconnected": True,
            "revoked_at": datetime.now(timezone.utc).isoformat(),
            "details": details,
        }

    # Check if already disconnected
    if connection.revoked_at is not None:
        logger.info(f"[offboarding] User {user_id} already disconnected at {connection.revoked_at}")
        return {
            "success": True,
            "already_disconnected": True,
            "revoked_at": connection.revoked_at.isoformat(),
            "details": details,
        }

    # 2. Stop Google webhook channel (if exists)
    if connection.google_channel_id and connection.google_resource_id:
        try:
            # Decrypt access token for API call
            access_token = decrypt_token(connection.encrypted_access_token)

            stop_result = await stop_webhook_channel(
                http_client=http_client,
                access_token=access_token,
                channel_id=connection.google_channel_id,
                resource_id=connection.google_resource_id,
            )
            details["webhook_stopped"] = stop_result.get("success", False)
            if not stop_result["success"]:
                logger.warning(
                    f"[offboarding] Webhook stop failed for user {user_id}: "
                    f"{stop_result.get('error')}"
                )
        except Exception as e:
            logger.warning(f"[offboarding] Webhook stop error for user {user_id}: {e}")
            # Continue - non-blocking

    # 3. Revoke Google OAuth token
    if connection.encrypted_refresh_token:
        try:
            refresh_token = decrypt_token(connection.encrypted_refresh_token)
            revoke_result = await revoke_google_token(
                refresh_token=refresh_token,
                http_client=http_client,
            )
            details["google_token_revoked"] = revoke_result.get("success", False)
            if not revoke_result["success"]:
                logger.warning(
                    f"[offboarding] Google token revoke failed for user {user_id}: "
                    f"{revoke_result.get('error')}"
                )
        except Exception as e:
            logger.warning(f"[offboarding] Google token revoke error for user {user_id}: {e}")
            # Continue - non-blocking

    # 4. Mark ChatGPT OAuth tokens as revoked (Focused-scoped only)
    now = datetime.now(timezone.utc)
    try:
        # Mark access tokens as revoked
        # Use ANY() for PostgreSQL array contains check
        from sqlalchemy import any_
        stmt = (
            update(OAuthAccessToken)
            .where(
                OAuthAccessToken.user_id == user_id,
                OAuthAccessToken.revoked == False,  # noqa: E712
                "focused.read" == any_(OAuthAccessToken.scope),  # Focused-scoped
            )
            .values(revoked=True, revoked_at=now)
        )
        result = await session.execute(stmt)
        details["chatgpt_tokens_revoked"] = result.rowcount

        # Delete unused authorization codes (they're single-use anyway)
        stmt = delete(OAuthAuthorizationCode).where(
            OAuthAuthorizationCode.user_id == user_id,
            "focused.read" == any_(OAuthAuthorizationCode.scope),
        )
        await session.execute(stmt)

    except Exception as e:
        logger.error(f"[offboarding] OAuth token revocation error for user {user_id}: {e}")
        # Continue - we still need to update the connection

    # 5. Update core_connections (mark revoked, clear webhook fields)
    connection.revoked_at = now
    connection.google_channel_id = None
    connection.google_resource_id = None
    connection.google_channel_expires_at = None

    await session.flush()

    # 6. Clear Redis cache
    try:
        deleted_keys = await clear_user_redis_cache(
            user_id=str(user_id),
            redis_client=redis_client,
        )
        details["redis_keys_deleted"] = deleted_keys
    except Exception as e:
        logger.warning(f"[offboarding] Redis cache clear error for user {user_id}: {e}")
        # Continue - non-blocking

    logger.info(
        f"[offboarding] Disconnect completed for user {user_id}: "
        f"google_revoked={details['google_token_revoked']}, "
        f"webhook_stopped={details['webhook_stopped']}, "
        f"chatgpt_tokens={details['chatgpt_tokens_revoked']}"
    )

    return {
        "success": True,
        "already_disconnected": False,
        "revoked_at": now.isoformat(),
        "details": details,
    }


async def delete_user_data(
    user_id: UUID,
    session: AsyncSession,
    http_client: httpx.AsyncClient,
    redis_client: Any,
) -> dict[str, Any]:
    """
    Delete all Focused app data for user (GDPR Art. 17 compliance).

    Calls disconnect first, then deletes all Focused-specific data.
    Does NOT delete core_users row (shared across SDK apps).

    Args:
        user_id: User UUID to delete data for
        session: Database session
        http_client: HTTP client for Google API calls
        redis_client: Redis client for cache clearing

    Returns:
        Dictionary with:
        - success: bool
        - tables_affected: int
        - rows_deleted: dict (per table)
        - audit_log_id: str
    """
    logger.info(f"[offboarding] Starting delete-data for user {user_id}")

    rows_deleted = {
        "focused_focus_sessions": 0,
        "focused_user_keywords": 0,
        "oauth_access_tokens": 0,
    }

    # 1. Call disconnect logic first
    disconnect_result = await disconnect_user(
        user_id=user_id,
        session=session,
        http_client=http_client,
        redis_client=redis_client,
    )

    if not disconnect_result["success"]:
        logger.error(f"[offboarding] Disconnect failed during delete-data for user {user_id}")
        # Continue with deletion anyway - best effort

    # 2. Delete from focused_focus_sessions
    try:
        stmt = delete(FocusedFocusSession).where(
            FocusedFocusSession.user_id == user_id
        )
        result = await session.execute(stmt)
        rows_deleted["focused_focus_sessions"] = result.rowcount
        logger.info(f"[offboarding] Deleted {result.rowcount} focus sessions for user {user_id}")
    except Exception as e:
        logger.error(f"[offboarding] Error deleting focus sessions for user {user_id}: {e}")

    # 3. Delete from focused_user_keywords
    try:
        stmt = delete(FocusedUserKeyword).where(
            FocusedUserKeyword.user_id == user_id
        )
        result = await session.execute(stmt)
        rows_deleted["focused_user_keywords"] = result.rowcount
        logger.info(f"[offboarding] Deleted {result.rowcount} user keywords for user {user_id}")
    except Exception as e:
        logger.error(f"[offboarding] Error deleting user keywords for user {user_id}: {e}")

    # 4. Delete already-revoked Focused OAuth tokens
    # ONLY delete tokens that are:
    # - Already marked as revoked (done in disconnect step)
    # - Focused-scoped
    try:
        from sqlalchemy import any_
        stmt = delete(OAuthAccessToken).where(
            OAuthAccessToken.user_id == user_id,
            OAuthAccessToken.revoked == True,  # noqa: E712
            "focused.read" == any_(OAuthAccessToken.scope),
        )
        result = await session.execute(stmt)
        rows_deleted["oauth_access_tokens"] = result.rowcount
        logger.info(f"[offboarding] Deleted {result.rowcount} OAuth tokens for user {user_id}")
    except Exception as e:
        logger.error(f"[offboarding] Error deleting OAuth tokens for user {user_id}: {e}")

    # 5. Write audit log
    tables_affected = sum(1 for v in rows_deleted.values() if v > 0)
    audit_log = CoreToolAuditLog(
        user_id=user_id,
        app_name="focused",
        action="delete_data",
        result_status="success",
        details={
            "rows_deleted": rows_deleted,
            "disconnect_details": disconnect_result.get("details", {}),
        },
    )
    session.add(audit_log)
    await session.flush()

    logger.info(
        f"[offboarding] Delete-data completed for user {user_id}: "
        f"tables_affected={tables_affected}, rows={rows_deleted}"
    )

    return {
        "success": True,
        "tables_affected": tables_affected,
        "rows_deleted": rows_deleted,
        "audit_log_id": str(audit_log.id),
    }


async def clear_user_redis_cache(
    user_id: str,
    redis_client: Any,
) -> int:
    """
    Clear all Redis cache entries for a user.

    Uses SCAN + DELETE pattern (not KEYS - production safe).

    Args:
        user_id: User ID string
        redis_client: Redis client instance

    Returns:
        Number of keys deleted
    """
    patterns = [
        f"*:focused:needs_sync:{user_id}",
        f"*:focused:webhook:{user_id}:*",
        f"*:focused:webhook:renew_throttle:{user_id}",
    ]

    total_deleted = 0

    for pattern in patterns:
        try:
            # Use scan_iter for production-safe iteration
            async for key in redis_client.scan_iter(match=pattern):
                await redis_client.delete(key)
                total_deleted += 1
        except Exception as e:
            logger.warning(f"[offboarding] Error scanning Redis pattern {pattern}: {e}")

    logger.info(f"[offboarding] Cleared {total_deleted} Redis keys for user {user_id}")
    return total_deleted
