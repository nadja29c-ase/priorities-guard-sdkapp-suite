# §17 Report — Claude Connector Auth: Loopback, Audience Guard, Revocation Semantics

**Date:** 2026-07-31
**Increment:** `inc_claude_auth_loopback_audience_revocation.md` (v4.1)

---

> ## ⚠️ AMENDMENT — 2026-07-31, after the env values were supplied
>
> The deployed MindSort-Claude value is
> **`CLARITY_CLAUDE_AUDIENCE = https://www.priority-guard.com`** — the **issuer**, not
> the resource URL. **Not byte-equal.** §3's decision rule fires:
>
> 1. **Part C must NOT merge.** It stays on `partc-mindsort-audience-guard`.
> 2. This is a **confirmed live isolation defect**, not a latent one.
> 3. **§11's scope doubles** — it covers **both** Claude resource servers, not PG-Claude
>    alone.
>
> **Two statements elsewhere in this report are now wrong and are withdrawn:**
>
> - Any characterisation of MindSort-Claude as sound under its production config. It is
>   not. It accepts issuer-audience tokens in production today, exactly as PG-Claude does.
> - Part E Layer 1's fixtures were described as "production-shaped". They are
>   **target-shaped** — they model the posture §11 will establish. The docstring's caveat
>   ("does NOT establish what production is configured to do") was honest and remains
>   correct; the *label* was wrong. Corrected in the test file.
>
> **The artifact that caused this** was a code comment in
> `mcp_server/mindsort_claude/config.py` asserting *"PRODUCTION SHAPE (verified
> 2026-07-04) … production env compensation is correct."* It was false, written as
> verified fact, and believed — it framed MindSort as the safe server for this entire
> increment. Corrected. **This is the fourth artifact in this increment found to state a
> confident falsehood** (after `OAuth_Hard_Requirements` §3 and §13, the stale
> `thought_items` data-shape claim, and the stale repo copy of the privacy policy), and
> it is the one that did the most damage, because it was the most specific: a named date
> and a claimed verification.
>
> **Severity is unchanged from the Layer 2 matrix: no live exploit.** The issuer is an
> *extra* accepted audience, not the one real tokens carry; production logs show every
> claude.ai flow carrying the resource-shaped `resource`; and the per-tool scope check
> still separates the apps. What is confirmed is that the **audience layer is dead in
> production on both servers**.
>
> **The branch isolation was load-bearing, not cautious.** MindSort-Claude auto-deploys
> on commit to `main`, and Part C's guard hard-fails boot on exactly this mismatch.
> Merging would have taken it down within about a minute — the §0.1(a) scenario,
> confirmed rather than hypothetical.
>
> **Unblock sequence** (MindSort-Claude is not under review; this does not touch PG's
> window): run §5 step 9's SQL scoped to MindSort clients → if zero outstanding
> issuer-audience tokens, set the Render var to the resource URL → verify `/mcp` still
> serves → then merge `partc`. **The step-9 query has moved from "§11 rollout planning"
> to the gating item for Part C.**

---

## 1. Commit SHAs for the reviewed state

**`main` — Parts A, B, D, E and documentation. Tip: `21f615a`**

| SHA | Part | What |
|---|---|---|
| `5fc435b` | B | RFC 8252 loopback redirect URIs at DCR, any port |
| `283df9b` | B | Empty-port rationale corrected |
| `b8d4bef` | B | Round-1 review fixes: validate/persist divergence, effective-settings test |
| `110f20a` | B | §14 integration coverage, DCR → authorize |
| `978d4b1` | B | Vacuous assertion fixed on the load-bearing authorize test |
| `b916329` | B | Assert the persisted DB row, not the endpoint echo |
| `fea7a38` | — | Backlog 21 + briefing edits |
| `9430d2e` | D | **ADR_006** — token revocation semantics |
| `9b62593` | D | ADR: audit-log exemption, identification gap, evidence scope |
| `8526912` | D | ADR: proportionality claim + revisit trigger corrected |
| `37a915b` | D | §8.4: `OAuth_Hard_Requirements` v1.2, `revoke_service` docstring |
| `65d11d6` | E | Layer 1 — validator audience isolation, both Claude servers |
| `1b12ed3` | E | Fixture saves all ten `REBOUND_GLOBALS` |
| `c0e14c1` | E | Layer 2 — six-row `(resource, scope)` issuance matrix |
| `2f36291` | E | Rows 5/6 pinned rather than recorded |
| `21f615a` | — | Briefing pass + `OAuth_Hard_Requirements` v1.3 (§12a) |

