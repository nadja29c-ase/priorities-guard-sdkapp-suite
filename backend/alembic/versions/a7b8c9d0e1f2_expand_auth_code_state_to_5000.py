"""Expand oauth_authorization_codes.state to VARCHAR(5000).

ChatGPT Apps SDK submission sends state tokens longer than 512 chars,
causing StringDataRightTruncationError during domain verification.

Revision ID: a7b8c9d0e1f2
Revises: z6a7b8c9d0e1
Create Date: 2026-04-05
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a7b8c9d0e1f2"
down_revision = "z6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "oauth_authorization_codes",
        "state",
        existing_type=sa.String(length=512),
        type_=sa.String(length=5000),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "oauth_authorization_codes",
        "state",
        existing_type=sa.String(length=5000),
        type_=sa.String(length=512),
        existing_nullable=True,
    )
