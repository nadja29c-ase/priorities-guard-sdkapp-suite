"""
Offboarding service for Priority Guardian — authenticated data deletion.

Implements Operation A from doc/ADR_008_data_ownership_and_deletion_model.md: delete the
user's Priority Guardian data, leaving every other Priority Guard Suite app untouched.

WHAT IS DELETED (verified inventory — Part A report, §1 and §4):
  pg_priorities, pg_goals, pg_deliverables, pg_weekly_snapshots  — PG-owned
  core_consents            — PG-scoped rows only (app_name="priority_guardian")
  oauth_access_tokens      — PG-scoped rows only ('pg.access' in scope), revoked then deleted
  core_connections         — the Google row, revoked at Google first

WHAT IS NEVER DELETED:
  core_users          — shared suite anchor; cascading it destroys other apps' data (ADR_008 §2)
  core_tool_audit_log — the record that deletion happened; expires on its own 90-day
                        schedule via cleanup_expired_audit_logs (ADR_008 §3)
  oauth_sessions      — suite-level browser session, not PG state. PG-scoped deletion is not
                        account deletion (data_retention_strategy.md §7.1)

DELIBERATE DIVERGENCE FROM THE REFERENCE IMPLEMENTATION.
backend/apps/focused/logic/offboarding.py::delete_user_data is the pattern this follows, but
it wraps each table delete in its own try/except and continues on failure, returning
success=True regardless. That is a best-effort sequence: it can leave priorities deleted,
snapshots retained and tokens half-removed, then report success. The increment briefing §4
forbids it for an erasure operation a privacy policy describes. The structure, the
rows_deleted accounting and the audit entry are copied; the error handling is not.

TRANSACTION BOUNDARY.
This function performs NO commit. backend/core/database.py::get_db commits when the request
handler returns and rolls back if it raises, so the request IS the transaction. Every local
deletion plus the audit entry therefore lands atomically. On local failure this function rolls
back explicitly and raises PgDeletionError, so no partial deletion can be committed.

This is also why the existing /disconnect route cannot be called as step 1: it commits its own
transaction and returns early when already disconnected. The Google revocation logic it needs
is extracted into revoke_google_access() below, which both paths call. /disconnect's behaviour
is unchanged — same lookup, same filter, same log events, same best-effort semantics.
"""

import structlog
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import any_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.priority_guardian.db_models import (
    PgDeliverable,
    PgGoal,
    PgPriority,
    PgWeeklySnapshot,
)
from backend.core.encryption import decrypt_token
from backend.core.google_oauth import revoke_google_token
from backend.core.models import CoreConnection, CoreConsent, CoreToolAuditLog
from backend.core.oauth_provider.models import OAuthAccessToken

logger = structlog.get_logger(__name__)


# App identity used to isolate PG's rows in shared tables.
# Verified against backend/core/oauth_provider/authorize.py::APP_PREFIX_MAPPING,
# which maps the "pg." scope prefix to "priority_guardian". MindSort's rows carry
# "mindsort" / "clarity.write" and are never matched by these filters.
PG_APP_NAME = "priority_guardian"
PG_SCOPE = "pg.access"


class PgDeletionError(Exception):
    """
    Raised when local deletion fails.

    `retryable` is always True: a retry is safe because every step tolerates work already
    done — the Google revocation tolerates an absent or already-revoked connection, and the
    local deletes are idempotent.

    `google_revoked` reports whether Google access was already given up before the local
    failure. When True the caller must NOT report "nothing changed": Calendar access is gone
    even though PG data remains.
    """

    def __init__(self, message: str, google_revoked: bool):
        super().__init__(message)
        self.message = message
        self.google_revoked = google_revoked
        self.retryable = True


async def revoke_google_access(
    connection: CoreConnection | None,
    http_client: httpx.AsyncClient | None,
    user_id: UUID,
) -> dict[str, Any]:
    """
    Revoke the user's Google OAuth token at Google. External call, best-effort.

    Extracted verbatim from offboarding_router.disconnect so both the disconnect and the
    delete paths share one implementation. Log event names are preserved exactly, because
    they are the operational signal for this flow.

    Tolerates an absent connection, an absent refresh token, and an absent HTTP client, so a
    retry after a partial failure proceeds rather than erroring. This is what makes
    PgDeletionError.retryable true.

    Does NOT touch the database. The caller decides what to persist and inside which
    transaction — that separation is what keeps this call outside the deletion transaction.

    Returns:
        {"google_token_revoked": bool, "error": str | None}
    """
    outcome: dict[str, Any] = {"google_token_revoked": False, "error": None}

    if connection is None:
        logger.info("pg_offboarding.no_google_connection", user_id=str(user_id))
        return outcome

    if not connection.encrypted_refresh_token:
        logger.info("pg_offboarding.no_refresh_token", user_id=str(user_id))
        return outcome

    try:
        refresh_token = decrypt_token(connection.encrypted_refresh_token)

        if http_client is None:
            logger.warning("pg_offboarding.no_http_client", user_id=str(user_id))
            outcome["error"] = "no_http_client"
            return outcome

        revoke_result = await revoke_google_token(
            refresh_token=refresh_token,
            http_client=http_client,
        )
        outcome["google_token_revoked"] = revoke_result.get("success", False)

        if not revoke_result.get("success"):
            outcome["error"] = revoke_result.get("error")
            logger.warning(
                "pg_offboarding.google_revoke_failed",
                user_id=str(user_id),
                error=revoke_result.get("error"),
            )

    except Exception as e:
        outcome["error"] = str(e)
        logger.warning(
            "pg_offboarding.google_revoke_error",
            user_id=str(user_id),
            error=str(e),
        )

    return outcome


