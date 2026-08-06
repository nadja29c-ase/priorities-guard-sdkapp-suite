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

---

## 12. REPORT — increment complete, 2026-08-06

**All six acceptance items pass. Two hard requirements closed by observation on production: M1 and M20.**

### Commits

`fd9d6cb` SDK 1.2.2 → 1.7.5 pinned exact, bundle v4 · `64b0572` WIDGET_URI asserted by import ·
`3a0874f` false count and false deprecation corrected in two records · `e36b64d` this briefing tracked ·
`c50259c` second unverified "5" recorded · `8d71d00` read-path test, mutation-verified · `785dd1d`
four-service identification table · `5aeb56c` M1 verified, autoDeploy row self-corrected.

**Deployed:** `dep-d9q7seeq1p3s73f34g5g` (commit `785dd1d`), live 12:31. The A-pass ran against it.
The widget bundle is **byte-identical across `fd9d6cb`, `785dd1d` and `5aeb56c`**
(`6f97b93c…`) — later commits touched documentation only — so the observations hold at HEAD.

### §4 findings — the increment's primary output

Protocol version **unchanged** (`2026-01-26`). `ui/` method surface 16 → 17, one added, none removed.
`McpUiHostContext` **deep-identical** — all twelve fields, including B's targets. 38 shared schema
definitions: 29 byte-identical, 9 changed, every change additive, zero removals. Double registration
cannot throw. `_assertInitialized` is a warning — but says *"will throw in a future release"*, so PG's
14 `callServerTool` sites are on a **deprecation clock**, recorded as a known future break.
`hostcontextchanged` is **not** in `ONE_SHOT_EVENTS`, so B may register after connect.

**The M1 fix landed in 1.4.0, not 1.7.5.** So 1.4.0 is the minimum version clearing M1, and the
better rollback target than 1.2.2 — reverting to 1.2.2 would leave a hard MUST broken.

**Changelog/dist discrepancy**, on the range's only Breaking-marked entry: v1.3.0 documents
`ui/notifications/request-close`; the shipped method is `ui/notifications/request-teardown`. Caught
only by checking claims against `dist`.

### Acceptance

| | Result |
|---|---|
| **A1** render, first observation of the M20 skeleton, no perceived regression | ✅ |
| **A2** runtime theme switching, mid-conversation | ✅ **M1 closes** |
| **A3** listener coexistence | ✅ runtime + static; font listener not exercised |
| **A4** widget call-path matrix, full CRUD across the bridge | ✅ |
| **A5** console, open throughout | ✅ one warning, host-side |
| **A6** supply chain, provenance, rollback | ✅ |

**A2 has both halves.** The same toggle was run on live **v2** first and the widget stayed light — the
defect reproducing on 1.2.2. A controlled comparison, not a single reading.

**A1 was recorded as a first observation, not a regression check** — M20's v3 was never deployed, so no
baseline existed. Amended before the pass, not after.

### A5 — console, open throughout

- **`handler replaced` — 6×, all `oncalltool`, all host-side.** Not PG's. The distinction is textual:
  `setEventHandler` emits *"…Use addEventListener(…)"*; `warnIfRequestHandlerReplaced` emits *"…Previous
  handler will no longer be called."* The A5 signal was about the **first**, on event handlers, which is
  what would show PG's `onhostcontextchanged` being clobbered — **zero of those.** The prediction held.
  `oncalltool` is declared on the host-side `AppBridge`; PG never sets it and registers no tools.
- **`callServerTool`** — clean.
- **`size-changed`** — present as pre-registered. The SDK discards its `ResizeObserver` disconnect
  function while 1.7.0's `useApp` cleanup calls `close()`. Upstream, dev-only, harmless in production.
- **`Ignoring message from unknown source`** — v2: 31 errors / 141 messages. v4: 48 / 1,042 after far
  heavier interaction. **Rate fell.** Ambient transport filtering; not attributable to the upgrade.

### The pre-upgrade CSP check — a question now permanently unanswerable

On live v2, console open, reloaded: **`eval` → 0, `Function` → 0.** Only CSP entries were Chrome's
*"Unrecognized directive 'webrtc'"* ×18, from the host's own policy. **Zod's JIT path was never blocked
by Claude's CSP.** So 1.7.5's `z.config({jitless:true})` is **hardening, not a fix**, and is withdrawn
as a justification. The upgrade stands on M1 alone, which suffices. Obtainable only before deploying.

