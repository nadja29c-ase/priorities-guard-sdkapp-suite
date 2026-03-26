# Increment 06: Clarity MCP Server Refactor

## Context

`mcp_server/clarity/server.py` is ~700 lines with everything in one file. We're adding 2-3 more tools soon. Current structure won't scale.

## Goal

Refactor into modular structure where adding a new tool means adding one file.

## Target Structure

```
mcp_server/clarity/
├── server.py              # SLIM: app creation, middleware, startup/shutdown only
├── config.py              # ✓ Keep as-is
├── mcp_auth.py            # ✓ Keep as-is
├── discovery.py           # ✓ Keep as-is
├── http_client.py         # NEW: module-level httpx client
├── persistence.py         # NEW: backend API calls
├── handlers/
│   ├── __init__.py
│   ├── resources.py       # Widget resource handlers
│   └── tools.py           # Tool call dispatcher
├── tools/
│   ├── __init__.py        # TOOL_REGISTRY + _list_tools handler
│   ├── base.py            # ToolDefinition dataclass/protocol
│   └── cluster_raw_thoughts.py  # First tool (extract from server.py)
└── widgets/
    └── clarity-clusters.html    # ✓ Keep as-is (move into widgets/)
```

## Deliverables

### 1. `http_client.py`

Extract from server.py:
- `_http_client` module-level variable
- `_get_http_client()` function
- `cleanup_http_client()` async function

### 2. `persistence.py`

Extract persistence logic from `_call_tool_request`:
- `persist_cluster(user_id, cluster_data, thoughts_exhausted, correctly_clustered)` async function
- Uses `_get_http_client()` from http_client.py
- Non-blocking (catches exceptions, logs warnings)
- Returns `cluster_id` or `None` on failure

### 3. `handlers/resources.py`

Extract from server.py:
- `WIDGET_URI` constant
- `WIDGET_HTML` loaded at module import
- `_list_resources()` handler
- `_list_resource_templates()` handler
- `_handle_read_resource()` handler

### 4. `handlers/tools.py`

New dispatcher:
- Imports `TOOL_REGISTRY` from `tools/__init__.py`
- `_call_tool_request(req)` function:
  - Extract name, arguments, meta from request
  - Check if tool exists in registry → error if not
  - Call `authenticate_request(name, meta)` → handle UnauthorizedError, InsufficientScopeError
  - Delegate to `TOOL_REGISTRY[name].handle(user_id, correlation_id, arguments)`
  - Return result

### 5. `tools/base.py`

```python
from dataclasses import dataclass
from typing import Callable, Awaitable, Any

@dataclass
class ToolDefinition:
    """
    Definition for an MCP tool.
    
    Contract:
    - Tool handlers receive raw `arguments` dict from ChatGPT
    - Handlers are responsible for validating arguments (e.g., via Pydantic)
    - Dispatcher does NOT validate against input_schema
    - input_schema is for ChatGPT/MCP discovery only
    """
    name: str
    description: str
    input_schema: dict
    required_scopes: list[str]
    widget_uri: str | None  # None if tool doesn't produce widget
    handle: Callable[[str, str, dict], Awaitable[Any]]  # (user_id, correlation_id, arguments)
```

### 6. `tools/__init__.py`

- `TOOL_REGISTRY: dict[str, ToolDefinition]` — populated by imports
- `register_tool(tool: ToolDefinition)` — adds to registry
- `get_tool(name: str) -> ToolDefinition | None`
- `_list_tools()` handler — builds `mcp_types.Tool` list from registry with `_meta`

**CRITICAL: Explicit imports for registration**

Tools self-register at import time. All tools MUST be imported in this file:

```python
# tools/__init__.py

# WARNING: Tools self-register at import time.
# If you add a new tool, import it here or it won't be in the registry.

from . import cluster_raw_thoughts  # noqa: F401
# from . import identify_relevant  # noqa: F401  (future)
# from . import specify_next_steps  # noqa: F401  (future)
```

This prevents "tool not found" bugs that are painful to debug.

### 7. `tools/cluster_raw_thoughts.py`

