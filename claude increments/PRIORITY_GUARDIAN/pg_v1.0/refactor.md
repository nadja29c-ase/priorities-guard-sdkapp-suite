# PG MCP Server Refactoring — FastMCP Decorators → Canonical Manual Registry

## Objective

Refactor `mcp_server/priority_guardian/` from a single 791-line `server.py` with FastMCP `@mcp.tool()` decorators to the canonical file structure used across all SDK apps. This is a structural refactoring — no behavioral changes, no new features, no new tools.

## Why

FastMCP's `@mcp.tool()` decorator cannot pass `_meta` fields to ChatGPT (specifically `openai/outputTemplate`, `openai/widgetDescription`, `securitySchemes`, `annotations`). PG Increment 03 adds a widget, which requires `_meta`. This refactoring must happen before Inc 03.

## Current State

```
mcp_server/priority_guardian/
├── __init__.py
├── config.py
├── discovery.py
├── mcp_auth.py
└── server.py          ← 791 lines: middleware, HTTP helpers, error decorator,
                         discovery wrappers, 3 tool handlers, app factory, entrypoint
```

Three tools exist: `connect_google_calendar`, `disconnect_google_calendar`, `create_priority`.

All tool handlers live in `server.py`. Each handler calls `authenticate_request()` internally. `backend_get()`/`backend_post()` HTTP helpers are also in `server.py`. A `handle_mcp_errors` decorator wraps each tool.

## Target State

```
mcp_server/priority_guardian/
├── __init__.py
├── config.py                          ← unchanged
├── discovery.py                       ← unchanged
├── mcp_auth.py                        ← modified (auth header source changes)
├── request_context.py                 ← NEW
├── http_client.py                     ← NEW (extracted from server.py)
├── server.py                          ← STRIPPED to infrastructure only
├── handlers/
│   ├── __init__.py
│   └── tools.py                       ← NEW (canonical dispatcher)
└── tools/
    ├── __init__.py                    ← NEW (explicit TOOL_REGISTRY + list_tools)
    ├── base.py                        ← NEW (ToolDefinition + ToolUsageError)
    ├── connect_google_calendar.py     ← NEW
    ├── disconnect_google_calendar.py  ← NEW
    └── create_priority.py             ← NEW
```

## Reference Implementations

Read these files before starting — they are the canonical pattern:

| File | Purpose |
|------|---------|
| `mcp_server/clarity/tools/base.py` | ToolDefinition dataclass, field contract |
| `mcp_server/clarity/tools/__init__.py` | TOOL_REGISTRY, `list_tools()` building `mcp_types.Tool` with `_meta` |
| `mcp_server/clarity/handlers/tools.py` | Canonical dispatcher: auth → lookup → dispatch → error → timing |
| `mcp_server/clarity/server.py` | How to register `call_tool_request` and `list_tools` on `mcp._mcp_server.request_handlers` |
| `mcp_server/clarity/request_context.py` | ContextVar for auth header bridging |

## What To Create

### 1. `request_context.py`

ContextVar for Authorization header. Same pattern as Clarity's `request_context.py`. The middleware captures the Authorization header from HTTP scope and sets it in the ContextVar. The dispatcher (via `mcp_auth.py`) reads from this ContextVar instead of from FastMCP's injected `meta.headers`.

### 2. `http_client.py`

Extract from `server.py`:
- `http_client` global (lazy-init `httpx.AsyncClient`)
- `cleanup_http_client()` async function
- `backend_get(path, user_id, correlation_id)` → dict
- `backend_post(path, json_data, user_id, correlation_id)` → dict

No changes to behavior. Same timeout (30s), same `X-User-ID` and `X-Correlation-ID` headers, same logging.

### 3. `tools/base.py`

`ToolDefinition` dataclass and `ToolUsageError` exception class.

**ToolDefinition required fields:**
- `name: str`
- `description: str`
- `input_schema: dict` (JSON Schema for MCP/ChatGPT discovery)
- `required_scopes: list[str]` (e.g., `["pg.access"]`)
- `widget_uri: str | None` (None for all current PG tools — no widget yet)
- `handle: Callable[[str, str, dict], Awaitable[Any]]` — signature is `(user_id, correlation_id, arguments)`
- `read_only_hint: bool`
- `destructive_hint: bool`
- `open_world_hint: bool`

Optional fields (with defaults):
- `widget_accessible: bool = False`

