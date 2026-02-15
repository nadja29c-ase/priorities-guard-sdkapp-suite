"""add_pg_check_constraints

Revision ID: 64d82150e4c7
Revises: t0u1v2w3x4y5
Create Date: 2026-02-15 21:18:39.986441

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '64d82150e4c7'
down_revision: Union[str, Sequence[str], None] = 't0u1v2w3x4y5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add CheckConstraints for data integrity."""
    # PgPriority constraints
    op.create_check_constraint(
        "ck_pg_priorities_type_field_consistency",
        "pg_priorities",
        "("
        "(type = 'deadline' AND deadline IS NOT NULL AND weekly_hour_target IS NULL AND checkpoint_date IS NULL) "
        "OR "
        "(type = 'flexible' AND weekly_hour_target IS NOT NULL AND checkpoint_date IS NOT NULL AND deadline IS NULL)"
        ")",
    )
    op.create_check_constraint(
        "ck_pg_priorities_weekly_target_positive",
        "pg_priorities",
        "weekly_hour_target IS NULL OR weekly_hour_target > 0",
    )
    op.create_check_constraint(
        "ck_pg_priorities_retirement_consistency",
        "pg_priorities",
        "(status = 'active' AND retired_at IS NULL) OR (status = 'retired' AND retired_at IS NOT NULL)",
    )

    # PgWeeklySnapshot constraints
    op.create_check_constraint(
        "ck_pg_weekly_snapshots_week_consistency",
        "pg_weekly_snapshots",
        "week_end = week_start + 6",
    )
    op.create_check_constraint(
        "ck_pg_weekly_snapshots_target_hours_non_negative",
        "pg_weekly_snapshots",
        "target_hours IS NULL OR target_hours >= 0",
    )


def downgrade() -> None:
    """Drop CheckConstraints."""
    # PgWeeklySnapshot constraints
    op.drop_constraint(
        "ck_pg_weekly_snapshots_target_hours_non_negative",
        "pg_weekly_snapshots",
        type_="check",
    )
    op.drop_constraint(
        "ck_pg_weekly_snapshots_week_consistency",
        "pg_weekly_snapshots",
        type_="check",
    )

    # PgPriority constraints
    op.drop_constraint(
        "ck_pg_priorities_retirement_consistency",
        "pg_priorities",
        type_="check",
    )
    op.drop_constraint(
        "ck_pg_priorities_weekly_target_positive",
        "pg_priorities",
        type_="check",
    )
    op.drop_constraint(
        "ck_pg_priorities_type_field_consistency",
        "pg_priorities",
        type_="check",
    )
