"""add_refresh_token_hash_column_and_index

Revision ID: e05fa5515893
Revises: 6f3c4d2a1b5e
Create Date: 2025-11-24 10:37:38.748377

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e05fa5515893'
down_revision: Union[str, Sequence[str], None] = '6f3c4d2a1b5e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add refresh_token_hash column and index to oauth_access_tokens.

    This is a CRITICAL performance fix that changes refresh token lookup
    from O(n) full table scan with decryption to O(1) indexed hash lookup.

    Migration steps:
    1. Add refresh_token_hash column (nullable initially)
    2. Backfill existing tokens with hash values
    3. Create index on refresh_token_hash

    Performance impact:
    - Before: O(n) with n decrypt operations per refresh
    - After: O(1) with single hash + index lookup
    """
    # Step 1: Add column (nullable for existing rows)
    op.add_column(
        'oauth_access_tokens',
        sa.Column(
            'refresh_token_hash',
            sa.String(64),
            nullable=True,
            comment='SHA-256 hash of refresh token for O(1) indexed lookup'
        )
    )

    # Step 2: Backfill existing tokens
    # NOTE: Existing tokens cannot be backfilled since we don't have plaintext
    # They will need to be re-issued on next refresh
    # New tokens will have hash from creation

    # Step 3: Create index (CRITICAL for O(1) lookups)
    op.create_index(
        'idx_oauth_access_tokens_refresh_token_hash',
        'oauth_access_tokens',
        ['refresh_token_hash'],
        unique=False
    )


def downgrade() -> None:
    """
    Remove refresh_token_hash column and index.

    WARNING: This will revert to O(n) full table scan lookups!
    """
    # Drop index first
    op.drop_index(
        'idx_oauth_access_tokens_refresh_token_hash',
        table_name='oauth_access_tokens'
    )

    # Drop column
    op.drop_column('oauth_access_tokens', 'refresh_token_hash')
