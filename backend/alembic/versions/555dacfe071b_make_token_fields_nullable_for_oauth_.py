"""make_token_fields_nullable_for_oauth_provider

Revision ID: 555dacfe071b
Revises: 03e1b764b754
Create Date: 2025-11-22 10:20:00.000000

Make encrypted_access_token and token_expires_at nullable in core_connections.

These fields are only relevant for outbound OAuth connections (Google, Apple).
For oauth_provider connections (inbound OAuth), these fields don't apply and
should be NULL instead of using fake placeholder values.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '555dacfe071b'
down_revision: Union[str, Sequence[str], None] = '03e1b764b754'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Make token fields nullable."""

    # Make encrypted_access_token nullable
    op.alter_column('core_connections', 'encrypted_access_token',
                    existing_type=sa.Text(),
                    nullable=True,
                    comment='Encrypted access token (NULL for oauth_provider connections)')

    # Make token_expires_at nullable
    op.alter_column('core_connections', 'token_expires_at',
                    existing_type=sa.DateTime(timezone=True),
                    nullable=True,
                    comment='Access token expiration (NULL for oauth_provider connections)')


def downgrade() -> None:
    """Make token fields NOT NULL again."""

    # First, set placeholder values for any NULL rows (should only be oauth_provider)
    op.execute("""
        UPDATE core_connections
        SET encrypted_access_token = ''
        WHERE encrypted_access_token IS NULL
    """)

    op.execute("""
        UPDATE core_connections
        SET token_expires_at = NOW()
        WHERE token_expires_at IS NULL
    """)

    # Make encrypted_access_token NOT NULL
    op.alter_column('core_connections', 'encrypted_access_token',
                    existing_type=sa.Text(),
                    nullable=False)

    # Make token_expires_at NOT NULL
    op.alter_column('core_connections', 'token_expires_at',
                    existing_type=sa.DateTime(timezone=True),
                    nullable=False)
