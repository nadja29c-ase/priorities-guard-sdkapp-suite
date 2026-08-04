# Authentication for connectors — Claude

**Source:** `https://claude.com/docs/connectors/building/authentication`
**Fetched:** 2026-08-04 — direct fetch.
**Raw source committed:** `sources_raw/authentication.raw.md` (141 lines, HTTP 200, 17,099 bytes).
**Feeds:** compliance master §4C. The master is NOT yet rewritten against this; see §11 header.

> **Round 2 was blocked and is now unblocked.** This artifact's entire requirement set rested on
> a fetch only one party had seen, which made it structurally un-round-2-able — and it is the
> artifact feeding §4C, the OAuth attestation on the submission form. Appending `.md` to these
> doc URLs returns the raw markdown, so the source is now **in the tree**. Every quotation below
> is checkable against it by anyone, permanently, without a paste.
>
> **Round 2 result (2026-08-04): no fabrications on the source side.** All 17 extracted
> requirements, the auth-type table, the egress range, the scope/refresh/DCR-at-scale facts and
> every verbatim quotation trace to the raw file. Two defects were found and are fixed below:
> **one arithmetic overclaim** and **one omitted MUST that PG does not satisfy**.

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
| **A18** | **AS must display the redirect URI hostname clearly on the consent screen**, and *should* add an extra warning when the only registered redirect URIs are loopback addresses — because a CIMD "can't prevent loopback impersonation on its own; any local process can bind a port and claim to be the legitimate client" | spec **"requires"** + "recommends" |

> **A18 was missed by round 1** (raw source line 106). It is a genuine MUST on the authorization
> server, it is a **security** requirement rather than a plumbing one, and it applies to PG
> directly because PG accepts loopback redirects for Claude Code (A9). Extracting 17 requirements
> and calling the set complete is exactly the shape the writing rule in `doc/README.md` prohibits.

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
| **A18** | Redirect URI hostname on the consent screen | ❌ **NOT SATISFIED** | `backend/templates/oauth_consent_pg_en.html` contains no `redirect`, no hostname, no host — grep returns nothing. `consent_ui.py` *has* the value: it parses `urlparse(redirect_uri).netloc` and **logs** it (`:270`), then uses `redirect_uri` only to build the redirect. It is never passed to the template. Same for the other seven consent templates |

### A18 — the one new failing requirement, stated plainly

PG accepts loopback redirects for Claude Code (A9, implemented in the Claude auth increment).
The spec's reasoning for A18 is that a Client ID Metadata Document **cannot** prevent loopback
impersonation: any local process can bind a port and claim to be the legitimate client. The
consent screen is the only place the user can see where their authorization is actually going.

PG shows them nothing. The data is present and already parsed one line away from the template
context — `netloc` is computed for a log line — so the gap is display, not plumbing.

**Severity is real but bounded:** it requires a hostile local process on the user's machine
during an active Claude Code authorization. **Not applicable to the hosted surfaces**, where the
redirect is always `claude.ai`. **Filed, not fixed** — a consent-screen change across eight
templates is an increment, and the fix decision is Nadja's.

### Also omitted by round 1 — captured now, none PG-failing

| Raw line | What it says | PG impact |
|---|---|---|
| 120 | **Enterprise Managed Auth** — SSO orgs can connect users with an IdP-signed identity assertion, **with no interactive OAuth consent step** | An entire alternative auth pathway, absent from this artifact and from §4C. Not required; relevant if PG pursues enterprise |
| 127–129 | **Custom connectors:** the OAuth Client Secret field is *optional*; an admin may supply their own pre-registered client credentials, scoping the OAuth client to that org | PG is directory-bound, so not applicable today |
| 41 | `oauth_anthropic_creds` are **bound to the issuing AS** — email `mcp-review@anthropic.com` with new credentials *before* cutting over to a new authorization server. CIMD has no such constraint (its `client_id` is a self-hosted URL) | Only if PG ever adopts Anthropic-held credentials |
| 39 | Claude Code does **not** use Anthropic-held credentials — it runs its own flow with its own CIMD. Claude Managed Agents uses a separate credential set | Clarifies why A9 loopback support is independent of the hosted-surface path |
| 81 | Microsoft Entra ID requires the MCP server URL registered as an Application ID URI or the token request fails `AADSTS9010010` | None — PG runs its own AS |

### Not verified — stated rather than assumed

| # | Item | Why not verified |
|---|---|---|
| A7 | AS reachable from `160.79.104.0/21` | Cannot originate traffic from Anthropic's range. Circumstantially satisfied — the connector works in production — but not directly measured |
| A12 | `/token` accepts form-urlencoded | No `Form(` or explicit content-type handler found by grep in `token_endpoint.py`; the parser may be implicit in the framework. **Needs a direct POST test.** The page calls this out specifically as a common failure (`415 Unsupported Media Type`) |
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
