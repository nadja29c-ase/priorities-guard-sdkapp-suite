# `_dupl` divergence sweep — 2026-08-09

**Report only. Nothing was fixed.** Two divergences below are findings; the rest are justified or benign.

---

## 1. Scope, stated up front

Stating the bound is the point of this section. An unstated scan bound is how this project has produced
nine or ten false negatives, including the one that caused A22.

**Swept:** every `*_dupl.py` in the two **Claude** trees — `mcp_server/priority_guardian_claude/` (8 files)
and `mcp_server/mindsort_claude/` (7 files). **15 files.**

**Not swept:** the OpenAI trees (`priority_guardian/`, `clarity/`). They are the **sources**, not copies —
a divergence there is not a `_dupl` defect, it is just code. PG-OpenAI is also published and approved, so
touching it is a different risk class with a different decision behind it.

**Compared:** each `_dupl` against the source **its own header names**, at the level of **same-named
symbols** — top-level functions, classes, and class methods.

**Method — and why not the obvious one.** Size was rejected as a signal because it is wrong in *both*
directions here:

| File | Size delta | Truth |
|---|---|---|
| `mindsort_claude/mcp_auth_dupl.py` | **−84 %** | **Safe.** It delegates: imports `clarity.mcp_auth`, rebinds its globals, re-exports its symbols. |
| `priority_guardian_claude/server_dupl.py` | **−11 %** | **This is A22.** Dropped JWT validation, scope enforcement and the 413 guard. |

A size-based sweep would have raised a false alarm on the safe file and **sailed straight past its own
founding case.** So each symbol is compared twice: once with constants intact, once with every constant
normalised. Structure identical + constants differ = the config swap the headers claim. Structure differs =
something else.

**Four outcomes**, per the agreed taxonomy:

1. **Config-only** — logic identical, values differ. The claimed reason. Fine.
2. **Platform-required** — a real Claude/ChatGPT difference. Fine, **but the reason must be written down.**
3. **Unjustified** — anything else. Findings.
4. **Dropped** — present in source, absent from `_dupl`. The A22 shape, and invisible to any comparison
   that only looks at symbols present in both.

Script: `scratchpad/dupl_sweep.py` (AST-based; re-runnable).

### What a clean result would and would not prove

It would **not** prove equivalence. Four known blind spots:

- **Relocation reads as DROPPED.** Comparison is per-file. MindSort's `wellknown_*` handlers show up as
  dropped from `server_dupl.py` but live in `discovery_dupl.py` and answer **200** in production. Confirmed
  false positive.
- **Module-level code is not compared** — only functions, classes and methods. Import-time constants,
  route registration and middleware *wiring order* are outside the sweep. A22's sibling risk lives exactly
  there.
- **Behaviour is inferred from structure, not executed.** Two structurally identical functions calling
  differently-configured dependencies still behave differently.
- **Only files whose header names a resolvable source were compared.** Three did not (below).

---

## 2. Result

15 files · 46 raw divergences · **2 findings** after triage.

| `_dupl` file | dropped | divergent | config-only | added |
|---|---:|---:|---:|---:|
| `priority_guardian_claude/server_dupl.py` | **7** | 4 | 0 | 4 |
| `priority_guardian_claude/handlers/resources_dupl.py` | 2 | 3 | 0 | 0 |
| `priority_guardian_claude/mcp_auth_dupl.py` | 1 | 1 | 0 | 0 |
| `priority_guardian_claude/discovery_dupl.py` | 0 | 3 | 0 | 0 |
| `priority_guardian_claude/handlers/tools_dupl.py` | 0 | 1 | 0 | 0 |
| `priority_guardian_claude/http_client_dupl.py` | 1 | 0 | 0 | 0 |
| `mindsort_claude/server_dupl.py` | **7** | 4 | 0 | 8 |
| `mindsort_claude/handlers/resources_dupl.py` | 2 | 4 | 0 | 0 |
| `mindsort_claude/mcp_auth_dupl.py` | 23 *(delegates — expected)* | 0 | 0 | 0 |
| `mindsort_claude/discovery_dupl.py` | 0 | 1 | 0 | 0 |
| `mindsort_claude/handlers/tools_dupl.py` | 0 | 1 | 0 | 0 |
| `*/response_adapter_dupl.py`, `*/tools_list_dupl.py` | — | — | — | — |

