# Supersede older widget instances — instance supersession

**Source:** `https://claude.com/docs/connectors/building/mcp-apps/instance-supersession`
**Fetched:** 2026-08-04 — direct fetch.
**Raw source committed:** `sources_raw/instance-supersession.raw.md` (245 lines, HTTP 200, 14,291 bytes).
**Feeds:** compliance master §4M. The master is **not** yet rewritten against this.

**Method:** read for obligations, not keywords — sweeping `<Note>`/`<Tip>` blocks, conditionals,
cross-references and prose attached to numbers. That correction came out of the `authentication`
round 2, where a keyword sweep missed six items including a failing MUST.

---

## Part 1 — Requirements: **none**

**This page contains no directory-compliance obligation.** Not one sentence on it gates
submission. The language is uniformly optional, and that is the single most important fact about
the page:

| Raw line | Language |
|---|---|
| 11 | *"only the most recent instance **should** remain interactive"* |
| 11 | *"**You can use** `BroadcastChannel` to make earlier instances disable themselves"* |
| 173 | *"A production widget **should also** handle the following"* |
| 240 | *"The `App` class handles the full request surface and is **recommended** for production"* |

Supersession is a **pattern offered** for stateful single-instance widgets. It is not a gate.

### Conditional constraints — binding only *if* the pattern is implemented

| # | Constraint | Why | Raw |
|---|---|---|---|
| S1 | Election key **must be server-minted** (`createdAt` + `seq`), never client `Date.now()` | Reopened conversations lazy-mount widget cells as they scroll into view, so an **older** widget can mount **after** a newer one and would win a client-timestamp election | 58–60 |
| S2 | Comparison order is `createdAt` → tie-break `seq` → tie-break **instance ID** | Determinism. §4M says only "compare keys" | 101, 107–112 |
| S3 | **Ignore inbound messages until your own key is finalized** (`keyFinalized`) | Otherwise you reply with an undefined key | 122 |
| S4 | Guard **every** `updateModelContext` **and `sendMessage`** call on `!superseded` | *"The election only matters if superseded instances actually stop talking to Claude"* | 136–138 |
| S5 | With a **fixed `_meta.ui.domain`**, the origin spans conversations — mint your own scope key **server-side** and append it to the channel name | *"Neither `hostContext` nor the tool-call arguments include a Claude-provided conversation ID"* | 177–180 |
| S6 | If using the timeout fallback: tag `keySource` and **refuse to compare client against server values** | A server `createdAt` from hours ago always loses to a fresh client timestamp | 215–229 |
| S7 | If the server key arrives **after** the timeout: adopt it, **recompute** `superseded` against peers already heard from, and **re-announce** | *"The recomputed result may flip the instance back to live"* | 213 |
| S8 | Announce is a **two-message handshake** — `hello` broadcast, and a `born` reply to any `hello` heard | Late-mounting siblings otherwise never learn about existing peers | 119–133 |

**Server-side, if implemented:** a per-process counter is demo-only; *"a production server should
derive the key from something durable, such as a database row ID or a version number on the
underlying record"* (raw 27). §4M already records this correctly.

---

## Part 2 — Diff against master §4M

§4M is unusually good on this page — the localStorage/iOS-rehydration caching rules, the durable
`seq` derivation, the 1-second race and the `keySource` caveat are all present and accurate.
The defects are one inflation, one un-applied rule, and four omissions.

### 1. ❌ A recommendation was promoted to a requirement

| | |
|---|---|
| **§4M `:576`** | *"The App class handles the full request surface and is **required** for production"* |
| **§4M `:572` heading** | *"SDK App class **requirement**:"* |
| **Source raw 240** | *"The `App` class handles the full request surface and is **recommended** for production."* |

**Harmless in effect — PG uses `useApp()` — and not harmless as a pattern.** This is the **third**
instance of the same failure today, after the 500px "hard limit" and the fabricated "recommended"
qualifier on the 4–5 data-point constraint. Two inflated a recommendation into a MUST; this one
does too.

**The bias has a direction.** It is not random error: soft language gets hardened, hard language
never gets softened. That direction is what turns into over-constrained increments and wasted
work, so it is recorded here as a bias rather than three separate corrections.

### 2. ⚠️ PG has a fixed `ui.domain`, and §4M never applies its own scope rule to PG

§4M states the rule correctly in the abstract: *"With fixed ui.domain, scope widens — include a
server-minted conversation scope key to prevent cross-conversation interference."*

