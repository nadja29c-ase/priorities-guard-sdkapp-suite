Enrich pattern data with per-week detail + compose assistant_guidance per-pattern
Files:

backend/apps/priority_guardian/services/pattern_service.py
mcp_server/priority_guardian/tools/get_patterns.py

Context: Two related issues being fixed together:

The consistency_streak pattern only returns streak_weeks: 6 — no per-week hours. The LLM can't reference specific weeks ("you put in 5h that week but still showed up") because it doesn't have the data. It resorts to vague guessing ("weeks where hours were likely lighter").
The assistant_guidance is one monolithic string for all patterns. Each pattern has different narration goals. Guidance should be composed per-pattern.


Change 1: Enrich pattern data in pattern_service.py
Pattern 1 — _compute_consistency_streaks:
After computing streak_value and passing the threshold check, build a weekly_detail list from the exact snapshots that determined the streak — the consecutive non-zero weeks counting backward from most recent. Do not include non-streak weeks.
Each entry (ordered chronologically, oldest first):
{
    "week_start": "2026-01-12",
    "actual_hours": 6.0,
    "target_hours": 8.0
}
week_start must be explicitly converted to string via .isoformat() — do not rely on implicit serialization.
target_hours comes from the snapshot row, not the priority object. NULL if snapshot has no target. This ensures historical accuracy if targets changed over time.
Hard cap: weekly_detail length is min(streak_weeks, 8). Take the 8 most recent streak weeks if streak exceeds 8. The LLM doesn't need 26 weeks to ground narration.
Sanity check: after building weekly_detail, verify its length equals min(streak_weeks, 8). If not, log a warning and omit the pattern entirely — do not send a pattern with empty or mismatched weekly_detail to the LLM.
Add to the pattern dict:

"weekly_detail": the capped list

Do NOT add a separate top-level target_hours from the priority object. The per-week target_hours from snapshots is the only source of truth.
Pattern 2 — _compute_abandoned_priorities:
Add weekly_detail with the last 4 qualifying snapshots. Same entry format: week_start (via .isoformat()), actual_hours, target_hours from snapshot.
Order: chronological, oldest first.
Same sanity check: if weekly_detail length != 4, log warning and omit pattern.
Pattern 3 — _compute_priority_switching:
No enrichment needed. Already has the right data.
Pattern 4 — _compute_priority_protection:
Add period_summary:
{
    "prior_avg_priority_hours": float,
    "recent_avg_priority_hours": float,
    "prior_avg_total_hours": float,
    "recent_avg_total_hours": float,
    "total_hours_change_pct": float
}
These values are already computed in the function — just surface them.
General:

Do not change function signatures, return types, or the overall response structure. The patterns list still contains dicts. These are additive fields.
decimal_to_float_recursive already handles nested conversion — verify it preserves None values as None (JSON null) and does not mutate string fields like week_start.


Change 2: Compose assistant_guidance per-pattern in get_patterns.py
Replace the single GUIDANCE_PATTERNS_FOUND constant with:
GUIDANCE_COMMON — short, applies to every patterns-found response:

Keep it conversational. No bullet points, no headers, no numbered lists. Weave patterns into a natural narrative.
Observed numbers ("0.5h/week", "6-week streak", "22% growth") are good — state them. Internal thresholds and computation rules must never be mentioned.
Do not use the word "abandoned" — paraphrase neutrally (e.g., "getting very little time lately").
Do not repeat any internal field names or identifiers from the data verbatim — use the narration_label or your own phrasing instead.
If a pattern has calendar_keyword null, refer to the priority by name only — do not mention a keyword.
For retired priorities, frame the pattern as historical ("before you retired it" or "when it was active") — do not imply the pattern is ongoing.
Do not compute or invent patterns beyond what this response contains.

GUIDANCE_CONSISTENCY_STREAK:

The dashboard already shows the streak count — do not just restate it.
weekly_detail contains the actual hours and target hours for each week in the streak. Use these specific numbers in your narration.
If some weeks fell significantly below target but the user still logged time, acknowledge that showing up consistently matters more than hitting the target every week. Reference the specific week's hours.
If hours are steady across weeks, note the reliability.
If the streak is 4+ weeks, note that this has moved past initial motivation into habit territory — the weeks where hours were lowest are actually the most telling because the user kept going anyway.
Keep it to 2-3 sentences max.

GUIDANCE_ABANDONED_PRIORITY:

