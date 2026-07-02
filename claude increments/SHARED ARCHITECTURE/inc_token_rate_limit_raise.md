# Increment: Raise /token rate limit 5→30/min (unblock ChatGPT reconnect)

**Type:** Backend hotfix-grade micro-increment (shared OAuth provider, token endpoint). Touches the `/token` rate limiter used by ALL apps (Focused, PG, MindSort) on BOTH platforms. Small diff, but shared-auth blast radius — full predeploy + live verification required.

**Priority:** High. This is the confirmed cause of the live "PG won't reconnect on ChatGPT" failure.

---

## Root cause (confirmed from production logs — not inferred)
A clean delete-and-re-add of the PG connector on ChatGPT produced, in ONE coherent flow (correlation_id `03d5349c` / `e6a13d9d`):
`oauth.authorize.request` → `consent_rendered` (priority_guardian) → `consent.allowed` → `consent.recorded` → code issued → 302 to ChatGPT → `oauth.token.request` (grant_type=authorization_code) → **`rate_limit.exceeded` key_pattern=ratelimit:oauth:token count=8 limit=5** → NO `oauth.token.success`.

So ChatGPT got the authorization code, attempted the code→token exchange, was **429'd at `/token`**, never received a token, and therefore never called the MCP server — tile stays "Connect." The token bucket was already saturated (counts 6–8 across the window) partly by background `refresh_token` traffic sharing the same per-client+IP bucket.

