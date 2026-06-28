# Increment MindSort-Claude-01: `mindsort_claude` — Folder Scaffold

**Goal:** Create the `mindsort_claude` MCP server module as a deployable empty service. Zero tool logic. Zero widget code. Server starts, binds port, passes health check, returns 401 on unauthenticated `/mcp`.

---

## Context

MindSort AI (codebase module `clarity/`) is being extended to the Anthropic MCP Directory as a second distribution channel alongside the existing OpenAI ChatGPT SDK app. The two platforms require separate MCP server processes (different `MCP_SERVER_URL`, different OAuth callback URLs, different CORS origins) but share the same backend API, same PostgreSQL database, and the same tool logic.

**Rule: duplicate a file ONLY when forced to by config coupling. Everything config-free is imported by reference. Annotate every duplicate file so the future consolidation is obvious.**

The existing `mcp_server/clarity/` module is the ChatGPT MCP server — it **must not be touched** in this increment. MindSort is currently under OpenAI review; any change to `clarity/` risks that review. This increment creates `mcp_server/mindsort_claude/` as a parallel module in the same repo.

Reference architecture: `doc/Claude_Compliance/structural_guideline_claude_vs_openai_MindSortAI.md`
Sibling reference (PG's equivalent increment): `claude increments/PRIORITY_GUARDIAN/pg_v1.0_claude/inc_01_filestr.md`

---

## Pre-Implementation

Read `doc/OPERATIONS_PREDEPLOY.md` before starting. No migrations in this increment.

---

## Implementation Approach — Copy and Adjust, Never Rewrite

Every duplicated file in this increment has an existing counterpart in `mcp_server/clarity/`. Claude Code must:

1. **Copy the source file verbatim** as the starting point.
2. **Make only the specific adjustments listed** in this briefing.
3. **Not rewrite, restructure, simplify, or improve** anything not explicitly listed.

The existing implementation is production-tested. Deviations introduce inconsistency. If something in the source looks wrong or suboptimal, **flag it — do not silently fix it.**

---

## Duplication Policy — verified against the codebase

Only files with a **hard import dependency on platform-specific config** are duplicated. Everything config-free is imported directly from `clarity`. This map was derived by reading each source file — follow it exactly; do not add duplicate files not listed here.

| File | Action | Reason |
|---|---|---|
| `config.py` | **new** (not `_dupl`) | Different env vars, URLs, port |
| `server_dupl.py` | **`_dupl`** | Platform entry point; own config + Claude middleware |
| `discovery_dupl.py` | **`_dupl`** | Imports own config for URLs |
| `mcp_auth_dupl.py` | **`_dupl`** thin wrapper | Re-exports `clarity.mcp_auth` logic, rebinds own config (incl. `TOOL_SCOPES`) |
| `handlers/tools_dupl.py` | **`_dupl`** stub | Imports Claude `mcp_auth_dupl` so error origins are correct; empty registry this increment |
| `http_client` | **import by reference** — NOT duplicated | `clarity/http_client.py` is config-free (no `BACKEND_URL`/secret). Nothing to rebind. |
| `request_context` | **import by reference** — not created | Pure `ContextVar`, zero config deps |
| `tools/` | **import by reference** — not created | All tool logic is config-free |
| `persistence`, `tool_logic`, `board_utils` | **import by reference** — not created | Pure logic (see structural doc §2) |
| `widget-react/` | **not created** — future increment | Claude widget (MCP Apps bridge) |

> **CRITICAL — `http_client` is NOT duplicated.** PG duplicated its `http_client` because PG's version rebinds `BACKEND_URL`/`INTERNAL_API_SECRET`. **MindSort's `clarity/http_client.py` has neither** — it is a config-free module-level client. Creating an `http_client_dupl.py` here would be a pointless duplicate with nothing to rebind. Import `get_http_client`/`cleanup_http_client` directly from `clarity.http_client`. This is the single biggest deviation from PG's scaffold.

Every `_dupl` file must carry this header comment (3 lines). Do NOT include a "move to `mcp_server/shared/`" migration promise — consolidation is not planned; it happens only if a file proves to cause recurring double-booking:

```python
# (duplicate) — exists only because <specific reason>.
# Logic lives in mcp_server/clarity/<same_filename>.
# Consolidate into shared/ ONLY if this file proves to churn — not preemptively.
```

---

## Folder Structure to Create

```
mcp_server/mindsort_claude/
├── __init__.py
├── config.py                    # new — all CLARITY_CLAUDE_* env vars
├── server_dupl.py               # (duplicate) platform entry point
├── discovery_dupl.py            # (duplicate) OAuth discovery URLs
├── mcp_auth_dupl.py             # (duplicate) thin wrapper
├── handlers/
│   ├── __init__.py
│   └── tools_dupl.py            # (duplicate) thin wrapper — empty registry
└── widgets/
    └── .gitkeep
```

(No `http_client_dupl.py`. No `request_context.py`. No `tools/`.)

---

## Implementation

### `__init__.py` and `handlers/__init__.py`

Empty. Module markers only.

---

### `config.py` — new (not duplicate)

**Source to copy:** `mcp_server/clarity/config.py` — copy verbatim, then make ONLY these adjustments:

- Rename env var keys from `CLARITY_*` to `CLARITY_CLAUDE_*` (mapping below).
- Update dev default for `MCP_SERVER_URL` to `http://localhost:8003`.
- Update the module docstring to reference `mindsort_claude`.
- **No duplicate header comment** — this file is genuinely new content.

All logic stays identical: same `get_env()` helper, same `ENV` detection, same fail-fast guards, same `TOOL_SCOPES` dict, same `IS_DEV`/CORS handling.

**Env var mapping:**

| Config value | Env var | Dev default |
|---|---|---|
| `MCP_SERVER_URL` | `CLARITY_CLAUDE_MCP_SERVER_URL` | `http://localhost:8003` |
| `MCP_RESOURCE_URL` | `CLARITY_CLAUDE_MCP_RESOURCE_URL` | `{MCP_SERVER_URL}/mcp` |
| `OAUTH_ISSUER_URL` | `CLARITY_CLAUDE_OAUTH_ISSUER_URL` | `http://localhost:8000/oauth/pg` |
| `BACKEND_URL` | `CLARITY_CLAUDE_BACKEND_URL` | `http://localhost:8000` |
| `INTERNAL_API_SECRET` | `CLARITY_CLAUDE_INTERNAL_API_SECRET` | `""` |
| `CLARITY_JWKS_URL` | `CLARITY_CLAUDE_JWKS_URL` | `http://localhost:8000/oauth/pg/jwks` |
| `CLARITY_ISSUER` | `CLARITY_CLAUDE_ISSUER` | `https://www.priority-guard.com` |
| `CLARITY_AUDIENCE` | `CLARITY_CLAUDE_AUDIENCE` | `https://www.priority-guard.com` |
| `CORS_ALLOWED_ORIGINS` | `CLARITY_CLAUDE_CORS_ALLOWED_ORIGINS` | `""` |
| `SCOPES_SUPPORTED` | hardcoded | `["clarity.write"]` |
| `TOOL_SCOPES` | hardcoded | same dict as `clarity/config.py` |

`MCP_RESOURCE_URL` MUST be `{MCP_SERVER_URL}/mcp` (path included) — the `resource` claim and `ui.domain` hash both depend on the `/mcp` suffix.

Add a comment block at the top listing all required Render env vars (self-documenting spec for the future Render service). Deployed domain is **not decided yet** — leave placeholder comments. **CRITICAL: `MCP_SERVER_URL` is an ORIGIN with NO `/mcp` path.** `discovery.py` appends `/mcp` itself (`resource = f"{MCP_SERVER_URL}/mcp"`), and `MCP_RESOURCE_URL` derives as `{MCP_SERVER_URL}/mcp`. Putting `/mcp` in `MCP_SERVER_URL` produces `https://domain/mcp/mcp` and breaks the `resource` claim, the `.well-known` URLs, AND the `ui.domain` hash. Placeholder:
```
# CLARITY_CLAUDE_MCP_SERVER_URL   = <deployed Claude origin, NO /mcp>   e.g. https://mindsort-claude.priority-guard.com
# CLARITY_CLAUDE_MCP_RESOURCE_URL = <origin>/mcp                        (derives automatically; only set if overriding)
```

---

### `discovery_dupl.py` — (duplicate)

**Source to copy:** `mcp_server/clarity/discovery.py` — copy verbatim, then:

- Change the config import from `mcp_server.clarity.config` to `mcp_server.mindsort_claude.config`.
- Add the duplicate header comment.

No logic changes. (Confirmed: this file already advertises `code_challenge_methods_supported: ["S256"]` and returns `resource = {MCP_SERVER_URL}/mcp` — both compliance-correct, keep verbatim.)

---

### `mcp_auth_dupl.py` — (duplicate) thin wrapper

**Do not copy the source file.** Write only the wrapper below. Pattern mirrors PG's `mcp_auth_dupl.py`, adapted to MindSort's config names.

**Invariant:** must not trigger any network call at import time. JWKS fetch happens only on first authenticated tool call. Importing this module with no backend running must not raise.

Config-dependent globals in `clarity.mcp_auth` that need rebinding: `CLARITY_JWKS_URL`, `CLARITY_ISSUER`, `CLARITY_AUDIENCE`, `MCP_SERVER_URL`, `TOOL_SCOPES`, and the JWKS timing constants. Note `TOOL_SCOPES` — MindSort's scope enforcement reads a module-level `TOOL_SCOPES` dict (unlike PG), so it MUST be in the rebind list.

```python
# (duplicate) — exists only because it imports platform-specific config.
# Logic lives in mcp_server/clarity/mcp_auth.py.
# Consolidate into shared/ ONLY if this file proves to churn — not preemptively.

import mcp_server.clarity.mcp_auth as _shared

from mcp_server.mindsort_claude.config import (
    CLARITY_JWKS_URL,
    CLARITY_ISSUER,
    CLARITY_AUDIENCE,
    MCP_SERVER_URL,
    TOOL_SCOPES,
    TOKEN_EXPIRY_GRACE_SECONDS,
    JWKS_CACHE_TTL_SECONDS,
    JWKS_MAX_STALE_SECONDS,
    JWKS_FETCH_TIMEOUT_SECONDS,
)

# Rebind config-dependent module globals to Claude platform values
_shared.CLARITY_JWKS_URL = CLARITY_JWKS_URL
_shared.CLARITY_ISSUER = CLARITY_ISSUER
_shared.CLARITY_AUDIENCE = CLARITY_AUDIENCE
_shared.MCP_SERVER_URL = MCP_SERVER_URL
_shared.TOOL_SCOPES = TOOL_SCOPES
_shared.TOKEN_EXPIRY_GRACE_SECONDS = TOKEN_EXPIRY_GRACE_SECONDS
_shared.JWKS_CACHE_TTL_SECONDS = JWKS_CACHE_TTL_SECONDS
_shared.JWKS_MAX_STALE_SECONDS = JWKS_MAX_STALE_SECONDS
_shared.JWKS_FETCH_TIMEOUT_SECONDS = JWKS_FETCH_TIMEOUT_SECONDS

# Re-export everything callers need
from mcp_server.clarity.mcp_auth import (  # noqa: E402, F401
    authenticate_request,
    cleanup_jwks_cache,
    build_unauthorized_meta,
    build_forbidden_meta,
    UnauthorizedError,
    InsufficientScopeError,
    JWKSCache,
)
```

**Verify before writing:** confirm the exact symbol names in `clarity/mcp_auth.py` (the import list above is from reading it, but re-check against the file). If `enforce_tool_scope` reads `TOOL_SCOPES` via the module global (it does), the rebind covers it. Note: MindSort's `build_unauthorized_meta`/`build_forbidden_meta` emit the ChatGPT `mcp/www_authenticate` format — these are still re-exported but the Claude OAuth path relies on `BearerAuthMiddleware`'s transport-level 401 (see server section), not these builders.

---

### `handlers/tools_dupl.py` — (duplicate) thin wrapper, empty registry

**Do not copy the source dispatcher.** Write only the stub below. Full dispatcher + response adapter come in MindSort-Claude-02.

```python
# (duplicate) — exists only because it imports platform-specific mcp_auth.
# Dispatcher logic mirrors mcp_server/clarity/handlers/tools.py.
# Consolidate into shared/ ONLY if this file proves to churn — not preemptively.

from mcp import types as mcp_types

# Import platform-specific mcp_auth so error responses use Claude's config
from mcp_server.mindsort_claude.mcp_auth_dupl import (  # noqa: F401
    authenticate_request,
    UnauthorizedError,
    InsufficientScopeError,
    build_unauthorized_meta,
    build_forbidden_meta,
)

# Empty registry — tools wired in MindSort-Claude-02
# from mcp_server.clarity.tools import get_tool


async def call_tool_request(req: mcp_types.CallToolRequest) -> mcp_types.CallToolResult:
    """Stub dispatcher — no tools registered in MindSort-Claude-01."""
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="No tools registered yet.")],
        isError=True,
    )
```

---

### `server_dupl.py` — (duplicate) — MIDDLEWARE NEEDS JUDGMENT, NOT BLIND COPY

**Source structure:** `mcp_server/clarity/server.py`. Copy its overall structure (FastMCP setup, discovery route wiring, health endpoints, handler registration), then adjust imports to the `_dupl`/Claude modules and the service name.

**Import adjustments inside `create_app()`:**
```python
from mcp_server.mindsort_claude.config import CORS_ALLOWED_ORIGINS, IS_DEV, ...
from mcp_server.mindsort_claude.discovery_dupl import (
    openid_configuration, oauth_authorization_server, oauth_protected_resource,
)
from mcp_server.mindsort_claude.mcp_auth_dupl import cleanup_jwks_cache
from mcp_server.mindsort_claude.handlers.tools_dupl import call_tool_request
# shared — imported by reference, NO _dupl:
from mcp_server.clarity.http_client import cleanup_http_client
from mcp_server.clarity.request_context import auth_header_var
```
- `FastMCP` name: `"mindsort-claude-mcp"`.
- `RequestLoggingMiddleware` service name: `"mindsort-claude-mcp"`.
- Health response: `{"status": "ok", "service": "mindsort-claude-mcp"}`.
- `list_tools` handler: return `[]` this increment.
- `__main__` default port: `8003`. Service name in log message updated.
- **Do NOT include the `/openai-apps-challenge` route** — ChatGPT-specific domain verification, no relevance on Claude.

#### Middleware — evaluate each by purpose. Reference PG's `priority_guardian_claude/server_dupl.py`, but VERIFY each middleware's purpose before copying. Do NOT cargo-cult the full PG stack.

| Middleware | Decision | Source | Note |
|---|---|---|---|
| `RequestLoggingMiddleware` | **KEEP** | clarity/server.py (already present) | Observability. Outermost. |
| `OriginValidationMiddleware` | **ADD** | PG `server_dupl.py` | Hard Anthropic security requirement (structural doc §8.3). MindSort source lacks it. Copy PG's class verbatim. |
| `BearerAuthMiddleware` | **ADD** | PG `server_dupl.py` | Required for Claude DCR — clean 401 + `WWW-Authenticate` on unauthenticated `/mcp` before FastMCP closes the stream (§8.4). MindSort source lacks it. Build `WWW_AUTHENTICATE_VALUE` with MindSort scope `clarity.write`. |
| `MCPContentTypeAndAcceptFixMiddleware` — **auth-capture half** | **KEEP (required)** | clarity/server.py | Sets `auth_header_var` from the Authorization header. MindSort's `mcp_auth` reads this ContextVar — without it, auth breaks entirely. Non-negotiable. |
| `MCPContentTypeAndAcceptFixMiddleware` — **header-fix half** (octet-stream→json, `*/*`→event-stream) | **VERIFY before keeping** | clarity/server.py | These fixes were written for *ChatGPT's* client quirks. Whether Claude's MCP client sends `application/octet-stream` or `Accept: */*` is an empirical question. Keep the fixes only if Claude's client needs them; if unverified, keep them (harmless if Claude doesn't send those headers) but ADD A COMMENT noting they are unverified-for-Claude and may be removable. Do not assert they are needed. |
| `HeadMcpMiddleware` | **VERIFY before keeping** | clarity/server.py | PG's comment frames this as *OpenAI's* reachability probe (HEAD /mcp). Whether Claude probes with HEAD is unconfirmed. Keep for now (harmless), but ADD A COMMENT noting it is unverified-for-Claude. Do not present it as a Claude requirement. |
| Shutdown cleanup | **KEEP** | match clarity/server.py mechanism | clarity uses `add_event_handler("shutdown", ...)`; PG uses `LifespanMiddleware`. Use whichever matches the copied structure — both valid. Must call `cleanup_jwks_cache` + `cleanup_http_client`. |

