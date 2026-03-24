Real-DB integration test: weekly report eligibility filter for past weeks
Context: The unit and mock-based integration tests for the eligibility fix are in place. This adds a real-database integration test to verify the fix end-to-end through the actual service function with real PostgreSQL.
File: tests/integration/priority_guardian/test_snapshot_weekly_report.py (add a new test class at the end)
Test harness: Use the existing conftest fixtures: async_session (real async PostgreSQL session with auto-cleanup via cleanup_db). Follow the pattern in TestSnapshotKeywordPersistence — create CoreUser, then PgPriority via ORM, commit, then call the service.
External mocking boundary: Only mock Google API calls (list_events, ensure_valid_access_token, get_user_timezone). Do NOT mock is_week_complete — use real past-week dates that are unambiguously complete (e.g., date(2026, 1, 5), a Monday well in the past). Let the real is_week_complete logic execute.
What to test (new class TestPastWeekEligibilityFilter):
Test 1: Past week before priority existed returns empty report, no calendar fetch.

Create a CoreUser and a CoreConnection (provider="google", connection_type="google", revoked_at=None).
Create one PgPriority with created_at = datetime(2026, 2, 19) (Thursday).
Call generate_weekly_report(user_id, session, http_client, week_start=date(2026, 1, 5)) — a week well before the priority existed.
Mock ensure_valid_access_token to return {"access_token": "test"}.
Mock get_user_timezone to return "UTC".
Mock list_events and assert it was NOT called.
Assert response matches _empty_report shape: priorities == [], all time_allocation values zero, is_current_week == False.

Test 2: Past week where priority IS eligible returns data with calendar fetch.

Same setup but created_at = datetime(2026, 1, 1) (Thursday of a prior week).
Request week_start=date(2026, 1, 5) — priority eligible since first_valid_monday is Jan 5.
Mock list_events to return a few P1-tagged events.
Assert list_events WAS called.
Assert response has 1 priority in the list with the correct name and hours from the mocked events.

Test 3: Mixed eligibility — one priority eligible, one not.

Create two priorities: one created_at = datetime(2026, 1, 1) (P1, eligible for Jan 5), one created_at = datetime(2026, 2, 19) (P2, not eligible).
Request week_start=date(2026, 1, 5).
Mock list_events to return events tagged both P1 and P2.
Assert only the eligible priority appears in priorities list.
Assert P2 hours land in other_hours (or are simply not attributed to any priority).

Important: These tests verify the real DB query path (Step 4 loads priorities from actual PostgreSQL) combined with Python-level filtering and real is_week_complete evaluation. The Google Calendar API is still mocked — that's correct, we're testing eligibility logic, not Google integration.
Do not change the service code or existing tests.