This is NOT inc_08 (consent classification works end-to-end in the same logs). This is the `/token` limiter being too low for the reconnect burst (code exchange + immediate refresh rotation + ChatGPT's parallel retries), all sharing one 5/min bucket.

---

## Scope (do ONLY this)
1. **Raise the `/token` rate limit from 5/min to 30/min** in `backend/core/rate_limit.py::rate_limit_token`.
2. **Log `grant_type` on token rate-limit events** so the follow-up (split buckets) can be decided from evidence.

NOTHING ELSE. No bucket-splitting by grant_type (that is the tracked follow-up below). No change to other limiters. No change to token issuance logic, discovery, MCP servers, or inc_08.

---

## Why 30 (not an arbitrary number)
Mirrors the EXISTING precedent in the same file: `rate_limit_register` was raised 10→30 with the documented rationale *"Claude.ai fires multiple parallel PKCE flows on reconnect (known platform behavior). 10/min is insufficient."* The `/token` endpoint faces the identical reconnect storm (ChatGPT AND Claude) and never got the same treatment. 30/min per client+IP comfortably absorbs a reconnect burst plus normal refresh churn, while remaining bounded and per-client (one client+IP cannot exceed 30/min, so no global hole; a misbehaving client cannot starve others).

## Why NOT split buckets now (scope discipline)
Splitting `authorization_code` and `refresh_token` into separate buckets is the structurally-correct fix (prevents refresh churn from ever starving a code exchange), but it is a redesign of a security-sensitive limiter and should not be done under pressure. Raise-the-limit is minimal, reversible, and matches precedent. Bucket-splitting is tracked as a follow-up, gated on whether 429s actually continue after this change.

---

## Required change (Copy and Adjust, Never Rewrite)

### `backend/core/rate_limit.py`
Current:
```python
async def rate_limit_token(request: Request, client_id: str) -> None:
    """Rate limit /token endpoint: 5 requests per minute per client+IP."""
    ip = get_client_ip(request)
    key = f"ratelimit:oauth:token:{client_id}:{ip}"
    await check_rate_limit(key, limit=5, window=60, request=request)
```
Change: raise `limit` to 30, update the docstring, and add a register-style rationale comment citing the same reconnect-storm reason and the observed production 429. The limit value is the only behavioral change; key shape and window stay identical.

**Guardrail 1 — log grant_type ON EXCEED ONLY, sanitized.** `check_rate_limit` emits the `rate_limit.exceeded` log generically; it does not know the grant_type. Make the token rate-limit event carry the grant_type, subject to TWO hard requirements:

1. **Log grant_type ONLY when the request is actually rate-limited (429), NEVER on a successful token request.** Do not emit a per-request log. The grant_type must appear only on the exceed path. Logging on every token request would create noise and misleading telemetry and would corrupt the exact signal this guardrail exists to provide (the follow-up bucket-split decision reads these exceed events). Recommended mechanism: add an optional `grant_type: str | None = None` parameter to `rate_limit_token`; pass it from the call site; and emit a dedicated `oauth.token.rate_limited` warning (with the sanitized grant_type + masked client_id) ONLY in the branch where `check_rate_limit` raises `RateLimitExceeded` (catch it, log, re-raise). Do NOT add grant_type to `check_rate_limit`'s generic success path.

2. **Sanitize grant_type before logging — it is attacker-controlled `Form(...)` input.** Validate against the known OAuth set `{"authorization_code", "refresh_token"}` before logging; any other/missing value logs as the literal `"unknown"`. Never log the raw client-supplied string (prevents log injection / telemetry poisoning from a malicious client sending an arbitrary grant_type).

REQUIREMENT restated: when (and only when) a token request is 429'd, the logs show which of `{authorization_code, refresh_token, unknown}` was rejected. Use `mask_client_id`; never log tokens.

### `backend/core/oauth_provider/token_endpoint.py`
Only if needed to pass `grant_type` into `rate_limit_token` (per guardrail 1). The call site is `await rate_limit_token(request, client_id)` — becomes `await rate_limit_token(request, client_id, grant_type=grant_type)`. No other change.

---

## What NOT to do
- Do not split grant-type buckets (tracked follow-up).
- Do not touch any other limiter (authorize/register/revoke).
- Do not change token issuance, refresh rotation, discovery, or MCP code.
- Do not touch inc_08 — the logs rule it out for this failure.
- Do not log tokens or unmasked client_id.

---

## Tests
This is a rate-limit constant + a log field. Keep tests proportional.
1. **`rate_limit_token` allows up to 30/min, blocks the 31st** (per client+IP). Assert the 30th call passes, 31st raises `RateLimitExceeded`. *Catches:* the limit not actually being raised (still 5), or an off-by-one.
2. **Two different client+IP combos have independent buckets** — client A at limit does not block client B. *Catches:* key collapsing to a shared/global bucket (regression that would let one client starve others, or mis-key on `[from_header]`).
3. **grant_type appears in the token rate-limit log ON EXCEED, sanitized.** Trigger the limit, assert the emitted warning includes the grant_type. *Catches:* guardrail 1 silently not wired (the follow-up decision would then be blind).
3a. **No grant_type log on a SUCCESSFUL token request.** A token request under the limit must NOT emit the `oauth.token.rate_limited` warning. *Catches:* logging on every request (noise + corrupted telemetry that the bucket-split decision relies on).
3b. **Unknown/garbage grant_type is sanitized to `"unknown"` in the log.** Send a 429 with an off-spec grant_type (e.g. `"foo"` or empty) and assert the log shows `"unknown"`, not the raw value. *Catches:* log injection / telemetry poisoning from attacker-controlled `Form(...)` input.
4. (If feasible) **`[from_header]` client_id path keys on the real client_id, not the literal "[from_header]"** — since ChatGPT sends credentials via Basic Auth, confirm the key uses the extracted client_id. *Catches:* all ChatGPT clients sharing one bucket because the key used the log-placeholder string. (Verify against token_endpoint: client_id is extracted from Basic Auth BEFORE rate_limit_token is called, so the real value is passed — this test confirms that wiring.)

For each test, document "what bug would still pass this test?"

---

## Production readiness
- **Security:** raising a per-client+IP limit 5→30 is bounded and does not open a global hole; per-client keying preserved. Token endpoint remains brute-force-bounded at 30/min/client+IP. Net: restores availability without materially weakening abuse protection (compare: authorize is 500/min, register 30/min).
- **Scalability/latency:** none (constant change).
- **DB:** none.
- **Reversibility:** trivially revert the constant if needed.

## Definition of Done
- [ ] `rate_limit_token` limit is 30, window unchanged (60), key shape unchanged, docstring + rationale comment updated.
- [ ] Token rate-limit events log `grant_type` (guardrail 1).
- [ ] Tests 1–3 pass (4 if feasible); each documents the bug it catches.
- [ ] Full `pytest tests/unit/ --ignore=tests/unit/mcp_focused -q`: known-baseline unchanged.
- [ ] No change outside `rate_limit.py` and (if needed) the one call-site line in `token_endpoint.py`.
- [ ] Before commit: read `OPERATIONS_PREDEPLOY.md`.

## Post-deploy verification — GUARDRAIL 2 (this is the real root-cause confirmation, not a formality)
After deploying the shared backend, perform ONE clean ChatGPT reconnect of PG and confirm the FULL chain in logs:
1. Backend: `oauth.authorize.request` → `consent.recorded` → `oauth.token.request` → **`oauth.token.success`** (NOT `rate_limit.exceeded`).
2. PG MCP (`pg.priority-guard.com`): an **authenticated `POST /mcp`** appears shortly after token success (Authorization header present; status 200, or at least past the `missing_header` middleware rejection).
3. ChatGPT: connector tile shows **Connected**.

Interpretation:
- All three present → root cause confirmed fixed. Done.
- token.success but STILL no authenticated `/mcp` call / tile stays Connect → the 429 was masking a SECOND problem (discovery/DCR-association, ChatGPT-side). Re-open investigation at the MCP-handshake layer — do NOT assume this increment failed; it fixed the 429, and the next layer is now observable.
- Still `rate_limit.exceeded` at token → 30 is still too low under real refresh load → escalate to the bucket-split follow-up immediately.

Verify both platforms aren't regressed: a MindSort (ChatGPT) and MindSort-Claude consent/token still succeed (shared limiter touched).

---

## Tracked follow-up (do NOT bundle)
**Split `/token` rate limits by grant_type.** IF 429s continue after this change (visible now via guardrail-1 grant_type logging), separate the buckets:
- `ratelimit:oauth:token:code:{client_id}:{ip}` (authorization_code) — the must-succeed connect path.
- `ratelimit:oauth:token:refresh:{client_id}:{ip}` (refresh_token) — high-frequency rotation.
This structurally prevents refresh churn from starving a code exchange. Gated on evidence from guardrail 1; not done preemptively.

Secondary note (not this increment): background refresh traffic alone was pushing the bucket to counts 6–8. If, after raising to 30, refresh-only 429s still appear, investigate refresh cadence (something may be rotating more aggressively than expected). Observe; do not chase now.
