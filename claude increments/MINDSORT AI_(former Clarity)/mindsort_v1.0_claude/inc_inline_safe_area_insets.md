# Increment: Inline card must honour safe-area insets (fix M3)

**Product:** MindSort — **Claude connector only.** Claude/Anthropic SDK app. Widget lives in `mcp_server/mindsort_claude/widget-react/`.
**Type:** Widget (React) layout fix. **Widget-bytes change → rebuild + cache-bust required** (see §6).
**Blast radius:** **MindSort-Claude only.** No shared `clarity/` code, no OpenAI surface, no server/handler changes.
**Scope discipline:** Copy and Adjust, Never Rewrite. Mirror the pattern `FullscreenBoardView` already uses. One padding change in the inline root, plus tests. Do NOT restructure the inline render, the accordion, or the capacity model.

---

## 1. Problem (verified against source; requirement is documented, not inferred)

The inline card's root `<main>` in `App.tsx` uses a fixed `padding: '16px'` and **ignores `hostContext.safeAreaInsets` entirely**. `FullscreenBoardView` applies the insets correctly (`padding: ${safeAreaInsets.top + 16}px ${safeAreaInsets.right + 20}px ${safeAreaInsets.bottom + 16}px ${safeAreaInsets.left + 20}px`); the inline path does not apply them anywhere. Compounding it, the widget sets `prefersBorder: false` — meaning MindSort deliberately does not rely on a host-provided bordered card as its layout boundary, so the widget must honour the safe-area information supplied through host context itself.

This is a documented Anthropic requirement, not a judgement call. The live design guidelines state: apps must read `hostContext.safeAreaInsets.{top,right,bottom,left}` and apply them as padding on the root container; the interactive portion of the app must render **inside** the safe area; **users cannot interact with anything rendered outside it**; this is **not** mobile-specific — the host composer can overlay the bottom of an inline app on web/desktop too; and in borderless mode (our case) honouring the insets is **essential**. Requirement ID: **M3**. It is a functional layout requirement, not cosmetic.

**Out of scope for this fix (documentation only):** do not touch the `LAYOUT` height constants (`maxHeight`, `targetThreshold`, `safetyMargin`, `outerPadding`). They are legacy self-imposed values consumed by the DORMANT capacity model — see §3. This fix is about safe-area padding on the rendered root, and has nothing to do with any height value.

---

## 2. Desired behaviour

The inline root container's padding = **base visual padding + the host-provided safe-area inset on each corresponding side**, all four sides:

- top: `16 + safeAreaInsets.top`
- right: `16 + safeAreaInsets.right`
- bottom: `16 + safeAreaInsets.bottom`
- left: `16 + safeAreaInsets.left`

Apply **all four sides** using the host's values. Do **not** invent inline-specific heuristics ("bottom only", "skip top because inline cards sit mid-conversation") — the host provides four authoritative values precisely because it knows where the card sits; if a side needs no inset in this context the host sends `0` for it. Second-guessing the contract is out of scope and wrong.

`safeAreaInsets` is already in scope in `App()` via `hostContext.safeAreaInsets` (default `{0,0,0,0}`), so no new plumbing is needed — this mirrors what `FullscreenBoardView` already receives as a prop.

---

## 3. Technical facts (verified against the committed widget source)

