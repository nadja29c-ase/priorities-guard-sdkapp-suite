# Increment Claude-C — Host-negotiated fullscreen, retry result handling, inset merge window (rev 2)

**Bundle version:** **v7.** v6 (`7f5a2b3`) is the currently deployed artifact.
**Precondition:** Increment B's on-host pass is complete.

**Supersedes rev 1.** Changes: C1 distinguishes app-declared support from host-offered availability ·
C4 gains a four-branch disposition gate · C2 requires a shared contract rather than parallel
implementations · M3/B1 closure made conditional on C4's outcome.

---

## 1. Scope

**Code**
- `widget-react/src/App.tsx`
- `widget-react/src/i18n.ts` — only if a new user-facing string is genuinely required; prove reuse first
- `widget-react/src/types.ts` — only if a new state shape is genuinely required; justify

**Build and version**
- The canonical `WIDGET_VERSION` declaration and `WIDGET_URI`
- The generated Claude widget bundle
- Resource metadata references requiring update because of the version change

**Documentation**
- `doc/Claude_Compliance/COMPLIANCE_AUDIT_RECORD.md` — PG's M3 status and evidence only

**Out of scope:** dependency versions · `useHostStyles` · other widget components · the fullscreen
`max-width` reconciliation · badge colours. Adjacent issues are reported, not fixed.

---

## 2. Why this exists — B1's acceptance did not pass on host

B1 fixed `platform`, fixed `hostFullscreen`'s setter, and applied `Math.max` on all four insets. The
code is correct. **The requirement is still not met**, because `isMobileHostFullscreen` requires
`hostFullscreen`, which becomes true only when the host *reports* fullscreen, which happens only after
the widget *requests* it — and `handleExpandToFullscreen` never does.

**One root cause, four observed symptoms:**

1. On mobile, tapping expand renders PG's fullscreen layout **inside the inline-sized iframe**. Content
   begins under the status bar and Claude's header. **The defect is the scroll origin, not the height**
   — a fullscreen dashboard scrolling for several screens is normal and compliant.
2. Safe-area insets never apply on the path users actually take.
3. `hostFullscreen` never becomes true, so PG's Minimize bar has never been hidden.
4. Host-reported fullscreen ("case two") was unproducible during B's pass, because the host only
   reports fullscreen after granting a request.

Report B1 as **partial**, not passed.

---

## 3. C1 — host-negotiated fullscreen

> `handleExpandToFullscreen` **must request host fullscreen through the MCP Apps display-mode API and
> must not set fullscreen layout solely from local state.** The widget must render from the
> host-reported display mode. **If fullscreen is unavailable or denied, remain inline and preserve a
> usable inline layout.**

### Two values, not one

These are different and both matter:

| Value | Meaning |
|---|---|
| `appCapabilities.availableDisplayModes` | what **PG declares** it can render, sent at initialization |
| `hostContext.availableDisplayModes` | what **Claude currently offers** |

The spec requires the view to declare its supported modes **and** check the host's available modes
before requesting one. Declaring is not permission.

### Required sequence

1. User taps Expand
2. **Check the current `hostContext.availableDisplayModes` includes `fullscreen`.** If it does not,
   **send no request** and stay inline
3. Request fullscreen from the host
4. **The return value determines the resulting UI state** — not the fact that the call succeeded. **A
   successful request can legitimately return `inline`**; in that case leave or restore the inline
   layout
5. Once host fullscreen is active, safe-area insets apply
6. The dashboard may scroll vertically for as many screens as needed
7. Claude's native close becomes the primary exit path

**Do not treat the request as success.** Fire-and-assume reproduces the exact state being fixed —
fullscreen layout inside an inline iframe — reached by a different route.

**Verify before implementing:** what the installed SDK's `requestDisplayMode` returns, and where
`hostContext.availableDisplayModes` is exposed. One root cause explaining four symptoms is when to
confirm rather than trust the story.

---

## 4. Also in scope

### C2 — retry and initial load must share one contract

