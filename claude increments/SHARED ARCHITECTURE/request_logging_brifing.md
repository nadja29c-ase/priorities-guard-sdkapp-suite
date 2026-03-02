# Claude Code Briefing: Add Request Logging Middleware

## Context

OpenAI rejected Clarity's MCP server with "unable to connect." Root cause analysis took hours because we had no app-level request logs showing what OpenAI's probe actually hit and what status it received. Render's built-in logs show requests but lack structured detail (no User-Agent, no Origin, no response time).

This must never happen again. Next time OpenAI reviews, we need 100% visibility into what they probed and what happened.

## Scope

Both MCP servers:

1. **Clarity MCP** — `mcp_server/clarity/server.py`
2. **Priority Guardian MCP** — `mcp_server/priority_guardian/server.py`

## Requirements

### R1: Log every HTTP request with structured fields

Every inbound HTTP request must produce one structured log entry with:

- `timestamp` (ISO 8601)
- `method` (GET, POST, HEAD, OPTIONS, etc.)
- `path` (e.g., `/mcp`, `/`, `/.well-known/oauth-protected-resource`)
- `status_code` (response status)
- `client_ip` (from `X-Forwarded-For` header first, then ASGI `client` scope — Render sits behind Cloudflare)
- `user_agent` (from `User-Agent` header, truncated to 200 chars)
- `origin` (from `Origin` header, if present)
- `response_time_ms` (time from request received to response sent)
- `service` (e.g., `clarity-mcp` or `priority-guardian-mcp`)

Use `structlog` — already in both servers.

### R2: Implement as a separate ASGI middleware

Name: `RequestLoggingMiddleware`

**Middleware stack order (outermost to innermost):**
1. `HeadMcpMiddleware` (outermost — short-circuits HEAD /mcp)
2. `RequestLoggingMiddleware` ← NEW (logs everything that passes through)
3. `LifespanMiddleware` (PG only)
4. `MCPContentTypeAndAcceptFixMiddleware`
5. `fastmcp_app` (innermost)

**Why this position:** It sits inside HeadMcpMiddleware so it logs HEAD /mcp as handled (not as a passthrough). It wraps everything else, so it captures the final status code for all requests including middleware-modified ones.

**Wait — correction:** If it sits inside HeadMcpMiddleware, it will NOT see HEAD /mcp requests (those are short-circuited before reaching it). 

**Actual requirement:** `RequestLoggingMiddleware` must be the outermost middleware. `HeadMcpMiddleware` moves to second position. This way ALL requests are logged, including HEAD /mcp.

**Corrected middleware stack order:**
1. `RequestLoggingMiddleware` (outermost — logs everything)
2. `HeadMcpMiddleware` (short-circuits HEAD /mcp)
3. `LifespanMiddleware` (PG only)
4. `MCPContentTypeAndAcceptFixMiddleware`
5. `fastmcp_app` (innermost)

### R3: Capture response status code

The middleware must intercept the ASGI `send` call to capture `http.response.start` status code. This is the only way to log the response status in ASGI middleware without using Starlette's `BaseHTTPMiddleware` (which breaks streaming).

Pattern:
```
status_code = None

async def send_wrapper(message):
    if message["type"] == "http.response.start":
        status_code = message["status"]
    await send(message)
```

### R4: Do NOT log sensitive data

- Do NOT log Authorization header values
- Do NOT log request/response bodies
- Do NOT log query parameters (may contain tokens)
- Truncate User-Agent to 200 chars

### R5: Do NOT log lifespan events

Only log `scope["type"] == "http"` requests. Skip `lifespan`, `websocket`, etc.

### R6: Log level

- `info` for all requests (this is low-volume — MCP servers don't get thousands of requests)
- `warning` for 4xx responses
- `error` for 5xx responses

## Technical Context

- Both servers use `structlog` already
- ASGI middleware pattern (not Starlette BaseHTTPMiddleware — that breaks SSE streaming)
- Render logs are accessible via dashboard and Render MCP tool
- Cloudflare sits in front — real client IP is in `X-Forwarded-For`

## Unit Tests

File: `tests/unit/mcp_clarity/test_request_logging.py` (and equivalent for PG)

| Test | Description | Expected |
|------|-------------|----------|
| `test_logs_get_request` | Send GET / | Log entry with method=GET, path=/, status=200 |
| `test_logs_post_mcp` | Send POST /mcp with initialize | Log entry with method=POST, path=/mcp |
| `test_logs_head_mcp` | Send HEAD /mcp | Log entry with method=HEAD, path=/mcp, status=200 |
| `test_logs_client_ip_from_xff` | Request with X-Forwarded-For header | Log entry uses XFF IP, not direct client |
| `test_logs_user_agent` | Request with User-Agent header | Log entry includes user_agent field |
| `test_no_auth_header_logged` | Request with Authorization header | Log entry does NOT contain auth token |
| `test_logs_response_time` | Any request | Log entry includes response_time_ms > 0 |
| `test_skips_lifespan` | Lifespan scope | No log entry produced |

Use `structlog.testing.capture_logs()` to assert log output without mocking.

## Integration Tests

File: `tests/integration/clarity/test_request_logging_integration.py`

| Test | Description | Expected |
|------|-------------|----------|
| `test_full_request_lifecycle_logged` | GET / → HEAD /mcp → POST /mcp initialize | Three log entries in order, correct status codes |
| `test_4xx_logged_as_warning` | Request to nonexistent path | Log level is warning, status 404 |

## Acceptance Criteria

1. Render logs show structured JSON entries for every request after deploy
2. Each entry contains: method, path, status_code, client_ip, user_agent, response_time_ms
3. No Authorization header values in logs
4. HEAD /mcp, GET /, and POST /mcp all produce log entries
5. All existing tests still pass
6. MCP protocol behavior unchanged

## What NOT to change

- Do not modify HeadMcpMiddleware logic (only its position in the stack)
- Do not modify MCPContentTypeAndAcceptFixMiddleware
- Do not modify tool handlers or OAuth endpoints
- Do not add external logging services or dependencies
