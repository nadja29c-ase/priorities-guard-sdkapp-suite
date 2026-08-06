# Increment Claude-B — Host context lifecycle, connection state, and result correctness (rev 6)

**Row coverage:** M3 (safe areas) · plus four pre-existing defects with no canonical row
**Bundle version:** **v5.** v4 is the currently deployed, tested artifact.

**Supersedes rev 5.** Four amendments, all authorised before implementation began and written down
here rather than left in a transcript:

1. **§3's deploy premise was stale.** It said `srv-d6vbrt9r0fns73c6n080` is "autoDeploy off, manual
   trigger". autoDeploy was switched **on** 2026-08-06 12:31 — which is how v4 reached production and
   why `5aeb56c` self-deployed. With it on, **pushing v5 deploys v5** and §3's before-deploy record has
   no window to exist in. **Resolution: autoDeploy is switched OFF for B's duration** (see §1).
2. **§7 cited a "±2% threshold established in Claude-M20". No such threshold exists** — M20 said "use a
   documented threshold *if one exists*; otherwise state a fallback", and Claude-A stated ">2×" as its
   fallback precisely because none was documented. ±2% now binds as **newly established by B**, with
   justification (§7).
3. **§5.5 contained two incompatible readings.** Resolution: **build the origin tracking.** The table
   is the target; the escape hatch covers a state that proves unreachable, not declining to build the
   capability (§5.5, §2).
4. **§8's unnatural states are reached by design change, not test hooks** — which is itself an argument
   for amendment 3 (§8).

---

## 1. Precondition

**Increment A completed successfully. Do not begin B until all of the following hold:**

- The Claude widget resolves exactly `@modelcontextprotocol/ext-apps@1.7.5`
- v4 passed its build, provenance and supply-chain gates
- **A1–A5 passed, including all required on-host acceptance for A1, A2, A3 and A5** — notably
  **A2: runtime theme switching verified in Claude.ai, inline and fullscreen**
- **No open A regression**

A3's font listener is **accepted as not runtime-verified**, not open: a theme toggle produces no
observable font change, so it was never exercised. This does not block B.

**Status 2026-08-06: every item above holds.** ext-apps resolves exactly `1.7.5`; v4 passed its build,
provenance and supply-chain gates and reproduced byte-for-byte; A1–A5 all passed on host, A2 included,
with M1 moved to VERIFIED; no A regression is open.

⚠️ **ONE ADDITIONAL PRECONDITION, added rev 6 — `autoDeploy` must be OFF on
`srv-d6vbrt9r0fns73c6n080` before implementation begins.** It was switched on at 2026-08-06 12:31, and
while it is on **a push deploys immediately**, which destroys §3's before-deploy rollback window — the
setting, not discipline, is what enforces the gate. This is Nadja's action (§0.1(c): read-only on
Render). **Verify it is off before starting; if it is on, stop and report rather than pushing.**

B is implemented against the 1.7.5 runtime. **Do not add compatibility paths for 1.2.2, and do not use
the `on*` setter as a subscription mechanism** — the additive `addEventListener` /
`removeEventListener` API is the target.

---

## 2. Scope

**Code**
- `widget-react/src/App.tsx`
- `widget-react/src/main.css` — **only** styling required by §5.5's stale state and §5.4's error states
- `widget-react/src/i18n.ts` — **only** the loading, timeout, connection-error, malformed-response and
  stale-chart strings required by §5.3–§5.5, **in both locales**
- `widget-react/src/types.ts` — **only if** new state shape is genuinely required; justify in the report

**Build and version**
- The canonical `WIDGET_VERSION` declaration and `WIDGET_URI`
- The generated Claude widget bundle
- Only those resource metadata references requiring update because of the version change

**Documentation**
- `doc/Claude_Compliance/COMPLIANCE_AUDIT_RECORD.md` — **PG's M3 status and evidence only**

`doc/OPERATIONS_PREDEPLOY.md` is **read, not edited**. If v5 requires no operational-document change,
**say so explicitly in the report.**

**Alternative to the code scope above:** if every string and style §5 needs already exists, **prove it**
— name the existing keys and classes reused — and touch neither file. Do not ship an untranslated or
unstyled stale marker to stay inside scope.

**Do not alter M3's requirement text or level** in `CLAUDE_COMPLIANCE_REQUIREMENTS_CANONICAL.md`. Only
PG's status moves.

**Out of scope:** dependency versions · `useHostStyles` and how it is called · any other widget
component · the fullscreen `max-width` reconciliation · badge colours · the loading skeleton's geometry.

Adjacent issues found during implementation are reported, not fixed.

---

## 3. Bundle version identity and rollback

- Increment A → **v4**, deployed and verified · Increment B → **v5**

**Reusing a version across different bytes is prohibited.**

**v5 replaces a tested artifact.** Before deploying, record: v4's commit · v4's resource URI · the
Render deployment identifier on **`srv-d6vbrt9r0fns73c6n080`** (`priority-guardian-claude-mcp`).
Confirm v4's bundle is restorable **as bytes**, not regenerated by an install that may resolve
differently.

