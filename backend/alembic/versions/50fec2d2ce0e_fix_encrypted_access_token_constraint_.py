"""fix_encrypted_access_token_constraint_for_oauth_provider

Revision ID: 50fec2d2ce0e
Revises: e05fa5515893
Create Date: 2025-11-24 10:50:05.607382

Fix CHECK constraint on encrypted_access_token to be conditional.

Problem:
- core_connections now serves dual purpose:
  1. Outbound OAuth (google, apple) - needs encrypted_access_token
  2. Inbound OAuth Provider (ChatGPT) - uses client_secret_enc instead

- Old constraint required encrypted_access_token to be non-empty for ALL rows
- This breaks oauth_provider connections which don't use that field

Solution:
- Drop old constraint
- Add conditional constraint:
  * For non-oauth_provider: encrypted_access_token must be non-empty
  * For oauth_provider: encrypted_access_token can be NULL or empty
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '50fec2d2ce0e'
down_revision: Union[str, Sequence[str], None] = 'e05fa5515893'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Fix encrypted_access_token constraint to be conditional on connection_type.
    """
    # Drop old constraint that assumes all rows need encrypted_access_token
    op.drop_constraint(
        'ck_encrypted_access_token_not_empty',
        'core_connections',
        type_='check'
    )

    # Add new conditional constraint:
    # - oauth_provider connections: can have NULL or empty encrypted_access_token
    # - all other connections: must have non-empty encrypted_access_token
    op.create_check_constraint(
        'ck_encrypted_access_token_conditional',
        'core_connections',
        "(connection_type = 'oauth_provider') OR (length(encrypted_access_token) > 0)"
    )


def downgrade() -> None:
    """
    Restore original constraint (WARNING: will break oauth_provider connections).
    """
    # Drop conditional constraint
    op.drop_constraint(
        'ck_encrypted_access_token_conditional',
        'core_connections',
        type_='check'
    )

    # Restore original constraint (incompatible with oauth_provider!)
    op.create_check_constraint(
        'ck_encrypted_access_token_not_empty',
        'core_connections',
        "length(encrypted_access_token) > 0"
    )
