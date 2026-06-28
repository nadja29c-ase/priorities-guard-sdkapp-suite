# Increment MindSort-Claude-02: Tool Wiring + Response Adapter

**Goal:** Wire all registered MindSort tools into the Claude MCP server, build a Claude-specific tool listing (with `title` + corrected `destructiveHint`), and adapt tool responses so Claude's model receives behavioral guidance correctly. No widget. No backend changes. No tool logic changes.

---

## Context

MindSort's tool handlers return `assistant_guidance` inside `structuredContent`. ChatGPT ignores `content` when `structuredContent` is present, so this works there. Claude reads `content` as the primary model channel — without adaptation Claude sees none of the coaching/behavioral guidance.

The response adapter is a thin transformation layer in the Claude MCP server (`mindsort_claude`). Shared tool handlers in `clarity/` are NEVER touched.

Reference: `doc/Claude_Compliance/structural_guideline_claude_vs_openai_MindSortAI.md` — §4 (Response Adapter Contract), §8.1 (title), §8.2 (destructiveHint).
Sibling reference (PG's equivalent): `claude increments/PRIORITY_GUARDIAN/pg_v1.0_claude/inc_02_tool_wiring.md`.

**MindSort differs from PG in four ways that matter for this increment — do not assume PG's Claude-02 transfers verbatim:**
1. MindSort's `ToolDefinition` has **no `visibility` field** → no visibility filter; the tool list is the full `TOOL_REGISTRY`.
2. MindSort's `ToolDefinition` has **no `title` field** → `_derive_title()` required (per §8.1 decision (a)).
3. `start_prioritization_flow` has `destructive_hint=False` but writes DB → **Claude registry must override to `True`** (§8.2).
4. MindSort tools place `saved_board_hash` in **top-level `_meta`** mixed with `openai/*` keys, and several tools return **empty `content`** → the adapter must discriminate within top-level `_meta` and treat empty content as normal.

---

## Pre-Implementation

Read `doc/OPERATIONS_PREDEPLOY.md` before starting. No migrations in this increment.

---

## Implementation Approach — Copy and Adjust, Never Rewrite

| File | Action | Source |
|---|---|---|
| `handlers/tools_dupl.py` | **Copy verbatim from source, adjust only listed items** | `mcp_server/clarity/handlers/tools.py` |
| `tools_list_dupl.py` | New file — write per spec | No copyable source (shared `list_tools()` embeds OpenAI `_meta`) |
| `response_adapter_dupl.py` | New file — write per spec | No copyable source |
| `server_dupl.py` | Minimal update only (one handler) | Existing Claude-01 file |

PG's `response_adapter_dupl.py` and `tools_list_dupl.py` are useful **structural references** but must NOT be copied — their tool names, widget URIs, `visibility` filter, and `_meta` passthrough are PG-specific and wrong for MindSort. Read them for shape; write MindSort's per this spec.

---

## Absolute Constraints — Read Before Writing Any Code

**Adapter constraints:**
- MUST move `assistant_guidance` from `structuredContent` to `content`.
- MUST handle `assistant_guidance` as either `str` OR `dict` with shape `{"action": ..., "instruction": ...}`. **Per §8.1 decision: when dict, render `instruction` ONLY — DROP `action`** (it is an internal control token, not model-facing prose). This DIFFERS from PG, which json-dumps the whole dict.
- MUST strip `"assistant_guidance"` from `structuredContent`.
- MUST strip any `"_meta"` key from *inside* `structuredContent` (defensive — MindSort tools don't currently put `_meta` there, but strip if present).
- **TOP-LEVEL `_meta` — DISCRIMINATE, do not blanket-pass and do not blanket-strip (§8.4):**
  - PRESERVE non-`openai/` keys (specifically `saved_board_hash`).
  - STRIP all keys starting with `openai/` (e.g. `openai/toolInvocation/invoking`, `openai/toolInvocation/invoked`).
  - If after stripping the `_meta` dict is empty, pass `_meta=None`.
- MUST NOT modify `structuredContent` data keys (`clusters`, `cluster_names`, `has_history`, `is_empty_snapshot`, etc.) — no renames, drops, value changes, or truncation.
- MUST NOT mutate the original `CallToolResult` — always return a NEW object, including on every early-return path.
- MUST handle `structuredContent is None` (return new object, discriminated `_meta`, content passed through).
- MUST treat **empty `content` list as the normal case** — several MindSort tools return `content=[]` with guidance only in `structuredContent`. When content is empty, the new content is the guidance alone.
- Access top-level `_meta` via `result.meta` (Pydantic alias), NOT `result._meta`.

**`tools_list_dupl.py` constraints:**
- MUST NOT modify `TOOL_REGISTRY`, `ToolDefinition`, or the shared `list_tools()`.
- Read only — import and adapt.
- Build the list from `TOOL_REGISTRY` (the 6 registered tools), NOT from `config.TOOL_SCOPES` (which lists 7, including unregistered `save_board`).
- `list_tools_for_claude` MUST be `async` (called from an async handler) even with no `await`.
- MUST import `from copy import deepcopy`.

**`server_dupl.py` constraints:**
- Change ONLY the `_list_tools` handler. No middleware/auth/proxy/discovery/route changes.

**Test constraints:**
- ADD tests to `tests/unit/mcp_claude_mindsort/test_scaffold.py` — do NOT rewrite existing tests or the autouse `restore_mcp_auth_globals` fixture.
- All existing scaffold tests must continue to pass unchanged.

---

## 1. `handlers/tools_dupl.py` — Full Dispatcher

**Source:** `mcp_server/clarity/handlers/tools.py` — copy verbatim, then make ONLY these adjustments:

**Adjustment 1 — mcp_auth import:**
```python
# Before (in source):
from ..mcp_auth import (authenticate_request, UnauthorizedError, InsufficientScopeError, build_unauthorized_meta, build_forbidden_meta)
# After:
from mcp_server.mindsort_claude.mcp_auth_dupl import (authenticate_request, UnauthorizedError, InsufficientScopeError, build_unauthorized_meta, build_forbidden_meta)
```

**Adjustment 2 — tools import:**
```python
# Before:
from ..tools import get_tool
# After:
from mcp_server.clarity.tools import get_tool
```

**Adjustment 3 — insert adapter call** after `result = await tool.handle(...)`. Place it after `tool.handle()` and after the `isinstance` type guard (so only validated `CallToolResult`s are adapted):
```python
from mcp_server.mindsort_claude.response_adapter_dupl import adapt_tool_result
result = adapt_tool_result(result)
```
Do NOT adapt the early-return error responses (unauthorized/forbidden/unknown-tool/unexpected-error). **Auth-error handling is out of scope for the response adapter.** Claude's OAuth challenge behavior is handled by `BearerAuthMiddleware` (Claude-01) at the transport layer — the 401 challenge fires before the tool dispatcher's auth errors are ever the re-auth driver. Only the successful `tool.handle()` result flows through `adapt_tool_result`. Do NOT modify the dispatcher's auth error handling in this increment.

> **Note on `build_unauthorized_meta`/`build_forbidden_meta`:** these emit OpenAI `mcp/www_authenticate` format. Because Claude's re-auth is transport-layer (`BearerAuthMiddleware`), this error `_meta` is inert on Claude — neither correct-for-Claude nor harmful, simply unused. Leave it as copied; do NOT modify (shared error path; changing it risks divergence). Flag only.

**Adjustment 4 —** update the `(duplicate)` header to reference `clarity/handlers/tools.py` as the source.

**No other changes.** Dispatcher sequence, error categories, logging event names, timing all verbatim.

---

## 2. `tools_list_dupl.py` — Claude-Specific Tool Listing

**New file.** Header:
```python
# (duplicate) — exists only because shared list_tools() embeds ChatGPT-specific _meta.
# Reads from mcp_server/clarity/tools/ (source of truth — never modified here).
# Consolidate into shared/ ONLY if this file proves to churn — not preemptively.
```

**Imports:**
```python
from copy import deepcopy
from mcp import types as mcp_types
from mcp_server.clarity.tools import TOOL_REGISTRY
```

**Title-source decision (§8.1(a)): derive from name, with an explicit override map for names that don't title-case cleanly.**
```python
_TITLE_OVERRIDES = {
    "start_prioritization_flow": "Set Priorities",
    "read_board_before_editing": "Read Board",
    "delete_my_data": "Delete My Data",
}

def _derive_title(tool_name: str) -> str:
    if tool_name in _TITLE_OVERRIDES:
        return _TITLE_OVERRIDES[tool_name]
    return " ".join(word.capitalize() for word in tool_name.split("_"))
```
(Derived results for the rest: `organize_thoughts`→"Organize Thoughts", `load_saved_board`→"Load Saved Board", `edit_board`→"Edit Board".)

**`destructiveHint` override (§8.2):**
```python
_CLAUDE_DESTRUCTIVE_HINT_OVERRIDES = {
    "start_prioritization_flow": True,  # writes/overwrites DB priorities; "reversible" is irrelevant to destructiveHint
}
```

**One public function:**
```python
async def list_tools_for_claude() -> list[mcp_types.Tool]:
```

Rules per tool, iterating `sorted(TOOL_REGISTRY.values(), key=lambda t: t.name)`:

1. **No visibility filter** — MindSort has no `visibility` field; include every registered tool.
2. **`name`:** `tool_def.name`.
3. **`description`:** `tool_def.description` unchanged.
4. **`inputSchema`:** `deepcopy(tool_def.input_schema)`.
5. **`_meta`:** `None` **for this increment**. (MindSort's shared `_meta` is entirely OpenAI Apps SDK fields — `openai/outputTemplate`, `openai/toolInvocation/*`, `ui.visibility`, `securitySchemes`. None apply to Claude; auth is transport-layer Bearer. Per §3/§8 do not carry them.) **Widget-related `_meta.ui.resourceUri`/`ui.domain` is intentionally deferred to the widget increment** — `_meta=None` is correct *now*, not a permanent rule. Widget-producing tools will gain `ui.*` metadata when the Claude widget lands.
6. **`ToolAnnotations`** (camelCase kwargs, snake_case sources):
   | kwarg | source |
   |---|---|
   | `title` | `_derive_title(tool_def.name)` |
   | `readOnlyHint` | `tool_def.read_only_hint` |
   | `destructiveHint` | `_CLAUDE_DESTRUCTIVE_HINT_OVERRIDES.get(tool_def.name, tool_def.destructive_hint)` |
   | `openWorldHint` | `tool_def.open_world_hint` |
7. **Construct** `mcp_types.Tool(name=..., description=..., inputSchema=..., annotations=..., _meta=None)`. Confirm the exact `Tool` constructor kwargs against the installed `mcp` package and the shared `list_tools()` before writing — if `annotations` is not a constructor kwarg, set it as an attribute after construction the way the shared `list_tools()` does (`if hasattr(tool, "annotations"): tool.annotations = ...`), but prefer the constructor form if supported.
8. **Sort:** by `tool_def.name` (deterministic).

No other functions besides `list_tools_for_claude` and `_derive_title`.

---

## 3. `response_adapter_dupl.py` — Response Adapter

**New file.** Header:
```python
# (duplicate) — exists only because tool responses embed ChatGPT-specific fields.
# Tool handlers in mcp_server/clarity/tools/ are never modified.
# Consolidate into shared/ ONLY if this file proves to churn — not preemptively.
```

**Imports:**
```python
from mcp import types as mcp_types
```
(No `json` needed — guidance dict renders `instruction` as a plain string, not json-dumped. This differs from PG.)

**One public function:**
```python
def adapt_tool_result(result: mcp_types.CallToolResult) -> mcp_types.CallToolResult:
```

**Helper — discriminate top-level `_meta` (used on every return path):**
```python
def _clean_top_meta(meta) -> dict | None:
    """Keep non-openai/ keys (e.g. saved_board_hash), strip openai/* keys. None if empty."""
    if not meta:
        return None
    cleaned = {k: v for k, v in dict(meta).items() if not k.startswith("openai/")}
    return cleaned or None
```

**Helper — render guidance to string (DROP `action`, keep `instruction`):**
```python
def _guidance_to_str(guidance) -> str:
    if isinstance(guidance, str):
        return guidance
    if isinstance(guidance, dict):
        # Per §8.1: render instruction only; action is an internal control token.
        instruction = guidance.get("instruction")
        if instruction is not None:
            return str(instruction)
        return str(guidance)  # defensive: dict without 'instruction'
    return str(guidance)
```

**Transformation — apply in order:**

**Step 1 — `structuredContent is None`:** return new object, content passed through, top-level `_meta` discriminated.
```python
if result.structuredContent is None:
    return mcp_types.CallToolResult(
        content=list(result.content) if result.content else [],
        structuredContent=None,
        isError=result.isError,
        _meta=_clean_top_meta(result.meta),
    )
```

**Step 2 — extract guidance:**
```python
guidance = result.structuredContent.get("assistant_guidance")
```

**Step 3 — build clean `structuredContent`** (strip `assistant_guidance` + any inner `_meta`):
```python
clean_structured = {
    k: v for k, v in result.structuredContent.items()
    if k not in ("assistant_guidance", "_meta")
}
```

**Step 4 — build new `content`:**
```python
existing_text = ""
if result.content:
    first = result.content[0]
    if getattr(first, "text", None):
        existing_text = first.text

if guidance is not None:
    guidance_str = _guidance_to_str(guidance)
    parts = [p for p in [guidance_str, existing_text] if p]
    new_text = "\n\n".join(parts)
    new_content = [mcp_types.TextContent(type="text", text=new_text)]
else:
    # No guidance — preserve existing content as-is (may be empty)
    new_content = list(result.content) if result.content else []
```
Note: empty `content` is normal for MindSort. When content is empty and guidance exists, `new_content` is the guidance alone. When content is empty and no guidance, `new_content` stays `[]`.

**Step 5 — return new object, discriminated top-level `_meta`:**
```python
return mcp_types.CallToolResult(
    content=new_content,
    structuredContent=clean_structured,
    isError=result.isError,
    _meta=_clean_top_meta(result.meta),
)
```

**Content-block assumption:** current MindSort tools return either `[]` or a single `TextContent`. The adapter assumes first block is text when present. Do not add multi-block branching this increment.

**No widget `_meta` injection in this increment.** PG's adapter has `adapt_widget_tool_meta` (adds `ui.resourceUri`/`ui.domain`). MindSort has no Claude widget yet (future increment) — do NOT add widget `_meta` here.

---

## 4. `server_dupl.py` — Minimal Update

**One change only.** Replace:
```python
@mcp._mcp_server.list_tools()
async def _list_tools():
    return []
```
with:
```python
@mcp._mcp_server.list_tools()
async def _list_tools():
    from mcp_server.mindsort_claude.tools_list_dupl import list_tools_for_claude
    return await list_tools_for_claude()
```
Nothing else changes.

---

## What NOT to Touch

- Any file in `mcp_server/clarity/` — ChatGPT server is under OpenAI review.
- Any file in `backend/`.
- `TOOL_REGISTRY`, `ToolDefinition`, shared `list_tools()`.
- Existing scaffold tests + the `restore_mcp_auth_globals` fixture.

---

## Tests

Add to `tests/unit/mcp_claude_mindsort/test_scaffold.py`. Do NOT replace existing tests.

**Tool-listing tests:**

1. `test_list_tools_returns_all_registered` — `{t.name for t in await list_tools_for_claude()} == set(TOOL_REGISTRY.keys())`. (No visibility filter.)

2. `test_list_tools_annotations` — for every returned tool: `annotations` is not None; `annotations.title` is a non-empty str; `readOnlyHint == TOOL_REGISTRY[name].read_only_hint`; `openWorldHint == TOOL_REGISTRY[name].open_world_hint`; `t._meta is None`.

3. `test_destructive_hint_override` — `start_prioritization_flow`'s returned `annotations.destructiveHint is True` (even though `TOOL_REGISTRY["start_prioritization_flow"].destructive_hint is False`). And a known-destructive tool (`organize_thoughts`) is `True`, and a read tool (`read_board_before_editing`) is `False`.

4. `test_title_derivation` — `titles["organize_thoughts"] == "Organize Thoughts"`; `titles["start_prioritization_flow"] == "Set Priorities"` (override); `titles["edit_board"] == "Edit Board"`.

5. `test_list_tools_sorted` — names returned in sorted order.

**Adapter tests:**

6. `test_adapter_moves_string_guidance` — string `assistant_guidance` appears in `content[0].text`; removed from `structuredContent`; data keys preserved.

7. `test_adapter_dict_guidance_renders_instruction_only` — guidance `{"action": "ASK_CLARIFYING", "instruction": "Ask the user X."}` → `content[0].text` contains `"Ask the user X."` and does NOT contain `"ASK_CLARIFYING"`. (Validates §8.1 action-drop.)

8. `test_adapter_discriminates_top_meta` — input top-level `_meta={"saved_board_hash": "abc", "openai/toolInvocation/invoking": "x"}` → adapted `result.meta == {"saved_board_hash": "abc"}` (openai/* stripped, saved_board_hash kept).

9. `test_adapter_empty_meta_becomes_none` — input top-level `_meta={"openai/toolInvocation/invoked": "x"}` → adapted `result.meta is None`.

10. `test_adapter_empty_content_with_guidance` — input `content=[]`, `structuredContent={"clusters": [], "assistant_guidance": "No board."}` → `content[0].text == "No board."`; `structuredContent` has `clusters`, no `assistant_guidance`.

11. `test_adapter_none_structured_content` — `structuredContent=None`, top-level `_meta={"saved_board_hash": "h", "openai/x": 1}` → returns new object (`adapted is not result`), `structuredContent is None`, `result.meta == {"saved_board_hash": "h"}`.

12. `test_adapter_does_not_mutate_original` — original `structuredContent` still contains `assistant_guidance` after adaptation; `adapted is not result`.

13. `test_adapter_preserves_data` — `clusters`/`cluster_names`/`has_history` unchanged through adaptation, no truncation.

---

## Definition of Done

- [ ] `response_adapter_dupl.py` — `adapt_tool_result` + the two private helpers; drops `action`, discriminates top-level `_meta`, handles empty content.
- [ ] `tools_list_dupl.py` — `async list_tools_for_claude` + `_derive_title`; title override map; destructiveHint override map; `_meta=None`; no visibility filter; built from `TOOL_REGISTRY`.
- [ ] `handlers/tools_dupl.py` — full dispatcher copied from `clarity/handlers/tools.py`, adapter called after type guard, only success path adapted.
- [ ] `server_dupl.py` `_list_tools` calls `list_tools_for_claude()` — no other change.
- [ ] All new files carry the `(duplicate)` header.
- [ ] All existing scaffold tests pass unchanged; `restore_mcp_auth_globals` fixture untouched.
- [ ] All 13 new tests pass.
- [ ] Zero files modified in `mcp_server/clarity/` and `backend/`.
- [ ] Run the FULL `tests/unit/` suite (not just the scaffold dir) and confirm no new failures beyond the 5 known-pre-existing stale `clarity` resource-URL tests.

---

## Scope honesty

This increment makes tools callable and responses Claude-correct. It does NOT add the widget, docs, screenshots, privacy policy, or Phase-2 OAuth allowlist. Not submission-ready. Widget is the next increment.

---

## Notes for the implementer (flag, don't fix)

- If any symbol name in the `clarity/handlers/tools.py` copy or the `mcp_auth_dupl` import list doesn't match source, STOP and report — do not guess.
- If `mcp_types.Tool` does not accept `annotations` as a constructor kwarg in the installed SDK version, use the post-construction attribute set that the shared `list_tools()` uses, and note it.
- The `save_board` name appears in `config.TOOL_SCOPES` but is not registered in `TOOL_REGISTRY` (not imported). The Claude tool list is driven by `TOOL_REGISTRY`, so it correctly excludes `save_board`. Do not add it. Flag if this discrepancy looks intentional or not — it's a pre-existing `clarity` config/registry mismatch, out of scope to fix here.