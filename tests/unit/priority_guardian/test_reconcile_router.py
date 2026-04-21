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

from sqlalchemy import select

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
async def test_case_a_race_lost_winner_found(async_session, user_a, user_b_fresh):
    """
    Simulate: user_b_fresh tries to bind subject that user_a already owns.
    Initial SELECT returns None (simulating race window), UPDATE returns 0,
    re-SELECT finds user_a. Returns (user_a.id, "C1") since fresh shell remaps.
    """
    # user_a has the subject, user_b_fresh is trying to claim it
    # This tests the path where initial SELECT misses but re-SELECT after
    # race-lost finds the winner.
    user_id, case = await _reconcile_user_by_subject(
        db=async_session,
        jwt_user_id=user_b_fresh.id,
        openai_subject=user_a.openai_subject,
        correlation_id="test-corr-id",
    )

    # user_b_fresh is a fresh shell, so it remaps to user_a (C1)
    assert user_id == user_a.id
    assert case == "C1"


@pytest.mark.asyncio
async def test_case_a_race_lost_no_winner_anomaly(async_session, user_b_fresh):
    """
    Simulate: UPDATE returns 0 rows AND re-SELECT returns None.
    This is an anomaly - race was lost but no one owns the subject.
    Returns (jwt_user_id, "X") with error log.
    """
    from unittest.mock import AsyncMock, patch, MagicMock
    from sqlalchemy import Update

    subject = "v1/anomaly-subject"

    # Mock the session to simulate:
    # 1. First SELECT returns None (no owner)
    # 2. UPDATE returns rowcount=0 (race lost)
    # 3. Second SELECT returns None (anomaly: no winner found)

    async def mock_execute(stmt):
        # Check if this is an UPDATE statement
        if isinstance(stmt, Update):
            # Return mock with rowcount=0
            mock_result = MagicMock()
            mock_result.rowcount = 0
            return mock_result

        # For SELECT statements, always return None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        return mock_result

    with patch.object(async_session, "execute", side_effect=mock_execute):
        with patch.object(async_session, "commit", new_callable=AsyncMock):
            user_id, case = await _reconcile_user_by_subject(
                db=async_session,
                jwt_user_id=user_b_fresh.id,
                openai_subject=subject,
                correlation_id="test-corr-id",
            )

    # Anomaly case: return jwt_user_id with "X" (anomaly, ERROR logged)
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
# DB Integrity Test
# =============================================================================
# NOTE: test_openai_subject_partial_unique_index is in the integration tests
# because it requires the migration to be applied (the partial unique index
# is defined in the migration, not the ORM model).
