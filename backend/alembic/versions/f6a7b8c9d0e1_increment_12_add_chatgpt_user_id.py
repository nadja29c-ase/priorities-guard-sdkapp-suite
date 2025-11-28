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
- Add chatgpt_user_id: String(64), NOT NULL, unique, indexed

Invariant: Every CoreUser is created through OAuth login_hint, so chatgpt_user_id
is always required. This constraint prevents orphan users with NULL identifiers.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = ('d4e5f6a7b8c9', 'e5f6a7b8c9d0')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# This migration merges two heads: d4e5f6a7b8c9 and e5f6a7b8c9d0
# It does not modify either branch besides adding new schema changes.


def upgrade() -> None:
    # NOTE: This migration assumes core_users is empty at this point.
    # If running on a database with existing rows, this will fail unless backfilled.
    #
    # Add chatgpt_user_id column to core_users (NOT NULL - all users created via OAuth login_hint)
    op.add_column(
        'core_users',
        sa.Column(
            'chatgpt_user_id',
            sa.String(64),
            nullable=False,
            comment='ChatGPT user ID from login_hint parameter (pseudonymous, for OAuth user lookup)'
        )
    )

    # Create unique constraint (explicit name for clarity, matches model's unique=True)
    op.create_unique_constraint(
        'uq_core_users_chatgpt_user_id',
        'core_users',
        ['chatgpt_user_id']
    )

    # Create index for chatgpt_user_id lookups (separate from unique constraint)
    op.create_index(
        'ix_core_users_chatgpt_user_id',
        'core_users',
        ['chatgpt_user_id']
    )


def downgrade() -> None:
    # Drop the index first
    op.drop_index('ix_core_users_chatgpt_user_id', table_name='core_users')

    # Drop the unique constraint
    op.drop_constraint('uq_core_users_chatgpt_user_id', 'core_users', type_='unique')

    # Drop the column
    op.drop_column('core_users', 'chatgpt_user_id')