### The column that says the most is `config-only`: **zero, everywhere.**

Not one symbol in any of the 15 files differs *only* in its constants. Every symbol is either byte-identical
to its source or **structurally different**. Yet every header says some version of *"exists only because it
imports platform-specific config."*

**That claim is false at symbol level across the entire convention.** Config differences live at module
level — imports and module constants — while the *functions* diverge structurally. The headers describe why
the file was created, and are routinely read as a statement about what is inside it. A22 is what that
misreading costs. **This is a documentation finding against all 15 files, not against any one of them.**

---

## 3. Findings

### F1 — `_sanitize_uri_for_logging` dropped; PG-Claude handled client-controlled URIs raw

**Unjustified divergence. FIXED in `f0170f8`.**

> **SCOPE CORRECTION, 2026-08-09.** This finding was first written — by me, and echoed in review — as
> *"URI **logging**"*, and as **two** sites. Both were wrong. It is **URI handling**, at **four** sites:
> three logs and **one reflection**. The reflection site puts raw caller input into a response `_meta`
> that travels back into **Claude's context** — a mild **prompt-injection** surface, which is a
> different exposure class from a PII or minimisation question. It is also the site nobody searching
> for *log* sites would ever find. The mis-scoping mattered more than the miscount: a reviewer told
> "URI logging" would not have looked for it.

`priority_guardian/handlers/resources.py` defines `_sanitize_uri_for_logging` and logs only `safe_uri`. Its
docstring records three increments of hardening:

> *inc_99: Defensive hygiene against pathological URIs from authenticated clients. inc_100: Strip
> query/fragment for all URIs, strip userinfo from netloc. inc_101: Switched from blocklist to allowlist.
> Only http/https/ui/file pass through with components; all other schemes (mailto:, blob:, data:,
> javascript:, etc.) are redacted. **Closes the class of PII leaks.***

`priority_guardian_claude/handlers/resources_dupl.py` **had no such function** and used the raw value at
**four** sites — three logs and one reflection:

```python
133:  logger.info("resource.read.called", uri=uri_str)                  # log
135:  logger.debug("resource.read.requested", uri=uri_str, ...)         # log — DEBUG is ON in prod
140:  logger.debug("resource.read.serving_widget", uri=uri_str, ...)    # log — multi-line
170:  _meta={"error": f"Unknown resource: {uri_str}"}                   # REFLECTED to the client
```

**How the fourth was nearly missed, and the method that found it.** The first search was
`logger\..*uri` — a pattern that requires both tokens on the *same line*, encoding an assumption about
**formatting** rather than about **behaviour**. Site 140 is a multi-line `logger.debug`, so it did not
match; site 170 is not a logger call at all, so no logger-shaped pattern could ever have matched it.
The fix was not a wider regex but a **different method**: enumerate every use of `uri_str`, not every
line matching a guessed pattern. *Eleventh instance of an unstated scan bound in this project, and the
second in one day.*

Line 137's `if uri_str == WIDGET_URI` keeps the raw value deliberately — that is routing, not hygiene.

`uri_str` is `str(req.params.uri)` — **client-controlled**. A `resources/read` carrying a `mailto:`, `data:`
or credential-bearing URI is written verbatim to production logs.

**A PII-leak class explicitly closed in the source is open in the Claude tree**, in a file whose header
asserts it exists only for config. Two aggravating facts: **DEBUG logging is enabled in production**, so
line 135 genuinely emits; and PG-Claude's tool descriptions and `_meta` are directory-submission surface.

*Not fixed. Fix is a port of one function plus two call sites — but it is a code change on a live service
and belongs in an increment.*

### F2 — A22, now fully enumerated

Already known, deployed and recorded. Listed because **this sweep rediscovered it independently**, which is
the method validating itself. The full drop list against `priority_guardian/server.py`:

`_escape_error_description` · `_BodyTooLargeError` (+ `__init__`) ·
`BearerAuthMiddleware._send_401` / `._send_403` / `._send_413` / `._create_replay_receive`

`_send_403` is the deferred `insufficient_scope` limb. `_send_413` + `_BodyTooLargeError` are the body-size
guard. `_create_replay_receive` is the replay that makes body-buffered scope enforcement safe — **so the
mechanism the deferral called dangerous to design was already written, in the file this one claims to
mirror.**

---

## 4. Justified, but only one of them was written down

Correct divergences. Category 2 requires the reason to be *stated*; mostly it was not.

- **`_meta` shape** — `resources_dupl` and `tools_dupl` divergences in both trees are Claude's `_meta.ui`
  (`domain`, `csp`, `prefersBorder`) against ChatGPT's `openai/*`. Correct and necessary.
- **`embedded_widget_resource`** dropped in both Claude trees — a ChatGPT surface. Correct.
- **`reconcile_user` / `reconcile_user_via_backend`** dropped from PG-Claude. **Correct, and actively
  safer.** It reconciles JWT identity against `openai/subject` — the client-controlled identity-redirect
  concern already open as its own item. Claude never sends it. *A dropped symbol that is a good thing,
  which is why this taxonomy needs judgment and not just detection.*
- **`discovery_dupl` divergences** — issuer, scopes, endpoints. Config by intent, structural in form.
- **MindSort `wellknown_*`** — relocated to `discovery_dupl.py`, live and 200. Sweep false positive.
- **`_escape_error_description`** dropped from PG-Claude — **benign today**: all five of its
  `error_description` values are static byte literals, so nothing needs escaping. *Becomes F1-shaped the
  moment anyone makes one dynamic.*

---

## 5. Loose ends

- **Three files name no resolvable source** and were not compared:
  `priority_guardian_claude/response_adapter_dupl.py`, `*/tools_list_dupl.py` (both trees),
  `mindsort_claude/response_adapter_dupl.py`. **Unswept, not clean.**
- **`_extract_origin`** is dropped in MindSort's `resources_dupl.py` and present-but-dead in PG-Claude's
  (computed into `WIDGET_DOMAIN`, never read; its docstring asserts a "pure origin without path" claim that
  contradicts the X2 finding). Already carried; the sweep confirms the two trees disagree about it.
- **`mindsort_claude/mcp_auth_dupl.py` delegates** via global rebinding of `clarity.mcp_auth` and carries an
  explicit `WARNING — PROCESS-WIDE SIDE EFFECT` header. Documented, and the only file whose header is
  candid about what it does.

## 6. What this sweep did not check

Module-level wiring — middleware **order**, route registration, import-time constants. **A22 was a symbol
defect, but middleware order is the same failure class and this sweep would not see it.**

---

## F2 closed — increment P1, deployed `e82bbf5` (2026-08-10)

The `_dupl` sweep listed six symbols dropped from `BearerAuthMiddleware`. A22a restored the 401 half;
P1 restored the rest that applies. Deploy `dep-d9st063l550s73eit8g0`, live 13:21:28Z.

- `_send_413` · `_BodyTooLargeError` · `_create_replay_receive` — **restored**, adapted: the body is
  buffered for the size guard only, not for scope parsing.
- `_send_401` — **already present** as `_send_challenge` from A22a.
- `_send_403` — **NOT APPLICABLE**, not deferred. PG has one scope, `pg.access`, required by every
  protected tool, so no valid-token-insufficient-scope state exists. Activation trigger recorded.
- `_escape_error_description` — **deliberately not ported**; PG-Claude builds no header containing
  caller-influenced text. Trigger recorded at `WWW_AUTHENTICATE_VALUE` itself.

### Three defects the sweep did not find, all caught in review before deploy

1. **A THIRD header decoder, outermost.** `RequestLoggingMiddleware` decoded every header with strict
   utf-8, so `b"Bearer caf\xe9"` became a 500 **before any auth code ran** — from an unauthenticated
   client, on any header. P1-a had replaced two `Authorization` decoders and both sat *below* it.
   Now `errors="replace"`. **Verified on the wire post-deploy: 401, where it was a 500.**