weekly_detail contains the actual hours for the last 4 weeks. Reference these specific numbers rather than just the average.
State the observed pattern neutrally.
Ask what the user wants to do about it — do not prescribe action.
Do not judge. Do not say "you should retire this" or "you're neglecting this."
Keep it to 1-2 sentences plus a question.

GUIDANCE_PRIORITY_SWITCHING:

Present both interpretations: this could be healthy pivoting and adapting, or it could signal difficulty committing.
Ask what's been driving the changes.
Do not lean toward either interpretation — present them equally.
Keep it to 2-3 sentences.

GUIDANCE_PRIORITY_PROTECTION:

Acknowledge warmly that the user protected this priority's time despite growing calendar pressure.
period_summary contains the exact numbers. Reference them: priority hours stayed at ~Xh/week while total calendar grew from ~Yh to ~Zh (N% increase).
This is a positive signal — the user is defending what matters to them.
Keep it to 1-2 sentences.

Mapping dict:
PATTERN_GUIDANCE = {
    "consistency_streak": GUIDANCE_CONSISTENCY_STREAK,
    "abandoned_priority": GUIDANCE_ABANDONED_PRIORITY,
    "priority_switching": GUIDANCE_PRIORITY_SWITCHING,
    "priority_protection": GUIDANCE_PRIORITY_PROTECTION,
}
Canonical guidance order: [consistency_streak, abandoned_priority, priority_switching, priority_protection]
Change _build_assistant_guidance:
For the PATTERNS_FOUND case:

Start with GUIDANCE_COMMON
Collect which pattern_type values are present in data["patterns"]
Iterate the canonical order list above (not the patterns array). For each type present, append its guidance using inline phrasing like "When narrating consistency streak patterns:" — do NOT use bracket labels like "[Consistency Streak]:" as these leak into user-facing text as headers
Skip types not present in the data. Skip unknown pattern_types gracefully (forward-compatible).
Join with double newline separators

This ensures guidance order is stable regardless of how the backend sorts patterns.
INSUFFICIENT_WEEKS and NO_PATTERNS paths remain unchanged.

Do not change:

Database schema or migrations
Pattern thresholds or detection logic
Handler handle() function structure
Tool definition, input schema, or registration
Any other tool or service file


Unit tests for pattern_service.py:
Test 1: _compute_consistency_streaks with 6-week streak on flexible priority → weekly_detail has 6 entries, chronological order (oldest first), each entry has week_start (string via isoformat), actual_hours, target_hours from snapshot. Values match the snapshot data.
Test 2: _compute_consistency_streaks with deadline priority (snapshot target_hours is NULL) → weekly_detail entries have target_hours: None (serializes as JSON null).
Test 3: _compute_consistency_streaks with 12-week streak → weekly_detail capped at 8 entries (the 8 most recent streak weeks, chronologically ordered). streak_weeks still reports 12.
Test 4: _compute_consistency_streaks builds weekly_detail from exactly the streak slice — if weeks 1-4 have hours > 0, week 5 has 0, weeks 6-8 have hours > 0, the streak is 4 and weekly_detail contains only weeks 1-4 (the consecutive run from most recent).
Test 5: _compute_abandoned_priorities returns weekly_detail with 4 entries matching the last 4 qualifying snapshots, chronological order, week_start as string.
Test 6: _compute_priority_protection returns period_summary with correct prior_avg_priority_hours, recent_avg_priority_hours, prior_avg_total_hours, recent_avg_total_hours, total_hours_change_pct.
Test 7: decimal_to_float_recursive converts Decimal values inside nested weekly_detail dicts to float, preserves None as None, does not mutate string fields.
Unit tests for get_patterns.py:
Test 8: Single pattern (consistency_streak) → guidance contains GUIDANCE_COMMON text + GUIDANCE_CONSISTENCY_STREAK text, does NOT contain text from other pattern guidance constants.
Test 9: All 4 patterns present → guidance contains GUIDANCE_COMMON + all 4 per-pattern guidance blocks in canonical order (streak, abandoned, switching, protection) regardless of input pattern order.
Test 10: No patterns (reason=NO_PATTERNS) → guidance is GUIDANCE_NO_PATTERNS, no per-pattern content.
Test 11: Insufficient weeks → guidance uses GUIDANCE_INSUFFICIENT_DATA_TEMPLATE, no per-pattern content.
Test 12: Unknown pattern_type in patterns list → skipped gracefully, no error, other patterns still get their guidance in canonical order.