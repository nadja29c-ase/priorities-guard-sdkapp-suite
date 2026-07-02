# Increment Briefing: inc_oauth_discovery_contracts

**Title:** Platform OAuth Discovery Contracts — ADR, contract tests, living-artifact repairs
**Date:** 2026-07-02
**Scope class:** Documentation + tests + code comments only. **Zero wire-behavior changes.** No discovery values, config values, routes, or endpoints may change.
**Spans:** Both platforms (ChatGPT + Claude) and both apps (PG + MindSort).

---

## Canonical guidance (read before starting)

ChatGPT-side context:
- `Shared Backend — Architecture, Data Flow, Storage Strategy` (project KB)
- `doc/compliance_master_1.3.26.md`
- `doc/ADR_MCP Server Implementation Standard.md`
- `doc/ADR_003_oauth_provider_route_scope_mapping.md` (directly relevant — new ADR must reference, not overlap)
- `doc/OAuth_Hard_Requirements.md` (being amended in this increment)

Claude-side context:
- `doc/Claude_Compliance/claude_connectors_compliance_master.md`
- `doc/Claude_Compliance/structural_guideline_claude_vs_openai.md` (being amended in this increment)

Operations:
- Read `doc/OPERATIONS_PREDEPLOY.md` before committing. Note: this increment requires **no production deploy** (docs, tests, comments). If services are redeployed anyway, expected wire diff is zero.

Incident context (required reading — this is the "why"):
- `claude increments/SHARED ARCHITECTURE/hotfix_pg_openai_discovery_restore.md`
- Regression commit: `5854d50`; working baseline: `5854d50~1`

---

## Background / Problem

Production incident (2026-06-30): commit 5854d50 "consolidated" PG-OpenAI's OAuth discovery endpoints from a deliberately mixed-origin shape to all-www "for consistency," breaking ChatGPT's same-origin discovery→token chain. Result: silent connect failure on a live App Store connector. Root cause was doctrinal, not technical: nothing in `doc/` records that discovery shape is **platform-coupled by design**, and `OAuth_Hard_Requirements.md` actively asserts the opposite ("One AS = one discovery document"). The only guards today are a NOTE block in one file and one rewritten unit test covering PG-OpenAI only.

There are **three intentional discovery shapes** in production, all fronting **one** Authorization Server (`iss = https://www.priority-guard.com`, minted in `backend/core/oauth_provider/jwt/utils.py`: `iss` always `settings.OAUTH_ISSUER`; `aud` = `resource` param or issuer fallback):

| # | Server | `authorization_servers` | token/jwks/register location | Constraint satisfied |
|---|---|---|---|---|
| 1 | PG-OpenAI (`mcp_server/priority_guardian/`) | RS origin (`pg.priority-guard.com`) | RS origin (same-origin proxy routes → backend); authorize on www | ChatGPT requires origin-coherent AS-discovery→token chain; token `iss` must stay www |
| 2 | MindSort-OpenAI (`mcp_server/clarity/`) | Path-qualified `https://www.priority-guard.com/oauth/mindsort` | www `/oauth/mindsort/*` (backend sub-mount, `backend/core/oauth_provider/mindsort_discovery.py`) | Same ChatGPT constraint, solved with a self-coherent www chain; ChatGPT tolerates issuer(root) ≠ discovery path |
| 3 | PG-Claude + MindSort-Claude (`_dupl` files) | Root `https://www.priority-guard.com` | www `/oauth/pg/*` (root AS metadata, `backend/core/oauth_provider/discovery.py`) | Claude's RFC 8414/9728-literal discovery: `authorization_servers` must be the AS issuer root (inc_05 evidence) |

Verified facts this increment relies on (source-verified 2026-07-02, do not re-derive from memory):
- Backend router mounted with no prefix (`backend/main.py:372`); only `/oauth/mindsort` has a `.well-known` sub-mount; **`/oauth/pg` has none**.
- Production Render env `CLARITY_OAUTH_ISSUER_URL = https://www.priority-guard.com/oauth/mindsort` (confirmed in Render dashboard) — the dev default and docstring in `mcp_server/clarity/config.py` say `/oauth/pg`, which is misleading.
- Production issuer is `www.priority-guard.com`; `OAuth_Hard_Requirements.md` says `api.priority-guard.com` (stale).

