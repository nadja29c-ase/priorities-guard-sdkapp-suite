# Increment Claude-01: `priority_guardian_claude` — Folder Scaffold

**Goal:** Create the `priority_guardian_claude` MCP server module as a deployable empty service. Zero tool logic. Zero widget code. Server starts, binds port, passes health check.

---

## Context

Priority Guardian is being extended to the Anthropic MCP Directory as a second distribution channel alongside the existing OpenAI ChatGPT SDK app. The two platforms require separate MCP server processes (different `PG_MCP_SERVER_URL`, different OAuth callback URLs, different CORS origins) but share the same backend API, same PostgreSQL database, and same tool logic.

**Rule: duplicate logic only when forced to by config coupling. Annotate every duplicate file so the future refactor is obvious.**

The existing `mcp_server/priority_guardian/` module is the ChatGPT MCP server — it must not be touched in this increment. This increment creates `mcp_server/priority_guardian_claude/` as a parallel module in the same repo.

Reference architecture: `doc/Claude_Compliance/structural_guideline_claude_vs_openai.md`
Dispatcher pattern: `doc/ADR_MCP Server Implementation Standard.md`

---

## Pre-Implementation

Read `doc/OPERATIONS_PREDEPLOY.md` before starting. No migrations in this increment.

---

## Implementation Approach — Copy and Adjust, Never Rewrite

Every file in this increment has an existing counterpart in `mcp_server/priority_guardian/`. Claude Code must:

1. **Copy the source file verbatim** as the starting point
2. **Make only the specific adjustments listed** in this briefing
3. **Not rewrite, restructure, simplify, or improve** anything not explicitly listed

The existing implementation is production-tested. Deviations introduce inconsistency across MCP servers. If something in the source file looks wrong or suboptimal, flag it — do not silently fix it.

Files and their exact source to copy from:

| New file | Copy from |
|---|---|
| `server_dupl.py` | `mcp_server/priority_guardian/server.py` |
| `discovery_dupl.py` | `mcp_server/priority_guardian/discovery.py` |
| `config.py` | `mcp_server/priority_guardian/config.py` |

`mcp_auth_dupl.py` and `http_client_dupl.py` are thin wrappers — see their sections for the exact pattern. Do not copy the full source; write only what is described.

---

## Duplication Policy

Only files that have a **hard import dependency on platform-specific config** exist in `priority_guardian_claude/`. Everything else is imported directly from `priority_guardian`.

| File | Location | Reason |
|---|---|---|
| `config.py` | `priority_guardian_claude/` — new | Different env vars, different URLs |
| `server_dupl.py` | `priority_guardian_claude/` — (duplicate) | Platform entry point, imports own config |
| `discovery_dupl.py` | `priority_guardian_claude/` — (duplicate) | Imports own config for URLs |
| `mcp_auth_dupl.py` | `priority_guardian_claude/` — (duplicate) thin wrapper | Re-exports logic from `priority_guardian.mcp_auth`, rebinds own config |
| `http_client_dupl.py` | `priority_guardian_claude/` — (duplicate) thin wrapper | Re-exports logic from `priority_guardian.http_client`, rebinds own config |
| `handlers/tools_dupl.py` | `priority_guardian_claude/` — (duplicate) thin wrapper | Must import own `mcp_auth` for correct `_MCP_ORIGIN` in error responses |
| `request_context.py` | **not created** — import from `priority_guardian` | Zero config deps, pure `ContextVar` |
| `tools/` | **not created** — import from `priority_guardian.tools` | All tool logic is config-free |
| `widget-react/` | **not created** — future increment | Claude widget (MCP Apps bridge) |

Every `(duplicate)` file must carry this header comment:

```python
# (duplicate) — exists only because it imports platform-specific config.
# Logic lives in mcp_server/priority_guardian/<same_filename>.
# Post-OpenAI-approval refactor: move shared logic to mcp_server/shared/
# with config injection and delete this file.
```

---

## Folder Structure to Create

```
mcp_server/priority_guardian_claude/
├── __init__.py
├── config.py                    # new — all PG_CLAUDE_* env vars
├── server_dupl.py               # (duplicate) platform entry point
├── discovery_dupl.py            # (duplicate) OAuth discovery URLs
├── mcp_auth_dupl.py             # (duplicate) thin wrapper
├── http_client_dupl.py          # (duplicate) thin wrapper
├── handlers/
│   ├── __init__.py
│   └── tools_dupl.py            # (duplicate) thin wrapper — empty registry
└── widgets/
    └── .gitkeep
```