⚠️ **Corrected rev 6 — this section previously asserted "autoDeploy off, manual trigger".** That was
true when rev 5 was written and is not true now: autoDeploy was switched **on** at 2026-08-06 12:31, and
`5aeb56c` deployed itself on push. **Verify the setting at the time you deploy; do not trust this
sentence or any table.** The durable rule is in `doc/OPERATIONS_PREDEPLOY.md`: settings differ per
service *and change*, so the deploy log is the truth and a push is never evidence of a deploy.

**v4's rollback record, already captured under Claude-A §8 and reusable here:** deploy
`dep-d9q7seeq1p3s73f34g5g`, commit `785dd1d`, resource URI `ui://pg-claude/dashboard-v4.html`, bundle
593,943 bytes / `6f97b93c9e9d8c03648ce9f3a41734581ac4895044f9f0299481b96a88690529`, byte-identical
across `fd9d6cb`, `785dd1d` and `5aeb56c`, restorable from git as bytes and an ancestor of HEAD.
**Re-verify it holds before deploying v5 rather than copying it forward.**

**Roll back if any of these regress:** widget initialisation · **runtime theme switching** · any tool
call through the widget bridge · safe-area layout · result-state routing. After rollback, verify the
restored v4 custom connector renders and tool calls work.

---

## 4. What is wrong — post-A state

Five defects, all pre-existing, none introduced by A or M20. They share a cause: **each fails silently.**

### ⚠️ The structural cause, added rev 6 during implementation — read before B3

**In this widget, state is set far from where it is read, behind a long chain of early returns in
render.** `applyHostContext` → `hostFullscreen` → `isMobileHostFullscreen` → padding is four hops.
`connectionFailure` → `isBridgeStale` → a branch that sat **70 lines below** the one returning first.

That is a characteristic of the file, not a coincidence, and it predicts where the next defect will be.
**Fixing the state is about half the work; the other half is proving the consumer can be reached.**

It has already bitten three times in this increment, and the static acceptance passed every time:

| State corrected | What made the correction unobservable |
|---|---|
| `platform` (B1) | `hostFullscreen` could never be `true` — `setHostFullscreen(true)` existed nowhere |
| `hostFullscreen` (B1) | — fixed; it in turn unlocked a `FullscreenHeader` branch that had never rendered |
| `connectionFailure` (B2) | the loading branch returned **before** the terminal branch, so it was unreachable in exactly the case it exists for |

**B4 is the highest-risk remaining case, because B4's defect *is* a branch-order defect** — §4 states
it plainly: *"the chart branch returns before the branches that render the error banner."* Adding error
and stale-marker state without first establishing where the chart branch sits in the return chain would
repeat the pattern in the one place where the pattern is the thing being fixed. **B3 and B5 carry the
same exposure, milder:** B3's error state must survive to a branch that renders it, and B5's empty-chart
path must be reached before the fall-through it currently loses to.

### B1 — Host context is read before it exists, and never re-read

**Historical cause (pre-A):** two failures compounded. `useApp` invokes `onAppCreated` *before*
`await connect()`, and `_hostContext` is assigned *inside* `connect()` — the SDK documents this:
*"Returns undefined if called before connection is established."* Separately, on 1.2.2 `useHostStyles`
overwrote PG's `onhostcontextchanged` handler. Both call sites for `setPlatform`, `setSafeArea*` and
`setDisplayMode` were therefore dead.

**Current state (post-A):** A established that **the SDK's own style listeners coexist under 1.7.5**
and the additive listener API is available. **A2 proved the SDK's style-variable listener is no longer
overwritten and runtime theme switching works. It did not prove PG's own `onhostcontextchanged`
handler is correctly registered, fires, or updates state.** That remains part of B1's acceptance and
**must not be assumed from A2.**

**The premature initial read is still broken**, and is unaffected by A.

**What B fixes:** the read timing, and the absence of a subscription lifecycle.

**Why the initial read is not merely a convenience:** if `displayMode: "fullscreen"` or
`platform: "mobile"` arrives **only** in the initialize response and no host-context-changed
notification follows, the initial read is the **sole delivery path** for that state.

**M3 correction:** the canonical file records insets as "applied only in mobile fullscreen." With
`platform` never set, `isMobileHostFullscreen` is permanently false and **insets are never applied at
all.** Correct PG's status in the audit record — not the requirement.

Why it survived: three of `platform`'s four consumers are no-ops by construction — a 560px cap never
binds below 560px, and the gap and margin differences are cosmetic.

### B2 — A hung or failed connection leaves the widget loading forever

The stale-bridge timer tests whether the app object exists. That object is assigned in `onAppCreated`,
**before** connection is attempted. If `connect()` hangs or fails, the object exists, the timer
concludes the bridge is fine, and the loading skeleton renders indefinitely.

`useApp` returns `{ app, isConnected, error }`. PG destructures only `app`.

### B3 — A first tool result without a usable payload also loads forever

