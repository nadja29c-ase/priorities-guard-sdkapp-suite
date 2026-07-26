# Increment 1 of 2: MindSort-Claude inline accordion (expandable clusters, 500px-safe)

**App:** MindSort AI for Claude (`mcp_server/mindsort_claude/`). Anthropic MCP connector, inline widget.
**Type:** Widget UI — add one-open-at-a-time accordion expansion to the existing inline cluster-overview card, with deterministic 500px-safe bounded detail. Read-only.
**Touches:** `mcp_server/mindsort_claude/widget-react/src/` only. Does NOT touch `clarity/`, `priority_guardian_claude/`, backend, tool handlers, or the response adapter.

This is increment 1 of 2. Increment 2 (desktop fullscreen full-board) is separate and NOT part of this. Do not build fullscreen here.

## Why this exists (product context)
Anthropic's current docs confirm fullscreen is desktop/web only — "Fullscreen is not yet available on mobile—apps render inline only" (verified 2026-07-21 at the design-guidelines page). Without in-card expansion, mobile MindSort users could only ever see cluster names + counts, never the contents — too weak for MVP1. This increment gives mobile users access to cluster *contents* through in-place accordion expansion, within the inline 500px limit. Desktop additionally gets fullscreen in increment 2.

## Canonical guidance (read before implementing)
1. `doc/Claude_Compliance/design guidelines_mcpapps_claude.md` (and the live source: https://claude.com/docs/connectors/building/mcp-apps/design-guidelines).
2. `doc/Claude_Compliance/structural_guideline_claude_vs_openai_MindSortAI.md`.
Before commit: read `OPERATIONS_PREDEPLOY.md`.

## Compliance framing (affirmative — this is NOT a deviation)
In-place accordion expand/collapse is EXPLICITLY PERMITTED by the guideline: under "App vs. chat interactions / Handle within your app" it lists "Expanding and collapsing content sections." The prohibited "drill-ins, breadcrumbs, multiple views" refer to NAVIGATION to secondary screens — which this does not do. State in code comments and the increment record: **"This uses permitted in-place expand/collapse behavior and does not introduce navigation, breadcrumbs, nested views, or internal scrolling."** Do NOT frame this as a deviation — it is compliant behavior. The binding constraints it must respect are: max height 500px, auto-fit, NO nested scrolling.

---

## Design (builds on the shipped inline cluster-overview card)

### Collapsed state (unchanged from current card)
The existing cluster-overview rows stay exactly as shipped: header "Your MindSort AI Board" + `{N} clusters · {M} thoughts`; one fixed-height row per cluster; priority badge + left accent when prioritized; tag icon when tagged; thought count; priorities-first ordering; truncation to MAX_INLINE_ROWS with "+N more clusters". Do not regress any of this.

### New: one cluster expandable at a time (accordion)
- Each cluster row becomes a toggle (button, `aria-expanded`, `aria-controls`). Tapping expands that cluster's detail inline, directly beneath its row. Tapping again (or opening another) collapses it. **Only ONE cluster open at a time** — opening a new one closes the previous.
- When a cluster is expanded, **its own collapsed row REMAINS visible** (as the accordion header for the open section); the detail renders directly beneath it. This is a stated term in the layout model below — it is NOT removed from the budget.
- Match the OpenAI expanded-section ORDER (verified from `clarity/.../ClusterCard.tsx`): **(1) summary → (2) thought items → (3) subclusters → (4) tags** — but BOUNDED per the layout model, not "show everything."
- Section adaptations (OpenAI look, Claude 500px reality):
  - **Summary**: if present, ONE clamped line (1-line clamp). Consumes one detail-row-height unit.
  - **Thought items**: priority-sorted (reuse existing priority-sort logic), each a fixed-height 1-line row (clamped), rendered up to the computed capacity.
  - **Subclusters**: as NAMED ROWS with their count (`subcluster_name` + `sum_thought_items`), NOT fully-expanded nested cards. Each is one fixed-height detail row. Nesting full subcluster cards inside 500px is not feasible; the row preserves the information (exists, name, size) without unbounded height. Full subcluster contents are reachable via the overflow chat action and (increment 2) desktop fullscreen.
  - **Tags**: **DO NOT render tag pills in the expanded inline detail.** Pills wrap unpredictably (tag length/count/locale/width) — that breaks the fixed-row-height guarantee the whole budget depends on. The collapsed row's existing single tag INDICATOR (the monochrome SVG icon) already signals "this cluster has tags." Full tag pills live only in increment 2 (desktop fullscreen). This keeps every expanded row a known fixed height.

### Deterministic 500px protection — EXPLICIT LAYOUT MODEL (the crux)
Do NOT continuously measure arbitrary content and pack pixels (resize loops, flicker, host-specific failures). Use a DETERMINISTIC bounded-row strategy with a SINGLE explicit layout model in which **every visible element belongs to exactly one term**. No element may be unaccounted for.

**Row heights are bounded, not assumed.** Define collapsed-row and detail-row heights as explicit CSS dimensions (fixed height or max-height + 1-line clamp), and VERIFY them against the real Claude host (test 13). They are "bounded row heights defined by explicit CSS dimensions and verified in the real host," not magic constants.

**Total-height model — account for ALL of these terms:**
```
totalHeight =
    outerPadding                       (card padding top+bottom)
  + boardHeaderHeight                  ("Your MindSort AI Board" + counts line)
  + visibleClusterRowsHeight           (collapsedRowH × number of visible cluster rows,
                                        INCLUDING the expanded cluster's own header row)
  + expandedDetailHeight               (detailRowH × renderedDetailRows) + sectionGaps
  + overflowActionRowHeight            (the "View remaining…" chat-action row — see below;
                                        height RESERVED whenever overflow exists, BEFORE
                                        computing detail capacity)
  + boardOverflowRowHeight             ("+N more clusters" board-level row, if present)
  + actionFooterHeight                 ("Open full board" button area — always present; see Q4 note)
  + allVerticalGapsAndBorders          (every row gap, section gap, and border — enumerate them)
```
Section labels (if any) also consume height and must be a term (prefer NO section labels to save budget; if used, count them).

**Capacity computation (reserve overflow row FIRST):**
```
available = 500
          − outerPadding − boardHeaderHeight − visibleClusterRowsHeight
          − boardOverflowRowHeight − actionFooterHeight
          − allVerticalGapsAndBorders − safetyMargin
provisionalDetailCapacity = floor(available / detailRowH)
if (totalContentUnits > provisionalDetailCapacity):
    available -= overflowActionRowHeight        # reserve the chat-action row's height
    finalDetailCapacity = floor(available / detailRowH)
else:
    finalDetailCapacity = provisionalDetailCapacity
```
Render, in OpenAI order, up to `finalDetailCapacity` content units: summary (1 unit if present) → thought rows → subcluster rows. `safetyMargin` targets a threshold BELOW 500 (e.g. ≤480px) so host variance has headroom.

**Overflow control ("View remaining cluster content"):**
- Shown when `totalContentUnits > finalDetailCapacity`. Its height is RESERVED in the calc above (term `overflowActionRowHeight`), so it can never be the element that pushes the card over 500px.
- Single-line, clamped, fixed height. Label: **"View remaining cluster content"** with an optional short count, e.g. `7 thoughts, 2 subclusters` — but the whole control is ONE clamped fixed-height line (do not let a two-part count wrap into a second line).
- **Definition of the count (N):** N = hidden THOUGHT items + hidden SUBCLUSTERS, counted as content units (the same units the budget counts). If the summary was dropped for budget, that is not counted in N (it is not "remaining content," it is a display omission). State this definition in a code comment.

**ResizeObserver — GUARD ONLY, with strict termination (NOT the pagination engine):**
The deterministic calc is primary. The observer is a backstop for host-rendering variance (fonts, accessibility text scaling). It MUST:
- Target a threshold BELOW the limit (≤480px or the measured safety threshold), not exactly 500.
- Only DECREMENT the visible detail count; never increase during the same expansion lifecycle.
- Not call setState if the next count equals the current count (prevents thrash — the observer firing must not re-trigger itself via an identical state write).
- Stop at zero detail rows (never a negative count).
- Disconnect on unmount AND on cluster change; cancel any pending animation-frame/callbacks.
- Log (`[MindSort Diagnostic] guard reached zero, card still exceeds target: {height}px`) if it reaches zero detail rows and the card STILL exceeds target — that is a real failure to surface, not to swallow.
- **Do NOT claim "cannot loop."** The correct statement: "Primary layout is bounded by deterministic limits; a monotonic runtime guard handles host-rendering variance." The guard is safe because of the strict termination rules above, not because decrementing is inherently loop-proof.

**Zero-detail-capacity fallback (required):**
A narrow viewport (320px), large accessibility font, or many visible collapsed rows may leave `finalDetailCapacity <= 0`. Required behavior:
- The cluster MAY still enter expanded state.
- Render ZERO detail rows.
- Still render the "View remaining cluster content" chat-action row (fixed height) — this is the ONLY path to the content and must never be hidden.
- Never produce a negative row count.

### Overflow / expansion → real chat action — MECHANISM CONFIRMED (`load_saved_board`)
The "View remaining cluster content" control (and, in the zero-capacity case, the whole expanded cluster) routes the user to the model to see full contents. **Confirmed mechanism (2026-07-21, from reading the shipped `App.tsx` and PG-Claude widget):** the bridge exposes `callServerTool` (used today by the existing "Open full board" button). There is NO `sendPrompt`/`sendFollowup`/`requestAssistantResponse` capability in either widget. So:
1. The overflow action calls `appRef.current.callServerTool({ name: 'load_saved_board', arguments: {} })` — an EXISTING tool already wired in this file. This is in-scope (no new tool, no backend contract).
2. **KNOWN BEHAVIOR: `load_saved_board` renders the WHOLE board in conversation, NOT a single cluster.** So "View remaining cluster content" produces a whole-board render, not a cluster-scoped one. This is acceptable — it is a valid "see everything" escape hatch — but the implementer MUST note it in the report.
3. Before wiring, do a quick SDK type check to (a) confirm the negative — no `sendPrompt`-style capability — and (b) check whether a CLUSTER-SCOPED load/read tool already exists in the MindSort tool set. If a cluster-scoped tool exists, prefer it (more precise). If it does NOT exist, use `load_saved_board`; do NOT invent a cluster-scoped tool.
4. **Redundancy note (expected, flag it):** because the existing "Open full board" button ALSO calls `load_saved_board`, the overflow action and that button will do nearly the same thing (both render the full board in chat). This is not a blocker — flag it in the report so review can decide whether/how to differentiate them (e.g. label, or a future cluster-scoped tool). Do not block on it.
The control must NOT be dead text implying in-card reachability.

### Scroll behavior: expand in place, no scroll management
Do NOT build scroll-into-view. The accordion keeps everything in one view under 500px with no nested scroll, so there is nothing to scroll to. "Compliant and simple" = plain toggle, no scroll logic.

### Accessibility (WCAG AA — required, with acceptance criteria)
- Cluster toggle is a real button: **Enter AND Space** activate it.
- On activation, focus REMAINS on the activated cluster button (do not lose focus to the expanded region or document body).
- Visible focus ring using `--color-ring-primary`.
- The expanded detail region has a STABLE unique id; the toggle's `aria-controls` references that exact id; `aria-expanded` reflects state.
- The overflow control has an accessible name INCLUDING the cluster name (e.g. "View remaining content in Marketing").
- **Priority is expressed TEXTUALLY, not only through color** — the P1/P2/P3 badge text (not just the role color/left-accent) conveys priority; a screen reader must learn priority without color.
- 1-line truncation must preserve the FULL text via an accessible label (e.g. `title`/`aria-label` carrying untruncated text) so clamped content remains available to assistive tech.
- Reduced-motion: if any expand/collapse transition is used, respect `prefers-reduced-motion`.

### Tokens / typography (from the confirmed design-guidelines token table)
- Host tokens only. Priority roles: P1 `--color-*-danger`, P2 `--color-*-warning`, P3 `--color-*-info` (SAME mapping the collapsed rows already use — shared, not divergent). Text `--color-text-primary/secondary/tertiary`. Surfaces `--color-background-primary/secondary/tertiary`. Focus ring `--color-ring-primary`.
- fontWeight 400/500 only (`--font-weight-normal`/`--font-weight-medium`). No 600.
- No `@openai/apps-sdk-ui`, no `window.openai`.
- **Hex fallbacks — MATCH THE EXISTING PATTERN (revised 2026-07-21 after reading the shipped `App.tsx`).** The shipped inline card uses `var(--token, #hex)` throughout, where the hex values ARE the guideline's own token values (e.g. `#141413` = light `color-text-primary`). New accordion code MUST match this existing pattern for consistency — do NOT introduce fallback-free rows beside the existing fallback-ful rows (a mix looks arbitrary and is the worst option). Do NOT do a repo-wide fallback removal in this increment. Rationale: `var(--token, #hex)` is a degradation fallback (applies only if a token is absent), not "hardcoding a color instead of the token," and consistency within the file beats strict-reading churn during a feature increment. If strict token-only is ever wanted, it is a separate whole-file increment, not this one. (This intentionally revises an earlier stricter line; the shipped code's established convention governs.)

