All four valid. Minimal adjustments only:

Claude Code Briefing — Pre-Submission Hardening: Schema & Timeout Fixes (v5)
Increment: Pre-submission hardening
Scope: Priority Guardian MCP server only
Risk: Low — no logic changes, no backend changes, no new dependencies

Context
Two issues identified during pre-submission audit:

additionalProperties: false missing from most tool input schemas. The OpenAI Apps SDK Reference uses this in every example including empty schemas. Without it, a schema allows arbitrary undeclared keys, which conflicts with the submission guidelines' data minimization requirements.
Inconsistent backend call timeout handling. get_priorities correctly wraps all backend calls with asyncio.wait_for at ≤8s. Other tools use bare backend_get/backend_post calls — the effective timeout falls through to the httpx.AsyncClient default of 30 seconds, exceeding ChatGPT's ~10-second MCP tool execution window. Some tool files also define BACKEND_TIMEOUT constants that are never passed to any call — dead config.


Fix 1 — additionalProperties: false on all input schemas
Scope rule: Every "type": "object" anywhere in any INPUT_SCHEMA must have "additionalProperties": False. This includes top-level schemas, nested objects inside items, oneOf, anyOf, and any other deeply nested object structure. No exceptions.
Schema already correct — no changes needed:

tools/create_priority.py
tools/inspect_adapt.py
tools/onboarding_calendar_setup.py

Files that need the fix — Fix 1 only (timeout fix handled separately in Fix 2):
FileWhat needs addingtools/get_weekly_report.pyTop-level + nested semantic_groupings items objecttools/get_priorities.pyTop-level (empty schema)tools/get_patterns.pyTop-level (empty schema)tools/widget_tools/add_priority.pyTop-level + any nested objectstools/widget_tools/update_priority.pyTop-level + any nested objectstools/widget_tools/delete_priority.pyTop-level + any nested objectstools/widget_tools/add_deliverable.pyTop-level + any nested objectstools/widget_tools/update_deliverable.pyTop-level + any nested objectstools/widget_tools/delete_deliverable.pyTop-level + any nested objectstools/widget_tools/add_goal.pyTop-level + any nested objectstools/widget_tools/update_goal.pyTop-level + any nested objectstools/widget_tools/delete_goal.pyTop-level + any nested objectstools/widget_tools/connect_google_calendar.pyTop-level + any nested objectstools/widget_tools/disconnect_google_calendar.pyTop-level + any nested objects
If the widget tools directory contains files not listed above, apply the same rule. The schema validation test will catch any missed file.
For empty schemas the correct shape is:
pythonINPUT_SCHEMA = {
    "type": "object",
    "properties": {},
    "required": [],
    "additionalProperties": False,
}

Fix 2 — Consistent timeout wrapping on all backend calls
Timeout constant: Define TIMEOUT_S = 8.0 at module level in each file that makes backend calls. Use this constant in all asyncio.wait_for calls within that file. Do not inline magic numbers. Do not share this constant across files — it is intentionally per-file.
Local helper: Each file that makes multiple backend calls should define a small file-local async helper to avoid copy/paste bugs. Do not create a shared helper across tool files or across apps. Pattern:
pythonTIMEOUT_S = 8.0

async def _call_with_timeout(coro, correlation_id: str, op_name: str):
    try:
        return await asyncio.wait_for(coro, timeout=TIMEOUT_S)
    except asyncio.TimeoutError:
        logger.warning("tool.<tool_name>.timeout", correlation_id=correlation_id, op=op_name)
        raise ToolUsageError(f"{op_name} timed out. Please try again.")
Use the tool's existing log event naming convention for the event string. If a file already has a timeout helper or equivalent pattern, align with it rather than adding a duplicate.
Pattern for all backend calls: Every backend_get and backend_post call in every tool handler must go through the file-local helper or asyncio.wait_for directly. On asyncio.TimeoutError, always raise ToolUsageError(...). The dispatcher converts ToolUsageError into an isError=True CallToolResult.
get_priorities.py — do not modify. Its parallel-gather pattern is intentional and production-stable.
Files to update:
tools/get_weekly_report.py:

