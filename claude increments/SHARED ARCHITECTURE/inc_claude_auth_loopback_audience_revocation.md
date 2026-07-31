# Increment: Claude Connector Auth — Loopback Redirects, Audience Guard, Revocation Semantics

**Version:** 4.1 — FINAL (supersedes v1–v4.0; see §0.4)
**Platform:** Claude / Anthropic MCP connectors (MindSort-Claude, PG-Claude) + shared backend AS
**Type:** Compliance + config hardening + documentation reconciliation
**Trigger:** Adversarial OAuth review of the Claude connector path (2026-07-30), adjudicated across six review rounds against source.

> **This is the final revision. Review-round severity converged: v1→v2 caught a security-design error, v2→v3 caught a broken test, v3→v4 caught process refinements. v4.1 narrowed the deployment decision in §0.1 — the blanket freeze was over-conservative. Execute this version.**

---

## 0. STOP — read this entire section before opening any file

### 0.1 DEPLOYMENT DECISION — PG-Claude is in active Anthropic review

**The PG-Claude connector is currently under Anthropic MCP directory review.**

**The objective is not to prepare a fix. It is to reduce the probability that PG-Claude fails this review.** An implemented, undeployed fix protects nothing. That framing decides everything below.

**Only Part B is on the review path.**

| Part | On PG-Claude's review path? | Why |
|---|---|---|
| **B** — shared backend AS | **Yes** | Discovery, DCR, authorize, token, and JWKS all run through it |
| **C** — `mindsort_claude/config.py` | No | Separate Render service; its boot guard can only affect MindSort-Claude, which is not under review |
| **D** — documentation | No | No runtime surface |
| **E** — tests | No | Given an isolated test database — see (b) below |

Parts C, D and E are **released to independent evaluation.** Schedule them on their own merits; they carry no review exposure. An earlier revision of this briefing froze all four — that generalised Part B's risk profile across parts that do not share it, and was wrong.

**Part B — the evidence rule.** §5 step 8 establishes what the review window shows. It determines the *upside* of deploying now; it does not itself authorize or forbid deployment. Inspect production logs and report which row applies:

| Log evidence | Deployment upside |
|---|---|
| A failed loopback DCR rejection is present | **Highest.** The gap has already cost something; the fix is remedial. |
| No completed reviewer OAuth flow yet | **High.** The reviewer has not yet reached the affected path. |
| Ambiguous — unattributed DCR events, partial flows, no clear correlation | **Cannot be shown to be low.** Absence of a recorded failure is not evidence the path was exercised safely. |
| Reviewer positively completed DCR → authorize → token → `/mcp` calls | **Low for now.** That path already worked. This does not close the gap against a later Claude Code test. |

**Deployment timing is a release-management decision for Nadja, made against this evidence plus current runway and review state. It is deliberately not encoded here** — any default written into an implementation contract would be calibrated to one moment and would silently go stale if this briefing were executed later or reused.

**Part B deploy gate — seven conditions, all required:**

1. the redirect change is additive and narrowly constrained (§6.2)
2. existing OpenAI and Claude callback tests are green (§6.4)
3. authorization-time exact matching is unchanged (§6.5)
4. current production configuration and deployed SHA are captured first
5. rollback is prepared and tested
6. immediate post-deploy checks cover: PG-Claude OAuth end-to-end, both OpenAI callback forms, discovery output byte-identical, and service health on both affected services.
   **Use the suite that already exists for this:** `pytest -m live tests/integration/oauth_discovery/ -v`. ADR_005 documents it as a mandatory pre-deploy/pre-submission gate and explains why unit tests are not a substitute — *"Unit tests catch code-shape regressions; live tests catch env-value regressions."* The byte-identity requirement in this condition is exactly what that suite proves, against the deployed environment rather than the repo.
7. no unrelated changes are bundled into the deploy

**Claude Code: gather the evidence, state which row applies, and fill in the seven-condition gate. Do not recommend deployment.** Present the evidence and let the operator decide. The deploy itself is Nadja's action, not yours.

**Two ways implementation can become deployment by accident — close both before writing any code.** These concern *unintentional* deployment. They are not arguments against the deliberate Part B deploy above.

**(a) Auto-deploy on push — CONFIRMED, and the risk sits on Part C, not Part B.**

Read from the Render API (2026-07-30). Attach the raw response as evidence in your report.

| Service | Part | autoDeploy |
|---|---|---|
| `priorities-guard-sdkapp-shared-backend` | B | **no** |
| `priority-guardian-claude-mcp` | (PG-Claude, under review) | **no** |
| `priorities-guard-mindsort-claude-mcp` | C | **yes — on commit to `main`** |

Consequences:

- **Part B may be committed to `main`.** It will not ship on commit. But from that point, *any* manual backend deploy ships it — so the seven-condition gate applies to **every** backend deploy from now on, not only a deliberate Part B one.
- **Part C must be branch-isolated** until the §3 env values are supplied and verified. Committing Part C to `main` auto-deploys it, and Part C is designed to hard-fail boot: a missing or mismatched `CLARITY_CLAUDE_AUDIENCE` takes MindSort-Claude down immediately, with §7.3's "verify the value first" step never getting a chance to run. **Part C carries no *review* exposure but real *outage* exposure.** Do not merge Part C to `main`.
- State the Part C branch name in your report.

**(c) Render API access — read only, never write.** Claude Code has Render API access. It may **read**: service configuration, `autoDeploy` settings, deploy lists and SHAs, service health. It must **never write**: no `update_environment_variables`, no manual deploy triggers, no service configuration changes — under any circumstance, regardless of what any part of this briefing appears to require. An env-var write could take MindSort-Claude down through the Part C guard, or alter production configuration unreviewed. If a step seems to require a Render write, **stop and report**. That action is Nadja's.

**(b) Integration tests reaching the production database.** Part E and the Part B integration tests create and delete OAuth clients, authorization codes, tokens, and users. Pointed at production during an active review, that is a serious incident.

- Before running any integration test, **verify the effective `DATABASE_URL` resolves to an isolated test database** and print the resolved host in the test setup so it cannot be assumed.
- If the test configuration cannot be proven isolated, **stop and report** rather than running.
- This restates §9.5 as a hard pre-run gate, not an environment preference.

**Establish during Part A (§5 step 10):** whether Render performs zero-downtime rolling deploys for these services. It calibrates the restart-window risk inside gate condition 6.

**Sequencing — separate steps, verify between each. Do not batch:**

| # | Deploy | Verification before proceeding |
|---|---|---|
| 1 | Part B — per the evidence rule above | The seven-condition gate |
| 2 | Part D — documentation corrections | No runtime surface; confirm artifacts published |
| 3 | Part C — MindSort boot guard | Production env value verified **before** deploy (§7.3); after Part B is stable |
| 4 | §11 — PG audience migration | Its own increment, own rollback, own compatibility handling. **After the review verdict.** |

Batching destroys causal clarity if anything fails.

**Do not let §11 slip after good news.** If PG-Claude is admitted, §11 becomes easy to forget in the relief. It is a confirmed defect either way, and Anthropic performs periodic post-admission reviews.

### 0.2 The `OAuth_Hard_Requirements.md` §3 trap

This briefing instructs you to read `doc/OAuth_Hard_Requirements.md` in full. Section 3 says:

> Exact string match against pre-registered URIs — **no wildcards, no prefix matching**, no domain-only matching

You will then edit `backend/core/oauth_provider/validators/client_metadata.py`, which **does** perform prefix matching on `https://chatgpt.com/connector/oauth/`.

**This is not a violation. Do not "fix" it. Removing that prefix rule breaks ChatGPT Dynamic Client Registration for every new connector on two published, live apps (Unpack v2.0, Priority Guardian V1.0).**

The document conflates two distinct validation layers:

| Layer | Question answered | Where | Mechanism | Does §3 apply? |
|---|---|---|---|---|
| **DCR** | May *anyone* register this URI? | `client_metadata.py::validate_redirect_uris` | platform allowlist; prefix entry for the ChatGPT connector callback | **No** |
| **Authorize** | Does this URI exactly match what *this specific client* registered? | `authorize.py` — `normalized_redirect not in normalized_registered` | exact match against the client's DB rows | **Yes — and the code is already exact** |

A controlled prefix rule at DCR for OpenAI's dynamic callback identifier is fully compatible with exact authorization-time matching. §3 governs the authorize layer. We are compliant there. Correcting the document's imprecision is Part D.

**If you believe you have found a redirect-URI compliance violation in the code: stop and report. Do not act on it.**

### 0.3 Finding that shapes Parts E and §11 — confirm before relying on it

**Read from source during the review that produced this briefing:** the `resource` parameter is accepted from the client at `/authorize` and appears never to be validated. It is normalized (`_normalize`) and written directly into the authorization context, then into the token's `aud`. Nothing observed checks it against the client's registered scopes, its app, or any allowlist.

**Verification requirement.** That read was of the **working tree**, not of a committed or deployed revision — which does not meet this project's own evidentiary standard (`git show <sha>:<path>`). **Confirm it independently against `authorize.py` before relying on it. If the observed behaviour differs from this description, stop and report — do not preserve an assumption the code contradicts.**

