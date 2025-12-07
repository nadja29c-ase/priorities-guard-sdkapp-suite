"""
Database models for the Focused SDK app.

System-level entities (users, connections, etc.) live in backend.core.models.
This module is only for Focused-specific tables.

Currently:
- FocusedUserKeyword: custom focus keywords added by a user
- FocusedFocusSession: calendar events with focus block detection + focus mode tracking
- FocusedScheduledJob: scheduled Celery tasks (auto-deactivation, etc.)

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
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID, JSONB
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

    Increment 11 additions:
    - actual_start: When user activated focus mode
    - actual_end: When user deactivated focus mode
    - trigger_source: 'calendar' (from detected event) or 'user' (manual)
    - google_event_id/google_ical_uid now nullable (for manual sessions)

    Example (calendar-triggered):
        session = FocusedFocusSession(
            user_id=UUID("..."),
            google_event_id="abc123",
            google_calendar_id="primary",
            event_summary="Deep Work Session",
            google_updated_at=datetime.now(timezone.utc),
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc) + timedelta(hours=2),
            is_focus_block=True,
            matched_keyword="deep work",
            sha256_content_hash="...",
            google_ical_uid="abc123@google.com",
            trigger_source="calendar",
        )

    Example (manual):
        session = FocusedFocusSession(
            user_id=UUID("..."),
            google_event_id=None,  # Manual session
            google_calendar_id="primary",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc) + timedelta(hours=2),
            is_focus_block=True,
            sha256_content_hash="...",
            google_ical_uid=None,  # Manual session
            trigger_source="user",
            actual_start=datetime.now(timezone.utc),
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
    # NOTE: Nullable for manual sessions (trigger_source='user')
    google_event_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Google's event.id (NULL for manual sessions)",
    )

    google_calendar_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default=text("'primary'"),
        comment="Calendar source",
    )

    # NOTE: Nullable for manual sessions (trigger_source='user')
    google_ical_uid: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="iCalendar UID (NULL for manual sessions)",
    )

    google_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Google's last modified timestamp (NULL for manual sessions)",
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

    # =========================================================================
    # Increment 11: Focus Mode Activation Tracking
    # =========================================================================

    # the real timestamp when Focus Mode entered ACTIVE state on the device
    actual_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When user actually activated focus mode (UTC)",
    )

    # the real timestamp when Focus Mode exited ACTIVE state on the device
    actual_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When user deactivated focus mode (UTC)",
    )

    # How the focus session was triggered
    trigger_source: Mapped[str | None] = mapped_column(
        Enum("calendar", "user", name="trigger_source_enum", create_type=False),
        nullable=True,
        comment="How the focus session was triggered ('calendar' or 'user')",
    )

    # =========================================================================
    # Audit timestamps
    # =========================================================================

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
        # Unique constraint: one row per (user, ical_uid, start_time)
        # This correctly handles recurring events where all instances share
        # the same google_event_id but have different start times.
        # Google Calendar API: iCalUID + start_time uniquely identifies an instance.
        # NOTE: Only applies to calendar-triggered sessions (google_ical_uid NOT NULL)
        UniqueConstraint(
            "user_id",
            "google_ical_uid",
            "start_time",
            name="uq_focus_sessions_user_ical_start",
        ),
        # Keep index on google_event_id for lookup queries (not uniqueness)
        Index("idx_focus_sessions_event_id", "google_event_id"),
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
        # Index: active focus sessions (Increment 11)
        Index(
            "idx_focus_sessions_active",
            "user_id",
            postgresql_where=text("actual_start IS NOT NULL AND actual_end IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<FocusedFocusSession id={self.id}, user_id={self.user_id}, "
            f"google_event_id={self.google_event_id!r}, is_focus_block={self.is_focus_block}, "
            f"trigger_source={self.trigger_source}>"
        )

    def validate(self) -> None:
        """
        Validate model constraints.

        Raises:
            ValueError: If validation fails
        """
        from datetime import timedelta

        # For calendar-triggered sessions, Google fields are required
        if self.trigger_source == "calendar":
            if not self.google_event_id or len(self.google_event_id) > 255:
                raise ValueError(
                    "google_event_id must be 1-255 characters for calendar-triggered sessions"
                )
            if not self.google_ical_uid or len(self.google_ical_uid) > 255:
                raise ValueError(
                    "google_ical_uid is required for calendar-triggered sessions"
                )
            if not self.google_updated_at:
                raise ValueError(
                    "google_updated_at is required for calendar-triggered sessions"
                )

        # For manual sessions, Google fields should be NULL
        if self.trigger_source == "user":
            if self.google_event_id is not None:
                raise ValueError(
                    "google_event_id must be NULL for manual sessions"
                )
            if self.google_ical_uid is not None:
                raise ValueError(
                    "google_ical_uid must be NULL for manual sessions"
                )

        # Validate event_description length (Google Calendar limit)
        if self.event_description and len(self.event_description) > 8192:
            raise ValueError("event_description must be <= 8192 characters")

        # Validate timezone awareness (CRITICAL: UTC only, no naive datetimes)
        if self.start_time.tzinfo is None or self.start_time.utcoffset() is None:
            raise ValueError("start_time must be timezone-aware (UTC)")
        if self.start_time.utcoffset() != timedelta(0):
            raise ValueError("start_time must be UTC (offset must be 0)")

        if self.end_time.tzinfo is None or self.end_time.utcoffset() is None:
            raise ValueError("end_time must be timezone-aware (UTC)")
        if self.end_time.utcoffset() != timedelta(0):
            raise ValueError("end_time must be UTC (offset must be 0)")

        if self.google_updated_at:
            if self.google_updated_at.tzinfo is None or self.google_updated_at.utcoffset() is None:
                raise ValueError("google_updated_at must be timezone-aware (UTC)")
            if self.google_updated_at.utcoffset() != timedelta(0):
                raise ValueError("google_updated_at must be UTC (offset must be 0)")

        if self.actual_start:
            if self.actual_start.tzinfo is None or self.actual_start.utcoffset() is None:
                raise ValueError("actual_start must be timezone-aware (UTC)")
            if self.actual_start.utcoffset() != timedelta(0):
                raise ValueError("actual_start must be UTC (offset must be 0)")

        if self.actual_end:
            if self.actual_end.tzinfo is None or self.actual_end.utcoffset() is None:
                raise ValueError("actual_end must be timezone-aware (UTC)")
            if self.actual_end.utcoffset() != timedelta(0):
                raise ValueError("actual_end must be UTC (offset must be 0)")

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

        # Validate trigger_source
        if self.trigger_source and self.trigger_source not in ("calendar", "user"):
            raise ValueError("trigger_source must be 'calendar' or 'user'")

    def is_active(self) -> bool:
        """Check if focus mode is currently active for this session."""
        return self.actual_start is not None and self.actual_end is None


class FocusedScheduledJob(Base):
    """
    Scheduled Celery tasks for the Focused app.

    Used for:
    - Focus mode activation (Increment 20)
    - Auto-deactivation of focus mode after duration expires
    - Webhook renewal tasks
    - Other time-based background jobs

    Status meanings:
    - pending: waiting for Celery to fire
    - running: task executing
    - pending_notification: URL generated, awaiting notify_user (Increment 21)
    - pending_confirmation: user has auto=false, must initiate via ChatGPT
    - completed: user tapped notification, Focus Mode activated
    - failed: error during processing
    - cancelled: event deleted/changed before firing
    - skipped: user already had active focus session

    Retention: Jobs with status 'completed', 'failed', 'cancelled', or 'skipped'
    are deleted after 7 days by a cleanup task.

    Example (activation job):
        job = FocusedScheduledJob(
            user_id=UUID("..."),
            job_type="activation",
            event_id=session.id,
            event_start_time=session.start_time,
            scheduled_at=session.start_time - timedelta(minutes=10),
        )

    Example (deactivation job):
        job = FocusedScheduledJob(
            user_id=UUID("..."),
            job_type="focus_deactivate",
            scheduled_at=datetime.now(timezone.utc) + timedelta(hours=2),
            payload={"session_id": str(session.id)},
        )
    """

    __tablename__ = "focused_scheduled_jobs"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
        comment="Internal identifier",
    )

    # Foreign key to core_users
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core_users.id", ondelete="CASCADE"),
        nullable=False,
        comment="User who owns this job",
    )

    # Job type (Increment 20: added 'activation')
    job_type: Mapped[str] = mapped_column(
        Enum(
            "focus_deactivate", "webhook_renewal", "activation",
            name="job_type_enum", create_type=False
        ),
        nullable=False,
        comment="Type of scheduled job",
    )

    # When the job should execute
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When the job should execute (UTC)",
    )

    # Job status (Increment 20: added running, pending_notification, pending_confirmation, skipped)
    status: Mapped[str] = mapped_column(
        Enum(
            "pending", "running", "pending_notification", "pending_confirmation",
            "completed", "failed", "cancelled", "skipped",
            name="job_status_enum", create_type=False
        ),
        nullable=False,
        server_default=text("'pending'"),
        default="pending",
        comment="Current job status",
    )

    # Celery task ID for tracking
    celery_task_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Celery task ID for this job",
    )

    # =========================================================================
    # Increment 20: Activation job fields
    # =========================================================================

    # event_id: FK to focused_focus_sessions (NULL for webhook_renewal jobs)
    event_id: Mapped[UUID | None] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("focused_focus_sessions.id", ondelete="CASCADE"),
        nullable=True,
        comment="Focus session this job relates to (NULL for webhook_renewal)",
    )

    # event_start_time: for idempotency (calendar event start time)
    event_start_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Calendar event start time (for idempotency constraint)",
    )

    # shortcut_url: generated URL for notification delivery
    shortcut_url: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="Generated shortcut URL for notification",
    )

    # error_reason: failure details
    error_reason: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="Error details if job failed",
    )

    # =========================================================================
    # Legacy fields (kept for backward compatibility)
    # =========================================================================

    # Retry tracking
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        default=0,
        comment="Number of retry attempts",
    )

    # Job-specific payload (e.g., session_id for deactivation)
    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        default=dict,
        comment="Job-specific parameters (session_id, etc.)",
    )

    # Audit timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When job was created",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="When job was last updated",
    )

    # Table-level indexes
    __table_args__ = (
        # Index for finding pending jobs by scheduled time
        Index(
            "idx_scheduled_jobs_pending",
            "scheduled_at",
            postgresql_where=text("status = 'pending'"),
        ),
        # Index for cleanup (find old completed/failed/cancelled jobs)
        Index(
            "idx_scheduled_jobs_cleanup",
            "updated_at",
            postgresql_where=text("status IN ('completed', 'failed', 'cancelled')"),
        ),
        # Index for user's jobs
        Index("idx_scheduled_jobs_user", "user_id", "status"),
        # Index for event lookups (Increment 20)
        Index(
            "idx_scheduled_jobs_event",
            "event_id",
            postgresql_where=text("event_id IS NOT NULL"),
        ),
        # Note: Unique constraint uq_scheduled_jobs_activation is created in migration
        # as a partial unique index (user_id, event_id, job_type, event_start_time)
        # WHERE event_id IS NOT NULL
    )

    def __repr__(self) -> str:
        return (
            f"<FocusedScheduledJob id={self.id}, user_id={self.user_id}, "
            f"job_type={self.job_type}, status={self.status}, "
            f"scheduled_at={self.scheduled_at}>"
        )

    def validate(self) -> None:
        """
        Validate model constraints.

        Raises:
            ValueError: If validation fails
        """
        from datetime import timedelta

        # Validate job_type
        valid_job_types = ("focus_deactivate", "webhook_renewal", "activation")
        if self.job_type not in valid_job_types:
            raise ValueError(f"job_type must be one of {valid_job_types}")

        # Validate status
        valid_statuses = (
            "pending", "running", "pending_notification", "pending_confirmation",
            "completed", "failed", "cancelled", "skipped"
        )
        if self.status not in valid_statuses:
            raise ValueError(f"status must be one of {valid_statuses}")

        # Validate scheduled_at is timezone-aware UTC
        if self.scheduled_at.tzinfo is None or self.scheduled_at.utcoffset() is None:
            raise ValueError("scheduled_at must be timezone-aware (UTC)")
        if self.scheduled_at.utcoffset() != timedelta(0):
            raise ValueError("scheduled_at must be UTC (offset must be 0)")

        # Validate event_start_time if provided
        if self.event_start_time:
            if self.event_start_time.tzinfo is None or self.event_start_time.utcoffset() is None:
                raise ValueError("event_start_time must be timezone-aware (UTC)")
            if self.event_start_time.utcoffset() != timedelta(0):
                raise ValueError("event_start_time must be UTC (offset must be 0)")

        # Activation jobs require event_id and event_start_time
        if self.job_type == "activation":
            if not self.event_id:
                raise ValueError("event_id is required for activation jobs")
            if not self.event_start_time:
                raise ValueError("event_start_time is required for activation jobs")

        # Validate retry_count is non-negative
        if self.retry_count < 0:
            raise ValueError("retry_count must be >= 0")

        # Validate payload is a dict
        if not isinstance(self.payload, dict):
            raise ValueError("payload must be a dictionary")


class FocusedConsentPreferences(Base):
    """
    User preferences for automatic focus mode handling (Increment 20).

    Controls how the system responds to detected focus blocks:
    - auto_handle_focus_blocks: If true, send push notification automatically
      when a focus block is about to start. If false, user must initiate via ChatGPT.
    - always_confirm_duration: If true, always ask user to confirm focus session duration.

    Note: auto_handle_focus_blocks=true means "send notification automatically",
    NOT "activate Focus Mode without user interaction" (iOS prevents that).

    Example:
        prefs = FocusedConsentPreferences(
            user_id=UUID("..."),
            auto_handle_focus_blocks=True,
            always_confirm_duration=False,
        )
    """

    __tablename__ = "focused_consent_preferences"

    # Primary key (user_id is both PK and FK - one row per user)
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core_users.id", ondelete="CASCADE"),
        primary_key=True,
        comment="User these preferences belong to",
    )

    # auto_handle_focus_blocks: if true, send push notification automatically
    auto_handle_focus_blocks: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
        default=False,
        comment="If true, send push notification when focus block starts",
    )

    # always_confirm_duration: if true, always ask user to confirm duration
    always_confirm_duration: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
        default=True,
        comment="If true, always ask user to confirm focus session duration",
    )

    # Audit timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When preferences were created",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="When preferences were last updated",
    )

    def __repr__(self) -> str:
        return (
            f"<FocusedConsentPreferences user_id={self.user_id}, "
            f"auto_handle_focus_blocks={self.auto_handle_focus_blocks}>"
        )
