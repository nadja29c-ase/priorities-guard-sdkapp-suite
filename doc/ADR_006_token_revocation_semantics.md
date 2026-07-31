# ADR 006 — Token Revocation Semantics and the Residual Access Window

**Date:** July 2026
**Status:** Accepted
**Context:** Access-token validation across the MCP resource servers (PG-Claude, MindSort-Claude, and their OpenAI twins) and the shared backend Authorization Server

---

## Decision

**MCP resource servers validate access tokens statelessly, via JWKS. They perform no revocation lookup, no token introspection, and no database access.**

A resource server verifies the RS256 signature against the cached JWKS, then checks `iss`, `aud`, `exp`, `nbf`, `iat` and scope. It does not consult the `oauth_access_tokens.revoked` column, holds no token-version or session-generation counter, and makes no call back to the Authorization Server on the request path.

This is a deliberate architectural choice, not an omission.

---

## Evidentiary basis

Every claim in this ADR carries its basis. Claims verified only against the working tree are marked as such — this project's standard is `git show <sha>:<path>`.

| Claim | Basis |
|---|---|
| Resource servers perform no revocation lookup | **Source-verified**, two independent reads. `mcp_server/clarity/mcp_auth.py` and `mcp_server/priority_guardian_claude/mcp_auth_dupl.py` contain zero matches for `revoked`, `revocation`, `introspect`, `token_version` or `session_check`. Neither imports SQLAlchemy, a session, models or persistence. The only network client in either is `httpx`, used solely to construct the JWKS fetch client (`clarity:66`, `pg_claude:83`) |
| The refresh grant honours revocation | **Source-verified + test-verified.** `services/token_service.py:332-342` filters `OAuthAccessToken.revoked == False` inside the WHERE clause and returns `("invalid_grant", "Invalid refresh token")` on no rows. Covered by `tests/unit/core/test_token_service_locking.py:57` (asserts the filter is present in the emitted SQL) and `:60` (asserts the original token is revoked after exchange) |
| `leeway` extends acceptance past `exp` | **Empirically demonstrated** against the pinned PyJWT 2.10.1. Signed RS256 tokens expired 0s/10s/29s ago are ACCEPTED with `leeway=30`; 31s/60s/120s are rejected with `ExpiredSignatureError`. The boundary is located, not assumed |
| PyJWT compares `aud` by exact string equality | **Empirically demonstrated** on 2.10.1. Trailing-slash, case and prefix variants are all rejected; list membership is a set intersection of exact strings |
| `resource` is not validated at `/authorize` | **Committed-SHA verified** at `0b05a69` (the deployed revision). Taken from the client at `:377`, passed through `_normalize()` at `:442` — which only strips whitespace and maps empty to `None` — then written into the auth context at `:487` and the token at `:734`. Between normalize and use, the only validations are `client_id` required and `redirect_uri` required. Nothing checks `resource` against the client's scopes, its app, or an allowlist |
| No reachable path revokes tokens at the AS | **Source-verified + log-verified.** See "Revocation triggers" below |

---

## Revocation triggers — what actually causes what

The four states this ADR distinguishes are *effects*. They are reached — or not — by these *triggers*. Conflating the two is what earlier drafts of this analysis got wrong.

| Trigger | Effect at the AS | Effect at the resource server | Basis |
|---|---|---|---|
| **In-app disconnect tool** | Revokes **Google Calendar** access only. PG's own OAuth tokens are untouched | None | Source-verified. `backend/apps/priority_guardian/routers/offboarding_router.py` states it outright: *"PG OAuth session tokens are NOT revoked here. Disconnect only revokes Google Calendar access. PG token revocation belongs in delete-account flows."* The module docstring records *"Increment 01: Minimal disconnect only. No DELETE /delete-data yet (later increment)."* |
| **Platform connector removal** (user removes the connector in Claude or ChatGPT) | **Nothing.** The platform does not call `/oauth/<app>/revoke` | None | Log-verified. `POST /oauth/pg/revoke` is mounted and functional — a malformed body returns 422, not 404 — but production logs contain **zero `oauth.revoke.*` events across the full 30-day retention window**. The filter is validated: the same query mechanism returns `oauth.register.success` and `oauth.token.success`, so the negative is real and not an artifact |
| **Explicit `/revoke` call** (RFC 7009) | Marks the row revoked; blocks future refresh | **None until `exp`** | Source-verified |
| **Account deletion** | `ondelete="CASCADE"` on `core_users.id` removes connections, token rows, sessions and app data | **None until `exp`** — see "State 4" | Source-verified |

**Consequence: `revoked`, the `revoked == False` filter, and the entire revocation service are live code with no live caller.** Token expiry is currently the only mechanism that ends access.

This is recorded, not resolved. Wiring `/revoke` — and deciding whether the published policy's *"withdraw consent at any time by disconnecting the app"* accurately describes the current behaviour — is a legal-and-engineering judgement that belongs to a separate increment (backlog 21), not to an architecture decision record.

One input for that decision: **processing does stop on disconnect, because the platform stops calling.** What persists is the grant and the consent record. The narrow failure mode is a platform that retained the refresh token resuming without fresh consent. That is the actual gap, and wiring `/revoke` is what closes it.

