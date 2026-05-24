# Fix: Calendar Event Overlap Overcounting — Part 2 of 2 (Integration Tests + Release Verification)

## Context

Part 1 (`fix_overlap_overcounting_part1.md`) replaced the algorithm in `compute_allocation_from_events` with interval sweep + distinct bucket attribution and added unit tests. Part 2 verifies the fix end-to-end across all three downstream consumers (live weekly report, snapshot writer, time allocation endpoint), produces an internal changelog entry documenting the user-visible change, and gates the production deploy.

**Do not start this increment until part 1 is merged and unit tests are green.**

## What Changes in This Increment

- Add integration tests that exercise the corrected algorithm through each of the three downstream code paths.
- Add one DB-integrity test that verifies snapshot rows written post-fix carry consistent week-level values and a correct per-priority breakdown.
- Write an internal changelog entry describing the user-visible behavior change (not a public release note).
- Run the production verification checklist before deploying, using a controlled internal test account with synthetic events.

## Production Code Changes Policy

**No intended production logic changes in this increment.** This increment touches tests and docs only. Production files in scope for change ONLY if integration tests expose a wiring bug (a router serializing a field incorrectly, a snapshot writer quantizing a value wrong, etc.) — in which case: stop, document the finding in this increment, and either patch with explicit justification in this same PR OR open a follow-up increment. **Never silently "fix" algorithm behavior in this increment** — algorithm changes belong in a part-1 amendment, not here.

## Implementation Approach — Copy and Adjust, Never Rewrite

For each test file you create or extend, copy the structure of the closest existing analogous test in the same directory. Use the same fixture conventions, the same auth/connection setup, the same DB session handling. Add only the new assertions described below. Do not refactor existing test scaffolding.

## Integration Tests

### File: `tests/integration/priority_guardian/test_overlap_fix_e2e.py` (new)

This is a new file. Mirror the imports, fixtures, and conftest usage from the closest existing integration test in the same directory (`test_calendar_endpoint_integration.py` is the best template — copy its setup, then add the new tests).

The tests need a way to inject deterministic Google Calendar events. Use whatever event-mocking pattern the existing integration tests in this directory already use (typically a fixture that monkeypatches `list_events` or stubs the Google API HTTP layer). Do not invent a new mocking approach. If the existing tests use VCR cassettes, real HTTP fakes, or in-process patches — match that pattern.

#### Required test cases

1. **`test_weekly_report_endpoint_overlap_corrected`**
   - Inject 3 events into the mocked calendar for current week: P1 15-17, P2 16-16:30, untagged 18-19.
   - Set up a user with active P1 priority and active P2 priority.
   - Hit `GET /weekly-report` (no `week_start`, current week → live computation path).
   - Assert response `data.priorities[P1].actual_hours == 1.75`, `data.priorities[P2].actual_hours == 0.25`, `data.time_allocation.other_hours == 1.0`, `data.time_allocation.total_tracked_hours == 3.0`.

2. **`test_calendar_time_allocation_endpoint_overlap_corrected`**
   - Same event setup as test 1.
   - Hit `GET /calendar/time-allocation`.
   - Assert `data.keywords.P1.hours == 1.75`, `data.keywords.P2.hours == 0.25`, `data.other_hours == 1.0`, `data.total_tracked_hours == 3.0`.
   - Assert `data.bar_segments` mirrors keywords + other (per part 1 invariant 13).

3. **`test_snapshot_writer_persists_corrected_hours`**
   - Set up a user with one active P1 priority.
   - Inject events for a **completed past week** (week before current): P1 15-17 + P1 16-16:30 (case b — same-priority overlap).
   - Trigger snapshot creation by calling `ensure_snapshots_up_to_date` directly (or hit whatever endpoint triggers it on dashboard load — match the pattern in existing snapshot integration tests).
   - Read the resulting `pg_weekly_snapshots` row from the DB.
   - Assert `actual_hours == Decimal("2.00")` (not 2.50).
   - Assert `total_tracked_hours == Decimal("2.00")` and `other_hours == Decimal("0.00")` on the snapshot row.

4. **`test_snapshot_based_past_week_report_uses_corrected_persisted_hours`**
   - Continuation of test 3: with the snapshot row present, hit `GET /weekly-report?week_start=<past_monday>`.
   - Assert the response is built from the snapshot path (`data.snapshot_saved == True`).
   - Assert `data.priorities[P1].actual_hours == 2.0` (matches the persisted value).

