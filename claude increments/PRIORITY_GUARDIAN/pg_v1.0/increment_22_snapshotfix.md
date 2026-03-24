Fix: Weekly report fallback path attributes calendar events to priorities that didn't exist during the requested week
Bug: When _build_report_from_snapshots returns None for a past week, the live calendar fallback loads all current active priorities regardless of creation date. Calendar events tagged P1/P2/P3 from before a priority existed get attributed to the current priority holding that keyword.
Root cause: Step 4 in generate_weekly_report queries PgPriority.status == "active" without filtering by creation date.
File: backend/apps/priority_guardian/services/weekly_report_service.py
Fix location: The live calendar fallback path in generate_weekly_report, between the snapshot attempt (Step 3b) and loading priorities (Step 4).
What to change:

After Step 3b (snapshot path returns None), before Step 4: if is_current is False, load priorities from DB as today (status == "active"), then filter in Python using priority_eligible_for_week(priority.created_at.date(), actual_week_start) from backend.apps.priority_guardian.services.utils (import already present at top of file). Do NOT add a SQL-level filter on created_at in the DB query — the eligibility logic must use priority_eligible_for_week for consistency with the snapshot service.
If no priorities pass the eligibility filter, return _empty_report(actual_week_start, actual_week_end, is_current) immediately. Do NOT fetch calendar events. No pie chart, no data. Add a brief code comment explaining: historical calendar time before the first eligible priority is intentionally not surfaced — tracking hadn't started yet.
If some priorities pass but others don't, continue with only the eligible ones. Ineligible priority keyword hours will naturally land in "Other" via the existing allocation logic.
For current week (is_current is True): no change. Load all active priorities as today.

Do not change:

_empty_report function (stays as-is with zeros)
_build_report_from_snapshots (already correct)
Current week behavior

Unit tests (add to existing weekly report test file, mock dependencies):

Test: past week, priority created Thursday of that week → priority_eligible_for_week returns False → priority excluded from live report
Test: past week, priority created Monday of that week → priority_eligible_for_week returns True → priority included
Test: past week, priority created after the requested week → excluded, _empty_report returned. Mock list_events and assert it was NOT called — this prevents someone from accidentally moving the early return below the calendar fetch.
Test: current week → all active priorities included regardless of creation date (no eligibility filter applied)

Integration test:

Request weekly report for a past week before any priorities existed → response matches _empty_report shape: empty priorities list, all time_allocation values zero, is_current_week: False
