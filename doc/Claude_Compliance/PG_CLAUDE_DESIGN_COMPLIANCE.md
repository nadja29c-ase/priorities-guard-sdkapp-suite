# PG-Claude — Design Guidelines Compliance (focused)

**Source:** `sources_raw/design-guidelines.raw.md`, **read end to end**, 415 lines
**Assessed:** 2026-08-05 · **Surface:** `widget-react/src`, all 6,724 lines
**Binding via:** Policy §3H — *"follow design guidelines Anthropic publishes"*

| | |
|---|---|
| ✅ Fulfils | **13** |
| 🟡 Partly | **6** |
| ➖ Not relevant | **1** (M13 carousel) |
| ⚠️ **Deviations that are NOT rows in the canonical file** | **2** |

---

## ⚠️ Two constraints the canonical file does not carry

Found by reading the source rather than the row list. Both sit under **Visual design**, which is
covered by the same §3H binding as M1–M20.

### 1. Typography — source: *"Stick to the three-level size scale (heading, body, caption) and two weights (regular, emphasized)"* (raw 224)

| PG uses | Source allows |
|---|---|
| **7 font sizes** — 10, 11, 12, 14, 16, 20, 24px | **3** |
| **4 weights** — 400, 500, 600, 700 | **2** |

*"This creates clear hierarchy without visual noise"* is the stated rationale. **Level:
`DOC-CONSTRAINT`** — "stick to" is imperative, sitting under **Design guidance**.

### 2. Border radii — source: *"Using a limited set of corner radii and thickness will keep your app feeling native"* (raw 232)

PG uses **7 distinct radii**: 4, 6, 8, 12, 16, 50%, 9999px. Whether that is "limited" is a
judgement — the language is advisory (*"will keep your app feeling native"*), so **`RECOMMENDED`**.

⚠️ **Both should become rows.** They are the only Visual-design constraints the canonical file
missed, and typography is the one with a real gap behind it.

---

## 🟡 PARTLY FULFILS (6)

### M8 — floating panels in fullscreen ⚠️ **NEW FINDING**

Source (raw 99, 117): *"In fullscreen mode, avoid the use of floating panels. Use collapsible
sidebars, tabs, or pagination to disclose details."*

`DeleteConfirmation.tsx:91-107` is a **full modal overlay** — `position: 'fixed'`, `inset: 0`,
`zIndex: 50`, `background: rgba(0,0,0,0.5)`, `role="dialog"`, `aria-modal="true"`.

**Mitigating:** it is **fullscreen-only** (`DeadlineCard.tsx:337`, after the inline return at
`:334`), it is a **destructive-action confirmation** rather than a disclosure mechanism — and the
source's clause is specifically about *disclosing details*, for which PG correctly uses
expand/collapse. It is also properly accessible: dialog role, modal flag, labelled, backdrop
dismiss, focus ref.

⚠️ **The finding is the inconsistency.** `KeywordPicker.tsx:20` states: *"Confirmation is inline
(no modal/popover) per MCP Apps guidelines."* **The same rule, applied two different ways in one
codebase.** One of the two is wrong, and the team already decided which when they wrote that
comment.

### M2 — accessibility

Strong: **64** `aria-label`, **24** `role=`, **37** focus/outline rules, **9** keyboard handlers,
and invisible 32px touch-target expanders (`DeliverableItem.tsx:401`, `:426`) marked
`aria-hidden`. **Gap: 10 of 27 `<svg>` elements carry no `aria-hidden`, `aria-label` or
`<title>`** — announced as unlabelled graphics. WCAG AA contrast **not measured**.

### M3 ⚠️SILENT — safe areas

Source (raw 134): *"not mobile-specific: on web and desktop the composer can overlay the bottom of
an inline app."* PG applies insets only under `platform === 'mobile' && hostFullscreen`
(`App.tsx:709`). `.left`/`.right` never read; horizontal padding hardcoded `16px`.

### M5 + M6 — inline density (**one finding**)