The result handler initialises only inside its data guard. Three distinct cases exit without setting a
load error **and** without clearing the loading state: an **MCP error result**, **empty structured
content**, and **structured content lacking the expected payload**.

### B4 — An error after a chart has rendered is never shown

The catch path sets the error state but does not clear the previously rendered data, and the chart
branch returns before the branches that render the error banner. The user keeps seeing a chart with no
indication anything failed.

### B5 — Empty chart results reach the wrong empty state

The chart branch is entered only when the payload has slices **and** the list is non-empty. An empty
result falls through, is treated as dashboard data, and renders the "no priorities" empty state. The
chart component's own "no time data" state is unreachable.

---

## 5. What must be true afterwards

### 5.1 — Host context lifecycle

A single read is **not sufficient**. Host-context changes are **partial updates**. Required:

1. **Wait for the connection to be established** before reading context.
2. **Read the initial context** and set `platform`, `displayMode` and all four safe-area insets from it.
3. **Subscribe** to subsequent changes using the additive `addEventListener` API.
4. **Merge partial updates into current state — never replace.**
5. **Remove the listener on cleanup.**

**Do not reimplement or work around A's listener fix.**

### 5.2 — Insets

All four — `top`, `right`, `bottom`, `left`. `.left` and `.right` are currently never read anywhere.
**Existing padding remains a floor:** take the larger of inset and current padding, never reduce.

### 5.3 — Connection failure has a defined terminal state

*"Never completes"* is not an acceptance criterion. Inspect the existing stale timer and:

- **Preserve its documented duration, or state and justify any change.**
- **Distinguish a timeout from an explicit SDK error.**
- **Clear the timer on success, on failure, and on unmount.**

### 5.4 — Result states, per error class

- **A valid MCP or tool error** surfaces the safe message the server supplied — meaning **an existing,
  intentionally user-facing error string**. Not exception text, not validation internals, not raw
  payload data.
- **A malformed or unusable success payload** surfaces a **generic localized load error**.
- **Neither remains in the loading state.**
- **Internal payload details are never exposed.**

### 5.5 — Stale chart — the marker tracks the operation that failed

**Retain previously rendered chart data when a later operation fails.**

**Mark the chart stale only when the failed operation was intended to refresh or replace that chart
data.** Errors from unrelated operations must remain **visible** but must **not** change the chart's
freshness state. **A subsequent successful chart result clears the stale marker.**

Three cases:

| What failed | Chart | Marker | Error |
|---|---|---|---|
| Chart or report refresh | retained | **marked stale** | shown |
| An unrelated tool or action | retained | **unchanged** | shown separately |
| — then a successful chart result | replaced | **cleared** | cleared |

⚠️ **AMENDED rev 6 — BUILD THE ORIGIN TRACKING.** Rev 5 carried two incompatible readings of the
paragraph below and did not notice. The table above **is the target**, and reaching all three of its
outcomes *requires* knowing which operation failed. It is confirmed that today's state cannot:
`loadError` is `useState<string | null>` at `App.tsx:29` — a bare message with no origin.

**That is the pre-state B fixes, not an excuse to skip it.** §2 permits `types.ts` "only if new state
shape is genuinely required" — **this is that case, and it is expected, not exceptional.** Minimal
shape: the message plus which operation produced it. **Not an error taxonomy** — just enough to answer
*was this a chart refresh?* Justify the final shape in the report.

**The clause below survives as a RUNTIME rule**, for an error whose origin genuinely is not known at
the moment it is handled — not as permission to omit the capability:

**If the current error state cannot distinguish which operation failed, report that as a finding.** Do
not fall back to marking everything stale. **Default to not marking when the origin is unknown** — an
unlabelled correct chart is better than a falsely labelled one. A widget that mislabels data freshness
is making a factually false claim, which is worse than showing an error plainly.

"Visibly stale" means, at minimum: a **localized** label visible while the chart is displayed · **not
conveyed by colour alone** · styled with **host tokens** · **cleared** on a subsequent successful chart
result.

### 5.6 — Empty chart

An empty chart result reaches the chart's own empty state.

---

## 6. Constraints

- **Host tokens throughout**, with fallbacks. No new bare hex.
- **No new user-facing string without i18n**, in both locales.
- **Do not remove the `onAppCreated` block silently.** State what it now does.
- **The `platform` ternaries stay as written.** Once `platform` is populated they take the mobile leg
  **for the first time ever**. Treat those branches as untested.
- **The loading skeleton stays platform-agnostic.**
- **Register handlers before `connect()`.**

---

## 7. Build and regression gates

- Type-check and production build pass.
- **No new runtime dependency; no change to `package.json`.**
- **Bundle size before and after, against a ±2% threshold — ESTABLISHED HERE, BY B.** ⚠️ Rev 5 cited
  this as "the ±2% threshold established in Claude-M20". **It was not.** M20 said to use a documented
  threshold *if one existed* and otherwise to state a fallback; Claude-A stated **">2×"** as its
  fallback because none was documented. The number appears nowhere in the repo but here. It binds as a
  **new** threshold, justified: B is a logic change to one file, so anything beyond ~2% means the build
  pulled in something unexpected. A's ">2×" was right for a twelve-release SDK upgrade and is
  meaningless for this. **A threshold with a borrowed provenance is worse than no threshold** — it
  survives review by looking pre-agreed.
