# Increment Claude-A — SDK upgrade `@modelcontextprotocol/ext-apps` 1.2.2 → 1.7.5 (rev 3)

**Purpose:** upgrade the widget's direct runtime dependency to the reviewed 1.7.5 release, restore
runtime host-**style** updates by eliminating the SDK listener collision, and bring the dependency
supply chain under control.

**Supersedes rev 2.** Changes: purpose narrowed to host-*style* updates · A3 evidence separated into
runtime, static and unverified · rollback gate added · tool testing replaced by a widget call-path
matrix · client-performance observation added.

**Independent of:** Increment B. A does not restore PG's host-context lifecycle — `platform`, safe
areas and `displayMode` remain broken until B.
**Order:** A runs first. B's subscription lifecycle should target and be verified against the additive
event API this upgrade introduces.
**Bundle version:** **v4.**

---

## 1. Scope

- `widget-react/package.json` — dependency version and pinning
- `widget-react/package-lock.json`
- `widget-react/src/App.tsx` — **only** where the upgrade forces a change
- The canonical `WIDGET_VERSION` declaration and `WIDGET_URI`
- The generated Claude widget bundle
- Only those resource metadata references requiring update because of the version change
- `doc/OPERATIONS_PREDEPLOY.md` — dependency and build-provenance note (§5) only
- `doc/Claude_Compliance/COMPLIANCE_AUDIT_RECORD.md` — PG-specific M1 status and evidence only

**Do not change the canonical M1 requirement.** Only PG's status against it moves.

**Out of scope:** every Increment B defect — host-context read timing, `isConnected` / `error`
consumption, malformed-result handling, stale-chart errors, empty-chart routing · any other widget
component · any behavioural change not forced by the upgrade.

Adjacent issues found during implementation are reported, not fixed.

---

## 2. Bundle version identity and deployment

- Increment A → **v4** · Increment B → **v5**

⚠️ **This section states INTENT, not state.** "v4 is deployed" is what the increment requires before
its on-host acceptance can run — it is **not** a claim that v4 is live at any moment you are reading
this. §8 correspondingly requires the rollback record to be captured *before* deployment; the two are
not in conflict, they are consecutive. **For actual state, read the deploy log on Render for
`priority-guardian-claude-mcp` (`srv-d6vbrt9r0fns73c6n080`), never this file** — a briefing committed
mid-increment describes a moving target. That service is `autoDeploy: "no"`; pushing does not deploy it.

**v4 is deployed** to the Render service so it can be verified. There is no staging environment —
`sources_raw/testing.raw.md`: *"There is no separate staging environment — you test in production using
a custom connector."* A custom connector uses the same runtime as a directory connector. PG-Claude is
not listed, so the only consumer is the developer.

**v4 is not the submission artifact.** B produces v5, and v5 is the artifact considered for submission.

**Reusing a version across different bytes is prohibited.**

---

## 3. What this fixes, and what it does not

### Fixes: the host-style listener collision

`onhostcontextchanged` on 1.2.2 is a **setter** calling `setNotificationHandler`, which *replaces* the
handler rather than adding one. `useHostStyles` is two hooks — `useHostStyleVariables` (theme and style
variables) then `useHostFonts` (fonts only) — each assigning it in an effect.

Chain: PG's handler → overwritten by the variables hook → overwritten by the fonts hook. **Only font
updates survive.**

Consequence: **runtime theme switching is dead.** Initial theme applies via a separate one-shot effect;
a mid-conversation change never reaches the appliers. This is **M1**, one of only two hard MUSTs on the
design-guidelines page.

1.7.5 moves both style hooks to `addEventListener` / `removeEventListener` on a listener array, and the
`on*` setter writes a separate slot nothing else touches. It also ships a diagnostic warning for this
defect class.

### Does not fix

- **B1** — host context read in `onAppCreated`. `useApp` still calls it before `await connect()`, and
  `_hostContext` is assigned inside `connect()`. The SDK documents the contract: *"Returns undefined if
  called before connection is established."* PG is using the API against its documented behaviour.
  `platform`, `safeAreaInsets` and `displayMode` stay dead. **Increment B.**
- **B2–B5** — connection state, malformed results, stale-chart errors, empty-chart routing.

---

## 4. First task — establish what changed, before any code moves