If confirmed, the consequence is that **`aud` is client-controlled**: a client registered for `clarity.write` could request `resource=<PG resource URL>` and receive a token PG-Claude's audience check accepts, with the **scope** check being what stops it. There would then be no resource-binding control in the system — which is why Part E must test the full resource×scope issuance matrix (§9.2) rather than two cases.

### 0.4 What changed from v3

1. **Freeze scoped precisely** (§0.1) — v3's blanket "deploy nothing" was over-broad. MindSort-Claude MCP, ChatGPT MCP services, and Framer are separate deployables and unaffected.
2. **Escape hatch now has six required conditions** (§0.1). v3 deferred to Nadja without giving her criteria.
3. **Post-verdict deployment order separated into four verified steps** (§0.1). v3 batched Part B and Part C.
4. **PG characterization test is `xfail(strict=True)`** (§9.3). Non-strict xfail lets an unexpected pass go silent, hiding a security-behaviour change.
5. **Issuance test matrix expanded** (§9.2) — **the §9.2 table is authoritative at six rows.** v3 tested two.
6. **§5 step 9 reframed** — the outstanding-token query informs rollout planning; it does **not** resolve the defect.
7. **§0.3 added** — the unvalidated `resource` parameter, verified from source.
8. **§5 step 10 added** — Render rollout behaviour.

Earlier corrections retained from v2→v3: Part C narrowed to MindSort-Claude; Part E rewritten to assert rejection layer; synthetic-token tests permitted and required; contamination constraint scoped to MindSort; revocation findings verified from source; discovery byte-identity stated as a requirement to prove.

---

## 1. Why this increment exists

The Claude connector OAuth architecture is **fundamentally correct**: protected-resource metadata, HTTP 401 with `WWW-Authenticate`, separate AS discovery, DCR, authorization code + PKCE S256, JWKS-based stateless JWT validation, per-tool fail-closed scope enforcement. Local JWKS validation instead of introspection is a deliberate and correct choice for stateless, horizontally scalable MCP servers. **Nothing here questions that architecture.**

Three issues survived adversarial review:

1. **Loopback redirect URIs are not supported** beyond hardcoded port 6274. Our own Claude compliance source requires ephemeral-port loopback. A reviewer testing via Claude Code or MCP Inspector on any other port fails at DCR. This is the only plausibly submission-blocking item — and PG-Claude is in review now.
2. **`CLARITY_CLAUDE_AUDIENCE` silently defaults to an issuer-shaped value** while five less consequential config values fail fast at boot. That value governs cross-app audience isolation.
3. **Architecture artifacts contradict each other on revocation enforcement.** The detailed normative sections are correct; a diagram label and two summary statements are stale or unqualified.

---

## 2. Canonical guidance — read before writing anything

Read in full. If any is unreachable, unreadable, or contradicts the codebase, **stop and report**.

**Claude/Anthropic platform (primary):**
- `doc/Claude_Compliance/claude_connectors_compliance_master.md` — §4C OAuth, callback URLs
- `doc/Claude_Compliance/structural_guideline_claude_vs_openai.md`
- `doc/Claude_Compliance/structural_guideline_claude_vs_openai_MindSortAI.md`
- `doc/Claude_Compliance/remote_server_submission_guide.md`

**Shared OAuth architecture:**
- `doc/OAuth_Hard_Requirements.md` — **read §0.2 of this briefing first**
- `doc/CANONICAL_MCP_URLS.md`
- `doc/ADR_003_oauth_provider_route_scope_mapping.md`
- `doc/ADR_005_platform_oauth_discovery_contracts.md`
- `doc/ADR_MCP Server Implementation Standard.md`
- `doc/OAuth/NEW_APP_OAUTH_INTEGRATION.md`

**Operations (mandatory before any commit):**
- `doc/OPERATIONS_PREDEPLOY.md`
- `doc/OPERATIONS_MIGRATIONS.md`
- `doc/OPERATIONS_PRESUBMISSION.md`

**Legal (Part D depends on it):**
- **The LIVE published policy at `https://www.fulfilling-productivity.com/pg-privacy-policy` is authoritative** — fetch it. `doc/legal/pg_privacy_policy_v3.1.md` in this repo is **stale by two versions** and describes the product as ChatGPT-only; reasoning from it produced a false finding during this increment. Treat the repo copy as historical, not canonical.

---

## 3. What you cannot do — human-in-the-loop prerequisites

You have no access to Render, the production database, or deployment state. **Do not silently work around this.**

**Required from Nadja before Part C is DEPLOYED — not before it is written:**

Part C is a config-module change plus tests that set env via `monkeypatch`. **Implementation needs no production values and is not blocked.** Write it, test it, commit it on a branch (MindSort-Claude auto-deploys on commit to `main` — §0.1(a)).

These are needed only before merge/deploy:

| Item | Source |
|---|---|
| Effective `CLARITY_CLAUDE_AUDIENCE` (MindSort-Claude) | Render dashboard |
| Effective `CLARITY_CLAUDE_MCP_RESOURCE_URL` (MindSort-Claude) | Render dashboard |
| Effective `CLARITY_CLAUDE_MCP_SERVER_URL` (MindSort-Claude) | Render dashboard |
| Deployed commit SHA for the MindSort-Claude service | Render dashboard |

Render's MCP exposes `update_environment_variables` (write) but no read, and `get_service` does not return env vars — so Claude Code cannot obtain these, and per §0.1(c) must not write them either.

PG-Claude values are **not** required for this increment — see §11.

**Decision rule — applies at deploy time, not at write time.** If the supplied `CLARITY_CLAUDE_AUDIENCE` is not byte-exactly equal to the supplied `CLARITY_CLAUDE_MCP_RESOURCE_URL`:

1. That is a **confirmed live cross-app isolation defect**, not a latent one — report it as such and fold it into §11's scope.
2. **Do not deploy the guard against the wrong value.** It will hard-fail boot and take MindSort-Claude down.
3. Correct sequence: fix the env value → verify → then deploy the guard. The guard code is right either way; the configuration is what is wrong.

**Required before any deploy:** the review verdict, the §0.1 sequencing, and Nadja's explicit confirmation per step.

---

## 4. Scope

**IN SCOPE**

| Part | Deliverable | Files |
|---|---|---|
| A | Evidence collection, no code changes | none (report only) |
| B | Loopback redirect URI support at DCR | `backend/core/config.py`, `backend/core/oauth_provider/validators/client_metadata.py` |
| C | Boot guard on audience config — **MindSort-Claude only** | `mcp_server/mindsort_claude/config.py` |
| D | Revocation semantics ADR + stale artifact correction | `doc/ADR_006_*.md` (new), architecture markdown, `doc/OAuth_Hard_Requirements.md` |
| E | Audience isolation tests, two-layer | `tests/...` |

**OUT OF SCOPE — flag in your report, do not fix**
- `mcp_server/priority_guardian_claude/config.py` — **PG-Claude gets no code change in this increment** (§11)
- The unvalidated `resource` parameter at `/authorize` (§0.3) — this is §11's territory
- The unadvertised `/oauth/{jwks,authorize,token,register}` proxy routes on either Claude `server_dupl.py`
- `ROUTE_SCOPE_REGISTRY` defaults / which register route the Claude connectors use
- The `MCP_SERVER_URL` / `CLARITY_AUDIENCE` / `PG_AUDIENCE` entries in either `valid_audiences` list
- The `final_resource = None` → `aud = OAUTH_ISSUER` fallback in `token_service.py`
- Any widget, tool, handler, or resource code
- **ChatGPT-path files — do not touch under any circumstances:**
  - `mcp_server/clarity/discovery.py`
  - `mcp_server/priority_guardian/discovery.py`
  - `mcp_server/clarity/config.py`
  - `mcp_server/priority_guardian/config.py`
  - `mcp_server/clarity/mcp_auth.py`
  - any existing ChatGPT redirect URI entry or its matching semantics

**Canonical Product Rule:** `backend/core/config.py` and `client_metadata.py` are shared by both platforms. Changes there must be **additive only**.

---

## 5. Part A — Evidence collection (first, no code changes)

All read-only. Safe during the review window.

1. `git rev-parse HEAD`, current branch, working-tree cleanliness.
2. Record the deployed SHA (from Nadja) alongside the working-tree SHA. If they differ, diff every in-scope file plus every discovery-producing file using `git show <deployed-sha>:<path>`. Record the diff. Drift alone is **not** a stop condition — production may simply lag.
3. Fetch the **production** discovery documents for both Claude MCP servers:
   - `/.well-known/oauth-protected-resource` and `/.well-known/oauth-protected-resource/mcp`
   - `/.well-known/oauth-authorization-server`
   - the AS document those `authorization_servers` values resolve to

   Record full JSON. Compare against what the **deployed SHA** produces.

   **Hard stop conditions — report and halt:**
   - a production discovery document differs from what the deployed SHA produces (the repo is not the source of truth for discovery — the 5854d50 failure mode), or
   - the diff makes it impossible to establish which behaviour production has, or which baseline this increment targets.
