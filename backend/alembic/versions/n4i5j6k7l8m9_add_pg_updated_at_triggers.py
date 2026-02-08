"""
Add updated_at triggers to pg_priorities and pg_deliverables.

Revision ID: n4i5j6k7l8m9
Revises: m3h4i5j6k7l8
Create Date: 2026-02-08

Adds database-level triggers to ensure updated_at stays accurate even when
Celery jobs, admin scripts, or raw SQL updates bypass the ORM.

The SQLAlchemy onupdate=func.now() in the model stays as-is — belt and suspenders.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'n4i5j6k7l8m9'
down_revision: Union[str, Sequence[str], None] = 'm3h4i5j6k7l8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create PG-namespaced trigger function for updated_at auto-update
    # Using pg_ prefix to avoid conflicts with other apps sharing this database
    op.execute("""
        CREATE OR REPLACE FUNCTION pg_set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Attach trigger to pg_priorities
    op.execute("""
        CREATE TRIGGER trg_pg_priorities_updated_at
        BEFORE UPDATE ON pg_priorities
        FOR EACH ROW
        EXECUTE FUNCTION pg_set_updated_at();
    """)

    # Attach trigger to pg_deliverables
    op.execute("""
        CREATE TRIGGER trg_pg_deliverables_updated_at
        BEFORE UPDATE ON pg_deliverables
        FOR EACH ROW
        EXECUTE FUNCTION pg_set_updated_at();
    """)


def downgrade() -> None:
    # Drop triggers before dropping function
    op.execute("DROP TRIGGER IF EXISTS trg_pg_priorities_updated_at ON pg_priorities")
    op.execute("DROP TRIGGER IF EXISTS trg_pg_deliverables_updated_at ON pg_deliverables")

    # Drop the PG-namespaced function
    op.execute("DROP FUNCTION IF EXISTS pg_set_updated_at()")
