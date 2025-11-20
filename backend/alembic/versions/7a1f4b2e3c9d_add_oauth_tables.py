"""add oauth tables and connection_type

Revision ID: 7a1f4b2e3c9d
Revises: 94adbd6c7fd3
Create Date: 2025-11-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '7a1f4b2e3c9d'
down_revision: Union[str, Sequence[str], None] = '94adbd6c7fd3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add OAuth tables and connection_type field."""

    # =========================================================================
    # Step 1: Add connection_type to core_connections (nullable first)
    # =========================================================================
    op.add_column('core_connections',
        sa.Column('connection_type', sa.String(50), nullable=True,
                  comment="Connection type: 'google', 'apple', 'oauth_provider', or 'unknown'")
    )

    # =========================================================================
    # Step 2: Backfill existing rows based on provider
    # =========================================================================
    op.execute("""
        UPDATE core_connections
        SET connection_type = 'google'
        WHERE provider = 'google'
    """)

    op.execute("""
        UPDATE core_connections
        SET connection_type = 'apple'
        WHERE provider = 'apple'
    """)

    # =========================================================================
    # Step 3: Make connection_type NOT NULL with neutral default
    # =========================================================================
    op.alter_column('core_connections', 'connection_type',
        nullable=False,
        server_default='unknown'
    )

    # =========================================================================
    # Step 4: Create oauth_authorization_codes table
    # =========================================================================
    op.create_table(
        'oauth_authorization_codes',
        sa.Column('code', sa.String(128), nullable=False, comment="Authorization code (cryptographically random)"),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('core_users.id', ondelete='CASCADE'), nullable=False, comment="User who authorized this code"),
        sa.Column('client_id', sa.String(255), nullable=False, comment="Client identifier (from registration)"),
        sa.Column('code_challenge', sa.String(255), nullable=False, comment="PKCE code challenge (base64url-encoded SHA256)"),
        sa.Column('code_challenge_method', sa.String(10), nullable=False, comment="PKCE challenge method (always 'S256')"),
        sa.Column('redirect_uri', sa.String(512), nullable=False, comment="Redirect URI for this authorization"),
        sa.Column('scope', sa.String(512), nullable=False, comment="Space-separated scopes (e.g., 'focused.read focused.write')"),
        sa.Column('state', sa.String(255), nullable=True, comment="CSRF protection state (optional)"),
        sa.Column('nonce', sa.String(255), nullable=True, comment="OpenID Connect nonce (optional)"),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False, comment="Code expiration (10 minutes from creation)"),
        sa.Column('used', sa.Boolean(), nullable=False, server_default='false', comment="Whether code has been exchanged for token"),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), comment="Code creation timestamp"),
        sa.PrimaryKeyConstraint('code')
    )

    # Indices for oauth_authorization_codes
    op.create_index('idx_oauth_authorization_codes_user_id', 'oauth_authorization_codes', ['user_id'])
    op.create_index('idx_oauth_authorization_codes_expires_at', 'oauth_authorization_codes', ['expires_at'])

    # =========================================================================
    # Step 5: Create oauth_access_tokens table
    # =========================================================================
    op.create_table(
        'oauth_access_tokens',
        sa.Column('jti', sa.String(128), nullable=False, comment="JWT ID (unique token identifier)"),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('core_users.id', ondelete='CASCADE'), nullable=False, comment="User who owns this token"),
        sa.Column('client_id', sa.String(255), nullable=False, comment="Client identifier"),
        sa.Column('scope', sa.String(512), nullable=False, comment="Space-separated scopes"),
        sa.Column('token_type', sa.String(20), nullable=False, server_default='Bearer', comment="Token type (always 'Bearer')"),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False, comment="Access token expiration"),
        sa.Column('refresh_token_enc', sa.Text(), nullable=True, comment="Encrypted refresh token (Fernet)"),
        sa.Column('refresh_token_expires_at', sa.DateTime(timezone=True), nullable=True, comment="Refresh token expiration (30 days)"),
        sa.Column('revoked', sa.Boolean(), nullable=False, server_default='false', comment="Whether token has been revoked"),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True, comment="When token was revoked"),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), comment="Token creation timestamp"),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True, comment="Last time token was used"),
        sa.PrimaryKeyConstraint('jti')
    )

    # Indices for oauth_access_tokens
    op.create_index('idx_oauth_access_tokens_user_id', 'oauth_access_tokens', ['user_id'])
    op.create_index('idx_oauth_access_tokens_jti', 'oauth_access_tokens', ['jti'])
    op.create_index('idx_oauth_access_tokens_expires_at', 'oauth_access_tokens', ['expires_at'])


def downgrade() -> None:
    """Downgrade schema - Remove OAuth tables and connection_type field."""

    # Drop indices first (oauth_access_tokens)
    op.drop_index('idx_oauth_access_tokens_expires_at', table_name='oauth_access_tokens')
    op.drop_index('idx_oauth_access_tokens_jti', table_name='oauth_access_tokens')
    op.drop_index('idx_oauth_access_tokens_user_id', table_name='oauth_access_tokens')

    # Drop indices (oauth_authorization_codes)
    op.drop_index('idx_oauth_authorization_codes_expires_at', table_name='oauth_authorization_codes')
    op.drop_index('idx_oauth_authorization_codes_user_id', table_name='oauth_authorization_codes')

    # Drop tables
    op.drop_table('oauth_access_tokens')
    op.drop_table('oauth_authorization_codes')

    # Remove connection_type column
    op.drop_column('core_connections', 'connection_type')
