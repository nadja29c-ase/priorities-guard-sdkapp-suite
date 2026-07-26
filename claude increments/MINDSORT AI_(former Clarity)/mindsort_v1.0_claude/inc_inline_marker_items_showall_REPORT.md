# Increment 7 — Report: inline marker + "items" label + show-all expansion

**Scope run:** implement, build, tests green, report. **Stopped before deploy.** Item 3's
real acceptance gate is your manual A–E on prod (esp. C: which element scrolls).

**Status: COMMITTED — round hash `0c56ab4`** (on `main`). Verify code against
`git show 0c56ab4:<path>`. OPERATIONS_PREDEPLOY.md read + all MindSort pre-commit checks
passed before commit. Deploy + manual A–E are Nadja's, not done here.

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
rows + header + footer + "+N more clusters"** ≈ **~1000px** (16 items without a summary ≈ ~960px).
That is roughly **2× the former ~500px budget** — the intended auto-fit. It exceeds the old
`maxHeight:500`/`target:480`, so the diagnostic will log "EXCEEDS 500px" — now just a log, not an
action. **Whether ~1000px is compliant depends entirely on manual C** (page scrolls = good;
card nested-scrolls = violation; host clips = revert).

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
- `vitest run`: ✓ **128 passed** (116 pre-existing unchanged + **5 sanctioned updates** + 7 new).

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
