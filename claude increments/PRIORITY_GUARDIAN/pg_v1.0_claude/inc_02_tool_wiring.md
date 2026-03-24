# Increment Claude-02: Tool Wiring + Response Adapter

**Goal:** Wire all 7 public tools into the Claude MCP server, build a Claude-specific tool listing, and adapt tool responses so Claude's model receives behavioral guidance correctly. No widget. No backend changes. No tool logic changes.

---

## Context

Priority Guardian's tool handlers return `assistant_guidance` inside `structuredContent`. This works for ChatGPT because ChatGPT ignores `content` when `structuredContent` is present. Claude reads `content` as the primary model channel. Without adaptation, Claude sees only the brief text summary and none of the coaching behavior.

The response adapter is a thin transformation layer in the Claude MCP server. Shared tool handlers are never touched.

Reference: `doc/Claude_Compliance/structural_guideline_claude_vs_openai.md` — "MCP Server Response Adapter" section.

---

## Pre-Implementation

Read `doc/OPERATIONS_PREDEPLOY.md` before starting. No migrations in this increment.

---

## Implementation Approach — Copy and Adjust, Never Rewrite

`tools_dupl.py` has an existing source file to copy from. `tools_list_dupl.py` and `response_adapter_dupl.py` are genuinely new — there is no copyable source for these because the shared equivalents embed ChatGPT-specific logic. Write them exactly per the spec below, nothing more.

| File | Action | Source |
|---|---|---|
| `handlers/tools_dupl.py` | **Copy verbatim, adjust only listed items** | `mcp_server/priority_guardian/handlers/tools.py` |
| `tools_list_dupl.py` | New file — write per spec | No copyable source |
| `response_adapter_dupl.py` | New file — write per spec | No copyable source |
| `server_dupl.py` | Minimal update only | Existing Increment Claude-01 file |

---

## Absolute Constraints — Read Before Writing Any Code

**Adapter constraints:**
- MUST move `assistant_guidance` from `structuredContent` to `content`
- MUST strip the nested `"_meta"` key from inside the `structuredContent` dict
- MUST preserve the top-level `CallToolResult._meta` field unchanged
- MUST NOT modify `structuredContent["data"]` in any way — no key renames, no key drops, no value changes, no array truncation
- MUST NOT mutate the original `CallToolResult` in place — MUST always return a new `CallToolResult`, even when returning early
- MUST handle `assistant_guidance` being either a `str` or a `dict`
- MUST handle tool responses where `structuredContent` has no `"_meta"` key
- MUST handle tool responses where `structuredContent` is `None`
- MUST pass `otherEvents` and `priorityEvents` through unchanged — no truncation in this increment
- When accessing top-level `_meta` from a `CallToolResult`, use `result.meta` — NOT `result._meta`. The field is defined with Pydantic alias `_meta` but accessed in Python as `.meta`

**`tools_list_dupl.py` constraints:**
- MUST NOT modify `TOOL_REGISTRY`
- MUST NOT modify `ToolDefinition`
- MUST NOT modify the shared `list_tools()` function
- Read only — import and adapt, never mutate
- `list_tools_for_claude` MUST be declared `async` even though it contains no `await` calls — it is called from an async MCP handler
- MUST import `from copy import deepcopy`

**`server_dupl.py` constraints:**
- Change ONLY the `_list_tools` handler to call `tools_list_dupl.list_tools_for_claude()`
- NO middleware changes, NO auth changes, NO proxy route changes, NO discovery changes, NO new routes, NO refactoring

**Test constraints:**
- ADD tests to `tests/unit/mcp_claude/test_scaffold.py` — do NOT rewrite or replace existing tests
- All 6 existing scaffold tests must continue to pass unchanged

---

## Folder Structure Changes

```
mcp_server/priority_guardian_claude/
├── response_adapter_dupl.py     # NEW
├── tools_list_dupl.py           # NEW
├── handlers/
│   └── tools_dupl.py            # UPDATED — full dispatcher replacing stub
└── server_dupl.py               # MINIMAL UPDATE — _list_tools only
```

---

## 1. `handlers/tools_dupl.py` — Full Dispatcher

**Source:** `mcp_server/priority_guardian/handlers/tools.py` — copy verbatim, then make only these four adjustments:

**Adjustment 1:** Replace relative mcp_auth import:
```python
# Before
from ..mcp_auth import (authenticate_request, UnauthorizedError, ...)
# After
from mcp_server.priority_guardian_claude.mcp_auth_dupl import (authenticate_request, UnauthorizedError, ...)
```

