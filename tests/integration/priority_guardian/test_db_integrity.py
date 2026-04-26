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
# Section 1: Soft Delete (API) and CASCADE DELETE (Direct SQL) Verification
# =============================================================================


class TestSoftDelete:
    """Verify API DELETE soft-deletes priorities (preserves children)."""

    @pytest.mark.asyncio
    async def test_soft_delete_preserves_deliverables_in_db(
        self, client, async_session: AsyncSession
    ):
        """1a. API DELETE soft-deletes priority, preserving deliverables."""
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

        # DELETE via API (soft delete)
        response = await client.delete(
            f"/api/priority-guardian/priorities/{priority_id}",
            headers={"X-User-ID": str(user.id)},
        )
        assert response.status_code == 200

        # Verify priority is retired (not deleted)
        result = await async_session.execute(
            text("SELECT status, calendar_keyword, retired_at FROM pg_priorities WHERE id = :pid"),
            {"pid": priority_id},
        )
        row = result.fetchone()
        assert row is not None, "Priority should still exist"
        assert row[0] == "retired", "Status should be 'retired'"
        assert row[1] is None, "calendar_keyword should be NULL"
        assert row[2] is not None, "retired_at should be set"

        # Verify deliverables are PRESERVED (soft delete keeps children)
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_deliverables WHERE priority_id = :pid"),
            {"pid": priority_id},
        )
        assert result.scalar() == 2, "Deliverables should be preserved on soft delete"

    @pytest.mark.asyncio
    async def test_soft_delete_preserves_goals_in_db(
        self, client, async_session: AsyncSession
    ):
        """1b. API DELETE soft-deletes priority, preserving goals."""
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

        # DELETE via API (soft delete)
        response = await client.delete(
            f"/api/priority-guardian/priorities/{priority_id}",
            headers={"X-User-ID": str(user_id)},
        )
        assert response.status_code == 200

        # Verify priority is retired
        result = await async_session.execute(
            text("SELECT status FROM pg_priorities WHERE id = :pid"),
            {"pid": priority_id},
        )
        assert result.scalar() == "retired"

        # Verify goals are PRESERVED
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_goals WHERE priority_id = :pid"),
            {"pid": priority_id},
        )
        assert result.scalar() == 2, "Goals should be preserved on soft delete"

    @pytest.mark.asyncio
    async def test_soft_delete_preserves_snapshots_in_db(
        self, client, async_session: AsyncSession
    ):
        """1c. API DELETE soft-deletes priority, preserving snapshots."""
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
                (id, priority_id, user_id, week_start, week_end, actual_hours, target_hours,
                 streak_at_snapshot, calendar_keyword_at_snapshot)
                VALUES
                (gen_random_uuid(), :pid, :uid, '2026-01-19', '2026-01-25', 5.0, 10.0, 1, 'P1'),
                (gen_random_uuid(), :pid, :uid, '2026-01-26', '2026-02-01', 6.0, 10.0, 2, 'P1')
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

        # DELETE via API (soft delete)
        response = await client.delete(
            f"/api/priority-guardian/priorities/{priority_id}",
            headers={"X-User-ID": str(user.id)},
        )
        assert response.status_code == 200

        # Verify priority is retired with NULL keyword
        result = await async_session.execute(
            text("SELECT status, calendar_keyword FROM pg_priorities WHERE id = :pid"),
            {"pid": priority_id},
        )
        row = result.fetchone()
        assert row[0] == "retired"
        assert row[1] is None

        # Verify snapshots are PRESERVED with calendar_keyword_at_snapshot intact
        result = await async_session.execute(
            text("""
                SELECT calendar_keyword_at_snapshot
                FROM pg_weekly_snapshots
                WHERE priority_id = :pid
            """),
            {"pid": priority_id},
        )
        rows = result.fetchall()
        assert len(rows) == 2, "Snapshots should be preserved on soft delete"
        for row in rows:
            assert row[0] == "P1", "calendar_keyword_at_snapshot should be preserved"


