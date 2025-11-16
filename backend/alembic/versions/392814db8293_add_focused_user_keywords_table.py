"""add focused_user_keywords table

Revision ID: 392814db8293
Revises: 796653ff0824
Create Date: 2025-11-16 18:43:14.937281

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '392814db8293'
down_revision = '796653ff0824'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "focused_user_keywords",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.String,
            sa.ForeignKey("core_users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("keyword", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_index(
        "ix_focused_user_keywords_user_id",
        "focused_user_keywords",
        ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_focused_user_keywords_user_id", table_name="focused_user_keywords")
    op.drop_table("focused_user_keywords")
