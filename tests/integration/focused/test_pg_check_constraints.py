"""
Database check constraint tests for Priority Guardian tables.

Tests all 5 check constraints added in migration 64d82150e4c7:
- ck_pg_priorities_type_field_consistency
- ck_pg_priorities_weekly_target_positive
- ck_pg_priorities_retirement_consistency
- ck_pg_weekly_snapshots_week_consistency
- ck_pg_weekly_snapshots_target_hours_non_negative

All tests use raw SQL to bypass ORM validation and test DB-level enforcement.
"""

from uuid import uuid4
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_test_user(async_session: AsyncSession) -> str:
    """Insert a core_users row and return its UUID as string."""
    user_id = str(uuid4())
    await async_session.execute(
        text("INSERT INTO core_users (id) VALUES (:id)"),
        {"id": user_id},
    )
    await async_session.commit()
    return user_id


async def _insert_priority(
    async_session: AsyncSession,
    user_id: str,
    *,
    priority_type: str = "deadline",
    calendar_keyword: str = "P1",
    status: str = "active",
    deadline: date | None = None,
    weekly_hour_target: float | None = None,
    checkpoint_date: date | None = None,
    retired_at: datetime | None = None,
) -> str:
    """Insert a pg_priorities row with specified fields."""
    priority_id = str(uuid4())

    # Build column/value lists dynamically
    columns = ["id", "user_id", "name", "type", "calendar_keyword", "status"]
    values = [":id", ":user_id", "'Test Priority'", ":type", ":keyword", ":status"]
    params: dict = {
        "id": priority_id,
        "user_id": user_id,
        "type": priority_type,
        "keyword": calendar_keyword,
        "status": status,
    }

    if deadline is not None:
        columns.append("deadline")
        values.append(":deadline")
        params["deadline"] = deadline

    if weekly_hour_target is not None:
        columns.append("weekly_hour_target")
        values.append(":weekly_hour_target")
        params["weekly_hour_target"] = weekly_hour_target

    if checkpoint_date is not None:
        columns.append("checkpoint_date")
        values.append(":checkpoint_date")
        params["checkpoint_date"] = checkpoint_date

    if retired_at is not None:
        columns.append("retired_at")
        values.append(":retired_at")
        params["retired_at"] = retired_at

    sql = f"INSERT INTO pg_priorities ({', '.join(columns)}) VALUES ({', '.join(values)})"
    await async_session.execute(text(sql), params)
    await async_session.commit()
    return priority_id


# ---------------------------------------------------------------------------
# 1. Type-field consistency constraint (ck_pg_priorities_type_field_consistency)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_type_field_consistency_valid_deadline(async_session: AsyncSession):
    """
    type='deadline' with deadline set, weekly_hour_target=NULL, checkpoint_date=NULL → succeeds.
    """
    user_id = await _create_test_user(async_session)

    # Should succeed
    priority_id = await _insert_priority(
        async_session,
        user_id,
        priority_type="deadline",
        deadline=date(2026, 3, 15),
        weekly_hour_target=None,
        checkpoint_date=None,
    )

    # Verify it was inserted
    result = await async_session.execute(
        text("SELECT id FROM pg_priorities WHERE id = :id"),
        {"id": priority_id},
    )
    assert str(result.scalar_one()) == priority_id


@pytest.mark.asyncio
async def test_type_field_consistency_invalid_deadline_no_date(async_session: AsyncSession):
    """
    type='deadline' with deadline=NULL → fails.
    """
    user_id = await _create_test_user(async_session)

    with pytest.raises(IntegrityError) as exc_info:
        await _insert_priority(
            async_session,
            user_id,
            priority_type="deadline",
            deadline=None,
            weekly_hour_target=None,
            checkpoint_date=None,
        )

    assert "ck_pg_priorities_type_field_consistency" in str(exc_info.value)
    await async_session.rollback()


@pytest.mark.asyncio
async def test_type_field_consistency_invalid_deadline_has_weekly_target(async_session: AsyncSession):
    """
    type='deadline' with deadline set AND weekly_hour_target set → fails.
    """
    user_id = await _create_test_user(async_session)

    with pytest.raises(IntegrityError) as exc_info:
        await _insert_priority(
            async_session,
            user_id,
            priority_type="deadline",
            deadline=date(2026, 3, 15),
            weekly_hour_target=10.0,
            checkpoint_date=None,
        )

    assert "ck_pg_priorities_type_field_consistency" in str(exc_info.value)
    await async_session.rollback()


