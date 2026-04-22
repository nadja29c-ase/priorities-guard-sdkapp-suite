"""
Unit tests for reconcile_router._reconcile_user_by_subject (Increment 78).

Tests the reconciliation algorithm cases:
- Case A: First-time bind (new subject)
- Case B: Match, same user (steady state)
- Case C1: Cross-device (fresh shell remapped to canonical)
- Case C2: Ambiguous collision (hydrated user, no remap)
"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock

from sqlalchemy import select, Select, Update

from backend.apps.priority_guardian.routers.reconcile_router import _reconcile_user_by_subject
from backend.apps.priority_guardian.db_models import PgPriority
from backend.core.models import CoreUser, CoreConnection


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
async def user_a(async_session):
    """Create a CoreUser with openai_subject set."""
    user = CoreUser(id=uuid4(), openai_subject="v1/test-subject-a")
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def user_b_fresh(async_session):
    """Create a fresh CoreUser with no openai_subject, no connections, no priorities."""
    user = CoreUser(id=uuid4(), openai_subject=None)
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def user_with_google(async_session):
    """Create a CoreUser with an active Google connection."""
    from datetime import datetime, timezone

    user = CoreUser(id=uuid4(), openai_subject=None)
    async_session.add(user)
    await async_session.flush()

    connection = CoreConnection(
        user_id=user.id,
        provider="google",
        connection_type="google",
        encrypted_access_token="enc-token",
        token_expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        scopes=["calendar.readonly"],
        revoked_at=None,  # Active connection
    )
    async_session.add(connection)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def user_with_revoked_google(async_session):
    """Create a CoreUser with a revoked Google connection."""
    from datetime import datetime, timezone

    user = CoreUser(id=uuid4(), openai_subject=None)
    async_session.add(user)
    await async_session.flush()

    connection = CoreConnection(
        user_id=user.id,
        provider="google",
        connection_type="google",
        encrypted_access_token="enc-token",
        token_expires_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        scopes=["calendar.readonly"],
        revoked_at=datetime.now(timezone.utc),  # Revoked
    )
    async_session.add(connection)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def user_with_priority(async_session):
    """Create a CoreUser with a PgPriority."""
    from datetime import date

    user = CoreUser(id=uuid4(), openai_subject=None)
    async_session.add(user)
    await async_session.flush()

    priority = PgPriority(
        user_id=user.id,
        name="Test Priority",
        type="deadline",
        calendar_keyword="P1",
        deadline=date(2099, 12, 31),
        status="active",
    )
    async_session.add(priority)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def user_with_retired_priority(async_session):
    """Create a CoreUser with a retired PgPriority."""
    from datetime import date, datetime, timezone

    user = CoreUser(id=uuid4(), openai_subject=None)
    async_session.add(user)
    await async_session.flush()

    priority = PgPriority(
        user_id=user.id,
        name="Retired Priority",
        type="deadline",
        calendar_keyword="P1",
        deadline=date(2025, 1, 1),
        status="retired",
        retired_at=datetime.now(timezone.utc),
    )
    async_session.add(priority)
    await async_session.commit()
    await async_session.refresh(user)
    return user


# =============================================================================
# Case A Tests
# =============================================================================

@pytest.mark.asyncio
async def test_case_a_first_bind_new_subject(async_session, user_b_fresh):
    """No CoreUser has subject S. Call with jwt_user_id=X stamps X.openai_subject=S. Returns (X, "A")."""
    subject = "v1/brand-new-subject"

    user_id, case = await _reconcile_user_by_subject(
        db=async_session,
        jwt_user_id=user_b_fresh.id,
        openai_subject=subject,
        correlation_id="test-corr-id",
    )

    assert user_id == user_b_fresh.id
    assert case == "A"

    # Verify the subject was stamped
    await async_session.refresh(user_b_fresh)
    assert user_b_fresh.openai_subject == subject


@pytest.mark.asyncio
async def test_case_a_race_lost_winner_found():
    """
    Exercises the real race-lost-winner-found code path:
      1. Initial SELECT by subject -> None (race window: subject not yet bound)
      2. Guarded UPDATE -> rowcount == 0 (another request won the race)
      3. Re-SELECT by subject -> winner_id (the concurrent writer's user_id)
      4. Function falls through to Case C logic with subject_user_id set
      5. jwt_user_id is a fresh shell (fake DB returns no Google/priorities) -> C1

    Uses a deterministic fake session that routes statements by class and tracks
    call order so the first SELECT returns None while the second returns the
    winner. Does not rely on MagicMock's accidental isinstance behavior.

    NOTE: This is the test the previous version was named for but did not
    actually exercise. The real-DB C1 path is covered by
    test_case_c1_fresh_shell_returns_canonical; this test fills in the
    race-lost-winner-found gap.
    """
    jwt_user_id = uuid4()
    winner_id = uuid4()
    subject = "v1/race-subject"

    # Track how many SELECT-by-subject calls have happened so the first
    # returns None and the second returns winner_id. Other SELECTs (Google
    # connection exists(), priorities exists()) also return None/False.
    select_subject_call_count = 0

    class FakeSubjectSelectResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    class FakeExistsResult:
        def scalar(self):
            return False  # No Google connection, no priorities -> fresh shell

    class FakeUpdateResult:
        rowcount = 0  # Race lost: UPDATE matched zero rows

    fake_session = AsyncMock()

    async def fake_execute(stmt):
        nonlocal select_subject_call_count
        if isinstance(stmt, Update):
            return FakeUpdateResult()
        if isinstance(stmt, Select):
            # Distinguish subject-lookup SELECTs from exists() SELECTs by
            # checking the compiled SQL. The subject SELECT is the only one
            # that references CoreUser.openai_subject.
            compiled = str(stmt.compile())
            if "openai_subject" in compiled:
                select_subject_call_count += 1
                if select_subject_call_count == 1:
                    return FakeSubjectSelectResult(None)  # Race window
                else:
                    return FakeSubjectSelectResult(winner_id)  # Re-lookup finds winner
            else:
                # exists() checks for Google connection / priorities
                return FakeExistsResult()
        raise AssertionError(
            f"Unexpected statement type in test: {type(stmt).__name__}"
        )

    fake_session.execute = fake_execute
    fake_session.commit = AsyncMock()

    user_id, case = await _reconcile_user_by_subject(
        db=fake_session,
        jwt_user_id=jwt_user_id,
        openai_subject=subject,
        correlation_id="test-corr-id",
    )

    assert user_id == winner_id
    assert case == "C1"
    # Confirm the race path was actually exercised: first SELECT None, re-SELECT winner
    assert select_subject_call_count == 2


@pytest.mark.asyncio
async def test_case_a_race_lost_no_winner_anomaly(user_b_fresh):
    """
    Simulate: UPDATE returns 0 rows AND re-SELECT returns None.
    This is an anomaly — race was lost but no one owns the subject.
    Returns (jwt_user_id, "X") with error log.

    Uses a deterministic fake session that differentiates SELECT from UPDATE
    by statement class. Does not rely on MagicMock's accidental isinstance
    behavior.
    """
    subject = "v1/anomaly-subject"

    class FakeSelectResult:
        def scalar_one_or_none(self):
            return None  # No owner found on initial lookup and re-lookup

    class FakeUpdateResult:
        rowcount = 0  # Race lost: UPDATE matched zero rows

    fake_session = AsyncMock()

    async def fake_execute(stmt):
        if isinstance(stmt, Update):
            return FakeUpdateResult()
        elif isinstance(stmt, Select):
            return FakeSelectResult()
        raise AssertionError(
            f"Unexpected statement type in test: {type(stmt).__name__}"
        )

    fake_session.execute = fake_execute
    fake_session.commit = AsyncMock()

    user_id, case = await _reconcile_user_by_subject(
        db=fake_session,
        jwt_user_id=user_b_fresh.id,
        openai_subject=subject,
        correlation_id="test-corr-id",
    )

    assert user_id == user_b_fresh.id
    assert case == "X"


# =============================================================================
# Case B Tests
# =============================================================================

@pytest.mark.asyncio
async def test_case_b_match_same_user(async_session, user_a):
    """CoreUser(X, openai_subject=S) exists. Call with jwt_user_id=X, subject=S. Returns (X, "B")."""
    user_id, case = await _reconcile_user_by_subject(
        db=async_session,
        jwt_user_id=user_a.id,
        openai_subject=user_a.openai_subject,
        correlation_id="test-corr-id",
    )

    assert user_id == user_a.id
    assert case == "B"


# =============================================================================
# Case C1 Tests
# =============================================================================

@pytest.mark.asyncio
async def test_case_c1_fresh_shell_returns_canonical(async_session, user_a, user_b_fresh):
    """
    CoreUser(A, openai_subject=S) with subject.
    CoreUser(B, openai_subject=NULL) fresh shell.
    Returns (A, "C1").
    """
    user_id, case = await _reconcile_user_by_subject(
        db=async_session,
        jwt_user_id=user_b_fresh.id,
        openai_subject=user_a.openai_subject,
        correlation_id="test-corr-id",
    )

    assert user_id == user_a.id
    assert case == "C1"


@pytest.mark.asyncio
async def test_case_c1_revoked_google_connection_treated_as_fresh_when_no_priorities(
    async_session, user_a, user_with_revoked_google
):
    """
    CoreUser(B) has Google connection row but revoked_at IS NOT NULL, NO priorities.
    Returns (A, "C1").
    """
    user_id, case = await _reconcile_user_by_subject(
        db=async_session,
        jwt_user_id=user_with_revoked_google.id,
        openai_subject=user_a.openai_subject,
        correlation_id="test-corr-id",
    )

    assert user_id == user_a.id
    assert case == "C1"


# =============================================================================
# Case C2 Tests
# =============================================================================

@pytest.mark.asyncio
async def test_case_c2_refuses_swap_when_google_connection_active(async_session, user_a, user_with_google):
    """
    CoreUser(B) WITH active Google connection, NO priorities.
    Returns (B, "C2").
    """
    user_id, case = await _reconcile_user_by_subject(
        db=async_session,
        jwt_user_id=user_with_google.id,
        openai_subject=user_a.openai_subject,
        correlation_id="test-corr-id",
    )

    assert user_id == user_with_google.id
    assert case == "C2"


@pytest.mark.asyncio
async def test_case_c2_refuses_swap_when_priorities_exist(async_session, user_a, user_with_priority):
    """
    CoreUser(B) with NO active Google connection BUT one active PgPriority.
    Returns (B, "C2").
    """
    user_id, case = await _reconcile_user_by_subject(
        db=async_session,
        jwt_user_id=user_with_priority.id,
        openai_subject=user_a.openai_subject,
        correlation_id="test-corr-id",
    )

    assert user_id == user_with_priority.id
    assert case == "C2"


@pytest.mark.asyncio
async def test_case_c2_refuses_swap_with_retired_priorities_only(async_session, user_a, user_with_retired_priority):
    """
    CoreUser(B) has NO active Google connection but has a PgPriority with status='retired'.
    Returns (B, "C2"). Confirms retired priorities count as hydrated state.
    """
    user_id, case = await _reconcile_user_by_subject(
        db=async_session,
        jwt_user_id=user_with_retired_priority.id,
        openai_subject=user_a.openai_subject,
        correlation_id="test-corr-id",
    )

    assert user_id == user_with_retired_priority.id
    assert case == "C2"


# =============================================================================
# Error Handling Tests
# =============================================================================

@pytest.mark.asyncio
async def test_db_error_propagates(async_session):
    """DB raises. Function re-raises."""
    from unittest.mock import AsyncMock, patch

    with patch.object(async_session, "execute", side_effect=Exception("DB error")):
        with pytest.raises(Exception, match="DB error"):
            await _reconcile_user_by_subject(
                db=async_session,
                jwt_user_id=uuid4(),
                openai_subject="v1/test",
                correlation_id="test-corr-id",
            )


# =============================================================================
# Observability Contract Tests
# =============================================================================
# These tests pin the ERROR-level structured logs that Better Stack alerting
# depends on. A refactor that renames or removes these log events would silently
# break ops alerting; these tests fail loudly if that happens.

@pytest.mark.asyncio
async def test_anomaly_x_logs_race_lost_no_winner_error(user_b_fresh, capsys):
    """
    Case X (race lost + no winner on re-SELECT) must emit ERROR-level
    'reconcile.race_lost_no_winner' — Better Stack alert key.
    """
    subject = "v1/anomaly-subject-logtest"

    class FakeSelectResult:
        def scalar_one_or_none(self):
            return None

    class FakeUpdateResult:
        rowcount = 0

    fake_session = AsyncMock()

    async def fake_execute(stmt):
        if isinstance(stmt, Update):
            return FakeUpdateResult()
        elif isinstance(stmt, Select):
            return FakeSelectResult()
        raise AssertionError(f"Unexpected statement type: {type(stmt).__name__}")

    fake_session.execute = fake_execute
    fake_session.commit = AsyncMock()

    await _reconcile_user_by_subject(
        db=fake_session,
        jwt_user_id=user_b_fresh.id,
        openai_subject=subject,
        correlation_id="test-corr-id",
    )

    # structlog writes to stdout; capture and verify the event key + level
    captured = capsys.readouterr()
    assert "reconcile.race_lost_no_winner" in captured.out, (
        f"Expected 'reconcile.race_lost_no_winner' in log output, got: {captured.out[:500]}"
    )
    assert "[error" in captured.out.lower(), (
        f"Expected [error] level marker in log output, got: {captured.out[:500]}"
    )


@pytest.mark.asyncio
async def test_case_c2_logs_ambiguous_collision_error(async_session, user_a, user_with_priority, capsys):
    """
    Case C2 (hydrated user refusing swap) must emit ERROR-level
    'reconcile.ambiguous_collision' — Better Stack alert key for identity
    collisions that need human review.
    """
    await _reconcile_user_by_subject(
        db=async_session,
        jwt_user_id=user_with_priority.id,
        openai_subject=user_a.openai_subject,
        correlation_id="test-corr-id",
    )

    # structlog writes to stdout; capture and verify the event key + level
    captured = capsys.readouterr()
    assert "reconcile.ambiguous_collision" in captured.out, (
        f"Expected 'reconcile.ambiguous_collision' in log output, got: {captured.out[:500]}"
    )
    assert "[error" in captured.out.lower(), (
        f"Expected [error] level marker in log output, got: {captured.out[:500]}"
    )


# =============================================================================
# DB Integrity Test
# =============================================================================
# NOTE: test_openai_subject_partial_unique_index is in the integration tests
# because it requires the migration to be applied (the partial unique index
# is defined in the migration, not the ORM model).
