# Increment 6 — Report: MindSort-Claude fullscreen width + density

**Scope run:** Option (a) — implement, build, tests green, report. **Stopped before deploy.**
Nadja owns the deploy gate; manual checks A–H happen on prod on her side.

**Status: COMMITTED — round hash `ad4608f`** (`ad4608ff637c58b1bdc5eb1764b474deabb932a0`,
on `main`). Verify against `git show ad4608f:<path>`. OPERATIONS_PREDEPLOY.md read + all
MindSort pre-commit checks passed before commit. Deploy is Nadja's, not done here.

---

## Files changed (5)
- `mcp_server/mindsort_claude/widget-react/src/App.tsx` — fullscreen components only + §1 attribute effect
- `mcp_server/mindsort_claude/widget-react/src/main.css` — §1 `#root` cap scoping
- `mcp_server/mindsort_claude/handlers/resources_dupl.py` — `WIDGET_VERSION` 6→7
- `mcp_server/mindsort_claude/widget-react/src/test/App.test.tsx` — 8 new tests (appended)
- `mcp_server/mindsort_claude/widgets/mindsort-dashboard-claude.html` — rebuilt bundle (artifact)

Nothing outside App.tsx / main.css / the WIDGET_VERSION line was changed (plus the
added tests and the rebuilt bundle artifact, both expected).

---

## §1 WIDTH — approach chosen

**Chosen: option (a)** — scope the `#root` cap to inline via a `data-display-mode`
attribute, stamped on `<html>` (`document.documentElement`).

- `main.css`: base `#root { width:100%; margin:0 auto }` (no cap). Cap moved to
  `html:not([data-display-mode="fullscreen"]) #root { max-width: 600px }`.
- `App.tsx`: a `useEffect` on `displayMode` sets `data-display-mode` on `<html>`.
- **Default-safe:** the attribute is absent on first paint → `:not(...fullscreen)` matches
  → inline renders capped. Only explicit fullscreen frees the width. Inline never flashes
  uncapped.

