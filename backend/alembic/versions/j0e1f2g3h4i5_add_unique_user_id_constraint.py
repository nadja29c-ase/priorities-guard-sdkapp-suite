"""add_unique_user_id_constraint

Revision ID: j0e1f2g3h4i5
Revises: i9d0e1f2g3h4
Create Date: 2025-12-16

Increment 10: Add UNIQUE constraint on user_id to enforce single-row-per-user.

This enables true upsert semantics and prevents race conditions where
concurrent POSTs could create multiple rows for the same user.

MIGRATION SAFETY:
    Before adding the constraint, this migration deletes any duplicate rows
    (keeping only the most recent per user). This handles cases where the
    race condition already occurred before this fix.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'j0e1f2g3h4i5'
down_revision: Union[str, Sequence[str], None] = 'i9d0e1f2g3h4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: Delete duplicate rows, keeping only the most recent per user
    # This handles any existing data from before the race condition fix
    op.execute("""
        DELETE FROM clarity_clusters
        WHERE id NOT IN (
            SELECT DISTINCT ON (user_id) id
            FROM clarity_clusters
            ORDER BY user_id, created_at DESC
        )
    """)

    # Step 2: Add UNIQUE constraint on user_id
    # This enforces single-row-per-user at the database level
    op.create_unique_constraint(
        'uq_clarity_clusters_user_id',
        'clarity_clusters',
        ['user_id']
    )


def downgrade() -> None:
    op.drop_constraint('uq_clarity_clusters_user_id', 'clarity_clusters', type_='unique')
