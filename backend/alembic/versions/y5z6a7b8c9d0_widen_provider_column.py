"""Widen provider column to VARCHAR(200).

Revision ID: y5z6a7b8c9d0
Revises: x4y5z6a7b8c9
Create Date: 2026-03-04

The provider column was originally VARCHAR(50) which is too short for
dynamic client registration where client_name is stored as provider.
ChatGPT SDK clients may have longer names.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "y5z6a7b8c9d0"
down_revision = "x4y5z6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Widen provider column from VARCHAR(50) to VARCHAR(200)."""
    op.execute(
        "ALTER TABLE core_connections ALTER COLUMN provider TYPE VARCHAR(200)"
    )


def downgrade() -> None:
    """Revert provider column to VARCHAR(50).

    WARNING: This will fail if any existing values exceed 50 characters.
    """
    op.execute(
        "ALTER TABLE core_connections ALTER COLUMN provider TYPE VARCHAR(50)"
    )
