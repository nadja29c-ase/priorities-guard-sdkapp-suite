"""add_connection_type_check_constraint

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2025-11-26

Add CheckConstraint to restrict connection_type to valid values only.
Prevents data corruption from typos or bugs inserting invalid values.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add connection_type enum check constraint."""
    op.create_check_constraint(
        'ck_connection_type_enum',
        'core_connections',
        "connection_type IN ('google', 'apple', 'oauth_provider', 'unknown')"
    )


def downgrade() -> None:
    """Remove connection_type enum check constraint."""
    op.drop_constraint('ck_connection_type_enum', 'core_connections', type_='check')
