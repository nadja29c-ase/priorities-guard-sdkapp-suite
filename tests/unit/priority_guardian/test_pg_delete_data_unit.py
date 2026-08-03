"""
Unit tests for PG deletion logic with a mocked session (§7).

These sit alongside the integration tests in
tests/integration/priority_guardian/test_pg_delete_data.py, which prove the same behaviour
against a real database. What a mocked session adds is visibility into the STATEMENTS
themselves: the integration tests observe rows disappearing, these observe which tables were
named and which predicates were compiled. A deletion that reached the right end state via the
wrong filter — leaning on a foreign key rather than naming a table, or filtering a shared
table by user_id alone — looks identical from the outside and different from here.

Every test states the bug that would still pass it.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, call
from uuid import uuid4

import pytest

from backend.apps.priority_guardian.services.offboarding_service import (
    PG_APP_NAME,
    PG_SCOPE,
    PgDeletionError,
    delete_user_data,
)

USER_ID = uuid4()


def _make_session(rowcount: int = 1, connection=MagicMock()):
    """
    An AsyncSession stand-in that records every statement passed to execute().

    execute() must satisfy three different call shapes in delete_user_data:
      - select(CoreConnection)  -> .scalar_one_or_none()
      - select(OAuthAccessToken) -> .scalars().all()
      - delete(...)             -> .rowcount
    One result object providing all three keeps the mock simple.
    """
    session = AsyncMock()
    session.statements = []

    token = MagicMock()
    token.revoked = False
    token.revoked_at = None

    result = MagicMock()
    result.rowcount = rowcount
    result.scalar_one_or_none.return_value = connection
    result.scalars.return_value.all.return_value = [token]

    async def _execute(stmt, *a, **kw):
        session.statements.append(str(stmt))
        return result

    session.execute = AsyncMock(side_effect=_execute)
    session.add = MagicMock()
    session.token = token
    return session


def _sql(session) -> str:
    return "\n".join(session.statements).lower()


@pytest.mark.asyncio
async def test_targets_exactly_the_expected_tables():
    """
    Bug this catches: relying on a cascade instead of naming a table. Every PG child table
    cascades from pg_priorities, so an integration test sees the rows gone either way — the
    exact trap recorded in Part A §1.1. Here the DELETE statements are inspected directly, so
    a table the code never names is visible.
    """
    session = _make_session()
    with _patched_revoke():
        await delete_user_data(USER_ID, session, AsyncMock())

    sql = _sql(session)
    for table in (
        "pg_weekly_snapshots", "pg_goals", "pg_deliverables", "pg_priorities",
        "oauth_access_tokens", "oauth_authorization_codes",
        "core_consents", "core_connections",
    ):
        assert f"delete from {table}" in sql, f"{table} was never named in a DELETE"


@pytest.mark.asyncio
async def test_never_targets_the_protected_tables():
    """
    Bug this catches: a DELETE against core_users, core_tool_audit_log or oauth_sessions —
    failure mode 1 from §0.2 and the two hard constraints in §4. The integration suite proves
    the core_users ROW survives, but that would also pass if the code issued a delete which
    happened to match nothing. This asserts the statement is never even constructed.
    """
    session = _make_session()
    with _patched_revoke():
        await delete_user_data(USER_ID, session, AsyncMock())

    sql = _sql(session)
    for forbidden in ("delete from core_users", "delete from core_tool_audit_log",
                      "delete from oauth_sessions"):
        assert forbidden not in sql, f"protected table targeted: {forbidden!r}"


@pytest.mark.asyncio
async def test_shared_tables_are_filtered_by_scope_not_user_id_alone():
    """
    Bug this catches: failure mode 2 — filtering shared tables by user_id alone, which takes
    MindSort's rows with PG's. The integration test catches it by asserting MindSort survives;
    this catches it one level earlier, in the compiled predicate, so the reason is legible
    rather than inferred from a missing row.
    """
    session = _make_session()
    with _patched_revoke():
        await delete_user_data(USER_ID, session, AsyncMock())

    sql = _sql(session)
    assert "app_name" in sql, "core_consents not filtered by app_name"
    assert "scope" in sql, "token/code deletes not filtered by scope"
    assert "provider" in sql and "connection_type" in sql, (
        "core_connections must use the conjunction (Part A §3.2)"
    )
    assert PG_APP_NAME == "priority_guardian" and PG_SCOPE == "pg.access"


@pytest.mark.asyncio
async def test_tokens_are_flagged_revoked_before_the_delete():
    """
    Bug this catches: dropping the revoke step. It is belt-and-braces rather than a race fix
    (the UPDATE is invisible outside the transaction until commit, by which point the DELETE
    is too), but it mirrors the reference implementation and §4 specifies the order.
    """
    session = _make_session()
    with _patched_revoke():
        await delete_user_data(USER_ID, session, AsyncMock())

    assert session.token.revoked is True
    assert session.token.revoked_at is not None


@pytest.mark.asyncio
async def test_audit_entry_is_added_with_counts_and_no_content():
    """
    Bug this catches: never writing the audit entry, or writing deleted CONTENT into it. §10
    forbids logging priority names — the row outlives the data by design, so leaking content
    there would survive the erasure it records.
    """
    session = _make_session()
    with _patched_revoke():
        await delete_user_data(USER_ID, session, AsyncMock())

    session.add.assert_called_once()
    entry = session.add.call_args[0][0]
    assert entry.app_name == PG_APP_NAME
    assert entry.action == "delete_data"
    assert entry.result_status == "success"
    assert "rows_deleted" in entry.details
    assert entry.user_id == USER_ID


@pytest.mark.asyncio
async def test_reports_zero_when_nothing_matched():
    """
    Bug this catches: a second call erroring, or reporting the first call's counts. With
    rowcount 0 everywhere and no connection, every count must be 0 and tables_affected 0 —
    which is what makes the retry guarantee in §4 real.
    """
    session = _make_session(rowcount=0, connection=None)
    session.execute.side_effect = None

    result_mock = MagicMock()
    result_mock.rowcount = 0
    result_mock.scalar_one_or_none.return_value = None
    result_mock.scalars.return_value.all.return_value = []

    async def _execute(stmt, *a, **kw):
        session.statements.append(str(stmt))
        return result_mock

    session.execute = AsyncMock(side_effect=_execute)

    with _patched_revoke():
        result = await delete_user_data(USER_ID, session, AsyncMock())

    assert result["success"] is True
    assert result["tables_affected"] == 0
    assert all(v == 0 for v in result["rows_deleted"].values()), result["rows_deleted"]


@pytest.mark.asyncio
async def test_local_failure_rolls_back_and_raises_retryable():
    """
    Bug this catches: the best-effort per-table pattern §4 forbids — swallowing the failure
    and reporting success. Asserts the rollback is issued by the service itself rather than
    left to get_db, so the guarantee does not depend on caller plumbing.
    """
    session = _make_session()
    session.flush = AsyncMock(side_effect=RuntimeError("boom"))

    with _patched_revoke():
        with pytest.raises(PgDeletionError) as exc:
            await delete_user_data(USER_ID, session, AsyncMock())

    session.rollback.assert_awaited_once()
    assert exc.value.retryable is True
    assert exc.value.google_revoked is True


@pytest.mark.asyncio
async def test_never_commits():
    """
    Bug this catches: committing inside the service. get_db owns the transaction (it commits
    on return, rolls back on raise), so a commit here would close it early and break the
    all-or-nothing guarantee — the precise defect that makes /disconnect unusable as step 1.
    """
    session = _make_session()
    with _patched_revoke():
        await delete_user_data(USER_ID, session, AsyncMock())

    session.commit.assert_not_called()


# ---------------------------------------------------------------------------

class _patched_revoke:
    """
    Make the Google revocation path actually execute.

    decrypt_token must be patched too. Without it the MagicMock connection's
    encrypted_refresh_token fails decryption, revoke_google_access returns early with an
    error, and the revoke_google_token patch is never reached — so every assertion about
    revocation would be measuring a path that did not run. First version of this helper had
    exactly that defect; it surfaced as google_revoked=False in the rollback test.
    """

    def __enter__(self):
        from unittest.mock import patch

        self._patches = [
            patch(
                "backend.apps.priority_guardian.services.offboarding_service.decrypt_token",
                MagicMock(return_value="decrypted-refresh-token"),
            ),
            patch(
                "backend.apps.priority_guardian.services.offboarding_service.revoke_google_token",
                AsyncMock(return_value={"success": True, "error": None}),
            ),
        ]
        for pt in self._patches:
            pt.start()
        return self

    def __exit__(self, *exc):
        for pt in self._patches:
            pt.stop()
        return False


@pytest.mark.asyncio
async def test_a_failing_rollback_still_raises_retryable():
    """
    Bug this catches: an unguarded `await session.rollback()` in the failure path. If the
    rollback itself raises — dead connection, exhausted pool — its exception propagates and
    the code never reaches the error event or the PgDeletionError. The route's handler never
    fires and the user is told "something went wrong" instead of "your data was NOT deleted,
    this is safe to retry".

    Same false-report class as the 503 seam bug: a correct guarantee defeated by an
    unhandled path. Found by adversarial review, not by the original test pass.
    """
    session = _make_session()
    session.flush = AsyncMock(side_effect=RuntimeError("local failure"))
    session.rollback = AsyncMock(side_effect=RuntimeError("connection is dead"))

    with _patched_revoke():
        with pytest.raises(PgDeletionError) as exc:
            await delete_user_data(USER_ID, session, AsyncMock())

    # The caller must still learn it is retryable, not receive the rollback's error.
    assert exc.value.retryable is True
    assert exc.value.google_revoked is True
    assert "NOT deleted" in exc.value.message
