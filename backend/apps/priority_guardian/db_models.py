"""
Database models for the Priority Guardian SDK app.

System-level entities (users, connections, etc.) live in backend.core.models.
This module is only for Priority Guardian-specific tables.

Currently:
- PgPriority: User's declared priorities with calendar keyword tracking
- PgDeliverable: Deliverables associated with deadline-type priorities
- PgWeeklySnapshot: Per-priority-per-week snapshot for weekly reports (Inc 06)
- PgWeeklyOverview: Per-user-per-week overview with semantic grouping (Inc 06/07)

Tables use `pg_*` prefix and live in the shared PostgreSQL instance alongside `core_*` tables.
The FK `pg_priorities.user_id → core_users.id` works because they share the same database.
"""

from datetime import datetime, date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    String,
    Integer,
    Date,
    DateTime,
    Boolean,
    Numeric,
    ForeignKey,
    CheckConstraint,
    Index,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from backend.core.models import Base


class PgPriority(Base):
    """
    User's declared priority for time tracking.

    Priority Guardian helps freelancers/solopreneurs protect time for their top 3 priorities.
    Each priority gets a calendar keyword (P1, P2, or P3) assigned by the backend.
    Users tag their Google Calendar events with this keyword so PG knows which hours
    count toward which priority.

    Two priority types exist:
    - deadline: has a hard end date (e.g., "Launch marketing site by March 15")
    - flexible: ongoing time investment toward a 1-month goal (e.g., "Spend 10h/week on client outreach")

    Data Lifecycle:
    - Creation: inserts row, persists until explicitly deleted or retired
    - Edits: update row in place, `updated_at` tracks when
    - Retirement: status = 'retired', retired_at = now(), data retained but frozen
    - Deletion: cascade deletes deliverables, snapshots, checkpoint history

    Aggregate columns (streak_count, avg_hours_week, total_hours_invested) are placeholders
    in Increment 02. They will be populated by weekly reflection tools in later increments.

    GDPR note: No intended PII fields. User-entered text (name, desired_result) may contain
    personal data. Users are instructed not to include sensitive data (UX-level guidance,
    not backend-enforced).
    """

    __tablename__ = "pg_priorities"

    # Primary key (server-generated UUID)
    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
        comment="Internal identifier",
    )

    # Foreign key to core_users.id (same DB - see Shared Database Convention)
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owner user ID",
    )

    # Priority name (user-authored, max 100 chars)
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="User-authored priority name",
    )

    # Priority type: 'deadline' or 'flexible'
    type: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Priority type: deadline or flexible",
    )

    # Calendar keyword assigned by backend (P1, P2, or P3)
    # Never assigned by LLM or client
    calendar_keyword: Mapped[str] = mapped_column(
        String(2),
        nullable=False,
        comment="Assigned calendar keyword (P1, P2, P3)",
    )

    # Status: 'active' or 'retired'
    status: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        server_default=text("'active'"),
        default="active",
        comment="Priority status: active or retired",
    )

    # Deadline (required when type=deadline)
    deadline: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="Hard end date (required for deadline type)",
    )

    # Weekly hour target (required when type=flexible, must be > 0)
    weekly_hour_target: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 2),
        nullable=True,
        comment="Hours per week target (required for flexible type)",
    )

    # Checkpoint date (required when type=flexible)
    checkpoint_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="Evaluation checkpoint ~1 month out (required for flexible type)",
    )

    # Desired result (required when type=flexible, max 200 chars)
    desired_result: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Concrete outcome in ~1 month (required for flexible type)",
    )

    # =========================================================================
    # Future aggregate columns (placeholders in Inc 02 - do NOT read/write)
    # These exist for migration simplicity (avoids future backfill migration)
    # =========================================================================

    streak_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        default=0,
        comment="Future: consecutive weeks meeting target",
    )

    avg_hours_week: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 2),
        nullable=True,
        comment="Future: rolling average hours per week",
    )

    total_hours_invested: Mapped[Decimal] = mapped_column(
        Numeric(8, 2),
        nullable=False,
        server_default=text("0"),
        default=Decimal("0"),
        comment="Future: cumulative hours invested",
    )

    # Retirement timestamp (set when status changes to 'retired')
    retired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When priority was retired",
    )

    # Audit timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When priority was created",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="When priority was last updated",
    )

    # Relationship to deliverables (for eager loading in responses)
    deliverables: Mapped[list["PgDeliverable"]] = relationship(
        "PgDeliverable",
        back_populates="priority",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    # Table-level constraints and indexes
    __table_args__ = (
        # Check constraint: type must be 'deadline' or 'flexible'
        CheckConstraint(
            "type IN ('deadline', 'flexible')",
            name="ck_pg_priorities_type",
        ),
        # Check constraint: calendar_keyword must be P1, P2, or P3
        CheckConstraint(
            "calendar_keyword IN ('P1', 'P2', 'P3')",
            name="ck_pg_priorities_keyword",
        ),
        # Check constraint: status must be 'active' or 'retired'
        CheckConstraint(
            "status IN ('active', 'retired')",
            name="ck_pg_priorities_status",
        ),
        # Partial unique index: one active keyword per user
        # (user_id, calendar_keyword) WHERE status = 'active'
        Index(
            "idx_pg_priorities_user_keyword_active",
            "user_id",
            "calendar_keyword",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
        # Index for user's active priorities
        Index(
            "idx_pg_priorities_user_active",
            "user_id",
            postgresql_where=text("status = 'active'"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<PgPriority id={self.id}, user_id={self.user_id}, "
            f"name={self.name!r}, type={self.type}, keyword={self.calendar_keyword}>"
        )


class PgDeliverable(Base):
    """
    Deliverable associated with a priority.

    Deliverables are added post-onboarding via widget CRUD tools (later increment).
    This table exists for schema completeness in Increment 02.

    Simple binary completion status (done/not done).
    """

    __tablename__ = "pg_deliverables"

    # Primary key (server-generated UUID)
    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
        comment="Internal identifier",
    )

    # Foreign key to pg_priorities.id with CASCADE delete
    priority_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("pg_priorities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Parent priority",
    )

    # Deliverable name (max 200 chars)
    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Deliverable name",
    )

    # Completion status (binary only)
    done: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
        default=False,
        comment="Whether deliverable is completed",
    )

    # Audit timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When deliverable was created",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="When deliverable was last updated",
    )

    # Relationship back to priority
    priority: Mapped["PgPriority"] = relationship(
        "PgPriority",
        back_populates="deliverables",
    )

    def __repr__(self) -> str:
        return (
            f"<PgDeliverable id={self.id}, priority_id={self.priority_id}, "
            f"name={self.name!r}, done={self.done}>"
        )


