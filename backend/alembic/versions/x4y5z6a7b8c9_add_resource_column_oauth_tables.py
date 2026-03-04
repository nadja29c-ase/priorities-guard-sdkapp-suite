"""Add resource column to OAuth tables for B2-5 compliance.

OAuth 2.1 RFC 9728 requires the authorization server to accept the
resource parameter on both /authorize and /token endpoints, and echo
it into the JWT aud claim.

This migration adds nullable resource columns to:
- oauth_authorization_codes: stores resource from /authorize
- oauth_access_tokens: stores resource for use during refresh grant

Revision ID: x4y5z6a7b8c9
Revises: w3x4y5z6a7b8
Create Date: 2026-03-04
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "x4y5z6a7b8c9"
down_revision = "w3x4y5z6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add resource column to oauth_authorization_codes
    # Nullable: resource is optional per RFC 9728
    op.add_column(
        "oauth_authorization_codes",
        sa.Column(
            "resource",
            sa.String(512),
            nullable=True,
            comment="Resource parameter from /authorize (RFC 9728 B2-5)"
        )
    )

    # Add resource column to oauth_access_tokens
    # Nullable: tokens issued before this fix won't have it
    # Used during refresh grant to preserve the original resource value
    op.add_column(
        "oauth_access_tokens",
        sa.Column(
            "resource",
            sa.String(512),
            nullable=True,
            comment="Resource parameter for JWT aud claim (RFC 9728 B2-5)"
        )
    )


def downgrade() -> None:
    op.drop_column("oauth_access_tokens", "resource")
    op.drop_column("oauth_authorization_codes", "resource")