**`partc-mindsort-audience-guard` — Part C only. Tip: `4f8a297`**

| SHA | What |
|---|---|
| `28acf52` | Boot guard on `CLARITY_CLAUDE_AUDIENCE` |
| `4f8a297` | Contradicting comment + stale module header corrected |

**`partc-backup-before-split` (`da032db`)** — pre-restructure state, retained until this report is accepted.

**Branch base:** `partc` descends from `main` at `21f615a`, so a later merge is a
fast-forward or trivial. Verified at ref level, not inferred.

---

## 2. Part A — evidence

**Working-tree SHA at Part A:** `1532b7d`. **Deployed backend SHA:** `0b05a69`
(committed 2026-07-06, deployed manually 2026-07-07).

**Drift:** the deployed SHA is ~24 days old but `backend/` is **byte-identical** — zero
commits touching `backend/` in the range; `config.py`, `client_metadata.py` and
`authorize.py` all identical; no migration drift; no dependency drift; single Alembic
head. `shared/` also identical (checked because `backend/core/logging.py:2` imports from
it — an earlier claim that the backend imports nothing outside `backend/` was unsound and
was corrected).

**Production discovery documents** (fetched live, full JSON recorded in-session):

- PG-Claude → `resource: https://mcp.priority-guard.com/mcp`, AS `https://www.priority-guard.com`, scopes `["pg.access"]`
- MindSort-Claude → `resource: https://mindsort-mcp.priority-guard.com/mcp`, same AS, scopes `["clarity.write"]`
- AS document → issuer `https://www.priority-guard.com`, all endpoints under `/oauth/pg/*`, S256 only, `token_endpoint_auth_methods_supported: ["none"]`

Root and `/mcp`-suffixed PRM documents are identical per server. No hard-stop triggered.

**Validator call sites:** one production site — `register_client.py:124`, with
`settings.OAUTH_ALLOWED_REDIRECT_URIS` at `:126`. All others are tests.
`OAUTH_ALLOWED_REDIRECT_URIS` typed `list[str]` at `config.py:70`, built at `:174`.

**Authorize matches the client's own URIs** (§5 step 5): `authorize.py:528-532` builds
`normalized_registered` from `client.redirect_uris` and rejects at `:535`. Exact set
membership, not the global allowlist.

**PyJWT `aud` semantics (§5 step 6) — proven, not read.** PyJWT **2.10.1**. Source
`api_jwt.py:365-410` normalises both sides to lists and set-intersects. Empirically, with
real RS256 tokens: exact match ACCEPTED; trailing-slash, case and prefix variants all
rejected with `InvalidAudienceError`; list membership accepted. This is what justifies
§7.1's byte-exact rule.

**JWKS fixture feasibility (§5 step 7):** yes. Pattern already exists at
`tests/unit/mcp_priority_guardian/test_jwt_grace_period.py:80-87` — patch `_jwks_cache`,
mock `fetch_jwks` to a no-op and `get_signing_key` to a test public JWK. Reused in Part E.

**Production DCR log check (§5 step 8), with attribution uncertainty stated:**
Across the full 30-day retention window — 3 × `oauth.register.success`, all
`client_name: "Claude"`; **zero** loopback redirect URIs; **zero** `invalid_redirect_uri`
or DCR 400s. **Attribution to a reviewer is not possible from logs** (no distinguishing
user-agent on `oauth.*` events).