---

## The four states, distinguished

1. **Refresh token revoked at the AS** — no *new* access tokens can be minted for that grant. Enforced in the WHERE clause, so a concurrent second caller sees zero rows.
2. **Access-token record marked revoked in the AS database** — the row is flagged.
3. **Resource-server enforcement of (2)** — **none.** This is the decision above.
4. **Account / data deletion** — a separate mechanism with a separate user-facing promise, described below.

States 1 and 2 are AS-side bookkeeping. State 3 is the architectural choice. State 4 is a data-lifecycle operation that people reasonably but wrongly assume implies state 3.

---

## Consequence: the residual acceptance window

**Residual acceptance window = `OAUTH_TOKEN_EXPIRY_SECONDS` + `TOKEN_EXPIRY_GRACE_SECONDS`**

= **60 minutes 30 seconds at current code defaults** (3600 + 30).

Stated as a formula deliberately. Both inputs are environment-derived:

- `OAUTH_TOKEN_EXPIRY_SECONDS` — a `Settings` field, default `3600` (`backend/core/config.py:50`)
- `TOKEN_EXPIRY_GRACE_SECONDS` — `get_env("TOKEN_EXPIRY_GRACE_SECONDS", default="30")`, **unprefixed**, so both Claude resource servers read the same variable (`clarity/config.py:159`, `priority_guardian_claude/config.py:133`)

**Neither has been verified against production.** If Render overrides either, the real window differs and this number is silently wrong. Pin them before quoting 60m30s as fact.

Within that window, a token revoked at the AS — or belonging to a deleted account — is still accepted by both resource servers.

### Retention and acceptance are different properties

The published privacy policy states *"OAuth access tokens (ChatGPT/Claude) — Retention period: 1 hour (auto-expire)"*. That describes **token lifetime**, and it is exactly correct: `OAUTH_TOKEN_EXPIRY_SECONDS` is 3600.

This ADR describes the **acceptance window**, which additionally includes the resource server's clock-skew tolerance. The extra 30 seconds is not a retention decision; it is `leeway` in the validator.

**There is no discrepancy between the policy and this ADR.** They measure different things.

---

## State 4 — account deletion in detail

**There is no user-initiated account-deletion code path.** The only `DELETE FROM core_users` in the backend is `jobs/retention_cleanup.py:242`, which deletes users created more than six months ago with no active connection and no active consent. That is an inactivity retention control, not an erasure mechanism — a user requesting deletion today matches none of its predicates.

The published policy's Art. 17 route is `support@priority-guard.com`, fulfilled **manually by the operator**, at which point CASCADE removes all dependent records. Manual fulfilment within 30 days is what the policy promises and what GDPR permits; recording it here is an accountability position under Art. 5(2), not an admission of a gap.

Do not confuse this with MindSort's `delete_my_data` tool, which deletes a **board**, not an account.

**Cascade coverage is complete across both apps** (source-verified):

| Table | Path to user | `ondelete` |
|---|---|---|
| `clarity_clusters` | direct `user_id` | CASCADE |
| `pg_priorities` | direct `user_id` | CASCADE |
| `pg_weekly_snapshots` | direct `user_id` | CASCADE |
| `pg_goals` | via `priority_id` → `pg_priorities.id` | CASCADE (transitive) |
| `pg_deliverables` | via `priority_id` → `pg_priorities.id` | CASCADE (transitive) |
| `oauth_access_tokens`, `oauth_authorization_codes`, `oauth_sessions`, `core_connections`, `core_consents` | direct `user_id` | CASCADE |

**The credential outlives the data.** After deletion:

- The already-issued JWT is **not** invalidated — it is a signed bearer token, valid until `exp`
- The resource server accepts it: JWKS-only, no revocation lookup, no user-existence check
- The backend accepts the forwarded `X-User-ID`: `core/dependencies.py:47-81` validates **UUID well-formedness only**, and its docstring states the trust boundary explicitly — *"This header is trusted because it comes from the MCP server after JWT validation"*
- The request then proceeds against a `user_id` with no rows

**Deletion is therefore effective for data, not for the credential.** No personal data is retrievable afterwards — the rows are gone — so the erasure promise holds, but the mechanism is *emptiness rather than revocation*.

A **write** in that window hits the `core_users` foreign key and fails on an integrity constraint, most likely surfacing as a 500 rather than a graceful denial (backlog 19). A **read** returns no data; whether it surfaces as 404 or an empty payload has not been checked, and this ADR does not claim which.

---

## Rationale

- **Stateless resource servers.** No RS→DB coupling, so the MCP servers scale horizontally and can be restarted, replaced or re-regioned without shared state.
- **No per-call introspection latency.** Every tool call would otherwise pay a network round trip to the AS or the database.
- **Failure isolation.** A database incident degrades writes; it does not take down token validation on every MCP server simultaneously.
- **Proportionality.** The data at risk is productivity content — priorities, board items, calendar-derived hour totals. No special-category data under GDPR Art. 9, no payment data, no credentials. A bounded ≤60m30s window on a revoked credential is proportionate to that sensitivity.

