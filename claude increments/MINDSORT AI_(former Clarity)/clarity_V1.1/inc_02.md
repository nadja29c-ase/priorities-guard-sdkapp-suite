Claude Code Briefing: asyncio.wait_for + additionalProperties: False
Before starting: Read OPERATIONS_PREDEPLOY.md.
Scope: Two independent fixes across multiple files. Do not touch anything else.

Fix 1 — asyncio.wait_for in persistence.py
File: mcp_server/clarity/persistence.py
Context: The ADR requires every backend call to be wrapped with asyncio.wait_for(timeout=TIMEOUT_S) where TIMEOUT_S ≤ 8.0. The current implementation relies on the httpx.AsyncClient 10-second timeout in http_client.py. This is explicitly forbidden by the ADR — the http_client timeout is 10s which exceeds the ~10s MCP execution window, leaving zero margin.
There are three backend calls in persistence.py:

client.post(...) in persist_cluster
client.get(...) in get_cluster
client.request("DELETE", ...) in delete_cluster

Required changes:
Add at module level (after imports):
pythonimport asyncio
TIMEOUT_S = 8.0
Wrap each backend call with asyncio.wait_for. Example for persist_cluster:
pythonresponse = await asyncio.wait_for(
    client.post(
        f"{BACKEND_URL}/api/clarity/clusters",
        headers=headers,
        json=payload,
    ),
    timeout=TIMEOUT_S,
)
On asyncio.TimeoutError, raise as the existing exception handling already catches Exception and logs + returns gracefully — so asyncio.TimeoutError propagating into the existing except Exception block is correct behavior for persist_cluster and get_cluster (they return None on failure). For delete_cluster it returns {"status": "error", "message": "..."}.
Do not change any other logic, error handling, or structure.

Fix 2 — additionalProperties: False on nested schemas
Files: All 7 tool files under mcp_server/clarity/tools/:

organize_thoughts.py
save_board.py
load_saved_board.py
read_saved_board.py
prioritize_clusters.py
edit_board.py
delete_my_data.py

Rule (from ADR): Every "type": "object" node at any depth in any INPUT_SCHEMA must have "additionalProperties": False. No exceptions. This includes objects inside items, oneOf, anyOf, properties values, and top-level.
load_saved_board.py and read_saved_board.py already have correct empty schemas:
pythonINPUT_SCHEMA = {
    "type": "object",
    "properties": {},
    "required": [],
    "additionalProperties": False
}
Verify these are correct and leave them untouched.
delete_my_data.py — top-level missing additionalProperties: False:
pythonINPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "user_confirmed_deletion": {...}
    },
    "required": ["user_confirmed_deletion"],
    "additionalProperties": False   # ← add this
}
organize_thoughts.py — add additionalProperties: False to:

clusters.items (the cluster object)
clusters.items.subclusters.items (the subcluster object)

save_board.py — add additionalProperties: False to:

clusters.items
clusters.items.priority
clusters.items.thought_items.items (the oneOf object branch: {text, priority})
clusters.items.thought_items.items.priority
clusters.items.subclusters.items
clusters.items.subclusters.items.priority
clusters.items.subclusters.items.thought_items.items (oneOf object branch)
clusters.items.subclusters.items.thought_items.items.priority

prioritize_clusters.py — add additionalProperties: False to every "type": "object" node in INPUT_SCHEMA at all depths including priority objects, clusters.items, subclusters.items, priorities.items, and all thought_items oneOf object branches.
edit_board.py — same rule: every "type": "object" node in INPUT_SCHEMA at all depths including board.items, nested priority, thought_items oneOf branches, subclusters.items, and all operations.items nested objects.
Copy and adjust only — do not rewrite, restructure, or change descriptions, enums, or any other field.

Unit tests
Schema validation test — add to mcp_server/clarity/tests/:
Write a unit test that:

Imports TOOL_REGISTRY from mcp_server.clarity.tools
For every registered tool, walks its input_schema recursively
Asserts that every node with "type": "object" also has "additionalProperties": False
Fails with a clear message naming which tool and which path violates the rule

This is a static structural test — no mocking, no backend calls needed.
Timeout test — add to the same test file:
Write a unit test that reads persistence.py as source text and asserts that asyncio.wait_for appears at least 3 times (once per backend call). This is a static presence check, not a runtime test.

Verification after deploy
bashcurl https://clarity.priority-guard.com/.well-known/oauth-protected-resource
Should still return correct values (no change expected — this is a sanity check that nothing regressed).
Manually trigger a save and load flow in ChatGPT to confirm persistence still works end-to-end.