**Step 9 SQL — written, not run**, per instruction. Schema verified against
`models.py` (`oauth_access_tokens`, `t.resource`, `core_connections` joined on the
`client_id` string with `connection_type='oauth_provider'`, `c.provider` as client name).
`resource IS NULL` **is** the issuer-shaped case per Rule 5 (`token_service.py:174-176`) —
there is no literal issuer string to match. Filed as §11 step 1.

**Render rollout (§5 step 10):** partially established. Backend has
`healthCheckPath: "/health"`; PG-Claude MCP has **none configured**. Could not verify
Render's zero-downtime semantics for single-instance starter services.

**§0.1(a) auto-deploy — machine-read, contradicting the briefing's assumption:**
shared backend **no**, PG-Claude MCP **no**, **MindSort-Claude yes** (`commit`, `main`).
So Part B carries no accidental-deploy risk; **Part C does**, which is why it is
branch-isolated.

---

## 3. Per part

### Part B — loopback redirect URIs at DCR
Files: `backend/core/oauth_provider/validators/client_metadata.py`, plus unit and
integration tests. Satisfies §6.2, §6.3, §6.4, §13, §14.

`_is_loopback_redirect_uri` added as an **additive** first check inside `_is_allowed`;
every non-loopback URI takes the existing allowlist path unchanged. Accepts only:
scheme exactly `http`; parsed hostname exactly `localhost` or `127.0.0.1`; any valid port
or absent with port `0` rejected; approved paths only; no query, fragment or userinfo;
and the raw string must survive `urlunsplit(urlsplit(uri)) == uri`.

**IPv6 `::1` deliberately excluded** — `authorize.py:213` strips ports with
`netloc.split(":")[0]`, IPv4-only, yielding `"["` for `[::1]:41234`. Accepting it at DCR
would let a client register a URI it could never authorize with. Verified: of every URI
the validator accepts, `[::1]` was the only one authorize rejected.

`backend/core/config.py` deliberately untouched — the two `6274` entries are now
redundant but not wrong, and §6.5 says leave them.

### Part C — MindSort-Claude audience boot guard *(branch, not merged)*
File: `mcp_server/mindsort_claude/config.py` + tests. Satisfies §7.1, §7.2, §13.

Implemented as a **pure function** called at module level, so tests exercise every branch
without `importlib.reload` — which in this package would re-trigger the `REBOUND_GLOBALS`
shim. "Explicitly set" reads `os.getenv` directly, because the module value holds the
default and an `is None` check could never fire.

### Part D — ADR_006 + stale-artifact corrections
Files: `doc/ADR_006_token_revocation_semantics.md` (new),
`doc/OAuth_Hard_Requirements.md` (v1.1 → v1.3),
`backend/core/oauth_provider/services/revoke_service.py` (docstring).

### Part E — audience isolation, two layers
Files: `tests/unit/mcp_claude_mindsort/test_audience_isolation_validator.py`,
`tests/integration/oauth_provider/test_audience_issuance_matrix.py`.

---

## 4. Part E results

### Layer 1 (§9.1) — validator, per server

Every rejection is asserted as `jwt.InvalidAudienceError` **specifically**. Because
`validate_jwt` raises before returning claims and scope enforcement happens downstream in
tool dispatch, that single assertion establishes both halves: **rejection occurred at the
audience layer, and scope enforcement was never reached.**

| Server | Token `aud` | Scope | Result | Rejection layer |
|---|---|---|---|---|
| MindSort-Claude | own resource URL | `clarity.write` | **ACCEPTED** (positive control) | — |
| MindSort-Claude | AS issuer | `clarity.write` | rejected | **audience** |
| MindSort-Claude | PG resource URL | `clarity.write` | rejected | **audience** |
| MindSort-Claude | third-party URL | `clarity.write` | rejected | **audience** |
| PG-Claude | own resource URL | `pg.access` | **ACCEPTED** (positive control) | — |
| PG-Claude | MindSort resource URL | `pg.access` | rejected | **audience** |
| PG-Claude | third-party URL | `pg.access` | rejected | **audience** |
| PG-Claude | AS issuer | `pg.access` | **xfail(strict=True)** — see below | — |