**Middleware ordering** (outermost first), once the KEEP/ADD set is settled:
`RequestLogging` → `HeadMcp` (if kept) → `OriginValidation` → `BearerAuth` → `MCPContentTypeAndAcceptFix` → `fastmcp_app`.

**CORS:** MindSort's `clarity/server.py` uses Starlette `CORSMiddleware`. PG does NOT (PG found Claude proxies widget calls; no direct browser access). **VERIFY before keeping** whether the Claude MindSort server is hit directly by a browser. If unconfirmed, keep CORS for now with a comment that it is unverified-for-Claude and may be removable once direct-access behavior is confirmed (operational verify, structural doc §8.10). Do not remove it blindly either — flag it.

**Critical constraint:** `create_app()` must complete and `/health` must return 200 with no tools registered and no backend connectivity required.

---

## What NOT to Touch

- Any file in `mcp_server/clarity/` — ChatGPT server is under OpenAI review.
- Any file in `backend/`.
- `mcp_server/shared/` — shared infrastructure is out of scope.
- `TOOL_SCOPES` / any config in `clarity/config.py` (copy values into the new `mindsort_claude/config.py`; do not edit the original).

---

## Render Service (document only — do not create yet)

Future Render service:
- Separate web service, same repo.
- Start command: `uvicorn mcp_server.mindsort_claude.server_dupl:create_app --factory --host 0.0.0.0 --port $PORT`.
- All `CLARITY_CLAUDE_*` env vars pointing at the same backend.
- `CLARITY_CLAUDE_MCP_SERVER_URL` = deployed Claude subdomain **origin, NO `/mcp` path** (e.g. `https://mindsort-claude.priority-guard.com`) — **not decided yet; placeholder until deploy.** `/mcp` is appended downstream, never stored in this var.

