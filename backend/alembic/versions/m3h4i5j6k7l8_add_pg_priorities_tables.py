"""
Add pg_priorities and pg_deliverables tables.

Revision ID: m3h4i5j6k7l8
Revises: l2g3h4i5j6k7
Create Date: 2026-02-08

PG Increment 02: Priority Guardian priority tracking tables.

pg_priorities: User's declared priorities with calendar keyword tracking.
pg_deliverables: Deliverables associated with deadline-type priorities.

Tables use `pg_*` prefix and live in the shared PostgreSQL instance alongside `core_*` tables.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'm3h4i5j6k7l8'
down_revision: Union[str, Sequence[str], None] = 'l2g3h4i5j6k7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure pgcrypto extension exists for gen_random_uuid()
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # Create pg_priorities table
    op.create_table(
        'pg_priorities',
        sa.Column(
            'id',
            postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'),
            nullable=False,
            comment='Internal identifier',
        ),
        sa.Column(
            'user_id',
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment='Owner user ID',
        ),
        sa.Column(
            'name',
            sa.String(100),
            nullable=False,
            comment='User-authored priority name',
        ),
        sa.Column(
            'type',
            sa.String(10),
            nullable=False,
            comment='Priority type: deadline or flexible',
        ),
        sa.Column(
            'calendar_keyword',
            sa.String(2),
            nullable=False,
            comment='Assigned calendar keyword (P1, P2, P3)',
        ),
        sa.Column(
            'status',
            sa.String(10),
            nullable=False,
            server_default=sa.text("'active'"),
            comment='Priority status: active or retired',
        ),
        sa.Column(
            'deadline',
            sa.Date(),
            nullable=True,
            comment='Hard end date (required for deadline type)',
        ),
        sa.Column(
            'weekly_hour_target',
            sa.Numeric(6, 2),
            nullable=True,
            comment='Hours per week target (required for flexible type)',
        ),
        sa.Column(
            'checkpoint_date',
            sa.Date(),
            nullable=True,
            comment='Evaluation checkpoint ~1 month out (required for flexible type)',
        ),
        sa.Column(
            'desired_result',
            sa.String(200),
            nullable=True,
            comment='Concrete outcome in ~1 month (required for flexible type)',
        ),
        # Future aggregate columns (placeholders - do NOT read/write in Inc 02)
        sa.Column(
            'streak_count',
            sa.Integer(),
            nullable=False,
            server_default=sa.text('0'),
            comment='Future: consecutive weeks meeting target',
        ),
        sa.Column(
            'avg_hours_week',
            sa.Numeric(6, 2),
            nullable=True,
            comment='Future: rolling average hours per week',
        ),
        sa.Column(
            'total_hours_invested',
            sa.Numeric(8, 2),
            nullable=False,
            server_default=sa.text('0'),
            comment='Future: cumulative hours invested',
        ),
        sa.Column(
            'retired_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='When priority was retired',
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
            comment='When priority was created',
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
            comment='When priority was last updated',
        ),
        # Constraints
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['core_users.id'],
            name='fk_pg_priorities_user_id',
            ondelete='CASCADE',
        ),
        sa.CheckConstraint(
            "type IN ('deadline', 'flexible')",
            name='ck_pg_priorities_type',
        ),
        sa.CheckConstraint(
            "calendar_keyword IN ('P1', 'P2', 'P3')",
            name='ck_pg_priorities_keyword',
        ),
        sa.CheckConstraint(
            "status IN ('active', 'retired')",
            name='ck_pg_priorities_status',
        ),
    )

    # Create index on user_id
    op.create_index(
        'idx_pg_priorities_user_id',
        'pg_priorities',
        ['user_id'],
    )

    # Create partial unique index: one active keyword per user
    # UNIQUE(user_id, calendar_keyword) WHERE status = 'active'
    op.execute(
        "CREATE UNIQUE INDEX idx_pg_priorities_user_keyword_active "
        "ON pg_priorities (user_id, calendar_keyword) "
        "WHERE status = 'active'"
    )

    # Create index for user's active priorities
    op.execute(
        "CREATE INDEX idx_pg_priorities_user_active "
        "ON pg_priorities (user_id) "
        "WHERE status = 'active'"
    )

    # Create pg_deliverables table
    op.create_table(
        'pg_deliverables',
        sa.Column(
            'id',
            postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'),
            nullable=False,
            comment='Internal identifier',
        ),
        sa.Column(
            'priority_id',
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment='Parent priority',
        ),
        sa.Column(
            'name',
            sa.String(200),
            nullable=False,
            comment='Deliverable name',
        ),
        sa.Column(
            'done',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
            comment='Whether deliverable is completed',
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
            comment='When deliverable was created',
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text('now()'),
            comment='When deliverable was last updated',
        ),
        # Constraints
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['priority_id'],
            ['pg_priorities.id'],
            name='fk_pg_deliverables_priority_id',
            ondelete='CASCADE',
        ),
    )

    # Create index on priority_id for CASCADE lookups
    op.create_index(
        'idx_pg_deliverables_priority_id',
        'pg_deliverables',
        ['priority_id'],
    )


def downgrade() -> None:
    # Drop indexes
    op.execute("DROP INDEX IF EXISTS idx_pg_deliverables_priority_id")
    op.execute("DROP INDEX IF EXISTS idx_pg_priorities_user_active")
    op.execute("DROP INDEX IF EXISTS idx_pg_priorities_user_keyword_active")
    op.execute("DROP INDEX IF EXISTS idx_pg_priorities_user_id")

    # Drop tables
    op.drop_table('pg_deliverables')
    op.drop_table('pg_priorities')
