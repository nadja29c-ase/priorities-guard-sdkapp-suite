"""add_content_hash_column

Revision ID: k1f2g3h4i5j6
Revises: j0e1f2g3h4i5
Create Date: 2025-12-17

Increment 12: Add content_hash column for board integrity.

The content_hash stores a SHA256 hash of the canonical board content.
Used for backend integrity, auditing, and LLM reasoning.
The UI does NOT use this value for persistent saved-state detection.

- Type: VARCHAR(64) for full SHA256 hex string
- Nullable: true (existing rows won't have it, computed on next save)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'k1f2g3h4i5j6'
down_revision: Union[str, Sequence[str], None] = 'j0e1f2g3h4i5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add content_hash column for backend integrity
    op.add_column(
        'clarity_clusters',
        sa.Column(
            'content_hash',
            sa.String(64),
            nullable=True,
            comment='SHA256 hash of canonical board content for backend integrity'
        )
    )


def downgrade() -> None:
    op.drop_column('clarity_clusters', 'content_hash')
