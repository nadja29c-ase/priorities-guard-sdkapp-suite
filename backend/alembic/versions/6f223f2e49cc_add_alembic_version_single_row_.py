"""add_alembic_version_single_row_constraint

Revision ID: 6f223f2e49cc
Revises: u1v2w3x4y5z6
Create Date: 2026-02-17 17:03:55.676155

Prevents the "multiple heads applied" state by ensuring alembic_version
can never have more than one row. If a forked migration tries to insert
a second version row, PostgreSQL rejects it.

Note: This is defense-in-depth. The primary guard is the pre-deploy check
that runs `alembic heads` and fails if multiple heads exist.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '6f223f2e49cc'
down_revision: Union[str, Sequence[str], None] = 'u1v2w3x4y5z6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add unique index to ensure exactly one row in alembic_version."""
    op.execute(
        "CREATE UNIQUE INDEX idx_alembic_version_single_row "
        "ON alembic_version ((true))"
    )


def downgrade() -> None:
    """Remove single-row constraint."""
    op.execute("DROP INDEX IF EXISTS idx_alembic_version_single_row")