**Adjustment 2:** Replace relative tools imports:
```python
# Before
from ..tools import get_tool
from ..tools.base import ToolUsageError
# After
from mcp_server.priority_guardian.tools import get_tool
from mcp_server.priority_guardian.tools.base import ToolUsageError
```

**Adjustment 3:** After `result = await tool.handle(user_id, correlation_id, arguments)`, insert the adapter call. Valid placements:
- After `tool.handle()` and **before** the `isinstance` type guard, OR
- After `tool.handle()` and **after** the `isinstance` type guard

Both are correct. Do NOT place the call before `tool.handle()`.

```python
from mcp_server.priority_guardian_claude.response_adapter_dupl import adapt_tool_result
result = adapt_tool_result(result)
```

**Adjustment 4:** Update the duplicate header comment to reference `handlers/tools.py` as the logic source.

**No other changes.** Dispatcher sequence, error categories, logging event names, timing, and return types all copied verbatim.

---

## 2. `tools_list_dupl.py` — Claude-Specific Tool Listing

**New file.** Add the duplicate header comment:

```python
# (duplicate) — exists only because shared list_tools() embeds ChatGPT-specific _meta.
# Reads from mcp_server/priority_guardian/tools/ (source of truth — never modified here).
# Post-OpenAI-approval refactor: move to mcp_server/shared/ and delete this file.
```

**Required imports:**
```python
from copy import deepcopy
from mcp import types as mcp_types
from mcp_server.priority_guardian.tools import TOOL_REGISTRY
```

**One public function:**
```python
async def list_tools_for_claude() -> list[mcp_types.Tool]:
```

Must be `async` even though it contains no `await` calls — required because `_list_tools` in `server_dupl.py` is an async handler.

**One private helper (explicitly allowed):**
```python
def _derive_title(tool_name: str) -> str:
    return " ".join(word.capitalize() for word in tool_name.split("_"))
```

No other functions.

**Rules for building each tool entry:**

**1. Filter:** Only include tools where `tool_def.visibility == "public"`.

`ToolDefinition` (in `mcp_server/priority_guardian/tools/base.py`) has `visibility: str = "public"` as a field with default `"public"`. Use this field directly.

**2. Construct `mcp_types.Tool`:** Use the same argument names as the shared `list_tools()` in `mcp_server/priority_guardian/tools/__init__.py`, except omit `_meta`. Look at that function to confirm the exact kwarg names before writing.

**3. `_meta`:** Pass `_meta=None` (or omit, since default is `None`).

In PG's shared registry, `Tool._meta` contains only OpenAI Apps SDK fields (`securitySchemes`, `ui.visibility`, `openai/outputTemplate`, `openai/toolInvocation/*`). None of these are used by Claude — Claude's auth is handled at the MCP transport layer (Bearer token), not via per-tool metadata. Setting `_meta=None` is correct for this codebase. Do not generalize this rule beyond PG's registry.

**4. `ToolAnnotations`:** Set using `ToolDefinition` fields. Use the exact snake_case field names from `ToolDefinition` — not the MCP camelCase annotation names:

| `ToolAnnotations` kwarg | Source from `ToolDefinition` |
|---|---|
| `readOnlyHint` | `tool_def.read_only_hint` |
| `destructiveHint` | `tool_def.destructive_hint` |
| `openWorldHint` | `tool_def.open_world_hint` |
| `title` | `_derive_title(tool_def.name)` |

**5. `inputSchema`:** `deepcopy(tool_def.input_schema)`.

**6. `description`:** `tool_def.description` unchanged.

**7. `name`:** `tool_def.name` unchanged.

**8. Sort:** Sort by `tool_def.name` for deterministic output.

---

## 3. `response_adapter_dupl.py` — Response Adapter

**New file.** Add the duplicate header comment:

```python
# (duplicate) — exists only because tool responses embed ChatGPT-specific fields.
# Tool handlers in mcp_server/priority_guardian/tools/ are never modified.
# Post-OpenAI-approval refactor: move to mcp_server/shared/ and delete this file.
```

**Required imports:**
```python
import json
from mcp import types as mcp_types
```

**One public function:**
```python
def adapt_tool_result(result: mcp_types.CallToolResult) -> mcp_types.CallToolResult:
```

Private serializer helpers are allowed only if minimal and directly required by the logic below. No additional logic.

