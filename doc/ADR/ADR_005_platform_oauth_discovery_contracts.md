# ADR 005 — Platform OAuth Discovery Contracts

**Date:** July 2026
**Status:** Accepted
**Context:** OAuth discovery endpoints across four MCP servers (PG-OpenAI, MindSort-OpenAI, PG-Claude, MindSort-Claude) and one backend Authorization Server

---

## Decision

One Authorization Server, one issuer (`https://www.priority-guard.com`), forever. Each MCP server (Resource Server) exposes a **platform-specific discovery facade** tailored to its platform's OAuth client behavior. Discovery shape is platform-coupled by design and MUST NOT be consolidated across the platform boundary.

The backend mints all JWTs with:
- `iss` = `settings.OAUTH_ISSUER` (always `https://www.priority-guard.com`)
- `aud` = `resource` parameter if provided, else `settings.OAUTH_ISSUER`

See `backend/core/oauth_provider/jwt/utils.py:64-70`.

---

## The Three Discovery Shapes

| # | Server | `authorization_servers` | token/jwks/register location | Constraint satisfied |
|---|---|---|---|---|
| 1 | PG-OpenAI (`mcp_server/priority_guardian/`) | RS origin (`pg.priority-guard.com`) | RS origin (same-origin proxy routes → backend); authorize on www | ChatGPT requires origin-coherent AS-discovery→token chain; token `iss` must stay www |
| 2 | MindSort-OpenAI (`mcp_server/clarity/`) | Path-qualified `https://www.priority-guard.com/oauth/mindsort` | www `/oauth/mindsort/*` (backend sub-mount, `backend/core/oauth_provider/mindsort_discovery.py`) | Same ChatGPT constraint, solved with a self-coherent www chain; ChatGPT tolerates issuer(root) ≠ discovery path |
| 3 | PG-Claude + MindSort-Claude (`*_dupl` files) | Root `https://www.priority-guard.com` | www `/oauth/pg/*` (root AS metadata, `backend/core/oauth_provider/discovery.py`) | Claude's RFC 8414/9728-literal discovery: `authorization_servers` must be the AS issuer root |

### Why Shape #1 is mixed-origin (PG-OpenAI)

ChatGPT discovers the AS via `authorization_servers`, then calls `token_endpoint`, `jwks_uri`, and `registration_endpoint` on that **same origin**. The working shape:

```
issuer                 = https://www.priority-guard.com            # matches token iss claim
authorization_endpoint = https://www.priority-guard.com/oauth/pg/authorize  # browser popup, no same-origin need
token_endpoint         = https://pg.priority-guard.com/oauth/token     # same-origin proxy route
jwks_uri               = https://pg.priority-guard.com/oauth/jwks       # same-origin proxy route
registration_endpoint  = https://pg.priority-guard.com/oauth/register  # same-origin proxy route
authorization_servers  = [https://pg.priority-guard.com]               # ChatGPT discovers AS at RS origin
```

If you consolidate all endpoints to www "for consistency," ChatGPT silently abandons the connection after OAuth completes — the exact regression of commit `5854d50` (2026-06-30).

### Why Shape #2 uses path-qualified issuer (MindSort-OpenAI)

MindSort-OpenAI needed an app-specific OAuth chain without cross-origin proxying. The backend mounts a dedicated discovery document at `/oauth/mindsort/.well-known/oauth-authorization-server` (via `mindsort_discovery.py`). This gives MindSort a self-coherent www chain: `authorization_servers` points at `https://www.priority-guard.com/oauth/mindsort`, and all endpoints are under that same path. ChatGPT tolerates `issuer` (root) differing from the discovery path.

### Why Shape #3 uses root issuer (Claude servers)

Claude's MCP OAuth flow follows RFC 8414/9728 literally: `authorization_servers` must match the AS's self-declared `issuer` (root). A path-qualified `authorization_servers` causes Claude DCR to fail. The Claude servers advertise `authorization_servers: [https://www.priority-guard.com]` and point at the backend's root discovery (`/.well-known/oauth-authorization-server`).

---

## The Binding Rule

**Any change to a discovery module or its config requires reproducing the affected platform's full live connect flow (delete-and-re-add the connector) before merge.**

This is not optional. The production incident (2026-06-30, commit `5854d50`) demonstrated that discovery changes that look correct in isolation can silently break the OAuth flow in ways that only manifest at runtime. See `claude increments/SHARED ARCHITECTURE/hotfix_pg_openai_discovery_restore.md` for the incident record.

---

## Rejected Alternatives (with revisit triggers)

### Separate Claude AS

**Rejected.** A second Authorization Server would require:
- A second signing key and JWKS
- A second client and token store
- A second consent flow
- Doubled GDPR surface (data subject rights across two stores)

