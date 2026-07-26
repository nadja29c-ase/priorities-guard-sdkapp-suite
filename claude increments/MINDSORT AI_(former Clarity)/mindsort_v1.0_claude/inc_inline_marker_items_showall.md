# Increment 7: MindSort-Claude inline — item marker consistency, "items" label, show-all expansion

**App:** MindSort AI for Claude (`mcp_server/mindsort_claude/`). Inline widget (primarily) + a shared label change touching fullscreen.
**Type:** Presentational (1, 2) + BEHAVIORAL/ARCHITECTURAL (3). Item 3 removes the inline expansion's item cap and must be validated on prod before the old machinery is deleted.
**Touches:** `widget-react/src/App.tsx`, possibly `widget-react/src/test/*`, plus `WIDGET_VERSION` in `handlers/resources_dupl.py`. No `main.css` change expected.

**Status: QUEUED.** Increments 1–6 shipped. Driven by a prod side-by-side (2026-07-26) — inline and fullscreen mark thoughts differently, the count says "thoughts," and expanded clusters truncate to 2 items.

---

## 1. Inline thought marker: dot → vertical bar (match fullscreen)

**Current:** inline `DetailRow` marks a thought with a monochrome target/circle SVG icon in a 16px icon column. Fullscreen `FullscreenThoughtItem` marks a thought with a LEFT VERTICAL BORDER BAR (4px when prioritized, 2px otherwise).
**Change:** make the inline thought row match fullscreen — remove the circle icon, use a left vertical border bar. Reuse the exact treatment from `FullscreenThoughtItem`:
- Prioritized thought: `borderLeft: 4px solid <rank border color>`.
- Unprioritized thought: `borderLeft: 2px solid var(--color-border-tertiary, #E0DFDB)`.
- Remove the 16px icon `<span>` and its circle SVG for the `thought` type.

**Scope of the marker change — decide and state:**
- The inline `DetailRow` also renders `summary` and `subcluster` types, which currently use their own icons (document, folder). Fullscreen does NOT put those in the same left-bar treatment. **This increment changes the THOUGHT marker only** — leave summary and subcluster markers as they are unless they look inconsistent once thoughts change, in which case flag it, don't silently restyle.
- ⚠️ **Height-model impact:** removing the icon column changes the `DetailRow` layout. `LAYOUT.detailRowH = 36` was calibrated with the icon present. This interacts with item 3 (which removes the height budget for expanded clusters), so re-verify row height as part of item 3's prod check rather than independently.

## 2. Count label: "thoughts" → "items"