class TestCascadeDelete:
    """Verify CASCADE DELETE (direct SQL or permanent delete) removes children."""

    @pytest.mark.asyncio
    async def test_permanent_delete_cascades_deliverables_via_api(
        self, client, async_session: AsyncSession
    ):
        """Permanent delete endpoint cascades deliverables."""
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

        # PERMANENT DELETE via API
        response = await client.delete(
            f"/api/priority-guardian/priorities/{priority_id}/permanent",
            headers={"X-User-ID": str(user.id)},
        )
        assert response.status_code == 200

        # Verify priority is gone
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_priorities WHERE id = :pid"),
            {"pid": priority_id},
        )
        assert result.scalar() == 0, "Priority should be hard deleted"

        # Verify deliverables are CASCADE deleted
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_deliverables WHERE priority_id = :pid"),
            {"pid": priority_id},
        )
        assert result.scalar() == 0, "Deliverables should be CASCADE deleted"

    @pytest.mark.asyncio
    async def test_permanent_delete_cascades_goals_and_snapshots_via_api(
        self, client, async_session: AsyncSession
    ):
        """Permanent delete endpoint cascades goals and snapshots."""
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
            created_at=datetime(2026, 1, 1),
        )
        async_session.add(priority)
        await async_session.flush()

        priority_id = priority.id

        # Add goals
        for i in range(2):
            goal = PgGoal(
                priority_id=priority_id,
                goal_text=f"Goal {i+1}",
                achieved=False,
            )
            async_session.add(goal)

        # Add snapshots
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

        # Verify children exist
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_goals WHERE priority_id = :pid"),
            {"pid": priority_id},
        )
        assert result.scalar() == 2

        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_weekly_snapshots WHERE priority_id = :pid"),
            {"pid": priority_id},
        )
        assert result.scalar() == 2

        # PERMANENT DELETE via API
        response = await client.delete(
            f"/api/priority-guardian/priorities/{priority_id}/permanent",
            headers={"X-User-ID": str(user.id)},
        )
        assert response.status_code == 200

        # Verify all children are CASCADE deleted
        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_goals WHERE priority_id = :pid"),
            {"pid": priority_id},
        )
        assert result.scalar() == 0, "Goals should be CASCADE deleted"

        result = await async_session.execute(
            text("SELECT COUNT(*) FROM pg_weekly_snapshots WHERE priority_id = :pid"),
            {"pid": priority_id},
        )
        assert result.scalar() == 0, "Snapshots should be CASCADE deleted"

    @pytest.mark.asyncio
    async def test_soft_delete_does_not_cascade_other_users_data(
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
    async def test_snapshot_negative_other_hours_rejected(self, async_session: AsyncSession):
        """3l. Negative other_hours on snapshot rejected by CHECK constraint."""
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
                    (id, priority_id, user_id, week_start, week_end, actual_hours, target_hours, streak_at_snapshot, other_hours)
                    VALUES (gen_random_uuid(), :pid, :uid, '2026-02-02', '2026-02-08', 5.0, 10.0, 0, -1.0)
                """),
                {"pid": priority.id, "uid": user.id},
            )
            await async_session.flush()

        assert "ck_pg_weekly_snapshots_other_hours_non_negative" in str(exc_info.value).lower()

        await async_session.rollback()

    @pytest.mark.asyncio
    async def test_snapshot_negative_total_tracked_hours_rejected(self, async_session: AsyncSession):
        """3m. Negative total_tracked_hours on snapshot rejected by CHECK constraint."""
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
                    (id, priority_id, user_id, week_start, week_end, actual_hours, target_hours, streak_at_snapshot, total_tracked_hours)
                    VALUES (gen_random_uuid(), :pid, :uid, '2026-02-02', '2026-02-08', 5.0, 10.0, 0, -5.0)
                """),
                {"pid": priority.id, "uid": user.id},
            )
            await async_session.flush()

        assert "ck_pg_weekly_snapshots_total_hours_non_negative" in str(exc_info.value).lower()

        await async_session.rollback()

    @pytest.mark.asyncio
    async def test_snapshot_zero_other_hours_accepted(self, async_session: AsyncSession):
        """3n. Zero other_hours is valid (boundary test)."""
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

        # Zero is valid
        await async_session.execute(
            text("""
                INSERT INTO pg_weekly_snapshots
                (id, priority_id, user_id, week_start, week_end, actual_hours, target_hours, streak_at_snapshot, other_hours, total_tracked_hours)
                VALUES (gen_random_uuid(), :pid, :uid, '2026-02-02', '2026-02-08', 5.0, 10.0, 0, 0.0, 5.0)
            """),
            {"pid": priority.id, "uid": user.id},
        )
        await async_session.commit()

        # Verify it was inserted
        result = await async_session.execute(
            text("SELECT other_hours, total_tracked_hours FROM pg_weekly_snapshots WHERE priority_id = :pid"),
            {"pid": priority.id},
        )
        row = result.fetchone()
        assert float(row[0]) == 0.0
        assert float(row[1]) == 5.0

    @pytest.mark.asyncio
    async def test_snapshot_null_other_hours_accepted(self, async_session: AsyncSession):
        """3o. NULL other_hours is valid (for pre-migration snapshots)."""
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

        # NULL is valid
        await async_session.execute(
            text("""
                INSERT INTO pg_weekly_snapshots
                (id, priority_id, user_id, week_start, week_end, actual_hours, target_hours, streak_at_snapshot, other_hours, total_tracked_hours)
                VALUES (gen_random_uuid(), :pid, :uid, '2026-02-02', '2026-02-08', 5.0, 10.0, 0, NULL, NULL)
            """),
            {"pid": priority.id, "uid": user.id},
        )
        await async_session.commit()

        # Verify it was inserted with NULL
        result = await async_session.execute(
            text("SELECT other_hours, total_tracked_hours FROM pg_weekly_snapshots WHERE priority_id = :pid"),
            {"pid": priority.id},
        )
        row = result.fetchone()
        assert row[0] is None
        assert row[1] is None

    @pytest.mark.asyncio
    async def test_snapshot_invalid_calendar_keyword_at_snapshot_rejected(
        self, async_session: AsyncSession
    ):
        """3p. Invalid calendar_keyword_at_snapshot rejected by CHECK constraint."""
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

        # P4 is not a valid keyword
        with pytest.raises(IntegrityError) as exc_info:
            await async_session.execute(
                text("""
                    INSERT INTO pg_weekly_snapshots
                    (id, priority_id, user_id, week_start, week_end, actual_hours, target_hours, streak_at_snapshot, calendar_keyword_at_snapshot)
                    VALUES (gen_random_uuid(), :pid, :uid, '2026-02-02', '2026-02-08', 5.0, 10.0, 0, 'P4')
                """),
                {"pid": priority.id, "uid": user.id},
            )
            await async_session.flush()

        assert "ck_pg_weekly_snapshots_calendar_keyword_at_snapshot" in str(exc_info.value).lower()

        await async_session.rollback()

    @pytest.mark.asyncio
    async def test_snapshot_valid_calendar_keyword_at_snapshot_accepted(
        self, async_session: AsyncSession
    ):
        """3q. Valid calendar_keyword_at_snapshot (P1/P2/P3 or NULL) accepted."""
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

        # Test valid values: P1, P2, P3, NULL
        for keyword in ['P1', 'P2', 'P3']:
            snapshot_id = uuid4()
            await async_session.execute(
                text("""
                    INSERT INTO pg_weekly_snapshots
                    (id, priority_id, user_id, week_start, week_end, actual_hours, target_hours, streak_at_snapshot, calendar_keyword_at_snapshot)
                    VALUES (:sid, :pid, :uid, '2026-02-02', '2026-02-08', 5.0, 10.0, 0, :keyword)
                """),
                {"sid": snapshot_id, "pid": priority.id, "uid": user.id, "keyword": keyword},
            )

            # Delete for next iteration
            await async_session.execute(
                text("DELETE FROM pg_weekly_snapshots WHERE id = :sid"),
                {"sid": snapshot_id},
            )

        await async_session.commit()

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


