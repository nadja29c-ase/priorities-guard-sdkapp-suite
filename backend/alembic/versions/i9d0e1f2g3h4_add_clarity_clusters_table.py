"""add_clarity_clusters_table

Revision ID: i9d0e1f2g3h4
Revises: h8c9d0e1f2g3
Create Date: 2025-12-14

Increment 05: Add clarity_clusters table for Clarity MCP persistence.

Simple append-only table storing cluster snapshots from cluster_raw_thoughts tool.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'i9d0e1f2g3h4'
down_revision: Union[str, Sequence[str], None] = 'h8c9d0e1f2g3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure pgcrypto extension exists for gen_random_uuid()
    # (Built-in on PostgreSQL 13+, but harmless to ensure for older versions)
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # Create clarity_clusters table
    op.create_table(
        'clarity_clusters',
        sa.Column(
            'id',
            postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'),
            nullable=False,
            comment='Internal identifier',
        ),
        sa.Column(
            'user_id',
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment='Owner user ID',
        ),
        sa.Column(
            'cluster_data',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment='Logical cluster data: {clusters: [...]}',
        ),
        sa.Column(
            'thoughts_exhausted',
            sa.Boolean(),
            nullable=False,
            comment='Whether user confirmed all thoughts were captured',
        ),
        sa.Column(
            'correctly_clustered',
            sa.Boolean(),
            nullable=True,
            comment='User confirmation of cluster accuracy (null before confirmation)',
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
            comment='When cluster was created',
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
            comment='When cluster was last updated',
        ),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['core_users.id'],
            name='fk_clarity_clusters_user_id',
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
    )

    # Create index for user's clusters ordered by creation time (most recent first)
    # Using raw SQL for reliable DESC index creation across PostgreSQL versions
    op.execute(
        "CREATE INDEX idx_clarity_clusters_user_created "
        "ON clarity_clusters (user_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_clarity_clusters_user_created")
    op.drop_table('clarity_clusters')