**Change every USER-VISIBLE count** that currently says "thought"/"thoughts" to "item"/"items". Locations (grep `thought` in App.tsx to confirm you got all):
- Inline header: `{thoughtCount} thoughts` → `{thoughtCount} items` (keep the singular/plural logic: "1 item" / "N items").
- Inline cluster row (`ClusterRowToggle`): `{sum_thought_items} thoughts` → `items`.
- Inline detail subcluster count (`DetailRow`): `{count} thoughts` → `items`.
- Fullscreen count pills' accessible text and any visible "thoughts".
- Accessible labels (`aria-label`) that say "thoughts" → "items" (e.g. DetailRow's `, ${count} thoughts`, the overflow "N more" context, cluster/subcluster `aria-label`s).
- The overflow action count string if it says thoughts.

**Do NOT change:**
- Data model / field names (`sum_thought_items`, `thought_items`, `getTotalThoughtCount`) — internal, not user-visible. Only the displayed WORD changes.
- Tool-facing or server language.
- Any variable names — this is a display-string change only.

Be consistent: inline AND fullscreen both say "items" after this. No mixed "thoughts"/"items" across the two views.

## 3. Inline expanded cluster: show ALL items (remove the 2-item cap) — PHASED, VALIDATE ON PROD

### Rationale
The current design truncates an expanded cluster's detail to a computed capacity (`computeDetailCapacity`) and shows "View remaining cluster content (N more)". That machinery was built around a deterministic ~500px inline height budget. **The current Anthropic guidelines publish NO numeric height limit** — they say *"Height: auto-fits to content (no nested scrolling)"* and that the host caps and clips overflow without defining the cap. So the ~500px budget is a self-imposed engineering target, not a rule. This increment removes the artificial cap and lets the expanded cluster auto-fit, THEN validates real host behavior before deleting the old machinery.

### The real constraint to respect: NO NESTED SCROLLING
*"Height: auto-fits to content (no nested scrolling)."* Auto-fitting tall content is fine; the card developing its OWN internal scrollbar is PROHIBITED. There are three possible prod outcomes and the validation MUST distinguish them:
1. **Card grows tall, the CONVERSATION/PAGE scrolls** → this is "auto-fit," compliant. Desired outcome.
2. **Host CLIPS at some cap** → content silently lost. Must revert / keep bounded.
3. **Card grows tall and develops an INTERNAL scroll region** → this is the prohibited nested-scrolling state. Compliance violation even though it "looks fine." Must fix (do not ship).

Checking only for clipping is insufficient — outcome 3 looks visually fine and is still a violation.

### Implementation (phased — do NOT delete the old machinery yet)
1. **Remove the item cap for the expanded cluster:** render ALL of the expanded cluster's detail units (summary + all thoughts + all subclusters), not `finalDetailCapacity`-limited.
2. **Ensure NO nested scroll is introduced by our code:** the expanded detail container and the inline `<main>` must NOT set `overflow: auto/scroll` or a fixed/max height that would create an internal scroll region. Let height be natural (`auto`). Audit the inline `<main>` style and the detail region style for any `maxHeight`/`overflow` that would trap scrolling.
3. **Keep the overflow machinery DORMANT, not deleted:** `computeDetailCapacity`, `OverflowActionRow`, the `hasDetailOverflow` path, and the ResizeObserver guard stay in the code but are bypassed (cap not applied). This preserves a one-line rollback if prod shows clipping. Gate the "show all vs. capped" behavior behind a single clearly-named constant (e.g. `INLINE_SHOW_ALL_ITEMS = true`) so reverting is trivial.
4. **Keep the ResizeObserver as a DIAGNOSTIC only:** it should no longer decrement/strip rows (that behavior is bypassed with the cap), but keep it logging `[MindSort Diagnostic] Inline main scrollHeight: {height}px` so prod testing can read actual heights from the console. Do not let it call `setGuardedDetailCount` while show-all is active.

### Sibling-cluster behavior (DECIDED)
When a cluster is expanded to show all items, **collapse the sibling cluster rows more aggressively** so the inline card stays a "focused summary with expansion" rather than a sprawling workspace. Specifically: when a cluster is expanded, show the expanded cluster's row + its full detail, and keep the OTHER cluster rows visible but minimal (the existing collapsed rows are fine) — do NOT additionally expand or grow siblings. If the current `MAX_INLINE_ROWS_EXPANDED = 3` still applies, keep it: expanded cluster shows all its items; up to 2 other clusters show as collapsed rows; the rest fall under "+N more clusters". This keeps the tall content to ONE cluster at a time. State in the report how tall the worst realistic case gets (e.g. a 16-item cluster expanded + 2 sibling rows + header + footer).

### Explicitly do NOT (this increment)
- Delete `computeDetailCapacity` / `OverflowActionRow` / overflow logic (that's a follow-up cleanup increment, only after prod validation).
- Add `overflow: auto`, `maxHeight`, or any internal scroll to the inline card or detail region.
- Change fullscreen behavior (fullscreen already shows everything).
- Change the accordion "one open at a time" rule.

---

## Compliance (preserve)
Monochrome outlined SVG icons only where icons remain; NO Unicode glyphs; Claude tokens + inline styles; fontWeight 400/500; focus ring `--color-ring-primary`; read-only; existing `var(--token, #hex)` fallback pattern. No `@openai/apps-sdk-ui`, no `window.openai`.

## Mandatory: WIDGET_VERSION bump + verify URI changed
Bump `WIDGET_VERSION` (current "7" → "8"). Verify the emitted `WIDGET_URI` string differs (`...v7.html` → `...v8.html`); state OLD and NEW in the report.

## Tests
1. Inline thought row renders a left border bar and NO circle/target icon; prioritized = wider bar than unprioritized. *Catches:* marker inconsistency, icon left behind.
2. No user-visible "thought"/"thoughts" string in rendered inline OR fullscreen output; counts say "item"/"items" with correct singular/plural. *Catches:* missed rename, mixed vocabulary. (Assert against rendered text, not source.)
3. Data-model identifiers unchanged (`sum_thought_items` etc. still present in code) — the rename was display-only. *Catches:* over-eager rename breaking the model.
4. Expanded cluster renders ALL its detail units (given a cluster with more items than the old cap, all appear; no "View remaining cluster content" shown while show-all is active). *Catches:* cap still applied.
5. No `overflow: auto`/`scroll` and no `maxHeight` on the inline `<main>` or the expanded detail region. *Catches:* accidental nested scroll region (the real constraint) — assert the style props are absent.
6. Overflow machinery still PRESENT in the module (dormant, behind the flag), not deleted. *Catches:* premature removal that would block rollback.
7. Accordion one-open-at-a-time unchanged; siblings stay collapsed when one is expanded. *Catches:* sibling-growth regression.
8. All increment 1–6 tests pass, EXCEPT those asserting the old capacity/overflow behavior, which change by design here — list each changed test with its reason (the cap-removal is sanctioned). *Catches:* unintended breakage; distinguishes sanctioned changes.

**Manual, real-host (THE acceptance gate for item 3):**
- **A. Small board:** expand a 2–3 item cluster → all items show, card is short, page behaves normally.
- **B. Medium board:** expand a 5-item cluster → all 5 show (previously truncated to ~2 + overflow). Confirm the "View remaining cluster content" affordance is GONE.
- **C. Large board / tall cluster:** expand a 12–16 item cluster. **Determine which of the three outcomes occurs:**
  - (1) card grows tall and the CONVERSATION/PAGE scrolls → COMPLIANT, desired. Record the max `[MindSort Diagnostic] scrollHeight`.
  - (2) host CLIPS content → items past some height vanish. NOT acceptable — record the clip height and REVERT (`INLINE_SHOW_ALL_ITEMS = false`).
  - (3) the CARD develops its OWN scrollbar (internal scroll region) → PROHIBITED nested scrolling. NOT acceptable — must fix before ship.
  **Explicitly confirm WHICH element scrolls: the page (good) or the card (violation).** This is the key check.
- **D. Dark mode + keyboard:** expanded tall cluster remains legible; keyboard can reach all items and the sibling rows; focus ring visible.
- **E. Marker consistency:** inline thought bars visually match fullscreen thought bars (same side, same weights).
Record the outcome of C explicitly (1/2/3, which element scrolled, max height). The increment is only "safe to keep show-all" if C resolves to outcome (1).

## Definition of Done
- [ ] Inline thought marker is a left vertical bar matching fullscreen (icon removed); prioritized vs not differ in bar width.
- [ ] All user-visible counts say "item(s)"; no "thought(s)" in rendered inline or fullscreen; singular/plural correct.
- [ ] Data model / variable names unchanged (display-only rename).
- [ ] Expanded cluster renders ALL items; cap bypassed behind `INLINE_SHOW_ALL_ITEMS` flag.
- [ ] No `overflow`/`maxHeight` introduced on inline `<main>` or detail region (no nested scroll from our code).
- [ ] Overflow machinery retained but dormant; ResizeObserver kept as diagnostic-only (no row stripping while show-all active).
- [ ] Sibling clusters stay collapsed when one is expanded; one tall cluster at a time.
- [ ] Compliance preserved (SVG-only remaining icons, no glyphs, tokens, weights, ring, read-only).
- [ ] `WIDGET_VERSION` 7→8; OLD and NEW URI strings stated and verified different.
- [ ] Tests 1–8 pass, each with its bug-caught line; sanctioned test changes listed.
- [ ] `OPERATIONS_PREDEPLOY.md` read before commit.
- [ ] No change outside `App.tsx`, tests, and the `WIDGET_VERSION` line.
- [ ] Report ends with commit hash.

## Post-deploy (item 3's validation is mandatory before this is "done")
1. Deploy; fresh conversation (v8 URI busts cache).
2. Run manual A–E. **Record outcome C explicitly** (which of the three outcomes; which element scrolls; max scrollHeight).
3. If C = outcome (1): show-all confirmed safe. Schedule a follow-up cleanup increment to delete the now-dormant overflow machinery.
4. If C = outcome (2) clipping: set `INLINE_SHOW_ALL_ITEMS = false`, redeploy, keep the bounded behavior; report the clip height as the empirical host cap.
5. If C = outcome (3) nested card scroll: fix the offending `overflow`/height style before considering it shippable; do not leave a nested-scroll card in prod.

## Note
Items 1 and 2 are safe cosmetic/label changes. Item 3 explores host auto-fit behavior WITHIN the published guidance (no numeric cap exists) — the phased flag + dormant machinery means rollback is one line if prod clips or nested-scrolls. MindSort's submission gate remains the privacy-policy / legal pages in Framer — not this increment.
