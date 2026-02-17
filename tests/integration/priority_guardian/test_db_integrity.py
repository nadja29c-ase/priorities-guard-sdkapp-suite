"""
DB-level integration tests for Priority Guardian.

These tests verify actual PostgreSQL behavior:
- CASCADE DELETE removes child rows
- Partial unique index rejects duplicate active keywords
- CHECK constraints reject invalid data
- FK constraints reject orphaned children
- Transaction rollback preserves existing data

All tests use real test PostgreSQL - no DB mocking.
"""

import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from backend.apps.priority_guardian.db_models import (
    PgPriority,
    PgDeliverable,
    PgGoal,
    PgWeeklySnapshot,
)
from backend.core.models import CoreUser


# =============================================================================
# Section 1: CASCADE DELETE Verification
# =============================================================================


class TestCascadeDelete:
    """Verify CASCADE DELETE actually removes child rows from the database."""

    @pytest.mark.asyncio
    async def test_delete_priority_cascades_deliverables_in_db(
        self, client, async_session: AsyncSession
    ):
        """1a. DELETE priority removes deliverables from DB, not just API response."""
        # Create user and priority
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        priority = PgPriority(
            user_id=user.id,
            name="Test Priority",
            type="deadline",
            calendar_keyword="P1",
            status="active",
            deadline=date.today() + timedelta(days=30),
        )
        async_session.add(priority)
        await async_session.flush()

        # Add 2 deliverables directly via ORM
        for i in range(2):
            deliverable = PgDeliverable(
                priority_id=priority.id,
                name=f"Deliverable {i+1}",
                done=False,
            )
            async_session.add(deliverable)
        await async_session.commit()

        priority_id = priority.id

        # Verify deliverables exist
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_deliverables WHERE priority_id = :pid"),
            {"pid": priority_id},
        )
        assert result.scalar() == 2

        # DELETE via API
        response = await client.delete(
            f"/api/priority-guardian/priorities/{priority_id}",
            headers={"X-User-ID": str(user.id)},
        )
        assert response.status_code == 200

        # Verify deliverables are gone from DB
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_deliverables WHERE priority_id = :pid"),
            {"pid": priority_id},
        )
        assert result.scalar() == 0, "Deliverables should be CASCADE deleted"

    @pytest.mark.asyncio
    async def test_delete_priority_cascades_goals_in_db(
        self, client, async_session: AsyncSession
    ):
        """1b. DELETE priority removes goals from DB."""
        user_id = uuid4()
        user = CoreUser(id=user_id)
        async_session.add(user)
        await async_session.flush()

        priority = PgPriority(
            user_id=user_id,
            name="Flexible Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date.today() + timedelta(days=30),
        )
        async_session.add(priority)
        await async_session.flush()

        priority_id = priority.id

        # Add 2 goals directly via ORM
        for i in range(2):
            goal = PgGoal(
                priority_id=priority_id,
                goal_text=f"Goal {i+1}",
                achieved=False,
            )
            async_session.add(goal)
        await async_session.commit()

        # Verify goals exist
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_goals WHERE priority_id = :pid"),
            {"pid": priority_id},
        )
        assert result.scalar() == 2

        # DELETE via API
        response = await client.delete(
            f"/api/priority-guardian/priorities/{priority_id}",
            headers={"X-User-ID": str(user_id)},
        )
        assert response.status_code == 200

        # Verify goals are gone from DB
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_goals WHERE priority_id = :pid"),
            {"pid": priority_id},
        )
        assert result.scalar() == 0, "Goals should be CASCADE deleted"

    @pytest.mark.asyncio
    async def test_delete_priority_cascades_snapshots_in_db(
        self, client, async_session: AsyncSession
    ):
        """1c. DELETE priority removes snapshots from DB."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        priority = PgPriority(
            user_id=user.id,
            name="Flexible Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date.today() + timedelta(days=30),
            created_at=datetime(2026, 1, 1),  # Predate test weeks
        )
        async_session.add(priority)
        await async_session.flush()

        priority_id = priority.id

        # Insert 2 snapshots directly via SQL (valid Monday start dates)
        await async_session.execute(
            text("""
                INSERT INTO pg_weekly_snapshots
                (id, priority_id, user_id, week_start, week_end, actual_hours, target_hours, streak_at_snapshot)
                VALUES
                (gen_random_uuid(), :pid, :uid, '2026-01-19', '2026-01-25', 5.0, 10.0, 1),
                (gen_random_uuid(), :pid, :uid, '2026-01-26', '2026-02-01', 6.0, 10.0, 2)
            """),
            {"pid": priority_id, "uid": user.id},
        )
        await async_session.commit()

        # Verify snapshots exist
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_weekly_snapshots WHERE priority_id = :pid"),
            {"pid": priority_id},
        )
        assert result.scalar() == 2

        # DELETE via API
        response = await client.delete(
            f"/api/priority-guardian/priorities/{priority_id}",
            headers={"X-User-ID": str(user.id)},
        )
        assert response.status_code == 200

        # Verify snapshots are gone from DB
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_weekly_snapshots WHERE priority_id = :pid"),
            {"pid": priority_id},
        )
        assert result.scalar() == 0, "Snapshots should be CASCADE deleted"

    @pytest.mark.asyncio
    async def test_delete_priority_does_not_cascade_other_users_data(
        self, client, async_session: AsyncSession
    ):
        """1d. DELETE user A's priority does NOT affect user B's data."""
        # Create two users
        user_a = CoreUser(id=uuid4())
        user_b = CoreUser(id=uuid4())
        async_session.add_all([user_a, user_b])
        await async_session.flush()

        # Create priority + deliverable for user A
        priority_a = PgPriority(
            user_id=user_a.id,
            name="User A Priority",
            type="deadline",
            calendar_keyword="P1",
            status="active",
            deadline=date.today() + timedelta(days=30),
        )
        async_session.add(priority_a)
        await async_session.flush()

        deliverable_a = PgDeliverable(
            priority_id=priority_a.id,
            name="User A Deliverable",
            done=False,
        )
        async_session.add(deliverable_a)

        # Create priority + deliverable for user B
        priority_b = PgPriority(
            user_id=user_b.id,
            name="User B Priority",
            type="deadline",
            calendar_keyword="P1",  # Same keyword is fine - different user
            status="active",
            deadline=date.today() + timedelta(days=30),
        )
        async_session.add(priority_b)
        await async_session.flush()

        deliverable_b = PgDeliverable(
            priority_id=priority_b.id,
            name="User B Deliverable",
            done=False,
        )
        async_session.add(deliverable_b)
        await async_session.commit()

        deliverable_b_id = deliverable_b.id

        # DELETE user A's priority
        response = await client.delete(
            f"/api/priority-guardian/priorities/{priority_a.id}",
            headers={"X-User-ID": str(user_a.id)},
        )
        assert response.status_code == 200

        # Verify user B's deliverable still exists
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_deliverables WHERE id = :did"),
            {"did": deliverable_b_id},
        )
        assert result.scalar() == 1, "User B's deliverable should be unaffected"

    @pytest.mark.asyncio
    async def test_delete_retired_priority_cascades_children_in_db(
        self, client, async_session: AsyncSession
    ):
        """DELETE retired priority still cascades children (FK not status-dependent)."""
        user_id = uuid4()
        user = CoreUser(id=user_id)
        async_session.add(user)
        await async_session.flush()

        priority = PgPriority(
            user_id=user_id,
            name="Retired Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",  # Start active
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date.today() + timedelta(days=30),
            created_at=datetime(2026, 1, 1),
        )
        async_session.add(priority)
        await async_session.flush()

        priority_id = priority.id

        # Add goal and snapshot
        goal = PgGoal(priority_id=priority_id, goal_text="Test goal", achieved=False)
        async_session.add(goal)

        await async_session.execute(
            text("""
                INSERT INTO pg_weekly_snapshots
                (id, priority_id, user_id, week_start, week_end, actual_hours, target_hours, streak_at_snapshot)
                VALUES (gen_random_uuid(), :pid, :uid, '2026-01-19', '2026-01-25', 5.0, 10.0, 1)
            """),
            {"pid": priority_id, "uid": user_id},
        )
        await async_session.commit()

        # Retire the priority via direct SQL (no retire endpoint)
        # Retired priorities keep their keyword - partial unique index excludes them
        await async_session.execute(
            text("""
                UPDATE pg_priorities
                SET status = 'retired', retired_at = NOW()
                WHERE id = :pid
            """),
            {"pid": priority_id},
        )
        await async_session.commit()

        # Verify children exist before delete
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_goals WHERE priority_id = :pid"),
            {"pid": priority_id},
        )
        assert result.scalar() == 1

        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_weekly_snapshots WHERE priority_id = :pid"),
            {"pid": priority_id},
        )
        assert result.scalar() == 1

        # DELETE retired priority via direct SQL (API may not find retired priorities)
        await async_session.execute(
            text("DELETE FROM pg_priorities WHERE id = :pid"),
            {"pid": priority_id},
        )
        await async_session.commit()

        # Verify CASCADE worked
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_goals WHERE priority_id = :pid"),
            {"pid": priority_id},
        )
        assert result.scalar() == 0, "Goals should be CASCADE deleted for retired priority"

        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_weekly_snapshots WHERE priority_id = :pid"),
            {"pid": priority_id},
        )
        assert result.scalar() == 0, "Snapshots should be CASCADE deleted for retired priority"


# =============================================================================
# Section 2: Partial Unique Index Enforcement
# =============================================================================


class TestPartialUniqueIndex:
    """Verify idx_pg_priorities_user_keyword_active rejects duplicates at PostgreSQL level."""

    @pytest.mark.asyncio
    async def test_duplicate_active_keyword_rejected_by_real_index(
        self, async_session: AsyncSession
    ):
        """2a. Raw INSERT of duplicate active keyword raises IntegrityError."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Insert first priority with P1 active
        priority1 = PgPriority(
            user_id=user.id,
            name="First",
            type="deadline",
            calendar_keyword="P1",
            status="active",
            deadline=date.today() + timedelta(days=30),
        )
        async_session.add(priority1)
        await async_session.commit()

        # Attempt raw INSERT of duplicate P1 active
        with pytest.raises(IntegrityError) as exc_info:
            await async_session.execute(
                text("""
                    INSERT INTO pg_priorities
                    (id, user_id, name, type, calendar_keyword, status, deadline)
                    VALUES (gen_random_uuid(), :uid, 'Second', 'deadline', 'P1', 'active', :deadline)
                """),
                {"uid": user.id, "deadline": date.today() + timedelta(days=30)},
            )
            await async_session.flush()

        assert "idx_pg_priorities_user_keyword_active" in str(exc_info.value).lower() or \
               "unique" in str(exc_info.value).lower()

        await async_session.rollback()

    @pytest.mark.asyncio
    async def test_same_keyword_allowed_when_one_is_retired(
        self, async_session: AsyncSession
    ):
        """2b. Same keyword allowed: one retired, one active (partial index only covers active)."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Insert retired priority with P1
        await async_session.execute(
            text("""
                INSERT INTO pg_priorities
                (id, user_id, name, type, calendar_keyword, status, retired_at, deadline)
                VALUES (gen_random_uuid(), :uid, 'Retired', 'deadline', 'P1', 'retired', NOW(), :deadline)
            """),
            {"uid": user.id, "deadline": date.today() + timedelta(days=30)},
        )
        await async_session.flush()

        # Insert active priority with same P1 - should succeed
        await async_session.execute(
            text("""
                INSERT INTO pg_priorities
                (id, user_id, name, type, calendar_keyword, status, deadline)
                VALUES (gen_random_uuid(), :uid, 'Active', 'deadline', 'P1', 'active', :deadline)
            """),
            {"uid": user.id, "deadline": date.today() + timedelta(days=30)},
        )
        await async_session.commit()

        # Verify both exist
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_priorities WHERE user_id = :uid AND calendar_keyword = 'P1'"),
            {"uid": user.id},
        )
        assert result.scalar() == 2

    @pytest.mark.asyncio
    async def test_different_users_can_have_same_active_keyword(
        self, async_session: AsyncSession
    ):
        """2c. Different users can have same active keyword (index is per-user)."""
        user_a = CoreUser(id=uuid4())
        user_b = CoreUser(id=uuid4())
        async_session.add_all([user_a, user_b])
        await async_session.flush()

        # Insert P1 active for user A
        await async_session.execute(
            text("""
                INSERT INTO pg_priorities
                (id, user_id, name, type, calendar_keyword, status, deadline)
                VALUES (gen_random_uuid(), :uid, 'User A', 'deadline', 'P1', 'active', :deadline)
            """),
            {"uid": user_a.id, "deadline": date.today() + timedelta(days=30)},
        )

        # Insert P1 active for user B - should succeed
        await async_session.execute(
            text("""
                INSERT INTO pg_priorities
                (id, user_id, name, type, calendar_keyword, status, deadline)
                VALUES (gen_random_uuid(), :uid, 'User B', 'deadline', 'P1', 'active', :deadline)
            """),
            {"uid": user_b.id, "deadline": date.today() + timedelta(days=30)},
        )
        await async_session.commit()

        # Verify both exist with P1
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_priorities WHERE calendar_keyword = 'P1' AND status = 'active'"),
        )
        assert result.scalar() == 2

    @pytest.mark.asyncio
    async def test_reactivating_retired_priority_with_duplicate_keyword_rejected(
        self, async_session: AsyncSession
    ):
        """2d. UPDATE to reactivate retired priority rejected if keyword conflicts."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Insert active priority A with P1
        await async_session.execute(
            text("""
                INSERT INTO pg_priorities
                (id, user_id, name, type, calendar_keyword, status, deadline)
                VALUES (gen_random_uuid(), :uid, 'Active A', 'deadline', 'P1', 'active', :deadline)
            """),
            {"uid": user.id, "deadline": date.today() + timedelta(days=30)},
        )

        # Insert retired priority B with P1 (allowed by partial index)
        retired_id = uuid4()
        await async_session.execute(
            text("""
                INSERT INTO pg_priorities
                (id, user_id, name, type, calendar_keyword, status, retired_at, deadline)
                VALUES (:rid, :uid, 'Retired B', 'deadline', 'P1', 'retired', NOW(), :deadline)
            """),
            {"rid": retired_id, "uid": user.id, "deadline": date.today() + timedelta(days=30)},
        )
        await async_session.commit()

        # Attempt to reactivate B - should fail (would create duplicate active P1)
        with pytest.raises(IntegrityError) as exc_info:
            await async_session.execute(
                text("""
                    UPDATE pg_priorities
                    SET status = 'active', retired_at = NULL
                    WHERE id = :rid
                """),
                {"rid": retired_id},
            )
            await async_session.flush()

        assert "idx_pg_priorities_user_keyword_active" in str(exc_info.value).lower() or \
               "unique" in str(exc_info.value).lower()

        await async_session.rollback()