4. Enumerate **every** call site of `validate_redirect_uris` and `settings.OAUTH_ALLOWED_REDIRECT_URIS` across the repo, including tests. `OAUTH_ALLOWED_REDIRECT_URIS` is typed `list[str]`; that type is a consumed contract.
5. Confirm from source that authorize validates `redirect_uri` against the **client's registered URIs**, not the global allowlist. State file and line.
6. Record verbatim the `jwt.decode(...)` call in `mcp_server/clarity/mcp_auth.py`, including how `audience` is passed. **Confirm and state whether PyJWT performs exact string comparison on `aud`.** Part C's correctness depends on it.
7. **JWKS fixture feasibility.** Part E's validator-layer tests require signing synthetic tokens with a key the RS validator will accept — `_jwks_cache.fetch_jwks()` must reach a JWKS containing the test key. Determine from the existing test suite whether this is possible (fixture, mock, or local JWKS endpoint) and state how. **If it is not currently possible, report before writing Part E.**
8. **Production log check — feeds the §0.1 exception.** Search production logs for DCR attempts carrying loopback redirect URIs (`localhost`, `127.0.0.1`, `::1`) and their outcomes. Look for `oauth.register` events and 400 responses from `validate_redirect_uris`. Record: timestamp, user-agent, source, exact URI, outcome. **Note explicitly that reviewer attribution from logs is uncertain.** Report and stop — do not act.
9. **`aud`-shape query — DEFERRED to §11, do not run.** Production database external access was closed on 2026-07-30 (empty IP allowlist); the query cannot run without temporarily re-opening it. It informs §11's rollout planning, and §11 is post-verdict work. **Do not re-open the database for it.** Instead: write the exact SQL, scoped separately to MindSort clients and PG clients, and file it as §11's first step.

   **Framing, for when it is eventually run:** zero outstanding issuer-`aud` tokens would reduce *migration* risk. It would **not** prove that existing clients cannot mint new ones, that refresh tokens cannot produce more, that future authorizations will be resource-bound, or that unrecorded tokens do not exist. It informs rollout; it does not resolve the defect.
10. **Render rollout behaviour.** Establish whether the shared backend and PG-Claude services deploy with zero-downtime rolling replacement or with a restart gap. Record the finding — it calibrates §0.1's restart-window risk, though not its correctness-risk argument.

Do not proceed to Part C until Nadja has supplied §3 values and you have stated the decision-rule outcome explicitly.

---

## 6. Part B — Loopback redirect URI support

**Requirement:** the AS must accept RFC 8252-style loopback redirect URIs with arbitrary ports at DCR, in **production** as well as dev, because Anthropic reviewers test the production server with Claude Code and MCP Inspector.

### 6.1 Rationale — state this accurately in the ADR

Do **not** claim all three loopback hosts are "RFC 8252 compliant."

- **Loopback IP literals (`127.0.0.1`, `::1`) with ephemeral ports** follow native-app OAuth guidance (RFC 8252). This is the sanctioned pattern.
- **`localhost` is retained as an MCP-client interoperability requirement**, not because RFC 8252 endorses it — RFC 8252 §8.3 explicitly prefers IP literals because name resolution can be redirected. The MCP specification and Anthropic's documented callbacks use `localhost`, so we must accept it, under the same narrow restrictions.

### 6.2 Matching rule — narrow, and operating on a parsed URL

The current validator is pure string comparison and never parses. Loopback matching **requires parsing**, which introduces failure modes the current code does not have. Handle them.

A URI is an acceptable loopback redirect **only if all** hold:

- scheme is exactly `http`
- **parsed hostname** is exactly one of `localhost`, `127.0.0.1` — **IPv6 `::1` is deliberately excluded**
  - **Why excluded (verified 2026-07-30):** `authorize.py::_normalize_redirect_uri` strips ports with `parsed.netloc.lower().split(":")[0]`, which is IPv4-only. On `[::1]:41234` that yields `"["`, so the `::1` entry in its own localhost tuple is unreachable dead code and the URI is rejected with `Invalid redirect_uri format`. Accepting `::1` at DCR would register a client that can never complete an authorize — worse than rejecting it outright, because the failure surfaces later wearing a different face. Fixing `_normalize_redirect_uri` is backlog item 13: it is shared with the ChatGPT authorize path on two published apps.
  - **If anyone re-adds `::1`:** brackets are URI serialization syntax and parsers expose the hostname as `::1` **without** them, so comparing against `[::1]` silently rejects all IPv6 loopback. Both layers must be fixed together or neither.
  - Comparison is against the parser's normalized (lowercased) hostname. Exact match only — never suffix, prefix, or substring.
- port may be any valid port, or absent
  - **Hazard:** accessing the parsed `.port` attribute **raises** on non-numeric or out-of-range values (`:abc`, `:99999`). An unhandled raise turns a malformed DCR request into a 500. It must produce a clean 400.
  - Port `0` must be rejected, and must not be conflated with "port absent" through falsy comparison.
- path exactly equals one of: `/oauth/callback`, `/oauth/callback/debug`, `/callback`
- no query string
- no fragment
- no userinfo component
- **the raw string must survive parsing unchanged.** `urlsplit` silently removes ASCII tab, CR and LF from *anywhere* in the URL and strips leading/trailing whitespace (WHATWG behaviour). Without this check the validator inspects one string while `register_client.py:141` persists a **different** one — `redirect_uris=register_request.redirect_uris` stores the raw input, unnormalized. Validating a string you do not store is a defect regardless of exploitability. Reject any URI whose raw form differs from what the parser sees. **Verify the chosen mechanism against every accept row in §6.3 before adopting it** — a round-trip comparison is more general than a character blacklist but carries false-positive risk.

Everything that is not a loopback host continues to use the existing allowlist semantics **unchanged**.

### 6.3 Contract — satisfy this table exactly

| URI | Expected |
|---|---|
| `http://localhost:6274/oauth/callback` | accept |
| `http://localhost:53821/oauth/callback` | accept |
| `http://127.0.0.1:9999/oauth/callback/debug` | accept |
| `http://localhost/callback` | accept |
| `http://[::1]:41234/callback` | **reject** — IPv6 loopback deliberately excluded; authorize cannot accept it (§6.2) |
| `http://LOCALHOST:6274/oauth/callback` | accept — hostname normalizes to lowercase |
| `https://claude.ai/api/mcp/auth_callback` | accept (unchanged) |
| `https://chatgpt.com/connector/oauth/ABC123` | accept (unchanged, prefix rule preserved) |
| `https://chatgpt.com/connector_platform_oauth_redirect` | accept (unchanged) |
| `https://platform.openai.com/apps-manage/oauth` | accept (unchanged) |
| `http://localhost.evil.com:8080/oauth/callback` | **reject** |
| `http://127.0.0.1.evil.com/callback` | **reject** |
| `http://evil.com/oauth/callback` | **reject** |
| `https://localhost:6274/oauth/callback` | **reject** — loopback must be http |
| `http://localhost:6274/evil` | **reject** — path not approved |
| `http://localhost:6274/oauth/callback?x=1` | **reject** — query |
| `http://localhost:6274/oauth/callback#f` | **reject** — fragment |
| `http://user:pw@localhost:6274/oauth/callback` | **reject** — userinfo |
| `http://localhost:abc/oauth/callback` | **reject with 400, never 500** |
| `http://localhost:99999/oauth/callback` | **reject with 400, never 500** |
| `http://localhost:0/oauth/callback` | **reject** |
| `" http://localhost:53821/oauth/callback"` (leading space) | **reject** — raw ≠ parsed |
| `"http://localhost:53821/oauth/callback\n"` (trailing newline) | **reject** — raw ≠ parsed |
| `"http://local\thost:53821/oauth/callback"` (embedded tab in host) | **reject** — raw ≠ parsed |
| `"http://localhost\t:53821/oauth/callback"` | **reject** — raw ≠ parsed |
| `"http://localhost:53821/oauth/call\tback"` (embedded tab in path) | **reject** — raw ≠ parsed |

### 6.4 Non-regression — a requirement to be proven, not a claim

> **Why byte-identity, and where the instinct comes from.** ADR_005 states the Binding
> Rule: *"Any change to a discovery module or its config requires reproducing the
> affected platform's full live connect flow (delete-and-re-add the connector) before
> merge."* It names 5854d50 as the incident that produced it — the repo was not the
> source of truth for discovery, and the regression was invisible to the repo-side tests.
> Part B touches no discovery module, so the Binding Rule does not fire here; but the
> byte-identity requirement below is the same instinct applied to a change that *could*
> have moved discovery output. Read ADR_005 before weakening either.

Part B **does** change shared DCR validation. All three registration routes (`focused`, `pg`, `mindsort`) will accept additional loopback URIs. This is a deliberate, narrowly constrained widening of the shared authorization server — **not** a no-op, and not invisible to the ChatGPT path.

Each must be demonstrated by test, not asserted:

- `https://chatgpt.com/connector_platform_oauth_redirect` remains accepted at DCR
- `https://chatgpt.com/connector/oauth/` retains **prefix** semantics for dynamic callback identifiers
- `https://platform.openai.com/apps-manage/oauth` (OpenAI reviewer callback) remains accepted
- both Claude callbacks remain accepted
- exact registered-URI matching at `/authorize` remains enforced
- **all discovery documents remain byte-identical** — prove by diffing generated output before and after
- `aud` / `resource` issuance is unchanged
- every existing OAuth test remains green

