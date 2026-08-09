# Increment Claude-A22 — Token validation at the HTTP boundary (rev 3)

**Row:** A22 · `DOC-CONSTRAINT`, binding via Policy §3H · ⚠️ SILENT
**Scope:** Claude tree only. **No widget change, no version bump.**

**Supersedes rev 2.** Changes: the audit-record file is added to scope, resolving a contradiction where §§6–7 and §10 required
edits §3 forbade · A22-1's valid-token half is made specific · A22-3 enumerates three malformed-header classes.

---

## 1. The requirement, verbatim

`sources_raw/authentication.raw.md`:

> **Always return a `401` with a `WWW-Authenticate` header** whose `resource_metadata` parameter points at your protected
> resource metadata document…
>
> The `401` status is required — **Claude does not honor a `WWW-Authenticate` header on a `200` response**

Why this is routine rather than an edge case, same page:

> Claude refreshes tokens **reactively on a 401 response**, with a proactive refresh up to five minutes before the stored
> expiry.

`sources_raw/lazy-authentication.raw.md` prescribes where the check belongs:

> Because the refusal must be an HTTP status, the check has to happen **before the JSON-RPC message reaches the MCP SDK**.
> Once a tool handler is running, its return value is already destined to be wrapped in a 200 response.

---

## 2. The defect

`BearerAuthMiddleware` tests **header presence**, not **token validity**:

```python
has_auth = any(name == b"authorization" for name, _ in scope.get("headers", []))
if not has_auth:
    → 401 + WWW-Authenticate
```

An expired token carries a header. It passes this gate, reaches dispatch, and `tools_dupl.py` returns
`CallToolResult(isError=True)` — an HTTP **200**. Claude does not honour a challenge on a 200, so **no refresh is triggered**
and the user sees *"Authentication required. Please connect your account."* where a re-auth prompt belongs.

The `_meta["mcp/www_authenticate"]` attached there is ChatGPT's re-auth channel per its own docstring. Claude does not read it.

**Reachable causes, all with a header present:** malformed header format · **token expired — routine mid-session** · token
validation failed. Only *absent header* is caught today.

---

## 3. Scope

**Code**
- `mcp_server/priority_guardian_claude/server_dupl.py` — `BearerAuthMiddleware` only
- `mcp_server/priority_guardian_claude/mcp_auth_dupl.py` — **only if** a change is genuinely required; justify

**Record**
- `doc/Claude_Compliance/COMPLIANCE_AUDIT_RECORD.md` — **only** A22's status and evidence, the deferred insufficient-scope
  limb, and the lazy-auth deliberate-difference note

**Do not touch the canonical requirement text** in `CLAUDE_COMPLIANCE_REQUIREMENTS_CANONICAL.md`. That file holds the
normative criterion; only PG's status against it moves.

**Out of scope:** the widget · `WIDGET_VERSION` and the bundle · the OpenAI tree · scope step-up (§6) · lazy auth
implementation (§7).

**OpenAI is unaffected — verified.** `tools_dupl.py` imports its auth from `priority_guardian_claude/mcp_auth_dupl.py`; the
OpenAI dispatcher uses `priority_guardian/mcp_auth.py`. Five `mcp_auth` files exist, one per app. `build_unauthorized_meta` is
Claude-local. ChatGPT's 200 + `_meta` shape — correct for that platform — is untouched.

---

## 4. What must be true afterwards

**A request to `/mcp` carrying an invalid or expired token receives an HTTP 401 with the `WWW-Authenticate` challenge, before
the JSON-RPC message reaches the MCP SDK.**

- **Reuse the existing `WWW_AUTHENTICATE_VALUE`.** It is already correct and already carries `scope="pg.access"` built from
  `SCOPES_SUPPORTED` — verified against the construction and against a live handshake observation. **Do not build a second
  challenge value.**
- **Headers only. Do not read the request body.** See §6.
- **Absent-header behaviour is unchanged.** That path works today and is how connector creation succeeds.
- **A malformed header produces a 401, not a 500.**
- Validation failure must not leak token contents or internal detail into the response body.

### The reachability finding this rests on

`validate_jwt(token, correlation_id)` is **context-free** — two string arguments, no request-scoped reads, module-level
dependencies only (`_jwks_cache`, `jwt`). It performs JWKS fetch, signature, issuer, audience, expiry and nbf checks. The
middleware already holds the header and can generate a correlation id.

