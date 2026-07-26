# Increment 7 — Report: inline marker + "items" label + show-all expansion

**Scope run:** implement, build, tests green, report. **Stopped before deploy.** Item 3's
real acceptance gate is your manual A–E on prod (esp. C: which element scrolls).

**Status: COMMITTED — round HEAD `701c486`** (on `main`). Two code commits:
`0c56ab4` = the increment; `701c486` = post-review fix (detail-row un-clamp + aria).
**Verify code against `git show 701c486:<path>`.** OPERATIONS_PREDEPLOY.md read + all MindSort
pre-commit checks passed before each commit. Deploy + manual A–E are Nadja's, not done here.

---

## Files changed
- `mcp_server/mindsort_claude/widget-react/src/App.tsx` — items 1–3 (inline only; item 2 also
  touches fullscreen count text, already "items")
- `mcp_server/mindsort_claude/widget-react/src/test/App.test.tsx` — 7 new tests + 5 sanctioned updates
- `mcp_server/mindsort_claude/handlers/resources_dupl.py` — `WIDGET_VERSION` 7→8
- `mcp_server/mindsort_claude/widgets/mindsort-dashboard-claude.html` — rebuilt bundle (artifact)

No `main.css` change (as the brief expected). Nothing outside App.tsx / tests / the
WIDGET_VERSION line.

## Item 1 — inline thought marker → left bar
`DetailRow` thought rows now use a **left vertical border bar** reusing `FullscreenThoughtItem`'s
exact weights + colours (`4px` prioritized rank-border / `2px` `--color-border-tertiary`), and the
former circle/target SVG + its 16px icon column are **removed for thoughts only**. Summary and
subcluster rows keep their document/folder icons (unchanged), per the brief's "thought marker only".

**Decision stated (brief delegated "decide and state"):** I kept the inline row's card treatment
(background, `border-radius`, `padding`, fixed 36px height) and only swapped the marker. The bar
matches fullscreen on **side + weight** (the Test-E criterion); it does not strip the inline row's
card background the way bare fullscreen rows have none — that's a deliberate kept difference, not an
oversight.

**⚠️ Flag (per §1 "flag, don't silently restyle"):** the expanded list now mixes markers — thought
rows = coloured left bar + no icon; summary/subcluster rows = icon + no bar. That is exactly the
brief's scope (thought-only), but whether the mix reads as intentional is a **visual call for manual
E**. I did not restyle summary/subcluster. If you want them unified, that's a follow-up decision.

## Item 2 — counts "thoughts" → "items"
Renamed the **4 user-visible count/aria strings**, singular/plural preserved:
- inline header `{thoughtCount} thoughts` → `items`
- inline cluster row (`ClusterRowToggle`) `{sum_thought_items} thoughts` → `items`
- inline detail subcluster count `{count} thoughts` → `items`
- inline detail `aria-label` `, ${count} thoughts` → `items`

Fullscreen counts already said "items" (verified). Per your decision, the **two descriptive prose
strings keep "thoughts"** — fullscreen subtitle "Your thoughts grouped into clusters…" and inline
empty-state "…organizing your thoughts!" — and Test 2 is scoped to counts (a number followed by
"thoughts") rather than the literal "no 'thoughts' anywhere". Grep confirms the only rendered
"thought" strings left are those two prose lines + the `type: 'thought'` model literal.
**No variable/field/type names changed.**

## Item 3 — show-all behind `INLINE_SHOW_ALL_ITEMS` (phased, dormant machinery kept)
- New module const **`INLINE_SHOW_ALL_ITEMS = true`**. When true: `visibleDetailUnits = detailUnits`
  (all units), `hiddenDetailUnits = []`, `hasDetailOverflow = false` (no "View remaining" control).
- The capacity slice (`finalDetailCapacity`, `computeDetailCapacity`), `OverflowActionRow`, and the
  `hasDetailOverflow` render path all **remain in the module, dormant**. Rollback = flip the flag to
  `false` (one line).
- **ResizeObserver is diagnostic-only under show-all:** it still logs
  `[MindSort Diagnostic] Inline main scrollHeight: {height}px` every resize, but an early
  `if (INLINE_SHOW_ALL_ITEMS) return` prevents it calling `setGuardedDetailCount` (no row stripping).
  The row-stripping stays wired for the flag=false path.
