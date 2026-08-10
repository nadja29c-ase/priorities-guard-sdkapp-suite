# Increment Claude-P1 — `BearerAuthMiddleware` parity (rev 3)

**Scope:** Claude tree only. **No widget change, no version bump.**
**Reference implementation:** `mcp_server/priority_guardian/server.py` — the OpenAI `BearerAuthMiddleware`.

**Supersedes rev 2.** Changes: the duplicate-header rejection response is specified as `401` +
challenge rather than left implicit · the buffering memory bound must be reported as a number, not
asserted as an adjective.

---

## 1. Why this exists

The `_dupl` divergence sweep established that `priority_guardian_claude/server_dupl.py`'s
`BearerAuthMiddleware` is a **copy of the OpenAI one that lost pieces**, in a file whose header claimed
a config-only difference. Dropped symbols:

`_send_403` · `_send_413` · `_create_replay_receive` · `_BodyTooLargeError` · `_escape_error_description` · `_send_401`

**A22a restored the 401 half.** This increment restores what remains and is applicable.

**The implementation exists, working, in the OpenAI tree.** This is a port with adaptations, not a
design.

---

## 2. In scope

### P1-a — One shared Authorization parser, and duplicates rejected

Two layers currently read the same header differently:

- **`BearerAuthMiddleware`** takes the **first** header via `next()`, decoding **latin-1**
- **The middleware below it** overwrites in a loop and hands dispatch the **last**, decoding **utf-8**

Two consequences:

1. **Valid-then-expired duplicates:** the gate admits on the first, dispatch rejects on the last and
   returns the HTTP-200 `isError` path — **precisely what A22a exists to eliminate.**
2. **Encoding split:** `b"Bearer caf\xe9"` passes the gate and raises `UnicodeDecodeError` downstream —
   a **500** where A22-3 requires a 401.

**Requirement — one shared parser, called by both layers:**

| Headers present | Behaviour |
|---|---|
| 0 | unauthenticated — existing absent-header path, unchanged |
| 1 | parse it |
| **>1** | **rejected before authentication proceeds**, via the existing invalid-authentication path: **`401` with the `WWW-Authenticate` challenge** |

**The rejection response is specified, not left to judgement.** `400`, `401` and `403` would all
satisfy "reject deterministically" and they mean different things to Claude — **only a `401` with the
challenge triggers re-authentication.** Two credentials is an authentication failure, not a malformed
request. A22-3 already establishes that every malformed-credential class returns 401, never 500;
duplicate headers is a malformed-credential class, and routing it to a 400 would make it the single
exception the shared parser exists to remove.

**Do not define first-vs-last semantics.** Harmonising the choice fixes the divergence and **preserves
the ambiguity**. Credential ambiguity is the condition behind request-smuggling and auth-layer
inconsistency.

**Remove one parser, do not align two.** Two implementations of one contract diverge — this is the
third instance of that shape in this project.

**On the edge:** Cloudflare returns 400 to any request carrying two `Authorization` headers, isolated
by controls (single `Basic` → 401, single garbage `Bearer` → 401, duplicate `X-Test` → 401). That is
**defence-in-depth PG does not own.** It holds only while the edge behaves this way and while PG sits
behind it — traffic may bypass it later, its behaviour may change, and tests call the origin directly.
**The origin must be safe on its own.** Record CF-2 as edge-blocked, not mitigated.

The encoding split is not edge-blocked.

### P1-b — Body size guard (413), enforced on the stream

`_send_413`, `_BodyTooLargeError` and `_create_replay_receive` were dropped. PG-Claude currently
accepts a request body of any size.

**Severity, stated accurately:** A22a's 401 fires before the body is read, so an *unauthenticated*
oversized body is cheap to reject. The exposure is an **authenticated** oversized body, on a Render
Starter instance.

**Requirement, in two layers:**

1. **`Content-Length` present and over the limit → reject immediately with 413**, without reading the
   body. This is an **optimisation only.**
2. **Otherwise → enforce the same hard limit while consuming the ASGI body**, aborting once exceeded.

**`Content-Length` alone is not sufficient and must not be the only enforcement.** It is
client-controlled and may be absent entirely under chunked transfer encoding. A limit enforced on a
header the caller sets is not a limit.

**Therefore bounded buffering and replay are required**, not conditional on a finding.

**The memory bound must be an engineering property, not an adjective.** "Bounded" is not a claim until
it carries a number. Report:

- the **configured size limit** and where the value came from
- the **maximum in-memory allocation per request**
- **why that is acceptable on a Render Starter instance under concurrent load** — each in-flight
  request holding a buffered body is a memory multiplier, and the instance is small
- **whether replay ever spills to disk.** Expected: **no.** If it does, that is a finding, not an
  implementation detail

⚠️ **This is the dangerous part of the increment.** Reading an ASGI request body consumes the stream.
**Without correct replay, FastMCP receives an empty body and every request fails — not only oversized
ones.** It fails closed for everybody. That is why `_create_replay_receive` exists in the source and
why this must be a port rather than a fresh implementation.

### P1-c — `_escape_error_description`

Dropped alongside the rest. **Establish from the source what it protects against**, then:

- **If it guards values interpolated into a `WWW-Authenticate` header or any other header
  construction — port it**, even if every current call site passes a controlled string.
  Header-generation utilities should be safe **by construction**, not safe by the accident of today's
  inputs.