---

## Implementation

### `__init__.py` and `handlers/__init__.py`

Empty. Module markers only.

---

### `config.py` — new (not duplicate)

**Source to copy:** `mcp_server/priority_guardian/config.py` — copy verbatim, then make the following adjustments only:

- Rename all env var keys from `PG_*` to `PG_CLAUDE_*` (see table below)
- Update all default values to use port `8004` for `MCP_SERVER_URL`
- Update the module docstring to reference `priority_guardian_claude`
- **No duplicate header comment** — this file is genuinely new content, not a copy

All logic stays identical: same `get_env()` helper, same `ENV` detection, same fail-fast guards, same same-origin validation, same localhost warning.

**Env var mapping:**

| Config value | Env var | Dev default |
|---|---|---|
| `MCP_SERVER_URL` | `PG_CLAUDE_MCP_SERVER_URL` | `http://localhost:8004` |
| `MCP_RESOURCE_URL` | `PG_CLAUDE_MCP_RESOURCE_URL` | `{MCP_SERVER_URL}/mcp` |
| `OAUTH_ISSUER_URL` | `PG_CLAUDE_OAUTH_ISSUER_URL` | `http://localhost:8000/oauth/pg` |
| `OAUTH_ISSUER_BASE` | `PG_CLAUDE_OAUTH_ISSUER_BASE` | `http://localhost:8000` |
| `BACKEND_URL` | `PG_CLAUDE_BACKEND_URL` | `http://localhost:8000` |
| `INTERNAL_API_SECRET` | `PG_CLAUDE_INTERNAL_API_SECRET` | `""` |
| `PG_JWKS_URL` | `PG_CLAUDE_JWKS_URL` | `http://localhost:8000/oauth/pg/jwks` |
| `PG_ISSUER` | `PG_CLAUDE_ISSUER` | `https://www.priority-guard.com` |
| `PG_AUDIENCE` | `PG_CLAUDE_AUDIENCE` | `https://www.priority-guard.com` |
| `CORS_ALLOWED_ORIGINS` | `PG_CLAUDE_CORS_ALLOWED_ORIGINS` | `""` |
| `SCOPES_SUPPORTED` | hardcoded | `["pg.access"]` |

All other config values (`TOKEN_EXPIRY_GRACE_SECONDS`, `JWKS_CACHE_TTL_SECONDS`, etc.) keep the same defaults — no separate env vars needed for these.

Add a comment block at the top of `config.py` listing all required Render env vars. This is the self-documenting spec for the future Render service setup.

---

### `discovery_dupl.py` — (duplicate)

**Source to copy:** `mcp_server/priority_guardian/discovery.py` — copy verbatim, then make the following adjustments only:

- Change the import at the top from `mcp_server.priority_guardian.config` to `mcp_server.priority_guardian_claude.config`
- Add the duplicate header comment

No logic changes.

---

### `mcp_auth_dupl.py` — (duplicate) thin wrapper

**Do not copy the source file.** Write only the wrapper described below.

**Invariant:** This file must not trigger any network call during import or module initialization. JWKS fetching happens only on first authenticated tool call. Importing `priority_guardian_claude.mcp_auth_dupl` with no backend running must not raise.

The config-dependent values in `priority_guardian.mcp_auth` that need rebinding:
- `PG_JWKS_URL` — used in `JWKSCache.fetch_jwks()`
- `PG_ISSUER`, `PG_AUDIENCE`, `MCP_RESOURCE_URL`, `MCP_SERVER_URL` — used in `validate_jwt()` and `build_unauthorized_meta()` / `build_forbidden_meta()`
- `_MCP_ORIGIN` — derived from `MCP_SERVER_URL`, used in WWW-Authenticate headers

The scope enforcement in `authenticate_request()` calls `from mcp_server.priority_guardian.tools import get_tool` — shared, no change needed. `request_context.auth_header_var` is also shared, no change needed.

