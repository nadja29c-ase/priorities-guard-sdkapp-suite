# Documented Pattern: MindSort-OpenAI — Tool-Level OAuth (Anonymous Handshake)

**Date documented:** 2026-07-04
**Status:** Official pattern per OpenAI Apps SDK auth documentation.
**Affects:** MindSort-OpenAI MCP server (`mindsort.priority-guard.com`)
**Contrast:** PG-OpenAI uses transport-level 401 pattern (the other official option).
**Submission impact:** None — this is one of two officially documented patterns.

---

## Plain-language summary

MindSort-OpenAI returns HTTP 200 (not 401) when receiving an unauthenticated POST to `/mcp`. This is the **tool-level OAuth pattern** per OpenAI Apps SDK: the MCP initialize/tools-list handshake succeeds without a token, but actual tool calls (`tools/call`) are scope-protected and return `_meta["mcp/www_authenticate"]` challenges.

Per [OpenAI Apps SDK Auth Documentation](https://developers.openai.com/apps-sdk/build/auth), two patterns are officially supported:
1. **Transport-level 401** — Unauthenticated requests to `/mcp` receive 401 + `WWW-Authenticate` header (used by PG-OpenAI)
2. **Tool-level OAuth** — Anonymous handshake allowed; per-tool `securitySchemes` metadata triggers auth UI (used by MindSort-OpenAI)

Both patterns are valid; MindSort-OpenAI implements pattern #2.

**Security assessment:** No data-access hole. The 200 response only confirms handshake capability. All tool dispatch goes through `authenticate_request()` → `enforce_tool_scope()`, which fails closed on missing/invalid tokens and returns `mcp/www_authenticate` with resource_metadata pointer.

---

## Evidence (2026-07-02 triage)

### Probe 1: Empty body without token → 400 (not 401)

```bash
curl -s -X POST https://mindsort.priority-guard.com/mcp \
  -H "Content-Type: application/json" \
  -d '' \
  -w "\nHTTP %{http_code}\n"
```

**Result:** HTTP 400 (empty body parse error) — but NOT 401, which is the quirk.

### Probe 2: Initialize with garbage token → 200 OK (handshake-before-auth)

```bash
curl -s -X POST https://mindsort.priority-guard.com/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer garbage-token" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{},"id":1}'
```

**Result:** HTTP 200 with valid MCP initialize response. Token is not validated until tool dispatch.

### Probe 3: tools/call with garbage token → 200 with isError + mcp/www_authenticate

```bash
curl -s -X POST https://mindsort.priority-guard.com/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer garbage-token" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"organize_thoughts","arguments":{}},"id":2}'
```

**Result:**
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "content": [{"type": "text", "text": "Authentication required..."}],
    "isError": true,
    "_meta": {
      "mcp/www_authenticate": ["Bearer resource_metadata=\"...\", error=\"invalid_token\"..."]
    }
  }
}
```

**Conclusion:** Scope enforcement is operational. The 401-probe test failure is a test-shape issue, not a security gap.

---

## Contrast with PG-Claude

| Behavior | MindSort-OpenAI | PG-Claude |
|----------|-----------------|-----------|
| Unauthenticated POST /mcp | 200 (handshake OK) | 401 + WWW-Authenticate |
| Pattern name | Handshake-before-auth | Presence-gate |
| Auth check timing | At tool dispatch | At /mcp middleware |
| Security model | Equivalent | Equivalent |

PG-Claude uses `BearerAuthMiddleware` to gate all `/mcp` requests before they reach the MCP layer. MindSort-OpenAI lets the MCP handshake through and enforces auth at tool dispatch. Both are valid implementations of RFC 9728 / OpenAI MCP Authentication.

---

## Test handling

The live suite test `test_post_mcp_returns_401_with_www_authenticate` is marked `xfail(strict=True)` for the `mindsort_openai` parametrization:

```python
pytest.param(
    "mindsort_openai",
    marks=pytest.mark.xfail(
        strict=True,
        reason=(
            "MindSort-OpenAI accepts unauthenticated initialize (handshake-before-auth); "
            "tools are scope-protected — triaged 2026-07-02, see doc/OAuth/platform_quirk_mindsort_openai_401.md; "
            "revisit at OpenAI resubmission."
        ),
    ),
),
```

`strict=True` ensures that if MindSort-OpenAI starts returning 401 (e.g., after adding a presence-gate), the test will XPASS and fail the suite, forcing conscious removal of the marker.

---

## Resubmission checklist (verified 2026-07-04)

Prior to MindSort-OpenAI resubmission, confirm:

1. **securitySchemes metadata** — VERIFIED: `clarity/tools/__init__.py` emits per-tool `securitySchemes: [{type: "oauth2", scopes: [...]}]` in `_meta`. This is the metadata half of tool-level OAuth.

2. **redirect-URI allowlist** — VERIFIED: `backend/core/config.py` line 58 has `"https://chatgpt.com/connector/oauth/"` (prefix match), supporting the new `{callback_id}` pattern per OpenAI March 2026 docs.

3. **Runtime _meta challenge** — VERIFIED: `authenticate_request()` returns `mcp/www_authenticate` with resource_metadata on auth failure.

All three verified — pattern is compliant with OpenAI Apps SDK auth documentation.