# =============================================================================
# Section 6: Retired Priority Aggregate Freeze
# =============================================================================


class TestRetiredPriorityAggregateFreeze:
    """Verify _update_aggregates only modifies active priorities."""

    @pytest.mark.asyncio
    async def test_aggregate_update_skips_retired_priority_in_db(
        self, async_session: AsyncSession
    ):
        """_update_aggregates WHERE clause excludes retired priorities.

        This is an integration test that verifies the actual SQL behavior:
        1. Create an active priority with known aggregate values
        2. Retire it
        3. Call _update_aggregates for that priority_id
        4. Verify the aggregate fields are unchanged (UPDATE affected 0 rows)
        """
        from backend.apps.priority_guardian.services.snapshot_service import _update_aggregates

        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Create priority with specific aggregate values
        priority = PgPriority(
            user_id=user.id,
            name="Test Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date.today() + timedelta(days=30),
            created_at=datetime(2026, 1, 1),
            # Set known aggregate values
            streak_count=5,
            total_hours_invested=Decimal("100.0"),
            avg_target_achievement=Decimal("85.0"),
        )
        async_session.add(priority)
        await async_session.commit()

        priority_id = priority.id

        # Record original values
        original_streak = 5
        original_hours = Decimal("100.0")
        original_achievement = Decimal("85.0")

        # Create a snapshot so _update_aggregates has data to compute from
        await async_session.execute(
            text("""
                INSERT INTO pg_weekly_snapshots
                (id, priority_id, user_id, week_start, week_end, actual_hours, target_hours,
                 streak_at_snapshot, calendar_keyword_at_snapshot)
                VALUES (gen_random_uuid(), :pid, :uid, '2026-01-19', '2026-01-25', 8.0, 10.0, 1, 'P1')
            """),
            {"pid": priority_id, "uid": user.id},
        )
        await async_session.commit()

        # Retire the priority
        await async_session.execute(
            text("""
                UPDATE pg_priorities
                SET status = 'retired', retired_at = NOW(), calendar_keyword = NULL
                WHERE id = :pid
            """),
            {"pid": priority_id},
        )
        await async_session.commit()

        # Call _update_aggregates - should NOT update because priority is retired
        await _update_aggregates(
            priority_id=priority_id,
            streak=10,  # Different from original
            actual_hours=50.0,  # Would change total_hours_invested
            session=async_session,
        )
        await async_session.commit()

        # Verify aggregates are UNCHANGED (frozen at retirement)
        result = await async_session.execute(
            text("""
                SELECT streak_count, total_hours_invested, avg_target_achievement
                FROM pg_priorities
                WHERE id = :pid
            """),
            {"pid": priority_id},
        )
        row = result.fetchone()

        assert row[0] == original_streak, "streak_count should be frozen"
        assert row[1] == original_hours, "total_hours_invested should be frozen"
        assert row[2] == original_achievement, "avg_target_achievement should be frozen"

    @pytest.mark.asyncio
    async def test_aggregate_update_modifies_active_priority_in_db(
        self, async_session: AsyncSession
    ):
        """Contrast test: _update_aggregates DOES modify active priorities."""
        from backend.apps.priority_guardian.services.snapshot_service import _update_aggregates

        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        priority = PgPriority(
            user_id=user.id,
            name="Active Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date.today() + timedelta(days=30),
            created_at=datetime(2026, 1, 1),
            streak_count=0,
            total_hours_invested=Decimal("0"),
            avg_target_achievement=None,
        )
        async_session.add(priority)
        await async_session.commit()

        priority_id = priority.id

        # Create a snapshot
        await async_session.execute(
            text("""
                INSERT INTO pg_weekly_snapshots
                (id, priority_id, user_id, week_start, week_end, actual_hours, target_hours,
                 streak_at_snapshot, calendar_keyword_at_snapshot)
                VALUES (gen_random_uuid(), :pid, :uid, '2026-01-19', '2026-01-25', 8.0, 10.0, 1, 'P1')
            """),
            {"pid": priority_id, "uid": user.id},
        )
        await async_session.commit()

        # Call _update_aggregates on ACTIVE priority
        await _update_aggregates(
            priority_id=priority_id,
            streak=3,
            actual_hours=8.0,
            session=async_session,
        )
        await async_session.commit()

        # Verify aggregates ARE updated
        result = await async_session.execute(
            text("""
                SELECT streak_count, total_hours_invested
                FROM pg_priorities
                WHERE id = :pid
            """),
            {"pid": priority_id},
        )
        row = result.fetchone()

        assert row[0] == 3, "streak_count should be updated"
        assert row[1] == Decimal("8.0"), "total_hours_invested should be updated"