- **State wiring already supports dynamic updates.** `hostContext` is `useState`; `onhostcontextchanged` writes `setHostContext(prev => ({...prev, safeAreaInsets: ctx.safeAreaInsets}))`, and the baseline effect seeds it. The inline `<main>` reads `hostContext.safeAreaInsets` directly in the component body, so any inset change from the host triggers a re-render that re-applies padding. **Requirement: padding must remain dynamic** — read from `hostContext.safeAreaInsets` at render, never snapshot into a one-shot value. (It already re-renders; just don't break that by caching.)
- **The change is the inline `<main>` `style.padding` only.** Currently `padding: '16px'`. Replace with per-side padding composed as in §2. Everything else on that element (`width`, `background`, `borderRadius`, `touchAction`, `overscrollBehavior`) stays byte-identical.
- **DO NOT fold insets into the `LAYOUT` height constants.** `computeDetailCapacity` reads `LAYOUT.outerPadding`, `LAYOUT.maxHeight`, `LAYOUT.targetThreshold`, `LAYOUT.safetyMargin`. That machinery is DORMANT under `INLINE_SHOW_ALL_ITEMS=true` but must stay correct for the one-line rollback path. Adding a runtime inset to the rendered root padding is correct; mutating the static `LAYOUT` budget constants would corrupt the dormant capacity math. Apply the inset at the JSX `style`, not in `LAYOUT`.
- **No internal vertical scroll may be introduced.** The purpose of insets is to keep content clear of occlusion, not to create a scroll container. The inline card must continue to fit content and let the host/conversation own vertical scroll (Anthropic guideline). Do not add `overflow-y: auto`/`scroll` or a fixed height to the root.

---

## 4. Invariants to preserve (state each holds in the report)
- The footer "Open full board" button remains a **44×44 minimum** touch target (`minHeight/minWidth: '44px'` today) — unchanged.
- Light/dark rendering unchanged (padding is layout, not colour; no token changes).
- Fullscreen path unchanged — do not touch `FullscreenBoardView` (it already handles insets).

### Early-return / other inline surfaces — inspect, don't blanket-exclude
M3 is a **rendering-surface** requirement, not a "normal board" requirement: any inline surface carrying **interactive** content must honour the same safe-area contract, or the fix is only partial. The briefing author inspected the two early-return branches in the committed source:
- **Stale-session** branch: a text-only `<div>` ("Session expired" / "Ask again to see your current board.") — **no interactive control.**
- **Loading** branch: a text-only `<div>` ("Loading...") — **no interactive control.**
Because neither contains anything to interact with, neither carries an interaction-occlusion risk, so **both may remain unchanged** this increment. Requirement (not just a branch exclusion): if either state ever gains an interactive control (Retry / Reconnect / Reload / etc.), that surface must honour the safe-area contract too. Confirm in the report that no *other* inline root surface with interactive content was left inset-blind. Do not expand into unrelated redesign or inset text-only surfaces for their own sake.

---

## 5. Tests (separate unit from integration)

**Discriminating test (must fail before, pass after):**
- Render the inline card with `hostContext.safeAreaInsets` set to non-zero values (e.g. `{top:10,right:20,bottom:30,left:40}`) and assert the inline root's computed padding includes those insets added to the base 16px on each side. This **fails against current code** (fixed `16px`, insets ignored) and **passes after**. That fail-before/pass-after is the proof.

**Unit / DOM:**
- Zero insets (`{0,0,0,0}`) → padding is the base `16px` each side (no regression to the default case).
- **Dynamic update:** simulate a host-context change delivering new insets and assert the root padding updates to reflect them (proves it reads from state at render, not a one-shot snapshot).
- Assert **no** `overflow-y: auto|scroll` and no fixed height is present on the inline root (guards against accidentally introducing internal scroll).

**Do not** weaken or delete existing inline/fullscreen tests. The fullscreen inset behaviour is already covered and must stay green untouched.

---

## 6. Build / deploy / verify (widget change → cache-bust required)
- This **is** a widget-bytes change. Criterion for the version bump: the layout change **modifies the generated widget artifact** → rebuild (Vite) → **verify the generated artifact actually changed** → **bump the widget cache-bust/version** (`WIDGET_VERSION` in `mcp_server/mindsort_claude/handlers/resources_dupl.py`). **Confirmed live value is `"10"`** (bumped 9→10 in 99113d1, live since 2026-08-18) — so this bump is **10 → 11**. Report old→new. The safe-area layout change guarantees the artifact changes; the bump is justified by that, not by anything else.
- **Batched into this same rebuild** (widget source, ride the one bump — not themselves reasons for it):
  1. The `App.tsx` doc-comment correction already applied to the working tree (500px is self-imposed, not a guideline).
  2. **The diagnostic log-string correction.** The ResizeObserver still prints `— EXCEEDS ${LAYOUT.maxHeight}px LIMIT`, the last false-attribution instance in the file — the runtime twin of the two comments already fixed, and the exact string PG-Claude deleted after it reported "704px (limit: 500px, EXCEEDS LIMIT)" for a valid height. This is a **message/wording** correction, NOT a logic change: the observer must still log the height as telemetry; it must stop framing a self-imposed number as an "EXCEEDS LIMIT" violation. Use the replacement text left in the ⚠ PENDING comment at the call site. Confirm in the report the log still emits height telemetry, minus the false "LIMIT" framing. Folded here because this rebuild already pays the rebuild+bump cost a string-literal fix would otherwise force on its own.
- Read `doc/OPERATIONS_PREDEPLOY.md` before deploying and check for additional pre-deploy tasks.
- **`committed ≠ live`.** After deploy, verify on the real Claude host (`mindsort-mcp.priority-guard.com`) on **BOTH mobile and web/desktop** (Anthropic states composer overlap happens on both): with the composer focused, the footer button and card content sit inside the safe area and are fully interactive; nothing is occluded. This device/host check is **acceptance of the fix**, not a precondition for it.

---

## 7. Report requirements
1. **Commit hash** for the reviewed round (reviews verify against `git show <hash>:<path>`).
2. The **diff** of the inline `<main>` padding change (and confirmation nothing else on that element changed).
3. Confirmation the discriminating test **failed before** and **passes after**, plus the dynamic-update and no-internal-scroll test results.
4. Explicit confirmation the four preserved invariants in §4 hold (44×44 footer, light/dark, fullscreen untouched, `LAYOUT` constants untouched).
5. The widget cache-bust old→new value, and confirmation the batched comment fix is in the same build.
6. Explicit confirmation **no `clarity/` file and no OpenAI-surface file was modified**.
7. An explicit **"what I did NOT verify"** list (e.g. the live mobile/desktop host acceptance if not yet deployed — report this as outstanding, do not claim it).
8. **Known limitation of the dormant capacity path (record, do not fix).** `LAYOUT.outerPadding: 32` encodes the model's assumption that the root consumes 16px top + 16px bottom. After this fix the rendered root consumes `32 + top + bottom` on inset-bearing devices, so the dormant `computeDetailCapacity` would under-count consumed height there. This is accepted, not a bug today (the model is dormant under `INLINE_SHOW_ALL_ITEMS=true`): correcting it would require either mutating `LAYOUT` (which corrupts the math for the zero-inset case) or plumbing runtime insets into the capacity model (out of scope — touches dormant machinery pre-submission). To be revisited **only if** the rollback flag `INLINE_SHOW_ALL_ITEMS` is ever re-enabled, as part of that rollback increment with the model active and testable. State this in the report so it does not later surface as "the fix broke the rollback."