- Production bundle contains no `window.openai` reference and no OpenAI-only import.
- **The bundle diff contains no test-only or state-forcing code** — see §8's provenance requirement.
- Changed set from `git status --porcelain` — byte deltas supplementary.
- Build provenance per Claude-A §7: Node, npm, build command, resolved SDK version, bundle hash, second
  clean build's hash, whether they match.

---

## 8. Acceptance — one block per defect

**No automated widget-runtime harness exists.** Assertions are manual and recorded. **Each block passes
or fails on its own.**

### ⚠️ REACHABILITY — added rev 6, applies to every *Static* assertion below

**Not just "the path exists" but "the path is reachable given the branch order above it."**

"`setPlatform` has a live call site" is a claim about the call site, not about whether anything
downstream reads it in a branch that can be reached. Three defects in this increment satisfied the
first and failed the second, and the static acceptance passed each time — see §4's structural note.

So for every *Static* item: state the branch order, and name what would have to be false above it for
the path to execute. A static assertion that does not do this **has not been met**, however true it is.

### Test-state provenance — applies to every on-host item below

Several acceptance states do not occur naturally: a blocked connection, a malformed result, a
post-chart failure, an empty weekly report. **For each, record how the state was produced**, and confirm:

- **No temporary production-only code was shipped.** The bundle diff is the evidence, not an assertion.
- **No validation or security guard was bypassed** to reach the state.
- **Controlled test data was restored afterwards.**
- **Any state that could not safely be produced remains explicitly unverified** — named, not omitted.

Inspecting a code path is not testing it. If a path was only read, say so.

⚠️ **AMENDED rev 6 — HOW each state is produced. No test hooks, no server changes, no bundle
contamination.** Building the origin tracking (§5.5) is what makes most of these reachable through
*real* failures rather than injected ones — that is a second argument for the amendment, not a
coincidence.

| State | How | Status |
|---|---|---|
| **B2** blocked/hung connection | DevTools → Network → **Offline**, then load the widget | **Real. Do it.** |
| **B4(a)** failed chart refresh | Chart displayed → go offline → click the chart's **refresh** control → restore | **Real.** A real refresh, a real failure, correct origin |
| **B4(b)** unrelated failure | Chart displayed → offline → click a **non-chart** action → restore. Chart must stay **unmarked** | **Real** |
| **B4(c)** marker clears | After (a), refresh the chart **successfully** | **Real** |
| **B5** empty chart | A weekly report over a period with no calendar data | **Real**, if such a period exists |
| **B3** malformed first result | — | **See below** |

**B3 is the exception.** A malformed first result is not producible from the client without touching
the server, which is out of scope. Its three sub-cases are **not equivalent**:

- **MCP error result** — reachable if a tool can be made to fail for real (e.g. lapsed auth). **Attempt
  this one.**
- **Empty structured content** and **structured content lacking the expected payload** — name both as
  **explicitly unverified**, individually, not as one line.

Record which sub-cases were exercised and which were not. **Do not report B3 as passing on the strength
of the one case that was reachable.**

### B1 — host context
*Static:* `platform`, `displayMode` and all four insets each have a live call site executing after
connection · `.left` and `.right` read and applied · listener registered via the additive API and
removed on cleanup.
*On host:* mobile inline and mobile fullscreen — safe-area padding applied **for the first time**. No
control under the composer or navigation bar; nothing clipped by the notch in landscape. Host-initiated
fullscreen reflects in widget state. **Check the mobile width, gap and margin branches — they have never
executed.**
**PG's own handler firing is proved here, not inherited from A2.**

### B2 — connection failure
*Static:* `isConnected` and `error` consumed; the stale check no longer depends on object existence; the
timer cleared on all three exits.
*On host:* a deliberately broken or blocked connection produces a terminal, visible state. Timeout and
explicit error are distinguishable.

### B3 — malformed first result
*Static:* every exit path from the result handler either initialises or sets a load error, with the
correct message class per §5.4.
*On host:* a result without a usable payload surfaces an error rather than loading indefinitely.

### B4 — error after a rendered chart
*Static:* the error branch is reachable from the chart view · chart data retained · **the stale marker is
set only by a failed chart-refresh operation** · the marker clears on a subsequent successful chart
result.
*On host:* with a chart displayed — (a) a **failed chart refresh** shows the error and marks the chart
stale; (b) an **unrelated failure** shows the error and leaves the chart unmarked; (c) a **later
successful chart result** clears the marker.
If (a) and (b) cannot be distinguished by the current error state, that is a finding — record it and
default to not marking.

### B5 — empty chart
*Static:* the empty-slice path reaches the chart's own empty state.
*On host:* a weekly report with no calendar data shows "no time data", not "no priorities".

