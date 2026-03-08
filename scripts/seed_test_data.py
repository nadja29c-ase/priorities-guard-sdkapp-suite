#!/usr/bin/env python3
"""
Priority Guardian — P1 Seed Script

Inserts only P1 (Launch client website) + deliverables + 4 weeks of snapshots.
P2 and P3 already exist in production — this script does not touch them.

Usage:
    python scripts/seed_test_data.py --db-url "postgresql+psycopg2://..." --dry-run
    python scripts/seed_test_data.py --db-url "postgresql+psycopg2://..."
"""

import argparse
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

TEST_USER_ID = "830a6673-d71b-4967-abbd-25357e3319db"

P1_ID = str(uuid4())

P1 = {
    "id": P1_ID,
    "name": "Launch client website",
    "type": "deadline",
    "calendar_keyword": "P1",
    "deadline": date(2026, 4, 15),
    "weekly_hour_target": None,
    "checkpoint_date": None,
    "streak_count": 0,
    "total_hours_invested": Decimal("29.5"),
    "avg_target_achievement": None,
    "deliverables": [
        {"name": "Clarify scope and sign contract", "done": True},
        {"name": "Collect brand assets and content", "done": True},
        {"name": "Design mockups approved by client", "done": True},
        {"name": "Build out all pages", "done": False},
        {"name": "Connect domain and configure hosting", "done": False},
        {"name": "Client review and feedback round", "done": False},
        {"name": "Fix revisions and final sign-off", "done": False},
        {"name": "Go live", "done": False},
    ],
}

# Snapshots for P1 only
# Week totals (other_hours, total_tracked_hours) are denormalized per week —
# they must match the values already stored in P2/P3 snapshots for the same weeks.
# If P2/P3 snapshots don't exist yet either, these values are consistent with the full dataset.
P1_SNAPSHOTS = [
    {
        "week_start": date(2026, 2, 9),
        "week_end":   date(2026, 2, 15),
        "actual_hours": Decimal("8.0"),
        "target_hours": None,
        "streak_at_snapshot": 0,
        "other_hours": Decimal("18.0"),
        "total_tracked_hours": Decimal("34.0"),
    },
    {
        "week_start": date(2026, 2, 16),
        "week_end":   date(2026, 2, 22),
        "actual_hours": Decimal("7.0"),
        "target_hours": None,
        "streak_at_snapshot": 0,
        "other_hours": Decimal("27.5"),
        "total_tracked_hours": Decimal("43.0"),
    },
    {
        "week_start": date(2026, 2, 23),
        "week_end":   date(2026, 3, 1),
        "actual_hours": Decimal("9.5"),
        "target_hours": None,
        "streak_at_snapshot": 0,
        "other_hours": Decimal("20.5"),
        "total_tracked_hours": Decimal("35.5"),
    },
    {
        "week_start": date(2026, 3, 2),
        "week_end":   date(2026, 3, 8),
        "actual_hours": Decimal("5.0"),
        "target_hours": None,
        "streak_at_snapshot": 0,
        "other_hours": Decimal("11.0"),
        "total_tracked_hours": Decimal("19.0"),
    },
]


def seed(session: Session, dry_run: bool = False):
    now = datetime.now(timezone.utc)
    label = "[DRY RUN] " if dry_run else ""
    print(f"\n{label}Seeding P1 for user: {TEST_USER_ID}\n")

    # Verify user exists
    result = session.execute(
        text("SELECT id FROM core_users WHERE id = :uid"),
        {"uid": TEST_USER_ID}
    ).fetchone()
    if not result:
        print(f"ERROR: User {TEST_USER_ID} not found. Aborting.")
        sys.exit(1)
    print("✓ User exists")

    # Guard: P1 keyword must not already be active
    existing = session.execute(
        text("SELECT id FROM pg_priorities WHERE user_id = :uid AND calendar_keyword = 'P1' AND status = 'active'"),
        {"uid": TEST_USER_ID}
    ).fetchone()
    if existing:
        print("WARNING: Active P1 already exists. Aborting to avoid conflict.")
        print("Delete it first:\n  DELETE FROM pg_priorities WHERE user_id = '830a6673-d71b-4967-abbd-25357e3319db' AND calendar_keyword = 'P1';")
        sys.exit(1)

    # Insert P1
    print(f"\n  → [P1] {P1['name']} (deadline: {P1['deadline']})")
    if not dry_run:
        session.execute(
            text("""
                INSERT INTO pg_priorities (
                    id, user_id, name, type, calendar_keyword, status,
                    deadline, weekly_hour_target, checkpoint_date,
                    streak_count, total_hours_invested, avg_target_achievement,
                    retired_at, created_at, updated_at
                ) VALUES (
                    :id, :user_id, :name, :type, :calendar_keyword, 'active',
                    :deadline, NULL, NULL,
                    :streak_count, :total_hours_invested, NULL,
                    NULL, :now, :now
                )
            """),
            {
                "id": P1["id"], "user_id": TEST_USER_ID,
                "name": P1["name"], "type": P1["type"],
                "calendar_keyword": P1["calendar_keyword"],
                "deadline": P1["deadline"],
                "streak_count": P1["streak_count"],
                "total_hours_invested": P1["total_hours_invested"],
                "now": now,
            }
        )
        print(f"    ✓ Priority inserted (id={P1['id']})")

    # Insert deliverables
    for d in P1["deliverables"]:
        print(f"    → Deliverable: '{d['name']}' (done={d['done']})")
        if not dry_run:
            session.execute(
                text("INSERT INTO pg_deliverables (id, priority_id, name, done, created_at, updated_at) VALUES (:id, :pid, :name, :done, :now, :now)"),
                {"id": str(uuid4()), "pid": P1["id"], "name": d["name"], "done": d["done"], "now": now}
            )

    # Insert snapshots
    print(f"\n  → Snapshots:")
    for s in P1_SNAPSHOTS:
        print(f"    {s['week_start']} | actual={s['actual_hours']}h")
        if not dry_run:
            session.execute(
                text("""
                    INSERT INTO pg_weekly_snapshots (
                        id, priority_id, user_id, week_start, week_end,
                        actual_hours, target_hours, streak_at_snapshot,
                        calendar_keyword_at_snapshot, other_hours, total_tracked_hours, created_at
                    ) VALUES (
                        :id, :priority_id, :user_id, :week_start, :week_end,
                        :actual_hours, NULL, :streak_at_snapshot,
                        'P1', :other_hours, :total_tracked_hours, :now
                    )
                    ON CONFLICT (priority_id, week_start) DO NOTHING
                """),
                {
                    "id": str(uuid4()), "priority_id": P1["id"],
                    "user_id": TEST_USER_ID,
                    "week_start": s["week_start"], "week_end": s["week_end"],
                    "actual_hours": s["actual_hours"],
                    "streak_at_snapshot": s["streak_at_snapshot"],
                    "other_hours": s["other_hours"],
                    "total_tracked_hours": s["total_tracked_hours"],
                    "now": now,
                }
            )

    if not dry_run:
        session.commit()
        print("\n✓ P1 committed.\n")
    else:
        print("\n[DRY RUN COMPLETE] No writes performed.\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-url", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    engine = create_engine(args.db_url, echo=False)
    with Session(engine) as session:
        seed(session, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