The retry button added in v6 made `refreshData` reachable from a failure state. It was written for a
working widget refreshing good data and was not read when wired in.

- It does not inspect `result.isError`. A retry returning a valid `CallToolResult` with `isError: true`
  falls through as success, clears the disabled state, and **leaves the original error text unchanged**
  — the user sees no indication the retry failed, or what it said.
- It accepts any truthy `content.data`. A malformed dashboard payload is stored and `loadError` cleared.

> **`refreshData` and `ontoolresult` must enforce the same result/error and payload-validity contract.
> Reuse an existing shared validator if one exists; if equivalent logic remains duplicated, prove the
> two paths have identical acceptance behaviour.**

Two independent implementations of one contract diverge. That is how initial-load and retry behaviour
come apart on the next increment.

### C3 — close the "No priorities yet" class, not the next route

`dashboardData?.priorities ?? []` defaults a missing array to empty, and `EmptyState` renders whenever
the list is empty **regardless of why**. Five routes to that false claim have been found; three closed
individually, and C2's malformed-success path is the fifth.

**Fix at the consumer:** render "No priorities yet" only when the payload is structurally valid *and*
the array is genuinely empty. Otherwise the generic load error.

### C4 — SDK shallow-merge window: disposition gate, not a fix

`connect()` receives a full `hostContext.safeAreaInsets`. If the host emits `hostcontextchanged` with a
partial `{ safeAreaInsets: { top } }` **before** PG's effect subscribes, the SDK updates its cache with
a shallow spread — `this._hostContext = {...this._hostContext, ...params}` — so the cache holds only
`top`. PG then reads `getHostContext()` and its per-field guards cannot recover the other three sides.

PG's per-field merge is correct for updates it receives. The gap is the window before subscription,
combined with the SDK's shallow nested merge.

**Inspect the 1.7.5 source and establish whether this window exists. Do not implement a speculative
workaround.** Then take exactly one branch:

| Branch | Action |
|---|---|
| **Does not exist** | Record the evidence and close C4 |
| **Exists, cleanly eliminable at app level within this increment** | Implement and verify the remedy |
| **Exists, not safely eliminable at app level** | **Leave explicitly open as an upstream/runtime risk. Do not mark M3/B1 fully satisfied.** Name precisely which safe-area path remains vulnerable or unverified |
| **Cannot be determined from source** | Say so. Do not guess in either direction |

**Branch 3 is the one that matters** — it is the outcome where everything else in C passes and the
temptation to round M3 up to closed is strongest.

### C5 — remove the 500px diagnostic

`App.tsx` logs `[PG Diagnostic] Inline main scrollHeight: …px (limit: 500px, EXCEEDS LIMIT)` on every
render. **No 500px limit exists** — a stale-fetch artifact corrected in the compliance docs. It has
shipped through M20, A, B and v6.

---

## 5. Bundle version identity and rollback

- v6 → **v7.** Reusing a version across different bytes is prohibited.
- **Record before deploying:** v6's commit (`7f5a2b3`), its resource URI, and the Render deployment
  identifier on `srv-d6vbrt9r0fns73c6n080`. **Re-verify at the point of use** — this record has gone
  stale three times.
