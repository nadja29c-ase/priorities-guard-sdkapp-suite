"""
Rename trigger function to pg_set_updated_at for namespace isolation.

Revision ID: o5j6k7l8m9n0
Revises: n4i5j6k7l8m9
Create Date: 2026-02-08

Renames set_updated_at() to pg_set_updated_at() to avoid conflicts with
other apps sharing this database. The pg_ prefix follows the same convention
as the pg_priorities and pg_deliverables tables.

NOTE: This migration is conditional. If the previous migration (n4i5j6k7l8m9)
already created pg_set_updated_at() directly (fresh deployments), this is a no-op.
Only databases that had the old set_updated_at() function need the rename.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'o5j6k7l8m9n0'
down_revision: Union[str, Sequence[str], None] = 'n4i5j6k7l8m9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if the old function name exists (only on databases that had the original migration)
    conn = op.get_bind()
    result = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_proc
            WHERE proname = 'set_updated_at'
        )
    """))
    old_function_exists = result.scalar()

    if old_function_exists:
        # Rename the trigger function for namespace isolation
        op.execute("ALTER FUNCTION set_updated_at() RENAME TO pg_set_updated_at")

        # Update triggers to use the renamed function
        # Must drop and recreate since PostgreSQL doesn't support ALTER TRIGGER ... SET FUNCTION
        op.execute("DROP TRIGGER IF EXISTS trg_pg_priorities_updated_at ON pg_priorities")
        op.execute("DROP TRIGGER IF EXISTS trg_pg_deliverables_updated_at ON pg_deliverables")

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
    # else: pg_set_updated_at() already exists from fresh migration, no action needed


def downgrade() -> None:
    # Check if pg_set_updated_at exists (it should on any database that ran upgrade)
    conn = op.get_bind()
    result = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1 FROM pg_proc
            WHERE proname = 'pg_set_updated_at'
        )
    """))
    new_function_exists = result.scalar()

    if new_function_exists:
        # Revert trigger function name
        op.execute("ALTER FUNCTION pg_set_updated_at() RENAME TO set_updated_at")

        # Recreate triggers with original function name
        op.execute("DROP TRIGGER IF EXISTS trg_pg_priorities_updated_at ON pg_priorities")
        op.execute("DROP TRIGGER IF EXISTS trg_pg_deliverables_updated_at ON pg_deliverables")

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