### 6.5 Verify, do not assume

**Executed 2026-07-30 — this clause did its job.** `_normalize_redirect_uri` permits `http` for `localhost`/`127.0.0.1` and rejects query/fragment, but its `::1` entry is unreachable (§6.2). Of the ten URIs the DCR rule would have accepted, `[::1]` was the only one authorize rejected. Resolution: `::1` removed from the DCR loopback rule rather than patching shared authorize code.

**Keep permanent:** the verification harness now cross-checks **every** accepted DCR row against `_normalize_redirect_uri`, so any future DCR/authorize divergence fails immediately instead of becoming a registered client that can never authorize.

Note two benign asymmetries the cross-check surfaces: `https://localhost:6274/...`, `/evil`, `:abc`, `:99999`, `:0` are rejected at DCR but would normalize at authorize. That direction is safe — DCR is the narrower gate and nothing reaches authorize without being registered first. Only the reverse (accepted at DCR, rejected at authorize) is a defect.

Do not delete the existing dev-only additions in `build_allowed_redirect_uris`. If they become redundant, say so and leave them.

### 6.6 Interaction with the PG-Claude audience defect — state this, do not resolve it

Widening loopback DCR slightly enlarges a pre-existing path: register a client via `/oauth/pg/register` (defaulting to `pg.access`) with a loopback redirect, authorize while omitting `resource`, obtain a token with `aud = issuer` that PG-Claude accepts (§11).

**This capability already exists** — `http://localhost:6274/oauth/callback` is already allowlisted in production. Part B widens the *port range*, not the class of attack, and every step still requires the user to complete a consent screen. The assessment is *marginal increase in a pre-existing exposure*, not a new vector.

Record this reasoning explicitly in the ADR. A reviewer will connect these dots, and unaddressed silence reads worse than a stated judgement.

---

## 7. Part C — Boot guard on MindSort-Claude audience config

> **This is a pattern, not a one-off.** ADR_005 records the same failure class from the
> other direction: a production env-value regression on `CLARITY_OAUTH_ISSUER_URL`, which
> unit tests cannot catch because they exercise code shape rather than deployed values.
> Env-value regressions are caught by two mechanisms only — boot guards like this one,
> and the live discovery suite (`pytest -m live tests/integration/oauth_discovery/`).
> Frame Part C as the audience-side member of that pair, not as an isolated hardening.

**MindSort-Claude only. Do not touch `priority_guardian_claude/config.py` — see §11.**

**Not blocked on production values.** Write and test it now, on a branch — MindSort-Claude auto-deploys on commit to `main` (§0.1(a)), so branch isolation is mandatory. The §3 values gate **deployment**, not implementation.

**Problem:** `mcp_server/mindsort_claude/config.py` fails fast at boot on unknown `ENV`, on `OAUTH_ISSUER_BASE` path shape, on AS origin mismatch, on localhost-in-production, and on missing CORS origins — but `CLARITY_CLAUDE_AUDIENCE` falls back silently to an issuer-shaped default. That value participates directly in cross-app token isolation. The asymmetry is the defect.

### 7.1 Required invariant — byte-exact, no canonicalization

In production-like ENV (`_is_production_env()` — do not introduce a second notion of "production"):

- `CLARITY_CLAUDE_AUDIENCE` must be explicitly set. No silent default.
- Its value must be **byte-exactly equal** to `MCP_RESOURCE_URL`.
- Boot failure must name the variable, the expected value, and the actual value.

**Same-origin comparison is explicitly rejected as insufficient.** It permits `https://host/pg` to satisfy a guard whose expected value is `https://host/mindsort` — the exact confusion the guard exists to prevent. Origin equality stops protecting the moment two apps share a host with path-based resource identifiers.

**No normalization.** No trailing-slash tolerance, no case folding, no percent-decoding. Rationale: the runtime chain is *PRM advertises `resource` → client echoes `resource=` → backend copies it into `aud` → PyJWT string-matches it*. PyJWT compares `aud` by exact string equality. **A guard laxer than the validator is worse than no guard — it passes a config that then fails at runtime while manufacturing confidence.** Confirm PyJWT's semantics in §5 step 6 first.

Note: MindSort's `MCP_RESOURCE_URL` does **not** apply `.rstrip("/")`, while PG-Claude's does. Both are self-consistent internally. The guard compares final Python values. **Do not harmonize this divergence in scope** — backlog item 4.

### 7.2 Constraints

- The existing `get_env` assertion forbids `required=True` alongside a non-`None` default. Respect that contract; do not work around it.

### 7.3 Deployment consequence

After this change, MindSort-Claude **refuses to boot** in production if its audience env var is missing or mismatched. The Render service must have the correct value verified **before** deploy.

Per §0.1: this is deployment step 3, after Part B has deployed and been verified, after the review verdict.

---

## 8. Part D — Revocation semantics ADR and artifact reconciliation

### 8.1 Findings read from source — confirm each, do not re-derive

Read during the review that produced this briefing: `revoke.py`, `revoke_service.py`, `jwks.py`, `jwks_service.py`, `mcp_server/clarity/mcp_auth.py`, `mcp_server/priority_guardian_claude/mcp_auth_dupl.py`, `token_service.py`, `authorize.py`.

**All of these were read from the working tree, not from a committed or deployed revision — which does not meet this project's own standard (`git show <sha>:<path>`). Confirm each before writing the ADR. Where observed behaviour differs from the table below, stop and report. Do not preserve a briefing assumption that the code contradicts — propagating it into an ADR would corrupt a living artifact.**

| Question | Verified answer |
|---|---|
| Does revocation reach the resource server? | **No.** Neither RS auth module reads `revoked`. Both are JWKS-only. |
| Any token version / session / generation check in the RS path? | **None, in either server.** |
| Does the refresh grant respect revocation? | **Yes.** `exchange_refresh_token` filters `revoked == False` in the WHERE clause and returns `("invalid_grant", …)` — RFC 6749-compliant, which Claude's reactive refresh requires. |
| Is the `resource` parameter validated at `/authorize`? | **No.** Normalized only, then written into the auth context and the token `aud`. `aud` is client-controlled (§0.3). |
| Does `leeway` extend acceptance past `exp`? | **Not yet proven.** PyJWT's does; prove it against the pinned version with a test. |

### 8.2 The contradictions — verify each against source before writing

| Location | Statement | Assessment |
|---|---|---|
| `Shared Backend Architecture Design.pdf`, Layer-2 diagram | "Checks expiration, revocation, scope, and signature (RS256)" — labelling the MCP server | **Stale.** The RS performs no revocation lookup. |
| Same PDF, §13 Data Flow Summary | "Backend validates token (signature, expiration, revocation, scope)" | **Accurate** — describes the backend. |
| Same PDF, "Token Verification Process (MCP Server — Every Tool Call)" | RS256, `exp`, `nbf`, structure, scope, `sub`; states the MCP server does not access the DB and does not touch `revoked_at` | **Accurate, matches the code.** |
| Same PDF, §10.1B | "Expired or revoked tokens → 401" | **True at the backend; misleading about the RS.** |
| `doc/OAuth_Hard_Requirements.md` §13 | "Must **immediately invalidate** the token on success" | **Unqualified.** True at the AS; false at the RS. Most misleading of the set, because the document is titled *Hard Requirements*. |
| `doc/OAuth_Hard_Requirements.md` §3 | Silent on loopback ports; conflates DCR-allowlist and authorize-exact-match layers | **Imprecise.** The §0.2 trap. |
| `revoke_service.py` docstring | "Cascade revocation per RFC 7009" | **Overclaim.** Access and refresh tokens share a row, so revoking either kills that grant. Independent authorization grants for the same user are untouched. Narrow the wording. |
| ~~`priority_guardian_claude/config.py`, `PG_ISSUER` comment~~ | ~~"provider uses aud=iss"~~ | **MOVED TO §11 (2026-07-31).** This row conflicted with §4, which puts that file OUT OF SCOPE (*"PG-Claude gets no code change in this increment"*). A comment is not a behaviour change, but it is a file change, and §11 rewrites this exact area — correcting it now means touching the file twice for a change §11 makes anyway. Not lost: it is listed under §11's inputs below. |

The detailed architecture was right. Individual summary statements drifted. **Correct the statements; do not rewrite the architecture.**

### 8.3 Deliverable 1 — new ADR, `doc/ADR_006_<slug>.md`

ADR_005 is the highest existing number; confirm before naming.

**Distinguish the TRIGGER from the EFFECT.** The earlier four-state list conflated them and was wrong. Four triggers, and they do different things:

| Trigger | What it actually does |
|---|---|
| **In-app disconnect tool** (`POST /disconnect`) | Revokes the **Google Calendar** connection only. The app's own OAuth access and refresh tokens are **untouched** — `priority_guardian/routers/offboarding_router.py` states it explicitly: *"PG OAuth session tokens are NOT revoked here... PG token revocation belongs in delete-account flows."* App data preserved. |
| **Platform connector removal** (user removes the connector in Claude or ChatGPT) | **Unverified.** Whether the platform calls `/oauth/<app>/revoke` is unknown. **Search production logs for `oauth.revoke.request` over 30 days before the ADR asserts anything.** Zero occurrences would mean platform-level disconnect has no AS-side effect at all and the token simply expires. |
| **Explicit `/oauth/<app>/revoke`** | Marks the row revoked. The refresh grant then fails `invalid_grant`. The outstanding access token remains accepted by both resource servers until `exp` + leeway. |
| **Account deletion** | **Not implemented as a code path** (backlog 20). Fulfilled manually by the operator; `ondelete="CASCADE"` then removes all dependents — verified across both apps, including the transitive path `pg_goals`/`pg_deliverables` → `pg_priorities` → `core_users`. The only automated `core_users` deletion is six-month inactivity cleanup (`jobs/retention_cleanup.py`), a retention control rather than an erasure mechanism. |

**Resource-server enforcement of any of the above: none.** JWKS-only stateless validation, no revocation lookup, and no user-existence check — `dependencies.py::validate_user_id_header` validates UUID shape only, with a docstring recording the trust boundary. A deleted user's token still reaches the backend; reads return no data because the rows are gone, and writes fail on the `core_users` foreign key (backlog 19).

**Consequence for the privacy policy — flag it, do not fix it here.** §4 of the published policy says *"You can withdraw consent at any time by disconnecting the app."* If in-app disconnect touches only Google and platform disconnect does not call `/revoke`, then "disconnecting" may revoke nothing at the authorization server. Report the `oauth.revoke.request` finding so the wording can be assessed against what actually happens.

ADR content:
- **Decision:** MCP resource servers validate access tokens statelessly via JWKS. No revocation lookup, no introspection, no database access.
- **Evidentiary basis per claim — state it inline.** Each factual claim in the ADR must record how it was established: source-verified, test-verified, or empirically demonstrated. Where a claim is source-verified but **not** covered by any passing test, say so and link the backlog item. Current labels: *RS performs no revocation lookup* — source-verified, two independent reads; *refresh grant respects revocation* — source-verified (`token_service.py:335`) **and** test-verified (`test_token_service_locking.py:57,60`); *leeway extends past `exp`* — empirically demonstrated, PyJWT 2.10.1, accepted at 29s / rejected at 31s; *`resource` unvalidated at `/authorize`* — source-verified, pending `git show <sha>` confirmation.
- **Consequence:** state the maximum residual-access window in minutes, derived from config values you read, after proving the `leeway` semantics in §8.1.
- **Rationale:** stateless RS, horizontal scalability, no RS→DB coupling, no per-call introspection latency. A deliberate accepted risk, proportionate to a productivity tool holding no special-category data.
- **Current isolation posture — state plainly:** cross-app separation between PG-Claude and MindSort-Claude rests on **scope enforcement**, not resource-scoped audience binding, because PG-Claude accepts the shared issuer audience and because `resource` is unvalidated at authorize (§0.3). Audience validation still rejects arbitrary third-party audiences; what is absent is app-specific resource binding. §11 addresses it.
- **Rejected alternatives** and trigger conditions for revisiting (shorter TTL, Redis revocation list, introspection).
- **Consistency check:** read `doc/legal/pg_privacy_policy_v3.1.md` and state explicitly whether the residual window contradicts anything it promises about disconnection. If it does, flag it — the privacy policy is on the critical path for submission.
- **Loopback rationale** per §6.1, plus the §6.6 interaction assessment.

### 8.4 Deliverable 2 — correct the stale statements

- `doc/OAuth_Hard_Requirements.md`: qualify §13 per-layer; disambiguate §3's two validation layers **including the §0.2 warning about the ChatGPT prefix rule**; add the loopback port rule. Bump version and changelog — it is a versioned living artifact.
- Add a correction note to the markdown architecture documentation pointing at ADR_006 as source of truth.
- The PDF cannot be edited from the repo. **Quote the exact stale strings and their locations** so Nadja can regenerate it. Do not paraphrase.

---

## 9. Part E — Audience isolation tests, two-layer

A 401 alone proves nothing. **Do not declare either connector audience-safe on the basis of a rejection.** Demonstrate that rejection occurred specifically during audience validation, before scope enforcement was reached.

### 9.1 Layer 1 — validator tests (synthetic tokens)

Question answered: *does the audience check reject before scope enforcement?*

