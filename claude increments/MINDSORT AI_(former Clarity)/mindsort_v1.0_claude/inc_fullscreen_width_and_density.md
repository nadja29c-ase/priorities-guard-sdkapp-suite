# Increment 6: MindSort-Claude fullscreen — responsive width + density pass

**App:** MindSort AI for Claude (`mcp_server/mindsort_claude/`). Fullscreen widget view.
**Type:** PURELY PRESENTATIONAL. Let the fullscreen board fill its container responsively and increase information density. NO logic, data, ordering, or behavioural changes.
**Touches:** `widget-react/src/App.tsx` (fullscreen components only), `widget-react/src/main.css`, plus `WIDGET_VERSION` in `handlers/resources_dupl.py`.

**Status: QUEUED.** Increments 1–5 shipped. Final visual pass.

## Why this exists
Side-by-side comparison on prod (2026-07-24): at the same screen size the OpenAI MindSort board shows ~4 clusters / ~10 subclusters / ~25 thoughts where Claude shows 2 clusters / ~10 thoughts. Two compounding causes:
1. **`#root { max-width: 600px }`** caps fullscreen at ~2 grid columns.
2. **Oversized type and spacing** — larger than the OpenAI board and, in several cases, off the Anthropic token scale.

Goal: **comparable information density to the OpenAI board** (measurable: similar content visible at the same viewport size), not pixel-identical replication.

## What the official guidelines actually say (verified 2026-07-24)
Framing matters — this increment is **design-system alignment**, not fixing compliance violations. Be accurate about which is which:

**Hard constraints (must not break):**
- *"Minimum tap target: 44 x 44pt"* — reducing padding is exactly how this gets broken. Verify after.
- *"All views must support both light and dark themes... Never hardcode colors."*
- *"Maintain high contrast standards (WCAG AA minimum)."*
- Fullscreen: no floating panels; composer always visible.

**Layout guidance (this increment follows it):**
- *"Apps always fill the container width — there are no fixed breakpoints. Design responsively from 320px up to fullscreen using container queries and the hostContext CSS variables."*
- *"Full-width layouts — don't add side margins that waste screen real estate."*
- *"Content should reflow gracefully; avoid fixed-width layouts."*
- ⚠️ This applies to ANY hardcoded board width. Do **not** replace the 600px cap with a different fixed number (e.g. 1100px) — that is the same fixed-width pattern at a different value. Fill the container.

**Design guidance (preferences, not violations):**
- *"Stick to the three-level size scale (heading, body, caption) and two weights."* → prefer token sizes; off-scale values are misalignment, not violation.
- *"Using a limited set of corner radii and thickness will keep your app feeling native."* → prefer radius tokens.

**Explicit counter-weight to this increment — read it before compressing:**
- *"Spacing. Maintain generous padding and logical groupings. **Balance information density with readability**, adapting to viewport constraints."*
Density is the goal; cramped is a failure. If a target value below makes something hard to read, back off and say so.

**Not a constraint here:** the ~500px figure is a self-imposed INLINE height budget, not an Anthropic limit, and is irrelevant to fullscreen.

## Reference
Compare against the OpenAI board screenshot and `mcp_server/clarity/widget-react/src/components/{ClusterCard,SubclusterCard,ThoughtItem}.tsx` (READ ONLY, never import).
Before commit: read `OPERATIONS_PREDEPLOY.md` ("Widget Bundle Changes").

---

## 1. WIDTH — responsive fill, no fixed board width

`main.css` currently: `#root { width: 100%; max-width: 600px; margin: 0 auto; }`

`#root` is shared by inline and fullscreen. Inline lives in the chat column where 600px is appropriate — **inline keeps its cap**. Fullscreen must fill its container.

**Objective:** in fullscreen, the board fills the available container width with no artificial side margins beyond the container padding and safe-area insets. Do NOT introduce a replacement fixed `max-width`.

**Implementation is yours to choose** — state which you used and why:
- (a) scope `#root`'s cap so it applies only when inline (e.g. a `data-display-mode` attribute on `#root`/`<html>` set from `displayMode`, with the cap under the inline selector), or
- (b) have the fullscreen container escape the ancestor cap by other means, verified to actually work.
Whatever you choose, **verify on prod that the board genuinely widens** — an ancestor `max-width` silently winning is the most likely failure mode.

**Column behaviour comes from the grid, not a board width.** Keep `repeat(auto-fit, minmax(<min>, 1fr))`. Tune `<min>` so common desktop widths naturally yield **3–4 columns** and cards never become too narrow to read. Current `<min>` is 240px (matches OpenAI); keep unless testing shows otherwise. Optionally add a max card width to prevent absurdly wide cards on ultrawide displays — if you do, state the value and reasoning.

**Report:** rendered board width and column count at **1280px, 1440px, and 1920px** viewports.