```python
# (duplicate) — exists only because it imports platform-specific config.
# Logic lives in mcp_server/priority_guardian/mcp_auth.py.
# Post-OpenAI-approval refactor: move shared logic to mcp_server/shared/
# with config injection and delete this file.

import mcp_server.priority_guardian.mcp_auth as _shared

from mcp_server.priority_guardian_claude.config import (
    PG_JWKS_URL,
    PG_ISSUER,
    PG_AUDIENCE,
    MCP_SERVER_URL,
    MCP_RESOURCE_URL,
    JWKS_CACHE_TTL_SECONDS,
    JWKS_MAX_STALE_SECONDS,
    JWKS_FETCH_TIMEOUT_SECONDS,
    TOKEN_EXPIRY_GRACE_SECONDS,
)

# Rebind config-dependent module globals to Claude platform values
_shared.PG_JWKS_URL = PG_JWKS_URL
_shared.PG_ISSUER = PG_ISSUER
_shared.PG_AUDIENCE = PG_AUDIENCE
_shared.MCP_SERVER_URL = MCP_SERVER_URL
_shared.MCP_RESOURCE_URL = MCP_RESOURCE_URL
_shared._MCP_ORIGIN = _shared._extract_origin(MCP_SERVER_URL)
_shared.JWKS_CACHE_TTL_SECONDS = JWKS_CACHE_TTL_SECONDS
_shared.JWKS_MAX_STALE_SECONDS = JWKS_MAX_STALE_SECONDS
_shared.JWKS_FETCH_TIMEOUT_SECONDS = JWKS_FETCH_TIMEOUT_SECONDS
_shared.TOKEN_EXPIRY_GRACE_SECONDS = TOKEN_EXPIRY_GRACE_SECONDS

# Re-export everything callers need
from mcp_server.priority_guardian.mcp_auth import (  # noqa: E402, F401
    authenticate_request,
    cleanup_jwks_cache,
    build_unauthorized_meta,
    build_forbidden_meta,
    UnauthorizedError,
    InsufficientScopeError,
    JWKSCache,
)
```

**Note:** The monkeypatching approach patches a shared module instance. In production each platform runs as a separate Render service (separate process), so there is no conflict. Unit test 6 (`test_config_isolation`) validates the rebinding works correctly. If that test fails, the alternative is to instantiate a fresh `JWKSCache` with Claude config and assign it to `_shared._jwks_cache` — either approach is acceptable.

---

### `http_client_dupl.py` — (duplicate) thin wrapper

**Do not copy the source file.** Write only the wrapper described below.

Config-dependent values to rebind: `BACKEND_URL` and `INTERNAL_API_SECRET`.

```python
# (duplicate) — exists only because it imports platform-specific config.
# Logic lives in mcp_server/priority_guardian/http_client.py.
# Post-OpenAI-approval refactor: move shared logic to mcp_server/shared/
# with config injection and delete this file.

import mcp_server.priority_guardian.http_client as _shared

from mcp_server.priority_guardian_claude.config import (
    BACKEND_URL,
    INTERNAL_API_SECRET,
)

# Rebind config-dependent module globals to Claude platform values
_shared.BACKEND_URL = BACKEND_URL
_shared.INTERNAL_API_SECRET = INTERNAL_API_SECRET

# Re-export everything callers need
from mcp_server.priority_guardian.http_client import (  # noqa: E402, F401
    backend_get,
    backend_post,
    backend_put,
    backend_delete,
    cleanup_http_client,
)
```

---

### `handlers/tools_dupl.py` — (duplicate) thin wrapper, empty registry

**Do not copy the source file.** Write only the stub described below. Full dispatcher logic is added in the next increment when tools are wired.

```python
# (duplicate) — exists only because it imports platform-specific mcp_auth.
# Dispatcher logic mirrors mcp_server/priority_guardian/handlers/tools.py.
# Post-OpenAI-approval refactor: move shared logic to mcp_server/shared/
# with config injection and delete this file.

from mcp import types as mcp_types

# Import platform-specific mcp_auth so error responses use Claude's _MCP_ORIGIN
from mcp_server.priority_guardian_claude.mcp_auth_dupl import (  # noqa: F401
    authenticate_request,
    UnauthorizedError,
    InsufficientScopeError,
    build_unauthorized_meta,
    build_forbidden_meta,
)

# Empty registry — tools wired in next increment
# from mcp_server.priority_guardian.tools import get_tool


async def call_tool_request(req: mcp_types.CallToolRequest) -> mcp_types.CallToolResult:
    """Stub dispatcher — no tools registered in Increment Claude-01."""
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text="No tools registered yet.",
        )],
        isError=True,
    )
```

---

### `server_dupl.py` — (duplicate)

**Source to copy:** `mcp_server/priority_guardian/server.py` — copy verbatim, then make the following adjustments only:

