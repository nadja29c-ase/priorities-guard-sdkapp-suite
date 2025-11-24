"""
OAuth Provider Models.

Contains all tables related to the OAuth 2.1 provider:
- OAuthClient
- OAuthAuthorizationCode
- OAuthAccessToken
- OAuthState

This is an isolated subsystem separate from core shared models.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    ARRAY,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func, text

from backend.core.models import Base


class OAuthClient(Base):
    """
    OAuth 2.1 client registrations (ChatGPT SDK apps).

    Stores registered OAuth clients that can request authorization.
    Each client has unique credentials and allowed redirect URIs.

    Security:
    - client_secret encrypted with Fernet
    - redirect_uris validated before authorization
    - allowed_scopes enforced during token issuance
    """

    __tablename__ = "oauth_clients"

    client_id: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
        comment="Client identifier (e.g., 'focused-client-{uuid}')"
    )

    client_secret_enc: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Encrypted client secret (Fernet)"
    )

    client_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Human-readable client name (e.g., 'ChatGPT')"
    )

    redirect_uris: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        comment="Allowed redirect URIs for authorization code flow"
    )

    allowed_scopes: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        comment="Space-separated allowed scopes (e.g., 'focused.read focused.write')"
    )

    grant_types: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        comment="Allowed grant types (e.g., ['authorization_code', 'refresh_token'])"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When the client was registered"
    )

    __table_args__ = (
        Index("idx_oauth_clients_client_id", "client_id"),
        {"comment": "OAuth 2.1 client registrations"}
    )


class OAuthAuthorizationCode(Base):
    """
    Authorization codes for OAuth 2.1 PKCE flow.

    Lifecycle:
    - Created during /authorize
    - Validated and consumed during /token
    - Expires after 10 minutes
    - Marked as 'used' after token exchange
    - Cleaned up by Celery job

    Security:
    - Single-use only (used=True after exchange)
    - PKCE code_challenge required (S256)
    - Expires_at enforced
    """

    __tablename__ = "oauth_authorization_codes"

    code: Mapped[str] = mapped_column(
        String(128),
        primary_key=True,
        comment="Authorization code (cryptographically random)"
    )

    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core_users.id", ondelete="CASCADE"),
        nullable=False,
        comment="User who authorized this code"
    )

    client_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Client identifier (from registration)"
    )

    code_challenge: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="PKCE code challenge (base64url-encoded SHA256)"
    )

    code_challenge_method: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="PKCE challenge method (always 'S256')"
    )

    redirect_uri: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        comment="Redirect URI for this authorization"
    )

    scope: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        comment="Space-separated scopes (e.g., 'focused.read focused.write')"
    )

    state: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="CSRF protection state (optional)"
    )

    nonce: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="OpenID Connect nonce (optional)"
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Code expiration (10 minutes from creation)"
    )

    used: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        comment="Whether code has been exchanged for token"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Code creation timestamp"
    )

    __table_args__ = (
        Index("idx_oauth_authorization_codes_user_id", "user_id"),
        Index("idx_oauth_authorization_codes_expires_at", "expires_at"),  # O(1) cleanup
        {"comment": "OAuth 2.1 PKCE authorization codes"}
    )


class OAuthAccessToken(Base):
    """
    Access tokens issued by OAuth provider.

    Lifecycle:
    - Created during /token endpoint
    - Used to authenticate MCP tool requests
    - Expires after 1 hour (configurable)
    - Can be revoked
    - Refresh token stored encrypted

    Security:
    - JTI (JWT ID) is primary key
    - Refresh tokens encrypted with Fernet
    - Revocation supported
    - Expiration enforced
    """

    __tablename__ = "oauth_access_tokens"

    jti: Mapped[str] = mapped_column(
        String(128),
        primary_key=True,
        comment="JWT ID (unique token identifier)"
    )

    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core_users.id", ondelete="CASCADE"),
        nullable=False,
        comment="User who owns this token"
    )

    client_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Client identifier"
    )

    scope: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        comment="Space-separated scopes"
    )

    token_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="Bearer",
        comment="Token type (always 'Bearer')"
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Access token expiration"
    )

    refresh_token_enc: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Encrypted refresh token (Fernet)"
    )

    refresh_token_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="SHA-256 hash of refresh token for O(1) indexed lookup"
    )

    refresh_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Refresh token expiration (30 days)"
    )

    revoked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        comment="Whether token has been revoked"
    )

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When token was revoked"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Token creation timestamp"
    )

    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last time token was used"
    )

    __table_args__ = (
        Index("idx_oauth_access_tokens_user_id", "user_id"),
        Index("idx_oauth_access_tokens_jti", "jti"),
        Index("idx_oauth_access_tokens_expires_at", "expires_at"),  # O(1) cleanup
        Index("idx_oauth_access_tokens_refresh_token_hash", "refresh_token_hash"),  # CRITICAL: O(1) refresh token lookup
        {"comment": "OAuth 2.1 access tokens with refresh token support"}
    )


class OAuthState(Base):
    """
    Store OAuth state tokens for CSRF protection.

    State tokens are single-use and expire after 10 minutes.
    Deleted after successful verification.
    """

    __tablename__ = "oauth_state"

    state: Mapped[str] = mapped_column(
        Text,
        primary_key=True,
        comment="OAuth state token for CSRF protection (cryptographically random, variable length)"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When the state was created",
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("(now() + interval '10 minutes')"),
        comment="When the state expires (10 minutes from creation)",
    )

    __table_args__ = (
        Index("idx_oauth_state_expires_at", "expires_at"),
        {"comment": "OAuth state tokens for CSRF protection"}
    )
