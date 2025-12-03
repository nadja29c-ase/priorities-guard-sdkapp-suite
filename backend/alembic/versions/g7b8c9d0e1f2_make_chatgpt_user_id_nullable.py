"""make_chatgpt_user_id_nullable

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2025-12-03

Make chatgpt_user_id nullable to support anonymous OAuth flows.

When ChatGPT connects to the MCP server without providing login_hint,
we create an anonymous user with chatgpt_user_id=NULL. This allows
the OAuth flow to proceed without requiring user identification upfront.

Changes to core_users:
- chatgpt_user_id: NOT NULL -> NULLABLE
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'g7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make chatgpt_user_id nullable to support anonymous users
    op.alter_column(
        'core_users',
        'chatgpt_user_id',
        existing_type=sa.String(64),
        nullable=True,
        comment='ChatGPT user ID from login_hint parameter (NULL for anonymous users)'
    )


def downgrade() -> None:
    # Revert to NOT NULL (will fail if NULL values exist)
    op.alter_column(
        'core_users',
        'chatgpt_user_id',
        existing_type=sa.String(64),
        nullable=False,
        comment='ChatGPT user ID from login_hint parameter (pseudonymous, for OAuth user lookup)'
    )
