"""
Offboarding service for Priority Guardian — authenticated data deletion.

Implements Operation A from doc/ADR/ADR_008_data_ownership_and_deletion_model.md: delete the
user's Priority Guardian data, leaving every other Priority Guard Suite app untouched.

WHAT IS DELETED (verified inventory — Part A report, §1 and §4):
  pg_priorities, pg_goals, pg_deliverables, pg_weekly_snapshots  — PG-owned
  core_consents            — PG-scoped rows only (app_name="priority_guardian")
  oauth_access_tokens      — PG-scoped rows only ('pg.access' in scope), revoked then deleted
  oauth_authorization_codes — PG-scoped rows only ('pg.access' in scope)
  core_connections         — the Google row, revoked at Google first

WHAT IS NEVER DELETED:
  core_users          — shared suite anchor; cascading it destroys other apps' data (ADR_008 §2)
  core_tool_audit_log — the record that deletion happened; expires on its own 90-day
                        schedule via cleanup_expired_audit_logs (ADR_008 §3)
  oauth_sessions      — suite-level browser session, not PG state. PG-scoped deletion is not
                        account deletion (pg_data_retention_and_permission_surface.md §10.1)

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

import asyncio

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
from backend.core.oauth_provider.models import OAuthAccessToken, OAuthAuthorizationCode

logger = structlog.get_logger(__name__)


# App identity used to isolate PG's rows in shared tables.
# Verified against backend/core/oauth_provider/authorize.py::APP_PREFIX_MAPPING,
# which maps the "pg." scope prefix to "priority_guardian". MindSort's rows carry
# "mindsort" / "clarity.write" and are never matched by these filters.
PG_APP_NAME = "priority_guardian"
PG_SCOPE = "pg.access"

# ---------------------------------------------------------------------------
# THE FILTERS BELOW ARE CORRECT ONLY BECAUSE OF INVARIANTS ENFORCED ELSEWHERE.
#
# Adversarial review found three row shapes that would defeat them. All three are
# unreachable through any code path at HEAD, and none is enforced at the storage boundary —
# so a future change to authorize.py or a new writer silently changes deletion correctness.
# Documented rather than fixed, per Nadja, 2026-08-03.
#
# 1. core_consents with app_name='unknown' AND scope='pg.access' would survive the
#    app_name filter. Unreachable: _derive_app_name_from_scopes maps any "pg." prefix to
#    "priority_guardian", and classify_scopes rejects multi-app requests. If revisited, the
#    safe fix is to WIDEN: app_name = PG_APP_NAME OR scope LIKE 'pg.%'. That cannot match a
#    MindSort row (app_name='mindsort', clarity.* scopes), so it fails toward deleting more
#    PG data — which is what the user asked for.
#
# 2. core_connections with provider='google' AND connection_type='unknown' is neither
#    revoked nor deleted here, because this path uses the conjunction while /disconnect
#    filters on provider alone. Unreachable: 7a1f4b2e3c9d backfilled every existing row and
#    both writers set the two columns together.
#
#    DO NOT "fix" this by dropping the conjunction. A stricter filter fails toward MISSED
#    DATA, which is recoverable by retrying once the row shape is understood. A looser one
#    fails toward destroying another application's Google connection, which is not
#    recoverable and is failure mode 1 from §0.2. /disconnect can afford the looser filter
#    because it MARKS a row revoked; this path DESTROYS it. Asymmetric consequences justify
#    asymmetric filters.
#
# 3. oauth_access_tokens / oauth_authorization_codes with a mixed scope array such as
#    ['pg.access', 'clarity.write'] would be deleted whole, taking MindSort's grant with it.
#    Unreachable: classify_scopes rejects multi-app authorize requests, so no such row can
#    be minted.
#
#    NOTE THE DIRECTION — this one is the inverse of (1). The safe fix here is to NARROW,
#    not widen: delete only rows whose scopes are exclusively pg.*. Widening would make the
#    cross-app destruction worse. Do not lump it with (1) when revisiting.
# ---------------------------------------------------------------------------

# Upper bound on the Google revocation call, for the DELETION path only.
#
# WHY THIS EXISTS. The shared client is httpx.AsyncClient(timeout=30.0) (backend/main.py:105)
# and revoke_google_token passes no timeout of its own, so the call can block for 30s. The
# MCP tool's budget is TIMEOUT_S = 8.0. Without a bound, a slow Google produces the worst
# possible outcome on an irreversible operation: the tool times out and tells the user their
# data was NOT deleted, while the backend request keeps running, completes the revocation,
# deletes everything and commits. The user is told nothing happened when everything did.
#
# 3s leaves room for the local deletes and the MCP -> backend hop inside the 8s budget.
# Revocation is already best-effort and a failure is already handled and reported, so
# treating a timeout as "unconfirmed" costs nothing.
#
# Deliberately NOT applied to /disconnect: that route is out of scope (§2) and bounding its
# call would change its behaviour. Hence a parameter defaulting to None rather than a bound
# inside revoke_google_access.
GOOGLE_REVOCATION_TIMEOUT_S = 3.0


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
    timeout_s: float | None = None,
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

        revoke_coro = revoke_google_token(
            refresh_token=refresh_token,
            http_client=http_client,
        )
        # timeout_s=None preserves /disconnect's existing unbounded behaviour exactly.
        if timeout_s is not None:
            revoke_result = await asyncio.wait_for(revoke_coro, timeout=timeout_s)
        else:
            revoke_result = await revoke_coro
        outcome["google_token_revoked"] = revoke_result.get("success", False)

        if not revoke_result.get("success"):
            outcome["error"] = revoke_result.get("error")
            logger.warning(
                "pg_offboarding.google_revoke_failed",
                user_id=str(user_id),
                error=revoke_result.get("error"),
            )

    except asyncio.TimeoutError:
        # Bounded deletion path only. Revocation is best-effort, so a timeout is reported as
        # unconfirmed and deletion proceeds — never raised.
        outcome["error"] = f"timeout after {timeout_s}s"
        logger.warning(
            "pg_offboarding.google_revoke_timeout",
            user_id=str(user_id),
            timeout_s=timeout_s,
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
        "oauth_authorization_codes": 0,
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
        timeout_s=GOOGLE_REVOCATION_TIMEOUT_S,
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
        # Revoke before delete, in this transaction — belt and braces, matching Focused.
        #
        # It is NOT what makes a concurrent refresh fail cleanly: inside one transaction the
        # UPDATE is invisible to other sessions until commit, by which point the DELETE is
        # visible too. A concurrent refresh blocks on the row lock and then finds the row
        # gone. The flag adds nothing the delete does not already provide, and this comment
        # previously claimed otherwise. Kept because it costs nothing and mirrors the
        # reference implementation, not because it closes a race.
        #
        # These rows hold a credential, not metadata about one — refresh_token_enc (Fernet)
        # and refresh_token_hash (indexed for lookup). Retaining them for the retention
        # strategy's 30-day "token audit log" would mean keeping a usable credential after
        # the user asked for deletion. Decided 2026-08-03; see
        # doc/legal/pg_data_retention_and_permission_surface.md.
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
        # Shared table: oauth_authorization_codes. Same shape as the token table —
        # user_id FK plus a scope ARRAY — so the same scope filter isolates PG's rows.
        #
        # Found by adversarial review of Part B, and it traces back to the gate artifact:
        # Part A's shared-table inventory omitted this table entirely. That is failure mode
        # 3 from §0.2 (a missed table), even though the practical exposure is near zero —
        # codes are single-use, expire in 10 minutes, and are swept by
        # cleanup_expired_oauth_codes. A user deleting their data is very unlikely to hold
        # a live code. Included because "verified inventory" has to mean verified.
        #
        # The reference implementation deletes these too, in disconnect_user rather than
        # delete_user_data; placed here because for PG this is deletion, not disconnect.
        # ---------------------------------------------------------------------
        result = await session.execute(
            delete(OAuthAuthorizationCode).where(
                OAuthAuthorizationCode.user_id == user_id,
                PG_SCOPE == any_(OAuthAuthorizationCode.scope),
            )
        )
        rows_deleted["oauth_authorization_codes"] = result.rowcount

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

    except asyncio.CancelledError:
        # CANCELLATION IS NOT AN Exception. asyncio.CancelledError inherits from
        # BaseException, so the handler below does NOT catch it — and neither does get_db,
        # whose own guard is `except Exception`. A client disconnecting mid-deletion
        # therefore skipped the rollback, the error event and PgDeletionError entirely,
        # leaving the §4 reverse case completely silent. Found by adversarial review.
        #
        # The exception is RE-RAISED rather than converted. Cancellation must propagate or
        # the task never actually stops; what was missing is the cleanup and the record, not
        # the exception. The caller sees cancellation, as it should.
        try:
            await session.rollback()
        except Exception as rollback_error:
            logger.error(
                "pg_offboarding.rollback_failed",
                user_id=str(user_id),
                error_type=type(rollback_error).__name__,
                error=str(rollback_error),
                original_error="CancelledError",
            )

        logger.error(
            "pg_offboarding.delete_data_cancelled",
            user_id=str(user_id),
            google_revocation_confirmed=google_revoked,
            partial_counts=rows_deleted,
        )
        raise

    except Exception as e:
        # Roll back before raising so no partial deletion can reach the database. get_db
        # would also roll back, but doing it here makes the guarantee local to this
        # function rather than dependent on the caller's plumbing.
        #
        # THE ROLLBACK ITSELF CAN FAIL — a dead connection or an exhausted pool — and an
        # unguarded `await session.rollback()` here would skip BOTH the error event and the
        # PgDeletionError below. The rollback's own exception would propagate instead, the
        # route's PgDeletionError handler would never fire, and the user would get the
        # dispatcher's generic "something went wrong" rather than "your data was NOT
        # deleted, this is safe to retry".
        #
        # That is the same false-report class as the 503 seam bug: a correct guarantee
        # defeated by an unhandled path. Found by adversarial review.
        #
        # Nothing is lost by continuing: if the rollback failed the connection is almost
        # certainly dead, so nothing was committed either way. What matters is that the
        # caller still learns the operation failed and is retryable.
        try:
            await session.rollback()
        except Exception as rollback_error:
            logger.error(
                "pg_offboarding.rollback_failed",
                user_id=str(user_id),
                error_type=type(rollback_error).__name__,
                error=str(rollback_error),
                original_error=str(e),
            )

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
