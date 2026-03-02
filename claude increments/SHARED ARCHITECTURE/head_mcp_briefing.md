# Claude Code Briefing: Add HEAD /mcp Support

## Context

OpenAI rejected Clarity with: "We're unable to connect to your MCP server."

Full diagnostic confirms DNS, TLS, and MCP POST all work correctly.

**Root cause analysis identified two issues:**

1. **GET / returned 404 during review window (Feb 25-27).** The health endpoint commit (`eb1d048`) was only deployed on Feb 27. If OpenAI's probe hit `GET /` before that deploy, it got 404 — which a simplistic connectivity check would classify as "unreachable." This is now fixed (returns `{"status": "ok"}`).

2. **HEAD /mcp returns 405.** If OpenAI also probes `/mcp` with HEAD, a 405 could be misclassified as unreachable. This is the remaining gap.

Both are defensive engineering — the MCP protocol itself works correctly. We're eliminating variables in OpenAI's opaque review probe behavior.

## Scope

Two MCP servers need this change:

1. **Clarity MCP** — `priorities-guard-sdkapp-suite` repo, `mcp_server/clarity/server.py`
2. **Priority Guardian MCP** — when it exists (apply same pattern)

For now, implement in Clarity only. Priority Guardian will follow the same pattern when built.

## Requirements

### R1: HEAD /mcp returns 200

Add a HEAD handler for the `/mcp` path that returns HTTP 200 with no body.

- Response headers: `Content-Type: application/json`, `Cache-Control: no-store`
- No response body (HEAD must not return a body per HTTP spec)
- This route must NOT interfere with existing POST /mcp (JSON-RPC), GET /mcp, or DELETE /mcp handlers

### R2: GET /mcp without proper Accept header returns 200

Currently GET /mcp without `Accept: text/event-stream` returns a JSON-RPC error with status 200. This is acceptable — no change needed here. Just verify it stays 200 (not 4xx/5xx).

### R3: No changes to existing MCP protocol behavior

- POST /mcp must continue to work identically (JSON-RPC, initialize, tools/list, tools/call)
- All existing middleware (MCPContentTypeAndAcceptFixMiddleware, CORS) must remain untouched
- Widget serving, resource handlers, tool handlers — no changes

## Technical Context

- Framework: FastMCP with Starlette underneath
- The `create_app()` function in `server.py` adds routes via `fastmcp_app.add_route()`
- Existing routes: `/`, `/health`, `/privacy-policy`, `/terms`, `/.well-known/openai-apps-challenge`, `/.well-known/*` OAuth discovery endpoints
- The `/mcp` path is handled by FastMCP's `streamable_http_app()` — the HEAD handler must be added without conflicting with FastMCP's own routing

### Implementation constraint: Separate middleware, NOT route override

FastMCP explicitly rejects HEAD on `/mcp` (returns 405 with `Allow: GET, POST, DELETE`). Adding a HEAD route risks conflict with FastMCP's internal routing.

**Required approach:** Create a NEW, separate ASGI middleware. Do NOT modify the existing `MCPContentTypeAndAcceptFixMiddleware`. Separation of concerns.

The new middleware must:
- Check ONLY: `scope["method"] == "HEAD" and scope["path"] == "/mcp"`
- Return 200 immediately with empty body and headers: `Content-Type: application/json`, `Cache-Control: no-store`
- For ALL other requests: pass through unchanged via `await self.app(scope, receive, send)`
- Be the **outermost** wrapper in `create_app()` (applied last in code, runs first at request time)

### CORS consideration

The HEAD middleware short-circuits before CORS middleware runs. It must manually include:
- `Access-Control-Allow-Origin` header (match what CORS middleware would set — use `*` or the configured origins)
- `Vary: Origin`

Otherwise HEAD responses may behave differently behind proxy. Integration tests must verify this.

**Important:** Reference the same `CORS_ALLOWED_ORIGINS` config constant used by the CORS middleware. Do NOT hardcode origins. If CORS config changes, both must stay in sync.

## Unit Tests

File: `tests/test_head_mcp.py` (or add to existing server test file)

| Test | Description | Expected |
|------|-------------|----------|
| `test_head_mcp_returns_200` | Send HEAD request to `/mcp` | Status 200, `response.content == b""` (explicit empty body check) |
| `test_head_mcp_has_content_type` | Check response headers | `Content-Type: application/json` and `Cache-Control: no-store` present |
| `test_get_root_returns_200` | Send GET to `/` | Status 200, JSON body with `status: ok` (verify existing health fix) |
| `test_post_mcp_still_works` | Send POST initialize request with proper headers | Valid JSON-RPC response with protocolVersion |
| `test_get_mcp_returns_200` | Send GET to `/mcp` with basic Accept | Status 200 (even if body is error JSON) |
| `test_head_does_not_affect_post_streaming` | POST still returns correct Content-Type and SSE behavior | Streaming headers unchanged, no extra/missing headers |
| `test_head_does_not_trigger_session` | HEAD does not instantiate MCP session state | No "Terminating session" log, no session side effects |
| `test_head_other_paths_unaffected` | HEAD /health and HEAD /privacy-policy | Behave as before (not intercepted by new middleware) |
| `test_head_mcp_no_allow_header` | HEAD /mcp response headers | Must NOT include `Allow` header (the old 405 included `Allow: GET, POST, DELETE` — the new 200 must not) |

Use `httpx.AsyncClient` with the ASGI app directly (no live server needed).

## Integration Tests

File: `tests/test_head_mcp_integration.py`

| Test | Description | Expected |
|------|-------------|----------|
| `test_head_mcp_through_middleware` | HEAD /mcp passes through full middleware stack | 200, CORS headers present (`Access-Control-Allow-Origin`, `Vary: Origin`) |
| `test_head_mcp_cors_with_origin` | HEAD /mcp with `Origin: https://chatgpt.com` header | CORS response headers match what POST /mcp returns |
| `test_full_mcp_flow_unaffected` | POST initialize → POST tools/list → verify tools returned | Same tool list as before, no regressions |

## Acceptance Criteria

1. `curl -I https://clarity.priority-guard.com/` returns `HTTP/2 200` (root health check — already fixed, just verify)
2. `curl -I https://clarity.priority-guard.com/mcp` returns `HTTP/2 200` (new HEAD handler)
3. `curl -X POST https://clarity.priority-guard.com/mcp -H "Content-Type: application/json" -H "Accept: text/event-stream, application/json" -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'` returns valid initialize response (unchanged)
4. All existing tests pass
5. ChatGPT can still discover and invoke Clarity tools

## What NOT to change

- Do not modify any tool logic, tool descriptions, or structured content
- Do not modify OAuth endpoints or middleware
- Do not modify widget HTML files
- Do not change the FastMCP configuration (stateless_http, streamable_http_path)
- Do not add any new dependencies