### Partial-update merging — evidence split
Manual testing may never produce four independently partial updates. Record separately:
- **Static:** the updater merges each defined field into previous state and **preserves omitted fields**.
- **On host:** every partial update the host naturally produces, observed.
- **Explicitly unverified:** any field combination that could not be triggered. Name them.

### Console — record everything, exempt nothing
**Record every warning.** A warning may be classified as host-origin **only** where Increment A's
evidence establishes that specific message's origin, quoted exactly, with the evidence named. **No
warning is ignored merely because it appears to come from host-side code.**

### Cross-cutting
- **Runtime theme switching still works**, inline and fullscreen. A's verified behaviour; B must not
  regress it.
- **Listener cleanup produces no warning after remount.**
- **The console was actually open.** State it.
- Loading→loaded transition still holds — **Claude-M20 must not regress.**
- No new bare hex; no untranslated string.

---

## 9. Before deployment

Read `doc/OPERATIONS_PREDEPLOY.md`. Its four deferred Better Stack steps remain outstanding —
`configure_logging()` is absent, so **the Claude server ships no logs**, which limits diagnosis if B's
on-host pass fails.

**After deploying v5: delete the connector and re-add it, then start a new conversation.** Disconnect
and reconnect does not fetch new bundle bytes.

---

## 10. Report

- Commit hash
- Changed file set from `git status --porcelain`, byte and line deltas supplementary
- **Which scoped files were touched, and for what** — including an explicit statement if `main.css`,
  `i18n.ts` or `types.ts` were *not* needed, with reused keys and classes named
- **Whether any operational document changed** — or an explicit statement that none did
- New `WIDGET_VERSION`, new URI, and the enumeration proving every reference resolves to it
- Bundle size delta, build provenance, and **confirmation the bundle diff contains no test-only code**
- **v4 rollback prerequisites, recorded before deployment**
- For each of B1–B5: mechanism found, mechanism after, and that block's acceptance result
- **How each unnatural test state was produced**, and confirmation of the four provenance conditions
- What the `onAppCreated` block now does
- The subscription mechanism used, and confirmation it is the additive API
- The timeout duration used, whether preserved or changed, and the justification if changed
- **How the chart-refresh failure is distinguished from an unrelated failure** — or a finding that it
  cannot be
- The partial-update evidence split, including field combinations that could not be triggered
- **Every console warning observed**, with classification and the evidence for any classified as
  host-origin
- Observed on-host behaviour, or an explicit statement that the smoke test has not been run
- **Still unresolved, carried forward:** no automated widget-runtime test harness · A3's font listener
  not runtime-verified · **server-side production logging absent — overall PG-Claude production
  readiness is not established by this increment**
- An explicit list of what was **not** verified

---

## 11. REPORT — static half, 2026-08-06

⚠️ **THE SMOKE TEST HAS NOT BEEN RUN.** Nothing here rests on observation. Written at implementation
time deliberately, so the on-host pass fills in a document rather than reconstructs a memory. Every
*On host* item in §8 remains open.

**Commit `9c3fc6c`. Not pushed, not deployed.**

### Changed set (`git status --porcelain`; byte/line deltas supplementary)

| File | Bytes | Lines |
|---|---|---|
| `App.tsx` | 35,419 → 49,644 (+14,225) | 1,001 → 1,222 (+221) |
| `i18n.ts` | 16,445 → 17,240 (+795) | 434 → 444 (+10) |
| `pg-dashboard-claude.html` | 593,943 → 595,114 (+1,171) | 155 → 155 |
| `resources_dupl.py` | 5,927 → 5,927 (**+0**) | 171 → 171 (**+0**) |
| this briefing | 23,321 → 25,730 (+2,409) | 422 → 457 (+35) |

`resources_dupl.py` shows **zero byte and zero line delta for the third consecutive increment** —
`"4"→"5"` and `v4→v5` are same-length substitutions. This is standing check 11's case reproducing every
time the version moves; byte counts cannot see it, and only the porcelain set can.

### Scoped files, and what each was for

- **`App.tsx`** — B1–B5, all five.
- **`i18n.ts`** — two new key pairs in **both locales**: `widgetConnectionFailed`/`Hint` (§5.3's
  timeout-vs-error distinction) and `failedToRefresh` (the `:384` amendment). **`noData` was REUSED**
  for §5.4's generic payload case rather than adding a synonym — it existed, was unused outside
  `i18n.ts`, and a second key for one meaning drifts across two locales.
- **`types.ts` — NOT TOUCHED.** §2 permits it "only if genuinely required"; it was not. See B4.
- **`main.css` — NOT TOUCHED.** The only new visual element is the chart-branch error banner, built
  from existing host tokens with inline styles matching the two banners already in the file.
- **No operational document changed.** `OPERATIONS_PREDEPLOY.md` was read, not edited, as §2 requires.

### Version identity

`WIDGET_VERSION` 4 → **5**; `ui://pg-claude/dashboard-v4.html` → **`ui://pg-claude/dashboard-v5.html`**.
Single declaration at `resources_dupl.py:40`; `response_adapter_dupl.py` and `tools_list_dupl.py` import
it; **0** stale v4 literals.

