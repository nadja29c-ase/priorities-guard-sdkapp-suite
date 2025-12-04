"""add core_consents table

Revision ID: ddbd7655b93a
Revises: g7b8c9d0e1f2
Create Date: 2025-12-04 12:26:24.371173

Increment 17: OAuth Provider Hardening - Consent Persistence.

Creates core_consents table for GDPR-compliant consent tracking.
Records user consent per app and scope with grant/revoke timestamps.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ddbd7655b93a'
down_revision: Union[str, Sequence[str], None] = 'g7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create core_consents table for GDPR consent tracking."""
    op.create_table(
        'core_consents',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False, comment='Unique consent record ID'),
        sa.Column('user_id', sa.UUID(), nullable=False, comment='User who granted consent'),
        sa.Column('app_name', sa.String(length=50), nullable=False, comment="SDK app name (e.g., 'focused')"),
        sa.Column('scope', sa.String(length=100), nullable=False, comment="Individual scope consented to (e.g., 'focused.read')"),
        sa.Column('granted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='When consent was granted (updated on re-consent)'),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True, comment='When consent was revoked (NULL if still active)'),
        sa.ForeignKeyConstraint(['user_id'], ['core_users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'app_name', 'scope', name='uq_user_app_scope')
    )
    op.create_index('ix_consent_app_name', 'core_consents', ['app_name'], unique=False)
    op.create_index('ix_consent_user_id', 'core_consents', ['user_id'], unique=False)


def downgrade() -> None:
    """Drop core_consents table."""
    op.drop_index('ix_consent_user_id', table_name='core_consents')
    op.drop_index('ix_consent_app_name', table_name='core_consents')
    op.drop_table('core_consents')
