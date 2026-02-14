"""Cleanup orphaned columns and tables.

Remove data/columns/tables that are stored but never read:
- pg_weekly_overview table (never written to or read by any service)
- avg_hours_week column from pg_priorities (replaced by avg_target_achievement)
- 7 orphaned columns from pg_weekly_snapshots (event_count, flex_status,
  pacing_status, deadline_date, days_remaining, deliverables_completed,
  deliverables_total)

Revision ID: s9t0u1v2w3x4
Revises: r8m9n0o1p2q3
Create Date: 2026-02-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "s9t0u1v2w3x4"
down_revision = "r8m9n0o1p2q3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 1. Drop pg_weekly_overview table and its trigger
    # -------------------------------------------------------------------------
    op.execute("DROP TRIGGER IF EXISTS trg_pg_weekly_overview_updated_at ON pg_weekly_overview")
    op.drop_table("pg_weekly_overview")

    # -------------------------------------------------------------------------
    # 2. Drop orphaned columns from pg_weekly_snapshots
    # -------------------------------------------------------------------------
    # Drop check constraint first (if it exists)
    op.execute("ALTER TABLE pg_weekly_snapshots DROP CONSTRAINT IF EXISTS ck_pg_weekly_snapshots_event_count_non_negative")

    op.drop_column("pg_weekly_snapshots", "event_count")
    op.drop_column("pg_weekly_snapshots", "flex_status")
    op.drop_column("pg_weekly_snapshots", "pacing_status")
    op.drop_column("pg_weekly_snapshots", "deadline_date")
    op.drop_column("pg_weekly_snapshots", "days_remaining")
    op.drop_column("pg_weekly_snapshots", "deliverables_completed")
    op.drop_column("pg_weekly_snapshots", "deliverables_total")

    # -------------------------------------------------------------------------
    # 3. Drop avg_hours_week from pg_priorities
    # -------------------------------------------------------------------------
    op.drop_column("pg_priorities", "avg_hours_week")


def downgrade() -> None:
    # -------------------------------------------------------------------------
    # 1. Restore avg_hours_week to pg_priorities
    # -------------------------------------------------------------------------
    op.add_column(
        "pg_priorities",
        sa.Column(
            "avg_hours_week",
            sa.Numeric(precision=6, scale=2),
            nullable=True,
            comment="Future: rolling average hours per week",
        ),
    )

    # -------------------------------------------------------------------------
    # 2. Restore orphaned columns to pg_weekly_snapshots
    # -------------------------------------------------------------------------
    op.add_column(
        "pg_weekly_snapshots",
        sa.Column(
            "event_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Number of keyword-matched events",
        ),
    )
    op.add_column(
        "pg_weekly_snapshots",
        sa.Column(
            "flex_status",
            sa.String(20),
            nullable=True,
            comment="Flex status: ahead, on_track, behind (based on 80%/110% thresholds)",
        ),
    )
    op.add_column(
        "pg_weekly_snapshots",
        sa.Column(
            "pacing_status",
            sa.String(20),
            nullable=True,
            comment="Pacing status: on_track, behind, ahead, completed",
        ),
    )
    op.add_column(
        "pg_weekly_snapshots",
        sa.Column(
            "deadline_date",
            sa.Date(),
            nullable=True,
            comment="Priority's deadline at time of snapshot",
        ),
    )
    op.add_column(
        "pg_weekly_snapshots",
        sa.Column(
            "days_remaining",
            sa.Integer(),
            nullable=True,
            comment="Calendar days from week_end to deadline_date",
        ),
    )
    op.add_column(
        "pg_weekly_snapshots",
        sa.Column(
            "deliverables_completed",
            sa.Integer(),
            nullable=True,
            comment="Count of done=true deliverables at snapshot time",
        ),
    )
    op.add_column(
        "pg_weekly_snapshots",
        sa.Column(
            "deliverables_total",
            sa.Integer(),
            nullable=True,
            comment="Total deliverable count at snapshot time",
        ),
    )

    # Restore check constraint
    op.create_check_constraint(
        "ck_pg_weekly_snapshots_event_count_non_negative",
        "pg_weekly_snapshots",
        "event_count >= 0",
    )

    # -------------------------------------------------------------------------
    # 3. Restore pg_weekly_overview table
    # -------------------------------------------------------------------------
    op.create_table(
        "pg_weekly_overview",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
            comment="Internal identifier",
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("core_users.id", ondelete="CASCADE"),
            nullable=False,
            comment="Owner user ID",
        ),
        sa.Column(
            "week_start",
            sa.Date(),
            nullable=False,
            comment="Monday of the reporting week",
        ),
        sa.Column(
            "other_hours",
            sa.Numeric(precision=6, scale=2),
            nullable=True,
            comment="Non-priority hours from calendar (cached during report generation)",
        ),
        sa.Column(
            "semantic_grouping",
            postgresql.JSONB(),
            nullable=True,
            comment="User-confirmed categories: [{category, hours, event_count}, ...]",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="When overview was created",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="When overview was last updated",
        ),
        sa.UniqueConstraint("user_id", "week_start", name="uq_pg_weekly_overview_user_week"),
    )

    # Restore updated_at trigger (uses pg_set_updated_at from o5j6k7l8m9n0)
    op.execute("""
        CREATE TRIGGER trg_pg_weekly_overview_updated_at
        BEFORE UPDATE ON pg_weekly_overview
        FOR EACH ROW
        EXECUTE FUNCTION pg_set_updated_at()
    """)
