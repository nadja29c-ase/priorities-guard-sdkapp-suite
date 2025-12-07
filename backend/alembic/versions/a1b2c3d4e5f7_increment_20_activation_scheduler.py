"""increment_20b_activation_scheduler

Revision ID: a1b2c3d4e5f7
Revises: a1b2c3d4e5f6
Create Date: 2025-12-07

Increment 20 Part B: Focus Block Activation Scheduler schema changes.

This migration depends on increment_20a which adds the enum values.
The enum values MUST be committed in a separate transaction before
this migration can reference them in partial indexes.

Changes:
1. Add columns to focused_scheduled_jobs:
   - event_id (FK to focused_focus_sessions)
   - event_start_time (for idempotency)
   - shortcut_url (generated URL for notification)
   - error_reason (failure details)
2. Add unique constraint for activation job idempotency
3. Create focused_consent_preferences table
4. Fix FocusedFocusSession uniqueness constraint for recurring events:
   - Drop old constraint on (user_id, google_event_id, google_calendar_id)
   - Add new constraint on (user_id, google_ical_uid, start_time)
   - Add index on google_event_id for lookups
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add activation scheduler schema changes.

    NOTE: Enum values were added in the previous migration (a1b2c3d4e5f6).
    """
    # =========================================================================
    # 1. Add columns to focused_scheduled_jobs
    # =========================================================================
    # event_id: FK to focused_focus_sessions (nullable for webhook_renewal jobs)
    op.add_column(
        'focused_scheduled_jobs',
        sa.Column(
            'event_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('focused_focus_sessions.id', ondelete='CASCADE'),
            nullable=True,
            comment='Focus session this job relates to (NULL for webhook_renewal)'
        )
    )

    # event_start_time: for idempotency (when the calendar event starts)
    op.add_column(
        'focused_scheduled_jobs',
        sa.Column(
            'event_start_time',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Calendar event start time (for idempotency constraint)'
        )
    )

    # shortcut_url: generated URL for notification delivery
    op.add_column(
        'focused_scheduled_jobs',
        sa.Column(
            'shortcut_url',
            sa.String(length=512),
            nullable=True,
            comment='Generated shortcut URL for notification'
        )
    )

    # error_reason: failure details
    op.add_column(
        'focused_scheduled_jobs',
        sa.Column(
            'error_reason',
            sa.String(length=512),
            nullable=True,
            comment='Error details if job failed'
        )
    )

    # =========================================================================
    # 4. Add unique constraint for activation job idempotency
    # =========================================================================
    # Only applies when event_id is NOT NULL (activation jobs)
    # Allows one activation job per (user, event, job_type, event_start_time)
    op.create_index(
        'idx_scheduled_jobs_event',
        'focused_scheduled_jobs',
        ['event_id'],
        postgresql_where=text("event_id IS NOT NULL")
    )

    # Unique constraint via partial unique index
    # Explicit job_type filter ensures each job type can define its own uniqueness rules
    op.execute("""
        CREATE UNIQUE INDEX uq_scheduled_jobs_activation
        ON focused_scheduled_jobs (user_id, event_id, job_type, event_start_time)
        WHERE event_id IS NOT NULL
          AND job_type = 'activation'
    """)

    # =========================================================================
    # 5. Fix FocusedFocusSession uniqueness for recurring events
    # =========================================================================
    # The old constraint (user_id, google_event_id, google_calendar_id) is WRONG
    # for recurring events - all instances share the same google_event_id.
    # Google Calendar API: iCalUID + start_time uniquely identifies an instance.

    # Drop the old incorrect constraint (idempotent - may not exist in all envs)
    op.execute("""
        ALTER TABLE focused_focus_sessions
        DROP CONSTRAINT IF EXISTS uq_focus_sessions_user_event
    """)

    # Add new correct constraint: (user_id, google_ical_uid, start_time)
    op.create_unique_constraint(
        'uq_focus_sessions_user_ical_start',
        'focused_focus_sessions',
        ['user_id', 'google_ical_uid', 'start_time']
    )

    # Add index on google_event_id for lookup queries (not uniqueness)
    op.create_index(
        'idx_focus_sessions_event_id',
        'focused_focus_sessions',
        ['google_event_id']
    )

    # =========================================================================
    # 6. Create focused_consent_preferences table
    # =========================================================================
    op.create_table(
        'focused_consent_preferences',
        # Primary key (user_id is both PK and FK)
        sa.Column(
            'user_id',
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey('core_users.id', ondelete='CASCADE'),
            primary_key=True,
            comment='User these preferences belong to'
        ),
        # auto_handle_focus_blocks: if true, send push notification automatically
        sa.Column(
            'auto_handle_focus_blocks',
            sa.Boolean(),
            server_default=text('false'),
            nullable=False,
            comment='If true, send push notification when focus block starts'
        ),
        # always_confirm_duration: if true, always ask user to confirm duration
        sa.Column(
            'always_confirm_duration',
            sa.Boolean(),
            server_default=text('true'),
            nullable=False,
            comment='If true, always ask user to confirm focus session duration'
        ),
        # Audit timestamps
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
            comment='When preferences were created'
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
            comment='When preferences were last updated'
        ),
    )


def downgrade() -> None:
    """
    Revert activation scheduler support.
    """
    # 1. Drop focused_consent_preferences table
    op.drop_table('focused_consent_preferences')

    # 2. Revert FocusedFocusSession uniqueness constraint
    op.drop_index('idx_focus_sessions_event_id', table_name='focused_focus_sessions')
    op.drop_constraint('uq_focus_sessions_user_ical_start', 'focused_focus_sessions')
    op.create_unique_constraint(
        'uq_focus_sessions_user_event',
        'focused_focus_sessions',
        ['user_id', 'google_event_id', 'google_calendar_id']
    )

    # 3. Drop unique index and event index for scheduled jobs
    op.execute("DROP INDEX IF EXISTS uq_scheduled_jobs_activation")
    op.drop_index('idx_scheduled_jobs_event', table_name='focused_scheduled_jobs')

    # 4. Drop columns from focused_scheduled_jobs
    op.drop_column('focused_scheduled_jobs', 'error_reason')
    op.drop_column('focused_scheduled_jobs', 'shortcut_url')
    op.drop_column('focused_scheduled_jobs', 'event_start_time')
    op.drop_column('focused_scheduled_jobs', 'event_id')

    # 5. Note: PostgreSQL does not support removing values from ENUMs
    # The extra enum values will remain but are harmless
