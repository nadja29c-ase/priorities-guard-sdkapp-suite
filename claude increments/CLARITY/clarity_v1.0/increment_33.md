# Increment: Add securitySchemes to Tool Metadata

**Date:** 2025-12-25  
**Component:** Clarity MCP Server  
**Priority:** High (OAuth compliance)

---

## Context

OpenAI SDK documentation states:

> "Triggering the tool-level OAuth flow requires both metadata (`securitySchemes` and the resource metadata document) **and** runtime errors that carry `_meta["mcp/www_authenticate"]`. Without both halves ChatGPT will not show the linking UI for that tool."

Clarity currently:
- ✅ Has `_meta["mcp/www_authenticate"]` in error responses
- ✅ Has protected resource metadata at `/.well-known/oauth-protected-resource`
- ❌ Missing `securitySchemes` in tool `_meta`

Without `securitySchemes`, ChatGPT may not properly trigger OAuth linking UI.

---

## Objective

Add `securitySchemes` to each tool's `_meta` in the `list_tools()` output.

---

## Requirements

### File: `mcp_server/clarity/tools/__init__.py`

In the `list_tools()` function, add `securitySchemes` to each tool's `_meta`.

**Format per SDK docs:**

```python
# For tools requiring OAuth:
"securitySchemes": [{"type": "oauth2", "scopes": ["clarity.write"]}]

# For anonymous tools (none in Clarity currently):
"securitySchemes": [{"type": "noauth"}]
```

**Logic:**
- If `tool_def.required_scopes` is non-empty → use `oauth2` with those scopes
- If `tool_def.required_scopes` is empty → use `noauth`

**Placement in `_meta`:**
- Add `securitySchemes` to ALL tool metadata blocks (widget-producing, widget-accessible, and data-only)

### Current Code (abbreviated):

```python
if tool_def.widget_uri:
    meta = {
        "openai/outputTemplate": tool_def.widget_uri,
        "openai/toolInvocation/invoking": "Processing...",
        "openai/toolInvocation/invoked": "Done.",
        "openai/widgetAccessible": True,
        "openai/resultCanProduceWidget": True,
        "annotations": annotations,
    }
elif tool_def.widget_accessible:
    meta = {
        "openai/widgetAccessible": True,
        "annotations": annotations,
    }
else:
    meta = {
        "annotations": annotations,
    }
```

### Target Code Pattern:

```python
# Build securitySchemes based on required_scopes
if tool_def.required_scopes:
    security_schemes = [{"type": "oauth2", "scopes": tool_def.required_scopes}]
else:
    security_schemes = [{"type": "noauth"}]

if tool_def.widget_uri:
    meta = {
        "openai/outputTemplate": tool_def.widget_uri,
        "openai/toolInvocation/invoking": "Processing...",
        "openai/toolInvocation/invoked": "Done.",
        "openai/widgetAccessible": True,
        "openai/resultCanProduceWidget": True,
        "annotations": annotations,
        "securitySchemes": security_schemes,
    }
elif tool_def.widget_accessible:
    meta = {
        "openai/widgetAccessible": True,
        "annotations": annotations,
        "securitySchemes": security_schemes,
    }
else:
    meta = {
        "annotations": annotations,
        "securitySchemes": security_schemes,
    }
```

---

## Data Reference

All Clarity tools require `clarity.write` scope (from `config.py`):

```python
TOOL_SCOPES = {
    "organize_thoughts": ["clarity.write"],
    "load_saved_board": ["clarity.write"],
    "read_saved_board": ["clarity.write"],
    "save_board": ["clarity.write"],
    "prioritize_clusters": ["clarity.write"],
    "edit_board": ["clarity.write"],
    "delete_my_data": ["clarity.write"],
}
```

All tools will get: `"securitySchemes": [{"type": "oauth2", "scopes": ["clarity.write"]}]`

---

## Unit Tests

**File:** `mcp_server/clarity/tests/test_security_schemes.py`

**Test harness:** pytest + pytest-asyncio

