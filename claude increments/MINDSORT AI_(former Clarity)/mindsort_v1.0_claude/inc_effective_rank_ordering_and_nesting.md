# Increment 5: MindSort-Claude — effective-rank ordering, subcluster sort, nesting contrast, host font token

**App:** MindSort AI for Claude (`mcp_server/mindsort_claude/`). Inline + fullscreen widget.
**Type:** **BEHAVIORAL + presentational.** Unlike increments 3–4, this one CHANGES ORDERING BEHAVIOR in both display modes. Read the tripwire note below before starting.
**Touches:** `widget-react/src/utils.ts`, `widget-react/src/App.tsx`, `widget-react/src/main.css` (font only), `widget-react/src/test/*`, plus `WIDGET_VERSION` in `handlers/resources_dupl.py`.

**Status: QUEUED — not urgent.** Increments 1–4 are shipped. This closes the last audit findings: two behavioral ordering gaps, one nesting-contrast gap, and one host-theming gap.

## ⚠️ TRIPWIRE NOTE — READ FIRST
Increments 3–4 carried the rule: *"all prior tests must pass UNCHANGED; if any needs its expected values altered, the change was NOT purely visual — STOP and surface it."*
**That rule is deliberately suspended for items 1 and 2 of this increment ONLY.** Cluster and subcluster ORDERING changes by design, so prior ordering-test expectations WILL legitimately change. This is sanctioned.
It remains in force for everything else: any test failure NOT explained by cluster/subcluster ordering means something unintended broke — STOP and surface it.
List in the report every test whose expectations changed and why.

## Why this exists
A third structural audit against the OpenAI board (`clarity/`) found four remaining deviations. Two are behavioral (ordering algorithms differ, so identical data can display in different orders), one is visual (nesting contrast), one is host-theming (hardcoded font).

## Reference source (READ ONLY — never import)
- `mcp_server/clarity/widget-react/src/utils.ts` — `getEffectiveRank`, `getEffectiveSubclusterRank`, `getBestThoughtItemRank`, `sortClustersByPriority`, `sortSubclustersByPriority`, `rankToNumber`
- `mcp_server/clarity/widget-react/src/components/{ClusterCard,SubclusterCard}.tsx` — nesting surfaces, subcluster sort usage
- `mcp_server/clarity/widget-react/src/main.css` — `font-family: var(--font-sans)`

Targets: `mindsort_claude/widget-react/src/{utils.ts,App.tsx,main.css}`.
Before commit: read `OPERATIONS_PREDEPLOY.md` ("Widget Bundle Changes").

---

## 1. Effective-rank cluster ordering — BOTH display modes (BEHAVIORAL)

**Today:** `sortClustersForOverview` ranks clusters by OWN-level priority only, then by `sum_thought_items` desc. A cluster with no own rank but containing a P1 thought sorts as unprioritized.
**OpenAI:** `sortClustersByPriority` uses `getEffectiveRank(cluster)` = the MINIMUM (highest priority) of: own rank, best subcluster effective rank, best direct thought-item rank.

**Change:** implement effective-rank ordering in `utils.ts` and use it for cluster ordering in BOTH inline and fullscreen (they share the model — do NOT create a second sort).

Port these from the OpenAI `utils.ts`, reimplemented against Claude's types (do not import):
- `getBestThoughtItemRank(items)` — best (lowest `rankToNumber`) rank among normalized thought items
- `getEffectiveSubclusterRank(subcluster)` — min(own rank, best thought-item rank); null if neither
- `getEffectiveRank(cluster)` — min(own rank, best subcluster effective rank, best direct thought-item rank); null if none

**Explicitly reverses a prior decision.** `test/App.test.tsx` currently asserts `utils.ts` does NOT export `getEffectiveRank`/`getEffectiveSubclusterRank` ("Source file compliance" block). **Delete that assertion** — it encodes the superseded decision. Note the reversal in the report.

**KEEP the size tiebreaker (decided).** OpenAI has no tiebreaker; equal-rank clusters keep array order. Claude sorts equal-rank clusters by `sum_thought_items` DESC. **Keep Claude's tiebreaker** — a deliberate improvement for boards with many unprioritized clusters. So the final comparator is: effective rank ASC, then `sum_thought_items` DESC. Document as an intentional deviation.

