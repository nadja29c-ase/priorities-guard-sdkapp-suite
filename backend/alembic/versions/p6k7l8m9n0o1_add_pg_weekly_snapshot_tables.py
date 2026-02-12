"""
Add pg_weekly_snapshots and pg_weekly_overview tables for weekly report persistence.

Revision ID: p6k7l8m9n0o1
Revises: o5j6k7l8m9n0
Create Date: 2026-02-12

pg_weekly_snapshots: One row per priority per week. Stores deterministic,
keyword-matched data at time of finalization. Supports week-over-week
comparison and aggregate computation.

pg_weekly_overview: One row per user per week. Stores user-week-level data
that doesn't belong on per-priority rows (e.g., semantic_grouping in Inc 07).
Created empty in this migration; populated by future save_semantic_grouping tool.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'p6k7l8m9n0o1'
down_revision: Union[str, Sequence[str], None] = 'o5j6k7l8m9n0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==========================================================================
    # pg_weekly_snapshots table
    # ==========================================================================
    op.create_table(
        'pg_weekly_snapshots',
        # Primary key
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),

        # Foreign keys (denormalized user_id for query efficiency)
        sa.Column('priority_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),

        # Week boundaries
        sa.Column('week_start', sa.Date(), nullable=False),  # Monday
        sa.Column('week_end', sa.Date(), nullable=False),    # Sunday (week_start + 6)

        # Core metrics (all priority types)
        sa.Column('actual_hours', sa.Numeric(6, 2), nullable=False),
        sa.Column('event_count', sa.Integer(), nullable=False),

        # Deadline-specific fields (nullable for flexible priorities)
        sa.Column('deadline_date', sa.Date(), nullable=True),
        sa.Column('days_remaining', sa.Integer(), nullable=True),
        sa.Column('deliverables_completed', sa.Integer(), nullable=True),
        sa.Column('deliverables_total', sa.Integer(), nullable=True),
        sa.Column('pacing_status', sa.String(20), nullable=True),  # on_track, behind, ahead, completed

        # Flexible-specific fields (nullable for deadline priorities)
        sa.Column('target_hours', sa.Numeric(6, 2), nullable=True),
        sa.Column('flex_status', sa.String(20), nullable=True),  # ahead, on_track, behind
        sa.Column('streak_at_snapshot', sa.Integer(), nullable=True),  # streak_count AFTER this week's update

        # Audit timestamp
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),

        # Primary key constraint
        sa.PrimaryKeyConstraint('id'),

        # Foreign key constraints with CASCADE delete
        sa.ForeignKeyConstraint(['priority_id'], ['pg_priorities.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['core_users.id'], ondelete='CASCADE'),

        # Check constraints
        sa.CheckConstraint('actual_hours >= 0', name='ck_pg_weekly_snapshots_actual_hours_non_negative'),
        sa.CheckConstraint('event_count >= 0', name='ck_pg_weekly_snapshots_event_count_non_negative'),
    )

    # Unique constraint: one snapshot per priority per week
    op.create_unique_constraint(
        'uq_pg_weekly_snapshots_priority_week',
        'pg_weekly_snapshots',
        ['priority_id', 'week_start']
    )

    # Index for loading recent snapshots by user
    op.create_index(
        'idx_pg_weekly_snapshots_user_week',
        'pg_weekly_snapshots',
        ['user_id', sa.text('week_start DESC')]
    )

    # Index for loading history of a specific priority
    op.create_index(
        'idx_pg_weekly_snapshots_priority_week',
        'pg_weekly_snapshots',
        ['priority_id', sa.text('week_start DESC')]
    )

    # ==========================================================================
    # pg_weekly_overview table
    # ==========================================================================
    op.create_table(
        'pg_weekly_overview',
        # Primary key
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),

        # Foreign key
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),

        # Week identifier
        sa.Column('week_start', sa.Date(), nullable=False),  # Monday

        # Semantic grouping (nullable, populated by Inc 07's save_semantic_grouping tool)
        # Shape: [{"category": "...", "hours": N, "event_count": N}, ...]
        sa.Column('semantic_grouping', postgresql.JSONB(), nullable=True),

        # Audit timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),

        # Primary key constraint
        sa.PrimaryKeyConstraint('id'),

        # Foreign key constraint with CASCADE delete
        sa.ForeignKeyConstraint(['user_id'], ['core_users.id'], ondelete='CASCADE'),
    )

    # Unique constraint: one overview per user per week (schema-enforced invariant)
    op.create_unique_constraint(
        'uq_pg_weekly_overview_user_week',
        'pg_weekly_overview',
        ['user_id', 'week_start']
    )

    # Add updated_at trigger for pg_weekly_overview
    op.execute("""
        CREATE TRIGGER trg_pg_weekly_overview_updated_at
        BEFORE UPDATE ON pg_weekly_overview
        FOR EACH ROW
        EXECUTE FUNCTION pg_set_updated_at();
    """)


def downgrade() -> None:
    # Drop trigger first
    op.execute("DROP TRIGGER IF EXISTS trg_pg_weekly_overview_updated_at ON pg_weekly_overview")

    # Drop pg_weekly_overview table
    op.drop_table('pg_weekly_overview')

    # Drop pg_weekly_snapshots table (indexes and constraints dropped automatically)
    op.drop_table('pg_weekly_snapshots')
