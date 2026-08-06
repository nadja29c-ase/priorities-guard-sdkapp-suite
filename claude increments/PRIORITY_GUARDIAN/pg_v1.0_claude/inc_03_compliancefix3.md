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