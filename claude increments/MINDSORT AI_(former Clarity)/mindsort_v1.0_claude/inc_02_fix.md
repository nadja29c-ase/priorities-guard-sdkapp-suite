# MindSort-Claude-02b: Discovery Fix (Codex Review Response)

**Goal:** Fix the one confirmed defect from the Codex adversarial review of Claude-01/02 — `oauth_protected_resource` ignoring the configured `MCP_RESOURCE_URL`. Add a regression test. Document (do NOT fix) the second Codex finding, which is a MindSort-wide concern out of scope for the Claude port.

**Scope:** `mcp_server/mindsort_claude/discovery_dupl.py` + tests only. Zero touches to `clarity/`, `backend/`, or `config.py` logic.

---

## Background — what the codebase verification established

The Codex review raised two findings. Verification against the actual codebase (PG Claude discovery, backend `core/oauth_provider/discovery.py`, `backend/core/config.py`, and `clarity/discovery.py`) produced this verdict:

**Codex Finding 2 (resource URL) — CONFIRMED. Fix in this increment.**
`oauth_protected_resource()` recomputes `f"{MCP_SERVER_URL}/mcp"` and ignores the configured `MCP_RESOURCE_URL`. In the default case they're equal, so it works today — but the config knob is silently ignored. If the deployed resource is ever not exactly `{origin}/mcp`, the resource claim and the `ui.domain` hash diverge. PG Claude correctly returns `MCP_RESOURCE_URL`. Fix to match PG.

**Codex Finding 1 (AS "same-origin") — REJECTED as diagnosed. Do NOT apply Codex's recommendation.**
Codex recommended pointing `issuer`/`authorization_servers` at the MCP-server origin. This is **wrong** and would break OAuth: the backend (`core/config.py`) sets `OAUTH_ISSUER = https://www.priority-guard.com` (root domain, AS), which is intentionally a *different* origin from the MCP server (RS). This is correct RFC 9728 AS/RS separation. Pointing `authorization_servers` at the MCP origin would reference an origin with no authorization server behind it → DCR failure. The MCP-origin OAuth proxy routes in `server_dupl.py` are a same-origin *convenience surface*, not where discovery must point.

There IS a real sub-issue inside Finding 1 (see "Deferred" below), but it is **MindSort-wide** (the in-review ChatGPT server `clarity/` has the identical behavior) and must NOT be fixed Claude-only.

---

## Pre-Implementation

Read `doc/OPERATIONS_PREDEPLOY.md`. No migrations.

---

## The Fix — `discovery_dupl.py`

**One change.** In `oauth_protected_resource()`, return the configured `MCP_RESOURCE_URL` instead of recomputing.

Add `MCP_RESOURCE_URL` to the config import:
```python
from mcp_server.mindsort_claude.config import (
    CLARITY_ISSUER,
    MCP_SERVER_URL,
    MCP_RESOURCE_URL,   # add
    OAUTH_ISSUER_URL,
    SCOPES_SUPPORTED,
)
```

Change the resource value:
```python
async def oauth_protected_resource():
    """OAuth 2.0 Protected Resource Metadata (RFC 9728)."""
    return {
        "resource": MCP_RESOURCE_URL,          # was: f"{MCP_SERVER_URL}/mcp"
        "authorization_servers": [OAUTH_ISSUER_URL],
        "scopes_supported": SCOPES_SUPPORTED,
    }
```

