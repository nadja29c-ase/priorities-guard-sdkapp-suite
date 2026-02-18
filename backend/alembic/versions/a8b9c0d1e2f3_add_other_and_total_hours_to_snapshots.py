"""add_other_and_total_hours_to_snapshots

Revision ID: a8b9c0d1e2f3
Revises: 7c548a4ce745
Create Date: 2026-02-18

Adds other_hours and total_tracked_hours columns to pg_weekly_snapshots.
These are denormalized per-week values (same across all snapshot rows for
a given week) that enable accurate pie charts for historical weeks.

Nullable for backward compatibility with existing snapshots.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8b9c0d1e2f3'
down_revision: Union[str, Sequence[str], None] = '7c548a4ce745'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add other_hours and total_tracked_hours columns with CHECK constraints."""
    # Add other_hours column
    op.add_column(
        'pg_weekly_snapshots',
        sa.Column(
            'other_hours',
            sa.Numeric(6, 2),
            nullable=True,
            comment='Untagged calendar hours for this week. Same value across all snapshots in the same week. NULL for pre-migration snapshots.',
        )
    )

    # Add total_tracked_hours column
    op.add_column(
        'pg_weekly_snapshots',
        sa.Column(
            'total_tracked_hours',
            sa.Numeric(8, 2),
            nullable=True,
            comment='Total tracked hours (all events) for this week. Same value across all snapshots in the same week. NULL for pre-migration snapshots.',
        )
    )

    # Add CHECK constraint for other_hours non-negative
    op.create_check_constraint(
        'ck_pg_weekly_snapshots_other_hours_non_negative',
        'pg_weekly_snapshots',
        'other_hours IS NULL OR other_hours >= 0',
    )

    # Add CHECK constraint for total_tracked_hours non-negative
    op.create_check_constraint(
        'ck_pg_weekly_snapshots_total_hours_non_negative',
        'pg_weekly_snapshots',
        'total_tracked_hours IS NULL OR total_tracked_hours >= 0',
    )


def downgrade() -> None:
    """Remove other_hours and total_tracked_hours columns and constraints."""
    op.drop_constraint('ck_pg_weekly_snapshots_total_hours_non_negative', 'pg_weekly_snapshots', type_='check')
    op.drop_constraint('ck_pg_weekly_snapshots_other_hours_non_negative', 'pg_weekly_snapshots', type_='check')
    op.drop_column('pg_weekly_snapshots', 'total_tracked_hours')
    op.drop_column('pg_weekly_snapshots', 'other_hours')
