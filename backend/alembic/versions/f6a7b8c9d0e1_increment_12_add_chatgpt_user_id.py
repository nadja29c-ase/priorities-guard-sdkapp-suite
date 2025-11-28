"""increment_12_add_chatgpt_user_id

Revision ID: f6a7b8c9d0e1
Revises: d4e5f6a7b8c9, e5f6a7b8c9d0
Create Date: 2025-11-28

Increment 12: OAuth Consent UI Support.

This migration merges two parallel heads:
- d4e5f6a7b8c9 (provider_client_unique_constraint)
- e5f6a7b8c9d0 (increment_11_focus_mode_support)

Add chatgpt_user_id column to core_users table.
This column stores the ChatGPT user ID from the login_hint OAuth parameter,
enabling user lookup/creation during OAuth authorization flow.

Changes to core_users:
- Add chatgpt_user_id: String(64), nullable, unique, indexed
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = ('d4e5f6a7b8c9', 'e5f6a7b8c9d0')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add chatgpt_user_id column to core_users
    op.add_column(
        'core_users',
        sa.Column(
            'chatgpt_user_id',
            sa.String(64),
            nullable=True,
            comment='ChatGPT user ID from login_hint parameter (pseudonymous, for OAuth user lookup)'
        )
    )

    # Create unique index for chatgpt_user_id lookups
    op.create_index(
        'ix_core_users_chatgpt_user_id',
        'core_users',
        ['chatgpt_user_id'],
        unique=True
    )


def downgrade() -> None:
    # Drop the index first
    op.drop_index('ix_core_users_chatgpt_user_id', table_name='core_users')

    # Drop the column
    op.drop_column('core_users', 'chatgpt_user_id')
