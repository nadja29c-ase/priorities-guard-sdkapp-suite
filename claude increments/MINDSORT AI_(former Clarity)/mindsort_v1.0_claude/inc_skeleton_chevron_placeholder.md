# Increment: Skeleton chevron placeholder (M20 layout-fidelity — v14, PARKED)

**Product:** MindSort — **Claude connector only.** Widget: `mcp_server/mindsort_claude/widget-react/`.
**Type:** Widget (React + test) change. **Widget-bytes change → rebuild + `WIDGET_VERSION` bump — but DO NOT deploy solo (see §6).**
**Blast radius:** **MindSort-Claude only.** No shared `clarity/`, no OpenAI, no server, no `main.css` change.
**Predecessor:** builds on d38601f (v13, the footer-fix). Implement on top of the current working tree.

---

## 1. Problem (verified against source, Codex-caught round 2)

The skeleton cluster-row placeholders omit the **chevron** that the loaded `ClusterRowToggle` renders as its **first child, unconditionally**. On load, every row's content shifts right by ~20px (12px icon + 8px gap), on every board, on every host. This is the mirror image of the v12 footer defect: that one *included something conditional* (collapse-upward on load); this *omits something unconditional* (shift-right on load). Same "mirror the most-likely loaded layout" rule, opposite error.

**This is the ONLY unconditional element the skeleton omits** — established by an exhaustive element-by-element diff (see §2). Requirement ID: **M20** (`DOC-CONSTRAINT`).

---

## 2. Exhaustive diff — asserted as a claim about what was checked

This is the important part of the increment: **not "add the chevron," but "the full structural comparison was done and the chevron is the only row-level omission."** Do not treat this as a single-element fix — treat it as closing the diff. If this section is right, there is no round-3 finding.

**All six `ClusterRowToggle` children compared against the skeleton row, in order:**
| # | Loaded element | Conditional? | Skeleton | Correct? |
|---|---|---|---|---|
| 1 | chevron span (12×12 SVG) | **unconditional** | **omitted** | **✗ — this fix** |
| 2 | priority badge | `hasPriority && rank && colors` | omitted | ✓ forgiving |
| 3 | inherited-rank sr-only text | `inheritedRank` | omitted | ✓ forgiving |
| 4 | name span (`flex:1`) | unconditional | `flex:1` name bar | ✓ |
| 5 | tag icon | `hasTags` | omitted | ✓ forgiving |
| 6 | thought count | unconditional (`{sum ?? 0} item(s)`) | 28px count bar | ✓ |

**Row SHELL properties (not just children — this is where the last near-miss lived):**
- `borderLeft`: loaded row is `effectiveRank && borderColors ? '3px accent' : '0.5px tertiary'` — **conditional**. Skeleton uses the `0.5px` tertiary form → a prioritized row gains a 3px accent on load (+2.5px, forgiving direction). **Correctly omitted.**
- Container `padding`: loaded inline `<main>` uses M3 inset padding (`16 + safeAreaInsets.*`); skeleton uses flat `16px`. **Deliberate by design** — the skeleton renders before `connect()`, so insets are unknown; reading them would consume undefined-derived state. Not a defect.

**Header (both children):** `<h2>` title (unconditional) + count `<span>` (unconditional), `space-between`, `marginBottom:12px` — skeleton mirrors both with title bar + count bar. **No header defect.**

**Loaded footer wrapper (Codex round-2 Finding 1 — REJECTED, recorded as a decision):** the loaded footer `<div>` renders unconditionally with `marginTop:'12px'` and an always-present overflow `<span>` (empty string when `boardOverflow === 0`), so the loaded card carries ~12px the skeleton doesn't reserve. **Do NOT reserve it.** This is the *forgiving direction* (content grows downward on load — "settles outward"), which the rule prefers. Reserving it means skeletoning an empty wrapper whose visible content (overflow text, fullscreen button) is conditional — which walks straight back into the v12 footer defect we spent two rounds removing. Leaving it is the correct call, not an oversight.

