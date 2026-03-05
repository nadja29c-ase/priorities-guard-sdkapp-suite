"""
Core Shared Application Models.

This file contains application-wide models that apply to all SDK apps:
- CoreUser
- CoreConnection
- CoreToolAuditLog

OAuth provider models live in:
backend/core/oauth_provider/models.py
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

    Maps external ChatGPT user IDs (from login_hint) to internal UUIDs.
    The chatgpt_user_id is a pseudonymous identifier used for OAuth flows.
    When login_hint is not provided, chatgpt_user_id will be NULL (anonymous user).
    """

    __tablename__ = "core_users"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="Internal user identifier (UUID)"
    )

    chatgpt_user_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        unique=True,
        index=True,
        comment="ChatGPT user ID from login_hint parameter (NULL for anonymous users)"
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

    provider: Mapped[str] = mapped_column(String(200), nullable=False)  # OAuth provider or client name

    connection_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default="unknown",
        comment="Connection type: 'google', 'apple', 'oauth_provider', or 'unknown'"
    )

    # Encrypted access token (unused for oauth_provider connections - see ck_encrypted_access_token_conditional)
    encrypted_access_token: Mapped[str] = mapped_column(Text, nullable=False)

    encrypted_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True) #Google’s refresh token, encrypted.
    
    token_expires_at: Mapped[datetime] = mapped_column( #The timestamp at which the access token expires.
        DateTime(timezone=True), nullable=False
    )

    scopes: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)  # All scopes authorized by the user (e.g. calendar.readonly)

    provider_metadata: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        server_default=text("'{}'::jsonb"),
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

    # Offboarding fields (Increment 10)
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the connection was revoked/disconnected"
    )

    # GDPR Retention (Increment 39)
    # ARCHITECTURAL RULE (permanent, enforced from Increment 39 forward):
    # last_used_at means: "a real Google Calendar API call succeeded for this connection."
    # Set connection.last_used_at = datetime.now(timezone.utc) immediately after each
    # successful Google API response — not after all calls succeed together, not on
    # token refresh, not on DB-only operations. This applies to all apps in the suite.
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of last successful Google Calendar API call. "
                "NULL means the connection has never successfully called the Google API, "
                "or predates Increment 39 migration."
    )

    __table_args__ = (  # Table-level constraints and indexes
        # For outbound OAuth (user connects to Google/Apple)
        UniqueConstraint("user_id", "provider", name="uq_user_provider"),
        # For inbound OAuth provider (ChatGPT connects to us) - supports multi-app suite
        UniqueConstraint("provider", "client_id", name="uq_provider_client"),
        UniqueConstraint("client_id", name="uq_client_id"),
        # Restrict connection_type to valid values only
        CheckConstraint(
            "connection_type IN ('google', 'apple', 'oauth_provider', 'unknown')",
            name="ck_connection_type_enum"
        ),
        # Conditional constraint: oauth_provider connections can have empty encrypted_access_token
        CheckConstraint(
            "(connection_type = 'oauth_provider') OR (length(encrypted_access_token) > 0)",
            name="ck_encrypted_access_token_conditional"
        ),
        # Note: No constraint on client_secret_enc for oauth_provider - enforced in application logic
        # (client_service.py sets client_secret_enc atomically during registration)
        CheckConstraint("(encrypted_refresh_token IS NULL) OR (length(encrypted_refresh_token) > 0)", name="ck_encrypted_refresh_token_not_empty"),
        # NOTE (Architectural Decision – Increment 12):
        # The "ck_scopes_not_empty" constraint enforces that ALL connections must have at
        # least one scope in the scopes[] array.
        #
        # This constraint was originally designed for OUTBOUND OAuth connections
        # (Google/Apple), where having at least one scope is mandatory.
        #
        # For INBOUND OAuth Provider clients (connection_type='oauth_provider'):
        # - OAuth 2.1 allows clients to have an empty default scope list.
        # - Our implementation *could* support scopes=[], and validate only against
        #   explicitly requested scopes during /authorize.
        #
        # However, for MVP:
        # - Focused always registers clients with explicit scopes.
        # - This constraint prevents misconfigured clients with empty or null scopes.
        # - We skip relaxing this constraint to avoid schema drift and complexity now.
        #
        # Post-MVP possible change:
        #     CHECK (
        #         connection_type = 'oauth_provider'
        #         OR cardinality(scopes) > 0
        #     )
        #
        # This will allow oauth_provider clients to have empty scopes while preserving
        # the constraint for Google/Apple connections.
        CheckConstraint("cardinality(scopes) > 0", name="ck_scopes_not_empty"),
        Index("ix_user_provider", "user_id", "provider"),
        Index("ix_token_expires", "token_expires_at"),
        # TODO: Used by webhook renewal query (Celery task, future increment):
        # SELECT * FROM core_connections WHERE google_channel_expires_at < NOW() + interval '48 hours'
        Index("ix_channel_expires", "google_channel_expires_at"),
        Index("ix_client_id", "client_id"),
    )


class CoreConsent(Base):
    """
    Records user consent per app and scope (GDPR compliance).

    Each row represents consent for a specific scope granted by a user
    to a specific app. Consent can be revoked (revoked_at set).

    Used for:
    - GDPR audit trail ("prove what user consented to")
    - Right to access ("show me my consent history")
    - Revocation tracking

    Example:
        consent = CoreConsent(
            user_id=uuid,
            app_name="focused",
            scope="focused.read",
        )
    """

    __tablename__ = "core_consents"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="Unique consent record ID"
    )

    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core_users.id", ondelete="CASCADE"),
        nullable=False,
        comment="User who granted consent"
    )

    app_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="SDK app name (e.g., 'focused')"
    )

    scope: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Individual scope consented to (e.g., 'focused.read')"
    )

    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When consent was granted (updated on re-consent)"
    )

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When consent was revoked (NULL if still active)"
    )

    __table_args__ = (
        # One active consent per user+app+scope combination
        UniqueConstraint("user_id", "app_name", "scope", name="uq_user_app_scope"),
        Index("ix_consent_user_id", "user_id"),
        Index("ix_consent_app_name", "app_name"),
    )


class CoreToolAuditLog(Base):
    """
    Audit log for user actions (GDPR compliance).

    Tracks sensitive operations like disconnect and delete-data
    for compliance and debugging purposes.

    Example:
        log = CoreToolAuditLog(
            user_id=uuid,
            app_name="focused",
            action="delete_data",
            result_status="success",
            details={"tables_affected": 2}
        )
    """

    __tablename__ = "core_tool_audit_log"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="Unique audit log entry ID"
    )

    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        nullable=False,
        comment="User who performed or was affected by the action. "
                "Intentionally NOT a FK - audit logs must persist after user deletion for GDPR compliance."
    )

    app_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="SDK app name (e.g., focused, decliner)"
    )

    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Action performed (e.g., disconnect, delete_data)"
    )

    result_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Result: success, failed, partial"
    )

    details: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Additional details (tables affected, error messages)"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When the action occurred"
    )

    __table_args__ = (
        Index("idx_audit_log_user_id", "user_id"),
        Index("idx_audit_log_app_name", "app_name"),
        Index("idx_audit_log_created_at", "created_at"),
    )