**ToolUsageError:** intentional rejection (input validation, business rules). Message surfaces to LLM verbatim. Distinct from unexpected Exception.

### 4. `tools/__init__.py`

**Explicit registry pattern (no import side effects, no `register_tool()`):**

```python
from .connect_google_calendar import CONNECT_GOOGLE_CALENDAR
from .disconnect_google_calendar import DISCONNECT_GOOGLE_CALENDAR
from .create_priority import CREATE_PRIORITY

TOOL_REGISTRY = {
    CONNECT_GOOGLE_CALENDAR.name: CONNECT_GOOGLE_CALENDAR,
    DISCONNECT_GOOGLE_CALENDAR.name: DISCONNECT_GOOGLE_CALENDAR,
    CREATE_PRIORITY.name: CREATE_PRIORITY,
}
```

`get_tool(name)` helper: returns `ToolDefinition | None`.

`list_tools()` async function: builds `list[mcp_types.Tool]` from TOOL_REGISTRY. Each tool gets `_meta` with `annotations` (readOnlyHint, destructiveHint, openWorldHint) and `securitySchemes` (oauth2 with scopes, or noauth). Sorted by name for deterministic output. Follow Clarity's `list_tools()` implementation.

### 5. `tools/connect_google_calendar.py`

One file containing:
- `NAME = "connect_google_calendar"`
- `DESCRIPTION` — from `mcp_server/shared/google_tools.py` CONNECT_GOOGLE_CALENDAR_DESCRIPTION
- `INPUT_SCHEMA` — empty object (no arguments). ChatGPT passes no arguments to this tool.
- `REQUIRED_SCOPES = ["pg.access"]`
- `handle(user_id, correlation_id, arguments)` → `CallToolResult`

The handler receives `user_id` and `correlation_id` already extracted by the dispatcher. It does NOT call `authenticate_request`.

**Important:** The current `server.py` implementation does NOT use `shared/google_tools.py` logic — it has its own inline implementation with PG-specific backend paths (`/api/priority-guardian/google/connection-status`, `/api/priority-guardian/google/initiate-connection`). Keep using these PG-specific paths. Do not call `connect_google_calendar_logic` from `shared/google_tools.py` (those hardcode `/api/focused/` paths).

Import `backend_get`/`backend_post` from `http_client.py`.

The handler currently returns `json.dumps(...)` strings. After refactoring, handlers should return `mcp_types.CallToolResult` with `content` (TextContent), `structuredContent`, and `_meta` as appropriate. Currently the Google tools return plain JSON success/error objects — convert these to proper `CallToolResult` objects.

`CONNECT_GOOGLE_CALENDAR = ToolDefinition(...)` constant at bottom of file.

### 6. `tools/disconnect_google_calendar.py`

Same pattern. PG-specific paths: `/api/priority-guardian/google/connection-status`, `/api/priority-guardian/disconnect`.

Has one argument: `confirm: bool`. Extract from `arguments` dict in the handler.

Annotations: `read_only_hint=False`, `destructive_hint=True`, `open_world_hint=True`.

### 7. `tools/create_priority.py`

Contains:
- `NAME = "create_priority"`
- `CREATE_PRIORITY_DESCRIPTION` — the long description with CALL PRECONDITIONS, currently in `server.py`
- `INPUT_SCHEMA` — explicit JSON Schema dict. Currently FastMCP generates this from the function signature. You must write it explicitly. Fields: `name` (string, required), `type` (string enum ["deadline", "flexible"], required), `deadline` (string, optional), `weekly_hour_target` (number, optional), `checkpoint_date` (string, optional), `desired_result` (string, optional).
- `REQUIRED_SCOPES = ["pg.access"]`
- `handle(user_id, correlation_id, arguments)` → `CallToolResult`

The handler extracts arguments from the `arguments` dict. It builds the payload, calls `backend_post`, builds `assistant_guidance` based on `active_priority_count`, and returns `CallToolResult`.

**HTTPStatusError handling:** The current implementation has an inner try/except for `httpx.HTTPStatusError` that builds tool-specific `assistant_guidance` (MAX_PRIORITIES_REACHED, KEYWORD_CONFLICT, VALIDATION_ERROR, etc.). This stays in the handler — it's business logic specific to `create_priority`, not generic dispatch logic.

**Behavioral invariance rule:** For known backend errors (MAX_PRIORITIES_REACHED, KEYWORD_CONFLICT, VALIDATION_ERROR), the handler returns `CallToolResult` directly with full `structuredContent` (including `error.code`, `error.message`, `assistant_guidance`). This preserves the current response structure. Do NOT raise `ToolUsageError` for these — that would change the response format.