```python
import pytest
from mcp_server.clarity.tools import list_tools, TOOL_REGISTRY

@pytest.mark.asyncio
async def test_all_tools_have_security_schemes():
    """Every tool must declare securitySchemes in meta."""
    tools = await list_tools()
    for tool in tools:
        assert tool.meta is not None, f"{tool.name}: missing meta"
        assert "securitySchemes" in tool.meta, f"{tool.name}: missing securitySchemes"
        schemes = tool.meta["securitySchemes"]
        assert isinstance(schemes, list), f"{tool.name}: securitySchemes must be list"
        assert len(schemes) > 0, f"{tool.name}: securitySchemes cannot be empty"

@pytest.mark.asyncio
async def test_security_schemes_match_required_scopes():
    """securitySchemes must reflect tool_def.required_scopes."""
    tools = await list_tools()
    for tool in tools:
        tool_def = TOOL_REGISTRY.get(tool.name)
        schemes = tool.meta["securitySchemes"]

        if tool_def.required_scopes:
            # Tools with scopes → oauth2
            assert schemes[0]["type"] == "oauth2", f"{tool.name}: expected oauth2"
            assert schemes[0]["scopes"] == tool_def.required_scopes
        else:
            # Tools without scopes → noauth
            assert schemes[0]["type"] == "noauth", f"{tool.name}: expected noauth"

@pytest.mark.asyncio
async def test_security_schemes_format():
    """Validate securitySchemes structure per SDK spec."""
    tools = await list_tools()
    for tool in tools:
        for scheme in tool.meta["securitySchemes"]:
            assert "type" in scheme
            assert scheme["type"] in ("oauth2", "noauth")
            if scheme["type"] == "oauth2":
                assert "scopes" in scheme
                assert isinstance(scheme["scopes"], list)
```

---

## Integration Tests

**Scope:** MCP Inspector

1. **Tool discovery shows securitySchemes**
   - Start Clarity MCP server locally
   - Connect via MCP Inspector
   - Call `tools/list`
   - Verify each tool's `_meta` includes `securitySchemes`
   - Verify format: `[{"type": "oauth2", "scopes": ["clarity.write"]}]`

2. **OAuth flow triggers correctly** (manual, ChatGPT)
   - In ChatGPT, invoke a Clarity tool without auth
   - Verify OAuth linking UI appears (not just error message)

---

## Validation Criteria

- [ ] All tools in `list_tools()` output include `securitySchemes` in `_meta`
- [ ] `securitySchemes` format: `[{"type": "oauth2", "scopes": ["clarity.write"]}]`
- [ ] Scopes in `securitySchemes` match `tool_def.required_scopes`
- [ ] Existing annotations remain correct (readOnlyHint/destructiveHint/openWorldHint unchanged)
- [ ] No TypeScript/Python errors
- [ ] All existing tests pass
- [ ] New test file `test_security_schemes.py` passes
- [ ] MCP Inspector shows `securitySchemes` in tool metadata

---

## Out of Scope

- Adding `noauth` tools (Clarity has none)
- Changing scope requirements
- Backend OAuth provider changes
- Widget changes

---

## Implementation Notes

### Pydantic alias pattern for `_meta`
MCP SDK uses Pydantic with field alias: `meta: ... = Field(alias="_meta")`

- **Constructor:** Use `_meta=...` (the alias)
- **Access:** Use `tool.meta` (Python field name)

Example:
```python
# Constructing Tool
tool = mcp_types.Tool(name="foo", ..., _meta={"securitySchemes": [...]})

# Accessing in tests
assert tool.meta["securitySchemes"] == [...]
```

### `securitySchemes` placement
Per ChatGPT Apps SDK API Reference, `securitySchemes` is explicitly allowed in `_meta` as a "back-compat mirror for clients that only read `_meta`". Placing it in `_meta` is correct and spec-compliant.

### `annotations` placement
Current code places annotations inside `_meta`. This is SDK-version-dependent:
- MCP spec prefers top-level `annotations` field
- Older mcp SDK versions (like ^1.3.1) may not support this cleanly
- ChatGPT reads annotations from `_meta` in practice

**Decision:** Keep annotations in `_meta` for now. This is pragmatically correct, not a blocker. Future cleanup when upgrading MCP SDK.

---

## Reference

- SDK docs: "Triggering authentication UI" section
- Current tools/__init__.py: `mcp_server/clarity/tools/__init__.py`
- Tool definitions: `mcp_server/clarity/tools/base.py` (`required_scopes` field)
- Scope config: `mcp_server/clarity/config.py` (`TOOL_SCOPES`)