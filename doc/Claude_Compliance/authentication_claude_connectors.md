# Authentication for connectors — Claude

**Source:** `https://claude.com/docs/connectors/building/authentication`
**Fetched:** 2026-08-04 — direct fetch.
**Raw source committed:** `sources_raw/authentication.raw.md` (141 lines, HTTP 200, 17,099 bytes).
**Feeds:** compliance master §4C. The master is NOT yet rewritten against this; see §11 header.

> ✅ **PROVENANCE: PASTE-VERIFIED 2026-08-04.** The committed raw was compared against Nadja's
> paste of the rendered page and agrees on every discriminating marker — the six-row auth-type
> table with `static_headers` at Beta, the Supabase/Cloudflare/Lambda list, the `localhost:3118`
> example, the RFC 8252 §7.3/§8.3 split, the Entra `AADSTS9010010` note, the 10 s/30 s budgets and
> `160.79.104.0/21` — **including the A18 sentence verbatim.** A18 now rests on Nadja's copy, not
> on a fetch. *(Comparison was structural + every distinctive string, not a byte-level diff.)*
> The `.md` method is now 2-for-2 against pastes (transparent-theming, authentication) — evidence
> about the method, **not** a licence to skip the paste on `review-criteria`.


> **Round 2 was PARTIALLY unblocked — and this paragraph originally overstated it.** This
> artifact's requirement set rested on a fetch only one party had seen, which made it
> un-round-2-able, and it is the artifact feeding §4C, the OAuth attestation on the submission
> form. Committing the raw `.md` makes every quotation below **checkable against a fixed source**,
> which is what round 2 needs. ⚠️ It does **not** make that source **current**.
>
> This paragraph previously ended *"checkable by anyone, permanently, **without a paste**."* That
> was the conflation: the paste was never about durability, it was about **freshness**. Corrected
> 2026-08-04 — see `sources_raw/PROVENANCE.md`. **A paste of this page is still required.**
>
> **Round 2 result (2026-08-04): source side clean — no fabrications.** All 17 originally
> extracted requirements, the auth-type table, the egress range, the CIMD dual condition and its
> rationale, the DCR-at-scale wording, the 10 s/30 s budgets and the parser split all trace
> verbatim to the raw file. The risk in this artifact was **omission, not invention.**
>
> ⚠️ **Round 1 on this page is therefore REOPENED, not complete.** Round 2 returned **six**
> omissions — one of them a failing MUST (**A18**) — plus one arithmetic overclaim. All are folded
> in below; the page is **not** re-looped. The extraction *method* that caused them is corrected
> for the remaining seven pages (see "Why round 1 missed these").

This page is the densest requirements source in the set. The page itself opens with
*"Authentication is the most common source of partner questions. Claude's auth support differs
in a few places from the generic MCP specification, so read this page even if you're already
familiar with MCP auth."*

---

## Part 1 — MUST requirements extracted (17)

