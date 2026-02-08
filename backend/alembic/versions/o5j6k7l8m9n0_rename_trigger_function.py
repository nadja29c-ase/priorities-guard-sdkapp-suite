"""
Rename trigger function to pg_set_updated_at for namespace isolation.

Revision ID: o5j6k7l8m9n0
Revises: n4i5j6k7l8m9
Create Date: 2026-02-08

Renames set_updated_at() to pg_set_updated_at() to avoid conflicts with
other apps sharing this database. The pg_ prefix follows the same convention
as the pg_priorities and pg_deliverables tables.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'o5j6k7l8m9n0'
down_revision: Union[str, Sequence[str], None] = 'n4i5j6k7l8m9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename the trigger function for namespace isolation
    op.execute("ALTER FUNCTION set_updated_at() RENAME TO pg_set_updated_at")

    # Update triggers to use the renamed function
    # Must drop and recreate since PostgreSQL doesn't support ALTER TRIGGER ... SET FUNCTION
    op.execute("DROP TRIGGER trg_pg_priorities_updated_at ON pg_priorities")
    op.execute("DROP TRIGGER trg_pg_deliverables_updated_at ON pg_deliverables")

    op.execute("""
        CREATE TRIGGER trg_pg_priorities_updated_at
        BEFORE UPDATE ON pg_priorities
        FOR EACH ROW
        EXECUTE FUNCTION pg_set_updated_at();
    """)

    op.execute("""
        CREATE TRIGGER trg_pg_deliverables_updated_at
        BEFORE UPDATE ON pg_deliverables
        FOR EACH ROW
        EXECUTE FUNCTION pg_set_updated_at();
    """)


def downgrade() -> None:
    # Revert trigger function name
    op.execute("ALTER FUNCTION pg_set_updated_at() RENAME TO set_updated_at")

    # Recreate triggers with original function name
    op.execute("DROP TRIGGER trg_pg_priorities_updated_at ON pg_priorities")
    op.execute("DROP TRIGGER trg_pg_deliverables_updated_at ON pg_deliverables")

    op.execute("""
        CREATE TRIGGER trg_pg_priorities_updated_at
        BEFORE UPDATE ON pg_priorities
        FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();
    """)

    op.execute("""
        CREATE TRIGGER trg_pg_deliverables_updated_at
        BEFORE UPDATE ON pg_deliverables
        FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();
    """)
