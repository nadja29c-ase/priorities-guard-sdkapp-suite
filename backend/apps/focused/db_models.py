"""
Database models for the Focused SDK app.

System-level entities (users, connections, etc.) live in backend.core.models.
This module is only for Focused-specific tables.

Currently:
- FocusedUserKeyword: custom focus keywords added by a user
- FocusedFocusSession: calendar events with focus block detection

System default keywords (e.g. "focus", "deep work") are defined in
backend.apps.focused.config and are NOT stored here.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    String,
    Integer,
    DateTime,
    Boolean,
    JSON,
    ForeignKey,
    CheckConstraint,
    Index,
    UniqueConstraint,
    Enum,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from backend.core.models import Base


class FocusedUserKeyword(Base):
    """
    Custom focus keywords added by the user.

    Example:
        user_id = "abc123"
        keyword = "writing sprint"
    """

    __tablename__ = "focused_user_keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to core_users.user_id
    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("core_users.user_id", ondelete="CASCADE"),
        nullable=False,
    )

    # The actual keyword text
    keyword: Mapped[str] = mapped_column(String, nullable=False)

    # Optional: simple audit timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<FocusedUserKeyword user_id={self.user_id!r}, keyword={self.keyword!r}>"


class FocusedFocusSession(Base):
    """
    Calendar events from Google Calendar with focus block detection.

    Stores event data for:
    - Focus block identification (keyword matching)
    - Change detection (SHA256 content hashing)
    - Conflict resolution (Google updated timestamp)
    - 90-day retention (GDPR compliance)

    Example:
        session = FocusedFocusSession(
            user_id=UUID("..."),
            google_event_id="abc123",
            google_calendar_id="primary",
            event_summary="Deep Work Session",
            event_description="Focus on project",
            google_updated_at=datetime.now(timezone.utc),
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc) + timedelta(hours=2),
            is_focus_block=True,
            matched_keyword="deep work",
            sha256_content_hash="...",
            google_ical_uid="abc123@google.com",
        )
    """

    __tablename__ = "focused_focus_sessions"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
        comment="Internal identifier",
    )

    # Foreign key to core_users (RESTRICT to prevent accidental deletion)
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core_users.id", ondelete="RESTRICT"),
        nullable=False,
        comment="Owner user ID",
    )

    # Google Calendar metadata
    google_event_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Google's event.id",
    )

    google_calendar_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default="primary",
        comment="Calendar source",
    )

    google_ical_uid: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="iCalendar UID (stable across updates, groups recurring instances)",
    )

    google_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Google's last modified timestamp (for conflict detection)",
    )

    # Event content
    event_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Event title (can be empty, used for keyword matching)",
    )

    event_description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Event description (max 8192 chars per Google Calendar limit)",
    )

    # Event timing (UTC only)
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Event start time (UTC)",
    )

    end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Event end time (UTC)",
    )

    # Focus block detection
    is_focus_block: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        default=False,  # Python default
        comment="Whether event matches focus keywords",
    )

    matched_keyword: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Which keyword triggered focus block match",
    )

    # Change detection (SHA256 of id + summary + description + start + end)
    sha256_content_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA256 hash of event content for change detection",
    )

    # Lifecycle status (PostgreSQL ENUM)
    status: Mapped[str] = mapped_column(
        Enum("active", "deleted", name="event_status_enum", create_type=False),
        nullable=False,
        server_default="active",
        default="active",  # Python default
        comment="Event lifecycle state",
    )

    # Versioning and sync tracking
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="1",
        default=1,  # Python default
        comment="Event version for history tracking",
    )

    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Last sync from Google (manually updated, no auto-update)",
    )

    # Audit timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="First sync",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="Last modified",
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Soft delete timestamp",
    )

    # Table-level constraints and indexes
    __table_args__ = (
        # Unique constraint: one row per (user, event, calendar)
        UniqueConstraint(
            "user_id",
            "google_event_id",
            "google_calendar_id",
            name="uq_focus_sessions_user_event",
        ),
        # Check: start_time < end_time
        CheckConstraint(
            "start_time < end_time",
            name="ck_focus_sessions_time_order",
        ),
        # Check: version >= 1
        CheckConstraint(
            "version >= 1",
            name="ck_focus_sessions_version_positive",
        ),
        # Check: event_description length <= 8192
        CheckConstraint(
            "length(event_description) <= 8192",
            name="ck_focus_sessions_description_length",
        ),
        # Check: sha256_content_hash length = 64
        CheckConstraint(
            "length(sha256_content_hash) = 64",
            name="ck_focus_sessions_hash_length",
        ),
        # Index: start_time for time-range queries
        Index("idx_focus_sessions_start_time", "start_time"),
        # Index: end_time for time-range queries
        Index("idx_focus_sessions_end_time", "end_time"),
        # Index: focus blocks (user_id, is_focus_block) WHERE status = 'active'
        Index(
            "idx_focus_sessions_focus_blocks",
            "user_id",
            "is_focus_block",
            postgresql_where=Text("status = 'active'"),
        ),
        # Index: composite (user_id, sha256_content_hash) for change detection
        Index("idx_focus_sessions_user_hash", "user_id", "sha256_content_hash"),
        # Index: cleanup job (created_at) WHERE status = 'active'
        Index(
            "idx_focus_sessions_cleanup",
            "created_at",
            postgresql_where=Text("status = 'active'"),
        ),
        # Index: google_ical_uid for recurring event queries
        Index("idx_focus_sessions_ical_uid", "google_ical_uid"),
    )

    def __repr__(self) -> str:
        return (
            f"<FocusedFocusSession id={self.id}, user_id={self.user_id}, "
            f"google_event_id={self.google_event_id!r}, is_focus_block={self.is_focus_block}>"
        )

    def validate(self) -> None:
        """
        Validate model constraints.

        Raises:
            ValueError: If validation fails
        """
        # Validate google_event_id
        if not self.google_event_id or len(self.google_event_id) > 255:
            raise ValueError("google_event_id must be 1-255 characters")

        # Validate google_ical_uid
        if not self.google_ical_uid or len(self.google_ical_uid) > 255:
            raise ValueError("google_ical_uid is required and must be 1-255 characters")

        # Validate google_updated_at
        if not self.google_updated_at:
            raise ValueError("google_updated_at is required")

        # Validate event_summary length
        if self.event_summary and len(self.event_summary) > 2000:
            raise ValueError("event_summary must be <= 2000 characters")

        # Validate event_description length
        if self.event_description and len(self.event_description) > 8192:
            raise ValueError("event_description must be <= 8192 characters")

        # Validate timing
        if self.start_time >= self.end_time:
            raise ValueError("start_time must be < end_time")

        # Validate SHA256 hash
        if not self.sha256_content_hash or len(self.sha256_content_hash) != 64:
            raise ValueError("sha256_content_hash must be exactly 64 hex characters")

        # Validate status
        if self.status not in ("active", "deleted"):
            raise ValueError("status must be 'active' or 'deleted'")

        # Validate matched_keyword length
        if self.matched_keyword and len(self.matched_keyword) > 100:
            raise ValueError("matched_keyword must be <= 100 characters")

        # Validate version
        if self.version is not None and self.version < 1:
            raise ValueError("version must be >= 1")