⚠️ **Scope correction (adversarial review).** This previously read "**3** `_meta.ui` blocks as expected",
unscoped. That is true only **within `resources_dupl.py`** — `tools_list_dupl.py` and
`response_adapter_dupl.py` also construct `_meta.ui` for tool results. The count was never wrong; the
sentence omitted the scope it was counted over, which is the negative-scope rule (standing check 2)
applied to a positive count. **Corrected: 3 `_meta.ui` blocks in `resources_dupl.py`; two further
construction sites exist in the tool-result path, both deriving from the same imported `WIDGET_URI`.**

**Standing check 11 earned its place a third time.** `resources_dupl.py` shows a **zero byte delta**
while `git` reports **2 insertions / 2 deletions**. A byte-count-derived changed set would have missed
this file entirely; the porcelain-derived set caught it. That is precisely the hole the check was
corrected to close, reproducing on every version bump.

### Build provenance (§7)

Node v24.8.0 · npm 11.6.0 · `rm -rf dist node_modules/.vite && npm run build`, run twice from clean.
**Both builds `2e208ae80b119d37fa649fb8d9e999eb7a057ac58fbc61f8c0fd8d4fc8bb5184` — reproducible.**
Bundle **+1,171 B (+0.197%)** against B's ±2%. No new dependency; `package.json` untouched. No
`window.openai`; 0 external `<script src=>`. **Bundle diff contains no test-only or state-forcing
code** — checked, not asserted: the source diff carries no `TODO`/`FIXME`/`window.__`/`localStorage`/
`forceState`/`mockData`/`debugger`.

Python suite **8 failed / 25 passed — unchanged across the version bump.** That is `64b0572`'s
imported-constant fix working: the first bump since, and the URI tests did not go red.

### §8 rollback prerequisites — recorded BEFORE any push

| | |
|---|---|
| Service | `srv-d6vbrt9r0fns73c6n080`, **`autoDeploy: yes` / commit → a push IS a deploy** |
| Live deploy | `dep-d9q8jq3bc2fs7395u1cg`, live 2026-08-06T13:20:43Z |
| Live commit | **`38c0076`** |
| Live URI | `ui://pg-claude/dashboard-v4.html` |
| Live bundle | 593,943 B / `6f97b93c…` — restorable from git as bytes, ancestor of HEAD |

⚠️ **ROLLBACK TARGET IS NOT THE PREVIOUS DEPLOY — go back two, to v4.**

v5 (`c6c932e`, live 14:51:05–…) shipped with **two known defects**, both found by the second
adversarial review and both consequences of v5's own fixes: the terminal error branch was a dead end
with no retry, and a malformed chart payload still rendered "No priorities yet". They were live to users
for the interval between v5 and v6.

So the most recent deploy is the **worse** fallback. **If v6 fails badly, roll back to
`38c0076` / v4** (`dep-d9q8jq3bc2fs7395u1cg`, bundle 593,943 B / `6f97b93c…`), not to v5. v4's defects
are the ones B set out to fix — known, characterised, and survived for months; v5's are known, newer,
and user-visible on a first-load failure. "Previous deploy" is a heuristic, not a rollback target.

⚠️ **NEAR MISS, recorded because it is the argument for the re-verify rule.** The record carried
forward from Claude-A named `785dd1d`. By the time B needed it the live commit had moved **twice**, to
`38c0076`. It happened to be harmless — the intervening commits were documentation, so the live bundle
is still the identical `6f97b93c…` artifact A built, and a rollback to `785dd1d` would have restored
the same bytes. **But that could not be known without checking**, and had any of those commits touched
the widget, the record would have pointed at the wrong artifact. Second time this session a Render
value went stale between being recorded and being used.

### Adversarial review before deploy — three fixes, two dispositions

Run against the unpushed commits, deliberately before pushing, since with `autoDeploy: yes` a push is a
deploy. Verdict was **hold**. Three changes made, three findings left as reported.

**FIXED — an error with no data rendered a FALSE claim.** The worst finding, and a regression *this
increment introduced*. B3 correctly made failed results set `loadError` and `isInitialized` but left
`data` null, so the render fell through to the dashboard branch, `dashboardData?.priorities ?? []`
yielded an empty list, and `EmptyState` rendered. An auth failure displayed *"Authentication required"*
directly above *"No priorities yet. Ask the assistant to help you set up your top priorities."* — telling
a user whose session lapsed that their data does not exist and inviting them to recreate it. Before B3
this path showed a skeleton: uninformative but honest. **Informative and wrong is worse.** Now a terminal
branch at `App.tsx:858`, ahead of both the chart and dashboard branches. Deliberately *not* implemented
by suppressing `EmptyState` inside the dashboard branch — that would leave the whole shell rendering
around an error and push the same reachability question one level down.

This is the **fifth** instance of the increment's pattern and the first where the consumer does not
merely hide the state but contradicts it.