`MCP_SERVER_URL` may become unused in the imports after this change — if so, remove it from the import to keep it clean (verify it's not used elsewhere in the file first; it is not, in the current version).

**Do NOT change** `openid_configuration()` or `oauth_authorization_server()` in this increment. Their `authorization_servers`/issuer behavior is the deferred MindSort-wide item below.

---

## Deferred (document in code comment, do NOT fix here)

Add this comment above `oauth_protected_resource()` so the deferred concern is recorded at the relevant site:

```python
# DEFERRED (MindSort-wide, post-OpenAI-review): authorization_servers advertises
# OAUTH_ISSUER_URL (path-qualified, .../oauth/pg) while the backend AS declares
# issuer = https://www.priority-guard.com (root, no path). RFC 8414/9728 expect the
# authorization_servers entry to match the AS's self-declared issuer. The in-review
# ChatGPT server (clarity/discovery.py) has the IDENTICAL behavior, so this is shared
# MindSort behavior, not a Claude-port defect. Fixing it Claude-only would diverge from
# ChatGPT MindSort (violates Canonical Product Rule §0) and is an unverified change to
# the OAuth surface. Evaluate for BOTH platforms together after OpenAI review clears,
# with a real OAuth client test. Do not fix in isolation.
```

**Why deferred, not fixed:** the `authorization_servers` path-qualification is shared with `clarity/` (in OpenAI review). Changing it in the Claude port only would (a) make Claude OAuth metadata diverge from the ChatGPT version that is presumably passing review, and (b) be an unverified change to the most consequential surface based on a spec-reading rather than an observed failure. Per the standing rule — never "fix" without a confirmed, reproduced defect — this requires an explicit cross-platform decision and a live OAuth test, not a Claude-only edit now.

---

## What NOT to Touch

- `clarity/` — in OpenAI review.
- `backend/` — the AS config (`OAUTH_ISSUER`, the `/oauth/mindsort` and `/oauth/pg` surfaces) is authoritative and out of scope.
- `config.py` logic — `MCP_RESOURCE_URL` already exists and is correctly defined; just consume it.
- `openid_configuration()` / `oauth_authorization_server()` — deferred item.
- The OAuth proxy routes and middleware in `server_dupl.py` — unrelated to this fix.

---

## Tests

Add to `tests/unit/mcp_claude_mindsort/test_scaffold.py`. Do NOT modify existing tests or the `restore_mcp_auth_globals` fixture.

1. `test_protected_resource_honors_configured_resource_url` —
   Set `CLARITY_CLAUDE_MCP_SERVER_URL=https://origin.example` and
   `CLARITY_CLAUDE_MCP_RESOURCE_URL=https://resource.example/custom`, reload
   `mindsort_claude.config` then `mindsort_claude.discovery_dupl`, call
   `oauth_protected_resource()`, assert `result["resource"] == "https://resource.example/custom"`
   (NOT `https://origin.example/mcp`). This is exactly the case Codex verified as broken.
   Use the same reload-isolation discipline as `test_config_isolation`; the autouse
   `restore_mcp_auth_globals` fixture already restores `clarity` globals, but ensure
   this test also restores/reloads `mindsort_claude.config` and `discovery_dupl` to
   their default-env state on exit (reload with the monkeypatched env removed), so it
   does not leak the custom resource value into later tests.

2. `test_protected_resource_default_is_origin_plus_mcp` —
   With default dev env (no override), `oauth_protected_resource()["resource"]`
   ends with `/mcp` and equals `{MCP_SERVER_URL}/mcp`. Confirms the default path
   still behaves correctly after the change.

3. `test_protected_resource_unchanged_fields` —
   `authorization_servers` and `scopes_supported` are unchanged by this fix
   (`authorization_servers == [OAUTH_ISSUER_URL]`, `scopes_supported == ["clarity.write"]`).
   Guards against accidental scope of the edit.

Run the FULL `tests/unit/` suite afterward — confirm the 5 known pre-existing failures
are unchanged and no new failure appears. The existing `test_oauth_protected_resource`
scaffold test (asserts `resource` ends with `/mcp`) must still pass.

---

## Definition of Done

- [ ] `oauth_protected_resource()` returns `MCP_RESOURCE_URL`; `MCP_RESOURCE_URL` imported.
- [ ] Deferred-concern comment present above `oauth_protected_resource()`.
- [ ] `openid_configuration()` / `oauth_authorization_server()` unchanged.
- [ ] 3 new tests pass; existing `test_oauth_protected_resource` still passes.
- [ ] Full `tests/unit/` suite: 5 known failures only, no new ones.
- [ ] Zero changes to `clarity/`, `backend/`, `config.py` logic, `server_dupl.py`.

---

## Note for the implementer

This increment intentionally fixes only ONE of the two Codex findings. The other is documented as deferred, by design — not an oversight. If the reload-based resource test proves flaky in the full-suite run (state leak), report it before forcing a workaround; do not weaken the assertion.