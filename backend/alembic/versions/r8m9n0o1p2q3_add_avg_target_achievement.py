"""Add avg_target_achievement column to pg_priorities

Revision ID: r8m9n0o1p2q3
Revises: q7l8m9n0o1p2
Create Date: 2026-02-14

Stores the average percentage of weekly target achieved across all snapshotted weeks.
NULL when fewer than 2 data points exist. Populated by snapshot pipeline on dashboard load.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "r8m9n0o1p2q3"
down_revision = "q7l8m9n0o1p2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pg_priorities",
        sa.Column(
            "avg_target_achievement",
            sa.Numeric(precision=6, scale=2),
            nullable=True,
            comment="Average % of weekly target achieved across all snapshotted weeks. NULL when < 2 data points.",
        ),
    )


def downgrade() -> None:
    op.drop_column("pg_priorities", "avg_target_achievement")
