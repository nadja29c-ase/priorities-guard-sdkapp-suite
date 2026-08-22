# MindSort-Claude — UI/UX Design Compliance Audit (must-have criteria)

**Audited:** 2026-08-20 · **Scope:** §8 (display modes & design) + §9 (widget domain, CSP, theming) of
`CLAUDE_COMPLIANCE_REQUIREMENTS_CANONICAL.md` — the design surface, **29 rows**
**Live at:** v15 (`56d6ce0`, deploy `dep-da3d6r37uimc73biigc0`) · `mindsort-mcp.priority-guard.com`
**Widget:** `mcp_server/mindsort_claude/widget-react/`

---

## Scope: which rows are "must-have"

Applying the derivation rule (blocking level **or** `⚠️SILENT` **or** `CONDITIONAL` with the precondition
holding): **27 of 29 design rows are must-have.**

Only two are not: **M8** (fullscreen floating panels) and **M14** (`prefersBorder`) — both `RECOMMENDED`,
neither `⚠️SILENT`. Both are satisfied anyway, and are recorded below rather than dropped.

| Verdict | Count |
|---|---|
| ✅ **Fulfilled** | 20 |
| ⚠️ **Partly** | 2 |
| ❌ **Not fulfilled** | 0 |
| ➖ **N/A** (precondition does not hold) | 4 |
| ❓ **Unexercised / not observable** | 3 |
| **Total** | **29** |

**No design row is outright failing.** The two Partly rows are `DOC-CONSTRAINT`, not portal gates.

---

## ⚠️ PARTLY FULFILLED (2)

### M2 — WCAG AA contrast · `DOC-CONSTRAINT`
> *"Maintain high contrast standards (WCAG AA minimum). Support keyboard navigation and provide text
> alternatives for visual content. Test with assistive technologies."* (`design-guidelines.raw.md:278`)

**Contrast: measured, 4 light-mode failures. Dark mode passes 11/11.**

| Element | Pairing | Ratio | Need |
|---|---|---|---|
| Header count summary | `text-tertiary` #73726C on `background-secondary` #F5F4ED | **4.38** | 4.5 |
| Footer "+N more clusters" | same | **4.38** | 4.5 |
| Empty-state "No clusters yet" | same | **4.38** | 4.5 |
| P3 badge text | `text-info` #3266AD on `background-info` #D6E4F6 | **4.48** | 4.5 |

All three tertiary sites are **12px** — normal text (large = ≥24px, or ≥18.66px bold), so **4.5:1
applies** and the 3:1 allowance does not reach them. Skeleton placeholder bars are **1.35–1.49:1**
against the 3:1 graphical threshold — arguably exempt (decorative, `aria-hidden`, transient).

**The failures are in Anthropic's palette, not our colour choices.** M18 (`raw 220`) mandates host tokens
for all structural elements; M2 mandates AA; these are documented pairings used exactly as instructed.
**M2 and M18 are in genuine tension at these values.**