This is an **accepted risk**, consciously taken, and it is the reason this ADR exists rather than the behaviour being left implicit.

---

## Current isolation posture — stated plainly

Cross-app separation between PG-Claude and MindSort-Claude currently rests on **scope enforcement**, not on resource-scoped audience binding.

Two facts combine to produce this:

1. PG-Claude's accepted-audience list includes the shared AS issuer (`PG_AUDIENCE`, commented in source as a "legacy fallback").
2. `resource` is unvalidated at `/authorize` (committed-SHA verified above), so **`aud` is client-controlled**: a client registered for `clarity.write` can request `resource=<PG resource URL>` and receive a token whose audience PG-Claude accepts.

Audience validation still rejects arbitrary third-party audiences. What is absent is **app-specific resource binding**. The per-tool scope check is what actually prevents cross-app access today.

This is why the audience-isolation work must test the full `(resource, scope)` issuance matrix rather than two illustrative cases — the question is not whether the validator rejects a wrong audience, but which combinations the AS will mint in the first place. Addressed by the PG-Claude resource-audience increment (§11 of the increment briefing).

---

## Loopback redirect URIs — rationale and interaction

Loopback IP literals with ephemeral ports follow native-app OAuth guidance (RFC 8252). `localhost` is **not** endorsed by RFC 8252 §8.3 — it explicitly prefers IP literals, because name resolution can be redirected — but the MCP specification and Anthropic's documented callbacks use it, so it is accepted as an interoperability requirement under the same narrow constraints. IPv6 `::1` is deliberately excluded: `authorize.py::_normalize_redirect_uri` strips ports with `netloc.split(":")[0]`, which is IPv4-only, so a `::1` URI accepted at DCR could never be authorized (backlog 13).

**Interaction with the audience posture, stated rather than left silent:** widening loopback DCR slightly enlarges a pre-existing path — register a client via `/oauth/pg/register` with a loopback redirect, authorize while omitting `resource`, obtain a token with `aud = issuer` that PG-Claude accepts.

That capability **already existed**: `http://localhost:6274/oauth/callback` has been allowlisted in production throughout. The change widens the *port range*, not the class of path, and every step still requires the user to complete a consent screen. The assessment is a **marginal increase in a pre-existing exposure, not a new vector.**

---

## Rejected alternatives, with revisit triggers

### Token introspection on every tool call (RFC 7662)
Rejected: adds a network round trip to the hot path, couples every MCP server to AS availability, and forfeits the horizontal-scaling property. **Revisit if** the data sensitivity changes — special-category data, payment data, or any regulated category entering the system.

### Shorter access-token TTL
Rejected for now: shrinking the window trades refresh traffic against residual exposure. At 1 hour with ≤60m30s residual, the exposure is already bounded and proportionate. **Revisit if** the residual window becomes material to a compliance commitment, or if a platform's refresh behaviour makes shorter TTLs cheap.

### Redis-backed revocation list checked by the resource servers
Rejected: reintroduces shared state and an availability dependency, in exchange for closing a window that no current trigger even reaches — nothing calls `/revoke` today. **Revisit if** `/revoke` is wired to platform disconnect (backlog 21) *and* the residual window is then judged too long.

### Server-side reconciliation at the resource server
Not applicable to revocation, but noted because it is the shape of the fix for a related class of problem: having the server reload authoritative state rather than trusting what the client presents.

---

## Cross-references

- **ADR 005** — Platform OAuth Discovery Contracts. One AS, one issuer; discovery shape is platform-coupled.
- **ADR 003** — OAuth provider route/scope mapping.
- **`doc/OAuth_Hard_Requirements.md`** §13 — must be read per-layer: revocation is immediate at the AS and has no effect at the resource server until `exp`.
- **Increment briefing** `inc_claude_auth_loopback_audience_revocation.md` — §11 (PG audience migration), backlog 13, 19, 20, 21.

---

## Trigger for revisiting this ADR

Revisit if **any** of the following becomes true:

1. The system begins handling special-category, payment or otherwise regulated data.
2. `/revoke` is wired to platform disconnect or in-app disconnect, making state 2 reachable in practice.
3. A compliance commitment is made that requires access to end in less than the residual window.
4. `OAUTH_TOKEN_EXPIRY_SECONDS` or `TOKEN_EXPIRY_GRACE_SECONDS` is changed in production — the window in this document is a formula, and its stated value assumes code defaults.
5. Resource-scoped audience binding is completed (§11), which changes the isolation posture described above.

---

## What Claude Code must know

- **Do not add a revocation lookup to a resource server** without revisiting this ADR. It is a deliberate decision, not an oversight.
- **Do not describe revocation as "immediate"** without naming the layer. It is immediate at the AS and has no effect at the resource server until `exp`.
- **Do not quote 60m30s as a fact.** It is the value at code defaults; the production values are unpinned.
- **Do not treat account deletion as revoking credentials.** It removes data; the token remains valid until `exp`.
- **Do not describe in-app disconnect as revoking app tokens.** It revokes Google Calendar access only.
