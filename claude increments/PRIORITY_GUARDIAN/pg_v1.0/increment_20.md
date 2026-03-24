# Claude Code Briefing: Priority Soft Delete

## Context

Priority Guardian currently hard-deletes priorities when users click "delete" in the widget. This cascade-deletes the priority, all deliverables, goals, and weekly snapshots. This destroys historical data needed for pattern recognition (upcoming feature).

The Data Retention Strategy already specifies two distinct operations:
- **Retire**: `status = 'retired'`, `retired_at = now()`, data preserved, read-only
- **Delete**: hard cascade delete of all related data

The DB model already supports retirement (`status`, `retired_at`, constraint `ck_pg_priorities_retirement_consistency`). The code just doesn't use it — the delete endpoint does a hard delete.

This increment converts the user-facing "delete" action to a soft delete (retirement). Hard delete is preserved as a separate endpoint for future GDPR account deletion.

## Scope

### Backend changes:
1. **`DELETE /priorities/{priority_id}`** — change from hard delete to soft delete
2. **New endpoint `DELETE /priorities/{priority_id}/permanent`** — hard delete for future GDPR use

### MCP tool changes:
3. **`delete_priority` widget tool** — update to call soft delete endpoint

### Widget changes:
4. **None in this increment** — widget already calls `delete_priority` tool which calls the backend. The backend behavior changes, widget doesn't need to know.

### NOT in scope:
- GDPR account deletion endpoint (`DELETE /delete-data`) — separate increment
- Widget UI for "permanently delete" — future increment
- Pattern recognition engine — separate increment
- Rolling window queries — separate increment

---

## Files to Modify

- `backend/apps/priority_guardian/routers/priorities_router.py` — delete endpoint + new permanent delete endpoint
- `mcp_server/priority_guardian/tools/widget_tools.py` — verify delete_priority tool forwards correctly (may need no changes)
- `tests/` — unit tests for both endpoints

---

## Change 1: Convert DELETE endpoint to soft delete

### Current behavior
`DELETE /priorities/{priority_id}` calls `session.delete(priority)` which cascade-deletes everything.

### New behavior
`DELETE /priorities/{priority_id}` should:
1. Fetch the priority (same validation as current — correct user, exists)
2. If already retired, return 200 with `build_priorities_response()` (idempotent — safe for double-clicks, retries, race conditions)
3. Set `status = 'retired'`
4. Set `retired_at = now()` (timezone-aware UTC)
5. Set `calendar_keyword = None` — this frees the keyword for reuse. The keyword is already captured in `pg_weekly_snapshots.calendar_keyword_at_snapshot` for historical reports.
6. Commit
7. Return full priorities response via `build_priorities_response()` (same as current)

### Important: keyword NULL during retirement
The partial unique index `idx_pg_priorities_user_keyword_active` only applies to `status = 'active'`, so NULLing the keyword on a retired priority won't violate any constraint. The `ck_pg_priorities_keyword` constraint allows NULL (`calendar_keyword` column is `nullable=True`). Verify this.

### Response shape
Same as current — `build_priorities_response()` returns all priorities (active + retired). The widget will see the retired priority disappear from active cards because it filters by status. Verify that `build_priorities_response` still returns retired priorities and that this doesn't break the widget.

### Logging
Change log event from `priority.delete.success` to `priority.retire.success`. Include `freed_keyword` in log context.

---

## Change 2: New permanent delete endpoint

### Endpoint
`DELETE /priorities/{priority_id}/permanent`

### Behavior
Exactly what the current delete endpoint does today — hard cascade delete via `session.delete(priority)`. Same validation (correct user, exists). Works on both active and retired priorities.

### Purpose
This endpoint exists for future GDPR account deletion and for the future "permanently delete" UI option. It is NOT called by any widget tool in this increment.

### Response
Same as current delete — `build_priorities_response()` after deletion.

### Logging
`priority.permanent_delete.success` with `priority_id` and `user_id`.

---

## Change 3: Verify snapshot_service behavior

### Concern
The `snapshot_service` (which creates weekly snapshots) must NOT create new snapshots for retired priorities. Check `ensure_snapshots_up_to_date()` — it should already filter by `status = 'active'`. Verify this. If it does, no changes needed. If it doesn't, add the filter.

### Concern
The `_update_aggregates()` function in `snapshot_service` must NOT update aggregates on retired priorities. Aggregates should be frozen at retirement. Verify this. If it already filters by active status, no changes needed.

---

## Change 4: Verify weekly_report_service behavior

### Concern
`generate_weekly_report()` queries active priorities only (`PgPriority.status == "active"`). Retired priorities should NOT appear in current week reports. Verify this is already the case.

### Concern
`_build_report_from_snapshots()` for past weeks queries snapshots by `user_id` and `week_start`. Since retired priority snapshots are preserved, past week reports will correctly include retired priorities' historical data. Verify this still works — the snapshots remain, the priority row remains (just retired), and the join still works.

