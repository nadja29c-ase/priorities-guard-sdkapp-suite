"""optimize_state_field_to_string_128

Revision ID: f3661795e097
Revises: 079b2ef29616
Create Date: 2025-11-22 10:08:17.045221

Optimize state fields to String(128) instead of Text/String(255):
- oauth_authorization_codes.state: String(255) → String(128)
- oauth_state.state: Text → String(128)

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3661795e097'
down_revision: Union[str, Sequence[str], None] = '079b2ef29616'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1. Change oauth_authorization_codes.state from String(255) to String(128)
    op.alter_column('oauth_authorization_codes', 'state',
                    existing_type=sa.String(length=255),
                    type_=sa.String(length=128),
                    existing_nullable=True)

    # 2. Change oauth_state.state from Text to String(128)
    op.alter_column('oauth_state', 'state',
                    existing_type=sa.Text(),
                    type_=sa.String(length=128),
                    existing_nullable=False)


def downgrade() -> None:
    """Downgrade schema."""

    # 1. Change oauth_state.state back from String(128) to Text
    op.alter_column('oauth_state', 'state',
                    existing_type=sa.String(length=128),
                    type_=sa.Text(),
                    existing_nullable=False)

    # 2. Change oauth_authorization_codes.state back from String(128) to String(255)
    op.alter_column('oauth_authorization_codes', 'state',
                    existing_type=sa.String(length=128),
                    type_=sa.String(length=255),
                    existing_nullable=True)
