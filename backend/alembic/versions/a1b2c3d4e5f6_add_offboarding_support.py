"""add_offboarding_support

Revision ID: a1b2c3d4e5f6
Revises: 5d6707474200
Create Date: 2025-11-26

Increment 10: User offboarding support
- Add revoked_at column to core_connections for tracking disconnection
- Create core_tool_audit_log table for GDPR compliance audit trail
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '5d6707474200'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add offboarding support."""

    # 1. Add revoked_at column to core_connections
    op.add_column(
        'core_connections',
        sa.Column(
            'revoked_at',
            sa.DateTime(timezone=True),
            nullable=True,
            comment='When the connection was revoked/disconnected'
        )
    )

    # 2. Create core_tool_audit_log table for GDPR compliance
    op.create_table(
        'core_tool_audit_log',
        sa.Column(
            'id',
            postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'),
            nullable=False,
            comment='Unique audit log entry ID'
        ),
        sa.Column(
            'user_id',
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment='User who performed or was affected by the action'
        ),
        sa.Column(
            'app_name',
            sa.String(50),
            nullable=False,
            comment='SDK app name (e.g., focused, decliner)'
        ),
        sa.Column(
            'action',
            sa.String(100),
            nullable=False,
            comment='Action performed (e.g., disconnect, delete_data)'
        ),
        sa.Column(
            'result_status',
            sa.String(20),
            nullable=False,
            comment='Result: success, failed, partial'
        ),
        sa.Column(
            'details',
            postgresql.JSON(),
            nullable=True,
            comment='Additional details (tables affected, error messages)'
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
            comment='When the action occurred'
        ),
        sa.PrimaryKeyConstraint('id'),
        comment='Audit log for user actions (GDPR compliance)'
    )

    # 3. Add indexes for audit log queries
    op.create_index(
        'idx_audit_log_user_id',
        'core_tool_audit_log',
        ['user_id']
    )
    op.create_index(
        'idx_audit_log_app_name',
        'core_tool_audit_log',
        ['app_name']
    )
    op.create_index(
        'idx_audit_log_created_at',
        'core_tool_audit_log',
        ['created_at']
    )


def downgrade() -> None:
    """Remove offboarding support."""

    # Drop audit log table and indexes
    op.drop_index('idx_audit_log_created_at', table_name='core_tool_audit_log')
    op.drop_index('idx_audit_log_app_name', table_name='core_tool_audit_log')
    op.drop_index('idx_audit_log_user_id', table_name='core_tool_audit_log')
    op.drop_table('core_tool_audit_log')

    # Remove revoked_at column
    op.drop_column('core_connections', 'revoked_at')
