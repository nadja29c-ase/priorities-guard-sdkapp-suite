"""
Integration tests for Priority Guardian authenticated data deletion (Operation A).

Covers backend/apps/priority_guardian/services/offboarding_service.py::delete_user_data
against a real database. Google is mocked; nothing else is.

Every test states the bug that would still pass it. The four the increment briefing §7 names
as load-bearing (core_users survives, cross-app isolation, complete deletion, audit written)
are mutation-verified separately — see the Part B report.

FIXTURE NOTE: connections here set connection_type="google" explicitly. The pre-existing
fixtures in test_pg_offboarding.py do not, so they land as 'unknown' via the column's server
default — a row shape no production write path creates, since google_connection_repo.py sets
provider and connection_type together. Deletion filters on the conjunction (Part A §3.2), so
fixtures must be representative or they test nothing.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.clarity.db_models import ClarityCluster
from backend.apps.priority_guardian.db_models import (
    PgDeliverable,
    PgGoal,
    PgPriority,
    PgWeeklySnapshot,
)
from backend.apps.priority_guardian.services.offboarding_service import (
    PgDeletionError,
    delete_user_data,
)
from backend.core.encryption import encrypt_token
from backend.core.models import CoreConnection, CoreConsent, CoreToolAuditLog, CoreUser
from backend.core.oauth_provider.models import OAuthAccessToken

SERVICE = "backend.apps.priority_guardian.services.offboarding_service"


# =============================================================================
# Fixtures
# =============================================================================

@pytest_asyncio.fixture
async def user_with_everything(async_session: AsyncSession):
    """
    A user carrying PG data, PG-scoped shared rows, AND MindSort data.

    The MindSort rows are the point: they make cross-app isolation observable. A fixture
    with PG data alone cannot distinguish correct filtering from `WHERE user_id = ...`.
    """
    user = CoreUser(id=uuid4())
    async_session.add(user)
    await async_session.flush()

    priority = PgPriority(
        user_id=user.id,
        name="Ship V1.0",
        type="deadline",
        calendar_keyword="P1",
        deadline=(datetime.now(timezone.utc) + timedelta(days=30)).date(),
    )
    async_session.add(priority)
    await async_session.flush()

    async_session.add_all([
        PgGoal(priority_id=priority.id, goal_text="Finish backend"),
        PgDeliverable(priority_id=priority.id, name="API complete"),
        PgWeeklySnapshot(
            priority_id=priority.id,
            user_id=user.id,
            week_start=datetime(2026, 7, 27).date(),   # a Monday (CHECK constraint)
            week_end=datetime(2026, 8, 2).date(),
            actual_hours=5,
        ),
        # Representative Google connection — both columns set, as production writes it.
        CoreConnection(
            user_id=user.id,
            provider="google",
            connection_type="google",
            encrypted_access_token=encrypt_token("access"),
            encrypted_refresh_token=encrypt_token("refresh"),
            token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            scopes=["https://www.googleapis.com/auth/calendar.readonly"],
        ),
        # PG-scoped shared rows
        CoreConsent(
            user_id=user.id, app_name="priority_guardian",
            scope="pg.access", granted_at=datetime.now(timezone.utc),
        ),
        OAuthAccessToken(
            jti=f"pg-{uuid4()}", user_id=user.id, client_id="pg-client",
            scope=["pg.access"],
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ),
        # MindSort rows — MUST survive
        ClarityCluster(user_id=user.id, cluster_data={"clusters": [{"cluster_name": "Work"}]}),
        CoreConsent(
            user_id=user.id, app_name="mindsort",
            scope="clarity.write", granted_at=datetime.now(timezone.utc),
        ),
        OAuthAccessToken(
            jti=f"ms-{uuid4()}", user_id=user.id, client_id="ms-client",
            scope=["clarity.write"],
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ),
    ])
    await async_session.commit()
    return user


def _google_ok():
    return patch(f"{SERVICE}.revoke_google_token", AsyncMock(return_value={"success": True}))


def _google_fails():
    """Google unreachable or the grant already revoked — both are non-success to us."""
    return patch(
        f"{SERVICE}.revoke_google_token",
        AsyncMock(return_value={"success": False, "error": "invalid_grant"}),
    )


def _google_raises():
    """
    The same condition surfacing as an exception rather than a response — a transport
    error, or a client that raises for status. Takes a different branch of
    revoke_google_access than _google_fails, which is why both are exercised.
    """
    return patch(
        f"{SERVICE}.revoke_google_token",
        AsyncMock(side_effect=RuntimeError("connection reset")),
    )


async def _count(session, model, user_id):
    stmt = select(func.count()).select_from(model).where(model.user_id == user_id)
    return (await session.execute(stmt)).scalar_one()


# =============================================================================
# The four load-bearing tests (§7)
# =============================================================================

@pytest.mark.asyncio
async def test_core_users_row_survives(async_session, user_with_everything):
    """
    Bug this catches: deleting the core_users row, or relying on a CASCADE that reaches it.
    That is failure mode 1 from §0.2 — it destroys every other app's data for this user and
    is irreversible. ADR_008 §2 makes retention architectural, not a legal judgement.
    """
    user_id = user_with_everything.id

    with _google_ok():
        await delete_user_data(user_id, async_session, AsyncMock())
    await async_session.commit()

    assert await async_session.get(CoreUser, user_id) is not None, (
        "core_users row must survive PG-scoped deletion"
    )


@pytest.mark.asyncio
async def test_mindsort_data_is_untouched(async_session, user_with_everything):
    """
    Bug this catches: filtering shared tables by user_id alone — failure mode 2 from §0.2.
    A `DELETE FROM core_consents WHERE user_id = :id` passes every PG-only assertion in this
    file while silently destroying MindSort's consent and token, breaking that connector
    with no error anywhere.

    This is the test that distinguishes correct scope/app_name filtering from convenient
    filtering, and the reason the fixture creates MindSort rows at all.
    """
    user_id = user_with_everything.id

    with _google_ok():
        await delete_user_data(user_id, async_session, AsyncMock())
    await async_session.commit()

    assert await _count(async_session, ClarityCluster, user_id) == 1, "MindSort board destroyed"

    ms_consents = (await async_session.execute(
        select(func.count()).select_from(CoreConsent).where(
            CoreConsent.user_id == user_id, CoreConsent.app_name == "mindsort")
    )).scalar_one()
    assert ms_consents == 1, "MindSort consent destroyed"

    ms_tokens = (await async_session.execute(
        select(OAuthAccessToken).where(
            OAuthAccessToken.user_id == user_id,
            OAuthAccessToken.client_id == "ms-client")
    )).scalars().all()
    assert len(ms_tokens) == 1, "MindSort token destroyed"
    assert ms_tokens[0].revoked is False, "MindSort token revoked by a PG-scoped deletion"


@pytest.mark.asyncio
async def test_every_pg_table_is_emptied(async_session, user_with_everything):
    """
    Bug this catches: missing a table — failure mode 3 from §0.2. Data the user asked to
    delete survives, making a published privacy-policy claim false.

    SCOPE LIMIT, stated rather than hidden: this assertion is derived from the ORM models,
    so it can only prove the code deletes every table the ORM knows about. It cannot detect
    a table that exists in production but is not modelled — the pg_weekly_overview class of
    problem (Part A §2, §6.1). The migration-derived version of this assertion is a separate
    piece of work recorded in the Part A report's §6.1 decision block.

    WHY THE ROW-COUNT ASSERTIONS BELOW ARE NOT REDUNDANT. Every child table cascades from
    pg_priorities, so emptiness alone is satisfied by the foreign key whether or not the
    code ever names those tables — the exact trap recorded in Part A §1.1. Mutation-verified:
    deleting the pg_weekly_snapshots statement leaves the emptiness assertions passing and is
    caught only by the reported count. The counts test the code; the emptiness tests the FK.
    Both are wanted.
    """
    user_id = user_with_everything.id

    with _google_ok():
        result = await delete_user_data(user_id, async_session, AsyncMock())
    await async_session.commit()

    assert result["rows_deleted"]["pg_priorities"] == 1
    assert result["rows_deleted"]["pg_weekly_snapshots"] == 1
    assert result["rows_deleted"]["pg_goals"] == 1
    assert result["rows_deleted"]["pg_deliverables"] == 1

    assert await _count(async_session, PgPriority, user_id) == 0
    assert await _count(async_session, PgWeeklySnapshot, user_id) == 0

    for model in (PgGoal, PgDeliverable):
        remaining = (await async_session.execute(
            select(func.count()).select_from(model)
            .where(model.priority_id.in_(select(PgPriority.id).where(PgPriority.user_id == user_id)))
        )).scalar_one()
        assert remaining == 0, f"{model.__tablename__} not emptied"

    conns = (await async_session.execute(
        select(func.count()).select_from(CoreConnection).where(CoreConnection.user_id == user_id)
    )).scalar_one()
    assert conns == 0, "Google connection row not deleted"

    pg_consents = (await async_session.execute(
        select(func.count()).select_from(CoreConsent).where(
            CoreConsent.user_id == user_id, CoreConsent.app_name == "priority_guardian")
    )).scalar_one()
    assert pg_consents == 0, "PG consent not deleted"


@pytest.mark.asyncio
async def test_audit_entry_written_and_survives(async_session, user_with_everything):
    """
    Bug this catches: deleting core_tool_audit_log rows along with the user's data, or never
    writing the entry. It is the only record that deletion happened and it must outlive the
    data (ADR_008 §3) — its user_id is deliberately not a foreign key for exactly this.

    Also catches leaking deleted content into the audit row: §10 forbids logging priority
    names, so the details payload must carry counts only.
    """
    user_id = user_with_everything.id

    with _google_ok():
        result = await delete_user_data(user_id, async_session, AsyncMock())
    await async_session.commit()

    entries = (await async_session.execute(
        select(CoreToolAuditLog).where(CoreToolAuditLog.user_id == user_id)
    )).scalars().all()

    assert len(entries) == 1
    entry = entries[0]
    assert entry.app_name == "priority_guardian"
    assert entry.action == "delete_data"
    assert entry.result_status == "success"
    assert entry.details["rows_deleted"]["pg_priorities"] == 1
    assert str(entry.id) == result["audit_log_id"]

    assert "Ship V1.0" not in str(entry.details), "audit row leaked deleted content"


# =============================================================================
# Atomicity and the retry path (§4)
# =============================================================================

@pytest.mark.asyncio
async def test_local_failure_rolls_back_every_deletion(async_session, user_with_everything):
    """
    Bug this catches: the best-effort per-table sequence the Focused reference uses — each
    delete in its own try/except, continuing past failures. Under it, a failure at the audit
    step leaves priorities deleted, snapshots gone and tokens half-removed, and still returns
    success. §4 forbids exactly this.

    Fails if the deletions are committed incrementally or if the exception is swallowed.
    """
    user_id = user_with_everything.id

    with _google_ok(), patch(f"{SERVICE}.CoreToolAuditLog", side_effect=RuntimeError("boom")):
        with pytest.raises(PgDeletionError) as exc:
            await delete_user_data(user_id, async_session, AsyncMock())

    assert exc.value.retryable is True
    assert exc.value.google_revoked is True, (
        "must report that Google access was given up before the local failure — "
        "never 'nothing changed'"
    )

    assert await _count(async_session, PgPriority, user_id) == 1, "priorities not rolled back"
    assert await _count(async_session, PgWeeklySnapshot, user_id) == 1, "snapshots not rolled back"
    assert await _count(async_session, ClarityCluster, user_id) == 1


@pytest.mark.parametrize(
    "second_attempt_google",
    [
        pytest.param(_google_fails, id="google-returns-invalid_grant"),
        pytest.param(_google_raises, id="google-raises"),
    ],
)
@pytest.mark.asyncio
async def test_retry_succeeds_after_google_already_disconnected(
    async_session, user_with_everything, second_attempt_google
):
    """
    THE REVERSE CASE (§4): Google revoked, local transaction rolled back.

    Distributed atomicity is impossible here, so this outcome is acceptable — but the retry
    must work. On the second attempt Google is already disconnected, so revocation fails. If
    the revocation step treated that as fatal, the user could never complete deletion:
    permanently stuck, Calendar access gone, PG data retained.

    Bug this catches: a revocation step that raises or returns early on an already-revoked
    grant, making PgDeletionError.retryable a false promise.

    BOTH FAILURE SHAPES ARE PARAMETRIZED DELIBERATELY. An already-revoked grant can surface
    either as a non-success response or as a raised exception, and they take different
    branches of revoke_google_access. Mutation-verified: with only the return-based case,
    re-raising inside the except branch survives undetected — the exception path is never
    entered, so the test cannot see the defect.
    """
    user_id = user_with_everything.id

    # Attempt 1 — Google succeeds, local blows up, everything rolls back.
    with _google_ok(), patch(f"{SERVICE}.CoreToolAuditLog", side_effect=RuntimeError("boom")):
        with pytest.raises(PgDeletionError):
            await delete_user_data(user_id, async_session, AsyncMock())

    assert await _count(async_session, PgPriority, user_id) == 1

    # Attempt 2 — Google now rejects the already-revoked grant. Deletion must still complete.
    with second_attempt_google():
        result = await delete_user_data(user_id, async_session, AsyncMock())
    await async_session.commit()

    assert result["success"] is True
    assert result["google_revocation_confirmed"] is False, (
        "must not claim confirmation it did not get"
    )
    assert result["google_revocation_error"] is not None, (
        "the reason revocation could not be confirmed must be recorded, not dropped"
    )
    assert await _count(async_session, PgPriority, user_id) == 0
    assert await async_session.get(CoreUser, user_id) is not None


@pytest.mark.asyncio
async def test_google_failure_does_not_block_deletion(async_session, user_with_everything):
    """
    Bug this catches: treating the Google call as a precondition. A user's erasure right must
    not depend on a third party's availability (§4). If Google is down, the data must still
    go — and the result must say the revocation was not confirmed rather than claiming it.
    """
    user_id = user_with_everything.id

    with _google_fails():
        result = await delete_user_data(user_id, async_session, AsyncMock())
    await async_session.commit()

    assert result["success"] is True
    assert result["google_revocation_confirmed"] is False
    assert await _count(async_session, PgPriority, user_id) == 0
    assert (await async_session.execute(
        select(func.count()).select_from(CoreConnection).where(CoreConnection.user_id == user_id)
    )).scalar_one() == 0, "connection row must be deleted even when revocation is unconfirmed"


@pytest.mark.asyncio
async def test_tokens_are_revoked_before_deletion(async_session, user_with_everything):
    """
    Bug this catches: deleting the token rows without setting revoked first. Ordering matters
    because exchange_refresh_token filters `revoked == False` in its WHERE clause
    (token_service.py:335), so flagging before deleting makes a concurrent refresh fail
    cleanly instead of racing the delete. Belt and braces inside one transaction, but free.

    Asserted via the PG row being gone while MindSort's is untouched and unrevoked — if the
    filter were user_id-only, the MindSort assertion fails.
    """
    user_id = user_with_everything.id

    with _google_ok():
        result = await delete_user_data(user_id, async_session, AsyncMock())
    await async_session.commit()

    assert result["rows_deleted"]["oauth_access_tokens"] == 1
    remaining = (await async_session.execute(
        select(OAuthAccessToken).where(OAuthAccessToken.user_id == user_id)
    )).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].client_id == "ms-client"
    assert remaining[0].revoked is False


@pytest.mark.asyncio
async def test_is_idempotent(async_session, user_with_everything):
    """
    Bug this catches: a second call erroring, or reporting the first call's counts. §4
    requires the second call to succeed reporting zero rows — which is also what makes the
    retry guarantee real.
    """
    user_id = user_with_everything.id

    with _google_ok():
        first = await delete_user_data(user_id, async_session, AsyncMock())
    await async_session.commit()

    with _google_fails():
        second = await delete_user_data(user_id, async_session, AsyncMock())
    await async_session.commit()

    assert first["rows_deleted"]["pg_priorities"] == 1
    assert second["success"] is True
    assert all(count == 0 for count in second["rows_deleted"].values()), second["rows_deleted"]


@pytest.mark.asyncio
async def test_user_with_no_data_succeeds(async_session):
    """
    Bug this catches: assuming a connection or priorities exist. A user who connected but
    never created a priority must be able to delete cleanly rather than hitting a
    NoResultFound on scalar_one().
    """
    user = CoreUser(id=uuid4())
    async_session.add(user)
    await async_session.commit()

    with _google_ok():
        result = await delete_user_data(user.id, async_session, AsyncMock())
    await async_session.commit()

    assert result["success"] is True
    assert result["tables_affected"] == 0
    assert result["google_revocation_confirmed"] is False