2. **Memory tracked chunk count, not bytes.** A 1 MiB body in 1-byte chunks cost **89 MiB**, not the
   2.01 MiB reported — six concurrent such requests exhaust a 512 MiB Starter. `bytearray.extend`.
3. **Origin comparison was case-sensitive** beside the case-insensitive selector P1-a had just built.

### Memory figures — corrected again, and this is the honest full-stack number

| | peak | retained |
|---|---|---|
| Before (list of bytes), 1-byte chunks | 89.06 MiB | 9.06 MiB |
| After (`bytearray`), 1-byte chunks | 2.07 MiB | 1.00 MiB |
| **After, FULL STACK incl. Starlette `request.body()`** | **~3 MiB** | **2.00 MiB** |

**The 2.07 MiB figure was for this middleware alone and understated the real cost.** FastMCP reads the
replayed body via Starlette's `request.body()` (`streamable_http.py:335`), which builds **a second
copy** — measured, `b is replayed` → `False`. So an in-flight 1 MiB request holds ~2 MiB, not 1 MiB.

*Codex raised this and named `RequestBodyLimitMiddleware` as the cause. **That class does not exist in
the installed `mcp==1.12.4`** — zero matches for `RequestBodyLimit`, `received_body`, `body_limit`. The
caveat was right in direction and wrong in mechanism; checking it turned up the real one. A correct
conclusion from a wrong premise still needs its own verification.*

### Codex re-review verdict

Three prior findings **verified fixed, not moved**. No new exploitable request-path defect. The replay
design was **validated against upstream source** rather than my SSE-shaped test: `sse-starlette`'s
disconnect watcher loops on `receive()` until `http.disconnect` (`sse/sse.py:198`, confirmed locally),
which is exactly why `_create_replay_receive` must forward after replay. That was the increment's
largest unverified risk.

**Carried forward, both observability rather than correctness:** `Origin` rejection and
`RequestLogging` log without a correlation id (they run *before* `BearerAuth`, which mints it), and
dispatch still mints its own — so middleware and tool records remain unjoinable. Threading one id
across that boundary is a change to the request-context contract and needs its own increment.

**Still unproven:** the admit half. Every production probe so far is a *reject* probe. Buffering,
replay and the 413 path all require a valid token, so only a real tool call through the widget
exercises them end to end.

### P1 on-host acceptance — 2026-08-10 14:32Z. COMPLETE.

Connector disconnected and reconnected, one MCP tool call on production against
`e82bbf5` / `dep-d9st063l550s73eit8g0`.

**THE REPLAY PATH IS PROVEN, and it was the increment's one genuinely open risk.**

`14:32:28.873` — `tool.dispatch.received argument_keys=[] tool_name=get_priorities`,
then `CallToolRequest` processed and `tool.get_priorities.success priority_count=3
google_connected=True calendar_available=True total_hours=38.75`.

For that line to exist the JSON-RPC body had to survive **`bytearray` buffer →
`bytes()` → `_create_replay_receive` → Starlette `request.body()` → FastMCP parse**.
A tool name and arguments came out the far end. Broken replay fails closed for
*every* request; this disproves it against a **real FastMCP session**, not the
SSE-shaped unit test and not Codex's reading of upstream source. Both of those were
worth having and neither was this.

- **No 401 from `Claude-User`. No 413, 500 or 503 anywhere in the window.**
- `auth_ms=1.4` against `total_ms=1056.8` — auth is **0.1%** of the call. Request-level
  `1073.04 ms` vs tool `1056.8 ms` leaves **~16 ms for the entire middleware stack
  including buffering**. No latency finding.
- Every JWKS lookup a `jwks.cache.hit`; no fetch on the request path.
- `scope.enforcement.success required=['pg.access']` — dispatch-level scope
  enforcement still running, so keeping double validation still buys what it was
  kept for.

#### Two things these logs do NOT show, recorded because the distinction is the shape of the bug that started this

