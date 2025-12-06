"""Drop redundant unique constraint on oauth_sessions.session_token

Revision ID: efcc28230f55
Revises: 75ec3b173dce
Create Date: 2025-12-06

Originally, Increment 19 migration accidentally created TWO unique constraints:
1. oauth_sessions_session_token_key  (implicit table-level UniqueConstraint)
2. idx_oauth_sessions_session_token  (explicit unique index)

The model and codebase expect ONLY the named unique index.
This migration removes the redundant constraint IF it exists.

Note: The constraint only exists in environments where the table was created
before the first migration was corrected. Fresh deployments won't have it.
"""

from alembic import op
from sqlalchemy import text


# revision identifiers
revision = "efcc28230f55"
down_revision = "75ec3b173dce"


def upgrade():
    """
    Remove the redundant unique constraint IF it exists.
    DO NOT drop the named unique index (idx_oauth_sessions_session_token).
    """
    conn = op.get_bind()

    # Check if constraint exists before trying to drop it
    result = conn.execute(
        text("""
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'oauth_sessions_session_token_key'
        """)
    ).fetchone()

    if result:
        op.drop_constraint(
            "oauth_sessions_session_token_key",
            "oauth_sessions",
            type_="unique",
        )


def downgrade():
    """
    Restore the unique constraint if the migration is rolled back.
    """
    op.create_unique_constraint(
        "oauth_sessions_session_token_key",
        "oauth_sessions",
        ["session_token"],
    )