- If it guards something PG-Claude genuinely does not do, report that with the scope of the claim
  stated.

---

## 3. Explicitly out of scope

**Scope step-up (403) — NOT APPLICABLE, not deferred.**

PG has **one** OAuth scope, `pg.access`, issued to every authorised user and required by every
protected tool. **No valid-token-insufficient-scope state exists**, so there is no reachable path to
implement against. A22b is recorded `NOT APPLICABLE` with an activation trigger: *any change
introducing multiple scopes, per-tool scope differences, or migration of existing grants to a new scope
model requires implementing the 403 challenge before deployment.*

**Do not implement `_send_403`.** P1-b's buffering makes the future 403 a small addition when the
trigger fires — note that in the report so the future increment knows the groundwork exists.

**Also out of scope:** the widget · `WIDGET_VERSION` and the bundle · the OpenAI tree · lazy
authentication (PG gates every request; recorded as a deliberate difference).

---

## 4. Constraints

- **Port, do not rewrite.** Copy from the OpenAI source and adapt only what platform difference
  requires. Verify byte-identity where nothing needed to change, as F1's port did with
  `inspect.getsource()`.
- **The OpenAI tree is not modified.** It is published, approved, and already correct.
- **Middleware ordering.** Establish the current runtime order and state whether this changes it.
  `MCPContentTypeAndAcceptFixMiddleware` sets `auth_header_var` and runs **after**
  `BearerAuthMiddleware`, which is why the gate reads the header off the ASGI scope directly. P1-a's
  shared parser must work in both positions.
- **Do not remove dispatch-level validation.** `authenticate_request` also performs tool-scope
  enforcement; removing it would delete that as a side effect.
- No new dependency. No change to `WWW_AUTHENTICATE_VALUE` or `SCOPES_SUPPORTED`.

---

## 5. Acceptance

No automated widget harness, but this is server-side and **A22a's in-process ASGI pattern applies** —
`tests/unit/mcp_pg_claude/test_bearer_auth_middleware_validation.py` is the shape to follow, including
its **negative control**: a test that cannot fail proves nothing.

### P1-a — shared parser, duplicates rejected
*Static:* exactly one extraction function; both layers call it; one decoding; **duplicates rejected at
the parser, before authentication proceeds** — not resolved to a winning header.
*Tests:*
- duplicate headers — valid-then-expired **and** expired-then-valid — both produce **`401` with the
  `WWW-Authenticate` challenge**, and gate and dispatch reach the **same** decision
- `b"Bearer caf\xe9"` → **401, not 500**
- 0 headers → unchanged absent-header path
- 1 valid header → admitted

*Negative control:* with the shared parser reverted, the duplicate and encoding tests fail.

### P1-b — size guard, three cases
1. **Oversized declared `Content-Length`** → **413 without a full read**
2. **Oversized streamed body with no length** → **413 during bounded read**
3. **Normal body** → **exact bytes replayed downstream**, asserted by the inner app receiving the full
   payload — not by absence of an error

*Negative control:* **with replay disabled, case 3 must fail.** If it still passes, the test is not
exercising the replay path and proves nothing.

*Static:* the limit's value, its source, and the memory-bound figures required above.

### P1-c
*Static:* ported, with what it guards named — or reported as not reached, with the scope of that claim
stated.

### Cross-cutting — A22a must not regress
Re-run A22a's wire probes against the deployed build: **expired/invalid token → 401 + exact challenge +
`Cache-Control: no-store` + not a 200 tool error**, and a valid token still admitted. This increment
touches the same middleware.

---

## 6. Rollback

**This is the auth path. If it is wrong, nobody can connect.** P1-b is worse than A22a in one respect:
**a broken replay fails closed for every request, not only unauthenticated ones.**

**Before deploying, record and re-verify at that moment** — this record has gone stale three times: the
deployed commit · the resource URI · the Render deployment identifier on `srv-d6vbrt9r0fns73c6n080` ·
**autoDeploy's current state**.

**Roll back immediately if:** the connector cannot be added · a valid token is rejected · any tool call
fails for an authenticated user · **any normal request returns an empty or malformed response**, which
is replay failing.

---

## 7. Report

- Commit hash · changed set from `git status --porcelain` · confirmation **no widget bytes, no version bump**
- What was ported byte-identically and what required adaptation, with the reason for each
- **P1-a's duplicate-header response**, confirmed as `401` + challenge via the existing
  invalid-authentication path
- **P1-b's four memory-bound figures**: configured limit and its source · maximum in-memory allocation
  per request · why that is acceptable on Render Starter under concurrent load · whether replay spills
  to disk
- Confirmation the size limit is **enforced on the stream**, not on `Content-Length` alone
- Middleware ordering before and after
- Each acceptance block with its result **and its negative control's result**
- A22a's wire probes re-run against the deployed build
- **A22b's status unchanged — NOT APPLICABLE** — with a note on whether P1-b's buffering makes the
  future 403 a small addition
- **CF-2 recorded as edge-blocked, not mitigated**, and confirmation the origin is now safe
  independently of the edge
- **Still unresolved, carried forward:** the `dupl_sweep` module-level blind spot (middleware order and
  route registration are not compared — A22a's own failure class) · JWKS unknown-kid amplification ·
  DEBUG logging in production · eight uncaptured sources
- An explicit list of what was **not** verified