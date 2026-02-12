"""
Add other_hours column to pg_weekly_overview for caching.

Revision ID: q7l8m9n0o1p2
Revises: p6k7l8m9n0o1
Create Date: 2026-02-12

Optimization: Cache other_hours during weekly report generation so
save_semantic_grouping can validate groupings without a duplicate
Google Calendar API fetch.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'q7l8m9n0o1p2'
down_revision: Union[str, Sequence[str], None] = 'p6k7l8m9n0o1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'pg_weekly_overview',
        sa.Column(
            'other_hours',
            sa.Numeric(6, 2),
            nullable=True,
            comment='Non-priority hours from calendar (cached during report generation)'
        )
    )


def downgrade() -> None:
    op.drop_column('pg_weekly_overview', 'other_hours')
