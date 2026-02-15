"""add_week_start_monday_constraint

Revision ID: bd663e1fe566
Revises: 64d82150e4c7
Create Date: 2026-02-15 21:29:41.765878

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'bd663e1fe566'
down_revision: Union[str, Sequence[str], None] = '64d82150e4c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add week_start must be Monday constraint."""
    op.create_check_constraint(
        "ck_pg_weekly_snapshots_week_start_monday",
        "pg_weekly_snapshots",
        "EXTRACT(ISODOW FROM week_start) = 1",
    )


def downgrade() -> None:
    """Drop week_start Monday constraint."""
    op.drop_constraint(
        "ck_pg_weekly_snapshots_week_start_monday",
        "pg_weekly_snapshots",
        type_="check",
    )