### Critical: keyword NULL in past-week report path
After retirement, `priority.calendar_keyword` is NULL. The `_build_report_from_snapshots()` function must use `snapshot.calendar_keyword_at_snapshot` for the keyword, NOT `priority.calendar_keyword`. Check the line that sets `kw` — it should already prefer the snapshot value with a fallback: `kw = snapshot.calendar_keyword_at_snapshot or priority.calendar_keyword`. After retirement the fallback will be NULL — verify this doesn't cause issues in the response builder (e.g., `keyword_hours[kw]` with kw=None).

---

## Change 5: Verify widget handles retired priorities in response

### Concern
`build_priorities_response()` returns all priorities (active + retired). The widget must filter by `status == 'active'` when rendering cards. If the widget currently assumes all returned priorities are active, retired priorities with NULL keywords will render as broken cards.

### What to verify
Check the widget JSX — does it filter priorities by status before rendering? If it does, no changes needed. If it doesn't, this is a bug that must be fixed in this increment (add `.filter(p => p.status === 'active')` before rendering priority cards).

---

## Unit Tests

### Tests for soft delete (modify existing or add new):

1. **`test_delete_priority_soft_deletes`** — Call DELETE on an active priority. Assert:
   - Response is 200 with full priorities response
   - Query DB directly: priority row still exists with `status = 'retired'` and `retired_at` is not None
   - Query DB directly: `calendar_keyword` is None on the retired priority
   - Query DB directly: deliverables for this priority still exist (count unchanged)
   - Query DB directly: weekly snapshots for this priority still exist (count unchanged)
   - Query DB directly: goals for this priority still exist (count unchanged)
   - The freed keyword appears in `available_keywords` in API response

2. **`test_delete_retired_priority_is_idempotent`** — Call DELETE on an already-retired priority. Assert 200 with full priorities response (not 404). Query DB: no state change (retired_at unchanged).

3. **`test_soft_deleted_priority_frees_keyword_for_reuse`** — Soft delete a P1 priority, then create a new priority. Assert the new priority can get P1.

4. **`test_soft_deleted_priority_snapshots_preserved`** — Create a priority, create snapshots via DB setup, soft delete it. Query DB directly: assert snapshot rows still exist with correct `calendar_keyword_at_snapshot` values.

### Tests for permanent delete:

5. **`test_permanent_delete_cascades`** — Call DELETE /priorities/{id}/permanent on a priority with deliverables, goals, and snapshots. Assert:
   - Response is 200
   - Query DB directly: priority row gone (SELECT returns None)
   - Query DB directly: deliverables for this priority_id return empty (cascade deleted)
   - Query DB directly: snapshots for this priority_id return empty (cascade deleted)
   - Query DB directly: goals for this priority_id return empty (cascade deleted)

6. **`test_permanent_delete_works_on_retired_priority`** — Retire a priority first, then permanently delete it. Assert everything is gone.

7. **`test_permanent_delete_nonexistent_returns_404`** — Assert 404 for invalid priority_id.

### Tests for service behavior:

8. **`test_snapshot_service_skips_retired_priorities`** — If snapshot_service already filters by active status, assert that retired priorities don't get new snapshots.

9. **`test_weekly_report_excludes_retired_from_current_week`** — Assert `generate_weekly_report()` for current week does not include retired priorities.

9b. **`test_aggregate_update_does_not_mutate_retired_priority`** — Retire a priority (record its `streak_count`, `total_hours_invested`, `avg_target_achievement`). Then trigger `_update_aggregates()` for another active priority. Query DB directly: assert the retired priority's aggregate fields are unchanged. This is a critical invariant — background recalculation must never mutate retired rows.

10. **`test_past_week_report_includes_retired_priority_snapshots`** — Assert `_build_report_from_snapshots()` still returns data for priorities that are now retired but had snapshots during that past week. Specifically: the returned priority data must use `calendar_keyword_at_snapshot` value (not the now-NULL `priority.calendar_keyword`).

11. **`test_past_week_report_keyword_from_snapshot_not_priority`** — Create a priority with keyword P1, generate a snapshot, retire the priority (keyword becomes NULL). Request past-week report. Assert the priority in the report has keyword P1 (from snapshot), not NULL.

12. **`test_widget_response_includes_retired_with_status`** — Call `build_priorities_response()` after retiring a priority. Assert the retired priority is present in the response with `status: 'retired'` and `calendar_keyword: null`.

---

## Acceptance Criteria

1. `DELETE /priorities/{priority_id}` soft-deletes (status='retired', retired_at set, keyword NULLed)
2. Deliverables, goals, and snapshots are NOT deleted on soft delete
3. Freed keyword is available for new priorities
4. `DELETE /priorities/{priority_id}/permanent` hard-deletes with cascade (same as old behavior)
5. Retired priorities don't get new snapshots
6. Retired priorities don't appear in current week reports
7. Past week reports from snapshots still include retired priorities' historical data
8. `build_priorities_response()` still includes retired priorities in response (widget handles filtering)
9. All existing tests pass
10. All new tests pass

## What NOT to Do

- Do not change the widget HTML/JSX
- Do not add a "permanently delete" button to the widget (future increment)
- Do not modify the MCP tool definitions or descriptions
- Do not add pattern recognition logic
- Do not add rolling window queries
- Do not modify the offboarding router
- Do not change the snapshot or weekly report service logic unless verification reveals a bug
