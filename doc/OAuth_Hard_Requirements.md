# OAuth 2.1 — Hard Requirements

**Version:** 1.1
**Date:** 2026-07-02
**Scope:** Priority Guardian OAuth provider (Authorization Server requirements for ChatGPT and Claude inbound flows)

**Changelog:**
- v1.1 (2026-07-02): Fixed issuer URL (api→www), clarified scope to include Claude, replaced "one discovery document" claim with ADR_005 cross-reference. See ADR_005 for platform-specific discovery shapes. Added /oauth/mindsort/* endpoints to §7 TLS table. Clarified §9 to document Claude's PRM + S256 requirements.

---

## Context

OAuth 2.1 is not a new protocol. It consolidates OAuth 2.0 + a decade of security best-practice extensions (PKCE, Security BCP, Browser-Based Apps, Bearer Token Usage) into a single reference document. It removes insecure patterns and makes previously optional security measures mandatory.

**Status:** Still an IETF draft (draft-ietf-oauth-v2-1), but already adopted as the standard by OpenAI (Apps SDK OAuth) and Anthropic (MCP authorization spec).

---

## Issuer Model (Priority Guardian)

- **One issuer:** `https://www.priority-guard.com` (configured via `OAUTH_ISSUER`)
- **Active authorization server:** `/oauth/pg/*` routes (Priority Guardian), `/oauth/mindsort/*` routes (MindSort)
- **Deprecated:** `/oauth/focused/*` (kept for backward compatibility only)
- **Multiple discovery documents by design:** One AS/issuer, multiple platform-specific discovery facades. See `doc/ADR_005_platform_oauth_discovery_contracts.md` for the three intentional shapes and why they exist.

---

## Hard Requirements

### 1. Allowed Grant Types

OAuth 2.1 permits only:

| Grant | Status |
|---|---|
| `authorization_code` | ✅ Required |
| `refresh_token` | ✅ Allowed |
| `implicit` (`response_type=token`) | ❌ Removed |
| Resource Owner Password Credentials (ROPC) | ❌ Removed |
| Device Authorization | Optional extension, not in core |

Any other grant type → reject with `unsupported_grant_type`.

---

### 2. PKCE — Mandatory for All Clients

PKCE (RFC 7636) is required for every authorization code flow, including confidential clients.

**Authorization request must include:**
- `code_challenge` — BASE64URL(SHA256(`code_verifier`))
- `code_challenge_method=S256` — only S256 is permitted; `plain` must be rejected

**Token exchange must include:**
- `code_verifier` — original random string (43–128 chars, unreserved charset: `[A-Z][a-z][0-9]-._~`)

**Server must:**
- Verify: `BASE64URL(SHA256(code_verifier)) == code_challenge` (constant-time comparison)
- Reject if: challenge missing, verifier missing, or mismatch

> **Note:** `plain` is only allowed by spec in constrained environments that cannot support SHA256 AND where the AS explicitly advertises `plain` in metadata. Priority Guardian must not advertise or accept `plain`. Advertising only `["S256"]` in discovery prevents well-behaved clients from attempting it; server-side rejection is the backstop.

---

### 3. Redirect URI Validation

**Rules:**
- Exact string match against pre-registered URIs — no wildcards, no prefix matching, no domain-only matching
- Query strings and fragments must not be present in the registered URI
- Scheme and host: case-insensitive (normalize to lowercase)
- Path: case-sensitive, preserved exactly
- HTTPS required for all non-localhost URIs
- Redirect URIs must be validated **before** any redirect is issued (open redirect prevention)
- If `client_id` or `redirect_uri` is invalid → return HTTP 400, do not redirect

---

### 4. Authorization Codes

| Property | Requirement |
|---|---|
| Single-use | Code must be marked used on first exchange; replay must fail |
| Lifetime | ≤ 10 minutes |
| Bound to client | `client_id` must match stored value |
| Bound to redirect URI | `redirect_uri` must match stored value |
| Bound to PKCE | `code_verifier` must verify against stored `code_challenge` |

All five must be validated on token exchange.

---

### 5. Access Tokens

- Must be kept confidential in transit and at rest
- **Forbidden in query strings** — `GET /api?access_token=...` is not permitted
- Must be sent via `Authorization: Bearer <token>` header or POST body only
- Short lifetime required (typically 1 hour)
- Must use integrity protection (e.g. RS256-signed JWT)

---

### 6. Refresh Tokens (Public Clients)

For public clients (such as ChatGPT / browser-based), refresh tokens must be protected by one of:

| Mechanism | Description |
|---|---|
| **Rotation (most common)** | Each refresh issues a new access token + new refresh token; old refresh token is immediately invalidated |
| Sender-constrained (DPoP / mTLS) | Token bound to client key; each request must include proof of possession |

Priority Guardian uses rotation. Old refresh token must be invalidated atomically with issuing the new one.

---

### 7. TLS / HTTPS

All endpoints must require HTTPS. No exceptions.

| Endpoint | Requirement |
|---|---|
| `/oauth/pg/authorize` | HTTPS |
| `/oauth/pg/token` | HTTPS |
| `/oauth/pg/revoke` | HTTPS |
| `/oauth/pg/jwks` | HTTPS |
| `/oauth/pg/register` | HTTPS |
| `/oauth/mindsort/authorize` | HTTPS |
| `/oauth/mindsort/token` | HTTPS |
| `/oauth/mindsort/jwks` | HTTPS |
| `/oauth/mindsort/register` | HTTPS |
| `/.well-known/openid-configuration` | HTTPS |
| `/.well-known/oauth-authorization-server` | HTTPS |
| `/.well-known/oauth-protected-resource` | HTTPS |

HTTP requests must be rejected (or redirected to HTTPS at infrastructure level — not in application code).

---

### 8. CSRF Protection

CSRF must be mitigated. Two accepted mechanisms (either is sufficient):

1. **PKCE** — mitigates authorization code injection; if the AS verifies `code_challenge` support, PKCE alone satisfies CSRF protection
2. **`state` parameter** — client sends a random one-time-use value; server echoes it back; client verifies match before accepting the response

Priority Guardian accepts `state` and echoes it in error redirects and authorization code responses. With PKCE S256 enforced on all flows, PKCE is the primary CSRF control; `state` is the secondary.

---

### 9. Authorization Server Metadata (Discovery)

**Not an OAuth 2.1 MUST** — the spec explicitly says endpoint discovery is out of scope and that metadata is "typically provided."

**Required by both platforms:**
- **OpenAI (ChatGPT)**: Apps SDK OAuth integration requires `/.well-known/openid-configuration` or `/.well-known/oauth-authorization-server`.
- **Claude (Anthropic)**: MCP OAuth spec requires `/.well-known/oauth-protected-resource` (RFC 9728) advertising `authorization_servers`, plus `/.well-known/oauth-authorization-server` at that AS with `code_challenge_methods_supported: ["S256"]`. Claude refuses to connect if S256 is not advertised.

Priority Guardian exposes all three discovery documents. See `doc/ADR_005_platform_oauth_discovery_contracts.md` for the platform-specific shapes.

Minimum required fields:

```json
{
  "issuer": "https://www.priority-guard.com",
  "authorization_endpoint": "...",
  "token_endpoint": "...",
  "jwks_uri": "...",
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code", "refresh_token"],
  "code_challenge_methods_supported": ["S256"],
  "scopes_supported": [...],
  "token_endpoint_auth_methods_supported": ["none"]
}
```

> **Important:** `code_challenge_methods_supported` must list only `["S256"]` — not `["S256", "plain"]`.

---

### 10. Token Signing + JWKS

- Access tokens must be RS256-signed JWTs
- The authorization server must publish its public keys at `jwks_uri`
- Clients (and resource servers) verify token signatures using the published JWKS
- `issuer` (`iss`) and `audience` (`aud`) claims must be validated on token verification

---

### 11. Client Authentication

| Client Type | Authentication |
|---|---|
| Public clients (ChatGPT, SPAs) | No secret; `client_id` only |
| Confidential clients | `client_id` + `client_secret` (form body or HTTP Basic Auth per RFC 6749 §2.3.1) |

Client must be validated at the token endpoint. Unknown `client_id` → `invalid_client`.

> **Design constraint — Priority Guardian supports public clients only.**  
> ChatGPT is a public client and cannot securely store a `client_secret`. The token endpoint accepts `client_id` from form body or HTTP Basic Auth header, but `client_secret` is intentionally not validated. This is correct and compliant behavior for public clients per OAuth 2.1.  
> **Consequence:** If a confidential client is ever registered, secret validation must be implemented before that client goes live. Until then this is not a gap — it is a documented scope boundary.

---

### 12. Scope Enforcement

- Access tokens must include a `scope` claim
- Every API call must validate the token's scope before execution
- Requested scopes must be a subset of the client's registered scopes (validated at `/authorize`)
- Over-privileged tokens are a security violation

---

### 13. Token Revocation (RFC 7009)

A `/revoke` endpoint must be implemented:

- Accepts `access_token` or `refresh_token`
- Always returns HTTP 200 (per RFC 7009 — do not leak token existence)
- Must immediately invalidate the token on success
- Rate limited

---

### 14. Rate Limiting

Not in the OAuth 2.1 spec, but required by security guidance (RFC 9700 / Security BCP).

| Endpoint | Rate Limit Basis |
|---|---|
| `/authorize` | IP + login_hint (if present) |
| `/token` | client_id |
| `/revoke` | client_id |
| `/register` | IP |

Purpose: prevent brute force against `code_verifier`, `client_secret`, and `refresh_token`.

---

### 15. Secure Token Storage

- Tokens must be encrypted at rest using Fernet (AES-128-CBC with HMAC-SHA256)
- Tokens must never appear in logs (use hashes for log correlation)
- Refresh tokens stored as hashed values; plaintext only returned once at issuance

---

## Summary: OAuth 2.1 vs OpenAI-Specific Requirements

| Requirement | Source |
|---|---|
| PKCE S256 mandatory | OAuth 2.1 |
| Exact redirect URI matching | OAuth 2.1 |
| Implicit grant removed | OAuth 2.1 |
| ROPC grant removed | OAuth 2.1 |
| Bearer tokens forbidden in query strings | OAuth 2.1 |
| Refresh token rotation (public clients) | OAuth 2.1 |
| CSRF protection | OAuth 2.1 |
| TLS everywhere | OAuth 2.1 |
| Auth code single-use + TTL | OAuth 2.1 / Security BCP |
| Client authentication | OAuth 2.1 |
| Scope enforcement | OAuth 2.1 |
| Token revocation endpoint | RFC 7009 (referenced by OAuth 2.1) |
| JWKS + JWT signing | Best practice / required by OpenAI |
| Discovery endpoint | **OpenAI + Claude requirement** (not OAuth 2.1 MUST) |
| Rate limiting | Security BCP (not OAuth 2.1 MUST) |
| Encrypted token storage | Security BCP / GDPR |

