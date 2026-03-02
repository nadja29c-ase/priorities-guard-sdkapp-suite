# Claude Code Briefing: Health Endpoint — All MCP Servers

## Context

Clarity was rejected by OpenAI review with "unable to connect to MCP server." Log analysis confirmed the reviewer never reached `POST /mcp`. Every external request in the Clarity MCP logs hit `GET / → 404 Not Found`. The most probable cause: submission URL was the domain root rather than `/mcp`, or the reviewer did a reachability check on `/` and failed before attempting the MCP handshake.

All three MCP servers in the suite need a `GET /` health endpoint returning `200 OK`. This prevents false negatives from reviewers, monitoring tools, and Render health checks.

## Scope

Add a `GET /` health endpoint to these three MCP servers:

1. **Clarity** — `mcp_server/clarity/server.py` (Priority Guardian repo)
2. **Unpack** — `apps/unpack/server.py` (fulfilling-productivity repo)
3. **Priority Guardian** — `mcp_server/priority_guardian/server.py` (Priority Guardian repo)

## What Already Exists

### Unpack (REFERENCE — already approved by OpenAI)
Unpack already has both endpoints and is the reference pattern:
- `GET /` → `RedirectResponse` to Framer landing page (302)
- `GET /health` → `PlainTextResponse("ok")` (200)

These are registered via `fastmcp_app.add_route()` in `create_app()`.

### Clarity
- No `GET /` route. Currently returns 404.
- No `GET /health` route.
- Routes are added inside `create_app()` before middleware wrapping.

### Priority Guardian
- No `GET /` route. Currently returns 404.
- No `GET /health` route.
- Routes are NOT added via `add_route()`. PG uses Starlette `Route` lists only for `/.well-known` discovery, then mounts as sub-app.

## Requirements

### Functional
- `GET /` must return `200 OK` with `application/json` content type
- Response body: `{"status": "ok", "service": "<service-name>"}`
  - Clarity: `"clarity-mcp"`
  - Unpack: Keep existing behavior (redirect to Framer landing — already 302, not 404)
  - Priority Guardian: `"priority-guardian-mcp"`
- `GET /health` must return `200 OK` with `text/plain` content type, body: `"ok"`
- No authentication on either endpoint

### Non-Functional
- Zero impact on MCP endpoint behavior (`POST /mcp` unchanged)
- Zero impact on OAuth discovery endpoints (`/.well-known/*` unchanged)
- Must work with the existing middleware stack (header fix middleware only intercepts `POST /mcp`)

## Implementation Guidance

### Route Registration Pattern
Each server uses `mcp.streamable_http_app()` which returns the **root Starlette app**. MCP lives at `/mcp` as a path *within* this app (via `streamable_http_path="/mcp"`). This is NOT `outer_app.mount("/mcp", mcp_app)` — the Starlette app owns the root, MCP is a route inside it. Routes must be added to `fastmcp_app` (the return value of `streamable_http_app()`), which is the top-level ASGI app. Unpack already does this successfully with `fastmcp_app.add_route("/", ...)`.

**Clarity:** Add routes to `fastmcp_app` in `create_app()` before the `MCPContentTypeAndAcceptFixMiddleware` wrap at the end.

**Priority Guardian:** Add routes to `fastmcp_app` in `create_app()` before the middleware wrapping section.

**Unpack:** Already has `GET /` (redirect) and `GET /health`. Only change needed: add `/health` endpoint returning `PlainTextResponse("ok")` if one isn't already present. CHECK FIRST — Unpack already has `health_handler`. Likely no changes needed.

### What NOT to Change
- Do not modify the `POST /mcp` handler or any MCP protocol behavior
- Do not add logging to the health endpoint (it will be hit by monitoring frequently)
- Do not add authentication or middleware to these routes
- Do not change Unpack's existing `GET /` redirect behavior

## Unit Tests

Test file per server. Tests should verify:

1. `GET /` returns 200 with correct JSON body and `application/json` content type
2. `GET /health` returns 200 with `"ok"` body and `text/plain` content type
3. `POST /mcp` regression: send a minimal initialize request and assert `response.status_code != 404`. A 401 (auth required) or 200 are both acceptable — what must NOT happen is 404.

Use `httpx.ASGITransport` with the app's `create_app()` to test without network.

For Unpack: verify `GET /` returns 302 redirect (existing behavior preserved).

## Integration Tests

Not required for this change. These are stateless endpoints with no external dependencies.

## Verification After Deploy

After deploying each service, confirm externally:

```bash
# Clarity
curl -s https://clarity.priority-guard.com/
curl -s https://clarity.priority-guard.com/health

# Priority Guardian
curl -s https://pg.priority-guard.com/
curl -s https://pg.priority-guard.com/health

# Unpack
curl -s https://unpack.fulfilling-productivity.com/
curl -s https://unpack.fulfilling-productivity.com/health
```

All must return 200 (or 302 for Unpack root).

## Files to Modify

| Server | File | Change |
|--------|------|--------|
| Clarity | `mcp_server/clarity/server.py` | Add health + root route handlers, register via `add_route()` in `create_app()` |
| Priority Guardian | `mcp_server/priority_guardian/server.py` | Add health + root route handlers, register via `add_route()` in `create_app()` |
| Unpack | `apps/unpack/server.py` | Verify existing endpoints. Likely no changes needed. |

## Priority

**HIGH** — Blocking Clarity resubmission to OpenAI.