---

## Tests

Create `tests/unit/mcp_claude_mindsort/test_scaffold.py`.

Use `httpx.AsyncClient(app=create_app(), base_url="http://test")` — same pattern as existing MCP server tests. Set `ENV=dev` via `monkeypatch.setenv`. No real backend connectivity for any test.

### Unit tests

1. `test_server_creates_without_backend` — `ENV=dev`, `create_app()` completes with no network calls.
2. `test_health_returns_ok` — GET `/health` 200, body contains `"mindsort-claude-mcp"`.
3. `test_oauth_protected_resource` — GET `/.well-known/oauth-protected-resource` returns JSON with `resource`, `authorization_servers`, `scopes_supported`; assert `resource` ends with `/mcp`.
4. `test_oauth_advertises_pkce_s256` — GET `/.well-known/oauth-authorization-server` returns `code_challenge_methods_supported == ["S256"]`. (Compliance-critical.)
5. `test_post_mcp_without_token_returns_401` — POST `/mcp` with no Authorization header returns 401 with a `WWW-Authenticate` header present (proves `BearerAuthMiddleware` wired).
6. `test_origin_validation_rejects_unknown` — POST `/mcp` with `Origin: https://evil.example` and no token: assert it does NOT 200 (403 from `OriginValidationMiddleware`, or 401 if Bearer runs first — either proves rejection; assert status in {401, 403}). A request with no Origin header must NOT be rejected by origin validation.
7. `test_config_isolation` — two assertions:
   - After importing both `clarity.config` and `mindsort_claude.config`, setting `mindsort_claude.config.BACKEND_URL` to a distinct test value does not affect `clarity.config.BACKEND_URL`.
   - After importing `mcp_auth_dupl`, assert `clarity.mcp_auth.MCP_SERVER_URL` reflects the Claude `MCP_SERVER_URL`. Add a comment: this rebinding is **intentional and safe** — the two servers never run in the same process in production. Documents the known limitation.