⚠️ **Measurement caveat.** `RANK_COLORS` fallbacks (`utils.ts:242-243`, #1E40AF on #DBEAFE = **7.15:1**)
are *more* accessible than the resolved host tokens (**4.48:1**). `useHostStyles` resolves the `var()`
inside Claude, so the fallback never paints — **contrast tested outside Claude reads falsely
reassuring.** An initial pass made exactly this error.

**Also outstanding for M2:** keyboard-only traversal and a screen-reader pass. Neither has been run. The
`sr-only` inherited-priority announcement is code-verified present but its spoken output is unverified,
and the skeleton's `role="status"` announces in **no** case (the branch is never re-entered).

**Fix available, not applied:** three tertiary sites → `--color-text-secondary` = **9.88:1**, still a host
token, zero M18 tension. Batched for the next widget rebuild. The P3 badge is **logged, not fixed** —
`RANK_COLORS` is shared with the OpenAI surface (cross-surface blast radius) and 4.48 is marginal.

**Method:** computed from the published token table (`design-guidelines.raw.md:284-305`), **not** sampled
from rendered pixels. A devtools eyedropper would be stronger if the host overrides the defaults.

### M5 — Inline: max 2 actions, at the bottom of the card · `DOC-CONSTRAINT`

**Count passes, placement deviates.** Two actions exist:
- **"Open full board"** (`App.tsx:1079`) — in the footer, at the bottom ✅
- **"View remaining content in {cluster}"** (`App.tsx:1504`) — renders **inside an expanded cluster**, not
  at the bottom of the card ⚠️

The accordion row itself (`App.tsx:1166`) is a content disclosure control, not a card action, so it
doesn't count toward the two.

Defensible — the overflow action is contextual to the row it belongs to, and hoisting it to the footer
would divorce it from its subject. Recorded as a deviation rather than argued away.

---

## ✅ FULFILLED (20)

| ID | Requirement | Evidence |
|---|---|---|
| **M1** | Light + dark, host tokens, never hardcode | Zero raw hex outside `var(--token, #fallback)`. **Dark mode confirmed on-device 2026-08-20** |
| **M3** ⚠️SILENT | Interactive portion inside `safeAreaInsets` | Fixed `77eb332`. Inline root padding = `16 + hostContext.safeAreaInsets` per side, read at render, all four sides. *See "Unexercised" — the host reported zero insets on tested surfaces* |
| **M4** ⚠️SILENT | Auto-fit height, no nested vertical scroll | **Zero** `overflow-y: auto/scroll` in `App.tsx` or `main.css`; `main.css:79` uses `overflow: hidden`. Content auto-fits via truncation + an overflow affordance |
| **M6** | Max 4–5 data points | `maxRows = expandedClusterId ? 3 : 5` applied via `truncateClusters()` (`App.tsx:501, 509`). Hard cap at **5** cluster rows, 3 when one is expanded — within range |
| **M7** | No drill-ins, breadcrumbs, menus, popovers | No `<select>`, `role="menu"`, popover or dropdown anywhere. Accordion expansion only; the sole match is a comment stating the app deliberately avoids these |
| **M9** | ≥44pt touch targets; no horizontal scroll | `LAYOUT.boardHeaderHeight/collapsedRowH/overflowActionRowH = 44`; explicit `minHeight/minWidth: '44px'` on the footer action. No `overflowX` anywhere |
| **M10** | No fixed-width; responsive from 320px; no side margins | `width: '100%'`, no fixed breakpoints, no side margins. Only fixed px widths are a 16px icon and 1px `sr-only` clips |
| **M12** | Declare `availableDisplayModes` | `capabilities: { availableDisplayModes: ['inline','fullscreen'] }` in the `useApp` config |
| **M15** | Mobile fullscreen supported; no camera/mic/location | Host-negotiated fullscreen; **0** matches for `getUserMedia`/`geolocation`/`mediaDevices` |
| **M16** | No chat inputs or conversational UI | **Zero** `<input>`, `<textarea>`, `contenteditable` or placeholder in the widget |
| **M18** | Host tokens for ALL structural elements | Backgrounds, text, borders and icons all `var(--color-*)`. Brand colour only on rank accents — which the source explicitly permits (*"semantic accent colors signal status"*) |
| **M19** | Icons monochromatic, outlined, host-token coloured | 5 SVGs, **5** with `stroke="currentColor"`. **No emoji** anywhere |
| **M20** | Skeleton screens, not spinners; match final layout | Implemented `efa1ad6`/`d38601f`. Mirrors header + 3 cluster rows. **Runtime measured**: visible and correct on slow loads (~1620ms); imperceptible on fast loads (~18ms, zero paints) because the widget fetches nothing at mount. No min-display timer added — see below |
| **X2** ⚠️ | `ui.domain` = `sha256(server URL)[:32]` **including path** | `sha256(MCP_RESOURCE_URL)[:32]` (`resources_dupl.py:94`). Production `MCP_RESOURCE_URL` confirmed as `…/mcp` via the live PRM → `c3980c6d…claudemcpcontent.com` |
| **X4** ⚠️SILENT | `html, body { margin: 0; background: transparent }` | Present in source **and verified in the shipped v15 bundle** |
| **X5** | `<meta name="color-scheme" content="light dark">` | Verified in the shipped v15 bundle |
| **X6** | `resourceDomains` includes `https://assets.claude.ai` | `resources_dupl.py:120` |
| **X7** | Register `hostcontextchanged` **before** connect | Assigned inside `onAppCreated`, which the SDK fires *before* `await connect()` — confirmed by reading the installed SDK's `useApp` |
| **X8** | Keep `resourceDomains` to trusted origins | Only `https://assets.claude.ai` (Anthropic's own). All third-party code bundled; **0** external `<script src>` in the bundle |
| **X9** ⚠️SILENT | Must `connect()`; no explicit transport | `useApp({...})` with no transport argument — SDK selects Claude vs ChatGPT |

**Non-must-have, satisfied anyway:** **M8** (fullscreen uses no floating panels; app provides its own
fullscreen button, host renders the close) · **M14** (`prefersBorder: false` set explicitly).

---

## ➖ N/A — precondition does not hold (4)

| ID | Why |
|---|---|
| **M11** | CSP required only if the widget loads external origins. It loads none — `connectDomains: []`. Declared anyway (`resources_dupl.py:116-121`), which is belt-and-braces |
| **M13** | Carousels only. MindSort has none |
| **M17** | Remedy for M4 (*"if the app genuinely needs its own vertically scrollable viewport"*). It doesn't inline — no nested scroll — and it offers host-negotiated fullscreen separately |
| **X3** | Local stdio connectors only. MindSort is remote and correctly *does* set `ui.domain` |

**X1** is `CONDITIONAL` and the precondition **does** hold (`ui.domain` is optional and we set it) — it is
counted under Fulfilled via X2, which is the substantive constraint.

---

## ❓ UNEXERCISED / NOT OBSERVABLE (3)

These are **not** failures. They are claims no evidence currently supports either way.

| ID | Status |
|---|---|
| **M3** | **Implemented per contract, unexercised.** The fix is a no-op when the host reports zero insets — rendered padding is then identical to pre-fix, so there is nothing to observe. The surfaces tested reported zero. The meaningful surface is **mobile** (keyboard up, nav bar present), where the test is a *tap*, not a look: is the bottom-edge "Open full board" still reachable with the composer focused? Cheap proxy: inspect the inline `<main>`'s computed padding — `16px` all round means zero insets reported |
| **M2** (partial) | Keyboard-only traversal and screen-reader pass **never run** |
| **M20** (partial) | Structural compliance holds, but the `role="status"` announcement claim is **weaker than first recorded**: `setIsInitialized` is only ever set `true` (`App.tsx:388, 395`), so the skeleton branch is never re-entered, the live region never changes while mounted, and it announces in **no** case |

---

## Two findings worth carrying beyond this audit

**1. The contrast failures are Anthropic's own token pairings.** M18 says use the host palette; M2 says
hit AA; `text-tertiary` on `background-secondary` is a documented pairing at 4.38:1. Following M18
exactly produced an M2 failure. That is a defensible position to state to a reviewer, and it is fixable
on our side without abandoning M18.

**2. Contrast tested outside Claude misleads.** Our hardcoded fallbacks are *more* accessible than the
real tokens. Any check that doesn't resolve host variables will read clean when the shipped product does
not. This caught a live error during the audit itself.

---

## Submission relevance

**No design row here is a portal gate.** Every §8/§9 row is `DOC-CONSTRAINT`, `RECOMMENDED` or
`CONDITIONAL` — binding in principle via Policy §3H, but the portal's own blockers are elsewhere: tool
annotations (S4/P5E), documentation (P3C/DOC1), screenshots (S7), OAuth (A-series) and the privacy policy
(P3A/T4/S5).

**P3A — the privacy policy — remains the only item actually gating the listing.** Nothing in this audit
changes that, and nothing in it should delay submission.

---

## What I did NOT verify

- **Rendered pixel contrast.** Computed from the published token table; the host may supply different
  values at runtime.
- **Keyboard traversal and screen-reader behaviour** (M2) — never run, on this app or PG.
- **M3 on a surface that actually reports insets** — mobile, keyboard up.
- **Anything requiring visual inspection on mobile** — M9's touch targets and M10's 320px responsiveness
  are verified in source, not on a device.
- **PG-Claude** — this audit covers MindSort-Claude only.
