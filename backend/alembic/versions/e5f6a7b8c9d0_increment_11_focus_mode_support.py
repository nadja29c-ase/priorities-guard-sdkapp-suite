"""increment_11_focus_mode_support

Revision ID: e5f6a7b8c9d0
Revises: c3d4e5f6a7b8
Create Date: 2025-11-26

Increment 11 Part B: Add focus mode activation support.

Changes to focused_focus_sessions:
- Add actual_start: DateTime (when user activated focus mode)
- Add actual_end: DateTime (when user deactivated focus mode)
- Add trigger_source: Enum('calendar', 'user') - how the session was triggered
- Make google_event_id nullable (for manual sessions)
- Make google_ical_uid nullable (for manual sessions)

New table focused_scheduled_jobs:
- Tracks scheduled Celery tasks (auto-deactivation, webhook renewal, etc.)
- 7-day retention for completed/failed/cancelled jobs
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add focus mode activation support.

    1. Create ENUM types
    2. Alter focused_focus_sessions table
    3. Create focused_scheduled_jobs table
    """
    # 1. Create ENUM types via raw SQL (postgresql.ENUM with create_type=False
    # is used in column definitions to reference these pre-created types)
    op.execute("CREATE TYPE trigger_source_enum AS ENUM ('calendar', 'user')")

    # job_type_enum: types of scheduled jobs
    op.execute(
        "CREATE TYPE job_type_enum AS ENUM ('focus_deactivate', 'webhook_renewal')"
    )

    # job_status_enum: job lifecycle states
    op.execute(
        "CREATE TYPE job_status_enum AS ENUM ('pending', 'completed', 'failed', 'cancelled')"
    )

    # 2. Alter focused_focus_sessions table
    # Add actual_start column
    op.add_column(
        'focused_focus_sessions',
        sa.Column(
            'actual_start',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='When user actually activated focus mode (UTC)'
        )
    )

    # Add actual_end column
    op.add_column(
        'focused_focus_sessions',
        sa.Column(
            'actual_end',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='When user deactivated focus mode (UTC)'
        )
    )

    # Add trigger_source column
    op.add_column(
        'focused_focus_sessions',
        sa.Column(
            'trigger_source',
            postgresql.ENUM('calendar', 'user', name='trigger_source_enum', create_type=False),
            nullable=True,
            comment='How the focus session was triggered'
        )
    )

    # Make google_event_id nullable (for manual sessions)
    op.alter_column(
        'focused_focus_sessions',
        'google_event_id',
        existing_type=sa.String(length=255),
        nullable=True
    )

    # Make google_ical_uid nullable (for manual sessions)
    op.alter_column(
        'focused_focus_sessions',
        'google_ical_uid',
        existing_type=sa.String(length=255),
        nullable=True
    )

    # Add index for finding active focus sessions
    op.create_index(
        'idx_focus_sessions_active',
        'focused_focus_sessions',
        ['user_id'],
        postgresql_where=text("actual_start IS NOT NULL AND actual_end IS NULL")
    )

    # 3. Create focused_scheduled_jobs table
    op.create_table(
        'focused_scheduled_jobs',
        # Primary key
        sa.Column(
            'id',
            postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'),
            nullable=False,
            comment='Internal identifier'
        ),
        # Foreign key to core_users
        sa.Column(
            'user_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('core_users.id', ondelete='CASCADE'),
            nullable=False,
            comment='User who owns this job'
        ),
        # Job type
        sa.Column(
            'job_type',
            postgresql.ENUM('focus_deactivate', 'webhook_renewal', name='job_type_enum', create_type=False),
            nullable=False,
            comment='Type of scheduled job'
        ),
        # When the job should execute
        sa.Column(
            'scheduled_at',
            sa.DateTime(timezone=True),
            nullable=False,
            comment='When the job should execute (UTC)'
        ),
        # Job status
        sa.Column(
            'status',
            postgresql.ENUM('pending', 'completed', 'failed', 'cancelled', name='job_status_enum', create_type=False),
            server_default=text("'pending'"),
            nullable=False,
            comment='Current job status'
        ),
        # Celery task ID for tracking
        sa.Column(
            'celery_task_id',
            sa.String(length=255),
            nullable=True,
            comment='Celery task ID for this job'
        ),
        # Retry tracking
        sa.Column(
            'retry_count',
            sa.Integer(),
            server_default=text('0'),
            nullable=False,
            comment='Number of retry attempts'
        ),
        # Job-specific payload (e.g., session_id for deactivation)
        sa.Column(
            'payload',
            postgresql.JSONB(),
            server_default=text("'{}'::jsonb"),
            nullable=False,
            comment='Job-specific parameters (session_id, etc.)'
        ),
        # Audit timestamps
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
            comment='When job was created'
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
            comment='When job was last updated'
        ),
        # Primary key constraint
        sa.PrimaryKeyConstraint('id'),
    )

    # Indexes for focused_scheduled_jobs
    # Index for finding pending jobs by scheduled time
    op.create_index(
        'idx_scheduled_jobs_pending',
        'focused_scheduled_jobs',
        ['scheduled_at'],
        postgresql_where=text("status = 'pending'")
    )

    # Index for cleanup (find old completed/failed/cancelled jobs)
    op.create_index(
        'idx_scheduled_jobs_cleanup',
        'focused_scheduled_jobs',
        ['updated_at'],
        postgresql_where=text("status IN ('completed', 'failed', 'cancelled')")
    )

    # Index for user's jobs
    op.create_index(
        'idx_scheduled_jobs_user',
        'focused_scheduled_jobs',
        ['user_id', 'status']
    )


def downgrade() -> None:
    """
    Revert focus mode activation support.

    1. Drop focused_scheduled_jobs table
    2. Revert focused_focus_sessions changes
    3. Drop ENUM types
    """
    # 1. Drop focused_scheduled_jobs indexes and table
    op.drop_index('idx_scheduled_jobs_user', table_name='focused_scheduled_jobs')
    op.drop_index('idx_scheduled_jobs_cleanup', table_name='focused_scheduled_jobs')
    op.drop_index('idx_scheduled_jobs_pending', table_name='focused_scheduled_jobs')
    op.drop_table('focused_scheduled_jobs')

    # 2. Revert focused_focus_sessions changes
    # Drop new index
    op.drop_index('idx_focus_sessions_active', table_name='focused_focus_sessions')

    # Make google_ical_uid NOT NULL again
    # First update any NULLs (from manual sessions) to a placeholder
    op.execute(
        "UPDATE focused_focus_sessions SET google_ical_uid = 'manual-session' "
        "WHERE google_ical_uid IS NULL"
    )
    op.alter_column(
        'focused_focus_sessions',
        'google_ical_uid',
        existing_type=sa.String(length=255),
        nullable=False
    )

    # Make google_event_id NOT NULL again
    op.execute(
        "UPDATE focused_focus_sessions SET google_event_id = 'manual-session' "
        "WHERE google_event_id IS NULL"
    )
    op.alter_column(
        'focused_focus_sessions',
        'google_event_id',
        existing_type=sa.String(length=255),
        nullable=False
    )

    # Drop new columns
    op.drop_column('focused_focus_sessions', 'trigger_source')
    op.drop_column('focused_focus_sessions', 'actual_end')
    op.drop_column('focused_focus_sessions', 'actual_start')

    # 3. Drop ENUM types
    op.execute("DROP TYPE IF EXISTS job_status_enum")
    op.execute("DROP TYPE IF EXISTS job_type_enum")
    op.execute("DROP TYPE IF EXISTS trigger_source_enum")