| # | Requirement | Language |
|---|---|---|
| A1 | AS **must support S256 PKCE**. Claude sends `code_challenge_method=S256` on **every** authorization request, regardless of registration mechanism | "must support" |
| A2 | AS metadata **must advertise** `"code_challenge_methods_supported": ["S256"]` | MCP spec "requires" |
| A3 | Return **401** with `WWW-Authenticate` whose `resource_metadata` points at the PRM document. **"The `401` status is required — Claude does not honor a `WWW-Authenticate` header on a `200` response"** | "required" |
| A4 | PRM `resource` **must match your MCP server URL exactly as the user enters it in Claude**, including any path component | "must match" |
| A5 | PRM `authorization_servers` **must list** the AS issuer URL. **Claude uses the first entry and does not fall back** — list the primary first | "must list" |
| A6 | AS **must serve its own discovery metadata** (RFC 8414 or OIDC Discovery) at its `/.well-known/` paths | "must serve" |
| A7 | That AS host **must be reachable from Anthropic's egress range** — a WAF in front of the IdP breaks the flow even when the MCP server is reachable | "must also be reachable" |
| A8 | Register redirect URI `https://claude.ai/api/mcp/auth_callback` for hosted surfaces | "register the following" |
| A9 | For Claude Code: accept **both** `http://localhost/callback` **and** `http://127.0.0.1/callback` **with the port component ignored** | "must accept both" |
| A10 | Return **RFC 6749-compliant error codes** — `invalid_grant`, *not* `invalid_request` or a custom code — when a refresh token is no longer valid | imperative |
| A11 | **Rotate refresh tokens for public clients.** DCR and CIMD register Claude as a public client; MCP spec adopts OAuth 2.1's rotate-or-sender-constrain requirement. If rotating, return the new refresh token in the same response that invalidates the old | "requirement" |
| A12 | `/token` **must accept** `Content-Type: application/x-www-form-urlencoded` (RFC 6749 §4.1.3) | "must accept" |
| A13 | `/register` uses `application/json` (RFC 7591 §3.1) — **do not assume one parser serves both** | imperative |
| A14 | Respond within **10 s** for discovery, registration and token endpoints; **30 s** for refresh. Beyond that the flow is treated as failed even if the server later completes | "waits up to" |
| A15 | Machine-to-machine `client_credentials` grant is **NOT supported**. Every connection requires user consent | "not supported" |
| A16 | Tokens/API keys in the connector **URL** are **not recommended**; the MCP spec **prohibits** access tokens in the URI query string | "prohibits" |
| A17 | CIMD is selected **only when AS metadata advertises BOTH** `"client_id_metadata_document_supported": true` **AND** `"none"` in `token_endpoint_auth_methods_supported`. If either is missing, Claude falls back to DCR | "only when… both" |
| **A18** | **AS must display the redirect URI hostname clearly on the consent screen — unconditionally.** *Separately,* it **should** add an extra warning when the only registered redirect URIs are loopback addresses. Rationale given upstream: a CIMD "can't prevent loopback impersonation on its own — any local process can bind a port and claim to be the legitimate client" | spec **"requires"** (display) + "recommends" (warning) |

> **A18 was missed by round 1** (raw source line 106), and its scope was then understated when
> first recorded. Two corrections:
>
> **1. The obligation is not scoped to loopback.** It was first written here as binding "because
> PG accepts loopback redirects for Claude Code." Re-read the sentence: *"requires authorization
> servers to display the redirect URI hostname clearly on the consent screen **and** recommends an
> extra warning when the only registered redirect URIs are loopback addresses."* Only the
> **warning** carries the loopback condition. The **display** requirement is unconditional — the
> surrounding paragraph is about loopback, the obligation isn't. So it applies to the hosted
> `claude.ai` consent screens too. **This widens the gap and cheapens the fix**: one change covers
> every flow instead of a Claude-Code-only branch.
>
> **2. Provenance, labelled.** This is the **MCP authorization spec** requiring it, surfaced on
> Anthropic's page — **not** an Anthropic-enumerated directory criterion. Whether reviewers gate
> on it is **not settled.** `review-criteria` (fetch-only) does not mention it, which shows only
> that it is absent from the reviewer's checklist; `software_directory_policy` — the actual policy
> document, §5D "must use secure OAuth 2.0" — is **still unfetched**. The honest label is *"unmet
> spec-inherited MUST, directory-gating status unresolved"*, not a bare "unmet MUST" — the
> difference decides how hard this is pushed against Blocker 1.

### Supported authentication types (complete list)

| Type | Availability |
|---|---|
| `oauth_dcr` — OAuth 2.0 + Dynamic Client Registration (RFC 7591) | Out of the box |
| `oauth_cimd` — OAuth 2.0 + Client ID Metadata Document | Out of the box |
| `oauth_anthropic_creds` — Anthropic-held client credentials | Contact `mcp-review@anthropic.com` |
| `custom_connection` — custom URL/credentials at connection time | Contact `mcp-review@anthropic.com` |
| `static_headers` — fixed credential as a request header, set by an org admin | **Beta** |
| `none` — authless. Optional partial-auth mode is experimental | Supported |

