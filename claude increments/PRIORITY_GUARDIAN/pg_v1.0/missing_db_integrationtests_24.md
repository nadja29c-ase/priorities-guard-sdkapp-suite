Real-DB integration tests: snapshot creation, streak computation, and aggregate updates
Context: The snapshot service (ensure_snapshots_up_to_date / _create_snapshots_for_week) is the core write path that all downstream features depend on (weekly reports, pattern recognition). Currently tested only with mocked DB sessions. This adds real-PostgreSQL integration tests to verify the actual SQL: INSERT ON CONFLICT, streak subquery, and aggregate UPDATE statements.
File: Create tests/integration/priority_guardian/test_snapshot_creation_db.py
Test harness: Use existing conftest fixtures: async_session (real PostgreSQL with auto-cleanup). Follow the pattern in test_db_integrity.py and test_snapshot_weekly_report.py — create CoreUser, PgPriority via ORM, then call the service function directly.
Testing strategy: Tests 1–9 test _create_snapshots_for_week directly — it contains all the DB write logic (INSERT ON CONFLICT, streak query, aggregate UPDATE) and internally checks priority_eligible_for_week. Test 10 tests ensure_snapshots_up_to_date for the multi-week backfill scenario, which requires the full orchestration setup.
External mocking boundary: Only mock list_events (Google Calendar API), compute_week_boundaries, and to_rfc3339 (these feed into the mocked list_events — their correctness is covered by their own unit tests). For Test 10, also mock ensure_valid_access_token, get_user_timezone, and _compute_target_weeks to control which weeks are processed. Everything else — INSERT, streak query, aggregate UPDATE — runs against real PostgreSQL.
For list_events, return controlled event lists that produce known allocations via compute_allocation_from_events (which runs real).
Decimal precision: All assertions on Numeric columns (actual_hours, total_hours_invested, avg_target_achievement) should compare against Decimal values or use pytest.approx() for float comparisons. Do not assert float equality directly.
New class: TestSnapshotCreationDB
Test 1: Basic snapshot creation — single priority, single week.

Create CoreUser + PgPriority (flexible, P1, created_at well before the test week, weekly_hour_target=10.0).
Mock list_events to return events with P1-tagged hours (e.g., 5h).
Call _create_snapshots_for_week(user_id, week_start, "UTC", [priority], "token", session, http_client, log).
Query pg_weekly_snapshots directly — assert 1 row exists with correct priority_id, week_start, actual_hours=Decimal("5.00"), target_hours=Decimal("10.00"), calendar_keyword_at_snapshot="P1", correct other_hours and total_tracked_hours.
Query pg_priorities — assert streak_count=1, total_hours_invested=Decimal("5.00").

Test 2: Streak continuation across two consecutive weeks.

Create user + priority.
Call _create_snapshots_for_week for week 1 (with hours > 0). Verify streak_at_snapshot=1.
Call _create_snapshots_for_week for week 2 (with hours > 0). Verify streak_at_snapshot=2.
Query priority — assert streak_count=2.

Test 3: Streak broken by zero-hour week.

Create user + priority.
Create snapshot for week 1 with hours > 0 (streak=1).
Call _create_snapshots_for_week for week 2 with 0 hours (mock list_events returns no P1 events).
Verify streak_at_snapshot=0.
Query priority — assert streak_count=0.

Test 4: Idempotency — calling twice for same week creates no duplicate.

Create user + priority.
Call _create_snapshots_for_week twice for the same week with same data.
Query pg_weekly_snapshots with COUNT(*) — assert exactly 1 row (ON CONFLICT DO NOTHING).
Verify function returns True first call, False second call.

Test 5: Partial week skipped — priority created mid-week.

Create user + priority with created_at on Thursday of the test week.
Pass the priority in the list to _create_snapshots_for_week for that week.
Query pg_weekly_snapshots with COUNT(*) — assert 0 rows. _create_snapshots_for_week internally calls priority_eligible_for_week and skips it.
Verify function returns False.

Test 6: Multiple priorities — each gets its own snapshot with correct keyword hours.

Create user + 2 priorities (P1 flexible, P2 deadline).
Mock list_events to return events: P1 gets 5h, P2 gets 3h, Other gets 2h.
Call _create_snapshots_for_week.
Query snapshots — assert 2 rows with correct actual_hours per keyword.
Both snapshots have same other_hours and total_tracked_hours (denormalized).

Test 7: Aggregate avg_target_achievement computed correctly after 2 weeks.

Create user + flexible priority (target=10h).
Create snapshots for 2 weeks: week 1 = 8h (80%), week 2 = 12h (120%).
Query priority — avg_target_achievement should be pytest.approx(100.0) or Decimal("100.00") depending on column precision.
Verify total_hours_invested = Decimal("20.00").

Test 8: Deadline priority — target_hours is NULL in snapshot.

Create user + deadline priority.
Call _create_snapshots_for_week.
Query snapshot — assert target_hours IS NULL.
Verify avg_target_achievement on priority stays NULL (no target to compare against).

Test 9: calendar_keyword_at_snapshot preserves keyword at creation time.

Create user + priority with keyword P1.
Call _create_snapshots_for_week — snapshot gets calendar_keyword_at_snapshot = "P1".
Change priority keyword to P2 (direct DB update to simulate swap).
Call _create_snapshots_for_week for next week — new snapshot gets calendar_keyword_at_snapshot = "P2".
Query both snapshots — week 1 has P1, week 2 has P2.

Test 10: Backfill multiple missing weeks via ensure_snapshots_up_to_date.

Create CoreUser + CoreConnection (provider="google", connection_type="google", revoked_at=None).
Create PgPriority (flexible, P1, created_at well before all 3 test weeks, weekly_hour_target=10.0).
Mock ensure_valid_access_token to return {"access_token": "test"}.
Mock get_user_timezone to return "UTC".
Mock _compute_target_weeks to return 3 specific Monday dates (deterministic, avoids dependency on current date).
Mock list_events to return different hours per week (e.g., week 1: 5h, week 2: 8h, week 3: 0h).
Call ensure_snapshots_up_to_date(user_id, session, http_client).
Assert return value: {"checked": 3, "created": 2, "errors": 0} (week 3 has 0h but eligible priority still gets snapshot with 0 hours — so actually created: 3 if the function creates rows for 0-hour weeks. Verify against actual behavior.)
Query pg_weekly_snapshots — assert 3 rows.
Verify streak chaining: week 1 streak=1, week 2 streak=2, week 3 streak=0 (broken by 0 hours).
Query priority aggregates: streak_count=0 (last week's streak), total_hours_invested = Decimal("13.00") (5+8+0).
Call ensure_snapshots_up_to_date again — assert {"checked": 3, "created": 0, "errors": 0} (idempotent).

Do not change the service code or existing tests.