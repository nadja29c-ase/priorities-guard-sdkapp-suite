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

### F1 — `_sanitize_uri_for_logging` dropped; PG-Claude logs client-controlled URIs raw

**Unjustified divergence. Privacy. Same family as P1D.**

`priority_guardian/handlers/resources.py` defines `_sanitize_uri_for_logging` and logs only `safe_uri`. Its
docstring records three increments of hardening:

> *inc_99: Defensive hygiene against pathological URIs from authenticated clients. inc_100: Strip
> query/fragment for all URIs, strip userinfo from netloc. inc_101: Switched from blocklist to allowlist.
> Only http/https/ui/file pass through with components; all other schemes (mailto:, blob:, data:,
> javascript:, etc.) are redacted. **Closes the class of PII leaks.***

`priority_guardian_claude/handlers/resources_dupl.py` **has no such function** and logs the raw value at two
sites:

```python
133:  logger.info("resource.read.called", uri=uri_str)
135:  logger.debug("resource.read.requested", uri=uri_str, widget_version=WIDGET_VERSION)
```

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