---

## Deliverables

### D1 — New ADR: `doc/ADR_005_platform_oauth_discovery_contracts.md`

Must contain (content requirements, not prose to copy):
1. **Decision:** One Authorization Server, one issuer (`https://www.priority-guard.com`), forever — per-platform **discovery façades** on each Resource Server. Discovery shape is platform-coupled by design and MUST NOT be consolidated across the platform boundary.
2. The three-shapes table above, with the *why* per shape (ChatGPT's observed stricter-than-spec same-origin chain vs Claude's RFC-literal root-issuer expectation).
3. **The binding rule:** any change to a discovery module or its config requires reproducing the affected platform's full live connect flow (delete-and-re-add) before merge. Reference the incident record.
4. **Rejected alternatives with revisit triggers:**
   - Separate Claude AS — rejected (second signing key/JWKS/client+token store/consent/GDPR surface; single-issuer invariant enforced at signer in `jwt/utils.py`; Claude needs nothing the AS lacks). Revisit: never, absent a platform requirement the shared AS cannot meet.
   - Dedicated auth subdomain issuer — rejected (invalidates all live tokens, forces re-consent, re-review risk, zero user value). Noted as the greenfield shape.
   - Converging both OpenAI apps on the path-qualified shape ("Option B") — deferred. Record the hard fact that `/oauth/pg` has **no** `.well-known` sub-mount, so Option B requires building one plus a full ChatGPT reconnect reproduction on a live approved connector. Trigger: demonstrated maintenance churn in the OpenAI discovery twins.
5. Cross-references: ADR_003 (DCR route→scope registry — adjacent, non-overlapping), `OAuth_Hard_Requirements.md` (AS-side requirements), the hotfix incident record, `structural_guideline_claude_vs_openai.md`.
6. Standard ADR format matching ADR_001–004 (Date, Status: Accepted, Context, Decision, Rationale, Trigger for Revisiting, What Claude Code Must Know, Files Affected).

### D2 — Amend `doc/OAuth_Hard_Requirements.md`

Minimal surgical edits only (Copy and Adjust, Never Rewrite — do not restructure the doc):
1. Fix issuer: `https://api.priority-guard.com` → `https://www.priority-guard.com` (both occurrences: Issuer Model section and discovery JSON example).
2. **Delete** the claim "One AS = one discovery document = one `authorization_endpoint`. This is correct and intentional." Replace with a short statement: one AS/issuer, multiple platform-specific discovery documents by design → see ADR_005. This sentence is the doctrine that legitimized 5854d50; removing it is the point.
3. Scope line: extend from "inbound: ChatGPT → Priority Guardian" to cover ChatGPT + Claude inbound, or explicitly narrow the doc to AS-side requirements with a cross-ref to ADR_005 for discovery. Either is acceptable; pick one and state it.
4. Bump version + date, add a one-line changelog note at top or bottom consistent with the doc's existing style.

### D3 — Amend `doc/Claude_Compliance/structural_guideline_claude_vs_openai.md`

Add one row to the "Shared vs. Platform-Specific — Layer Boundary" table:
`OAuth discovery shape (AS metadata / authorization_servers) — platform-specific → see ADR_005`.
No other changes to this doc.

### D4 — Contract tests: discovery-chain invariants, all four servers

**Purpose:** convert the load-bearing shapes into CI-enforced invariants so the next well-intentioned consolidation fails CI instead of production. These test the *invariant per platform*, not file contents.

