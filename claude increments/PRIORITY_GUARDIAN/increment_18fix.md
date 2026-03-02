# Corrective Briefing: onboarding_calendar_setup fixes

## Context
Post-implementation review of `onboarding_calendar_setup.py` found 4 issues that need fixing before this increment is complete. Tests are also still missing.

---

## Fix 1: Remove "already onboarded" hard block (BUG)

**Problem:** The guard checks if past `pg_weekly_snapshots` exist and returns `isError=True` to block onboarding. But `snapshot_service.ensure_snapshots_up_to_date` runs on every dashboard load (`get_priorities` handler calls `POST /snapshots/ensure`). A user who loads the dashboard once, comes back next week, and tries Phase 2 will have a past snapshot — even though they never completed onboarding. This falsely blocks legitimate users.

**Fix:** In all three phase handlers (`_handle_keyword_education`, `_handle_first_snapshot`, `_handle_reflection_setup`):
- Remove the `isError=True` hard block when past snapshots exist
- Replace with a log-only warning: `onboarding.possible_returning_user`
- Do NOT block the flow — let the tool proceed normally
- The tool description ("Do NOT call this for returning users") remains the behavioral guard

Remove the entire past-report check block from all three handlers. Replace with:
```
# Log if user might be returning (past snapshots exist), but don't block
```
Log `onboarding.possible_returning_user` with user_id, correlation_id, and the snapshot check result. Continue execution regardless.

**Why not a real flag:** Adding `onboarding_completed_at` to the user record requires a migration. Not worth it for v1. We'll add it when it matters.

---

## Fix 2: Verify weekly report field names in first_snapshot normalization

**Problem:** `_handle_first_snapshot` normalizes the weekly report response using field names like `p.get("actual_hours")`, `p.get("deadline_date")`, `p.get("days_remaining")`, `p.get("deliverables_completed")`, `p.get("deliverables_total")`, `p.get("target_hours")`, `p.get("flex_status")`, `p.get("pacing_status")`. These must match the actual keys returned by `generate_weekly_report` in `backend/apps/priority_guardian/services/weekly_report_service.py`.

**Fix:** 
1. Read `weekly_report_service.py` — find the exact dict keys in the priority objects it returns
2. Update the normalization mapping in `_handle_first_snapshot` to match exactly
3. If any key doesn't exist in the backend response, remove it from the normalization (don't output `null` for keys the backend never sends)

---

## Fix 3: BACKEND_TIMEOUT declared but unused

**Problem:** `BACKEND_TIMEOUT = 15.0` is declared at module level but never passed to any `backend_get` call.

**Fix:** Either:
- Pass timeout to `backend_get` if it supports a timeout parameter (check `http_client.py` signature)
- If `backend_get` doesn't support timeout, remove the `BACKEND_TIMEOUT` constant entirely

---

## Fix 4: Remove "Frame positively" from FIRST_SNAPSHOT guidance

**Problem:** The `assistant_guidance` instruction for `FIRST_SNAPSHOT` says "Frame positively — this is the user's first look at their data." This is motivational framing, not mechanistic instruction.

**Fix:** Change the instruction opening from:
```
"Present the weekly snapshot. Frame positively — this is the user's first look at their data. Show how time splits across priorities."
```
To:
```
"Present the weekly snapshot. Show how time splits across priorities."
```

Remove only "Frame positively — this is the user's first look at their data." Keep everything else.

---

## Fix 5: Remove "tag" from create_priority defensive fallback

**Problem:** In `create_priority.py`, the `_build_success_guidance` function's defensive fallback (when `available_keywords is None`) contains:
```
f"Remind user: tag calendar events with {keyword} to track time "
```
This violates the "never use 'tag'" rule.

**Fix:** Change to:
```
f"Remind user: add {keyword} to calendar event titles to track time "
f"(e.g., '{keyword}: Meeting name')."
```

---

## Tests

No tests were written. The briefing specified them. Write them now.

### Unit Tests

**File:** `tests/unit/mcp_pg/test_onboarding_calendar_setup.py`

Mock `backend_get` for all tests. Import the phase handlers or call `handle()` directly.

