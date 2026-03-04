MCP Server Implementation Standardization

Feb 26
all SDK apps use manual registry with ToolDefinition + TOOL_REGISTRY + dispatcher
Feb 26
BUT each app has its own dispatcher that follows the same pattern same handler signature, same error categories, same logging structure.

These six points are the pattern contract: ​​ MCP Server Implementation Standard


Canonical Dispatcher Pattern — All SDK Apps
Each SDK app has its own dispatcher. No shared dispatcher across apps. All dispatchers follow these rules.

1. Handler signature
async def handle(user_id: str, correlation_id: str, arguments: dict) -> CallToolResult
For noauth apps, user_id is empty string. Never change the signature — any tool can move between apps without rewriting the interface.
2. Error categories
Two categories, no more:
ToolUsageError — intentional rejection. Input validation, business rule violation, guardrail. Message surfaces to the LLM verbatim. Logged at info level.
Unhandled Exception — unexpected crash. Full stack trace logged at exception level. Generic message returned to LLM ("Something went wrong. Please try again."). Never expose internals.
3. Dispatcher sequence
Every dispatcher follows this sequence in this order:
Extract tool name and arguments from request
Generate correlation_id
Look up tool in TOOL_REGISTRY → unknown tool returns isError=True
Authenticate (if required_scopes is non-empty) → auth failure returns MCP-compliant 401/403. For authenticated apps, the dispatcher extracts user_id from the validated JWT sub claim. Handlers never access tokens or auth context directly.
Call tool.handle(user_id, correlation_id, arguments)
Catch ToolUsageError → return isError=True with verbatim message
Catch Exception → log full trace, return generic error
Log timing (tool_ms, total_ms)
Return CallToolResult
4. Logging structure
These exact structured log event names, every dispatcher:
tool.dispatch.received — tool_name, correlation_id, argument_keys
tool.dispatch.rejected — tool_name, correlation_id, reason (for ToolUsageError)
tool.dispatch.unexpected_error — tool_name, correlation_id (with .exception() for stack trace)
tool.timing — tool_name, correlation_id, tool_ms, total_ms
5. ToolDefinition fields
Every ToolDefinition dataclass must include at minimum:
name: str
description: str
input_schema: dict
required_scopes: list[str] (empty list for noauth)
widget_uri: str | None
handle: Callable[[str, str, dict], Awaitable[Any]]
read_only_hint: bool
destructive_hint: bool
open_world_hint: bool
Additional fields (like widget_accessible) are app-specific and optional.

Each app defines ToolUsageError in its own tools/base.py alongside ToolDefinition. Same class, same name, same behavior, independent copies. No shared error module across apps.

**INPUT_SCHEMA requirements — every tool without exception:**

Every `INPUT_SCHEMA` dict must conform to these rules:

1. Top-level object must have `"additionalProperties": False`
2. Every nested `"type": "object"` node at any depth (inside `items`, `oneOf`, `anyOf`, or any other nesting) must also have `"additionalProperties": False`
3. Empty schemas are not exempt. An empty schema must look exactly like this:
```python
INPUT_SCHEMA = {
    "type": "object",
    "properties": {},
    "required": [],
    "additionalProperties": False,
}
```

Forbidden — the following are never permitted:
```python
# Missing additionalProperties entirely
INPUT_SCHEMA = {"type": "object", "properties": {...}}

# Nested object without additionalProperties
"items": {"type": "object", "properties": {...}}
```

Rationale: `additionalProperties: false` is present in every official OpenAI Apps SDK example including empty schemas. Omitting it means the schema accepts arbitrary undeclared keys, which conflicts with data minimization requirements (D1/D2 of the compliance checklist) and signals poor schema hygiene to reviewers.