**Two positive controls, one per server.** Without them a broken JWKS mock would make
every rejection pass for reasons unrelated to audience.

**The environment these tests represent — a stated limit.** Both servers' audience
defaults are **issuer-shaped** (`clarity/config.py:153`, `pg_claude/config.py:125`), so
run against dev defaults an issuer-`aud` token is accepted by both. The MindSort tests
therefore patch **production-shaped** config explicitly, and a dedicated test asserts the
dev defaults are still issuer-shaped so the patching is not later removed as redundant.
**This establishes what each validator accepts given a config. It does NOT establish what
production is configured to do.**

**PG marker confirmed `strict=True`.** It uses PG's **real code default** (issuer), so it
characterises the actual defect; an earlier draft patched it production-shaped and could
not see the defect at all. Verified by mutation: making PG's default resource-shaped
produces `[XPASS(strict)]` and fails the suite, forcing marker removal — which is §11's
definition of done.

### Layer 2 (§9.2) — the full six-row issuance matrix

Real flow: DCR → `/authorize` → consent POST → token exchange, against the isolated test
database.

| # | Route | Scope | `resource` | Result | resulting `aud` |
|---|---|---|---|---|---|
| 1 | `/oauth/pg` | `pg.access` | omitted | **MINTED** | issuer (Rule 5 fallback) |
| 2 | `/oauth/mindsort` | `clarity.write` | omitted | **MINTED** | issuer (Rule 5 fallback) |
| 3 | `/oauth/pg` | `pg.access` | PG resource | **MINTED** | PG resource |
| 4 | `/oauth/mindsort` | `clarity.write` | MindSort resource | **MINTED** | MindSort resource |
| **5** | `/oauth/mindsort` | `clarity.write` | **PG resource** | **MINTED** | **PG resource** |
| **6** | `/oauth/pg` | `pg.access` | **MindSort resource** | **MINTED** | **MindSort resource** |

**All six mint, including both cross-binding directions.** Neither `classify_scopes` nor
the registered-scope check prevents cross-binding upstream. The AS mints; **only the
resource server's per-tool scope check** stands between a cross-bound token and cross-app
access. Behaviour is **symmetric**, so §11's fix can be uniform.

**Severity — the qualifier that determines §11's priority.** The cross-bound token is
**inert at both servers today**: at PG-Claude the audience passes but scope rejects; at
MindSort-Claude the audience itself fails. **There is no live exploit.** The finding is
that audience contributes *nothing* to isolation, so scope carries alone a load meant to
be shared — exploitable only if scopes ever overlap or a future app reuses one. Row 1 has
live reach, but `sub` is the requesting user's own, so it grants access to data that user
already consented to: an open-DCR property, not the audience defect. **§11 is
architectural hardening on a fragile single control, not incident response.**

**Scope limits:** establishes what the AS mints *given this code*, not what production
does. `login_hint` is sent on every row (production ChatGPT never sends it), so every row
creates a fresh user and **the returning-user / existing-consent path is never
exercised**.

---

## 5. Test isolation (§9.4) and how it was verified

MindSort tests use a locally-defined `restore_mcp_auth_globals` saving **all ten**
`REBOUND_GLOBALS`, matching `test_scaffold.py`'s tuple. The tuple is **hardcoded, not
imported** — importing it from `mcp_auth_dupl` would execute the shim and cause the
contamination the fixture exists to undo. PG-Claude is standalone and correctly carries
no such constraint (§9.4 says not to impose it there).

Verified by mutation in both directions rather than by reasoning: adding the issuer to
MindSort's accepted audiences fails the MindSort issuer case; making PG's default
resource-shaped turns the characterization into `[XPASS(strict)]`. Sources restored
byte-identical after each.

---

## 6. §6.4 non-regression — item by item

