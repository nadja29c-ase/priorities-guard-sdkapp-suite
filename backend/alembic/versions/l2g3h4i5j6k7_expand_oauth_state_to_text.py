"""
Expand oauth_state.state back to Text.

The String(128) limit from migration f3661795e097 is too short for Apps SDK
state tokens, which can exceed 128 characters. This causes
StringDataRightTruncationError during OAuth flow.

Revision ID: l2g3h4i5j6k7
Revises: k1f2g3h4i5j6
Create Date: 2024-12-25
"""
from alembic import op
import sqlalchemy as sa


revision = 'l2g3h4i5j6k7'
down_revision = 'k1f2g3h4i5j6'
branch_labels = None
depends_on = None


def upgrade():
    # Expand oauth_state.state from String(128) to Text
    # Apps SDK state tokens can exceed 128 characters
    op.alter_column('oauth_state', 'state',
                    existing_type=sa.String(length=128),
                    type_=sa.Text(),
                    existing_nullable=False)

    # Also expand oauth_authorization_codes.state from String(128) to String(512)
    # for consistency (state values can be long)
    op.alter_column('oauth_authorization_codes', 'state',
                    existing_type=sa.String(length=128),
                    type_=sa.String(length=512),
                    existing_nullable=True)


def downgrade():
    # Revert oauth_authorization_codes.state to String(128)
    op.alter_column('oauth_authorization_codes', 'state',
                    existing_type=sa.String(length=512),
                    type_=sa.String(length=128),
                    existing_nullable=True)

    # Revert oauth_state.state to String(128)
    op.alter_column('oauth_state', 'state',
                    existing_type=sa.Text(),
                    type_=sa.String(length=128),
                    existing_nullable=False)