Remove dead BACKEND_TIMEOUT = 15.0
Add TIMEOUT_S = 8.0 and file-local helper
Wrap backend_get call through helper

tools/onboarding_calendar_setup.py (Fix 2 only — schema is already correct):

Add TIMEOUT_S = 8.0 and file-local helper
Past-report check calls in _handle_keyword_education and _handle_first_weekly_report currently swallow all exceptions via except Exception. Preserve that behavior exactly — do not narrow the exception scope. For these silent branches, do not add new logging unless an equivalent log event string already exists in the file. If logging already exists on that branch, keep it unchanged. Correct pattern for silent branches:

pythontry:
    await asyncio.wait_for(backend_get(...), timeout=TIMEOUT_S)
except (asyncio.TimeoutError, Exception):
    pass  # or existing logger call if already present

Critical fetch calls (priorities fetch in _handle_keyword_education, weekly-report fetch in _handle_first_weekly_report): use file-local helper, raise ToolUsageError on timeout
_handle_reflection_setup: no backend calls, nothing to change

All widget tool files: Add TIMEOUT_S = 8.0 and file-local helper per file. Apply uniformly — no exceptions based on perceived likelihood of timeout.
Dead constant cleanup: Search the entire mcp_server/priority_guardian/tools/ directory for any BACKEND_TIMEOUT = definitions. Remove every one. Zero occurrences must remain after this increment.

Acceptance Criteria

 Schema validation test passes — see Unit Tests
 Filesystem coverage test passes — see Unit Tests
 grep -r "BACKEND_TIMEOUT" mcp_server/priority_guardian/tools/ returns zero results
 Every backend_get and backend_post call in all tool handlers goes through asyncio.wait_for via the file-local helper or directly, at TIMEOUT_S = 8.0
 All asyncio.TimeoutError cases raise ToolUsageError, never return raw exception objects
 Onboarding past-report check branches preserve existing exception-swallowing behavior — except (asyncio.TimeoutError, Exception) not except asyncio.TimeoutError alone
 No new ad-hoc log event name strings — silent branches either have no new logging or reuse an existing event string already in the file
 No handler logic, response shapes, assistant_guidance content, or structuredContent fields are changed
 get_priorities.py is not modified
 All existing tests pass


Unit Tests
Schema validation test — test_all_input_schemas_have_additional_properties_false:
Read schemas via TOOL_REGISTRY: iterate all registered ToolDefinition objects and access tool_def.input_schema. For each schema, recursively walk the entire tree. For every node where node.get("type") == "object", assert node.get("additionalProperties") is False. On failure, report tool name and JSON path of the violation.
Filesystem coverage test — test_no_unregistered_tool_modules:
Walk mcp_server/priority_guardian/tools/ and mcp_server/priority_guardian/tools/widget_tools/ for all .py files excluding __init__.py and base.py. For each file, assert that at least one ToolDefinition from that module is present in TOOL_REGISTRY. This ensures the schema validation test has full coverage — any tool file that exists but is not registered will fail this test explicitly.
Timeout unit tests — assert at handler level:
For each tool that gains timeout wrapping (get_weekly_report, onboarding_calendar_setup phases keyword_education and first_weekly_report, each widget tool):

Patch backend_get/backend_post to raise asyncio.TimeoutError immediately
Call the handler directly, not via dispatcher
Assert ToolUsageError is raised
Test name: test_<tool_name>_backend_timeout

For the onboarding silent branches: patch the past-report backend_get to raise asyncio.TimeoutError and assert the handler continues without raising.

Integration Tests
For get_weekly_report and onboarding_calendar_setup:

Patch backend_get to raise asyncio.TimeoutError immediately — no asyncio.sleep, no wall-clock assertions
Call via the dispatcher
Assert the dispatcher returns CallToolResult with isError=True
One test per tool


Before Deployment
Read OPERATIONS.md and check for additional pre-deploy tasks before deploying.
No migration required. No backend changes. No environment variable changes.