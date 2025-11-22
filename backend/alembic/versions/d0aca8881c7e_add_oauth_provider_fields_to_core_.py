"""add_oauth_provider_fields_to_core_connections

Revision ID: d0aca8881c7e
Revises: e4a790ebd732
Create Date: 2025-11-22 09:57:49.439647

Fixes for Increment 7B:
- Move OAuth client registration from oauth_clients to core_connections
- Make user_id nullable (OAuth clients are not user-specific)
- Add OAuth provider fields to core_connections
- Drop oauth_clients table

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd0aca8881c7e'
down_revision: Union[str, Sequence[str], None] = 'e4a790ebd732'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 1. Make user_id nullable (OAuth clients are not user-specific)
    op.alter_column('core_connections', 'user_id',
                    existing_type=postgresql.UUID(),
                    nullable=True)

    # 2. Add OAuth provider fields
    op.add_column('core_connections', sa.Column('client_id', sa.String(length=255), nullable=True, comment='OAuth client ID (for oauth_provider connections)'))
    op.add_column('core_connections', sa.Column('client_secret_enc', sa.Text(), nullable=True, comment='Encrypted OAuth client secret (for oauth_provider connections)'))
    op.add_column('core_connections', sa.Column('redirect_uris', postgresql.ARRAY(sa.String()), nullable=True, comment='Allowed redirect URIs for OAuth authorization (for oauth_provider connections)'))
    op.add_column('core_connections', sa.Column('grant_types', postgresql.ARRAY(sa.String()), nullable=True, comment="Allowed grant types (e.g., ['authorization_code', 'refresh_token'])"))

    # 3. Add unique constraint for client_id
    op.create_unique_constraint('uq_client_id', 'core_connections', ['client_id'])

    # 4. Add index for client_id lookups
    op.create_index('ix_client_id', 'core_connections', ['client_id'], unique=False)

    # 5. Drop oauth_clients table if it exists (replaced by core_connections)
    op.execute('DROP TABLE IF EXISTS oauth_clients CASCADE')


def downgrade() -> None:
    """Downgrade schema."""

    # Recreate oauth_clients table
    op.create_table('oauth_clients',
        sa.Column('client_id', sa.String(length=255), nullable=False, comment='Client identifier (e.g., \'focused-client-{uuid}\')'),
        sa.Column('client_secret_enc', sa.Text(), nullable=False, comment='Encrypted client secret (Fernet)'),
        sa.Column('client_name', sa.String(length=255), nullable=False, comment='Human-readable client name (e.g., \'ChatGPT\')'),
        sa.Column('redirect_uris', postgresql.ARRAY(sa.String()), nullable=False, comment='Allowed redirect URIs for authorization code flow'),
        sa.Column('allowed_scopes', sa.String(length=512), nullable=False, comment='Space-separated allowed scopes (e.g., \'focused.read focused.write\')'),
        sa.Column('grant_types', postgresql.ARRAY(sa.String()), nullable=False, comment="Allowed grant types (e.g., ['authorization_code', 'refresh_token'])"),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='When the client was registered'),
        sa.PrimaryKeyConstraint('client_id'),
        comment='OAuth 2.1 client registrations'
    )
    op.create_index('idx_oauth_clients_client_id', 'oauth_clients', ['client_id'], unique=False)

    # Remove OAuth provider fields from core_connections
    op.drop_index('ix_client_id', table_name='core_connections')
    op.drop_constraint('uq_client_id', 'core_connections', type_='unique')
    op.drop_column('core_connections', 'grant_types')
    op.drop_column('core_connections', 'redirect_uris')
    op.drop_column('core_connections', 'client_secret_enc')
    op.drop_column('core_connections', 'client_id')

    # Make user_id non-nullable again
    op.alter_column('core_connections', 'user_id',
                    existing_type=postgresql.UUID(),
                    nullable=False)
