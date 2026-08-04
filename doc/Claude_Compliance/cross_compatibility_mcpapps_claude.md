# Building cross-platform MCP Apps — cross-compatibility

**Source:** `https://claude.com/docs/connectors/building/mcp-apps/cross-compatibility`
**Fetched:** 2026-08-04 — direct fetch.
**Raw source committed:** `sources_raw/cross-compatibility.raw.md` (39 lines, HTTP 200, 2,149 bytes).
**Feeds:** compliance master §4K. The master is **not** yet rewritten against this.

The shortest page in the set, which makes it the cheapest to round-2.

---

## Part 1 — Requirements: one

| # | Requirement | Language | Raw |
|---|---|---|---|
| X1 | For Claude, `Resource._meta.ui.domain` = `sha256(<full MCP server URL, including /mcp>)[:32] + ".claudemcpcontent.com"` | imperative: *"compute the value by running this command"* | 29–33 |

**Everything else on the page is descriptive or advisory.** `registerAppTool()` /
`registerAppResource()` *"automatically generate platform-specific metadata"*; `App.connect()`
without an explicit transport auto-detects the host. Both are **TypeScript SDK conveniences**.
PG's server is Python and constructs `mcp_types.Resource` directly — **fine, and no gap**: the
page describes a convenience, not an obligation.

### What the page does **not** say — the load-bearing omission

**It never states that `_meta.ui.domain` is required.** Verbatim (raw 27):

> The `Resource._meta.ui.domain` field **format and validation rules are determined by each host
> platform**. For example, hosts may use hash-based subdomains, URL-derived patterns, or other
> formats.

That is a **conditional**: *if* you set it, here is Claude's value. Nothing more.

**Method note:** the formula's own worked example was used to validate the extraction —
`https://example.com/mcp` → `c3d80a4ed901ee05b21755a88273b4a4`, recomputed locally and matching
the page **byte-for-byte**. So the formula below is verified, not transcribed.

---

## Part 2 — Diff against master §4K

### 1. ❌ §4K inflates `ui.domain` to mandatory — **and this one deleted an architectural option**

| | |
|---|---|
| **§4K `:490`** | *"Widget App Domain (`_meta.ui.domain`) — **mandatory** for MCP Apps"* |
| **§4K `:492`** | *"The `_meta.ui.domain` field is **required** on every `ui://` resource. **Without it the widget will not render.**"* |
| **This page** | Never says required. Format/validation are **host-determined** |

**The second claim is contradicted by a source already in this repo.**
`sources_raw/instance-supersession.raw.md:179`:

> **Without `ui.domain`** (the default), Claude derives the iframe origin from the conversation
> and connector, so the broadcast is scoped to a single conversation.

Widgets render **fine** without it; the host derives an origin. That is the **documented default**,
not a failure mode.

**Fifth hardening instance in one session — and the first with a design consequence.**

The previous page established that PG's **fixed** `ui.domain` is exactly what widens
`BroadcastChannel` scope **across conversations**, making **S5** (a server-minted per-conversation
scope key) a **pre-condition** if supersession is ever built.

**If `ui.domain` is optional, dropping it gives per-conversation scoping for free and deletes S5
entirely.** The false "mandatory" framing removed that option from consideration **without anyone
deciding against it.** That is the difference between this instance and the previous four: the
others produced wasted effort; this one silently foreclosed a design choice.

**The decision, with its reason — recorded so it stops being an inherited constraint:**

> **Keep `ui.domain`, because PG's widget runs its own OAuth flow** and therefore needs a **stable
> sandbox origin**. **Accepted cost:** cross-conversation `BroadcastChannel` scope. **Consequence:**
> S5 is a pre-condition if supersession is ever built.

**Verified in code:** `ConnectionStatus.tsx` calls `connect_google_calendar` (`:52`), extracts
`connect_url` (`:59`), then `await app.openLink({ url: connectUrl })` (`:63`) — a widget-initiated
Google Calendar OAuth round trip.

**Source for the rule:** the troubleshooting page — *"Setting `_meta.ui.domain` opts your app into
a stable sandbox origin, which you need if your app runs its own OAuth flow."*
⚠️ **Not yet in `sources_raw/`.** That quotation comes from Nadja's read, not a committed source.
Confirm when `troubleshooting` is pasted.

⚠️ **An earlier version of this section gave a weaker reason** — that a fixed domain keeps the
origin stable "for anything relying on `localStorage`". **That fails twice for PG.** The
supersession page's `localStorage` caching is keyed on `hostContext.toolInfo.id` and exists to
survive **remount within a conversation**, for which per-conversation origin stability is already
sufficient — cross-conversation stability buys nothing. And PG implements **neither** supersession
nor `localStorage` caching, so the argument does not reach PG even if it were sound.

