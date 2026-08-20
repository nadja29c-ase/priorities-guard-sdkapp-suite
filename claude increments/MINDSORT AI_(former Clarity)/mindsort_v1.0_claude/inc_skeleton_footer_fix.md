# Increment: Skeleton footer fix (M20 follow-up to efa1ad6)

**Product:** MindSort — **Claude connector only.** Widget: `mcp_server/mindsort_claude/widget-react/`.
**Type:** Widget (React + test) change. **Widget-bytes change → rebuild + `WIDGET_VERSION` bump + cache-bust.**
**Blast radius:** **MindSort-Claude only.** No shared `clarity/`, no OpenAI, no server, no `main.css` change (the CSS from efa1ad6 stays).
**Predecessor:** builds directly on efa1ad6 (the M20 skeleton). This is a **defect fix** to that increment, caught by Codex post-deploy. Implement on top of the current working tree (which already has efa1ad6).

---

## 1. Problem (verified against source, Codex-caught)

The skeleton's footer placeholder (`App.tsx` `!isInitialized` branch — the `justifyContent: 'flex-end'` div with one `ms-skeleton-bar`) renders **unconditionally**. But the loaded inline card's footer is **entirely conditional**:
- The "Open full board" button renders only under `{isFullscreenAvailable && (…)}` in the inline render, and `isFullscreenAvailable = hostContext.availableDisplayModes.includes('fullscreen')`, with `availableDisplayModes` initialised to `[]`.
- The `+N more clusters` overflow indicator renders only when `boardOverflow > 0`.

So on a host that does not advertise fullscreen (with no board overflow), the loaded footer row is **empty** — but the skeleton showed a button-shaped bar. That bar **vanishes on load and the card collapses upward**: exactly the layout seam M20 exists to remove, and exactly what the "forgiving direction" rule was meant to prevent. The original spec asserted the button was "always-present" — **false against source** — and the implementation faithfully built that false premise. The spec is now corrected (§3 of `inc_inline_loading_skeleton.md`); this increment fixes the shipped code.

**This is live** — v12 (efa1ad6) carries the defect.

---

## 2. The fix — drop the footer placeholder entirely

Remove the footer `<div>` (the `marginTop: '12px'`, `justifyContent: 'flex-end'` block containing the single footer `ms-skeleton-bar`) from the `!isInitialized` skeleton branch. **Do not replace it with anything.**

Rationale — **the boundary, stated so it can't be reduced to "skeleton nothing":** the skeleton predicts the *most-likely loaded layout*. Skeleton an element when it will be present in the typical loaded card on this host; omit it when its presence depends on a host/surface capability the skeleton cannot yet observe.

- **Rows ARE skeletoned** even though they're technically conditional (`visibleClusters.length > 0 ? rows : "No clusters yet"`). A cluster is absent only for a **transient data reason** — an empty board, which is rare and resolves the moment the user adds content. The typical loaded card has rows, so predicting rows is correct.
- **The footer is NOT skeletoned.** Its button is absent for a **host-capability reason** (`isFullscreenAvailable`, a property of the surface fixed for the whole session), and its indicator is absent for a data reason (`boardOverflow > 0`, not the typical case). On a host that never advertises fullscreen the footer placeholder is wrong on **every** load, forever — not once on an edge case — and the skeleton renders before `connect()` so `isFullscreenAvailable` is `false`/empty and the footer cannot be predicted from within the skeleton anyway.

The operative distinction is **transient-data-absence (skeleton it) vs. host-capability / atypical-data absence (omit it)** — NOT the binary "conditional vs unconditional," which, applied literally, would also delete the rows (they are conditional too) and gut M20. Do not skeleton what is wrong-forever on a class of hosts; do skeleton the common-case content that a rare transient state briefly lacks.

**Leave everything else in the skeleton untouched:** header placeholder (two bars), the 3 cluster-row placeholders, `aria-busy`, the `role="status"` region, the `aria-hidden` visual wrapper, the flat `16px` padding, all host-token colours. Only the footer block goes.

---

## 3. Second change — sturdier row-count selector (Codex 5b)