- **Check autoDeploy's current state before pushing.** It has changed mid-session before.
- **Rollback target is v6** — the best-understood artifact, with B's five defects fixed and its on-host
  pass observed. Not v5 (two known first-load defects), not v4 (B's defects present). Previous-deploy
  is a heuristic; best-understood is the target.

---

## 6. Constraints

- Host tokens throughout, with fallbacks. No new bare hex.
- No new user-facing string without i18n, both locales. **Prove reuse before adding.**
- **Establish reachability before writing state.** Five defects in B were "state fixed, consumer
  wrong" — a fix must be observable given the branch order above it.
- **A negative claim states the scope it was proved over.**

---

## 7. Acceptance

No automated widget-runtime harness exists. Assertions are manual and recorded, with test-state
provenance: how each state was produced, no test-only code in the bundle diff, no guard bypassed, and
anything unproducible **named individually**.

### C1 — host-negotiated fullscreen

*Static:*
- `appCapabilities.availableDisplayModes` includes `fullscreen`
- **Immediately before requesting**, current `hostContext.availableDisplayModes` is checked and includes
  `fullscreen`
- **No request is sent when it does not**
- **The return value from `requestDisplayMode` determines the resulting UI state**
- **A returned mode other than `fullscreen` leaves or restores the inline layout**

*Three cases, tested separately:*
1. Fullscreen offered → host returns fullscreen → fullscreen layout
2. Fullscreen **not** offered → **no request sent** → inline preserved
3. Fullscreen offered and requested, **result is not fullscreen** → **remain inline**

*On host, mobile:*
- Content **begins below the status bar and Claude's header** — the scroll origin is the observable
- Scrolling works normally; height is not a defect
- **Safe-area insets apply.** Whether this closes M3/B1 **depends on C4's disposition** — see below
- **PG's Minimize bar disappears**, replaced by Claude's native close. Pre-registered. **Confirm the
  native close returns cleanly to inline**
- Landscape: content clears the notch on the sides

*On host, desktop:* **checked separately.** Expand is local-only there today and works. This changes a
surface that isn't broken.

*Denial path:* if fullscreen is unavailable or denied, PG stays inline with a usable layout — **not**
fullscreen UI inside an inline iframe.

### C2 — shared contract
*Static:* `refreshData` and `ontoolresult` enforce the same result/error and payload-validity contract.
If a shared validator exists, both use it. If logic remains duplicated, **prove identical acceptance
behaviour** across both paths.
*On host:* a failing retry shows the retry's own error, not the original.

### C3 — EmptyState guard
*Static:* "No priorities yet" renders only for a structurally valid, genuinely empty payload.
*On host:* a malformed dashboard payload reaches the generic load error, not the empty state.

### C4 — disposition
*Static:* the branch taken, with the SDK-source evidence for it.
**If branch 3:** M3/B1 remains **partial**, with the vulnerable safe-area path named. C1's on-host
inset observation is recorded as working on the observed path, **not** as M3 closed.

### C5 — diagnostic removed
*Static:* the string is absent from the bundle.

### Cross-cutting
Runtime theme switching still works, inline and fullscreen · M20's skeleton unregressed · B2–B5
unregressed · console open and stated · every warning recorded, none exempted for appearing host-side.

---

## 8. Before deployment

Read `doc/OPERATIONS_PREDEPLOY.md`. Its four deferred Better Stack steps remain outstanding —
`configure_logging()` is absent, so the Claude server ships no logs.

**After deploying: delete the connector and re-add it, then start a new conversation.**

---

## 9. Report

- Commit hash · changed set from `git status --porcelain` · bundle size delta against the ±2% threshold
  established in B · build provenance including both clean-build hashes
- New `WIDGET_VERSION`, new URI, and the enumeration proving every reference resolves to it
- v6 rollback prerequisites, recorded before deployment, and the autoDeploy state at that moment
- **What `requestDisplayMode` returns**, where `hostContext.availableDisplayModes` is read, and how
  render derives from the returned mode
- **C1's three test cases, each with its result**
- For C2, C3, C5: mechanism found, mechanism after, acceptance result
- **C4's branch, the SDK-source evidence, and the consequence for M3/B1's status**
- **B1's status after C** — closed, or partial with the named vulnerable path
- Observed on-host behaviour, or an explicit statement that it has not been run
- **Still unresolved, carried forward:** no automated widget-runtime test harness · A3's font listener
  not runtime-verified · server-side production logging absent · the `var(--color-*, #hex)`
  fallback-mismatch class, unswept
- An explicit list of what was **not** verified

---

## 10. REPORT — static half, 2026-08-07

⚠️ **THE ON-HOST PASS HAS NOT BEEN RUN.** Nothing below rests on observation. Every *On host* item in
§7 is open. Written at implementation time so the pass fills in a document rather than reconstructs a
memory — and, per Increment B's §11 lesson, **this section must be re-read against the code before it
is called done**, because a report drafted in parallel describes the code at the moment of drafting.

### Changed set (`git status --porcelain`; byte/line deltas supplementary)

| File | Bytes | Lines |
|---|---|---|
| `App.tsx` | 55,416 → 70,615 (+15,199) | 1,338 → 1,598 (+260) |
| `pg-dashboard-claude.html` | 596,205 → 597,515 (+1,310) | 155 → 155 |
| `COMPLIANCE_AUDIT_RECORD.md` | 96,452 → 97,785 (+1,333) | 1,586 → 1,586 |
| `main.css` | 1,685 → 2,607 (+922) | 96 → 112 (+16) |
| `resources_dupl.py` | 5,927 → 5,927 (**+0**) | 171 → 171 (**+0**) |

`resources_dupl.py` at **zero byte and zero line delta for the fourth consecutive increment** — every
version bump is a same-length substitution. Standing check 11's case, arriving on schedule.

### ⚠️ TWO AUTHORISED SCOPE AMENDMENTS

Recorded here rather than left as unexplained work outside §1's list — M20 rev 4's lesson.

1. **M10 was not in C's scope and is now in C.** §1 explicitly excluded "the fullscreen `max-width`
   reconciliation". That exclusion was correct while host fullscreen was impossible: the caps were
   inert because the widget was always inside a chat panel narrower than any of them. **C1 makes them
   bind for the first time.** Shipping C without M10 would land the mobile fix half-working, and the
   missing half is the visible one.
2. **`main.css` was not in C's scope and is now edited.** The binding cap is `#root { max-width: 600px }`,
   which lives outside the component tree. **No child can exceed it**, so M10 was not fixable from
   inside App.tsx. A `body.pg-host-fullscreen` class is the narrowest lever that reaches it.

### Version identity

`WIDGET_VERSION` 6 → **7**; `ui://pg-claude/dashboard-v7.html`. Single declaration at
`resources_dupl.py:40`; `response_adapter_dupl.py` and `tools_list_dupl.py` import it; **0** stale v6
literals. **3 `_meta.ui` blocks *in `resources_dupl.py`*** — scoped deliberately: `tools_list_dupl.py`
and `response_adapter_dupl.py` construct `_meta.ui` for tool results as well, and the previous
unscoped phrasing was standing check 2 applied to a positive count.

### Build provenance

Node v24.8.0 · npm 11.6.0 · `rm -rf dist node_modules/.vite && npm run build`, twice from clean.
**Both builds `3807a3a6a1770f49870e4a27e87f5321e862890d367864880c5c050d62b5dee5` — reproducible.**
Bundle **597,515 B**, +1,310 vs v6 (+0.220%) and +0.601% against the v4 baseline — inside B's ±2%.
No `window.openai`; 0 external `<script src=>`. **Bundle diff checked, not asserted, for test-only or
state-forcing code:** no `TODO`/`FIXME`/`window.__`/`localStorage`/`forceState`/`mockData`/`debugger`.
Python suite **8 failed / 25 passed — unchanged across the bump**, which is `64b0572`'s
imported-constant fix continuing to hold.

### v6 rollback prerequisites — re-verified at the moment of writing

This record has gone stale three times, so nothing here is carried forward from earlier in the session.

| | |
|---|---|
| Service | `srv-d6vbrt9r0fns73c6n080` |
| **autoDeploy AT THIS MOMENT** | **`yes` / `commit` → a push IS a deploy** |
| Live deploy | `dep-d9qaaigae00c73aa3dbg`, live 2026-08-06T15:17:19Z |
| Live commit | `7f5a2b3` |
| Live URI | `ui://pg-claude/dashboard-v6.html` |
| Live bundle | 596,205 B, restorable from git as bytes, ancestor of HEAD |

**Rollback target is v6** — the best-understood artifact, with B's five defects fixed and its on-host
pass observed. Not v5 (two known first-load defects), not v4 (B's defects present). Best-understood,
not most-recent.

### C1 — what the SDK actually returns, and how render derives from it

Verified from the installed SDK rather than assumed, as §3 requires:

- **`requestDisplayMode` returns `Promise<{ mode: "inline" | "fullscreen" | "pip" }>`** — the granted
  mode, not merely success. This is what makes "the return value decides" implementable.
- **`hostContext.availableDisplayModes`** is `("inline"|"fullscreen"|"pip")[]` — and **OPTIONAL**,
  while `hostContext` itself is required.

**Render derives from one applier.** `applyDisplayMode(mode)` is the sole writer of `displayMode`;
`hostFullscreen` is **derived** (`displayMode === 'fullscreen'`) rather than tracked, because every
fullscreen is now host-granted. Called from expand's result and catch, minimize's result and catch, and
the host-context path. **`setHostFullscreen` no longer exists.**

**Absent `availableDisplayModes` is PERMISSIVE.** Absent means "the host didn't say", not "not
offered" — the field is optional and a spec-legal host may omit it. Treating silence as denial would
have made fullscreen permanently unreachable, replacing "expand always works locally, wrongly" with
"expand never works at all". The real guard is the returned mode; the pre-check only skips a request
known to be refused. This also closes the pre-population window for free, since `undefined` during it
is permissive.

Plus an in-flight ref so a double-tap cannot fire two requests, and `displayModeNegotiatedRef` so the
**one-shot initial context read** cannot undo a just-granted mode — `requestDisplayMode` does not update
the SDK's cached `_hostContext`, only a notification does. Notifications are never skipped.

**C1's three cases — STATIC ONLY, all three on-host results pending:**

| Case | Static |
|---|---|
| 1. Offered → returns fullscreen → fullscreen layout | ✅ |
| 2. Not offered → **no request sent** → inline preserved | ✅ |
| 3. Offered, result is not fullscreen → remain inline | ✅ (incl. `pip`, which warns then falls back) |

### C2, C3, C5 — mechanism found → mechanism after

**C2.** `refreshData` ignored `result.isError` and accepted any truthy `content.data`. → One
`classifyToolResult` (what a result *is*) and one `applyToolOutcome` (what the widget *does*), both
shared. **Scoped claim:** one contract for the **two paths that had diverged** — initial load and
refresh. `extractClaudeStructuredContent` remains on the CRUD and backfill paths, unchanged and out of
scope; this is **not** a global single source of truth. One deliberate divergence: `markInitialized`,
a parameter with **no default**, because `isInitialized` is a lifecycle fact and a refresh is
post-initialisation by definition.

**C3.** `dashboardData?.priorities ?? []` defaulted a missing array to empty and `EmptyState` rendered
whenever the list was empty regardless of why. → One consumer guard, above the dashboard render and
below the chart branch. Validity is also enforced at ingestion by C2, but the consumer guard is what
closes the **class**: ingestion validity is a property of two call sites, the guard is a property of
the claim.

**C5.** Removed. **Its absence from C's console record is the expected signal** — do not look for it
and conclude the filter broke. The literal string `500px` survives in the comment explaining the
removal, which is intended; the claim is "the diagnostic is removed", not "nothing references 500px".

### C4 — DISPOSITION: BRANCH 3. Exists, not safely eliminable at app level.

**Mechanism, from the installed 1.7.5 source:**

```js
super.setNotificationHandler(X, ($) => {
  let G = $.params
  this.onEventDispatch(K, G)   // shallow merge — runs FIRST, unconditionally
  Z.onHandler?.(G)
  for (let j of [...Z.listeners]) j(G)
})
```

`onEventDispatch` does `this._hostContext = {...this._hostContext, ...params}` — a **shallow** spread,
so a partial `{ safeAreaInsets: { top } }` replaces the whole nested object. It runs **before any
handler and regardless of whether any listeners exist**, and the slot is registered at **construction**
(the App constructor calls `setEventHandler("hostcontextchanged", undefined)`, which calls
`_ensureEventSlot`). So the merge is live from construction onward.

**Why registering earlier does not help:** the initial full insets arrive with `connect()`'s response,
and PG cannot read them before `app` is set. Subscribing in `onAppCreated` is legal —
`hostcontextchanged` is not a one-shot event — but PG would have no full baseline to merge into, so a
partial update arriving before PG's first read still destroys the omitted sides inside the SDK's cache.

**The vulnerable ordering exists in the SDK. It was not observed during the available on-host tests,
and its practical frequency is unknown.** No likelihood is characterised, because none was measured.

**Consequence: M3 remains PARTIAL.** Recorded in `COMPLIANCE_AUDIT_RECORD.md`. C1's on-host inset
observation, once made, records insets working **on the observed path** — not M3 closed.

### B1's status after C

**B1 was PARTIAL after B**, because the insets were correct code nothing could reach. C1 makes the path
reachable. **B1's remaining acceptance is entirely on-host and cannot be inherited** from any static
result. **B1 closes only if the on-host pass confirms it, and even then M3 stays partial via C4.**

### ⚠️ A LIVE PATH WITH A STATED EXPIRY — decide before submission

`FullscreenHeader` (PG's Minimize bar) previously rendered under `{!hostFullscreen && ...}`. With
`hostFullscreen` derived, that guard is **always false** in the fullscreen branch, which would have
made PG's only fallback exit — and `handleMinimizeToInline` — silently unreachable.

**The guard was removed, deliberately: the header now always renders in fullscreen.** The guidelines
say Claude renders a close button in the native header bar in fullscreen. **Nobody has observed it** —
host fullscreen was unreachable until C1, so B's pre-registered *"confirm the native close returns
cleanly to inline"* could never be run. Deleting the only fallback exit on a documented-but-unobserved
behaviour is the trade this project has repeatedly been punished for (the 500px limit, the deprecated
service, `--maxfail=5` — all documented, none true). The asymmetry decides it: a redundant control for
one release, versus a user trapped in fullscreen with no way out.

**EXPIRY — this is a decision with a trigger, not a permanent state.** On C's pass, host fullscreen is
finally producible and PG's Minimize bar will appear beside Claude's native close. **If the native
close is clearly present and returns cleanly on BOTH platforms, delete `FullscreenHeader` and
`handleMinimizeToInline` before submission** — two exit affordances on one surface is exactly what a
reviewer notices in a screenshot.

### Four review passes, each finding what the previous missed

C was reviewed four times. Each pass found something its predecessors did not: the tautological URI
assertions; the unpopulated `availableDisplayModes` window and the optional-field case behind it; the
minimize/expand desync, the desktop cap that asserted a width the outer cap forbade, and the stale
initial-context read; then the `FullscreenHeader` path going dead.

**Every one was reachable by reading. None required running anything.** That is the clearest evidence
in this project for the missing widget-runtime test harness — not as a complaint, but because a suite
that exercised expand, minimize and the render chain would have caught all four in seconds, and four
human and machine passes were spent instead.

### Carried forward, unresolved

No automated widget-runtime test harness · A3's font listener not runtime-verified · **server-side
production logging absent** — `configure_logging()` is not called in `server_dupl.py`, so the Claude
server ships no logs, and C's on-host pass runs without them · **the `var(--color-*, #hex)`
fallback-mismatch class, now at THREE instances** — `App.tsx:694`, `PieChart.tsx:74` and
`FullscreenHeader.tsx`, all pairing `--color-text-secondary` with tertiary's `#73726C`. Three in three
files is a class, not a coincidence; nobody has swept the pairs against the token table in
`sources_raw/`. Deliberately not fixed instance-by-instance.

### NOT VERIFIED

**The entire on-host half of §7**, every item — C1's three cases, the mobile scroll origin, safe-area
insets on a real device, the landscape notch, PG's Minimize bar beside Claude's native close, the
desktop path, C2's failing-retry message, C3's malformed payload, and the console record. Plus: the
C4 ordering, which is **not verifiable by construction** · M10's five reconciled caps on any real
device · whether the desktop path, which worked before C, still works — **C puts a working surface
through host negotiation for the first time** · the 8 pre-existing Python failures, individually ·
reproducibility on any machine other than this one.