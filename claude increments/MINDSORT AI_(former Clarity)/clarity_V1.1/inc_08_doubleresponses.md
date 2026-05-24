Claude Code Briefing — Remove duplicate content from MindSort AI tool responses
Context
Every MindSort tool success path currently returns both a confirmation string in content AND assistant_guidance in structuredContent. Both appear in the conversation transcript. When assistant_guidance instructs the LLM to confirm the same action already in content, the user sees the message twice. Fix: content=[] on all success paths where assistant_guidance drives the response.
organize_thoughts.py is already correct — tool_logic.py already returns content=[{"type": "text", "text": ""}]. That file is not touched, but update it to return content=[] instead for cleanliness.
Rule being enforced: If assistant_guidance exists in structuredContent → content must be []. Error paths are exempt.

File 1: mcp_server/clarity/tools/load_saved_board.py
Three success return paths — change all three:
python# All three success paths
content=[]
Remove the message variable from all three success paths — it's no longer used. Keep it in the error path.
Keep the persistence error path content unchanged.

File 2: mcp_server/clarity/tools/read_saved_board.py
Same pattern — three success return paths:
pythoncontent=[]
Remove the message variable from success paths where no longer used. Keep error sentinel path unchanged.

File 3: mcp_server/clarity/tools/edit_board.py
Success return at bottom of handle():
python# Before
content=[mcp_types.TextContent(type="text", text=message)]

# After
content=[]
Remove the message variable and operation_messages dict — no longer used in content. If useful for debugging, convert to logger.debug("edit_board.operation_summary", message=message) before removing. Keep all isError=True paths unchanged.

File 4: mcp_server/clarity/tools/start_prioritization_flow.py
Success return at bottom of handle():
python# Before
content=[mcp_types.TextContent(type="text", text=message)]

# After
content=[]
The message variable stays — it's used in _meta["openai/toolInvocation/invoked"]. Keep all isError=True paths unchanged.

File 5: mcp_server/clarity/tools/delete_my_data.py
Three changes:
Change 1 — Remove user_confirmed_deletion from schema:
pythonINPUT_SCHEMA = {
    "type": "object",
    "properties": {},
    "required": [],
    "additionalProperties": False,
}
Change 2 — Update DESCRIPTION:
pythonDESCRIPTION = """
Permanently deletes the user's saved MindSort AI board. This cannot be undone.

BEFORE CALLING: Confirm with the user what will be deleted — their saved board with all clusters, thought items, tags, and priorities. Only call after they confirm.
"""
Change 3 — Remove user_confirmed check from handler — the entire block from user_confirmed = arguments.get(...) through its return statement. Handler goes straight to result = await delete_cluster(...).
Change 4 — Empty content on success paths:
python# deleted path and no_data path
content=[]
Keep error path unchanged.

File 6: mcp_server/clarity/tool_logic.py
In organize_thoughts(), both branches currently return content=[{"type": "text", "text": ""}]. Update to:
python"content": []

File 7: doc/ADR_MCP Server Implementation Standard.md
Add the following section after the existing "Widget URI Consistency" section:
markdown## Tool Response Architecture — `content` vs `assistant_guidance`

### The Rule

Every tool response uses one of two patterns. Never both simultaneously.

**Option A — Tool speaks (no `assistant_guidance`):**
```python
content=[mcp_types.TextContent(type="text", text="Board updated.")]
structuredContent={"clusters": enriched}  # no assistant_guidance key
```
Use when the tool response is deterministic, non-conversational, and requires no LLM narration.

**Option B — Model speaks (recommended for conversational flows):**
```python
content=[]
structuredContent={
    "clusters": enriched,
    "assistant_guidance": "Confirm the change briefly..."
}
```
Use when `assistant_guidance` in `structuredContent` drives the user-facing response.

### Why

Per the OpenAI Apps SDK reference: both `content` and `structuredContent` appear in the conversation transcript and are surfaced to the model. When `assistant_guidance` instructs the LLM to confirm the same action already described in `content`, the user sees a duplicate message — once from the tool transcript entry, once from the LLM following `assistant_guidance`.

`content=[]` (empty array) is the canonical form for "no content" per the MCP spec — `content` is typed as `Content[]`, so the empty array is cleaner than a TextContent block with empty string.

### Rule

**If `assistant_guidance` exists in `structuredContent` → `content` must be `[]`.**

### Exceptions

`content` may remain non-empty only when:
- The response is an error (`isError=True`) — error text must surface regardless of `structuredContent` processing
- No `assistant_guidance` is present and the tool is the sole author of the visible response

### Enforcement

Every tool response that contains `assistant_guidance` in `structuredContent` must have `content=[]`. This applies to all SDK apps in the suite.

### Production Bug Reference

MindSort AI (March 2026): All non-error tool responses returned both a confirmation string in `content` AND `assistant_guidance` in `structuredContent` instructing the LLM to confirm the same action. Users saw each response twice. Fix: `content=[]` on all success paths across all six tools. Error paths preserved.

What does NOT change:

All isError=True return paths across all tools
All assistant_guidance strings
All structuredContent structure
All _meta fields
All validation, persistence, auth, and registration logic

Before deploying: Read OPERATIONS_PREDEPLOY.md.