| Requirement | Status | Evidence |
|---|---|---|
| `chatgpt.com/connector_platform_oauth_redirect` accepted at DCR | ✅ | unit + integration |
| `chatgpt.com/connector/oauth/` retains **prefix** semantics | ✅ | unit test asserts dynamic ids accepted and that prefix does not degrade to substring |
| `platform.openai.com/apps-manage/oauth` accepted | ✅ | asserted against the **derived** allowlist |
| Both Claude callbacks accepted | ✅ | unit + integration |
| Exact registered-URI matching at `/authorize` unchanged | ✅ | integration: an unregistered but valid-shaped loopback URI is **refused with 400** |
| **All discovery documents byte-identical** | ✅ | **file-level proof:** the commits touch only `client_metadata.py` and its tests; no discovery-producing file (`oauth_provider/discovery.py`, `mindsort_discovery.py`, `mcp_server/*/discovery*.py`) appears in the diff. Unchanged **by construction** |
| `aud` / `resource` issuance unchanged | ✅ | Part B touches neither |
| Every existing OAuth test remains green | ⚠️ **See below** |

**Correction to the last row, stated precisely:** the requirement says "remains green."
**Thirty-four are red.** The accurate claim is **"no new failures introduced"** — the
delta is zero, verified by running the same suites at `HEAD` before and after. Given how
much of this increment turned on assertions that could not fail, the report should not
close on a claim that is not literally true.

**§16 delta against `doc/testing_baseline_2026-07-04.md`:** the baseline records **5**
known-red in `core` + `oauth_provider`; the measured figure is **34**. All 5 documented
failures are still failing; **29 have accumulated since 2026-07-04 and 25 remain
untriaged.** Four were triaged in-pass (the `TestRedirectURIExactMatch` set — all
`assert 400 == 302`, stale expectations, and RFC 6749 requires the 400). The baseline
document is stale by roughly 6× (backlog 16).

---

## 7. §6.6 interaction assessment, as written into the ADR

Widening loopback DCR slightly enlarges a pre-existing path: register via
`/oauth/pg/register` with a loopback redirect, authorize while omitting `resource`,
obtain a token with `aud = issuer` that PG-Claude accepts.

**That capability already existed** — `http://localhost:6274/oauth/callback` has been
allowlisted in production throughout. Part B widens the **port range**, not the class of
path, and every step still requires the user to complete a consent screen. **Marginal
increase in a pre-existing exposure, not a new vector.**

---

## 8. Part D findings — exact quoted strings

**`Shared Backend Architecture Design.pdf` is NOT in the repository**, so these are
reproduced **as recorded in the briefing** and were not independently verified by me.
Three of four were later confirmed verbatim by the reviewer, who can reach the file.

| Location | Exact string | Assessment |
|---|---|---|
| Layer-2 diagram, labelling the MCP server | *"Checks expiration, revocation, scope, and signature (RS256)"* | **Stale** — the RS performs no revocation lookup |
| §10.1B | *"Expired or revoked tokens → 401"* | True at the backend; **misleading about the RS**. *Not reconfirmed — treat as unverified* |

**Accurate, do not change:** §13 Data Flow Summary (*"Backend validates token (signature,
expiration, revocation, scope)"*) and *"Token Verification Process (MCP Server — Every
Tool Call)"*, which already states the MCP server does not access the DB or touch
`revoked_at`.

**Also noted:** the PDF hedges twice on *"JWKS endpoint (stateless verification), or
optional introspection endpoint"* — plausibly where the diagram label drifted. And its
verification section is headed *"Executed inside the Focused MCP Server"*; Focused is
deprecated, so the PDF's staleness is broader than these strings.

**No markdown architecture correction note was added** — §8.4 asks for one, but no
`doc/*.md` makes an RS-revocation claim. `Architecture_clarity_v1.0.md` has none.
Manufacturing the deliverable would have been worse than reporting its absence.

---

## 9. Could not verify / had to assume — explicit

