# Fix: Calendar Event Overlap Overcounting — Part 1 of 2 (Algorithm + Unit Tests)

## Problem

`compute_allocation_from_events` in `backend/apps/priority_guardian/services/calendar_service.py` overcounts hours whenever calendar events overlap in time. It naively sums each event's duration into bucket totals (`keyword_hours`, `other_hours`, `total_tracked_hours`, `bar_segments`) without deduplicating overlapping wall-clock minutes.

**Concrete examples of current wrong behavior:**

| Case | Events | Today's output (wrong) | Correct output |
|---|---|---|---|
| (a) Cross-priority overlap | `P1 15-17` + `P2 16-16:30` | total=2.5h, P1=2h, P2=0.5h | total=2h, P1=1.75h, P2=0.25h |
| (b) Same-priority overlap | `P1 15-17` + `P1 16-16:30` | total=2.5h, P1=2.5h | total=2h, P1=2h |
| (c) Priority + untagged overlap | `P1 15-17` + `untagged 16-16:30` | total=2.5h, P1=2h, other=0.5h | total=2h, P1=1.75h, other=0.25h |
| (d) Two untagged overlap | `untagged 15-17` + `untagged 16-16:30` | total=2.5h, other=2.5h | total=2h, other=2h |
| (e) Multi-keyword in one event title (no event overlap) | `"P1 P2 sync" 15-17` | P1=2h, P2=2h, total=2h (only this case has correct total today, by coincidence — the multi-attribution itself is wrong post-fix) | P1=1h, P2=1h, total=2h |

The bug affects **three downstream consumers** of this function:
- `calendar_service.compute_time_allocation` — live time allocation endpoint
- `weekly_report_service.generate_weekly_report` — live weekly report (current week + past weeks without snapshots)
- `snapshot_service._create_snapshots_for_week` — what gets persisted into `pg_weekly_snapshots`

One algorithm fix corrects all three. **No fix is being applied to existing snapshot rows** (decision: fix forward only).

## Fix

Replace the duration-summation loop in `compute_allocation_from_events` with a **interval sweep with distinct bucket attribution**.

### Algorithm rule (one sentence)

Every wall-clock minute covered by at least one filtered-in event contributes its length to `total_tracked_hours` exactly once; that length is divided evenly across the **distinct claimant buckets** for that minute, where each event contributes one claim to each bucket it claims.

### Bucket model

Four buckets: `P1`, `P2`, `P3`, `other`. A single filtered-in event's claims:
- Event title matches one keyword (e.g. "P1 sync") → claims that one priority bucket.
- Event title matches multiple keywords (e.g. "P1 P2 sync") → claims **each** matched priority bucket (multiple distinct claims from one event).
- Event title matches no keyword → claims `other`.

**Keyword matching scope (preserve existing behavior):** This increment uses `match_keywords` exactly as it exists today. The current implementation matches keywords in the event **title (`summary` field) only**, not the description. Do not change this. There is a known spec/code mismatch — some product specs reference matching against title AND description — but expanding the match scope would change which events count as priority work for every existing user, materially shifting reported hours independently of the overlap fix. That is a separate decision and a separate increment. **Out of scope here.**

### Worked behavior (must match exactly)

| Case | Sub-interval | Claimant buckets at that minute | Sub-interval contribution |
|---|---|---|---|
| (a) P1 15-17 + P2 16-16:30 | 15:00-16:00 | {P1} | P1 += 1.0 |
| | 16:00-16:30 | {P1, P2} | P1 += 0.25, P2 += 0.25 |
| | 16:30-17:00 | {P1} | P1 += 0.5 |
| | **Result** | | **P1=1.75, P2=0.25, total=2.0** |
| (b) P1 15-17 + P1 16-16:30 | 15:00-16:00 | {P1} | P1 += 1.0 |
| | 16:00-16:30 | {P1} (one distinct bucket — both events claim same bucket) | P1 += 0.5 |
| | 16:30-17:00 | {P1} | P1 += 0.5 |
| | **Result** | | **P1=2.0, total=2.0** |
| (c) P1 15-17 + untagged 16-16:30 | 15:00-16:00 | {P1} | P1 += 1.0 |
| | 16:00-16:30 | {P1, other} | P1 += 0.25, other += 0.25 |
| | 16:30-17:00 | {P1} | P1 += 0.5 |
| | **Result** | | **P1=1.75, other=0.25, total=2.0** |
| (d) Two untagged overlap | 15:00-17:00 | {other} (one distinct bucket — both untagged) | other += 2.0 |
| | **Result** | | **other=2.0, total=2.0** |
| (e) "P1 P2 sync" 15-17 alone | 15:00-17:00 | {P1, P2} (single event, two claims) | P1 += 1.0, P2 += 1.0 |
| | **Result** | | **P1=1.0, P2=1.0, total=2.0** |
| 3-way: P1 + P2 + P3 all 15-16 | 15:00-16:00 | {P1, P2, P3} | each += 1/3 |
| | **Result** | | **P1≈0.333, P2≈0.333, P3≈0.333, total=1.0** |

