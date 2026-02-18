"""add_keyword_check_constraint

Revision ID: b9c0d1e2f3g4
Revises: a8b9c0d1e2f3
Create Date: 2026-02-18

Adds CHECK constraint for calendar_keyword_at_snapshot domain.
Ensures the column only accepts valid values ('P1', 'P2', 'P3') or NULL,
matching the domain of the source column pg_priorities.calendar_keyword.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b9c0d1e2f3g4'
down_revision: Union[str, Sequence[str], None] = 'a8b9c0d1e2f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add CHECK constraint for calendar_keyword_at_snapshot."""
    op.create_check_constraint(
        'ck_pg_weekly_snapshots_calendar_keyword_at_snapshot',
        'pg_weekly_snapshots',
        "calendar_keyword_at_snapshot IS NULL OR calendar_keyword_at_snapshot IN ('P1', 'P2', 'P3')"
    )


def downgrade() -> None:
    """Remove CHECK constraint for calendar_keyword_at_snapshot."""
    op.drop_constraint(
        'ck_pg_weekly_snapshots_calendar_keyword_at_snapshot',
        'pg_weekly_snapshots',
        type_='check'
    )
