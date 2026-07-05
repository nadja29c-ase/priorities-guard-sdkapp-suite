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

---

## Evidence record (2026-07-04)

This section persists the investigation findings to prevent re-running the same audit.

### Per-app aud distribution (DB query on oauth_access_tokens)

| Row | App / resource pattern | Active | Revoked | Observation |
|-----|------------------------|--------|---------|-------------|
| 1 | MindSort-Claude (`mindsort-mcp.../mcp`) | 1 | 0 | Current reviewer flow — healthy |
| 2 | MindSort-OpenAI (`mindsort.../mcp`) | 60 | 3 | Production load — healthy |
| 3 | PG-OpenAI (`pg.../mcp`) | 125 | 36 | Production load — healthy |
| 4 | PG-Claude (`mcp.priority-guard.com/mcp`) | 41 | 1 | Production load — healthy |
| 5 | PG-Claude onrender (`priorities-guard-sdkapp-suite-6jri.onrender.com/mcp`) | 9 | 0 | Zombie legacy tokens — see below |

**Key finding:** Zero NULL-resource rows. ALL tokens carry `/mcp`-qualified `aud`. Both OpenAI and Claude clients always send `resource=` in authorize requests; the "falls-back-to-issuer" code path does not exist in production.

### Row 5 analysis (legacy zombie tokens)

The 9 active tokens with onrender `aud` are pre-custom-domain artifacts:
- They exist because the PRM advertised the onrender resource URL before `PG_CLAUDE_MCP_RESOURCE_URL` was set to the custom domain.
- Refresh carry-forward (`resource=matching_token.resource` in token refresh flow) preserves the stale `aud` indefinitely.
- These tokens FAIL validation today (onrender aud ∉ valid_audiences list) but their refreshes succeed (refresh doesn't validate aud, just carries it forward).
- **Impact:** A zombie client 401s on every tool call and re-mints broken tokens forever. Harmless to review; mildly noisy in auth logs.
- **Cleanup:** Find and delete/re-add the stale Claude client config, or `UPDATE oauth_access_tokens SET revoked = true WHERE resource LIKE '%onrender%' AND revoked = false;`.

### CLARITY_AUDIENCE env compensation

Production deploys set `CLARITY_AUDIENCE` / `CLARITY_CLAUDE_AUDIENCE` to the **resource URL** (e.g., `https://mindsort.priority-guard.com/mcp`), not the issuer URL the code defaults imply. This is correct — it matches what tokens actually carry. The code defaults remain issuer-shaped for local dev; production env compensation is the source of truth.

### Verified code artifacts

1. **securitySchemes metadata** — `clarity/tools/__init__.py:58-62` emits per-tool `securitySchemes: [{type: "oauth2", scopes: [...]}]` in `_meta`.

2. **redirect-URI allowlist** — `backend/core/config.py:58` includes `"https://chatgpt.com/connector/oauth/"` (prefix match), supporting `{callback_id}` pattern per OpenAI March 2026 docs.

3. **Runtime _meta challenge** — `authenticate_request()` returns `mcp/www_authenticate` with resource_metadata on auth failure (fail-closed).

4. **MCP_RESOURCE_URL in valid_audiences** — Commit `ef7f554` added `MCP_RESOURCE_URL` to the three-form audience list, making token validation match production token shape.

---

## Incident record: MindSort-Claude silent persistence failure (2026-07-05)

This section documents a distinct incident discovered during the OAuth audit.

### Root cause (100% confirmed)

`mcp_server/clarity/persistence.py` imports `BACKEND_URL` from `clarity/config.py`, which reads env var `CLARITY_BACKEND_URL`. MindSort-Claude's Render service set only `CLARITY_CLAUDE_BACKEND_URL` (correct value, read by nothing in the persistence path). The `mcp_auth_dupl.py` shim rebinds auth globals only — `BACKEND_URL` is not in its contract.

Result: `BACKEND_URL` silently fell to the dev default (`http://localhost:8000`) **in production**, and every persist/retrieve operation since first deploy connected to a port on the container where nothing listens.

### Failure masking

`organize_thoughts` logged `auto_persisted` unconditionally after calling `persist_cluster`, even when `persist_cluster` returned `None` (failure). The `persist_cluster` function catches all exceptions internally and returns `None` instead of raising, so the calling code's try/except never triggered. Users saw success responses while their data was silently discarded.

### Affected window

- **Start:** First MindSort-Claude deploy (date: deployment day)
- **End:** 2026-07-05 hotfix applied (`CLARITY_BACKEND_URL=https://www.priority-guard.com`)

### Data impact (GDPR statement)

During the affected window, MindSort-Claude boards were never persisted:
- **Data stored:** None (persist operations failed silently)
- **Data at risk:** None (nothing was written)
- **Affected users:** 1 (Nadja only — pre-submission, no external users)
- **Retention impact:** N/A (no data to retain or delete)

This incident occurred entirely pre-submission. No external user data was affected.

### Why this survived audits

Five audits, two adversarial reviewers, and a full compliance read all passed because:
1. Unit tests mock persistence — they don't call production endpoints
2. Integration tests use test databases — they don't touch production
3. No live test exercised an authenticated persist roundtrip with a real token
4. The `auto_persisted` log message falsely indicated success

**Evidence beats review, every time it's available.**

### Remediation

1. **Hotfix (immediate):** Add `CLARITY_BACKEND_URL=https://www.priority-guard.com` to MindSort-Claude Render env — applied 2026-07-05.

2. **D1 — Production guard:** `clarity/config.py` now fails at boot if `CLARITY_BACKEND_URL` contains `localhost` in production. The guard comment documents this incident.

3. **D2 — Truthfulness fix:** `organize_thoughts`, `edit_board`, `start_prioritization_flow` now check `persist_cluster` return value. If `None`, they log `persist_returned_none` and return error with `assistant_guidance` telling the model to inform the user their board was NOT saved.

4. **D3 — Namespace contract:** `mcp_auth_dupl.py` header now documents that `CLARITY_BACKEND_URL` and `INTERNAL_API_SECRET` are NOT rebound and must be set per-service.

5. **D4 — Live roundtrip test:** `tests/integration/clarity/test_live_persist_roundtrip.py` exercises authenticated persist + retrieve against production. Requires token via env var; skipped if not provided.

### Lesson

This is Codex finding #2 materialized: "BACKEND_URL still has localhost defaults that aren't rejected in production" was classified as defense-in-depth/latent in the audit. It just produced actual silent data loss on the submission app. "Latent" means "will happen" — the only question is when.