`ToolUsageError` is only for simple pre-backend rejections (e.g., missing required argument before any HTTP call is made). Let unexpected HTTPStatusError and connection errors propagate to the dispatcher's generic catch.

Annotations: `read_only_hint=False`, `destructive_hint=False`, `open_world_hint=False`.

### 8. `handlers/tools.py`

Canonical dispatcher. Follow Clarity's `handlers/tools.py` exactly for structure.

**Dispatcher sequence (fixed order):**
1. Extract tool name, arguments, `_meta` from request
2. Generate `correlation_id` (UUID)
3. Look up tool in TOOL_REGISTRY → unknown tool returns `isError=True`
4. Authenticate: call `authenticate_request(name, meta)` from `mcp_auth.py` → extracts `user_id` from validated JWT `sub` claim. Handlers never access tokens or auth context directly.
5. Catch `UnauthorizedError` → return `CallToolResult` with `isError=True` and `_meta` containing `build_unauthorized_error()`
6. Catch `InsufficientScopeError` → return `CallToolResult` with `isError=True` and `_meta` containing `build_forbidden_error()`
7. Call `tool.handle(user_id, correlation_id, arguments)`
8. Catch `ToolUsageError` → return `isError=True` with verbatim message, log at `info` level as `tool.dispatch.rejected`
9. Catch `Exception` → log full stack trace at `exception` level as `tool.dispatch.unexpected_error`, return generic "Something went wrong. Please try again." message
10. Log timing: `tool.timing` with `tool_name`, `correlation_id`, `auth_ms`, `tool_ms`, `total_ms`

**Note on `meta` parameter for `authenticate_request`:** After refactoring, `authenticate_request` will read the auth header from `request_context.auth_header_var` (ContextVar), NOT from `meta.get("headers")`. The `meta` parameter is still passed for `correlation_id` extraction only. See mcp_auth.py modification below.

### 9. Modify `server.py`

**Remove:**
- All tool handler functions (`connect_google_calendar`, `disconnect_google_calendar`, `create_priority`)
- `handle_mcp_errors` decorator
- `backend_get()`, `backend_post()` functions
- `http_client` global and `cleanup_http_client()`
- `CREATE_PRIORITY_DESCRIPTION` string
- `@mcp.tool()` decorators
- Import of `FastMCP` parameter injection types
- Import of `shared/google_tools.py` descriptions

**Keep:**
- `LifespanMiddleware` class (but update cleanup to import from `http_client.py`)
- `MCPContentTypeAndAcceptFixMiddleware` class (but add auth header capture — see below)
- Discovery route wrappers (`wellknown_*` functions)
- `create_app()` factory
- ASGI entrypoint (`app = create_app()`)
- Startup config validation logging

**Add:**
- Import `call_tool_request` from `handlers.tools`
- Import `list_tools` from `tools`
- Import `auth_header_var` from `request_context`
- Register handlers on `mcp._mcp_server`:
  ```python
  @mcp._mcp_server.list_tools()
  async def _list_tools():
      return await list_tools()
  
  mcp._mcp_server.request_handlers[mcp_types.CallToolRequest] = call_tool_request
  ```
- **Auth header capture in middleware:** Modify `MCPContentTypeAndAcceptFixMiddleware.__call__` to extract the `authorization` header from scope headers and set `auth_header_var.set(value)`. Follow Clarity's middleware pattern exactly.

**FastMCP stays** as the transport layer. It still handles `/mcp` endpoint, SSE streaming, JSON-RPC framing. Only tool registration and dispatch are bypassed.

### 10. Modify `mcp_auth.py`

**One change:** `authenticate_request()` currently reads the auth header from `meta.get("headers", {})` via `extract_authorization_header(headers)`. After refactoring, FastMCP no longer injects headers into meta.

Change `authenticate_request` to:
1. Import `auth_header_var` from `request_context`
2. Read auth header from `auth_header_var.get(None)` instead of from `meta.get("headers", {})`
3. Keep `extract_bearer_token()` — it still parses "Bearer <token>"
4. Everything else (JWT validation, scope enforcement, correlation ID extraction) stays unchanged

The `extract_authorization_header()` function becomes unused after this change. Keep it for now (no harm), or remove it.

### 11. `config.py` — No Changes

