# Claude Code Briefing: Increment 11 — CORS Security Hardening + Correlation ID Propagation

## Context

Two small improvements for production readiness:

1. **CORS:** The Clarity MCP server has `allow_origins=["*"]` — a security risk before production
2. **Correlation ID:** MCP → Backend calls don't propagate correlation IDs, breaking end-to-end tracing

Both are quick fixes touching the same service.

## Problem Statement

**CORS:** `allow_origins=["*"]` allows any website to make cross-origin requests to the MCP server. While OAuth protects authenticated endpoints, this is still a security anti-pattern.

**Correlation ID:** The backend uses `X-Correlation-ID` header (via `CorrelationIDMiddleware`). The MCP server generates correlation IDs but doesn't pass them to backend HTTP calls, making cross-service debugging difficult.

## Success Criteria

- [ ] CORS restricted to known ChatGPT/OpenAI domains
- [ ] Widget rendering continues to work
- [ ] MCP Inspector continues to work (localhost in dev mode)
- [ ] No `Access-Control-Allow-Origin: *` in production responses
- [ ] `X-Correlation-ID` header propagated from MCP → Backend on all HTTP calls
- [ ] Backend logs show correlation IDs from MCP requests

## Technical Requirements

### 1. Update CORS Configuration

File: `mcp_server/clarity/server.py`

Replace:
```python
allow_origins=["*"],  # TODO: Restrict before production
```

With:
```python
allow_origins=[
    # ChatGPT widget sandbox (where widgets render)
    "https://web-sandbox.oaiusercontent.com",
    # ChatGPT domains
    "https://chatgpt.com",
    "https://chat.openai.com",
    # OpenAI API (if needed for future integrations)
    "https://api.openai.com",
],
```

### 2. Environment-Based Configuration

For development flexibility, make origins configurable. **In production, require explicit configuration.**

File: `mcp_server/clarity/config.py`

Add:
```python
import os

# Environment mode
ENV = os.getenv("ENV", "development").lower()
IS_PRODUCTION = ENV in ("production", "prod")
IS_DEV = ENV in ("development", "dev", "local")

# CORS allowed origins
# PRODUCTION: Must be explicitly set via environment variable
# DEVELOPMENT: Falls back to known ChatGPT domains for convenience
_DEFAULT_ORIGINS = "https://web-sandbox.oaiusercontent.com,https://chatgpt.com,https://chat.openai.com"

CORS_ALLOWED_ORIGINS_RAW = os.getenv("CORS_ALLOWED_ORIGINS")

if IS_PRODUCTION and not CORS_ALLOWED_ORIGINS_RAW:
    raise RuntimeError(
        "CORS_ALLOWED_ORIGINS must be explicitly set in production. "
        "OpenAI may add subdomains without notice. "
        "Set to comma-separated list of allowed origins."
    )

CORS_ALLOWED_ORIGINS = (
    CORS_ALLOWED_ORIGINS_RAW.split(",") if CORS_ALLOWED_ORIGINS_RAW 
    else _DEFAULT_ORIGINS.split(",")
)
```

File: `mcp_server/clarity/server.py`

Update CORS middleware:
```python
from mcp_server.clarity.config import CORS_ALLOWED_ORIGINS, IS_DEV

# Build allowed origins list
allowed_origins = list(CORS_ALLOWED_ORIGINS)
if IS_DEV:
    # Add localhost origins for MCP Inspector during development
    allowed_origins.extend([
        "http://localhost:5173",      # MCP Inspector default
        "http://127.0.0.1:5173",
        "http://localhost:3000",      # Common dev port
        "http://127.0.0.1:3000",
    ])

fastmcp_app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET", "POST", "OPTIONS"],  # Restrict to needed methods
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Correlation-ID"],
    allow_credentials=False,
)
```

**Why require explicit production config:**
- OpenAI has historically added subdomains without notice
- Hard-coded defaults will silently break when infrastructure changes
- Explicit config forces operator awareness and enables quick updates

### 3. Future-Proof Focused MCP Server

File: `mcp_server/focused/server.py`

The Focused server does NOT currently have widgets, so CORS is not needed. However, widgets are likely coming (timeline, focus summary, conflicts).

**Action:** Add a commented, disabled CORS block as a future-proofing note:

```python
# ============================================================================
# CORS Configuration (currently disabled - no widgets)
# ============================================================================
# NOTE: Enable CORS when UI output/widgets are added to Focused.
# When enabling, follow the same pattern as Clarity:
#
# from mcp_server.focused.config import CORS_ALLOWED_ORIGINS, IS_DEV
# from starlette.middleware.cors import CORSMiddleware
#
# allowed_origins = list(CORS_ALLOWED_ORIGINS)
# if IS_DEV:
#     allowed_origins.extend([
#         "http://localhost:5173",
#         "http://127.0.0.1:5173",
#     ])
#
# fastmcp_app.add_middleware(
#     CORSMiddleware,
#     allow_origins=allowed_origins,
#     allow_methods=["GET", "POST", "OPTIONS"],
#     allow_headers=["Authorization", "Content-Type", "Accept", "X-Correlation-ID"],
#     allow_credentials=False,
# )
# ============================================================================
```

This prevents forgetting the CORS requirement when widgets are added later.

### 4. Correlation ID Propagation

File: `mcp_server/clarity/persistence.py`

Update both functions to accept and propagate correlation ID:

**`get_cluster()`:**
```python
async def get_cluster(user_id: str, correlation_id: str | None = None) -> dict | None:
    headers = {"X-User-ID": user_id}
    if INTERNAL_API_SECRET:
        headers["X-Internal-Secret"] = INTERNAL_API_SECRET
    if correlation_id:
        headers["X-Correlation-ID"] = correlation_id
    # ... rest unchanged
```

**`persist_cluster()`:**
```python
async def persist_cluster(
    user_id: str,
    cluster_data: dict,
    thoughts_exhausted: bool,
    correctly_clustered: bool | None,
    correlation_id: str | None = None,  # Add parameter
) -> str | None:
    headers = {"X-User-ID": user_id}
    if INTERNAL_API_SECRET:
        headers["X-Internal-Secret"] = INTERNAL_API_SECRET
    if correlation_id:
        headers["X-Correlation-ID"] = correlation_id
    # ... rest unchanged
```

### 5. Update Tool Handlers to Pass Correlation ID

File: `mcp_server/clarity/tools/cluster_raw_thoughts.py`

Update the `persist_cluster()` call:
```python
await persist_cluster(
    user_id=user_id,
    cluster_data=cluster_data_to_store,
    thoughts_exhausted=validated_request.thoughts_exhausted,
    correctly_clustered=validated_request.correctly_clustered,
    correlation_id=correlation_id,  # Add this
)
```

File: `mcp_server/clarity/tools/get_my_clusters.py`

Update the `get_cluster()` call:
```python
cluster_data = await get_cluster(user_id, correlation_id)
```

## Files to Modify

```
mcp_server/clarity/config.py                      — Add CORS config with production requirement
mcp_server/clarity/server.py                      — Update CORSMiddleware configuration
mcp_server/clarity/persistence.py                 — Add correlation_id parameter to both functions
mcp_server/clarity/tools/cluster_raw_thoughts.py  — Pass correlation_id to persist_cluster()
mcp_server/clarity/tools/get_my_clusters.py       — Pass correlation_id to get_cluster()
mcp_server/focused/server.py                      — Add commented CORS block for future-proofing
```

## Files to Reference (Read-Only)

```
backend/core/middleware.py       — CorrelationIDMiddleware (accepts X-Correlation-ID)
```

## Constraints

- Widget rendering must continue to work in ChatGPT
- MCP Inspector must work in development mode
- No changes to authentication or tool logic
- Backward compatible — existing deployments work after update

## Unit Tests

File: `tests/unit/mcp_clarity/test_config.py`

| Test | Assertion |
|------|-----------|
| `test_cors_origins_default_in_dev` | Dev mode uses default ChatGPT domains |
| `test_cors_origins_no_wildcard` | `"*"` never in origins list |
| `test_cors_origins_from_env` | `CORS_ALLOWED_ORIGINS` env var is respected |
| `test_production_requires_explicit_config` | `ENV=production` + no `CORS_ALLOWED_ORIGINS` → RuntimeError |
| `test_production_accepts_explicit_config` | `ENV=production` + `CORS_ALLOWED_ORIGINS` set → no error |

File: `tests/unit/mcp_clarity/test_persistence.py`

| Test | Assertion |
|------|-----------|
| `test_get_cluster_propagates_correlation_id` | X-Correlation-ID header sent when provided |
| `test_get_cluster_no_correlation_id` | No X-Correlation-ID header when None |
| `test_persist_cluster_propagates_correlation_id` | X-Correlation-ID header sent when provided |
| `test_persist_cluster_no_correlation_id` | No X-Correlation-ID header when None |