Twelve releases span five months. Behaviour was verified from built artifacts, **not release notes**.
Read the official changelog and source diff across the range, and **report findings before making
changes**. Establish at minimum:

1. **Protocol version.** 1.2.2 declares `2026-01-26`. If it moved, does the host negotiate or require a
   match?
2. **`ui/initialize` payload and `McpUiInitializeResult` shape.**
3. **Host-context schema** — fields added, removed or renamed, particularly `platform`,
   `safeAreaInsets`, `displayMode`, `containerDimensions`.
4. **`useApp`'s new `strict` option** — default and enforcement. **Most likely to break at runtime
   rather than at compile time.**
5. **`setNotificationHandler` / `setRequestHandler` now `_assertMethodNotRegistered`** — throwing on
   double registration. The `App` constructor already assigns a no-op `onhostcontextchanged`, and PG
   assigns its own in `onAppCreated`. **Does that pattern now throw?**
6. **`_assertInitialized` on `callServerTool`** — warns before handshake completion. PG has 14 call
   sites. Warning or ordering constraint?
7. **`useAutoResize` now calls `setupSizeChangedNotifications()`**, and **`useApp` cleanup calls
   `close()`.**
8. Anything else in the diff touching an API PG uses.

**If the review surfaces a breaking change, stop and report rather than working around it.**

---

## 5. Supply chain — all four, not just the pin

`package.json` declares `^1.2.2`. That caret does **not** cause `npm ci` with a committed lockfile to
jump versions — the risk is lockfile regeneration or bypass: plain `npm install`, lock deletion, or
update tooling. Because the widget bundle is a **committed build artifact**, such a jump lands in a
shipped file nobody reviewed.

1. **Exact version** in `package.json` — `1.7.5`, no caret, no range.
2. **Committed lockfile**, same commit.
3. **`npm ci` in documented builds**, not `npm install`.
4. **A note in `doc/OPERATIONS_PREDEPLOY.md`** recording that the widget bundle is a committed artifact
   whose dependency versions must be exact, and that dependency changes are reviewed explicitly.

---

## 6. Constraints

- **No behavioural change beyond what the upgrade forces.**
- **Do not fix any Increment B defect**, even where the new API makes it tempting.
- `useHostStyles` continues to be called as it is today — the upgrade fixes it from underneath.
- Host tokens throughout. No new bare hex, no new untranslated string.
- No change to `resources_dupl.py` beyond version and URI.

---

## 7. Build gates and provenance

- Type-check and production build pass on the new version.
- **`npm ci` from the committed lockfile installs exactly one `@modelcontextprotocol/ext-apps@1.7.5`.**
- Bundle size before and after. This upgrade may move it materially — **investigate rather than
  report**, and state the threshold used.
- Production bundle contains no `window.openai` reference and no OpenAI-only import.
- Changed set from `git status --porcelain` — byte deltas supplementary, and can be zero on same-length
  substitutions.
- No new runtime dependency beyond the upgrade; report transitive additions.

**Provenance — record all of it:** Node version · npm version · exact clean-build command · clean
working-tree and build-directory state · resolved SDK version from the lockfile · generated bundle hash
· a **second clean build's** hash · whether they match.

A hash mismatch **does not fail the increment** — Vite output can vary without behavioural difference.
It **does** block any claim of byte-for-byte reproducibility. If they differ, say so.

---

## 8. Rollback gate — complete before deploying

v4 goes to the live Render service. Not listed is not the same as not production.

**Before deployment, record:** the currently deployed commit · the currently served bundle URI · the
Render deployment identifier.

**Confirm** the previous bundle and lockfile can be restored **without rebuilding from unreviewed
dependencies** — i.e. the prior committed bundle is restorable as bytes, not regenerated by an install
that may resolve differently.

**Roll back if any of these is observed:** the widget fails to initialise · any tool call regresses ·
theme switching fails · duplicate-registration errors appear in the console · unexplained protocol
incompatibility.

**After any rollback,** verify the previous custom-connector path still renders and tool calls still
work. A rollback that isn't verified isn't a rollback.

---

## 9. Acceptance

**There is no automated widget-runtime test harness** — no runner, no test files, no test script. A
known production-quality gap, filed separately, and an **unresolved risk rather than an acceptable
steady state**. Until it exists, A's evidence is static and build checks plus recorded Claude.ai
verification.