Extract from server.py:
- `DESCRIPTION` constant
- `INPUT_SCHEMA` constant (was `CLUSTER_RAW_THOUGHTS_SCHEMA`)
- `REQUIRED_SCOPES = ["clarity.write"]`
- `WIDGET_URI` imported from handlers/resources
- Pydantic models: `SubclusterInput`, `ClusterInput`, `ClusterRequest`
- `ALLOWED_TAGS` list
- `async def handle(user_id, correlation_id, arguments) -> CallToolResult`
  - Validation logic
  - Repair logic
  - Call `cluster_raw_thoughts()` from tools.py (the existing pure function)
  - Call `persist_cluster()` from persistence.py
  - Return CallToolResult with widget _meta
- At module load: `register_tool(ToolDefinition(...))`

### 8. `server.py` (slim down)

After refactor, server.py contains only:
- Imports
- Logger setup
- `mcp = FastMCP(...)` instance
- `MCPContentTypeAndAcceptFixMiddleware` class
- `_cleanup_on_shutdown()` — calls cleanup functions from http_client, mcp_auth
- `create_app()` — middleware, routes, shutdown handler
- `app = create_app()`
- `if __name__ == "__main__"` block

Register handlers by importing:
```python
from mcp_server.clarity.handlers.resources import (
    _list_resources, _list_resource_templates, _handle_read_resource
)
from mcp_server.clarity.handlers.tools import _call_tool_request
from mcp_server.clarity.tools import _list_tools

# Register on mcp._mcp_server
mcp._mcp_server.list_resources()(_list_resources)
# etc.
```

### 9. Move widget HTML

Move `clarity-clusters.html` to `widgets/clarity-clusters.html`

Update path in `handlers/resources.py`:
```python
WIDGET_HTML = Path(__file__).parent.parent.joinpath("widgets/clarity-clusters.html").read_text()
```

## Constraints

- **No behavior change** — all existing functionality must work identically
- **No new dependencies** — use existing imports only
- **Keep tools.py** (the pure function file) — don't confuse with tools/ directory
- Rename existing `tools.py` to `tool_logic.py` if name collision is confusing

## Tests

### Unit Tests

**File:** `tests/unit/mcp/clarity/test_tool_registry.py`
- `test_cluster_raw_thoughts_registered` — tool exists in registry
- `test_registry_returns_none_for_unknown` — get_tool("fake") returns None
- `test_tool_definition_has_required_fields` — name, description, schema, scopes, handle

**File:** `tests/unit/mcp/clarity/test_persistence.py`
- `test_persist_cluster_success` — mock httpx, verify correct payload
- `test_persist_cluster_failure_returns_none` — mock 500 response, returns None
- `test_persist_cluster_exception_returns_none` — mock network error, returns None

### Integration Tests

Existing tests in `tests/integration/clarity/` should pass unchanged. Run full suite to verify no regression.

## Success Criteria

1. ✅ `server.py` < 150 lines
2. ✅ Adding new tool = add one file in `tools/` + import
3. ✅ All existing tests pass
4. ✅ MCP Inspector shows same tools/resources as before
5. ✅ ChatGPT integration works unchanged

## Files to Create

```
NEW:
  mcp_server/clarity/http_client.py
  mcp_server/clarity/persistence.py
  mcp_server/clarity/handlers/__init__.py
  mcp_server/clarity/handlers/resources.py
  mcp_server/clarity/handlers/tools.py
  mcp_server/clarity/tools/__init__.py
  mcp_server/clarity/tools/base.py
  mcp_server/clarity/tools/cluster_raw_thoughts.py
  mcp_server/clarity/widgets/  (directory)
  tests/unit/mcp/clarity/__init__.py
  tests/unit/mcp/clarity/test_tool_registry.py
  tests/unit/mcp/clarity/test_persistence.py

MOVE:
  mcp_server/clarity/clarity-clusters.html → mcp_server/clarity/widgets/clarity-clusters.html

RENAME (optional, if confusing):
  mcp_server/clarity/tools.py → mcp_server/clarity/tool_logic.py

MODIFY:
  mcp_server/clarity/server.py (slim down)
```

## Reference

- Current server.py: `mcp_server/clarity/server.py`
- Focused MCP patterns: `mcp_server/focused/` (if exists)
- FastMCP handler registration: current server.py lines ~280-300