## Integration Tests

File: `tests/integration/clarity/test_cors.py`

| Test | Setup | Assertion |
|------|-------|-----------|
| `test_cors_allows_chatgpt_origin` | Request with `Origin: https://chatgpt.com` | Response has `Access-Control-Allow-Origin: https://chatgpt.com` |
| `test_cors_allows_widget_sandbox` | Request with `Origin: https://web-sandbox.oaiusercontent.com` | Response has matching ACAO header |
| `test_cors_blocks_unknown_origin` | Request with `Origin: https://evil.com` | No `Access-Control-Allow-Origin` header |
| `test_cors_preflight_success` | OPTIONS request with valid origin | Status in `{200, 204}`, correct CORS headers present |
| `test_no_wildcard_header_ever` | Any request | `Access-Control-Allow-Origin` is never `*` |

**Note on `test_cors_preflight_success`:** Starlette can return either `200` or `204` for preflight depending on headers. Test must accept both status codes to avoid CI flakiness.

**Note on `test_no_wildcard_header_ever`:** This is a regression guard. Protects against accidental reintroduction of `allow_origins=["*"]`.

File: `tests/integration/clarity/test_correlation_id.py`

| Test | Setup | Assertion |
|------|-------|-----------|
| `test_correlation_id_propagated_to_backend` | Call tool with correlation_id | Backend receives X-Correlation-ID header |
| `test_correlation_id_in_backend_logs` | Call tool, check backend logs | Log entry contains correlation_id |

## Verification

After deployment:

**CORS:**
1. **Widget test:** Open ChatGPT, invoke Clarity tool, verify widget renders
2. **Browser devtools:** Check network tab, verify `Access-Control-Allow-Origin` is NOT `*`
3. **MCP Inspector:** Verify still works in dev mode (localhost allowed)
4. **Curl tests:**
   ```bash
   # Should return specific CORS header (not *)
   curl -H "Origin: https://chatgpt.com" \
        -I https://priorities-guard-clarity-mcp.onrender.com/mcp
   # Verify: Access-Control-Allow-Origin: https://chatgpt.com
   
   # Should NOT return CORS header
   curl -H "Origin: https://evil.com" \
        -I https://priorities-guard-clarity-mcp.onrender.com/mcp
   # Verify: No Access-Control-Allow-Origin header
   
   # Wildcard regression check
   curl -I https://priorities-guard-clarity-mcp.onrender.com/mcp | grep -i "access-control-allow-origin"
   # Verify: Never shows "*"
   ```

**Correlation ID:**
1. Invoke Clarity tool via ChatGPT
2. Check backend Render logs for the request
3. Verify log entries contain `correlation_id` matching MCP server logs
4. Verify `X-Correlation-ID` header present in backend request logs

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CORS_ALLOWED_ORIGINS` | ChatGPT domains (dev only) | **Required in production.** Comma-separated list of allowed origins. |
| `ENV` | `development` | Set to `production` to enforce explicit CORS config and disable localhost origins |

**Production deployment checklist:**
1. Set `ENV=production`
2. Set `CORS_ALLOWED_ORIGINS` explicitly (e.g., `https://web-sandbox.oaiusercontent.com,https://chatgpt.com`)
3. Monitor for new OpenAI domains and update as needed

## Out of Scope

- Route consolidation (`/oauth/focused` → `/oauth/pg`)
- Env var renaming (`FOCUSED_*` → generic)
- Shared auth extraction to `mcp_server/common/`
- Path-qualified issuer
- Focused MCP server CORS (no widgets, not needed)

## Notes

**CORS:**
- Starlette's CORSMiddleware handles preflight (OPTIONS) automatically — can return 200 or 204
- `allow_credentials=False` is correct — we use Authorization header, not cookies
- The widget sandbox domain is required because that's where ChatGPT renders iframes
- OpenAI may add subdomains without notice — explicit production config prevents silent breakage
- Never hard-code allowed origins as "known good" — always require operator to set them

**Correlation ID:**
- Backend already has `CorrelationIDMiddleware` that accepts `X-Correlation-ID`
- MCP server generates correlation IDs in tool handlers — just need to pass them through
- Enables end-to-end request tracing: ChatGPT → MCP → Backend
- ~10 lines of code total across persistence.py and tool handlers