5. **`test_two_endpoints_agree_on_same_calendar`**
   - Inject the same events into the mocked calendar.
   - Hit BOTH endpoints: `GET /calendar/time-allocation` and `GET /weekly-report` (current week).
   - Assert the per-keyword hours and `total_tracked_hours` match between the two endpoint responses.
   - Note: This test verifies endpoint-level cross-consumer agreement only. Direct calls to `compute_allocation_from_events` belong in unit tests (already covered in part 1) and are not repeated here.

#### Tests NOT to add

- Do not add tests for old buggy behavior — those are obsolete.
- Do not add direct function calls to `compute_allocation_from_events` in integration tests — algorithm correctness is fully covered by part 1 unit tests.
- Do not add tests for case (e) multi-keyword events at integration level — unit tests in part 1 cover this; the integration path is identical to other cases.
- Do not add load tests — out of scope.

### File: `tests/integration/priority_guardian/test_db_integrity.py` (extend existing file)

Add one new test to this existing file. Match the existing test style and fixtures.

**`test_snapshot_row_invariant_total_equals_components`**

**Critical context for understanding this test:** `pg_weekly_snapshots` stores `other_hours` and `total_tracked_hours` as **denormalized week-level values** — every snapshot row for a given user+week carries identical copies of these two values (see `snapshot_service._create_snapshots_for_week`, where `week_other_hours` and `week_total_tracked_hours` are computed once per week and written to every per-priority row for that week). This means a naive `SUM(other_hours)` across rows would multiply-count by the number of priorities. The integrity test below accounts for this.

Test logic:
- Trigger snapshot creation for a week with overlapping events. Use a setup with at least 2 active priorities so the denormalization is exercised: e.g. P1 priority + P2 priority + events {P1 15-17, P2 16-16:30}.
- Read all snapshot rows for that week (one row per priority).
- **Consistency assertion:** Assert all rows agree on `other_hours` and `total_tracked_hours`. Specifically: `SELECT DISTINCT other_hours, total_tracked_hours FROM pg_weekly_snapshots WHERE user_id = :u AND week_start = :w` must return exactly one row. (This catches partial-snapshot corruption — already guarded against by the `inconsistent_week_totals` check in `weekly_report_service._build_report_from_snapshots`, but a DB-level test gives belt-and-suspenders coverage.)
- **Per-priority bound:** For each row, assert `actual_hours <= total_tracked_hours`.
- **Component sum:** Pick one representative row's `other_hours` and `total_tracked_hours` (since all rows agree per the consistency assertion). Assert `sum(actual_hours across all priority rows for the week) + representative_other_hours == representative_total_tracked_hours` within 0.02 tolerance.

The 0.02 tolerance matches the rounding tolerance documented in part 1 invariant 1.

## Internal Changelog Entry

Create file: `doc/internal_changelog/2026-XX-overlap-fix.md` (use today's YYYY-MM in the filename; create the `internal_changelog` directory if it doesn't exist).

**This is internal documentation, NOT a user-facing release note.** No in-app announcement, no email, no dashboard banner. Two purposes only:
1. Future-self reference: in 3 months when you wonder "wait, why did P1 hours drop in April?", this is your answer.
2. Support-ready response template: if a user asks why their hours decreased, you have a single source of truth to point to.

Contents — write in plain language. Avoid implementation jargon. Approximately 200-300 words. Cover:

- **What changed:** The weekly report now correctly handles overlapping calendar events. Previously, when two events overlapped in time, both events' full durations were counted, inflating reported hours.
- **What users will notice (if they look closely):** Hours per priority (`actual_hours`), total tracked hours, and the "total hours invested" growth rate may all be lower starting from the deploy date. This is the corrected number — they weren't actually working those extra hours, the report was double-counting overlapping calendar blocks.
- **How overlapping time is now attributed:** When events overlap, the overlapping portion is split evenly across the priorities involved. Two-event overlap → 50/50 split. Three-event overlap → thirds. Untagged events count toward "other" the same way.
- **Multi-keyword event titles** (e.g. "P1 P2 strategy review"): Previously credited to both priorities at full duration. Now split evenly between them, consistent with the new overlap rule.
- **Past weeks:** Reports for weeks before this fix are built from snapshots that were saved with the old logic. Those past-week numbers stay as they were — the fix applies to this week and going forward.
- **Why this was changed:** Honest tracking surfaces real signals. If a user sees an unexpected drop in P1 hours, it's a sign of conflicted/overlapping calendar time that may be worth resolving.
- **Support response template:** A short paragraph the support function (currently you) can paste verbatim if a user asks about the change.