**The correct reason had already been surfaced in the same session and was passed over.**
Substituting a weaker justification for a stronger one already in hand is its own failure mode,
distinct from the ones catalogued in `doc/README.md`: the answer was **in the conversation**, not
only in the tree.

### 2. ⚠️ Two different PG domain hashes live in the repo — both arithmetically right, one stale

Recomputed locally, all three:

| Hash | Derived from | Verdict |
|---|---|---|
| `c3d80a4ed901ee05b21755a88273b4a4` | `https://example.com/mcp` | the page's own example — **matches byte-for-byte**, validating the method |
| **`a7b31ccb44096357600a7460eb0a78e9`** | `https://mcp.priority-guard.com/mcp` | ✅ **CANONICAL.** Master §4K `:502` is **correct** |
| `e524d9efa639471cac7431657ac08f2c` | `https://priority-guardian-claude-mcp.onrender.com/mcp` | ❌ **STALE** — legacy Render URL |

**Neither doc did bad arithmetic. One names a superseded URL.** The stale hash lives in **two**
places, not one — the corollary applies before anyone points at the second:

- `remote_server_submission_guide.md:445`
- `structural_guideline_claude_vs_openai.md:388-389`

**Operationally PG is safe.** `resources_dupl.py:74` computes
`hashlib.sha256(MCP_RESOURCE_URL.encode()).hexdigest()[:32]` **at import time**, so the served
value always matches whatever `MCP_RESOURCE_URL` is configured to. The risk is documentary: at
submission the domain must correspond to **the URL the reviewer enters**, and the repo currently
asserts two different answers.

**Rule going forward: record the computation, or record a hash together with the URL it derives
from. Never a bare hash.** A frozen hash is a claim with its premise deleted.

**And the URL must be exact.** Three trivially-confusable spellings of PG's own URL, recomputed:

| Hash | URL |
|---|---|
| `a7b31ccb44096357600a7460eb0a78e9` | `https://mcp.priority-guard.com/mcp` — **canonical** |
| `4c08ba210ef30c57e400ae94d8b49e97` | `https://mcp.priority-guard.com/mcp/` — trailing slash |
| `6a52566e8cef0070d2481bfab80f0c82` | `https://mcp.priority-guard.com` — bare origin |

They share **nothing**. There is **no way to spot the mistake by eye** — a wrong domain looks
exactly as plausible as a right one, which is why the troubleshooting page warns about the
trailing slash specifically. **Always recompute from the configured `MCP_RESOURCE_URL`; never
transcribe.**

### 3. ⚠️ Dead code carrying a rule that contradicts this page

`priority_guardian_claude/handlers/resources_dupl.py` defines `_extract_origin()` (`:26`) with:

> *"MCP Apps SDK **requires** `ui.domain` to be a pure origin without path.
> Example: `https://pg-mcp-claude.priority-guard.com` (not `…/mcp`)"*

and sets `WIDGET_DOMAIN = _extract_origin(MCP_SERVER_URL)` (`:42`). **That value is never used in
the Claude path** — all three `_meta.ui` blocks use `WIDGET_APP_DOMAIN`, the hash. So an unused
variable sits directly above the correct implementation, asserting the opposite rule to the next
reader. §4K records that a hash-vs-origin confusion once caused a `ui.domain` mismatch rendering
failure; **this is the artifact of that bug, still in the file.**

⚠️ **The fix is not "delete the docstring", and this is the part worth getting right.**
`WIDGET_DOMAIN` is **dead only in the Claude path**. It is **live on the ChatGPT surface** —
`priority_guardian/handlers/resources.py:150` and six sites in `clarity/handlers/resources.py`
use the **origin** form as `domain`.

**The docstring's actual error is the word "SDK".** It generalises a per-host rule into a
universal one, which is precisely what this page contradicts: *"format and validation rules are
determined by each host platform."* Both forms are correct — for different hosts.

*(`mindsort_claude/handlers/resources_dupl.py:82` already carries a note that PG has a dead
`_extract_origin`/`WIDGET_DOMAIN` pair, so this was spotted before and documented in a third file
rather than resolved in the second.)*

**Code fix NOT applied** — the decision is Nadja's.

### 4. ⚠️ Stale reference URL, two places

Both cite `docs.anthropic.com/en/docs/claude-ai-connectors/…`; the live page is
`claude.com/docs/connectors/building/mcp-apps/cross-compatibility`.

- `remote_server_submission_guide.md:455` — doc, fixable here
- `resources_dupl.py:73` — **code comment, NOT changed** (RULE 0a)

---

## Part 3 — Correct and unchanged in §4K

- The formula itself, including the **"full URL including `/mcp`, not the origin"** warning
- The worked example — verified by local recomputation
- §4K's cross-platform note on `App.connect()` auto-detection and the two `register*` helpers
- PG's canonical computed domain `a7b31ccb…` and its "confirmed working ✅" status
