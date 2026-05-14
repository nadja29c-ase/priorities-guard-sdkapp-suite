# Increment Shared-Annotations-01: Fix Tool Annotations Across OpenAI + Claude

**Goal:** Add `title` to `ToolDefinition` and fix `destructive_hint` on all write tools. Fix once in the shared source — both ChatGPT and Claude inherit correct annotations. Simplify `tools_list_dupl.py` to use `tool_def.title` directly.

---

## Context

PG v1.0 is published in the ChatGPT store. There is no OpenAI review risk. The shared codebase can be touched.

**Two annotation gaps exist across all 17 tools:**

1. `title` — required by Anthropic §5E. Missing from `ToolDefinition` entirely. Claude server compensates with `_derive_title()` in `tools_list_dupl.py` — a workaround that becomes unnecessary after this fix.

2. `destructive_hint=False` on write tools — required `True` by both Anthropic (any write) and OpenAI (write with side effects). Currently wrong on 9 tools.

**Tools that are already correct and need no `destructive_hint` change:**
- `delete_priority`, `delete_deliverable`, `delete_goal` — already `True` ✅
- All read-only tools — correctly `False` ✅

---

## Pre-Implementation

Read `doc/OPERATIONS_PREDEPLOY.md` before starting. No backend changes. No migration. Both MCP servers must be regression-tested after this change.

---

## CRITICAL: Copy-Adjust, Never Rewrite

Each file already exists. Make only the listed changes. Do not restructure, reorder, or improve anything not listed.

---

## Part A: `mcp_server/priority_guardian/tools/base.py`

Add `title: str` field to `ToolDefinition`.

**Change:** Add after `name: str`:
```python
title: str  # Human-readable tool name for UI display (required by Anthropic §5E)
```

No other changes to `base.py`.

---

## Part B: `mcp_server/priority_guardian/tools/__init__.py`

Pass `title` from `tool_def` to `ToolAnnotations` in `list_tools()`.

**Change:** In the `ToolAnnotations` construction block:
```python
# Current:
tool.annotations = mcp_types.ToolAnnotations(
    readOnlyHint=tool_def.read_only_hint,
    destructiveHint=tool_def.destructive_hint,
    openWorldHint=tool_def.open_world_hint,
)

# Replace with:
tool.annotations = mcp_types.ToolAnnotations(
    title=tool_def.title,
    readOnlyHint=tool_def.read_only_hint,
    destructiveHint=tool_def.destructive_hint,
    openWorldHint=tool_def.open_world_hint,
)
```

No other changes to `__init__.py`.

---

## Part C: Tool files — add `title`, fix `destructive_hint` where needed

For each file below, make only the two listed changes to the `ToolDefinition(...)` instantiation at the bottom of the file. Do not touch the handler, schema, or any other code.

### Public tools (7 files)

**`tools/get_priorities.py`**
```python
GET_PRIORITIES = ToolDefinition(
    name=NAME,
    title="Get Priorities",          # ADD
    # ... all other fields unchanged
)
```

**`tools/create_priority.py`**
```python
CREATE_PRIORITY = ToolDefinition(
    name=NAME,
    title="Create Priority",         # ADD
    # ...
    read_only_hint=False,
    destructive_hint=True,           # CHANGE: False → True (creates DB record)
    # ...
)
```

**`tools/get_priority_events.py`**
```python
GET_PRIORITY_EVENTS = ToolDefinition(
    name=NAME,
    title="Get Priority Events",     # ADD
    # ... all other fields unchanged
)
```

**`tools/render_weekly_report.py`**
```python
RENDER_WEEKLY_REPORT = ToolDefinition(
    name=NAME,
    title="Render Weekly Report",    # ADD
    # ... all other fields unchanged
)
```

**`tools/get_patterns.py`**
```python
GET_PATTERNS = ToolDefinition(
    name=NAME,
    title="Get Patterns",            # ADD
    # ... all other fields unchanged
)
```

**`tools/onboarding_calendar_setup.py`**
```python
ONBOARDING_CALENDAR_SETUP = ToolDefinition(
    name=NAME,
    title="Onboarding Calendar Setup",  # ADD
    # ... all other fields unchanged
)
```