### A1 — the upgrade is inert where it should be
*Static:* every PG-used API resolves; either no signature change required a call-site edit, or each edit
is listed with its cause.
*On host:* widget loads, renders inline, expands to fullscreen. **Claude-M20's loading skeleton must not
regress.**
*Performance:* record whether first render, theme switching, expansion or tool interaction shows a
visible latency regression. Bundle-size evidence is primary. **No backend load test is required** — the
increment adds no backend work.

### A2 — runtime theme switching works
**The reason this increment exists, and unverifiable any other way.**
*On host:* with the widget rendered, toggle the host between light and dark **mid-conversation**.
Colours, backgrounds, borders and text must follow. Verify inline and fullscreen.
**Do not record the M1 theme defect as fixed until this is observed in Claude.ai.**

### A3 — listener coexistence, evidence separated
Record as three lines, not one:

- **Runtime evidence:** theme and style variables update mid-conversation, proving the variables
  listener is no longer lost. This is what A2 demonstrates.
- **Static/source evidence:** 1.7.5 registers both the variables and font hooks additively and cleans
  them up on unmount.
- **Not runtime-verified:** the **font** listener. Toggling theme need not produce an observable font
  change, so A2 does not exercise it. Verify only if Claude provides a way to trigger and observe a
  font-context change; otherwise record as unverified.

**Also not verified by A:** PG's own host-context consumers. `platform`, `safeAreaInsets` and
`displayMode` remain dead via B1 regardless of this upgrade. Increment B's acceptance, not A's.

### A4 — widget call-path matrix
The upgrade principally risks widget initialisation and **widget-originated `callServerTool` paths**.
Calling eight tools through chat does not necessarily exercise the 14 widget call sites.

**Exercise every distinct widget-originated `callServerTool` path at least once**, using controlled demo
data. Public tools not invoked by the widget may be smoke-tested separately but **do not substitute for
those call-site checks.**

Record a matrix with one row per path: the tool invoked · read-only / mutating / destructive · the
controlled demo data used · expected result · observed result · cleanup or restoration performed ·
whether the call exercised the widget bridge or only the MCP/backend path.

**Destructive paths run last, on disposable data.** The deletion tool destroys the state every other
path needs.

### A5 — console observation
1.7.5 ships runtime diagnostics for the failure modes §4 items 5 and 6 describe. **Watch the browser
console throughout** and record:
- any duplicate-registration error or `on* handler replaced` warning
- any pre-initialisation `callServerTool` warning during normal flows
- any lifecycle warning on mount, unmount or remount

Absence is evidence **only if the console was actually open**. State that it was.

### A6 — supply chain
*Static:* exact version pinned · lockfile committed · `npm ci` documented · `OPERATIONS_PREDEPLOY.md`
note added · provenance recorded per §7 · rollback prerequisites recorded per §8.

### Cross-cutting
No new bare hex · no untranslated string · no behavioural change outside the upgrade.

---

## 10. Before deployment

Read `doc/OPERATIONS_PREDEPLOY.md`. Its "currently deprecated" line for the Claude MCP server is known
stale and its four deferred-service steps are unexecuted, including `configure_logging()` — so the
Claude server ships no logs. That audit is separate work, but note that **A's on-host verification runs
without server-side logging**, which limits diagnosis if something fails and raises the value of §8's
rollback record.

---

## 11. Report

- Commit hash
- **The changelog and source-diff findings from §4, itemised** — the increment's primary output, due
  whether or not code changed
- Changed file set from `git status --porcelain`, with byte and line deltas as supplementary evidence
- New `WIDGET_VERSION`, new URI, and the enumeration proving every reference resolves to it
- Bundle size delta, threshold used, transitive dependency additions
- **Build provenance per §7**, both hashes and whether they match
- **Rollback prerequisites per §8**, recorded before deployment
- Every call-site edit the upgrade forced, with its cause
- A1's performance observations
- A2's result observed on host — or an explicit statement it was not run, in which case M1 stays open
- **A3 as three lines** — runtime evidence, static evidence, not-runtime-verified — plus the separate
  note that PG's own consumers remain unverified pending B
- **A4's call-path matrix**, complete
- A5's console observations, and confirmation the console was open
- An explicit list of what was **not** verified