### Invariants the implementation MUST satisfy (verifiable as test assertions)

1. **Total preservation (with rounding tolerance):** `keyword_hours["P1"] + keyword_hours["P2"] + keyword_hours["P3"] + other_hours` equals `total_tracked_hours` within an `abs=0.02` tolerance. The 0.02h tolerance (not 0.01h) is required because each of the four bucket values is independently rounded to 2 decimals, and an N-way split of an indivisible second produces per-bucket rounding errors that can sum (e.g. a 3-way split of exactly 1.00h produces 0.33 + 0.33 + 0.33 = 0.99 vs total 1.00 = 0.01 gap; with `other` also rounded the worst-case gap is bounded near 0.02). **Do NOT** attempt to fix this by widening tolerance further — if invariant 1 fails with `abs=0.02`, the algorithm is wrong, not the rounding.
2. **Total = real wall-clock union:** `total_tracked_hours` equals the union of all filtered-in event intervals (i.e. computing it with a separate independent union also gives the same number).
3. **Empty input:** Returns the same shape as `_empty_allocation` minus the `week_start`/`week_end`/`timezone` fields.
4. **No-overlap baseline:** When no events overlap, output equals the old behavior exactly (the fix is a strict superset that degenerates to the old summation in the absence of overlap).
5. **Event count semantics unchanged:** `keyword_event_counts[kw]` still counts the number of events whose title matches that keyword (independent of hour attribution). A "P1 P2 sync" event increments BOTH P1 and P2 event counts. This is the existing behavior — preserve it.

### `bar_segments` in the new model

`bar_segments` was a separate exclusive-allocation view computed via "first-keyword-wins" hierarchy. **Drop the separate `bar_segments` computation** — under the new model, `bar_segments[kw]` and `keyword_hours[kw]` would compute identically (both honest, both summing to total). Set `bar_segments` to mirror `keyword_hours` plus `other_hours`:

```
bar_segments = {
    "P1": keyword_hours["P1"],
    "P2": keyword_hours["P2"],
    "P3": keyword_hours["P3"],
    "other": other_hours,
}
```

This preserves the response shape (no breaking change to consumers reading `bar_segments`) while collapsing the dual-attribution philosophy into one. Existing widget/UI code reading `bar_segments` continues to work; the numbers just become honest.

### Floating-point safety (mandatory)

The sweep MUST operate in **integer seconds**, not floats. Convert each event's start/end to UTC integer epoch seconds, sweep on those, accumulate per-bucket totals as integer seconds, and divide by 3600.0 once at the end with `round(value, 2)`. This avoids drift across many sub-intervals (a real concern with weekly calendars containing 50+ events).

## Implementation Approach — Copy and Adjust, Never Rewrite

Open `backend/apps/priority_guardian/services/calendar_service.py`. Replace the body of `compute_allocation_from_events` with the new sweep-line implementation. **Do not** modify any other function in this file. **Do not** touch `match_keywords`, `is_all_day_event`, `is_declined_event`, `is_cancelled_event`, `compute_event_duration_hours`, `compute_week_boundaries`, `to_rfc3339`, `compute_time_allocation`, or `_empty_allocation`. The new implementation reuses these helpers as-is — preserve their signatures and behavior.

The function's docstring needs updating to describe the new attribution model. The return shape stays identical — same keys, same nesting, same types.

If you find yourself wanting to refactor anything else in `calendar_service.py` while you're in there, stop. Don't.

### Concrete sub-tasks for this file