**Unit tests (in-process, no network):**
Location: follow existing test layout conventions (note `tests/unit/mcp_priority_guardian/test_discovery_consistency.py` already locks shape #1 — extend/generalize rather than duplicate; it is acceptable to migrate its assertions into the new contract-test module and retire the old file, or keep both, but do not leave overlapping assertions drifting in two places).

Invariants to assert, driven by production-like config values (constraint: all four config modules read env at import time — tests must ensure the production-shaped env is actually reflected in the module under test, not the dev defaults):

Shape #1 — PG-OpenAI (`mcp_server/priority_guardian/discovery.py`):
- `authorization_servers == [MCP_SERVER_URL]` (RS origin, not www)
- `token_endpoint`, `jwks_uri`, `registration_endpoint` origins == `MCP_SERVER_URL` origin
- `issuer == OAUTH_ISSUER_BASE`; `authorization_endpoint` on `OAUTH_ISSUER_BASE`
- Regression guard: test must FAIL if all endpoints are consolidated to `OAUTH_ISSUER_BASE` (i.e., re-applying 5854d50 must break CI)

Shape #2 — MindSort-OpenAI (`mcp_server/clarity/discovery.py` + `backend/core/oauth_provider/mindsort_discovery.py`):
- RS PRM: `authorization_servers == [OAUTH_ISSUER_URL]` (path-qualified, ends `/oauth/mindsort` under production env)
- Backend mount AS metadata: all of token/jwks/register/authorize under `<issuer>/oauth/mindsort/`; `issuer` == root `settings.OAUTH_ISSUER`
- Chain coherence: origin of AS metadata endpoints == origin of the `authorization_servers` value

Shape #3 — PG-Claude + MindSort-Claude (`*_dupl.py`):
- `authorization_servers == [OAUTH_ISSUER_BASE]`, and the value is a **root** (no path/query/fragment)
- `issuer` == root issuer
- Regression guard: test must FAIL if `authorization_servers` becomes path-qualified (the pre-inc_05 bug)

Cross-cutting (all AS metadata documents, including backend root discovery):
- `code_challenge_methods_supported == ["S256"]` exactly (never `plain`) — Claude refuses without it; `OAuth_Hard_Requirements.md` §9 forbids `plain`
- `response_types_supported == ["code"]`; grant types exactly `authorization_code` + `refresh_token`
- PRM `resource` == the configured `MCP_RESOURCE_URL` for that server

For every test, the briefing rule applies: state in a comment or test docstring what real bug the assertion would catch (which historical regression it re-detects).

**Integration tests (live, manual, not in default CI):**
A separately-marked test module or script that walks the **deployed** discovery chain over HTTP for each of the four production servers: fetch PRM → follow `authorization_servers` → fetch AS metadata → assert the same shape invariants against live responses. Must be excluded from default CI (external network), runnable on demand pre-submission/pre-deploy, and referenced from `OPERATIONS_PRESUBMISSION.md` if that doc has a natural place for it (flag if it doesn't — do not force it).

### D5 — Code comment corrections (comments/docstrings only — no logic, no values)

1. `mcp_server/priority_guardian_claude/discovery_dupl.py` — header currently reads "All AS metadata endpoints point to www for consistency." That is verbatim the rationale of regression commit 5854d50. Amend to state: correct **for Claude** (RFC-literal root-issuer discovery), fatal **for ChatGPT** — never port this shape to the OpenAI twin; reference the incident record and ADR_005.
2. `mcp_server/clarity/config.py` — module docstring and `OAUTH_ISSUER_URL` comments say `/oauth/pg`; production runs `/oauth/mindsort` (Render-confirmed). Correct the docstring/comments to state the production value and that the dev default differs. **Do NOT change the dev default value** in this increment — changing it requires verifying the local backend mounts `/oauth/mindsort` in dev, which is out of scope; flag it as a follow-up note in the comment instead.

---

## Non-goals (explicitly out of scope)

- Any change to discovery return values, endpoints, routes, env vars, or config defaults
- Option B (OpenAI shape convergence), the shared-discovery-module refactor (`mcp_server/shared/`), and the `_dupl` consolidation — all separately triggered
- `inc_token_rate_limit_raise` (independent, already briefed)

## Implementation approach — Copy and Adjust, Never Rewrite

Doc amendments (D2, D3) and comment fixes (D5) are surgical: make only the listed adjustments; do not restructure, rephrase, or "improve" anything not explicitly listed. `_dupl` file edits are comment-only.

## Definition of done

1. ADR_005 exists with all six content requirements; doc amendments D2/D3 applied and verified by re-reading the files.
2. All unit contract tests pass; demonstrate (by temporary local mutation or explicit reasoning in the PR notes) that re-applying the 5854d50 consolidation would fail CI, and that a path-qualified Claude `authorization_servers` would fail CI.
3. Integration test module exists, is excluded from default CI, and passes against production when run manually.
4. `pytest` full suite green (Nadja runs).
5. Explicit final list of what was NOT verified.