@pytest.mark.asyncio
async def test_type_field_consistency_valid_flexible(async_session: AsyncSession):
    """
    type='flexible' with weekly_hour_target set, checkpoint_date set, deadline=NULL → succeeds.
    """
    user_id = await _create_test_user(async_session)

    priority_id = await _insert_priority(
        async_session,
        user_id,
        priority_type="flexible",
        deadline=None,
        weekly_hour_target=10.0,
        checkpoint_date=date(2026, 3, 15),
    )

    result = await async_session.execute(
        text("SELECT id FROM pg_priorities WHERE id = :id"),
        {"id": priority_id},
    )
    assert str(result.scalar_one()) == priority_id


@pytest.mark.asyncio
async def test_type_field_consistency_invalid_flexible_no_target(async_session: AsyncSession):
    """
    type='flexible' with weekly_hour_target=NULL → fails.
    """
    user_id = await _create_test_user(async_session)

    with pytest.raises(IntegrityError) as exc_info:
        await _insert_priority(
            async_session,
            user_id,
            priority_type="flexible",
            deadline=None,
            weekly_hour_target=None,
            checkpoint_date=date(2026, 3, 15),
        )

    assert "ck_pg_priorities_type_field_consistency" in str(exc_info.value)
    await async_session.rollback()


@pytest.mark.asyncio
async def test_type_field_consistency_invalid_flexible_has_deadline(async_session: AsyncSession):
    """
    type='flexible' with all flexible fields set AND deadline also set → fails.
    """
    user_id = await _create_test_user(async_session)

    with pytest.raises(IntegrityError) as exc_info:
        await _insert_priority(
            async_session,
            user_id,
            priority_type="flexible",
            deadline=date(2026, 3, 15),
            weekly_hour_target=10.0,
            checkpoint_date=date(2026, 3, 15),
        )

    assert "ck_pg_priorities_type_field_consistency" in str(exc_info.value)
    await async_session.rollback()


# ---------------------------------------------------------------------------
# 2. Weekly target positive constraint (ck_pg_priorities_weekly_target_positive)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_weekly_target_positive_valid(async_session: AsyncSession):
    """
    weekly_hour_target=0.5 → succeeds.
    """
    user_id = await _create_test_user(async_session)

    priority_id = await _insert_priority(
        async_session,
        user_id,
        priority_type="flexible",
        weekly_hour_target=0.5,
        checkpoint_date=date(2026, 3, 15),
    )

    result = await async_session.execute(
        text("SELECT weekly_hour_target FROM pg_priorities WHERE id = :id"),
        {"id": priority_id},
    )
    assert float(result.scalar_one()) == 0.5


@pytest.mark.asyncio
async def test_weekly_target_positive_zero_fails(async_session: AsyncSession):
    """
    weekly_hour_target=0 → fails.
    """
    user_id = await _create_test_user(async_session)

    with pytest.raises(IntegrityError) as exc_info:
        await _insert_priority(
            async_session,
            user_id,
            priority_type="flexible",
            weekly_hour_target=0,
            checkpoint_date=date(2026, 3, 15),
        )

    assert "ck_pg_priorities_weekly_target_positive" in str(exc_info.value)
    await async_session.rollback()


@pytest.mark.asyncio
async def test_weekly_target_positive_negative_fails(async_session: AsyncSession):
    """
    weekly_hour_target=-1 → fails.
    """
    user_id = await _create_test_user(async_session)

    with pytest.raises(IntegrityError) as exc_info:
        await _insert_priority(
            async_session,
            user_id,
            priority_type="flexible",
            weekly_hour_target=-1,
            checkpoint_date=date(2026, 3, 15),
        )

    assert "ck_pg_priorities_weekly_target_positive" in str(exc_info.value)
    await async_session.rollback()


@pytest.mark.asyncio
async def test_weekly_target_positive_null_allowed(async_session: AsyncSession):
    """
    weekly_hour_target=NULL (deadline type) → succeeds.
    """
    user_id = await _create_test_user(async_session)

    priority_id = await _insert_priority(
        async_session,
        user_id,
        priority_type="deadline",
        deadline=date(2026, 3, 15),
        weekly_hour_target=None,
    )

    result = await async_session.execute(
        text("SELECT weekly_hour_target FROM pg_priorities WHERE id = :id"),
        {"id": priority_id},
    )
    assert result.scalar_one() is None


# ---------------------------------------------------------------------------
# 3. Retirement consistency constraint (ck_pg_priorities_retirement_consistency)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_retirement_consistency_active_no_retired_at(async_session: AsyncSession):
    """
    status='active' with retired_at=NULL → succeeds.
    """
    user_id = await _create_test_user(async_session)

    priority_id = await _insert_priority(
        async_session,
        user_id,
        priority_type="deadline",
        deadline=date(2026, 3, 15),
        status="active",
        retired_at=None,
    )

    result = await async_session.execute(
        text("SELECT status, retired_at FROM pg_priorities WHERE id = :id"),
        {"id": priority_id},
    )
    row = result.first()
    assert row.status == "active"
    assert row.retired_at is None