---

## Explicitly OUT of scope
- Desktop fullscreen full-board (increment 2).
- Full nested subcluster cards with their own thought lists (subclusters are named rows here).
- Tag pills in inline detail (indicator only; pills are increment 2).
- Any CRUD; any mutation tool call; any NEW tool or backend contract (reusing the existing `load_saved_board` is fine).
- Scroll-into-view / scroll-position persistence.
- 2-line text (1-line clamp is the deterministic choice).
- Repo-wide hex-fallback removal (match existing pattern instead).
- Changes outside `widget-react/`.

---

## Tests

**Unit (pure helpers — deterministic, no layout):**
1. Layout-model capacity calc: given all explicit constants (outerPadding, boardHeader, collapsedRowH, detailRowH, gaps/borders, safetyMargin, overflowActionRowH, actionFooterH) and K visible collapsed rows, `finalDetailCapacity` is computed correctly; the sum of all model terms at capacity is ≤ threshold (≤480). *Catches:* any unaccounted term; off-by-one.
2. Overflow-row reservation: when content exceeds provisional capacity, the overflow row's height is subtracted BEFORE final capacity; final capacity is strictly ≤ provisional. *Catches:* the overflow control pushing the card over 500.
3. Accordion state: opening cluster B when A is open closes A (exactly one open). *Catches:* multi-open leak (breaks budget).
4. Detail composition + N definition: given summary + T thoughts + S subclusters, the bounded model emits units in OpenAI order (summary → thoughts → subclusters) up to capacity, and `N = hiddenThoughts + hiddenSubclusters` (summary omission NOT counted). *Catches:* wrong order, wrong N, mixing unit types.
5. Zero-capacity fallback: when capacity ≤ 0, zero detail rows render but the overflow chat-action row still renders; count never negative. *Catches:* negative rows; hiding the only content path.
6. Priority sort within expanded thoughts uses real keys (`priority.rank`, real item shape). *Catches:* wrong keys.