**Conclusion:** the chevron is the single unconditional omission. Everything else is either correctly-dropped-conditional or deliberate-by-design. This increment closes the diff.

---

## 3. The fix — add a chevron placeholder to each skeleton row

Add a **12×12 placeholder element as the first child** of each skeleton row, before the name bar, mirroring the loaded chevron's geometry (verified against source):
- The loaded chevron span is `display:flex, alignItems:center, justifyContent:center, flexShrink:0` wrapping a 12×12 SVG, and it is the button's first child with the parent's `gap:8px` after it.
- So the placeholder is a **12×12 element with `flexShrink:0`**, placed before the name bar. **`flexShrink:0` is load-bearing** — without it the placeholder compresses at narrow widths and the horizontal shift reappears exactly where the fix was meant to remove it.
- It may be a `ms-skeleton-bar` (so it pulses with the rest) or a static token-filled box — either is fine; if it's a `ms-skeleton-bar` it counts toward the bar total (see §5). Keep it visually a small square/dot, not a wide bar, to read as the chevron's footprint.
- **No a11y delta:** the whole skeleton visual tree is already `aria-hidden`, and the real chevron is itself `aria-hidden`, so nothing changes for AT.

Leave everything else in the row untouched — the `data-testid="skeleton-row"` marker, the name bar (`flex:1`), the count bar, the shell styling all stay exactly as they are.

---

## 4. Hard constraints (unchanged, restated so they aren't regressed)
- Only the chevron placeholder is added. Do NOT touch the header, the footer decision, the flat padding, the `borderLeft`, or the row shell's other styles.
- No `hostContext.safeAreaInsets` / `platform` read in the skeleton branch.
- Pulse-on-bars-never-container, reduced-motion, `aria-busy`, `role="status"`, `aria-hidden` tree, host-token colours — all preserved.
- No `main.css`, `clarity/`, OpenAI, or server file changes. Only `App.tsx` (skeleton branch) and the test file.

---

## 5. Tests — RE-PROBE the counts, do NOT hard-code them from arithmetic

⚠️ **Adding a chevron bar per row changes two hard-coded numbers in the current tests: the total bar count (currently 8) and the in-rows count (currently 6).** Arithmetic *suggests* 8+3=11 total and 6+3=9 in-rows **IF** the chevron is implemented as a `ms-skeleton-bar`. **DO NOT trust that arithmetic — verify against the rendered DOM.** This is exactly where the last round nearly shipped a wrong number: `grep -c` said 5 bars, the DOM said 9, and only probing the rendered output caught it. A test that hard-codes "assert 11" ships a wrong number the moment the reasoning slips or the chevron is implemented as a non-`ms-skeleton-bar` element.

**Instructions:**
- **Render the skeleton and probe the actual `.ms-skeleton-bar` count and the in-rows count from the DOM.** Update the discriminating test's two numbers to the *measured* values, and state both measured numbers in the report.
- **Tighten the row-structure assertion (folds in Codex round-2 Finding 2):** assert each `skeleton-row` now contains the chevron placeholder as its first child — a structural assertion that pins the fix, so a regression that drops the chevron again is caught. If the chevron is a `ms-skeleton-bar`, assert the per-row bar count is now 3 (chevron + name + count); if it's a static element, assert its presence structurally. Whichever, the assertion must **fail against v13** (no chevron placeholder) and **pass after**.
- The `flex-end === 0` footer assertion stays (footer still absent). The 8→N total-bar assertion updates to the measured N.
- Do NOT weaken the a11y / token / flat-padding assertions.

---