1. Update the docstring of `compute_allocation_from_events` to describe interval sweep + distinct bucket attribution and reference the four-bucket model.
2. Rewrite the function body to:
   - Filter events using existing helpers (`is_all_day_event`, `is_declined_event`, `is_cancelled_event`, `compute_event_duration_hours <= 0`).
   - For each filtered event, compute claims using existing `match_keywords` behavior (title-only). Claims are the distinct matched priority buckets, or `["other"]` if no priority matches.
   - Sweep over UTC epoch-second boundaries.
   - For each atomic interval, union all distinct bucket claims from covering events into a set `S`.
   - Split that interval equally across those distinct buckets: each bucket in `S` gets `L / len(S)` seconds. Use `Fraction` from the standard library OR accumulate as integer numerator/denominator pairs — keep integer arithmetic throughout the sweep. Convert to hours via `value / 3600.0` and round to 2 decimals **once at the very end**.
   - Track `keyword_event_counts` separately by walking the filtered event list once and incrementing per matched keyword (preserve today's behavior — a multi-keyword title event increments each matched bucket's count).
   - Compute `total_tracked_hours` as the sum of all sub-interval lengths in seconds, divided by 3600 and rounded.
3. Set `bar_segments` to mirror `keyword_hours` + `other_hours` as described above.
4. Leave the surrounding code (imports, helper functions, `compute_time_allocation`, `_empty_allocation`) untouched.

### Files to change

- `backend/apps/priority_guardian/services/calendar_service.py` — rewrite `compute_allocation_from_events` body and docstring only. **The only allowed non-function change in this file is adding `from fractions import Fraction` to the existing import block** (if you choose `Fraction` for integer arithmetic; alternatively use plain integer numerator/denominator pairs and skip this import). All other imports, helper functions, and the rest of the file stay byte-identical.

### Files NOT to change in this increment

- `backend/apps/priority_guardian/services/weekly_report_service.py` — already calls the function correctly. No change.
- `backend/apps/priority_guardian/services/snapshot_service.py` — already calls the function correctly. The new return shape is identical, so snapshot writes pick up the corrected hours automatically. No change.
- `backend/apps/priority_guardian/routers/calendar_router.py` — unaffected. No change.
- Any widget code — unaffected. The response shape is identical.
- DB models, migrations — no schema change.

## Unit Tests

Add a new test class `TestSweepLineAllocation` to `tests/unit/priority_guardian/test_calendar_service.py`. **Existing tests in this file that assert the old buggy behavior must also be updated in this same increment** — see "Existing tests that will fail" section below. Do not delete existing tests; adjust their assertions.

### Required test cases

Each test builds a minimal event dict (mirror existing test fixtures in the file) and asserts the output dict's specific fields. Use the helper pattern already present in the file for constructing events with `start.dateTime` / `end.dateTime` / `id` / `summary`.

1. **`test_no_overlap_baseline_matches_naive_sum`** — Three non-overlapping events (P1 1h, P2 1h, untagged 1h). Asserts P1=1.0, P2=1.0, other=1.0, total=3.0. Confirms the new algorithm degenerates to the old behavior when nothing overlaps.

2. **`test_case_a_cross_priority_partial_overlap`** — P1 15-17 + P2 16-16:30. Asserts P1=1.75, P2=0.25, other=0.0, total=2.0. Asserts P1 event_count=1, P2 event_count=1.

3. **`test_case_b_same_priority_partial_overlap`** — P1 15-17 + P1 16-16:30. Asserts P1=2.0, total=2.0. Asserts P1 event_count=2.

4. **`test_case_c_priority_plus_untagged_overlap`** — P1 15-17 + untagged 16-16:30. Asserts P1=1.75, other=0.25, total=2.0.

5. **`test_case_d_two_untagged_overlap`** — Two untagged events 15-17 + 16-16:30. Asserts other=2.0, total=2.0.

6. **`test_case_e_multi_keyword_single_event`** — Single event "P1 P2 sync" 15-17, no overlapping events. Asserts P1=1.0, P2=1.0, total=2.0. Asserts P1 event_count=1, P2 event_count=1.

7. **`test_three_way_overlap_equal_split`** — P1, P2, P3 events all spanning identical 15-16. Asserts each bucket gets within 0.01h of 0.333, total=1.0. Use `pytest.approx(0.33, abs=0.01)`.

8. **`test_full_containment`** — P1 15-17, P2 15:30-16:00 (fully inside P1). Walkthrough: 15:00-15:30 = {P1} → P1 += 0.5; 15:30-16:00 = {P1, P2} → P1 += 0.25, P2 += 0.25; 16:00-17:00 = {P1} → P1 += 1.0. Asserts P1=1.75, P2=0.25, total=2.0.

9. **`test_back_to_back_no_overlap`** — P1 15-16, P2 16-17 (touching but not overlapping). Asserts P1=1.0, P2=1.0, total=2.0.

10. **`test_zero_length_event_excluded`** — P1 15-17 + zero-duration event 16-16. Asserts the zero-duration event is filtered out (existing behavior); P1=2.0, total=2.0.

