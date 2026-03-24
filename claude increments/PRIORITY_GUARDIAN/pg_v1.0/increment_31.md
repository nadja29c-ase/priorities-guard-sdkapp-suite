Updated instruction for Claude Code:

Bug fix: get_weekly_report — prevent semantic breakdown on snapshot data
File: mcp_server/priority_guardian/tools/get_weekly_report.py
Problem: When serving a completed week (snapshot), allEvents is empty but the handler still (1) offers semantic breakdown in guidance, and (2) accepts semantic_groupings input. The LLM fabricates categories. Observed in production.
Two fixes:
Fix 1: Handler guard — reject semantic_groupings when no event data
In handle(), after the backend call returns and data is extracted, before _build_pie_slices:
If has_semantic_groupings is true AND all_events is empty → return an error response. Use the same _build_provenance_error-style pattern (but inline, since this file doesn't import that helper):
pythonif has_semantic_groupings and not all_events:
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text="Semantic breakdown not available for this week.",
        )],
        structuredContent={
            "success": False,
            "error": "semantic_breakdown_unavailable",
            "assistant_guidance": (
                "Semantic breakdown is not available for past weeks — "
                "detailed event data is only available for the current week. "
                "Do NOT propose or offer any breakdown. "
                "Present the report as-is."
            ),
        },
        isError=True,
    )
Place this after all_events = data.get("all_events", []) and before the no-priorities early return check.
Fix 2: Guidance guard — don't offer breakdown when no events
In _build_assistant_guidance, change the GUIDANCE_WITHIN_PRIORITY_BREAKDOWN append to be conditional:
pythonif all_events:
    guidance_parts.append(GUIDANCE_WITHIN_PRIORITY_BREAKDOWN)
This prevents the LLM from being told it can offer breakdowns when there's no data.
No other changes. The GUIDANCE_SEMANTIC_NO_EVENTS_TEMPLATE path for "Other" hours is already correct.
Tests
Unit tests (add to existing weekly report test file):

test_semantic_groupings_rejected_when_no_events — call handler with semantic_groupings provided but all_events empty in backend response → returns isError: true with semantic_breakdown_unavailable error
test_no_within_priority_breakdown_offered_when_no_events — call _build_assistant_guidance with all_events=[] and has_semantic_groupings=False → returned guidance does NOT contain GUIDANCE_WITHIN_PRIORITY_BREAKDOWN text
test_within_priority_breakdown_offered_when_events_exist — call _build_assistant_guidance with non-empty all_events → returned guidance DOES contain GUIDANCE_WITHIN_PRIORITY_BREAKDOWN text