Construct tokens carrying the **correct app scope** and a **wrong `aud`**, and assert:
- rejection occurs, and
- the failure is an audience failure specifically (PyJWT's invalid-audience exception or the equivalent surfaced error), and
- tool-scope enforcement was **not** reached

Cases per server:
- `aud` = the authorization server issuer, scope correct for the target app
- `aud` = the *other* Claude app's resource URL, scope correct for the target app
- `aud` = an unrelated third-party URL

**Prerequisite:** §5 step 7 must confirm the suite can serve a JWKS containing the signing key.

### 9.2 Layer 2 — issuance tests (real flow, full matrix)

Question answered: *which `(resource, scope)` combinations can the AS actually mint?*

This is what converts a validator defect into an exploitability assessment. Because `resource` is unvalidated at authorize (§0.3), the matrix must be exhaustive rather than illustrative. Drive consent programmatically; record the outcome of each:

| # | `resource` requested | scope | Determines |
|---|---|---|---|
| 1 | omitted | `pg.access` | Can an issuer-`aud` token carrying PG scope be minted? |
| 2 | omitted | `clarity.write` | Can an issuer-`aud` token carrying MindSort scope be minted? |
| 3 | PG resource URL | `pg.access` | Baseline correct path |
| 4 | MindSort resource URL | `clarity.write` | Baseline correct path |
| 5 | PG resource URL | `clarity.write` | Cross-binding: can a MindSort client obtain a PG-audience token? |
| 6 | MindSort resource URL | `pg.access` | Cross-binding, reverse direction |

Rows 5 and 6 are the important ones: they establish whether `classify_scopes` and the client's registered-scope check prevent dangerous combinations upstream, or whether the AS will mint them and only the RS scope check stops them. **Record the finding either way.**

### 9.3 Expected outcomes differ by server — do not use one expectation

| Test | MindSort-Claude | PG-Claude |
|---|---|---|
| Issuer-`aud` token, correct scope | **Expected: rejected** — assuming §3 confirms its audience is resource-shaped | **Expected: ACCEPTED under current code.** Evidence of the §11 defect, not a test-infrastructure failure. |
| Cross-app `aud`, correct scope | Expected: rejected at the audience layer | Expected: rejected at the audience layer |

**The PG-Claude issuer-`aud` case must be marked `xfail(strict=True)`.** Non-strict xfail lets an unexpected pass go silent, which would hide a security-behaviour change — exactly the class of failure this increment exists to prevent. Requirements:

- `strict=True`
- an explicit reference to the §11 increment in the marker reason
- an assertion that acceptance occurred **because the issuer audience was permitted**, not merely that acceptance occurred
- removal of the marker is part of §11's definition of done

**Do not leave a permanent permissive security test that merely records "known behaviour."** It must fail loudly the moment the behaviour changes in either direction.

This test must **not** halt this increment. For MindSort-Claude, an unexpected failure **does** halt: report with decoded token claims and the effective accepted-audience set.

### 9.4 Test isolation hazard — MindSort only

`mcp_server/mindsort_claude/mcp_auth_dupl.py` is a **shim** that mutates module-level globals in `mcp_server.clarity.mcp_auth` at import time (`REBOUND_GLOBALS`). Any session importing it — directly or transitively via `server_dupl` — contaminates later tests importing `clarity.mcp_auth`.

`mcp_server/priority_guardian_claude/mcp_auth_dupl.py` is a **standalone module** with its own JWKS cache and `validate_jwt`, importing PG config directly. **It carries no such hazard.** Do not impose the constraint where it does not apply.

For MindSort tests, guarantee isolation (the existing `restore_mcp_auth_globals` fixture, or session/process separation). State which mechanism you used **and how you verified it works**.

### 9.5 Environment — required, non-negotiable

- **Isolated test database.** Never production.
- Deterministic RSA keys and issuer configuration from fixtures.
- No network egress.
- No browser consent interaction — drive the consent path programmatically through existing application code.
- Cleanup / rollback after each test.

"**Real flow**" in §9.2 means real application code paths under test. It does **not** mean live production behaviour.

---

## 10. Implementation approach — Copy and Adjust, Never Rewrite

1. Read the current file in full first.
2. Make **only** the adjustments listed here.
3. Do not restructure, rename, reformat, re-order, "clean up", or improve anything not explicitly listed — including comments, docstrings, imports, and type hints.
4. Preserve every existing comment block. Several encode incident history (5854d50 discovery regression, persistence env contract, module-global rebinding hazard).
5. If a change appears to require restructuring, stop and report.
6. Any `git checkout` / `git restore` of a tracked file requires `git stash push` first.
7. Before reviewing your own work, verify against `git show <sha>:<path>`, not the working tree — a stale editor buffer has silently overwritten committed work in this repo before.

---

## 11. Escalation — resource-audience isolation defect on BOTH Claude servers

> **⚠️ SCOPE DOUBLED, 2026-07-31.** This section was written as "the PG-Claude
> resource-audience defect". The deployed MindSort-Claude env value was read on
> 2026-07-31 and is:
>
> ```
> CLARITY_CLAUDE_AUDIENCE = https://www.priority-guard.com          <-- the ISSUER
> MCP_RESOURCE_URL        = https://mindsort-mcp.priority-guard.com/mcp
> ```
>
> **Not byte-equal.** §3's decision rule fires: **Part C must not merge**, and this is a
> **confirmed live isolation defect**, not a latent one. MindSort-Claude accepts
> issuer-audience tokens in production today, exactly as PG-Claude does.
>
> The framing that made this invisible was a code comment asserting
> *"PRODUCTION SHAPE (verified 2026-07-04): ... CLARITY_CLAUDE_AUDIENCE is set to the
> resource URL ... production env compensation is correct."* It was false, it was written
> as verified fact, and it was believed — it shaped this entire increment into treating
> MindSort as sound and PG-Claude as the problem. Corrected in
> `mcp_server/mindsort_claude/config.py`.
>
> **Severity is unchanged from the Layer 2 matrix: no live exploit.** `valid_audiences`
> is `[MCP_RESOURCE_URL, MCP_SERVER_URL, CLARITY_AUDIENCE]`, so the issuer is an EXTRA
> accepted audience rather than the one real tokens carry; production logs show every
> claude.ai flow carrying the resource-shaped `resource`, and the per-tool scope check
> still separates the apps. What is confirmed is that **the audience layer is dead in
> production on both servers**, not one.
>
> **Sequence to unblock Part C** (MindSort-Claude is not under review, so this does not
> touch PG's window):
> 1. Run the §5 step 9 SQL **scoped per app** — `resource IS NULL` counts the grants that
>    would break. Requires briefly re-opening the DB allow list, which is currently EMPTY,
>    so the query cannot run until it is. Read `resource_value`, not the shape label:
>    "safe" means **this app's own resource URL**, not merely non-NULL. A row carrying the
>    *other* app's resource would also break, and Part E row 5 proved the AS mints exactly
>    that shape.
> 2. If zero outstanding issuer-audience grants → set
>    `CLARITY_CLAUDE_AUDIENCE = https://mindsort-mcp.priority-guard.com/mcp` in Render.
> 3. Verify MindSort-Claude still serves `/mcp` after the redeploy.
> 4. **Then** merge `partc` — the guard now passes and permanently prevents regression.
>
> **✅ STEP 1'S GATING QUERY HAS RUN — 2026-07-31. Result: ZERO issuer-shaped tokens.**
>
> Across all **5,621** rows in `oauth_access_tokens`: `resource IS NULL` count = **0**,
> live such grants = **0**, `refreshable_but_no_expiry` = **0** on every row. Verified
> both by direct `WHERE resource IS NULL` count and by the grouped query, whose row
> counts sum to 5,621 — so the grouping covered every row.
>
> | App | `resource_value` | live grants | tightening breaks? |
> |---|---|---|---|
> | MindSort-**Claude** | `mindsort-mcp.priority-guard.com/mcp` | 9 | **No** — this is exactly the target value |
> | MindSort-OpenAI | `mindsort.priority-guard.com/mcp` | 3 | No — different server, own config |
> | PG-OpenAI | `pg.priority-guard.com/mcp` | 94 | No — different server, own config |
> | PG-**Claude** | `mcp.priority-guard.com/mcp` | 2 | **No** — this is exactly the target value |
> | PG-Claude (pre-custom-domain) | `priority-guardian-claude-mcp.onrender.com/mcp` | 0 | No — expired naturally, none live since 2026-05-27 |
>
> **Both `CLARITY_CLAUDE_AUDIENCE` and `PG_CLAUDE_AUDIENCE` are safe to tighten.**
>
> **And the finding is stronger than "safe".** The Rule 5 fallback exists in code, and
> Part E proved the AS will mint it — but **no client has ever triggered it**. The issuer
> entry in `valid_audiences` has never matched a real token. It is not a compatibility
> fallback being retired; it is **dead weight accepting an audience nothing legitimate
> carries**. The `onrender.com` row proves it survived even a domain migration unused.
> So §11 is not "accept a compatibility risk to gain isolation" — it is "remove a control
> that was never doing anything."
>
> Read `resource_value`, not the shape label, exactly as required: the MindSort-OpenAI
> and PG-OpenAI rows are non-NULL and *would* have been mislabelled "safe" by shape alone,
> while belonging to servers this change does not touch.

> **⚠️ STEP 2 IS NOT THE COMPLETE FIX — do not mistake it for done.** After setting the
> env var, `valid_audiences = [MCP_RESOURCE_URL, MCP_SERVER_URL, CLARITY_AUDIENCE]`
> becomes `[resource, origin, resource]`. **The bare origin is still accepted.** The full
> fix is three steps:
>
> | # | Change | Backlog |
> |---|---|---|
> | 1 | Set the audience env var to the resource URL | this section |
> | 2 | Delete the now-redundant `CLARITY_AUDIENCE` / `PG_AUDIENCE` entry from `valid_audiences` (provably redundant once step 1 holds and Part C's guard enforces it) | **3** |
> | 3 | Delete the `MCP_SERVER_URL` bare-origin entry | **10** |
>
> Step 1 alone leaves a second unnecessary audience accepted. Part C's guard enforces
> step 1's *invariant*, which is what makes steps 2 and 3 safe to take.
>
> That step-9 query has moved from "§11 rollout planning input" to **the gating item for
> Part C**.
>
> **The branch isolation was load-bearing, not cautious.** MindSort-Claude has
> `autoDeploy: yes` on commit to `main`, and Part C's guard hard-fails boot when
> audience ≠ resource URL. Merging `partc` would have taken MindSort-Claude down within
> roughly a minute. That is precisely the scenario §0.1(a) exists for, now confirmed
> rather than hypothetical.

**Not ordinary backlog. Record as a named, prioritized follow-up increment.**

**Read from source (working tree — confirm before acting):**
- `mcp_server/priority_guardian_claude/config.py` documents `PG_CLAUDE_AUDIENCE (e.g., https://www.priority-guard.com)` — the AS issuer, not a resource identifier
- `mcp_auth_dupl.py` builds `valid_audiences = [MCP_RESOURCE_URL, MCP_SERVER_URL, PG_AUDIENCE]` and comments `PG_AUDIENCE` as a "legacy fallback"
- `authorize.py` accepts `resource` from the client without validating it against the client's scopes or app (§0.3)

**What is NOT established:** the *effective* `PG_CLAUDE_AUDIENCE` value in the PG-Claude Render environment. The config docstring gives an example, not a guarantee. If production sets it to the resource URL, this finding narrows sharply. **Nobody has read that value** — it is a required input below.

**Assessment on current evidence:** resource-specific audience binding appears not to be providing the intended isolation on PG-Claude, and scope enforcement appears to be the effective isolation layer for cross-app separation within the suite. Audience validation still rejects arbitrary third-party audiences — what is absent is app-specific resource binding. Part E exists to verify the complete issuance and validation chain. **Treat this assessment as provisional until it does.**

**Why not fixed here:** requires coordinated changes to production environment configuration, accepted-audience construction, the `resource` validation path, potentially token-issuance compatibility for live connections, and a rollback plan — on an app currently in Anthropic review.

**Status:**
- PG-Claude is **in active Anthropic MCP directory review** (as of 2026-07-30) — imminently or already externally exposed.
- Treat as a **release gate for full RFC 9728 alignment**, scheduled immediately after the verdict, whichever way it lands.
- Anthropic performs periodic post-admission reviews. Admission does not close this.

**Empirical answer from Part E Layer 2 (2026-07-31) — §11 no longer needs to assume:**

The six-row issuance matrix ran the real flow (DCR → authorize → consent → token) against
the isolated test database. **All six rows mint, including both cross-binding rows:**

| # | Route | Scope | `resource` | Result | resulting `aud` |
|---|---|---|---|---|---|
| 1 | `/oauth/pg` | `pg.access` | omitted | MINTED | issuer (Rule 5 fallback) |
| 2 | `/oauth/mindsort` | `clarity.write` | omitted | MINTED | issuer (Rule 5 fallback) |
| 3 | `/oauth/pg` | `pg.access` | PG resource | MINTED | PG resource |
| 4 | `/oauth/mindsort` | `clarity.write` | MindSort resource | MINTED | MindSort resource |
| **5** | `/oauth/mindsort` | `clarity.write` | **PG resource** | **MINTED** | **PG resource** |
| **6** | `/oauth/pg` | `pg.access` | **MindSort resource** | **MINTED** | **MindSort resource** |

Neither `classify_scopes` nor the registered-scope check prevents cross-binding upstream.
The AS mints the token; **only the resource server's per-tool scope check** stands between
a cross-bound token and cross-app access. Behaviour is **symmetric**, so §11's fix can be
uniform rather than per-app.

**SEVERITY — read before scheduling.** The cross-bound token is **inert at both servers
today**: at PG-Claude the audience passes but the scope check rejects; at MindSort-Claude
the audience itself fails. There is **no live exploit**. The finding is that audience
contributes *nothing* to isolation, so scope carries a load alone that was meant to be
shared — which becomes exploitable only if scopes ever overlap between apps or a future
app reuses one. Row 1 has live reach (issuer-`aud` + `pg.access` is accepted by PG-Claude
today), but `sub` is the requesting user's own, so it grants access to data that user
already consented to — an open-DCR property, not the audience defect. **§11 is
architectural hardening on a fragile single control, not incident response.**

**Scope limits of the matrix:** it establishes what the AS mints *given this code*, not
what production is configured to do. `login_hint` is passed on every row (production
ChatGPT never sends it), so every row creates a fresh user and the **returning-user /
existing-consent path is never exercised** — if that path handles `resource` differently,
the matrix would not show it.

**Inputs the escalation increment needs:**
- **The `PG_ISSUER` comment correction** moved here from §8.2 — *"provider uses aud=iss"* is stale, enshrines the pre-RFC-9728 model, and would mislead anyone tightening audience validation. Correct it as part of §11's own diff, since §11 rewrites this area.
- **Step 1: run the `aud`-shape query** written but not executed under §5 step 9. Requires temporarily re-opening production database access (closed 2026-07-30, empty IP allowlist) and closing it again afterwards. **Rollout planning input, not a resolution.**
- §9.2 full issuance matrix — establishes reachability
- Effective PG-Claude Render env values
- Removal of the §9.3 `xfail(strict=True)` marker as part of its definition of done

---

## 12. Backlog to file (do not fix)

1. **Unadvertised `/oauth/*` proxy routes on both Claude MCP servers.** No discovery document advertises them. They remain externally reachable and sit outside both `OriginValidationMiddleware` and `BearerAuthMiddleware`, which gate on `path == "/mcp"` only. Characterise as *unadvertised, externally reachable legacy proxy surface* — not a vulnerability until auth, validation and rate-limiting on those paths are verified. The ChatGPT twin genuinely does advertise its equivalents.
2. **DCR default-scope semantics.** Claude connectors register via `/oauth/pg/register`, whose omitted-scope default is `pg.access`. Works today only because the client sends an explicit scope. Needs production DCR log evidence.
3. **`CLARITY_AUDIENCE` is provably redundant** once §7.1 byte-exact equality is enforced. The real fix is deleting the env var and its `valid_audiences` entry. Touches shared `clarity/mcp_auth.py`. **The Part C guard is a stepping stone, not the destination.**
4. **`MCP_RESOURCE_URL` normalization divergence.** PG-Claude applies `.rstrip("/")`; MindSort does not.
5. **`revoke_service.py` uses `jose`**, not PyJWT. **Specific failure mode to test:** `_try_revoke_access_token` relies on `jose.JWTError` firing for non-JWT input so control falls through to refresh handling. That handler and the broad `except Exception` both return `None`, and the endpoint returns 200 per RFC 7009 regardless — so a silently failing revocation is indistinguishable from a successful one, including to the caller. One targeted test settles it.
6. **Unknown-tool handling diverges:** `clarity` raises `InsufficientScopeError` (403); `priority_guardian_claude` raises `UnauthorizedError` (401). Both fail closed.
7. **Correlation-ID defensiveness diverges:** PG-Claude checks `meta is None`; clarity checks `isinstance(meta, dict)`. PG's is weaker.
8. **Dead `PyJWKClient` import** in `priority_guardian_claude/mcp_auth_dupl.py`.
9. **CORS default diverges:** PG-Claude `[]`; MindSort `["https://claude.ai"]`. Dev-only.
10. **`MCP_SERVER_URL` in both accepted-audience lists** — bare-origin alias. Tighten after Part E is green.
11. **`final_resource = None` → `aud = OAUTH_ISSUER` fallback** in `token_service.py`.
12. **Revoked-token behaviour integration test** — useful as a deployed-build regression test. Deferred on runway grounds.
13. **`authorize.py::_normalize_redirect_uri` IPv6 host parsing.** `parsed.netloc.lower().split(":")[0]` is IPv4-only; on `[::1]:41234` it yields `"["`, making the `::1` entry in its own localhost tuple unreachable dead code. Shared with the ChatGPT authorize path on two published apps — fix both layers together or not at all.
14. **Render's `buildCommand` API field is not what Render executes** for these Python services. Three services built successfully after `requirements_fullbackend.txt` was deleted (shared-backend and pg-mcp 2026-07-07, clarity-mcp 2026-07-20) while running a command that provably exits 1 — most plausibly Render auto-detects poetry from `pyproject.toml`. Consequence: any future reasoning from that field is unreliable. Not a deploy blocker; the stale filename should still be cleaned up.
15. **The ChatGPT prefix rule has the same raw-vs-parsed defect** (pre-existing, unchanged by Part B). `https://chatgpt.com/connector/oauth/\tABC123` passes `uri.startswith(allowed)` and is persisted raw. It still resolves correctly because `_normalize_redirect_uri` strips identically at authorize — same reasoning as §6.2 — but the validate/persist mismatch is identical in shape. **Do not fix in this increment:** it touches the ChatGPT path on two published apps. Fix alongside backlog item 13 if both are ever addressed.
16. **`doc/testing_baseline_2026-07-04.md` is stale by ~6×** — records 5 known-red, actual is 34. Needs regeneration with a fresh per-failure triage. A stale baseline is worse than none: it made "34 matches the known-red set" read as a clean result when it was a six-fold discrepancy. **Until it is regenerated, §16's "report the delta against baseline" gate returns a meaningless number.**
17. **Refresh-token revocation — two dead tests, not a coverage gap.** `test_revoked_token_cannot_be_used` and `test_refresh_rotation_marks_old_revoked` (`test_increment_13_unit.py`) fail on stale mocks before reaching the behaviour they name. **Redundant coverage exists and is green:** `test_token_service_locking.py:57` asserts the `revoked` filter appears in the emitted SQL of `exchange_refresh_token`, and `:60` asserts the original token is revoked after exchange, plus integration coverage in `test_oauth_revocation_integration.py`. This is dead-test cleanup, not an untested security behaviour. Out of §4 scope (another increment's file).
18. **Unit tests are database-dependent via an autouse fixture.** `tests/conftest.py:148`'s autouse `cleanup_db` pulls in `setup_test_database`, so every test under `tests/unit/` requires a reachable `postgresql://localhost/priority_guardian_test`. §13 specifies "no database" for unit tests; the harness violates it repo-wide and predates this increment. Consequences: the unit suite fails entirely on a machine without Postgres running, and the unit/integration distinction in this repo is nominal. Harness-wide fix — out of §4 scope.
19. **A write from a deleted user's still-valid token raises an unhandled FK `IntegrityError`**, most likely surfacing as a 500. The resource server performs no user-existence check and `validate_user_id_header` validates UUID shape only, so the request reaches the backend and fails on the `core_users` foreign key. Narrow window (≤ `exp` + leeway after a manual deletion), rare trigger, but an ungraceful failure on a documented path.
22. **No localhost-in-production guard on `CLARITY_CLAUDE_MCP_SERVER_URL`.** `OAUTH_ISSUER_BASE` has one; `MCP_SERVER_URL` does not, and it defaults to `http://localhost:8003`. Part C's audience guard now catches this **transitively** — a localhost-derived `MCP_RESOURCE_URL` cannot byte-match a production audience, so boot fails — but that is a side effect of a different control, not a designed one. If the audience guard is ever relaxed or removed, the gap reopens silently. Add a direct guard alongside the existing localhost check.
23. **`doc/OAuth_Hard_Requirements.md` §7 TLS table lists only `/oauth/pg/revoke`.** All three revoke routes are in fact mounted and functional — `revoke.py:28-30` registers `focused`, `pg` and `mindsort`, and all three return 422 (not 404) on a malformed body in production. So this is a **table omission, not a missing endpoint**. Add the other two rows.
21. **No reachable path revokes OAuth tokens at the AS — verified 2026-07-30.** `POST /oauth/pg/revoke` is mounted and functional (returns 422 on a malformed body, not 404), but production logs show **zero `oauth.revoke.*` events across the full 30-day retention window** — filter validated, since the same mechanism returns `oauth.register.success` and `oauth.token.success`. Neither Claude nor ChatGPT calls it on connector removal. The in-app disconnect tool does not revoke AS tokens either: `priority_guardian/routers/offboarding_router.py` states *"PG OAuth session tokens are NOT revoked here. Disconnect only revokes Google Calendar access."* So `revoked`, `exchange_refresh_token`'s `revoked == False` filter, and the whole revocation service are live code with **no live caller** — token expiry is the only mechanism that ends access. Consequence to assess (legal, not engineering): the published policy §4 says *"withdraw consent at any time by disconnecting the app"*, which does not describe what disconnect does at the authorization server.
20. **No user-initiated account-deletion code path — and the promised email route may be unfulfillable.** The published privacy policy routes Art. 17 erasure to `support@priority-guard.com`, fulfilled manually. `priority_guardian/routers/offboarding_router.py` exposes `/disconnect` only, and its docstring records the omission: *"No DELETE /delete-data yet (later increment)."* The single automated `DELETE FROM core_users` (`jobs/retention_cleanup.py`) is six-month inactivity cleanup, not erasure.

    **Manual fulfilment is not the problem — identification is.** `CoreUser` stores only `id` (UUID), `chatgpt_user_id`, `openai_subject`, `created_at`. No email, no name. For Claude users both pseudonymous columns are NULL (session-cookie UUID only). A request arriving by email therefore cannot be mapped to a row, and the same gap applies to §9's promised email data export.

    **What actually works — verify before relying on this.** MindSort exposes `delete_my_data`, which works because the tool call carries the JWT and therefore the `user_id`. **PG-Claude's advertised tool set contains no deletion tool** — not account-wide, not per-item (`create_priority`, `get_patterns`, `get_priorities`, `get_priority_events`, `inspect_adapt`, `onboarding_calendar_setup`, `render_weekly_report`). Confirm against the MCP server source: an unadvertised tool, admin route, or backend endpoint could exist. If confirmed, email is the only **documented user-facing** route for PG erasure — and it is the route that cannot identify the requester.

    **Two distinct problems, and the second is harder.** *Identification* — which row belongs to this person? *Authentication* — is the sender actually the data subject? A support identifier addresses the first and only weakly the second, since possession of a string is thin evidence. In pseudonymous systems authentication is usually the harder problem. Both belong in the runbook.

    **The gap compounds for users who have already left.** The most likely person to email "delete my data" has already removed the connector, so any in-app route — including reading a support identifier out of the app — is unavailable to them by definition. Any correlation mechanism must state its fallback for that case, or admit it has none.

    **Partial mitigation already in place:** `jobs/retention_cleanup.py` deletes users dormant for six months with no active connection or consent. A departed user's data is therefore erased automatically, just not "without undue delay." That is a true and disclosable fact, not a substitute for a request process.

    **Decision needed — not "build an endpoint":** (a) a low-data correlation mechanism — a user-visible support identifier derived from `user_id` by keyed one-way construction rather than exposing the raw UUID, required on email requests, with authenticated in-app deletion kept as the preferred route; (b) align the policy wording to what can actually be executed. **GDPR Art. 11(2) is not a clean exit:** Arts. 15–20 reapply the moment the data subject supplies information enabling identification, and such information cannot be refused. Pseudonymised data remains personal data where attribution is possible. Write the runbook covering identity verification, deletion scope, database procedure, audit evidence, and response deadline — note the policy commits to 30 days, which is stricter than Art. 12(3)'s one month, and that commitment binds.

---

## 13. Unit test instructions

Unit tests only. No network, no database, no live services.

**Part B — redirect URI validation**
- Cover **every row** of §6.3, one assertion per row.
- Malformed-port cases must assert clean rejection **and that no exception propagates**.
- **Derive the allowlist by instantiating `Settings()` under `ENV=production` and reading `OAUTH_ALLOWED_REDIRECT_URIS`**, then assert it equals `_CHATGPT_REDIRECT_URIS`. Reading the class constant directly is **not sufficient**: that catches someone editing `_CHATGPT_REDIRECT_URIS`, but misses `build_allowed_redirect_uris` (`config.py:165`) no longer sourcing from it — which is the drift that actually matters. Env fixtures (`ENV`, `INTERNAL_API_SECRET`, `OAUTH_ISSUER`, RSA keys, `DATABASE_URL`, `ENCRYPTION_KEY`) are required; supply them rather than reaching for the constant. A hardcoded fixture copy is not acceptable either.
- Cover every whitespace / control-character row in §6.3, asserting rejection.
- Assert `http://[::1]:41234/callback` is **rejected**, with a comment recording that this is deliberate exclusion (§6.2), not an oversight.
- Cross-check every accepted row against `_normalize_redirect_uri` (§6.5).
- Assert empty list rejected.
- Assert the production allowlist is unchanged for every non-loopback entry.

**Part C — config guard**
- Raises in production-like ENV when the audience var is unset.
- Raises when the value differs from `MCP_RESOURCE_URL` by a trailing slash. *(This test is the point of §7.1 — it must fail if any normalization creeps in.)*
- Raises when the value differs only by case.
- Raises when the value equals `OAUTH_ISSUER_BASE`.
- Raises when the value equals `MCP_SERVER_URL` (origin without path).
- Raises when the value is another app's resource URL on the same origin.
- Does **not** raise on byte-exact match.
- Does **not** raise in dev/test ENV.
- Cover every value in `_PRODUCTION_ENV_VALUES` — including `prod` and `staging`.

**Mandatory per-test discipline:** for **every** test, state what bug would still pass it. v2 of this briefing shipped a test that would have passed for the wrong reason (§0.4); that is precisely what this discipline exists to catch. A test whose honest answer is "none" is almost certainly overstated — say so.

**Stating the bug is necessary but not sufficient — it catches omission, never vacuity.** Three assertions in this increment named the correct bug in the docstring while being structurally unable to detect it:

| Assertion | Why it could not fail |
|---|---|
| `"invalid_redirect_uri" not in body` | that string is a **log field only**; both rejection bodies say something else |
| `response.json()["redirect_uris"] == [uri]` | `register_client.py` returns `register_request.redirect_uris` — the **request**, never the stored row |
| AST scan for the bug-caught line | confirms the line **exists**, not that the assertion bites |

**For every load-bearing assertion, demonstrate it by mutation:** break the behaviour under test in the source, confirm the test fails, restore byte-identically (§10.6–10.7). Apply this by default, not on request. It matters most in Part E — a vacuous pass on audience isolation would be considerably worse than any of the three above.

---

## 14. Integration test instructions

Separate files from §13. Environment per §9.5.

**Part B — end-to-end DCR + authorize**
- DCR with `["http://127.0.0.1:53821/oauth/callback"]` → 200, client row persists that exact URI.
- Subsequent `/authorize` with that exact URI → consent renders, no `invalid_redirect_uri`.
- DCR with `http://[::1]:41234/callback` → 400 (deliberate exclusion, §6.2).
- DCR with `http://localhost.evil.com:8080/oauth/callback` → 400.
- DCR with `http://localhost:abc/oauth/callback` → 400, not 500.
- Run across **all three** register routes. §6.4 must hold.

**Part E** — per §9.

---

## 15. Production-readiness in context

Evaluate at **increment** scope. Product production-readiness is established only by completed implementation, green tests, a committed SHA, verified configuration, deployment, and post-deployment checks. Whether this increment reaches deployment is decided by §0.1, not assumed either way.

- **Scalability:** no new per-request I/O, no new DB access, no new network calls on the hot path. MCP servers remain stateless.
- **GDPR / data retention:** no new personal data stored, read, or logged. Part D documents an existing retention-relevant behaviour; it does not change one.
- **Logging rule:** never log raw tokens, token fragments, authorization codes, refresh tokens, or client secrets. Decoded user-bound claims must be redacted or minimized. Canonical configured resource identifiers *are* service identifiers, not user identifiers, and may be logged where operationally necessary.
- **Latency:** Part B affects DCR only (infrequent, rate-limited). Part C is boot-time only. Neither touches tool-call latency.
- **Cross-platform consistency:** demonstrated by §6.4 plus integration tests across all three register routes.
- **Availability:** Part C is designed to hard-fail boot. Token semantics are unchanged, but a valid token against a service that will not start is still an outage. This is why §0.1 exists.

---

## 16. Pre-deploy gate

**Complete this gate at implementation time so the increment is deploy-ready the moment §0.1's evidence rule says to ship.**

Before committing:
- Read `doc/OPERATIONS_PREDEPLOY.md` in full; execute every applicable item.
- Read `doc/OPERATIONS_MIGRATIONS.md`; state explicitly whether any migration is required (none expected).
- Check both for **additional pre-deploy tasks** beyond the obvious checklist and report what you found.
- Run the full unit and integration suites, not only new tests. Report the delta against `doc/testing_baseline_2026-07-04.md`.

No `WIDGET_VERSION` bump is required — no widget code is touched. Confirm in your report.

---

## 17. Definition of done — report requirements

In this order:

1. **Commit SHA** for the reviewed state. Uncommitted work is not done. A report without a SHA is rejected without review.
2. Part A evidence: both SHAs, drift diff if any, production discovery documents, the §3 decision-rule outcome, the PyJWT `aud` comparison finding (step 6), JWKS fixture feasibility (step 7), **the production log check result with explicit attribution uncertainty (step 8)**, the SQL supplied for step 9, and Render rollout behaviour (step 10).
3. Per part: what changed, in which files, and which briefing requirement it satisfies.
4. Per test: what bug would still pass it (§13).
5. Part E results, split by layer (§9.1 / §9.2) and by server (§9.3), with decoded token claims and the **full six-row issuance matrix**. State the rejection **layer** for every rejection, never just the status code. Confirm the PG marker is `strict=True`.
6. Part D findings, with exact quoted stale strings and locations.
7. Test isolation mechanism for the MindSort tests and how you verified it.
8. Explicit §6.4 non-regression confirmation, item by item, **with the discovery-document diff attached as proof**.
9. §6.6 interaction assessment as written into the ADR.
10. Anything you could **not** verify, could not reach, or had to assume. Explicitly, not buried.
11. Adjacent issues noticed but not fixed — flagged only.
12. **Deployment evidence**, per §0.1: the log findings, which row of the evidence table applies, the seven-condition gate with each condition marked and evidenced, and the sequencing position of each part. **Do not include a deploy/hold recommendation** — present the evidence and stop.

**If any requirement here is unclear, contradicts the codebase, or conflicts with a canonical document: stop and report. Do not resolve the ambiguity by choosing.**
