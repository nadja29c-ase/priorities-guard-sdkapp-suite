"""add_provider_client_unique_constraint

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2025-11-26

Add UniqueConstraint on (provider, client_id) for multi-app OAuth provider support.
Allows multiple SDK apps (Focused, Decliner, Scheduler) to register as separate
OAuth provider clients with the same provider (e.g., 'chatgpt') but different client_ids.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add unique constraint on (provider, client_id)."""
    op.create_unique_constraint(
        'uq_provider_client',
        'core_connections',
        ['provider', 'client_id']
    )


def downgrade() -> None:
    """Remove unique constraint on (provider, client_id)."""
    op.drop_constraint('uq_provider_client', 'core_connections', type_='unique')
