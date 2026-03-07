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

---

## OAuth Discovery Configuration

This section governs OAuth discovery endpoint configuration for authenticated MCP servers. Non-compliance causes ChatGPT connector creation to fail silently.

### Two Distinct Config Values

| Config Variable | Purpose | Example Value |
|-----------------|---------|---------------|
| `OAUTH_ISSUER_BASE` | Authorization server identifier. Used for `issuer` claim in discovery and `authorization_servers` in protected resource metadata. | `https://www.priority-guard.com` |
| `OAUTH_ISSUER_URL` | Endpoint path prefix. Used to construct `authorization_endpoint`, `token_endpoint`, `jwks_uri`, `registration_endpoint`. | `https://www.priority-guard.com/oauth/pg` |

**Why they must be separate:**
- `issuer` in OAuth/OIDC discovery must be the root domain of the authorization server, not a path prefix
- ChatGPT fetches `{authorization_servers[0]}/.well-known/oauth-authorization-server` — if `authorization_servers` contains a path, this fetch fails
- Endpoint URLs legitimately include path prefixes (e.g., `/oauth/pg/authorize`)

**Never derive one from the other.** Parsing a URL to strip paths is fragile and fails silently when paths change. Define both explicitly via separate environment variables.

### Invariants

1. **`issuer` must equal the root domain** — In all discovery documents (`oauth-authorization-server`, `openid-configuration`), the `issuer` field must be the authorization server's root domain (e.g., `https://www.priority-guard.com`), not an endpoint path prefix (e.g., `https://www.priority-guard.com/oauth/pg`).

2. **`authorization_servers` must match `issuer`** — In `oauth-protected-resource`, the `authorization_servers` array must contain the same value as `issuer`. ChatGPT uses this to fetch `{authorization_servers[0]}/.well-known/oauth-authorization-server`.

3. **MCP `OAUTH_ISSUER_BASE` must equal backend `OAUTH_ISSUER`** — These are separate environment variables on separate services (MCP server vs backend). They must always contain the same value. Divergence breaks JWT validation: the backend signs tokens with `iss` = `OAUTH_ISSUER`, and the MCP server validates against `OAUTH_ISSUER_BASE`.

### Environment Variable Sync Table

| MCP Server Env Var | Backend Env Var | Must Match? |
|--------------------|-----------------|-------------|
| `PG_OAUTH_ISSUER_BASE` | `OAUTH_ISSUER` | **Yes — exactly** |
| `PG_ISSUER` (JWT validation) | `OAUTH_ISSUER` | **Yes — exactly** |
| `PG_AUDIENCE` (JWT validation) | `OAUTH_ISSUER` | **Yes — exactly** |

### Production Bug Reference

Increment 41 (March 2026): MCP discovery returned `issuer: "https://www.priority-guard.com/oauth/pg"` instead of `issuer: "https://www.priority-guard.com"`. ChatGPT connector creation failed silently. Root cause: single config variable used for both issuer identifier and endpoint prefix. Fix: separate `OAUTH_ISSUER_BASE` and `OAUTH_ISSUER_URL` with explicit env vars.

---

### Authorization Server / Resource Server Separation

**The MCP server is a Resource Server. It is not an Authorization Server.**

In the Priority Guard Suite, these roles are assigned to separate domains:

| Role | Domain | Responsibility |
|------|--------|----------------|
| Authorization Server (AS) | `www.priority-guard.com` | Issues tokens, hosts OAuth endpoints, signs JWTs |
| Resource Server / MCP Server (RS) | `pg.priority-guard.com` | Validates tokens, exposes MCP tools, serves widget |

This separation is valid per OAuth 2.1 and the MCP authorization spec. The AS and RS may live on different origins. However, the discovery documents must reflect this separation cleanly — never mix origins within a single document.

#### The Hybrid Document Anti-Pattern

**Never do this.** This is what caused the Increment 46 production failure:

