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

Each app defines ToolUsageError in its own tools/base.py alongside ToolDefinition. Same class, same name, same behavior, independent copies. No shared error module across apps
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

MUST NOT:

Put tool handlers in server.py
Put auth logic in tool files
Put HTTP client helpers in server.py
Split a single tool's logic across multiple files unless shared with other tools
Import from one tool file into another tool file