`App.tsx:662` maps `sortedPriorities` with **no `.slice()`**; no backend cap. The inline card also
renders `TimeAllocationBar`, `CalendarConnectionMinimal`, `ExpandButton` and a hint line — so
capping the list alone does not bring it under **4–5 data points**. Actions: **1 per card** (the
expand toggle — within M5's limit), but the aggregate surface has `2 + N`, and the refresh button
sits at the **top** where M5 says bottom.

### M10 — width

**Inline compliant** (`max-width` + `width:100%` reflows from 320px). **Fullscreen not** —
`#root`'s 600px cap binds and `margin: 0 auto` produces the side margins raw 172 names. Four
layered caps; the two 672px ones are **dead**.

### M20 — loading states

Source (raw 210): *"Show skeleton screens… Avoid spinners for inline content."* PG shows **text**
(`App.tsx:537-548`, `t('loading')`). No spinners — so the prohibition is respected — but no
skeletons either.

---

## ✅ FULFILS (13) — each verified by reading

| Row | Evidence |
|---|---|
| **M1 / M18** | 22 of 24 bare hex are **documented product identity**; `constants.ts` states *"semantic product colors… intentionally fixed"* and `PieChart.tsx:44-46` adds *"no official solid tokens exist for pie chart fills"* — true. **M18 permits brand colours for accents and identity.** `BAR_COLORS.other` uses `var(--color-text-tertiary, …)`, proving the line was drawn deliberately. 275 `var(--color…)` uses. ⚠️ Two structural exceptions: `GoalItem.tsx:330`, `KeywordPicker.tsx:230` |
| **M4** | **No nested vertical scroll anywhere** — grep for `overflowY`/`overflow: auto`/`maxHeight` across all `.tsx`/`.css` returns nothing in the inline path. `touchAction: 'pan-y'` and `overscrollBehavior: 'contain'` set on the roots |
| **M7** | No dropdowns, `<select>`, context menus or popover panels. `KeywordPicker.tsx:20` documents the choice. Expand/collapse is **disclosure, not a drill-in** |
| **M9** | Explicit `minHeight/minWidth: 44px` on action buttons; shared `Button.tsx` reaches 44px by arithmetic (`16+16+12`, `15+15+14`); invisible ±16px hit expanders on small controls |
| **M11** | `_meta.ui.csp` on all three blocks; `connectDomains: []` — the widget uses `postMessage`, not HTTP |
| **M12** | `availableDisplayModes: ['inline','fullscreen']` |
| **M14** | `prefersBorder: false` set explicitly on all three blocks — the source asks for an explicit value |
| **M15** | Mobile fullscreen supported; no camera/mic/location use |
| **M16** | The only `<textarea>` is `AddPriorityForm.tsx:437`, rendered at `App.tsx:799` — **fullscreen only**, a priority-entry field, **not conversational UI** |
| **M17** | `requestDisplayMode` used for inline→fullscreen escalation — the source's stated remedy for needing a scroll viewport |
| **M19** | **Zero emoji** across all 6,724 lines; 27 inline SVGs, monochromatic, stroke-based |
| **Transitions** (raw 196-198) | `ExpandButton` is a clear visual affordance for expansion |
| **Interaction split** (raw 248-266) | Handled in-app: expand/collapse, confirming prepared actions, direct manipulation — exactly the source's list. Freeform text entry is **fullscreen-only**, not inline |

---

## What would close each gap

| Gap | Fix |
|---|---|
| **M8** | Decide once: modal or inline confirmation. `KeywordPicker` already shows the compliant pattern |
| **M2** | Add `aria-hidden="true"` to the 10 decorative SVGs; measure contrast on the P1/P2/P3 badges |
| **M3** | Apply `safeAreaInsets` in the inline branch too, and read `.left`/`.right` |
| **M5 + M6** | A product decision about what the inline card shows |
| **M10** | Reconcile the four width caps; scope `#root`'s to inline |
| **M20** | Skeletons matching final layout |
| **Typography** | Collapse 7 sizes → 3, 4 weights → 2 |

**None is a submission gate.** All are `DOC-CONSTRAINT`/`RECOMMENDED` level, binding via §3H —
which reviewers assess as *"follow design guidelines"*, not as pass/fail clauses.

**The two strongest results:** M19 (zero emoji — the recurring violation across these apps, and PG
is clean) and M4 (no nested scrolling, the constraint most inline widgets get wrong).