# =============================================================================
# Section 3: CHECK Constraint Enforcement
# =============================================================================


class TestCheckConstraints:
    """Verify CHECK constraints reject invalid data at PostgreSQL level via raw SQL."""

    @pytest.mark.asyncio
    async def test_invalid_calendar_keyword_rejected(self, async_session: AsyncSession):
        """3a. calendar_keyword='P4' rejected by CHECK constraint."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        with pytest.raises(IntegrityError) as exc_info:
            await async_session.execute(
                text("""
                    INSERT INTO pg_priorities
                    (id, user_id, name, type, calendar_keyword, status, deadline)
                    VALUES (gen_random_uuid(), :uid, 'Test', 'deadline', 'P4', 'active', :deadline)
                """),
                {"uid": user.id, "deadline": date.today() + timedelta(days=30)},
            )
            await async_session.flush()

        assert "ck_pg_priorities_keyword" in str(exc_info.value).lower()

        await async_session.rollback()

    @pytest.mark.asyncio
    async def test_invalid_type_rejected(self, async_session: AsyncSession):
        """3b. type='invalid' rejected by CHECK constraint."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        with pytest.raises(IntegrityError) as exc_info:
            await async_session.execute(
                text("""
                    INSERT INTO pg_priorities
                    (id, user_id, name, type, calendar_keyword, status, deadline)
                    VALUES (gen_random_uuid(), :uid, 'Test', 'invalid', 'P1', 'active', :deadline)
                """),
                {"uid": user.id, "deadline": date.today() + timedelta(days=30)},
            )
            await async_session.flush()

        assert "ck_pg_priorities_type" in str(exc_info.value).lower()

        await async_session.rollback()

    @pytest.mark.asyncio
    async def test_invalid_status_rejected(self, async_session: AsyncSession):
        """3c. status='unknown' rejected by CHECK constraint.

        Note: Either ck_pg_priorities_status or ck_pg_priorities_retirement_consistency
        may fire first - both effectively reject invalid status values. The retirement
        consistency constraint fails because 'unknown' matches neither 'active' nor 'retired'.
        """
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        with pytest.raises(IntegrityError) as exc_info:
            await async_session.execute(
                text("""
                    INSERT INTO pg_priorities
                    (id, user_id, name, type, calendar_keyword, status, deadline)
                    VALUES (gen_random_uuid(), :uid, 'Test', 'deadline', 'P1', 'unknown', :deadline)
                """),
                {"uid": user.id, "deadline": date.today() + timedelta(days=30)},
            )
            await async_session.flush()

        error_msg = str(exc_info.value).lower()
        # Either constraint may fire first - both reject invalid status
        assert "ck_pg_priorities_status" in error_msg or \
               "ck_pg_priorities_retirement_consistency" in error_msg

        await async_session.rollback()

    @pytest.mark.asyncio
    async def test_deadline_type_with_weekly_hour_target_rejected(
        self, async_session: AsyncSession
    ):
        """3d. deadline type with weekly_hour_target rejected by type-field consistency CHECK."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        with pytest.raises(IntegrityError) as exc_info:
            await async_session.execute(
                text("""
                    INSERT INTO pg_priorities
                    (id, user_id, name, type, calendar_keyword, status, deadline, weekly_hour_target)
                    VALUES (gen_random_uuid(), :uid, 'Test', 'deadline', 'P1', 'active', :deadline, 10.0)
                """),
                {"uid": user.id, "deadline": date.today() + timedelta(days=30)},
            )
            await async_session.flush()

        assert "ck_pg_priorities_type_field_consistency" in str(exc_info.value).lower()

        await async_session.rollback()

    @pytest.mark.asyncio
    async def test_flexible_type_with_deadline_rejected(self, async_session: AsyncSession):
        """3e. flexible type with deadline rejected by type-field consistency CHECK."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        with pytest.raises(IntegrityError) as exc_info:
            await async_session.execute(
                text("""
                    INSERT INTO pg_priorities
                    (id, user_id, name, type, calendar_keyword, status, deadline, weekly_hour_target, checkpoint_date)
                    VALUES (gen_random_uuid(), :uid, 'Test', 'flexible', 'P1', 'active', :deadline, 10.0, :checkpoint)
                """),
                {"uid": user.id, "deadline": date.today() + timedelta(days=30), "checkpoint": date.today() + timedelta(days=30)},
            )
            await async_session.flush()

        assert "ck_pg_priorities_type_field_consistency" in str(exc_info.value).lower()

        await async_session.rollback()

    @pytest.mark.asyncio
    async def test_negative_weekly_hour_target_rejected(self, async_session: AsyncSession):
        """3f. Negative weekly_hour_target rejected by CHECK constraint."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        with pytest.raises(IntegrityError) as exc_info:
            await async_session.execute(
                text("""
                    INSERT INTO pg_priorities
                    (id, user_id, name, type, calendar_keyword, status, weekly_hour_target, checkpoint_date)
                    VALUES (gen_random_uuid(), :uid, 'Test', 'flexible', 'P1', 'active', -5.0, :checkpoint)
                """),
                {"uid": user.id, "checkpoint": date.today() + timedelta(days=30)},
            )
            await async_session.flush()

        assert "ck_pg_priorities_weekly_target_positive" in str(exc_info.value).lower()

        await async_session.rollback()

    @pytest.mark.asyncio
    async def test_zero_weekly_hour_target_rejected(self, async_session: AsyncSession):
        """3f2. Zero weekly_hour_target rejected by CHECK constraint (boundary test)."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        with pytest.raises(IntegrityError) as exc_info:
            await async_session.execute(
                text("""
                    INSERT INTO pg_priorities
                    (id, user_id, name, type, calendar_keyword, status, weekly_hour_target, checkpoint_date)
                    VALUES (gen_random_uuid(), :uid, 'Test', 'flexible', 'P1', 'active', 0, :checkpoint)
                """),
                {"uid": user.id, "checkpoint": date.today() + timedelta(days=30)},
            )
            await async_session.flush()

        assert "ck_pg_priorities_weekly_target_positive" in str(exc_info.value).lower()

        await async_session.rollback()

    @pytest.mark.asyncio
    async def test_active_with_retired_at_rejected(self, async_session: AsyncSession):
        """3g. status='active' with retired_at set rejected by retirement consistency CHECK."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        with pytest.raises(IntegrityError) as exc_info:
            await async_session.execute(
                text("""
                    INSERT INTO pg_priorities
                    (id, user_id, name, type, calendar_keyword, status, retired_at, deadline)
                    VALUES (gen_random_uuid(), :uid, 'Test', 'deadline', 'P1', 'active', NOW(), :deadline)
                """),
                {"uid": user.id, "deadline": date.today() + timedelta(days=30)},
            )
            await async_session.flush()

        assert "ck_pg_priorities_retirement_consistency" in str(exc_info.value).lower()

        await async_session.rollback()

    @pytest.mark.asyncio
    async def test_retired_without_retired_at_rejected(self, async_session: AsyncSession):
        """3h. status='retired' without retired_at rejected by retirement consistency CHECK."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        with pytest.raises(IntegrityError) as exc_info:
            await async_session.execute(
                text("""
                    INSERT INTO pg_priorities
                    (id, user_id, name, type, calendar_keyword, status, retired_at, deadline)
                    VALUES (gen_random_uuid(), :uid, 'Test', 'deadline', 'P1', 'retired', NULL, :deadline)
                """),
                {"uid": user.id, "deadline": date.today() + timedelta(days=30)},
            )
            await async_session.flush()

        assert "ck_pg_priorities_retirement_consistency" in str(exc_info.value).lower()

        await async_session.rollback()

    @pytest.mark.asyncio
    async def test_snapshot_negative_actual_hours_rejected(self, async_session: AsyncSession):
        """3i. Negative actual_hours on snapshot rejected by CHECK constraint."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        priority = PgPriority(
            user_id=user.id,
            name="Test",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date.today() + timedelta(days=30),
        )
        async_session.add(priority)
        await async_session.commit()

        with pytest.raises(IntegrityError) as exc_info:
            await async_session.execute(
                text("""
                    INSERT INTO pg_weekly_snapshots
                    (id, priority_id, user_id, week_start, week_end, actual_hours, target_hours, streak_at_snapshot)
                    VALUES (gen_random_uuid(), :pid, :uid, '2026-02-02', '2026-02-08', -1.0, 10.0, 0)
                """),
                {"pid": priority.id, "uid": user.id},
            )
            await async_session.flush()

        assert "ck_pg_weekly_snapshots_actual_hours_non_negative" in str(exc_info.value).lower()

        await async_session.rollback()

    @pytest.mark.asyncio
    async def test_snapshot_week_end_not_week_start_plus_6_rejected(
        self, async_session: AsyncSession
    ):
        """3j. week_end != week_start + 6 rejected by CHECK constraint."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        priority = PgPriority(
            user_id=user.id,
            name="Test",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date.today() + timedelta(days=30),
        )
        async_session.add(priority)
        await async_session.commit()

        with pytest.raises(IntegrityError) as exc_info:
            await async_session.execute(
                text("""
                    INSERT INTO pg_weekly_snapshots
                    (id, priority_id, user_id, week_start, week_end, actual_hours, target_hours, streak_at_snapshot)
                    VALUES (gen_random_uuid(), :pid, :uid, '2026-02-02', '2026-02-10', 5.0, 10.0, 0)
                """),
                {"pid": priority.id, "uid": user.id},
            )
            await async_session.flush()

        assert "ck_pg_weekly_snapshots_week_consistency" in str(exc_info.value).lower()

        await async_session.rollback()

    @pytest.mark.asyncio
    async def test_snapshot_week_start_not_monday_rejected(self, async_session: AsyncSession):
        """3k. week_start not Monday rejected by CHECK constraint."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        priority = PgPriority(
            user_id=user.id,
            name="Test",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date.today() + timedelta(days=30),
        )
        async_session.add(priority)
        await async_session.commit()

        # 2026-02-03 is a Tuesday
        with pytest.raises(IntegrityError) as exc_info:
            await async_session.execute(
                text("""
                    INSERT INTO pg_weekly_snapshots
                    (id, priority_id, user_id, week_start, week_end, actual_hours, target_hours, streak_at_snapshot)
                    VALUES (gen_random_uuid(), :pid, :uid, '2026-02-03', '2026-02-09', 5.0, 10.0, 0)
                """),
                {"pid": priority.id, "uid": user.id},
            )
            await async_session.flush()

        assert "ck_pg_weekly_snapshots_week_start_monday" in str(exc_info.value).lower()

        await async_session.rollback()

    @pytest.mark.asyncio
    async def test_check_constraint_enforced_on_update(self, async_session: AsyncSession):
        """3l. CHECK constraint fires on UPDATE, not just INSERT."""
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        priority = PgPriority(
            user_id=user.id,
            name="Test",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date.today() + timedelta(days=30),
        )
        async_session.add(priority)
        await async_session.commit()

        # Attempt to UPDATE to invalid type
        with pytest.raises(IntegrityError) as exc_info:
            await async_session.execute(
                text("UPDATE pg_priorities SET type = 'invalid' WHERE id = :pid"),
                {"pid": priority.id},
            )
            await async_session.flush()

        assert "ck_pg_priorities_type" in str(exc_info.value).lower()

        await async_session.rollback()


# =============================================================================
# Section 4: Foreign Key Constraint Existence
# =============================================================================


class TestForeignKeyConstraints:
    """Verify FK constraints reject orphaned child rows at PostgreSQL level."""

    @pytest.mark.asyncio
    async def test_deliverable_with_nonexistent_priority_rejected(
        self, async_session: AsyncSession
    ):
        """4a. Deliverable with non-existent priority_id rejected by FK."""
        with pytest.raises(IntegrityError) as exc_info:
            await async_session.execute(
                text("""
                    INSERT INTO pg_deliverables (id, priority_id, name, done)
                    VALUES (gen_random_uuid(), gen_random_uuid(), 'Orphan', false)
                """),
            )
            await async_session.flush()

        # FK violation
        assert "foreign key" in str(exc_info.value).lower() or \
               "fk_" in str(exc_info.value).lower() or \
               "violates" in str(exc_info.value).lower()

        await async_session.rollback()

    @pytest.mark.asyncio
    async def test_goal_with_nonexistent_priority_rejected(self, async_session: AsyncSession):
        """4b. Goal with non-existent priority_id rejected by FK."""
        with pytest.raises(IntegrityError) as exc_info:
            await async_session.execute(
                text("""
                    INSERT INTO pg_goals (id, priority_id, text, achieved)
                    VALUES (gen_random_uuid(), gen_random_uuid(), 'Orphan', false)
                """),
            )
            await async_session.flush()

        assert "foreign key" in str(exc_info.value).lower() or \
               "fk_" in str(exc_info.value).lower() or \
               "violates" in str(exc_info.value).lower()

        await async_session.rollback()

    @pytest.mark.asyncio
    async def test_snapshot_with_nonexistent_priority_rejected(
        self, async_session: AsyncSession
    ):
        """4c. Snapshot with non-existent priority_id rejected by FK."""
        with pytest.raises(IntegrityError) as exc_info:
            await async_session.execute(
                text("""
                    INSERT INTO pg_weekly_snapshots
                    (id, priority_id, user_id, week_start, week_end, actual_hours, target_hours, streak_at_snapshot)
                    VALUES (gen_random_uuid(), gen_random_uuid(), gen_random_uuid(), '2026-02-02', '2026-02-08', 5.0, 10.0, 0)
                """),
            )
            await async_session.flush()

        assert "foreign key" in str(exc_info.value).lower() or \
               "fk_" in str(exc_info.value).lower() or \
               "violates" in str(exc_info.value).lower()

        await async_session.rollback()


# =============================================================================
# Section 5: Transaction Rollback State Verification
# =============================================================================


class TestTransactionRollback:
    """Verify rollback after IntegrityError preserves existing data."""

    @pytest.mark.asyncio
    async def test_rollback_after_integrity_error_preserves_existing_data(
        self, async_session: AsyncSession
    ):
        """After IntegrityError and rollback, original data is unchanged."""
        user_id = uuid4()
        user = CoreUser(id=user_id)
        async_session.add(user)
        await async_session.flush()

        # Insert valid priority
        priority = PgPriority(
            user_id=user_id,
            name="Original Priority",
            type="deadline",
            calendar_keyword="P1",
            status="active",
            deadline=date.today() + timedelta(days=30),
        )
        async_session.add(priority)
        await async_session.commit()

        original_id = priority.id
        original_name = priority.name

        # Attempt duplicate INSERT that will fail
        with pytest.raises(IntegrityError):
            await async_session.execute(
                text("""
                    INSERT INTO pg_priorities
                    (id, user_id, name, type, calendar_keyword, status, deadline)
                    VALUES (gen_random_uuid(), :uid, 'Duplicate', 'deadline', 'P1', 'active', :deadline)
                """),
                {"uid": user_id, "deadline": date.today() + timedelta(days=30)},
            )
            await async_session.flush()

        await async_session.rollback()

        # Verify original priority still exists with correct data
        result = await async_session.execute(
            text("SELECT id, name, calendar_keyword, status FROM pg_priorities WHERE user_id = :uid"),
            {"uid": user_id},
        )
        rows = result.fetchall()

        assert len(rows) == 1, "Should have exactly 1 priority row (no partial second row)"
        row = rows[0]
        assert str(row[0]) == str(original_id), "Original ID preserved"
        assert row[1] == original_name, "Original name preserved"
        assert row[2] == "P1", "Original keyword preserved"
        assert row[3] == "active", "Original status preserved"