**Content assumption:** All 7 current public tools return a single `TextContent` block in `content`. The adapter replaces `content` with a new single `TextContent`. This is intentional for this increment. If a future tool returns multiple content blocks, this adapter will need revisiting.

**Transformation rules — apply in this order:**

**Step 1: Guard — return new object if no structuredContent.**

The adapter MUST always return a new `CallToolResult`, even on the early return path — never return the original object:

```python
if result.structuredContent is None:
    return mcp_types.CallToolResult(
        content=result.content,
        structuredContent=None,
        isError=result.isError,
        _meta=result.meta,
    )
```

**Step 2: Extract `assistant_guidance`.**
```python
assistant_guidance = result.structuredContent.get("assistant_guidance")
```
If `None`, skip steps 3–4.

**Step 3: Serialize `assistant_guidance` to string.**

```python
if isinstance(assistant_guidance, str):
    guidance_str = assistant_guidance
elif isinstance(assistant_guidance, dict):
    guidance_str = json.dumps(assistant_guidance, ensure_ascii=False, indent=2)
else:
    guidance_str = str(assistant_guidance)
```

Note: `json.dumps` with `indent=2` is a temporary, lossless serialization choice for Increment 2. It preserves all structured fields in human-readable form. It is not the intended long-term UX for dict guidance. Do not optimize this here.

**Step 4: Build new `content`.**

Guard for empty content list; assume first item is `TextContent` for all current public tools — do not add type branching:

```python
existing_text = result.content[0].text if result.content else ""
new_text = f"{guidance_str}\n\n{existing_text}".strip() if existing_text else guidance_str
new_content = [mcp_types.TextContent(type="text", text=new_text)]
```

**Step 5: Build clean `structuredContent`.**

Remove only `"assistant_guidance"` and `"_meta"` from the `structuredContent` dict. Do NOT touch `"data"` or any other key:

```python
clean_structured = {
    k: v for k, v in result.structuredContent.items()
    if k not in ("assistant_guidance", "_meta")
}
```

**Step 6: Return new `CallToolResult` — do not mutate original.**

Access top-level `_meta` via `result.meta`. Do NOT use `result._meta`:

```python
return mcp_types.CallToolResult(
    content=new_content,
    structuredContent=clean_structured,
    isError=result.isError,
    _meta=result.meta,
)
```

---

## 4. `server_dupl.py` — Minimal Update

**One change only.** Replace:
```python
@mcp._mcp_server.list_tools()
async def _list_tools():
    return []
```
With:
```python
@mcp._mcp_server.list_tools()
async def _list_tools():
    from mcp_server.priority_guardian_claude.tools_list_dupl import list_tools_for_claude
    return await list_tools_for_claude()
```

**Nothing else changes.**

---

## What NOT to Touch

- Any file in `mcp_server/priority_guardian/`
- Any file in `backend/`
- `TOOL_REGISTRY`, `ToolDefinition`, shared `list_tools()`
- Existing scaffold tests

---

## Tests

Add to `tests/unit/mcp_claude/test_scaffold.py`. Do NOT replace existing tests.

**1. `test_list_tools_returns_public_tools_only`**
```python
from mcp_server.priority_guardian.tools import TOOL_REGISTRY
expected_public_names = {
    name for name, td in TOOL_REGISTRY.items() if td.visibility == "public"
}
tools = await list_tools_for_claude()
assert {t.name for t in tools} == expected_public_names
```

**2. `test_list_tools_annotations_match_registry`**

For every tool returned by `list_tools_for_claude()`:
- `tool.annotations` is not `None`
- `tool.annotations.title` is a non-empty string
- `tool.annotations.readOnlyHint == TOOL_REGISTRY[tool.name].read_only_hint`
- `tool.annotations.destructiveHint == TOOL_REGISTRY[tool.name].destructive_hint`
- `tool.annotations.openWorldHint == TOOL_REGISTRY[tool.name].open_world_hint`
- `tool._meta is None`

Use exact snake_case field names from `ToolDefinition` when reading from `TOOL_REGISTRY`.

**3. `test_list_tools_title_derived_correctly`**
```python
tools = await list_tools_for_claude()
titles = {t.name: t.annotations.title for t in tools}
assert titles["get_priorities"] == "Get Priorities"
assert titles["render_weekly_report"] == "Render Weekly Report"
assert titles["onboarding_calendar_setup"] == "Onboarding Calendar Setup"
```

