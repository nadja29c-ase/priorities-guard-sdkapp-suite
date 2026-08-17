# Increment: MindSort-Claude — host-negotiated fullscreen (mobile + desktop)

**App:** MindSort AI for Claude (`mcp_server/mindsort_claude/`). Fullscreen widget view.
**Type:** Behavioral fix to display-mode handling. Adopt genuine host-negotiated fullscreen so the widget is promoted to real host fullscreen (as PG-Claude is), on mobile and desktop, relying on the host's native close and removing the app's own exit control.
**Touches:** `mcp_server/mindsort_claude/widget-react/src/App.tsx` only (plus its tests) and the `WIDGET_VERSION` line in `handlers/resources_dupl.py`. Does NOT touch PG-Claude, `clarity/`, the OpenAI path, backend, or tool handlers.
**Explicitly out of scope:** any redesign of the fullscreen board's visual layout (increments 3–6 own that); the inline accordion; ordering; the projection adapter.

## UNBLOCKING OBSERVATION (recorded 2026-08-17)
Native host close (`✕` in Claude's header, outside the widget surface) confirmed **present
AND returning cleanly to inline** on **both mobile and desktop** fullscreen — device
observation, 2026-08-17. App-owned Minimize / `FullscreenHeader` removed as redundant per
this confirmation.

This matters because change #2 deletes the app's only exit control. Until this observation
the native close was *documented but unobserved* — PG-Claude's own source says so verbatim
(`priority_guardian_claude/widget-react/src/App.tsx:1580`: "NOBODY HAS OBSERVED IT") and PG
therefore still renders its own Minimize unconditionally as a fallback. The deletion here
rests on an observation, not on the guidelines. A gated fallback was considered and is
**impossible**: `hostFullscreen` answers "did the host grant fullscreen?", not "does the
host provide a close?", and once it tracks the host faithfully
`displayMode === 'fullscreen'` ⟺ `hostFullscreen === true`, so a `!hostFullscreen` gate
inside a fullscreen-only view is unreachable in every state. The ext-apps 1.7.4 host-context
schema exposes no native-close signal, so no gate can encode one.

Consequence logged, NOT actioned here: this same both-platform confirmation satisfies
PG-Claude's own pre-registered expiry (same file, "delete this header and
handleMinimizeToInline ... before submission"). PG is submitted and hands-off; the cleanup
is now actionable whenever PG is next touched.

## Why this exists (evidence, not assumption)
1. **Observed production host behavior has advanced beyond the published mobile documentation — rely on capability negotiation, not the docs claim.** PG-Claude has been EMPIRICALLY VERIFIED to receive genuine host fullscreen on Claude mobile, including native host chrome (the `✕` in Claude's header, outside the widget surface). Do NOT claim Anthropic's public documentation currently *guarantees* mobile fullscreen — reports of the live page's exact wording conflict (some readings say "design from 320pt up to fullscreen on mobile," others still say fullscreen is "coming soon / mobile is inline-only"), and this increment must not depend on resolving that. What is certain and sufficient: the real host grants mobile fullscreen today, display modes are host-negotiated, and the host renders a native close in fullscreen. Therefore MindSort must use capability negotiation rather than any hard-coded device assumption. The July MindSort premise "mobile must stay inline-only" is falsified by the production observation regardless of the docs' current wording.
2. **MindSort's current fullscreen entry is NOT host-negotiated.** In `App.tsx`, `handleExpandToFullscreen` does `setDisplayMode('fullscreen')` — LOCAL STATE ONLY — and never calls `requestDisplayMode`. A code comment claims "This is the pattern used by PG-Claude (verified 2026-07-22)." **That comment is stale/incorrect:** current PG-Claude calls `requestDisplayMode({mode:'fullscreen'})` and applies the host-returned mode as authoritative. Local React state can select a fullscreen *layout* but cannot ask the host to *promote the app into host fullscreen*. So MindSort currently cannot achieve the real fullscreen PG achieves — most visibly on mobile.

## Reference (READ before implementing — READ ONLY, do not modify PG)
`mcp_server/priority_guardian_claude/widget-react/src/App.tsx` — current PG-Claude display-mode handling: `handleExpandToFullscreen`, the host-context lifecycle, `availableDisplayModes` handling, `hostFullscreen` derivation, safe-area application, and the in-flight request guard cleared in `finally`. PG is the working reference for the MECHANISM. Do NOT copy PG's visual layout, its CRUD, its own Minimize control, or its permissive-when-absent gate (see "What NOT to copy from PG").
Before commit: read `OPERATIONS_PREDEPLOY.md` ("Widget Bundle Changes").

## PREREQUISITE — verify the declared capability set FIRST
Before any other change, confirm MindSort initializes the MCP App with `appCapabilities.availableDisplayModes` containing BOTH `'inline'` and `'fullscreen'`. (Current source appears to: `useApp({ capabilities: { availableDisplayModes: ['inline','fullscreen'] } })` — verify this is intact, do not assume.) If it does not declare both, correct it in `App.tsx`. Rationale: the host reports what IT supports only after the app declares what it supports; implementing the request side correctly while advertising the wrong capability set would silently fail. `availableDisplayModes` on host context is the host describing the modes IT supports.

## The required flow (host-negotiated, capability-gated, binary)
```
host advertises 'fullscreen' in availableDisplayModes
  → MindSort shows the "Open full board" affordance   (already gated this way — keep)
  → user taps → requestDisplayMode({ mode: 'fullscreen' })   (NEW — currently missing)
  → apply the HOST-RETURNED mode as authoritative (may differ from requested; may be 'inline')
  → subsequent host context (onhostcontextchanged) is authoritative and reconciles state
  → in host fullscreen: rely on Claude's NATIVE close; render NO app-owned exit control
  → fullscreen layout applies safe-area insets
If fullscreen is NOT advertised, or the request is declined/rejected:
  → remain inline cleanly. Do NOT create a local/fake fullscreen fallback.
  → NO device-specific "mobile = false" logic anywhere.
```
There are exactly two end states: **host-granted fullscreen** (native close, no app Minimize) or **inline**. There is no third "fullscreen layout without host fullscreen" state.

## Changes

### 1. Fullscreen ENTRY must call `requestDisplayMode` (the core fix)
Current `handleExpandToFullscreen`:
```
if (isBridgeStale || !isFullscreenAvailable) return
setDisplayMode('fullscreen')   // local only — never asks the host
```
Change it to request host fullscreen and apply the returned mode, following PG's current pattern:
- Keep the `isBridgeStale` guard and the STRICT `isFullscreenAvailable` capability gate (see §"What NOT to copy").
- Call `appRef.current.requestDisplayMode({ mode: 'fullscreen' })`.
- Apply the **host-returned** `result.mode` authoritatively — do NOT assume the request succeeded (a resolved request may legitimately return `inline`, and the SDK explicitly allows the returned mode to differ from the requested one).
- Set/derive `hostFullscreen` from the host's answer, not optimistically (see §3).
- **In-flight guard, cleared in `finally`:** guard against double-tap with an in-flight ref, and clear it in a `finally` block that runs on BOTH success AND rejection. If the ref is cleared only on the success path, a single failed/rejected request permanently disables fullscreen until remount. (PG does exactly this — mirror it.)
- Handle rejection (catch) by remaining inline cleanly.
- If `requestDisplayMode` is unavailable on the app instance, remain inline (do NOT fake a local fullscreen).

### 2. REMOVE the app-owned Minimize / FullscreenHeader from the fullscreen view
Anthropic renders a native close control in the host header in fullscreen; the device screenshot confirms it on mobile. So:
- In genuine host fullscreen, rely on Claude's native close. **Remove/hide MindSort's own `FullscreenHeader` / "Minimize" button from `FullscreenBoardView`.** No app-owned exit control in fullscreen.
- The state "fullscreen layout + `hostFullscreen === false` + app-owned Minimize" is NOT a UX mode to support — it is state divergence. After this increment it must not be reachable: either the host granted fullscreen (native close) or the app is inline.
- Delete the `{!hostFullscreen && <FullscreenHeader …>}` branch and the `FullscreenHeader` usage in the fullscreen view. Whether the `FullscreenHeader` component definition is deleted or retained-unused is the implementer's call; if retained, it must not render in the fullscreen path.
- Removing the Minimize resolves the pre-existing 36px tap-target issue by deletion.

### 3. `handleMinimizeToInline` — grep callers; remove if dead. Do NOT tie it to reconciliation.
(Corrected: an earlier draft said to keep `handleMinimizeToInline` "as the programmatic inline-return path used by host-context reconciliation / focus restoration." That is architecturally wrong and must not be implemented that way.)
- After removing the app-owned Minimize (change #2), **grep ALL callers of `handleMinimizeToInline`.** If there is no remaining USER-INITIATED caller, remove it as dead code.
- **`onhostcontextchanged` must RECONCILE local React state FROM the host notification** — i.e. observe Claude moving the app back to inline and update `displayMode`/derived state accordingly. It must NOT call `requestDisplayMode('inline')` in response to the host having already switched to inline (that asks the host to redo what it just did).
- **Focus restoration is independent of display-mode requests.** Keep focus restoration driven by the `displayMode` transition (fullscreen→inline) as it is today; it must not call `requestDisplayMode`.
- Net: reconciliation observes and updates state; it never re-requests a mode the host already reported. This also simplifies the binary state model.

### 4. `hostFullscreen` and the state model — DERIVE, don't double-track (inspect first)
Currently MindSort tracks `hostFullscreen` as SEPARATE state (`setHostFullscreen`) alongside `displayMode`, which can drift. PG derives the equivalent fact (`hostFullscreen = displayMode === 'fullscreen'`).
- **Inspect current `App.tsx` first.** If `hostFullscreen` only ever means "the host has us in fullscreen," derive it strictly from the authoritative host mode (`displayMode === 'fullscreen'`) instead of a second state variable, matching PG. This removes a drift class.
- Do NOT refactor blindly — if the current code uses `hostFullscreen` to encode something genuinely distinct, keep them separate but ensure both are set only from the authoritative host answer. State which you did and why.

### 5. Host-context reconciliation (verify against PG, align only if weaker)
PG registers the `hostcontextchanged` listener BEFORE connect, reconciles per-field (never replacing the whole context object), reads the baseline after connect, and treats host context as authoritative. Review MindSort's `onhostcontextchanged` + `onAppCreated` reads against PG's lifecycle. Where MindSort's would drop a display-mode or safe-area update, align it — minimally, scoped to display-mode/safe-area correctness. Do NOT rewrite the whole lifecycle if it already reconciles displayMode, availableDisplayModes, safeAreaInsets, and platform per-field (it appears to — verify).

### 6. Safe-area insets in fullscreen (verify for real host fullscreen)
`FullscreenBoardView` reads `safeAreaInsets` and applies them to container padding. Now that the widget will actually be in host fullscreen on mobile — where the composer/native header/home-indicator overlay the app — verify the insets are applied correctly. Reference PG's handling (floors, bottom-composer clearance) and align only if MindSort's is demonstrably insufficient. Keep existing values unless the on-device check shows content obscured.

### 7. Correct the stale comment
Replace the `handleExpandToFullscreen` comment claiming "LOCAL STATE only ... This is the pattern used by PG-Claude (verified 2026-07-22)" with an accurate description of the host-negotiated flow.

## Tap targets (hard constraint)
44×44pt minimum for interactive targets is a hard mobile requirement. The pre-existing 36px Minimize is removed by change #2. **If any interactive fallback control is deliberately retained anywhere, it MUST be ≥44×44pt now** — no "leave it for later." The "Open full board" button already declares `minHeight/minWidth: 44px` — keep that.

## What NOT to copy from PG
- **Do NOT adopt PG's permissive-when-absent gate.** PG treats a MISSING `availableDisplayModes` as "try fullscreen anyway" — a PG resilience choice, NOT the standards-canonical pattern. **Keep MindSort's strict gate:** if fullscreen isn't advertised, stay inline, do not request.
- **Do NOT copy PG's own Minimize control** — this increment REMOVES MindSort's; do not import PG's.
- **Do NOT copy PG's visual layout or CRUD.** MindSort fullscreen is read-only and visually aligned (increments 3–6). This is display-mode MECHANICS only.
- **Do NOT add any `platform === 'mobile'` gate.** Gating is by host capability, never device identity.
- **DO mirror PG's in-flight-guard-cleared-in-`finally` pattern** (this one IS worth copying — see change #1).

## Compliance (preserve)
No Unicode glyphs; SVG icons only; Claude tokens + inline styles; fontWeight 400/500; focus ring `--color-ring-primary`; read-only; safe-area insets respected; 44×44pt tap targets.

## Mandatory: WIDGET_VERSION bump + verify URI changed
Bump `WIDGET_VERSION` in `handlers/resources_dupl.py`. Verify the emitted `WIDGET_URI` string differs; state OLD and NEW in the report.

## Tests
1. Expand calls `requestDisplayMode({mode:'fullscreen'})` when fullscreen is advertised (mock the app). *Catches:* regression to local-only entry.
2. Expand applies the HOST-RETURNED mode: mock resolve `{mode:'inline'}` → stays inline; `{mode:'fullscreen'}` → goes fullscreen. *Catches:* treating request-resolved as success.
3. Expand does nothing / no request when fullscreen NOT advertised (strict gate). *Catches:* accidental permissive gate; dead button.
4. Rejection path: `requestDisplayMode` rejects → remains inline cleanly AND the in-flight guard is cleared (a second expand attempt still issues a request). *Catches:* unhandled rejection; the guard-not-cleared-on-failure bug that permanently disables fullscreen.
5. In the fullscreen view, NO app-owned Minimize/`FullscreenHeader` is rendered in ANY state. *Catches:* the removed duplicate-exit control regressing; the illegitimate "fullscreen + hostFullscreen=false + app Minimize" state.
6. `onhostcontextchanged` reporting `displayMode:'inline'` from fullscreen reconciles local state to inline AND does NOT call `requestDisplayMode` (assert the SDK method is not invoked during reconciliation). *Catches:* re-requesting a mode the host already switched to.
7. `appCapabilities.availableDisplayModes` declared with both 'inline' and 'fullscreen' (assert on `useApp` init). *Catches:* the prerequisite silently regressing.
8. No `platform === 'mobile'` gate on any fullscreen path. *Catches:* device-identity gating.
9. No Unicode glyphs; no PG/OpenAI imports; fontWeight 400/500; any retained interactive control ≥44pt. *Catches:* recurring regressions + tap-target constraint.
10. All prior increment 1–7 tests pass unchanged EXCEPT any asserting the old local-only entry or the presence of the app Minimize in fullscreen — those change by design; list each with its reason. *Catches:* unintended breakage; distinguishes sanctioned changes.

Each test states the bug it would catch. **Verify test discrimination against the pre-fix commit using `git show <precommit>:<path>` or a temporary fixture — do NOT mutate/overwrite the working tree to prove a test fails.** (Production repo; working-tree edits to prove a red test risk stranding changes.)

## Manual acceptance (the real gate — mobile AND desktop, on prod)
- **Mobile:** open a board, tap "Open full board." Confirm (a) GENUINE host fullscreen (fills screen, Claude's native `✕` in the host header), (b) NO app-owned "Minimize" anywhere (only the host's `✕`), (c) content not obscured by notch/composer.
- **Mobile, no-fullscreen fallback:** on any surface not advertising fullscreen, confirm the button is absent and the accordion works.
- **Desktop:** expand works (host-negotiated), the host's close returns to inline, focus returns to the opener.
- Record: does the host render the native close on BOTH platforms?

## Definition of Done
- [ ] Prerequisite verified: `appCapabilities.availableDisplayModes` declares 'inline' + 'fullscreen'.
- [ ] Fullscreen entry calls `requestDisplayMode` and applies the host-returned mode authoritatively; no local-only fullscreen.
- [ ] In-flight request guard cleared in `finally` (success AND rejection).
- [ ] App-owned Minimize / FullscreenHeader REMOVED from the fullscreen view; native close relied upon; no "fullscreen + hostFullscreen=false + app Minimize" state reachable.
- [ ] `handleMinimizeToInline` callers grepped; removed if no user-initiated use remains; reconciliation does NOT call `requestDisplayMode('inline')`; focus restoration not tied to display-mode requests.
- [ ] Strict capability gate kept (no permissive-when-absent); no `platform==='mobile'` gate.
- [ ] `hostFullscreen` derived from the authoritative host mode where feasible (inspected; approach stated).
- [ ] Safe-area insets verified correct in real host fullscreen.
- [ ] Any retained interactive control ≥44×44pt; stale "matches PG (local only)" comment corrected.
- [ ] No PG / OpenAI / clarity / backend changes; only MindSort `App.tsx` (+ tests) and the `WIDGET_VERSION` line.
- [ ] `WIDGET_VERSION` bumped; OLD and NEW URI stated and verified different.
- [ ] Tests 1–10 pass, each with its bug-caught line; discrimination verified via `git show`/fixture (no working-tree mutation); sanctioned test changes listed.
- [ ] `OPERATIONS_PREDEPLOY.md` read before commit.
- [ ] Report ends with commit hash (review verifies against `git show <hash>:<path>`).

## Post-deploy
Deploy; fresh conversation (new URI busts cache); run the mobile + desktop manual acceptance; record results. Not done until seen working in genuine host fullscreen on mobile with no app-owned Minimize.

## Note
Makes MindSort's fullscreen genuinely host-promoted (matching PG's confirmed mobile behavior) and removes duplicate exit chrome. The docs-vs-observed-host divergence is deliberately handled by capability negotiation, not by asserting a documentation guarantee. Separately logged, NOT this increment: PG-Claude's own Minimize is confirmed redundant on mobile and should be removed when PG is next touched. MindSort's submission gate remains the privacy-policy / legal pages in Framer.
