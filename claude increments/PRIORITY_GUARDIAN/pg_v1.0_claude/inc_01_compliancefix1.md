# Increment Claude-M20 — Inline loading skeleton (rev 3)

**Row:** M20 · `DOC-CONSTRAINT`, binding via Policy §3H

Supersedes rev 2. Changes: scope list now matches the required edits · latency claim separated into
backend vs client-side · storage baseline reworded to avoid implying §1D mandates zero storage ·
loading-message test scoped to the branch · bundle threshold must be stated, not assumed.

---

## 1. Scope

- `widget-react/src/App.tsx` — loading branch only
- `widget-react/src/main.css`
- The canonical `WIDGET_VERSION` declaration
- The generated Claude widget bundle
- Only those resource metadata references that require updating because of the version change

Nothing else. Adjacent issues found during implementation are reported, not fixed.

---

## 2. The requirement, verbatim

Source: `sources_raw/design-guidelines.raw.md`, "Loading states"

> Show skeleton screens while content loads. **Match the layout structure of the final content so the
> transition feels seamless.** Avoid spinners for inline content — skeletons feel more native.

Current state: the prohibition is met (no spinners). The positive instruction is not — the loading
branch renders a centred text block, which is closer to Anthropic's illustrated anti-pattern (a flat
undifferentiated block) than to its target (structured placeholders you can read the content type
from).

**The second sentence is operative.** A skeleton that doesn't mirror the real layout creates the seam
the requirement exists to remove.

---

## 3. Implementation approach — copy and adjust, never rewrite

Read the inline branch of `App.tsx` and reproduce its geometry from what is actually there — shell,
card shape, and the order of children. Take values from the source, not from this briefing. Do not
invent a layout, do not restyle anything, do not touch the inline branch itself.

---

## 4. What the skeleton mirrors

The inline card renders, in order:

| Region | Conditional? |
|---|---|
| `TimeAllocationBar` | **Yes** — gated on `dashboardData?.google_connected` |
| Priority cards | No |
| `CalendarConnectionMinimal` | No |
| `ExpandButton` | No |
| Hint line | Yes — gated on priorities existing; text-only |

**Mirror the three unconditional regions.** Omitting the connection row and expand affordance is what
made the first proposal fail — content would appear below the cards at transition and the block would
jump.

**`TimeAllocationBar` is a judgement call, and yours to make from evidence.** Connection state is
unknown before data arrives; including it jumps for disconnected users, omitting it jumps for
connected ones. Inspect what state is actually available at the loading branch and decide from that.
**Do not invent or assume connection state.** State the reasoning in the report.

**Hint line:** omit. Text-only and conditional.

### Placeholder count

Render **two** priority-card placeholders by default — the middle case for a result bounded between
zero and three by the P1/P2/P3 keyword set. Anthropic's illustration fills the expected content
footprint with several representative rows rather than under-promising.

**The exact count is an implementation default, not an M20 requirement. Do not dynamically guess the
eventual count.**

---

## 5. Constraints

**Motion.** One shared animation on the placeholder bars via a class — never on the container. A
pulsing shell reads as a rendering fault rather than a loading affordance. Disable the whole
animation under `@media (prefers-reduced-motion: reduce)`.

**Accessibility.** Mark decorative skeleton geometry `aria-hidden="true"` — on **logical groups**, not
on every nested bar. Provide one localized, visually hidden loading message; reuse the existing i18n
loading string. Do not announce individual placeholders or animation cycles.

If a live region (`role="status"` / `aria-live`) is used, **verify it actually announces** — a region
that mounts already populated frequently does not, because live regions announce changes to content
already in the accessibility tree. Do not describe an unverified announcement as an accessibility
improvement. Use the project's established accessible-status pattern if one exists.

**Host tokens throughout**, with fallbacks, so M1 and M18 hold and dark mode adapts. No new bare hex.

**No `platform` dependency.** `platform` is assigned in `onAppCreated`, which may not have fired when
the loading branch renders. The current loading block has no such dependency; do not introduce one.
Keep the frame platform-agnostic or guard the read.

