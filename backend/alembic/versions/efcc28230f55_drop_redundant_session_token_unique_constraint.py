"""Drop redundant unique constraint on oauth_sessions.session_token

Revision ID: efcc28230f55
Revises: 75ec3b173dce
Create Date: 2025-12-06

Originally, Increment 19 migration accidentally created TWO unique constraints:
1. oauth_sessions_session_token_key  (implicit table-level UniqueConstraint)
2. idx_oauth_sessions_session_token  (explicit unique index)

The model and codebase expect ONLY the named unique index.
This migration removes the redundant constraint.
"""

from typing import Sequence, Union
from alembic import op


# revision identifiers
revision: str = "efcc28230f55"
down_revision: Union[str, Sequence[str], None] = "75ec3b173dce"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Remove the redundant unique constraint created by the original migration.
    DO NOT drop the named unique index (idx_oauth_sessions_session_token).
    """
    # Constraint name is created automatically by Postgres:
    # oauth_sessions_session_token_key
    op.drop_constraint(
        "oauth_sessions_session_token_key",
        "oauth_sessions",
        type_="unique",
    )


def downgrade() -> None:
    """
    Restore the unique constraint if the migration is rolled back.
    """
    op.create_unique_constraint(
        "oauth_sessions_session_token_key",
        "oauth_sessions",
        ["session_token"],
    )