The single-issuer invariant is enforced at the signer (`jwt/utils.py`). Claude needs nothing the shared AS cannot provide.

**Revisit:** Never, absent a platform requirement the shared AS cannot meet.

### Dedicated auth subdomain issuer (e.g., `auth.priority-guard.com`)

**Rejected.** This is the greenfield-correct shape but would:
- Invalidate all live tokens
- Force re-consent from all connected users
- Risk re-review of approved connectors
- Deliver zero user value

**Noted:** This is what a from-scratch implementation would choose. Not viable for a running system with live connectors.

### Converging both OpenAI apps on the path-qualified shape ("Option B")

**Deferred.** MindSort-OpenAI uses Shape #2 (path-qualified), PG-OpenAI uses Shape #1 (mixed-origin). Converging PG to Shape #2 would:

1. Require building `/oauth/pg/.well-known/oauth-authorization-server` in the backend — **this does not exist today** (`/oauth/pg` has no `.well-known` sub-mount; only `/oauth/mindsort` has one)
2. Require a full ChatGPT reconnect reproduction on a **live approved connector** (PG is in the GPT Store)

**Trigger:** Demonstrated maintenance churn in the OpenAI discovery twins. Until then, the mixed-origin shape works and is protected by contract tests.

---

## Cross-References

| Document | Relationship |
|----------|--------------|
| `doc/ADR/ADR_003_oauth_provider_route_scope_mapping.md` | Adjacent: route→scope registry. Non-overlapping. |
| `doc/OAuth/OAuth_Hard_Requirements.md` | AS-side requirements (amended to remove stale "one discovery document" claim) |
| `doc/Claude_Compliance/structural_guideline_claude_vs_openai.md` | Platform boundary documentation (amended to note discovery shape divergence) |
| `claude increments/SHARED ARCHITECTURE/hotfix_pg_openai_discovery_restore.md` | Incident record — the "why" for this ADR |
| `backend/core/oauth_provider/jwt/utils.py` | Single-issuer enforcement point |
| `backend/core/oauth_provider/discovery.py` | Root AS metadata (Claude servers point here) |
| `backend/core/oauth_provider/mindsort_discovery.py` | MindSort-specific AS metadata (Shape #2) |

---

## Trigger for Revisiting

Revisit this ADR if:

1. A platform changes its OAuth discovery behavior in a way that invalidates the current shapes
2. Option B becomes necessary due to maintenance burden in the OpenAI discovery twins
3. A new platform is added with discovery requirements neither shape satisfies

Do NOT revisit for "consistency" or "tidiness" — those motivations caused the 5854d50 regression.

---

## What Claude Code Must Know

1. **Discovery shape is platform-coupled.** Never apply a change from one platform's discovery file to another without verifying the target platform's OAuth flow end-to-end.

2. **The three shapes exist for functional reasons.** Shape #1's mixed-origin is not a bug. Shape #2's path-qualified issuer is not inconsistent. Shape #3's root issuer is not lazy.

3. **Contract tests exist.** `tests/unit/oauth_discovery/test_oauth_discovery_contracts.py` locks all three shapes. A consolidation attempt will fail CI before it fails production.

4. **The binding rule is real.** If you modify any discovery module, you must reproduce the affected platform's connect flow (delete-and-re-add) before merge. "It still returns JSON" is not verification.

5. **`/oauth/pg/.well-known/*` does not exist.** Only `/oauth/mindsort` has a `.well-known` sub-mount. If Option B is pursued, that mount must be built first.

6. **Unit tests catch code-shape regressions; live tests catch env-value regressions.** The unit tests run against dev-default config values and verify the discovery code emits the correct URL structure. They do NOT verify production Render env vars are correct. Env-value regressions (e.g., production `CLARITY_OAUTH_ISSUER_URL` reset to `/oauth/pg`) are caught only by the live suite (`tests/integration/oauth_discovery/`), which must be run pre-deploy/pre-submission: `pytest -m live tests/integration/oauth_discovery/ -v`.

---

## Files Affected

| File | Role |
|------|------|
| `mcp_server/priority_guardian/discovery.py` | Shape #1 (PG-OpenAI, mixed-origin) |
| `mcp_server/clarity/discovery.py` | Shape #2 (MindSort-OpenAI, path-qualified) |
| `mcp_server/priority_guardian_claude/discovery_dupl.py` | Shape #3 (PG-Claude, root issuer) |
| `mcp_server/mindsort_claude/discovery_dupl.py` | Shape #3 (MindSort-Claude, root issuer) |
| `backend/core/oauth_provider/discovery.py` | Root AS metadata (Shape #3 points here) |
| `backend/core/oauth_provider/mindsort_discovery.py` | MindSort AS metadata (Shape #2 points here) |
| `tests/unit/oauth_discovery/test_oauth_discovery_contracts.py` | Contract tests locking all shapes |
