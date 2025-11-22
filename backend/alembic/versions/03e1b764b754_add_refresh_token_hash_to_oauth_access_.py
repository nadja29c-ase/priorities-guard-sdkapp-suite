"""add_refresh_token_hash_to_oauth_access_tokens

Revision ID: 03e1b764b754
Revises: f3661795e097
Create Date: 2025-11-22 10:15:00.000000

Add refresh_token_hash column to oauth_access_tokens for O(1) refresh token lookups.

This fixes the critical scalability issue where refresh token validation required
O(N) table scan with N decryptions. With this indexed hash column, lookups are O(1).

Security:
- Hash computed using HMAC-SHA256 with ENCRYPTION_KEY as secret
- Hash is deterministic (same token = same hash)
- Hash is safe to store unencrypted (one-way function)
- Index enables fast lookups without decrypting all tokens

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '03e1b764b754'
down_revision: Union[str, Sequence[str], None] = 'f3661795e097'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add refresh_token_hash column with index."""

    # Add refresh_token_hash column (nullable initially for existing rows)
    op.add_column('oauth_access_tokens',
        sa.Column('refresh_token_hash', sa.String(length=64), nullable=True,
                  comment='HMAC-SHA256 hash of refresh token (for fast lookups without decryption)'))

    # Create index for O(1) lookups
    op.create_index(
        'idx_oauth_access_tokens_refresh_token_hash',
        'oauth_access_tokens',
        ['refresh_token_hash'],
        unique=False
    )

    # Add CHECK constraint to ensure both columns are NULL or both are NOT NULL
    op.create_check_constraint(
        'ck_refresh_token_consistency',
        'oauth_access_tokens',
        "(refresh_token_enc IS NULL AND refresh_token_hash IS NULL) OR "
        "(refresh_token_enc IS NOT NULL AND refresh_token_hash IS NOT NULL)"
    )


def downgrade() -> None:
    """Remove refresh_token_hash column and index."""

    # Drop CHECK constraint first
    op.drop_constraint(
        'ck_refresh_token_consistency',
        'oauth_access_tokens',
        type_='check'
    )

    # Drop index
    op.drop_index('idx_oauth_access_tokens_refresh_token_hash',
                  table_name='oauth_access_tokens')

    # Drop column
    op.drop_column('oauth_access_tokens', 'refresh_token_hash')
