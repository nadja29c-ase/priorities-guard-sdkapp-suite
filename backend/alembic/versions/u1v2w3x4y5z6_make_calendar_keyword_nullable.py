"""Make calendar_keyword nullable for keyword reassignment.

Revision ID: u1v2w3x4y5z6
Revises: t0u1v2w3x4y5
Create Date: 2026-02-17

The keyword reassignment feature requires a 3-step swap using NULL as
a transient intermediary to satisfy the unique index constraint.
NULL is never persisted after transaction commit.
"""
from alembic import op


revision = "u1v2w3x4y5z6"
down_revision = "t0u1v2w3x4y5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("pg_priorities", "calendar_keyword", nullable=True)


def downgrade() -> None:
    # Fail fast if any NULL rows exist — do not silently mutate semantic data
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_priorities WHERE calendar_keyword IS NULL) THEN
                RAISE EXCEPTION 'Cannot downgrade: NULL calendar_keyword rows exist. Fix data before retrying.';
            END IF;
        END$$;
    """)
    op.alter_column("pg_priorities", "calendar_keyword", nullable=False)
