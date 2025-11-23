"""add_client_id_indices_to_oauth_tables

Revision ID: 2ab26a1bd81b
Revises: d0aca8881c7e
Create Date: 2025-11-22 10:01:14.606183

Add client_id indices to oauth_authorization_codes and oauth_access_tokens
for improved query performance on client-based lookups.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2ab26a1bd81b'
down_revision: Union[str, Sequence[str], None] = 'd0aca8881c7e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add client_id index to oauth_authorization_codes
    op.create_index(
        'idx_oauth_authorization_codes_client_id',
        'oauth_authorization_codes',
        ['client_id'],
        unique=False
    )

    # Add client_id index to oauth_access_tokens
    op.create_index(
        'idx_oauth_access_tokens_client_id',
        'oauth_access_tokens',
        ['client_id'],
        unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop client_id indices
    op.drop_index('idx_oauth_access_tokens_client_id', table_name='oauth_access_tokens')
    op.drop_index('idx_oauth_authorization_codes_client_id', table_name='oauth_authorization_codes')