**Normalization:** thought items may be bare strings or objects (`ThoughtItemInput`). Bare strings carry no priority. Normalize before reading `.priority` — reuse the existing normalization already in `utils.ts`; do not write a second one.

## 2. Sort subclusters by effective rank (BEHAVIORAL)

**Today:** subclusters render in raw array order — unsorted — in fullscreen nested cards AND in inline detail units.
**OpenAI:** `sortSubclustersByPriority` orders by `getEffectiveSubclusterRank`.

**Change:** add `sortSubclustersByPriority` to `utils.ts` (using `getEffectiveSubclusterRank` from item 1) and apply it in BOTH places subclusters are emitted:
- `extractDetailUnits` (inline detail units), and
- `FullscreenClusterCard` (nested cards).
One shared helper, both call sites — no duplication (shared-view-model requirement).
No size tiebreaker here (OpenAI has none, and there is no established Claude behavior to preserve).

## 3. Subcluster card: tonal contrast in nesting (VISUAL)

**Today:** cluster cards and subcluster cards are BOTH `--color-background-primary` (white) — white-on-white, distinguished only by a border. Increment 4 moved cluster cards to primary without adjusting the nested level.
**OpenAI:** `ClusterCard` = `bg-surface-secondary`, `SubclusterCard` = `bg-surface` — two distinct tones.

**Change:** `FullscreenSubclusterCard` background → `--color-background-secondary` (with the existing hex-fallback pattern), so nested cards read as a distinct level against the white cluster card. Everything else about the subcluster card stays as shipped (radius `--border-radius-md`, 12px padding, conditional left accent, tags last).
Verify in dark mode too — the tonal relationship must hold in both themes.

## 4. Host font token (HOST THEMING)

**Today:** `main.css` hardcodes `font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`. The widget never adopts the host's typeface, so it can render in a different font than surrounding Claude UI.
**OpenAI:** `font-family: var(--font-sans)` — the host's font token.