**4. `test_adapter_moves_string_guidance_to_content`**
```python
result = mcp_types.CallToolResult(
    content=[mcp_types.TextContent(type="text", text="Short summary.")],
    structuredContent={"success": True, "data": {"foo": "bar"}, "assistant_guidance": "Do not repeat priorities."},
)
adapted = adapt_tool_result(result)
assert "Do not repeat priorities." in adapted.content[0].text
assert "Short summary." in adapted.content[0].text
assert "assistant_guidance" not in adapted.structuredContent
assert adapted.structuredContent["data"] == {"foo": "bar"}
assert "_meta" not in adapted.structuredContent
```

**5. `test_adapter_moves_dict_guidance_to_content`**
```python
result = mcp_types.CallToolResult(
    content=[mcp_types.TextContent(type="text", text="Summary.")],
    structuredContent={
        "success": True,
        "data": {},
        "assistant_guidance": {"action": "PRIORITY_CREATED", "instruction": "Do not list priorities."},
    },
)
adapted = adapt_tool_result(result)
assert "PRIORITY_CREATED" in adapted.content[0].text
assert "Do not list priorities." in adapted.content[0].text
assert "assistant_guidance" not in adapted.structuredContent
```

**6. `test_adapter_handles_no_meta_in_structured_content`**
```python
result = mcp_types.CallToolResult(
    content=[mcp_types.TextContent(type="text", text="Summary.")],
    structuredContent={"success": True, "data": {}, "assistant_guidance": "Some guidance."},
)
adapted = adapt_tool_result(result)
assert "Some guidance." in adapted.content[0].text
assert "assistant_guidance" not in adapted.structuredContent
```

**7. `test_adapter_handles_no_structured_content`**
```python
result = mcp_types.CallToolResult(
    content=[mcp_types.TextContent(type="text", text="Summary.")],
    structuredContent=None,
)
adapted = adapt_tool_result(result)
assert adapted is not result
assert adapted.content[0].text == "Summary."
assert adapted.structuredContent is None
```

**8. `test_adapter_does_not_modify_data`**
```python
result = mcp_types.CallToolResult(
    content=[mcp_types.TextContent(type="text", text="Summary.")],
    structuredContent={
        "success": True,
        "data": {"priorities": [{"id": "1", "name": "Test"}], "otherEvents": [{"title": "Meeting"}]},
        "assistant_guidance": "guidance",
        "_meta": {"openai/outputTemplate": "ui://widget/test.html"},
    },
)
adapted = adapt_tool_result(result)
assert adapted.structuredContent["data"]["priorities"] == [{"id": "1", "name": "Test"}]
assert adapted.structuredContent["data"]["otherEvents"] == [{"title": "Meeting"}]
assert len(adapted.structuredContent["data"]["otherEvents"]) == 1
assert "_meta" not in adapted.structuredContent
assert "assistant_guidance" not in adapted.structuredContent
```

**9. `test_adapter_does_not_mutate_original`**
```python
original_structured = {
    "success": True,
    "data": {"foo": "bar"},
    "assistant_guidance": "guidance",
    "_meta": {"openai/outputTemplate": "ui://widget/test.html"},
}
result = mcp_types.CallToolResult(
    content=[mcp_types.TextContent(type="text", text="Summary.")],
    structuredContent=original_structured,
)
adapted = adapt_tool_result(result)
assert adapted is not result
assert "assistant_guidance" in result.structuredContent
assert "_meta" in result.structuredContent
```

**10. `test_list_tools_for_claude_directly`**
```python
tools = await list_tools_for_claude()
assert len(tools) > 0
assert all(isinstance(t, mcp_types.Tool) for t in tools)
names = [t.name for t in tools]
assert names == sorted(names)
```

---

## Definition of Done

- [ ] `response_adapter_dupl.py` exists with one public function `adapt_tool_result`
- [ ] `tools_list_dupl.py` exists with one public `async` function `list_tools_for_claude` and one private helper `_derive_title`
- [ ] `handlers/tools_dupl.py` is the full dispatcher copied from source, calls adapter after `tool.handle()` (before or after type guard — both valid)
- [ ] `server_dupl.py` `_list_tools` calls `list_tools_for_claude()` — no other changes to the file
- [ ] All new files carry the `(duplicate)` header comment
- [ ] All 6 existing scaffold tests pass unchanged
- [ ] All 10 new tests pass
- [ ] Zero files modified in `mcp_server/priority_guardian/`
- [ ] Zero files modified in `backend/`
- [ ] `TOOL_REGISTRY`, `ToolDefinition`, and shared `list_tools()` are untouched