Enforcement: A schema validation unit test must be present in every SDK app's test suite that programmatically walks all registered schemas and asserts this invariant. The test must also assert that no unregistered tool modules exist under `tools/` and `tools/widget_tools/` — to ensure the registry test has complete coverage.
6. Registration pattern — explicit registry
Each tool is defined in its own module as a ToolDefinition constant. tools/__init__.py imports each constant and builds the registry as an explicit dict:
python
from .create_priority import CREATE_PRIORITY
from .retire_priority import RETIRE_PRIORITY

TOOL_REGISTRY = {
    CREATE_PRIORITY.name: CREATE_PRIORITY,
    RETIRE_PRIORITY.name: RETIRE_PRIORITY,
}
No register_tool() calls. No import side effects. The registry is a single inspectable, testable data structure.

MUST NOT
Auto-register tools via import side effects
Share a dispatcher across apps
Leak auth logic into tool handlers
Vary the handler signature between apps
Surface internal error details to the LLM
Vary log event names between apps

Canonical MCP Server File Structure — All SDK Apps
mcp_server/<app_name>/
├── server.py          # App factory, middleware, ASGI entrypoint. No tools, no business logic.
├── config.py          # Environment variables, constants
├── discovery.py       # OAuth discovery endpoint builders
├── mcp_auth.py        # JWT validation, scope enforcement, error builders
├── http_client.py     # Backend HTTP helpers (backend_get, backend_post) — only for authenticated apps with backends
├── handlers/
│   └── tools.py       # Dispatcher. Auth → lookup → dispatch → error handling → timing.
└── tools/
    ├── __init__.py    # Explicit TOOL_REGISTRY dict, list_tools() builder
    ├── base.py        # ToolDefinition dataclass, ToolUsageError
    ├── <tool_a>.py    # One file: metadata + validation + handler + helpers
    └── <tool_b>.py    # One file: metadata + validation + handler + helpers
Rules:

server.py contains only infrastructure: middleware, discovery route wiring, app factory, entrypoint. Zero tool logic.
Each tool gets one file. That file contains everything about that tool: NAME, DESCRIPTION, INPUT_SCHEMA, Pydantic models (if any), helper functions, and the handle() function. One file, one tool, fully self-contained.
Business logic stays in the tool file unless it's shared across multiple tools — then extract to a utility module (like Clarity's board_utils.py).
http_client.py owns backend_get/backend_post for apps that forward to the backend. Tools import from it. It's not in server.py.
Module cleanup contract: Modules that own stateful resources (HTTP clients, caches, connection pools) must expose a public `async def cleanup_*()` function; `server.py` calls these on shutdown — it never imports or accesses private instances directly.
handlers/tools.py is the dispatcher. It imports from mcp_auth for auth, from tools for the registry. Nothing else imports from the dispatcher.

**Required vs Optional Files by Auth Model:**

| File | Authenticated App | Noauth App |
|------|-------------------|------------|
| `server.py` | ✓ | ✓ |
| `config.py` | ✓ | ✓ |
| `discovery.py` | ✓ | ✗ |
| `mcp_auth.py` | ✓ | ✗ |
| `http_client.py` | ✓ (if backend) | ✓ (if backend) |
| `handlers/tools.py` | ✓ | ✓ |
| `tools/` | ✓ | ✓ |

Noauth apps without backends (e.g., Sharpen) only need server.py, config.py, handlers/tools.py, and tools/.

**Backend call timeout contract — all apps with http_client.py:**

Every `backend_get` and `backend_post` call in every tool handler must be wrapped with `asyncio.wait_for` at a timeout of ≤ 8 seconds. This is non-negotiable regardless of the tool's perceived complexity or typical response time.

Rules:

1. Define `TIMEOUT_S = 8.0` at module level in each tool file that makes backend calls. Use this constant in all `asyncio.wait_for` calls in that file. Do not inline magic numbers.
2. `TIMEOUT_S` is per-file. Do not share it across tool files or across apps.
3. On `asyncio.TimeoutError`, always `raise ToolUsageError(...)`. The dispatcher converts this to `isError=True`. Never return a timeout exception as a value.
4. Tools with multiple backend calls should define a small file-local async helper to avoid copy-paste bugs. Do not create a shared helper across tool files.
5. Silent exception branches (where a timeout should not abort the tool) must explicitly catch `(asyncio.TimeoutError, Exception)` — not `asyncio.TimeoutError` alone — to preserve existing behavior.
6. Do not define timeout constants that are not passed to any call. A constant that exists but is unused is worse than no constant: it implies correctness that isn't there.

Forbidden — the following is never permitted:
```python
# Constant defined but not used
TIMEOUT_S = 8.0
await backend_get(endpoint, user_id, correlation_id)  # no wait_for
```

Rationale: The ChatGPT MCP execution window is approximately 10 seconds. The `httpx.AsyncClient` default timeout is 30 seconds. Any tool without explicit `asyncio.wait_for` wrapping will silently run against the 30-second HTTP client default, triple the MCP window. Reviewers interpret tool hangs and flakiness as app instability, which causes rejection. `get_priorities` is the reference implementation — all other tools must follow the same pattern.

Enforcement: Every SDK app test suite must include a static check that scans all tool files under `tools/` and `tools/widget_tools/` and fails if `backend_get(` or `backend_post(` appears without `asyncio.wait_for` wrapping in the same file. This catches bare backend calls before they reach production.

MUST NOT:

Put tool handlers in server.py
Put auth logic in tool files
Put HTTP client helpers in server.py
Split a single tool's logic across multiple files unless shared with other tools
Import from one tool file into another tool file

---

## Operational Invariants

These invariants apply to every tool handler in every SDK app. Deviation is an architectural violation, not a style issue.

1. Every backend call uses `asyncio.wait_for(timeout=TIMEOUT_S)` where `TIMEOUT_S ≤ 8.0`
2. `ToolUsageError` is raised for all intentional tool failures — never returned as a value
3. Raw exceptions are never returned as values — they always propagate to the dispatcher
4. Silent exception branches preserve their exact exception scope — narrowing `except (asyncio.TimeoutError, Exception)` to `except asyncio.TimeoutError` is a behavioral change, not a refactor
5. Dead configuration does not exist — every defined constant is referenced by executable code or removed

---

## Reference Implementations

When implementing a new tool, follow the closest matching reference. Do not copy from tools that predate this standard.

| Pattern | Reference Tool |
|---|---|
| Backend timeout wrapping with parallel calls | `get_priorities` |
| Complex nested schema with `additionalProperties` at all depths | `inspect_adapt` |
| Simple tool with straightforward schema and single backend call | `create_priority` |

If your tool's structure matches none of these, flag it for review before implementing.

---

## Tool Implementation Checklist

Before merging any new tool or modifying an existing one, verify all of the following:

**Schema**
- [ ] `INPUT_SCHEMA` top-level has `"additionalProperties": False`
- [ ] Every nested `"type": "object"` at any depth also has `"additionalProperties": False`
- [ ] No permissive bare `{"type": "object"}` anywhere in the schema tree
- [ ] Tool is registered in `TOOL_REGISTRY` in `tools/__init__.py`

**Backend calls (authenticated apps only)**
- [ ] Every `backend_get` / `backend_post` call is wrapped with `asyncio.wait_for`
- [ ] `TIMEOUT_S = 8.0` is defined at module level and actually used
- [ ] No timeout constants defined but not passed to any call
- [ ] `asyncio.TimeoutError` raises `ToolUsageError`, never returned as a value
- [ ] Silent exception branches catch `(asyncio.TimeoutError, Exception)`, not `asyncio.TimeoutError` alone

**Handler contract**
- [ ] Signature is `async def handle(user_id: str, correlation_id: str, arguments: dict) -> CallToolResult`
- [ ] No auth logic inside the handler
- [ ] No internal error details surfaced to the LLM
- [ ] `ToolUsageError` used for intentional rejections; unhandled exceptions fall through to dispatcher