**Change:** **audit first.** Determine whether the Claude host exposes a font token (check the design-guidelines typography section and what `useHostStyles` actually injects at runtime — inspect the applied CSS variables, don't assume).
- **If a font token exists:** use `font-family: var(--font-<name>, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif)` — token first, current stack as fallback.
- **If NO font token exists:** leave `main.css` unchanged and REPORT that finding. Do NOT invent a token name.
Either way, state in the report which tokens were found and what was applied. (Increment 3 shipped a wrong token by assuming; do not repeat.)

---

## Explicitly OUT of scope
- `#root { max-width: 600px }` — **DECIDED: keep 600px.** Do NOT widen. Known consequence: the fullscreen 240px grid renders ~2 columns where OpenAI fits 3–4. Accepted.
- `body { padding }` difference — ignore.
- Any change to increments 1–4 behavior OTHER than the ordering changes in items 1–2 (accordion mechanics, capacity math, ResizeObserver, display-mode handling, capability gating, focus restoration, read-only: all frozen).
- Any CRUD/mutation, new tool, or backend contract.
- Importing or porting OpenAI components, Tailwind, or the OpenAI SDK.
- Changes to `clarity/`, backend, adapters, or tool handlers.

## Compliance (preserve)
fontWeight 400/500 only · monochrome outlined SVG icons only, NO Unicode glyphs (`▲▼·→›•`) · Claude tokens + inline styles, no Tailwind / `@openai/apps-sdk-ui` / `window.openai` · focus ring `--color-ring-primary` · existing `var(--token, #hex)` fallback pattern · color-coded priority badges KEPT (intentional deviation from OpenAI's neutral badges) · read-only.

## Token audit (required)
Report for every token referenced or added: "direct token / nearest token + deviation / literal with fallback." **The fallback must equal the token's real value** — increment 3 shipped `var(--border-radius-lg, 8px)` when `lg` is 10px. Confirm the previously-unverified `--border-radius-2xl` and `--shadow-lg`, plus any font token from item 4.

## Mandatory: WIDGET_VERSION bump + verify URI changed
Bump `WIDGET_VERSION` in `handlers/resources_dupl.py` (current → next). **Verify the emitted `WIDGET_URI` string actually differs**; state OLD and NEW URI strings in the report, not just the version number.

## Tests

**Unit — ordering (the core of this increment):**
1. `getBestThoughtItemRank`: returns the best rank among items; null when none; handles bare strings (no priority). *Catches:* wrong min, normalization miss.
2. `getEffectiveSubclusterRank`: min(own, best item); own-only; item-only; neither → null. *Catches:* wrong precedence.
3. `getEffectiveRank`: cluster with NO own rank but a P1 thought → 'P1'; cluster with no own rank but a P1 subcluster thought → 'P1'; own P2 + child P1 → 'P1'; nothing anywhere → null. *Catches:* the exact behavior this increment adds.
4. Cluster comparator: effective rank ASC, then `sum_thought_items` DESC for equal rank. Include two equal-rank clusters of different sizes and assert the larger sorts first. *Catches:* tiebreaker dropped (the decided deviation).
5. `sortSubclustersByPriority`: orders by effective subcluster rank; unranked last; stable for equals. *Catches:* item 2 regression.

**Component:**
6. **Inline** cluster rows reflect effective-rank order — a cluster whose only priority is a nested P1 thought appears FIRST. *Catches:* ordering applied to fullscreen only.
7. **Fullscreen** cluster cards reflect the same order as inline for the same data. *Catches:* two divergent sorts (shared-model violation).
8. Subclusters render priority-ordered in BOTH inline detail units and fullscreen nested cards. *Catches:* one call site missed.
9. Subcluster card uses the secondary background; cluster card uses primary — assert they differ. *Catches:* white-on-white nesting.
10. No Unicode glyphs; no OpenAI imports; fontWeight 400/500. *Catches:* the recurring regressions.
11. All non-ordering tests from increments 1–4 pass unchanged (accordion mechanics, capacity math, capability gating, focus, read-only, tag pills, count-removal-in-fullscreen, inline count present). *Catches:* unintended breakage. **Ordering-test expectation changes are expected and sanctioned — list them; everything else must be unchanged.**

**Manual (acceptance):** deploy; fresh conversation; verify on a real board that (a) a cluster whose only priority is a nested thought now sorts to the top in BOTH inline and fullscreen, (b) subclusters appear priority-ordered, (c) nested subcluster cards are visually distinct from their parent card in light AND dark mode, (d) the font matches surrounding Claude UI if a token was applied. Record observations.

## Definition of Done
- [ ] `getBestThoughtItemRank`, `getEffectiveSubclusterRank`, `getEffectiveRank`, `sortSubclustersByPriority` in `utils.ts`; reimplemented, not imported from `clarity/`.
- [ ] Cluster ordering uses effective rank + `sum_thought_items` DESC tiebreaker, in BOTH modes via the single shared model.
- [ ] Subclusters priority-sorted at BOTH call sites (`extractDetailUnits`, `FullscreenClusterCard`) via one shared helper.
- [ ] The `getEffectiveRank`-must-not-exist assertion DELETED; reversal noted in the report.
- [ ] Subcluster card background → secondary; contrast verified in light AND dark mode.
- [ ] Font token audited; applied with the current stack as fallback if it exists, otherwise unchanged + reported.
- [ ] `#root` max-width still 600px (unchanged).
- [ ] Everything else from increments 1–4 behaviorally unchanged.
- [ ] Compliance preserved (weights, SVG-only icons, tokens, ring, color-coded badges, read-only).
- [ ] Token audit reported with fallback-equals-token-value verified.
- [ ] `WIDGET_VERSION` bumped; OLD and NEW URI strings stated and verified different.
- [ ] Tests 1–11 pass, each with its bug-caught line; every changed test expectation listed with its reason.
- [ ] `OPERATIONS_PREDEPLOY.md` read before commit.
- [ ] No change outside `widget-react/src/{utils.ts,App.tsx,main.css}`, `widget-react/src/test/*`, and the `WIDGET_VERSION` line.
- [ ] Report ends with commit hash (review verifies against `git show <hash>:<path>`).

## Post-deploy
Deploy; fresh conversation (new URI busts cache); confirm the four manual checks above; side-by-side with the OpenAI board. Not done until seen on prod.

## Note
This closes the structural audit. Remaining known-and-accepted differences from the OpenAI board: 600px vs 900px max width (decided), color-coded vs neutral priority badges (decided), full vs 100-char-clamped summary (decided), no card collapsibility (by design), and implementation stack (Claude tokens + inline styles vs Tailwind + OpenAI SDK — required). Exact pixel parity is not the goal and is not achievable.
MindSort's submission gate remains the privacy-policy / legal pages in Framer — not this increment.
