Increment Briefing: Fix Semantic Drill-Down Friction in get_weekly_report
What's broken
When a user clearly asks to see a breakdown of a segment (e.g. "what's in Other?", "break down Other"), the LLM stops at a text proposal and asks the user to confirm groupings before calling get_weekly_report again. This creates an unnecessary extra round-trip. The intent was already expressed — the LLM should act on it immediately.
The same friction exists for within-priority breakdown requests.
Root cause
The assistant_guidance strings in get_weekly_report.py instruct the LLM to:

Propose groupings
Ask if the grouping looks right
Only then call the tool again

This was the original design (user-confirmed groupings). The correct behavior: if the user has expressed intent to drill into a segment, that expression IS the confirmation — call the tool immediately with best-effort groupings.
What to change
File: mcp_server/priority_guardian/tools/get_weekly_report.py
Changes are guidance strings only — no logic, no schema, no backend changes.

1. Update module docstring
Change the docstring at the top of the file from:
On first call: Shows P1/P2/P3 + "Other" slice. LLM proposes semantic groupings.
On second call (with semantic_groupings): Shows priority slices + user-confirmed
semantic category slices. No persistence - purely conversational refinement.
To:
On first call: Shows P1/P2/P3 + "Other" slice. If other_hours > 0, LLM immediately
groups allEvents into semantic categories and calls the tool again with semantic_groupings.
No confirmation step — the user's intent to see the report is sufficient.
On second call (with semantic_groupings): Shows priority slices + semantic subcategory
slices. No persistence - purely conversational refinement.

2. Update semantic_groupings input schema description
Change:
python"description": (
    "User-confirmed semantic categories for the target slice. "
    "When provided, replaces the target category's slice in the pie chart "
    "with these subcategory slices. Only pass this after user confirms groupings."
),
To:
python"description": (
    "Semantic categories for the target slice, derived from allEvents. "
    "When provided, replaces the target category's slice in the pie chart "
    "with these subcategory slices. Pass immediately after grouping allEvents — "
    "no user confirmation step required."
),

3. Replace GUIDANCE_SEMANTIC_PROPOSAL_TEMPLATE
Replace the entire constant with:
pythonGUIDANCE_SEMANTIC_PROPOSAL_TEMPLATE = (
    "The user has {other_hours:.1f} hours of non-priority time. "
    "Group the non-priority events from allEvents into approximate semantic categories "
    "(e.g. 'Client calls', 'Admin', 'Unclassified'). "
    "IMMEDIATELY call get_weekly_report again with semantic_target='other' and "
    "semantic_groupings containing your grouped categories (category name, hours, event_count). "
    "Do NOT propose the groupings in text first. Do NOT ask the user to confirm. "
    "Just compute and call the tool. "
    "CRITICAL: NEVER interpret non-priority time as wasted, unfocused, or dilutive. "
    "NEVER assume non-priority time should be strategic or priority-related."
)

4. Replace GUIDANCE_WITHIN_PRIORITY_BREAKDOWN
Replace:
pythonGUIDANCE_WITHIN_PRIORITY_BREAKDOWN = (
    "You can also propose a within-priority breakdown for any single priority. "
)
With:
pythonGUIDANCE_WITHIN_PRIORITY_BREAKDOWN = (
    "If the user asks to drill into a specific priority's time, "
    "group that priority's events from allEvents into subcategories and immediately call "
    "get_weekly_report again with semantic_target set to that priority's keyword (e.g. 'P1') "
    "and semantic_groupings containing the breakdown. "
    "Do NOT ask for confirmation first."
)

5. Update _build_assistant_guidance — rename MODE labels in inline comments only
The comment # MODE 1 and # MODE 2 are confusing given the new behavior. Update to:
python    if has_semantic_groupings:
        # Semantic groupings already applied — brief neutral observation
        guidance_parts.append(GUIDANCE_SEMANTIC_PROVIDED)
    else:
        # Initial report — LLM will immediately group and re-call if other_hours > 0
        ...

What NOT to change

No changes to _build_pie_slices logic
No changes to the handle() function
No changes to the backend
No changes to the widget
No schema changes beyond the description strings above


Tests
Unit tests (tests/unit/mcp_pg/test_weekly_report_handler.py):
Check the existing tests still pass. Specifically verify:

GUIDANCE_SEMANTIC_PROPOSAL_TEMPLATE renders correctly with other_hours substitution (the {other_hours:.1f} format string must still work after the change)
GUIDANCE_WITHIN_PRIORITY_BREAKDOWN is still included in guidance output when all_events is non-empty and has_semantic_groupings is False

No new test cases required — the guidance strings are LLM instructions, not testable behavior. Existing coverage of _build_assistant_guidance is sufficient to catch regressions.

Pre-deploy
Read OPERATIONS_PREDEPLOYMENT.md before committing anything.