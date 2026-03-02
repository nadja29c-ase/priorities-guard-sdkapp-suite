"""Add session_token_hash and session_token_enc columns to oauth_sessions.

Increment 20 - Security hardening: Hash session tokens before storage.

Phase 1 Migration (this file):
- Step 1: Add nullable columns (no unique constraint yet)
- Step 2: Backfill existing rows with SHA-256 hashes
- Step 3: Create unique index on session_token_hash

Phase 2 (future increment):
- Drop session_token column after all sessions have rotated

IMPORTANT: This migration uses inline hashlib, NOT application code imports.
Migrations must be self-contained and stable across codebase changes.

Revision ID: v2w3x4y5z6a7
Revises: u1v2w3x4y5z6
Create Date: 2026-03-01
"""

import hashlib
import os

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = "v2w3x4y5z6a7"
down_revision = "b9c0d1e2f3g4"  # Rebased to be after keyword_check_constraint
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # Step 1: Add nullable columns (NO unique constraint yet)
    # =========================================================================
    op.add_column(
        "oauth_sessions",
        sa.Column(
            "session_token_hash",
            sa.String(64),
            nullable=True,
            comment="SHA-256 hash of session token for O(1) indexed lookup"
        )
    )
    op.add_column(
        "oauth_sessions",
        sa.Column(
            "session_token_enc",
            sa.Text(),
            nullable=True,
            comment="Fernet-encrypted session token for audit/recovery"
        )
    )

    # =========================================================================
    # Step 2: Backfill existing rows with SHA-256 hashes
    # =========================================================================
    # Get database connection for batch processing
    conn = op.get_bind()

    # Fetch all existing sessions
    result = conn.execute(
        text("SELECT id, session_token FROM oauth_sessions WHERE session_token_hash IS NULL")
    )
    rows = result.fetchall()

    # Check if encryption key is available (for session_token_enc backfill)
    encryption_key = os.environ.get("ENCRYPTION_KEY")
    fernet = None
    if encryption_key:
        try:
            from cryptography.fernet import Fernet
            fernet = Fernet(encryption_key.encode())
        except Exception:
            # Skip encryption if key is invalid or cryptography not available
            pass

    # Backfill in batches
    for row in rows:
        session_id = row[0]
        session_token = row[1]
        if not session_token:
            continue

        # Compute SHA-256 hash (inline, not using app code)
        token_hash = hashlib.sha256(session_token.encode()).hexdigest()

        # Encrypt if Fernet is available
        token_enc = None
        if fernet:
            try:
                token_enc = fernet.encrypt(session_token.encode()).decode()
            except Exception:
                pass  # Skip encryption on error, app code will backfill lazily

        # Update the row
        if token_enc:
            conn.execute(
                text(
                    "UPDATE oauth_sessions SET session_token_hash = :hash, "
                    "session_token_enc = :enc WHERE id = :id"
                ),
                {"hash": token_hash, "enc": token_enc, "id": session_id}
            )
        else:
            conn.execute(
                text(
                    "UPDATE oauth_sessions SET session_token_hash = :hash WHERE id = :id"
                ),
                {"hash": token_hash, "id": session_id}
            )

    # =========================================================================
    # Step 3: Create unique index on session_token_hash
    # Done AFTER backfill to avoid uniqueness violations on NULL rows
    # =========================================================================
    op.create_index(
        "idx_oauth_sessions_session_token_hash",
        "oauth_sessions",
        ["session_token_hash"],
        unique=True
    )


def downgrade() -> None:
    # Drop index first
    op.drop_index("idx_oauth_sessions_session_token_hash", table_name="oauth_sessions")

    # Drop columns
    op.drop_column("oauth_sessions", "session_token_enc")
    op.drop_column("oauth_sessions", "session_token_hash")
