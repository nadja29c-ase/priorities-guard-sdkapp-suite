"""fix_encrypted_access_token_check_constraint

Revision ID: 6f3c4d2a1b5e
Revises: 555dacfe071b
Create Date: 2025-11-22 16:15:00.000000

Fix ck_encrypted_access_token_not_empty check constraint to allow NULL values
for oauth_provider connections while still preventing empty strings.

The original constraint was:
    length(encrypted_access_token) > 0

This fails when encrypted_access_token is NULL because length(NULL) is NULL,
and NULL > 0 evaluates to false, causing INSERT failures for oauth_provider records.

The fixed constraint is:
    (encrypted_access_token IS NULL) OR (length(encrypted_access_token) > 0)

This allows NULL (for oauth_provider) while still preventing empty strings for
actual OAuth connections (Google, Apple).

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6f3c4d2a1b5e'
down_revision: Union[str, Sequence[str], None] = '555dacfe071b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fix check constraint to allow NULL values."""

    # Drop old constraint (doesn't allow NULL)
    op.drop_constraint('ck_encrypted_access_token_not_empty', 'core_connections', type_='check')

    # Add new constraint (allows NULL, prevents empty string)
    op.create_check_constraint(
        'ck_encrypted_access_token_not_empty',
        'core_connections',
        '(encrypted_access_token IS NULL) OR (length(encrypted_access_token) > 0)'
    )


def downgrade() -> None:
    """Restore original constraint (will fail if oauth_provider rows exist with NULL)."""

    # Drop fixed constraint
    op.drop_constraint('ck_encrypted_access_token_not_empty', 'core_connections', type_='check')

    # Restore original constraint (WARNING: will fail if any rows have NULL)
    op.create_check_constraint(
        'ck_encrypted_access_token_not_empty',
        'core_connections',
        'length(encrypted_access_token) > 0'
    )
