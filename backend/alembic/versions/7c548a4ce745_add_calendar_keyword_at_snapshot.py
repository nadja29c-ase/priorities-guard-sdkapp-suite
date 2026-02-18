"""add_calendar_keyword_at_snapshot

Revision ID: 7c548a4ce745
Revises: 6f223f2e49cc
Create Date: 2026-02-18

Adds calendar_keyword_at_snapshot column to pg_weekly_snapshots.
This captures the keyword assigned to a priority at the time the snapshot
was created, enabling accurate past-week reports even after keyword swaps.

Nullable because existing snapshots were created before this column existed.
No backfill needed - snapshots are at most 3 weeks old, and the null fallback
(using current priority.calendar_keyword) handles them gracefully.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c548a4ce745'
down_revision: Union[str, Sequence[str], None] = '6f223f2e49cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add calendar_keyword_at_snapshot column."""
    op.add_column(
        'pg_weekly_snapshots',
        sa.Column(
            'calendar_keyword_at_snapshot',
            sa.String(2),
            nullable=True,
            comment='Calendar keyword (P1/P2/P3) at time of snapshot creation. NULL for pre-migration snapshots.',
        )
    )


def downgrade() -> None:
    """Remove calendar_keyword_at_snapshot column."""
    op.drop_column('pg_weekly_snapshots', 'calendar_keyword_at_snapshot')
