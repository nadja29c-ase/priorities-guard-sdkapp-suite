"""
Database models for the Priority Guardian SDK app.

System-level entities (users, connections, etc.) live in backend.core.models.
This module is only for Priority Guardian-specific tables.

Currently:
- PgPriority: User's declared priorities with calendar keyword tracking and running aggregates
- PgDeliverable: Deliverables associated with deadline-type priorities
- PgWeeklySnapshot: Per-priority weekly data point for running aggregate computation

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
    UniqueConstraint,
    Index,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
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

    Aggregate columns (streak_count, avg_target_achievement, total_hours_invested) are
    updated by snapshot_service when weekly snapshots are finalized.

    GDPR note: No intended PII fields. User-entered text (name, goals) may contain
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

    # Calendar keyword (P1, P2, or P3)
    # User-chosen on creation or reassignable via update
    calendar_keyword: Mapped[str | None] = mapped_column(
        String(2),
        nullable=True,  # Allows NULL as transient state during keyword reassignment
        comment="Calendar keyword (P1, P2, P3). Nullable only as transient state during keyword reassignment.",
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

    # NOTE: desired_result was removed in Inc D - replaced by pg_goals table

    # =========================================================================
    # Aggregate columns (updated by snapshot_service)
    # =========================================================================

    streak_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        default=0,
        comment="Consecutive weeks with hours > 0 (binary streak rule, see ADR-001)",
    )

    total_hours_invested: Mapped[Decimal] = mapped_column(
        Numeric(8, 2),
        nullable=False,
        server_default=text("0"),
        default=Decimal("0"),
        comment="Cumulative hours invested across all snapshotted weeks",
    )

    avg_target_achievement: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 2),
        nullable=True,
        comment="Average % of weekly target achieved across all snapshotted weeks. NULL when no valid snapshots exist.",
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
        order_by="PgDeliverable.created_at",
    )

    # Relationship to goals (for eager loading in responses)
    goals: Mapped[list["PgGoal"]] = relationship(
        "PgGoal",
        back_populates="priority",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="PgGoal.created_at",
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
        # Check constraint: type-field consistency
        # Deadline: must have deadline, must NOT have weekly_hour_target or checkpoint_date
        # Flexible: must have weekly_hour_target and checkpoint_date, must NOT have deadline
        CheckConstraint(
            "("
            "(type = 'deadline' AND deadline IS NOT NULL AND weekly_hour_target IS NULL AND checkpoint_date IS NULL) "
            "OR "
            "(type = 'flexible' AND weekly_hour_target IS NOT NULL AND checkpoint_date IS NOT NULL AND deadline IS NULL)"
            ")",
            name="ck_pg_priorities_type_field_consistency",
        ),
        # Check constraint: weekly_hour_target must be positive when set
        CheckConstraint(
            "weekly_hour_target IS NULL OR weekly_hour_target > 0",
            name="ck_pg_priorities_weekly_target_positive",
        ),
        # Check constraint: retirement consistency
        # Active must have retired_at=NULL, retired must have retired_at set
        CheckConstraint(
            "(status = 'active' AND retired_at IS NULL) OR (status = 'retired' AND retired_at IS NOT NULL)",
            name="ck_pg_priorities_retirement_consistency",
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


class PgGoal(Base):
    """
    Goal associated with a flexible priority.

    Goals are the 1-3 concrete outcomes a user wants to achieve by their
    checkpoint date. Unlike the single desired_result string, goals can be
    individually toggled as achieved.

    Maximum 3 goals per flexible priority (enforced at API layer).
    """

    __tablename__ = "pg_goals"

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

    # Goal text (max 200 chars)
    goal_text: Mapped[str] = mapped_column(
        "text",  # Column name in DB stays "text"
        String(200),
        nullable=False,
        comment="Goal text",
    )

    # Achievement status (binary only)
    achieved: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
        default=False,
        comment="Whether goal is achieved",
    )

    # Audit timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When goal was created",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="When goal was last updated",
    )

    # Relationship back to priority
    priority: Mapped["PgPriority"] = relationship(
        "PgPriority",
        back_populates="goals",
    )

    def __repr__(self) -> str:
        return (
            f"<PgGoal id={self.id}, priority_id={self.priority_id}, "
            f"text={self.goal_text!r}, achieved={self.achieved}>"
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
    Per-priority weekly data point for historical reports and aggregate computation.

    One row per priority per completed week. Created opportunistically on dashboard
    load via ensure_snapshots_up_to_date(). Immutable after creation (INSERT ON
    CONFLICT DO NOTHING).

    Used by:
    - snapshot_service._update_aggregates() to compute streak_count, total_hours_invested,
      avg_target_achievement on pg_priorities
    - weekly_report_service._build_report_from_snapshots() for past week reports

    The calendar_keyword_at_snapshot field captures the keyword at snapshot creation time,
    enabling accurate past-week reports even after keyword reassignments.

    Denormalized fields (same value across all snapshots for a week):
    - other_hours: Untagged calendar hours for this week
    - total_tracked_hours: Total tracked hours (all events) for this week
    These enable accurate pie charts for historical weeks.
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

    # Core metric
    actual_hours: Mapped[Decimal] = mapped_column(
        Numeric(6, 2),
        nullable=False,
        comment="Keyword-matched hours for this priority this week",
    )

    # Flexible-specific field
    target_hours: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 2),
        nullable=True,
        comment="weekly_hour_target at time of snapshot",
    )

    streak_at_snapshot: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="streak_count value AFTER this week's update",
    )

    calendar_keyword_at_snapshot: Mapped[str | None] = mapped_column(
        String(2),
        nullable=True,
        comment="Calendar keyword (P1/P2/P3) at time of snapshot creation. NULL for pre-migration snapshots.",
    )

    # Denormalized per-week values (same across all snapshots for a given week)
    other_hours: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 2),
        nullable=True,
        comment="Untagged calendar hours for this week. Same value across all snapshots in the same week. NULL for pre-migration snapshots.",
    )

    total_tracked_hours: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 2),
        nullable=True,
        comment="Total tracked hours (all events) for this week. Same value across all snapshots in the same week. NULL for pre-migration snapshots.",
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

    # Table-level constraints
    __table_args__ = (
        UniqueConstraint(
            "priority_id", "week_start",
            name="uq_pg_weekly_snapshots_priority_week",
        ),
        CheckConstraint(
            "actual_hours >= 0",
            name="ck_pg_weekly_snapshots_actual_hours_non_negative",
        ),
        # Check constraint: week_end must be exactly week_start + 6 days
        # PostgreSQL: DATE + integer returns DATE
        CheckConstraint(
            "week_end = week_start + 6",
            name="ck_pg_weekly_snapshots_week_consistency",
        ),
        # Check constraint: target_hours must be non-negative when set
        CheckConstraint(
            "target_hours IS NULL OR target_hours >= 0",
            name="ck_pg_weekly_snapshots_target_hours_non_negative",
        ),
        # Check constraint: week_start must be a Monday (ISODOW 1 = Monday)
        CheckConstraint(
            "EXTRACT(ISODOW FROM week_start) = 1",
            name="ck_pg_weekly_snapshots_week_start_monday",
        ),
        # Check constraint: other_hours must be non-negative when set
        CheckConstraint(
            "other_hours IS NULL OR other_hours >= 0",
            name="ck_pg_weekly_snapshots_other_hours_non_negative",
        ),
        # Check constraint: total_tracked_hours must be non-negative when set
        CheckConstraint(
            "total_tracked_hours IS NULL OR total_tracked_hours >= 0",
            name="ck_pg_weekly_snapshots_total_hours_non_negative",
        ),
        # Check constraint: calendar_keyword_at_snapshot must be valid domain (P1/P2/P3 or NULL)
        CheckConstraint(
            "calendar_keyword_at_snapshot IS NULL OR calendar_keyword_at_snapshot IN ('P1', 'P2', 'P3')",
            name="ck_pg_weekly_snapshots_calendar_keyword_at_snapshot",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<PgWeeklySnapshot id={self.id}, priority_id={self.priority_id}, "
            f"week_start={self.week_start}, actual_hours={self.actual_hours}>"
        )
