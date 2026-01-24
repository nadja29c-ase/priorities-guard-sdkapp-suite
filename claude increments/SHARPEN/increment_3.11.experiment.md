
Claude Code Briefing: Sharpen Increment — Tool-as-Recorder Pattern
Objective
Refactor frame_initiative_intent to eliminate premature tool calls by:

Making the tool description concise and precondition-focused
Returning zero-information errors to the model (removing reward signal)
Maintaining full server-side logging for debugging
Preserving old guidance messages for potential rollback

Context
Problem diagnosed: LLM calls tool early (with *_stated_by_user: false) because failure responses return educational guidance — creating a reward loop. The model learns: call → fail → get instructions.
Pattern to implement: Tool as final recorder. The assistant must verify preconditions internally before calling. Tool failure is not a feedback mechanism.
Files to modify
mcp_server/sharpen/tools/frame_initiative_intent.py
Changes
1. Create _LEGACY_GUIDANCE dict at module level
Store all current GUIDANCE_* constants in a single dict:
python_LEGACY_GUIDANCE = {
    "provenance_failed": GUIDANCE_PROVENANCE_FAILED,
    "empty_pain_verbatim": GUIDANCE_EMPTY_PAIN_VERBATIM,
    "empty_observable_verbatim": GUIDANCE_EMPTY_OBSERVABLE_VERBATIM,
    "missing_fields": GUIDANCE_MISSING_FIELDS,
    "multiple_stakeholders": GUIDANCE_MULTIPLE_STAKEHOLDERS,
    "confirmed": GUIDANCE_CONFIRMED,
}
Comment: "Preserved for rollback if zero-info experiment fails."
Remove the individual GUIDANCE_* constants after moving to dict (except GUIDANCE_CONFIRMED which is still used in success path).
2. Replace DESCRIPTION
Current: ~200 words with sequence, style notes, examples.
New (≤60 words, no step lists, no examples, no embedded questions):
pythonDESCRIPTION = """Records confirmed problem framing: WHO benefits and WHY (outcome derived from pain + observable).

CALL PRECONDITIONS — DO NOT CALL if any would be false:
- who_stated_by_user
- why_reframed_from_observable  
- user_confirmed_framing
- user_pain_verbatim non-empty
- user_observable_verbatim non-empty

FACILITATOR MODE: One question at a time. Wait for answer. Store verbatim. Reflect and confirm before calling."""
3. Modify handler error responses
Validation functions still execute and return structured results. Handler logs the result, then discards detail before returning.
Every isError=True return becomes:
pythonlogger.info(
    "frame_initiative_intent.rejected",
    error_type=provenance_result["error_type"],
    failed_checks=provenance_result.get("failed_checks", []),
    input_snapshot={
        "who": validated_request.who,
        "user_pain_verbatim": bool(pain_verbatim),  # Log presence, not content
        "user_observable_verbatim": bool(observable_verbatim),
        "why": validated_request.why,
        "who_stated_by_user": who_stated,
        "why_reframed_from_observable": why_reframed,
        "user_confirmed_framing": user_confirmed,
    },
)
return mcp_types.CallToolResult(
    structuredContent={"status": "incomplete"},
    isError=True,
)
This applies to all failure paths:

Pydantic validation failure
Provenance validation failure (empty pain, empty observable, boolean checks)
Structural validation failure (missing fields, multiple stakeholders)

4. Keep success response unchanged
The confirmed=True path with assistant_guidance using GUIDANCE_CONFIRMED stays as-is. Guidance on success is appropriate — the tool completed its job as recorder.
5. Handler structure clarification

Validation functions in tool_logic.py remain unchanged
Handler still calls them and receives structured failure reasons
Handler logs the structured result
Handler intentionally discards detail in the response to model
This is a design choice, not accidental deletion

What NOT to change

tool_logic.py — validation logic stays intact
INPUT_SCHEMA — field descriptions already explain requirements
Success response structure
Tool registration / annotations

Operational Requirements (non-user-facing)

Server-side logging of all validation failures:

Error type
Which gates failed
Input snapshot (booleans and field presence, not full content)
Existing timestamp from structlog


Handler explicitly discards failure details:

Validation functions still execute and return structured results
Handler logs the result server-side
Handler returns only {"status": "incomplete"} to model
This is intentional design, not accidental loss



Unit Tests
File: tests/unit/mcp_sharpen/test_frame_initiative_intent.py
Update existing error tests:

All error cases expect {"status": "incomplete"} in structuredContent
No assistant_guidance key in error responses
No error or failed_checks keys in error responses

Add new tests:

Verify _LEGACY_GUIDANCE dict exists and contains expected keys
Verify success response still contains assistant_guidance

Do not change:

Success case tests (structure unchanged)

Manual Validation Criteria
Before/after comparison in MCP Inspector:

Same prompt test: Use "Help me sharpen the scope for this initiative: My team needs to work on improving our onboarding process."

Before: Expect premature tool call with who_stated_by_user: false
After: Expect assistant asks clarifying questions first


Tool call count: For a complete flow, tool should be called exactly once (at confirmation)
Transcript evidence: One logged session showing:

Assistant asks WHO question → waits
Assistant asks PAIN question → waits
Assistant asks OBSERVABLE question → waits
Assistant reflects and asks for confirmation → waits
Tool called once with all booleans true



Acceptance Criteria

 _LEGACY_GUIDANCE dict exists with all old messages preserved
 GUIDANCE_CONFIRMED still used in success path
 DESCRIPTION is ≤60 words
 DESCRIPTION has no step lists, examples, or embedded questions
 All isError=True returns have only {"status": "incomplete"}
 All validation failures logged server-side with error_type, failed_checks, input_snapshot
 Success response unchanged (still has assistant_guidance)
 All unit tests pass
 No changes to tool_logic.py

Rollback Plan
If experiment fails (LLM gets stuck, deadlocks, or user experience degrades):

Restore GUIDANCE_* constants from _LEGACY_GUIDANCE dict
Restore error responses with assistant_guidance containing specific instructions
Keep logging additions (those are valuable regardless)
