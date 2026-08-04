# Authentication for connectors — Claude

**Source:** `https://claude.com/docs/connectors/building/authentication`
**Fetched:** 2026-08-04 — direct fetch.
**Feeds:** compliance master §4C. The master is NOT yet rewritten against this; see §11 header.

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
| A17 | CIMD vs DCR selection | ✅ correct-by-config | `token_endpoint_auth_methods_supported: ["none"]` present, `client_id_metadata_document_supported` **absent** → Claude falls back to DCR, which PG supports (`registration_endpoint` present) |

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
| master §4C: six supported auth types | **Correct**, and `static_headers` is confirmed **Beta** |
| master §9: *"ensure Claude Code loopback URIs support port-agnostic matching"* | **Correct**, and now satisfied |

**Nothing in the repo's §4C material was found to be stale.** That is a real result rather than
an absence of work: design guidelines was stale on two material facts after ~2 months, so the
prior on any unrefreshed page was "expect drift". §4C did not drift.

### New since the June verification — not yet in the master

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
7. **Proactive refresh up to 5 minutes before expiry** (previously documented as reactive-only).

---

## One item worth acting on

**A12 is the only unverified item with a known failure mode.** The page singles it out:
a framework defaulting to JSON-only body parsing returns `415` and breaks token exchange.
PG's token exchange demonstrably works in production, so this is near-certainly satisfied —
but "works in production" is the argument, not a test. A direct
`POST /oauth/pg/token` with `Content-Type: application/x-www-form-urlencoded` would settle it
in one request.