**FIXED — `Array.isArray` on the chart payload.** `isPieChartData` tests only `'slices' in data`, and
`PieChart` calls `slices.filter()` **during render**, outside the result handler's `try/catch`, so a
malformed `slices` would throw past it into the error boundary. The type guard proves the key exists; it
does not prove the component can use the value. One clause, in the branch B5 had just made reachable.

**CHANGED — the timeout's message, not its budget.** The review rated the 3s timer High, reasoning that
cold starts could exceed it. That reasoning is wrong: `connect()` is a **postMessage handshake with the
parent frame**, not a network call, so Render latency never enters into it. But the underlying complaint
was right for a different reason — at 3s the widget asserted *"This dashboard is from a previous
session. Start a new conversation"*, which is confident, directive, and unwarranted by the evidence,
and while set it silently refuses 12 tool-call sites plus expand.

**Two thresholds now.** `BRIDGE_SLOW_MS` 3000 → `'slow'` → the existing non-directive `connecting`
string, no advice given. `BRIDGE_STALE_MS` 15000 → `'stale'` → the session-expired wording, which now
requires five times the evidence before it is spoken. The budget is unchanged; what changed is what the
widget is willing to claim on three seconds of silence.

**LEFT AS REPORTED:** local-expand-then-collapse and the `FullscreenHeader` disappearance (both already
carry on-host reproductions, and the second needs observation before anyone decides), and the CRUD
suppression window (recorded at the guard).

### B1–B5: mechanism found → mechanism after → static result

**B1 — host context read before it existed.** `onAppCreated` runs before `await connect()`;
`_hostContext` is assigned inside `connect()`. Every read returned `undefined`. → Read moved to an
effect keyed on `app`, which `useApp` sets only after connect resolves. Subscribe-then-read so nothing
arriving between the two is lost. **Static: PASS** — `platform`, `displayMode` and all four insets have
exactly one live call site, in `applyHostContext`, reached only post-connection.

**B1 also found a second dead flag.** `setHostFullscreen(true)` existed **nowhere in the file**;
`hostFullscreen` was initialised `false` and could only ever be set `false`. It gates
`isMobileHostFullscreen`, which gates every inset — so the gate was dead **twice over, either cause
sufficient**, and fixing `platform` alone would have changed nothing observable.

**B2 — predicate tested object existence.** The object is assigned before connect is attempted. →
`isConnected`/`error` (both returned by `useApp`, never destructured) drive
`'slow' | 'stale' | 'error' | null`; `isBridgeStale` derived. Timers cleared on all three exits.
**Two thresholds: `BRIDGE_SLOW_MS` 3000 and `BRIDGE_STALE_MS` 15000.** The 3s budget is preserved from
pre-B; what changed is what the widget will *claim* on three seconds of silence. **Static: PASS.**

⚠️ **This paragraph was WRONG until the second review caught it, and the way it went wrong matters
more than the error.** It described `'timeout' | 'error' | null` and a `BRIDGE_TIMEOUT_MS` constant —
accurate when written, and false within the hour, because the mechanism changed underneath it after the
first adversarial review and this section was never re-read. **A report drafted in parallel with
implementation describes the code at the moment of drafting, not at the moment of reading.** Same class
as `--maxfail=5` and the "deprecated service" line, both corrected earlier today, both authored by
someone describing a true thing that later stopped being true. **Carry this forward: any §-report
written before the code settles must be re-read against the code before it is called done.**

**B3 — three results fell through.** → Four exits, all terminating. MCP-error surfaces the server's own
message, **verified safe at the source**: `handlers/tools_dupl.py` returns `str(e)` for an intentional
`ToolUsageError` and a fixed `"Something went wrong. Please try again."` otherwise, so exception text
and payload internals never reach `content[0].text`. **Static: PASS.**

**B4 — PARTIAL.** §5.5(b) implemented: the chart branch returned before both `loadError` sites, so the
banner now renders inside it, chart retained. **Deliberately NOT by reordering** — see below.
**§5.5(a) and (c) not implemented: no reachable trigger.** **Static: PASS for (b), FINDING for (a)/(c).**

**B5 — one clause.** `&& data.slices.length > 0` sent an empty chart result into the dashboard branch,
where it was cast to `DashboardData` and rendered "no priorities yet". `isPieChartData` tests key
presence, not length. → Clause removed. `PieChart.tsx:61-79` has owned the correct empty state since
v1 — never missing, just never routed to. **Static: PASS.**

### What `onAppCreated` now does

**Registers handlers, and nothing else.** The host-context reads are gone. Handler registration must
stay there: `toolresult` is a one-shot event and the SDK warns (throws under `strict`) if it is first
registered after `connect()`. `hostcontextchanged` is **not** one-shot, which is what makes the later
subscription legal.

### Subscription mechanism

`app.addEventListener('hostcontextchanged', …)` with `removeEventListener` on cleanup — the **additive**
API. **Zero `onhostcontextchanged =` assignments remain.** That single slot is what `useHostStyles`
destroyed on 1.2.2.

### Timeout

**3000 ms, preserved.** B changes the predicate, not the budget; moving both would make an on-host
regression unattributable.

