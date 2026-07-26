# Increment 4: MindSort-Claude fullscreen — board shell & primitives alignment

**App:** MindSort AI for Claude (`mcp_server/mindsort_claude/`). Fullscreen widget view.
**Type:** PURELY PRESENTATIONAL, follow-on to increment 3. Aligns the board SHELL (container, grid, header, footer) and the PRIMITIVES (tag pill, card borders) with the OpenAI MindSort board. NO logic, data, display-mode, or behavioral changes.
**Touches:** `mcp_server/mindsort_claude/widget-react/src/App.tsx` (fullscreen components only) + `WIDGET_VERSION` in `handlers/resources_dupl.py`. Nothing else.

**Status: QUEUED — not urgent.** Increments 1–3 are shipped. This closes the remaining visual gaps found in a second structural diff against the OpenAI board. All decisions are made — there are no open questions; implement as specified.

## Why this exists
Increment 3 aligned the CARD components (cluster card, subcluster card, thought item) and was derived only from `clarity/.../components/{ClusterCard,SubclusterCard,ThoughtItem}.tsx`. It never covered the board SHELL (`clarity/widget-react/src/App.tsx`), the `Header` component, or the badge/pill primitives — so those deviations remain. This increment closes them.

## Reference source (read ALL of these before implementing — READ ONLY, never import)
- `mcp_server/clarity/widget-react/src/App.tsx` (board shell: container, grid, empty state, footer)
- `mcp_server/clarity/widget-react/src/components/Header.tsx`
- `mcp_server/clarity/widget-react/src/components/TagPill.tsx`
- `mcp_server/clarity/widget-react/src/components/PriorityBadge.tsx`
- `mcp_server/clarity/widget-react/src/components/ClusterCard.tsx` (border treatment)

Target: `FullscreenBoardView`, `FullscreenClusterCard`, `TagPill` in `mcp_server/mindsort_claude/widget-react/src/App.tsx`.
Before commit: read `OPERATIONS_PREDEPLOY.md` ("Widget Bundle Changes").

---

## DECIDED — implement these

### 1. Grid column width: 320px → 240px
OpenAI: `grid gap-4 grid-cols-[repeat(auto-fit,minmax(240px,1fr))]`.
Claude currently: `minmax(320px, 1fr)`. **Change to 240px.** Gap stays 16px (already matches `gap-4`).
This is the largest remaining layout difference — at the same width OpenAI fits noticeably more columns.

### 2. Board container: tinted rounded card, not plain white page
OpenAI `<main>`: `bg-surface-secondary rounded-2xl px-8 py-6` — a SECONDARY-surface rounded container, 32px horizontal / 24px vertical padding.
Claude currently: `--color-background-primary` (white), `minHeight:100vh`, 16px padding.
**Change to:** `--color-background-secondary` background, 16px radius (verify token — see token audit), padding 24px vertical / 32px horizontal. KEEP the safe-area-inset additions (`safeAreaInsets.top/right/bottom/left` added to the padding) — a Claude requirement with no OpenAI equivalent. Drop `minHeight:'100vh'` if it conflicts with the card look; state the choice in the report.