1. **test_keyword_education_returns_priorities_with_keywords** — mock `/priorities` returning 2 active priorities with `google_connection.connected=True`. Assert `structuredContent.assistant_guidance.action == "KEYWORD_EDUCATION"`. Assert guidance `priorities` list contains both priority names and keywords.

2. **test_keyword_education_no_connection_returns_error** — mock `/priorities` returning `google_connection.connected=False`. Assert `isError=True`. Assert text content mentions "full dashboard".

3. **test_keyword_education_no_priorities_returns_error** — mock `/priorities` returning empty priorities list with `google_connection.connected=True`. Assert `isError=True`. Assert text mentions "at least one priority".

4. **test_keyword_education_already_onboarded_logs_warning_but_continues** — mock past weekly report returning `snapshot_saved=True`, AND mock `/priorities` returning valid data. Assert tool does NOT return `isError=True`. Assert log contains `onboarding.possible_returning_user`. Assert response contains `KEYWORD_EDUCATION` guidance.

5. **test_first_snapshot_returns_weekly_data** — mock `/weekly-report` returning current week with P1=4h, P2=2h, other=8h. Assert `structuredContent.data.timeAllocation.totalTrackedHours == 14`. Assert `assistant_guidance.action == "FIRST_SNAPSHOT"`. Assert `deliverable_education` present in guidance.

6. **test_first_snapshot_zero_keyword_hours_returns_retry** — mock `/weekly-report` returning P1=0, P2=0, P3=0, other_hours=12. Assert `isError=True`. Assert text mentions "keywords aren't reflected yet".

7. **test_first_snapshot_empty_week_returns_no_events** — mock `/weekly-report` returning total_tracked_hours=0. Assert `isError=True`. Assert text mentions "No calendar events found".

8. **test_first_snapshot_google_not_connected_returns_error** — mock `/weekly-report` returning `success=False, error.code="GOOGLE_NOT_CONNECTED"`. Assert `isError=True`. Assert text mentions dashboard.

9. **test_reflection_setup_returns_guidance_only** — call with phase `reflection_setup`. Assert `structuredContent.assistant_guidance.action == "REFLECTION_SETUP"`. Assert `onboarding_complete == True`. Assert `structuredContent.data` is empty dict.

10. **test_reflection_setup_no_backend_data_call** — call with phase `reflection_setup`. Assert `backend_get` was called only for the past-snapshot check (if it still exists after Fix 1), NOT for `/priorities` or `/weekly-report`.

11. **test_schema_rejects_invalid_phase** — call `handle()` with `phase="invalid"`. Assert `ToolUsageError` raised.

12. **test_tool_metadata** — assert `read_only_hint=True`, `widget_accessible=False`, `open_world_hint=True`, `required_scopes=["pg.access"]`.

### Integration Tests

**File:** `tests/integration/priority_guardian/test_onboarding_flow.py`

These use real database and real backend calls (test database, not production).

13. **test_keyword_education_with_real_priorities** — create test user with 2 priorities and Google Calendar connected. Call `keyword_education` phase via the handler. Assert response contains correct priority names and keywords from the database.

14. **test_first_snapshot_with_tagged_events** — create test user with priorities and calendar connection. Seed calendar events with keywords. Call `first_snapshot` phase. Assert response includes non-zero priority hours.

15. **test_full_onboarding_sequence** — call all three phases in order with valid test data. Assert `keyword_education` returns `next_phase: "first_snapshot"`. Assert `first_snapshot` returns `next_phase: "reflection_setup"`. Assert `reflection_setup` returns `onboarding_complete: true`.

16. **test_first_snapshot_no_keywords_rejected** — create test user with priorities and calendar but no keyword-tagged events. Call `first_snapshot`. Assert `isError=True` with retry guidance.

---

## Acceptance Criteria

- [ ] No `isError=True` returned based on past snapshot existence — log only
- [ ] All field names in `_handle_first_snapshot` normalization verified against `weekly_report_service.py`
- [ ] `BACKEND_TIMEOUT` either used or removed
- [ ] "Frame positively" removed from FIRST_SNAPSHOT guidance
- [ ] "tag" removed from create_priority defensive fallback
- [ ] 12 unit tests pass
- [ ] 4 integration tests pass
- [ ] All existing tests still pass