11. **`test_invariant_total_equals_bucket_sum`** — Parametrized over cases (a) through (e): assert `keyword_hours["P1"] + keyword_hours["P2"] + keyword_hours["P3"] + other_hours == pytest.approx(total_tracked_hours, abs=0.02)`. The 0.02 tolerance matches invariant 1 in the spec — see the rounding-tolerance explanation there. Do not tighten to 0.01.

12. **`test_invariant_total_equals_event_union`** — For cases (a) through (e): independently compute the union of all filtered event intervals using a separate naive interval-merge implementation, divide by 3600, and assert it equals `total_tracked_hours` within 0.01h. This is a cross-check that the sweep-line implementation produces the right total.

13. **`test_bar_segments_mirrors_keywords_and_other`** — For any of the cases, assert `bar_segments == {"P1": keyword_hours["P1"], "P2": keyword_hours["P2"], "P3": keyword_hours["P3"], "other": other_hours}`.

14. **`test_empty_event_list`** — `compute_allocation_from_events([])` returns all zeros, all event counts zero, `bar_segments` all zeros.

**Out of scope for this increment:** No DST-specific test. The existing `compute_event_duration_hours` parses ISO datetimes with offsets via `datetime.fromisoformat` and computes elapsed seconds via subtraction, which already handles DST correctly when Google returns offset-suffixed timestamps (which it always does). If a separate DST regression test is desired, add it as a focused test against `compute_event_duration_hours` in isolation — not bundled into the sweep-line tests.

### Existing tests that will fail and must be updated in this increment

Several existing tests in `test_calendar_service.py` assert the old buggy behavior. Walk through every test in the file. For each test that calls `compute_allocation_from_events` AND involves overlapping events, recompute the expected output under the new algorithm and update the assertion. **Do not delete tests** — adjust their assertions. If a test was specifically designed to demonstrate the multi-keyword double-attribution behavior, rename it to reflect the new behavior and update its assertions accordingly.

For tests that do NOT involve overlapping events, expectations should be unchanged (invariant 4 above).

Add a comment at the top of any updated test explaining: `# Updated for interval sweep + distinct bucket attribution (overlap fix). Pre-fix expected values: <old values>.`

### Tests NOT in scope for this increment

- Integration tests against the live weekly report endpoint, snapshot writer, calendar endpoint — those are part 2.
- Widget rendering tests — out of scope, response shape unchanged.

## Pre-Deploy Tasks

Before committing this increment:

1. Run `pytest tests/unit/priority_guardian/test_calendar_service.py -v` and confirm all tests pass (existing + new).
2. Read `doc/OPERATIONS_PREDEPLOY.md` and check for any additional pre-deploy tasks relevant to a logic-only change (no schema change here, so migration head check still applies as routine but is not specifically triggered by this change).
3. Confirm no other test file imports `compute_allocation_from_events` or asserts on its output. Run `grep -r "compute_allocation_from_events" tests/` and confirm any other call sites are tested correctly.

**Do not deploy yet.** This is part 1 of 2. Part 2 covers integration verification and the production rollout step.

## What This Increment Does NOT Do

- Does NOT touch existing snapshot rows in `pg_weekly_snapshots` (fix forward only — pre-deploy snapshots stay inflated as a known accepted state).
- Does NOT change DB schema.
- Does NOT change response shape returned by any endpoint.
- Does NOT change widget code.
- Does NOT update the release note / user-facing comms (part 2).
- Does NOT include integration tests against the snapshot writer or weekly report (part 2).

## Production Behavior Change Summary (for awareness during review)

After this increment is deployed:
- All future weekly report generations return honest, deduplicated hours.
- All future snapshot writes capture honest, deduplicated hours.
- `actual_hours` per priority and bar segment values may shift downward or redistribute across priorities. Total tracked hours will never exceed the pre-fix naive total for overlapping calendars, but per-bucket numbers can move in either direction. Lower-priority buckets (P2/P3) can increase relative to pre-fix because the old `bar_segments` first-keyword-wins logic suppressed them; the new model allocates honestly based on actual claims.
- `total_hours_invested` (running aggregate) will grow more slowly post-fix.
- `avg_target_achievement` may shift downward as new lower snapshots roll in.
- Multi-keyword event tagging ("P1 P2 sync") now splits hours instead of double-counting — users relying on the old multi-attribution behavior will see lower per-bucket numbers.
- Pre-fix snapshot rows remain unchanged. Reports for past weeks built from those snapshots will continue to show inflated hours indefinitely.