**Why `<html>` not `#root`:** §1 sanctions "on `#root`/`<html>`". `<html>` is observable in
jsdom (the `#root` mount node isn't the React tree in tests), which makes the gate testable.
In prod `<html>` always exists; the CSS still targets `#root`.

**No new fixed board width.** The board container is `width: 100%`; columns come from the
grid, not a board width. Verified in the bundle and by Test 2.

**Effect hardening (post-review, both directions of the mirror-image bug):**
- **`useLayoutEffect`, not `useEffect`** — runs before paint, so a fullscreen-initial mount
  (`getHostContext()` → 'fullscreen' in `onAppCreated`) never flashes the capped/narrow board
  for a frame before widening. (Inline-direction first-paint was already safe: absent = capped.)
- **Cleanup removes the attribute on unmount** — absent = inline-capped (safe default). A widget
  that unmounts while fullscreen (Claude iOS resource-teardown / instance supersession) cannot
  strand `data-display-mode="fullscreen"` on a shared `<html>` and silently uncap a later inline
  card. State-change paths already re-stamp correctly (every inline-return calls
  `setDisplayMode('inline')`; host-initiated exit via `onhostcontextchanged` at App.tsx:301).
- **Test 1b** locks the host-initiated-exit clearing path (the forward-test blind spot).

### Grid / columns (§1) — 240px kept
`repeat(auto-fit, minmax(240px, 1fr))`, gap 12px. **Kept 240px** — required by inc-4 Test 1,
matches the OpenAI reference, and §1 says keep unless testing shows otherwise.

**Computed column counts** (model, not measured — real measurement is manual-A on prod,
assuming board content width ≈ viewport − 40px container padding):

| Viewport | ~content width | computed columns | ~card width |
|---|---|---|---|
| 1280px | ~1240px | **4** | ~301px |
| 1440px | ~1400px | **5** | ~264px |
| 1920px | ~1880px | **7** | ~247px |

**Honest flag (refined post-review):** the "3–4 columns at common desktop widths" target is met
at ~1280px (the width the density comparison was made at). At 1440/1920 the 240px min yields
more columns. The parity claim needs a precise caveat: the **minmax value** matches OpenAI
(240px), but the **rendered result** does not at wide viewports — OpenAI caps its board at
~900px, so it never reaches 7 columns, whereas our unconstrained fullscreen at 1920px produces
a density OpenAI never shows. At 7 columns each ~250px card holds name+summary+thoughts+
subclusters+tags, which likely reads **too dense** — the guidelines' "balance density with
readability" cuts against it. I kept 240px (required by inc-4 Test 1 + §1 "keep unless testing
shows otherwise") and did **not** add a max card width, but I now expect **manual-A at 1920px
to show it as too dense**. The cheap, correct lever is a card `max-width` (~400px) — flagged as
a design decision for you after you see it on prod, not applied here.

---

## §2 TYPOGRAPHY — token scale, line-height sweep done

All fullscreen font sizes are now token vars on the **12/14** scale (16 unused — no md text
needed). No off-scale literal remains; enforced by Test 3.

| Element | Was | Now |
|---|---|---|
| Thought text (normal/small) | 13px / 12px, lh 1.5 | `--font-text-xs-size` (12px), lh 1.4 |
| Cluster summary | 13px, lh 1.5 | 12px, lh 1.4 |
| Cluster name / Board title | 14px | 14px (kept, tokenized), lh 1.4 |
| Subcluster name | 14px | 12px (subordinate), lh 1.4 |
| Board subtitle | 14px | 12px |
| Count pill (subcluster) | 11px | 12px |
| Priority badges (thought/subcluster) | 9/10px | 12px |
| Tag pill | 11px | 12px |
| Large-board notice | 13px | 12px |
| Minimize button | 13px (off-scale) | 14px (test-3 required; geometry untouched) |
| Placeholder "Loading…" | 13px | 12px |

**Line-height sweep (as requested):** I set an explicit `line-height` token on **every**
fullscreen text element — including the ones NOT in the §2 table (tag pills, count pills,
priority badges, large-board notice, placeholder, minimize button). None inherit the global
`body { line-height: 1.5 }` anymore. Body's 1.5 is unchanged (inline depends on it). Test 3
fails if any inline `line-height: 1.5` reappears.

**Weights:** unchanged — only `font-weight: 500` explicit + default 400. No 600/700 (Test 8).

---

## §3 DENSITY — targets applied, deviations noted

All §3 target values applied as written. `minHeight: 120px` removed from the cluster card.
Radii tokenized (board container + cluster card → `--border-radius-xl`; count/tag pills →
`--border-radius-full`). No literal 16px radius remains (Test 5).

**Shadow decision:** `--shadow-lg` → **`--shadow-sm`** (fallback `0 1px 2px 0 rgba(0,0,0,.05)`).
Reasoning: cards already carry a 1px border for figure/ground on the tinted board; at reduced
padding + 12px radius, `lg`'s large blur read heavy and inflated perceived inter-card spacing,
working against density. `sm` keeps a subtle lift. **This is the one call best confirmed
visually — flagged for your manual B/G.** (Could go to `md` if `sm` reads too flat.)

**No target made anything cramped** in review, so no §3 target was backed off. Readability
(manual C) is your visual gate on prod.

---

## §5 TOKEN AUDIT — every token + fallback

| Token | Fallback | Used for |
|---|---|---|
| `--font-text-xs-size` | 12px | thought/summary/subtitle/subcluster-name/badges/pills/notice/placeholder/footer |
| `--font-text-sm-size` | 14px | board title, cluster name, empty-state, minimize button |
| `--font-text-xs-line-height` | 1.4 | all xs text |
| `--font-text-sm-line-height` | 1.4 | all sm text |
| `--border-radius-xl` | 12px | board container, cluster card |
| `--border-radius-md` | 8px | subcluster card (pre-existing, unchanged) |
| `--border-radius-full` | 9999px | count pills (cluster+subcluster), tag pill |
| `--shadow-sm` | `0 1px 2px 0 rgba(0,0,0,0.05)` | cluster card |

**Deliberately non-tokenized literals (with reason):**
- **Spacing (12/16/10/8/6/4/3/2/1 px):** §5's confirmed-real token list covers font-size,
  line-height, radius, shadow, font-sans — **no spacing-scale tokens exist**, so spacing stays
  as px literals per the §3 target table. Consistent with existing code.
- **Priority-badge radius 3px / 4px:** no token at that scale; §3 didn't target them; Test 5
  only bans the 16px literal + the non-existent 2xl. Left as-is.
- **Minimize button `minHeight: 36px`, svg 14px:** see flag below.

`--border-radius-2xl` — **not referenced** anywhere (only named in a comment explaining it
doesn't exist). Test 5 enforces.

---

## ⚠️ Flags for your decision (RULE 0a — reporting, not fixing)

1. **Minimize button is a pre-existing HARD-CONSTRAINT violation, not just a manual-F item**
   (`minHeight: 36px`, FullscreenHeader). "Minimum tap target: 44 x 44pt" is in the guidelines'
   **constraint** list, not the guidance list — so 36px is a genuine compliance gap, and it
   should be **logged as a known gap to fix** (a small separate fix), not merely eyeballed. It
   predates this increment and is outside §2/§3 scope; my density changes touched **zero**
   interactive targets, so I introduced no new 44pt risk. Only renders when `!hostFullscreen`
   (real host provides native close, so usually absent). NOT changed here (RULE 0a).

2. **inc-4 Test 2 now passes coincidentally.** It asserts the board style `toContain('16px')`
   with the *intent* of the old 16px radius. The radius is now `--border-radius-xl` (12px), but
   the new container **padding** is `16px 20px`, so `'16px'` still matches. Test stays green,
   unmodified (keeping "inc 1–5 tests unchanged" literally true). New Test 5 provides the
   correct radius coverage going forward. Candidate for a future cleanup — not touched here.

3. **Two pre-existing `tsc` errors** at `App.test.tsx:1413` (`fireEvent`/`waitFor` declared but
   unused, in inc-fullscreen Test 3). Confirmed present on committed `HEAD` with my changes
   stashed — **not introduced by this increment**, and in code outside my scope. Not fixed.
   (The `test`/`build` scripts don't run `tsc`, so they're green; `tsc --noEmit` reports them.)

---

## Version + URI (mandatory)
- `WIDGET_VERSION`: **"6" → "7"**
- **OLD URI:** `ui://mindsort-claude/dashboard-v6.html`
- **NEW URI:** `ui://mindsort-claude/dashboard-v7.html`
- Verified different. New bundle contains the `data-display-mode` gate + `border-radius-xl`.

## Build + tests
- `vite build`: ✓ clean (171 modules) → `widgets/mindsort-dashboard-claude.html`
- `vitest run`: ✓ **130 passed** (121 pre-existing unchanged + 9 new).
- Tests 1–8 + 1b (this increment) all green; each carries its "Catches:" line.
- Inc 1–5 inline + fullscreen behaviour tests: pass **unchanged**.

## Tests 1–8 — what each catches
1. `data-display-mode` = fullscreen in fullscreen / inline otherwise — width gate; catches inline widening or cap winning.
1b. Host-initiated exit re-stamps `inline` — catches a stuck `fullscreen` attribute (mirror-image bug) that forward tests miss.
2. No fixed board `max-width`; auto-fit minmax(240px) — catches one fixed width swapped for another.
3. On-scale fonts only, no `line-height:1.5` — catches off-scale type returning.
4. Cluster card has no `min-height` — catches the stretch regression.
5. No `16px` literal radius, no `border-radius-2xl` — catches off-scale radius.
6. Inline keeps its gate + count + accordion — catches density leaking into inline.
7. Fullscreen behaviour preserved (tags-last, no header count, colour badges, footer, nesting bg) — catches accidental behavioural change.
8. No glyphs, only 400/500 weights, clean imports — catches recurring regressions.

## NOT done in this run (yours, post-hand-back)
- Manual checks A–H on prod (width at 1280/1440/1920, density vs OpenAI screenshot,
  readability, large board, long content/localization, **44pt incl. the flagged button**,
  dark mode, before/after screenshots).
- Read `OPERATIONS_PREDEPLOY.md` before commit; commit (→ hash); deploy; fresh convo to
  bust the v7 cache; re-run A–H on prod.
