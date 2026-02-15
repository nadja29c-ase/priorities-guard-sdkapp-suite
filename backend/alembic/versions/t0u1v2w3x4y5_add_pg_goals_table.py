"""Add pg_goals table and migrate desired_result.

Create pg_goals table for flexible priorities (1-3 goals per priority).
Migrate existing desired_result values to goals.
Drop desired_result column from pg_priorities.

Revision ID: t0u1v2w3x4y5
Revises: s9t0u1v2w3x4
Create Date: 2026-02-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "t0u1v2w3x4y5"
down_revision = "s9t0u1v2w3x4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 1. Create pg_goals table
    # -------------------------------------------------------------------------
    op.create_table(
        "pg_goals",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
            comment="Internal identifier",
        ),
        sa.Column(
            "priority_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pg_priorities.id", ondelete="CASCADE"),
            nullable=False,
            comment="Parent priority",
        ),
        sa.Column(
            "text",
            sa.String(200),
            nullable=False,
            comment="Goal text",
        ),
        sa.Column(
            "achieved",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Whether goal is achieved",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="When goal was created",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="When goal was last updated",
        ),
    )

    # Create index on priority_id for efficient lookups
    op.create_index(
        "ix_pg_goals_priority_id",
        "pg_goals",
        ["priority_id"],
    )

    # Create updated_at trigger (uses pg_set_updated_at from o5j6k7l8m9n0)
    op.execute("""
        CREATE TRIGGER trg_pg_goals_updated_at
        BEFORE UPDATE ON pg_goals
        FOR EACH ROW
        EXECUTE FUNCTION pg_set_updated_at()
    """)

    # -------------------------------------------------------------------------
    # 2. Migrate existing desired_result values to pg_goals
    # -------------------------------------------------------------------------
    # For each flexible priority with a non-null desired_result, create a goal
    op.execute("""
        INSERT INTO pg_goals (priority_id, text, achieved, created_at, updated_at)
        SELECT id, desired_result, false, now(), now()
        FROM pg_priorities
        WHERE type = 'flexible'
          AND desired_result IS NOT NULL
          AND desired_result != ''
    """)

    # -------------------------------------------------------------------------
    # 3. Drop desired_result column from pg_priorities
    # -------------------------------------------------------------------------
    op.drop_column("pg_priorities", "desired_result")


def downgrade() -> None:
    # -------------------------------------------------------------------------
    # 1. Re-add desired_result column to pg_priorities
    # -------------------------------------------------------------------------
    op.add_column(
        "pg_priorities",
        sa.Column(
            "desired_result",
            sa.String(200),
            nullable=True,
            comment="Concrete outcome in ~1 month (required for flexible type)",
        ),
    )

    # -------------------------------------------------------------------------
    # 2. Migrate first goal back to desired_result
    # -------------------------------------------------------------------------
    # For each priority, take the first goal (by created_at) and put it back
    op.execute("""
        UPDATE pg_priorities p
        SET desired_result = (
            SELECT g.text
            FROM pg_goals g
            WHERE g.priority_id = p.id
            ORDER BY g.created_at ASC
            LIMIT 1
        )
        WHERE p.type = 'flexible'
    """)

    # -------------------------------------------------------------------------
    # 3. Drop pg_goals table and its trigger
    # -------------------------------------------------------------------------
    op.execute("DROP TRIGGER IF EXISTS trg_pg_goals_updated_at ON pg_goals")
    op.drop_index("ix_pg_goals_priority_id", table_name="pg_goals")
    op.drop_table("pg_goals")