The efa1ad6 test that asserts "exactly 3 cluster-row placeholders" counts by `[style*="min-height: 48px"]`. That matches any element sharing that inline value — it's scoped to the skeleton subtree so it isn't wrong today, but it's brittle. Replace the selector with a **dedicated structural marker**: add `data-testid="skeleton-row"` (or a dedicated class) to each of the 3 row shells, and count by that marker instead. This is the only change to the row shells — their styles stay identical.

---

## 4. Hard constraints (unchanged from efa1ad6, restated so they aren't regressed)
- **No `hostContext.safeAreaInsets` / `platform` read** in the skeleton branch. (Removing the footer must not tempt any host-context read.)
- Pulse on bars, never the container. Reduced-motion honoured (no `main.css` change this increment — the class stays).
- `aria-busy="true"`, `role="status"` + `sr-only` string, `aria-hidden` visual tree — all preserved.
- Host tokens for all colours.
- **No** `main.css`, `clarity/`, OpenAI, or server file changes. Only `App.tsx` (skeleton branch) and the test file.

---

## 5. Tests

**Discriminating (fails before, passes after):**
- Assert the skeleton footer bar is **absent**: in the `!isInitialized` render, the footer button-shaped placeholder no longer exists. The cleanest discriminating assertion is on the **count of `ms-skeleton-bar` elements**: efa1ad6 renders 5 bars (2 header + 2×… wait, verify actual count against source before asserting) — read the current skeleton and assert the exact post-fix bar count, which must be the pre-fix count **minus one** (the removed footer bar). This fails against the shipped code (which has the footer bar) and passes after. State the exact numbers in the report.

**Adjust the existing tests from efa1ad6:**
- The "exactly 3 cluster-row placeholders" test: switch its selector to the new `data-testid="skeleton-row"` marker (§3). Assertion count unchanged (still 3); only the handle moves. State the subject is unchanged (row count), only the selector hardened.
- Any efa1ad6 test that asserted the footer bar's presence (if one exists — **check**; the skeleton test may have asserted `ms-skeleton-bar` count `> 0`, which still passes and needs no change) must be updated to the new reality. If the only footer assertion was the aggregate `> 0` count, it still holds; do not manufacture a change.

**Do not** weaken the a11y assertions (`aria-busy`, `role="status"`, `aria-hidden`) — they are unaffected and must stay.

---

## 6. Build / deploy / verify
- Widget-bytes change → **rebuild** (Vite), **verify the built artifact changed** (and that the footer bar is gone from the bundle), **bump `WIDGET_VERSION`** in `handlers/resources_dupl.py`. **Confirmed current committed value is `"12"`** (efa1ad6) → bump **12 → 13**. Report old→new.
- Read `doc/OPERATIONS_PREDEPLOY.md` before deploying.
- **`committed ≠ live`.** Post-deploy on the real Claude host, **both mobile and web/desktop**: confirm the skeleton shows header + rows and **no** footer bar, and transitions cleanly to the loaded card with **no upward collapse** at the footer. This is also the moment to answer the open question: **does the host advertise fullscreen?** (i.e. does the loaded card show "Open full board"?) — record it, because it determines how visible the original defect was.
- **Dark mode** — the skeleton surface unchanged from efa1ad6 except the removed footer; a fresh dark check is cheap and still worth doing since v12's dark acceptance may not have happened before this supersedes it.

---

## 7. Report requirements
1. **Commit hash** for the reviewed round.
2. Diff of the `App.tsx` skeleton branch (footer block removed; row shells gain the test marker) and the test file. Confirm **no** `main.css` change.
3. The exact `ms-skeleton-bar` count before (efa1ad6) and after (this fix) — must be N−1.
4. Confirmation the discriminating footer-absence test fails-before / passes-after; the row-count test still asserts 3 via the new marker; a11y assertions unchanged.
5. `WIDGET_VERSION` **12 → 13**.
6. Confirmation **no `clarity/`, OpenAI, server, or `main.css` file changed**.
7. Explicit **"what I did NOT verify"** — live host render, dark mode, and whether the host advertises fullscreen if not yet checked on-device.
