"""increment_20a_enum_additions

Revision ID: a1b2c3d4e5f6
Revises: efcc28230f55
Create Date: 2025-12-07

Increment 20 Part A: Add new ENUM values for activation scheduler.

This migration MUST run separately before the main schema changes because
PostgreSQL doesn't allow using new enum values in the same transaction
they were added.

We use a separate sync connection with AUTOCOMMIT isolation level to
commit the enum changes immediately, then close that connection.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import create_engine, text

from backend.core.config import settings


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'efcc28230f55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add new enum values using a separate AUTOCOMMIT connection.

    PostgreSQL requires enum additions to be committed before they can be
    used in the same session. We create a separate sync connection with
    AUTOCOMMIT isolation to ensure each ADD VALUE commits immediately.
    """
    # Create a separate sync connection with AUTOCOMMIT isolation
    # This bypasses Alembic's transaction management
    sync_url = settings.DATABASE_URL.replace(
        "postgresql+asyncpg://", "postgresql://"
    )
    engine = create_engine(sync_url, isolation_level="AUTOCOMMIT")

    with engine.connect() as conn:
        # job_type_enum additions
        conn.execute(text("ALTER TYPE job_type_enum ADD VALUE IF NOT EXISTS 'activation'"))

        # job_status_enum additions
        conn.execute(text("ALTER TYPE job_status_enum ADD VALUE IF NOT EXISTS 'running'"))
        conn.execute(text("ALTER TYPE job_status_enum ADD VALUE IF NOT EXISTS 'pending_notification'"))
        conn.execute(text("ALTER TYPE job_status_enum ADD VALUE IF NOT EXISTS 'pending_confirmation'"))
        conn.execute(text("ALTER TYPE job_status_enum ADD VALUE IF NOT EXISTS 'skipped'"))

    engine.dispose()


def downgrade() -> None:
    """
    PostgreSQL does not support removing values from ENUMs.
    The extra enum values will remain but are harmless.
    """
    pass