## Pre-Deploy Tasks

Before committing this increment:

1. Run `pytest tests/integration/priority_guardian/test_overlap_fix_e2e.py -v` and confirm all tests pass.
2. Run `pytest tests/integration/priority_guardian/test_db_integrity.py -v` and confirm the new test plus all existing tests pass.
3. Run the **full** unit + integration suite for `priority_guardian`: `pytest tests/unit/priority_guardian tests/integration/priority_guardian -v` and confirm zero failures. This catches any side effects from part 1.
4. Read `doc/OPERATIONS_PREDEPLOY.md`. Specifically:
   - Confirm there are no new migrations introduced by part 1 or part 2 (there shouldn't be).
   - Confirm `alembic heads | wc -l` returns 1.
5. Read `doc/OPERATIONS_PRESUBMISSION.md`. This change does not require resubmission to OpenAI (algorithm internals are not surfaced in tool descriptions or schemas), but verify nothing in this checklist now applies due to the behavior change.

## Production Verification (after deploy)

**CRITICAL PRIVACY RULE: Use ONLY a controlled internal test account with synthetic events. Never inspect a real user's calendar manually under any circumstances.** GDPR/Einzelunternehmer compliance is non-negotiable here. The verification steps below assume you have an internal test Google account that you control entirely, populated with synthetic calendar events you've created yourself.

1. **Synthetic past-week verification (run immediately after deploy, do not wait for Monday):**
   - Using your internal test account, create synthetic overlapping events in a *past* completed week. Suggested setup: P1 priority on the test account; calendar events for last week including P1 Tue 15-17, P1 Tue 16-16:30 (same-priority overlap), and an untagged Wed 10-12.
   - Run a one-shot script that calls `ensure_snapshots_up_to_date` for that test user. (You can do this via a Python REPL pointed at production DB + production access token, or via a temporary admin endpoint, or via direct DB session — match how you've handled similar one-shot verifications historically.)
   - SQL-verify the resulting snapshot row(s) directly: `SELECT actual_hours, other_hours, total_tracked_hours FROM pg_weekly_snapshots WHERE user_id = :test_user AND week_start = :past_monday`.
   - Expected for the suggested setup: `actual_hours = 2.00` for the P1 priority (not 2.50, which would indicate the bug is still live), `other_hours = 2.00`, `total_tracked_hours = 4.00`.
   - If numbers don't match, halt and investigate before continuing rollout.

2. **Live current-week endpoint check (test account only):**
   - Trigger a weekly report on the dashboard for the same internal test account.
   - Spot-check: pick two overlapping events in the synthetic calendar and verify the report's per-priority hours reflect the split, not the sum.

3. **Passive monitoring (next 48 hours):**
   - Monitor logs for warnings under the `weekly_report.*`, `snapshot.*`, `calendar.*` namespaces.
   - Watch for `overlap_segment_count > 0` in `calendar.allocation_computed` logs — this confirms real users are exercising the new code path.

4. **Monday rollover (passive):**
   - When real user snapshots roll over the following Monday, observe DB writes via existing logs. No additional active verification needed if step 1 succeeded — Monday is just the natural production exercise.

5. **Support readiness:**
   - Have the internal changelog entry ready to paste if any user asks about reduced hours.

## Rollback Plan

If integration tests pass but production verification reveals incorrect numbers:

1. Revert the part 1 commit only (algorithm change).
2. Snapshots written between deploy and rollback will carry the corrected numbers — these are correct values and should not be reverted. They will simply represent honest data inside the period when the fix was active.
3. Investigate the discrepancy and re-issue a corrected part 1 amendment.

Do not attempt to "fix" snapshots written during the corrected period — they are honest, not broken.

## What This Increment Does NOT Do

- Does NOT change any production code logic (unless integration testing exposes a wiring bug — see Production Code Changes Policy).
- Does NOT introduce migrations.
- Does NOT backfill or rewrite pre-fix snapshot rows.
- Does NOT change widget rendering or response shapes.
- Does NOT trigger MCP tool description changes or require store resubmission.
- Does NOT publish a user-facing release note (changelog is internal-only).
- Does NOT inspect any real user's calendar at any point.
