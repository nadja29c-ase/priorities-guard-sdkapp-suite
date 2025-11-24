"""
Core Shared Application Models.

This file contains application-wide models that apply to all SDK apps:
- CoreUser
- CoreConnection

OAuth provider models live in:
backend/core/oauth_models.py
"""

from datetime import datetime
from uuid import UUID
from sqlalchemy import (
    String,
    Text,
    CheckConstraint,
    Index,
    UniqueConstraint,
    ARRAY,
    DateTime,
    JSON,
    ForeignKey,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func, text


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


class CoreUser(Base):
    """
    Minimal user table for storing user references.

    This is a placeholder table for user management.
    Currently only tracks user existence with minimal fields.
    """

    __tablename__ = "core_users"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="User identifier"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When the user was created"
    )


class CoreConnection(Base):
    """
    Store encrypted OAuth tokens for external service connections.

    Supports:
    - Outbound: Google and Apple OAuth (user connects TO external services)
    - Inbound: OAuth Provider (ChatGPT connects TO our app)

    For inbound OAuth provider connections (connection_type='oauth_provider'):
    - user_id is NULL (clients are not user-specific)
    - client_id, client_secret_enc, redirect_uris, grant_types are populated
    - This replaces the old oauth_clients table
    """

    __tablename__ = "core_connections"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), # unique identifier for database row
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    user_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core_users.id", ondelete="CASCADE"),
        nullable=True,
        comment="Reference to core_users.id (UUID). NULL for oauth_provider connections."
    )

    provider: Mapped[str] = mapped_column(String(50), nullable=False) #OAuth provider.

    connection_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default="unknown",
        comment="Connection type: 'google', 'apple', 'oauth_provider', or 'unknown'"
    )

    encrypted_access_token: Mapped[str] = mapped_column(Text, nullable=False) #The user's Google access token, but encrypted with AES-256

    encrypted_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True) #Google’s refresh token, encrypted.
    
    token_expires_at: Mapped[datetime] = mapped_column( #The timestamp at which the access token expires.
        DateTime(timezone=True), nullable=False
    )

    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False) #All scopes authorized by the user (f.e. calendar.readyonly)

    provider_metadata: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Provider-specific metadata (flexible storage for future fields)"
    )

    created_at: Mapped[datetime] = mapped_column( #The timestamp when this connection row was first created.
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column( #Whenever tokens are refreshed or updated, this timestamp updates.
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Webhook fields (Google Calendar push notifications)
    google_channel_id: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        comment="Google Calendar webhook channel ID (Google-generated; expires ~7 days)"
    )

    google_resource_id: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
        comment="Google Calendar webhook resource ID (Google-generated; may change on renewal)"
    )

    google_channel_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the Google Calendar webhook channel expires (~7 days from registration)"
    )

    # OAuth Provider fields (for inbound connections where ChatGPT connects to us)
    client_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="OAuth client ID (for oauth_provider connections)"
    )

    client_secret_enc: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Encrypted OAuth client secret (for oauth_provider connections)"
    )

    redirect_uris: Mapped[list[str] | None] = mapped_column(
        ARRAY(String),
        nullable=True,
        comment="Allowed redirect URIs for OAuth authorization (for oauth_provider connections)"
    )

    grant_types: Mapped[list[str] | None] = mapped_column(
        ARRAY(String),
        nullable=True,
        comment="Allowed grant types (e.g., ['authorization_code', 'refresh_token'])"
    )

    __table_args__ = ( #Inside a SQLAlchemy model, __table_args__ is a special class attribute that lets you define anything that applies to the whole table f.e. Unique constrainsts, Indexes, Check constraints
        UniqueConstraint("user_id", "provider", name="uq_user_provider"), # Ensures there is only one row per user per provider to prevent duplicates
        UniqueConstraint("client_id", name="uq_client_id"),  # Unique constraint for OAuth provider client_id
        # Conditional constraint: oauth_provider connections can have empty encrypted_access_token
        CheckConstraint(
            "(connection_type = 'oauth_provider') OR (length(encrypted_access_token) > 0)",
            name="ck_encrypted_access_token_conditional"
        ),
        CheckConstraint("(encrypted_refresh_token IS NULL) OR (length(encrypted_refresh_token) > 0)", name="ck_encrypted_refresh_token_not_empty"),
        CheckConstraint("cardinality(scopes) > 0", name="ck_scopes_not_empty"),
        Index("ix_user_provider", "user_id", "provider"), #A database index for fast lookups
        Index("ix_token_expires", "token_expires_at"),
        Index("ix_channel_expires", "google_channel_expires_at"),
        Index("ix_client_id", "client_id"),  # Index for OAuth provider client_id lookups
    )