`authenticate_request` is **not** the function to call from middleware: it reads `_meta` for the correlation id, reads the
header back out of `auth_header_var` — a ContextVar the middleware itself sets — and performs tool-scope enforcement, which
needs the tool name from the body.

**So this increment needs no refactor.** The separation already exists in the code.

### Middleware ordering — establish and state

`MCPContentTypeAndAcceptFixMiddleware` sets `auth_header_var`; `BearerAuthMiddleware` performs the presence check. Different
classes, different positions in the stack. Establish the current order and state whether validation changes it. Anything
touching either is ordering-sensitive.

### Double validation — keep by default

`authenticate_request` will still run at dispatch and re-validate.

> **Keep dispatch-level validation unless source inspection proves it is redundant, semantically identical, and that removing
> it cannot weaken scope enforcement or another auth guarantee.**

This increment adds the correct HTTP rejection boundary. Removing an existing security layer at the same time expands it into
a redesign of the defence layers. Duplication costs a little; accidentally removing scope enforcement costs a lot. If the
duplication is kept, say so and why — do not leave it unaddressed.

---

## 5. Constraints

- No new dependency.
- No change to `WWW_AUTHENTICATE_VALUE` or `SCOPES_SUPPORTED`.
- No change to the OpenAI tree.

### JWKS on the request path — decision boundary

Validation at the HTTP boundary puts the JWKS fetch on every protected request. **Establish the existing cache behaviour and
report it. Do not optimise speculatively.**

> **If moving validation to the HTTP boundary introduces a new failure mode in which ordinary valid-token requests
> systematically fail on a normal JWKS cache miss or transient fetch condition, stop and report before deployment.**

A transient upstream outage can obviously make authentication unavailable; that is not the concern. The concern is
accidentally creating a new implementation-specific failure mode that did not exist when validation ran at dispatch.

---

## 6. Deferred — scope step-up, and the accounting consequence

PG returns a 200 tool error for `InsufficientScopeError` as well, so the same defect exists for scope insufficiency. It is
**deliberately not in this increment**:

- Scope sufficiency is **tool-level** — it needs the tool name, which is in the JSON-RPC body.
- **Reading an ASGI request body in middleware consumes the stream.** Without correct buffering and replay, FastMCP downstream
  receives an empty body and **every request fails — not just unauthenticated ones.** It fails closed for everybody, on a
  server that ships no logs, behind a widget that cannot diagnose it.

  > **[ANNOTATION 2026-08-09, post-implementation — not a change to the brief's intent.]** *"ships no logs" is
  > **FALSE**. `configure_logging()` is genuinely never called in the Claude tree, but structlog's default `ConsoleRenderer`
  > plus Render's stdout capture means PG-Claude has always emitted `auth.success`, `jwt.validation.success`,
  > `scope.enforcement.success`, `tool.timing` and per-request `http.request`. Observed directly in this increment's deploy
  > logs. This was one of two legs supporting the deferral and it does not hold; the body-read leg is also weaker than stated,
  > since PG-OpenAI already implements buffering, size guard and replay. See the audit record.*
 **That is strictly worse than the defect being fixed.**
- Scope insufficiency requires a valid token with wrong scopes — for PG, a token issued before a scope change. **Rare.**
  Expired tokens are **routine**.

### A22 does not close with this increment

A22 covers two limbs: `401` rather than a tool error, **and** `403` with `error="insufficient_scope"` for scope step-up. Only
the first is fixed here.

> **A22 PARTIAL.** The HTTP 401 limb is fixed and verified at wire level. The `403` / `insufficient_scope` limb remains open
> under the separately recorded scope-step-up gap.

**Do not mark the A22 row closed.** A correct implementation with a falsely closed row is worse than an open row — the
deferred limb disappears from the record and nobody looks for it again.

---

## 7. Recorded, not fixed — lazy auth

The page describes lazy authentication as optional. PG gates every request, including `initialize` and `tools/list`.

That is **defensible** — PG exposes no unauthenticated tools — but state it in the audit record as a **deliberate difference**,
so it does not read as an unnoticed gap.

---

## 8. Acceptance

No automated harness. Manual, recorded, with test-state provenance: how each state was produced, no test-only code in the
diff, no guard bypassed, anything unproducible **named individually**.

### A22-1 — DEPLOYMENT GATE. Wire-level. Non-waivable.

**The reason this increment exists, and it is not an acceptance item that can be recorded unverified.**

**Reject half.** Send `/mcp` an **expired or cryptographically invalid** bearer token. Assert on the actual HTTP response:

- status is **`401`**
- **`WWW-Authenticate` is present and equals the expected challenge**
- **`Cache-Control: no-store` is present**
- the response is **not** HTTP `200` containing a FastMCP or tool error

**Admit half.** Send a **valid bearer token with a well-formed MCP JSON-RPC request**. Assert the response is **not a `401`
from `BearerAuthMiddleware`**.

State the admit half this precisely because "admitted normally" is ambiguous: a malformed body would produce a non-401 failure
downstream and could be misread as a pass. The assertion isolates the middleware from everything below it.

> **If this test cannot be executed, or does not pass, do not deploy A22.**

This is a direct HTTP test — it does not require Claude.ai, and it asserts on the wire rather than on what a UI does with the
response. That makes it both more available and more precise than a host observation.

### A22-1b — host-level confirmation, secondary

*On host:* with the connector working, cause the access token to expire, then use the widget or ask Claude to call a tool.
**Expect:** Claude prompts re-authentication. **Not expect:** an error message reading *"Authentication required. Please
connect your account."*

Good evidence, and **no longer the only proof**. If it cannot be produced, record it as unproduced — A22-1 already carries the
gate.

### A22-2 — absent header unchanged
*Static:* the absent-header branch is untouched.
*On host:* **delete and re-add the connector.** OAuth discovery and DCR complete as they do today. This is the path that works
and must not regress.

### A22-3 — malformed headers, three classes

Test each separately, not one arbitrary malformed string:

1. **Wrong auth scheme** — e.g. `Authorization: Basic …`
2. **`Bearer` with no token**
3. **Syntactically valid but cryptographically invalid JWT** — the class most likely to take a different path through
   `validate_jwt` and surface an exception

Each must produce **401, never 500**, with **no token contents or internal detail in the response body.**

### A22-4 — valid token unaffected
*On host:* normal operation across several tool calls. Watch for latency regression from JWKS on the request path.

### Cross-cutting
Widget renders and behaves as on v10 · console open and stated · every warning recorded, none exempted for appearing
host-side.

---

## 9. Rollback — read before deploying

**This is the auth path. If it is wrong, nobody can connect, and the Claude server ships no logs to diagnose it.**

> **[ANNOTATION 2026-08-09]** *The "no logs" half is **FALSE** — see the §6 annotation. The risk framing here was
> overstated: diagnosis was available throughout, and the deploy produced full structured logs including `auth.success` and
> `tool.timing auth_ms=0.6`. The rest of the sentence stands — it **is** the auth path.*
 That is a
different risk class from every widget increment in this sequence.

**Before deploying, record and re-verify at that moment** — this record has gone stale three times: the deployed commit · the
resource URI · the Render deployment identifier on `srv-d6vbrt9r0fns73c6n080` · **autoDeploy's current state**.

**Rollback target: v10.** Best-understood artifact — B and C verified on host, M3 and M9 observed.

**Roll back immediately if:** the connector cannot be added · a valid token is rejected · any tool call fails for an
authenticated user · `initialize` or `tools/list` regress. After rollback, verify the restored build renders and tool calls
work.

---

## 10. Report

- Commit hash · changed set from `git status --porcelain` · confirmation **no widget bytes changed and no version bump**
- **A22-1's wire-level result, with the four reject assertions and the admit assertion individually** — this is the deployment
  gate
- **A22-3's three malformed classes, each with its result**
- Middleware ordering before and after, and whether validation changed it
- **The double-validation outcome** — kept, or removed with the three-part proof from §4
- **JWKS behaviour**: cache, timeout, and whether a normal cache miss or transient fetch can systematically fail a valid
  request
- Each acceptance block's result, with how each state was produced — or **named individually as unproduced**
- **A22 recorded as PARTIAL** in the audit record, per §6, with the deferred limb named
- **Still unresolved, carried forward:** scope step-up (§6) with the body-read hazard · lazy auth as a deliberate difference
  (§7) · server-side logging absent · no widget test harness
- An explicit list of what was **not** verified