### 3. Card-on-background figure/ground (follows from #2)
OpenAI: board is tinted, cards are `bg-surface-secondary` + **`border`** + `shadow-lg` — cards read as raised panels *with an outline*.
Claude currently: board white, cluster cards tinted, subcluster cards white — the relationship is inverted.
**Change:** with the board now secondary (#2), give cluster cards a visible default border so they read as panels. See #4.

### 4. Cluster card: ALWAYS has a border; left accent only when prioritized
OpenAI `ClusterCard`: `border` + `border-default` always; when prioritized ALSO `border-l-4 border-l-strong pl-6`.
Claude currently: `borderLeft` 4px ONLY when prioritized, NO border otherwise (unprioritized cards are borderless).
**Change:** add a default 1px border (`--color-border-tertiary`) to ALL cluster cards; keep the 4px left accent + 24px left padding when prioritized. Use the shorthand/longhand-safe computed `borderStyles` pattern already used in `FullscreenSubclusterCard` to avoid CSS conflicts.

### 5. Header: title + subtitle, and DROP the count (DECIDED)
OpenAI `Header.tsx` renders exactly:
- Title: "Your MindSort AI Board" (heading-sm, default text, `mb-1`)
- Subtitle: "Your thoughts grouped into clusters. Use the chat to rename, split, or reprioritize them." (text-sm, secondary)
- Wrapper: `mb-6` (24px bottom margin). **NO count anywhere.**

Claude currently: `<h1>` title + `{N} clusters / {M} thoughts` count on the same flex row, no subtitle.
**Change:** render title + subtitle stacked, matching OpenAI. **REMOVE the cluster/thought count from the fullscreen header entirely** — decided for strict parity. Subtitle carries over VERBATIM (accurate for Claude: fullscreen is read-only and editing is model-mediated).
**Note the resulting intentional asymmetry:** the INLINE card keeps its count (inline is frozen and is not being aligned to OpenAI); fullscreen will have none. This is deliberate, matches OpenAI, and is not a bug — record it in the report so it isn't "fixed" later.
**Compliance:** title fontWeight 500 max (not 600). `--color-text-primary` for title, `--color-text-secondary` for subtitle.

### 6. Tag pill: lowercase text, soft variant (no border)
OpenAI `TagPill`: `Badge color="secondary" variant="soft"` with `{tag.toLowerCase()}`, wrapped in `<span role="listitem" aria-label={`Suggested action: ${tag}`}>`.
Claude currently: tag rendered as-is, tinted background PLUS a 1px border.
**Change:** (a) render `tag.toLowerCase()`; (b) drop the border (soft = filled tint, no outline); (c) accessible label becomes `Suggested action: ${tag}` using the ORIGINAL casing — lowercase only the visible text.

### 7. Empty-state copy
OpenAI: "No saved board yet. Start one by sharing what's on your mind in the chat."
Claude: "No clusters yet. Start organizing your thoughts!"
**Change to the OpenAI wording.** FULLSCREEN empty state only — do NOT touch the inline empty state (inline is frozen).

### 8. Add the auto-save footer (DECIDED — confirmed true for Claude)
OpenAI ends the board with: `<p className="text-xs text-secondary mt-3 text-left">Changes are saved automatically</p>`.
Persistence has been confirmed to behave the same way on the Claude connector, so this claim is accurate.
**Change:** add the same footer line at the END of the fullscreen board (after the cluster grid): text "Changes are saved automatically", small size (12px), `--color-text-secondary`, left-aligned, ~12px top margin. FULLSCREEN only — do NOT add to the inline card.

---

## DECIDED — deliberately KEEP Claude's version (do NOT change)

### 9. Color-coded priority badges — KEEP
OpenAI `PriorityBadge` uses `Badge variant="solid" color="secondary"` — a SOLID NEUTRAL badge. Claude uses `RANK_COLORS` (danger/warning/info tints per rank).
**Keep Claude's color-coded badges.** Deliberate product decision, not an oversight: colour reinforces rank, and priority is still conveyed by badge TEXT so it stays WCAG-compliant without colour. Document as an intentional deviation in a code comment where the badge renders.
Optional low-priority parity touch: OpenAI's badge `aria-label` is `Priority ${n}` (e.g. "Priority 1") rather than raw "P1". Adopt if trivial — improves screen-reader clarity, no visual change.

### 10. Safe-area insets — KEEP
No OpenAI equivalent; required for Claude fullscreen. Preserve in the container padding calculation (#2).

### 11. No collapsibility — KEEP
OpenAI cards collapse on mobile (`isCollapsible`/`defaultCollapsed`); Claude fullscreen shows everything expanded by design (the inline accordion covers progressive disclosure). Do NOT add collapsibility.

### 12. Scroll-position persistence / `notifyIntrinsicHeight` — KEEP OUT
OpenAI's shell uses `window.openai` scroll persistence and height notification. OpenAI-SDK-specific, no Claude equivalent. Do NOT port. (Note: the auto-save footer in #8 refers to BACKEND persistence of the board, not this widget-state API — adding the footer does NOT mean porting these.)

---

## COMPLIANCE DEVIATIONS — preserve (unchanged from increment 3)
1. fontWeight 400/500 only (OpenAI uses `font-semibold`/600 and `heading-sm`).
2. Monochrome outlined SVG icons only — NO Unicode glyphs (`▲▼·→›•`). This regression has appeared 5× in this workstream.
3. Claude tokens + inline styles; no Tailwind, no `@openai/apps-sdk-ui`, no `window.openai`.
4. Focus ring via `--color-ring-primary`.
5. Existing `var(--token, #hex)` fallback pattern — no fallback-free/fallback-ful mix.

## Token audit (required before implementing — increment 3 shipped a wrong token)
Increment 3 used `var(--border-radius-lg, 8px)` for the subcluster card, but `--border-radius-lg` is **10px**; the 8px token is `--border-radius-md`. Confirm whether that was fixed; if not, fix it here.
Before writing styles, audit and REPORT: does `--border-radius-2xl` exist (needed for 16px in #2)? Does `--shadow-lg` exist? For every value used, state "direct token / nearest token + deviation / literal with fallback." Do not reference tokens that may not exist without stating the fallback rationale.

## Explicitly OUT of scope
- ANY change to the inline accordion (increments 1–2 frozen) — including its count and empty state.
- Any logic, data, sorting, capability-gating, display-mode, focus, or virtualization change.
- Any CRUD/mutation; read-only stands.
- Importing or porting OpenAI components, Tailwind, or the OpenAI SDK.
- Porting `window.openai` scroll/height APIs.
- Changes to `clarity/` (reference only), backend, adapters, or tool handlers.

## Mandatory: WIDGET_VERSION bump + verify URI changed
Bump `WIDGET_VERSION` in `handlers/resources_dupl.py` (current value → next). **Verify the emitted `WIDGET_URI` string actually differs**; state OLD and NEW URI strings in the report, not just the version number. Skipping this ships stale (happened in increment 1).

## Tests
1. **Grid uses 240px minmax.** *Catches:* revert to 320px.
2. **Board container uses secondary background** + new padding. *Catches:* figure/ground revert.
3. **Cluster card always has a border**; prioritized additionally has the 4px left accent. Render one prioritized + one unprioritized; assert both have a border, only one has the accent. *Catches:* borderless unprioritized cards.
4. **Header renders title AND subtitle, and NO count** — assert the subtitle text is present and that no cluster/thought count string appears in the fullscreen header. *Catches:* missing subtitle; count left in place.
5. **Tag pill text is lowercase; accessible label uses original casing** and reads `Suggested action: X`. *Catches:* casing/label regressions.
6. **Fullscreen empty state uses the new copy.** *Catches:* copy revert.
7. **Auto-save footer renders** with the exact text at the end of the fullscreen board. *Catches:* missing/removed footer.
8. **Priority badges remain color-coded** (P1 danger / P2 warning / P3 info) — assert they are NOT neutral. *Catches:* someone "aligning" this to OpenAI's solid-neutral against the decision.
9. **Inline card still shows its count** (proves the count removal was scoped to fullscreen only). *Catches:* accidentally stripping the inline count.
10. **No Unicode glyphs; no OpenAI imports.** *Catches:* the recurring glyph regression.
11. **All increment 1–3 tests pass UNCHANGED.** If any needs its expected values altered, the change was NOT purely visual — STOP and surface it. *Catches:* accidental behavioural change.

**Manual (the real acceptance):** deploy, fresh conversation, open fullscreen on a real board and **compare side-by-side with the OpenAI MindSort board**. Confirm: same column density, tinted rounded board container, bordered cards, title+subtitle header with no count, lowercase borderless tag pills, auto-save footer. Record the comparison.

## Definition of Done
- [ ] Grid `minmax(240px, 1fr)`, gap 16px.
- [ ] Board container: secondary background, 16px radius, 24px/32px padding, safe-area insets preserved.
- [ ] Cluster cards: default border always; 4px left accent + 24px left padding when prioritized.
- [ ] Header: title + subtitle stacked, subtitle verbatim, 24px bottom margin, fontWeight ≤500, **count REMOVED**.
- [ ] Inline card's count untouched (asymmetry is intentional and recorded).
- [ ] Tag pills: lowercase visible text, no border, `Suggested action: X` label with original casing.
- [ ] Fullscreen empty-state copy matches OpenAI.
- [ ] Auto-save footer added at the end of the fullscreen board (fullscreen only).
- [ ] Priority badges STILL color-coded, with intentional-deviation comment.
- [ ] Safe-area insets, no-collapsibility, no-`window.openai` all preserved.
- [ ] Token audit reported; `--border-radius-lg` (10px) misuse fixed if still present.
- [ ] No Unicode glyphs; no OpenAI SDK/Tailwind imports; fontWeight 400/500.
- [ ] Inline accordion untouched; increments 1–3 tests pass unchanged.
- [ ] `WIDGET_VERSION` bumped; OLD and NEW URI strings stated and verified different.
- [ ] Tests 1–11 pass, each with its bug-caught line.
- [ ] `OPERATIONS_PREDEPLOY.md` read before commit.
- [ ] No change outside `widget-react/src/App.tsx` and the `WIDGET_VERSION` line.
- [ ] Report ends with commit hash (review verifies against `git show <hash>:<path>`).

## Post-deploy
Deploy; fresh conversation (new URI busts cache); open fullscreen; side-by-side comparison with the OpenAI board; record the result. Not done until seen on prod.

## Note
This is intended as the FINAL cosmetic alignment pass. Increments 3 + 4 together bring the boards to "reads as the same product" — exact pixel parity is not achievable (Tailwind + OpenAI SDK vs. Claude tokens + inline styles) and is not the goal. MindSort's submission gate remains the privacy-policy / legal pages in Framer — not this increment.
