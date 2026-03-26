# Increment: Fix OAuth www_authenticate Format + Hardening

## Priority: HIGH (Blocking)

## Context

The OpenAI ChatGPT Apps SDK requires a specific format for OAuth error responses to trigger the account linking UI. Current implementation uses wrong format — ChatGPT will not show OAuth linking.

---

## Problem 1: `www_authenticate` Format (CRITICAL)

### Current (WRONG)

`mcp_server/clarity/mcp_auth.py` returns:

```python
{
    "mcp/www_authenticate": [{
        "type": "oauth2",
        "resource_metadata": f"{MCP_SERVER_URL}/.well-known/oauth-protected-resource"
    }]
}
```

### SDK Expects (RFC 6750 header string)

From OpenAI SDK Authentication docs:

```json
{
  "mcp/www_authenticate": [
    "Bearer resource_metadata=\"https://your-mcp.example.com/.well-known/oauth-protected-resource\", error=\"insufficient_scope\", error_description=\"You need to login to continue\""
  ]
}
```

The value must be an **RFC 6750 WWW-Authenticate header string**, not a JSON object.

### Files to Change

1. **`mcp_server/clarity/mcp_auth.py`**
   - `build_unauthorized_error()` — return dict with RFC 6750 string
   - `build_forbidden_error()` — return dict with RFC 6750 string including scope info

2. **`mcp_server/clarity/handlers/tools.py`**
   - Use `meta=` parameter on `CallToolResult` instead of `json.dumps()` in text content
   - Provide human-readable text in `content`, not JSON

### Expected Format After Fix

**For 401 Unauthorized:**
```python
return mcp_types.CallToolResult(
    content=[mcp_types.TextContent(
        type="text",
        text="Authentication required. Please connect your account."
    )],
    meta={
        "mcp/www_authenticate": [
            f'Bearer resource_metadata="{MCP_SERVER_URL}/.well-known/oauth-protected-resource", error="invalid_token", error_description="No access token provided"'
        ]
    },
    isError=True,
)
```

**For 403 Forbidden (insufficient scope):**
```python
return mcp_types.CallToolResult(
    content=[mcp_types.TextContent(
        type="text",
        text="Insufficient permissions. Please reconnect your account."
    )],
    meta={
        "mcp/www_authenticate": [
            f'Bearer resource_metadata="{MCP_SERVER_URL}/.well-known/oauth-protected-resource", error="insufficient_scope", error_description="Required scope: clarity.write", scope="clarity.write"'
        ]
    },
    isError=True,
)
```

### RFC 6750 Header Format

```
Bearer resource_metadata="<url>", error="<code>", error_description="<message>"
```

Optional additional parameters: `scope="<required_scopes>"`

Error codes per RFC 6750:
- `invalid_token` — token missing, malformed, or expired
- `insufficient_scope` — token valid but lacks required scopes

---

## Problem 2: Annotations Placement (MEDIUM)

### Current

Annotations only in `_meta`:
```python
meta = {
    "annotations": annotations,
    ...
}
```

### MCP Spec

Annotations should be a top-level field on `Tool`, not inside `_meta`.

### Risk

- Today: ChatGPT reads from `_meta` → works
- Future SDK update: annotations silently ignored

### Fix

Mirror annotations at top level if the SDK supports it:

```python
tool = mcp_types.Tool(
    name=tool_def.name,
    ...
    _meta=meta,
)

# Future-proof: mirror at top level if supported
if hasattr(tool, "annotations"):
    tool.annotations = annotations
```

**Important:** Check the instance (`tool`), not the class (`mcp_types.Tool`). The `annotations` field may be defined dynamically on instances, not guaranteed to exist on the class.

This is non-breaking. If attribute doesn't exist, nothing happens.

### File to Change

`mcp_server/clarity/tools/__init__.py` — in `list_tools()`

---

## Problem 3: Tool Ordering (LOW)

### Current

```python
for tool_def in TOOL_REGISTRY.values():
```

Dict order depends on import order — non-deterministic.

### Fix

```python
for tool_def in sorted(TOOL_REGISTRY.values(), key=lambda t: t.name):
```

Benefits:
- Reproducible output
- Stable test assertions
- Clean diffs in MCP Inspector

### File to Change

`mcp_server/clarity/tools/__init__.py` — in `list_tools()`

---

## Out of Scope

- Backend OAuth provider changes
- Widget changes
- Scope requirement changes
- PKCE validation (already correct)

---

## Unit Tests

**File:** `mcp_server/clarity/tests/test_www_authenticate.py`

```python
import pytest
from mcp_server.clarity.mcp_auth import (
    build_unauthorized_error,
    build_forbidden_error,
    MCP_SERVER_URL,
)

def test_unauthorized_error_format():
    """401 response has RFC 6750 header string format."""
    result = build_unauthorized_error()
    
    assert "mcp/www_authenticate" in result
    www_auth = result["mcp/www_authenticate"]
    assert isinstance(www_auth, list)
    assert len(www_auth) == 1
    
    # Must be string, not dict
    header = www_auth[0]
    assert isinstance(header, str)
    
    # Must contain required parts
    assert header.startswith("Bearer ")
    assert f'resource_metadata="{MCP_SERVER_URL}/.well-known/oauth-protected-resource"' in header
    assert 'error="invalid_token"' in header
    assert 'error_description=' in header

def test_forbidden_error_format():
    """403 response has RFC 6750 header string with scope."""
    result = build_forbidden_error(required_scopes=["clarity.write"])
    
    assert "mcp/www_authenticate" in result
    www_auth = result["mcp/www_authenticate"]
    header = www_auth[0]
    
    assert isinstance(header, str)
    assert 'error="insufficient_scope"' in header
    assert 'scope="clarity.write"' in header

def test_forbidden_error_multiple_scopes():
    """403 with multiple scopes joins them with space."""
    result = build_forbidden_error(required_scopes=["clarity.read", "clarity.write"])
    
    header = result["mcp/www_authenticate"][0]
    assert 'scope="clarity.read clarity.write"' in header
```

**File:** `mcp_server/clarity/tests/test_tool_ordering.py`

```python
import pytest
from mcp_server.clarity.tools import list_tools

@pytest.mark.asyncio
async def test_tools_returned_in_alphabetical_order():
    """Tools are returned sorted by name for deterministic output."""
    tools = await list_tools()
    names = [t.name for t in tools]
    assert names == sorted(names)
```

---

## Integration Tests

**MCP Inspector:**

1. Connect to Clarity MCP server without auth token
2. Call any tool (e.g., `organize_thoughts`)
3. Verify response contains:
   - `isError: true`
   - `_meta.mcp/www_authenticate` as RFC 6750 string (not JSON object)
   - Human-readable text in `content`

**ChatGPT (manual):**

1. Remove Clarity connection
2. Start new conversation
3. Say "organize my thoughts: buy milk, call mom"
4. Verify OAuth linking UI appears (not just error message)

---

## Validation Criteria

- [ ] `build_unauthorized_error()` returns `{"mcp/www_authenticate": ["Bearer ..."]}`
- [ ] `build_forbidden_error()` returns RFC 6750 string with scope info
- [ ] `handlers/tools.py` uses `meta=` parameter on `CallToolResult`
- [ ] `handlers/tools.py` provides human-readable error text, not JSON
- [ ] Tool ordering is deterministic (sorted by name)
- [ ] Annotations mirrored at top level if SDK supports it
- [ ] All existing tests pass
- [ ] New tests pass
- [ ] MCP Inspector shows correct `www_authenticate` format