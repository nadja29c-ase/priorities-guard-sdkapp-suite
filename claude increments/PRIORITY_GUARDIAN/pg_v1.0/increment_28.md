Fix Pattern 3 (Priority Switching) — definition, window, and guidance
Files:

backend/apps/priority_guardian/services/pattern_service.py
mcp_server/priority_guardian/tools/get_patterns.py

Context: Pattern 3 currently counts all retirements within a 6-month window as "switching." This conflates successful completions with reactive abandonment. A user who ships 3 priorities in 3 months gets flagged the same as someone who keeps quitting. The pattern is product-hostile to fast executors. Three changes fix this.

Change 1: Fix switch definition in pattern_service.py
In _compute_priority_switching, only count a retirement as a "switch" if the priority was retired with incomplete goals/deliverables. A successfully completed priority is not a switch.
Logic for each retired priority in the window:

Flexible priority: if priority.goals is non-empty and all(g.achieved is True for g in priority.goals) → skip (successful completion, not a switch)
Deadline priority: if priority.deliverables is non-empty and all(d.done is True for d in priority.deliverables) → skip (successful completion, not a switch)
Empty goals/deliverables list ([]) → count as switch (empty is not completed — user never defined success criteria, likely abandonment or cleanup)
No goals and no deliverables → count as switch (same reasoning)

Critical: Use is True checks, not truthiness. all(g.achieved for g in priority.goals) would incorrectly pass if achieved were None. Must be all(g.achieved is True for g in priority.goals). Same for all(d.done is True for d in priority.deliverables).
The priority query in _compute_patterns_impl currently uses select(PgPriority). The relationships goals and deliverables use lazy="selectin" on the model, but this may not trigger automatically in async context with a raw select. Add explicit eager loading:
from sqlalchemy.orm import selectinload

priority_query = (
    select(PgPriority)
    .where(PgPriority.user_id == user_id)
    .options(
        selectinload(PgPriority.goals),
        selectinload(PgPriority.deliverables),
    )
)
This ensures goals and deliverables are loaded for all priorities in one query. All four pattern functions receive the same all_priorities list, so this benefits any future pattern that needs goal/deliverable data.
Add to the pattern dict: "successful_retirements_excluded" (integer) — how many retirements in the window were filtered out as successful completions. This is for auditability, not narration. The LLM does not need to mention it.
Update docstring to document the switch definition: retirements with all goals/deliverables completed are excluded. Empty or missing goals/deliverables count as switches.

Change 2: Pattern-specific window in pattern_service.py
Add a new constant:
SWITCHING_WINDOW_MONTHS = 3
In _compute_priority_switching, compute its own window start:
switching_window_start = current_week_start - relativedelta(months=SWITCHING_WINDOW_MONTHS)
Use switching_window_start instead of the global window_start_date for counting retirements and creations. relativedelta is already imported in this file.
Update the detail string to say "in the last 3 months" instead of "in the last 6 months."
Remove window_start_date from the function signature. Update the call site in _compute_patterns_impl to pass only current_week_start. Since _compute_patterns_impl is internal, this is a safe change.
Update docstring to reflect the 3-month window.

Change 3: Update guidance and description in get_patterns.py
Replace GUIDANCE_PRIORITY_SWITCHING with:
"This pattern detected multiple priorities that were retired with goals or deliverables still incomplete — "
"meaning they were abandoned before completion, not finished and moved on from. "
"Present both interpretations: this could be healthy, intentional pivoting — or it could signal reactive switching. "
"To help the user reflect, ask 1-2 of these questions based on what fits: "
"Did you have hard evidence that each pivot was more promising, or did it feel more like a gut call? "
"Were any of those switches driven by frustration, low energy, or feeling stuck rather than a clear reason to move on? "
"Keep the overall narration to 2-4 sentences including the question(s)."
Update DESCRIPTION (tool description string): if it mentions the switching window, use "recent months" instead of hardcoding "3 months" or "6 months." The service layer knows the exact window; the tool description should be durable across future window changes.

Do not change:

Database schema or migrations
Other pattern functions (1, 2, 4)
Handler or tool definition structure
The global ROLLING_WINDOW_MONTHS constant (still used for snapshot queries and other patterns)


Unit tests for pattern_service.py:
Test 1: 3 retired priorities in 3-month window, all with incomplete goals → retirements_in_window: 3, pattern fires.
Test 2: 3 retired priorities in 3-month window, all flexible with all goals achieved is True → retirements_in_window: 0, pattern does NOT fire. successful_retirements_excluded: 3.
Test 3: 3 retired priorities in 3-month window, 1 with all goals achieved + 2 with incomplete goals → retirements_in_window: 2, pattern does NOT fire (below threshold of 3).
Test 4: 4 retired priorities in 3-month window, 1 successfully completed + 3 incomplete → retirements_in_window: 3, pattern fires. successful_retirements_excluded: 1.
Test 5: 3 retired priorities in 3-month window, all with zero goals and zero deliverables → retirements_in_window: 3, pattern fires (no success criteria = likely abandonment).
Test 6: Deadline priority with all deliverables done is True → excluded from switch count.
Test 7: Mixed types — 1 flexible (all goals achieved), 1 deadline (deliverables incomplete), 1 flexible (no goals) → only the last 2 count as switches.
Test 8: 3 retirements but all outside 3-month window (within 6-month window) → pattern does NOT fire. Confirms pattern uses 3-month window, not global 6-month.
Test 9: successful_retirements_excluded field is present in pattern dict and correctly counts filtered retirements.
Test 10: Flexible priority with 2/3 goals achieved and 1 incomplete → counts as switch (partial completion is not full completion).
Test 11: Flexible priority with empty goals list ([]) → counts as switch (empty is not completed).
Unit tests for get_patterns.py:
Test 12: Verify GUIDANCE_PRIORITY_SWITCHING contains the two reflection questions.
Test 13: Verify guidance for switching pattern uses inline phrasing consistent with canonical order.
Test 14: Verify DESCRIPTION uses "recent months" not a hardcoded month count for the switching window.