**Reuse what exists.** `main.css` already has a `@keyframes` block and an `.sr-only` utility, and the
i18n module carries a loading string in both languages. Follow those idioms.

---

## 6. Explicitly out of scope

Fullscreen loading · the inline branch itself · any other row in the audit bundle ·
`TimeAllocationBar`, `CalendarConnectionMinimal` or `ExpandButton` internals · M20's level in the
canonical file.

---

## 7. Widget bundle discipline

- Bump `WIDGET_VERSION` and **verify the resulting resource URI string differs from the actual current
  value**, read fresh — not from an assumed previous value. A bundle change that doesn't change the
  URI will not be picked up.
- **Enumerate every resource and tool metadata reference to the URI and prove each resolves to the new
  one.** `resources_dupl.py` is expected to carry three `_meta.ui` blocks; if the enumeration finds a
  different number, flag it rather than proceeding.

---

## 8. Build and regression gates

- Widget type-check, unit tests, and production build all pass.
- **No new runtime dependency.**
- No changes outside the §1 scope, except generated bundle output and required version references.
- **Bundle size before and after.** Use an existing documented project threshold for what counts as a
  material increase if one exists; if none exists, state the fallback threshold used and justify it.
  Do not adopt an arbitrary figure silently.
- **The production bundle contains no `window.openai` reference and no OpenAI-only package import.**
  `types.ts` records that `window.openai` declarations were removed when this widget was copied from
  the ChatGPT tree — a live contamination vector between the two surfaces. This is the Claude widget
  and must remain on the MCP Apps bridge.

---

## 9. Tests

### Unit
- The loading branch renders the expected placeholder set: two card placeholders plus one each for the
  connection row and expand affordance, and the `TimeAllocationBar` placeholder if §4's decision
  includes it.
- Decorative geometry carries `aria-hidden="true"` at group level.
- **Exactly one visually hidden loading message is present inside the loading skeleton branch** —
  scoped to the branch, so unrelated `.sr-only` text elsewhere in `App.tsx` cannot cause a false
  failure.
- No bare hex colour in any changed file — not only in the branch.
- The branch renders without error when `platform` is undefined.

### Integration
- With `prefers-reduced-motion: reduce`, no animation is applied.
- Light and dark both render legibly — placeholder fill visible against the container in each.
- Loading→loaded transition does not change vertical order, nor the presence of the regions §4
  specifies.

### On-host smoke test — manual, in Claude.ai, recorded
Automated DOM tests cannot establish visual seamlessness. Observe and record:

- Loading state appears with structured placeholders — no blank block, no spinner.
- Loading→loaded transition in Claude.ai, watched.
- Narrow mobile width and desktop.
- Light, dark, and reduced-motion.
- No horizontal overflow; no nested vertical scrolling introduced (M4 must still hold).

Record what was actually observed, not that the test was run.

---

## 10. Latency and data

State explicitly in the report:

**Latency.** This increment introduces no backend I/O and must not affect MCP server execution or
backend request latency. Record the bundle-size delta, because widget download, parse and first-render
time may still change. Expectation is calibrated: this replaces a text block with markup and one
keyframe, so a meaningful change would itself be a finding.

**Data.** The widget currently performs no client-side persistence, telemetry, analytics, or browser
storage. Preserve this baseline unless a separately approved increment explicitly introduces such
functionality. This maintains the current data-minimization posture under Policy §1D.

---

## 11. Before deployment

Read `doc/OPERATIONS_PREDEPLOY.md` and check for additional pre-deploy tasks specific to
widget-bundle changes.

---

## 12. Report

End with:

- Commit hash
- Before/after byte and line counts for every file in the working tree (standing check 11) — process
  evidence, which does not substitute for build and runtime results
- New `WIDGET_VERSION`, new resource URI, and the enumeration proving every reference resolves to it
- Bundle size delta and the threshold used
- The `TimeAllocationBar` decision from §4 and the evidence behind it
- Observed on-host behaviour
- An explicit list of what was **not** verified