# =============================================================================
# Section 7: Snapshot Row Invariants (Overlap Fix)
# =============================================================================


class TestSnapshotRowInvariants:
    """
    Verify snapshot row invariants hold after overlap fix.

    Critical context: pg_weekly_snapshots stores `other_hours` and `total_tracked_hours`
    as **denormalized week-level values** — every snapshot row for a given user+week
    carries identical copies of these two values. This means a naive SUM(other_hours)
    across rows would multiply-count. These tests account for this.
    """

    @pytest.mark.asyncio
    async def test_snapshot_row_invariant_total_equals_components(
        self, async_session: AsyncSession
    ):
        """
        Verify snapshot invariant: sum(actual_hours) + other_hours == total_tracked_hours.

        Setup: P1 and P2 priorities with overlapping events {P1 15-17, P2 16-16:30}.
        Triggers snapshot creation and verifies:
        1. All rows agree on other_hours and total_tracked_hours (consistency)
        2. For each row, actual_hours <= total_tracked_hours (per-priority bound)
        3. sum(actual_hours) + other_hours == total_tracked_hours (component sum)
        """
        from backend.apps.priority_guardian.services.snapshot_service import (
            _create_snapshots_for_week,
        )
        from unittest.mock import AsyncMock, patch

        # Create user
        user = CoreUser(id=uuid4())
        async_session.add(user)
        await async_session.flush()

        # Create P1 priority (created well before test week)
        priority_p1 = PgPriority(
            user_id=user.id,
            name="P1 Priority",
            type="flexible",
            calendar_keyword="P1",
            status="active",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=date(2026, 3, 15),
            created_at=datetime(2025, 12, 1),
        )
        async_session.add(priority_p1)

        # Create P2 priority
        priority_p2 = PgPriority(
            user_id=user.id,
            name="P2 Priority",
            type="flexible",
            calendar_keyword="P2",
            status="active",
            weekly_hour_target=Decimal("5.0"),
            checkpoint_date=date(2026, 3, 15),
            created_at=datetime(2025, 12, 1),
        )
        async_session.add(priority_p2)
        await async_session.commit()

        # Test week: Jan 5, 2026 (Monday)
        test_week_start = date(2026, 1, 5)
        test_tuesday = "2026-01-06"

        # Overlapping events: P1 15-17, P2 16-16:30
        # Expected allocation:
        #   P1: 1.5h (15:00-16:00) + 0.25h (half of 16:00-16:30 overlap) = 1.75h
        #   P2: 0.25h (half of 16:00-16:30 overlap)
        #   P1 remaining: 0.5h (16:30-17:00) — wait, let me recalculate:
        #   Actually the sweep line logic:
        #     15:00-16:00: P1 only → 1h to P1
        #     16:00-16:30: P1+P2 overlap → 0.25h each
        #     16:30-17:00: P1 only → 0.5h to P1
        #   So P1 = 1 + 0.25 + 0.5 = 1.75h, P2 = 0.25h
        mock_events = [
            {
                "id": "event-p1",
                "summary": "[P1] Deep work",
                "start": {"dateTime": f"{test_tuesday}T15:00:00Z"},
                "end": {"dateTime": f"{test_tuesday}T17:00:00Z"},
                "status": "confirmed",
            },
            {
                "id": "event-p2",
                "summary": "[P2] Quick call",
                "start": {"dateTime": f"{test_tuesday}T16:00:00Z"},
                "end": {"dateTime": f"{test_tuesday}T16:30:00Z"},
                "status": "confirmed",
            },
        ]

        mock_http_client = AsyncMock()
        log = {"user_id": str(user.id), "correlation_id": "test"}

        with patch(
            "backend.apps.priority_guardian.services.snapshot_service.list_events"
        ) as mock_list_events, patch(
            "backend.apps.priority_guardian.services.snapshot_service.compute_week_boundaries"
        ) as mock_boundaries, patch(
            "backend.apps.priority_guardian.services.snapshot_service.to_rfc3339"
        ) as mock_rfc:
            mock_list_events.return_value = (mock_events, 0)
            mock_boundaries.return_value = (
                datetime(2026, 1, 5, 0, 0),
                datetime(2026, 1, 12, 0, 0),
            )
            mock_rfc.side_effect = lambda dt: dt.isoformat() + "Z"

            result = await _create_snapshots_for_week(
                user_id=user.id,
                week_start=test_week_start,
                timezone_str="UTC",
                priorities=[priority_p1, priority_p2],
                access_token="test_token",
                session=async_session,
                http_client=mock_http_client,
                log=log,
            )

        assert result is True

        # -------------------------------------------------------------------------
        # Consistency assertion: all rows agree on other_hours and total_tracked_hours
        # -------------------------------------------------------------------------
        distinct_result = await async_session.execute(
            text("""
                SELECT DISTINCT other_hours, total_tracked_hours
                FROM pg_weekly_snapshots
                WHERE user_id = :uid AND week_start = :ws
            """),
            {"uid": user.id, "ws": test_week_start},
        )
        distinct_rows = distinct_result.fetchall()

        assert len(distinct_rows) == 1, (
            f"Expected exactly 1 distinct (other_hours, total_tracked_hours) pair, "
            f"got {len(distinct_rows)}: {distinct_rows}"
        )

        representative_other_hours = distinct_rows[0][0]
        representative_total_tracked = distinct_rows[0][1]

        # -------------------------------------------------------------------------
        # Per-priority bound: actual_hours <= total_tracked_hours for each row
        # -------------------------------------------------------------------------
        all_snapshots_result = await async_session.execute(
            text("""
                SELECT priority_id, actual_hours, other_hours, total_tracked_hours
                FROM pg_weekly_snapshots
                WHERE user_id = :uid AND week_start = :ws
            """),
            {"uid": user.id, "ws": test_week_start},
        )
        all_rows = all_snapshots_result.fetchall()

        assert len(all_rows) == 2, f"Expected 2 snapshot rows, got {len(all_rows)}"

        for row in all_rows:
            priority_id, actual_hours, other_hours, total_tracked = row
            assert actual_hours <= total_tracked, (
                f"Per-priority bound violated: actual_hours ({actual_hours}) > "
                f"total_tracked_hours ({total_tracked}) for priority {priority_id}"
            )

        # -------------------------------------------------------------------------
        # Component sum: sum(actual_hours) + other_hours == total_tracked_hours
        # -------------------------------------------------------------------------
        total_actual_hours = sum(row[1] for row in all_rows)  # actual_hours from all rows
        computed_total = total_actual_hours + representative_other_hours

        # 0.02 tolerance matches the rounding tolerance in part 1 invariant 1
        assert abs(float(computed_total) - float(representative_total_tracked)) <= 0.02, (
            f"Component sum invariant violated: "
            f"sum(actual_hours)={total_actual_hours} + other_hours={representative_other_hours} "
            f"= {computed_total} != total_tracked_hours={representative_total_tracked}"
        )