class PgWeeklySnapshot(Base):
    """
    Per-priority-per-week snapshot for weekly reports.

    Stores deterministic, keyword-matched data at the time of finalization.
    Used for week-over-week comparison and aggregate computation.

    One row per priority per week. Created when a completed week is finalized
    via the get_weekly_report tool. Immutable after creation (no overwrites).

    Deadline-specific fields are null for flexible priorities, and vice versa.
    """

    __tablename__ = "pg_weekly_snapshots"

    # Primary key (server-generated UUID)
    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
        comment="Internal identifier",
    )

    # Foreign keys (denormalized user_id for query efficiency)
    priority_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("pg_priorities.id", ondelete="CASCADE"),
        nullable=False,
        comment="Parent priority",
    )

    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core_users.id", ondelete="CASCADE"),
        nullable=False,
        comment="Owner user ID (denormalized for query efficiency)",
    )

    # Week boundaries
    week_start: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="Monday of the reporting week",
    )

    week_end: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="Sunday of the reporting week (week_start + 6)",
    )

    # Core metrics (all priority types)
    actual_hours: Mapped[Decimal] = mapped_column(
        Numeric(6, 2),
        nullable=False,
        comment="Keyword-matched hours for this priority this week",
    )

    event_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Number of keyword-matched events",
    )

    # Deadline-specific fields (nullable for flexible priorities)
    deadline_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
        comment="Priority's deadline at time of snapshot",
    )

    days_remaining: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Calendar days from week_end to deadline_date",
    )

    deliverables_completed: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Count of done=true deliverables at snapshot time",
    )

    deliverables_total: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Total deliverable count at snapshot time",
    )

    pacing_status: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Pacing status: on_track, behind, ahead, completed",
    )

    # Flexible-specific fields (nullable for deadline priorities)
    target_hours: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 2),
        nullable=True,
        comment="weekly_hour_target at time of snapshot",
    )

    flex_status: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Flex status: ahead, on_track, behind (based on 80%/110% thresholds)",
    )

    streak_at_snapshot: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="streak_count value AFTER this week's update",
    )

    # Audit timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When snapshot was saved",
    )

    # Relationship to priority
    priority: Mapped["PgPriority"] = relationship(
        "PgPriority",
        foreign_keys=[priority_id],
    )

    # Table-level constraints (indexes and unique constraint defined in migration)
    __table_args__ = (
        CheckConstraint(
            "actual_hours >= 0",
            name="ck_pg_weekly_snapshots_actual_hours_non_negative",
        ),
        CheckConstraint(
            "event_count >= 0",
            name="ck_pg_weekly_snapshots_event_count_non_negative",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<PgWeeklySnapshot id={self.id}, priority_id={self.priority_id}, "
            f"week_start={self.week_start}, actual_hours={self.actual_hours}>"
        )


class PgWeeklyOverview(Base):
    """
    Per-user-per-week overview with semantic grouping.

    Stores user-week-level data that doesn't belong on per-priority snapshot rows.
    The semantic_grouping column holds user-confirmed categories for non-priority time.

    Created empty in Inc 06. Populated by Inc 07's save_semantic_grouping tool via UPSERT.
    No rows created by weekly report save - rows only exist when semantic grouping is saved.

    Shape of semantic_grouping:
    [{"category": "Client calls", "hours": 8.5, "event_count": 12}, ...]
    """

    __tablename__ = "pg_weekly_overview"

    # Primary key (server-generated UUID)
    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
        comment="Internal identifier",
    )

    # Foreign key
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core_users.id", ondelete="CASCADE"),
        nullable=False,
        comment="Owner user ID",
    )

    # Week identifier
    week_start: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="Monday of the reporting week",
    )

    # Semantic grouping (populated by Inc 07's save_semantic_grouping tool)
    semantic_grouping: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="User-confirmed categories: [{category, hours, event_count}, ...]",
    )

    # Audit timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When overview was created",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="When overview was last updated",
    )

    # Note: Unique constraint (user_id, week_start) defined in migration

    def __repr__(self) -> str:
        has_grouping = self.semantic_grouping is not None
        return (
            f"<PgWeeklyOverview id={self.id}, user_id={self.user_id}, "
            f"week_start={self.week_start}, has_grouping={has_grouping}>"
        )