## 2. TYPOGRAPHY — prefer the token scale

Preferred sizes: **12px (`--font-text-xs-size`)**, **14px (`--font-text-sm-size`)**, **16px (`--font-text-md-size`)**. Preferred line-height **1.4** (`--font-text-xs-line-height` / `--font-text-sm-line-height`); the current `1.5` is off-scale and inflates every text block.

If a specific element genuinely needs a size outside this set, use it — but state which and why in the report.

| Element | Current | Target |
|---|---|---|
| Thought text (normal) | 13px / lh 1.5 | **12px / lh 1.4** |
| Thought text (small) | 12px / lh 1.5 | **12px / lh 1.4** |
| Cluster summary | 13px / lh 1.5 | **12px / lh 1.4** |
| Cluster name | 14px | **14px** (keep — heading level) |
| Subcluster name | 14px | **12px** (subordinate to cluster name) |
| Board title | 14px | **14px** (keep) |
| Board subtitle | 14px | **12px** |
| Count pill (cluster) | 12px | **12px** (keep) |
| Count pill (subcluster) | 11px | **12px** |
| Priority badge (cluster) | 12px | **12px** (keep) |
| Priority badge (thought normal) | 10px | **12px** |
| Priority badge (thought small) | 9px | **12px** |
| Priority badge (subcluster) | 10px | **12px** |
| Tag pill | 11px | **12px** |
| Auto-save footer | 12px | **12px** (keep) |
| Large-board notice | 13px | **12px** |

Badges/pills compensate with **smaller padding** rather than smaller font (see §3).
Weights stay **400/500 only** — unchanged.

## 3. DENSITY — design goals + target values

**Goals (what actually matters):**
- Reduce cluster and subcluster card padding.
- Reduce vertical whitespace between thoughts, sections, and cards.
- Remove the forced minimum card height.
- Reduce inter-card spacing.
- Preserve readability and keep 44pt interactive targets.

**Target values.** These are density targets derived from the screenshot comparison, **not** from reading OpenAI's exact Tailwind values. **Treat them as targets: if achieving comparable density requires minor deviation, prefer the visually equivalent result and explain the deviation in the report.**

| Element | Current | Target |
|---|---|---|
| Cluster card padding | 20px (24px left when prioritized) | **12px** (16px left when prioritized) |
| Cluster card `minHeight` | 120px | **REMOVE** |
| Cluster card radius | 16px literal | **`var(--border-radius-xl, 12px)`** |
| Cluster card shadow | `--shadow-lg` | **Evaluate `--shadow-sm` or `--shadow-md`** — `lg` looks heavy at this density, but compare before deciding; state which you chose and why |
| Header→content margin (cluster) | 12px | **8px** |
| Thought list gap | 8px | **4px** |
| Thought item padding-Y | 4px (2px small) | **2px** (1px small) |
| Thought item padding-left | 12px (8px small) | **10px** (8px small) |
| Summary bottom margin | 12px | **8px** |
| Subcluster block top margin | 12px | **8px** |
| Subcluster card gap | 12px | **8px** |
| Subcluster card padding | 12px | **10px** |
| Subcluster header bottom margin | 8px | **6px** |
| Subcluster thought list gap | 4px | **3px** |
| Tags padding-top (cluster) | 16px | **10px** |
| Tags padding-top (subcluster) | 8px | **6px** |
| Tag pill padding | 3px 8px | **2px 6px** |
| Tag pill radius | 12px | **`var(--border-radius-full, 9999px)`** |
| Priority badge padding (cluster) | 2px 8px | **1px 6px** |
| Priority badge padding (thought/subcluster) | 1px 5px / 0 4px | **0 5px** |
| Count pill padding | 2px 8px / 1px 6px | **1px 6px** |
| Grid gap | 16px | **12px** |
| Board container padding | 24px / 32px | **16px vertical / 20px horizontal** (+ safe-area insets, unchanged) |
| Board container radius | 16px literal | **`var(--border-radius-xl, 12px)`** |
| Board header bottom margin | 24px | **16px** |
| Board title bottom margin | 4px | **2px** |

**Safe-area insets stay** in the container padding calculation — unchanged.

## 4. What must NOT change
- Inline card: everything (width cap, type, spacing, accordion, count, empty state). Frozen.
- All ordering behaviour from increment 5 (effective rank, subcluster sort, size tiebreaker).
- Section order: summary → thoughts → subclusters → tags LAST.
- Thought item structure: left priority bar (4px/2px), NO bullet, NO card background, text first / badge after.
- Colour-coded priority badges; full summary (no clamp); header title+subtitle with NO count; auto-save footer; empty-state copy; subcluster tonal contrast.
- Capability gating, display-mode handling, focus restoration, read-only, virtualization logic.
- No Unicode glyphs; no OpenAI SDK/Tailwind imports; fontWeight 400/500 only.