`TOOL_SCOPES` dict stays. It's currently consumed by `mcp_auth.py`'s `enforce_tool_scope()`. This is technically redundant with `ToolDefinition.required_scopes` but changing the `mcp_auth` API is out of scope for this refactoring. Known tech debt — scopes declared in two places.

## What Gets Deleted

- `handle_mcp_errors` decorator — replaced by dispatcher's error handling
- `@mcp.tool()` decorators — replaced by manual registry
- FastMCP's `meta: Optional[Dict[str, Any]]` parameter injection — dispatcher handles auth, handlers receive `user_id` and `correlation_id` directly
- Inline tool handler code in `server.py`

## Behavioral Invariants (Must Not Change)

- All three tools respond identically to the same inputs (same JSON structure, same error codes, same assistant_guidance strings)
- OAuth discovery endpoints unchanged (same URLs, same responses)
- JWT validation logic unchanged (same JWKS fetching, same scope enforcement)
- Backend API calls unchanged (same paths, same headers, same payloads)
- Middleware behavior unchanged (same Content-Type fix, same Accept fix)
- Startup config validation logging unchanged
- `ENV=dev` azp bypass unchanged

## Compliance Notes

- `[OpenAI]` Compliance requirement #10: "Errors must be well-handled with clear messaging" — the two-category error model (ToolUsageError + Exception) satisfies this
- `[OpenAI]` Compliance requirement #2: `_meta.openai/outputTemplate` — not needed yet (no widget tools), but `list_tools()` must be ready to emit it. Include the `widget_uri` path in `list_tools()` logic even though all current tools have `widget_uri=None`.
- `[Google]` Requirement #19: "Never log tokens" — ensure no auth header or token values appear in any new log statements

---

## Unit Tests

Add to `tests/unit/priority_guardian/`.

### `test_tool_registry.py`
- All 3 tools present in TOOL_REGISTRY: `connect_google_calendar`, `disconnect_google_calendar`, `create_priority`
- No duplicate names
- Every ToolDefinition has all required fields populated
- `required_scopes` matches `TOOL_SCOPES` in config.py for each tool
- `get_tool("nonexistent")` returns None
- `list_tools()` returns 3 `mcp_types.Tool` objects with correct `_meta` (annotations, securitySchemes)

### `test_tool_definitions.py`
- Each tool's `INPUT_SCHEMA` is valid JSON Schema
- `create_priority` schema has `name` and `type` as required fields
- `connect_google_calendar` schema has no required fields
- `disconnect_google_calendar` schema has `confirm` field
- Annotation values match expectations (e.g., disconnect is destructive)

### `test_dispatcher.py`
- Unknown tool name → `isError=True` with "Unknown tool" message
- `ToolUsageError` → `isError=True` with verbatim error message
- Unexpected `Exception` → `isError=True` with generic message (no internal details leaked)
- Auth failure (`UnauthorizedError`) → `isError=True` with `_meta` containing `mcp/www_authenticate`
- Scope failure (`InsufficientScopeError`) → `isError=True` with `_meta` containing `mcp/www_authenticate`
- Timing logged for successful calls

### `test_request_context.py`
- `auth_header_var` default is `None`
- Setting and reading ContextVar works correctly
- Different async contexts get independent values

### `test_http_client.py`
- `backend_get` sends correct headers (`X-User-ID`, `X-Correlation-ID`)
- `backend_post` sends correct headers and JSON body
- `cleanup_http_client` closes the client

---

## Integration Tests

Add to `tests/integration/priority_guardian/`.

### `test_mcp_server_startup.py`
- App factory creates ASGI app without errors
- Discovery endpoints respond at `/.well-known/oauth-protected-resource`
- `/mcp` endpoint accepts POST (SSE handshake)

### `test_tool_roundtrip.py`
- Simulate `CallToolRequest` for each tool through the full dispatcher
- Mock `authenticate_request` to return a test `user_id`
- Mock `backend_post`/`backend_get` to return expected backend responses
- Verify `CallToolResult` structure matches current behavior
- Verify `create_priority` returns `structuredContent` with `assistant_guidance`
- Verify `connect_google_calendar` returns connect_url when not connected
- Verify `disconnect_google_calendar` requires confirmation

### `test_auth_header_flow.py`
- Simulate middleware receiving Authorization header in HTTP scope
- Verify `auth_header_var` is set correctly
- Verify `mcp_auth.authenticate_request` reads from ContextVar
- Verify auth failure when no Authorization header present