### No integration tests in this increment

End-to-end OAuth with Claude.ai requires the deployed Render service + Claude callback URIs in the backend allowlist. Both deferred to Phase 2 (post-OpenAI approval).

---

## Definition of Done

- [ ] `mcp_server/mindsort_claude/` exists with exactly the files listed (no `http_client_dupl.py`, no `request_context.py`, no `tools/`).
- [ ] Every `_dupl` file carries the 3-line header (no "move to shared/" migration promise).
- [ ] `http_client` and `request_context` are imported by reference from `clarity`, NOT duplicated.
- [ ] `python -c "from mcp_server.mindsort_claude.server_dupl import create_app; create_app()"` completes without error in `ENV=dev`.
- [ ] Importing `mindsort_claude.mcp_auth_dupl` with no backend running does not raise.
- [ ] Middleware set reflects the KEEP/ADD/VERIFY decisions — `OriginValidationMiddleware` and `BearerAuthMiddleware` present; any VERIFY-flagged middleware carries an "unverified-for-Claude" comment.
- [ ] All 7 unit tests pass.
- [ ] Zero files modified in `mcp_server/clarity/`.
- [ ] Zero files modified in `backend/`.

**Scope honesty — this increment is NOT Claude-directory-submission-ready.** It produces a locally runnable scaffold only. It is not submittable until tools + response adapter (Claude-02), tool `title` and corrected `destructiveHint` annotations (structural doc §8.1/§8.2), widget, docs page, screenshots, privacy policy, OAuth callback allowlist (Phase 2), and end-to-end Claude tests are complete. A green DoD here means "scaffold works locally," not "connector is shippable." `title` and `destructiveHint` in particular are mandatory for submission and are deferred to Claude-02 — do not forget them.

---

## Notes for the implementer (flag, don't fix)

- `clarity/mcp_auth.py` and `clarity/http_client.py` carry comments about future extraction to `mcp_server/common/` / `shared/`. Those are pre-existing notes in the OpenAI module — do not act on them, do not edit them (that file is in-review).
- If any symbol name in the `mcp_auth_dupl` import list does not match `clarity/mcp_auth.py`, STOP and report — do not guess a replacement.