## 5. Token audit (required)
Every value uses a token where one exists, with **fallback equal to the token's real value**. Confirmed real: `--font-text-xs-size` 12px, `--font-text-sm-size` 14px, `--font-text-md-size` 16px, `--font-text-xs/sm/md-line-height` 1.4, `--border-radius-md` 8px, `--border-radius-lg` 10px, `--border-radius-xl` 12px, `--border-radius-full` 9999px, `--shadow-hairline/sm/md/lg`, `--font-sans`. **`--border-radius-2xl` does NOT exist** — no new references. Report every token used and its fallback.

## Mandatory: WIDGET_VERSION bump + verify URI changed
Bump `WIDGET_VERSION` (current → next). Verify the emitted `WIDGET_URI` string differs; state OLD and NEW URI strings in the report.

## Tests
1. Fullscreen container is not constrained by the 600px cap; inline card still capped at 600px. *Catches:* widening leaking into inline, or the ancestor cap winning.
2. No new fixed board `max-width` introduced in fullscreen. *Catches:* replacing one fixed-width layout with another.
3. Font sizes in fullscreen are on the preferred scale (12/14/16) except any documented exception; no line-height 1.5. *Catches:* off-scale type returning.
4. Cluster card has no `minHeight`. *Catches:* the stretch regression.
5. No literal `16px` radius and no `--border-radius-2xl` reference. *Catches:* off-scale radius.
6. Inline accordion behaviour unchanged — all increment 1–5 inline tests pass UNCHANGED. *Catches:* density pass leaking into inline.
7. All increment 1–5 fullscreen behaviour tests pass unchanged (ordering, gating, tags-last, read-only, colour-coded badges, header no-count, footer). **This increment changes only sizes/spacing — any behavioural expectation change means something unintended broke; STOP and surface it.** *Catches:* accidental behavioural change.
8. No Unicode glyphs; no OpenAI imports; fontWeight 400/500. *Catches:* recurring regressions.

**Manual acceptance (the real gate) — record results for each:**
- **A. Responsive:** verify at **1280px, 1440px, 1920px** viewport widths. Report rendered board width and column count at each. Confirm no horizontal scroll, no clipped cards, no absurdly wide cards.
- **B. Density:** side-by-side with the OpenAI board screenshot. Confirm comparable information density (similar content visible at similar viewport size).
- **C. Readability:** text is comfortably readable; nothing feels cramped. Per the guidelines' balance requirement — if it reads as compressed, back off and report.
- **D. Large board:** load a board at/above the scale target. Confirm no layout collapse, no overlapping badges, no tag overflow, virtualization still behaves.
- **E. Long content / localization:** test long cluster names, long tag strings, long thought text (and a long-word locale). Smaller type increases wrapping risk. Confirm graceful reflow, no overlap, no clipping.
- **F. Accessibility:** after the padding reductions, confirm **all interactive targets remain ≥44×44pt** (cluster toggle, minimize, overflow action, "Open full board"), keyboard focus rings remain clearly visible, and contrast holds.
- **G. Dark mode:** confirm legibility and that the nesting contrast still reads.
- **H. Before/after screenshots:** capture the fullscreen board before and after this increment and include both in the report.

## Definition of Done
- [ ] Fullscreen fills its container responsively; NO new fixed board width; inline unchanged at 600px; verified on prod that it actually widens.
- [ ] Grid `minmax()` tuned so 3–4 columns appear at common desktop widths; width + column count reported at 1280/1440/1920.
- [ ] Typography on the preferred token scale per §2; any exception documented.
- [ ] §3 density goals met; target values applied or deviations explained.
- [ ] `minHeight: 120px` removed; radii use tokens; shadow choice stated with reasoning.
- [ ] Safe-area insets preserved.
- [ ] Nothing in §4 changed.
- [ ] Token audit reported (token + fallback for every value).
- [ ] `WIDGET_VERSION` bumped; OLD and NEW URI strings stated and verified different.
- [ ] Tests 1–8 pass, each with its bug-caught line; increments 1–5 tests pass unchanged.
- [ ] Manual checks A–H completed and recorded, including before/after screenshots and the 44pt verification.
- [ ] `OPERATIONS_PREDEPLOY.md` read before commit.
- [ ] No change outside `widget-react/src/App.tsx`, `widget-react/src/main.css`, and the `WIDGET_VERSION` line.
- [ ] Report ends with commit hash.

## Post-deploy
Deploy; fresh conversation (new URI busts cache); run manual checks A–H on prod. Not done until seen working on prod.

## Note
Final visual pass. Accepted remaining differences from the OpenAI board: colour-coded vs neutral priority badges, full vs clamped summary, no card collapsibility, Claude tokens + inline styles vs Tailwind + OpenAI SDK. MindSort's submission gate remains the privacy-policy / legal pages in Framer.