- Update module docstring to reference `priority_guardian_claude`
- Add the duplicate header comment
- Inside `create_app()`: change all imports to use Claude-specific modules with `_dupl` suffixes:
  ```python
  from mcp_server.priority_guardian_claude.config import ...  # no _dupl
  from mcp_server.priority_guardian_claude.discovery_dupl import ...
  from mcp_server.priority_guardian_claude.mcp_auth_dupl import ...
  from mcp_server.priority_guardian_claude.http_client_dupl import ...
  from mcp_server.priority_guardian_claude.handlers.tools_dupl import ...
  # shared — no _dupl, no Claude copy:
  from mcp_server.priority_guardian.request_context import auth_header_var
  ```
- `FastMCP` name argument: `"priority-guardian-claude-mcp"`
- `RequestLoggingMiddleware` service name: `"priority-guardian-claude-mcp"`
- Health endpoint response: `{"status": "ok", "service": "priority-guardian-claude-mcp"}`
- `list_tools` handler registered on `mcp._mcp_server`: return `[]` (empty list) in this increment — no import from tools yet
- Default port in `__main__` block: `8004`
- Log message in `__main__` block: updated service name

No other changes. The five middleware classes, the OAuth proxy routes, the discovery route wiring, the cleanup logic, the `__getattr__` lazy getter, and the `get_app()` function are all copied verbatim.

**Critical constraint:** `create_app()` must complete and `/health` must return 200 with no tools registered and no backend connectivity required.

---

## What NOT to Touch

- Any file in `mcp_server/priority_guardian/` — ChatGPT server is under OpenAI review
- Any file in `backend/`
- `mcp_server/shared/` — shared infrastructure refactor is post-OpenAI-approval

---

## Render Service (document only — do not create yet)

Future Render service:
- Separate web service, same repo
- Start command: `uvicorn mcp_server.priority_guardian_claude.server_dupl:create_app --factory --host 0.0.0.0 --port $PORT`
- All `PG_CLAUDE_*` env vars pointing at same backend
- `PG_CLAUDE_MCP_SERVER_URL` = new subdomain (e.g. `https://pg-claude.priority-guard.com`)

---

## Tests

Create `tests/unit/mcp_claude/test_scaffold.py`.

Use `httpx.AsyncClient(app=create_app(), base_url="http://test")` — same pattern as existing MCP server tests. Set `ENV=dev` via `monkeypatch.setenv`. No real backend connectivity for any test.

### Unit tests

1. `test_server_creates_without_backend` — `ENV=dev`, `create_app()` completes without error and without making any network calls
2. `test_health_returns_ok` — GET `/health` returns 200, body contains `"priority-guardian-claude-mcp"`
3. `test_oauth_protected_resource` — GET `/.well-known/oauth-protected-resource` returns JSON with `resource`, `authorization_servers`, `scopes_supported` keys present
4. `test_head_mcp_returns_200` — HEAD `/mcp` returns 200
5. `test_post_mcp_without_token_returns_401` — POST `/mcp` without Authorization header returns 401 with `WWW-Authenticate` header present
6. `test_config_isolation` — two assertions:
   - Config module isolation: after importing both `priority_guardian.config` and `priority_guardian_claude.config`, setting `priority_guardian_claude.config.BACKEND_URL` to a distinct test value does not affect `priority_guardian.config.BACKEND_URL`
   - Monkeypatch documentation: after importing `mcp_auth_dupl`, assert that `priority_guardian.mcp_auth._MCP_ORIGIN` reflects the Claude `MCP_SERVER_URL`. Add a comment explaining this is **intentional and safe** — the two servers never run in the same process in production. This documents the known limitation and why the post-OpenAI refactor into `shared/` with config injection is needed.

### No integration tests in this increment

End-to-end OAuth flow with Claude.ai requires the Render service deployed and Claude OAuth callback URIs added to the backend allowlist. Both deferred to Phase 2 (post-OpenAI approval).

---

## Definition of Done

- [ ] `mcp_server/priority_guardian_claude/` exists with all files listed above
- [ ] Every `(duplicate)` file carries the header comment
- [ ] `python -c "from mcp_server.priority_guardian_claude.server_dupl import create_app; create_app()"` completes without error in `ENV=dev`
- [ ] Importing `priority_guardian_claude.mcp_auth_dupl` with no backend running does not raise
- [ ] All 6 unit tests pass
- [ ] Zero files modified in `mcp_server/priority_guardian/`
- [ ] Zero files modified in `backend/`