**Component/render (jsdom — logic/DOM/a11y, NOT height):**
7. Collapsed card unchanged: existing inline-card tests still pass (header text, ordering, truncation, tag icon). *Catches:* regression to the shipped card.
8. Toggle: Enter AND Space expand (`aria-expanded=true`, detail visible, `aria-controls` → the region's actual id); opening another collapses the first; focus stays on the activated button. *Catches:* keyboard inaccessibility, broken aria wiring, multi-open, focus loss.
9. Overflow present when content > capacity; overflow control has accessible name including cluster name; activating it calls `callServerTool('load_saved_board', {})` (mock it; assert the call). *Catches:* dead-end overflow; wrong/missing mechanism.
10. No tag PILLS in inline detail (only the indicator on the collapsed row); priority conveyed by badge TEXT not only color. *Catches:* wrapping pills breaking fixed height; color-only priority (a11y fail).
11. Read-only: no mutation controls in expanded detail. *Catches:* CRUD creep.
12. No `@openai/apps-sdk-ui`, no `window.openai`, no NEW hardcoded color outside the existing `var(--token, #hex)` pattern. *Catches:* leaked dep / inconsistent color handling.

**Height — MANUAL, real-host (jsdom has no layout; THIS is the acceptance gate):**
13. Build a deliberate WORST-CASE fixture and test it on real Claude, desktop AND mobile at 320px width AND with increased accessibility text scaling: MAX visible collapsed cluster rows + an expanded cluster positioned NEAR THE BOTTOM + board-level "+N more clusters" present + the detail overflow action present + long localized (long-word) text. Read `[MindSort Diagnostic] scrollHeight`. Assert ≤500px, no nested scroll, no clipping, overflow control present and reachable. Repeat with each cluster expanded. State the observed MAX height across all cases in the report. (Testing only the "largest cluster" is insufficient — the worst TOTAL height is the combination above.)

Each automated test states the bug it catches. Separate unit from component. Height compliance is verified manually (test 13), not in jsdom — state this explicitly.

---

## Definition of Done
- [ ] Collapsed cluster-overview card unchanged; its tests still pass.
- [ ] One-cluster-at-a-time accordion; opening one closes the previous; expanded cluster's own row remains as the section header.
- [ ] Single explicit layout model implemented; EVERY visible element is an accounted term (including `actionFooterHeight` for the existing button); constants defined as explicit CSS dims and verified on-host.
- [ ] Overflow chat-action row height RESERVED before computing final detail capacity.
- [ ] Expanded detail matches OpenAI section order (summary → thoughts → subclusters-as-rows); NO tag pills inline (indicator only).
- [ ] 1-line clamp on all detail + overflow text; full text preserved via accessible label.
- [ ] `finalDetailCapacity` computed from constants (stated in code); targets ≤480 threshold.
- [ ] ResizeObserver guard with ALL termination rules: below-threshold target, decrement-only, no-op when count unchanged, stop at zero, disconnect on unmount/cluster-change, cancel pending rAF, log on zero-and-still-over. No "cannot loop" claim in code/comments.
- [ ] Zero-capacity fallback: expands, zero detail rows, overflow action still shown, never negative.
- [ ] Overflow control named "View remaining cluster content" (+ optional single-line count); N = hidden thoughts + subclusters.
- [ ] Overflow action calls existing `load_saved_board` (whole-board render — noted in report); SDK type-checked to confirm no `sendPrompt` and whether a cluster-scoped tool exists (use it if so, do NOT invent one); redundancy with "Open full board" flagged in report.
- [ ] Accessibility criteria met (Enter/Space, focus retention, ring, stable region id + aria-controls, accessible overflow name, textual priority, accessible-label full text, reduced-motion).
- [ ] Host tokens with `var(--token, #hex)` fallbacks MATCHING the existing pattern (no fallback-free/fallback-ful mix; no repo-wide removal); no `@openai/apps-sdk-ui`, no `window.openai`; fontWeight 400/500; priority mapping shared with collapsed rows.
- [ ] Read-only; no mutation controls or NEW tool calls.
- [ ] Compliance comment present (permitted expand/collapse, no navigation/nesting/scroll).
- [ ] Unit 1–6 + component 7–12 pass, each with its bug-caught line; state known-baseline before/after.
- [ ] Manual worst-case real-host height check (test 13) on desktop AND mobile (320px + text scaling); observed MAX height recorded.
- [ ] No change outside `mcp_server/mindsort_claude/widget-react/`.
- [ ] `OPERATIONS_PREDEPLOY.md` read before commit.
- [ ] Report ends with commit hash (review verifies against `git show <hash>:<path>`).

## Post-deploy verification
Deploy MindSort-Claude MCP only. In Claude, desktop AND mobile:
1. Board with content → tap a cluster → summary/thoughts/subcluster-rows appear beneath; card ≤500px; no nested scroll.
2. Tap another → first collapses, second expands (one open at a time).
3. Cluster with overflow → "View remaining cluster content" → activating it renders the full board in conversation (whole-board, via `load_saved_board`).
4. Zero-capacity case (narrow width / large font / many rows) → cluster expands, shows only the chat-action path; nothing hidden.
5. Keyboard: Tab to a cluster, Enter/Space expands, focus stays; screen reader announces priority and full (unclamped) text.
6. Dark mode legible; mobile tap targets ≥44pt.
7. Collapsed overview + "Open full board" still behave as before.

## Note for increment 2 (do NOT build here)
Desktop fullscreen full-board (read-only, all clusters/subclusters/thoughts fully expanded, full tag PILLS) is the next increment, gated on `hostContext.availableDisplayModes` containing 'fullscreen' (desktop/web only per current Anthropic docs; mobile stays on this accordion until Anthropic ships mobile fullscreen). "Open full board" changes to show ONLY when the host advertises fullscreen, and to switch display mode (not call `load_saved_board`). Uses the proper `requestDisplayMode` request/await flow (inspect availableDisplayModes → request → update from returned mode / host-context notification → retain inline on decline/timeout/error; never optimistic). Must NOT duplicate the host's native fullscreen close button (render an app-level exit only where the host provides none). Increment 2 is also where the overflow-action/full-board redundancy noted above should be resolved.