**`tools/inspect_adapt.py`**
```python
INSPECT_ADAPT = ToolDefinition(
    name=NAME,
    title="Inspect Adapt",           # ADD
    # ... all other fields unchanged
)
```

### Widget tools (10 files)

**`tools/widget_tools/add_priority.py`**
```python
ADD_PRIORITY = ToolDefinition(
    name=NAME,
    title="Add Priority",            # ADD
    # ...
    destructive_hint=True,           # CHANGE: False → True (creates DB record)
    # ...
)
```

**`tools/widget_tools/update_priority.py`**
```python
UPDATE_PRIORITY = ToolDefinition(
    name=NAME,
    title="Update Priority",         # ADD
    # ...
    destructive_hint=True,           # CHANGE: False → True (modifies DB record)
    # ...
)
```

**`tools/widget_tools/delete_priority.py`**
```python
DELETE_PRIORITY = ToolDefinition(
    name=NAME,
    title="Delete Priority",         # ADD
    # destructive_hint=True already — no change
)
```

**`tools/widget_tools/add_deliverable.py`**
```python
ADD_DELIVERABLE = ToolDefinition(
    name=NAME,
    title="Add Deliverable",         # ADD
    # ...
    destructive_hint=True,           # CHANGE: False → True (creates DB record)
    # ...
)
```

**`tools/widget_tools/update_deliverable.py`**
```python
UPDATE_DELIVERABLE = ToolDefinition(
    name=NAME,
    title="Update Deliverable",      # ADD
    # ...
    destructive_hint=True,           # CHANGE: False → True (modifies DB record)
    # ...
)
```

**`tools/widget_tools/delete_deliverable.py`**
```python
DELETE_DELIVERABLE = ToolDefinition(
    name=NAME,
    title="Delete Deliverable",      # ADD
    # destructive_hint=True already — no change
)
```

**`tools/widget_tools/add_goal.py`**
```python
ADD_GOAL = ToolDefinition(
    name=NAME,
    title="Add Goal",                # ADD
    # ...
    destructive_hint=True,           # CHANGE: False → True (creates DB record)
    # ...
)
```

**`tools/widget_tools/update_goal.py`**
```python
UPDATE_GOAL = ToolDefinition(
    name=NAME,
    title="Update Goal",             # ADD
    # ...
    destructive_hint=True,           # CHANGE: False → True (modifies DB record)
    # ...
)
```

**`tools/widget_tools/delete_goal.py`**
```python
DELETE_GOAL = ToolDefinition(
    name=NAME,
    title="Delete Goal",             # ADD
    # destructive_hint=True already — no change
)
```

**`tools/widget_tools/connect_google_calendar.py`**
```python
CONNECT_GOOGLE_CALENDAR = ToolDefinition(
    name=NAME,
    title="Connect Google Calendar", # ADD
    # ...
    destructive_hint=True,           # CHANGE: False → True (modifies connection state, initiates OAuth flow)
    # ...
)
```

> Note: `connect_google_calendar` is not destructive in the "deletes data" sense, but both Anthropic and OpenAI classify tools with external side effects (OAuth flow initiation, connection state change) as `destructiveHint: true`. Marking it `True` is correct and conservative.

**`tools/widget_tools/disconnect_google_calendar.py`**
```python
DISCONNECT_GOOGLE_CALENDAR = ToolDefinition(
    name=NAME,
    title="Disconnect Google Calendar",  # ADD
    # ...
    destructive_hint=True,               # CHANGE: False → True (revokes OAuth tokens, modifies connection state)
    # ...
)
```

---

## Part D: `backend/core/config.py`

Add localhost callback URIs for MCP Inspector and Claude Code local development.

**Change:** Append to `_CHATGPT_REDIRECT_URIS` list:
```python
_CHATGPT_REDIRECT_URIS: ClassVar[list[str]] = [
    # ChatGPT (existing — do not modify)
    "https://chatgpt.com/connector/oauth/",  # prefix — any connector callback_id
    "https://chatgpt.com/connector_platform_oauth_redirect",  # legacy
    "https://platform.openai.com/apps-manage/oauth",  # review
    # Claude
    "https://claude.ai/api/mcp/auth_callback",
    "https://claude.com/api/mcp/auth_callback",
    # Claude Code + MCP Inspector (local development and Anthropic review testing)
    "http://localhost:6274/oauth/callback",
    "http://localhost:6274/oauth/callback/debug",
]
```