@pytest.mark.asyncio
async def test_retirement_consistency_retired_with_retired_at(async_session: AsyncSession):
    """
    status='retired' with retired_at set → succeeds.
    """
    user_id = await _create_test_user(async_session)

    priority_id = await _insert_priority(
        async_session,
        user_id,
        priority_type="deadline",
        deadline=date(2026, 3, 15),
        status="retired",
        retired_at=datetime(2026, 2, 15, 12, 0, 0, tzinfo=timezone.utc),
    )

    result = await async_session.execute(
        text("SELECT status, retired_at FROM pg_priorities WHERE id = :id"),
        {"id": priority_id},
    )
    row = result.first()
    assert row.status == "retired"
    assert row.retired_at is not None


@pytest.mark.asyncio
async def test_retirement_consistency_retired_without_retired_at_fails(async_session: AsyncSession):
    """
    status='retired' with retired_at=NULL → fails.
    """
    user_id = await _create_test_user(async_session)

    with pytest.raises(IntegrityError) as exc_info:
        await _insert_priority(
            async_session,
            user_id,
            priority_type="deadline",
            deadline=date(2026, 3, 15),
            status="retired",
            retired_at=None,
        )

    assert "ck_pg_priorities_retirement_consistency" in str(exc_info.value)
    await async_session.rollback()


@pytest.mark.asyncio
async def test_retirement_consistency_active_with_retired_at_fails(async_session: AsyncSession):
    """
    status='active' with retired_at set → fails.
    """
    user_id = await _create_test_user(async_session)

    with pytest.raises(IntegrityError) as exc_info:
        await _insert_priority(
            async_session,
            user_id,
            priority_type="deadline",
            deadline=date(2026, 3, 15),
            status="active",
            retired_at=datetime(2026, 2, 15, 12, 0, 0, tzinfo=timezone.utc),
        )

    assert "ck_pg_priorities_retirement_consistency" in str(exc_info.value)
    await async_session.rollback()


# ---------------------------------------------------------------------------
# 4. Week consistency constraint (ck_pg_weekly_snapshots_week_consistency)
# ---------------------------------------------------------------------------

async def _insert_snapshot(
    async_session: AsyncSession,
    priority_id: str,
    user_id: str,
    *,
    week_start: date,
    week_end: date,
    actual_hours: float = 5.0,
    target_hours: float | None = None,
) -> str:
    """Insert a pg_weekly_snapshots row."""
    snapshot_id = str(uuid4())

    columns = ["id", "priority_id", "user_id", "week_start", "week_end", "actual_hours"]
    values = [":id", ":priority_id", ":user_id", ":week_start", ":week_end", ":actual_hours"]
    params: dict = {
        "id": snapshot_id,
        "priority_id": priority_id,
        "user_id": user_id,
        "week_start": week_start,
        "week_end": week_end,
        "actual_hours": actual_hours,
    }

    if target_hours is not None:
        columns.append("target_hours")
        values.append(":target_hours")
        params["target_hours"] = target_hours

    sql = f"INSERT INTO pg_weekly_snapshots ({', '.join(columns)}) VALUES ({', '.join(values)})"
    await async_session.execute(text(sql), params)
    await async_session.commit()
    return snapshot_id


@pytest.mark.asyncio
async def test_week_consistency_valid(async_session: AsyncSession):
    """
    week_end = week_start + 6 days → succeeds.
    """
    user_id = await _create_test_user(async_session)
    priority_id = await _insert_priority(
        async_session,
        user_id,
        priority_type="deadline",
        deadline=date(2026, 3, 15),
    )

    # 2026-02-09 is a Monday, 2026-02-15 is Sunday
    snapshot_id = await _insert_snapshot(
        async_session,
        priority_id,
        user_id,
        week_start=date(2026, 2, 9),   # Monday
        week_end=date(2026, 2, 15),    # Sunday (Monday + 6)
    )

    result = await async_session.execute(
        text("SELECT week_start, week_end FROM pg_weekly_snapshots WHERE id = :id"),
        {"id": snapshot_id},
    )
    row = result.first()
    assert row.week_start == date(2026, 2, 9)
    assert row.week_end == date(2026, 2, 15)


