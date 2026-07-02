# Increment MindSort-Claude-OAuth-AS-Fix: root-issuer `authorization_servers` (minimal)

**Status:** Confirmed blocker. After the backend redeploy (which activated the Claude redirect URIs), the MindSort-Claude connector STILL fails DCR with the same "Couldn't register with the sign-in service" error. That confirms a second, independent defect: protected-resource discovery advertises a path-qualified authorization server, so Claude's RFC 8414 discovery chain misresolves.

**This increment is the MINIMAL fix to unblock and confirm the hypothesis.** A follow-up hardening increment (inc_05b) adds PG's structural parity (`OAUTH_ISSUER_BASE` + same-origin guard) — but ONLY after this confirms Claude connects. We harden a proven fix, not an unproven one.

**Scope:** ONLY `mcp_server/mindsort_claude/discovery_dupl.py` + that service's tests. NO config.py change. NO new env var. NO touching `clarity/`, `priority_guardian*/`, backend, or OpenAI code. Roll independently.

---

## Root cause (verified at source)

Claude connect = RFC 9728 + RFC 8414 discovery + RFC 7591 DCR:
1. read `…/.well-known/oauth-protected-resource` → take `authorization_servers[0]`
2. fetch `{authorization_servers[0]}/.well-known/oauth-authorization-server`
3. POST to that document's `registration_endpoint`

`mcp_server/mindsort_claude/discovery_dupl.py` → `oauth_protected_resource()` currently returns:
```python
"authorization_servers": [OAUTH_ISSUER_URL],   # = https://www.priority-guard.com/oauth/pg  (PATH-QUALIFIED — WRONG)
```
The backend AS declares `issuer = https://www.priority-guard.com` (root, no path — enforced by backend `validate_production_urls`). RFC requires `authorization_servers[]` to match the AS's self-declared issuer. Root ≠ path → Claude builds `…/oauth/pg/.well-known/oauth-authorization-server`, which does not resolve as the DCR flow expects → registration fails.

**Proven reference:** PG-Claude connects to Claude. Its `oauth_protected_resource()` advertises the ROOT issuer. MindSort must do the same.

**Minimal fix:** MindSort-Claude config ALREADY has a root-issuer value: `CLARITY_ISSUER` (= `https://www.priority-guard.com`, default; the JWT `iss` claim value; already imported in `discovery_dupl.py`). Use it for `authorization_servers`. This mirrors PG's *behavior* (root issuer advertised) with zero new config surface and zero new env var.

**Why not add `OAUTH_ISSUER_BASE` now:** that is PG's full structural form and is the right END state, but it adds a new required env var and a fail-fast guard. Adding it before the root-issuer hypothesis is confirmed means changing more than one thing while the fix is still unproven. If this minimal change does NOT fix the connection, a one-line diff gives the cleanest possible signal that root-issuer was not the whole story. Hardening (inc_05b) follows confirmation.

---

## Canonical guidance (read fresh)
- `doc/Claude_Compliance/claude_connectors_compliance_master.md`
- `doc/Claude_Compliance/structural_guideline_claude_vs_openai_MindSortAI.md`
- `doc/OPERATIONS_PREDEPLOY.md` → OAuth Discovery Sanity Check + the "MindSort Claude MCP — Deploy Runbook" section.
- Behavior reference: `mcp_server/priority_guardian_claude/discovery_dupl.py` (`oauth_protected_resource` advertises root).

---

## Required change (Copy and Adjust, Never Rewrite)

### `mcp_server/mindsort_claude/discovery_dupl.py`
- In `oauth_protected_resource()`: change `"authorization_servers": [OAUTH_ISSUER_URL]` → `"authorization_servers": [CLARITY_ISSUER]`.
- `CLARITY_ISSUER` is already imported in this file — confirm the import line includes it; if not, add it to the existing `from ...config import (...)` block. Do NOT add new config values.
- Leave `openid_configuration()` and `oauth_authorization_server()` exactly as they are: their endpoint URLs are built from `OAUTH_ISSUER_URL` (`…/oauth/pg/authorize` etc.) — correct; their `issuer` fields already use `CLARITY_ISSUER` (root) — correct.
- **Replace the `DEFERRED` comment block** above `oauth_protected_resource()` with a note recording: (a) the Claude-side `authorization_servers` now advertises the root issuer to satisfy Claude's DCR discovery; (b) this does not violate Canonical Product Rule §0 because this is the platform-coupled `_dupl` Claude file and the ChatGPT server (`clarity/discovery.py`) is untouched and retains its behavior; (c) the structural hardening (dedicated `OAUTH_ISSUER_BASE` + same-origin guard, mirroring PG) is tracked as a follow-up (inc_05b) to run after the connection is confirmed.