```json
{
  "issuer": "https://www.priority-guard.com",
  "token_endpoint": "https://pg.priority-guard.com/oauth/token",
  "jwks_uri": "https://pg.priority-guard.com/oauth/jwks"
}
```

`issuer` is on `www`, endpoints are on `pg`. This document is served from `pg`. ChatGPT completed the full OAuth flow (DCR → authorize → token) but silently aborted before calling `/mcp`. The root cause: RFC 8414 requires that the AS metadata document served at `{origin}/.well-known/oauth-authorization-server` is internally consistent — all endpoints must belong to the same AS that the `issuer` identifies.

**Symptom signature of this failure:**
- DCR succeeds
- Authorize + consent succeeds
- Token issued successfully
- No `GET /oauth/jwks` in MCP logs
- No `POST /mcp` in MCP logs
- Silent abort after token exchange — no error logged anywhere

This is indistinguishable from a JWKS or audience failure from log inspection alone. The distinguishing factor is: if token claims are correct and JWKS is valid JSON, suspect AS metadata consistency.

#### Correct Pattern: Two Clean Documents

The MCP server (`pg`) serves TWO distinct documents:

**1. Protected Resource Metadata (`/.well-known/oauth-protected-resource`) — served by pg**

This is the RS document. It tells ChatGPT where the real AS lives:

```json
{
  "resource": "https://pg.priority-guard.com/mcp",
  "authorization_servers": ["https://www.priority-guard.com"],
  "scopes_supported": ["pg.access"]
}
```

`authorization_servers` must point to `www` (the real AS). ChatGPT fetches `{authorization_servers[0]}/.well-known/oauth-authorization-server` to discover OAuth endpoints.

**2. AS Metadata (`/.well-known/oauth-authorization-server` and `/.well-known/openid-configuration`) — mirrored on pg**

ChatGPT may also fetch these directly from `pg` based on the MCP server origin. These documents must be **identical to what `www` serves** — fully consistent, all endpoints pointing to `www`:

```json
{
  "issuer": "https://www.priority-guard.com",
  "authorization_endpoint": "https://www.priority-guard.com/oauth/pg/authorize",
  "token_endpoint": "https://www.priority-guard.com/oauth/pg/token",
  "jwks_uri": "https://www.priority-guard.com/oauth/pg/jwks",
  "registration_endpoint": "https://www.priority-guard.com/oauth/pg/register"
}
```

No `pg` endpoints appear in this document. The MCP server is a transparent mirror of the AS metadata, not a proxy or hybrid.

#### Implementation Rule for `discovery.py`

All three functions in `discovery.py` follow a single rule:

- `oauth_protected_resource()`: use `OAUTH_ISSUER_BASE` for `authorization_servers`
- `openid_configuration()`: use `OAUTH_ISSUER_BASE` for `issuer` and all endpoint base URLs
- `oauth_authorization_server()`: identical to `openid_configuration()`

`MCP_SERVER_URL` must **not** appear in any endpoint URL in `discovery.py`. It belongs in `server.py` for route wiring and in `mcp_auth.py` for token audience validation — not in discovery.

#### Verification Checklist — After Any Discovery Change

- [ ] `GET pg/.well-known/oauth-authorization-server` → all endpoints on `www`, `issuer=www`
- [ ] `GET pg/.well-known/openid-configuration` → all endpoints on `www`, `issuer=www`
- [ ] `GET pg/.well-known/oauth-protected-resource` → `authorization_servers: ["https://www.priority-guard.com"]`
- [ ] `GET www/.well-known/oauth-authorization-server` → consistent with pg mirror
- [ ] Trigger fresh ChatGPT auth flow → `POST /mcp` appears in MCP server logs

---

### Multi-App OAuth: One Shared AS, Multiple MCP Servers