@pytest.mark.asyncio
async def test_week_consistency_invalid(async_session: AsyncSession):
    """
    week_end = week_start + 5 days → fails.
    """
    user_id = await _create_test_user(async_session)
    priority_id = await _insert_priority(
        async_session,
        user_id,
        priority_type="deadline",
        deadline=date(2026, 3, 15),
    )

    # 2026-02-09 is a Monday
    with pytest.raises(IntegrityError) as exc_info:
        await _insert_snapshot(
            async_session,
            priority_id,
            user_id,
            week_start=date(2026, 2, 9),   # Monday
            week_end=date(2026, 2, 14),    # +5 days, not +6
        )

    assert "ck_pg_weekly_snapshots_week_consistency" in str(exc_info.value)
    await async_session.rollback()


# ---------------------------------------------------------------------------
# 5. Target hours non-negative constraint (ck_pg_weekly_snapshots_target_hours_non_negative)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_target_hours_nonnegative_valid_zero(async_session: AsyncSession):
    """
    target_hours=0 → succeeds.
    """
    user_id = await _create_test_user(async_session)
    priority_id = await _insert_priority(
        async_session,
        user_id,
        priority_type="deadline",
        deadline=date(2026, 3, 15),
    )

    # 2026-02-16 is a Monday
    snapshot_id = await _insert_snapshot(
        async_session,
        priority_id,
        user_id,
        week_start=date(2026, 2, 16),  # Monday
        week_end=date(2026, 2, 22),    # Sunday
        target_hours=0,
    )

    result = await async_session.execute(
        text("SELECT target_hours FROM pg_weekly_snapshots WHERE id = :id"),
        {"id": snapshot_id},
    )
    assert float(result.scalar_one()) == 0


@pytest.mark.asyncio
async def test_target_hours_nonnegative_valid_null(async_session: AsyncSession):
    """
    target_hours=NULL → succeeds.
    """
    user_id = await _create_test_user(async_session)
    priority_id = await _insert_priority(
        async_session,
        user_id,
        priority_type="deadline",
        deadline=date(2026, 3, 15),
    )

    # 2026-02-23 is a Monday
    snapshot_id = await _insert_snapshot(
        async_session,
        priority_id,
        user_id,
        week_start=date(2026, 2, 23),  # Monday
        week_end=date(2026, 3, 1),     # Sunday
        target_hours=None,
    )

    result = await async_session.execute(
        text("SELECT target_hours FROM pg_weekly_snapshots WHERE id = :id"),
        {"id": snapshot_id},
    )
    assert result.scalar_one() is None


@pytest.mark.asyncio
async def test_target_hours_nonnegative_negative_fails(async_session: AsyncSession):
    """
    target_hours=-1 → fails.
    """
    user_id = await _create_test_user(async_session)
    priority_id = await _insert_priority(
        async_session,
        user_id,
        priority_type="deadline",
        deadline=date(2026, 3, 15),
    )

    # 2026-02-16 is a Monday
    with pytest.raises(IntegrityError) as exc_info:
        await _insert_snapshot(
            async_session,
            priority_id,
            user_id,
            week_start=date(2026, 2, 16),  # Monday
            week_end=date(2026, 2, 22),    # Sunday
            target_hours=-1,
        )

    assert "ck_pg_weekly_snapshots_target_hours_non_negative" in str(exc_info.value)
    await async_session.rollback()


# ---------------------------------------------------------------------------
# 6. Week start Monday constraint (ck_pg_weekly_snapshots_week_start_monday)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_week_start_monday_valid(async_session: AsyncSession):
    """
    week_start=Monday → succeeds.
    """
    user_id = await _create_test_user(async_session)
    priority_id = await _insert_priority(
        async_session,
        user_id,
        priority_type="deadline",
        deadline=date(2026, 3, 15),
    )

    # 2026-02-09 is a Monday
    snapshot_id = await _insert_snapshot(
        async_session,
        priority_id,
        user_id,
        week_start=date(2026, 2, 9),   # Monday
        week_end=date(2026, 2, 15),    # Sunday
    )

    result = await async_session.execute(
        text("SELECT week_start FROM pg_weekly_snapshots WHERE id = :id"),
        {"id": snapshot_id},
    )
    assert result.scalar_one() == date(2026, 2, 9)


@pytest.mark.asyncio
async def test_week_start_monday_invalid(async_session: AsyncSession):
    """
    week_start=Wednesday → fails.
    """
    user_id = await _create_test_user(async_session)
    priority_id = await _insert_priority(
        async_session,
        user_id,
        priority_type="deadline",
        deadline=date(2026, 3, 15),
    )

    # 2026-02-11 is a Wednesday
    with pytest.raises(IntegrityError) as exc_info:
        await _insert_snapshot(
            async_session,
            priority_id,
            user_id,
            week_start=date(2026, 2, 11),  # Wednesday
            week_end=date(2026, 2, 17),    # Tuesday (+6)
        )

    assert "ck_pg_weekly_snapshots_week_start_monday" in str(exc_info.value)
    await async_session.rollback()