### Other facts worth having

- **Egress range:** `160.79.104.0/21`. Discovery requests come from the same range as tool calls.
- **Scope control:** include a `scope` parameter in the `WWW-Authenticate` header on the 401.
  Absent that, Claude requests the scopes in PRM `scopes_supported`. Claude appends
  `offline_access` if AS metadata lists it in `scopes_supported`.
- **Refresh timing:** reactive on 401, plus a proactive refresh up to 5 minutes before expiry.
- **Directory connectors use a single shared OAuth application per connector.** There is no
  per-org OAuth client for directory connectors.
- **DCR at scale:** *"For servers expecting high traffic from the directory, prefer CIMD or
  `oauth_anthropic_creds` over DCR."* DCR registers a new client on every fresh connection.
- **Fallback discovery:** if the 401 carries no `resource_metadata`, Claude probes
  `/.well-known/oauth-protected-resource/<path>` then `/.well-known/oauth-protected-resource`.
  Treat as fallback — extra round-trips, and only works if the platform serves `/.well-known/*`.

---

## Part 2 — PG-Claude conformance, verified 2026-08-04

Live measurements against `https://mcp.priority-guard.com` and
`https://www.priority-guard.com`, plus source inspection. **Not inferred.**

**12 of the 17 obligations are verified.** A17 is excluded from the obligation count — it describes
*Claude's* selection logic, not a duty on the server — leaving **17 requirements = 16 obligations +
A17**, of which **12 verified ✅, 4 not verified ⚠️, 1 newly failed ❌ (A18)**.

> ⚠️ **This line previously read "11 of the 17."** It counted **table rows**, not requirements —
> the `A1/A2` row carries two. Corrected 2026-08-04 in round 2. The error is small and its shape
> is not: a summary sentence quantifying over a table that does not enumerate its items the same
> way is precisely what the `doc/README.md` writing rule exists to catch, and it slipped through
> in the document that cites that rule.

| # | Requirement | PG-Claude | Evidence |
|---|---|---|---|
| A1/A2 | S256 advertised | ✅ | AS metadata: `code_challenge_methods_supported: ["S256"]` |
| A3 | 401 + `WWW-Authenticate` | ✅ | Live: `HTTP/2 401`, `WWW-Authenticate: Bearer resource_metadata="…/.well-known/oauth-protected-resource/mcp", scope="pg.access"` |
| A4 | `resource` matches exactly | ✅ | PRM `resource: https://mcp.priority-guard.com/mcp` = canonical URL |
| A5 | Single/first AS entry | ✅ | `authorization_servers: ["https://www.priority-guard.com"]` — one entry, no ambiguity |
| A6 | AS discovery served | ✅ | `https://www.priority-guard.com/.well-known/oauth-authorization-server` returns RFC 8414 metadata, `issuer` = root domain |
| A8 | `claude.ai` callback | ✅ | `backend/core/config.py:62-63` registers **both** `claude.ai` and `claude.com` variants |
| A9 | Loopback, both hosts, port-ignored | ✅ | `_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1"})` in `validators/client_metadata.py`; implemented in the Claude auth increment Part B |
| A10 | `invalid_grant` | ✅ | `token_endpoint.py:116`; OAuth 2.1 status mapping noted at :220 and :270 |
| A11 | Refresh rotation | ✅ | `token_service.py` marks the old token `revoked=True` in the same exchange that issues the new one |
| A15 | No `client_credentials` | ✅ | Not implemented; PG is consent-gated throughout |
| A16 | No tokens in the URI query string | ✅ | PG is bearer-header only. No `?token=`/`?apiKey=`/`?userToken=` parameter is read anywhere on the MCP path; `mcp_auth_dupl.py` reads the `Authorization` header exclusively |
| A17 | CIMD vs DCR selection | ➖ n/a — see below | `token_endpoint_auth_methods_supported: ["none"]` present, `client_id_metadata_document_supported` **absent** → Claude falls back to DCR, which PG supports (`registration_endpoint` present) |
| **A18** | Redirect URI hostname on the consent screen | ❌ **NOT SATISFIED** | **All 8** `backend/templates/oauth_consent_*.html` — grep for `redirect`/`hostname`/`redirect_host` returns nothing in any of them. The render site is `oauth_provider/authorize.py` (`TemplateResponse`, `:788`); its context passes `request`, `auth_context_id`, `client_name`, `scopes`, `scope_descriptions` — no redirect data |