No other changes to `config.py`.

---

## Part E: `mcp_server/priority_guardian_claude/response_adapter_dupl.py`

Add `_meta.ui.domain` to tool result for iframe isolation stability.

**Change 1 — Add import at top of file:**
```python
from mcp_server.priority_guardian_claude.handlers.resources_dupl import WIDGET_APP_DOMAIN
```

**Change 2 — Update `adapt_get_priorities_meta()` to include `domain`:**
```python
# Current:
new_meta = {
    **existing_meta,
    "ui": {
        "resourceUri": WIDGET_URI,
    },
}

# Replace with:
new_meta = {
    **existing_meta,
    "ui": {
        "resourceUri": WIDGET_URI,
        "domain": WIDGET_APP_DOMAIN,
    },
}
```

No other changes to this file.

---

## Part F: `mcp_server/priority_guardian_claude/tools_list_dupl.py`

Make only these two targeted changes. Do not rewrite the file.

**Change 1 — Remove `_derive_title()`:** Delete the entire `_derive_title` function. It is no longer needed because `title` now comes from `tool_def.title`.

**Change 2 — Replace `title=_derive_title(tool_def.name)` with `title=tool_def.title`** in the `ToolAnnotations` construction:

```python
# Current:
tool.annotations = mcp_types.ToolAnnotations(
    title=_derive_title(tool_def.name),
    readOnlyHint=tool_def.read_only_hint,
    destructiveHint=tool_def.destructive_hint,
    openWorldHint=tool_def.open_world_hint,
)

# Replace with:
tool.annotations = mcp_types.ToolAnnotations(
    title=tool_def.title,
    readOnlyHint=tool_def.read_only_hint,
    destructiveHint=tool_def.destructive_hint,
    openWorldHint=tool_def.open_world_hint,
)
```

No other changes to this file. All other lines stay exactly as they are.

---

## What NOT to Touch

- Any handler function in any tool file
- Any `INPUT_SCHEMA`, `DESCRIPTION`, `REQUIRED_SCOPES`, or `WIDGET_URI` in any tool file
- Any backend file except `backend/core/config.py` (OAuth URI list only)
- Any other file in `mcp_server/priority_guardian_claude/` except `response_adapter_dupl.py` and `tools_list_dupl.py`

---

## Tests

### Shared `list_tools()` tests — add to existing shared test suite

These verify the ChatGPT/shared path is also correct after the change to `__init__.py`.

**`test_shared_list_tools_all_tools_have_title`**
```python
@pytest.mark.asyncio
async def test_shared_list_tools_all_tools_have_title():
    from mcp_server.priority_guardian.tools import list_tools
    tools = await list_tools()
    for tool in tools:
        assert tool.annotations is not None
        assert tool.annotations.title is not None
        assert len(tool.annotations.title) > 0, f"{tool.name} has empty title in shared list_tools()"
```

**`test_shared_create_priority_destructive_hint_true`**
```python
@pytest.mark.asyncio
async def test_shared_create_priority_destructive_hint_true():
    from mcp_server.priority_guardian.tools import list_tools
    tools = await list_tools()
    tool = next((t for t in tools if t.name == "create_priority"), None)
    assert tool is not None
    assert tool.annotations.destructiveHint is True
```

### Claude scaffold tests — add to `tests/unit/mcp_pg_claude/test_scaffold.py`

**`test_all_claude_tools_have_title`**
```python
@pytest.mark.asyncio
async def test_all_claude_tools_have_title():
    from mcp_server.priority_guardian_claude.tools_list_dupl import list_tools_for_claude
    tools = await list_tools_for_claude()
    for tool in tools:
        assert tool.annotations is not None
        assert tool.annotations.title is not None
        assert len(tool.annotations.title) > 0, f"{tool.name} has empty title"
```

**`test_create_priority_destructive_hint_true`**
```python
@pytest.mark.asyncio
async def test_create_priority_destructive_hint_true():
    from mcp_server.priority_guardian_claude.tools_list_dupl import list_tools_for_claude
    tools = await list_tools_for_claude()
    tool = next((t for t in tools if t.name == "create_priority"), None)
    assert tool is not None
    assert tool.annotations.destructiveHint is True
```

