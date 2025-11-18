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
    text,
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

    # Foreign key to core_users.id (UUID)
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core_users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # The actual keyword text
    keyword: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Focus keyword (max 100 chars, consistent with matched_keyword)",
    )

    # Optional: simple audit timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"<FocusedUserKeyword user_id={self.user_id!r}, keyword={self.keyword!r}>"

    def validate(self) -> None:
        """
        Validate model constraints.

        Raises:
            ValueError: If validation fails
        """
        # Validate keyword is not empty
        if not self.keyword or not self.keyword.strip():
            raise ValueError("keyword cannot be empty or whitespace-only")

        # Validate keyword length
        if len(self.keyword) > 100:
            raise ValueError("keyword must be <= 100 characters")


class FocusedFocusSession(Base):
    """
    Calendar events from Google Calendar with focus block detection.

    Stored for three purposes:
    1. Operational correctness
       - Focus block identification (keyword matching)
       - Change detection (SHA256 hashing)
       - Conflict resolution using Google's updated timestamp
       - Webhook-driven, idempotent sync correctness

    2. Short-term retention (≤90 days)
       - Required for reliable re-sync, orphan detection, and conflict handling
       - Description field retained only temporarily (≤72h) for hashing

    3. Focus pattern insights
       - Identifying when and how often the user enters focus blocks
       - Deriving preferred time-of-day / day-of-week patterns
       - Enabling future predictive or assistive features

    This table supports both immediate Focus Mode triggering
    and medium-term analysis of user focus behavior.

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
        server_default=text("'primary'"),
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
        comment="Event description (temporary, max 8192 chars; deleted after 72h)",
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
        server_default=text("false"),
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
        server_default=text("'active'"),
        default="active",  # Python default needed for validate() before DB insert
        comment="Event lifecycle state",
    )

    # Versioning and sync tracking
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
        comment="Event version for history tracking",
    )

    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last sync from Google (manually set after successful sync, no defaults)",
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
        # Check: event_description length <= 8192 (allow NULL)
        CheckConstraint(
            "(event_description IS NULL) OR (length(event_description) <= 8192)",
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
            postgresql_where=text("status = 'active'"),
        ),
        # Index: composite (user_id, sha256_content_hash) for change detection
        Index("idx_focus_sessions_user_hash", "user_id", "sha256_content_hash"),
        # Index: cleanup job (created_at) WHERE status = 'active'
        Index(
            "idx_focus_sessions_cleanup",
            "created_at",
            postgresql_where=text("status = 'active'"),
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

        # Validate event_description length (Google Calendar limit)
        if self.event_description and len(self.event_description) > 8192:
            raise ValueError("event_description must be <= 8192 characters")

        # Validate timezone awareness (CRITICAL: UTC only, no naive datetimes)
        from datetime import timedelta

        if self.start_time.tzinfo is None or self.start_time.utcoffset() is None:
            raise ValueError("start_time must be timezone-aware (UTC)")
        if self.start_time.utcoffset() != timedelta(0):
            raise ValueError("start_time must be UTC (offset must be 0)")

        if self.end_time.tzinfo is None or self.end_time.utcoffset() is None:
            raise ValueError("end_time must be timezone-aware (UTC)")
        if self.end_time.utcoffset() != timedelta(0):
            raise ValueError("end_time must be UTC (offset must be 0)")

        if self.google_updated_at.tzinfo is None or self.google_updated_at.utcoffset() is None:
            raise ValueError("google_updated_at must be timezone-aware (UTC)")
        if self.google_updated_at.utcoffset() != timedelta(0):
            raise ValueError("google_updated_at must be UTC (offset must be 0)")

        # Validate timing order
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
