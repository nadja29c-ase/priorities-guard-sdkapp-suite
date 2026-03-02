"""merge_session_token_and_keyword_branches

Revision ID: e1030e3cb279
Revises: b9c0d1e2f3g4, v2w3x4y5z6a7
Create Date: 2026-03-02 11:05:49.416653

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1030e3cb279'
down_revision: Union[str, Sequence[str], None] = ('b9c0d1e2f3g4', 'v2w3x4y5z6a7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