1. **Production env values.** `CLARITY_CLAUDE_AUDIENCE`, `CLARITY_CLAUDE_MCP_RESOURCE_URL`, `CLARITY_CLAUDE_MCP_SERVER_URL`, MindSort deployed SHA. The Render MCP has no env-var read, and §0.1(c) forbids writing. **Part C cannot merge without these.**
2. **What production is configured to do** for audiences. Part E establishes code-shape behaviour given a config, never deployed posture.
3. **The residual acceptance window's real value.** Stated as a formula; both inputs env-derived and unpinned.
4. **Whether the backend build currently succeeds.** Its `buildCommand` references `requirements_fullbackend.txt`, deleted 2026-04-24 — yet three services built successfully after that date (most recently clarity-mcp on 2026-07-20). Conclusion: **the API's `buildCommand` field is not what Render executes** for these Python services. Not a blocker; backlog 14.
5. **Reviewer attribution in logs**, and DCR history before 2026-07-21.
6. **Render's zero-downtime behaviour** for these services.
7. **Whether a post-deletion read returns 404 or an empty payload** — unchecked; the ADR does not claim either.
8. **PDF §10.1B string** — recorded from the briefing, not reconfirmed.

---

## 10. Adjacent issues flagged, not fixed

Backlog 13–23, filed in the briefing. The notable ones:

- **13** — `authorize.py` IPv6 host parsing is IPv4-only; shared with the ChatGPT path
- **14** — Render's `buildCommand` API field is unreliable as a source of truth
- **15** — the ChatGPT prefix rule shares Part B's raw-vs-parsed defect; pre-existing, two published apps
- **16** — the testing baseline is stale by ~6×
- **19** — a write from a deleted user's live token raises an unhandled FK `IntegrityError`, likely a 500
- **20** — no user-initiated account-deletion path; Art. 17 is fulfilled manually, and `CoreUser` holds no email or name to identify a requester by
- **21** — **no reachable path revokes tokens at the AS.** `/oauth/*/revoke` is mounted and functional but **zero `oauth.revoke.*` events in 30 days**; in-app disconnect revokes Google Calendar only. The published policy's *"withdraw consent by disconnecting"* does not describe what disconnect does at the AS — a legal judgement, not an engineering one
- **22** — no direct localhost guard on `MCP_SERVER_URL`; Part C catches it transitively
- **§4 vs §8.2 conflict** on the `PG_ISSUER` comment, resolved by moving it to §11's inputs

---

## 11. Process findings

**Three vacuous constructions in one increment — structural, not incidental.**

1. Part B's integration test asserted `"invalid_redirect_uri" not in body`, a string that appears only in a **log field**, never the HTTP body. It could not fail.
2. The same file asserted the endpoint's **echo** of the request rather than the persisted DB row — near-tautological.
3. Part E's `xfail` did `pytest.raises(...)` then `pytest.fail(...)`, failing in **both** directions and always XFAILing; and it patched the audience production-shaped so it could not see the defect it existed to characterise.

**An assertion that cannot fail looks identical to one that passes.** The AST check
confirming §13's "state what bug would still pass it" verifies the *line exists*, not that
the assertion is *true* — it catches omission, never vacuity. **Only mutation
distinguishes them**, and it is cheap when aimed at the one or two tests carrying real
weight in a file. From Part E onward it was run *before* reporting green rather than after
being asked, and it caught #3.

**A second class: the vacuous environment.** Twice, tests were correct but the
configuration made them meaningless — audience defaults that would have produced a false
"MindSort has PG's defect" finding, and an assertion of the *production* issuer against a
dev-configured system. Neither is a bad assertion; both are right assertions in the wrong
world.

**Verification gap, and how it closed.** Sixteen commits were reported with accurate SHAs
and messages, but **branch attribution was wrong** — Part E and the briefing pass were
reported on `main` while sitting on the Part C branch, hostage to a merge condition that
may never be met. No test, no code review and no file read could have surfaced that:
**which branch a file is on is not in the file.** It was caught by the first independent
ref-level verification of the session. The reason none happened earlier was a **false
diagnosis** — "bash can't reach the spaced path", when the real cause is that the bash
tool and the filesystem MCP run on different machines. A wrong explanation is worse than
an unexplained failure, because it stops the search.

