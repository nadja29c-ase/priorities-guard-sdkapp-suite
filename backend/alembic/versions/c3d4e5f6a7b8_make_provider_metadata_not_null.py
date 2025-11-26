"""make_provider_metadata_not_null

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2025-11-26

Make provider_metadata NOT NULL with default '{}'.
Eliminates null checks throughout codebase.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Set existing NULLs to '{}' and add NOT NULL constraint."""
    # Step 1: Update existing NULL values to empty JSON object
    op.execute(
        "UPDATE core_connections SET provider_metadata = '{}' WHERE provider_metadata IS NULL"
    )

    # Step 2: Add NOT NULL constraint with default
    op.alter_column(
        'core_connections',
        'provider_metadata',
        existing_type=postgresql.JSON(),
        nullable=False,
        server_default=text("'{}'::jsonb")
    )


def downgrade() -> None:
    """Remove NOT NULL constraint from provider_metadata."""
    op.alter_column(
        'core_connections',
        'provider_metadata',
        existing_type=postgresql.JSON(),
        nullable=True,
        server_default=None
    )
