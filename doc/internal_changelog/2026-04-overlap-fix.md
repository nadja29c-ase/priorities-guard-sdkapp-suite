# Calendar Event Overlap Fix — April 2026

**Internal documentation only.** This is not a user-facing release note.

---

## What Changed

The weekly report and time allocation features now correctly handle overlapping calendar events. Previously, when two events overlapped in time, both events' full durations were counted, inflating reported hours. The same issue affected events with multiple keywords in their title (e.g., "P1 P2 strategy meeting").

## What Users Might Notice

Starting from the deploy date, users may observe:

- **Lower hours per priority** — The `actual_hours` figure for P1, P2, or P3 may be lower than previously displayed.
- **Lower total tracked hours** — The overall "total hours invested" and weekly totals may decrease.
- **Slower growth rate** — Historical progress charts built from new data will show more modest growth.

These are the *correct* numbers. Users weren't actually working those extra hours — the report was double-counting calendar blocks that overlapped.

## How Overlapping Time Is Now Attributed

When events overlap, the overlapping portion is split evenly across all priorities involved:

- **Two-event overlap:** 50/50 split between the two priorities
- **Three-event overlap:** One-third each
- **Untagged events:** Count toward "other" using the same split logic

**Multi-keyword event titles** (e.g., "P1 P2 strategy review"): Previously credited to both priorities at full duration. Now split evenly between them, consistent with the overlap rule.

## Past Weeks

Reports for weeks before this fix are built from snapshots that were saved with the old counting logic. Those past-week numbers remain unchanged. The fix applies to the current week and all weeks going forward.

## Why This Was Changed

Honest tracking surfaces real signals. If a user sees an unexpected drop in P1 hours, it may indicate conflicted or double-booked calendar time that's worth resolving. The corrected numbers help users make better decisions about how they allocate time across priorities.

---

## Support Response Template

If a user asks about reduced hours, the following can be pasted directly:

> We recently fixed how Priority Guardian counts overlapping calendar events. Previously, if two events overlapped (say, a P1 block from 3-5pm and a P2 call from 4-4:30pm), both were counted at full duration — which inflated your totals. Now the overlapping time is split fairly between the priorities involved.
>
> Your reported hours may be lower than before, but this reflects what was actually happening in your calendar. If you're seeing a significant drop, it might be worth checking your calendar for double-booked or overlapping blocks.
>
> Past week reports are unchanged — they show what was recorded at the time. The new counting applies to this week and going forward.

---

## Known Telemetry Gap

**`overlap_segment_count` is logged from live endpoints but not persisted to snapshots.**

`overlap_segment_count` is internal telemetry used for logging during live allocation computation. It is **not** part of public endpoint responses (the router strips it before returning) and is **not** persisted to `pg_weekly_snapshots`. It exists solely as an INFO-level log field on `calendar.allocation_computed` events emitted by `compute_time_allocation`.

When debugging past weeks (e.g., "user X has weirdly low hours for week of 2026-04-13"), the snapshot row tells you the final hours but not whether overlap was a contributing factor — that signal lives only in live-computation logs.

**Diagnostic workaround (compliance-bound):** Do not access real user calendar data for diagnostic purposes. If a user requests support for a specific past week and explicitly consents to a temporary live recomputation, that is permitted — log the consent in the support ticket and recompute. For all other diagnostic scenarios, use synthetic events on an internal test account; do not inspect any real user's calendar at any point.

**Future improvement (optional):** Add `overlap_segment_count` as a nullable column on `pg_weekly_snapshots` if historical overlap diagnostics become operationally important.