It never says **PG is in that case.** `resources_dupl.py:75` defines
`WIDGET_APP_DOMAIN = f"{_hash}.claudemcpcontent.com"` and sets it on **all three** `_meta.ui`
blocks (`:90`, `:114`, `:148`). Per raw 180, that means *"the origin is shared across every
conversation and tab for your connector. A fixed channel name would let a widget in one
conversation supersede a widget in another."*

**Consequence if §4M is ever implemented as written: cross-conversation supersession is the
default outcome.** S5 is a **pre-condition** for PG, not a footnote.

### 3. ➕ Four implementation items absent from §4M

| Item | Raw | §4M |
|---|---|---|
| **Post-timeout adoption path** — adopt a late server key, recompute against known peers, re-announce; *"may flip the instance back to live"* | 213 | Fallback section stops at the `keySource` caveat |
| **S3 — the `keyFinalized` guard** | 122 | Absent |
| **S8 — the `hello`/`born` two-message handshake** | 119–133 | Says "broadcasts on BroadcastChannel"; no reply protocol |
| **`sendMessage` in the guard** | 138 | Guard instruction names only model-context updates |

### 4. ➕ S2's instance-ID tie-break is missing

§4M says "older instances compare keys". The source specifies a three-level chain —
`createdAt`, then `seq`, then `String(instanceId)` — and the third level exists **for
determinism**, which is exactly the part that goes wrong silently.

### 5. ➕ The cross-reference to `cross-compatibility#domain-handling` (raw 17, 244)

The page twice points at *Cross-platform compatibility* for **how `_meta.ui.domain` is computed on
Claude**. That is an adjacent requirements surface, and it is directly load-bearing for PG given
gap 2. §4M does not cross-reference it. *(Found by the corrected method — cross-references were
one of the four shapes that defeated the keyword sweep.)*

---

## Part 3 — PG status: correct verdict, wrong scope

**§4M's verdict stands.** *"Not a submission blocker, known UX degradation, track
post-submission"* is right, and this page creates no obligation to be blocked by.

**But the stated risk is not PG's actual risk.**

**Verified across the whole of `App.tsx` (933 lines), re-run 2026-08-04 by two methods —
`grep -c` (matching lines) and `grep -o | wc -l` (occurrences) — which agree exactly:**

| Symbol | Occurrences | Lines |
|---|---|---|
| `updateModelContext` | **0** | **0** |
| `sendMessage` | **0** | **0** |
| `callServerTool` | 28 | 28 |
| `isBridgeStale` | 28 | 28 |

> **The identical 28/28 is real, not a copy-paste artifact** — it was challenged on exactly that
> suspicion, and the suspicion was reasonable. The cause is structural: **`isBridgeStale` guards
> `callServerTool`**, so **12 lines contain both symbols** —
> `if (isBridgeStale || !appRef.current?.callServerTool) throw new Error('Tool calls not available')`
> at `:266, :287, :309, :333, :353, :373, :393, :415, :435, :455, :475, :497`. Add 12 dependency-array
> entries, the `useState` at `:48`, and `:519`, `:521`, `:554` → 28. All 28 sit between `:48` and
> `:554`; the observation that it appears nowhere in the last 240 lines is correct and consistent.
>
> **This matters because the zeros are the load-bearing values** — the whole "S4 is inapplicable
> to PG" conclusion rests on them — and they were sitting next to a number under suspicion. Both
> methods now confirm them independently.

**Sharpening this artifact's own PG-risk finding:** `isBridgeStale` is not merely "a different
mechanism" — it **already gates every `callServerTool` site**, which is precisely the
data-mutation surface flagged below as PG's real exposure. What it does **not** do is instance
election: it answers *"is this bridge dead?"*, not *"is this the newest instance?"*, so it does
nothing to stop **several simultaneously-live** dashboards from each mutating. The gap is
narrower than "no protection" and real.

**PG never calls either API this page's guards protect.** S4 — the heart of the pattern — is
inapplicable to PG as written. The page's whole concern is *context pollution*: several live
instances each pushing model-context updates and injected messages into Claude's next turn.

**PG's exposure is different in kind.** Several live dashboards can each `callServerTool` to
**create and delete priorities** — a **data-mutation** concern. This page does not address it, and
no guard on it appears anywhere in the page. Recording it as an instance of supersession
mis-files it; it is a **PG-specific risk that sits outside this page** and should be tracked on
its own terms.

**Also unmentioned in §4M:** PG already has an `isBridgeStale` 3-second staleness detection (28
occurrences). It is a **different mechanism** answering a different question — bridge liveness,
not instance election — and §4M should not be read as though PG has nothing in this area.