---

## What NOT to do
- No `config.py` change, no new env var (that is inc_05b).
- No `/oauth/pg` → `/oauth/mindsort` switch (that is inc_07, consent-screen branding).
- No change to `CLARITY_ISSUER`/`CLARITY_AUDIENCE`/`OAUTH_ISSUER_URL` definitions.
- Nothing outside `mcp_server/mindsort_claude/`.

---

## Tests

### Unit (no network) — each with "what bug would still pass it?"
1. **`authorization_servers` is the root issuer** — assert `oauth_protected_resource()["authorization_servers"] == [CLARITY_ISSUER]` AND `urlparse(authorization_servers[0]).path in ("", "/")` (no path component). *Catches:* regression to the path-qualified `OAUTH_ISSUER_URL` — the exact defect being fixed. (The path-component assertion is what makes the test meaningful: asserting only `== [CLARITY_ISSUER]` would still pass if someone later pointed CLARITY_ISSUER at a path, so assert no-path explicitly.)
2. **AS-metadata endpoints remain path-qualified** — assert `oauth_authorization_server()` and `openid_configuration()` return `authorization_endpoint`/`token_endpoint`/`jwks_uri`/`registration_endpoint` each containing `/oauth/pg/`. *Catches:* an over-correction that roots the endpoint URLs too (which would break the actual OAuth calls Claude makes after discovery).
3. **`issuer` fields are root** — assert the `issuer` in both AS-metadata functions == `CLARITY_ISSUER`. *Catches:* accidentally swapping issuer to the path value.

### Integration (separate) — the assertion that maps to the production failure
4. **Discovery chain resolves to root well-known** — take `oauth_protected_resource()["authorization_servers"][0]`, construct `{that}/.well-known/oauth-authorization-server`, assert it equals `https://www.priority-guard.com/.well-known/oauth-authorization-server` (root-based), NOT `…/oauth/pg/.well-known/…`. *Catches:* any reintroduction of a path-qualified AS that field-level unit tests might miss.

---

## Production readiness (increment scope)
- Scalability / GDPR / latency: none (static discovery dict, one value changed).
- Security: neutral at this step (hardening guard comes in inc_05b).

## Definition of Done
- [ ] `discovery_dupl.py`: `oauth_protected_resource()` advertises `[CLARITY_ISSUER]`; AS-metadata endpoints unchanged (`/oauth/pg/*`); `issuer` fields unchanged (root); `DEFERRED` comment replaced with the fix-record note.
- [ ] No `config.py` change; no new env var; nothing outside `mcp_server/mindsort_claude/`.
- [ ] Unit tests 1–3 + integration test 4 pass.
- [ ] Full `pytest tests/unit/ --ignore=tests/unit/mcp_focused -q`: known-5 baseline unchanged, no new failures.
- [ ] Before commit: read `doc/OPERATIONS_PREDEPLOY.md` (OAuth Discovery Sanity Check + MindSort runbook); confirm no additional pre-deploy task.

## Post-deploy verification (deployer; not Claude Code)
No env var to set — redeploy the MindSort Claude MCP service, then:
```bash
curl https://mindsort-mcp.priority-guard.com/.well-known/oauth-protected-resource
#   "authorization_servers[0]" == https://www.priority-guard.com   (ROOT, not .../oauth/pg)
#   "resource"                 == https://mindsort-mcp.priority-guard.com/mcp
curl https://www.priority-guard.com/.well-known/oauth-authorization-server
#   "issuer" == https://www.priority-guard.com ; "registration_endpoint" present
```
Then: delete + re-add the MindSort connector in Claude, new conversation, retry connect.
- **Connects** → hypothesis confirmed. Proceed to inc_06 (both-platform verify), then inc_05b (hardening).
- **Same "couldn't register"** → root-issuer was not the (whole) cause. One line changed, so signal is clean: pull backend logs for the `/oauth/*/register` request + response and report. Do NOT pile on more changes.
- **New error later in the flow** → progress; report the new error.

## Not verified by this briefing (state in review)
- That root-issuer `authorization_servers` is *sufficient* for Claude DCR. It is the verified diff vs. the working PG connector and matches the OPERATIONS path-prefix invariant — but the empirical proof is PG actually connecting in Claude. Treated as a strong hypothesis; the post-deploy retry + backend logs are the confirmation.
