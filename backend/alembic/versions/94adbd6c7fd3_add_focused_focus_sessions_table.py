"""add focused_focus_sessions table

Revision ID: 94adbd6c7fd3
Revises: 483397ac6460
Create Date: 2025-11-18 16:12:12.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '94adbd6c7fd3'
down_revision: Union[str, Sequence[str], None] = '483397ac6460'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Upgrade schema: Create focused_focus_sessions table.

    Creates:
    1. PostgreSQL ENUM type for event status (handled by SQLAlchemy)
    2. Table with all columns
    3. All indexes (including composite and partial)
    4. All constraints (FK, unique, check)
    """
    # 1. Create table (ENUM type will be created automatically by SQLAlchemy)
    op.create_table(
        'focused_focus_sessions',
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
            sa.ForeignKey('core_users.id', ondelete='RESTRICT'),
            nullable=False,
            comment='Owner user ID'
        ),
        # Google Calendar metadata
        sa.Column(
            'google_event_id',
            sa.String(length=255),
            nullable=False,
            comment="Google's event.id"
        ),
        sa.Column(
            'google_calendar_id',
            sa.String(length=255),
            server_default=text("'primary'"),
            nullable=False,
            comment='Calendar source'
        ),
        sa.Column(
            'google_ical_uid',
            sa.String(length=255),
            nullable=False,
            comment='iCalendar UID (stable across updates, groups recurring instances)'
        ),
        sa.Column(
            'google_updated_at',
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Google's last modified timestamp (for conflict detection)"
        ),
        # Event content
        sa.Column(
            'event_summary',
            sa.Text(),
            nullable=True,
            comment='Event title (can be empty, used for keyword matching)'
        ),
        sa.Column(
            'event_description',
            sa.Text(),
            nullable=True,
            comment='Event description (temporary, max 8192 chars; deleted after 72h)'
        ),
        # Event timing (UTC only)
        sa.Column(
            'start_time',
            sa.DateTime(timezone=True),
            nullable=False,
            comment='Event start time (UTC)'
        ),
        sa.Column(
            'end_time',
            sa.DateTime(timezone=True),
            nullable=False,
            comment='Event end time (UTC)'
        ),
        # Focus block detection
        sa.Column(
            'is_focus_block',
            sa.Boolean(),
            server_default=text('false'),
            nullable=False,
            comment='Whether event matches focus keywords'
        ),
        sa.Column(
            'matched_keyword',
            sa.String(length=100),
            nullable=True,
            comment='Which keyword triggered focus block match'
        ),
        # Change detection
        sa.Column(
            'sha256_content_hash',
            sa.String(length=64),
            nullable=False,
            comment='SHA256 hash of event content for change detection'
        ),
        # Lifecycle status (PostgreSQL ENUM - will be auto-created)
        sa.Column(
            'status',
            sa.Enum('active', 'deleted', name='event_status_enum'),
            server_default=text("'active'"),
            nullable=False,
            comment='Event lifecycle state'
        ),
        # Versioning and sync tracking
        sa.Column(
            'version',
            sa.Integer(),
            server_default=text('1'),
            nullable=False,
            comment='Event version for history tracking'
        ),
        sa.Column(
            'last_synced_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Last sync from Google (manually set after successful sync, no defaults)'
        ),
        # Audit timestamps
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
            comment='First sync'
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
            comment='Last modified'
        ),
        sa.Column(
            'deleted_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='Soft delete timestamp'
        ),
        # Primary key
        sa.PrimaryKeyConstraint('id'),
        # Unique constraint: one row per (user, event, calendar)
        sa.UniqueConstraint(
            'user_id',
            'google_event_id',
            'google_calendar_id',
            name='uq_focus_sessions_user_event'
        ),
        # Check constraints
        sa.CheckConstraint(
            'start_time < end_time',
            name='ck_focus_sessions_time_order'
        ),
        sa.CheckConstraint(
            'version >= 1',
            name='ck_focus_sessions_version_positive'
        ),
        sa.CheckConstraint(
            '(event_description IS NULL) OR (length(event_description) <= 8192)',
            name='ck_focus_sessions_description_length'
        ),
        sa.CheckConstraint(
            'length(sha256_content_hash) = 64',
            name='ck_focus_sessions_hash_length'
        ),
    )

    # 3. Create indexes
    # Index: start_time for time-range queries
    op.create_index(
        'idx_focus_sessions_start_time',
        'focused_focus_sessions',
        ['start_time']
    )

    # Index: end_time for time-range queries
    op.create_index(
        'idx_focus_sessions_end_time',
        'focused_focus_sessions',
        ['end_time']
    )

    # Index: focus blocks (user_id, is_focus_block) WHERE status = 'active' (partial index)
    op.create_index(
        'idx_focus_sessions_focus_blocks',
        'focused_focus_sessions',
        ['user_id', 'is_focus_block'],
        postgresql_where=text("status = 'active'")
    )

    # Index: composite (user_id, sha256_content_hash) for change detection
    # CRITICAL: Composite index prevents cross-user scans
    op.create_index(
        'idx_focus_sessions_user_hash',
        'focused_focus_sessions',
        ['user_id', 'sha256_content_hash']
    )

    # Index: cleanup job (created_at) WHERE status = 'active' (partial index)
    op.create_index(
        'idx_focus_sessions_cleanup',
        'focused_focus_sessions',
        ['created_at'],
        postgresql_where=text("status = 'active'")
    )

    # Index: google_ical_uid for recurring event queries
    op.create_index(
        'idx_focus_sessions_ical_uid',
        'focused_focus_sessions',
        ['google_ical_uid']
    )


def downgrade() -> None:
    """
    Downgrade schema: Drop focused_focus_sessions table and ENUM type.

    Drops in reverse order:
    1. All indexes
    2. Table (ENUM type will be auto-dropped by SQLAlchemy)
    """
    # 1. Drop indexes (not strictly necessary as table drop cascades, but explicit is better)
    op.drop_index('idx_focus_sessions_ical_uid', table_name='focused_focus_sessions')
    op.drop_index('idx_focus_sessions_cleanup', table_name='focused_focus_sessions')
    op.drop_index('idx_focus_sessions_user_hash', table_name='focused_focus_sessions')
    op.drop_index('idx_focus_sessions_focus_blocks', table_name='focused_focus_sessions')
    op.drop_index('idx_focus_sessions_end_time', table_name='focused_focus_sessions')
    op.drop_index('idx_focus_sessions_start_time', table_name='focused_focus_sessions')

    # 2. Drop table (ENUM type will be dropped automatically by SQLAlchemy)
    op.drop_table('focused_focus_sessions')
