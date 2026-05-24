Claude Code Briefing: Verbatim Quality Gates — organize_thoughts and prioritize_clusters
Before starting: Read OPERATIONS_PREDEPLOY.md.
Reference implementation: mcp_server/priority_guardian/tools/create_priority.py — verbatim field pattern, _build_provenance_error, guidance constants, provenance check block at top of handle(). Copy this pattern exactly. Do not invent a different structure.
Scope: Two files only. Copy and adjust — do not rewrite, restructure, or improve anything not listed.

File 1: mcp_server/clarity/tools/organize_thoughts.py
Four changes:
A. Update DESCRIPTION
Add this block after the existing WHEN NOT TO CALL section, before AFTER TOOL RETURNS:
CALL PRECONDITION: user_thoughts_exhausted_verbatim must be non-empty.
Do NOT call this tool until the user has explicitly confirmed they have no more thoughts to add.
Never infer this from silence, a pause, or the number of items provided.
Do not change any other part of the description.
B. Add to INPUT_SCHEMA properties:
python"user_thoughts_exhausted_verbatim": {
    "type": "string",
    "description": (
        "Copy-paste the user's exact words confirming they are done adding thoughts. "
        "Must be non-empty. "
        "Examples: 'that's it', 'I think that's everything', 'done', 'nothing else comes to mind'. "
        "Do NOT set thoughts_exhausted=true and call this tool until the user has explicitly "
        "signaled they are done. Never infer completion from silence or item count."
    ),
    "minLength": 1,
},
Add "user_thoughts_exhausted_verbatim" to the "required" list.
C. Add guidance constant and _build_provenance_error helper at module level, before the handler. Identical pattern to create_priority.py:
pythonGUIDANCE_EMPTY_THOUGHTS_EXHAUSTED_VERBATIM = (
    "user_thoughts_exhausted_verbatim is empty. Do not call this tool until the user has "
    "explicitly confirmed they are done adding thoughts. "
    "Ask: 'Is there anything else on your mind, or shall we organize what you have so far?' "
    "Store their exact answer in user_thoughts_exhausted_verbatim."
)


def _build_provenance_error(error_code: str, instruction: str) -> mcp_types.CallToolResult:
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Provenance validation failed: {error_code}"
        )],
        structuredContent={
            "success": False,
            "error": error_code,
            "assistant_guidance": {
                "action": "ASK_CLARIFYING",
                "instruction": instruction,
            },
        },
        isError=True,
    )
D. Add provenance check at the very top of handle(), before the existing validation block:
pythonuser_thoughts_exhausted_verbatim = arguments.get("user_thoughts_exhausted_verbatim", "")
if not user_thoughts_exhausted_verbatim or not user_thoughts_exhausted_verbatim.strip():
    logger.info("organize_thoughts.provenance_failed",
                user_id=user_id,
                field="user_thoughts_exhausted_verbatim")
    return _build_provenance_error(
        "empty_thoughts_exhausted_verbatim",
        GUIDANCE_EMPTY_THOUGHTS_EXHAUSTED_VERBATIM,
    )
user_thoughts_exhausted_verbatim is a behavioral gate only — do not pass it to format_clusters or any downstream logic.

File 2: mcp_server/clarity/tools/prioritize_clusters.py
Three changes (no description update needed — existing description already says "after USER explicitly names" and "NEVER infer or guess"):
A. Add to INPUT_SCHEMA properties:
python"user_priorities_verbatim": {
    "type": "string",
    "description": (
        "Copy-paste the user's exact words explicitly naming their priorities. "
        "Must be non-empty. "
        "Examples: 'my P1 is the client project', 'I want to focus on health first, work second'. "
        "Do NOT call this tool until the user has explicitly stated which clusters or items "
        "are their priorities. Never infer priorities from context or conversation history."
    ),
    "minLength": 1,
},
Add "user_priorities_verbatim" to the "required" list.
B. Add guidance constant and _build_provenance_error helper at module level, before the handler. Each tool file has its own independent copy per ADR — do not import from organize_thoughts.py:
pythonGUIDANCE_EMPTY_PRIORITIES_VERBATIM = (
    "user_priorities_verbatim is empty. Do not call this tool until the user has explicitly "
    "named their priorities. "
    "Ask: 'Which of these feels most important to focus on right now? Name your P1, "
    "and optionally a P2 and P3.' "
    "Store their exact answer in user_priorities_verbatim."
)


def _build_provenance_error(error_code: str, instruction: str) -> mcp_types.CallToolResult:
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Provenance validation failed: {error_code}"
        )],
        structuredContent={
            "success": False,
            "error": error_code,
            "assistant_guidance": {
                "action": "ASK_CLARIFYING",
                "instruction": instruction,
            },
        },
        isError=True,
    )
C. Add provenance check at the very top of handle(), before the existing PrioritizeClustersRequest.model_validate call:
pythonuser_priorities_verbatim = arguments.get("user_priorities_verbatim", "")
if not user_priorities_verbatim or not user_priorities_verbatim.strip():
    logger.info("prioritize_clusters.provenance_failed",
                user_id=user_id,
                field="user_priorities_verbatim")
    return _build_provenance_error(
        "empty_priorities_verbatim",
        GUIDANCE_EMPTY_PRIORITIES_VERBATIM,
    )
user_priorities_verbatim is a behavioral gate only — do not pass it to _apply_priorities or any downstream logic.

Unit tests
Add to mcp_server/clarity/tests/ — extend existing test file or create new one:
For each tool, three tests:

Calling handle() with user_thoughts_exhausted_verbatim="" returns isError=True with error field "empty_thoughts_exhausted_verbatim" in structuredContent
Calling handle() with user_thoughts_exhausted_verbatim missing entirely returns same
Calling handle() with a non-empty verbatim field proceeds past the provenance gate — does not return a provenance error

Same three tests for prioritize_clusters with user_priorities_verbatim.
These are pure handler unit tests. Pass user_id="test", correlation_id="test", and minimal otherwise-valid arguments. No backend calls, no persistence mocking needed for the provenance tests.

Verification after deploy
Test in ChatGPT:

Start a brain dump with 6+ items, then stop without saying you're done. Tool must not fire.
Say "that's it" explicitly. Tool fires.
Show a board, stay silent about priorities. Tool must not fire.
Say "my P1 is the work cluster." Tool fires.
