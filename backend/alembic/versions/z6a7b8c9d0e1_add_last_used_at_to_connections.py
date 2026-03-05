"""Add last_used_at column and indexes to core_connections.

Revision ID: z6a7b8c9d0e1
Revises: y5z6a7b8c9d0
Create Date: 2026-03-05

GDPR Retention Enforcement (Increment 39):
- Adds last_used_at column to track real Google API usage
- Adds simple index for general queries
- Adds partial index for Task 2 (cleanup_idle_google_connections) query performance
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "z6a7b8c9d0e1"
down_revision = "y5z6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add last_used_at column with indexes."""
    # Add nullable DateTime column (no server default, no backfill)
    op.add_column(
        "core_connections",
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp of last successful Google Calendar API call. "
                    "Architectural rule: update immediately after each successful "
                    "Google API response, not on token refresh or DB-only operations."
        )
    )

    # Simple index for general last_used_at queries
    op.create_index(
        "ix_core_connections_last_used_at",
        "core_connections",
        ["last_used_at"]
    )

    # Partial index for Task 2: cleanup_idle_google_connections
    # This keeps the monthly cleanup O(log n) as the table grows
    op.execute("""
        CREATE INDEX ix_core_connections_google_active
        ON core_connections(last_used_at)
        WHERE connection_type = 'google' AND revoked_at IS NULL
    """)

    # Partial index for active connections by user
    op.execute("""
        CREATE INDEX ix_core_connections_user_active
        ON core_connections(user_id)
        WHERE revoked_at IS NULL
    """)


def downgrade() -> None:
    """Remove last_used_at column and indexes."""
    # Drop partial indexes first (schema-qualified for safety)
    op.execute("DROP INDEX IF EXISTS public.ix_core_connections_google_active")
    op.execute("DROP INDEX IF EXISTS public.ix_core_connections_user_active")

    # Drop simple index
    op.drop_index("ix_core_connections_last_used_at", table_name="core_connections")

    # Drop column
    op.drop_column("core_connections", "last_used_at")