### A18 — the one new failing requirement, stated plainly

The consent screen is the only place a user can see where their authorization is actually going.
PG shows them nothing, on **every** flow — the display obligation is unconditional (see the
scope correction above), so this is not a Claude-Code-only gap.

**Correction to how the fix size was first stated.** This artifact previously said the value sat
*"one line away from the template context"* and called the gap *"display, not plumbing."* Both
oversold it:

- The existing `urlparse(redirect_uri).netloc` is in **`consent_ui.py`**, on the **post-consent
  redirect path**, where it feeds the `oauth.consent.redirect_prepared` log. That is a different
  module and a different request phase from the render. Nothing there is reusable.
- The render path is `authorize.py`. `redirect_uri` **is** in scope there — the same function
  uses it at `:770` — but nothing computes its `netloc` and nothing passes it into the context.

So the fix is **an add, not a move**: one computation and one context entry in `authorize.py`,
plus display markup in **all eight** templates (four languages × three apps, plus the legacy
`focused` pair). Still small. Not one line, and not in the file that already has the value.

**Severity, bounded but wider than first written.** The loopback impersonation scenario needs a
hostile local process during an active Claude Code authorization. The *display* gap, however,
applies to hosted `claude.ai` consent screens as well, where it is a transparency failure rather
than an exploitable one. **Filed, not fixed** — the decision is Nadja's.

### Why round 1 missed these — the extraction method, not six unlucky misses

A18 was not a one-off. Round 1 swept this page for **obligation-shaped words** — "must",
"required", "prohibits" — and therefore missed every requirement carried by a `<Note>`, a
conditional clause, a cross-reference to another page, or an operational sentence attached to a
number. Six items came back on the re-read below, one of them a failing MUST.

**The method fix, for the seven remaining pages:** read the raw source top to bottom for
*obligations*, not for *keywords*. Specifically sweep the four shapes that defeated the keyword
pass — `<Note>`/`<Tip>` blocks, conditionals ("if you… then you must"), links to adjacent
requirement surfaces, and the prose *around* a stated number.

### Also omitted by round 1 — captured now