---

## 12. Deployment evidence (§0.1) — no recommendation

**Production log findings:** zero loopback DCR attempts, zero DCR rejections, in the full
30-day window. Three `oauth.register.success` events, all `client_name: "Claude"`.
Reviewer attribution from logs is **not possible**.

**The gap is real and reviewer-reachable — measured, not inferred.** A single probe to
`/oauth/mindsort/register` with `http://127.0.0.1:53821/oauth/callback` returned **HTTP
400 `redirect_uri not in allowlist`** (2026-07-30T17:58:47Z, correlation
`e90aef4a-607d-4986-bfc6-1c1cccdfbc58`, route chosen to keep PG's trail clean; no client
row created on that path).

**Which row applies:** the evidence best fits **row 2 — "No completed reviewer OAuth flow
yet → upside High"**, with **row 3 ("cannot be shown to be low") as the defensible
conservative reading**, because attribution is impossible. PG-Claude **is** functional:
five authenticated `POST /mcp` calls from `Claude-User` on 2026-07-30, correlating with
refresh-token grants one second earlier. Zero *new* PG-Claude authorizations in 30 days is
explained by a long-lived grant refreshing, not by breakage.

**Row 4 cannot be excluded** without one input: whether PG-Claude appears in Nadja's own
connector list. If that refreshing grant is a reviewer's, row 4 applies instead.

### Seven-condition gate

| # | Condition | Status |
|---|---|---|
| 1 | Redirect change additive and narrowly constrained | ✅ Additive first check; non-loopback path unchanged; scoped to the loopback branch |
| 2 | Existing OpenAI and Claude callback tests green | ✅ **No new failures**; ChatGPT prefix, both OpenAI callbacks and both Claude callbacks asserted at unit **and** endpoint level |
| 3 | Authorization-time exact matching unchanged | ✅ `authorize.py` untouched; integration test proves an unregistered loopback URI is refused |
| 4 | Current production config and deployed SHA captured | ✅ `0b05a69`; discovery documents recorded; `backend/` byte-identical to `HEAD` |
| 5 | Rollback prepared and tested | ⚠️ **NOT SATISFIED.** Not prepared. Earlier reasoning that a broken build made rollback impossible was **over-stated and withdrawn** — three services have built successfully since the file was deleted. Whether Render's rollback rebuilds is **unverified** |
| 6 | Post-deploy checks defined | ✅ Defined: PG-Claude OAuth end-to-end, both OpenAI callback forms, discovery byte-identity via `pytest -m live tests/integration/oauth_discovery/`, health on both services |
| 7 | No unrelated changes bundled | ✅ Zero `backend/` commits between the deployed SHA and `HEAD` before Part B; `shared/` identical; Part B's diff is two files |

**Sequencing position:** Part B is step 1. Part D (step 2) has no runtime surface and is
already on `main`. Part C is step 3 — **branch-isolated and unmergeable** until the env
values are supplied; if the audience is not byte-equal to the resource URL, §3's decision
rule makes it a §11 escalation rather than a merge. §11 is step 4, after the verdict, and
now has its empirical answer.

**Presenting evidence only. No deploy/hold recommendation, per §0.1.**

---

## 13. Not required by DoD, stated anyway

**`WIDGET_VERSION`:** no bump required — no widget code touched. Confirmed.

**`OPERATIONS_PREDEPLOY.md`:** read before the first commit; its git rules were followed
throughout (explicit staging, never `git add -A`, stash before checkout/restore, no
`--amend` after a hook failure). It was also **amended** during this increment to record
the now-empty production database allow list.

**`OPERATIONS_MIGRATIONS.md`:** no migration required by any part of this increment. Single
Alembic head confirmed.