### Build provenance

Node v24.8.0 · npm 11.6.0 · `npm ci` then clean build. The **pre-upgrade** bundle reproduced
byte-for-byte (375,573 / `42cfea79…`), proving bundle and lockfile had not diverged; **two** clean
builds of the new bundle both produce 593,943 / `6f97b93c…`. Reproducible in both directions.

**Bundle +218,370 B (+58.1%)**, gzip 100.42 → 147.70 kB. Attributed by experiment, not assumption:
forcing zod back to 4.3.6 gives 580,490, so **+205KB is ext-apps itself, +13KB is zod**. Threshold used:
flag at >2×, not reached; no documented project ceiling exists.

**Supply chain:** exact pin, lockfile committed, `npm ci` documented. 24 packages moved — verified
**forced** by the upgrade, since `npm install` with no manifest change moves zero. One added
(`@standard-schema/spec`), zero removed. `npm audit --omit=dev` → **0**; the 4 findings are dev-only
picomatch via Vite, deliberately unfixed.

**No call-site edit was forced.** `App.tsx` untouched, `tsc --noEmit` clean.

### §8 rollback — recorded before deployment, against the correct service

**`srv-d6vbrt9r0fns73c6n080`** — PG-Claude, `mcp.priority-guard.com/mcp`. Confirmed by two independent
means: identical `oauth-protected-resource` from custom and onrender domains, and
`sha256("https://mcp.priority-guard.com/mcp")[:32]` = `a7b31ccb44096357600a7460eb0a78e9`, matching the
widget's own iframe origin. Prior live deploy `dep-d9oem1lbedkc73avfvsg` at `eb3373c7`, serving
`dashboard-v2.html`, bundle 373,879 / `2554dfd9…`, restorable as bytes and an ancestor of HEAD.

**A service-identification error cost several exchanges.** `srv-d90din3sq97s7399nbl0` is
**MindSort-Claude**, and it auto-deployed every commit while PG-Claude did not — so watching a commit
go live was evidence about the wrong service. Both services, their apps and the identification recipe
are now in `OPERATIONS_PREDEPLOY.md`. PG-Claude's `autoDeploy` was switched **on** at 12:31; the doc
row written 30 minutes earlier was corrected the same day.

### Tests

`8 failed / 21 passed` → **`8 failed / 25 passed`**. Two URI tests fixed; two read-path tests added,
**mutation-verified in both directions** — a handler pinned to a stale `dashboard-v3.html` is caught by
the new test *only*, while the three older tests pass, demonstrating the tautology rather than arguing it.

**The documented known-red count was an artifact.** `tests/unit/mcp_pg_claude/` was recorded as 5; the
real number is 10. The "5" is `pytest.ini:26 --maxfail=5` — a stopping condition recorded as a
measurement. `--maxfail=5` predates the baseline by seven months, so the headline "~154 known-red"
cannot have come from the documented command either. **No corrected aggregate was stated, because none
was measured.** And there is no gate: no `.github/workflows`, no `preDeployCommand` — nothing ever ran
these tests.

### NOT verified

The **font listener** (a theme toggle produces no observable font change — accepted, not open) ·
**PG's own `onhostcontextchanged` handler firing and updating state** — A2 proves the *SDK's* listener
survives, **not PG's**; this is B1's acceptance and must not be inferred from A2 · `platform`,
`safeAreaInsets`, `displayMode` — all still dead, B's work · the 8 remaining test failures, individually ·
every unamended count in `testing_baseline_2026-07-04.md` · `add_priority`'s **success** path, blocked by
the three-priority cap on a populated account; its 409 crossed the bridge and returned, which is what A4
tests · byte-for-byte reproducibility on any machine other than this one.

### Flagged, not fixed

`test_list_tools_annotations_match_registry` is red, and several compliance rows rest on annotation
claims — the title-annotation blocker was itself once resolved by reading code rather than running it ·
`adapt_get_priorities_meta` renamed to `adapt_widget_tool_meta`, leaving 3 tests importing a function
that no longer exists · the four deferred Better Stack steps remain unexecuted, so **the Claude server
still ships no logs** · the `size-changed` observer defect, upstream.