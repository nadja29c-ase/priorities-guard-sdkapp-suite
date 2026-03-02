Add deadline proximity filter to Pattern 2 (Abandoned Priority) for deadline priorities
Files:

backend/apps/priority_guardian/services/pattern_service.py
mcp_server/priority_guardian/tools/get_patterns.py

Context: Pattern 2 currently fires for any active priority averaging < 1.0h/week over the last 4 snapshots, regardless of priority type. For deadline priorities, low hours are only meaningful when the deadline is approaching. A priority with 0h/week but a deadline 3 months away is not abandoned — it's just not urgent yet. Flexible priorities remain unchanged.

Change 1: pattern_service.py — _compute_abandoned_priorities
Add a constant:
ABANDONED_DEADLINE_PROXIMITY_WEEKS = 4
Add current_week_start as a parameter to _compute_abandoned_priorities. This keeps deadline proximity computation anchored to the same week boundary as the snapshot system — do not use datetime.now() or raw today to avoid off-by-one inconsistencies with the week-based snapshot system.
Update the call site in _compute_patterns_impl to pass current_week_start.
Add deadline-aware logic after the existing if priority.status != "active": continue check:
For deadline priorities (priority.type == "deadline"):

Read priority.deadline (a date field, always present for deadline priorities per the ck_pg_priorities_type_field_consistency constraint)
Compute weeks remaining: (priority.deadline - current_week_start).days // 7
Clamp to zero: weeks_until_deadline = max(0, computed_value) — a past deadline is the strongest signal, but negative values must not leak into LLM narration
Only proceed with the abandoned priority check if weeks_until_deadline <= ABANDONED_DEADLINE_PROXIMITY_WEEKS
If deadline is > 4 weeks away, skip this priority entirely

For flexible priorities (priority.type == "flexible"):

No change. Current logic applies as-is.

Add weeks_until_deadline to the pattern dict for deadline priorities only. This lets the LLM say "your birthday party is in 2 weeks and it's gotten almost no time." Do not add this field for flexible priorities.
Update the function docstring to document:

Flexible: fires when avg < 1.0h/week over last 4 snapshots
Deadline: same threshold + deadline must be ≤ 4 weeks away (relative to current_week_start)
Past deadlines are clamped to 0 weeks remaining


Change 2: get_patterns.py — Update tool description and guidance
Update DESCRIPTION (the tool description string). The current text mentions "low-investment priorities" without specifying the deadline proximity condition. OpenAI reviews tool descriptions against actual behavior — mismatch is a rejection risk.
Update the relevant part to reflect:

Low-investment detection for flexible priorities (4-week average below threshold)
Low-investment detection for deadline priorities (same threshold, only when deadline is within 4 weeks)

Keep the description concise — don't expose exact thresholds, just the behavioral distinction.
Update GUIDANCE_ABANDONED_PRIORITY — add:

If the pattern includes weeks_until_deadline, mention how close the deadline is. Frame it as context, not pressure (e.g., "with about 3 weeks to go" not "you only have 3 weeks left!").
If weeks_until_deadline is 0, the deadline has passed or is this week — frame accordingly without judgment.


Do not change:

Database schema or migrations
Pattern thresholds for flexible priorities
Any other pattern function
Any other tool or service file


Unit tests for pattern_service.py:
Test 1: Deadline priority, avg < 1.0h, deadline in 3 weeks from current_week_start → pattern fires, weeks_until_deadline = 3.
Test 2: Deadline priority, avg < 1.0h, deadline in 8 weeks → pattern does NOT fire.
Test 3: Deadline priority, avg < 1.0h, deadline in exactly 4 weeks → pattern fires (boundary, ≤ 4). weeks_until_deadline = 4.
Test 4: Deadline priority, avg < 1.0h, deadline in 5 weeks → pattern does NOT fire (boundary, > 4).
Test 5: Flexible priority, avg < 1.0h → pattern fires as before, no weeks_until_deadline field in output.
Test 6: Deadline priority, avg ≥ 1.0h, deadline in 2 weeks → pattern does NOT fire (hours above threshold).
Test 7: Deadline priority, avg < 1.0h, deadline already passed (deadline < current_week_start) → pattern fires, weeks_until_deadline = 0 (clamped).
Test 8: Deadline priority, avg < 1.0h, deadline is exactly current_week_start → pattern fires, weeks_until_deadline = 0.