"""Data minimization cleanup - GDPR Art. 5(1)(c).

Drop unused/deprecated columns across OAuth and Clarity tables:
- oauth_access_tokens.last_used_at (write-only, duplicates created_at)
- oauth_sessions.session_token (plaintext, replaced by hash+enc)
- oauth_authorization_codes.nonce (OpenID Connect field, never used)
- clarity_clusters.thoughts_exhausted (deprecated, always False)
- clarity_clusters.correctly_clustered (deprecated, always None)

Also:
- Backfill any remaining NULL session_token_hash rows
- Make session_token_hash NOT NULL
- Drop idx_oauth_sessions_session_token index

Revision ID: w3x4y5z6a7b8
Revises: v2w3x4y5z6a7
Create Date: 2026-03-03
"""

import hashlib

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "w3x4y5z6a7b8"
down_revision = "v2w3x4y5z6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # Step 1: Backfill session_token_hash for any NULL rows (Change 3 pre-condition)
    # Uses Python hashlib for consistency with v2w3x4y5z6a7 migration
    # =========================================================================
    conn = op.get_bind()

    result = conn.execute(
        text("SELECT id, session_token FROM oauth_sessions WHERE session_token_hash IS NULL")
    )
    rows = result.fetchall()

    for row in rows:
        session_id = row[0]
        session_token = row[1]
        if not session_token:
            continue

        # Compute SHA-256 hash (inline, consistent with existing migration)
        token_hash = hashlib.sha256(session_token.encode()).hexdigest()

        conn.execute(
            text("UPDATE oauth_sessions SET session_token_hash = :hash WHERE id = :id"),
            {"hash": token_hash, "id": session_id}
        )

    # Safety check: Verify no NULL session_token_hash rows remain
    # This prevents a cryptic PostgreSQL constraint error when applying NOT NULL
    result = conn.execute(
        text("SELECT COUNT(*) FROM oauth_sessions WHERE session_token_hash IS NULL")
    )
    null_count = result.scalar()
    if null_count > 0:
        raise RuntimeError(
            f"Backfill incomplete: session_token_hash is still NULL for {null_count} row(s). "
            "Cannot proceed with NOT NULL constraint."
        )

    # =========================================================================
    # Step 2: Drop last_used_at from oauth_access_tokens (Change 2)
    # =========================================================================
    op.drop_column("oauth_access_tokens", "last_used_at")

    # =========================================================================
    # Step 3: Drop session_token from oauth_sessions (Change 3)
    # =========================================================================
    # Drop index first
    op.drop_index("idx_oauth_sessions_session_token", table_name="oauth_sessions")

    # Drop column
    op.drop_column("oauth_sessions", "session_token")

    # Make session_token_hash NOT NULL (now that backfill is done and column is dropped)
    op.alter_column(
        "oauth_sessions",
        "session_token_hash",
        existing_type=sa.String(64),
        nullable=False
    )

    # =========================================================================
    # Step 4: Drop nonce from oauth_authorization_codes (Change 5)
    # =========================================================================
    op.drop_column("oauth_authorization_codes", "nonce")

    # =========================================================================
    # Step 5: Drop deprecated Clarity columns (Change 4)
    # =========================================================================
    op.drop_column("clarity_clusters", "thoughts_exhausted")
    op.drop_column("clarity_clusters", "correctly_clustered")


def downgrade() -> None:
    # =========================================================================
    # Restore Clarity columns
    # =========================================================================
    op.add_column(
        "clarity_clusters",
        sa.Column(
            "correctly_clustered",
            sa.Boolean(),
            nullable=True,
            comment="DEPRECATED: User confirmation. Always null in explicit save model."
        )
    )
    op.add_column(
        "clarity_clusters",
        sa.Column(
            "thoughts_exhausted",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="DEPRECATED: Always false in explicit save model."
        )
    )
    # Remove server_default after adding column
    op.alter_column("clarity_clusters", "thoughts_exhausted", server_default=None)

    # =========================================================================
    # Restore nonce column
    # =========================================================================
    op.add_column(
        "oauth_authorization_codes",
        sa.Column(
            "nonce",
            sa.String(255),
            nullable=True,
            comment="OpenID Connect nonce (optional)"
        )
    )

    # =========================================================================
    # Restore session_token column
    # =========================================================================
    # Make session_token_hash nullable again
    op.alter_column(
        "oauth_sessions",
        "session_token_hash",
        existing_type=sa.String(64),
        nullable=True
    )

    # Add session_token column back (will be NULL for new sessions)
    op.add_column(
        "oauth_sessions",
        sa.Column(
            "session_token",
            sa.String(64),
            nullable=True,  # Must be nullable since we can't recover plaintext
            comment="Random token stored in cookie (32 bytes hex) - DEPRECATED"
        )
    )

    # Recreate index
    op.create_index(
        "idx_oauth_sessions_session_token",
        "oauth_sessions",
        ["session_token"],
        unique=True
    )

    # =========================================================================
    # Restore last_used_at column
    # =========================================================================
    op.add_column(
        "oauth_access_tokens",
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last time token was used"
        )
    )
