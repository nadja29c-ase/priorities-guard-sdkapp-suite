"""add_oauth_clients_table

Revision ID: e4a790ebd732
Revises: 7a1f4b2e3c9d
Create Date: 2025-11-20 20:11:26.719060

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e4a790ebd732'
down_revision: Union[str, Sequence[str], None] = '7a1f4b2e3c9d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add oauth_clients table for OAuth 2.1 client registrations."""

    # Create oauth_clients table
    op.create_table(
        'oauth_clients',
        sa.Column('client_id', sa.String(255), nullable=False, comment="Client identifier (e.g., 'focused-client-{uuid}')"),
        sa.Column('client_secret_enc', sa.Text(), nullable=False, comment="Encrypted client secret (Fernet)"),
        sa.Column('client_name', sa.String(255), nullable=False, comment="Human-readable client name (e.g., 'ChatGPT')"),
        sa.Column('redirect_uris', postgresql.ARRAY(sa.String()), nullable=False, comment="Allowed redirect URIs for authorization code flow"),
        sa.Column('allowed_scopes', sa.String(512), nullable=False, comment="Space-separated allowed scopes (e.g., 'focused.read focused.write')"),
        sa.Column('grant_types', postgresql.ARRAY(sa.String()), nullable=False, comment="Allowed grant types (e.g., ['authorization_code', 'refresh_token'])"),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), comment="When the client was registered"),
        sa.PrimaryKeyConstraint('client_id'),
        comment="OAuth 2.1 client registrations"
    )

    # Create index on client_id for fast lookups
    op.create_index('idx_oauth_clients_client_id', 'oauth_clients', ['client_id'])


def downgrade() -> None:
    """Downgrade schema - Remove oauth_clients table."""

    # Drop index first
    op.drop_index('idx_oauth_clients_client_id', table_name='oauth_clients')

    # Drop table
    op.drop_table('oauth_clients')
