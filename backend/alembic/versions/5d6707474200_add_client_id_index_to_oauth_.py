"""add_client_id_index_to_oauth_authorization_codes

Revision ID: 5d6707474200
Revises: 50fec2d2ce0e
Create Date: 2025-11-24 11:00:34.783837

Add client_id indexes to oauth_authorization_codes and oauth_access_tokens tables.

Purpose:
- Enables efficient client-scoped cleanup queries
- Supports per-client rate limiting and monitoring
- Optimizes analytics queries (GROUP BY client_id)
- Improves debugging/admin tools performance

Without these indexes, queries filtered by client_id require full table scans.
With these indexes, client-filtered queries become O(log n) indexed lookups.

Example queries that benefit:

oauth_authorization_codes:
- DELETE FROM oauth_authorization_codes WHERE client_id = :id AND expires_at < now();
- SELECT COUNT(*) FROM oauth_authorization_codes WHERE client_id = :id AND used = false;
- SELECT client_id, COUNT(*) FROM oauth_authorization_codes GROUP BY client_id;

oauth_access_tokens:
- SELECT COUNT(*) FROM oauth_access_tokens WHERE client_id = :id AND revoked = false;
- DELETE FROM oauth_access_tokens WHERE client_id = :id AND expires_at < now();
- SELECT client_id, COUNT(*) FROM oauth_access_tokens GROUP BY client_id;
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5d6707474200'
down_revision: Union[str, Sequence[str], None] = '50fec2d2ce0e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add client_id indexes to oauth_authorization_codes and oauth_access_tokens tables.
    """
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
    """
    Remove client_id indexes from oauth_authorization_codes and oauth_access_tokens tables.
    """
    # Drop client_id index from oauth_access_tokens
    op.drop_index(
        'idx_oauth_access_tokens_client_id',
        table_name='oauth_access_tokens'
    )

    # Drop client_id index from oauth_authorization_codes
    op.drop_index(
        'idx_oauth_authorization_codes_client_id',
        table_name='oauth_authorization_codes'
    )