### How a chart-refresh failure is distinguished from an unrelated one — IT IS NOT, and why

**Three independent lines of evidence, each separately sufficient:** none of the 14 `callServerTool`
sites returns chart data; the chart branch has no refresh control; `PieChart` has no controls at all.
Chart data arrives **only** via chat-initiated `render_weekly_report`, and `ontoolresult` carries no
tool identity.

**`chartStale` was deliberately NOT built.** A state variable with no possible setter is the mirror of
the four defects this increment found, and would let this report claim a capability nothing can
exercise. This is §5.5's own contingency: report it, default to not marking.

**The cause is a PG DESIGN gap, not a protocol one.** `TimeAllocationBar` has a refresh control through
`callServerTool`; the chart does not. Had it shipped with the same affordance, origin would be known at
the call site and `ontoolresult`'s anonymity would never bind. **Prerequisite for (a)/(c): a
widget-initiated chart refresh control** — a feature, outside B. The protocol framing would wrongly
suggest waiting for the spec to change.

### The two branch-order fixes are a contrasting pair — keep them together

**B2 was fixed BY reordering:** the terminal connection state had to precede the loading branch, because
`setIsInitialized(true)` is only called from `ontoolresult`, so a failed connection meant the loading
branch returned forever and the terminal branch was unreachable in exactly the case it exists for.

**B4 must NOT be:** §5.5 requires the chart **retained**, so hoisting the error above it would remove
the thing the requirement protects. The banner is rendered *inside* the chart branch instead.

Same defect shape, opposite remedies. **The discriminator is whether the branch below carries something
the user still needs.**

### Partial-update merging — evidence split

- **Static:** `applyHostContext` guards **every field individually**, so an update carrying only `theme`
  cannot blank `platform`, and a `safeAreaInsets` carrying only `top` cannot zero `.bottom`. Verified by
  reading; each of the six fields has its own `!== undefined` guard.
- **On host:** *pending.*
- **Explicitly unverified:** any combination the host does not naturally produce. To be named
  individually after the pass, not summarised as one line.

### Console

*Pending.* §8 requires every warning recorded, with host-origin classification permitted **only** where
Claude-A's evidence establishes that specific message's origin. **Known in advance:** `App.tsx:75-79`
logs a `[PG Diagnostic]` line on every inline render, asserting a 500px limit that does not exist. It
will appear in the record. Out of B's scope; it has now survived M20, A and B.

### Carried forward, unresolved

No automated widget-runtime harness · A3's font listener not runtime-verified · **server-side production
logging absent — `configure_logging()` is not called in `server_dupl.py`, so the Claude server ships no
logs, and B's failure-path testing runs without them.** **PG-Claude's overall production readiness is
not established by this increment.**

### Reported, not fixed

- **`PieChart.tsx:74`** — `var(--color-text-secondary, #73726C)`. `#73726C` is *tertiary*'s value;
  secondary is `#3D3D3A`. Zero production consequence (inside a Claude host the token always wins), but
  it is the **second** instance found by accident — the first during M2's contrast work at
  `App.tsx:694`. **The finding is the class, not the instance: nobody has swept `var(--color-*, #hex)`
  pairs against the published token table.** A mechanical follow-up increment; the token values are
  already committed in `sources_raw/`. Fixing this one instance would leave the rest, which is the
  standing-checks lesson.
- **The CRUD suppression window now swallows errors.** `if (Date.now() - lastCrudAtRef.current < 1500)
  return` sits **above** the `try`, so within 1.5 s of a CRUD operation every result is dropped —
  including, now, an `isError` result that B3's CASE 1 would surface. Harmless before B3 because errors
  were not handled at all. Does not affect B3's requirement (a *first* result cannot fall inside a CRUD
  window), but it is a new interaction B3 created.
- **`handleExpandToFullscreen` never tells the host.** It sets `displayMode` locally and never calls
  `requestDisplayMode`, unlike `handleMinimizeToInline`. Before B1 nothing could contradict the local
  state; now `applyHostContext` can. **On-host reproduction required:** expand locally, then rotate or
  resize, and see whether fullscreen survives. Not guarded, because the fix belongs at the asymmetry and
  that is outside B1–B5 — and it may be theoretical if the host never sends `displayMode` in partials.
- **`FullscreenHeader` now disappears under host-initiated fullscreen** for the first time ever, because
  `hostFullscreen` can finally be `true`. Correct per the guidelines, but nobody has seen the resulting
  state. **On host: confirm there is a visible way back.**

### NOT VERIFIED

**The entire on-host half of §8**, every item. Plus, specifically: **the mobile width, gap and margin
branches have never executed in production** — `platform` was permanently `undefined` before B, so every
`platform === 'mobile'` ternary has always taken the desktop leg. They are not what B was fixing, which
makes them the most likely and least expected place for a regression. **Check them harder than the
fixes.** Also unverified: PG's own `onhostcontextchanged` handler actually firing (B1's on-host half,
which §1 forbids inheriting from A2) · all four insets applied on a real device · the 8 remaining Python
test failures, individually · reproducibility on any machine other than this one.