## 6. Build / deploy — WRITTEN NOW, PARKED. Do NOT deploy solo.
- This is a widget-bytes change, so when it *does* ship it needs: rebuild (Vite), verify the built artifact changed, **bump `WIDGET_VERSION`** in `handlers/resources_dupl.py` (**confirmed current committed value is `"13"`** → 13 → 14), report old→new.
- **DEPLOY GATE — explicit, not just conversational:** do **NOT** deploy this on its own. Deploy it **only** (a) batched with the next widget change whenever that occurs, **or** (b) together with whatever the pending **v13 on-device pass** surfaces. Rationale: v11/v12/v13 have all shipped with zero on-device verification; a solo deploy for a ~20px text shift is exactly the cycle we're avoiding. The next implementer must not read this as a normal increment and bump to v14 out of habit.
- **The higher-priority action is the on-device pass on v13** (live now), which carries FOUR questions worth answering in one sitting — and which no code review can reach:
  1. **Does the host advertise fullscreen?** (sets the v12 footer defect's real severity in hindsight — if the host never advertises it, that defect manifested on every load; if it does, it was minor.)
  2. **Is the skeleton visible at all, or does it flash past?** If load resolves in ~80ms the skeleton is imperceptible and this entire three-round exercise was polish on something no user sees. This is the single highest-value unknown.
  3. **Do the bars render correctly in dark mode?** ("Uses tokens" is verified in source; "visible and correctly tinted in dark" is not — a new rendering surface.)
  4. **Does the safe-area padding (M3, v11) behave with the composer focused**, on both mobile and web/desktop?

---

## 7. Report requirements
1. **Commit hash** for the reviewed round.
2. Diff of the `App.tsx` skeleton row (chevron placeholder added as first child) and the test file. Confirm no other skeleton element changed.
3. The **measured** (not derived) `.ms-skeleton-bar` total and in-rows counts, post-fix.
4. Confirmation the tightened row-structure test fails-before / passes-after; a11y/token/padding assertions unchanged.
5. `WIDGET_VERSION` **13 → 14** (only when deployed — if parked, state it's not yet bumped/deployed).
6. Confirmation **no `main.css`, `clarity/`, OpenAI, or server file changed**.
7. Explicit **"what I did NOT verify"** — and confirm the deploy gate (§6) is respected: not shipped solo.

---

## 8. Bundled comment-only correction: the `role="status"` rationale is FALSE

Fold this in when implementing v14 (comment-only, therefore bundle-neutral — comments strip in minification, so it costs no separate deploy).

**The claim to correct:** the skeleton's `role="status"` region is documented — in the code comment AND in d38601f's commit message — as "load-bearing for the RE-ENTRY case (`handleViewRemainingContent` sets loading again while mounted)." **This is false, verified against source:** `setIsInitialized` is called only with `true`, at `App.tsx:388` and `:395` (both inside `ontoolresult`), and is never reset to `false`. So the `!isInitialized` skeleton branch renders **exactly once, at first mount, and is never re-entered.** `handleViewRemainingContent` sets `isLoadingBoard` (which feeds the overflow row's `isLoading` prop) — a different state that does NOT re-enter the skeleton branch. There is no re-entry path.

**The accurate rationale (replace the false one):** `role="status"` announces when its content *changes while it is already in the accessibility tree*. This skeleton mounts with its text already present and unmounts without ever changing — the exact case NVDA/JAWS/VoiceOver skip. So it announces in **NO** case here, not merely "not guaranteed at first mount." **Keep the markup** — it is inert, costs nothing, and would correctly announce IF the branch ever became re-enterable (e.g. a future increment makes loading a revisitable state). But state the reason truthfully: it is a correct-but-currently-silent affordance kept for a hypothetical future re-entry, NOT a currently-load-bearing one.

**Consequence for the compliance record (carry into the on-device pass and the assessment):** M2's a11y credit for the skeleton is weaker than recorded. The assessment must NOT lean on "the loading state is announced." What actually ships is `aria-busy` plus a visually-hidden string that may never be spoken. If Q1 (on-device) shows the skeleton flashes past, this compounds: a once-only, imperceptible, unannounced surface — which retires M20 and this parked chevron fix together.