async def delete_user_data(
    user_id: UUID,
    session: AsyncSession,
    http_client: httpx.AsyncClient | None,
) -> dict[str, Any]:
    """
    Delete the user's Priority Guardian data. Operation A (ADR_008 §4).

    Sequence, in the order the retention strategy specifies (§3) adapted to Operation A:
      1. Revoke the Google token AT GOOGLE — external, outside the transaction, best-effort
      2. Delete PG-owned tables
      3. Revoke then delete PG-scoped rows in shared tables, filtered by scope/app_name
      4. Delete the Google connection row
      5. Write the audit entry
    Steps 2-5 are one transaction owned by get_db. This function never commits.

    Idempotent: a second call revokes nothing, deletes nothing, and reports zero rows.

    Args:
        user_id: the CoreUser to delete PG data for. On ChatGPT this is already the
            reconciled canonical id — mcp_auth reconciles before handlers run (ADR_007 §3).
        session: request-scoped session. Owns the transaction; do not commit here.
        http_client: for the Google revocation call. May be None — deletion proceeds.

    Returns:
        {
          "success": bool,                      # local deletion committed-able
          "google_revocation_confirmed": bool,  # NEVER collapsed into success
          "google_revocation_error": str|None,
          "tables_affected": int,
          "rows_deleted": dict[str, int],
          "audit_log_id": str,
        }

    Raises:
        PgDeletionError: local deletion failed and was rolled back. Explicitly retryable.
    """
    logger.info("pg_offboarding.delete_data_started", user_id=str(user_id))

    rows_deleted: dict[str, int] = {
        "pg_weekly_snapshots": 0,
        "pg_goals": 0,
        "pg_deliverables": 0,
        "pg_priorities": 0,
        "oauth_access_tokens": 0,
        "core_consents": 0,
        "core_connections": 0,
    }

    # -------------------------------------------------------------------------
    # 1. Google revocation — EXTERNAL, OUTSIDE THE TRANSACTION
    #
    # A user's erasure right must not depend on a third party's availability, so a failure
    # here is recorded and does not block local deletion. The connection row is still
    # deleted below; the audit entry records the unconfirmed revocation.
    #
    # Filter note: the conjunction (provider AND connection_type) is the majority predicate
    # in this codebase and the one Part A §3.2 settled on. /disconnect uses provider alone
    # and reconcile_router uses connection_type alone — flagged, out of scope to change.
    # -------------------------------------------------------------------------
    google_stmt = select(CoreConnection).where(
        CoreConnection.user_id == user_id,
        CoreConnection.provider == "google",
        CoreConnection.connection_type == "google",
    )
    google_result = await session.execute(google_stmt)
    connection = google_result.scalar_one_or_none()

    revocation = await revoke_google_access(
        connection=connection,
        http_client=http_client,
        user_id=user_id,
    )
    google_revoked = revocation["google_token_revoked"]

    # -------------------------------------------------------------------------
    # 2-5. Local deletion — ONE TRANSACTION, no per-step error swallowing.
    #
    # Any failure rolls the whole thing back. Deliberately unlike the Focused reference,
    # which continues past a failed table and still reports success.
    # -------------------------------------------------------------------------
    try:
        # Child tables first, so the counts are real. Deleting pg_priorities first would
        # cascade the children away and every subsequent count would read zero — the
        # deletion would still be correct but the audit entry and tests would be lying.
        priority_ids = select(PgPriority.id).where(PgPriority.user_id == user_id)

        # Direct user_id column (denormalized), so this catches every snapshot the user owns
        # even if a priority row were somehow missing.
        result = await session.execute(
            delete(PgWeeklySnapshot).where(PgWeeklySnapshot.user_id == user_id)
        )
        rows_deleted["pg_weekly_snapshots"] = result.rowcount

        result = await session.execute(
            delete(PgGoal).where(PgGoal.priority_id.in_(priority_ids))
        )
        rows_deleted["pg_goals"] = result.rowcount

        result = await session.execute(
            delete(PgDeliverable).where(PgDeliverable.priority_id.in_(priority_ids))
        )
        rows_deleted["pg_deliverables"] = result.rowcount

        result = await session.execute(
            delete(PgPriority).where(PgPriority.user_id == user_id)
        )
        rows_deleted["pg_priorities"] = result.rowcount

        # ---------------------------------------------------------------------
        # Shared table: oauth_access_tokens. SCOPE-FILTERED, never by user_id alone —
        # user_id alone would take MindSort's tokens and silently break that connector.
        #
        # Revoke before delete, in this transaction. The revoked flag is what makes a
        # concurrent refresh fail cleanly: token_service.py:335 filters revoked == False in
        # the refresh-exchange WHERE clause. Deleting alone would race.
        #
        # These rows hold a credential, not metadata about one — refresh_token_enc (Fernet)
        # and refresh_token_hash (indexed for lookup). Retaining them for the retention
        # strategy's 30-day "token audit log" would mean keeping a usable credential after
        # the user asked for deletion. Decided 2026-08-03; see data_retention_strategy.md.
        # ---------------------------------------------------------------------
        pg_token_filter = (
            OAuthAccessToken.user_id == user_id,
            PG_SCOPE == any_(OAuthAccessToken.scope),
        )

        tokens_result = await session.execute(
            select(OAuthAccessToken).where(*pg_token_filter)
        )
        for token in tokens_result.scalars().all():
            token.revoked = True
            token.revoked_at = datetime.now(timezone.utc)
        await session.flush()

        result = await session.execute(delete(OAuthAccessToken).where(*pg_token_filter))
        rows_deleted["oauth_access_tokens"] = result.rowcount

        # ---------------------------------------------------------------------
        # Shared table: core_consents. Filtered by app_name, never by user_id alone.
        #
        # A request to delete PG data is a withdrawal of consent for PG processing, so the
        # retention strategy's stated trigger ("deleted on user revocation") fires and its
        # §3 step 2 applies. ADR_008 §1 agrees independently.
        # ---------------------------------------------------------------------
        result = await session.execute(
            delete(CoreConsent).where(
                CoreConsent.user_id == user_id,
                CoreConsent.app_name == PG_APP_NAME,
            )
        )
        rows_deleted["core_consents"] = result.rowcount

        # Google connection row. Deleted whether or not Google confirmed the revocation —
        # see step 1. Same conjunction filter used for the lookup above.
        if connection is not None:
            result = await session.execute(
                delete(CoreConnection).where(
                    CoreConnection.user_id == user_id,
                    CoreConnection.provider == "google",
                    CoreConnection.connection_type == "google",
                )
            )
            rows_deleted["core_connections"] = result.rowcount

        # ---------------------------------------------------------------------
        # Audit entry — inside the transaction, so it is present exactly when the deletion
        # it describes is. Never deleted by this or any other app path (ADR_008 §3).
        #
        # Row counts only. Never priority names, goal text or deliverable names: §10 forbids
        # logging deleted content, and this row outlives the data by design.
        # ---------------------------------------------------------------------
        tables_affected = sum(1 for count in rows_deleted.values() if count > 0)
        audit_log = CoreToolAuditLog(
            user_id=user_id,
            app_name=PG_APP_NAME,
            action="delete_data",
            result_status="success",
            details={
                "rows_deleted": rows_deleted,
                "tables_affected": tables_affected,
                "google_revocation_confirmed": google_revoked,
                "google_revocation_error": revocation["error"],
            },
        )
        session.add(audit_log)
        await session.flush()

    except Exception as e:
        # Roll back before raising so no partial deletion can reach the database. get_db
        # would also roll back, but doing it here makes the guarantee local to this
        # function rather than dependent on the caller's plumbing.
        await session.rollback()

        # The audit row rolled back with everything else, so the failed attempt is recorded
        # as a log event rather than a database row. This is the only trace of the reverse
        # case, which is why it is ERROR rather than WARNING.
        logger.error(
            "pg_offboarding.delete_data_failed",
            user_id=str(user_id),
            error_type=type(e).__name__,
            error=str(e),
            google_revocation_confirmed=google_revoked,
            partial_counts=rows_deleted,
        )

        raise PgDeletionError(
            "Local deletion failed and was rolled back. Priority Guardian data was NOT "
            "deleted. This operation is safe to retry.",
            google_revoked=google_revoked,
        ) from e

    logger.info(
        "pg_offboarding.delete_data_completed",
        user_id=str(user_id),
        tables_affected=tables_affected,
        rows_deleted=rows_deleted,
        google_revocation_confirmed=google_revoked,
    )

    return {
        "success": True,
        "google_revocation_confirmed": google_revoked,
        "google_revocation_error": revocation["error"],
        "tables_affected": tables_affected,
        "rows_deleted": rows_deleted,
        "audit_log_id": str(audit_log.id),
    }
