"""
OAuth Provider Models.

Contains all tables related to the OAuth 2.1 provider:
- OAuthAuthorizationCode
- OAuthAccessToken
- OAuthState
- OAuthSession (Increment 19)

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


# ==============================================================================
# DEPRECATED: OAuthClient class removed (replaced by CoreConnection)
# ==============================================================================
#
# The oauth_clients table was dropped in migration d0aca8881c7e (Nov 22, 2024).
# OAuth provider client registration now uses core_connections table with:
#   - connection_type = 'oauth_provider'
#   - client_id, client_secret_enc, redirect_uris, grant_types fields
#   - user_id = NULL (clients are not user-specific)
#
# Use: from backend.core.models import CoreConnection
#
# If you see this class referenced in code, it's a bug that must be fixed.
# ==============================================================================


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

    scope: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        comment="Array of scopes (e.g., ['focused.read', 'focused.write'])"
    )

    state: Mapped[str | None] = mapped_column(
        String(5000),
        nullable=True,
        comment="CSRF protection state (optional)"
    )

    resource: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="Resource parameter from /authorize (RFC 9728 B2-5)"
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
        Index("idx_oauth_authorization_codes_client_id", "client_id"),  # Client-filtered queries
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

    scope: Mapped[list[str]] = mapped_column(
        ARRAY(String),
        nullable=False,
        comment="Array of scopes (e.g., ['focused.read', 'focused.write'])"
    )

    resource: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="Resource parameter for JWT aud claim (RFC 9728 B2-5)"
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

    __table_args__ = (
        Index("idx_oauth_access_tokens_user_id", "user_id"),
        Index("idx_oauth_access_tokens_client_id", "client_id"),  # Client-filtered queries
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


class OAuthSession(Base):
    """
    Browser sessions for cross-app user identification (Increment 19).

    When a user authorizes one SDK app (e.g., Focused), a session cookie is set.
    When they later authorize another app (e.g., Decliner), the cookie identifies
    them as the same user, allowing shared CoreUser identity across apps.

    Lifecycle:
    - Created after user clicks "Allow" on consent screen
    - Session token stored in pg_session cookie (HttpOnly, Secure, SameSite=Lax)
    - expires_at extended on each use (sliding window). Default = now() + 730 days.
    - NOT deleted on app revocation (/oauth/revoke) - preserves cross-app identity
    - Expired sessions cleaned up by Celery task
    - Deleted only on full user data deletion (DELETE sessions + clear cookie)

    Security:
    - Token is 32 bytes, cryptographically random (64 hex chars)
    - Cookie is HttpOnly (no JavaScript access)
    - Cookie is Secure (HTTPS only in production)
    - Cookie is SameSite=Lax (sent on OAuth redirects, blocked on cross-site POST)
    - Cookie scoped to /oauth path only
    """

    __tablename__ = "oauth_sessions"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        comment="Session identifier (UUID)"
    )

    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core_users.id", ondelete="CASCADE"),
        nullable=False,
        comment="User this session belongs to"
    )

    session_token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 hash of session token for O(1) indexed lookup"
    )

    session_token_enc: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Fernet-encrypted session token for audit/recovery"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When session was created"
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("(now() + interval '730 days')"),
        comment="When session expires (sliding window: extended on each use). Default = now() + 730 days."
    )

    __table_args__ = (
        Index("idx_oauth_sessions_session_token_hash", "session_token_hash", unique=True),
        Index("idx_oauth_sessions_user_id", "user_id"),
        Index("idx_oauth_sessions_expires_at", "expires_at"),
        {"comment": "Browser sessions for cross-app user identification"}
    )
