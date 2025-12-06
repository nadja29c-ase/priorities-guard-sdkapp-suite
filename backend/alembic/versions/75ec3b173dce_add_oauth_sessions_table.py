"""add_oauth_sessions_table

Revision ID: 75ec3b173dce
Revises: ddbd7655b93a
Create Date: 2025-12-06 13:30:33.442073

Increment 19: Cross-app user identification via OAuth sessions.
Creates the oauth_sessions table for browser session cookies.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '75ec3b173dce'
down_revision: Union[str, Sequence[str], None] = 'ddbd7655b93a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create oauth_sessions table for cross-app user identification."""
    op.create_table(
        'oauth_sessions',
        sa.Column(
            'id',
            sa.UUID(),
            server_default=sa.text('gen_random_uuid()'),
            nullable=False,
            comment='Session identifier (UUID)'
        ),
        sa.Column(
            'user_id',
            sa.UUID(),
            nullable=False,
            comment='User this session belongs to'
        ),
        sa.Column(
            'session_token',
            sa.String(length=64),
            nullable=False,
            comment='Random token stored in cookie (32 bytes hex)'
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
            comment='When session was created'
        ),
        sa.Column(
            'expires_at',
            sa.DateTime(timezone=True),
            server_default=sa.text("(now() + interval '730 days')"),
            nullable=False,
            comment='When session expires (extended on each use, 2 years of inactivity)'
        ),
        sa.ForeignKeyConstraint(['user_id'], ['core_users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        # Note: session_token uniqueness enforced by idx_oauth_sessions_session_token (unique index)
        comment='Browser sessions for cross-app user identification'
    )

    # Create indexes for efficient lookups
    op.create_index(
        'idx_oauth_sessions_session_token',
        'oauth_sessions',
        ['session_token'],
        unique=True
    )
    op.create_index(
        'idx_oauth_sessions_user_id',
        'oauth_sessions',
        ['user_id'],
        unique=False
    )
    op.create_index(
        'idx_oauth_sessions_expires_at',
        'oauth_sessions',
        ['expires_at'],
        unique=False
    )


def downgrade() -> None:
    """Drop oauth_sessions table."""
    op.drop_index('idx_oauth_sessions_expires_at', table_name='oauth_sessions')
    op.drop_index('idx_oauth_sessions_user_id', table_name='oauth_sessions')
    op.drop_index('idx_oauth_sessions_session_token', table_name='oauth_sessions')
    op.drop_table('oauth_sessions')
