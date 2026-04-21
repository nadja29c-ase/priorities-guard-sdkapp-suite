"""Add openai_subject column to core_users

Revision ID: b8c9d0e1f2g3
Revises: a7b8c9d0e1f2
Create Date: 2026-04-21

Increment 78: Cross-device identity reconciliation via openai/subject.
Adds openai_subject column for cross-device user identity anchor.
Partial unique index ensures uniqueness only for non-NULL values.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b8c9d0e1f2g3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "core_users",
        sa.Column(
            "openai_subject",
            sa.String(128),
            nullable=True,
            comment="Anonymized ChatGPT user id from _meta['openai/subject']. "
                    "Used as cross-device identity anchor."
        )
    )
    op.create_index(
        "ix_core_users_openai_subject",
        "core_users",
        ["openai_subject"],
        unique=True,
        postgresql_where=sa.text("openai_subject IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_core_users_openai_subject", table_name="core_users")
    op.drop_column("core_users", "openai_subject")