- **No nested scroll introduced by our code:** the inline `<main>` (`width/background/border-radius/
  padding/touchAction:pan-y/overscrollBehavior:contain`) and the detail region (`marginTop/flex/gap`)
  set **no `overflow:auto|scroll` and no `maxHeight`**. Confirmed by audit + Test 5. (Per-row
  `DetailRow` keeps its fixed 36px + 1-line clamp — that's per row, not a scroll container.)

### Worst-case expanded height (from `LAYOUT`, as §3 asks)
A 16-thought cluster **+ summary (17 detail rows @36px+4gap) + expanded row + 2 sibling collapsed
rows + header + footer + "+N more clusters"** ≈ **~1000px** at one line per row (16 items without a
summary ≈ ~960px). That is roughly **2× the former ~500px budget** — the intended auto-fit. It
exceeds the old `maxHeight:500`/`target:480`, so the diagnostic will log "EXCEEDS 500px" — now just
a log, not an action. **Whether it is compliant depends entirely on manual C** (page scrolls = good;
card nested-scrolls = violation; host clips = revert). **NOTE (post-review):** rows now WRAP to full
text (see below), so real row height is variable and typically **taller** than the 36px-per-row
estimate — the ~1000px figure is a floor. This makes manual C even more the gate; the diagnostic
`scrollHeight` log gives the true number on prod.

## Post-review fix (reviewer-found clamp bug) — follow-up commit
Adversarial review found a **real bug** that this increment exposed: `DetailRow` still clamped every
expanded item to a single 36px line (`height`/`maxHeight` + `white-space:nowrap` + `text-overflow:
ellipsis`), so show-all listed all items but truncated the long ones — the founding "hidden content"
complaint reappearing one level down. Fixed:

- **Un-clamp under show-all, all 3 row types** (thought/summary/subcluster): rows drop the fixed
  height (→ `minHeight` + grow), text drops `nowrap`/`ellipsis` and wraps with `overflow-wrap:
  anywhere`; `align-items` → `flex-start` so marker/badge top-align with line 1. Now matches
  `FullscreenThoughtItem`.
- **Gated on `INLINE_SHOW_ALL_ITEMS`** (the key safety point): the fixed 36px is load-bearing for the
  DORMANT capacity model (`computeDetailCapacity` assumes `detailRowH`). Un-clamping only under
  show-all keeps the **flag=false rollback path byte-faithful** to the 36px model it depends on —
  the one-line rollback stays correct.
- **aria miss fixed:** fullscreen thought `<ul>` `aria-label` "Thoughts in {cluster}" → "Items in
  {cluster}" — an item-2 completeness miss the review caught (item 2 listed aria-labels).

Decision on scope (yours): all three types wrap. Two new tests added (wrap-on-style, aria).

## ⚠️ Regression + root cause (test-coverage loss, found by Codex — now fixed)
A second Codex adversarial pass caught that the inc-7 commit `0c56ab4` **silently deleted 9 inc-6
tests** (the `Fullscreen width + density` block) **and** reverted my inc-6 fix to inc4-Test-2 (the
radius assertion) — 239 deletions in `App.test.tsx` I never scrutinized. My earlier "116 pre-existing
unchanged" claim was **false**.

**Root cause:** the `App.test.tsx` I edited at inc-7 start was a **stale, pre-inc-6 buffer** — almost
certainly the IDE re-saving an open pre-inc-6 version of the file over the committed one on disk. I
did **not** `git diff` the large committed test file against HEAD before editing, so the stale copy
overwrote committed work without a trace, and my inc-7 commit captured the deletion. The tell was
visible and I missed it: the inc-7 baseline suite ran **121** tests while inc-6 ended at **130**. The
inc-6 *source* (main.css cap-scoping, App.tsx `data-display-mode` effect) was never affected — only
the test file. Every prior review passed against the *code*; the regression lived in an unexamined
test file, which is exactly why an adversarial pass on the committed tree caught what code review
could not.

**Fix (this follow-up):** restored the fullscreen block byte-for-byte from `098791a` (one sanctioned
deviation: `/8 thoughts/` → `/8 items/`, the inc-7 rename — triaged as a legitimate label change, not
a code revert), and re-applied the inc4-Test-2 token-radius fix. Suite 130 → **139**, green. Test-only;
no source/bundle change (`WIDGET_VERSION` stays 8).

**Standing practice adopted:** before editing any large committed file, `git status` / `git diff` it
against HEAD first, so a stale working copy can never silently overwrite committed work again.

## Compliance preserved
Remaining icons are monochrome outlined SVG; no Unicode glyphs; Claude tokens + inline styles;
`fontWeight` 400/500; read-only; `var(--token, #hex)` fallbacks. No `@openai/apps-sdk-ui`, no
`window.openai`.

## Version + URI
- `WIDGET_VERSION`: **"7" → "8"**
- OLD URI: `ui://mindsort-claude/dashboard-v7.html`
- NEW URI: `ui://mindsort-claude/dashboard-v8.html` — verified different.

## Build + tests
- `vite build`: ✓ clean (171 modules) → 510KB inlined bundle.
- `vitest run`: ✓ **139 passed**. Composition (corrected — see regression note): the inc-6
  fullscreen width+density block (9 tests) + my inc-6 inc4-Test-2 radius fix had been **silently
  reverted** by a stale test-file buffer at inc-7 start and were absent at `0c56ab4`/`701c486`;
  both are now **restored** (block byte-identical to `098791a` except one sanctioned `/8 items/`
  rename). Net: pre-existing inc 1–6 (incl. the restored 9) + 5 sanctioned inc-7 updates + 9 new
  inc-7 tests = 139, all green. The restored fullscreen tests pass under inc-7 code, confirming
  inc-7 introduced no fullscreen regression.

### Tests 1–7 (new) — each with its Catches
1. Inline thought row = left bar (4px prioritized / 2px not), no circle/svg icon — marker parity.
2. Counts say item/items (singular/plural); no "N thoughts" count (prose unaffected) — rename/vocab.
3. Data model still reads `sum_thought_items` / `thought_items` — display-only rename.
4. Expanded cluster renders every unit; no overflow control — cap bypassed.
5. `<main>` + detail region set no `overflow:auto|scroll` / `maxHeight` — no nested scroll.
6. `computeDetailCapacity` still exported + functional — machinery dormant, not deleted.
7. Accordion one-open; siblings stay collapsed — no sibling-growth regression.

### Test 8 (meta) — sanctioned inc 1–6 changes
All inc 1–6 tests pass except **5** that asserted the now-removed cap/count wording, each changed
by design:
- `renders cluster names when no priorities exist`: `/25 thoughts/` → `/25 items/` (item 2).
- `renders empty state message when no clusters`: `/0 thoughts/` → `/0 items/` (item 2).
- `inline card still shows cluster/thought count`: `/8 thoughts/` → `/8 items/` (item 2).
- `shows "View remaining cluster content" when content overflows` → inverted: **all items show, no
  overflow control** (item 3).
- `shows overflow control even with zero capacity` → inverted: **all items show, no control,
  siblings collapsed** (item 3).
The `computeDetailCapacity` pure-function unit tests are **unchanged and still green** — they prove
the machinery survives (Test 6 corroborates).

## ⚠️ Pre-existing, not mine
Two `tsc` unused-var warnings at `App.test.tsx:1422` (`fireEvent`/`waitFor` in an inc-fullscreen
test) — pre-existing since inc 6 (line shifted by my additions), untouched code, not fixed.

## NOT done in this run (yours, post-hand-back)
- **Manual A–E on prod — item 3's real gate.** Especially **C**: expand a 12–16 item cluster and
  record which of the 3 outcomes occurs (record max `[MindSort Diagnostic] scrollHeight`, and
  **explicitly which element scrolls: page = compliant; card = nested-scroll violation; clip =
  revert**). E: confirm the thought bar matches fullscreen and judge the mixed-marker look.
- Read `OPERATIONS_PREDEPLOY.md`; commit (→ hash); deploy; fresh convo (v8 busts cache); run A–E.
- If C = outcome 1: schedule the follow-up cleanup increment to delete the dormant machinery.
  If C = outcome 2 (clip): `INLINE_SHOW_ALL_ITEMS = false`, redeploy. If C = outcome 3 (card
  scroll): fix the offending style before shipping.