1. **The correlation-ID fix is NOT demonstrated.** The middleware logs more than once
   only on a 413 or a disconnect, and neither occurred. What is visible is the
   *documented limitation* behaving as documented: middleware validation under
   `cca1b3f3…`, then `correlation.generated_fallback` minting `4c110b12…` for
   dispatch. **A single `jwt.validation.success` proves the id was PASSED, not that
   it is SHARED.** That is the same shape as the original finding — a log line that
   proves one thing being read as proving a related one.
2. **A22-2's discovery path was NOT re-exercised.** OAuth did not appear because
   reconnect reused the existing token — correct behaviour, but it means no
   unauthenticated probe → 401 → DCR sequence ran. That was verified 2026-08-09 with
   a full delete-and-re-add; today does not re-confirm it, and "reconnected
   successfully" must not stand in for it.

#### P1 status: COMPLETE

Both halves verified in production — reject probes at 13:23Z, admit path at 14:32Z.

**Not verified in production, correctly bounded:** the **413 path itself**, because a
>1 MiB body requires a valid token that cannot be minted from here. Covered by three
unit tests plus negative control B, with the ordering confirmed on the wire
(unauthenticated 3 MB → **401, not 413**, so auth runs before the body is read).

**Carried forward:** the correlation-id boundary above and below this middleware ·
`Origin` rejection and `RequestLogging` logging without an id · the OpenAI back-port
of the `bytearray` fix · the `dupl_sweep` module-level blind spot (middleware order
and route registration are still not compared — A22a's own failure class).

### P1 — last unasserted claim closed, and A22-2 split into its two halves (2026-08-10)

**The correlation-id fix is now ASSERTED, not correct-by-reading.** The claim that
matters is not "one id was passed" but "**one request emitting TWO records emits the
SAME id in both**". Production cannot show it — the middleware logs twice only on a
413 or a mid-body disconnect, neither of which occurs on a healthy request — but both
are trivially producible in the ASGI harness. Two tests now capture structlog output
across *both* modules and assert `jwt.validation.success` and
`auth.middleware.rejected` / `auth.middleware.client_disconnected` carry an identical
id. **Negative control I:** restoring the second `uuid4()` fails all three
correlation-id tests.

#### A22-2 — recorded as TWO HALVES, because only one of them is automatable

Neither "verified" nor "not re-confirmed" is accurate on its own.

**Wire half — re-run 2026-08-10 14:38Z, PASSES. Re-runnable any time, no client needed.**

| Step | Result |
|---|---|
| unauthenticated `POST /mcp` | **401**, `Cache-Control: no-store`, body `"Bearer token required"` |
| `WWW-Authenticate` | `Bearer resource_metadata="https://mcp.priority-guard.com/.well-known/oauth-protected-resource/mcp", scope="pg.access"` |
| the pointer that challenge names | **200** → `authorization_servers: ["https://www.priority-guard.com"]`, `scopes_supported: ["pg.access"]` |
| that AS's `oauth-authorization-server` | **200** |
| that AS's `openid-configuration` | **200** |

The chain a client must follow is intact end to end, from the challenge to the AS
metadata, with every hop resolved rather than assumed.

**Client half — NOT automatable, last produced 2026-08-09.** Claude receiving the
401, following the pointer, performing DCR and completing consent requires Claude's
own client. It is produced by **fully deleting and re-adding the connector**, which
was done 2026-08-09. The 2026-08-10 reconnect did **not** re-run it, because the
existing token was reused and no OAuth prompt appeared — correct behaviour, and
precisely why "reconnected successfully" cannot stand in for it.

**Re-run the client half at submission time**, since a fresh reviewer takes exactly
that path with no cached token.

---

## `azp` — reported as a validator divergence, STRUCK 2026-08-22. Not a divergence.

**azp handling re-verified 2026-08-22: PG and shared validators both extract/log
only; neither validates `azp`; no divergence.**

That sentence is the finding. It is dated because it is a point-in-time read, and
bounded to `azp` on purpose — it says exactly what was checked and claims nothing
about the rest of the two validators.

### What was checked

`validate_jwt` Step 5 in both:

| | `mcp_server/clarity/mcp_auth.py` (shared) | `mcp_server/priority_guardian_claude/mcp_auth_dupl.py` (PG-local) |
|---|---|---|
| reads `azp` | `payload.get("azp")` | `payload.get("azp")` |
| validates it | no | no |
| logs it | yes | yes |
| cites `remove_azp.md` | yes | yes |

Behaviourally identical for `azp`: extract, log, do not validate — same DCR
rationale in both (DCR assigns a different `client_id` per user, so `azp` is not a
stable identity to bind against).

### Scope of the claim, stated precisely

The two files were **not** diffed line-for-line, and their surrounding comment prose
is **not** identical — shared's audience comment carries the long §11 correction,
PG's is shorter and says "legacy fallback." So the defensible statement is
"behaviourally identical for `azp` handling," **not** "byte-identical." An earlier
draft of this entry said byte-identical; that was an unverified claim and is
withdrawn.

### Why the phantom appeared, recorded so it does not regenerate

The divergence was inferred from the two **docstrings**, not the two bodies. PG's
docstring mentions extracting `azp`; shared's describes it as not-validated. Read
side by side those sound like different behaviour. They are not — they are two
descriptions of the same code, written at different times, emphasising different
halves of "extract but don't validate."

Any future validator-diff will hit the same trap and re-report the same
non-divergence. This entry exists so the next reader can strike it in seconds
instead of re-deriving it. **No increment. No code change. Closed.**

---

## TICKET 2026-08-22 — the shim meta-tests are disarmed. Diagnosis is sharper than "vacuous."

**Captured, not scheduled.** Repair before the next shim/auth change, because these
are the guards that would catch a `REBOUND_GLOBALS` drift and they currently cannot.

Three tests in `tests/unit/mcp_claude_mindsort/test_scaffold.py` guard the
`mcp_auth_dupl` shim. Measured 2026-08-22, and **all three were already in this state
at `ccf3596`** — confirmed by running them in a detached worktree at that commit, so
they are baseline-red, not fallout from the A22 work:

| Test | State | Mechanism |
|---|---|---|
| `test_fixture_rebound_list_matches_shim` | FAIL | `ast.literal_eval(result.stdout)` → `SyntaxError` |
| `test_shim_assignments_match_rebound_globals` | FAIL | same |
| `test_fixture_restores_to_true_originals` | FAIL in full run, SKIP in isolation | its own non-vacuity guard (`test_scaffold.py:1447`) |

### The actual cause, which was NOT what the earlier "vacuous `ast.parse`" note said

The first two shell out to a fresh interpreter and `ast.literal_eval()` its stdout.
That stdout is **no longer only the repr** — config import now emits a structlog line
first:

```
2026-08-22 ... [info     ] clarity.config.oauth_resolved  env=dev jwks_url=... mcp_resource_url=...
```

`literal_eval` parses that as source and dies on `2026-08-22` — *"leading zeros in
decimal integer literals are not permitted"*. So the guard is not weak, it is
**inoperative**: it fails identically whether the shim is correct or corrupt, which
means it can never report the drift it exists to detect. A test that fails
unconditionally is as blind as one that passes unconditionally.

The third is a different failure mode and the earlier note conflated them: it has a
deliberate non-vacuity guard that skips when `mcp_auth_dupl` was never imported. That
guard is working as designed — it is honest about proving nothing. It only *fails*
in the full-module run, which is a separate question from the stdout pollution and
should be diagnosed on its own rather than assumed to share a cause.

### Repair shape (not approved, not drafted)

Stop parsing stdout. Either have the subprocess write the repr to a file the parent
reads, or emit it on a dedicated delimiter and slice to it, or silence logging in the
child (`ENV`/log-level) — whichever the repo's existing subprocess-test convention
already uses; `test_discovery.py` `TestConfigGuards` is the established pattern and
asserts on *stderr substrings* rather than parsing stdout as a literal, which is
plausibly the technique these three should have used.

**Before the next shim or auth change**, because until then any `REBOUND_GLOBALS`
drift ships unguarded. The A22 work added `extract_bearer_token` and `validate_jwt`
to the shim's re-export block (correctly NOT to `REBOUND_GLOBALS`, which is config
values only) — exactly the class of edit these guards exist to police, and they were
blind to it.