**`test_read_only_tools_destructive_hint_false`**
```python
@pytest.mark.asyncio
async def test_read_only_tools_destructive_hint_false():
    from mcp_server.priority_guardian_claude.tools_list_dupl import list_tools_for_claude
    tools = await list_tools_for_claude()
    read_only = {
        "get_priorities", "get_patterns", "get_priority_events",
        "render_weekly_report", "onboarding_calendar_setup", "inspect_adapt",
    }
    for tool in tools:
        if tool.name in read_only:
            assert tool.annotations.destructiveHint is False, (
                f"{tool.name} should have destructiveHint=False"
            )
```

**`test_no_private_tools_in_claude_list`**
```python
@pytest.mark.asyncio
async def test_no_private_tools_in_claude_list():
    from mcp_server.priority_guardian.tools import TOOL_REGISTRY
    from mcp_server.priority_guardian_claude.tools_list_dupl import list_tools_for_claude
    tools = await list_tools_for_claude()
    tool_names = {t.name for t in tools}
    private_names = {name for name, td in TOOL_REGISTRY.items() if td.visibility == "private"}
    assert tool_names & private_names == set()
```

### Backend OAuth tests — add to `tests/unit/core/test_normalize_redirect_uri.py`

**`test_mcp_inspector_localhost_uris_accepted`**
```python
def test_mcp_inspector_localhost_uris_accepted():
    from backend.core.config import settings
    allowed = settings.OAUTH_ALLOWED_REDIRECT_URIS
    assert "http://localhost:6274/oauth/callback" in allowed
    assert "http://localhost:6274/oauth/callback/debug" in allowed
```

### Response adapter tests — add to `tests/unit/mcp_pg_claude/test_scaffold.py`

**`test_adapt_get_priorities_meta_sets_domain`**
```python
def test_adapt_get_priorities_meta_sets_domain():
    from mcp_server.priority_guardian_claude.response_adapter_dupl import adapt_get_priorities_meta
    from mcp_server.priority_guardian_claude.handlers.resources_dupl import WIDGET_APP_DOMAIN
    from mcp import types as mcp_types

    result = mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="3 priorities")],
        structuredContent={"success": True, "data": {"priorities": []}},
    )
    adapted = adapt_get_priorities_meta(result)
    assert adapted.meta["ui"]["domain"] == WIDGET_APP_DOMAIN
```

### Run full test suite

```
pytest tests/ -v
```

All existing tests must pass. This is a shared change — run the complete suite, not just Claude scaffold tests.

---

## Deployment

Both MCP servers must be redeployed after this change:
- ChatGPT MCP server on Render — shared `list_tools()` changed
- Claude MCP server on Render — `tools_list_dupl.py` changed

Read `doc/OPERATIONS_PREDEPLOY.md` for pre-deployment checklist before deploying either service.

---

## Definition of Done

- [ ] `title: str` field added to `ToolDefinition` in `base.py`
- [ ] `title=tool_def.title` passed to `ToolAnnotations` in shared `list_tools()` in `__init__.py`
- [ ] All 17 tool files have `title=` in their `ToolDefinition` instantiation
- [ ] `create_priority` — `destructive_hint=True`
- [ ] `add_priority` — `destructive_hint=True`
- [ ] `update_priority` — `destructive_hint=True`
- [ ] `add_deliverable` — `destructive_hint=True`
- [ ] `update_deliverable` — `destructive_hint=True`
- [ ] `add_goal` — `destructive_hint=True`
- [ ] `update_goal` — `destructive_hint=True`
- [ ] `connect_google_calendar` — `destructive_hint=True`
- [ ] `disconnect_google_calendar` — `destructive_hint=True`
- [ ] `tools_list_dupl.py` — `_derive_title()` removed, uses `tool_def.title` directly
- [ ] `backend/core/config.py` — localhost:6274 callback URIs added
- [ ] `response_adapter_dupl.py` — `WIDGET_APP_DOMAIN` imported, `domain` added to `adapt_get_priorities_meta()`
- [ ] All 6 new tests pass (4 Claude scaffold + 1 backend OAuth + 1 adapter domain)
- [ ] Full test suite passes (`pytest tests/ -v`)
- [ ] Both MCP servers redeployed