| Raw line | What it says | PG impact |
|---|---|---|
| 120 | **Enterprise Managed Auth** — SSO orgs can connect users with an IdP-signed identity assertion, **with no interactive OAuth consent step** | An entire alternative auth pathway, absent from this artifact and from §4C. Not required; relevant if PG pursues enterprise |
| 127–129 | **Custom connectors:** the OAuth Client Secret field is *optional*; an admin may supply their own pre-registered client credentials, scoping the OAuth client to that org | PG is directory-bound, so not applicable today |
| 41 | `oauth_anthropic_creds` are **bound to the issuing AS** — email `mcp-review@anthropic.com` with new credentials *before* cutting over to a new authorization server. CIMD has no such constraint (its `client_id` is a self-hosted URL) | Only if PG ever adopts Anthropic-held credentials |
| 39 | Claude Code does **not** use Anthropic-held credentials — it runs its own flow with its own CIMD. Claude Managed Agents uses a separate credential set | Clarifies why A9 loopback support is independent of the hosted-surface path |
| 81 | Microsoft Entra ID requires the MCP server URL registered as an Application ID URI or the token request fails `AADSTS9010010` | None — PG runs its own AS. Listed because it is a **literal "must"** in a `<Note>`, and this artifact claims to extract MUSTs |
| 137 | **A14's operational half.** The 10 s / 30 s budgets were captured as bare numbers; the source also says to *return the response headers and body without buffering behind upstream work*, and to check that no reverse proxy, API gateway or WAF is holding the response | Actionable if A14 is ever measured (still unverified) |
| 24 | **`static_headers` sharing model.** The credential is entered **once by an org administrator** and is *"shared by the organization rather than pasted per user"* | Sharpens the `static_bearer` drift finding in Part 3: the type was not merely renamed and promoted from unsupported to beta — **the credential model changed**, from per-user paste to org-shared admin entry |
| 39 | **Claude Managed Agents uses a SEPARATE credential set**, and Claude Code does not use Anthropic-held credentials at all | **An eighth surface.** Master §1 enumerates six platforms and has never mentioned Managed Agents. Not PG-affecting today; it is a platform-inventory gap |
| 104 | **Claude Code's Client ID Metadata Document is a PUBLISHED, FETCHABLE ARTIFACT** at `https://claude.ai/oauth/claude-code-client-metadata` | **Testable, and now tested** — see the A9 verification above. Nothing in the repo pointed at it, so A9 had been argued from prose when a live artifact was available |
| 70 | **`resource_metadata` need NOT be on the MCP server's origin** — *"it can be any HTTPS location that serves the JSON document"* | A **permission**, not an obligation. PG does not need it, but it is the documented escape hatch if `/.well-known/*` routing ever becomes a problem on the platform |
| 104 | **A9's RFC split.** Port-agnostic matching is **mandatory** under RFC 8252 §7.3 for the IP-literal form (`127.0.0.1`); for `localhost` it is pragmatic, applied *"so Claude Code works, even though RFC 8252 section 8.3 discourages `localhost`"* | Matters if anyone ever tightens `_LOOPBACK_HOSTS` — the two hosts rest on different footings, and only one is RFC-mandated |

### ✅ A12 — VERIFIED 2026-08-04 by live probe (was the last unverified item with a named failure mode)

`POST https://www.priority-guard.com/oauth/pg/token` with deliberately invalid credentials:

| `Content-Type` | Response |
|---|---|
| `application/x-www-form-urlencoded` | **HTTP 400** — `{"error":"invalid_grant","error_description":"Invalid authorization code"}` |
| `application/json` | HTTP 422 — `grant_type: Field required` |

The form body was **parsed**: `grant_type` was read, the code looked up, and the grant rejected on
its merits. **Not `415`** — the failure mode the page singles out. The JSON contrast confirms the
endpoint is form-only, which is the A12/A13 parser split working as specified.

**This also re-confirms A10 on a live request** — the error code returned is `invalid_grant`,
RFC 6749-compliant, exactly as A10 requires.

### ✅ A9 — VERIFIED against Claude Code's PUBLISHED metadata, not against prose

`https://claude.ai/oauth/claude-code-client-metadata` (HTTP 200) declares:

```json
{"redirect_uris":["http://localhost/callback","http://127.0.0.1/callback"],
 "token_endpoint_auth_method":"none","grant_types":["authorization_code","refresh_token"]}
```

PG's `_is_loopback_redirect_uri()` run against those literal strings:

| URI | Accepted |
|---|---|
| `http://localhost/callback` | ✅ |
| `http://127.0.0.1/callback` | ✅ |
| `http://localhost:3118/callback` (the page's own port example) | ✅ |
| `http://127.0.0.1:53821/callback` | ✅ |
| `https://localhost/callback` · `http://evil.com/callback` · `http://localhost:0/callback` · `http://localhost/cb` | ❌ all rejected |

Both declared paths clear `_LOOPBACK_PATHS`, which already contains `/callback` alongside
`/oauth/callback`. Port-agnostic in both directions, with negative controls holding.

### Not verified — stated rather than assumed

| # | Item | Why not verified |
|---|---|---|
| A7 | AS reachable from `160.79.104.0/21` | Cannot originate traffic from Anthropic's range. Circumstantially satisfied — the connector works in production — but not directly measured |

| A13 | `/register` uses JSON | Not separately tested |
| A14 | 10 s / 30 s latency budgets | Not measured under load |

---

## Part 3 — Diff against repo docs

| Repo claim | Status |
|---|---|
| master §4C: *"OAuth 2.0 authorization code flow with PKCE S256 support, as required by Claude's auth implementation and the MCP authorization spec"* | **Correct.** Confirmed by A1/A2 |
| master §4C callback note: *"`claude.com/api/mcp/auth_callback` appears in some older documentation. The current official auth reference lists only the `.ai` URL… Register both"* | **Correct and still current.** The live page lists only `claude.ai`; PG registers both |
| master §4C:141 — *"`static_bearer` (user-pasted tokens) is not yet supported"* | ❌ **STALE — this is drift.** The live page lists **no `static_bearer`**. It lists `static_headers` — *"fixed credential (API key or bearer token) entered by an organization administrator as a request header"* — marked **Beta**. Either the type was renamed, its actor changed (user-pasted → org-admin-entered) and it was promoted from unsupported to beta, or `static_bearer` was removed outright. Both readings are drift. **Not PG-affecting** — PG uses `oauth_dcr` — but the master states a capability fact that is no longer true. |
| master §9: *"ensure Claude Code loopback URIs support port-agnostic matching"* | **Correct**, and now satisfied |

**§4C DID drift, in one place.** An earlier version of this document concluded "nothing in the
repo's §4C material was found to be stale" and used that to argue drift is not uniform. **That
conclusion was wrong and the inference built on it was unsound** — it rested on a row
(`static_bearer`) that had been marked "Correct" without being checked against the live type
table.

Corrected result: **one stale claim in §4C** (the `static_bearer` row above), plus six items
new since June. The requirement set itself — PKCE, the 401 handshake, resource matching,
callbacks, refresh semantics — did not move. So the honest statement is narrower: §4C's
*obligations* held; its *capability inventory* did not.

### New since the June verification — not yet in the master (6, not 7)

1. **A17's dual condition for CIMD selection.** The master does not state that `"none"` in
   `token_endpoint_auth_methods_supported` is *required* alongside the CIMD flag.
2. **The DCR-at-scale warning.** PG is a directory-bound connector using DCR, so
   *"prefer CIMD or `oauth_anthropic_creds` over DCR"* applies directly. **Forward-looking
   finding, not a defect** — DCR is supported out of the box and PG works today.
3. **A14's explicit 10 s / 30 s budgets.**
4. **A12/A13's parser split** — `/token` form-urlencoded vs `/register` JSON, called out
   because frameworks default to JSON-only.
5. **`static_headers` as a named beta auth type.**
6. **The `offline_access` auto-append rule.**
*(A seventh item was listed here — "proactive refresh up to 5 minutes before expiry, previously documented as reactive-only". **That was fabricated.** Master §4C line 176 already states "Proactive refresh up to 5 minutes before stored expiry", line 824 repeats it, and the May 2026 changelog records it. Not new, and the parenthetical misstated what the master says. Removed 2026-08-04.)*

---

## Two items worth acting on

### PG is one metadata flag away from CIMD

The page tells directory-bound connectors to *"prefer CIMD or `oauth_anthropic_creds` over
DCR"*, because DCR registers a new client on **every fresh connection**. PG is directory-bound
and uses DCR.

CIMD selection requires **both** conditions (A17). PG already satisfies one:
`token_endpoint_auth_methods_supported: ["none"]` is advertised. The only missing piece is
`"client_id_metadata_document_supported": true` in the AS metadata, plus hosting the metadata
document.

That is a cheap strategic option rather than a finding — DCR works and is supported out of the
box. But "one flag away" is worth knowing before the directory drives registration volume.

### The one unverified requirement with a known failure mode

**A12 is the only unverified item with a known failure mode.** The page singles it out:
a framework defaulting to JSON-only body parsing returns `415` and breaks token exchange.
PG's token exchange demonstrably works in production, so this is near-certainly satisfied —
but "works in production" is the argument, not a test. A direct
`POST /oauth/pg/token` with `Content-Type: application/x-www-form-urlencoded` would settle it
in one request.