The shared backend AS on `www.priority-guard.com` is designed to serve multiple SDK apps simultaneously. Each app gets its own route prefix on the backend and its own MCP server domain. The AS itself is untouched when adding a new app.

#### How It Works

Each SDK app has:
1. Its own MCP server domain (e.g. `pg.priority-guard.com`, `unpack.priority-guard.com`)
2. Its own backend route prefix (e.g. `/oauth/pg/*`, `/oauth/unpack/*`)
3. Its own `discovery.py` with `oauth_protected_resource` pointing `authorization_servers` to `www`
4. Its own scopes declared in the backend `SCOPES_SUPPORTED` list

The shared AS on `www` handles all DCR, authorize, and token requests. Each app's MCP server is purely a resource server — it validates tokens but does not issue them.

#### Current Route Map

| App | Backend Route Prefix | MCP Server Domain | Default Scopes |
|-----|---------------------|-------------------|----------------|
| Priority Guardian | `/oauth/pg/*` | `pg.priority-guard.com` | `pg.access` |
| Focused | `/oauth/focused/*` | (deprecated) | `focused.read`, `focused.write`, `focused.notify` |

Each route prefix has independent:
- `POST /oauth/{app}/register` — DCR, assigns default scopes for that app
- `GET /oauth/{app}/authorize` — consent screen (app-specific template)
- `POST /oauth/{app}/token` — token issuance
- `GET /oauth/{app}/jwks` — JWKS (shared signing key, per-app path)

#### Adding a New App: What Changes

**Backend (`www`):**
- Add new scopes to `SCOPES_SUPPORTED` in `discovery.py`
- Add `DEFAULT_SCOPES_{APP}` and route detection in `register_client.py`
- Add `@router.post("/oauth/{app}/register")` etc. across token, authorize, jwks endpoints
- Add consent screen template (HTML, EN + DE)
- Add scope descriptions to `SCOPE_DESCRIPTIONS_EN` and `SCOPE_DESCRIPTIONS_DE` in `authorize.py`

**New MCP server:**
- New service on its own domain (e.g. `unpack.priority-guard.com`)
- `discovery.py`: `authorization_servers: [OAUTH_ISSUER_BASE]`, all AS endpoints pointing to `www`
- `config.py`: `PG_OAUTH_ISSUER_BASE` = `https://www.priority-guard.com` (same value, different env var name per service)
- Token validation: `issuer=www`, `audience=<new MCP resource URL>`

**What does NOT change:**
- Backend `OAUTH_ISSUER` env var — stays `https://www.priority-guard.com`
- JWT signing key — shared across all apps (same `kid`)
- Any existing app's routes or config

#### Invariant: Never Change `OAUTH_ISSUER` for a Single App

`OAUTH_ISSUER` is a global backend setting. Changing it to accommodate one app breaks token validation for all other apps. Each new app gets a new route prefix — the issuer stays fixed.

#### Client Namespace Isolation

DCR creates clients per app route. A client registered at `/oauth/pg/register` gets `client_id` prefixed `pg-client-*` and default scopes `pg.access`. A client registered at `/oauth/focused/register` gets `focused.client-*` scopes. Client IDs do not cross app boundaries.

---

#### Production Bug Reference

Increment 46 (March 2026): ChatGPT completed full OAuth flow but never called `/mcp`. All prior hypotheses (JWKS compression, issuer mismatch in JWT, Redis replay, audience claim) were ruled out over ~10 increments. Root cause: `pg/.well-known/oauth-authorization-server` and `pg/.well-known/openid-configuration` served hybrid documents (`issuer=www`, endpoints=`pg`). Fix: all three discovery functions in `discovery.py` made fully consistent with `www`. `authorization_servers` in protected resource metadata changed from `[MCP_SERVER_URL]` to `[OAUTH_ISSUER_BASE]`. The proxy OAuth routes on `pg` (`/oauth/token`, `/oauth/jwks`, `/oauth/register`) became unused by ChatGPT but were left in place.